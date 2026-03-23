"""
Emare Security OS — Log Store Soyutlama Katmanı
=============================================

Küçük ağlar: SQLiteStore (in-memory ring buffer + SQLite)
ISP modunda : PostgresStore (PostgreSQL, bağlantı havuzlu)

Aynı arayüz, farklı backend. LogStore ortak mantığı sağlar.
"""

import json
import heapq
import logging
import threading
import collections
from datetime import datetime, timezone, timedelta

from emarefirewall.law5651 import Law5651Stamper

logger = logging.getLogger('emarefirewall.store')


class LogStore:
    """Thread-safe in-memory ring buffer + kalıcı depolama backend'i.

    standalone modda: SQLite (mevcut davranış)
    isp modda      : PostgreSQL
    """

    def __init__(self, max_entries: int = 5000, db_backend=None,
                 retention_days: int = 30, law5651_stamper: Law5651Stamper = None):
        self._entries = collections.deque(maxlen=max_entries)
        self._counter = 0
        self._lock = threading.Lock()
        self._db = db_backend       # SQLiteBackend veya PostgresBackend
        self._retention_days = retention_days
        self._law5651 = law5651_stamper
        self._write_buf = []
        self._flush_timer = None
        self._FLUSH_SIZE = 50
        self._FLUSH_INTERVAL = 0.25
        self.stats = {
            'total_requests': 0,
            'total_errors': 0,
            'total_blocked': 0,
            'total_l7_blocks': 0,
            'by_method': {},
            'by_status': {},
            'by_ip': {},
            'by_path': {},
            'by_category': {},
            'hourly_requests': {},
            'severity_counts': {'INFO': 0, 'WARNING': 0, 'ERROR': 0, 'CRITICAL': 0},
            'l7_by_type': {},
        }
        if self._db:
            self._db.init()
            self._cleanup_old_logs()
            self._load_from_db()

    def _cleanup_old_logs(self):
        if not self._db:
            return
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self._retention_days)).isoformat()
        try:
            self._db.delete_before(cutoff)
        except Exception as e:
            logger.warning('Log cleanup hatası: %s', e)

    def _load_from_db(self):
        if not self._db:
            return
        try:
            rows = self._db.load_recent(self._entries.maxlen)
            for entry in rows:
                self._entries.append(entry)
                self._counter = max(self._counter, entry['id'])
                self._update_stats(entry)
            if self._law5651:
                self._law5651.restore_from_entries(list(self._entries))
            logger.info('DB\'den %d log yüklendi.', len(rows))
        except Exception as e:
            logger.warning('DB yükleme hatası: %s', e)

    def set_5651_stamper(self, stamper: Law5651Stamper):
        """5651 damgalama motorunu çalışma anında ata."""
        with self._lock:
            self._law5651 = stamper
            if self._law5651:
                self._law5651.restore_from_entries(list(self._entries))

    def _persist(self, entry: dict):
        if not self._db:
            return
        self._write_buf.append(entry)
        if len(self._write_buf) >= self._FLUSH_SIZE:
            self._flush_db()
        elif self._flush_timer is None:
            self._flush_timer = threading.Timer(self._FLUSH_INTERVAL, self._flush_db)
            self._flush_timer.daemon = True
            self._flush_timer.start()

    def _flush_db(self):
        if self._flush_timer is not None:
            self._flush_timer.cancel()
            self._flush_timer = None
        buf = self._write_buf
        self._write_buf = []
        if not buf:
            return
        try:
            self._db.insert_batch(buf)
        except Exception as e:
            logger.warning('DB batch yazma hatası: %s', e)

    def _update_stats(self, entry: dict):
        category = entry['category']
        status_code = entry['status']
        level = entry['level']
        method = entry['method']
        ip = entry['ip']
        path = entry['path']

        self.stats['total_requests'] += 1 if category == 'RESPONSE' else 0
        if status_code and status_code >= 400:
            self.stats['total_errors'] += 1
        if category in ('RATE_LIMIT', 'CSRF'):
            self.stats['total_blocked'] += 1
        if category.startswith('L7_'):
            self.stats['total_l7_blocks'] += 1
            self.stats['l7_by_type'][category] = self.stats['l7_by_type'].get(category, 0) + 1
        self.stats['by_category'][category] = self.stats['by_category'].get(category, 0) + 1
        if category == 'RESPONSE':
            self.stats['by_method'][method] = self.stats['by_method'].get(method, 0) + 1
            sc = str(status_code)
            self.stats['by_status'][sc] = self.stats['by_status'].get(sc, 0) + 1
            self.stats['by_ip'][ip] = self.stats['by_ip'].get(ip, 0) + 1
            self.stats['by_path'][path] = self.stats['by_path'].get(path, 0) + 1
            try:
                hour = entry['ts'][11:13]
                self.stats['hourly_requests'][hour] = self.stats['hourly_requests'].get(hour, 0) + 1
            except (IndexError, TypeError):
                pass
        sev = level.upper()
        if sev in self.stats['severity_counts']:
            self.stats['severity_counts'][sev] += 1

    def add(self, level, category, method, path, ip, status_code=0,
            message='', server_id='', extra=None):
        with self._lock:
            self._counter += 1
            entry = {
                'id': self._counter,
                'ts': datetime.now(timezone.utc).isoformat(),
                'level': level,
                'category': category,
                'method': method,
                'path': path,
                'ip': ip,
                'status': status_code,
                'message': message,
                'server_id': server_id,
                'extra': extra or {},
            }
            if self._law5651:
                stamp = self._law5651.stamp_entry(entry)
                stamped_extra = dict(entry['extra'])
                stamped_extra['law_5651'] = stamp
                entry['extra'] = stamped_extra
            self._entries.append(entry)
            self._update_stats(entry)
            self._persist(entry)
            return entry

    def query(self, limit=100, offset=0, level='', category='', ip='',
              method='', path_contains='', since_id=0, since_ts='',
              category_prefix=''):
        results = []
        for e in reversed(self._entries):
            if since_id and e['id'] <= since_id:
                continue
            if since_ts and e['ts'] < since_ts:
                continue
            if level and e['level'].upper() != level.upper():
                continue
            if category and e['category'].upper() != category.upper():
                continue
            if category_prefix and not e['category'].upper().startswith(category_prefix.upper()):
                continue
            if ip and e['ip'] != ip:
                continue
            if method and e['method'].upper() != method.upper():
                continue
            if path_contains and path_contains.lower() not in e['path'].lower():
                continue
            results.append(e)
        total = len(results)
        return {'entries': results[offset:offset + limit], 'total': total}

    def get_stats(self):
        top_ips = heapq.nlargest(15, self.stats['by_ip'].items(), key=lambda x: x[1])
        top_paths = heapq.nlargest(15, self.stats['by_path'].items(), key=lambda x: x[1])
        return {
            'total_requests': self.stats['total_requests'],
            'total_errors': self.stats['total_errors'],
            'total_blocked': self.stats['total_blocked'],
            'total_logs': len(self._entries),
            'by_method': self.stats['by_method'],
            'by_status': self.stats['by_status'],
            'severity_counts': self.stats['severity_counts'],
            'hourly_requests': self.stats['hourly_requests'],
            'top_ips': top_ips,
            'top_paths': top_paths,
            'total_l7_blocks': self.stats['total_l7_blocks'],
            'l7_by_type': self.stats['l7_by_type'],
            'by_category': self.stats['by_category'],
        }

    def get_ip_detail(self, ip):
        entries = [e for e in self._entries if e['ip'] == ip]
        if not entries:
            return {'ip': ip, 'found': False}
        first_seen = entries[0]['ts']
        last_seen = entries[-1]['ts']
        paths, methods, statuses, categories, hourly = {}, {}, {}, {}, {}
        errors, warnings, blocked = 0, 0, 0
        for e in entries:
            paths[e['path']] = paths.get(e['path'], 0) + 1
            methods[e['method']] = methods.get(e['method'], 0) + 1
            if e['status']:
                sc = str(e['status'])
                statuses[sc] = statuses.get(sc, 0) + 1
                if e['status'] >= 400:
                    errors += 1
            categories[e['category']] = categories.get(e['category'], 0) + 1
            if e['category'] in ('RATE_LIMIT', 'CSRF'):
                blocked += 1
            if e['level'] == 'WARNING':
                warnings += 1
            if e['level'] == 'ERROR':
                errors += 1
            try:
                hour = e['ts'][11:13]
                hourly[hour] = hourly.get(hour, 0) + 1
            except (IndexError, TypeError):
                pass
        top_paths = sorted(paths.items(), key=lambda x: x[1], reverse=True)[:20]
        total = len(entries)
        error_rate = errors / max(total, 1)
        block_rate = blocked / max(total, 1)
        risk = min(100, int(error_rate * 40 + block_rate * 40 + min(total / 100, 1) * 20))
        recent = list(reversed(entries[-20:]))
        return {
            'ip': ip, 'found': True, 'total_requests': total,
            'first_seen': first_seen, 'last_seen': last_seen,
            'errors': errors, 'warnings': warnings, 'blocked': blocked,
            'risk_score': risk, 'by_method': methods, 'by_status': statuses,
            'by_category': categories, 'hourly': hourly,
            'top_paths': top_paths, 'recent': recent,
        }

    def get_all_ips(self):
        ip_data = {}
        for e in self._entries:
            ip = e['ip']
            if ip not in ip_data:
                ip_data[ip] = {
                    'ip': ip, 'total': 0, 'errors': 0, 'blocked': 0,
                    'first_seen': e['ts'], 'last_seen': e['ts'],
                    'methods': set()
                }
            d = ip_data[ip]
            d['total'] += 1
            d['last_seen'] = e['ts']
            d['methods'].add(e['method'])
            if e['status'] and e['status'] >= 400:
                d['errors'] += 1
            if e['category'] in ('RATE_LIMIT', 'CSRF'):
                d['blocked'] += 1
        result = []
        for d in ip_data.values():
            total = d['total']
            error_rate = d['errors'] / max(total, 1)
            block_rate = d['blocked'] / max(total, 1)
            risk = min(100, int(error_rate * 40 + block_rate * 40 + min(total / 100, 1) * 20))
            result.append({
                'ip': d['ip'], 'total': total, 'errors': d['errors'],
                'blocked': d['blocked'], 'risk_score': risk,
                'first_seen': d['first_seen'], 'last_seen': d['last_seen'],
                'methods': sorted(d['methods']),
            })
        result.sort(key=lambda x: x['total'], reverse=True)
        return result

    def export(self, fmt='json', limit=5000, category_prefix='', since_ts=''):
        import csv
        import io
        entries = []
        for e in reversed(self._entries):
            if since_ts and e['ts'] < since_ts:
                continue
            if category_prefix and not e['category'].startswith(category_prefix):
                continue
            entries.append(e)
            if len(entries) >= limit:
                break
        if fmt == 'csv':
            if not entries:
                return 'id,ts,level,category,method,path,ip,status,message\n'
            output = io.StringIO()
            writer = csv.DictWriter(output,
                fieldnames=['id', 'ts', 'level', 'category', 'method',
                            'path', 'ip', 'status', 'message', 'server_id'])
            writer.writeheader()
            for e in entries:
                writer.writerow({k: e.get(k, '') for k in writer.fieldnames})
            return output.getvalue()
        return json.dumps(entries, ensure_ascii=False, indent=2)

    def get_l7_summary(self):
        l7_entries = [e for e in self._entries if e['category'].startswith('L7_')]
        by_type = {}
        total_count = 0
        for e in l7_entries:
            cat = e['category']
            count = e.get('extra', {}).get('count', 1)
            by_type[cat] = by_type.get(cat, 0) + count
            total_count += count
        return {
            'total_events': len(l7_entries),
            'total_blocks': total_count,
            'by_type': by_type,
            'last_events': list(reversed(l7_entries[-20:])),
        }

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._counter = 0
            for k in self.stats:
                if isinstance(self.stats[k], dict):
                    self.stats[k] = {} if k != 'severity_counts' else {
                        'INFO': 0, 'WARNING': 0, 'ERROR': 0, 'CRITICAL': 0}
                else:
                    self.stats[k] = 0
            if self._db:
                try:
                    self._db.delete_all()
                except Exception as e:
                    logger.warning('DB clear hatası: %s', e)

    def get_db_info(self):
        info = {
            'persistent': self._db is not None,
            'backend': self._db.__class__.__name__ if self._db else 'memory',
            'retention_days': self._retention_days,
            'memory_entries': len(self._entries),
            'db_entries': 0,
            'law_5651_enabled': self._law5651 is not None,
        }
        if self._db:
            try:
                info['db_entries'] = self._db.count()
            except Exception:
                pass
        return info

    def get_5651_status(self):
        if not self._law5651:
            return {
                'enabled': False,
                'message': '5651 damgalama motoru etkin degil.',
            }
        return self._law5651.status()

    def verify_5651_chain(self, limit=5000):
        if not self._law5651:
            return {
                'ok': False,
                'verified': 0,
                'broken_at': None,
                'reason': '5651 damgalama motoru etkin degil.',
            }
        with self._lock:
            entries = list(self._entries)[-max(1, int(limit)):]
        return self._law5651.verify_entries(entries)

    def seal_5651(self, note='manual-seal'):
        """5651 zincirine manuel bir muhurlu kontrol kaydi ekler."""
        entry = self.add(
            'INFO', 'LAW_5651_SEAL', 'SYSTEM', '/api/firewall/logs/5651/seal',
            '-', status_code=200, message=note, extra={'seal': True},
        )
        return (entry.get('extra') or {}).get('law_5651', {})


# ═══════════════════ DB BACKEND'LER ═══════════════════

_LOG_COLUMNS = ('id', 'ts', 'level', 'category', 'method', 'path',
                'ip', 'status', 'message', 'server_id', 'extra')


class SQLiteBackend:
    """Tek dosya, sıfır bağımlılık — küçük ağlar için."""

    def __init__(self, db_path: str):
        import os
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
        self._conn = None

    def init(self):
        import sqlite3
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=10)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA cache_size=-2000")
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._conn.execute("PRAGMA mmap_size=4194304")
        self._conn.execute('''CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL, level TEXT NOT NULL, category TEXT NOT NULL,
            method TEXT DEFAULT '', path TEXT DEFAULT '', ip TEXT DEFAULT '',
            status INTEGER DEFAULT 0, message TEXT DEFAULT '',
            server_id TEXT DEFAULT '', extra TEXT DEFAULT '{}'
        )''')
        self._conn.execute('CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(ts)')
        self._conn.execute('CREATE INDEX IF NOT EXISTS idx_logs_category ON logs(category)')
        self._conn.execute('CREATE INDEX IF NOT EXISTS idx_logs_ip ON logs(ip)')
        self._conn.execute('CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level)')
        self._conn.commit()

    def load_recent(self, limit: int) -> list:
        import sqlite3
        self._conn.row_factory = sqlite3.Row
        rows = self._conn.execute(
            'SELECT * FROM logs ORDER BY id DESC LIMIT ?', (limit,)
        ).fetchall()
        self._conn.row_factory = None
        result = []
        for row in reversed(rows):
            result.append({
                'id': row['id'], 'ts': row['ts'], 'level': row['level'],
                'category': row['category'], 'method': row['method'],
                'path': row['path'], 'ip': row['ip'], 'status': row['status'],
                'message': row['message'], 'server_id': row['server_id'],
                'extra': json.loads(row['extra'] or '{}'),
            })
        return result

    def insert_batch(self, entries: list):
        self._conn.executemany(
            '''INSERT INTO logs (id, ts, level, category, method, path, ip,
               status, message, server_id, extra)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            [(e['id'], e['ts'], e['level'], e['category'], e['method'],
              e['path'], e['ip'], e['status'], e['message'], e['server_id'],
              json.dumps(e.get('extra', {}), ensure_ascii=False))
             for e in entries]
        )
        self._conn.commit()

    def delete_before(self, cutoff_ts: str):
        self._conn.execute('DELETE FROM logs WHERE ts < ?', (cutoff_ts,))
        self._conn.commit()

    def delete_all(self):
        self._conn.execute('DELETE FROM logs')
        self._conn.commit()

    def count(self) -> int:
        return self._conn.execute('SELECT COUNT(*) FROM logs').fetchone()[0]

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


class PostgresBackend:
    """PostgreSQL + bağlantı havuzu — ISP modunda yüksek throughput."""

    def __init__(self, postgres_url: str, pool_size: int = 5):
        try:
            import psycopg2
            import psycopg2.pool
        except ImportError:
            raise ImportError("ISP modu için psycopg2 gerekli: pip install psycopg2-binary")
        self._pool = psycopg2.pool.ThreadedConnectionPool(1, pool_size, postgres_url)
        logger.info("PostgreSQL bağlantı havuzu oluşturuldu: pool_size=%d", pool_size)

    def _get_conn(self):
        return self._pool.getconn()

    def _put_conn(self, conn):
        self._pool.putconn(conn)

    def init(self):
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                # Advisory lock — birden fazla worker'ın aynı anda tablo oluşturmasını önler
                cur.execute('SELECT pg_advisory_lock(42)')
                try:
                    cur.execute('''CREATE TABLE IF NOT EXISTS logs (
                        id BIGSERIAL PRIMARY KEY,
                        ts TIMESTAMPTZ NOT NULL, level VARCHAR(16) NOT NULL,
                        category VARCHAR(64) NOT NULL,
                        method VARCHAR(8) DEFAULT '', path VARCHAR(512) DEFAULT '',
                        ip VARCHAR(45) DEFAULT '', status INTEGER DEFAULT 0,
                        message TEXT DEFAULT '', server_id VARCHAR(128) DEFAULT '',
                        extra JSONB DEFAULT '{}'
                    )''')
                    cur.execute('CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(ts)')
                    cur.execute('CREATE INDEX IF NOT EXISTS idx_logs_category ON logs(category)')
                    cur.execute('CREATE INDEX IF NOT EXISTS idx_logs_ip ON logs(ip)')
                    conn.commit()
                finally:
                    cur.execute('SELECT pg_advisory_unlock(42)')
        finally:
            self._put_conn(conn)

    def load_recent(self, limit: int) -> list:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    'SELECT id, ts, level, category, method, path, ip, status, '
                    'message, server_id, extra FROM logs ORDER BY id DESC LIMIT %s',
                    (limit,))
                rows = cur.fetchall()
            result = []
            for row in reversed(rows):
                result.append({
                    'id': row[0], 'ts': row[1].isoformat() if hasattr(row[1], 'isoformat') else str(row[1]),
                    'level': row[2], 'category': row[3], 'method': row[4],
                    'path': row[5], 'ip': row[6], 'status': row[7],
                    'message': row[8], 'server_id': row[9],
                    'extra': row[10] if isinstance(row[10], dict) else json.loads(row[10] or '{}'),
                })
            return result
        finally:
            self._put_conn(conn)

    def insert_batch(self, entries: list):
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                from psycopg2.extras import execute_values
                values = [(
                    e['ts'], e['level'], e['category'], e['method'],
                    e['path'], e['ip'], e['status'], e['message'],
                    e['server_id'], json.dumps(e.get('extra', {}), ensure_ascii=False)
                ) for e in entries]
                execute_values(cur,
                    'INSERT INTO logs (ts, level, category, method, path, ip, '
                    'status, message, server_id, extra) VALUES %s', values)
                conn.commit()
        finally:
            self._put_conn(conn)

    def delete_before(self, cutoff_ts: str):
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM logs WHERE ts < %s', (cutoff_ts,))
                conn.commit()
        finally:
            self._put_conn(conn)

    def delete_all(self):
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute('TRUNCATE logs')
                conn.commit()
        finally:
            self._put_conn(conn)

    def count(self) -> int:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT COUNT(*) FROM logs')
                return cur.fetchone()[0]
        finally:
            self._put_conn(conn)


def create_store(db_backend: str = 'sqlite', **kwargs) -> LogStore:
    """Yapılandırmaya göre LogStore oluştur."""
    backend = None
    if db_backend == 'postgres':
        backend = PostgresBackend(
            postgres_url=kwargs.get('postgres_url', 'postgresql://localhost/emarefirewall'),
            pool_size=kwargs.get('pool_size', 5),
        )
    elif db_backend == 'sqlite' and kwargs.get('db_path'):
        backend = SQLiteBackend(db_path=kwargs['db_path'])

    return LogStore(
        max_entries=kwargs.get('max_entries', 5000),
        db_backend=backend,
        retention_days=kwargs.get('retention_days', 30),
        law5651_stamper=kwargs.get('law5651_stamper'),
    )
