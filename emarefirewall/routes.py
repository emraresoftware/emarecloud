"""
EmareFirewall — Flask Blueprint (Opsiyonel Flask Entegrasyonu)
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

from functools import wraps
from flask import Blueprint, jsonify, request

from emarefirewall.manager import FirewallManager


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

    Returns:
        Flask Blueprint
    """
    fw = FirewallManager(ssh_executor=ssh_executor)
    bp = Blueprint('emarefirewall', __name__, url_prefix=url_prefix)

    auth = auth_decorator or _noop_decorator
    perm_view = (lambda fn: permission_decorator('firewall.view')(fn)) if permission_decorator else _noop_decorator
    perm_manage = (lambda fn: permission_decorator('firewall.manage')(fn)) if permission_decorator else _noop_decorator

    def _audit(action, **kw):
        if audit_fn:
            audit_fn(action, **kw)

    def _check(server_id):
        if connection_checker and not connection_checker(server_id):
            return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400
        return None

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
            return jsonify({'success': False, 'message': str(e)}), 500

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
        ok, msg = fw.add_rule(server_id, port=port,
            protocol=d.get('protocol', 'tcp'), action=d.get('action', 'allow'),
            from_ip=d.get('from_ip', ''))
        _audit('firewall.add_rule', target_type='server', target_id=server_id,
               details={'port': port}, success=ok)
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
        limit = request.args.get('limit', 50, type=int)
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
            return jsonify({'success': False, 'message': str(e)}), 500

    # ── Geo-Block ──
    @bp.route('/api/servers/<server_id>/firewall/geo-block', methods=['POST'])
    @auth
    @perm_manage
    def api_geo(server_id):
        err = _check(server_id)
        if err: return err
        d = request.get_json(silent=True) or {}
        ok, msg = fw.geo_block_country(server_id, d.get('country', ''))
        _audit('firewall.geo_block', target_type='server', target_id=server_id, success=ok)
        return jsonify({'success': ok, 'message': msg})

    return bp
