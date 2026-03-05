"""
EmareCloud — Firewall API Route'ları
/api/servers/<id>/firewall/* endpoint'leri.
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required

from audit import log_action
from core.helpers import ssh_mgr
from firewall_manager import add_rule as firewall_add_rule
from firewall_manager import delete_rule as firewall_delete_rule
from firewall_manager import disable_firewall, enable_firewall
from firewall_manager import get_status as firewall_get_status
from rbac import permission_required

firewall_bp = Blueprint('firewall', __name__)


@firewall_bp.route('/api/servers/<server_id>/firewall/status', methods=['GET'])
@login_required
@permission_required('firewall.view')
def api_firewall_status(server_id):
    if not ssh_mgr.is_connected(server_id):
        return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400
    try:
        status = firewall_get_status(ssh_mgr, server_id)
        return jsonify({'success': True, 'firewall': status})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@firewall_bp.route('/api/servers/<server_id>/firewall/enable', methods=['POST'])
@login_required
@permission_required('firewall.manage')
def api_firewall_enable(server_id):
    if not ssh_mgr.is_connected(server_id):
        return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400
    ok, msg = enable_firewall(ssh_mgr, server_id)
    log_action('firewall.enable', target_type='server', target_id=server_id, success=ok)
    return jsonify({'success': ok, 'message': msg})


@firewall_bp.route('/api/servers/<server_id>/firewall/disable', methods=['POST'])
@login_required
@permission_required('firewall.manage')
def api_firewall_disable(server_id):
    if not ssh_mgr.is_connected(server_id):
        return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400
    ok, msg = disable_firewall(ssh_mgr, server_id)
    log_action('firewall.disable', target_type='server', target_id=server_id, success=ok)
    return jsonify({'success': ok, 'message': msg})


@firewall_bp.route('/api/servers/<server_id>/firewall/rules', methods=['POST'])
@login_required
@permission_required('firewall.manage')
def api_firewall_add_rule(server_id):
    if not ssh_mgr.is_connected(server_id):
        return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400
    data = request.get_json(silent=True) or {}
    port = (data.get('port') or '').strip()
    if not port:
        return jsonify({'success': False, 'message': 'Port veya servis girin'}), 400
    ok, msg = firewall_add_rule(
        ssh_mgr, server_id,
        direction=data.get('direction', 'in'),
        action=data.get('action', 'allow'),
        port=port,
        protocol=data.get('protocol', 'tcp'),
        from_ip=data.get('from_ip', ''),
    )
    log_action('firewall.add_rule', target_type='server', target_id=server_id,
              details={'port': port}, success=ok)
    return jsonify({'success': ok, 'message': msg})


@firewall_bp.route('/api/servers/<server_id>/firewall/rules/<int:rule_index>', methods=['DELETE'])
@login_required
@permission_required('firewall.manage')
def api_firewall_delete_rule(server_id, rule_index):
    if not ssh_mgr.is_connected(server_id):
        return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400
    ok, msg = firewall_delete_rule(ssh_mgr, server_id, rule_index)
    log_action('firewall.delete_rule', target_type='server', target_id=server_id,
              details={'rule_index': rule_index}, success=ok)
    return jsonify({'success': ok, 'message': msg})
