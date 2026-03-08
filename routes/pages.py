"""
EmareCloud — Sayfa Route'ları
Dashboard, market, server_detail, terminal, virtualization, storage, server_map sayfaları.
"""

import json
import subprocess

from flask import Blueprint, jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required

from core.helpers import get_app_settings, get_server_by_id, get_servers_for_sidebar, monitor, ssh_mgr
from license_manager import verify_license
from market_apps import get_all_apps, get_apps_by_category, get_categories, get_emare_projects, get_stack_bundles
from rbac import permission_required, role_required

pages_bp = Blueprint('pages', __name__)


@pages_bp.route('/landing')
def landing():
    """Pazarlama landing page — giriş gerekmez."""
    return render_template('landing.html')


@pages_bp.route('/health')
def health():
    from flask import current_app, jsonify
    return jsonify({
        'ok': True,
        'app': 'EmareCloud',
        'version': current_app.config.get('APP_VERSION', '1.0.0'),
    }), 200


@pages_bp.route('/')
def index():
    """Kök URL — giriş yapılmışsa dashboard, yoksa landing page."""
    if current_user.is_authenticated:
        return redirect(url_for('pages.dashboard'))
    return render_template('landing.html')


@pages_bp.route('/dashboard')
@login_required
def dashboard():
    try:
        settings = get_app_settings()
        servers = get_servers_for_sidebar()
        return render_template('dashboard.html',
                               servers=servers, settings=settings,
                               total=len(servers),
                               online=sum(1 for s in servers if s.get('reachable')),
                               connected=sum(1 for s in servers if s.get('connected')))
    except Exception as e:
        return render_template('dashboard.html',
                               servers=[], settings={},
                               total=0, online=0, connected=0,
                               error_message=str(e)), 200


@pages_bp.route('/market')
@login_required
@permission_required('market.view')
def market_page():
    return render_template('market.html',
                           servers=get_servers_for_sidebar(),
                           apps=get_all_apps(),
                           categories=get_categories(),
                           apps_by_category=get_apps_by_category(),
                           stacks=get_stack_bundles(),
                           emare_projects=get_emare_projects())


@pages_bp.route('/app-builder')
@login_required
@permission_required('market.view')
def app_builder_page():
    """No-Code AI App Builder sayfası."""
    return render_template('app_builder.html',
                           servers=get_servers_for_sidebar())


@pages_bp.route('/ai-wizard')
@login_required
def ai_wizard_page():
    """AI Use-Case Wizard — 3 soruda tam AI çözüm."""
    return render_template('ai_wizard.html',
                           servers=get_servers_for_sidebar())


@pages_bp.route('/ai-cost')
@login_required
def ai_cost_page():
    """AI Cost Forecasting paneli."""
    return render_template('ai_cost.html',
                           servers=get_servers_for_sidebar())


@pages_bp.route('/ai-logs')
@login_required
def ai_logs_page():
    """AI Log Intelligence — Anomali tespit paneli."""
    return render_template('ai_logs.html',
                           servers=get_servers_for_sidebar())


@pages_bp.route('/ai-revenue')
@login_required
def ai_revenue_page():
    """AI Gelir Paylaşımı Dashboard — kazanç takibi."""
    return render_template('ai_revenue.html',
                           servers=get_servers_for_sidebar())


@pages_bp.route('/ai-server-recommend')
@login_required
def ai_server_recommend_page():
    """AI Sunucu Öneri Motoru — bütçeye göre sunucu önerisi."""
    return render_template('ai_server_recommend.html',
                           servers=get_servers_for_sidebar())


@pages_bp.route('/ai-performance')
@login_required
def ai_performance_page():
    """AI Model Performance Skor — market uygulamaları kalite sıralaması."""
    return render_template('ai_performance.html',
                           servers=get_servers_for_sidebar())


@pages_bp.route('/ai-security')
@login_required
def ai_security_page():
    """AI Güvenlik & Uyumluluk Denetçisi — GDPR/KVKK taraması."""
    return render_template('ai_security.html',
                           servers=get_servers_for_sidebar())


@pages_bp.route('/token-payment')
@login_required
def token_payment_page():
    """EMARE Token ile abonelik satın alma sayfası."""
    from flask import current_app
    from models import Plan

    plans = Plan.query.filter_by(is_active=True).order_by(Plan.sort_order).all()
    token_address = current_app.config.get('EMARE_TOKEN_ADDRESS', '')
    payment_address = current_app.config.get('EMARE_PAYMENT_ADDRESS', '')
    chain_id = current_app.config.get('BLOCKCHAIN_CHAIN_ID', 31337)
    blockchain_enabled = current_app.config.get('BLOCKCHAIN_ENABLED', False)

    from flask_login import current_user
    from models import Organization
    user_org = None
    if current_user.org_id:
        user_org = Organization.query.get(current_user.org_id)

    return render_template(
        'token_payment.html',
        servers=get_servers_for_sidebar(),
        plans=plans,
        token_address=token_address,
        payment_address=payment_address,
        chain_id=chain_id,
        blockchain_enabled=blockchain_enabled,
        user_org=user_org,
    )


@pages_bp.route('/server/<server_id>')
@login_required
@permission_required('server.view')
def server_detail(server_id):
    server = get_server_by_id(server_id)
    if not server:
        return redirect(url_for('pages.dashboard'))
    sv = {k: v for k, v in server.items() if k != 'password'}
    sv['reachable'], sv['latency'] = ssh_mgr.check_server_reachable(
        server['host'], server.get('port', 22))
    sv['connected'] = ssh_mgr.is_connected(server_id)
    metrics = None
    if sv['connected']:
        metrics = monitor.get_all_metrics(server_id)
    return render_template('server_detail.html',
                           server=sv, metrics=metrics,
                           servers=get_servers_for_sidebar())


@pages_bp.route('/terminal')
@login_required
@permission_required('terminal.access')
def terminal_index():
    """Sunucu ID'siz /terminal isteğini dashboard'a yönlendir."""
    return redirect(url_for('pages.dashboard'))


@pages_bp.route('/terminal/<server_id>')
@login_required
@permission_required('terminal.access')
def terminal_page(server_id):
    server = get_server_by_id(server_id)
    if not server:
        return redirect(url_for('pages.dashboard'))
    sv = {k: v for k, v in server.items() if k != 'password'}
    name = (server.get('name') or '')[:30]
    host = (server.get('host') or '')[:32]
    sv['display_name'] = name + ' ' * (30 - len(name))
    sv['display_host'] = host + ' ' * (32 - len(host))
    sv['reachable'], sv['latency'] = ssh_mgr.check_server_reachable(
        server['host'], server.get('port', 22))
    sv['connected'] = ssh_mgr.is_connected(server_id)
    return render_template('terminal.html', server=sv,
                           servers=get_servers_for_sidebar())


@pages_bp.route('/ide/<server_id>')
@login_required
@permission_required('terminal.access')
def ide_page(server_id):
    """Web IDE — VS Code benzeri tarayıcı tabanlı editör."""
    server = get_server_by_id(server_id)
    if not server:
        return redirect(url_for('pages.dashboard'))
    sv = {k: v for k, v in server.items() if k != 'password'}
    sv['reachable'], sv['latency'] = ssh_mgr.check_server_reachable(
        server['host'], server.get('port', 22))
    sv['connected'] = ssh_mgr.is_connected(server_id)
    return render_template('ide.html', server=sv,
                           servers=get_servers_for_sidebar())


@pages_bp.route('/virtualization')
@login_required
@permission_required('vm.view')
def virtualization_page():
    return render_template('virtualization.html', servers=get_servers_for_sidebar())


@pages_bp.route('/storage')
@login_required
@permission_required('storage.view')
def storage_page():
    return render_template('storage.html', servers=get_servers_for_sidebar())


@pages_bp.route('/monitoring')
@login_required
@permission_required('monitoring.view')
def monitoring_page():
    return render_template('monitoring.html', servers=get_servers_for_sidebar())


@pages_bp.route('/api/license', methods=['GET'])
@login_required
@role_required('super_admin', 'admin')
def api_license_info():
    """Lisans bilgilerini döndürür."""
    info = verify_license()
    return jsonify({'success': True, 'license': info.to_dict() if info else None})


@pages_bp.route('/ai-optimizer')
@login_required
def ai_optimizer_page():
    """Auto AI Resource Optimizer paneli."""
    return render_template('ai_optimizer.html', servers=get_servers_for_sidebar())


@pages_bp.route('/ai-marketplace')
@login_required
def ai_marketplace_page():
    """AI Model Marketplace — model satış."""
    return render_template('ai_marketplace.html', servers=get_servers_for_sidebar())


@pages_bp.route('/ai-saas-builder')
@login_required
def ai_saas_builder_page():
    """One-Click AI SaaS Builder."""
    return render_template('ai_saas_builder.html', servers=get_servers_for_sidebar())


@pages_bp.route('/ai-gpu-pool')
@login_required
def ai_gpu_pool_page():
    """AI Auto-Scaling GPU Pool."""
    return render_template('ai_gpu_pool.html', servers=get_servers_for_sidebar())


@pages_bp.route('/ai-whitelabel')
@login_required
def ai_whitelabel_page():
    """White-Label AI Platform (Reseller Edition)."""
    return render_template('ai_whitelabel.html', servers=get_servers_for_sidebar())


@pages_bp.route('/ai-community-templates')
@login_required
def ai_community_templates_page():
    """Topluluk AI Şablon Paylaşımı."""
    return render_template('ai_community_templates.html', servers=get_servers_for_sidebar())


@pages_bp.route('/ai-training')
@login_required
def ai_training_page():
    """Entegre AI Model Eğitim Laboratuvarı."""
    return render_template('ai_training.html', servers=get_servers_for_sidebar())


@pages_bp.route('/ai-orchestrator')
@login_required
def ai_orchestrator_page():
    """Çoklu AI Model Orkestratörü."""
    return render_template('ai_orchestrator.html', servers=get_servers_for_sidebar())


@pages_bp.route('/ai-backup')
@login_required
def ai_backup_page():
    """AI Tabanlı Otomatik Yedekleme & Restore."""
    return render_template('ai_backup.html', servers=get_servers_for_sidebar())


@pages_bp.route('/ai-isolation')
@login_required
def ai_isolation_page():
    """Multi-Tenant Isolation Guard."""
    return render_template('ai_isolation.html', servers=get_servers_for_sidebar())


@pages_bp.route('/ai-migration')
@login_required
def ai_migration_page():
    """Zero-Downtime Migration Assistant."""
    return render_template('ai_migration.html', servers=get_servers_for_sidebar())


@pages_bp.route('/ai-voice')
@login_required
def ai_voice_page():
    """Voice-Controlled AI Admin."""
    return render_template('ai_voice.html', servers=get_servers_for_sidebar())


@pages_bp.route('/ai-market-intel')
@login_required
def ai_market_intel_page():
    """AI Marketplace Intelligence Dashboard."""
    return render_template('ai_market_intel.html', servers=get_servers_for_sidebar())


@pages_bp.route('/ai-self-healing')
@login_required
def ai_self_healing_page():
    """Self-Healing AI Infrastructure."""
    return render_template('ai_self_healing.html', servers=get_servers_for_sidebar())


@pages_bp.route('/ai-landing-gen')
@login_required
def ai_landing_gen_page():
    """AI Landing Page & Sales Funnel Generator."""
    return render_template('ai_landing_gen.html', servers=get_servers_for_sidebar())


@pages_bp.route('/ai-cross-cloud')
@login_required
def ai_cross_cloud_page():
    """Cross-Cloud AI Sync & Failover."""
    return render_template('ai_cross_cloud.html', servers=get_servers_for_sidebar())


@pages_bp.route('/ai-ethics')
@login_required
def ai_ethics_page():
    """AI Ethics & Bias Auditor."""
    return render_template('ai_ethics.html', servers=get_servers_for_sidebar())


@pages_bp.route('/ai-mastery')
@login_required
def ai_mastery_page():
    """Gamified AI Mastery Path."""
    return render_template('ai_mastery.html', servers=get_servers_for_sidebar())


@pages_bp.route('/ai-sandbox')
@login_required
def ai_sandbox_page():
    """Instant AI Demo Sandbox."""
    return render_template('ai_sandbox.html', servers=get_servers_for_sidebar())


@pages_bp.route('/cloudflare')
@login_required
def cloudflare_page():
    """Cloudflare DNS & CDN Yönetimi."""
    return render_template('cloudflare.html', servers=get_servers_for_sidebar())


# ── EmareFirewall — Güvenlik Duvarı Yönetimi ────────────────
@pages_bp.route('/firewall')
@login_required
@permission_required('firewall.view')
def firewall_page():
    """EmareFirewall — Güvenlik duvarı yönetim paneli."""
    return render_template('firewall.html', servers=get_servers_for_sidebar())


# ── Data Center Yönetimi ────────────────────────────────────
@pages_bp.route('/datacenters')
@login_required
def datacenters_page():
    """Veri Merkezi (DC) yönetim sayfası."""
    return render_template('datacenters.html', servers=get_servers_for_sidebar())


# ── Geliştirici Scoreboard ──────────────────────────────────
@pages_bp.route('/scoreboard')
@login_required
def scoreboard_page():
    """Geliştirici aktivite panosu."""
    return render_template('scoreboard.html', servers=get_servers_for_sidebar())


# ── Server Map ──────────────────────────────────────────────
@pages_bp.route('/server-map')
@login_required
def server_map_page():
    """Sunucu mimarisi görsel haritası."""
    return render_template(
        'server_map.html',
        servers=get_servers_for_sidebar(),
        is_admin=current_user.is_admin,
    )


def _run(cmd: str, timeout: int = 5) -> str:
    """Run a shell command and return stripped stdout, or empty string on error."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ''


@pages_bp.route('/api/server-map', methods=['GET'])
@login_required
def api_server_map():
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Yetkisiz erişim'}), 403
    """Sunucu servis durumlarını JSON olarak döndürür."""
    # --- systemd services ---
    svc_names = ['nginx', 'emarecloud', 'firewalld', 'sshd']
    services = {}
    for name in svc_names:
        active = _run(f'systemctl is-active {name}') == 'active'
        # Map emarecloud → gunicorn for frontend
        key = 'gunicorn' if name == 'emarecloud' else name
        services[key] = {'active': active}

    # --- versions ---
    py_ver = _run('python3 --version').replace('Python ', '')
    node_ver = _run('node --version').lstrip('v')
    nginx_ver = _run("nginx -v 2>&1 | grep -oP '[\\d.]+'")

    # --- SELinux ---
    selinux = _run('getenforce')

    # --- firewall ports ---
    ports = _run('firewall-cmd --list-ports 2>/dev/null')

    # --- PM2 processes ---
    pm2_raw = _run('pm2 jlist 2>/dev/null')
    pm2_procs = []
    if pm2_raw:
        try:
            for p in json.loads(pm2_raw):
                mem_bytes = p.get('monit', {}).get('memory', 0)
                mem_mb = f"{mem_bytes / 1048576:.1f} MB" if mem_bytes else '—'
                pm2_procs.append({
                    'name': p.get('name', ''),
                    'pid': p.get('pid', 0),
                    'status': p.get('pm2_env', {}).get('status', 'unknown'),
                    'memory': mem_mb,
                    'cpu': p.get('monit', {}).get('cpu', 0),
                    'uptime': p.get('pm2_env', {}).get('pm_uptime', 0),
                })
        except (json.JSONDecodeError, TypeError):
            pass

    # --- System info ---
    hostname = _run('hostname')
    uptime = _run("uptime -p 2>/dev/null || uptime | sed 's/.*up/up/'")
    kernel = _run('uname -r')

    return jsonify({
        'services': services,
        'python_version': py_ver,
        'node_version': node_ver,
        'nginx_version': nginx_ver,
        'selinux': selinux,
        'ports': ports,
        'pm2_processes': pm2_procs,
        'hostname': hostname,
        'uptime': uptime,
        'kernel': kernel,
    })
