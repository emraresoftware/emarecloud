"""
EmareCloud — Market & GitHub API Route'ları
/api/market/* endpoint'leri.
"""

import base64

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from audit import log_action
from core.helpers import connect_server_ssh, get_server_by_id, ssh_mgr
from market_apps import (
    build_install_script,
    get_all_apps,
    get_app,
    get_categories,
    get_stack_apps_detail,
    get_stack_bundles,
    get_stack_by_id,
    github_get_readme,
    github_install_script,
    github_search,
    github_trending,
    search_stacks,
)
from rbac import permission_required

market_bp = Blueprint('market', __name__)

# EP ödül yardımcısı — import ve kullanımda hata olmaması için güvenli
def _award_ep(action, metadata=None):
    try:
        from blockchain.reward_engine import reward_engine
        if hasattr(current_user, 'id'):
            reward_engine.award_ep(user_id=current_user.id, action=action, metadata=metadata)
    except Exception:
        pass  # EP sistemi opsiyonel


@market_bp.route('/api/market/apps', methods=['GET'])
@login_required
@permission_required('market.view')
def api_market_apps():
    return jsonify({'success': True, 'apps': get_all_apps(), 'categories': get_categories()})


@market_bp.route('/api/market/install', methods=['POST'])
@login_required
@permission_required('market.install')
def api_market_install():
    data = request.get_json(silent=True) or {}
    app_id = data.get('app_id')
    server_id = data.get('server_id')
    options = data.get('options') or {}

    if not app_id or not server_id:
        return jsonify({'success': False, 'message': 'Uygulama ve sunucu seçin'}), 400

    app_def = get_app(app_id)
    if not app_def:
        return jsonify({'success': False, 'message': 'Bilinmeyen uygulama'}), 404

    server = get_server_by_id(server_id)
    if not server:
        return jsonify({'success': False, 'message': 'Sunucu bulunamadı'}), 404

    if not ssh_mgr.is_connected(server_id):
        success, msg = connect_server_ssh(server_id, server)
        if not success:
            return jsonify({'success': False, 'message': f'SSH bağlantısı kurulamadı: {msg}'}), 400

    for opt in app_def.get('options', []):
        if opt.get('required') and not options.get(opt['key']):
            return jsonify({'success': False, 'message': f'"{opt["label"]}" alanı zorunludur'}), 400

    script = build_install_script(app_id, options)
    if not script:
        return jsonify({'success': False, 'message': 'Kurulum scripti oluşturulamadı'}), 500

    encoded = base64.b64encode(script.encode('utf-8')).decode('ascii')
    command = f"echo {encoded} | base64 -d | sudo bash"
    success, stdout, stderr = ssh_mgr.execute_command(server_id, command, timeout=600)
    log_action('market.install', target_type='server', target_id=server_id,
              details={'app': app_id}, success=success)
    if success:
        is_ai = app_def.get('category', '') == 'AI / Yapay Zeka'
        _award_ep('ai_app_installed' if is_ai else 'marketplace_purchase',
                  {'app': app_id, 'server': server_id})
    return jsonify({
        'success': success, 'stdout': stdout, 'stderr': stderr,
        'message': 'Kurulum tamamlandı' if success else 'Kurulum sırasında hata oluştu',
    })


# ==================== STACK BUILDER API ====================

@market_bp.route('/api/market/stacks', methods=['GET'])
@login_required
@permission_required('market.view')
def api_market_stacks():
    q = request.args.get('q', '').strip()
    stacks = search_stacks(q) if q else get_stack_bundles()
    return jsonify({'success': True, 'stacks': stacks})


@market_bp.route('/api/market/stacks/<stack_id>', methods=['GET'])
@login_required
@permission_required('market.view')
def api_stack_detail(stack_id):
    detail = get_stack_apps_detail(stack_id)
    if not detail:
        return jsonify({'success': False, 'message': 'Stack bulunamadı'}), 404
    return jsonify({'success': True, **detail})


@market_bp.route('/api/market/stack/install', methods=['POST'])
@login_required
@permission_required('market.install')
def api_stack_install():
    """Stack paketindeki secili uygulamalari sirayla kurar."""
    data = request.get_json(silent=True) or {}
    stack_id = data.get('stack_id')
    server_id = data.get('server_id')
    selected_apps = data.get('apps', [])  # [{"id": "docker", "options": {}}, ...]
    all_options = data.get('all_options', {})  # {"mysql": {"root_password": "..."}}

    if not stack_id or not server_id:
        return jsonify({'success': False, 'message': 'Stack ve sunucu seçin'}), 400

    stack = get_stack_by_id(stack_id)
    if not stack:
        return jsonify({'success': False, 'message': 'Bilinmeyen stack'}), 404

    server = get_server_by_id(server_id)
    if not server:
        return jsonify({'success': False, 'message': 'Sunucu bulunamadı'}), 404

    if not ssh_mgr.is_connected(server_id):
        success, msg = connect_server_ssh(server_id, server)
        if not success:
            return jsonify({'success': False, 'message': f'SSH bağlantısı kurulamadı: {msg}'}), 400

    # Kurulacak app ID listesini belirle
    if selected_apps:
        app_ids = [a['id'] if isinstance(a, dict) else a for a in selected_apps]
    else:
        app_ids = [a['id'] for a in stack.get('apps', []) if a.get('required', False)]

    results = []
    overall_success = True
    for app_id in app_ids:
        app_def = get_app(app_id)
        if not app_def:
            results.append({'app': app_id, 'success': False, 'message': 'Uygulama bulunamadı'})
            continue

        opts = all_options.get(app_id, {})
        script = build_install_script(app_id, opts)
        if not script:
            results.append({'app': app_id, 'success': False, 'message': 'Script oluşturulamadı'})
            continue

        encoded = base64.b64encode(script.encode('utf-8')).decode('ascii')
        command = f"echo {encoded} | base64 -d | sudo bash"
        ok, stdout, stderr = ssh_mgr.execute_command(server_id, command, timeout=600)
        results.append({
            'app': app_id,
            'name': app_def.get('name', app_id),
            'success': ok,
            'stdout': (stdout or '')[-500:],
            'stderr': (stderr or '')[-300:],
        })
        if not ok:
            overall_success = False

    log_action('market.stack_install', target_type='server', target_id=server_id,
              details={'stack': stack_id, 'apps': app_ids, 'results_ok': sum(1 for r in results if r['success'])},
              success=overall_success)

    if overall_success:
        _award_ep('stack_builder_used', {'stack': stack_id, 'apps': app_ids})
        # AI stack ise ekstra ödül
        if stack and any(t.lower() in ('ai',) for t in stack.get('tags', [])):
            _award_ep('ai_stack_completed', {'stack': stack_id})

    return jsonify({
        'success': overall_success,
        'stack': stack_id,
        'results': results,
        'message': f'{sum(1 for r in results if r["success"])}/{len(results)} uygulama başarıyla kuruldu',
    })


# ==================== GITHUB MARKET API ====================

@market_bp.route('/api/market/github/search', methods=['GET'])
@login_required
@permission_required('market.view')
def api_github_search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'success': False, 'message': 'Arama terimi gerekli'}), 400
    result = github_search(
        q, language=request.args.get('lang', ''),
        sort=request.args.get('sort', 'stars'),
        per_page=min(int(request.args.get('per_page', 20)), 50),
        page=int(request.args.get('page', 1)),
    )
    if result.get('error'):
        return jsonify({'success': False, 'message': result['error']}), 502
    return jsonify({'success': True, **result})


@market_bp.route('/api/market/github/trending', methods=['GET'])
@login_required
@permission_required('market.view')
def api_github_trending():
    result = github_trending(
        language=request.args.get('lang', ''),
        since=request.args.get('since', 'weekly'),
    )
    return jsonify({'success': True, **result})


@market_bp.route('/api/market/github/readme', methods=['GET'])
@login_required
@permission_required('market.view')
def api_github_readme():
    repo = request.args.get('repo', '').strip()
    if not repo or '/' not in repo:
        return jsonify({'success': False, 'message': 'repo parametresi gerekli (owner/name)'}), 400
    return jsonify({'success': True, 'readme': github_get_readme(repo)})


@market_bp.route('/api/market/github/install', methods=['POST'])
@login_required
@permission_required('market.install')
def api_github_install():
    data = request.get_json(silent=True) or {}
    full_name = (data.get('repo') or '').strip()
    server_id = (data.get('server_id') or '').strip()
    branch = data.get('branch', 'main')

    if not full_name or '/' not in full_name:
        return jsonify({'success': False, 'message': 'Geçerli bir repo adı gerekli'}), 400
    if not server_id:
        return jsonify({'success': False, 'message': 'Sunucu seçin'}), 400

    server = get_server_by_id(server_id)
    if not server:
        return jsonify({'success': False, 'message': 'Sunucu bulunamadı'}), 404

    if not ssh_mgr.is_connected(server_id):
        success, msg = connect_server_ssh(server_id, server)
        if not success:
            return jsonify({'success': False, 'message': f'SSH bağlantısı kurulamadı: {msg}'}), 400

    script = github_install_script(full_name, branch)
    encoded = base64.b64encode(script.encode('utf-8')).decode('ascii')
    command = f"echo {encoded} | base64 -d | sudo bash"
    success, stdout, stderr = ssh_mgr.execute_command(server_id, command, timeout=600)
    log_action('market.github_install', target_type='server', target_id=server_id,
              details={'repo': full_name}, success=success)
    return jsonify({
        'success': success, 'stdout': stdout, 'stderr': stderr,
        'message': f'{full_name} kurulumu tamamlandı' if success else 'Kurulum sırasında hata oluştu',
    })
