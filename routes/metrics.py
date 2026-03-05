"""
EmareCloud — Metrik API Route'ları
/api/servers/<id>/metrics|cpu|memory|disks|processes|services|security
"""

from flask import Blueprint, jsonify
from flask_login import login_required

from core.helpers import monitor, ssh_mgr
from rbac import permission_required

metrics_bp = Blueprint('metrics', __name__)


def _require_connected(server_id):
    """Sunucu bağlı değilse hata döndürür."""
    if not ssh_mgr.is_connected(server_id):
        return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400
    return None


@metrics_bp.route('/api/servers/<server_id>/metrics', methods=['GET'])
@login_required
@permission_required('server.metrics')
def api_server_metrics(server_id):
    err = _require_connected(server_id)
    if err:
        return err
    return jsonify({'success': True, 'metrics': monitor.get_all_metrics(server_id)})


@metrics_bp.route('/api/servers/<server_id>/cpu', methods=['GET'])
@login_required
@permission_required('server.metrics')
def api_server_cpu(server_id):
    err = _require_connected(server_id)
    if err:
        return err
    return jsonify({'success': True, 'cpu': monitor.get_cpu_info(server_id)})


@metrics_bp.route('/api/servers/<server_id>/memory', methods=['GET'])
@login_required
@permission_required('server.metrics')
def api_server_memory(server_id):
    err = _require_connected(server_id)
    if err:
        return err
    return jsonify({'success': True, 'memory': monitor.get_memory_info(server_id)})


@metrics_bp.route('/api/servers/<server_id>/disks', methods=['GET'])
@login_required
@permission_required('server.metrics')
def api_server_disks(server_id):
    err = _require_connected(server_id)
    if err:
        return err
    return jsonify({'success': True, 'disks': monitor.get_disk_info(server_id)})


@metrics_bp.route('/api/servers/<server_id>/processes', methods=['GET'])
@login_required
@permission_required('server.metrics')
def api_server_processes(server_id):
    err = _require_connected(server_id)
    if err:
        return err
    return jsonify({'success': True, 'processes': monitor.get_process_list(server_id)})


@metrics_bp.route('/api/servers/<server_id>/services', methods=['GET'])
@login_required
@permission_required('server.metrics')
def api_server_services(server_id):
    err = _require_connected(server_id)
    if err:
        return err
    return jsonify({'success': True, 'services': monitor.get_service_status(server_id)})


@metrics_bp.route('/api/servers/<server_id>/security', methods=['GET'])
@login_required
@permission_required('server.metrics')
def api_server_security(server_id):
    err = _require_connected(server_id)
    if err:
        return err
    return jsonify({'success': True, 'security': monitor.get_security_info(server_id)})
