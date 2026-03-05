"""
EmareCloud — Cloudflare API Route'ları
/api/cloudflare/* endpoint'leri.

Cloudflare v4 API ile DNS, SSL, Cache, Firewall, Analytics ve Page Rules yönetimi.
Docs: https://developers.cloudflare.com/api/
"""

import os
import requests
from flask import Blueprint, jsonify, request
from flask_login import login_required

from audit import log_action

cloudflare_bp = Blueprint('cloudflare', __name__)

# ── Cloudflare Config ─────────────────────────────────────────
CF_BASE = 'https://api.cloudflare.com/client/v4'


def _cf_headers(token: str = None) -> dict:
    """Cloudflare API token ile Authorization header döndürür."""
    t = token or os.environ.get('CLOUDFLARE_API_TOKEN', '')
    return {
        'Authorization': f'Bearer {t}',
        'Content-Type': 'application/json',
    }


def _cf_get(path: str, token: str = None, params: dict = None) -> dict:
    """Cloudflare GET isteği."""
    try:
        r = requests.get(f'{CF_BASE}{path}', headers=_cf_headers(token),
                         params=params, timeout=15)
        return r.json()
    except Exception as e:
        return {'success': False, 'errors': [{'message': str(e)}]}


def _cf_post(path: str, data: dict, token: str = None) -> dict:
    """Cloudflare POST isteği."""
    try:
        r = requests.post(f'{CF_BASE}{path}', headers=_cf_headers(token),
                          json=data, timeout=15)
        return r.json()
    except Exception as e:
        return {'success': False, 'errors': [{'message': str(e)}]}


def _cf_put(path: str, data: dict, token: str = None) -> dict:
    """Cloudflare PUT isteği."""
    try:
        r = requests.put(f'{CF_BASE}{path}', headers=_cf_headers(token),
                         json=data, timeout=15)
        return r.json()
    except Exception as e:
        return {'success': False, 'errors': [{'message': str(e)}]}


def _cf_patch(path: str, data: dict, token: str = None) -> dict:
    """Cloudflare PATCH isteği."""
    try:
        r = requests.patch(f'{CF_BASE}{path}', headers=_cf_headers(token),
                           json=data, timeout=15)
        return r.json()
    except Exception as e:
        return {'success': False, 'errors': [{'message': str(e)}]}


def _cf_delete(path: str, token: str = None, data: dict = None) -> dict:
    """Cloudflare DELETE isteği."""
    try:
        r = requests.delete(f'{CF_BASE}{path}', headers=_cf_headers(token),
                            json=data, timeout=15)
        return r.json()
    except Exception as e:
        return {'success': False, 'errors': [{'message': str(e)}]}


def _get_token_and_zone():
    """Request body veya env'den token ve zone_id al."""
    body = request.get_json(silent=True) or {}
    token = body.get('token') or os.environ.get('CLOUDFLARE_API_TOKEN', '')
    zone_id = body.get('zone_id') or os.environ.get('CLOUDFLARE_ZONE_ID', '')
    return token, zone_id


# ══════════════════════════════════════════════════════════════
# CONNECTION & ZONES
# ══════════════════════════════════════════════════════════════

@cloudflare_bp.route('/api/cloudflare/verify', methods=['POST'])
@login_required
def cf_verify_token():
    """API Token'ı doğrula."""
    body = request.get_json(silent=True) or {}
    token = body.get('token') or os.environ.get('CLOUDFLARE_API_TOKEN', '')
    if not token:
        return jsonify({'success': False, 'message': 'API Token gerekli'}), 400

    resp = _cf_get('/user/tokens/verify', token=token)
    if resp.get('success'):
        log_action('cloudflare_verify', details='API Token doğrulandı')
        return jsonify({'success': True, 'result': resp.get('result', {})})
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 401


@cloudflare_bp.route('/api/cloudflare/zones', methods=['POST'])
@login_required
def cf_list_zones():
    """Hesaptaki tüm zone'ları listele."""
    body = request.get_json(silent=True) or {}
    token = body.get('token') or os.environ.get('CLOUDFLARE_API_TOKEN', '')
    resp = _cf_get('/zones', token=token, params={'per_page': 50})
    if resp.get('success'):
        zones = [{'id': z['id'], 'name': z['name'], 'status': z['status'],
                   'plan': z.get('plan', {}).get('name', ''),
                   'ns': z.get('name_servers', [])}
                  for z in resp.get('result', [])]
        return jsonify({'success': True, 'zones': zones})
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 400


# ══════════════════════════════════════════════════════════════
# DNS RECORDS
# ══════════════════════════════════════════════════════════════

@cloudflare_bp.route('/api/cloudflare/dns', methods=['POST'])
@login_required
def cf_list_dns():
    """Zone'daki tüm DNS kayıtlarını listele."""
    token, zone_id = _get_token_and_zone()
    if not zone_id:
        return jsonify({'success': False, 'message': 'zone_id gerekli'}), 400

    body = request.get_json(silent=True) or {}
    params = {'per_page': 100}
    if body.get('type'):
        params['type'] = body['type']
    if body.get('name'):
        params['name'] = body['name']

    resp = _cf_get(f'/zones/{zone_id}/dns_records', token=token, params=params)
    if resp.get('success'):
        records = []
        for r in resp.get('result', []):
            records.append({
                'id': r['id'],
                'type': r['type'],
                'name': r['name'],
                'content': r['content'],
                'ttl': r['ttl'],
                'proxied': r.get('proxied', False),
                'priority': r.get('priority'),
                'created_on': r.get('created_on'),
                'modified_on': r.get('modified_on'),
            })
        return jsonify({'success': True, 'records': records,
                        'total': resp.get('result_info', {}).get('total_count', len(records))})
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 400


@cloudflare_bp.route('/api/cloudflare/dns/create', methods=['POST'])
@login_required
def cf_create_dns():
    """Yeni DNS kaydı oluştur."""
    token, zone_id = _get_token_and_zone()
    if not zone_id:
        return jsonify({'success': False, 'message': 'zone_id gerekli'}), 400

    body = request.get_json(silent=True) or {}
    record_data = {
        'type': body.get('record_type', 'A'),
        'name': body.get('name', '@'),
        'content': body.get('content', ''),
        'ttl': body.get('ttl', 1),  # 1 = auto
        'proxied': body.get('proxied', False),
    }
    if body.get('priority') is not None:
        record_data['priority'] = int(body['priority'])

    if not record_data['content']:
        return jsonify({'success': False, 'message': 'content (IP/değer) gerekli'}), 400

    resp = _cf_post(f'/zones/{zone_id}/dns_records', data=record_data, token=token)
    if resp.get('success'):
        log_action('cloudflare_dns_create',
                   details=f"{record_data['type']} {record_data['name']} → {record_data['content']}")
        return jsonify({'success': True, 'record': resp.get('result', {})})
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 400


@cloudflare_bp.route('/api/cloudflare/dns/update', methods=['PUT'])
@login_required
def cf_update_dns():
    """DNS kaydını güncelle."""
    token, zone_id = _get_token_and_zone()
    body = request.get_json(silent=True) or {}
    record_id = body.get('record_id')
    if not zone_id or not record_id:
        return jsonify({'success': False, 'message': 'zone_id ve record_id gerekli'}), 400

    update_data = {}
    for field in ('type', 'name', 'content', 'ttl', 'proxied', 'priority'):
        if field in body:
            update_data[field] = body[field]
    # type zorunlu Cloudflare'da
    if 'type' not in update_data:
        update_data['type'] = body.get('record_type', 'A')

    resp = _cf_put(f'/zones/{zone_id}/dns_records/{record_id}', data=update_data, token=token)
    if resp.get('success'):
        log_action('cloudflare_dns_update', details=f"Record {record_id} güncellendi")
        return jsonify({'success': True, 'record': resp.get('result', {})})
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 400


@cloudflare_bp.route('/api/cloudflare/dns/delete', methods=['DELETE'])
@login_required
def cf_delete_dns():
    """DNS kaydını sil."""
    token, zone_id = _get_token_and_zone()
    body = request.get_json(silent=True) or {}
    record_id = body.get('record_id')
    if not zone_id or not record_id:
        return jsonify({'success': False, 'message': 'zone_id ve record_id gerekli'}), 400

    resp = _cf_delete(f'/zones/{zone_id}/dns_records/{record_id}', token=token)
    if resp.get('success'):
        log_action('cloudflare_dns_delete', details=f"Record {record_id} silindi")
        return jsonify({'success': True})
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 400


# ══════════════════════════════════════════════════════════════
# SSL / TLS
# ══════════════════════════════════════════════════════════════

@cloudflare_bp.route('/api/cloudflare/ssl', methods=['POST'])
@login_required
def cf_get_ssl():
    """SSL/TLS modunu ve sertifika bilgilerini al."""
    token, zone_id = _get_token_and_zone()
    if not zone_id:
        return jsonify({'success': False, 'message': 'zone_id gerekli'}), 400

    ssl_resp = _cf_get(f'/zones/{zone_id}/settings/ssl', token=token)
    # Universal SSL durumu
    universal = _cf_get(f'/zones/{zone_id}/ssl/universal/settings', token=token)
    # Edge sertifikaları
    certs = _cf_get(f'/zones/{zone_id}/ssl/certificate_packs', token=token, params={'per_page': 50})

    result = {
        'mode': ssl_resp.get('result', {}).get('value', 'off') if ssl_resp.get('success') else 'unknown',
        'universal_enabled': universal.get('result', {}).get('enabled', False) if universal.get('success') else False,
        'certificate_packs': [],
    }
    if certs.get('success'):
        for c in certs.get('result', []):
            result['certificate_packs'].append({
                'id': c.get('id'),
                'type': c.get('type'),
                'status': c.get('status'),
                'hosts': c.get('hosts', []),
                'validity_days': c.get('validity_days'),
            })

    return jsonify({'success': True, 'ssl': result})


@cloudflare_bp.route('/api/cloudflare/ssl/mode', methods=['PATCH'])
@login_required
def cf_set_ssl_mode():
    """SSL/TLS modunu değiştir (off, flexible, full, strict)."""
    token, zone_id = _get_token_and_zone()
    body = request.get_json(silent=True) or {}
    mode = body.get('mode', 'full')
    if mode not in ('off', 'flexible', 'full', 'strict'):
        return jsonify({'success': False, 'message': 'Geçersiz SSL modu'}), 400

    resp = _cf_patch(f'/zones/{zone_id}/settings/ssl', data={'value': mode}, token=token)
    if resp.get('success'):
        log_action('cloudflare_ssl_mode', details=f"SSL modu → {mode}")
        return jsonify({'success': True, 'mode': mode})
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 400


# ══════════════════════════════════════════════════════════════
# CACHE
# ══════════════════════════════════════════════════════════════

@cloudflare_bp.route('/api/cloudflare/cache/purge', methods=['POST'])
@login_required
def cf_purge_cache():
    """Cache temizle (tümünü veya URL bazlı)."""
    token, zone_id = _get_token_and_zone()
    if not zone_id:
        return jsonify({'success': False, 'message': 'zone_id gerekli'}), 400

    body = request.get_json(silent=True) or {}
    urls = body.get('files')  # None ise tümünü temizle

    if urls and isinstance(urls, list):
        purge_data = {'files': urls}
    else:
        purge_data = {'purge_everything': True}

    resp = _cf_post(f'/zones/{zone_id}/purge_cache', data=purge_data, token=token)
    if resp.get('success'):
        detail = f"{len(urls)} URL" if urls else "Tüm cache"
        log_action('cloudflare_cache_purge', details=detail)
        return jsonify({'success': True, 'message': 'Cache temizlendi'})
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 400


@cloudflare_bp.route('/api/cloudflare/cache/settings', methods=['POST'])
@login_required
def cf_get_cache_settings():
    """Cache ayarlarını al (minify, brotli, polish, rocket_loader, always_online, browser_cache_ttl)."""
    token, zone_id = _get_token_and_zone()
    if not zone_id:
        return jsonify({'success': False, 'message': 'zone_id gerekli'}), 400

    settings_keys = ['minify', 'brotli', 'polish', 'rocket_loader',
                     'always_online', 'browser_cache_ttl', 'development_mode',
                     'early_hints']
    result = {}
    for key in settings_keys:
        resp = _cf_get(f'/zones/{zone_id}/settings/{key}', token=token)
        if resp.get('success'):
            result[key] = resp.get('result', {}).get('value')

    return jsonify({'success': True, 'settings': result})


@cloudflare_bp.route('/api/cloudflare/cache/settings/update', methods=['PATCH'])
@login_required
def cf_update_cache_setting():
    """Tek bir cache ayarını güncelle."""
    token, zone_id = _get_token_and_zone()
    body = request.get_json(silent=True) or {}
    setting = body.get('setting')
    value = body.get('value')

    if not zone_id or not setting:
        return jsonify({'success': False, 'message': 'zone_id ve setting gerekli'}), 400

    resp = _cf_patch(f'/zones/{zone_id}/settings/{setting}', data={'value': value}, token=token)
    if resp.get('success'):
        log_action('cloudflare_cache_update', details=f"{setting} → {value}")
        return jsonify({'success': True, 'setting': setting, 'value': value})
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 400


@cloudflare_bp.route('/api/cloudflare/dev-mode', methods=['PATCH'])
@login_required
def cf_dev_mode():
    """Development Mode aç/kapa."""
    token, zone_id = _get_token_and_zone()
    body = request.get_json(silent=True) or {}
    enabled = body.get('enabled', True)

    resp = _cf_patch(f'/zones/{zone_id}/settings/development_mode',
                     data={'value': 'on' if enabled else 'off'}, token=token)
    if resp.get('success'):
        log_action('cloudflare_dev_mode', details=f"Dev mode → {'on' if enabled else 'off'}")
        return jsonify({'success': True, 'enabled': enabled})
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 400


# ══════════════════════════════════════════════════════════════
# FIREWALL / WAF RULES
# ══════════════════════════════════════════════════════════════

@cloudflare_bp.route('/api/cloudflare/firewall/rules', methods=['POST'])
@login_required
def cf_list_firewall_rules():
    """Firewall kurallarını listele."""
    token, zone_id = _get_token_and_zone()
    if not zone_id:
        return jsonify({'success': False, 'message': 'zone_id gerekli'}), 400

    resp = _cf_get(f'/zones/{zone_id}/firewall/rules', token=token, params={'per_page': 50})
    if resp.get('success'):
        rules = []
        for r in resp.get('result', []):
            rules.append({
                'id': r['id'],
                'description': r.get('description', ''),
                'action': r.get('action', ''),
                'filter': r.get('filter', {}),
                'paused': r.get('paused', False),
                'priority': r.get('priority'),
            })
        return jsonify({'success': True, 'rules': rules})
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 400


@cloudflare_bp.route('/api/cloudflare/firewall/rules/create', methods=['POST'])
@login_required
def cf_create_firewall_rule():
    """Yeni firewall kuralı oluştur."""
    token, zone_id = _get_token_and_zone()
    body = request.get_json(silent=True) or {}
    if not zone_id:
        return jsonify({'success': False, 'message': 'zone_id gerekli'}), 400

    expression = body.get('expression', '')
    action = body.get('action', 'block')
    description = body.get('description', '')

    if not expression:
        return jsonify({'success': False, 'message': 'expression gerekli'}), 400

    # Önce filter oluştur
    filter_resp = _cf_post(f'/zones/{zone_id}/filters', data=[{
        'expression': expression,
        'description': description,
    }], token=token)

    if not filter_resp.get('success'):
        return jsonify({'success': False, 'errors': filter_resp.get('errors', [])}), 400

    filter_id = filter_resp['result'][0]['id']

    rule_resp = _cf_post(f'/zones/{zone_id}/firewall/rules', data=[{
        'filter': {'id': filter_id},
        'action': action,
        'description': description,
    }], token=token)

    if rule_resp.get('success'):
        log_action('cloudflare_fw_create', details=f"{action}: {expression[:80]}")
        return jsonify({'success': True, 'rule': rule_resp.get('result', [{}])[0]})
    return jsonify({'success': False, 'errors': rule_resp.get('errors', [])}), 400


@cloudflare_bp.route('/api/cloudflare/firewall/rules/delete', methods=['DELETE'])
@login_required
def cf_delete_firewall_rule():
    """Firewall kuralını sil."""
    token, zone_id = _get_token_and_zone()
    body = request.get_json(silent=True) or {}
    rule_id = body.get('rule_id')
    if not zone_id or not rule_id:
        return jsonify({'success': False, 'message': 'zone_id ve rule_id gerekli'}), 400

    resp = _cf_delete(f'/zones/{zone_id}/firewall/rules/{rule_id}', token=token)
    if resp.get('success'):
        log_action('cloudflare_fw_delete', details=f"Rule {rule_id} silindi")
        return jsonify({'success': True})
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 400


@cloudflare_bp.route('/api/cloudflare/firewall/rules/toggle', methods=['PATCH'])
@login_required
def cf_toggle_firewall_rule():
    """Firewall kuralını aç/kapa."""
    token, zone_id = _get_token_and_zone()
    body = request.get_json(silent=True) or {}
    rule_id = body.get('rule_id')
    paused = body.get('paused', True)

    if not zone_id or not rule_id:
        return jsonify({'success': False, 'message': 'zone_id ve rule_id gerekli'}), 400

    # Mevcut kuralı al
    get_resp = _cf_get(f'/zones/{zone_id}/firewall/rules/{rule_id}', token=token)
    if not get_resp.get('success'):
        return jsonify({'success': False, 'errors': get_resp.get('errors', [])}), 400

    rule = get_resp['result']
    rule['paused'] = paused

    resp = _cf_put(f'/zones/{zone_id}/firewall/rules/{rule_id}', data=rule, token=token)
    if resp.get('success'):
        log_action('cloudflare_fw_toggle', details=f"Rule {rule_id} → {'paused' if paused else 'active'}")
        return jsonify({'success': True, 'paused': paused})
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 400


# ══════════════════════════════════════════════════════════════
# ANALYTICS
# ══════════════════════════════════════════════════════════════

@cloudflare_bp.route('/api/cloudflare/analytics', methods=['POST'])
@login_required
def cf_analytics():
    """Zone analytics (son 24 saat veya belirtilen süre)."""
    token, zone_id = _get_token_and_zone()
    if not zone_id:
        return jsonify({'success': False, 'message': 'zone_id gerekli'}), 400

    body = request.get_json(silent=True) or {}
    since = body.get('since', '-1440')  # varsayılan: son 24 saat (dakika)

    resp = _cf_get(f'/zones/{zone_id}/analytics/dashboard', token=token,
                   params={'since': since, 'continuous': 'true'})
    if resp.get('success'):
        data = resp.get('result', {})
        totals = data.get('totals', {})
        timeseries = data.get('timeseries', [])

        return jsonify({
            'success': True,
            'analytics': {
                'requests': {
                    'all': totals.get('requests', {}).get('all', 0),
                    'cached': totals.get('requests', {}).get('cached', 0),
                    'uncached': totals.get('requests', {}).get('uncached', 0),
                    'ssl_encrypted': totals.get('requests', {}).get('ssl', {}).get('encrypted', 0),
                    'content_type': totals.get('requests', {}).get('content_type', {}),
                    'country': totals.get('requests', {}).get('country', {}),
                    'http_status': totals.get('requests', {}).get('http_status', {}),
                },
                'bandwidth': {
                    'all': totals.get('bandwidth', {}).get('all', 0),
                    'cached': totals.get('bandwidth', {}).get('cached', 0),
                    'uncached': totals.get('bandwidth', {}).get('uncached', 0),
                },
                'threats': {
                    'all': totals.get('threats', {}).get('all', 0),
                    'country': totals.get('threats', {}).get('country', {}),
                    'type': totals.get('threats', {}).get('type', {}),
                },
                'pageviews': {
                    'all': totals.get('pageviews', {}).get('all', 0),
                },
                'uniques': {
                    'all': totals.get('uniques', {}).get('all', 0),
                },
                'timeseries': [{
                    'since': t.get('since'),
                    'until': t.get('until'),
                    'requests': t.get('requests', {}).get('all', 0),
                    'bandwidth': t.get('bandwidth', {}).get('all', 0),
                    'threats': t.get('threats', {}).get('all', 0),
                    'pageviews': t.get('pageviews', {}).get('all', 0),
                } for t in timeseries],
            }
        })
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 400


# ══════════════════════════════════════════════════════════════
# PAGE RULES
# ══════════════════════════════════════════════════════════════

@cloudflare_bp.route('/api/cloudflare/pagerules', methods=['POST'])
@login_required
def cf_list_pagerules():
    """Page rules listele."""
    token, zone_id = _get_token_and_zone()
    if not zone_id:
        return jsonify({'success': False, 'message': 'zone_id gerekli'}), 400

    resp = _cf_get(f'/zones/{zone_id}/pagerules', token=token, params={'per_page': 50})
    if resp.get('success'):
        rules = []
        for r in resp.get('result', []):
            targets = r.get('targets', [])
            url_match = targets[0].get('constraint', {}).get('value', '') if targets else ''
            rules.append({
                'id': r['id'],
                'status': r.get('status', 'active'),
                'priority': r.get('priority'),
                'url': url_match,
                'actions': r.get('actions', []),
            })
        return jsonify({'success': True, 'rules': rules})
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 400


@cloudflare_bp.route('/api/cloudflare/pagerules/create', methods=['POST'])
@login_required
def cf_create_pagerule():
    """Yeni page rule oluştur."""
    token, zone_id = _get_token_and_zone()
    body = request.get_json(silent=True) or {}
    if not zone_id:
        return jsonify({'success': False, 'message': 'zone_id gerekli'}), 400

    url_match = body.get('url', '')
    actions = body.get('actions', [])
    if not url_match or not actions:
        return jsonify({'success': False, 'message': 'url ve actions gerekli'}), 400

    rule_data = {
        'targets': [{'target': 'url', 'constraint': {'operator': 'matches', 'value': url_match}}],
        'actions': actions,
        'status': body.get('status', 'active'),
    }

    resp = _cf_post(f'/zones/{zone_id}/pagerules', data=rule_data, token=token)
    if resp.get('success'):
        log_action('cloudflare_pagerule_create', details=f"URL: {url_match}")
        return jsonify({'success': True, 'rule': resp.get('result', {})})
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 400


@cloudflare_bp.route('/api/cloudflare/pagerules/delete', methods=['DELETE'])
@login_required
def cf_delete_pagerule():
    """Page rule sil."""
    token, zone_id = _get_token_and_zone()
    body = request.get_json(silent=True) or {}
    rule_id = body.get('rule_id')
    if not zone_id or not rule_id:
        return jsonify({'success': False, 'message': 'zone_id ve rule_id gerekli'}), 400

    resp = _cf_delete(f'/zones/{zone_id}/pagerules/{rule_id}', token=token)
    if resp.get('success'):
        log_action('cloudflare_pagerule_delete', details=f"Rule {rule_id} silindi")
        return jsonify({'success': True})
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 400


# ══════════════════════════════════════════════════════════════
# ZONE SETTINGS (Genel)
# ══════════════════════════════════════════════════════════════

@cloudflare_bp.route('/api/cloudflare/settings', methods=['POST'])
@login_required
def cf_get_settings():
    """Zone genel ayarlarını al."""
    token, zone_id = _get_token_and_zone()
    if not zone_id:
        return jsonify({'success': False, 'message': 'zone_id gerekli'}), 400

    resp = _cf_get(f'/zones/{zone_id}/settings', token=token)
    if resp.get('success'):
        settings = {s['id']: s['value'] for s in resp.get('result', [])}
        return jsonify({'success': True, 'settings': settings})
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 400


@cloudflare_bp.route('/api/cloudflare/settings/update', methods=['PATCH'])
@login_required
def cf_update_setting():
    """Tek bir zone ayarını güncelle."""
    token, zone_id = _get_token_and_zone()
    body = request.get_json(silent=True) or {}
    setting_id = body.get('setting')
    value = body.get('value')

    if not zone_id or not setting_id:
        return jsonify({'success': False, 'message': 'zone_id ve setting gerekli'}), 400

    resp = _cf_patch(f'/zones/{zone_id}/settings/{setting_id}',
                     data={'value': value}, token=token)
    if resp.get('success'):
        log_action('cloudflare_setting_update', details=f"{setting_id} → {value}")
        return jsonify({'success': True})
    return jsonify({'success': False, 'errors': resp.get('errors', [])}), 400
