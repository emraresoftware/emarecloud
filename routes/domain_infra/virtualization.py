"""
EmareCloud — Sanal Makine (LXD) API Route'ları
/api/servers/<id>/vms/* endpoint'leri.
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required

from audit import log_action
from core.helpers import get_server_obj_with_access, ssh_mgr
from rbac import permission_required
from virtualization_manager import (
    create_container as vm_create,
)
from virtualization_manager import (
    delete_container as vm_delete,
)
from virtualization_manager import (
    exec_in_container as vm_exec,
)
from virtualization_manager import (
    get_images as vm_get_images,
)
from virtualization_manager import (
    list_containers,
)
from virtualization_manager import (
    start_container as vm_start,
)
from virtualization_manager import (
    stop_container as vm_stop,
)

vms_bp = Blueprint('virtualization_api', __name__)


@vms_bp.route('/api/servers/<server_id>/vms', methods=['GET'])
@login_required
@permission_required('vm.view')
def api_vms_list(server_id):
    srv = get_server_obj_with_access(server_id)
    if not srv:
        return jsonify({'success': False, 'message': 'Sunucu bulunamadı veya erişim yetkiniz yok'}), 404
    if not ssh_mgr.is_connected(server_id):
        return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400
    return jsonify({'success': True, 'vms': list_containers(ssh_mgr, server_id)})


@vms_bp.route('/api/servers/<server_id>/vms/images', methods=['GET'])
@login_required
@permission_required('vm.view')
def api_vms_images(server_id):
    srv = get_server_obj_with_access(server_id)
    if not srv:
        return jsonify({'success': False, 'message': 'Sunucu bulunamadı veya erişim yetkiniz yok'}), 404
    if not ssh_mgr.is_connected(server_id):
        return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400
    return jsonify({'success': True, 'images': vm_get_images(ssh_mgr, server_id)})


@vms_bp.route('/api/servers/<server_id>/vms', methods=['POST'])
@login_required
@permission_required('vm.manage')
def api_vms_create(server_id):
    srv = get_server_obj_with_access(server_id)
    if not srv:
        return jsonify({'success': False, 'message': 'Sunucu bulunamadı veya erişim yetkiniz yok'}), 404
    if not ssh_mgr.is_connected(server_id):
        return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Container adı gerekli'}), 400
    ok, msg = vm_create(
        ssh_mgr, server_id, name=name,
        image=data.get('image') or 'ubuntu:22.04',
        memory=data.get('memory') or '1GB',
        cpu=str(data.get('cpu') or '1'),
        disk=data.get('disk') or '10GB',
    )
    log_action('vm.create', target_type='vm', target_id=name,
              details={'server_id': server_id}, success=ok)
    return jsonify({'success': ok, 'message': msg})


@vms_bp.route('/api/servers/<server_id>/vms/<name>/start', methods=['POST'])
@login_required
@permission_required('vm.manage')
def api_vms_start(server_id, name):
    srv = get_server_obj_with_access(server_id)
    if not srv:
        return jsonify({'success': False, 'message': 'Sunucu bulunamadı veya erişim yetkiniz yok'}), 404
    if not ssh_mgr.is_connected(server_id):
        return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400
    ok, msg = vm_start(ssh_mgr, server_id, name)
    return jsonify({'success': ok, 'message': msg})


@vms_bp.route('/api/servers/<server_id>/vms/<name>/stop', methods=['POST'])
@login_required
@permission_required('vm.manage')
def api_vms_stop(server_id, name):
    srv = get_server_obj_with_access(server_id)
    if not srv:
        return jsonify({'success': False, 'message': 'Sunucu bulunamadı veya erişim yetkiniz yok'}), 404
    if not ssh_mgr.is_connected(server_id):
        return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400
    ok, msg = vm_stop(ssh_mgr, server_id, name)
    return jsonify({'success': ok, 'message': msg})


@vms_bp.route('/api/servers/<server_id>/vms/<name>', methods=['DELETE'])
@login_required
@permission_required('vm.manage')
def api_vms_delete(server_id, name):
    srv = get_server_obj_with_access(server_id)
    if not srv:
        return jsonify({'success': False, 'message': 'Sunucu bulunamadı veya erişim yetkiniz yok'}), 404
    if not ssh_mgr.is_connected(server_id):
        return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400
    ok, msg = vm_delete(ssh_mgr, server_id, name)
    log_action('vm.delete', target_type='vm', target_id=name, success=ok)
    return jsonify({'success': ok, 'message': msg})


@vms_bp.route('/api/servers/<server_id>/vms/<name>/exec', methods=['POST'])
@login_required
@permission_required('vm.manage')
def api_vms_exec(server_id, name):
    srv = get_server_obj_with_access(server_id)
    if not srv:
        return jsonify({'success': False, 'message': 'Sunucu bulunamadı veya erişim yetkiniz yok'}), 404
    if not ssh_mgr.is_connected(server_id):
        return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400
    data = request.get_json(silent=True) or {}
    command = (data.get('command') or '').strip()
    if not command:
        return jsonify({'success': False, 'message': 'Komut gerekli'}), 400
    ok, stdout, stderr = vm_exec(ssh_mgr, server_id, name, command)
    return jsonify({'success': ok, 'stdout': stdout, 'stderr': stderr})
