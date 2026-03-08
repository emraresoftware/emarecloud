"""
EmareCloud — Veri Merkezi (Data Center) API Route'ları
/api/datacenters CRUD + sunucu atama.
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required

from audit import log_action
from core.helpers import _build_tenant_query, get_server_obj_with_access
from core.tenant import get_tenant_id, is_global_access
from extensions import db
from models import DataCenter, ServerCredential
from rbac import permission_required

dc_bp = Blueprint('datacenters', __name__)


def _get_dc_with_access(dc_id):
    """DataCenter nesnesini tenant erişim kontrolü ile döndürür."""
    dc = db.session.get(DataCenter, dc_id)
    if not dc:
        return None
    if is_global_access() and not get_tenant_id():
        return dc
    tenant_id = get_tenant_id()
    if tenant_id is not None:
        return dc if dc.org_id == tenant_id else None
    return dc if dc.org_id is None else None


@dc_bp.route('/api/datacenters', methods=['GET'])
@login_required
@permission_required('dc.view')
def api_list_datacenters():
    """Tüm veri merkezlerini listele."""
    dcs = _build_tenant_query(DataCenter).order_by(DataCenter.name).all()
    return jsonify({
        'success': True,
        'datacenters': [dc.to_dict() for dc in dcs],
    })


@dc_bp.route('/api/datacenters/<int:dc_id>', methods=['GET'])
@login_required
@permission_required('dc.view')
def api_get_datacenter(dc_id):
    """Tek bir DC detayını al (sunucularıyla birlikte)."""
    dc = _get_dc_with_access(dc_id)
    if not dc:
        return jsonify({'success': False, 'message': 'Veri merkezi bulunamadı'}), 404

    dc_dict = dc.to_dict()
    dc_dict['servers'] = [s.to_dict() for s in
                          _build_tenant_query(ServerCredential).filter_by(dc_id=dc_id).all()]
    return jsonify({'success': True, 'datacenter': dc_dict})


@dc_bp.route('/api/datacenters', methods=['POST'])
@login_required
@permission_required('dc.manage')
def api_create_datacenter():
    """Yeni veri merkezi oluştur."""
    data = request.get_json(silent=True) or {}

    name = (data.get('name') or '').strip()
    code = (data.get('code') or '').strip().lower()

    if not name or not code:
        return jsonify({'success': False, 'message': '"name" ve "code" zorunlu'}), 400

    # Benzersizlik kontrolü
    if _build_tenant_query(DataCenter).filter_by(code=code).first():
        return jsonify({'success': False, 'message': f'"{code}" kodu zaten kullanılıyor'}), 409

    dc = DataCenter(
        name=name,
        code=code,
        location=(data.get('location') or '').strip(),
        provider=(data.get('provider') or '').strip(),
        ip_range=(data.get('ip_range') or '').strip(),
        description=(data.get('description') or '').strip(),
        status=data.get('status', 'active'),
        latitude=data.get('latitude'),
        longitude=data.get('longitude'),
        org_id=get_tenant_id(),
    )
    db.session.add(dc)
    db.session.commit()

    log_action('dc.create', target_type='datacenter', target_id=str(dc.id),
               details={'name': name, 'code': code})
    return jsonify({'success': True, 'message': 'Veri merkezi oluşturuldu', 'datacenter': dc.to_dict()})


@dc_bp.route('/api/datacenters/<int:dc_id>', methods=['PUT'])
@login_required
@permission_required('dc.manage')
def api_update_datacenter(dc_id):
    """Veri merkezi güncelle."""
    data = request.get_json(silent=True) or {}
    dc = _get_dc_with_access(dc_id)
    if not dc:
        return jsonify({'success': False, 'message': 'Veri merkezi bulunamadı'}), 404

    fields = ['name', 'location', 'provider', 'ip_range', 'description', 'status']
    changes = {}
    for f in fields:
        if f in data:
            val = (data[f] or '').strip() if isinstance(data[f], str) else data[f]
            setattr(dc, f, val)
            changes[f] = val

    if 'code' in data:
        new_code = (data['code'] or '').strip().lower()
        existing = _build_tenant_query(DataCenter).filter_by(code=new_code).first()
        if existing and existing.id != dc_id:
            return jsonify({'success': False, 'message': f'"{new_code}" kodu zaten kullanılıyor'}), 409
        dc.code = new_code
        changes['code'] = new_code

    if 'latitude' in data:
        dc.latitude = data['latitude']
    if 'longitude' in data:
        dc.longitude = data['longitude']

    db.session.commit()
    log_action('dc.update', target_type='datacenter', target_id=str(dc_id), details=changes)
    return jsonify({'success': True, 'message': 'Veri merkezi güncellendi', 'datacenter': dc.to_dict()})


@dc_bp.route('/api/datacenters/<int:dc_id>', methods=['DELETE'])
@login_required
@permission_required('dc.manage')
def api_delete_datacenter(dc_id):
    """Veri merkezi sil — içindeki sunucular dc_id=NULL olur."""
    dc = _get_dc_with_access(dc_id)
    if not dc:
        return jsonify({'success': False, 'message': 'Veri merkezi bulunamadı'}), 404

    name = dc.name
    # Sunucuları DC'den ayır (sadece tenant'ın sunucuları)
    _build_tenant_query(ServerCredential).filter_by(dc_id=dc_id).update({'dc_id': None})
    db.session.delete(dc)
    db.session.commit()

    log_action('dc.delete', target_type='datacenter', target_id=str(dc_id),
               details={'name': name})
    return jsonify({'success': True, 'message': 'Veri merkezi silindi'})


@dc_bp.route('/api/datacenters/<int:dc_id>/assign', methods=['POST'])
@login_required
@permission_required('dc.manage')
def api_assign_servers_to_dc(dc_id):
    """Sunucuları bir DC'ye ata."""
    data = request.get_json(silent=True) or {}
    server_ids = data.get('server_ids', [])

    dc = _get_dc_with_access(dc_id)
    if not dc:
        return jsonify({'success': False, 'message': 'Veri merkezi bulunamadı'}), 404

    count = 0
    for sid in server_ids:
        srv = get_server_obj_with_access(sid)
        if srv:
            srv.dc_id = dc_id
            count += 1

    db.session.commit()
    log_action('dc.assign_servers', target_type='datacenter', target_id=str(dc_id),
               details={'server_ids': server_ids, 'count': count})
    return jsonify({'success': True, 'message': f'{count} sunucu atandı', 'assigned': count})


@dc_bp.route('/api/datacenters/<int:dc_id>/unassign', methods=['POST'])
@login_required
@permission_required('dc.manage')
def api_unassign_servers_from_dc(dc_id):
    """Sunucuları DC'den ayır."""
    data = request.get_json(silent=True) or {}
    server_ids = data.get('server_ids', [])

    # DC erişim kontrolü
    dc = _get_dc_with_access(dc_id)
    if not dc:
        return jsonify({'success': False, 'message': 'Veri merkezi bulunamadı'}), 404

    count = 0
    for sid in server_ids:
        srv = get_server_obj_with_access(sid)
        if srv and srv.dc_id == dc_id:
            srv.dc_id = None
            count += 1

    db.session.commit()
    log_action('dc.unassign_servers', target_type='datacenter', target_id=str(dc_id),
               details={'server_ids': server_ids, 'count': count})
    return jsonify({'success': True, 'message': f'{count} sunucu ayrıldı', 'unassigned': count})


@dc_bp.route('/api/datacenters/overview', methods=['GET'])
@login_required
@permission_required('dc.view')
def api_dc_overview():
    """Tüm DC'lerin özet bilgisi + atanmamış sunucular."""
    dcs = _build_tenant_query(DataCenter).order_by(DataCenter.name).all()
    unassigned = _build_tenant_query(ServerCredential).filter_by(dc_id=None).all()

    return jsonify({
        'success': True,
        'datacenters': [dc.to_dict() for dc in dcs],
        'unassigned_servers': [s.to_dict() for s in unassigned],
        'total_servers': _build_tenant_query(ServerCredential).count(),
        'total_dcs': len(dcs),
    })
