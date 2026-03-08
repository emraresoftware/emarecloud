"""
EmareCloud — Web IDE API Route'ları
Sunucu dosya sistemi üzerinde okuma/yazma/listeleme işlemleri.
Monaco Editor + xterm.js + AI Chat paneli için backend.
"""

import os

from flask import Blueprint, jsonify, request
from flask_login import login_required

from core.helpers import get_server_by_id, ssh_mgr
from rbac import permission_required

ide_bp = Blueprint('ide', __name__)


# ── Güvenlik: izin verilmeyen dizinler ve dosyalar ─────────────────
BLOCKED_PATHS = {'/proc', '/sys', '/dev', '/run/secrets'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def _safe_path(path: str) -> str:
    """Path traversal saldırılarını engeller."""
    p = os.path.normpath(path or '/')
    if '..' in p.split('/'):
        return '/'
    for blocked in BLOCKED_PATHS:
        if p.startswith(blocked):
            return '/'
    return p


def _get_language(filename: str) -> str:
    """Dosya uzantısına göre Monaco Editor dil tanımını döndürür."""
    ext_map = {
        '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
        '.jsx': 'javascript', '.tsx': 'typescript', '.json': 'json',
        '.html': 'html', '.htm': 'html', '.css': 'css', '.scss': 'scss',
        '.less': 'less', '.xml': 'xml', '.yaml': 'yaml', '.yml': 'yaml',
        '.md': 'markdown', '.sh': 'shell', '.bash': 'shell',
        '.zsh': 'shell', '.fish': 'shell',
        '.sql': 'sql', '.rb': 'ruby', '.go': 'go', '.rs': 'rust',
        '.java': 'java', '.kt': 'kotlin', '.c': 'c', '.cpp': 'cpp',
        '.h': 'c', '.hpp': 'cpp', '.cs': 'csharp', '.php': 'php',
        '.lua': 'lua', '.r': 'r', '.swift': 'swift',
        '.toml': 'toml', '.ini': 'ini', '.cfg': 'ini',
        '.dockerfile': 'dockerfile', '.tf': 'hcl',
        '.vue': 'html', '.svelte': 'html',
        '.conf': 'plaintext', '.log': 'plaintext', '.txt': 'plaintext',
        '.env': 'plaintext', '.gitignore': 'plaintext',
        '.makefile': 'plaintext',
    }
    name = (filename or '').lower()
    if name == 'dockerfile':
        return 'dockerfile'
    if name == 'makefile':
        return 'plaintext'
    _, ext = os.path.splitext(name)
    return ext_map.get(ext, 'plaintext')


# ── Dosya Listele ──────────────────────────────────────────────────
@ide_bp.route('/api/ide/<int:server_id>/ls')
@login_required
@permission_required('terminal.access')
def list_files(server_id):
    """Dizin içeriğini listeler."""
    path = _safe_path(request.args.get('path', '/'))

    server = get_server_by_id(server_id)
    if not server:
        return jsonify(success=False, message='Sunucu bulunamadı'), 404

    cmd = (
        f"ls -laF --time-style=long-iso {path!r} 2>/dev/null | tail -n +2"
    )
    ok, out, err = ssh_mgr.execute_command(str(server_id), cmd, timeout=10)
    if not ok and not out:
        return jsonify(success=False, message=err or 'Dizin okunamadı')

    items = []
    for line in out.strip().split('\n'):
        if not line.strip():
            continue
        parts = line.split(None, 7)
        if len(parts) < 8:
            continue
        perms = parts[0]
        size = parts[4]
        date = parts[5]
        time_str = parts[6]
        name = parts[7]

        # Sembolik link hedefini temizle
        if ' -> ' in name:
            name = name.split(' -> ')[0]

        # Gizli . ve .. atla
        if name in ('.', '..', './', '../'):
            continue

        is_dir = perms.startswith('d')
        is_link = perms.startswith('l')

        # Trailing slash veya @ temizle
        clean_name = name.rstrip('/@*')

        items.append({
            'name': clean_name,
            'path': os.path.join(path, clean_name),
            'is_dir': is_dir,
            'is_link': is_link,
            'size': int(size) if size.isdigit() else 0,
            'perms': perms,
            'modified': f'{date} {time_str}',
            'language': _get_language(clean_name) if not is_dir else None,
        })

    # Klasörler önce, sonra dosyalar (isme göre)
    items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

    return jsonify(success=True, path=path, items=items)


# ── Dosya Oku ──────────────────────────────────────────────────────
@ide_bp.route('/api/ide/<int:server_id>/read')
@login_required
@permission_required('terminal.access')
def read_file_content(server_id):
    """Dosya içeriğini okur."""
    path = _safe_path(request.args.get('path', ''))
    if not path or path == '/':
        return jsonify(success=False, message='Dosya yolu gerekli')

    server = get_server_by_id(server_id)
    if not server:
        return jsonify(success=False, message='Sunucu bulunamadı'), 404

    # Önce dosya boyutunu kontrol et
    ok, out, _ = ssh_mgr.execute_command(
        str(server_id), f"stat -c '%s' {path!r} 2>/dev/null", timeout=5
    )
    if ok and out.strip().isdigit():
        fsize = int(out.strip())
        if fsize > MAX_FILE_SIZE:
            return jsonify(
                success=False,
                message=f'Dosya çok büyük ({fsize // 1024 // 1024} MB). Maks: {MAX_FILE_SIZE // 1024 // 1024} MB'
            )

    # Binary kontrolü
    ok2, out2, _ = ssh_mgr.execute_command(
        str(server_id), f"file -b --mime-encoding {path!r} 2>/dev/null", timeout=5
    )
    encoding = out2.strip() if ok2 else ''
    if encoding == 'binary':
        return jsonify(success=False, message='Binary dosya editörde açılamaz')

    # Dosyayı oku
    ok, content, err = ssh_mgr.execute_command(
        str(server_id), f"cat {path!r} 2>/dev/null", timeout=15
    )
    if not ok and not content:
        return jsonify(success=False, message=err or 'Dosya okunamadı')

    filename = os.path.basename(path)
    return jsonify(
        success=True,
        path=path,
        filename=filename,
        content=content,
        language=_get_language(filename),
        encoding=encoding or 'utf-8',
    )


# ── Dosya Yaz ─────────────────────────────────────────────────────
@ide_bp.route('/api/ide/<int:server_id>/write', methods=['POST'])
@login_required
@permission_required('terminal.access')
def write_file_content(server_id):
    """Dosya içeriğini kaydeder."""
    data = request.get_json(silent=True) or {}
    path = _safe_path(data.get('path', ''))
    content = data.get('content', '')

    if not path or path == '/':
        return jsonify(success=False, message='Dosya yolu gerekli')

    server = get_server_by_id(server_id)
    if not server:
        return jsonify(success=False, message='Sunucu bulunamadı'), 404

    if len(content.encode('utf-8')) > MAX_FILE_SIZE:
        return jsonify(success=False, message='Dosya boyutu limiti aşıldı')

    # Yedek al
    ssh_mgr.execute_command(
        str(server_id),
        f"cp {path!r} {path!r}.emarecloud.bak 2>/dev/null",
        timeout=5,
    )

    # base64 ile güvenli yazma (özel karakter sorunlarını önler)
    import base64
    b64 = base64.b64encode(content.encode('utf-8')).decode('ascii')
    cmd = f"echo '{b64}' | base64 -d > {path!r}"
    ok, _, err = ssh_mgr.execute_command(str(server_id), cmd, timeout=15)

    if not ok:
        return jsonify(success=False, message=err or 'Dosya yazılamadı')

    return jsonify(success=True, message='Dosya kaydedildi')


# ── Dosya Ara ──────────────────────────────────────────────────────
@ide_bp.route('/api/ide/<int:server_id>/search')
@login_required
@permission_required('terminal.access')
def search_files(server_id):
    """Dosya içeriklerinde arama yapar."""
    query = request.args.get('q', '').strip()
    path = _safe_path(request.args.get('path', '/'))
    if not query:
        return jsonify(success=False, message='Arama terimi gerekli')

    server = get_server_by_id(server_id)
    if not server:
        return jsonify(success=False, message='Sunucu bulunamadı'), 404

    # grep ile arama — max 50 sonuç
    safe_q = query.replace("'", "'\\''")
    cmd = f"grep -rnl --include='*' -m 50 '{safe_q}' {path!r} 2>/dev/null | head -50"
    ok, out, _ = ssh_mgr.execute_command(str(server_id), cmd, timeout=15)

    results = []
    if out:
        for fpath in out.strip().split('\n'):
            if fpath.strip():
                results.append({
                    'path': fpath.strip(),
                    'name': os.path.basename(fpath.strip()),
                })

    return jsonify(success=True, query=query, results=results)


# ── Dosya/Klasör Oluştur ──────────────────────────────────────────
@ide_bp.route('/api/ide/<int:server_id>/create', methods=['POST'])
@login_required
@permission_required('terminal.access')
def create_item(server_id):
    """Yeni dosya veya klasör oluşturur."""
    data = request.get_json(silent=True) or {}
    path = _safe_path(data.get('path', ''))
    item_type = data.get('type', 'file')  # 'file' veya 'dir'

    if not path or path == '/':
        return jsonify(success=False, message='Yol gerekli')

    server = get_server_by_id(server_id)
    if not server:
        return jsonify(success=False, message='Sunucu bulunamadı'), 404

    if item_type == 'dir':
        cmd = f"mkdir -p {path!r}"
    else:
        cmd = f"mkdir -p $(dirname {path!r}) && touch {path!r}"

    ok, _, err = ssh_mgr.execute_command(str(server_id), cmd, timeout=10)
    if not ok:
        return jsonify(success=False, message=err or 'Oluşturulamadı')

    return jsonify(success=True, message=f'{"Klasör" if item_type == "dir" else "Dosya"} oluşturuldu')


# ── Dosya/Klasör Sil ──────────────────────────────────────────────
@ide_bp.route('/api/ide/<int:server_id>/delete', methods=['POST'])
@login_required
@permission_required('terminal.access')
def delete_item(server_id):
    """Dosya veya klasör siler."""
    data = request.get_json(silent=True) or {}
    path = _safe_path(data.get('path', ''))

    if not path or path == '/':
        return jsonify(success=False, message='Root silinemez')

    server = get_server_by_id(server_id)
    if not server:
        return jsonify(success=False, message='Sunucu bulunamadı'), 404

    # Güvenlik: kritik yolları engelle
    critical = {'/', '/etc', '/bin', '/sbin', '/usr', '/var', '/boot', '/lib', '/root', '/home'}
    if path in critical:
        return jsonify(success=False, message='Kritik sistem yolu silinemez')

    cmd = f"rm -rf {path!r}"
    ok, _, err = ssh_mgr.execute_command(str(server_id), cmd, timeout=10)
    if not ok:
        return jsonify(success=False, message=err or 'Silinemedi')

    return jsonify(success=True, message='Silindi')


# ── Dosya/Klasör Yeniden Adlandır ─────────────────────────────────
@ide_bp.route('/api/ide/<int:server_id>/rename', methods=['POST'])
@login_required
@permission_required('terminal.access')
def rename_item(server_id):
    """Dosya/klasör adını değiştirir."""
    data = request.get_json(silent=True) or {}
    old_path = _safe_path(data.get('old_path', ''))
    new_path = _safe_path(data.get('new_path', ''))

    if not old_path or not new_path:
        return jsonify(success=False, message='Eski ve yeni yol gerekli')

    server = get_server_by_id(server_id)
    if not server:
        return jsonify(success=False, message='Sunucu bulunamadı'), 404

    cmd = f"mv {old_path!r} {new_path!r}"
    ok, _, err = ssh_mgr.execute_command(str(server_id), cmd, timeout=10)
    if not ok:
        return jsonify(success=False, message=err or 'Yeniden adlandırılamadı')

    return jsonify(success=True, message='Yeniden adlandırıldı')
