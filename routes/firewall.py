"""
EmareFirewall Dervişi — Güvenlik Duvarı API Route'ları
Tam kapsamlı firewall yönetimi: kurallar, IP engelleme, port forwarding,
zone yönetimi, fail2ban, güvenlik taraması, bağlantı izleme.
"""

from flask import Blueprint, jsonify, request
from flask_login import login_required

from audit import log_action
from core.helpers import get_server_obj_with_access, ssh_mgr
from firewall_manager import (
    add_port_forward,
    add_rich_rule,
    add_rule as firewall_add_rule,
    add_service,
    block_ip,
    delete_rule as firewall_delete_rule,
    disable_firewall,
    enable_firewall,
    fail2ban_ban,
    fail2ban_unban,
    geo_block_country,
    get_blocked_ips,
    get_connection_stats,
    get_connections,
    get_fail2ban_status,
    get_status as firewall_get_status,
    get_zone_detail,
    get_zones,
    remove_port_forward,
    remove_rich_rule,
    remove_service,
    security_scan,
    set_default_zone,
    unblock_ip,
)
from rbac import permission_required

firewall_bp = Blueprint('firewall', __name__)


def _check_connection(server_id):
    """Sunucu bağlantı kontrolü + tenant erişim kontrolü."""
    srv = get_server_obj_with_access(server_id)
    if not srv:
        return jsonify({'success': False, 'message': 'Sunucu bulunamadı veya erişim yetkiniz yok'}), 404
    if not ssh_mgr.is_connected(server_id):
        return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400
    return None


# ─────────────────── DURUM ───────────────────

@firewall_bp.route('/api/servers/<server_id>/firewall/status', methods=['GET'])
@login_required
@permission_required('firewall.view')
def api_firewall_status(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    try:
        status = firewall_get_status(ssh_mgr, server_id)
        return jsonify({'success': True, 'firewall': status})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@firewall_bp.route('/api/servers/<server_id>/firewall/enable', methods=['POST'])
@login_required
@permission_required('firewall.manage')
def api_firewall_enable(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    ok, msg = enable_firewall(ssh_mgr, server_id)
    log_action('firewall.enable', target_type='server', target_id=server_id, success=ok)
    return jsonify({'success': ok, 'message': msg})


@firewall_bp.route('/api/servers/<server_id>/firewall/disable', methods=['POST'])
@login_required
@permission_required('firewall.manage')
def api_firewall_disable(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    ok, msg = disable_firewall(ssh_mgr, server_id)
    log_action('firewall.disable', target_type='server', target_id=server_id, success=ok)
    return jsonify({'success': ok, 'message': msg})


# ─────────────────── PORT/SERVİS KURALLARI ───────────────────

@firewall_bp.route('/api/servers/<server_id>/firewall/rules', methods=['POST'])
@login_required
@permission_required('firewall.manage')
def api_firewall_add_rule(server_id):
    err = _check_connection(server_id)
    if err:
        return err
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
               details={'port': port, 'action': data.get('action', 'allow')}, success=ok)
    return jsonify({'success': ok, 'message': msg})


@firewall_bp.route('/api/servers/<server_id>/firewall/rules/<int:rule_index>', methods=['DELETE'])
@login_required
@permission_required('firewall.manage')
def api_firewall_delete_rule(server_id, rule_index):
    err = _check_connection(server_id)
    if err:
        return err
    ok, msg = firewall_delete_rule(ssh_mgr, server_id, rule_index)
    log_action('firewall.delete_rule', target_type='server', target_id=server_id,
               details={'rule_index': rule_index}, success=ok)
    return jsonify({'success': ok, 'message': msg})


@firewall_bp.route('/api/servers/<server_id>/firewall/services', methods=['POST'])
@login_required
@permission_required('firewall.manage')
def api_firewall_add_service(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    service = (data.get('service') or '').strip()
    if not service:
        return jsonify({'success': False, 'message': 'Servis adı girin'}), 400
    ok, msg = add_service(ssh_mgr, server_id, service)
    log_action('firewall.add_service', target_type='server', target_id=server_id,
               details={'service': service}, success=ok)
    return jsonify({'success': ok, 'message': msg})


@firewall_bp.route('/api/servers/<server_id>/firewall/services/<service_name>', methods=['DELETE'])
@login_required
@permission_required('firewall.manage')
def api_firewall_remove_service(server_id, service_name):
    err = _check_connection(server_id)
    if err:
        return err
    ok, msg = remove_service(ssh_mgr, server_id, service_name)
    log_action('firewall.remove_service', target_type='server', target_id=server_id,
               details={'service': service_name}, success=ok)
    return jsonify({'success': ok, 'message': msg})


# ─────────────────── IP ENGELLEME ───────────────────

@firewall_bp.route('/api/servers/<server_id>/firewall/block-ip', methods=['POST'])
@login_required
@permission_required('firewall.manage')
def api_firewall_block_ip(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    ip = (data.get('ip') or '').strip()
    reason = (data.get('reason') or '').strip()
    if not ip:
        return jsonify({'success': False, 'message': 'IP adresi girin'}), 400
    ok, msg = block_ip(ssh_mgr, server_id, ip, reason)
    log_action('firewall.block_ip', target_type='server', target_id=server_id,
               details={'ip': ip, 'reason': reason}, success=ok)
    return jsonify({'success': ok, 'message': msg})


@firewall_bp.route('/api/servers/<server_id>/firewall/unblock-ip', methods=['POST'])
@login_required
@permission_required('firewall.manage')
def api_firewall_unblock_ip(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    ip = (data.get('ip') or '').strip()
    if not ip:
        return jsonify({'success': False, 'message': 'IP adresi girin'}), 400
    ok, msg = unblock_ip(ssh_mgr, server_id, ip)
    log_action('firewall.unblock_ip', target_type='server', target_id=server_id,
               details={'ip': ip}, success=ok)
    return jsonify({'success': ok, 'message': msg})


@firewall_bp.route('/api/servers/<server_id>/firewall/blocked-ips', methods=['GET'])
@login_required
@permission_required('firewall.view')
def api_firewall_blocked_ips(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    blocked = get_blocked_ips(ssh_mgr, server_id)
    return jsonify({'success': True, 'blocked': blocked})


# ─────────────────── PORT YÖNLENDİRME ───────────────────

@firewall_bp.route('/api/servers/<server_id>/firewall/port-forward', methods=['POST'])
@login_required
@permission_required('firewall.manage')
def api_firewall_add_port_forward(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    port = (data.get('port') or '').strip()
    to_port = (data.get('to_port') or '').strip()
    to_addr = (data.get('to_addr') or '').strip()
    protocol = (data.get('protocol') or 'tcp').strip()
    if not port or not to_port:
        return jsonify({'success': False, 'message': 'Kaynak port ve hedef port girin'}), 400
    ok, msg = add_port_forward(ssh_mgr, server_id, port, to_port, to_addr, protocol)
    log_action('firewall.port_forward', target_type='server', target_id=server_id,
               details={'port': port, 'to_port': to_port, 'to_addr': to_addr}, success=ok)
    return jsonify({'success': ok, 'message': msg})


@firewall_bp.route('/api/servers/<server_id>/firewall/port-forward', methods=['DELETE'])
@login_required
@permission_required('firewall.manage')
def api_firewall_remove_port_forward(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    port = (data.get('port') or '').strip()
    to_port = (data.get('to_port') or '').strip()
    to_addr = (data.get('to_addr') or '').strip()
    protocol = (data.get('protocol') or 'tcp').strip()
    ok, msg = remove_port_forward(ssh_mgr, server_id, port, to_port, to_addr, protocol)
    log_action('firewall.remove_port_forward', target_type='server', target_id=server_id,
               details={'port': port, 'to_port': to_port}, success=ok)
    return jsonify({'success': ok, 'message': msg})


# ─────────────────── ZONE YÖNETİMİ ───────────────────

@firewall_bp.route('/api/servers/<server_id>/firewall/zones', methods=['GET'])
@login_required
@permission_required('firewall.view')
def api_firewall_zones(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    zones = get_zones(ssh_mgr, server_id)
    return jsonify({'success': True, **zones})


@firewall_bp.route('/api/servers/<server_id>/firewall/zones/<zone_name>', methods=['GET'])
@login_required
@permission_required('firewall.view')
def api_firewall_zone_detail(server_id, zone_name):
    err = _check_connection(server_id)
    if err:
        return err
    detail = get_zone_detail(ssh_mgr, server_id, zone_name)
    return jsonify({'success': True, 'detail': detail})


@firewall_bp.route('/api/servers/<server_id>/firewall/zones/default', methods=['POST'])
@login_required
@permission_required('firewall.manage')
def api_firewall_set_default_zone(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    zone = (data.get('zone') or '').strip()
    if not zone:
        return jsonify({'success': False, 'message': 'Zone adı girin'}), 400
    ok, msg = set_default_zone(ssh_mgr, server_id, zone)
    log_action('firewall.set_zone', target_type='server', target_id=server_id,
               details={'zone': zone}, success=ok)
    return jsonify({'success': ok, 'message': msg})


# ─────────────────── RICH RULE ───────────────────

@firewall_bp.route('/api/servers/<server_id>/firewall/rich-rules', methods=['POST'])
@login_required
@permission_required('firewall.manage')
def api_firewall_add_rich_rule(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    rule = (data.get('rule') or '').strip()
    if not rule:
        return jsonify({'success': False, 'message': 'Kural girin'}), 400
    ok, msg = add_rich_rule(ssh_mgr, server_id, rule)
    log_action('firewall.add_rich_rule', target_type='server', target_id=server_id,
               details={'rule': rule}, success=ok)
    return jsonify({'success': ok, 'message': msg})


@firewall_bp.route('/api/servers/<server_id>/firewall/rich-rules', methods=['DELETE'])
@login_required
@permission_required('firewall.manage')
def api_firewall_remove_rich_rule(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    rule = (data.get('rule') or '').strip()
    if not rule:
        return jsonify({'success': False, 'message': 'Kural girin'}), 400
    ok, msg = remove_rich_rule(ssh_mgr, server_id, rule)
    log_action('firewall.remove_rich_rule', target_type='server', target_id=server_id,
               details={'rule': rule}, success=ok)
    return jsonify({'success': ok, 'message': msg})


# ─────────────────── FAIL2BAN ───────────────────

@firewall_bp.route('/api/servers/<server_id>/firewall/fail2ban', methods=['GET'])
@login_required
@permission_required('firewall.view')
def api_firewall_fail2ban_status(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    status = get_fail2ban_status(ssh_mgr, server_id)
    return jsonify({'success': True, 'fail2ban': status})


@firewall_bp.route('/api/servers/<server_id>/firewall/fail2ban/ban', methods=['POST'])
@login_required
@permission_required('firewall.manage')
def api_firewall_fail2ban_ban(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    jail = (data.get('jail') or '').strip()
    ip = (data.get('ip') or '').strip()
    if not jail or not ip:
        return jsonify({'success': False, 'message': 'Jail ve IP girin'}), 400
    ok, msg = fail2ban_ban(ssh_mgr, server_id, jail, ip)
    log_action('firewall.f2b_ban', target_type='server', target_id=server_id,
               details={'jail': jail, 'ip': ip}, success=ok)
    return jsonify({'success': ok, 'message': msg})


@firewall_bp.route('/api/servers/<server_id>/firewall/fail2ban/unban', methods=['POST'])
@login_required
@permission_required('firewall.manage')
def api_firewall_fail2ban_unban(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    jail = (data.get('jail') or '').strip()
    ip = (data.get('ip') or '').strip()
    if not jail or not ip:
        return jsonify({'success': False, 'message': 'Jail ve IP girin'}), 400
    ok, msg = fail2ban_unban(ssh_mgr, server_id, jail, ip)
    log_action('firewall.f2b_unban', target_type='server', target_id=server_id,
               details={'jail': jail, 'ip': ip}, success=ok)
    return jsonify({'success': ok, 'message': msg})


# ─────────────────── BAĞLANTI İZLEME ───────────────────

@firewall_bp.route('/api/servers/<server_id>/firewall/connections', methods=['GET'])
@login_required
@permission_required('firewall.view')
def api_firewall_connections(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    limit = request.args.get('limit', 50, type=int)
    connections = get_connections(ssh_mgr, server_id, limit)
    return jsonify({'success': True, 'connections': connections})


@firewall_bp.route('/api/servers/<server_id>/firewall/connection-stats', methods=['GET'])
@login_required
@permission_required('firewall.view')
def api_firewall_connection_stats(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    stats = get_connection_stats(ssh_mgr, server_id)
    return jsonify({'success': True, 'stats': stats})


# ─────────────────── GÜVENLİK TARAMASI ───────────────────

@firewall_bp.route('/api/servers/<server_id>/firewall/security-scan', methods=['GET'])
@login_required
@permission_required('firewall.view')
def api_firewall_security_scan(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    try:
        scan = security_scan(ssh_mgr, server_id)
        return jsonify({'success': True, 'scan': scan})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ─────────────────── GEO-BLOCK ───────────────────

@firewall_bp.route('/api/servers/<server_id>/firewall/geo-block', methods=['POST'])
@login_required
@permission_required('firewall.manage')
def api_firewall_geo_block(server_id):
    err = _check_connection(server_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    country = (data.get('country') or '').strip()
    if not country:
        return jsonify({'success': False, 'message': 'Ülke kodu girin (örn: CN)'}), 400
    ok, msg = geo_block_country(ssh_mgr, server_id, country)
    log_action('firewall.geo_block', target_type='server', target_id=server_id,
               details={'country': country}, success=ok)
    return jsonify({'success': ok, 'message': msg})
