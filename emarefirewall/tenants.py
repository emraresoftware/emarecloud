"""
Emare Security OS — ISP Multi-Tenant Yönetim Modülü
=================================================

ISP modunda müşteri (tenant) yönetimi:
- Tenant CRUD (oluştur, listele, güncelle, sil)
- Sunucu tahsisi (tenant ↔ server eşleştirme)
- API key yönetimi (tenant başına)
- Kota takibi (max sunucu, max kural, rate limit)
- Audit trail (tenant bazlı değişmez loglama)
- Bulk işlemler (toplu kural uygulama)
- Webhook bildirimleri
- Zamanlanmış görevler

Standalone modda bu modül kullanılmaz — tüm işlevler ISP moduna özeldir.
"""

import re
import json
import time
import hashlib
import secrets
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

logger = logging.getLogger('emarefirewall.tenants')

# ═══════════════════ GÜVENLİK: Input Validation ═══════════════════

_VALID_TENANT_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9 _.-]{0,127}$')
_VALID_API_KEY_RE = re.compile(r'^efwk_[a-zA-Z0-9]{48}$')
_VALID_PLAN_RE = re.compile(r'^(bronze|silver|gold|enterprise)$')
_VALID_EMAIL_RE = re.compile(r'^[^@\s]{1,64}@[^@\s]{1,255}\.[a-zA-Z]{2,}$')
_VALID_WEBHOOK_EVENT_RE = re.compile(
    r'^(rule_change|ip_blocked|ddos_detected|backup_created|'
    r'l7_alert|connections_high|scan_complete|tenant_update)$'
)
_VALID_URL_RE = re.compile(
    r'^https?://[a-zA-Z0-9][a-zA-Z0-9._-]{0,253}[a-zA-Z0-9]'
    r'(?::\d{1,5})?(?:/[^\s]{0,2000})?$'
)

# Plan limitleri
PLAN_LIMITS = {
    'bronze':     {'max_servers': 5,    'max_rules': 50,   'rate_limit': 30},
    'silver':     {'max_servers': 25,   'max_rules': 250,  'rate_limit': 120},
    'gold':       {'max_servers': 100,  'max_rules': 1000, 'rate_limit': 600},
    'enterprise': {'max_servers': 1000, 'max_rules': 10000,'rate_limit': 0},
}


def _generate_api_key() -> str:
    """Kriptografik olarak güvenli API key üret."""
    return 'efwk_' + secrets.token_urlsafe(36)[:48]


def _hash_api_key(key: str) -> str:
    """API key'i SHA-256 ile hashle (DB'de plaintext tutma)."""
    return hashlib.sha256(key.encode()).hexdigest()


# ═══════════════════ TENANT STORE (PostgreSQL) ═══════════════════

class TenantStore:
    """ISP mod: PostgreSQL'de tenant, sunucu, audit, webhook tabloları yönetir."""

    def __init__(self, db_backend=None):
        self._db = db_backend   # PostgresBackend instance
        self._lock = threading.Lock()

    def init(self):
        """Tabloları oluşturur (advisory lock ile çoklu worker-safe)."""
        if not self._db:
            logger.warning("TenantStore: DB backend yok, devre dışı.")
            return
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT pg_advisory_lock(43)')
                try:
                    cur.execute('''CREATE TABLE IF NOT EXISTS tenants (
                        id BIGSERIAL PRIMARY KEY,
                        name VARCHAR(128) NOT NULL,
                        email VARCHAR(320) DEFAULT '',
                        plan VARCHAR(16) NOT NULL DEFAULT 'bronze',
                        api_key_hash VARCHAR(64) NOT NULL UNIQUE,
                        api_key_prefix VARCHAR(12) NOT NULL,
                        max_servers INTEGER NOT NULL DEFAULT 5,
                        max_rules INTEGER NOT NULL DEFAULT 50,
                        rate_limit INTEGER NOT NULL DEFAULT 30,
                        active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        metadata JSONB DEFAULT '{}'
                    )''')
                    cur.execute('''CREATE TABLE IF NOT EXISTS tenant_servers (
                        id BIGSERIAL PRIMARY KEY,
                        tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                        server_id VARCHAR(128) NOT NULL,
                        label VARCHAR(256) DEFAULT '',
                        ssh_host VARCHAR(256) NOT NULL,
                        ssh_user VARCHAR(64) NOT NULL DEFAULT 'root',
                        ssh_port INTEGER NOT NULL DEFAULT 22,
                        ssh_key_ref VARCHAR(512) DEFAULT '',
                        active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE(tenant_id, server_id)
                    )''')
                    cur.execute('''CREATE TABLE IF NOT EXISTS audit_logs (
                        id BIGSERIAL PRIMARY KEY,
                        ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        tenant_id BIGINT REFERENCES tenants(id) ON DELETE SET NULL,
                        user_ip VARCHAR(45) DEFAULT '',
                        action VARCHAR(64) NOT NULL,
                        resource_type VARCHAR(32) DEFAULT '',
                        resource_id VARCHAR(256) DEFAULT '',
                        details JSONB DEFAULT '{}',
                        success BOOLEAN DEFAULT TRUE
                    )''')
                    cur.execute('''CREATE TABLE IF NOT EXISTS webhooks (
                        id BIGSERIAL PRIMARY KEY,
                        tenant_id BIGINT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                        url VARCHAR(2048) NOT NULL,
                        events TEXT[] NOT NULL DEFAULT '{}',
                        secret VARCHAR(128) DEFAULT '',
                        active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        last_triggered TIMESTAMPTZ,
                        fail_count INTEGER DEFAULT 0
                    )''')
                    cur.execute('''CREATE TABLE IF NOT EXISTS scheduled_tasks (
                        id BIGSERIAL PRIMARY KEY,
                        tenant_id BIGINT REFERENCES tenants(id) ON DELETE CASCADE,
                        task_type VARCHAR(64) NOT NULL,
                        server_id VARCHAR(128) DEFAULT '',
                        cron_expr VARCHAR(64) NOT NULL,
                        payload JSONB DEFAULT '{}',
                        active BOOLEAN NOT NULL DEFAULT TRUE,
                        last_run TIMESTAMPTZ,
                        next_run TIMESTAMPTZ,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )''')
                    cur.execute('''CREATE TABLE IF NOT EXISTS bulk_jobs (
                        id BIGSERIAL PRIMARY KEY,
                        tenant_id BIGINT REFERENCES tenants(id) ON DELETE SET NULL,
                        job_type VARCHAR(64) NOT NULL,
                        status VARCHAR(16) NOT NULL DEFAULT 'pending',
                        total INTEGER NOT NULL DEFAULT 0,
                        completed INTEGER NOT NULL DEFAULT 0,
                        failed INTEGER NOT NULL DEFAULT 0,
                        payload JSONB DEFAULT '{}',
                        results JSONB DEFAULT '[]',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        finished_at TIMESTAMPTZ
                    )''')
                    cur.execute('''CREATE TABLE IF NOT EXISTS alerts (
                        id BIGSERIAL PRIMARY KEY,
                        tenant_id BIGINT REFERENCES tenants(id) ON DELETE CASCADE,
                        alert_type VARCHAR(64) NOT NULL,
                        server_id VARCHAR(128) DEFAULT '',
                        severity VARCHAR(16) NOT NULL DEFAULT 'warning',
                        message TEXT NOT NULL,
                        details JSONB DEFAULT '{}',
                        acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )''')
                    cur.execute('''CREATE TABLE IF NOT EXISTS cgnat_pools (
                        id BIGSERIAL PRIMARY KEY,
                        tenant_id BIGINT REFERENCES tenants(id) ON DELETE CASCADE,
                        pool_name VARCHAR(128) NOT NULL,
                        public_ip VARCHAR(45) NOT NULL,
                        port_start INTEGER NOT NULL DEFAULT 1024,
                        port_end INTEGER NOT NULL DEFAULT 65535,
                        ports_per_subscriber INTEGER NOT NULL DEFAULT 1024,
                        active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE(pool_name)
                    )''')
                    cur.execute('''CREATE TABLE IF NOT EXISTS cgnat_mappings (
                        id BIGSERIAL PRIMARY KEY,
                        pool_id BIGINT NOT NULL REFERENCES cgnat_pools(id) ON DELETE CASCADE,
                        subscriber_ip VARCHAR(45) NOT NULL,
                        public_ip VARCHAR(45) NOT NULL,
                        port_start INTEGER NOT NULL,
                        port_end INTEGER NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        expires_at TIMESTAMPTZ,
                        UNIQUE(pool_id, subscriber_ip)
                    )''')
                    cur.execute('''CREATE TABLE IF NOT EXISTS ipam_blocks (
                        id BIGSERIAL PRIMARY KEY,
                        tenant_id BIGINT REFERENCES tenants(id) ON DELETE CASCADE,
                        cidr VARCHAR(50) NOT NULL,
                        description VARCHAR(256) DEFAULT '',
                        block_type VARCHAR(16) NOT NULL DEFAULT 'assigned',
                        vlan INTEGER,
                        gateway VARCHAR(45) DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE(cidr)
                    )''')
                    cur.execute('''CREATE TABLE IF NOT EXISTS ipam_assignments (
                        id BIGSERIAL PRIMARY KEY,
                        block_id BIGINT NOT NULL REFERENCES ipam_blocks(id) ON DELETE CASCADE,
                        ip_address VARCHAR(45) NOT NULL,
                        assigned_to VARCHAR(256) DEFAULT '',
                        mac_address VARCHAR(17) DEFAULT '',
                        status VARCHAR(16) NOT NULL DEFAULT 'assigned',
                        note VARCHAR(512) DEFAULT '',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE(ip_address)
                    )''')
                    # İndeksler
                    cur.execute('CREATE INDEX IF NOT EXISTS idx_ts_tenant ON tenant_servers(tenant_id)')
                    cur.execute('CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_logs(tenant_id)')
                    cur.execute('CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_logs(ts)')
                    cur.execute('CREATE INDEX IF NOT EXISTS idx_webhook_tenant ON webhooks(tenant_id)')
                    cur.execute('CREATE INDEX IF NOT EXISTS idx_sched_active ON scheduled_tasks(active, next_run)')
                    cur.execute('CREATE INDEX IF NOT EXISTS idx_bulk_status ON bulk_jobs(status)')
                    cur.execute('CREATE INDEX IF NOT EXISTS idx_alerts_tenant ON alerts(tenant_id, acknowledged)')
                    cur.execute('CREATE INDEX IF NOT EXISTS idx_cgnat_pool ON cgnat_mappings(pool_id)')
                    cur.execute('CREATE INDEX IF NOT EXISTS idx_ipam_block ON ipam_assignments(block_id)')
                    conn.commit()
                    logger.info("ISP tabloları başarıyla oluşturuldu/doğrulandı.")
                finally:
                    cur.execute('SELECT pg_advisory_unlock(43)')
        finally:
            self._db._put_conn(conn)

    # ── Tenant CRUD ──

    def create_tenant(self, name: str, email: str = '',
                      plan: str = 'bronze') -> dict:
        """Yeni tenant oluşturur, API key döndürür."""
        name = name.strip()
        if not _VALID_TENANT_NAME_RE.match(name):
            return {'success': False, 'message': 'Geçersiz tenant adı.'}
        if email and not _VALID_EMAIL_RE.match(email):
            return {'success': False, 'message': 'Geçersiz email formatı.'}
        if not _VALID_PLAN_RE.match(plan):
            return {'success': False, 'message': 'Geçersiz plan. bronze/silver/gold/enterprise'}

        limits = PLAN_LIMITS[plan]
        api_key = _generate_api_key()
        key_hash = _hash_api_key(api_key)
        key_prefix = api_key[:12]

        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''INSERT INTO tenants (name, email, plan, api_key_hash,
                       api_key_prefix, max_servers, max_rules, rate_limit)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                       RETURNING id, created_at''',
                    (name, email, plan, key_hash, key_prefix,
                     limits['max_servers'], limits['max_rules'],
                     limits['rate_limit']))
                row = cur.fetchone()
                conn.commit()
            return {
                'success': True,
                'tenant': {
                    'id': row[0], 'name': name, 'email': email,
                    'plan': plan, 'api_key': api_key,
                    'api_key_prefix': key_prefix,
                    'max_servers': limits['max_servers'],
                    'max_rules': limits['max_rules'],
                    'rate_limit': limits['rate_limit'],
                    'created_at': row[1].isoformat(),
                },
                'message': 'Tenant oluşturuldu. API key\'i güvenli bir yerde saklayın.',
            }
        except Exception as e:
            conn.rollback()
            if 'unique' in str(e).lower():
                return {'success': False, 'message': 'Bu API key zaten mevcut.'}
            logger.error('Tenant oluşturma hatası: %s', e)
            return {'success': False, 'message': 'Tenant oluşturulamadı.'}
        finally:
            self._db._put_conn(conn)

    def list_tenants(self, active_only: bool = True) -> list:
        """Tüm tenant'ları listeler."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                sql = '''SELECT id, name, email, plan, api_key_prefix,
                         max_servers, max_rules, rate_limit, active,
                         created_at, updated_at FROM tenants'''
                if active_only:
                    sql += ' WHERE active = TRUE'
                sql += ' ORDER BY id'
                cur.execute(sql)
                rows = cur.fetchall()
            result = []
            for r in rows:
                result.append({
                    'id': r[0], 'name': r[1], 'email': r[2], 'plan': r[3],
                    'api_key_prefix': r[4], 'max_servers': r[5],
                    'max_rules': r[6], 'rate_limit': r[7], 'active': r[8],
                    'created_at': r[9].isoformat() if hasattr(r[9], 'isoformat') else str(r[9]),
                    'updated_at': r[10].isoformat() if hasattr(r[10], 'isoformat') else str(r[10]),
                })
            return result
        finally:
            self._db._put_conn(conn)

    def get_tenant(self, tenant_id: int) -> dict:
        """Tek tenant bilgisi."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''SELECT id, name, email, plan, api_key_prefix,
                       max_servers, max_rules, rate_limit, active,
                       created_at, updated_at, metadata
                       FROM tenants WHERE id = %s''', (int(tenant_id),))
                r = cur.fetchone()
            if not r:
                return None
            return {
                'id': r[0], 'name': r[1], 'email': r[2], 'plan': r[3],
                'api_key_prefix': r[4], 'max_servers': r[5],
                'max_rules': r[6], 'rate_limit': r[7], 'active': r[8],
                'created_at': r[9].isoformat() if hasattr(r[9], 'isoformat') else str(r[9]),
                'updated_at': r[10].isoformat() if hasattr(r[10], 'isoformat') else str(r[10]),
                'metadata': r[11] if isinstance(r[11], dict) else {},
            }
        finally:
            self._db._put_conn(conn)

    def update_tenant(self, tenant_id: int, **fields) -> dict:
        """Tenant bilgilerini günceller. İzin verilen: name, email, plan, active, metadata."""
        allowed = {'name', 'email', 'plan', 'active', 'metadata'}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return {'success': False, 'message': 'Güncellenecek alan belirtin.'}

        if 'name' in updates and not _VALID_TENANT_NAME_RE.match(str(updates['name']).strip()):
            return {'success': False, 'message': 'Geçersiz tenant adı.'}
        if 'email' in updates and updates['email'] and not _VALID_EMAIL_RE.match(updates['email']):
            return {'success': False, 'message': 'Geçersiz email formatı.'}
        if 'plan' in updates:
            if not _VALID_PLAN_RE.match(updates['plan']):
                return {'success': False, 'message': 'Geçersiz plan.'}
            limits = PLAN_LIMITS[updates['plan']]
            updates['max_servers'] = limits['max_servers']
            updates['max_rules'] = limits['max_rules']
            updates['rate_limit'] = limits['rate_limit']

        set_clauses = []
        params = []
        for k, v in updates.items():
            if k == 'metadata':
                set_clauses.append(f'{k} = %s::jsonb')
                params.append(json.dumps(v, ensure_ascii=False))
            else:
                set_clauses.append(f'{k} = %s')
                params.append(v)
        set_clauses.append('updated_at = NOW()')
        params.append(int(tenant_id))

        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f'UPDATE tenants SET {", ".join(set_clauses)} WHERE id = %s',
                    params)
                conn.commit()
                if cur.rowcount == 0:
                    return {'success': False, 'message': 'Tenant bulunamadı.'}
            return {'success': True, 'message': 'Tenant güncellendi.'}
        except Exception as e:
            conn.rollback()
            logger.error('Tenant güncelleme hatası: %s', e)
            return {'success': False, 'message': 'Güncelleme başarısız.'}
        finally:
            self._db._put_conn(conn)

    def delete_tenant(self, tenant_id: int) -> dict:
        """Tenant'ı siler (CASCADE ile alt kayıtlar da silinir)."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM tenants WHERE id = %s', (int(tenant_id),))
                conn.commit()
                if cur.rowcount == 0:
                    return {'success': False, 'message': 'Tenant bulunamadı.'}
            return {'success': True, 'message': 'Tenant ve tüm ilişkili veriler silindi.'}
        finally:
            self._db._put_conn(conn)

    def regenerate_api_key(self, tenant_id: int) -> dict:
        """Tenant için yeni API key üretir, eskisi geçersiz olur."""
        api_key = _generate_api_key()
        key_hash = _hash_api_key(api_key)
        key_prefix = api_key[:12]
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''UPDATE tenants SET api_key_hash = %s, api_key_prefix = %s,
                       updated_at = NOW() WHERE id = %s''',
                    (key_hash, key_prefix, int(tenant_id)))
                conn.commit()
                if cur.rowcount == 0:
                    return {'success': False, 'message': 'Tenant bulunamadı.'}
            return {'success': True, 'api_key': api_key,
                    'message': 'Yeni API key üretildi. Eski key artık geçersiz.'}
        finally:
            self._db._put_conn(conn)

    def authenticate_by_key(self, api_key: str) -> dict:
        """API key ile tenant doğrulama. -> tenant dict veya None."""
        if not api_key or not _VALID_API_KEY_RE.match(api_key):
            return None
        key_hash = _hash_api_key(api_key)
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''SELECT id, name, plan, max_servers, max_rules,
                       rate_limit, active FROM tenants
                       WHERE api_key_hash = %s''', (key_hash,))
                r = cur.fetchone()
            if not r:
                return None
            if not r[6]:  # active
                return None
            return {
                'id': r[0], 'name': r[1], 'plan': r[2],
                'max_servers': r[3], 'max_rules': r[4],
                'rate_limit': r[5],
            }
        finally:
            self._db._put_conn(conn)

    # ── Sunucu Yönetimi ──

    def add_server(self, tenant_id: int, server_id: str, ssh_host: str,
                   ssh_user: str = 'root', ssh_port: int = 22,
                   ssh_key_ref: str = '', label: str = '') -> dict:
        """Tenant'a sunucu atar."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {'success': False, 'message': 'Tenant bulunamadı.'}
        # Kota kontrolü
        current = self.list_servers(tenant_id)
        if len(current) >= tenant['max_servers']:
            return {'success': False,
                    'message': f'Sunucu kotası doldu ({tenant["max_servers"]}).'}
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''INSERT INTO tenant_servers
                       (tenant_id, server_id, label, ssh_host, ssh_user,
                        ssh_port, ssh_key_ref)
                       VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id''',
                    (int(tenant_id), server_id, label, ssh_host, ssh_user,
                     int(ssh_port), ssh_key_ref))
                conn.commit()
            return {'success': True, 'message': f'Sunucu {server_id} eklendi.'}
        except Exception as e:
            conn.rollback()
            if 'unique' in str(e).lower():
                return {'success': False, 'message': 'Bu sunucu zaten bu tenant\'a atanmış.'}
            logger.error('Sunucu ekleme hatası: %s', e)
            return {'success': False, 'message': 'Sunucu eklenemedi.'}
        finally:
            self._db._put_conn(conn)

    def list_servers(self, tenant_id: int) -> list:
        """Tenant'ın sunucularını listeler."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''SELECT id, server_id, label, ssh_host, ssh_user,
                       ssh_port, active, created_at
                       FROM tenant_servers WHERE tenant_id = %s
                       ORDER BY id''', (int(tenant_id),))
                rows = cur.fetchall()
            return [
                {'id': r[0], 'server_id': r[1], 'label': r[2],
                 'ssh_host': r[3], 'ssh_user': r[4], 'ssh_port': r[5],
                 'active': r[6],
                 'created_at': r[7].isoformat() if hasattr(r[7], 'isoformat') else str(r[7])}
                for r in rows
            ]
        finally:
            self._db._put_conn(conn)

    def remove_server(self, tenant_id: int, server_id: str) -> dict:
        """Tenant'tan sunucu kaldırır."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    'DELETE FROM tenant_servers WHERE tenant_id = %s AND server_id = %s',
                    (int(tenant_id), server_id))
                conn.commit()
                if cur.rowcount == 0:
                    return {'success': False, 'message': 'Sunucu bulunamadı.'}
            return {'success': True, 'message': f'Sunucu {server_id} kaldırıldı.'}
        finally:
            self._db._put_conn(conn)

    def is_server_allowed(self, tenant_id: int, server_id: str) -> bool:
        """Tenant'ın bu sunucuya erişim izni var mı?"""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''SELECT 1 FROM tenant_servers
                       WHERE tenant_id = %s AND server_id = %s AND active = TRUE''',
                    (int(tenant_id), server_id))
                return cur.fetchone() is not None
        finally:
            self._db._put_conn(conn)

    # ── Audit Trail ──

    def add_audit(self, tenant_id: int, action: str, user_ip: str = '',
                  resource_type: str = '', resource_id: str = '',
                  details: dict = None, success: bool = True):
        """Değişmez audit log kaydı ekler."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''INSERT INTO audit_logs
                       (tenant_id, user_ip, action, resource_type,
                        resource_id, details, success)
                       VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)''',
                    (int(tenant_id), user_ip, action, resource_type,
                     resource_id,
                     json.dumps(details or {}, ensure_ascii=False),
                     success))
                conn.commit()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.warning('Audit log yazma hatası: %s', e)
        finally:
            self._db._put_conn(conn)

    def query_audit(self, tenant_id: int = None, limit: int = 100,
                    action: str = '', since_ts: str = '') -> list:
        """Audit loglarını sorgular."""
        conn = self._db._get_conn()
        try:
            conditions = []
            params = []
            if tenant_id is not None:
                conditions.append('tenant_id = %s')
                params.append(int(tenant_id))
            if action:
                conditions.append('action = %s')
                params.append(action)
            if since_ts:
                conditions.append('ts >= %s')
                params.append(since_ts)
            where = ' AND '.join(conditions) if conditions else '1=1'
            params.append(min(int(limit), 500))
            with conn.cursor() as cur:
                cur.execute(
                    f'''SELECT id, ts, tenant_id, user_ip, action,
                        resource_type, resource_id, details, success
                        FROM audit_logs WHERE {where}
                        ORDER BY id DESC LIMIT %s''', params)
                rows = cur.fetchall()
            return [
                {'id': r[0],
                 'ts': r[1].isoformat() if hasattr(r[1], 'isoformat') else str(r[1]),
                 'tenant_id': r[2], 'user_ip': r[3], 'action': r[4],
                 'resource_type': r[5], 'resource_id': r[6],
                 'details': r[7] if isinstance(r[7], dict) else {},
                 'success': r[8]}
                for r in rows
            ]
        finally:
            self._db._put_conn(conn)

    # ── Webhook Yönetimi ──

    def add_webhook(self, tenant_id: int, url: str,
                    events: list, secret: str = '') -> dict:
        """Webhook kaydı ekler."""
        if not _VALID_URL_RE.match(url):
            return {'success': False, 'message': 'Geçersiz URL formatı.'}
        for ev in events:
            if not _VALID_WEBHOOK_EVENT_RE.match(ev):
                return {'success': False, 'message': f'Geçersiz event: {ev}'}
        if not secret:
            secret = secrets.token_hex(32)
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''INSERT INTO webhooks (tenant_id, url, events, secret)
                       VALUES (%s, %s, %s, %s) RETURNING id''',
                    (int(tenant_id), url, events, secret))
                wid = cur.fetchone()[0]
                conn.commit()
            return {'success': True, 'webhook_id': wid, 'secret': secret,
                    'message': 'Webhook eklendi.'}
        except Exception as e:
            conn.rollback()
            logger.error('Webhook ekleme hatası: %s', e)
            return {'success': False, 'message': 'Webhook eklenemedi.'}
        finally:
            self._db._put_conn(conn)

    def list_webhooks(self, tenant_id: int) -> list:
        """Tenant'ın webhook'larını listeler."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''SELECT id, url, events, active, created_at,
                       last_triggered, fail_count
                       FROM webhooks WHERE tenant_id = %s ORDER BY id''',
                    (int(tenant_id),))
                rows = cur.fetchall()
            return [
                {'id': r[0], 'url': r[1], 'events': r[2], 'active': r[3],
                 'created_at': r[4].isoformat() if hasattr(r[4], 'isoformat') else str(r[4]),
                 'last_triggered': r[5].isoformat() if r[5] and hasattr(r[5], 'isoformat') else None,
                 'fail_count': r[6]}
                for r in rows
            ]
        finally:
            self._db._put_conn(conn)

    def remove_webhook(self, tenant_id: int, webhook_id: int) -> dict:
        """Webhook siler."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    'DELETE FROM webhooks WHERE id = %s AND tenant_id = %s',
                    (int(webhook_id), int(tenant_id)))
                conn.commit()
                if cur.rowcount == 0:
                    return {'success': False, 'message': 'Webhook bulunamadı.'}
            return {'success': True, 'message': 'Webhook silindi.'}
        finally:
            self._db._put_conn(conn)

    def get_webhooks_for_event(self, tenant_id: int, event: str) -> list:
        """Belirli event için aktif webhook'ları döndürür."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''SELECT id, url, secret FROM webhooks
                       WHERE tenant_id = %s AND active = TRUE
                       AND %s = ANY(events)''',
                    (int(tenant_id), event))
                rows = cur.fetchall()
            return [{'id': r[0], 'url': r[1], 'secret': r[2]} for r in rows]
        finally:
            self._db._put_conn(conn)

    def update_webhook_status(self, webhook_id: int, success: bool):
        """Webhook tetikleme sonucunu günceller."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                if success:
                    cur.execute(
                        '''UPDATE webhooks SET last_triggered = NOW(),
                           fail_count = 0 WHERE id = %s''',
                        (int(webhook_id),))
                else:
                    cur.execute(
                        '''UPDATE webhooks SET fail_count = fail_count + 1,
                           active = CASE WHEN fail_count >= 9 THEN FALSE
                           ELSE active END WHERE id = %s''',
                        (int(webhook_id),))
                conn.commit()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.warning('Webhook durum güncelleme hatası: %s', e)
        finally:
            self._db._put_conn(conn)

    # ── Alert Yönetimi ──

    def add_alert(self, tenant_id: int, alert_type: str, message: str,
                  server_id: str = '', severity: str = 'warning',
                  details: dict = None) -> int:
        """Alert kaydı ekler, id döndürür."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''INSERT INTO alerts
                       (tenant_id, alert_type, server_id, severity,
                        message, details)
                       VALUES (%s, %s, %s, %s, %s, %s::jsonb) RETURNING id''',
                    (int(tenant_id), alert_type, server_id, severity,
                     message,
                     json.dumps(details or {}, ensure_ascii=False)))
                aid = cur.fetchone()[0]
                conn.commit()
            return aid
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.warning('Alert ekleme hatası: %s', e)
            return 0
        finally:
            self._db._put_conn(conn)

    def list_alerts(self, tenant_id: int, limit: int = 50,
                    unacknowledged_only: bool = False) -> list:
        """Tenant'ın alert'lerini listeler."""
        conn = self._db._get_conn()
        try:
            conditions = ['tenant_id = %s']
            params = [int(tenant_id)]
            if unacknowledged_only:
                conditions.append('acknowledged = FALSE')
            params.append(min(int(limit), 200))
            where = ' AND '.join(conditions)
            with conn.cursor() as cur:
                cur.execute(
                    f'''SELECT id, alert_type, server_id, severity, message,
                        details, acknowledged, created_at
                        FROM alerts WHERE {where}
                        ORDER BY id DESC LIMIT %s''', params)
                rows = cur.fetchall()
            return [
                {'id': r[0], 'alert_type': r[1], 'server_id': r[2],
                 'severity': r[3], 'message': r[4],
                 'details': r[5] if isinstance(r[5], dict) else {},
                 'acknowledged': r[6],
                 'created_at': r[7].isoformat() if hasattr(r[7], 'isoformat') else str(r[7])}
                for r in rows
            ]
        finally:
            self._db._put_conn(conn)

    def acknowledge_alert(self, tenant_id: int, alert_id: int) -> dict:
        """Alert'i okundu olarak işaretle."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''UPDATE alerts SET acknowledged = TRUE
                       WHERE id = %s AND tenant_id = %s''',
                    (int(alert_id), int(tenant_id)))
                conn.commit()
                if cur.rowcount == 0:
                    return {'success': False, 'message': 'Alert bulunamadı.'}
            return {'success': True, 'message': 'Alert onaylandı.'}
        finally:
            self._db._put_conn(conn)

    # ── Zamanlanmış Görevler ──

    def add_scheduled_task(self, tenant_id: int, task_type: str,
                           cron_expr: str, server_id: str = '',
                           payload: dict = None) -> dict:
        """Zamanlanmış görev ekler."""
        valid_tasks = {'backup', 'security_scan', 'l7_scan', 'rule_apply',
                       'rule_remove', 'log_cleanup'}
        if task_type not in valid_tasks:
            return {'success': False,
                    'message': f'Geçersiz görev tipi. İzin verilenler: {", ".join(sorted(valid_tasks))}'}

        # cron_expr format kontrolü: basit 5-alan cron (dk sa gün ay haftaGünü)
        cron_parts = cron_expr.strip().split()
        if len(cron_parts) != 5:
            return {'success': False, 'message': 'Cron ifadesi 5 alanlı olmalı (dk sa gün ay haftaGünü).'}

        next_run = datetime.now(timezone.utc) + timedelta(minutes=1)
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''INSERT INTO scheduled_tasks
                       (tenant_id, task_type, server_id, cron_expr,
                        payload, next_run)
                       VALUES (%s, %s, %s, %s, %s::jsonb, %s) RETURNING id''',
                    (int(tenant_id), task_type, server_id, cron_expr,
                     json.dumps(payload or {}, ensure_ascii=False),
                     next_run))
                tid = cur.fetchone()[0]
                conn.commit()
            return {'success': True, 'task_id': tid,
                    'message': 'Zamanlanmış görev oluşturuldu.'}
        except Exception as e:
            conn.rollback()
            logger.error('Scheduled task ekleme hatası: %s', e)
            return {'success': False, 'message': 'Görev oluşturulamadı.'}
        finally:
            self._db._put_conn(conn)

    def list_scheduled_tasks(self, tenant_id: int) -> list:
        """Tenant'ın zamanlanmış görevlerini listeler."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''SELECT id, task_type, server_id, cron_expr, active,
                       last_run, next_run, created_at
                       FROM scheduled_tasks WHERE tenant_id = %s
                       ORDER BY id''', (int(tenant_id),))
                rows = cur.fetchall()
            def _ts(v):
                return v.isoformat() if v and hasattr(v, 'isoformat') else None
            return [
                {'id': r[0], 'task_type': r[1], 'server_id': r[2],
                 'cron_expr': r[3], 'active': r[4],
                 'last_run': _ts(r[5]), 'next_run': _ts(r[6]),
                 'created_at': _ts(r[7])}
                for r in rows
            ]
        finally:
            self._db._put_conn(conn)

    def remove_scheduled_task(self, tenant_id: int, task_id: int) -> dict:
        """Zamanlanmış görevi siler."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    'DELETE FROM scheduled_tasks WHERE id = %s AND tenant_id = %s',
                    (int(task_id), int(tenant_id)))
                conn.commit()
                if cur.rowcount == 0:
                    return {'success': False, 'message': 'Görev bulunamadı.'}
            return {'success': True, 'message': 'Zamanlanmış görev silindi.'}
        finally:
            self._db._put_conn(conn)

    # ── Bulk Job Yönetimi ──

    def create_bulk_job(self, tenant_id: int, job_type: str,
                        total: int, payload: dict = None) -> int:
        """Bulk iş oluşturur, job_id döndürür."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''INSERT INTO bulk_jobs
                       (tenant_id, job_type, status, total, payload)
                       VALUES (%s, %s, 'running', %s, %s::jsonb) RETURNING id''',
                    (int(tenant_id), job_type, int(total),
                     json.dumps(payload or {}, ensure_ascii=False)))
                jid = cur.fetchone()[0]
                conn.commit()
            return jid
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.error('Bulk job oluşturma hatası: %s', e)
            return 0
        finally:
            self._db._put_conn(conn)

    def update_bulk_job(self, job_id: int, completed: int = 0,
                        failed: int = 0, results: list = None,
                        status: str = None):
        """Bulk job ilerlemesini günceller."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                sets = ['completed = %s', 'failed = %s']
                params = [int(completed), int(failed)]
                if results is not None:
                    sets.append('results = %s::jsonb')
                    params.append(json.dumps(results, ensure_ascii=False))
                if status:
                    sets.append('status = %s')
                    params.append(status)
                    if status in ('completed', 'failed'):
                        sets.append('finished_at = NOW()')
                params.append(int(job_id))
                cur.execute(
                    f'UPDATE bulk_jobs SET {", ".join(sets)} WHERE id = %s',
                    params)
                conn.commit()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.warning('Bulk job güncelleme hatası: %s', e)
        finally:
            self._db._put_conn(conn)

    def get_bulk_job(self, job_id: int) -> dict:
        """Bulk job durumunu sorgular."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''SELECT id, tenant_id, job_type, status, total,
                       completed, failed, results, created_at, finished_at
                       FROM bulk_jobs WHERE id = %s''', (int(job_id),))
                r = cur.fetchone()
            if not r:
                return None
            def _ts(v):
                return v.isoformat() if v and hasattr(v, 'isoformat') else None
            return {
                'id': r[0], 'tenant_id': r[1], 'job_type': r[2],
                'status': r[3], 'total': r[4], 'completed': r[5],
                'failed': r[6], 'results': r[7] if isinstance(r[7], list) else [],
                'created_at': _ts(r[8]), 'finished_at': _ts(r[9]),
            }
        finally:
            self._db._put_conn(conn)

    def list_bulk_jobs(self, tenant_id: int, limit: int = 20) -> list:
        """Tenant'ın bulk job'larını listeler."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''SELECT id, job_type, status, total, completed, failed,
                       created_at, finished_at
                       FROM bulk_jobs WHERE tenant_id = %s
                       ORDER BY id DESC LIMIT %s''',
                    (int(tenant_id), min(int(limit), 100)))
                rows = cur.fetchall()
            def _ts(v):
                return v.isoformat() if v and hasattr(v, 'isoformat') else None
            return [
                {'id': r[0], 'job_type': r[1], 'status': r[2],
                 'total': r[3], 'completed': r[4], 'failed': r[5],
                 'created_at': _ts(r[6]), 'finished_at': _ts(r[7])}
                for r in rows
            ]
        finally:
            self._db._put_conn(conn)

    # ── CGNAT Yönetimi ──

    def add_cgnat_pool(self, tenant_id: int, pool_name: str, public_ip: str,
                       port_start: int = 1024, port_end: int = 65535,
                       ports_per_subscriber: int = 1024) -> dict:
        """CGNAT havuzu oluşturur."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''INSERT INTO cgnat_pools
                       (tenant_id, pool_name, public_ip, port_start,
                        port_end, ports_per_subscriber)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id''',
                    (int(tenant_id), pool_name, public_ip,
                     int(port_start), int(port_end), int(ports_per_subscriber)))
                pid = cur.fetchone()[0]
                conn.commit()
            return {'success': True, 'pool_id': pid,
                    'message': f'CGNAT havuzu {pool_name} oluşturuldu.'}
        except Exception as e:
            conn.rollback()
            if 'unique' in str(e).lower():
                return {'success': False, 'message': 'Bu havuz adı zaten mevcut.'}
            logger.error('CGNAT havuz oluşturma hatası: %s', e)
            return {'success': False, 'message': 'CGNAT havuzu oluşturulamadı.'}
        finally:
            self._db._put_conn(conn)

    def list_cgnat_pools(self, tenant_id: int) -> list:
        """CGNAT havuzlarını listeler."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''SELECT p.id, p.pool_name, p.public_ip, p.port_start,
                       p.port_end, p.ports_per_subscriber, p.active,
                       COUNT(m.id) as mapping_count
                       FROM cgnat_pools p
                       LEFT JOIN cgnat_mappings m ON p.id = m.pool_id
                       WHERE p.tenant_id = %s
                       GROUP BY p.id ORDER BY p.id''', (int(tenant_id),))
                rows = cur.fetchall()
            return [
                {'id': r[0], 'pool_name': r[1], 'public_ip': r[2],
                 'port_start': r[3], 'port_end': r[4],
                 'ports_per_subscriber': r[5], 'active': r[6],
                 'mapping_count': r[7],
                 'capacity': (r[4] - r[3] + 1) // r[5]}
                for r in rows
            ]
        finally:
            self._db._put_conn(conn)

    def allocate_cgnat(self, pool_id: int, subscriber_ip: str) -> dict:
        """Aboneye CGNAT port bloğu tahsis eder (deterministik)."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                # Havuz bilgisi
                cur.execute(
                    'SELECT public_ip, port_start, port_end, ports_per_subscriber '
                    'FROM cgnat_pools WHERE id = %s AND active = TRUE',
                    (int(pool_id),))
                pool = cur.fetchone()
                if not pool:
                    return {'success': False, 'message': 'Havuz bulunamadı veya pasif.'}

                pub_ip, p_start, p_end, pps = pool
                total_slots = (p_end - p_start + 1) // pps

                # Mevcut tahsis kontrolü
                cur.execute(
                    'SELECT public_ip, port_start, port_end FROM cgnat_mappings '
                    'WHERE pool_id = %s AND subscriber_ip = %s',
                    (int(pool_id), subscriber_ip))
                existing = cur.fetchone()
                if existing:
                    return {'success': True, 'already_allocated': True,
                            'mapping': {'public_ip': existing[0],
                                        'port_start': existing[1],
                                        'port_end': existing[2]}}

                # Mevcut tahsis sayısı
                cur.execute(
                    'SELECT COUNT(*) FROM cgnat_mappings WHERE pool_id = %s',
                    (int(pool_id),))
                count = cur.fetchone()[0]
                if count >= total_slots:
                    return {'success': False, 'message': 'Havuz kapasitesi doldu.'}

                # Sonraki port bloğu
                ps = p_start + (count * pps)
                pe = ps + pps - 1
                cur.execute(
                    '''INSERT INTO cgnat_mappings
                       (pool_id, subscriber_ip, public_ip, port_start, port_end)
                       VALUES (%s, %s, %s, %s, %s)''',
                    (int(pool_id), subscriber_ip, pub_ip, ps, pe))
                conn.commit()
            return {'success': True,
                    'mapping': {'public_ip': pub_ip, 'port_start': ps,
                                'port_end': pe, 'subscriber_ip': subscriber_ip}}
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            if 'unique' in str(e).lower():
                return {'success': False, 'message': 'Bu abone zaten tahsisli.'}
            logger.error('CGNAT tahsis hatası: %s', e)
            return {'success': False, 'message': 'CGNAT tahsisi başarısız.'}
        finally:
            self._db._put_conn(conn)

    def release_cgnat(self, pool_id: int, subscriber_ip: str) -> dict:
        """CGNAT tahsisini serbest bırakır."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    'DELETE FROM cgnat_mappings WHERE pool_id = %s AND subscriber_ip = %s',
                    (int(pool_id), subscriber_ip))
                conn.commit()
                if cur.rowcount == 0:
                    return {'success': False, 'message': 'Tahsis bulunamadı.'}
            return {'success': True, 'message': f'{subscriber_ip} CGNAT tahsisi serbest bırakıldı.'}
        finally:
            self._db._put_conn(conn)

    def list_cgnat_mappings(self, pool_id: int) -> list:
        """CGNAT eşlemelerini listeler."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''SELECT id, subscriber_ip, public_ip, port_start,
                       port_end, created_at
                       FROM cgnat_mappings WHERE pool_id = %s
                       ORDER BY port_start''', (int(pool_id),))
                rows = cur.fetchall()
            return [
                {'id': r[0], 'subscriber_ip': r[1], 'public_ip': r[2],
                 'port_start': r[3], 'port_end': r[4],
                 'created_at': r[5].isoformat() if hasattr(r[5], 'isoformat') else str(r[5])}
                for r in rows
            ]
        finally:
            self._db._put_conn(conn)

    # ── IPAM (IP Adres Yönetimi) ──

    def add_ipam_block(self, tenant_id: int, cidr: str,
                       description: str = '', block_type: str = 'assigned',
                       vlan: int = None, gateway: str = '') -> dict:
        """IP bloğu ekler."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''INSERT INTO ipam_blocks
                       (tenant_id, cidr, description, block_type, vlan, gateway)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id''',
                    (int(tenant_id), cidr, description, block_type,
                     int(vlan) if vlan else None, gateway))
                bid = cur.fetchone()[0]
                conn.commit()
            return {'success': True, 'block_id': bid,
                    'message': f'IP bloğu {cidr} eklendi.'}
        except Exception as e:
            conn.rollback()
            if 'unique' in str(e).lower():
                return {'success': False, 'message': 'Bu CIDR zaten kayıtlı.'}
            logger.error('IPAM blok ekleme hatası: %s', e)
            return {'success': False, 'message': 'IP bloğu eklenemedi.'}
        finally:
            self._db._put_conn(conn)

    def list_ipam_blocks(self, tenant_id: int) -> list:
        """Tenant'ın IP bloklarını listeler."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''SELECT b.id, b.cidr, b.description, b.block_type,
                       b.vlan, b.gateway, COUNT(a.id) as assigned_count
                       FROM ipam_blocks b
                       LEFT JOIN ipam_assignments a ON b.id = a.block_id
                       WHERE b.tenant_id = %s
                       GROUP BY b.id ORDER BY b.id''', (int(tenant_id),))
                rows = cur.fetchall()
            return [
                {'id': r[0], 'cidr': r[1], 'description': r[2],
                 'block_type': r[3], 'vlan': r[4], 'gateway': r[5],
                 'assigned_count': r[6]}
                for r in rows
            ]
        finally:
            self._db._put_conn(conn)

    def remove_ipam_block(self, tenant_id: int, block_id: int) -> dict:
        """IP bloğunu siler."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    'DELETE FROM ipam_blocks WHERE id = %s AND tenant_id = %s',
                    (int(block_id), int(tenant_id)))
                conn.commit()
                if cur.rowcount == 0:
                    return {'success': False, 'message': 'IP bloğu bulunamadı.'}
            return {'success': True, 'message': 'IP bloğu silindi.'}
        finally:
            self._db._put_conn(conn)

    def assign_ip(self, block_id: int, ip_address: str,
                  assigned_to: str = '', mac_address: str = '',
                  note: str = '') -> dict:
        """IP adresi tahsis eder."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''INSERT INTO ipam_assignments
                       (block_id, ip_address, assigned_to, mac_address, note)
                       VALUES (%s, %s, %s, %s, %s) RETURNING id''',
                    (int(block_id), ip_address, assigned_to, mac_address, note))
                conn.commit()
            return {'success': True, 'message': f'IP {ip_address} tahsis edildi.'}
        except Exception as e:
            conn.rollback()
            if 'unique' in str(e).lower():
                return {'success': False, 'message': 'Bu IP zaten tahsis edilmiş.'}
            logger.error('IP tahsis hatası: %s', e)
            return {'success': False, 'message': 'IP tahsisi başarısız.'}
        finally:
            self._db._put_conn(conn)

    def release_ip(self, ip_address: str) -> dict:
        """IP tahsisini serbest bırakır."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM ipam_assignments WHERE ip_address = %s',
                            (ip_address,))
                conn.commit()
                if cur.rowcount == 0:
                    return {'success': False, 'message': 'IP tahsisi bulunamadı.'}
            return {'success': True, 'message': f'IP {ip_address} serbest bırakıldı.'}
        finally:
            self._db._put_conn(conn)

    def list_ipam_assignments(self, block_id: int) -> list:
        """Blok'taki IP tahsislerini listeler."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    '''SELECT id, ip_address, assigned_to, mac_address,
                       status, note, created_at
                       FROM ipam_assignments WHERE block_id = %s
                       ORDER BY ip_address''', (int(block_id),))
                rows = cur.fetchall()
            return [
                {'id': r[0], 'ip_address': r[1], 'assigned_to': r[2],
                 'mac_address': r[3], 'status': r[4], 'note': r[5],
                 'created_at': r[6].isoformat() if hasattr(r[6], 'isoformat') else str(r[6])}
                for r in rows
            ]
        finally:
            self._db._put_conn(conn)

    # ── ISP Dashboard / Raporlama ──

    def get_isp_dashboard(self) -> dict:
        """ISP geneli özet istatistikler."""
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT COUNT(*) FROM tenants WHERE active = TRUE')
                total_tenants = cur.fetchone()[0]
                cur.execute('SELECT COUNT(*) FROM tenant_servers WHERE active = TRUE')
                total_servers = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM alerts WHERE acknowledged = FALSE")
                pending_alerts = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM bulk_jobs WHERE status = 'running'")
                running_jobs = cur.fetchone()[0]
                cur.execute("""
                    SELECT plan, COUNT(*) FROM tenants WHERE active = TRUE
                    GROUP BY plan ORDER BY plan""")
                plans = {r[0]: r[1] for r in cur.fetchall()}
                cur.execute("""
                    SELECT COUNT(*) FROM audit_logs
                    WHERE ts > NOW() - INTERVAL '24 hours'""")
                audit_24h = cur.fetchone()[0]
                cur.execute('SELECT COUNT(*) FROM cgnat_mappings')
                cgnat_active = cur.fetchone()[0]
                cur.execute('SELECT COUNT(*) FROM ipam_assignments')
                ipam_assigned = cur.fetchone()[0]
            return {
                'total_tenants': total_tenants,
                'total_servers': total_servers,
                'pending_alerts': pending_alerts,
                'running_jobs': running_jobs,
                'plans': plans,
                'audit_last_24h': audit_24h,
                'cgnat_active_mappings': cgnat_active,
                'ipam_assigned_ips': ipam_assigned,
            }
        finally:
            self._db._put_conn(conn)

    def get_tenant_report(self, tenant_id: int) -> dict:
        """Tenant bazlı detaylı rapor."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return None
        conn = self._db._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT COUNT(*) FROM tenant_servers WHERE tenant_id = %s AND active = TRUE',
                    (int(tenant_id),))
                server_count = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM alerts WHERE tenant_id = %s AND acknowledged = FALSE",
                    (int(tenant_id),))
                pending_alerts = cur.fetchone()[0]
                cur.execute(
                    """SELECT COUNT(*) FROM audit_logs
                       WHERE tenant_id = %s AND ts > NOW() - INTERVAL '24 hours'""",
                    (int(tenant_id),))
                audit_24h = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM webhooks WHERE tenant_id = %s AND active = TRUE",
                    (int(tenant_id),))
                active_webhooks = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM scheduled_tasks WHERE tenant_id = %s AND active = TRUE",
                    (int(tenant_id),))
                active_tasks = cur.fetchone()[0]
            return {
                'tenant': tenant,
                'server_count': server_count,
                'pending_alerts': pending_alerts,
                'audit_last_24h': audit_24h,
                'active_webhooks': active_webhooks,
                'active_scheduled_tasks': active_tasks,
                'quota_usage': {
                    'servers': f'{server_count}/{tenant["max_servers"]}',
                    'servers_pct': round(server_count / max(tenant['max_servers'], 1) * 100, 1),
                },
            }
        finally:
            self._db._put_conn(conn)


# ═══════════════════ WEBHOOK DİSPATCHER ═══════════════════

class WebhookDispatcher:
    """Asenkron webhook tetikleme — arka plan thread'inde çalışır."""

    def __init__(self, tenant_store: TenantStore):
        self._store = tenant_store
        self._queue = []
        self._lock = threading.Lock()

    def trigger(self, tenant_id: int, event: str, data: dict):
        """Webhook'u arka planda tetikler."""
        if not self._store:
            return
        t = threading.Thread(
            target=self._dispatch, args=(tenant_id, event, data),
            daemon=True)
        t.start()

    def _dispatch(self, tenant_id: int, event: str, data: dict):
        """Webhook'ları çağırır (retry ile)."""
        import urllib.request
        import hmac as _hmac

        hooks = self._store.get_webhooks_for_event(tenant_id, event)
        for hook in hooks:
            payload = json.dumps({
                'event': event,
                'tenant_id': tenant_id,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'data': data,
            }, ensure_ascii=False).encode()

            signature = _hmac.new(
                hook['secret'].encode(), payload, hashlib.sha256
            ).hexdigest()

            req = urllib.request.Request(
                hook['url'], data=payload,
                headers={
                    'Content-Type': 'application/json',
                    'X-EFW-Signature': signature,
                    'X-EFW-Event': event,
                },
                method='POST')

            success = False
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        if resp.status < 400:
                            success = True
                            break
                except Exception as e:
                    logger.warning('Webhook %s denemesi %d başarısız: %s',
                                   hook['url'], attempt + 1, e)
                    time.sleep(2 ** attempt)  # exponential backoff

            self._store.update_webhook_status(hook['id'], success)


# ═══════════════════ DictTenantStore (Mock / Standalone) ═══════════════════

class DictTenantStore:
    """In-memory tenant store — demo/test için. Standalone modda kullanılır."""

    def __init__(self):
        self._tenants = {}
        self._servers = {}
        self._audits = []
        self._webhooks = {}
        self._scheduled = {}
        self._bulk_jobs = {}
        self._alerts = {}
        self._cgnat_pools = {}
        self._cgnat_mappings = {}
        self._ipam_blocks = {}
        self._ipam_assignments = {}
        self._counter = 0
        self._lock = threading.Lock()

    def init(self):
        """Demo veri yükle."""
        self._db = None  # WebhookDispatcher uyumluluğu

    def _next_id(self):
        with self._lock:
            self._counter += 1
            return self._counter

    def create_tenant(self, name, email='', plan='bronze'):
        if not _VALID_TENANT_NAME_RE.match(name.strip()):
            return {'success': False, 'message': 'Geçersiz tenant adı.'}
        if plan not in PLAN_LIMITS:
            return {'success': False, 'message': 'Geçersiz plan.'}
        limits = PLAN_LIMITS[plan]
        api_key = _generate_api_key()
        tid = self._next_id()
        self._tenants[tid] = {
            'id': tid, 'name': name.strip(), 'email': email,
            'plan': plan, 'api_key_hash': _hash_api_key(api_key),
            'api_key_prefix': api_key[:12], 'active': True,
            'max_servers': limits['max_servers'],
            'max_rules': limits['max_rules'],
            'rate_limit': limits['rate_limit'],
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
            'metadata': {},
        }
        return {'success': True, 'tenant': {**self._tenants[tid], 'api_key': api_key},
                'message': 'Tenant oluşturuldu.'}

    def list_tenants(self, active_only=True):
        return [t for t in self._tenants.values()
                if not active_only or t['active']]

    def get_tenant(self, tenant_id):
        return self._tenants.get(int(tenant_id))

    def update_tenant(self, tenant_id, **fields):
        t = self._tenants.get(int(tenant_id))
        if not t:
            return {'success': False, 'message': 'Tenant bulunamadı.'}
        allowed = {'name', 'email', 'plan', 'active', 'metadata'}
        for k, v in fields.items():
            if k in allowed:
                t[k] = v
                if k == 'plan' and v in PLAN_LIMITS:
                    for lk, lv in PLAN_LIMITS[v].items():
                        t[lk] = lv
        t['updated_at'] = datetime.now(timezone.utc).isoformat()
        return {'success': True, 'message': 'Tenant güncellendi.'}

    def delete_tenant(self, tenant_id):
        if int(tenant_id) in self._tenants:
            del self._tenants[int(tenant_id)]
            return {'success': True, 'message': 'Tenant silindi.'}
        return {'success': False, 'message': 'Tenant bulunamadı.'}

    def regenerate_api_key(self, tenant_id):
        t = self._tenants.get(int(tenant_id))
        if not t:
            return {'success': False, 'message': 'Tenant bulunamadı.'}
        api_key = _generate_api_key()
        t['api_key_hash'] = _hash_api_key(api_key)
        t['api_key_prefix'] = api_key[:12]
        return {'success': True, 'api_key': api_key, 'message': 'Yeni API key üretildi.'}

    def authenticate_by_key(self, api_key):
        if not api_key:
            return None
        key_hash = _hash_api_key(api_key)
        for t in self._tenants.values():
            if t['api_key_hash'] == key_hash and t['active']:
                return {'id': t['id'], 'name': t['name'], 'plan': t['plan'],
                        'max_servers': t['max_servers'],
                        'max_rules': t['max_rules'],
                        'rate_limit': t['rate_limit']}
        return None

    def add_server(self, tenant_id, server_id, ssh_host, ssh_user='root',
                   ssh_port=22, ssh_key_ref='', label=''):
        t = self._tenants.get(int(tenant_id))
        if not t:
            return {'success': False, 'message': 'Tenant bulunamadı.'}
        key = (int(tenant_id), server_id)
        if key in self._servers:
            return {'success': False, 'message': 'Sunucu zaten atanmış.'}
        cur = [s for k, s in self._servers.items() if k[0] == int(tenant_id)]
        if len(cur) >= t['max_servers']:
            return {'success': False, 'message': 'Kota doldu.'}
        self._servers[key] = {
            'server_id': server_id, 'label': label, 'ssh_host': ssh_host,
            'ssh_user': ssh_user, 'ssh_port': ssh_port, 'active': True,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        return {'success': True, 'message': f'Sunucu {server_id} eklendi.'}

    def list_servers(self, tenant_id):
        return [s for k, s in self._servers.items() if k[0] == int(tenant_id)]

    def remove_server(self, tenant_id, server_id):
        key = (int(tenant_id), server_id)
        if key in self._servers:
            del self._servers[key]
            return {'success': True, 'message': 'Sunucu kaldırıldı.'}
        return {'success': False, 'message': 'Sunucu bulunamadı.'}

    def is_server_allowed(self, tenant_id, server_id):
        return (int(tenant_id), server_id) in self._servers

    def add_audit(self, tenant_id, action, user_ip='', resource_type='',
                  resource_id='', details=None, success=True):
        self._audits.append({
            'id': self._next_id(),
            'ts': datetime.now(timezone.utc).isoformat(),
            'tenant_id': int(tenant_id), 'user_ip': user_ip,
            'action': action, 'resource_type': resource_type,
            'resource_id': resource_id, 'details': details or {},
            'success': success,
        })
        if len(self._audits) > 10000:
            self._audits = self._audits[-5000:]

    def query_audit(self, tenant_id=None, limit=100, action='', since_ts=''):
        results = self._audits[:]
        if tenant_id is not None:
            results = [a for a in results if a['tenant_id'] == int(tenant_id)]
        if action:
            results = [a for a in results if a['action'] == action]
        results.reverse()
        return results[:min(int(limit), 500)]

    # Webhook (in-memory)
    def add_webhook(self, tenant_id, url, events, secret=''):
        wid = self._next_id()
        self._webhooks[wid] = {
            'id': wid, 'tenant_id': int(tenant_id), 'url': url,
            'events': events, 'secret': secret or secrets.token_hex(32),
            'active': True, 'fail_count': 0,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'last_triggered': None,
        }
        return {'success': True, 'webhook_id': wid,
                'secret': self._webhooks[wid]['secret'],
                'message': 'Webhook eklendi.'}

    def list_webhooks(self, tenant_id):
        return [w for w in self._webhooks.values()
                if w['tenant_id'] == int(tenant_id)]

    def remove_webhook(self, tenant_id, webhook_id):
        w = self._webhooks.get(int(webhook_id))
        if w and w['tenant_id'] == int(tenant_id):
            del self._webhooks[int(webhook_id)]
            return {'success': True, 'message': 'Webhook silindi.'}
        return {'success': False, 'message': 'Webhook bulunamadı.'}

    def get_webhooks_for_event(self, tenant_id, event):
        return [{'id': w['id'], 'url': w['url'], 'secret': w['secret']}
                for w in self._webhooks.values()
                if w['tenant_id'] == int(tenant_id) and w['active']
                and event in w['events']]

    def update_webhook_status(self, webhook_id, success):
        w = self._webhooks.get(int(webhook_id))
        if w:
            if success:
                w['fail_count'] = 0
                w['last_triggered'] = datetime.now(timezone.utc).isoformat()
            else:
                w['fail_count'] += 1
                if w['fail_count'] >= 10:
                    w['active'] = False

    # Alert (in-memory)
    def add_alert(self, tenant_id, alert_type, message, server_id='',
                  severity='warning', details=None):
        aid = self._next_id()
        self._alerts[aid] = {
            'id': aid, 'tenant_id': int(tenant_id),
            'alert_type': alert_type, 'server_id': server_id,
            'severity': severity, 'message': message,
            'details': details or {}, 'acknowledged': False,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        return aid

    def list_alerts(self, tenant_id, limit=50, unacknowledged_only=False):
        alerts = [a for a in self._alerts.values()
                  if a['tenant_id'] == int(tenant_id)]
        if unacknowledged_only:
            alerts = [a for a in alerts if not a['acknowledged']]
        alerts.sort(key=lambda x: x['id'], reverse=True)
        return alerts[:min(int(limit), 200)]

    def acknowledge_alert(self, tenant_id, alert_id):
        a = self._alerts.get(int(alert_id))
        if a and a['tenant_id'] == int(tenant_id):
            a['acknowledged'] = True
            return {'success': True, 'message': 'Alert onaylandı.'}
        return {'success': False, 'message': 'Alert bulunamadı.'}

    # Scheduled Task (in-memory)
    def add_scheduled_task(self, tenant_id, task_type, cron_expr,
                           server_id='', payload=None):
        valid_tasks = {'backup', 'security_scan', 'l7_scan', 'rule_apply',
                       'rule_remove', 'log_cleanup'}
        if task_type not in valid_tasks:
            return {'success': False, 'message': 'Geçersiz görev tipi.'}
        if len(cron_expr.strip().split()) != 5:
            return {'success': False, 'message': 'Cron ifadesi 5 alanlı olmalı.'}
        tid = self._next_id()
        self._scheduled[tid] = {
            'id': tid, 'tenant_id': int(tenant_id), 'task_type': task_type,
            'server_id': server_id, 'cron_expr': cron_expr, 'active': True,
            'last_run': None, 'next_run': None,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        return {'success': True, 'task_id': tid, 'message': 'Görev oluşturuldu.'}

    def list_scheduled_tasks(self, tenant_id):
        return [t for t in self._scheduled.values()
                if t['tenant_id'] == int(tenant_id)]

    def remove_scheduled_task(self, tenant_id, task_id):
        t = self._scheduled.get(int(task_id))
        if t and t['tenant_id'] == int(tenant_id):
            del self._scheduled[int(task_id)]
            return {'success': True, 'message': 'Görev silindi.'}
        return {'success': False, 'message': 'Görev bulunamadı.'}

    # Bulk Job (in-memory)
    def create_bulk_job(self, tenant_id, job_type, total, payload=None):
        jid = self._next_id()
        self._bulk_jobs[jid] = {
            'id': jid, 'tenant_id': int(tenant_id), 'job_type': job_type,
            'status': 'running', 'total': total, 'completed': 0,
            'failed': 0, 'results': [], 'payload': payload or {},
            'created_at': datetime.now(timezone.utc).isoformat(),
            'finished_at': None,
        }
        return jid

    def update_bulk_job(self, job_id, completed=0, failed=0,
                        results=None, status=None):
        j = self._bulk_jobs.get(int(job_id))
        if j:
            j['completed'] = completed
            j['failed'] = failed
            if results is not None:
                j['results'] = results
            if status:
                j['status'] = status
                if status in ('completed', 'failed'):
                    j['finished_at'] = datetime.now(timezone.utc).isoformat()

    def get_bulk_job(self, job_id):
        return self._bulk_jobs.get(int(job_id))

    def list_bulk_jobs(self, tenant_id, limit=20):
        jobs = [j for j in self._bulk_jobs.values()
                if j['tenant_id'] == int(tenant_id)]
        jobs.sort(key=lambda x: x['id'], reverse=True)
        return jobs[:min(int(limit), 100)]

    # CGNAT (in-memory)
    def add_cgnat_pool(self, tenant_id, pool_name, public_ip,
                       port_start=1024, port_end=65535,
                       ports_per_subscriber=1024):
        for p in self._cgnat_pools.values():
            if p['pool_name'] == pool_name:
                return {'success': False, 'message': 'Havuz adı mevcut.'}
        pid = self._next_id()
        self._cgnat_pools[pid] = {
            'id': pid, 'tenant_id': int(tenant_id),
            'pool_name': pool_name, 'public_ip': public_ip,
            'port_start': port_start, 'port_end': port_end,
            'ports_per_subscriber': ports_per_subscriber, 'active': True,
        }
        return {'success': True, 'pool_id': pid, 'message': 'CGNAT havuzu oluşturuldu.'}

    def list_cgnat_pools(self, tenant_id):
        pools = [p for p in self._cgnat_pools.values()
                 if p['tenant_id'] == int(tenant_id)]
        for p in pools:
            mappings = [m for m in self._cgnat_mappings.values()
                        if m['pool_id'] == p['id']]
            p['mapping_count'] = len(mappings)
            p['capacity'] = (p['port_end'] - p['port_start'] + 1) // p['ports_per_subscriber']
        return pools

    def allocate_cgnat(self, pool_id, subscriber_ip):
        pool = self._cgnat_pools.get(int(pool_id))
        if not pool or not pool['active']:
            return {'success': False, 'message': 'Havuz bulunamadı.'}
        for m in self._cgnat_mappings.values():
            if m['pool_id'] == int(pool_id) and m['subscriber_ip'] == subscriber_ip:
                return {'success': True, 'already_allocated': True, 'mapping': m}
        mappings = [m for m in self._cgnat_mappings.values()
                    if m['pool_id'] == int(pool_id)]
        count = len(mappings)
        pps = pool['ports_per_subscriber']
        total_slots = (pool['port_end'] - pool['port_start'] + 1) // pps
        if count >= total_slots:
            return {'success': False, 'message': 'Havuz kapasitesi doldu.'}
        ps = pool['port_start'] + (count * pps)
        pe = ps + pps - 1
        mid = self._next_id()
        self._cgnat_mappings[mid] = {
            'id': mid, 'pool_id': int(pool_id), 'subscriber_ip': subscriber_ip,
            'public_ip': pool['public_ip'], 'port_start': ps, 'port_end': pe,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        return {'success': True, 'mapping': self._cgnat_mappings[mid]}

    def release_cgnat(self, pool_id, subscriber_ip):
        for mid, m in list(self._cgnat_mappings.items()):
            if m['pool_id'] == int(pool_id) and m['subscriber_ip'] == subscriber_ip:
                del self._cgnat_mappings[mid]
                return {'success': True, 'message': 'Tahsis serbest bırakıldı.'}
        return {'success': False, 'message': 'Tahsis bulunamadı.'}

    def list_cgnat_mappings(self, pool_id):
        return sorted(
            [m for m in self._cgnat_mappings.values()
             if m['pool_id'] == int(pool_id)],
            key=lambda x: x['port_start'])

    # IPAM (in-memory)
    def add_ipam_block(self, tenant_id, cidr, description='',
                       block_type='assigned', vlan=None, gateway=''):
        for b in self._ipam_blocks.values():
            if b['cidr'] == cidr:
                return {'success': False, 'message': 'CIDR zaten kayıtlı.'}
        bid = self._next_id()
        self._ipam_blocks[bid] = {
            'id': bid, 'tenant_id': int(tenant_id), 'cidr': cidr,
            'description': description, 'block_type': block_type,
            'vlan': vlan, 'gateway': gateway,
        }
        return {'success': True, 'block_id': bid, 'message': 'IP bloğu eklendi.'}

    def list_ipam_blocks(self, tenant_id):
        blocks = [b.copy() for b in self._ipam_blocks.values()
                  if b['tenant_id'] == int(tenant_id)]
        for b in blocks:
            b['assigned_count'] = len([a for a in self._ipam_assignments.values()
                                       if a['block_id'] == b['id']])
        return blocks

    def remove_ipam_block(self, tenant_id, block_id):
        b = self._ipam_blocks.get(int(block_id))
        if b and b['tenant_id'] == int(tenant_id):
            del self._ipam_blocks[int(block_id)]
            return {'success': True, 'message': 'IP bloğu silindi.'}
        return {'success': False, 'message': 'IP bloğu bulunamadı.'}

    def assign_ip(self, block_id, ip_address, assigned_to='',
                  mac_address='', note=''):
        for a in self._ipam_assignments.values():
            if a['ip_address'] == ip_address:
                return {'success': False, 'message': 'IP zaten tahsisli.'}
        aid = self._next_id()
        self._ipam_assignments[aid] = {
            'id': aid, 'block_id': int(block_id), 'ip_address': ip_address,
            'assigned_to': assigned_to, 'mac_address': mac_address,
            'status': 'assigned', 'note': note,
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        return {'success': True, 'message': f'IP {ip_address} tahsis edildi.'}

    def release_ip(self, ip_address):
        for aid, a in list(self._ipam_assignments.items()):
            if a['ip_address'] == ip_address:
                del self._ipam_assignments[aid]
                return {'success': True, 'message': 'IP serbest bırakıldı.'}
        return {'success': False, 'message': 'IP bulunamadı.'}

    def list_ipam_assignments(self, block_id):
        return sorted(
            [a for a in self._ipam_assignments.values()
             if a['block_id'] == int(block_id)],
            key=lambda x: x['ip_address'])

    # Dashboard (in-memory)
    def get_isp_dashboard(self):
        return {
            'total_tenants': len([t for t in self._tenants.values() if t['active']]),
            'total_servers': len(self._servers),
            'pending_alerts': len([a for a in self._alerts.values() if not a['acknowledged']]),
            'running_jobs': len([j for j in self._bulk_jobs.values() if j['status'] == 'running']),
            'plans': {},
            'audit_last_24h': len(self._audits),
            'cgnat_active_mappings': len(self._cgnat_mappings),
            'ipam_assigned_ips': len(self._ipam_assignments),
        }

    def get_tenant_report(self, tenant_id):
        t = self.get_tenant(tenant_id)
        if not t:
            return None
        servers = self.list_servers(tenant_id)
        return {
            'tenant': t, 'server_count': len(servers),
            'pending_alerts': len([a for a in self._alerts.values()
                                   if a['tenant_id'] == int(tenant_id) and not a['acknowledged']]),
            'audit_last_24h': len([a for a in self._audits
                                   if a['tenant_id'] == int(tenant_id)]),
            'active_webhooks': len([w for w in self._webhooks.values()
                                    if w['tenant_id'] == int(tenant_id) and w['active']]),
            'active_scheduled_tasks': len([s for s in self._scheduled.values()
                                           if s['tenant_id'] == int(tenant_id) and s['active']]),
            'quota_usage': {
                'servers': f'{len(servers)}/{t["max_servers"]}',
                'servers_pct': round(len(servers) / max(t['max_servers'], 1) * 100, 1),
            },
        }


def create_tenant_store(db_backend=None) -> 'TenantStore | DictTenantStore':
    """Yapılandırmaya göre TenantStore oluştur."""
    if db_backend is not None:
        store = TenantStore(db_backend=db_backend)
        store.init()
        return store
    return DictTenantStore()
