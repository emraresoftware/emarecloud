"""
Emare Security OS — WSGI üretim giriş noktası (Gunicorn)
=====================================================

Kullanım (standalone):
    gunicorn -w 1 -b 0.0.0.0:5555 wsgi:app

Kullanım (ISP — çoklu worker):
    EMARE_MODE=isp gunicorn -w 4 -k gevent -b 0.0.0.0:5555 wsgi:app
"""

from app import create_app

app = create_app()
