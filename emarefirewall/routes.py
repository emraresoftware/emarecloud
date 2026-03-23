"""
Emare Security OS — Flask Blueprint (Opsiyonel Flask Entegrasyonu)
================================================================

Herhangi bir Flask uygulamasına eklenebilen firewall API Blueprint'i.
EmareCloud dışında bağımsız Flask app'lerde de kullanılabilir.

Kullanım:
    from flask import Flask
    from emarefirewall.routes import create_blueprint
    from emarefirewall.ssh import ParamikoExecutor

    app = Flask(__name__)
    ssh = ParamikoExecutor()
    ssh.connect("srv1", host="1.2.3.4", user="root", key_path="~/.ssh/id_rsa")

    fw_bp = create_blueprint(
        ssh_executor=ssh.execute,
        auth_decorator=login_required,     # opsiyonel
        permission_decorator=None,         # opsiyonel
        audit_fn=None,                     # opsiyonel
    )
    app.register_blueprint(fw_bp)
"""

import re
import time
import json
import heapq
import logging
import threading
from datetime import datetime, timezone, timedelta
from functools import wraps

from flask import Blueprint, jsonify, request, render_template

from emarefirewall.manager import FirewallManager
from emarefirewall import __version__
from emarefirewall.store import LogStore, create_store
from emarefirewall.cache import create_cache

logger = logging.getLogger('emarefirewall.routes')

# GÜVENLİK: İzin verilen server_id formatı — alfanümerik, tire, altçizgi, nokta
_VALID_SERVER_ID_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$')

# Global log store — create_blueprint'te moduna göre oluşturulur
_log_store = LogStore()


def _noop_decorator(*args, **kwargs):
    """Hiçbir şey yapmayan dekoratör (auth/permission yoksa kullanılır)."""
    if len(args) == 1 and callable(args[0]):
        return args[0]
    def wrapper(fn):
        return fn
    return wrapper


def create_blueprint(
    ssh_executor,
    auth_decorator=None,
    permission_decorator=None,
    audit_fn=None,
    connection_checker=None,
    url_prefix="",
    csrf_checker=None,
    rate_limit_per_minute=30,
    log_db_path=None,
    log_retention_days=30,
    cache_backend=None,
    log_store=None,
    tenant_store=None,
    webhook_dispatcher=None,
    rmm_store=None,
):
    """
    Firewall Flask Blueprint'i oluşturur.

    Args:
        ssh_executor: (server_id, command) -> (ok, stdout, stderr)
        auth_decorator: Login gerektiren dekoratör (örn: login_required). None ise auth yok.
        permission_decorator: Yetki dekoratörü (örn: permission_required). None ise yetki yok.
        audit_fn: Audit log fonksiyonu: audit_fn(action, **kwargs). None ise log yok.
        connection_checker: (server_id) -> bool. None ise her zaman True.
        url_prefix: Blueprint URL prefix.
        csrf_checker: CSRF token doğrulama fonksiyonu: csrf_checker() -> bool.
        rate_limit_per_minute: Dakika başına izin verilen istek sayısı (0 = sınırsız).
        log_db_path: SQLite log dosyası yolu (standalone mod). None ise sadece bellek.
        log_retention_days: Logların tutulacağı gün sayısı (varsayılan 30).
        cache_backend: Cache nesnesi (DictCache/RedisCache). None ise DictCache oluşturulur.
        log_store: Harici LogStore nesnesi. None ise oluşturulur.
        tenant_store: TenantStore / DictTenantStore nesnesi. ISP multi-tenant desteği.
        webhook_dispatcher: WebhookDispatcher nesnesi. Webhook bildirimleri.
        rmm_store: RMMStore nesnesi. RMM + ITSM desteği.

    Returns:
        Flask Blueprint
    """
    global _log_store
    if log_store is not None:
        _log_store = log_store
    elif log_db_path:
        _log_store = create_store(db_backend='sqlite', db_path=log_db_path,
                                  retention_days=log_retention_days)

    _cache = cache_backend or create_cache('dict')

    fw = FirewallManager(ssh_executor=ssh_executor, cache_backend=_cache)
    bp = Blueprint('emarefirewall', __name__, url_prefix=url_prefix)

    auth = auth_decorator or _noop_decorator
    perm_view = (lambda fn: permission_decorator('firewall.view')(fn)) if permission_decorator else _noop_decorator
    perm_manage = (lambda fn: permission_decorator('firewall.manage')(fn)) if permission_decorator else _noop_decorator

    # ═══ GZIP SIKIŞTIRMA ═══
    @bp.after_request
    def _gzip_response(response):
        """JSON ve text yanıtlarını gzip ile sıkıştır (%60-80 bant genişliği tasarrufu)."""
        if (response.status_code < 200 or response.status_code >= 300
                or response.direct_passthrough
                or 'Content-Encoding' in response.headers
                or len(response.get_data()) < 256):
            return response
        accept_enc = request.headers.get('Accept-Encoding', '')
        if 'gzip' not in accept_enc:
            return response
        ct = response.content_type or ''
        if not (ct.startswith('application/json') or ct.startswith('text/')):
            return response
        import gzip as _gzip
        response.set_data(_gzip.compress(response.get_data(), compresslevel=6))
        response.headers['Content-Encoding'] = 'gzip'
        response.headers['Content-Length'] = len(response.get_data())
        response.headers['Vary'] = 'Accept-Encoding'
        return response

    # ═══ GÜVENLİK: Response Headers ═══
    @bp.after_request
    def _security_headers(response):
        """Güvenlik header'larını tüm yanıtlara ekle."""
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        if request.environ.get('wsgi.url_scheme') == 'https':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    # ═══ İSTEK LOGLAMA ═══
    @bp.before_request
    def _log_request():
        """Gelen tüm istekleri logla."""
        request._fw_start_time = time.time()
        logger.info('[REQUEST] %s %s from=%s',
                     request.method, request.path, request.remote_addr)
        _log_store.add('INFO', 'REQUEST', request.method, request.path,
                       request.remote_addr or '-', message='İstek alındı')

    @bp.after_request
    def _log_response(response):
        """Yanıt durumunu logla."""
        level = 'WARNING' if response.status_code >= 400 else 'INFO'
        elapsed = round((time.time() - getattr(request, '_fw_start_time', time.time())) * 1000, 1)
        logger.log(logging.WARNING if response.status_code >= 400 else logging.INFO,
                   '[RESPONSE] %s %s status=%d from=%s %dms',
                   request.method, request.path, response.status_code,
                   request.remote_addr, elapsed)
        _log_store.add(level, 'RESPONSE', request.method, request.path,
                       request.remote_addr or '-', status_code=response.status_code,
                       message=f'{elapsed}ms')
        return response

    # ═══ GÜVENLİK: Rate Limiter (cache-backed, ISP modda Redis paylaşımlı) ═══
    def _rate_limited():
        """Rate limit kontrolü. Cache üzerinden atomik sayaç. Aşılırsa 429 döner."""
        if rate_limit_per_minute <= 0:
            return None
        ip = request.remote_addr or 'unknown'
        count = _cache.incr(f'rl:{ip}', ttl=60)
        if count > rate_limit_per_minute:
            logger.warning('[RATE_LIMIT] %s %s from=%s (limit=%d/min)',
                           request.method, request.path, ip, rate_limit_per_minute)
            _log_store.add('WARNING', 'RATE_LIMIT', request.method, request.path,
                          ip, status_code=429,
                          message=f'Rate limit aşıldı ({rate_limit_per_minute}/dk)')
            return jsonify({'success': False, 'message': 'Çok fazla istek. Lütfen bekleyin.'}), 429
        return None

    # ═══ GÜVENLİK: CSRF Koruması ═══
    _csrf_tokens = {}  # ip -> (token, timestamp)

    @bp.route('/api/firewall/csrf-token', methods=['GET'])
    @auth
    def api_csrf_token():
        """CSRF token üret."""
        import secrets as _secrets
        token = _secrets.token_hex(32)
        ip = request.remote_addr or 'unknown'
        _csrf_tokens[ip] = (token, time.time())
        # Eski token'ları temizle (10 dk'dan eski)
        cutoff = time.time() - 600
        for k in list(_csrf_tokens):
            if _csrf_tokens[k][1] < cutoff:
                del _csrf_tokens[k]
        return jsonify({'success': True, 'csrf_token': token})

    def _csrf_check():
        """State-changing (POST/PUT/DELETE) isteklerinde CSRF koruması."""
        if request.method == 'GET':
            return None
        # 1. Harici csrf_checker varsa kullan
        if csrf_checker is not None:
            if not csrf_checker():
                return jsonify({'success': False, 'message': 'CSRF doğrulama başarısız.'}), 403
            return None
        # 2. Token bazlı doğrulama
        token = request.headers.get('X-CSRF-Token', '')
        ip = request.remote_addr or 'unknown'
        stored = _csrf_tokens.get(ip)
        if stored and token and stored[0] == token:
            # Token geçerli, kullanıldı — yenile
            del _csrf_tokens[ip]
            return None
        # 3. Fallback: XHR header + Content-Type kontrolü
        xhr = request.headers.get('X-Requested-With', '')
        ct = request.content_type or ''
        if 'XMLHttpRequest' not in xhr and 'application/json' not in ct:
            logger.warning('[CSRF_REJECT] %s %s from=%s',
                           request.method, request.path, request.remote_addr)
            _log_store.add('WARNING', 'CSRF', request.method, request.path,
                          request.remote_addr or '-', status_code=403,
                          message='CSRF koruması reddetti')
            return jsonify({'success': False, 'message': 'İstek reddedildi (CSRF koruması).'}), 403
        return None

    # ═══ GÜVENLİK: server_id doğrulama ═══
    def _validate_server_id(server_id):
        if not _VALID_SERVER_ID_RE.match(server_id):
            return jsonify({'success': False, 'message': 'Geçersiz sunucu ID formatı.'}), 400
        return None

    # ═══ GÜVENLİK: Hata mesajı sanitizasyonu ═══
    def _safe_error_msg(e):
        """Dahili hata detaylarını dı kullanıcıya göstermez."""
        msg = str(e)
        # Dosya yolu, stack trace gibi hassas bilgileri filtrele
        if any(k in msg.lower() for k in ['traceback', '/home/', '/root/', '/etc/', 'password', 'secret']):
            logger.error('Firewall iç hata: %s', msg)
            _log_store.add('ERROR', 'ERROR', request.method, request.path,
                          request.remote_addr or '-', status_code=500,
                          message='İç sunucu hatası (detay loglandı)')
            return 'İşlem sırasında bir hata oluştu.'
        _log_store.add('ERROR', 'ERROR', request.method, request.path,
                      request.remote_addr or '-', status_code=500, message=msg)
        return msg

    def _audit(action, **kw):
        logger.info('[AUDIT] action=%s target=%s success=%s from=%s',
                    action, kw.get('target_id', '-'), kw.get('success', '-'),
                    request.remote_addr)
        _log_store.add('INFO', 'AUDIT', request.method, request.path,
                      request.remote_addr or '-',
                      server_id=kw.get('target_id', ''),
                      message=f"{action} → {'başarılı' if kw.get('success') else 'başarısız'}",
                      extra={'action': action, 'details': kw.get('details', {})})
        if audit_fn:
            audit_fn(action, **kw)

    def _check(server_id):
        """Sunucu ID doğrulama + bağlantı kontrolü + rate limit + CSRF."""
        id_err = _validate_server_id(server_id)
        if id_err:
            return id_err
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        if connection_checker and not connection_checker(server_id):
            return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400
        return None

    # ── Health Check ──
    _start_time = time.time()

    @bp.route('/api/firewall/health', methods=['GET'])
    def api_health():
        """Sistem sağlık kontrolü — auth gerektirmez."""
        return jsonify({'status': 'healthy'})

    # ── Durum ──
    @bp.route('/api/servers/<server_id>/firewall/status', methods=['GET'])
    @auth
    @perm_view
    def api_status(server_id):
        err = _check(server_id)
        if err: return err
        try:
            return jsonify({'success': True, 'firewall': fw.get_status(server_id)})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error_msg(e)}), 500

    @bp.route('/api/servers/<server_id>/firewall/enable', methods=['POST'])
    @auth
    @perm_manage
    def api_enable(server_id):
        err = _check(server_id)
        if err: return err
        ok, msg = fw.enable(server_id)
        _audit('firewall.enable', target_type='server', target_id=server_id, success=ok)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/api/servers/<server_id>/firewall/disable', methods=['POST'])
    @auth
    @perm_manage
    def api_disable(server_id):
        err = _check(server_id)
        if err: return err
        ok, msg = fw.disable(server_id)
        _audit('firewall.disable', target_type='server', target_id=server_id, success=ok)
        return jsonify({'success': ok, 'message': msg})

    # ── Kurallar ──
    @bp.route('/api/servers/<server_id>/firewall/rules', methods=['POST'])
    @auth
    @perm_manage
    def api_add_rule(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        port = (d.get('port') or '').strip()
        if not port:
            return jsonify({'success': False, 'message': 'Port girin'}), 400
        to_port = (d.get('to_port') or '').strip()
        ok, msg = fw.add_rule(server_id, port=port,
            protocol=d.get('protocol', 'tcp'), action=d.get('action', 'allow'),
            from_ip=d.get('from_ip', ''), to_port=to_port)
        _audit('firewall.add_rule', target_type='server', target_id=server_id,
               details={'port': port, 'to_port': to_port}, success=ok)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/api/servers/<server_id>/firewall/rules/<int:rule_index>', methods=['DELETE'])
    @auth
    @perm_manage
    def api_delete_rule(server_id, rule_index):
        err = _check(server_id)
        if err: return err
        ok, msg = fw.delete_rule(server_id, rule_index)
        _audit('firewall.delete_rule', target_type='server', target_id=server_id,
               details={'rule_index': rule_index}, success=ok)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/api/servers/<server_id>/firewall/services', methods=['POST'])
    @auth
    @perm_manage
    def api_add_service(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        svc = (d.get('service') or '').strip()
        if not svc:
            return jsonify({'success': False, 'message': 'Servis adı girin'}), 400
        ok, msg = fw.add_service(server_id, svc)
        _audit('firewall.add_service', target_type='server', target_id=server_id,
               details={'service': svc}, success=ok)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/api/servers/<server_id>/firewall/services/<svc_name>', methods=['DELETE'])
    @auth
    @perm_manage
    def api_remove_service(server_id, svc_name):
        err = _check(server_id)
        if err: return err
        ok, msg = fw.remove_service(server_id, svc_name)
        _audit('firewall.remove_service', target_type='server', target_id=server_id,
               details={'service': svc_name}, success=ok)
        return jsonify({'success': ok, 'message': msg})

    # ── Kural Toggle (Emare OS) ──
    @bp.route('/api/servers/<server_id>/firewall/rules/<int:rule_index>/toggle', methods=['POST'])
    @auth
    @perm_manage
    def api_toggle_rule(server_id, rule_index):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        enable = d.get('enable', True)
        ok, msg = fw.toggle_rule(server_id, rule_index, enable)
        _audit('firewall.toggle_rule', target_type='server', target_id=server_id,
               details={'rule_index': rule_index, 'enable': enable}, success=ok)
        return jsonify({'success': ok, 'message': msg})

    # ── DNS Yönetimi (Emare OS) ──
    @bp.route('/api/servers/<server_id>/firewall/dns', methods=['POST'])
    @auth
    @perm_manage
    def api_set_dns(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ok, msg = fw.set_dns(server_id,
                             servers=d.get('servers'),
                             allow_remote=d.get('allow_remote'))
        _audit('firewall.set_dns', target_type='server', target_id=server_id,
               details=d, success=ok)
        return jsonify({'success': ok, 'message': msg})

    # ══════════════════════════════════════════════════════════════
    #  ROUTING / NETWORK ENDPOINTS  (Emare OS)
    # ══════════════════════════════════════════════════════════════

    # ── Static Routes ──
    @bp.route('/api/servers/<server_id>/firewall/routes')
    @auth
    @perm_view
    def api_get_routes(server_id):
        err = _check(server_id)
        if err: return err
        return jsonify({'success': True, 'routes': fw.get_routes(server_id)})

    @bp.route('/api/servers/<server_id>/firewall/routes', methods=['POST'])
    @auth
    @perm_manage
    def api_add_route(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ok, msg = fw.add_route(server_id,
                               dst=d.get('dst', ''),
                               gateway=d.get('gateway', ''),
                               distance=d.get('distance', 1),
                               comment=d.get('comment', ''))
        _audit('firewall.add_route', target_type='server',
               target_id=server_id, details=d, success=ok)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/api/servers/<server_id>/firewall/routes/<int:idx>',
              methods=['DELETE'])
    @auth
    @perm_manage
    def api_remove_route(server_id, idx):
        err = _check(server_id)
        if err: return err
        ok, msg = fw.remove_route(server_id, idx)
        _audit('firewall.remove_route', target_type='server',
               target_id=server_id, details={'index': idx}, success=ok)
        return jsonify({'success': ok, 'message': msg})

    # ── IP Addresses ──
    @bp.route('/api/servers/<server_id>/firewall/ip-addresses')
    @auth
    @perm_view
    def api_get_ip_addresses(server_id):
        err = _check(server_id)
        if err: return err
        return jsonify({'success': True, 'addresses': fw.get_ip_addresses(server_id)})

    @bp.route('/api/servers/<server_id>/firewall/ip-addresses',
              methods=['POST'])
    @auth
    @perm_manage
    def api_add_ip_address(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ok, msg = fw.add_ip_address(server_id,
                                    address=d.get('address', ''),
                                    interface=d.get('interface', ''),
                                    comment=d.get('comment', ''))
        _audit('firewall.add_ip_address', target_type='server',
               target_id=server_id, details=d, success=ok)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/api/servers/<server_id>/firewall/ip-addresses/<int:idx>',
              methods=['DELETE'])
    @auth
    @perm_manage
    def api_remove_ip_address(server_id, idx):
        err = _check(server_id)
        if err: return err
        ok, msg = fw.remove_ip_address(server_id, idx)
        _audit('firewall.remove_ip_address', target_type='server',
               target_id=server_id, details={'index': idx}, success=ok)
        return jsonify({'success': ok, 'message': msg})

    # ── ARP ──
    @bp.route('/api/servers/<server_id>/firewall/arp')
    @auth
    @perm_view
    def api_get_arp(server_id):
        err = _check(server_id)
        if err: return err
        return jsonify({'success': True, 'arp': fw.get_arp_table(server_id)})

    @bp.route('/api/servers/<server_id>/firewall/arp', methods=['POST'])
    @auth
    @perm_manage
    def api_add_arp(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ok, msg = fw.add_arp_entry(server_id,
                                   address=d.get('address', ''),
                                   mac=d.get('mac', ''),
                                   interface=d.get('interface', ''))
        _audit('firewall.add_arp', target_type='server',
               target_id=server_id, details=d, success=ok)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/api/servers/<server_id>/firewall/arp/<int:idx>',
              methods=['DELETE'])
    @auth
    @perm_manage
    def api_remove_arp(server_id, idx):
        err = _check(server_id)
        if err: return err
        ok, msg = fw.remove_arp_entry(server_id, idx)
        _audit('firewall.remove_arp', target_type='server',
               target_id=server_id, details={'index': idx}, success=ok)
        return jsonify({'success': ok, 'message': msg})

    # ── DHCP ──
    @bp.route('/api/servers/<server_id>/firewall/dhcp')
    @auth
    @perm_view
    def api_get_dhcp(server_id):
        err = _check(server_id)
        if err: return err
        return jsonify({
            'success':  True,
            'servers':  fw.get_dhcp_servers(server_id),
            'leases':   fw.get_dhcp_leases(server_id),
            'networks': fw.get_dhcp_networks(server_id),
        })

    # ── IP Pool ──
    @bp.route('/api/servers/<server_id>/firewall/ip-pools')
    @auth
    @perm_view
    def api_get_ip_pools(server_id):
        err = _check(server_id)
        if err: return err
        return jsonify({'success': True, 'pools': fw.get_ip_pools(server_id)})

    @bp.route('/api/servers/<server_id>/firewall/ip-pools', methods=['POST'])
    @auth
    @perm_manage
    def api_add_ip_pool(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ok, msg = fw.add_ip_pool(server_id,
                                 name=d.get('name', ''),
                                 ranges=d.get('ranges', ''))
        _audit('firewall.add_ip_pool', target_type='server',
               target_id=server_id, details=d, success=ok)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/api/servers/<server_id>/firewall/ip-pools/<int:idx>',
              methods=['DELETE'])
    @auth
    @perm_manage
    def api_remove_ip_pool(server_id, idx):
        err = _check(server_id)
        if err: return err
        ok, msg = fw.remove_ip_pool(server_id, idx)
        _audit('firewall.remove_ip_pool', target_type='server',
               target_id=server_id, details={'index': idx}, success=ok)
        return jsonify({'success': ok, 'message': msg})

    # ── Queues (Bant Genişliği) ──
    @bp.route('/api/servers/<server_id>/firewall/queues')
    @auth
    @perm_view
    def api_get_queues(server_id):
        err = _check(server_id)
        if err: return err
        return jsonify({'success': True, 'queues': fw.get_queues(server_id)})

    @bp.route('/api/servers/<server_id>/firewall/queues', methods=['POST'])
    @auth
    @perm_manage
    def api_add_queue(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ok, msg = fw.add_queue(server_id,
                               name=d.get('name', ''),
                               target=d.get('target', ''),
                               max_limit=d.get('max_limit', ''),
                               comment=d.get('comment', ''))
        _audit('firewall.add_queue', target_type='server',
               target_id=server_id, details=d, success=ok)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/api/servers/<server_id>/firewall/queues/<int:idx>',
              methods=['DELETE'])
    @auth
    @perm_manage
    def api_remove_queue(server_id, idx):
        err = _check(server_id)
        if err: return err
        ok, msg = fw.remove_queue(server_id, idx)
        _audit('firewall.remove_queue', target_type='server',
               target_id=server_id, details={'index': idx}, success=ok)
        return jsonify({'success': ok, 'message': msg})

    # ── Bridge ──
    @bp.route('/api/servers/<server_id>/firewall/bridges')
    @auth
    @perm_view
    def api_get_bridges(server_id):
        err = _check(server_id)
        if err: return err
        return jsonify({'success': True, 'bridges': fw.get_bridges(server_id)})

    # ── DNS Static ──
    @bp.route('/api/servers/<server_id>/firewall/dns-static')
    @auth
    @perm_view
    def api_get_dns_static(server_id):
        err = _check(server_id)
        if err: return err
        return jsonify({'success': True, 'records': fw.get_dns_static(server_id)})

    @bp.route('/api/servers/<server_id>/firewall/dns-static', methods=['POST'])
    @auth
    @perm_manage
    def api_add_dns_static(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ok, msg = fw.add_dns_static(server_id,
                                    name=d.get('name', ''),
                                    address=d.get('address', ''))
        _audit('firewall.add_dns_static', target_type='server',
               target_id=server_id, details=d, success=ok)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/api/servers/<server_id>/firewall/dns-static/<int:idx>',
              methods=['DELETE'])
    @auth
    @perm_manage
    def api_remove_dns_static(server_id, idx):
        err = _check(server_id)
        if err: return err
        ok, msg = fw.remove_dns_static(server_id, idx)
        _audit('firewall.remove_dns_static', target_type='server',
               target_id=server_id, details={'index': idx}, success=ok)
        return jsonify({'success': ok, 'message': msg})

    # ── Neighbors ──
    @bp.route('/api/servers/<server_id>/firewall/neighbors')
    @auth
    @perm_view
    def api_get_neighbors(server_id):
        err = _check(server_id)
        if err: return err
        return jsonify({'success': True, 'neighbors': fw.get_neighbors(server_id)})

    # ── IP Engelleme ──
    @bp.route('/api/servers/<server_id>/firewall/block-ip', methods=['POST'])
    @auth
    @perm_manage
    def api_block_ip(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ip = (d.get('ip') or '').strip()
        if not ip:
            return jsonify({'success': False, 'message': 'IP girin'}), 400
        ok, msg = fw.block_ip(server_id, ip, d.get('reason', ''))
        _audit('firewall.block_ip', target_type='server', target_id=server_id,
               details={'ip': ip}, success=ok)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/api/servers/<server_id>/firewall/unblock-ip', methods=['POST'])
    @auth
    @perm_manage
    def api_unblock_ip(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ip = (d.get('ip') or '').strip()
        if not ip:
            return jsonify({'success': False, 'message': 'IP girin'}), 400
        ok, msg = fw.unblock_ip(server_id, ip)
        _audit('firewall.unblock_ip', target_type='server', target_id=server_id,
               details={'ip': ip}, success=ok)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/api/servers/<server_id>/firewall/blocked-ips', methods=['GET'])
    @auth
    @perm_view
    def api_blocked_ips(server_id):
        err = _check(server_id)
        if err: return err
        return jsonify({'success': True, 'blocked': fw.get_blocked_ips(server_id)})

    # ── Port Forward ──
    @bp.route('/api/servers/<server_id>/firewall/port-forward', methods=['POST'])
    @auth
    @perm_manage
    def api_add_fwd(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ok, msg = fw.add_port_forward(server_id, d.get('port',''), d.get('to_port',''),
                                       d.get('to_addr',''), d.get('protocol','tcp'))
        _audit('firewall.port_forward', target_type='server', target_id=server_id, success=ok)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/api/servers/<server_id>/firewall/port-forward', methods=['DELETE'])
    @auth
    @perm_manage
    def api_del_fwd(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ok, msg = fw.remove_port_forward(server_id, d.get('port',''), d.get('to_port',''),
                                          d.get('to_addr',''), d.get('protocol','tcp'))
        _audit('firewall.remove_port_forward', target_type='server', target_id=server_id, success=ok)
        return jsonify({'success': ok, 'message': msg})

    # ── Zones ──
    @bp.route('/api/servers/<server_id>/firewall/zones', methods=['GET'])
    @auth
    @perm_view
    def api_zones(server_id):
        err = _check(server_id)
        if err: return err
        return jsonify({'success': True, **fw.get_zones(server_id)})

    @bp.route('/api/servers/<server_id>/firewall/zones/<zone>', methods=['GET'])
    @auth
    @perm_view
    def api_zone_detail(server_id, zone):
        err = _check(server_id)
        if err: return err
        return jsonify({'success': True, 'detail': fw.get_zone_detail(server_id, zone)})

    @bp.route('/api/servers/<server_id>/firewall/zones/default', methods=['POST'])
    @auth
    @perm_manage
    def api_set_zone(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ok, msg = fw.set_default_zone(server_id, d.get('zone', ''))
        _audit('firewall.set_zone', target_type='server', target_id=server_id, success=ok)
        return jsonify({'success': ok, 'message': msg})

    # ── Rich Rule ──
    @bp.route('/api/servers/<server_id>/firewall/rich-rules', methods=['POST'])
    @auth
    @perm_manage
    def api_add_rich(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ok, msg = fw.add_rich_rule(server_id, d.get('rule', ''))
        _audit('firewall.add_rich_rule', target_type='server', target_id=server_id, success=ok)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/api/servers/<server_id>/firewall/rich-rules', methods=['DELETE'])
    @auth
    @perm_manage
    def api_del_rich(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ok, msg = fw.remove_rich_rule(server_id, d.get('rule', ''))
        _audit('firewall.remove_rich_rule', target_type='server', target_id=server_id, success=ok)
        return jsonify({'success': ok, 'message': msg})

    # ── Fail2ban ──
    @bp.route('/api/servers/<server_id>/firewall/fail2ban', methods=['GET'])
    @auth
    @perm_view
    def api_f2b(server_id):
        err = _check(server_id)
        if err: return err
        return jsonify({'success': True, 'fail2ban': fw.get_fail2ban_status(server_id)})

    @bp.route('/api/servers/<server_id>/firewall/fail2ban/ban', methods=['POST'])
    @auth
    @perm_manage
    def api_f2b_ban(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ok, msg = fw.fail2ban_ban(server_id, d.get('jail',''), d.get('ip',''))
        _audit('firewall.f2b_ban', target_type='server', target_id=server_id, success=ok)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/api/servers/<server_id>/firewall/fail2ban/unban', methods=['POST'])
    @auth
    @perm_manage
    def api_f2b_unban(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ok, msg = fw.fail2ban_unban(server_id, d.get('jail',''), d.get('ip',''))
        _audit('firewall.f2b_unban', target_type='server', target_id=server_id, success=ok)
        return jsonify({'success': ok, 'message': msg})

    # ── Bağlantılar ──
    @bp.route('/api/servers/<server_id>/firewall/connections', methods=['GET'])
    @auth
    @perm_view
    def api_conns(server_id):
        err = _check(server_id)
        if err: return err
        limit = max(1, min(request.args.get('limit', 50, type=int), 500))
        return jsonify({'success': True, 'connections': fw.get_connections(server_id, limit)})

    @bp.route('/api/servers/<server_id>/firewall/connection-stats', methods=['GET'])
    @auth
    @perm_view
    def api_conn_stats(server_id):
        err = _check(server_id)
        if err: return err
        return jsonify({'success': True, 'stats': fw.get_connection_stats(server_id)})

    # ── Güvenlik Taraması ──
    @bp.route('/api/servers/<server_id>/firewall/security-scan', methods=['GET'])
    @auth
    @perm_view
    def api_scan(server_id):
        err = _check(server_id)
        if err: return err
        try:
            return jsonify({'success': True, 'scan': fw.security_scan(server_id)})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error_msg(e)}), 500

    # ── Geo-Block ──
    @bp.route('/api/servers/<server_id>/firewall/geo-block', methods=['POST'])
    @auth
    @perm_manage
    def api_geo(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ok, msg = fw.geo_block_country(server_id, d.get('country_code', d.get('country', '')))
        _audit('firewall.geo_block', target_type='server', target_id=server_id, success=ok)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/api/servers/<server_id>/firewall/geo-block', methods=['DELETE'])
    @auth
    @perm_manage
    def api_geo_unblock(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ok, msg = fw.geo_unblock_country(server_id, d.get('country_code', d.get('country', '')))
        _audit('firewall.geo_unblock', target_type='server', target_id=server_id, success=ok)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/api/servers/<server_id>/firewall/geo-block', methods=['GET'])
    @auth
    @perm_view
    def api_geo_list(server_id):
        err = _check(server_id)
        if err: return err
        return jsonify({'success': True, 'blocked': fw.get_geo_blocked(server_id)})

    # ═══════════════════ L7 KORUMASI ═══════════════════

    @bp.route('/api/servers/<server_id>/firewall/l7/status', methods=['GET'])
    @auth
    @perm_view
    def api_l7_status(server_id):
        """L7 koruma durumunu sorgula."""
        err = _check(server_id)
        if err: return err
        try:
            status = fw.get_l7_status(server_id)
            return jsonify({'success': True, 'status': status})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error_msg(e)}), 500

    @bp.route('/api/servers/<server_id>/firewall/l7/apply', methods=['POST'])
    @auth
    @perm_manage
    def api_l7_apply(server_id):
        """Seçilen L7 korumalarını etkinleştir."""
        err = _check(server_id)
        if err: return err
        csrf_err = _csrf_check()
        if csrf_err: return csrf_err
        d = request.get_json(silent=True) or {}
        protections = d.get('protections', [])
        if not isinstance(protections, list) or not protections:
            return jsonify({'success': False, 'message': 'protections listesi gerekli.'}), 400
        # Max 20 koruma bir seferde
        protections = protections[:20]
        try:
            results = fw.apply_l7_protection(server_id, protections)
            all_ok = all(r.get('ok') for r in results.values())
            _audit('firewall.l7_apply', target_type='server', target_id=server_id,
                   success=all_ok, details={'protections': protections})
            return jsonify({'success': True, 'results': results})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error_msg(e)}), 500

    @bp.route('/api/servers/<server_id>/firewall/l7/remove', methods=['POST'])
    @auth
    @perm_manage
    def api_l7_remove(server_id):
        """Belirli L7 korumayı kaldır."""
        err = _check(server_id)
        if err: return err
        csrf_err = _csrf_check()
        if csrf_err: return csrf_err
        d = request.get_json(silent=True) or {}
        prot = d.get('protection', '')
        if not prot:
            return jsonify({'success': False, 'message': 'protection parametresi gerekli.'}), 400
        try:
            ok, msg = fw.remove_l7_protection(server_id, prot)
            _audit('firewall.l7_remove', target_type='server', target_id=server_id,
                   success=ok, details={'protection': prot})
            return jsonify({'success': ok, 'message': msg})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error_msg(e)}), 500

    @bp.route('/api/servers/<server_id>/firewall/l7/scan', methods=['GET'])
    @auth
    @perm_view
    def api_l7_scan(server_id):
        """L7 güvenlik taraması — skor, bulgular, öneriler."""
        err = _check(server_id)
        if err: return err
        try:
            scan = fw.l7_security_scan(server_id)
            return jsonify({'success': True, 'scan': scan})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error_msg(e)}), 500

    @bp.route('/api/servers/<server_id>/firewall/l7/apply-all', methods=['POST'])
    @auth
    @perm_manage
    def api_l7_apply_all(server_id):
        """Tüm uygulanabilir L7 korumalarını etkinleştir."""
        err = _check(server_id)
        if err: return err
        csrf_err = _csrf_check()
        if csrf_err: return csrf_err
        all_prots = sorted(fw._ALL_PROTECTIONS)
        try:
            results = fw.apply_l7_protection(server_id, all_prots)
            all_ok = all(r.get('ok') for r in results.values())
            _audit('firewall.l7_apply_all', target_type='server', target_id=server_id,
                   success=all_ok)
            return jsonify({'success': True, 'results': results})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error_msg(e)}), 500

    # ═══════════════════ ÇOK KATMANLI KORUMA (Unified) ═══════════════════

    @bp.route('/api/servers/<server_id>/firewall/protection/status', methods=['GET'])
    @auth
    @perm_view
    def api_protection_status(server_id):
        """Tüm katmanlar (L3/L4/L7) koruma durumu."""
        err = _check(server_id)
        if err: return err
        try:
            status = fw.get_l7_status(server_id)
            # Katmanlara göre grupla
            layers = {'l3': {}, 'l4': {}, 'l7_network': {}, 'l7_nginx': {}}
            for key, val in status.items():
                if key.startswith('l3_'):
                    layers['l3'][key] = val
                elif key.startswith('l4_'):
                    layers['l4'][key] = val
                elif key.startswith('nginx_'):
                    layers['l7_nginx'][key] = val
                else:
                    layers['l7_network'][key] = val
            return jsonify({'success': True, 'status': status, 'layers': layers})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error_msg(e)}), 500

    @bp.route('/api/servers/<server_id>/firewall/protection/apply', methods=['POST'])
    @auth
    @perm_manage
    def api_protection_apply(server_id):
        """Herhangi bir katman korumasını etkinleştir."""
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        protections = d.get('protections', [])
        if not isinstance(protections, list) or not protections:
            return jsonify({'success': False, 'message': 'protections listesi gerekli.'}), 400
        protections = protections[:30]
        try:
            results = fw.apply_l7_protection(server_id, protections)
            all_ok = all(r.get('ok') for r in results.values())
            _audit('firewall.protection_apply', target_type='server', target_id=server_id,
                   success=all_ok, details={'protections': protections})
            return jsonify({'success': True, 'results': results})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error_msg(e)}), 500

    @bp.route('/api/servers/<server_id>/firewall/protection/remove', methods=['POST'])
    @auth
    @perm_manage
    def api_protection_remove(server_id):
        """Herhangi bir katman korumasını kaldır."""
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        prot = d.get('protection', '')
        if not prot:
            return jsonify({'success': False, 'message': 'protection parametresi gerekli.'}), 400
        try:
            ok, msg = fw.remove_l7_protection(server_id, prot)
            _audit('firewall.protection_remove', target_type='server', target_id=server_id,
                   success=ok, details={'protection': prot})
            return jsonify({'success': ok, 'message': msg})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error_msg(e)}), 500

    @bp.route('/api/servers/<server_id>/firewall/protection/scan', methods=['GET'])
    @auth
    @perm_view
    def api_protection_scan(server_id):
        """Çok katmanlı güvenlik taraması — L3/L4/L7 skor."""
        err = _check(server_id)
        if err: return err
        try:
            scan = fw.l7_security_scan(server_id)
            return jsonify({'success': True, 'scan': scan})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error_msg(e)}), 500

    @bp.route('/api/servers/<server_id>/firewall/protection/apply-all', methods=['POST'])
    @auth
    @perm_manage
    def api_protection_apply_all(server_id):
        """Tüm katmanlarda (L3+L4+L7) tüm korumalar etkinleştir."""
        err = _check(server_id)
        if err: return err
        all_prots = sorted(fw._ALL_PROTECTIONS)
        try:
            results = fw.apply_l7_protection(server_id, all_prots)
            all_ok = all(r.get('ok') for r in results.values())
            _audit('firewall.protection_apply_all', target_type='server', target_id=server_id,
                   success=all_ok)
            return jsonify({'success': True, 'results': results})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error_msg(e)}), 500

    # ═══════════════════ LOG DASHBOARD ═══════════════════

    @bp.route('/api/firewall/logs', methods=['GET'])
    @auth
    @perm_view
    def api_logs():
        """Log girişlerini sorgula."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        limit = max(1, min(request.args.get('limit', 100, type=int), 500))
        offset = max(0, request.args.get('offset', 0, type=int))
        since_id = request.args.get('since_id', 0, type=int)
        result = _log_store.query(
            limit=limit, offset=offset,
            level=request.args.get('level', ''),
            category=request.args.get('category', ''),
            ip=request.args.get('ip', ''),
            method=request.args.get('method', ''),
            path_contains=request.args.get('path', ''),
            since_id=since_id,
            since_ts=request.args.get('since_ts', ''),
            category_prefix=request.args.get('category_prefix', ''),
        )
        return jsonify({'success': True, **result})

    @bp.route('/api/firewall/logs/stats', methods=['GET'])
    @auth
    @perm_view
    def api_log_stats():
        """Log istatistikleri."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        return jsonify({'success': True, 'stats': _log_store.get_stats()})

    @bp.route('/api/firewall/logs/clear', methods=['POST'])
    @auth
    @perm_manage
    def api_log_clear():
        """Logları temizle."""
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        _log_store.clear()
        logger.info('[AUDIT] Loglar temizlendi by %s', request.remote_addr)
        return jsonify({'success': True, 'message': 'Loglar temizlendi.'})

    @bp.route('/api/firewall/logs/ips', methods=['GET'])
    @auth
    @perm_view
    def api_log_ips():
        """Tüm IP'lerin özet listesi."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        return jsonify({'success': True, 'ips': _log_store.get_all_ips()})

    @bp.route('/api/firewall/logs/ip/<ip_addr>', methods=['GET'])
    @auth
    @perm_view
    def api_log_ip_detail(ip_addr):
        """Belirli IP'nin detaylı aktivite raporu."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        # Basit IP format doğrulaması
        if not re.match(r'^[\d.:a-fA-F]{3,45}$', ip_addr):
            return jsonify({'success': False, 'message': 'Geçersiz IP adresi.'}), 400
        detail = _log_store.get_ip_detail(ip_addr)
        return jsonify({'success': True, 'detail': detail})

    @bp.route('/firewall/logs')
    @auth
    @perm_view
    def log_dashboard_page():
        """Log dashboard HTML sayfası."""
        return render_template('logs.html')

    # ═══════════════════ L7 OLAY TOPLAMA & LOG EXPORT ═══════════════════

    @bp.route('/api/servers/<server_id>/firewall/l7/events', methods=['GET'])
    @auth
    @perm_view
    def api_l7_events(server_id):
        """Sunucudan L7 saldırı olaylarını topla ve log store'a ekle."""
        err = _check(server_id)
        if err: return err
        try:
            events = fw.collect_l7_events(server_id)
            # Olayları LogStore'a ekle
            for ev in events:
                _log_store.add(
                    ev.get('severity', 'INFO'),
                    ev['category'],
                    'SYSTEM', '/l7-event',
                    '-',
                    server_id=server_id,
                    message=f"{ev['title']}: {ev['detail']}",
                    extra={'count': ev.get('count', 0),
                           'protection': ev.get('protection', '')},
                )
            return jsonify({'success': True, 'events': events,
                           'total': len(events)})
        except Exception as e:
            return jsonify({'success': False, 'message': _safe_error_msg(e)}), 500

    @bp.route('/api/firewall/logs/l7-summary', methods=['GET'])
    @auth
    @perm_view
    def api_l7_summary():
        """L7 saldırı olay özeti."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        return jsonify({'success': True, 'summary': _log_store.get_l7_summary()})

    @bp.route('/api/firewall/logs/export', methods=['GET'])
    @auth
    @perm_view
    def api_log_export():
        """Logları CSV veya JSON olarak export et."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        fmt = request.args.get('format', 'json')
        if fmt not in ('json', 'csv'):
            return jsonify({'success': False, 'message': 'Geçersiz format. json veya csv kullanın.'}), 400
        limit = max(1, min(request.args.get('limit', 5000, type=int), 10000))
        cat_prefix = request.args.get('category_prefix', '')
        since_ts = request.args.get('since_ts', '')
        content = _log_store.export(fmt=fmt, limit=limit,
                                    category_prefix=cat_prefix,
                                    since_ts=since_ts)
        content_type = 'text/csv' if fmt == 'csv' else 'application/json'
        from flask import Response
        resp = Response(content, mimetype=content_type)
        ext = 'csv' if fmt == 'csv' else 'json'
        resp.headers['Content-Disposition'] = f'attachment; filename=emare_security_os_logs.{ext}'
        return resp

    @bp.route('/api/firewall/logs/db-info', methods=['GET'])
    @auth
    @perm_view
    def api_log_db_info():
        """Log veritabanı bilgilerini döndürür."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        return jsonify({'success': True, 'db_info': _log_store.get_db_info()})

    # ═══════════════════ YEDEKLEME / GERİ YÜKLEME ═══════════════════

    def _log_action(action, server_id, message=''):
        """Yedekleme işlemlerini log store'a kaydeder."""
        _log_store.add('INFO', action, 'SYSTEM', '/backup',
                      '-', server_id=server_id, message=message)

    @bp.route('/api/servers/<server_id>/firewall/backups', methods=['GET'])
    @auth
    @perm_view
    def api_list_backups(server_id):
        """Tüm yedekleri listeler."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        if not _VALID_SERVER_ID_RE.match(server_id):
            return jsonify({'success': False, 'message': 'Geçersiz server_id'}), 400
        backups = fw.list_backups(server_id)
        return jsonify({'success': True, 'backups': backups})

    @bp.route('/api/servers/<server_id>/firewall/backups', methods=['POST'])
    @auth
    @perm_manage
    def api_create_backup(server_id):
        """Yeni yedek oluşturur."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        if not _VALID_SERVER_ID_RE.match(server_id):
            return jsonify({'success': False, 'message': 'Geçersiz server_id'}), 400
        d = request.get_json(silent=True) or {}
        name = str(d.get('name', ''))[:64]
        ok, info = fw.backup_firewall(server_id, name=name)
        if ok:
            _log_action('BACKUP_CREATE', server_id, f"Yedek oluşturuldu: {info.get('id','')}")
        return jsonify({'success': ok, 'backup': info if ok else None,
                        'message': info if not ok else 'Yedek oluşturuldu.'})

    @bp.route('/api/servers/<server_id>/firewall/backups/restore', methods=['POST'])
    @auth
    @perm_manage
    def api_restore_backup(server_id):
        """Yedeği geri yükler."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        if not _VALID_SERVER_ID_RE.match(server_id):
            return jsonify({'success': False, 'message': 'Geçersiz server_id'}), 400
        d = request.get_json(silent=True) or {}
        backup_id = str(d.get('backup_id', ''))
        if not backup_id:
            return jsonify({'success': False, 'message': 'backup_id gerekli'}), 400
        ok, msg = fw.restore_firewall(server_id, backup_id)
        if ok:
            _log_action('BACKUP_RESTORE', server_id, f"Yedek geri yüklendi: {backup_id}")
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/api/servers/<server_id>/firewall/backups/<backup_id>', methods=['DELETE'])
    @auth
    @perm_manage
    def api_delete_backup(server_id, backup_id):
        """Yedeği siler."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        if not _VALID_SERVER_ID_RE.match(server_id):
            return jsonify({'success': False, 'message': 'Geçersiz server_id'}), 400
        ok, msg = fw.delete_backup(server_id, backup_id)
        if ok:
            _log_action('BACKUP_DELETE', server_id, f"Yedek silindi: {backup_id}")
        return jsonify({'success': ok, 'message': msg})

    # ═══════════════════ NETWORK ANALYSER ═══════════════════

    @bp.route('/api/servers/<server_id>/network/summary', methods=['GET'])
    @auth
    @perm_view
    def api_net_summary(server_id):
        """Ağ analiz özeti (dashboard)."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        err = _validate_server_id(server_id)
        if err:
            return err
        return jsonify({'success': True, 'data': fw.net_summary(server_id)})

    @bp.route('/api/servers/<server_id>/network/bandwidth', methods=['GET'])
    @auth
    @perm_view
    def api_net_bandwidth(server_id):
        """Interface bant genişliği/trafik istatistikleri."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        err = _validate_server_id(server_id)
        if err:
            return err
        return jsonify({'success': True, 'data': fw.net_bandwidth(server_id)})

    @bp.route('/api/servers/<server_id>/network/ping', methods=['POST'])
    @auth
    @perm_view
    def api_net_ping(server_id):
        """Ping testi."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        err = _validate_server_id(server_id)
        if err:
            return err
        d = request.get_json(silent=True) or {}
        target = str(d.get('target', '')).strip()
        if not target:
            return jsonify({'success': False, 'message': 'target gerekli'}), 400
        count = int(d.get('count', 4))
        result = fw.net_ping(server_id, target, count)
        _log_action('NET_PING', server_id, f"Ping: {target}")
        return jsonify({'success': True, 'data': result})

    @bp.route('/api/servers/<server_id>/network/traceroute', methods=['POST'])
    @auth
    @perm_view
    def api_net_traceroute(server_id):
        """Traceroute."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        err = _validate_server_id(server_id)
        if err:
            return err
        d = request.get_json(silent=True) or {}
        target = str(d.get('target', '')).strip()
        if not target:
            return jsonify({'success': False, 'message': 'target gerekli'}), 400
        max_hops = int(d.get('max_hops', 20))
        result = fw.net_traceroute(server_id, target, max_hops)
        _log_action('NET_TRACEROUTE', server_id, f"Traceroute: {target}")
        return jsonify({'success': True, 'data': result})

    @bp.route('/api/servers/<server_id>/network/dns-lookup', methods=['POST'])
    @auth
    @perm_view
    def api_net_dns_lookup(server_id):
        """DNS sorgusu."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        err = _validate_server_id(server_id)
        if err:
            return err
        d = request.get_json(silent=True) or {}
        domain = str(d.get('domain', '')).strip()
        if not domain:
            return jsonify({'success': False, 'message': 'domain gerekli'}), 400
        rtype = str(d.get('type', 'A'))
        result = fw.net_dns_lookup(server_id, domain, rtype)
        _log_action('NET_DNS', server_id, f"DNS: {domain} ({rtype})")
        return jsonify({'success': True, 'data': result})

    @bp.route('/api/servers/<server_id>/network/port-check', methods=['POST'])
    @auth
    @perm_view
    def api_net_port_check(server_id):
        """Port bağlantı testi."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        err = _validate_server_id(server_id)
        if err:
            return err
        d = request.get_json(silent=True) or {}
        target = str(d.get('target', '')).strip()
        port = d.get('port')
        if not target or port is None:
            return jsonify({'success': False, 'message': 'target ve port gerekli'}), 400
        protocol = str(d.get('protocol', 'tcp'))
        result = fw.net_port_check(server_id, target, int(port), protocol)
        _log_action('NET_PORT_CHECK', server_id, f"Port kontrol: {target}:{port}")
        return jsonify({'success': True, 'data': result})

    @bp.route('/api/servers/<server_id>/network/top-talkers', methods=['GET'])
    @auth
    @perm_view
    def api_net_top_talkers(server_id):
        """En çok bağlantı yapan IP'ler."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        err = _validate_server_id(server_id)
        if err:
            return err
        limit = max(1, min(request.args.get('limit', 20, type=int), 500))
        return jsonify({'success': True, 'data': fw.net_top_talkers(server_id, limit)})

    @bp.route('/api/servers/<server_id>/network/listening-ports', methods=['GET'])
    @auth
    @perm_view
    def api_net_listening_ports(server_id):
        """Dinleyen portlar."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        err = _validate_server_id(server_id)
        if err:
            return err
        return jsonify({'success': True, 'data': fw.net_listening_ports(server_id)})

    @bp.route('/api/servers/<server_id>/network/packet-capture', methods=['POST'])
    @auth
    @perm_manage
    def api_net_packet_capture(server_id):
        """Paket yakalama (tcpdump snapshot)."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        err = _validate_server_id(server_id)
        if err:
            return err
        d = request.get_json(silent=True) or {}
        iface = str(d.get('interface', 'any'))
        count = int(d.get('count', 50))
        filt = str(d.get('filter', ''))
        result = fw.net_packet_capture(server_id, iface, count, filt)
        _log_action('NET_CAPTURE', server_id, f"Paket yakalama: {iface} ({count})")
        return jsonify({'success': True, 'data': result})

    @bp.route('/api/servers/<server_id>/network/speed-test', methods=['POST'])
    @auth
    @perm_manage
    def api_net_speed_test(server_id):
        """Hız testi."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        err = _validate_server_id(server_id)
        if err:
            return err
        d = request.get_json(silent=True) or {}
        target = str(d.get('target', '8.8.8.8'))
        duration = int(d.get('duration', 5))
        result = fw.net_speed_test(server_id, target, duration)
        _log_action('NET_SPEED', server_id, f"Hız testi: {target}")
        return jsonify({'success': True, 'data': result})

    @bp.route('/api/servers/<server_id>/network/whois', methods=['POST'])
    @auth
    @perm_view
    def api_net_whois(server_id):
        """WHOIS sorgusu."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        err = _validate_server_id(server_id)
        if err:
            return err
        d = request.get_json(silent=True) or {}
        target = str(d.get('target', '')).strip()
        if not target:
            return jsonify({'success': False, 'message': 'target gerekli'}), 400
        result = fw.net_whois(server_id, target)
        _log_action('NET_WHOIS', server_id, f"WHOIS: {target}")
        return jsonify({'success': True, 'data': result})

    # ═══════════════════════════════════════════════════════════════════
    # ISP MULTI-TENANT ENDPOINTLERİ
    # ═══════════════════════════════════════════════════════════════════
    _ts = tenant_store  # kısa referans

    def _isp_admin_check():
        """ISP admin endpointleri için yetki + rate limit + CSRF kontrolü."""
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        return None

    def _tenant_from_key():
        """X-API-Key header'ından tenant doğrulama."""
        if not _ts:
            return None
        api_key = request.headers.get('X-API-Key', '')
        if not api_key:
            return None
        return _ts.authenticate_by_key(api_key)

    # ── Tenant CRUD ──

    @bp.route('/api/isp/tenants', methods=['GET'])
    @auth
    def api_isp_list_tenants():
        chk = _isp_admin_check()
        if chk:
            return chk
        active = request.args.get('active', '1') == '1'
        return jsonify({'success': True, 'tenants': _ts.list_tenants(active)})

    @bp.route('/api/isp/tenants', methods=['POST'])
    @auth
    def api_isp_create_tenant():
        chk = _isp_admin_check()
        if chk:
            return chk
        d = request.get_json(silent=True) or {}
        name = str(d.get('name', '')).strip()
        email = str(d.get('email', '')).strip()
        plan = str(d.get('plan', 'bronze')).strip()
        result = _ts.create_tenant(name, email, plan)
        if result.get('success'):
            _ts.add_audit(result['tenant']['id'], 'tenant_create',
                          user_ip=request.remote_addr,
                          resource_type='tenant',
                          resource_id=str(result['tenant']['id']))
        return jsonify(result), 201 if result.get('success') else 400

    @bp.route('/api/isp/tenants/<int:tenant_id>', methods=['GET'])
    @auth
    def api_isp_get_tenant(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        t = _ts.get_tenant(tenant_id)
        if not t:
            return jsonify({'success': False, 'message': 'Tenant bulunamadı.'}), 404
        return jsonify({'success': True, 'tenant': t})

    @bp.route('/api/isp/tenants/<int:tenant_id>', methods=['PUT'])
    @auth
    def api_isp_update_tenant(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        d = request.get_json(silent=True) or {}
        result = _ts.update_tenant(tenant_id, **d)
        if result.get('success'):
            _ts.add_audit(tenant_id, 'tenant_update',
                          user_ip=request.remote_addr,
                          resource_type='tenant',
                          resource_id=str(tenant_id),
                          details=d)
        return jsonify(result), 200 if result.get('success') else 400

    @bp.route('/api/isp/tenants/<int:tenant_id>', methods=['DELETE'])
    @auth
    def api_isp_delete_tenant(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        result = _ts.delete_tenant(tenant_id)
        return jsonify(result), 200 if result.get('success') else 404

    @bp.route('/api/isp/tenants/<int:tenant_id>/regenerate-key', methods=['POST'])
    @auth
    def api_isp_regenerate_key(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        result = _ts.regenerate_api_key(tenant_id)
        if result.get('success'):
            _ts.add_audit(tenant_id, 'api_key_regenerate',
                          user_ip=request.remote_addr,
                          resource_type='tenant',
                          resource_id=str(tenant_id))
        return jsonify(result), 200 if result.get('success') else 404

    # ── Sunucu Yönetimi ──

    @bp.route('/api/isp/tenants/<int:tenant_id>/servers', methods=['GET'])
    @auth
    def api_isp_list_servers(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        return jsonify({'success': True, 'servers': _ts.list_servers(tenant_id)})

    @bp.route('/api/isp/tenants/<int:tenant_id>/servers', methods=['POST'])
    @auth
    def api_isp_add_server(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        d = request.get_json(silent=True) or {}
        result = _ts.add_server(
            tenant_id,
            server_id=str(d.get('server_id', '')),
            ssh_host=str(d.get('ssh_host', '')),
            ssh_user=str(d.get('ssh_user', 'root')),
            ssh_port=int(d.get('ssh_port', 22)),
            ssh_key_ref=str(d.get('ssh_key_ref', '')),
            label=str(d.get('label', '')),
        )
        if result.get('success'):
            _ts.add_audit(tenant_id, 'server_add',
                          user_ip=request.remote_addr,
                          resource_type='server',
                          resource_id=d.get('server_id', ''))
        return jsonify(result), 201 if result.get('success') else 400

    @bp.route('/api/isp/tenants/<int:tenant_id>/servers/<server_id>', methods=['DELETE'])
    @auth
    def api_isp_remove_server(tenant_id, server_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        result = _ts.remove_server(tenant_id, server_id)
        if result.get('success'):
            _ts.add_audit(tenant_id, 'server_remove',
                          user_ip=request.remote_addr,
                          resource_type='server',
                          resource_id=server_id)
        return jsonify(result), 200 if result.get('success') else 404

    # ── Audit Trail ──

    @bp.route('/api/isp/audit', methods=['GET'])
    @auth
    def api_isp_audit():
        chk = _isp_admin_check()
        if chk:
            return chk
        tid = request.args.get('tenant_id', type=int)
        limit = max(1, min(request.args.get('limit', 100, type=int), 1000))
        action = request.args.get('action', '')
        since = request.args.get('since', '')
        logs = _ts.query_audit(tenant_id=tid, limit=limit,
                               action=action, since_ts=since)
        return jsonify({'success': True, 'audit_logs': logs})

    # ── Webhook Yönetimi ──

    @bp.route('/api/isp/tenants/<int:tenant_id>/webhooks', methods=['GET'])
    @auth
    def api_isp_list_webhooks(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        return jsonify({'success': True, 'webhooks': _ts.list_webhooks(tenant_id)})

    @bp.route('/api/isp/tenants/<int:tenant_id>/webhooks', methods=['POST'])
    @auth
    def api_isp_add_webhook(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        d = request.get_json(silent=True) or {}
        url = str(d.get('url', ''))
        events = d.get('events', [])
        if not isinstance(events, list):
            return jsonify({'success': False, 'message': 'events liste olmalı.'}), 400
        result = _ts.add_webhook(tenant_id, url, events,
                                 secret=str(d.get('secret', '')))
        return jsonify(result), 201 if result.get('success') else 400

    @bp.route('/api/isp/tenants/<int:tenant_id>/webhooks/<int:webhook_id>', methods=['DELETE'])
    @auth
    def api_isp_remove_webhook(tenant_id, webhook_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        result = _ts.remove_webhook(tenant_id, webhook_id)
        return jsonify(result), 200 if result.get('success') else 404

    # ── Alert Yönetimi ──

    @bp.route('/api/isp/tenants/<int:tenant_id>/alerts', methods=['GET'])
    @auth
    def api_isp_list_alerts(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        unack = request.args.get('unacknowledged', '0') == '1'
        limit = max(1, min(request.args.get('limit', 50, type=int), 500))
        return jsonify({'success': True,
                        'alerts': _ts.list_alerts(tenant_id, limit, unack)})

    @bp.route('/api/isp/tenants/<int:tenant_id>/alerts', methods=['POST'])
    @auth
    def api_isp_create_alert(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        d = request.get_json(silent=True) or {}
        aid = _ts.add_alert(
            tenant_id,
            alert_type=str(d.get('alert_type', 'custom')),
            message=str(d.get('message', '')),
            server_id=str(d.get('server_id', '')),
            severity=str(d.get('severity', 'warning')),
            details=d.get('details'),
        )
        if webhook_dispatcher:
            webhook_dispatcher.trigger(tenant_id, 'l7_alert', {
                'alert_id': aid, 'type': d.get('alert_type'),
                'message': d.get('message'), 'severity': d.get('severity'),
            })
        return jsonify({'success': True, 'alert_id': aid}), 201

    @bp.route('/api/isp/tenants/<int:tenant_id>/alerts/<int:alert_id>/ack', methods=['POST'])
    @auth
    def api_isp_ack_alert(tenant_id, alert_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        result = _ts.acknowledge_alert(tenant_id, alert_id)
        return jsonify(result), 200 if result.get('success') else 404

    # ── Zamanlanmış Görevler ──

    @bp.route('/api/isp/tenants/<int:tenant_id>/scheduled', methods=['GET'])
    @auth
    def api_isp_list_scheduled(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        return jsonify({'success': True,
                        'tasks': _ts.list_scheduled_tasks(tenant_id)})

    @bp.route('/api/isp/tenants/<int:tenant_id>/scheduled', methods=['POST'])
    @auth
    def api_isp_add_scheduled(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        d = request.get_json(silent=True) or {}
        result = _ts.add_scheduled_task(
            tenant_id,
            task_type=str(d.get('task_type', '')),
            cron_expr=str(d.get('cron_expr', '')),
            server_id=str(d.get('server_id', '')),
            payload=d.get('payload'),
        )
        return jsonify(result), 201 if result.get('success') else 400

    @bp.route('/api/isp/tenants/<int:tenant_id>/scheduled/<int:task_id>', methods=['DELETE'])
    @auth
    def api_isp_remove_scheduled(tenant_id, task_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        result = _ts.remove_scheduled_task(tenant_id, task_id)
        return jsonify(result), 200 if result.get('success') else 404

    # ── Bulk İşlemler ──

    @bp.route('/api/isp/tenants/<int:tenant_id>/bulk', methods=['POST'])
    @auth
    def api_isp_bulk_operation(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        d = request.get_json(silent=True) or {}
        job_type = str(d.get('job_type', ''))
        operations = d.get('operations', [])
        if not isinstance(operations, list) or not operations:
            return jsonify({'success': False, 'message': 'operations listesi gerekli.'}), 400
        valid_jobs = {'rule_add', 'rule_delete', 'ip_block', 'ip_unblock',
                      'l7_enable', 'l7_disable'}
        if job_type not in valid_jobs:
            return jsonify({'success': False,
                            'message': f'Geçersiz job_type. İzin: {", ".join(sorted(valid_jobs))}'}), 400
        job_id = _ts.create_bulk_job(tenant_id, job_type, len(operations),
                                     payload={'operations': operations})
        # Senkron çalıştır (küçük batchler için OK, büyük batchler ileride async)
        import threading as _thr
        def _run_bulk():
            completed = 0
            failed = 0
            results = []
            for op in operations:
                sid = op.get('server_id', '')
                try:
                    if job_type == 'rule_add':
                        rule = op.get('rule', {})
                        if isinstance(rule, dict):
                            r = fw.add_rule(sid, port=rule.get('port', ''),
                                            protocol=rule.get('protocol', 'tcp'),
                                            action=rule.get('action', 'allow'),
                                            direction=rule.get('direction', 'in'),
                                            from_ip=rule.get('from_ip', ''))
                        else:
                            r = (False, 'rule dict gerekli')
                    elif job_type == 'rule_delete':
                        rn = op.get('rule_number', '')
                        r = fw.delete_rule(sid, int(rn))
                    elif job_type == 'ip_block':
                        r = fw.block_ip(sid, op.get('ip', ''))
                    elif job_type == 'ip_unblock':
                        r = fw.unblock_ip(sid, op.get('ip', ''))
                    elif job_type == 'l7_enable':
                        ptype = op.get('protection_type', '')
                        r = fw.apply_l7_protection(sid, [ptype]) if ptype else (False, 'protection_type gerekli')
                    elif job_type == 'l7_disable':
                        ptype = op.get('protection_type', '')
                        r = fw.remove_l7_protection(sid, ptype) if ptype else (False, 'protection_type gerekli')
                    else:
                        r = (False, 'Bilinmeyen işlem')
                    if isinstance(r, tuple):
                        ok = r[0]
                        msg = r[1] if len(r) > 1 else ''
                    elif isinstance(r, dict):
                        ok = all(v.get('ok') for v in r.values()) if r else False
                        msg = ''
                    else:
                        ok = False
                        msg = str(r)
                    results.append({'server_id': sid, 'success': ok,
                                    'message': msg})
                    if ok:
                        completed += 1
                    else:
                        failed += 1
                except Exception as e:
                    failed += 1
                    results.append({'server_id': sid, 'success': False,
                                    'message': str(e)})
            status = 'completed' if failed == 0 else ('failed' if completed == 0 else 'completed')
            _ts.update_bulk_job(job_id, completed=completed, failed=failed,
                                results=results, status=status)
        _thr.Thread(target=_run_bulk, daemon=True).start()
        return jsonify({'success': True, 'job_id': job_id,
                        'message': 'Bulk iş başlatıldı.'}), 202

    @bp.route('/api/isp/bulk/<int:job_id>', methods=['GET'])
    @auth
    def api_isp_bulk_status(job_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        job = _ts.get_bulk_job(job_id)
        if not job:
            return jsonify({'success': False, 'message': 'Job bulunamadı.'}), 404
        return jsonify({'success': True, 'job': job})

    @bp.route('/api/isp/tenants/<int:tenant_id>/bulk/history', methods=['GET'])
    @auth
    def api_isp_bulk_history(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        limit = max(1, min(request.args.get('limit', 20, type=int), 500))
        return jsonify({'success': True,
                        'jobs': _ts.list_bulk_jobs(tenant_id, limit)})

    # ── CGNAT Yönetimi ──

    @bp.route('/api/isp/tenants/<int:tenant_id>/cgnat/pools', methods=['GET'])
    @auth
    def api_isp_cgnat_pools(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        return jsonify({'success': True, 'pools': _ts.list_cgnat_pools(tenant_id)})

    @bp.route('/api/isp/tenants/<int:tenant_id>/cgnat/pools', methods=['POST'])
    @auth
    def api_isp_cgnat_add_pool(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        d = request.get_json(silent=True) or {}
        result = _ts.add_cgnat_pool(
            tenant_id,
            pool_name=str(d.get('pool_name', '')),
            public_ip=str(d.get('public_ip', '')),
            port_start=int(d.get('port_start', 1024)),
            port_end=int(d.get('port_end', 65535)),
            ports_per_subscriber=int(d.get('ports_per_subscriber', 1024)),
        )
        return jsonify(result), 201 if result.get('success') else 400

    @bp.route('/api/isp/cgnat/<int:pool_id>/allocate', methods=['POST'])
    @auth
    def api_isp_cgnat_allocate(pool_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        d = request.get_json(silent=True) or {}
        subscriber_ip = str(d.get('subscriber_ip', ''))
        if not subscriber_ip:
            return jsonify({'success': False, 'message': 'subscriber_ip gerekli.'}), 400
        result = _ts.allocate_cgnat(pool_id, subscriber_ip)
        return jsonify(result), 200 if result.get('success') else 400

    @bp.route('/api/isp/cgnat/<int:pool_id>/release', methods=['POST'])
    @auth
    def api_isp_cgnat_release(pool_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        d = request.get_json(silent=True) or {}
        subscriber_ip = str(d.get('subscriber_ip', ''))
        result = _ts.release_cgnat(pool_id, subscriber_ip)
        return jsonify(result), 200 if result.get('success') else 400

    @bp.route('/api/isp/cgnat/<int:pool_id>/mappings', methods=['GET'])
    @auth
    def api_isp_cgnat_mappings(pool_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        return jsonify({'success': True,
                        'mappings': _ts.list_cgnat_mappings(pool_id)})

    # ── IPAM (IP Adres Yönetimi) ──

    @bp.route('/api/isp/tenants/<int:tenant_id>/ipam/blocks', methods=['GET'])
    @auth
    def api_isp_ipam_blocks(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        return jsonify({'success': True, 'blocks': _ts.list_ipam_blocks(tenant_id)})

    @bp.route('/api/isp/tenants/<int:tenant_id>/ipam/blocks', methods=['POST'])
    @auth
    def api_isp_ipam_add_block(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        d = request.get_json(silent=True) or {}
        result = _ts.add_ipam_block(
            tenant_id,
            cidr=str(d.get('cidr', '')),
            description=str(d.get('description', '')),
            block_type=str(d.get('block_type', 'assigned')),
            vlan=d.get('vlan'),
            gateway=str(d.get('gateway', '')),
        )
        return jsonify(result), 201 if result.get('success') else 400

    @bp.route('/api/isp/tenants/<int:tenant_id>/ipam/blocks/<int:block_id>', methods=['DELETE'])
    @auth
    def api_isp_ipam_remove_block(tenant_id, block_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        result = _ts.remove_ipam_block(tenant_id, block_id)
        return jsonify(result), 200 if result.get('success') else 404

    @bp.route('/api/isp/ipam/<int:block_id>/assign', methods=['POST'])
    @auth
    def api_isp_ipam_assign(block_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        d = request.get_json(silent=True) or {}
        result = _ts.assign_ip(
            block_id,
            ip_address=str(d.get('ip_address', '')),
            assigned_to=str(d.get('assigned_to', '')),
            mac_address=str(d.get('mac_address', '')),
            note=str(d.get('note', '')),
        )
        return jsonify(result), 201 if result.get('success') else 400

    @bp.route('/api/isp/ipam/release', methods=['POST'])
    @auth
    def api_isp_ipam_release():
        chk = _isp_admin_check()
        if chk:
            return chk
        d = request.get_json(silent=True) or {}
        ip = str(d.get('ip_address', ''))
        result = _ts.release_ip(ip)
        return jsonify(result), 200 if result.get('success') else 404

    @bp.route('/api/isp/ipam/<int:block_id>/assignments', methods=['GET'])
    @auth
    def api_isp_ipam_assignments(block_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        return jsonify({'success': True,
                        'assignments': _ts.list_ipam_assignments(block_id)})

    # ── ISP Dashboard / Raporlama ──

    @bp.route('/api/isp/dashboard', methods=['GET'])
    @auth
    def api_isp_dashboard():
        chk = _isp_admin_check()
        if chk:
            return chk
        return jsonify({'success': True, 'dashboard': _ts.get_isp_dashboard()})

    @bp.route('/api/isp/tenants/<int:tenant_id>/report', methods=['GET'])
    @auth
    def api_isp_tenant_report(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        report = _ts.get_tenant_report(tenant_id)
        if not report:
            return jsonify({'success': False, 'message': 'Tenant bulunamadı.'}), 404
        return jsonify({'success': True, 'report': report})

    # ── Batch Import/Export ──

    @bp.route('/api/isp/tenants/<int:tenant_id>/batch/export-rules', methods=['POST'])
    @auth
    def api_isp_batch_export_rules(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        d = request.get_json(silent=True) or {}
        server_id = str(d.get('server_id', ''))
        if not server_id:
            return jsonify({'success': False, 'message': 'server_id gerekli.'}), 400
        err = _validate_server_id(server_id)
        if err:
            return err
        status = fw.get_status(server_id)
        if not status.get('success'):
            return jsonify(status), 400
        return jsonify({'success': True, 'server_id': server_id,
                        'rules': status.get('rules', []),
                        'exported_at': datetime.now(timezone.utc).isoformat()})

    @bp.route('/api/isp/tenants/<int:tenant_id>/batch/import-rules', methods=['POST'])
    @auth
    def api_isp_batch_import_rules(tenant_id):
        chk = _isp_admin_check()
        if chk:
            return chk
        d = request.get_json(silent=True) or {}
        server_id = str(d.get('server_id', ''))
        rules = d.get('rules', [])
        if not server_id or not rules:
            return jsonify({'success': False, 'message': 'server_id ve rules gerekli.'}), 400
        err = _validate_server_id(server_id)
        if err:
            return err
        results = []
        ok_count = 0
        for rule in rules:
            if not isinstance(rule, dict):
                results.append({'success': False, 'message': 'Geçersiz kural formatı'})
                continue
            r = fw.add_rule(server_id, rule)
            ok = r.get('success', False) if isinstance(r, dict) else False
            if ok:
                ok_count += 1
            results.append(r if isinstance(r, dict) else {'success': False, 'message': str(r)})
        _ts.add_audit(tenant_id, 'batch_import_rules',
                      user_ip=request.remote_addr,
                      resource_type='rules',
                      resource_id=server_id,
                      details={'total': len(rules), 'success': ok_count})
        return jsonify({'success': True, 'total': len(rules),
                        'imported': ok_count, 'results': results})

    # ── 5651 Log Compliance ──────────────────────────────
    @bp.route('/api/firewall/logs/5651/status', methods=['GET'])
    @auth
    def law5651_status():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        result = log_store.get_5651_status()
        return jsonify(success=True, data=result)

    @bp.route('/api/firewall/logs/5651/verify', methods=['GET'])
    @auth
    def law5651_verify():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        limit = max(1, min(request.args.get('limit', 5000, type=int), 50000))
        result = log_store.verify_5651_chain(limit=limit)
        return jsonify(success=True, data=result)

    @bp.route('/api/firewall/logs/5651/seal', methods=['POST'])
    @auth
    def law5651_seal():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        body = request.get_json(silent=True) or {}
        note = str(body.get('note', 'manual-seal'))[:200]
        result = log_store.seal_5651(note=note)
        return jsonify(success=True, data=result)

    # ═══════════════════ NETWORK (Çoklu Ağ Yönetimi) ═══════════════════
    # Network CRUD — bellekte tutulan ağ tanımları
    _networks = {}
    _network_seq = [0]
    _VALID_NETWORK_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9 _.-]{0,127}$')

    @bp.route('/api/networks', methods=['GET'])
    @auth
    def api_list_networks():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        nets = sorted(_networks.values(), key=lambda n: n['id'])
        return jsonify(success=True, networks=nets)

    @bp.route('/api/networks', methods=['POST'])
    @auth
    def api_create_network():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        d = request.get_json(silent=True) or {}
        name = str(d.get('name', '')).strip()
        if not name or not _VALID_NETWORK_NAME_RE.match(name):
            return jsonify(success=False, message='Geçersiz ağ adı.'), 400
        description = str(d.get('description', ''))[:500]
        dns_servers = d.get('dns_servers', [])
        if not isinstance(dns_servers, list):
            dns_servers = []
        dns_servers = [str(s).strip() for s in dns_servers[:10] if str(s).strip()]
        server_ids = d.get('server_ids', [])
        if not isinstance(server_ids, list):
            server_ids = []
        server_ids = [str(s).strip() for s in server_ids[:100]
                      if str(s).strip() and _VALID_SERVER_ID_RE.match(str(s).strip())]
        _network_seq[0] += 1
        net = {
            'id': _network_seq[0],
            'name': name,
            'description': description,
            'dns_servers': dns_servers,
            'server_ids': server_ids,
            'routing_policy': str(d.get('routing_policy', ''))[:200],
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        _networks[net['id']] = net
        _audit('network.create', target_type='network', target_id=str(net['id']),
               success=True, details={'name': name})
        return jsonify(success=True, network=net), 201

    @bp.route('/api/networks/<int:network_id>', methods=['GET'])
    @auth
    def api_get_network(network_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        net = _networks.get(network_id)
        if not net:
            return jsonify(success=False, message='Ağ bulunamadı.'), 404
        return jsonify(success=True, network=net)

    @bp.route('/api/networks/<int:network_id>', methods=['PUT'])
    @auth
    def api_update_network(network_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        net = _networks.get(network_id)
        if not net:
            return jsonify(success=False, message='Ağ bulunamadı.'), 404
        d = request.get_json(silent=True) or {}
        if 'name' in d:
            name = str(d['name']).strip()
            if not name or not _VALID_NETWORK_NAME_RE.match(name):
                return jsonify(success=False, message='Geçersiz ağ adı.'), 400
            net['name'] = name
        if 'description' in d:
            net['description'] = str(d['description'])[:500]
        if 'dns_servers' in d:
            dns = d['dns_servers']
            if isinstance(dns, list):
                net['dns_servers'] = [str(s).strip() for s in dns[:10] if str(s).strip()]
        if 'server_ids' in d:
            sids = d['server_ids']
            if isinstance(sids, list):
                net['server_ids'] = [str(s).strip() for s in sids[:100]
                                     if str(s).strip() and _VALID_SERVER_ID_RE.match(str(s).strip())]
        if 'routing_policy' in d:
            net['routing_policy'] = str(d['routing_policy'])[:200]
        _audit('network.update', target_type='network', target_id=str(network_id),
               success=True, details={'name': net['name']})
        return jsonify(success=True, network=net)

    @bp.route('/api/networks/<int:network_id>', methods=['DELETE'])
    @auth
    def api_delete_network(network_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        net = _networks.pop(network_id, None)
        if not net:
            return jsonify(success=False, message='Ağ bulunamadı.'), 404
        _audit('network.delete', target_type='network', target_id=str(network_id),
               success=True, details={'name': net['name']})
        return jsonify(success=True, message=f"Ağ '{net['name']}' silindi.")

    @bp.route('/api/networks/<int:network_id>/members', methods=['POST'])
    @auth
    def api_add_network_member(network_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        net = _networks.get(network_id)
        if not net:
            return jsonify(success=False, message='Ağ bulunamadı.'), 404
        d = request.get_json(silent=True) or {}
        sid = str(d.get('server_id', '')).strip()
        if not sid or not _VALID_SERVER_ID_RE.match(sid):
            return jsonify(success=False, message='Geçersiz sunucu ID.'), 400
        if sid in net['server_ids']:
            return jsonify(success=False, message='Sunucu zaten bu ağda.'), 409
        net['server_ids'].append(sid)
        return jsonify(success=True, message=f'{sid} ağa eklendi.', network=net)

    @bp.route('/api/networks/<int:network_id>/members/<server_id>', methods=['DELETE'])
    @auth
    def api_remove_network_member(network_id, server_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        net = _networks.get(network_id)
        if not net:
            return jsonify(success=False, message='Ağ bulunamadı.'), 404
        id_err = _validate_server_id(server_id)
        if id_err:
            return id_err
        if server_id not in net['server_ids']:
            return jsonify(success=False, message='Sunucu bu ağda değil.'), 404
        net['server_ids'].remove(server_id)
        return jsonify(success=True, message=f'{server_id} ağdan çıkarıldı.', network=net)

    @bp.route('/api/networks/<int:network_id>/statuses', methods=['GET'])
    @auth
    def api_network_statuses(network_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        net = _networks.get(network_id)
        if not net:
            return jsonify(success=False, message='Ağ bulunamadı.'), 404
        result = fw.network_get_statuses(net['server_ids'])
        result['network'] = net['name']
        return jsonify(**result)

    @bp.route('/api/networks/<int:network_id>/sync-check', methods=['GET'])
    @auth
    def api_network_sync_check(network_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        net = _networks.get(network_id)
        if not net:
            return jsonify(success=False, message='Ağ bulunamadı.'), 404
        result = fw.network_sync_check(net['server_ids'])
        result['network'] = net['name']
        return jsonify(**result)

    @bp.route('/api/networks/<int:network_id>/apply-rule', methods=['POST'])
    @auth
    def api_network_apply_rule(network_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        net = _networks.get(network_id)
        if not net:
            return jsonify(success=False, message='Ağ bulunamadı.'), 404
        d = request.get_json(silent=True) or {}
        action = str(d.get('action', '')).strip()
        allowed = ('add_rule', 'delete_rule', 'block_ip', 'unblock_ip',
                   'add_port_forward', 'delete_port_forward')
        if action not in allowed:
            return jsonify(success=False, message=f'Geçersiz aksiyon. İzin verilenler: {", ".join(allowed)}'), 400
        rule_params = d.get('params', {})
        if not isinstance(rule_params, dict):
            return jsonify(success=False, message='params dict olmalı.'), 400
        target_ids = d.get('server_ids', net['server_ids'])
        if not isinstance(target_ids, list):
            target_ids = net['server_ids']
        valid_ids = [s for s in target_ids if s in net['server_ids']]
        if not valid_ids:
            return jsonify(success=False, message='Geçerli hedef sunucu yok.'), 400
        result = fw.network_apply_rule(valid_ids, action, rule_params)
        _audit('network.apply_rule', target_type='network', target_id=str(network_id),
               success=result['success'],
               details={'action': action, 'succeeded': result['succeeded'],
                        'failed': result['failed']})
        return jsonify(**result)

    @bp.route('/api/networks/<int:network_id>/dns', methods=['PUT'])
    @auth
    def api_network_dns(network_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        net = _networks.get(network_id)
        if not net:
            return jsonify(success=False, message='Ağ bulunamadı.'), 404
        d = request.get_json(silent=True) or {}
        dns = d.get('dns_servers', [])
        if not isinstance(dns, list):
            return jsonify(success=False, message='dns_servers liste olmalı.'), 400
        net['dns_servers'] = [str(s).strip() for s in dns[:10] if str(s).strip()]
        _audit('network.dns_update', target_type='network', target_id=str(network_id),
               success=True, details={'dns_servers': net['dns_servers']})
        return jsonify(success=True, network=net)

    # ═══════════════════════════════════════════════════════════════
    # RMM + ITSM (Uzaktan İzleme ve IT Servis Yönetimi)
    # ═══════════════════════════════════════════════════════════════

    _rmm = rmm_store

    def _agent_auth():
        """Agent key ile kimlik doğrulama. -> (device_info, error_response)"""
        if not _rmm:
            return None, (jsonify(success=False, message='RMM modülü aktif değil.'), 503)
        key = request.headers.get('X-Agent-Key', '')
        if not key:
            return None, (jsonify(success=False, message='X-Agent-Key gerekli.'), 401)
        dev = _rmm.authenticate_agent(key)
        if not dev:
            return None, (jsonify(success=False, message='Geçersiz agent key.'), 401)
        return dev, None

    # ── Agent API (Symon / Linux agent çağırır) ──

    @bp.route('/api/rmm/agent/register', methods=['POST'])
    def rmm_agent_register():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        d = request.get_json(silent=True) or {}
        hostname = str(d.get('hostname', '')).strip()
        if not hostname or len(hostname) > 255:
            return jsonify(success=False, message='hostname gerekli (max 255 karakter).'), 400
        os_type = str(d.get('os_type', '')).strip()[:64]
        os_version = str(d.get('os_version', '')).strip()[:128]
        ip_address = str(d.get('ip_address', '')).strip()[:45]
        agent_version = str(d.get('agent_version', '')).strip()[:32]
        tenant_id = str(d.get('tenant_id', '')).strip()[:64]
        tags = d.get('tags', [])
        if not isinstance(tags, list):
            tags = []
        tags = [str(t).strip()[:64] for t in tags[:20]]
        result = _rmm.register_device(
            hostname=hostname, os_type=os_type, os_version=os_version,
            ip_address=ip_address, agent_version=agent_version,
            tenant_id=tenant_id, tags=tags)
        _audit('rmm.device_register', success=True,
               details={'hostname': hostname, 'os_type': os_type,
                        'device_id': result['id']})
        return jsonify(success=True, **result)

    @bp.route('/api/rmm/agent/heartbeat', methods=['POST'])
    def rmm_agent_heartbeat():
        dev, err = _agent_auth()
        if err:
            return err
        d = request.get_json(silent=True) or {}
        cpu = max(0.0, min(float(d.get('cpu', 0)), 100.0))
        ram = max(0.0, min(float(d.get('ram', 0)), 100.0))
        disk = max(0.0, min(float(d.get('disk', 0)), 100.0))
        net_in = max(0, int(d.get('net_in', 0)))
        net_out = max(0, int(d.get('net_out', 0)))
        extra = d.get('extra', {})
        if not isinstance(extra, dict):
            extra = {}
        _rmm.heartbeat(dev['id'], cpu=cpu, ram=ram, disk=disk,
                       net_in=net_in, net_out=net_out, extra=extra)
        return jsonify(success=True, ack=True)

    @bp.route('/api/rmm/agent/tasks', methods=['GET'])
    def rmm_agent_tasks():
        dev, err = _agent_auth()
        if err:
            return err
        tasks = _rmm.get_pending_tasks(dev['id'])
        return jsonify(success=True, tasks=tasks)

    @bp.route('/api/rmm/agent/task-result', methods=['POST'])
    def rmm_agent_task_result():
        dev, err = _agent_auth()
        if err:
            return err
        d = request.get_json(silent=True) or {}
        task_id = str(d.get('task_id', '')).strip()
        if not task_id or not re.match(r'^[a-f0-9]{16}$', task_id):
            return jsonify(success=False, message='Geçersiz task_id.'), 400
        success = bool(d.get('success', True))
        result = str(d.get('result', ''))[:10000]
        _rmm.complete_task(task_id, result=result, success=success)
        return jsonify(success=True)

    # ── Yönetim API (UI çağırır) ──

    @bp.route('/api/rmm/dashboard', methods=['GET'])
    @auth
    def rmm_dashboard():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        _rmm.update_statuses()
        return jsonify(success=True, **_rmm.dashboard())

    @bp.route('/api/rmm/devices', methods=['GET'])
    @auth
    def rmm_devices():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        _rmm.update_statuses()
        status = request.args.get('status', '')
        devices = _rmm.list_devices(status=status)
        return jsonify(success=True, devices=devices)

    @bp.route('/api/rmm/devices/<device_id>', methods=['GET'])
    @auth
    def rmm_device_detail(device_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        if not re.match(r'^[a-f0-9]{16}$', device_id):
            return jsonify(success=False, message='Geçersiz device_id.'), 400
        dev = _rmm.get_device(device_id)
        if not dev:
            return jsonify(success=False, message='Cihaz bulunamadı.'), 404
        hours = max(1, min(request.args.get('hours', 24, type=int), 168))
        metrics = _rmm.get_metrics(device_id, hours=hours)
        tasks = _rmm.list_tasks(device_id=device_id, limit=20)
        return jsonify(success=True, device=dev, metrics=metrics, tasks=tasks)

    @bp.route('/api/rmm/devices/<device_id>', methods=['DELETE'])
    @auth
    def rmm_device_delete(device_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        if not re.match(r'^[a-f0-9]{16}$', device_id):
            return jsonify(success=False, message='Geçersiz device_id.'), 400
        _rmm.remove_device(device_id)
        _audit('rmm.device_remove', success=True, details={'device_id': device_id})
        return jsonify(success=True, message='Cihaz silindi.')

    @bp.route('/api/rmm/devices/<device_id>/task', methods=['POST'])
    @auth
    def rmm_device_task(device_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        if not re.match(r'^[a-f0-9]{16}$', device_id):
            return jsonify(success=False, message='Geçersiz device_id.'), 400
        d = request.get_json(silent=True) or {}
        task_type = str(d.get('task_type', '')).strip()
        if task_type not in _rmm.VALID_TASK_TYPES:
            return jsonify(success=False,
                           message=f'Geçersiz task_type. İzinli: {", ".join(_rmm.VALID_TASK_TYPES)}'), 400
        payload = d.get('payload', {})
        if not isinstance(payload, dict):
            return jsonify(success=False, message='payload dict olmalı.'), 400
        task_id = _rmm.create_task(device_id, task_type, payload)
        _audit('rmm.task_create', success=True,
               details={'device_id': device_id, 'task_type': task_type, 'task_id': task_id})
        return jsonify(success=True, task_id=task_id)

    # ── ITSM Ticket API ──

    @bp.route('/api/rmm/tickets', methods=['GET'])
    @auth
    def rmm_tickets_list():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        status = request.args.get('status', '')
        priority = request.args.get('priority', '')
        limit = max(1, min(request.args.get('limit', 50, type=int), 500))
        tickets = _rmm.list_tickets(status=status, priority=priority, limit=limit)
        stats = _rmm.ticket_stats()
        return jsonify(success=True, tickets=tickets, stats=stats)

    @bp.route('/api/rmm/tickets', methods=['POST'])
    @auth
    def rmm_ticket_create():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        d = request.get_json(silent=True) or {}
        title = str(d.get('title', '')).strip()
        if not title or len(title) > 500:
            return jsonify(success=False, message='title gerekli (max 500 karakter).'), 400
        description = str(d.get('description', '')).strip()[:5000]
        priority = str(d.get('priority', 'medium')).strip()
        if priority not in _rmm.VALID_PRIORITIES:
            priority = 'medium'
        category = str(d.get('category', 'general')).strip()[:64]
        device_id = str(d.get('device_id', '')).strip()[:32]
        assignee = str(d.get('assignee', '')).strip()[:128]
        ticket_id = _rmm.create_ticket(
            title=title, description=description, priority=priority,
            category=category, device_id=device_id, assignee=assignee,
            created_by=request.remote_addr)
        _audit('rmm.ticket_create', success=True,
               details={'ticket_id': ticket_id, 'title': title, 'priority': priority})
        return jsonify(success=True, ticket_id=ticket_id, message='Ticket oluşturuldu.')

    @bp.route('/api/rmm/tickets/<int:ticket_id>', methods=['GET'])
    @auth
    def rmm_ticket_detail(ticket_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        ticket = _rmm.get_ticket(ticket_id)
        if not ticket:
            return jsonify(success=False, message='Ticket bulunamadı.'), 404
        device = None
        if ticket.get('device_id'):
            device = _rmm.get_device(ticket['device_id'])
        return jsonify(success=True, ticket=ticket, device=device)

    @bp.route('/api/rmm/tickets/<int:ticket_id>', methods=['PUT'])
    @auth
    def rmm_ticket_update(ticket_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        d = request.get_json(silent=True) or {}
        status = str(d.get('status', '')).strip()
        assignee = d.get('assignee')
        if assignee is not None:
            assignee = str(assignee).strip()[:128]
        note = str(d.get('note', '')).strip()[:2000]
        added_by = str(d.get('added_by', request.remote_addr)).strip()[:128]
        ok = _rmm.update_ticket(ticket_id, status=status, assignee=assignee,
                                note=note, added_by=added_by)
        if not ok:
            return jsonify(success=False, message='Ticket bulunamadı.'), 404
        _audit('rmm.ticket_update', success=True,
               details={'ticket_id': ticket_id, 'status': status})
        return jsonify(success=True, message='Ticket güncellendi.')

    # ── RMM Alerts API ──

    @bp.route('/api/rmm/alerts', methods=['GET'])
    @auth
    def rmm_alerts_list():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        device_id = request.args.get('device_id', '')
        ack = request.args.get('acknowledged', -1, type=int)
        alerts = _rmm.list_alerts(device_id=device_id, acknowledged=ack)
        stats = _rmm.alert_stats()
        return jsonify(success=True, alerts=alerts, stats=stats)

    @bp.route('/api/rmm/alerts/<int:alert_id>/ack', methods=['PUT'])
    @auth
    def rmm_alert_ack(alert_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        ok = _rmm.acknowledge_alert(alert_id)
        if not ok:
            return jsonify(success=False,
                           message='Alarm bulunamadı veya zaten onaylandı.'), 404
        return jsonify(success=True, message='Alarm onaylandı.')

    @bp.route('/api/rmm/alert-config', methods=['GET'])
    @auth
    def rmm_alert_config_get():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        return jsonify(success=True, config=_rmm.get_alert_config())

    @bp.route('/api/rmm/alert-config', methods=['POST'])
    @auth
    def rmm_alert_config_save():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        d = request.get_json(silent=True) or {}
        _rmm.save_alert_config(d)
        return jsonify(success=True,
                       message='Alarm yapılandırması kaydedildi.')

    @bp.route('/api/rmm/devices/<device_id>', methods=['PUT'])
    @auth
    def rmm_device_update(device_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        if not re.match(r'^[a-f0-9]{16}$', device_id):
            return jsonify(success=False, message='Geçersiz device_id.'), 400
        d = request.get_json(silent=True) or {}
        tenant_id = d.get('tenant_id')
        if tenant_id is not None:
            tenant_id = str(tenant_id).strip()[:64]
        label = d.get('label')
        if label is not None:
            label = str(label).strip()[:128]
        ok = _rmm.update_device(device_id, tenant_id=tenant_id, label=label)
        if not ok:
            return jsonify(success=False, message='Cihaz bulunamadı.'), 404
        _audit('rmm.device_update', success=True,
               details={'device_id': device_id})
        return jsonify(success=True, message='Cihaz güncellendi.')

    # ── SIEM: Threat Intelligence API ──

    @bp.route('/api/rmm/threats', methods=['GET'])
    @auth
    def rmm_threats_list():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        indicator_type = request.args.get('type', '')
        reputation = request.args.get('reputation', '')
        threats = _rmm.list_threats(indicator_type=indicator_type,
                                    reputation=reputation)
        stats = _rmm.threat_stats()
        return jsonify(success=True, threats=threats, stats=stats)

    @bp.route('/api/rmm/threats', methods=['POST'])
    @auth
    def rmm_threat_add():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        d = request.get_json(silent=True) or {}
        indicator = str(d.get('indicator', '')).strip()
        if not indicator or len(indicator) > 255:
            return jsonify(success=False, message='indicator gerekli (max 255).'), 400
        indicator_type = str(d.get('indicator_type', 'ip')).strip()
        if indicator_type not in ('ip', 'domain', 'hash', 'url', 'email'):
            indicator_type = 'ip'
        source = str(d.get('source', 'manual')).strip()[:64]
        reputation = str(d.get('reputation', 'malicious')).strip()
        if reputation not in ('malicious', 'suspicious', 'clean', 'unknown'):
            reputation = 'unknown'
        tags = d.get('tags', [])
        if not isinstance(tags, list):
            tags = []
        tags = [str(t).strip()[:32] for t in tags[:10]]
        tid = _rmm.add_threat_indicator(
            indicator=indicator, indicator_type=indicator_type,
            source=source, reputation=reputation, tags=tags)
        _audit('siem.threat_add', success=True,
               details={'indicator': indicator, 'type': indicator_type})
        return jsonify(success=True, id=tid,
                       message='Tehdit göstergesi eklendi.')

    @bp.route('/api/rmm/threats/check', methods=['POST'])
    @auth
    def rmm_threat_check():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        d = request.get_json(silent=True) or {}
        indicator = str(d.get('indicator', '')).strip()
        if not indicator:
            return jsonify(success=False, message='indicator gerekli.'), 400
        indicator_type = str(d.get('indicator_type', 'ip')).strip()
        result = _rmm.check_threat(indicator, indicator_type)
        return jsonify(success=True, found=result is not None,
                       threat=result)

    @bp.route('/api/rmm/threats/<int:threat_id>', methods=['DELETE'])
    @auth
    def rmm_threat_delete(threat_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        ok = _rmm.remove_threat(threat_id)
        if not ok:
            return jsonify(success=False, message='Gösterge bulunamadı.'), 404
        return jsonify(success=True, message='Gösterge silindi.')

    # ── SIEM: Correlation API ──

    @bp.route('/api/rmm/correlation/rules', methods=['GET'])
    @auth
    def rmm_correlation_rules():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        rules = _rmm.list_correlation_rules()
        return jsonify(success=True, rules=rules)

    @bp.route('/api/rmm/correlation/rules', methods=['POST'])
    @auth
    def rmm_correlation_rule_create():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        d = request.get_json(silent=True) or {}
        name = str(d.get('name', '')).strip()
        if not name or len(name) > 200:
            return jsonify(success=False, message='name gerekli (max 200).'), 400
        description = str(d.get('description', '')).strip()[:1000]
        rule_type = str(d.get('rule_type', 'threshold')).strip()
        conditions = d.get('conditions', {})
        if not isinstance(conditions, dict):
            return jsonify(success=False, message='conditions dict olmalı.'), 400
        severity = str(d.get('severity', 'warning')).strip()
        rid = _rmm.create_correlation_rule(
            name=name, description=description, rule_type=rule_type,
            conditions=conditions, severity=severity)
        _audit('siem.correlation_rule_create', success=True,
               details={'rule_id': rid, 'name': name})
        return jsonify(success=True, rule_id=rid,
                       message='Korelasyon kuralı oluşturuldu.')

    @bp.route('/api/rmm/correlation/rules/<int:rule_id>', methods=['PUT'])
    @auth
    def rmm_correlation_rule_toggle(rule_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        d = request.get_json(silent=True) or {}
        enabled = bool(d.get('enabled', True))
        ok = _rmm.toggle_correlation_rule(rule_id, enabled)
        if not ok:
            return jsonify(success=False, message='Kural bulunamadı.'), 404
        return jsonify(success=True, message='Kural güncellendi.')

    @bp.route('/api/rmm/correlation/rules/<int:rule_id>', methods=['DELETE'])
    @auth
    def rmm_correlation_rule_delete(rule_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        _rmm.delete_correlation_rule(rule_id)
        return jsonify(success=True, message='Kural silindi.')

    @bp.route('/api/rmm/correlation/events', methods=['GET'])
    @auth
    def rmm_correlation_events():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        rule_id = request.args.get('rule_id', 0, type=int)
        device_id = request.args.get('device_id', '')
        events = _rmm.list_correlation_events(
            rule_id=rule_id, device_id=device_id)
        return jsonify(success=True, events=events)

    # ── SIEM: MITRE ATT&CK API ──

    @bp.route('/api/rmm/mitre/summary', methods=['GET'])
    @auth
    def rmm_mitre_summary():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        summary = _rmm.get_mitre_summary()
        return jsonify(success=True, **summary)

    @bp.route('/api/rmm/mitre/heatmap', methods=['GET'])
    @auth
    def rmm_mitre_heatmap():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        device_id = request.args.get('device_id', '')
        heatmap = _rmm.get_mitre_heatmap(device_id=device_id)
        return jsonify(success=True, **heatmap)

    # ── SIEM: Risk Score API ──

    @bp.route('/api/rmm/risk', methods=['GET'])
    @auth
    def rmm_risk_dashboard():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        data = _rmm.risk_dashboard()
        return jsonify(success=True, **data)

    @bp.route('/api/rmm/risk/<device_id>', methods=['GET'])
    @auth
    def rmm_risk_device(device_id):
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        if not re.match(r'^[a-f0-9]{16}$', device_id):
            return jsonify(success=False, message='Geçersiz device_id.'), 400
        data = _rmm.get_risk_score(device_id)
        return jsonify(success=True, **data)

    @bp.route('/api/rmm/risk/decay', methods=['POST'])
    @auth
    def rmm_risk_decay():
        rate_err = _rate_limited()
        if rate_err:
            return rate_err
        csrf_err = _csrf_check()
        if csrf_err:
            return csrf_err
        if not _rmm:
            return jsonify(success=False, message='RMM modülü aktif değil.'), 503
        d = request.get_json(silent=True) or {}
        pct = max(1.0, min(float(d.get('percent', 5)), 50.0))
        _rmm.decay_risk_scores(decay_percent=pct)
        return jsonify(success=True, message='Risk puanları azaltıldı.')

    return bp
