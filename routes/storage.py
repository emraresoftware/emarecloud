"""
EmareCloud — Storage & RAID API Route'ları
/api/raid-protocols/* + /api/servers/<id>/storage-status endpoint'leri.
"""

import uuid

from flask import Blueprint, jsonify, request
from flask_login import login_required

from audit import log_action
from core.config_io import load_config, save_config
from core.helpers import monitor, ssh_mgr
from rbac import permission_required

storage_bp = Blueprint('storage', __name__)


# ==================== RAID PROTOKOLLERİ ====================

@storage_bp.route('/api/raid-protocols', methods=['GET'])
@login_required
@permission_required('raid.view')
def api_raid_protocols_list():
    config = load_config()
    return jsonify({'success': True, 'protocols': config.get('raid_protocols', [])})


@storage_bp.route('/api/raid-protocols', methods=['POST'])
@login_required
@permission_required('raid.manage')
def api_raid_protocols_create():
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Protokol adı gerekli'}), 400
    try:
        delay_ms = int(data.get('inter_disk_delay_ms', 4))
    except (TypeError, ValueError):
        delay_ms = 4
    config = load_config()
    protocols = config.setdefault('raid_protocols', [])
    protocol = {
        'id': str(uuid.uuid4())[:8],
        'name': name,
        'description': (data.get('description') or '').strip(),
        'inter_disk_delay_ms': delay_ms,
        'raid_level': data.get('raid_level') or 'Özel',
        'min_disks': int(data.get('min_disks') or 2),
        'notes': (data.get('notes') or '').strip(),
    }
    protocols.append(protocol)
    save_config(config)
    log_action('raid.create', target_type='raid', target_id=protocol['id'],
              details={'name': name})
    return jsonify({'success': True, 'message': 'Protokol eklendi', 'protocol': protocol})


@storage_bp.route('/api/raid-protocols/<protocol_id>', methods=['PUT'])
@login_required
@permission_required('raid.manage')
def api_raid_protocols_update(protocol_id):
    data = request.get_json(silent=True) or {}
    config = load_config()
    for p in config.get('raid_protocols', []):
        if p.get('id') == protocol_id:
            if data.get('name'):
                p['name'] = data['name'].strip()
            if 'inter_disk_delay_ms' in data:
                try:
                    p['inter_disk_delay_ms'] = int(data['inter_disk_delay_ms'])
                except (TypeError, ValueError):
                    pass
            for field in ('raid_level', 'min_disks', 'description', 'notes'):
                if field in data:
                    p[field] = data[field] if field != 'min_disks' else int(data.get(field, 2))
            save_config(config)
            log_action('raid.update', target_type='raid', target_id=protocol_id)
            return jsonify({'success': True, 'message': 'Protokol güncellendi', 'protocol': p})
    return jsonify({'success': False, 'message': 'Protokol bulunamadı'}), 404


@storage_bp.route('/api/raid-protocols/<protocol_id>', methods=['DELETE'])
@login_required
@permission_required('raid.manage')
def api_raid_protocols_delete(protocol_id):
    config = load_config()
    protocols = config.get('raid_protocols', [])
    new_list = [p for p in protocols if p.get('id') != protocol_id]
    if len(new_list) == len(protocols):
        return jsonify({'success': False, 'message': 'Protokol bulunamadı'}), 404
    config['raid_protocols'] = new_list
    save_config(config)
    log_action('raid.delete', target_type='raid', target_id=protocol_id)
    return jsonify({'success': True, 'message': 'Protokol silindi'})


# ==================== STORAGE STATUS ====================

@storage_bp.route('/api/servers/<server_id>/storage-status', methods=['GET'])
@login_required
@permission_required('storage.view')
def api_server_storage_status(server_id):
    if not ssh_mgr.is_connected(server_id):
        return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400
    return jsonify({
        'success': True,
        'disks': monitor.get_disk_info(server_id),
        'raid': monitor.get_raid_status(server_id),
    })
