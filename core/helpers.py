"""
EmareCloud — Yardımcı Fonksiyonlar
Sunucu sorgulama, sidebar verisi, SSH bağlantı kurma, ayarlar.
"""

import json
import logging

from extensions import db
from models import AppSetting, ServerCredential
from server_monitor import ServerMonitor
from ssh_manager import SSHManager

logger = logging.getLogger('emarecloud.helpers')

# Paylaşılan SSH & Monitor nesneleri
ssh_mgr = SSHManager(timeout=10)
monitor = ServerMonitor(ssh_mgr)

# Paralel çalıştırma: gevent varsa gevent pool, yoksa ThreadPoolExecutor
try:
    import gevent
    from gevent.pool import Pool as _Pool
    _gpool = _Pool(size=8)
    _USE_GEVENT = True
except ImportError:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    _executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix='srv-check')
    _USE_GEVENT = False


def _check_single_server(server_dict: dict) -> dict:
    """Tek bir sunucunun erişilebilirliğini kontrol eder (thread-safe)."""
    rec = {k: v for k, v in server_dict.items() if k != 'password'}
    try:
        host = server_dict.get('host') or ''
        port = server_dict.get('port', 22)
        rec['reachable'], rec['latency'] = ssh_mgr.check_server_reachable(host, port)
        rec['connected'] = ssh_mgr.is_connected(server_dict.get('id', ''))
    except Exception:
        rec['reachable'] = False
        rec['latency'] = 0.0
        rec['connected'] = False
    return rec


def _user_can_see_server(srv) -> bool:
    """Tenant izolasyonu: Kullanıcı kendi organizasyonundaki sunucuları görür.
    Super admin → global, admin → kendi org, normal → kendi org."""
    try:
        from flask_login import current_user

        from core.tenant import get_tenant_id, is_global_access
        if not current_user.is_authenticated:
            return False
        # Süper admin global modda → her şeyi görür
        if is_global_access() and not get_tenant_id():
            return True
        # Tenant ID varsa → sadece o org'un sunucuları
        tenant_id = get_tenant_id()
        if tenant_id is not None:
            return srv.org_id == tenant_id
        # Tenant olmayan geçiş dönemi: org_id=None sunucular görülebilir
        return srv.org_id is None
    except Exception:
        # Background thread / uygulama context olmayan durumlar — erişim açık bırak
        return True


def get_server_by_id(server_id: str) -> dict | None:
    """ID ile sunucu bilgisi (şifre dahil — sadece backend).
    Tenant izolasyonu: kullanıcı sadece kendi org'unun sunucusunu alabilir."""
    srv = db.session.get(ServerCredential, server_id)
    if not srv:
        return None
    if not _user_can_see_server(srv):
        return None
    return srv.to_dict(include_password=True)


def get_server_obj_with_access(server_id: str):
    """Server DB nesnesi döndürür, tenant erişim kontrolü ile.
    Nesneye erişim yoksa None döndürür."""
    srv = db.session.get(ServerCredential, server_id)
    if not srv:
        return None
    if not _user_can_see_server(srv):
        return None
    return srv


def _build_tenant_query(model):
    """Verilen model için tenant filtrelenmiş sorgu üretir.
    model'de org_id kolonu olmalı."""
    from core.tenant import get_tenant_id, is_global_access
    query = model.query
    # Süper admin global modda → filtre yok
    if is_global_access() and not get_tenant_id():
        return query
    tenant_id = get_tenant_id()
    if tenant_id is not None:
        return query.filter(model.org_id == tenant_id)
    # Geçiş dönemi: org_id=None kayıtlar
    return query.filter(model.org_id.is_(None))


def get_servers_for_sidebar() -> list:
    """Sidebar + template için sunucu listesi — paralel reachability kontrolü.
    Tenant izolasyonu: kullanıcı sadece kendi org'unun sunucularını görür."""
    try:
        query = _build_tenant_query(ServerCredential)
    except Exception:
        query = ServerCredential.query
    raw = [s.to_dict() for s in query.order_by(ServerCredential.added_at).all()]
    if not raw:
        return []

    servers = []
    try:
        if _USE_GEVENT:
            # gevent uyumlu paralel çalıştırma
            jobs = [_gpool.spawn(_check_single_server, s) for s in raw]
            gevent.joinall(jobs, timeout=10)
            for i, job in enumerate(jobs):
                if job.value is not None:
                    servers.append(job.value)
                else:
                    s = {k: v for k, v in raw[i].items() if k != 'password'}
                    s['reachable'] = False
                    s['latency'] = 0.0
                    s['connected'] = False
                    servers.append(s)
        else:
            # ThreadPoolExecutor ile paralel çalıştırma
            futures = {_executor.submit(_check_single_server, s): s for s in raw}
            for future in as_completed(futures, timeout=10):
                try:
                    servers.append(future.result(timeout=5))
                except Exception:
                    s = futures[future]
                    s['reachable'] = False
                    s['latency'] = 0.0
                    s['connected'] = False
                    servers.append(s)
    except Exception as e:
        logger.warning('Sunucu kontrolü başarısız: %s', e)
        for s in raw:
            s['reachable'] = False
            s['latency'] = 0.0
            s['connected'] = False
            servers.append(s)

    id_order = {s.get('id'): i for i, s in enumerate(raw)}
    servers.sort(key=lambda x: id_order.get(x.get('id'), 999))
    return servers


def get_app_settings() -> dict:
    """Uygulama ayarlarını döndürür."""
    settings = {}
    for s in AppSetting.query.all():
        try:
            settings[s.key] = json.loads(s.value)
        except (json.JSONDecodeError, TypeError):
            settings[s.key] = s.value
    defaults = {
        'refresh_interval': 30, 'ssh_timeout': 10,
        'max_concurrent_connections': 5,
        'alert_cpu_threshold': 90, 'alert_ram_threshold': 85,
        'alert_disk_threshold': 90,
    }
    for k, v in defaults.items():
        if k not in settings:
            settings[k] = v
    return settings


def connect_server_ssh(server_id: str, server: dict) -> tuple[bool, str]:
    """Sunucuya SSH bağlantısı kurar (DRY helper). Key varsa key ile dener."""
    return ssh_mgr.connect(
        server_id,
        (server.get('host') or '').strip(),
        int(server.get('port') or 22),
        server.get('username') or '',
        server.get('password') or '',
        ssh_key_pem=server.get('ssh_key') or None,
    )
