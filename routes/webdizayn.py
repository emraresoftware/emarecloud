"""
EmareCloud — Web Dizayn Müşteri Yönetimi
webdizayn.emarecloud.tr altında statik site barındırma.
"""

import pathlib
import re
import shutil
import subprocess
import zipfile

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from audit import log_action
from extensions import db
from models import WebDizaynClient
from rbac import permission_required

webdizayn_bp = Blueprint('webdizayn', __name__)

WEB_ROOT = pathlib.Path('/var/www/webdizayn')
UPLOAD_TMP = pathlib.Path('/tmp/webdizayn_uploads')
ALLOWED_EXT = {'.html', '.css', '.js', '.png', '.jpg', '.jpeg', '.gif',
               '.svg', '.ico', '.woff', '.woff2', '.ttf', '.eot', '.json',
               '.webp', '.avif', '.mp4', '.webm', '.pdf', '.map'}


def _safe_slug(slug: str) -> bool:
    return bool(re.match(r'^[a-z0-9][a-z0-9_-]{1,60}$', slug))


# ── Panel Sayfası ─────────────────────────────────────────────

@webdizayn_bp.route('/webdizayn')
@login_required
@permission_required('admin.access')
def webdizayn_panel():
    clients = WebDizaynClient.query.order_by(WebDizaynClient.created_at.desc()).all()
    return render_template('webdizayn_panel.html', clients=clients)


# ── API: Müşteri Listesi ──────────────────────────────────────

@webdizayn_bp.route('/api/webdizayn/clients', methods=['GET'])
@login_required
@permission_required('admin.access')
def api_list_clients():
    clients = WebDizaynClient.query.order_by(WebDizaynClient.created_at.desc()).all()
    return jsonify({'success': True, 'clients': [c.to_dict() for c in clients]})


# ── API: Yeni Müşteri Ekle ────────────────────────────────────

@webdizayn_bp.route('/api/webdizayn/clients', methods=['POST'])
@login_required
@permission_required('admin.access')
def api_create_client():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    slug = (data.get('slug') or '').strip().lower()
    description = (data.get('description') or '').strip()
    contact = (data.get('contact') or '').strip()

    if not name:
        return jsonify({'success': False, 'message': 'İsim zorunludur'}), 400
    if not slug:
        # slug'u isimden otomatik üret
        tr_map = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosuCGIOSU')
        slug = re.sub(r'[^a-z0-9]+', '-', name.translate(tr_map).lower()).strip('-')
    if not _safe_slug(slug):
        return jsonify({'success': False, 'message': 'Slug sadece küçük harf, rakam, - ve _ içerebilir'}), 400
    if WebDizaynClient.query.filter_by(slug=slug).first():
        return jsonify({'success': False, 'message': f'"{slug}" slug zaten kullanılıyor'}), 409

    # Klasörü oluştur
    site_dir = WEB_ROOT / slug
    try:
        site_dir.mkdir(parents=True, exist_ok=True)
        # SELinux: nginx'in okuyabilmesi için httpd_sys_content_t context ata
        subprocess.run(['restorecon', '-Rv', str(site_dir)], capture_output=True)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Klasör oluşturulamadı: {e}'}), 500

    client = WebDizaynClient(
        slug=slug, name=name,
        description=description, contact=contact,
        added_by=current_user.id,
    )
    db.session.add(client)
    db.session.commit()

    log_action('webdizayn.create', target_type='webdizayn', target_id=slug,
               details={'name': name, 'url': client.public_url})
    return jsonify({'success': True, 'message': 'Müşteri eklendi', 'client': client.to_dict()})


# ── API: Müşteri Güncelle ─────────────────────────────────────

@webdizayn_bp.route('/api/webdizayn/clients/<slug>', methods=['PUT'])
@login_required
@permission_required('admin.access')
def api_update_client(slug):
    client = WebDizaynClient.query.filter_by(slug=slug).first_or_404()
    data = request.get_json(silent=True) or {}
    if 'name' in data:
        client.name = (data['name'] or '').strip() or client.name
    if 'description' in data:
        client.description = (data['description'] or '').strip()
    if 'contact' in data:
        client.contact = (data['contact'] or '').strip()
    if 'is_active' in data:
        client.is_active = bool(data['is_active'])
    db.session.commit()
    return jsonify({'success': True, 'message': 'Güncellendi', 'client': client.to_dict()})


# ── API: Müşteri Sil ──────────────────────────────────────────

@webdizayn_bp.route('/api/webdizayn/clients/<slug>', methods=['DELETE'])
@login_required
@permission_required('admin.access')
def api_delete_client(slug):
    client = WebDizaynClient.query.filter_by(slug=slug).first_or_404()
    name = client.name
    # Klasörü sil
    site_dir = WEB_ROOT / slug
    try:
        if site_dir.exists():
            shutil.rmtree(site_dir)
    except Exception as e:
        return jsonify({'success': False, 'message': f'Klasör silinemedi: {e}'}), 500
    db.session.delete(client)
    db.session.commit()
    log_action('webdizayn.delete', target_type='webdizayn', target_id=slug,
               details={'name': name})
    return jsonify({'success': True, 'message': f'{name} silindi'})


# ── API: Dosya Yükle (ZIP) ────────────────────────────────────

@webdizayn_bp.route('/api/webdizayn/clients/<slug>/upload', methods=['POST'])
@login_required
@permission_required('admin.access')
def api_upload_files(slug):
    client = WebDizaynClient.query.filter_by(slug=slug).first_or_404()

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Dosya seçilmedi'}), 400

    f = request.files['file']
    if not f.filename.endswith('.zip'):
        return jsonify({'success': False, 'message': 'Sadece .zip dosyası kabul edilir'}), 400

    # Geçici dosyaya kaydet
    UPLOAD_TMP.mkdir(parents=True, exist_ok=True)
    tmp_zip = UPLOAD_TMP / f'{slug}_upload.zip'
    f.save(tmp_zip)

    site_dir = WEB_ROOT / slug

    try:
        with zipfile.ZipFile(tmp_zip, 'r') as zf:
            # Güvenlik: path traversal engelle
            for member in zf.namelist():
                member_path = pathlib.Path(member)
                if member_path.is_absolute() or '..' in member_path.parts:
                    return jsonify({'success': False, 'message': 'ZIP içinde güvenli olmayan yol var'}), 400
                ext = pathlib.Path(member).suffix.lower()
                if ext and ext not in ALLOWED_EXT:
                    return jsonify({'success': False, 'message': f'İzin verilmeyen dosya uzantısı: {ext}'}), 400

            # Mevcut dosyaları temizle, yenileri çıkar
            if site_dir.exists():
                shutil.rmtree(site_dir)
            site_dir.mkdir(parents=True)

            # ZIP içinde tek bir üst klasör varsa onu soy (build/ vs.)
            names = [n for n in zf.namelist() if n.strip('/')]
            tops = {n.split('/')[0] for n in names}
            single_root = len(tops) == 1 and all(n.startswith(list(tops)[0] + '/') for n in names if '/' in n)

            for member in zf.namelist():
                if member.endswith('/'):
                    continue
                if single_root:
                    rel = '/'.join(member.split('/')[1:])
                    if not rel:
                        continue
                else:
                    rel = member
                dest = site_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(dest, 'wb') as dst:
                    shutil.copyfileobj(src, dst)

        # SELinux: ZIP çıkarıldıktan sonra httpd_sys_content_t context ata
        subprocess.run(['restorecon', '-Rv', str(site_dir)], capture_output=True)

    except zipfile.BadZipFile:
        return jsonify({'success': False, 'message': 'Geçersiz ZIP dosyası'}), 400
    finally:
        tmp_zip.unlink(missing_ok=True)

    files_count = sum(1 for _ in site_dir.rglob('*') if _.is_file())
    log_action('webdizayn.upload', target_type='webdizayn', target_id=slug,
               details={'name': client.name, 'files': files_count})
    return jsonify({
        'success': True,
        'message': f'{files_count} dosya yüklendi',
        'url': client.public_url,
    })


# ── API: Dosyaları Listele ────────────────────────────────────

@webdizayn_bp.route('/api/webdizayn/clients/<slug>/files', methods=['GET'])
@login_required
@permission_required('admin.access')
def api_list_files(slug):
    WebDizaynClient.query.filter_by(slug=slug).first_or_404()
    site_dir = WEB_ROOT / slug
    if not site_dir.exists():
        return jsonify({'success': True, 'files': []})
    files = [
        {'path': str(p.relative_to(site_dir)), 'size': p.stat().st_size}
        for p in site_dir.rglob('*') if p.is_file()
    ]
    files.sort(key=lambda x: x['path'])
    return jsonify({'success': True, 'files': files, 'count': len(files)})
