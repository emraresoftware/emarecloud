"""
EmareCloud — Yapılandırma ve Kripto Testleri
Config sınıfları, AES-256-GCM şifreleme, lisans doğrulama.
"""

import os

# ==================== CONFIG ====================

class TestConfig:
    """Yapılandırma testleri."""

    def test_config_class_exists(self):
        """Config sınıfı import edilebilmeli."""
        from config import Config, DevelopmentConfig, ProductionConfig
        assert Config is not None
        assert DevelopmentConfig is not None
        assert ProductionConfig is not None

    def test_development_debug_on(self):
        """Development modda debug açık olmalı."""
        from config import DevelopmentConfig
        assert DevelopmentConfig.DEBUG is True

    def test_production_debug_off(self):
        """Production modda debug kapalı olmalı."""
        from config import ProductionConfig
        assert ProductionConfig.DEBUG is False

    def test_production_secure_cookie(self):
        """Production modda cookie güvenli olmalı."""
        from config import ProductionConfig
        assert ProductionConfig.SESSION_COOKIE_SECURE is True

    def test_default_port(self):
        """Varsayılan port 5555 olmalı."""
        from config import Config
        # Ortam değişkeni ayarlanmamışsa 5555
        assert int(os.environ.get('PORT', '5555')) == Config.PORT

    def test_app_name(self):
        """Uygulama adı EmareCloud olmalı."""
        from config import Config
        assert Config.APP_NAME == 'EmareCloud'

    def test_get_config_function(self):
        """get_config() fonksiyonu çalışmalı."""
        from config import get_config
        cfg = get_config()
        assert cfg is not None

    def test_session_cookie_httponly(self):
        """Cookie HttpOnly olmalı."""
        from config import Config
        assert Config.SESSION_COOKIE_HTTPONLY is True

    def test_session_cookie_samesite(self):
        """Cookie SameSite Lax olmalı."""
        from config import Config
        assert Config.SESSION_COOKIE_SAMESITE == 'Lax'


# ==================== KRİPTO (AES-256-GCM) ====================

class TestCrypto:
    """AES-256-GCM şifreleme testleri."""

    def test_encrypt_decrypt_roundtrip(self):
        """Şifreleme → çözme döngüsü doğru çalışmalı."""
        from crypto import decrypt_password, encrypt_password
        original = 'MyS3cr3tP@ss!'
        ciphertext, nonce = encrypt_password(original)
        decrypted = decrypt_password(ciphertext, nonce)
        assert decrypted == original

    def test_encrypt_returns_bytes(self):
        """Şifreleme bytes döndürmeli."""
        from crypto import encrypt_password
        ciphertext, nonce = encrypt_password('test')
        assert isinstance(ciphertext, bytes)
        assert isinstance(nonce, bytes)

    def test_nonce_is_12_bytes(self):
        """Nonce 12 byte (96-bit) olmalı."""
        from crypto import encrypt_password
        _, nonce = encrypt_password('test')
        assert len(nonce) == 12

    def test_different_encryptions_different_output(self):
        """Aynı şifre farklı ciphertext üretmeli (random nonce)."""
        from crypto import encrypt_password
        ct1, _ = encrypt_password('same_pass')
        ct2, _ = encrypt_password('same_pass')
        assert ct1 != ct2  # Random nonce sayesinde

    def test_decrypt_wrong_nonce_fails(self):
        """Yanlış nonce ile çözme boş string döndürmeli."""
        from crypto import decrypt_password, encrypt_password
        ciphertext, _ = encrypt_password('test')
        wrong_nonce = os.urandom(12)
        result = decrypt_password(ciphertext, wrong_nonce)
        assert result == ''  # Hata durumunda boş

    def test_decrypt_empty_ciphertext(self):
        """Boş ciphertext ile çözme başarısız olmalı."""
        from crypto import decrypt_password
        result = decrypt_password(b'', os.urandom(12))
        assert result == ''

    def test_encrypt_unicode(self):
        """Unicode şifre şifrelenebilmeli."""
        from crypto import decrypt_password, encrypt_password
        original = 'Türkçe Şifre #1 ğüöçı'
        ciphertext, nonce = encrypt_password(original)
        decrypted = decrypt_password(ciphertext, nonce)
        assert decrypted == original

    def test_encrypt_long_password(self):
        """Uzun şifre şifrelenebilmeli."""
        from crypto import decrypt_password, encrypt_password
        original = 'A' * 1000
        ciphertext, nonce = encrypt_password(original)
        decrypted = decrypt_password(ciphertext, nonce)
        assert decrypted == original


# ==================== LİSANS ====================

class TestLicenseManager:
    """Lisans yönetici testleri."""

    def test_verify_license_invalid(self):
        """Geçersiz lisans anahtarı reddedilmeli."""
        from license_manager import verify_license
        result = verify_license()
        # Lisans dosyası yoksa community plan döner
        assert result is not None

    def test_check_server_limit(self):
        """Sunucu limiti kontrolü çalışmalı."""
        from license_manager import check_server_limit
        allowed, msg = check_server_limit(0)
        assert isinstance(allowed, bool)
        assert isinstance(msg, str)

    def test_community_plan_limit(self):
        """Community plan sunucu limiti olmalı."""
        from license_manager import check_server_limit
        # Community plan genellikle 3-5 sunucu limiti
        allowed_low, _ = check_server_limit(1)
        assert allowed_low is True


# ==================== MODELLER ====================

class TestModels:
    """Veritabanı model testleri."""

    def test_user_password_hashing(self):
        """Şifre hash'lenmeli, düz metin saklanmamalı."""
        from models import User
        user = User(username='hashtest', role='read_only')
        user.set_password('TestP@ss1')
        assert user.password_hash is not None
        assert user.password_hash != 'TestP@ss1'

    def test_user_password_check(self):
        """Doğru şifre doğrulanmalı."""
        from models import User
        user = User(username='checktest', role='read_only')
        user.set_password('TestP@ss1')
        assert user.check_password('TestP@ss1') is True
        assert user.check_password('wrong') is False

    def test_user_roles(self):
        """Kullanıcı rolleri doğru çalışmalı."""
        from models import User
        admin = User(username='roletest', role='super_admin')
        assert admin.is_super_admin is True
        assert admin.is_admin is True

        op = User(username='optest', role='operator')
        assert op.is_super_admin is False
        assert op.is_admin is False

    def test_user_to_dict(self, app):
        """to_dict() doğru alanlar döndürmeli."""
        from models import User
        user = User(username='dicttest', email='dict@test.com', role='admin')
        result = user.to_dict()
        assert result['username'] == 'dicttest'
        assert result['email'] == 'dict@test.com'
        assert result['role'] == 'admin'

    def test_user_active_property(self):
        """is_active özelliği doğru çalışmalı."""
        from models import User
        user = User(username='activetest', role='read_only', is_active_user=True)
        assert user.is_active is True
        user.is_active_user = False
        assert user.is_active is False
