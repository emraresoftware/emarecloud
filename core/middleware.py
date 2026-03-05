"""
EmareCloud — Güvenlik Middleware
Gzip sıkıştırma + güvenlik header'ları.
"""

import gzip

from flask import request


def register_middleware(app):
    """after_request middleware'lerini uygulamaya kaydeder."""

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
