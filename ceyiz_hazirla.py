#!/usr/bin/env python3
"""
╔═══════════════════════════════════════════════════════════════════╗
║  EmareCloud — Yeni Derviş Çeyiz Hazırlama Scripti                ║
║                                                                   ║
║  Her yeni Derviş projesi kurulurken bu script çalıştırılır.       ║
║  Port tahsisi ZORUNLU olarak EmareCloud panelinden yapılır.       ║
║  Manuel port girişi yasaktır (--force ile override edilebilir).   ║
╚═══════════════════════════════════════════════════════════════════╝

Kullanım:
  python3 ceyiz_hazirla.py \\
        --name "Emare MLOps"  \\
        --slug "emaremlops"   \\
        --stack python        \\
        --dc dc1              \\
        --path /Users/emre/Desktop/Emare/emaremlops

  # Başka panelle (prod yerine local):
  EMARECLOUD_PANEL=http://127.0.0.1:5555 python3 ceyiz_hazirla.py ...

  # Belirli bir port iste (uygunsa verilir, doluysa hata):
  python3 ceyiz_hazirla.py ... --preferred-port 8200

  # Sadece port sorgula (dosya oluşturma):
  python3 ceyiz_hazirla.py ... --dry-run
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Ayarlar
# ---------------------------------------------------------------------------
DEFAULT_PANEL   = os.environ.get('EMARECLOUD_PANEL', 'https://emarecloud.tr')
PANEL_TOKEN     = os.environ.get('EMARECLOUD_TOKEN', '')   # Bearer token
ALLOCATE_ENDPOINT = '/api/ports/allocate'
TIMEOUT         = 15   # saniye

STACKS = ('python', 'node', 'php', 'docker', 'go', 'rust', 'ruby', 'java', 'other')
DCS    = ('dc1', 'dc2', 'dc3', 'local', 'all')

# ---------------------------------------------------------------------------
# Panel ile iletişim
# ---------------------------------------------------------------------------

def panel_allocate(panel: str, token: str, payload: dict) -> dict:
    """EmareCloud panelinden port tahsis et."""
    url  = panel.rstrip('/') + ALLOCATE_ENDPOINT
    body = json.dumps(payload).encode('utf-8')

    headers = {
        'Content-Type': 'application/json',
        'Accept':       'application/json',
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'

    req = urllib.request.Request(url, data=body, headers=headers, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', errors='replace')
        try:
            err = json.loads(raw)
        except Exception:
            err = {'error': raw}
        return {'error': err.get('error', str(e)), '__status': e.code}
    except urllib.error.URLError as e:
        return {'error': f'Panele ulaşılamadı: {e.reason}'}


# ---------------------------------------------------------------------------
# Şablon dosyaları
# ---------------------------------------------------------------------------

def _python_env(slug: str, port: int) -> str:
    return (
        f"# {slug} — Ortam Değişkenleri\n"
        f"# Port EmareCloud panelinden tahsis edildi.\n\n"
        f"APP_NAME={slug}\n"
        f"PORT={port}\n"
        f"FLASK_ENV=development\n"
        f"SECRET_KEY=changeme_{slug}\n"
        f"DATABASE_URL=sqlite:///instance/{slug}.db\n"
    )


def _node_env(slug: str, port: int) -> str:
    return (
        f"# {slug} — Ortam Değişkenleri\n"
        f"# Port EmareCloud panelinden tahsis edildi.\n\n"
        f"APP_NAME={slug}\n"
        f"PORT={port}\n"
        f"NODE_ENV=development\n"
    )


def _php_env(slug: str, port: int) -> str:
    return (
        f"# {slug} — Ortam Değişkenleri\n"
        f"# Port EmareCloud panelinden tahsis edildi.\n\n"
        f"APP_NAME={slug}\n"
        f"APP_PORT={port}\n"
        f"APP_ENV=local\n"
        f"APP_KEY=base64:changeme\n"
    )


def _docker_compose(slug: str, port: int) -> str:
    return (
        f"# docker-compose.yml — {slug}\n"
        f"# Port EmareCloud panelinden tahsis edildi.\n\n"
        f"services:\n"
        f"  app:\n"
        f"    build: .\n"
        f"    ports:\n"
        f"      - \"{port}:{port}\"\n"
        f"    env_file: .env\n"
        f"    restart: unless-stopped\n"
    )


def _gunicorn_conf(port: int) -> str:
    return (
        f"# gunicorn.conf.py\n"
        f"# Port EmareCloud panelinden tahsis edildi.\n\n"
        f"import os\n"
        f"bind      = f\"0.0.0.0:{port}\"\n"
        f"workers   = 2\n"
        f"threads   = 2\n"
        f"timeout   = 120\n"
        f"loglevel  = 'info'\n"
    )


ENV_GENERATORS = {
    'python': _python_env,
    'node':   _node_env,
    'php':    _php_env,
    'docker': _python_env,   # docker proje de python gibi
    'go':     _python_env,
    'rust':   _python_env,
    'ruby':   _php_env,
    'java':   _python_env,
    'other':  _python_env,
}


def _deploy_json(slug: str, name: str, port: int, stack: str, dc: str, path_str: str) -> str:
    """Yeni proje için deploy.json içeriğini üretir."""
    # stack → gunicorn suffix mapping
    stack_map = {
        'python': 'python-gunicorn',
        'node':   'node-pm2',
        'php':    'php-laravel',
        'docker': 'docker',
        'go':     'python-gunicorn',
        'rust':   'python-gunicorn',
        'ruby':   'python-gunicorn',
        'java':   'docker',
        'other':  'python-gunicorn',
    }
    full_stack = stack_map.get(stack, 'python-gunicorn')

    dc_hosts = {
        'dc1': {'host': '185.189.54.104', 'ssh_port': 22},
        'dc2': {'host': '77.92.152.3',    'ssh_port': 2222},
        'dc3': {'host': None,             'ssh_port': 22},
        'local': {'host': None,           'ssh_port': 22},
    }
    dc_info = dc_hosts.get(dc, {'host': None, 'ssh_port': 22})

    remote = f'/var/www/{slug}' if dc in ('dc2', 'dc3') else f'/opt/{slug}'

    # Deploy komutları
    branch = 'main'
    if full_stack == 'python-gunicorn':
        cmds = [
            f'cd {remote}',
            f'git pull origin {branch}',
            'source venv/bin/activate && pip install -r requirements.txt -q',
            f'sudo systemctl restart {slug}',
        ]
        restart = f'systemctl status {slug} --no-pager'
    elif full_stack == 'php-laravel':
        cmds = [
            f'cd {remote}',
            f'git pull origin {branch}',
            'composer install --no-dev --optimize-autoloader --no-interaction -q',
            'php artisan migrate --force',
            'php artisan config:cache',
            'php artisan route:cache',
            'php artisan view:cache',
            f'chown -R nginx:nginx {remote}/storage {remote}/bootstrap/cache',
        ]
        restart = 'systemctl reload nginx'
    elif full_stack == 'node-pm2':
        cmds = [
            f'cd {remote}',
            f'git pull origin {branch}',
            'npm ci --silent',
            f'pm2 restart {slug} || pm2 start ecosystem.config.js',
        ]
        restart = f'pm2 status {slug}'
    elif full_stack == 'docker':
        cmds = [
            f'cd {remote}',
            f'git pull origin {branch}',
            'docker-compose pull',
            'docker-compose up -d --remove-orphans',
        ]
        restart = 'docker-compose ps'
    else:
        cmds = [f'cd {remote}', f'git pull origin {branch}']
        restart = ''

    manifest = {
        'slug':               slug,
        'name':               name,
        'github_repo':        f'emraresoftware/{slug}',
        'branch':             branch,
        'dc':                 dc,
        'server_host':        dc_info['host'],
        'server_ssh_port':    dc_info['ssh_port'],
        'remote_path':        remote,
        'stack':              full_stack,
        'port':               port,
        'domain':             '',
        'deploy_commands':    cmds,
        'restart_command':    restart,
        'auto_deploy_on_push': False,
        'health_check_url':   None,
    }
    return json.dumps(manifest, indent=2, ensure_ascii=False) + '\n'


def create_project_files(project_path: Path, slug: str, port: int, stack: str, dry_run: bool,
                         name: str = None, dc: str = 'dc1'):
    """Proje klasöründe temel dosyaları oluştur."""
    if dry_run:
        print("  [dry-run] Dosyalar oluşturulmayacak — sadece port tahsis edildi.")
        return

    project_path.mkdir(parents=True, exist_ok=True)

    # .env
    env_content = ENV_GENERATORS.get(stack, _python_env)(slug, port)
    env_file = project_path / '.env'
    if not env_file.exists():
        env_file.write_text(env_content, encoding='utf-8')
        print(f"  ✅ .env oluşturuldu  ({env_file})")
    else:
        print("  ⏭  .env zaten var, atlandı")

    # .env.example
    example_file = project_path / '.env.example'
    if not example_file.exists():
        example_file.write_text(env_content, encoding='utf-8')
        print("  ✅ .env.example oluşturuldu")

    # docker-compose.yml
    dc_file = project_path / 'docker-compose.yml'
    if not dc_file.exists():
        dc_file.write_text(_docker_compose(slug, port), encoding='utf-8')
        print("  ✅ docker-compose.yml oluşturuldu")

    if stack == 'python':
        gc_file = project_path / 'gunicorn.conf.py'
        if not gc_file.exists():
            gc_file.write_text(_gunicorn_conf(port), encoding='utf-8')
            print("  ✅ gunicorn.conf.py oluşturuldu")

    # deploy.json — merkezi deploy manifesti
    dj_file = project_path / 'deploy.json'
    if not dj_file.exists():
        dj_content = _deploy_json(slug, name or slug, port, stack, dc, str(project_path))
        dj_file.write_text(dj_content, encoding='utf-8')
        print(f"  ✅ deploy.json oluşturuldu  (port={port}, dc={dc}, stack={stack})")
    else:
        print("  ⏭  deploy.json zaten var, atlandı")

    # README
    readme = project_path / 'README.md'
    if not readme.exists():
        readme.write_text(
            f"# {slug}\n\n"
            f"> Port: **{port}** (EmareCloud panelinden tahsis edildi)\n\n"
            f"## Kurulum\n\n"
            f"```bash\ncp .env.example .env\n# .env dosyasını düzenle\n```\n",
            encoding='utf-8'
        )
        print("  ✅ README.md oluşturuldu")


# ---------------------------------------------------------------------------
# Ana akış
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Yeni Derviş projesi için çeyiz hazırla ve port tahsis et.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--name',  required=True, help='Proje adı (örn. "Emare MLOps")')
    parser.add_argument('--slug',  required=True, help='Proje slug (örn. "emaremlops")')
    parser.add_argument('--stack', choices=STACKS, default='python', help='Teknoloji yığını')
    parser.add_argument('--dc',    choices=DCS,    default='dc1',    help='Veri merkezi')
    parser.add_argument('--path',  default=None,
                        help='Proje dizini (opsiyonel, dosyaları buraya yazar)')
    parser.add_argument('--description', default=None, help='Kısa açıklama')
    parser.add_argument('--preferred-port', type=int, default=None,
                        help='Tercih edilen port numarası (panel müsaitse verir)')
    parser.add_argument('--panel', default=DEFAULT_PANEL,
                        help=f'Panel URL (varsayılan: {DEFAULT_PANEL})')
    parser.add_argument('--token', default=PANEL_TOKEN,
                        help='Bearer token (veya EMARECLOUD_TOKEN env var)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Sadece port tahsis et, dosya oluşturma')
    parser.add_argument('--force', action='store_true',
                        help='Panel erişimi olmasa bile devam et (geliştirme ortamı)')

    args = parser.parse_args()

    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║  EmareCloud Derviş Çeyiz Hazırlama Scripti           ║")
    print("╚══════════════════════════════════════════════════════╝")
    print(f"  Proje   : {args.name} ({args.slug})")
    print(f"  Yığın   : {args.stack}  |  DC: {args.dc}")
    print(f"  Panel   : {args.panel}")
    print()

    # 1. Panel'den port tahsis et
    print("🔌 EmareCloud panelinden port tahsis ediliyor...")
    payload = {
        'project_name':  args.name,
        'project_slug':  args.slug,
        'dc':            args.dc,
        'stack':         args.stack,
        'description':   args.description or f'{args.name} servisi',
        'project_path':  args.path,
    }
    if args.preferred_port:
        payload['preferred_port'] = args.preferred_port

    result = panel_allocate(args.panel, args.token, payload)

    if 'error' in result:
        status_code = result.get('__status', 0)
        print(f"  ❌ Port tahsisi başarısız: {result['error']}")

        if args.force:
            # Panel'e erişim yoksa geliştirici modu: rastgele port seç
            import random
            fallback_port = args.preferred_port or random.randint(8200, 9900)
            print(f"  ⚠️  --force aktif: geçici port {fallback_port} kullanılıyor.")
            print("  ⚠️  Bu port panele KAYITLI DEĞİL. Geliştirme sadece lokal!")
            allocated_port = fallback_port
        else:
            print()
            print("  💡 İpucu: Panel'e erişim yoksa --force ile geliştirme modunu deneyin.")
            print("  💡 Panel token gerekiyorsa EMARECLOUD_TOKEN env var'ını ayarlayın.")
            sys.exit(1)
    else:
        allocated_port = result['port']['port']
        print(f"  ✅ Port tahsis edildi: {allocated_port}")
        print(f"     Proje: {result['port']['project_name']}")
        print(f"     Durum: {result['port']['status']}")

    # 2. Proje dosyalarını oluştur
    if args.path:
        project_path = Path(args.path)
        print()
        print(f"📁 Proje dosyaları oluşturuluyor: {project_path}")
        create_project_files(project_path, args.slug, allocated_port, args.stack, args.dry_run,
                             name=args.name, dc=args.dc)

    # 3. Özet
    print()
    print("═══════════════════════════════════════════════════════")
    print("  🎉 Çeyiz hazır!")
    print(f"     Proje  : {args.name}")
    print(f"     Slug   : {args.slug}")
    print(f"     Port   : {allocated_port}")
    print(f"     Yığın  : {args.stack}")
    print(f"     DC     : {args.dc}")
    if args.path:
        print(f"     Dizin  : {args.path}")
    print()
    print(f"  Portlar: {args.panel}/api/ports")
    print("═══════════════════════════════════════════════════════")
    print()


if __name__ == '__main__':
    main()
