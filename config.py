"""
EmareCloud — Uygulama Yapılandırması
Ortam değişkenlerinden yapılandırma yükler.
"""

import os
from datetime import timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    """Ana yapılandırma sınıfı."""

    # Temel
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32).hex()
    APP_NAME = 'EmareCloud'
    APP_VERSION = '1.0.0'

    # Veritabanı
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'emarecloud.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Şifreleme
    MASTER_KEY = os.environ.get('MASTER_KEY')  # AES-256 master key

    # Oturum
    PERMANENT_SESSION_LIFETIME = timedelta(hours=int(os.environ.get('SESSION_LIFETIME_HOURS', '8')))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'

    # Rate Limiting
    RATE_LIMIT_LOGIN = int(os.environ.get('RATE_LIMIT_LOGIN', '5'))   # dakikada max
    RATE_LIMIT_API = int(os.environ.get('RATE_LIMIT_API', '60'))

    # SSH
    SSH_TIMEOUT = int(os.environ.get('SSH_TIMEOUT', '10'))
    MAX_CONCURRENT_CONNECTIONS = int(os.environ.get('MAX_CONCURRENT_CONNECTIONS', '5'))

    # Sunucu
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', '5555'))
    DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

    # CORS — SocketIO için izin verilen origin'ler
    # Virgülle ayrılmış: "https://panel.example.com,https://admin.example.com"
    _cors_raw = os.environ.get('CORS_ALLOWED_ORIGINS', '')
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_raw.split(',') if o.strip()] or None

    # ==================== BLOCKCHAIN (EmareToken) ====================
    BLOCKCHAIN_ENABLED = os.environ.get('BLOCKCHAIN_ENABLED', 'false').lower() == 'true'
    BLOCKCHAIN_RPC_URL = os.environ.get('BLOCKCHAIN_RPC_URL', '')  # BSC: https://bsc-dataseed.binance.org
    BLOCKCHAIN_CHAIN_ID = int(os.environ.get('BLOCKCHAIN_CHAIN_ID', '97'))  # 97=BSC Testnet, 56=BSC Mainnet, 31337=Local
    EMARE_TOKEN_ADDRESS = os.environ.get('EMARE_TOKEN_ADDRESS', '')
    EMARE_REWARD_POOL_ADDRESS = os.environ.get('EMARE_REWARD_POOL_ADDRESS', '')
    EMARE_MARKETPLACE_ADDRESS = os.environ.get('EMARE_MARKETPLACE_ADDRESS', '')
    EMARE_SETTLEMENT_ADDRESS = os.environ.get('EMARE_SETTLEMENT_ADDRESS', '')
    BLOCKCHAIN_ORACLE_PRIVATE_KEY = os.environ.get('BLOCKCHAIN_ORACLE_PRIVATE_KEY', '')  # RewardPool oracle
    # Ödeme alıcı adres (deployer/fee collector — abonelik ödemeleri buraya gelir)
    EMARE_PAYMENT_ADDRESS = os.environ.get('EMARE_PAYMENT_ADDRESS', '')

    # ==================== CLOUDFLARE ====================
    CLOUDFLARE_API_TOKEN = os.environ.get('CLOUDFLARE_API_TOKEN', '')
    CLOUDFLARE_ZONE_ID = os.environ.get('CLOUDFLARE_ZONE_ID', '')

    # Varsayılan admin (ilk kurulumda)
    DEFAULT_ADMIN_USERNAME = os.environ.get('DEFAULT_ADMIN_USERNAME', 'admin')
    DEFAULT_ADMIN_PASSWORD = os.environ.get('DEFAULT_ADMIN_PASSWORD')
    DEFAULT_ADMIN_EMAIL = os.environ.get('DEFAULT_ADMIN_EMAIL', 'admin@emarecloud.com')


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'true').lower() == 'true'


_config_map = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': Config,
}


def get_config():
    env = os.environ.get('FLASK_ENV', 'development')
    return _config_map.get(env, Config)
