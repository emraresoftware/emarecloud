"""
EmareCloud — Gunicorn Yapılandırması
Production deployment için optimize edilmiş ayarlar.
"""

import os

# Sunucu
bind = f"0.0.0.0:{os.environ.get('PORT', 5555)}"
workers = int(os.environ.get('GUNICORN_WORKERS', 2))
worker_class = 'geventwebsocket.gunicorn.workers.GeventWebSocketWorker'

# Timeout
timeout = 120
keepalive = 5
graceful_timeout = 30

# Logging
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('LOG_LEVEL', 'info')

# Güvenlik
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Performans
preload_app = True
max_requests = 1000
max_requests_jitter = 50
