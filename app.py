"""
EmareCloud — Altyapı Yönetim Paneli
Multi-tenant, güvenli, ölçeklenebilir sunucu yönetim ürünü.
v1.0.0 — Secure Core Edition
"""

import logging
import os
import secrets

from flask import Flask, jsonify, redirect, request, session, url_for
from flask_login import current_user, login_user
from flask_socketio import SocketIO

from config import get_config

# Structured logging
from core.logging_config import setup_logging
from extensions import db, login_manager
from models import User


def create_app(config_overrides=None):
    """Uygulama factory fonksiyonu."""
    AppConfig = get_config()
    app = Flask(__name__)
    app.config.from_object(AppConfig)

    # Test veya özel yapılandırma
    if config_overrides:
        app.config.update(config_overrides)

    # Instance klasörünü oluştur (SQLite DB)
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance'), exist_ok=True)

    # Structured logging
    setup_logging(app)

    # Extension'ları başlat
    db.init_app(app)
    login_manager.init_app(app)

    # SocketIO — CORS kısıtlı
    allowed_origins = app.config.get('CORS_ALLOWED_ORIGINS', None)
    if app.debug and not allowed_origins:
        allowed_origins = '*'
    # gevent worker kullanıldığında async_mode='gevent' olmalı
    try:
        import gevent  # noqa: F401
        _async_mode = 'gevent'
    except ImportError:
        _async_mode = 'threading'
    socketio = SocketIO(
        app,
        cors_allowed_origins=allowed_origins,
        async_mode=_async_mode,
        ping_interval=25,          # 25s'de bir ping
        ping_timeout=60,           # 60s cevap gelmezse kes (Chrome freeze önlenir)
        max_http_buffer_size=10 * 1024 * 1024,  # 10MB
        logger=False,
        engineio_logger=False,
    )

    # User loader
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'success': False, 'message': 'Giriş yapmalısınız'}), 401
        return redirect(url_for('auth.login', next=request.url))

    # API Token auth — Bearer token ile oturum açma
    @app.before_request
    def authenticate_api_token():
        """API token ile gelen request'leri otomatik doğrular."""
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return
        # Zaten login olmuşsa geç
        if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
            return
        from datetime import datetime as dt

        from models import ApiToken
        raw_token = auth_header[7:]
        token = ApiToken.find_by_raw_token(raw_token)
        if token and token.is_active:
            # Süre kontrolü
            if token.expires_at and dt.utcnow() > token.expires_at:
                return
            user = db.session.get(User, token.user_id)
            if user and user.is_active:
                login_user(user, remember=False)
                token.last_used = dt.utcnow()
                db.session.commit()

    # CSRF koruması
    @app.before_request
    def ensure_csrf_token():
        if 'csrf_token' not in session:
            session['csrf_token'] = secrets.token_hex(32)

    @app.context_processor
    def inject_globals():
        return {
            'csrf_token': session.get('csrf_token', ''),
            'app_name': app.config.get('APP_NAME', 'EmareCloud'),
            'app_version': app.config.get('APP_VERSION', '1.0.0'),
        }

    # Middleware (gzip + güvenlik header'ları)
    from core.middleware import register_middleware
    register_middleware(app)

    # Tenant middleware (multi-tenant izolasyon)
    from core.tenant import register_tenant_middleware
    register_tenant_middleware(app)

    # Blueprint'leri kaydet
    from routes import register_blueprints
    register_blueprints(app)

    # SocketIO terminal event'leri
    from routes.terminal import register_terminal_events
    register_terminal_events(socketio)

    # Veritabanı başlatma
    from core.database import init_database
    init_database(app)

    # Blockchain servisi başlat (EmareToken ekosistemi)
    from blockchain.service import blockchain_service
    blockchain_service.init_app(app)

    # Reward Engine başlat (EP ödül motoru)
    from blockchain.reward_engine import reward_engine
    reward_engine.init_app(app, db)

    return app, socketio


# ===================== ANA GİRİŞ =====================

app, socketio = create_app()

if __name__ == '__main__':
    logger = logging.getLogger('emarecloud')
    logger.info("=" * 60)
    logger.info("  🏢 EmareCloud — Altyapı Yönetim Paneli")
    logger.info(f"  📍 http://localhost:{app.config.get('PORT', 5555)}")
    logger.info("  🔒 Auth: Aktif | RBAC: Aktif | Encryption: AES-256-GCM")
    logger.info("  📅 Monitoring: Aktif | Scheduler: Aktif")
    logger.info("=" * 60)

    # Background scheduler başlat
    from scheduler import start_scheduler
    start_scheduler(app)

    socketio.run(app, host='0.0.0.0', port=app.config.get('PORT', 5555),
                 debug=app.config.get('DEBUG', True))
