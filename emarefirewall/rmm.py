"""
Emare Security OS — RMM + ITSM Modülü
================================

Bağımsız Uzaktan İzleme ve Yönetim (RMM) + IT Servis Yönetimi (ITSM).
Dış bağımlılık yok — sadece Python stdlib (sqlite3, json, threading).
Symon (Windows), Linux ve macOS agent'larıyla uyumlu HTTP JSON API.

Agent Protokolü:
    POST /api/rmm/agent/register    → {hostname, os_type, os_version, ...}
    POST /api/rmm/agent/heartbeat   → {cpu, ram, disk, net_in, net_out, ...}
    GET  /api/rmm/agent/tasks       → [{id, task_type, payload}, ...]
    POST /api/rmm/agent/task-result → {task_id, success, result}

Symon Windows Agent Uyumluluğu:
    - Pure HTTP/HTTPS JSON API (platform bağımsız)
    - Agent key ile kimlik doğrulama (X-Agent-Key header)
    - Polling tabanlı görev dağıtımı (agent çeker, server pushlama yapmaz)
    - Standart REST — herhangi bir dil/framework ile agent yazılabilir
"""

import json
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional


class RMMStore:
    """SQLite tabanlı RMM + ITSM veri deposu. Sıfır dış bağımlılık."""

    VALID_TASK_TYPES = (
        'shell_exec', 'powershell_exec', 'file_collect', 'update_agent',
        'restart_service', 'install_software', 'uninstall_software',
        'registry_query', 'event_log', 'sysinfo_collect', 'sysmon_collect',
        'custom',
    )
    VALID_PRIORITIES = ('critical', 'high', 'medium', 'low')
    VALID_TICKET_STATUSES = ('open', 'in_progress', 'resolved', 'closed')

    def __init__(self, db_path: str = 'data/rmm.db'):
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None

    def init(self):
        self._conn = sqlite3.connect(
            self._db_path, check_same_thread=False, timeout=10)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")

        self._conn.execute('''CREATE TABLE IF NOT EXISTS devices (
            id TEXT PRIMARY KEY,
            agent_key TEXT UNIQUE NOT NULL,
            hostname TEXT NOT NULL,
            os_type TEXT DEFAULT '',
            os_version TEXT DEFAULT '',
            ip_address TEXT DEFAULT '',
            agent_version TEXT DEFAULT '',
            status TEXT DEFAULT 'offline',
            last_heartbeat TEXT DEFAULT '',
            cpu_usage REAL DEFAULT 0,
            ram_usage REAL DEFAULT 0,
            disk_usage REAL DEFAULT 0,
            tags TEXT DEFAULT '[]',
            extra TEXT DEFAULT '{}',
            tenant_id TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )''')

        self._conn.execute('''CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            device_id TEXT NOT NULL,
            task_type TEXT NOT NULL,
            payload TEXT DEFAULT '{}',
            status TEXT DEFAULT 'pending',
            result TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            completed_at TEXT DEFAULT '',
            FOREIGN KEY (device_id) REFERENCES devices(id)
        )''')

        self._conn.execute('''CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            ts TEXT NOT NULL,
            cpu REAL DEFAULT 0,
            ram REAL DEFAULT 0,
            disk REAL DEFAULT 0,
            net_in INTEGER DEFAULT 0,
            net_out INTEGER DEFAULT 0,
            custom TEXT DEFAULT '{}',
            FOREIGN KEY (device_id) REFERENCES devices(id)
        )''')

        self._conn.execute('''CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            priority TEXT DEFAULT 'medium',
            status TEXT DEFAULT 'open',
            category TEXT DEFAULT 'general',
            device_id TEXT DEFAULT '',
            assignee TEXT DEFAULT '',
            created_by TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            notes TEXT DEFAULT '[]'
        )''')

        self._conn.execute('''CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            threshold REAL NOT NULL,
            current_value REAL NOT NULL,
            message TEXT DEFAULT '',
            severity TEXT DEFAULT 'warning',
            acknowledged INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (device_id) REFERENCES devices(id)
        )''')

        self._conn.execute('''CREATE TABLE IF NOT EXISTS alert_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            cpu_warning REAL DEFAULT 80,
            cpu_critical REAL DEFAULT 95,
            ram_warning REAL DEFAULT 80,
            ram_critical REAL DEFAULT 95,
            disk_warning REAL DEFAULT 85,
            disk_critical REAL DEFAULT 95,
            enabled INTEGER DEFAULT 1,
            cooldown_minutes INTEGER DEFAULT 30,
            auto_ticket INTEGER DEFAULT 0
        )''')

        self._conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_dev_status ON devices(status)')
        self._conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_task_dev ON tasks(device_id)')
        self._conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_task_status ON tasks(status)')
        self._conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_met_dev_ts ON metrics(device_id, ts)')
        self._conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_tkt_status ON tickets(status)')
        self._conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_tkt_priority ON tickets(priority)')
        self._conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_alert_dev ON alerts(device_id)')
        self._conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_alert_ack ON alerts(acknowledged)')
        # Schema migration — add columns if missing
        try:
            self._conn.execute('SELECT auto_ticket FROM alert_config LIMIT 0')
        except sqlite3.OperationalError:
            self._conn.execute(
                'ALTER TABLE alert_config ADD COLUMN auto_ticket INTEGER DEFAULT 0')

        # ── SIEM Tables ──

        self._conn.execute('''CREATE TABLE IF NOT EXISTS threat_intel (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            indicator TEXT NOT NULL,
            indicator_type TEXT DEFAULT 'ip',
            source TEXT DEFAULT 'manual',
            reputation TEXT DEFAULT 'unknown',
            tags TEXT DEFAULT '[]',
            raw_data TEXT DEFAULT '{}',
            first_seen TEXT NOT NULL,
            last_checked TEXT NOT NULL,
            expires_at TEXT DEFAULT ''
        )''')
        self._conn.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS idx_ti_indicator '
            'ON threat_intel(indicator, indicator_type)')

        self._conn.execute('''CREATE TABLE IF NOT EXISTS correlation_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            rule_type TEXT DEFAULT 'threshold',
            conditions TEXT DEFAULT '{}',
            severity TEXT DEFAULT 'warning',
            enabled INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        )''')

        self._conn.execute('''CREATE TABLE IF NOT EXISTS correlation_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id INTEGER NOT NULL,
            device_id TEXT DEFAULT '',
            details TEXT DEFAULT '{}',
            severity TEXT DEFAULT 'warning',
            mitre_tactic TEXT DEFAULT '',
            mitre_technique TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (rule_id) REFERENCES correlation_rules(id)
        )''')
        self._conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_ce_rule '
            'ON correlation_events(rule_id)')
        self._conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_ce_dev '
            'ON correlation_events(device_id)')

        self._conn.execute('''CREATE TABLE IF NOT EXISTS risk_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            score REAL DEFAULT 0,
            factors TEXT DEFAULT '[]',
            updated_at TEXT NOT NULL,
            FOREIGN KEY (device_id) REFERENCES devices(id)
        )''')
        self._conn.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS idx_rs_dev '
            'ON risk_scores(device_id)')

        self._conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── Device Management ──

    def register_device(self, hostname: str, os_type: str = '',
                        os_version: str = '', ip_address: str = '',
                        agent_version: str = '', tenant_id: str = '',
                        tags: list = None) -> dict:
        device_id = secrets.token_hex(8)
        agent_key = f"eak_{secrets.token_hex(24)}"
        now = self._now()
        with self._lock:
            self._conn.execute(
                '''INSERT INTO devices
                   (id, agent_key, hostname, os_type, os_version,
                    ip_address, agent_version, status, last_heartbeat,
                    tags, tenant_id, created_at)
                   VALUES (?,?,?,?,?,?,?,'online',?,?,?,?)''',
                (device_id, agent_key, hostname, os_type, os_version,
                 ip_address, agent_version, now,
                 json.dumps(tags or []), tenant_id, now))
            self._conn.commit()
        return {'id': device_id, 'agent_key': agent_key}

    def authenticate_agent(self, agent_key: str) -> Optional[dict]:
        if not agent_key or not agent_key.startswith('eak_'):
            return None
        row = self._conn.execute(
            'SELECT id, hostname, status FROM devices WHERE agent_key = ?',
            (agent_key,)).fetchone()
        if row:
            return {'id': row[0], 'hostname': row[1], 'status': row[2]}
        return None

    def heartbeat(self, device_id: str, cpu: float = 0, ram: float = 0,
                  disk: float = 0, net_in: int = 0, net_out: int = 0,
                  extra: dict = None) -> bool:
        now = self._now()
        extra_json = json.dumps(extra or {})
        with self._lock:
            self._conn.execute(
                '''UPDATE devices SET status='online', last_heartbeat=?,
                   cpu_usage=?, ram_usage=?, disk_usage=?, extra=? WHERE id=?''',
                (now, cpu, ram, disk, extra_json, device_id))
            self._conn.execute(
                '''INSERT INTO metrics
                   (device_id, ts, cpu, ram, disk, net_in, net_out, custom)
                   VALUES (?,?,?,?,?,?,?,?)''',
                (device_id, now, cpu, ram, disk, net_in, net_out, extra_json))
            self._conn.commit()
        self._check_thresholds(device_id, cpu, ram, disk)
        self.evaluate_correlation_rules(device_id)
        return True

    def list_devices(self, tenant_id: str = '', status: str = '') -> list:
        sql = 'SELECT * FROM devices WHERE 1=1'
        params: list = []
        if tenant_id:
            sql += ' AND tenant_id = ?'
            params.append(tenant_id)
        if status:
            sql += ' AND status = ?'
            params.append(status)
        sql += ' ORDER BY last_heartbeat DESC'
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            rows = self._conn.execute(sql, params).fetchall()
            self._conn.row_factory = None
        return [self._dev_dict(r) for r in rows]

    def get_device(self, device_id: str) -> Optional[dict]:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            row = self._conn.execute(
                'SELECT * FROM devices WHERE id = ?', (device_id,)
            ).fetchone()
            self._conn.row_factory = None
        return self._dev_dict(row) if row else None

    def remove_device(self, device_id: str) -> bool:
        with self._lock:
            self._conn.execute(
                'DELETE FROM metrics WHERE device_id = ?', (device_id,))
            self._conn.execute(
                'DELETE FROM tasks WHERE device_id = ?', (device_id,))
            self._conn.execute(
                'DELETE FROM devices WHERE id = ?', (device_id,))
            self._conn.commit()
        return True

    def update_statuses(self, timeout_minutes: int = 5):
        cutoff = (datetime.now(timezone.utc)
                  - timedelta(minutes=timeout_minutes)).isoformat()
        with self._lock:
            self._conn.execute(
                "UPDATE devices SET status='offline' "
                "WHERE last_heartbeat < ? AND status='online'", (cutoff,))
            self._conn.commit()

    def _dev_dict(self, row) -> dict:
        return {
            'id': row['id'], 'hostname': row['hostname'],
            'os_type': row['os_type'], 'os_version': row['os_version'],
            'ip_address': row['ip_address'],
            'agent_version': row['agent_version'],
            'status': row['status'],
            'last_heartbeat': row['last_heartbeat'],
            'cpu_usage': row['cpu_usage'], 'ram_usage': row['ram_usage'],
            'disk_usage': row['disk_usage'],
            'tags': json.loads(row['tags'] or '[]'),
            'extra': json.loads(row['extra'] or '{}'),
            'tenant_id': row['tenant_id'],
            'created_at': row['created_at'],
        }

    # ── Task Management ──

    def create_task(self, device_id: str, task_type: str,
                    payload: dict = None) -> str:
        task_id = secrets.token_hex(8)
        with self._lock:
            self._conn.execute(
                '''INSERT INTO tasks
                   (id, device_id, task_type, payload, status, created_at)
                   VALUES (?,?,?,?,'pending',?)''',
                (task_id, device_id, task_type,
                 json.dumps(payload or {}), self._now()))
            self._conn.commit()
        return task_id

    def get_pending_tasks(self, device_id: str) -> list:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            rows = self._conn.execute(
                "SELECT * FROM tasks "
                "WHERE device_id = ? AND status = 'pending' "
                "ORDER BY created_at", (device_id,)).fetchall()
            self._conn.row_factory = None
            for r in rows:
                self._conn.execute(
                    "UPDATE tasks SET status='running' WHERE id=?",
                    (r['id'],))
            self._conn.commit()
        return [self._task_dict(r) for r in rows]

    def complete_task(self, task_id: str, result: str = '',
                      success: bool = True) -> bool:
        st = 'completed' if success else 'failed'
        with self._lock:
            self._conn.execute(
                'UPDATE tasks SET status=?, result=?, completed_at=? '
                'WHERE id=?', (st, result, self._now(), task_id))
            self._conn.commit()
        return True

    def list_tasks(self, device_id: str = '', status: str = '',
                   limit: int = 50) -> list:
        sql = 'SELECT * FROM tasks WHERE 1=1'
        params: list = []
        if device_id:
            sql += ' AND device_id = ?'
            params.append(device_id)
        if status:
            sql += ' AND status = ?'
            params.append(status)
        sql += ' ORDER BY created_at DESC LIMIT ?'
        params.append(limit)
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            rows = self._conn.execute(sql, params).fetchall()
            self._conn.row_factory = None
        return [self._task_dict(r) for r in rows]

    def _task_dict(self, row) -> dict:
        return {
            'id': row['id'], 'device_id': row['device_id'],
            'task_type': row['task_type'],
            'payload': json.loads(row['payload'] or '{}'),
            'status': row['status'], 'result': row['result'],
            'created_at': row['created_at'],
            'completed_at': row['completed_at'],
        }

    # ── Metrics ──

    def get_metrics(self, device_id: str, hours: int = 24,
                    limit: int = 200) -> list:
        since = (datetime.now(timezone.utc)
                 - timedelta(hours=hours)).isoformat()
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            rows = self._conn.execute(
                'SELECT * FROM metrics WHERE device_id = ? AND ts > ? '
                'ORDER BY ts DESC LIMIT ?',
                (device_id, since, limit)).fetchall()
            self._conn.row_factory = None
        return [{'ts': r['ts'], 'cpu': r['cpu'], 'ram': r['ram'],
                 'disk': r['disk'], 'net_in': r['net_in'],
                 'net_out': r['net_out'],
                 'custom': json.loads(r['custom'] or '{}')}
                for r in reversed(rows)]

    def cleanup_metrics(self, days: int = 30):
        cutoff = (datetime.now(timezone.utc)
                  - timedelta(days=days)).isoformat()
        with self._lock:
            self._conn.execute(
                'DELETE FROM metrics WHERE ts < ?', (cutoff,))
            self._conn.commit()

    # ── ITSM Tickets ──

    def create_ticket(self, title: str, description: str = '',
                      priority: str = 'medium', category: str = 'general',
                      device_id: str = '', assignee: str = '',
                      created_by: str = '') -> int:
        now = self._now()
        with self._lock:
            cur = self._conn.execute(
                '''INSERT INTO tickets
                   (title, description, priority, status, category,
                    device_id, assignee, created_by, created_at,
                    updated_at, notes)
                   VALUES (?,?,?,'open',?,?,?,?,?,?,'[]')''',
                (title, description, priority, category,
                 device_id, assignee, created_by, now, now))
            self._conn.commit()
            return cur.lastrowid

    def list_tickets(self, status: str = '', priority: str = '',
                     category: str = '', limit: int = 50) -> list:
        sql = 'SELECT * FROM tickets WHERE 1=1'
        params: list = []
        if status:
            sql += ' AND status = ?'
            params.append(status)
        if priority:
            sql += ' AND priority = ?'
            params.append(priority)
        if category:
            sql += ' AND category = ?'
            params.append(category)
        sql += ' ORDER BY id DESC LIMIT ?'
        params.append(limit)
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            rows = self._conn.execute(sql, params).fetchall()
            self._conn.row_factory = None
        return [self._tkt_dict(r) for r in rows]

    def get_ticket(self, ticket_id: int) -> Optional[dict]:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            row = self._conn.execute(
                'SELECT * FROM tickets WHERE id = ?', (ticket_id,)
            ).fetchone()
            self._conn.row_factory = None
        return self._tkt_dict(row) if row else None

    def update_ticket(self, ticket_id: int, status: str = '',
                      assignee: str = None, note: str = '',
                      added_by: str = '') -> bool:
        now = self._now()
        ticket = self.get_ticket(ticket_id)
        if not ticket:
            return False
        updates = ['updated_at = ?']
        params: list = [now]
        if status and status in self.VALID_TICKET_STATUSES:
            updates.append('status = ?')
            params.append(status)
        if assignee is not None:
            updates.append('assignee = ?')
            params.append(assignee)
        if note:
            notes = ticket.get('notes', [])
            notes.append({'text': note, 'by': added_by, 'ts': now})
            updates.append('notes = ?')
            params.append(json.dumps(notes, ensure_ascii=False))
        params.append(ticket_id)
        with self._lock:
            self._conn.execute(
                f"UPDATE tickets SET {', '.join(updates)} WHERE id = ?",
                params)
            self._conn.commit()
        return True

    def ticket_stats(self) -> dict:
        stats = {}
        with self._lock:
            for s in self.VALID_TICKET_STATUSES:
                stats[s] = self._conn.execute(
                    'SELECT COUNT(*) FROM tickets WHERE status = ?',
                    (s,)).fetchone()[0]
        stats['total'] = sum(stats.values())
        return stats

    def _tkt_dict(self, row) -> dict:
        return {
            'id': row['id'], 'title': row['title'],
            'description': row['description'],
            'priority': row['priority'], 'status': row['status'],
            'category': row['category'], 'device_id': row['device_id'],
            'assignee': row['assignee'], 'created_by': row['created_by'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
            'notes': json.loads(row['notes'] or '[]'),
        }

    # ── Dashboard ──

    def dashboard(self) -> dict:
        with self._lock:
            total = self._conn.execute(
                'SELECT COUNT(*) FROM devices').fetchone()[0]
            online = self._conn.execute(
                "SELECT COUNT(*) FROM devices WHERE status='online'"
            ).fetchone()[0]
            os_dist = {}
            for row in self._conn.execute(
                'SELECT os_type, COUNT(*) FROM devices GROUP BY os_type'
            ).fetchall():
                os_dist[row[0] or 'unknown'] = row[1]
            pending = self._conn.execute(
                "SELECT COUNT(*) FROM tasks "
                "WHERE status IN ('pending','running')").fetchone()[0]
        return {
            'devices': {
                'total': total, 'online': online,
                'offline': total - online,
            },
            'os_distribution': os_dist,
            'tickets': self.ticket_stats(),
            'pending_tasks': pending,
        }

    # ── Alerts ──

    def _check_thresholds(self, device_id: str, cpu: float,
                          ram: float, disk: float):
        """Heartbeat sonrası eşik kontrolü — gerekirse alarm oluşturur."""
        config = self.get_alert_config()
        if not config.get('enabled', True):
            return
        cooldown = config.get('cooldown_minutes', 30)
        cutoff = (datetime.now(timezone.utc)
                  - timedelta(minutes=cooldown)).isoformat()
        checks = [
            ('cpu', cpu, config.get('cpu_warning', 80),
             config.get('cpu_critical', 95)),
            ('ram', ram, config.get('ram_warning', 80),
             config.get('ram_critical', 95)),
            ('disk', disk, config.get('disk_warning', 85),
             config.get('disk_critical', 95)),
        ]
        labels = {'cpu': 'CPU', 'ram': 'RAM', 'disk': 'Disk'}
        with self._lock:
            for metric, value, warn_t, crit_t in checks:
                if value >= crit_t:
                    severity, threshold = 'critical', crit_t
                elif value >= warn_t:
                    severity, threshold = 'warning', warn_t
                else:
                    continue
                existing = self._conn.execute(
                    "SELECT id FROM alerts WHERE device_id=? AND "
                    "alert_type=? AND created_at>? AND acknowledged=0",
                    (device_id, metric, cutoff)).fetchone()
                if existing:
                    continue
                now = self._now()
                msg = (f"{labels[metric]} kullanımı %{value:.1f} "
                       f"(eşik: %{threshold:.0f})")
                self._conn.execute(
                    '''INSERT INTO alerts
                       (device_id, alert_type, threshold, current_value,
                        message, severity, created_at)
                       VALUES (?,?,?,?,?,?,?)''',
                    (device_id, metric, threshold, value, msg,
                     severity, now))
                # Auto-ticket: alert → ticket
                if config.get('auto_ticket'):
                    dev_row = self._conn.execute(
                        'SELECT hostname FROM devices WHERE id=?',
                        (device_id,)).fetchone()
                    dev_name = dev_row[0] if dev_row else device_id
                    tkt_title = f"[Otomatik] {dev_name} — {msg}"
                    tkt_desc = (f"Cihaz: {dev_name} ({device_id})\n"
                                f"Metrik: {labels[metric]}\n"
                                f"Seviye: {severity}\n"
                                f"Değer: %{value:.1f} / Eşik: %{threshold:.0f}")
                    tkt_pri = 'critical' if severity == 'critical' else 'high'
                    self._conn.execute(
                        '''INSERT INTO tickets
                           (title, description, priority, status, category,
                            device_id, assignee, created_by, created_at,
                            updated_at, notes)
                           VALUES (?,?,?,'open','alert',?,?,'system',?,?,'[]')''',
                        (tkt_title, tkt_desc, tkt_pri,
                         device_id, '', now, now))
            self._conn.commit()
        # Update risk score based on alerts
        for metric, value, warn_t, crit_t in checks:
            if value >= crit_t:
                self._add_risk_factor(device_id, f'alert_{metric}_critical', 20)
            elif value >= warn_t:
                self._add_risk_factor(device_id, f'alert_{metric}_warning', 5)

    def list_alerts(self, device_id: str = '', acknowledged: int = -1,
                    limit: int = 100) -> list:
        sql = ('SELECT a.*, d.hostname FROM alerts a '
               'LEFT JOIN devices d ON a.device_id = d.id WHERE 1=1')
        params: list = []
        if device_id:
            sql += ' AND a.device_id = ?'
            params.append(device_id)
        if acknowledged >= 0:
            sql += ' AND a.acknowledged = ?'
            params.append(acknowledged)
        sql += ' ORDER BY a.id DESC LIMIT ?'
        params.append(limit)
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            rows = self._conn.execute(sql, params).fetchall()
            self._conn.row_factory = None
        return [{'id': r['id'], 'device_id': r['device_id'],
                 'hostname': r['hostname'] or '',
                 'alert_type': r['alert_type'],
                 'threshold': r['threshold'],
                 'current_value': r['current_value'],
                 'message': r['message'], 'severity': r['severity'],
                 'acknowledged': bool(r['acknowledged']),
                 'created_at': r['created_at']} for r in rows]

    def acknowledge_alert(self, alert_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                'UPDATE alerts SET acknowledged=1 '
                'WHERE id=? AND acknowledged=0', (alert_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def alert_stats(self) -> dict:
        with self._lock:
            total = self._conn.execute(
                'SELECT COUNT(*) FROM alerts '
                'WHERE acknowledged=0').fetchone()[0]
            critical = self._conn.execute(
                "SELECT COUNT(*) FROM alerts "
                "WHERE acknowledged=0 AND severity='critical'"
            ).fetchone()[0]
            warning = self._conn.execute(
                "SELECT COUNT(*) FROM alerts "
                "WHERE acknowledged=0 AND severity='warning'"
            ).fetchone()[0]
        return {'total': total, 'critical': critical,
                'warning': warning}

    def get_alert_config(self) -> dict:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            row = self._conn.execute(
                'SELECT * FROM alert_config WHERE id=1').fetchone()
            self._conn.row_factory = None
        if not row:
            return {'cpu_warning': 80, 'cpu_critical': 95,
                    'ram_warning': 80, 'ram_critical': 95,
                    'disk_warning': 85, 'disk_critical': 95,
                    'enabled': True, 'cooldown_minutes': 30,
                    'auto_ticket': False}
        d = {k: row[k] for k in row.keys() if k != 'id'}
        d['enabled'] = bool(d.get('enabled', 1))
        d['auto_ticket'] = bool(d.get('auto_ticket', 0))
        return d

    def save_alert_config(self, config: dict) -> bool:
        fields = ('cpu_warning', 'cpu_critical', 'ram_warning',
                  'ram_critical', 'disk_warning', 'disk_critical',
                  'enabled', 'cooldown_minutes', 'auto_ticket')
        safe = {}
        for f in fields:
            if f in config:
                val = config[f]
                if f in ('enabled', 'auto_ticket'):
                    safe[f] = 1 if val else 0
                elif f == 'cooldown_minutes':
                    safe[f] = max(1, min(int(val), 1440))
                else:
                    safe[f] = max(0.0, min(float(val), 100.0))
        if not safe:
            return False
        with self._lock:
            existing = self._conn.execute(
                'SELECT id FROM alert_config WHERE id=1').fetchone()
            if existing:
                sets = ', '.join(f'{k}=?' for k in safe)
                self._conn.execute(
                    f'UPDATE alert_config SET {sets} WHERE id=1',
                    list(safe.values()))
            else:
                cols = ', '.join(['id'] + list(safe.keys()))
                phs = ', '.join(['?'] * (len(safe) + 1))
                self._conn.execute(
                    f'INSERT INTO alert_config ({cols}) VALUES ({phs})',
                    [1] + list(safe.values()))
            self._conn.commit()
        return True

    # ── Device Update ──

    def update_device(self, device_id: str, tenant_id: str = None,
                      label: str = None) -> bool:
        """Cihaz sahiplik/etiket bilgisini günceller."""
        updates: list = []
        params: list = []
        if tenant_id is not None:
            updates.append('tenant_id = ?')
            params.append(tenant_id)
        if label is not None:
            dev = self.get_device(device_id)
            if not dev:
                return False
            extra = dev.get('extra') or {}
            extra['label'] = label
            updates.append('extra = ?')
            params.append(json.dumps(extra, ensure_ascii=False))
        if not updates:
            return False
        params.append(device_id)
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE devices SET {', '.join(updates)} WHERE id=?",
                params)
            self._conn.commit()
        return cur.rowcount > 0

    # ── Threat Intelligence ──

    # MITRE ATT&CK — Sysmon Event ID → Tactic/Technique mapping
    MITRE_SYSMON_MAP = {
        1:  ('Execution', 'T1059', 'Process Creation'),
        2:  ('Defense Evasion', 'T1070.006', 'File Creation Time Changed'),
        3:  ('Command and Control', 'T1071', 'Network Connection'),
        5:  ('Execution', 'T1059', 'Process Terminated'),
        6:  ('Persistence', 'T1543.003', 'Driver Loaded'),
        7:  ('Execution', 'T1129', 'Image Loaded'),
        8:  ('Defense Evasion', 'T1055', 'CreateRemoteThread'),
        9:  ('Discovery', 'T1120', 'RawAccessRead'),
        10: ('Credential Access', 'T1003', 'ProcessAccess'),
        11: ('Collection', 'T1074', 'FileCreate'),
        12: ('Discovery', 'T1012', 'Registry Object Added/Deleted'),
        13: ('Persistence', 'T1547.001', 'Registry Value Set'),
        14: ('Defense Evasion', 'T1112', 'Registry Key/Value Rename'),
        15: ('Execution', 'T1204', 'FileCreateStreamHash (ADS)'),
        17: ('Execution', 'T1559', 'PipeEvent Created'),
        18: ('Lateral Movement', 'T1021', 'PipeEvent Connected'),
        19: ('Persistence', 'T1546', 'WmiEvent Filter'),
        20: ('Persistence', 'T1546', 'WmiEvent Consumer'),
        21: ('Persistence', 'T1546', 'WmiEvent Binding'),
        22: ('Command and Control', 'T1071.004', 'DNS Query'),
        23: ('Defense Evasion', 'T1070.004', 'FileDelete archived'),
        25: ('Defense Evasion', 'T1055.012', 'Process Tampering'),
        26: ('Defense Evasion', 'T1070.004', 'FileDelete logged'),
    }

    def add_threat_indicator(self, indicator: str,
                             indicator_type: str = 'ip',
                             source: str = 'manual',
                             reputation: str = 'malicious',
                             tags: list = None,
                             raw_data: dict = None) -> int:
        """Tehdit istihbaratı veritabanına yeni gösterge ekler."""
        now = self._now()
        with self._lock:
            try:
                cur = self._conn.execute(
                    '''INSERT INTO threat_intel
                       (indicator, indicator_type, source, reputation,
                        tags, raw_data, first_seen, last_checked)
                       VALUES (?,?,?,?,?,?,?,?)''',
                    (indicator, indicator_type, source, reputation,
                     json.dumps(tags or []), json.dumps(raw_data or {}),
                     now, now))
                self._conn.commit()
                return cur.lastrowid
            except sqlite3.IntegrityError:
                # Update existing
                self._conn.execute(
                    '''UPDATE threat_intel SET reputation=?, source=?,
                       tags=?, raw_data=?, last_checked=?
                       WHERE indicator=? AND indicator_type=?''',
                    (reputation, source, json.dumps(tags or []),
                     json.dumps(raw_data or {}), now,
                     indicator, indicator_type))
                self._conn.commit()
                row = self._conn.execute(
                    'SELECT id FROM threat_intel WHERE indicator=? AND indicator_type=?',
                    (indicator, indicator_type)).fetchone()
                return row[0] if row else 0

    def check_threat(self, indicator: str,
                     indicator_type: str = 'ip') -> Optional[dict]:
        """Göstergenin tehdit veritabanında olup olmadığını kontrol eder."""
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            row = self._conn.execute(
                'SELECT * FROM threat_intel '
                'WHERE indicator=? AND indicator_type=?',
                (indicator, indicator_type)).fetchone()
            self._conn.row_factory = None
        if not row:
            return None
        return {
            'id': row['id'], 'indicator': row['indicator'],
            'indicator_type': row['indicator_type'],
            'source': row['source'], 'reputation': row['reputation'],
            'tags': json.loads(row['tags'] or '[]'),
            'raw_data': json.loads(row['raw_data'] or '{}'),
            'first_seen': row['first_seen'],
            'last_checked': row['last_checked'],
        }

    def list_threats(self, indicator_type: str = '',
                     reputation: str = '', limit: int = 200) -> list:
        sql = 'SELECT * FROM threat_intel WHERE 1=1'
        params: list = []
        if indicator_type:
            sql += ' AND indicator_type = ?'
            params.append(indicator_type)
        if reputation:
            sql += ' AND reputation = ?'
            params.append(reputation)
        sql += ' ORDER BY last_checked DESC LIMIT ?'
        params.append(limit)
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            rows = self._conn.execute(sql, params).fetchall()
            self._conn.row_factory = None
        return [{
            'id': r['id'], 'indicator': r['indicator'],
            'indicator_type': r['indicator_type'],
            'source': r['source'], 'reputation': r['reputation'],
            'tags': json.loads(r['tags'] or '[]'),
            'first_seen': r['first_seen'],
            'last_checked': r['last_checked'],
        } for r in rows]

    def remove_threat(self, threat_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute(
                'DELETE FROM threat_intel WHERE id=?', (threat_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def threat_stats(self) -> dict:
        with self._lock:
            total = self._conn.execute(
                'SELECT COUNT(*) FROM threat_intel').fetchone()[0]
            malicious = self._conn.execute(
                "SELECT COUNT(*) FROM threat_intel "
                "WHERE reputation='malicious'").fetchone()[0]
            suspicious = self._conn.execute(
                "SELECT COUNT(*) FROM threat_intel "
                "WHERE reputation='suspicious'").fetchone()[0]
            by_type = {}
            for row in self._conn.execute(
                'SELECT indicator_type, COUNT(*) FROM threat_intel '
                'GROUP BY indicator_type').fetchall():
                by_type[row[0]] = row[1]
        return {'total': total, 'malicious': malicious,
                'suspicious': suspicious, 'by_type': by_type}

    # ── Event Correlation Engine ──

    def create_correlation_rule(self, name: str, description: str = '',
                                rule_type: str = 'threshold',
                                conditions: dict = None,
                                severity: str = 'warning') -> int:
        """Yeni korelasyon kuralı oluşturur.
        rule_type: threshold | sequence | frequency
        conditions örneği:
          threshold: {"metric": "cpu", "operator": ">=", "value": 95, "count": 3, "window_minutes": 10}
          frequency: {"alert_type": "cpu", "count": 5, "window_minutes": 60}
        """
        valid_types = ('threshold', 'sequence', 'frequency')
        if rule_type not in valid_types:
            rule_type = 'threshold'
        if severity not in ('info', 'warning', 'critical'):
            severity = 'warning'
        with self._lock:
            cur = self._conn.execute(
                '''INSERT INTO correlation_rules
                   (name, description, rule_type, conditions,
                    severity, enabled, created_at)
                   VALUES (?,?,?,?,?,1,?)''',
                (name, description, rule_type,
                 json.dumps(conditions or {}), severity, self._now()))
            self._conn.commit()
            return cur.lastrowid

    def list_correlation_rules(self) -> list:
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            rows = self._conn.execute(
                'SELECT * FROM correlation_rules ORDER BY id').fetchall()
            self._conn.row_factory = None
        return [{
            'id': r['id'], 'name': r['name'],
            'description': r['description'],
            'rule_type': r['rule_type'],
            'conditions': json.loads(r['conditions'] or '{}'),
            'severity': r['severity'],
            'enabled': bool(r['enabled']),
            'created_at': r['created_at'],
        } for r in rows]

    def toggle_correlation_rule(self, rule_id: int,
                                enabled: bool) -> bool:
        with self._lock:
            cur = self._conn.execute(
                'UPDATE correlation_rules SET enabled=? WHERE id=?',
                (1 if enabled else 0, rule_id))
            self._conn.commit()
        return cur.rowcount > 0

    def delete_correlation_rule(self, rule_id: int) -> bool:
        with self._lock:
            self._conn.execute(
                'DELETE FROM correlation_events WHERE rule_id=?',
                (rule_id,))
            self._conn.execute(
                'DELETE FROM correlation_rules WHERE id=?', (rule_id,))
            self._conn.commit()
        return True

    def evaluate_correlation_rules(self, device_id: str):
        """Heartbeat sonrası korelasyon kurallarını değerlendirir."""
        rules = self.list_correlation_rules()
        for rule in rules:
            if not rule['enabled']:
                continue
            cond = rule['conditions']
            if rule['rule_type'] == 'frequency':
                self._eval_frequency_rule(rule, cond, device_id)
            elif rule['rule_type'] == 'threshold':
                self._eval_threshold_rule(rule, cond, device_id)

    def _eval_frequency_rule(self, rule: dict, cond: dict,
                             device_id: str):
        """Belirli bir süre içinde belirli sayıda alert oluşursa tetikle."""
        alert_type = cond.get('alert_type', '')
        count = cond.get('count', 5)
        window = cond.get('window_minutes', 60)
        cutoff = (datetime.now(timezone.utc)
                  - timedelta(minutes=window)).isoformat()
        with self._lock:
            cnt = self._conn.execute(
                'SELECT COUNT(*) FROM alerts '
                'WHERE device_id=? AND alert_type=? AND created_at>?',
                (device_id, alert_type, cutoff)).fetchone()[0]
        if cnt >= count:
            # Duplicate check — same rule+device within window
            with self._lock:
                dup = self._conn.execute(
                    'SELECT id FROM correlation_events '
                    'WHERE rule_id=? AND device_id=? AND created_at>?',
                    (rule['id'], device_id, cutoff)).fetchone()
            if dup:
                return
            self._create_correlation_event(
                rule['id'], device_id, rule['severity'],
                {'matched_count': cnt, 'window_minutes': window,
                 'alert_type': alert_type})

    def _eval_threshold_rule(self, rule: dict, cond: dict,
                             device_id: str):
        """Metrik eşiğinin belirli süre boyunca aşılması."""
        metric = cond.get('metric', 'cpu')
        operator = cond.get('operator', '>=')
        value = cond.get('value', 95)
        count = cond.get('count', 3)
        window = cond.get('window_minutes', 10)
        cutoff = (datetime.now(timezone.utc)
                  - timedelta(minutes=window)).isoformat()
        col_map = {'cpu': 'cpu', 'ram': 'ram', 'disk': 'disk'}
        col = col_map.get(metric)
        if not col:
            return
        op_map = {'>=': '>=', '>': '>', '<=': '<=', '<': '<'}
        op = op_map.get(operator, '>=')
        with self._lock:
            cnt = self._conn.execute(
                f'SELECT COUNT(*) FROM metrics '
                f'WHERE device_id=? AND ts>? AND {col} {op} ?',
                (device_id, cutoff, value)).fetchone()[0]
        if cnt >= count:
            with self._lock:
                dup = self._conn.execute(
                    'SELECT id FROM correlation_events '
                    'WHERE rule_id=? AND device_id=? AND created_at>?',
                    (rule['id'], device_id, cutoff)).fetchone()
            if dup:
                return
            self._create_correlation_event(
                rule['id'], device_id, rule['severity'],
                {'metric': metric, 'operator': operator,
                 'value': value, 'matched_count': cnt})

    def _create_correlation_event(self, rule_id: int, device_id: str,
                                  severity: str, details: dict):
        now = self._now()
        with self._lock:
            self._conn.execute(
                '''INSERT INTO correlation_events
                   (rule_id, device_id, details, severity, created_at)
                   VALUES (?,?,?,?,?)''',
                (rule_id, device_id, json.dumps(details), severity, now))
            self._conn.commit()
        # Update risk score
        self._add_risk_factor(
            device_id, 'correlation',
            30 if severity == 'critical' else 15, now)

    def list_correlation_events(self, rule_id: int = 0,
                                device_id: str = '',
                                limit: int = 100) -> list:
        sql = ('SELECT ce.*, cr.name as rule_name, d.hostname '
               'FROM correlation_events ce '
               'LEFT JOIN correlation_rules cr ON ce.rule_id = cr.id '
               'LEFT JOIN devices d ON ce.device_id = d.id '
               'WHERE 1=1')
        params: list = []
        if rule_id:
            sql += ' AND ce.rule_id = ?'
            params.append(rule_id)
        if device_id:
            sql += ' AND ce.device_id = ?'
            params.append(device_id)
        sql += ' ORDER BY ce.id DESC LIMIT ?'
        params.append(limit)
        with self._lock:
            self._conn.row_factory = sqlite3.Row
            rows = self._conn.execute(sql, params).fetchall()
            self._conn.row_factory = None
        return [{
            'id': r['id'], 'rule_id': r['rule_id'],
            'rule_name': r['rule_name'] or '',
            'device_id': r['device_id'],
            'hostname': r['hostname'] or '',
            'details': json.loads(r['details'] or '{}'),
            'severity': r['severity'],
            'mitre_tactic': r['mitre_tactic'],
            'mitre_technique': r['mitre_technique'],
            'created_at': r['created_at'],
        } for r in rows]

    # ── MITRE ATT&CK Mapping ──

    def map_sysmon_to_mitre(self, sysmon_events: list) -> list:
        """Sysmon olaylarını MITRE ATT&CK taktik/tekniklerine eşler."""
        results = []
        for ev in sysmon_events:
            eid = ev.get('event_id', 0)
            mapping = self.MITRE_SYSMON_MAP.get(eid)
            if mapping:
                tactic, technique, desc = mapping
                results.append({
                    'event_id': eid,
                    'tactic': tactic,
                    'technique': technique,
                    'technique_desc': desc,
                    'event_message': ev.get('message', ''),
                    'timestamp': ev.get('timestamp', ''),
                })
        return results

    def get_mitre_heatmap(self, device_id: str = '') -> dict:
        """MITRE taktik bazlı heatmap verisi döndürür."""
        # Sysmon task result'larından veri çek
        sql = ("SELECT result FROM tasks WHERE task_type='sysmon_collect' "
               "AND status='completed'")
        params: list = []
        if device_id:
            sql += ' AND device_id = ?'
            params.append(device_id)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        tactic_counts: dict = {}
        technique_list: list = []
        for row in rows:
            try:
                events = json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(events, list):
                continue
            mapped = self.map_sysmon_to_mitre(events)
            for m in mapped:
                tac = m['tactic']
                tactic_counts[tac] = tactic_counts.get(tac, 0) + 1
                technique_list.append(m)
        # Also include correlation events with MITRE tags
        with self._lock:
            c_rows = self._conn.execute(
                'SELECT mitre_tactic, mitre_technique FROM correlation_events '
                'WHERE mitre_tactic != ""').fetchall()
        for r in c_rows:
            tac = r[0]
            tactic_counts[tac] = tactic_counts.get(tac, 0) + 1
        return {
            'tactic_counts': tactic_counts,
            'techniques': technique_list[-100:],
            'total_mapped': len(technique_list),
        }

    def get_mitre_summary(self) -> dict:
        """Tüm MITRE taktiklerinin özet istatistiği."""
        all_tactics = [
            'Initial Access', 'Execution', 'Persistence',
            'Privilege Escalation', 'Defense Evasion',
            'Credential Access', 'Discovery', 'Lateral Movement',
            'Collection', 'Command and Control', 'Exfiltration',
            'Impact',
        ]
        heatmap = self.get_mitre_heatmap()
        counts = heatmap['tactic_counts']
        return {
            'tactics': [{
                'name': t,
                'count': counts.get(t, 0),
            } for t in all_tactics],
            'total_events': heatmap['total_mapped'],
            'top_techniques': heatmap['techniques'][:20],
        }

    # ── Risk-Based Alerting (RBA) ──

    def _add_risk_factor(self, device_id: str, factor_type: str,
                         points: float, timestamp: str = ''):
        """Cihaza risk puanı faktörü ekler."""
        ts = timestamp or self._now()
        with self._lock:
            row = self._conn.execute(
                'SELECT score, factors FROM risk_scores WHERE device_id=?',
                (device_id,)).fetchone()
            if row:
                score = row[0]
                factors = json.loads(row[1] or '[]')
            else:
                score = 0.0
                factors = []
            factors.append({
                'type': factor_type, 'points': points,
                'ts': ts,
            })
            # Keep last 50 factors
            factors = factors[-50:]
            new_score = min(100.0, score + points)
            if row:
                self._conn.execute(
                    'UPDATE risk_scores SET score=?, factors=?, updated_at=? '
                    'WHERE device_id=?',
                    (new_score, json.dumps(factors), ts, device_id))
            else:
                self._conn.execute(
                    'INSERT INTO risk_scores (device_id, score, factors, updated_at) '
                    'VALUES (?,?,?,?)',
                    (device_id, new_score, json.dumps(factors), ts))
            self._conn.commit()

    def get_risk_score(self, device_id: str) -> dict:
        with self._lock:
            row = self._conn.execute(
                'SELECT rs.*, d.hostname FROM risk_scores rs '
                'LEFT JOIN devices d ON rs.device_id = d.id '
                'WHERE rs.device_id=?', (device_id,)).fetchone()
        if not row:
            return {'device_id': device_id, 'score': 0,
                    'level': 'low', 'factors': []}
        score = row[1]
        return {
            'device_id': device_id,
            'hostname': row[4] if len(row) > 4 else '',
            'score': score,
            'level': ('critical' if score >= 75 else
                      'high' if score >= 50 else
                      'medium' if score >= 25 else 'low'),
            'factors': json.loads(row[2] or '[]'),
            'updated_at': row[3],
        }

    def list_risk_scores(self) -> list:
        with self._lock:
            rows = self._conn.execute(
                'SELECT rs.device_id, rs.score, rs.updated_at, d.hostname '
                'FROM risk_scores rs '
                'LEFT JOIN devices d ON rs.device_id = d.id '
                'ORDER BY rs.score DESC').fetchall()
        results = []
        for r in rows:
            score = r[1]
            results.append({
                'device_id': r[0], 'hostname': r[3] or '',
                'score': score,
                'level': ('critical' if score >= 75 else
                          'high' if score >= 50 else
                          'medium' if score >= 25 else 'low'),
                'updated_at': r[2],
            })
        return results

    def decay_risk_scores(self, decay_percent: float = 5.0):
        """Tüm risk puanlarını yüzdesel olarak azaltır (zaman bazlı çürüme)."""
        with self._lock:
            rows = self._conn.execute(
                'SELECT device_id, score FROM risk_scores '
                'WHERE score > 0').fetchall()
            now = self._now()
            for device_id, score in rows:
                new_score = max(0, score * (1 - decay_percent / 100))
                if new_score < 0.5:
                    new_score = 0
                self._conn.execute(
                    'UPDATE risk_scores SET score=?, updated_at=? '
                    'WHERE device_id=?', (new_score, now, device_id))
            self._conn.commit()

    def risk_dashboard(self) -> dict:
        scores = self.list_risk_scores()
        critical = sum(1 for s in scores if s['level'] == 'critical')
        high = sum(1 for s in scores if s['level'] == 'high')
        medium = sum(1 for s in scores if s['level'] == 'medium')
        low = sum(1 for s in scores if s['level'] == 'low')
        return {
            'scores': scores,
            'summary': {
                'critical': critical, 'high': high,
                'medium': medium, 'low': low,
                'total': len(scores),
            },
        }

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
