"""
EmareCloud — Ağ Cihazları Route'ları
Router, Switch, Firewall CRUD + bağlanma + komut çalıştırma.
"""

import uuid

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from audit import log_action
from core.helpers import _build_tenant_query, get_servers_for_sidebar
from core.tenant import get_tenant_id
from extensions import db
from models import NetworkDevice
from network_manager import BRAND_COMMANDS, BRAND_LABELS, DEVICE_TYPE_ICONS, net_mgr
from rbac import permission_required

network_bp = Blueprint('network', __name__)


def _generate_id() -> str:
    return 'nd-' + uuid.uuid4().hex[:8]


def _device_with_status(d: NetworkDevice) -> dict:
    r = d.to_dict()
    r['reachable'], r['latency'] = net_mgr.ping(d.host, d.port)
    r['connected'] = net_mgr.is_connected(d.id)
    r['type_icon'] = DEVICE_TYPE_ICONS.get(d.device_type, 'fa-microchip')
    r['brand_label'] = BRAND_LABELS.get(d.brand, d.brand)
    return r


# -- Sayfa --------------------------------------------------

@network_bp.route('/network-devices')
@login_required
@permission_required('network.view')
def network_devices_page():
    from flask import render_template
    return render_template(
        'network_devices.html',
        servers=get_servers_for_sidebar(),
        brands=BRAND_LABELS,
        device_types=list(DEVICE_TYPE_ICONS.keys()),
    )


# -- API: Liste ---------------------------------------------

@network_bp.route('/api/network-devices', methods=['GET'])
@login_required
@permission_required('network.view')
def api_list_devices():
    q = _build_tenant_query(NetworkDevice)
    group_filter = request.args.get('group', '').strip()
    type_filter = request.args.get('type', '').strip()
    brand_filter = request.args.get('brand', '').strip()
    if group_filter:
        q = q.filter(NetworkDevice.group_name == group_filter)
    if type_filter:
        q = q.filter(NetworkDevice.device_type == type_filter)
    if brand_filter:
        q = q.filter(NetworkDevice.brand == brand_filter)

    devices = []
    for d in q.order_by(NetworkDevice.group_name, NetworkDevice.name).all():
        try:
            devices.append(_device_with_status(d))
        except Exception:
            devices.append(d.to_dict())

    groups = sorted({d['group'] for d in devices})
    return jsonify({'success': True, 'devices': devices, 'groups': groups,
                    'brands': BRAND_LABELS})


# -- API: Ekle ----------------------------------------------

@network_bp.route('/api/network-devices', methods=['POST'])
@login_required
@permission_required('network.add')
def api_add_device():
    data = request.get_json(silent=True) or {}

    name = (data.get('name') or '').strip()
    host = (data.get('host') or '').strip()
    if not name or not host:
        return jsonify({'success': False, 'error': 'Ad ve IP/host zorunludur'}), 400

    dev = NetworkDevice(
        id=_generate_id(),
        name=name,
        host=host,
        port=int(data.get('port') or 22),
        username=(data.get('username') or 'admin').strip(),
        device_type=(data.get('device_type') or 'router').strip(),
        brand=(data.get('brand') or 'generic').strip(),
        model=(data.get('model') or '').strip(),
        connection_type=(data.get('connection_type') or 'ssh').strip(),
        group_name=(data.get('group') or 'Genel').strip(),
        location=(data.get('location') or '').strip(),
        description=(data.get('description') or '').strip(),
        org_id=get_tenant_id(),
        added_by=current_user.id,
    )
    pw = (data.get('password') or '').strip()
    if pw:
        dev.set_password(pw)
    ep = (data.get('enable_password') or '').strip()
    if ep:
        dev.set_enable_password(ep)

    db.session.add(dev)
    db.session.commit()
    log_action('network_device_add', details=f'{name} ({host})')
    return jsonify({'success': True, 'device': _device_with_status(dev)})


# -- API: Duzenle -------------------------------------------

@network_bp.route('/api/network-devices/<device_id>', methods=['PUT'])
@login_required
@permission_required('network.edit')
def api_edit_device(device_id):
    q = _build_tenant_query(NetworkDevice)
    dev = q.filter(NetworkDevice.id == device_id).first()
    if not dev:
        return jsonify({'success': False, 'error': 'Cihaz bulunamadı'}), 404

    data = request.get_json(silent=True) or {}
    if 'name' in data:
        dev.name = (data['name'] or '').strip() or dev.name
    if 'host' in data:
        dev.host = (data['host'] or '').strip() or dev.host
    if 'port' in data:
        dev.port = int(data['port'] or 22)
    if 'username' in data:
        dev.username = (data['username'] or 'admin').strip()
    if 'device_type' in data:
        dev.device_type = data['device_type']
    if 'brand' in data:
        dev.brand = data['brand']
    if 'model' in data:
        dev.model = (data.get('model') or '').strip()
    if 'connection_type' in data:
        dev.connection_type = data['connection_type']
    if 'group' in data:
        dev.group_name = (data['group'] or 'Genel').strip()
    if 'location' in data:
        dev.location = (data.get('location') or '').strip()
    if 'description' in data:
        dev.description = (data.get('description') or '').strip()
    pw = (data.get('password') or '').strip()
    if pw:
        dev.set_password(pw)
    ep = (data.get('enable_password') or '').strip()
    if ep:
        dev.set_enable_password(ep)

    db.session.commit()
    log_action('network_device_edit', details=f'{dev.name} ({dev.host})')
    return jsonify({'success': True, 'device': _device_with_status(dev)})


# -- API: Sil -----------------------------------------------

@network_bp.route('/api/network-devices/<device_id>', methods=['DELETE'])
@login_required
@permission_required('network.delete')
def api_delete_device(device_id):
    q = _build_tenant_query(NetworkDevice)
    dev = q.filter(NetworkDevice.id == device_id).first()
    if not dev:
        return jsonify({'success': False, 'error': 'Cihaz bulunamadı'}), 404
    net_mgr.disconnect(device_id)
    name, host = dev.name, dev.host
    db.session.delete(dev)
    db.session.commit()
    log_action('network_device_delete', details=f'{name} ({host})')
    return jsonify({'success': True})


# -- API: Baglan --------------------------------------------

@network_bp.route('/api/network-devices/<device_id>/connect', methods=['POST'])
@login_required
@permission_required('network.execute')
def api_connect_device(device_id):
    q = _build_tenant_query(NetworkDevice)
    dev = q.filter(NetworkDevice.id == device_id).first()
    if not dev:
        return jsonify({'success': False, 'error': 'Cihaz bulunamadı'}), 404
    ok, msg = net_mgr.connect(device_id, dev.host, dev.port,
                              dev.username, dev.get_password(), dev.brand)
    return jsonify({'success': ok, 'message': msg,
                    'connected': net_mgr.is_connected(device_id)})


# -- API: Baglanti Kes --------------------------------------

@network_bp.route('/api/network-devices/<device_id>/disconnect', methods=['POST'])
@login_required
@permission_required('network.execute')
def api_disconnect_device(device_id):
    net_mgr.disconnect(device_id)
    return jsonify({'success': True, 'connected': False})


# -- API: Komut calistir ------------------------------------

@network_bp.route('/api/network-devices/<device_id>/execute', methods=['POST'])
@login_required
@permission_required('network.execute')
def api_execute_command(device_id):
    q = _build_tenant_query(NetworkDevice)
    dev = q.filter(NetworkDevice.id == device_id).first()
    if not dev:
        return jsonify({'success': False, 'error': 'Cihaz bulunamadı'}), 404

    data = request.get_json(silent=True) or {}
    command = (data.get('command') or '').strip()
    if not command:
        return jsonify({'success': False, 'error': 'Komut boş olamaz'}), 400

    _dangerous = ('reload', 'reboot', 'shutdown', 'format ', 'erase ', 'delete ')
    cmd_lower = command.lower()
    for dangerous in _dangerous:
        if cmd_lower.startswith(dangerous):
            return jsonify({'success': False,
                            'error': 'Bu komut güvenlik nedeniyle engellendi'}), 403

    ok, output = net_mgr.execute_auto_connect(
        device_id, dev.host, dev.port,
        dev.username, dev.get_password(), dev.brand,
        command
    )
    log_action('network_execute', details=f'{dev.name}: {command[:60]}')
    return jsonify({'success': ok, 'output': output,
                    'command': command, 'device': dev.name})


# -- API: Hazir sorgular ------------------------------------

@network_bp.route('/api/network-devices/<device_id>/query/<query_key>', methods=['GET'])
@login_required
@permission_required('network.execute')
def api_quick_query(device_id, query_key):
    q = _build_tenant_query(NetworkDevice)
    dev = q.filter(NetworkDevice.id == device_id).first()
    if not dev:
        return jsonify({'success': False, 'error': 'Cihaz bulunamadı'}), 404

    from network_manager import get_command
    cmd = get_command(dev.brand, query_key)
    if not cmd:
        return jsonify({'success': False,
                        'error': f'Bu marka için "{query_key}" komutu tanımlı değil'}), 400

    ok, output = net_mgr.execute_auto_connect(
        device_id, dev.host, dev.port,
        dev.username, dev.get_password(), dev.brand,
        cmd
    )
    return jsonify({'success': ok, 'output': output,
                    'query': query_key, 'command': cmd})


# -- API: Running config yedek ------------------------------

@network_bp.route('/api/network-devices/<device_id>/backup', methods=['GET'])
@login_required
@permission_required('network.execute')
def api_backup_config(device_id):
    q = _build_tenant_query(NetworkDevice)
    dev = q.filter(NetworkDevice.id == device_id).first()
    if not dev:
        return jsonify({'success': False, 'error': 'Cihaz bulunamadı'}), 404

    ok, output = net_mgr.get_running_config(
        device_id, dev.host, dev.port,
        dev.username, dev.get_password(), dev.brand
    )
    log_action('network_backup', details=f'{dev.name} ({dev.host}) config backup')
    return jsonify({'success': ok, 'output': output,
                    'device': dev.name, 'host': dev.host})


# -- API: Cihaz bilgisi (ping + versiyon) -------------------

@network_bp.route('/api/network-devices/<device_id>/info', methods=['GET'])
@login_required
@permission_required('network.view')
def api_device_info(device_id):
    q = _build_tenant_query(NetworkDevice)
    dev = q.filter(NetworkDevice.id == device_id).first()
    if not dev:
        return jsonify({'success': False, 'error': 'Cihaz bulunamadı'}), 404

    reachable, latency = net_mgr.ping(dev.host, dev.port)
    connected = net_mgr.is_connected(dev.id)
    version_output = ''
    if reachable:
        ok, version_output = net_mgr.get_version(
            device_id, dev.host, dev.port,
            dev.username, dev.get_password(), dev.brand
        )

    return jsonify({
        'success': True,
        'device': dev.to_dict(),
        'reachable': reachable,
        'latency': latency,
        'connected': connected,
        'version': version_output,
        'brand_label': BRAND_LABELS.get(dev.brand, dev.brand),
        'type_icon': DEVICE_TYPE_ICONS.get(dev.device_type, 'fa-microchip'),
        'available_commands': list(BRAND_COMMANDS.get(dev.brand, {}).keys()),
    })
