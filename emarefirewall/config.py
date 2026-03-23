"""
Emare Security OS — Yapılandırma Modülü
=========================================

Ortam değişkenleriyle mod seçimi:
    EMARE_MODE=standalone   (varsayılan — küçük ağlar, dict cache, SQLite)
    EMARE_MODE=isp          (büyük ISP — Redis cache, PostgreSQL, çoklu worker)
"""

import os
import secrets

# ── Mod ──
MODE = os.environ.get('EMARE_MODE', 'standalone').lower()
IS_ISP = MODE == 'isp'

# ── Web Sunucu ──
HOST = os.environ.get('EMARE_HOST', '0.0.0.0')
PORT = int(os.environ.get('EMARE_PORT', '5555'))
WORKERS = int(os.environ.get('EMARE_WORKERS', '4' if IS_ISP else '1'))
DEBUG = os.environ.get('EMARE_DEBUG', '0') == '1'
SECRET_KEY = os.environ.get('EMARE_SECRET_KEY') or secrets.token_hex(32)

# ── Cache ──
CACHE_BACKEND = os.environ.get('EMARE_CACHE', 'redis' if IS_ISP else 'dict')
CACHE_TTL = int(os.environ.get('EMARE_CACHE_TTL', '5'))
REDIS_URL = os.environ.get('EMARE_REDIS_URL', 'redis://localhost:6379/0')

# ── Veritabanı (Loglar) ──
DB_BACKEND = os.environ.get('EMARE_DB', 'postgres' if IS_ISP else 'sqlite')
SQLITE_PATH = os.environ.get('EMARE_SQLITE_PATH', '/tmp/emarefirewall.db')
POSTGRES_URL = os.environ.get('EMARE_POSTGRES_URL', '')

# ── Log ──
LOG_RETENTION_DAYS = int(os.environ.get('EMARE_LOG_RETENTION_DAYS', '30'))
LOG_MAX_MEMORY = int(os.environ.get('EMARE_LOG_MAX_MEMORY', '5000'))

# ── 5651 / Zaman Damgasi ──
LAW5651_ENABLED = os.environ.get('EMARE_5651_ENABLED', '0') == '1'
LAW5651_ORGANIZATION = os.environ.get('EMARE_5651_ORGANIZATION', 'Emare Security OS')
LAW5651_STAMP_EVERY = int(os.environ.get('EMARE_5651_STAMP_EVERY', '1'))
LAW5651_TSA_URL = os.environ.get('EMARE_5651_TSA_URL', '')
LAW5651_TSA_USERNAME = os.environ.get('EMARE_5651_TSA_USERNAME', '')
LAW5651_TSA_PASSWORD = os.environ.get('EMARE_5651_TSA_PASSWORD', '')
LAW5651_TSA_TIMEOUT = int(os.environ.get('EMARE_5651_TSA_TIMEOUT', '10'))
LAW5651_TSA_DRY_RUN = os.environ.get('EMARE_5651_TSA_DRY_RUN', '1') == '1'
LAW5651_TSA_CA_FILE = os.environ.get('EMARE_5651_TSA_CA_FILE', '')

# ── Rate Limit ──
RATE_LIMIT_PER_MINUTE = int(os.environ.get('EMARE_RATE_LIMIT', '30'))

# ── SSH ──
SSH_POOL_SIZE = int(os.environ.get('EMARE_SSH_POOL_SIZE', '5' if IS_ISP else '1'))
SSH_CONNECT_TIMEOUT = int(os.environ.get('EMARE_SSH_TIMEOUT', '10'))

# ── ISP Multi-Tenant ──
TENANT_MODE = os.environ.get('EMARE_TENANT_MODE', '1' if IS_ISP else '0') == '1'
ALERT_WEBHOOK_URL = os.environ.get('EMARE_ALERT_WEBHOOK', '')
SCHEDULER_ENABLED = os.environ.get('EMARE_SCHEDULER', '1' if IS_ISP else '0') == '1'
ISP_ADMIN_KEY = os.environ.get('EMARE_ISP_ADMIN_KEY') or secrets.token_hex(24)

# ── Çalışma özeti ──
def summary() -> dict:
    return {
        'mode': MODE,
        'cache': CACHE_BACKEND,
        'database': DB_BACKEND,
        'workers': WORKERS,
        'ssh_pool_size': SSH_POOL_SIZE,
        'rate_limit': RATE_LIMIT_PER_MINUTE,
        'redis_url': REDIS_URL if CACHE_BACKEND == 'redis' else None,
        'postgres_url': '***' if DB_BACKEND == 'postgres' else None,
        'sqlite_path': SQLITE_PATH if DB_BACKEND == 'sqlite' else None,
        'tenant_mode': TENANT_MODE,
        'scheduler': SCHEDULER_ENABLED,
        'law5651_enabled': LAW5651_ENABLED,
        'law5651_tsa_url': '***' if LAW5651_TSA_URL else None,
        'law5651_stamp_every': LAW5651_STAMP_EVERY,
    }
