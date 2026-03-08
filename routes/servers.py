"""
EmareCloud — Sunucu API Route'ları
/api/servers CRUD + connect/disconnect.
"""

import json
import uuid

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from audit import log_action
from core.helpers import (
    _build_tenant_query,
    connect_server_ssh,
    get_server_by_id,
    get_server_obj_with_access,
    ssh_mgr,
)
from core.tenant import get_tenant_id
from extensions import db
from license_manager import check_server_limit
from models import ServerCredential
from rbac import permission_required

# Paralel çalıştırma: gevent varsa gevent pool, yoksa ThreadPoolExecutor
try:
    import gevent
    from gevent.pool import Pool as _Pool
    _srv_pool = _Pool(size=8)
    _USE_GEVENT = True
except ImportError:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    _executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix='srv-api')
    _USE_GEVENT = False

servers_bp = Blueprint('servers', __name__)


@servers_bp.route('/api/servers', methods=['GET'])
@login_required
@permission_required('server.view')
def api_list_servers():
    query = _build_tenant_query(ServerCredential)
    raw = [s.to_dict() for s in query.all()]
    if not raw:
        return jsonify({'success': True, 'servers': []})

    def _check_api(server):
        try:
            server['reachable'], server['latency'] = ssh_mgr.check_server_reachable(
                server['host'], server.get('port', 22))
            server['connected'] = ssh_mgr.is_connected(server['id'])
        except Exception:
            server['reachable'] = False
            server['latency'] = 0.0
            server['connected'] = False
        return server

    futures = {}
    if _USE_GEVENT:
        jobs = [_srv_pool.spawn(_check_api, s) for s in raw]
        gevent.joinall(jobs, timeout=10)
        results = []
        for i, job in enumerate(jobs):
            if job.value is not None:
                results.append(job.value)
            else:
                raw[i]['reachable'] = False
                raw[i]['latency'] = 0.0
                raw[i]['connected'] = False
                results.append(raw[i])
    else:
        futures = {_executor.submit(_check_api, s): i for i, s in enumerate(raw)}
        results = [None] * len(raw)
        for future in as_completed(futures, timeout=10):
            idx = futures[future]
            try:
                results[idx] = future.result(timeout=5)
            except Exception:
                results[idx] = raw[idx]
                results[idx]['reachable'] = False
        results = [r if r else raw[i] for i, r in enumerate(results)]
    return jsonify({'success': True, 'servers': results})


@servers_bp.route('/api/servers', methods=['POST'])
@login_required
@permission_required('server.add')
def api_add_server():
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'success': False, 'message': 'Veri gönderilmedi'}), 400

    for field in ('name', 'host', 'username', 'password'):
        val = data.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            return jsonify({'success': False, 'message': f'"{field}" alanı zorunludur'}), 400

    # Lisans sunucu limiti kontrolü (tenant bazlı)
    tenant_id = get_tenant_id()
    if tenant_id:
        current_count = ServerCredential.query.filter_by(org_id=tenant_id).count()
    else:
        current_count = ServerCredential.query.filter(ServerCredential.org_id.is_(None)).count()
    allowed, limit_msg = check_server_limit(current_count)
    if not allowed:
        return jsonify({'success': False, 'message': limit_msg}), 403

    try:
        port = int(data.get('port', 22))
        if not (1 <= port <= 65535):
            port = 22
    except (TypeError, ValueError):
        port = 22

    server_id = f"srv-{uuid.uuid4().hex[:6]}"
    srv = ServerCredential(
        id=server_id,
        name=(data.get('name') or '').strip(),
        host=(data.get('host') or '').strip(),
        port=port,
        username=(data.get('username') or '').strip() or 'root',
        group_name=(data.get('group') or 'Genel').strip(),
        description=(data.get('description') or '').strip(),
        tags=json.dumps(data.get('tags', [])),
        role=(data.get('role') or '').strip(),
        location=(data.get('location') or '').strip(),
        installed_at=(data.get('installed_at') or '').strip(),
        responsible=(data.get('responsible') or '').strip(),
        os_planned=(data.get('os_planned') or '').strip(),
        dc_id=data.get('dc_id') or None,
        org_id=get_tenant_id(),
        added_by=current_user.id if current_user.is_authenticated else None,
    )
    password = data.get('password', '')
    if password:
        srv.set_password(password)
    db.session.add(srv)
    db.session.commit()

    log_action('server.add', target_type='server', target_id=server_id,
              details={'name': srv.name, 'host': srv.host})
    return jsonify({'success': True, 'message': 'Sunucu eklendi', 'server_id': server_id})


@servers_bp.route('/api/servers/<server_id>', methods=['DELETE'])
@login_required
@permission_required('server.delete')
def api_delete_server(server_id):
    srv = get_server_obj_with_access(server_id)
    if not srv:
        return jsonify({'success': False, 'message': 'Sunucu bulunamadı veya erişim yetkiniz yok'}), 404
    name = srv.name
    db.session.delete(srv)
    db.session.commit()
    ssh_mgr.disconnect(server_id)
    log_action('server.delete', target_type='server', target_id=server_id,
              details={'name': name})
    return jsonify({'success': True, 'message': 'Sunucu silindi'})


@servers_bp.route('/api/servers/<server_id>', methods=['PUT'])
@login_required
@permission_required('server.edit')
def api_update_server(server_id):
    data = request.get_json(silent=True) or {}
    if not data:
        return jsonify({'success': False, 'message': 'Veri gönderilmedi'}), 400
    srv = get_server_obj_with_access(server_id)
    if not srv:
        return jsonify({'success': False, 'message': 'Sunucu bulunamadı veya erişim yetkiniz yok'}), 404

    field_map = {
        'name': 'name', 'host': 'host', 'username': 'username',
        'group': 'group_name', 'description': 'description',
        'role': 'role', 'location': 'location',
        'installed_at': 'installed_at', 'responsible': 'responsible',
        'os_planned': 'os_planned',
    }
    changes = {}
    for json_key, db_attr in field_map.items():
        if json_key in data:
            val = (data[json_key] or '').strip() if isinstance(data[json_key], str) else data[json_key]
            setattr(srv, db_attr, val)
            changes[json_key] = val

    if 'port' in data:
        try:
            srv.port = int(data['port']) if data['port'] else 22
        except (TypeError, ValueError):
            pass
    if 'tags' in data:
        srv.tags = json.dumps(data['tags']) if isinstance(data['tags'], list) else '[]'
    if 'dc_id' in data:
        srv.dc_id = data['dc_id'] or None
    if 'password' in data and data['password']:
        srv.set_password(data['password'])
        changes['password_changed'] = True

    db.session.commit()
    log_action('server.edit', target_type='server', target_id=server_id, details=changes)
    return jsonify({'success': True, 'message': 'Sunucu güncellendi'})


@servers_bp.route('/api/servers/<server_id>/connect', methods=['POST'])
@login_required
@permission_required('server.connect')
def api_connect_server(server_id):
    server = get_server_by_id(server_id)
    if not server:
        return jsonify({'success': False, 'message': 'Sunucu bulunamadı'}), 404
    success, message = connect_server_ssh(server_id, server)
    log_action('server.connect', target_type='server', target_id=server_id,
              details={'host': server.get('host'), 'method': message}, success=success)
    return jsonify({'success': success, 'message': message})


@servers_bp.route('/api/servers/<server_id>/disconnect', methods=['POST'])
@login_required
@permission_required('server.disconnect')
def api_disconnect_server(server_id):
    srv = get_server_obj_with_access(server_id)
    if not srv:
        return jsonify({'success': False, 'message': 'Sunucu bulunamadı veya erişim yetkiniz yok'}), 404
    ssh_mgr.disconnect(server_id)
    log_action('server.disconnect', target_type='server', target_id=server_id)
    return jsonify({'success': True, 'message': 'Bağlantı kesildi'})
