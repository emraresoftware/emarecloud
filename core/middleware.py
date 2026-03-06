"""
EmareCloud — Güvenlik Middleware
Gzip sıkıştırma + güvenlik header'ları + aktivite takibi.
"""

import gzip
from datetime import datetime

from flask import request
from flask_login import current_user


def register_middleware(app):
    """after_request middleware'lerini uygulamaya kaydeder."""

    @app.before_request
    def track_user_activity():
        """Giriş yapmış kullanıcının son görülme zamanını günceller."""
        if current_user.is_authenticated:
            now = datetime.utcnow()
            # Veritabanı yükünü azaltmak için sadece 60 saniyede bir güncelle
            if not current_user.last_seen or (now - current_user.last_seen).total_seconds() > 60:
                current_user.last_seen = now
                # Hangi sayfadaysa activity olarak kaydet
                path = request.path
                activity_map = {
                    '/dashboard': 'Dashboard',
                    '/market': 'Uygulama Pazarı',
                    '/datacenters': 'Veri Merkezi Yönetimi',
                    '/virtualization': 'Sanal Makine',
                    '/storage': 'Depolama',
                    '/monitoring': 'İzleme',
                    '/cloudflare': 'Cloudflare DNS',
                    '/terminal': 'Terminal',
                    '/server-map': 'Sunucu Haritası',
                    '/scoreboard': 'Geliştirici Panosu',
                    '/admin/users': 'Kullanıcı Yönetimi',
                    '/admin/panel': 'Admin Paneli',
                    '/admin/audit': 'Denetim Günlüğü',
                }
                activity = None
                for prefix, label in activity_map.items():
                    if path.startswith(prefix):
                        activity = label
                        break
                if path.startswith('/server/') and not activity:
                    activity = 'Sunucu Yönetimi'
                elif path.startswith('/ai-'):
                    activity = 'AI Araçları'
                elif path.startswith('/api/'):
                    activity = 'API Çağrısı'
                if activity:
                    current_user.current_activity = activity
                try:
                    from extensions import db
                    db.session.commit()
                except Exception:
                    pass

    @app.after_request
    def compress_response(response):
        """Gzip sıkıştırma."""
        if response.status_code < 200 or response.status_code >= 300:
            return response
        if 'Content-Encoding' in response.headers:
            return response
        if response.direct_passthrough:
            return response
        accept = request.headers.get('Accept-Encoding', '')
        if 'gzip' not in accept.lower():
            return response
        content_type = response.content_type or ''
        if not any(ct in content_type for ct in ['text/', 'application/json', 'application/javascript']):
            return response
        try:
            data = response.get_data()
        except RuntimeError:
            return response
        if len(data) < 500:
            return response
        compressed = gzip.compress(data, compresslevel=6)
        response.set_data(compressed)
        response.headers['Content-Encoding'] = 'gzip'
        response.headers['Content-Length'] = len(compressed)
        response.headers['Vary'] = 'Accept-Encoding'
        return response

    @app.after_request
    def add_security_headers(response):
        """Güvenlik ve cache header'ları."""
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if not app.debug:
            response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        if request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'public, max-age=86400'
        return response
