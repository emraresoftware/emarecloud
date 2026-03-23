"""
EmareCloud — Komut Çalıştırma API Route'ları
/api/servers/<id>/execute + quick-action endpoint'leri.
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from audit import log_action
from command_security import is_command_allowed
from core.helpers import get_server_obj_with_access, ssh_mgr
from rbac import permission_required

commands_bp = Blueprint('commands', __name__)


@commands_bp.route('/api/servers/<server_id>/execute', methods=['POST'])
@login_required
@permission_required('server.execute')
def api_execute_command(server_id):
    """Sunucuda komut çalıştırır — rol bazlı güvenlik kontrolü ve tenant izolasyonu ile."""
    data = request.get_json(silent=True) or {}
    command = (data.get('command') or '').strip()
    if not command:
        return jsonify({'success': False, 'message': 'Komut belirtilmedi'}), 400

    # Tenant erişim kontrolü
    srv = get_server_obj_with_access(server_id)
    if not srv:
        return jsonify({'success': False, 'message': 'Sunucu bulunamadı veya erişim yetkiniz yok'}), 404

    if not ssh_mgr.is_connected(server_id):
        return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400

    # Komut güvenlik kontrolü
    allowed, reason = is_command_allowed(command, current_user.role)
    if not allowed:
        log_action('command.blocked', target_type='server', target_id=server_id,
                  details={'command': command[:200], 'reason': reason}, success=False)
        return jsonify({'success': False, 'message': reason}), 403

    success, stdout, stderr = ssh_mgr.execute_command(server_id, command)
    log_action('command.execute', target_type='server', target_id=server_id,
              details={'command': command[:200]}, success=success)
    return jsonify({'success': success, 'stdout': stdout, 'stderr': stderr})


@commands_bp.route('/api/servers/<server_id>/quick-action', methods=['POST'])
@login_required
@permission_required('server.quick_action')
def api_quick_action(server_id):
    data = request.get_json(silent=True) or {}
    action = data.get('action', '')

    # Tenant erişim kontrolü
    srv = get_server_obj_with_access(server_id)
    if not srv:
        return jsonify({'success': False, 'message': 'Sunucu bulunamadı veya erişim yetkiniz yok'}), 404

    if not ssh_mgr.is_connected(server_id):
        return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400

    actions = {
        'update': 'apt update && apt upgrade -y 2>/dev/null || yum update -y 2>/dev/null',
        'reboot': 'reboot',
        'shutdown': 'shutdown -h now',
        'clear_cache': 'sync; echo 3 > /proc/sys/vm/drop_caches',
        'restart_nginx': 'systemctl restart nginx',
        'restart_apache': 'systemctl restart apache2 || systemctl restart httpd',
        'restart_mysql': 'systemctl restart mysql || systemctl restart mariadb',
        'restart_docker': 'systemctl restart docker',
        'check_updates': 'apt list --upgradable 2>/dev/null || yum check-update 2>/dev/null',
        'disk_cleanup': 'apt autoremove -y 2>/dev/null; apt autoclean 2>/dev/null; journalctl --vacuum-time=7d 2>/dev/null',
    }
    if action not in actions:
        return jsonify({'success': False, 'message': 'Geçersiz eylem'}), 400

    success, stdout, stderr = ssh_mgr.execute_command(server_id, actions[action], timeout=120)
    log_action('server.quick_action', target_type='server', target_id=server_id,
              details={'action': action}, success=success)
    return jsonify({'success': success, 'stdout': stdout, 'stderr': stderr, 'action': action})
