"""
EmareCloud — Faz 5: 2FA (TOTP) Testleri
2FA kurulumu, doğrulama, kurtarma kodları, devre dışı bırakma.
"""


import pyotp


class TestTwoFactorSetup:
    """2FA kurulumu testleri."""

    def test_2fa_setup(self, auth_client):
        """2FA setup endpoint'i QR kod ve secret döndürmeli."""
        resp = auth_client.post('/api/2fa/setup')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'secret' in data
        assert 'qr_code' in data
        assert data['qr_code'].startswith('data:image/png;base64,')

    def test_2fa_enable(self, auth_client):
        """Doğru kod ile 2FA aktifleştirilebilmeli."""
        # Setup
        setup_resp = auth_client.post('/api/2fa/setup')
        secret = setup_resp.get_json()['secret']

        # Enable — doğru TOTP kodu
        totp = pyotp.TOTP(secret)
        code = totp.now()
        resp = auth_client.post('/api/2fa/enable', json={'code': code})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'recovery_codes' in data
        assert len(data['recovery_codes']) == 8

    def test_2fa_enable_wrong_code(self, auth_client):
        """Yanlış kod ile 2FA aktifleştirilemez."""
        auth_client.post('/api/2fa/setup')
        resp = auth_client.post('/api/2fa/enable', json={'code': '000000'})
        assert resp.status_code == 400

    def test_2fa_enable_without_setup(self, auth_client, app):
        """Setup yapılmadan 2FA aktifleştirilemez."""
        # User'ın totp_secret'ı temizle
        from models import User
        with app.app_context():
            user = User.query.filter_by(username='testadmin').first()
            user.totp_secret = None
            user.totp_enabled = False
            from extensions import db
            db.session.commit()

        resp = auth_client.post('/api/2fa/enable', json={'code': '123456'})
        assert resp.status_code == 400

    def test_2fa_double_enable(self, auth_client):
        """Zaten aktif 2FA tekrar aktifleştirilemez."""
        # Setup + Enable
        setup_resp = auth_client.post('/api/2fa/setup')
        secret = setup_resp.get_json()['secret']
        totp = pyotp.TOTP(secret)
        auth_client.post('/api/2fa/enable', json={'code': totp.now()})

        # Tekrar setup
        resp = auth_client.post('/api/2fa/setup')
        assert resp.status_code == 400

    def test_2fa_disable(self, auth_client):
        """2FA şifre doğrulaması ile devre dışı bırakılabilmeli."""
        # Setup + Enable
        setup_resp = auth_client.post('/api/2fa/setup')
        secret = setup_resp.get_json()['secret']
        totp = pyotp.TOTP(secret)
        auth_client.post('/api/2fa/enable', json={'code': totp.now()})

        # Disable
        resp = auth_client.post('/api/2fa/disable', json={
            'password': 'TestPass123!',
        })
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_2fa_disable_wrong_password(self, auth_client):
        """Yanlış şifre ile 2FA devre dışı bırakılamaz."""
        setup_resp = auth_client.post('/api/2fa/setup')
        secret = setup_resp.get_json()['secret']
        totp = pyotp.TOTP(secret)
        auth_client.post('/api/2fa/enable', json={'code': totp.now()})

        resp = auth_client.post('/api/2fa/disable', json={
            'password': 'WrongPass!',
        })
        assert resp.status_code == 400


class TestTwoFactorLogin:
    """2FA ile login flow testleri."""

    def test_login_redirects_to_2fa(self, app, client):
        """2FA aktif kullanıcı login'de 2FA sayfasına yönlendirilmeli."""
        from extensions import db
        from models import User

        with app.app_context():
            user = User.query.filter_by(username='testadmin').first()
            secret = pyotp.random_base32()
            user.totp_secret = secret
            user.totp_enabled = True
            db.session.commit()

        # Login dene
        client.get('/login')
        with client.session_transaction() as sess:
            csrf = sess.get('csrf_token', '')

        resp = client.post('/login', data={
            'username': 'testadmin',
            'password': 'TestPass123!',
            'csrf_token': csrf,
        })
        # 2FA sayfasına redirect olmalı
        assert resp.status_code == 302
        assert '/2fa/verify' in resp.headers.get('Location', '')

        # Temizle
        with app.app_context():
            user = User.query.filter_by(username='testadmin').first()
            user.totp_enabled = False
            user.totp_secret = None
            db.session.commit()

    def test_2fa_verify_page(self, app, client):
        """2FA doğrulama sayfası session'da user_id varken render olmalı."""
        with client.session_transaction() as sess:
            sess['_2fa_user_id'] = 1

        resp = client.get('/2fa/verify')
        assert resp.status_code == 200

    def test_2fa_verify_no_session(self, client):
        """Session'da user_id yoksa login'e yönlenmeli."""
        resp = client.get('/2fa/verify')
        assert resp.status_code == 302

    def test_2fa_verify_correct_code(self, app, client):
        """Doğru TOTP kodu ile giriş başarılı olmalı."""
        from extensions import db
        from models import User

        secret = pyotp.random_base32()
        with app.app_context():
            user = User.query.filter_by(username='testadmin').first()
            user.totp_secret = secret
            user.totp_enabled = True
            db.session.commit()
            user_id = user.id

        with client.session_transaction() as sess:
            sess['_2fa_user_id'] = user_id
            csrf = sess.get('csrf_token', '')

        totp = pyotp.TOTP(secret)
        resp = client.post('/2fa/verify', data={
            'code': totp.now(),
            'csrf_token': csrf,
        })
        assert resp.status_code == 302  # Dashboard'a redirect

        # Temizle
        with app.app_context():
            user = User.query.filter_by(username='testadmin').first()
            user.totp_enabled = False
            user.totp_secret = None
            db.session.commit()

    def test_2fa_verify_wrong_code(self, app, client):
        """Yanlış TOTP kodu reddedilmeli."""
        from extensions import db
        from models import User

        secret = pyotp.random_base32()
        with app.app_context():
            user = User.query.filter_by(username='testadmin').first()
            user.totp_secret = secret
            user.totp_enabled = True
            db.session.commit()
            user_id = user.id

        with client.session_transaction() as sess:
            sess['_2fa_user_id'] = user_id

        # CSRF token al
        client.get('/login')
        with client.session_transaction() as sess:
            sess['_2fa_user_id'] = user_id
            csrf = sess.get('csrf_token', '')

        resp = client.post('/2fa/verify', data={
            'code': '000000',
            'csrf_token': csrf,
        })
        assert resp.status_code == 200  # Sayfada kalmalı

        # Temizle
        with app.app_context():
            user = User.query.filter_by(username='testadmin').first()
            user.totp_enabled = False
            user.totp_secret = None
            db.session.commit()


class TestRecoveryCodes:
    """Kurtarma kodları testleri."""

    def test_recovery_codes_generated(self, app):
        """Kurtarma kodları doğru üretilmeli."""
        from extensions import db
        from models import User

        with app.app_context():
            user = User.query.filter_by(username='testadmin').first()
            codes = user.generate_recovery_codes(count=6)
            db.session.commit()
            assert len(codes) == 6
            assert all(len(c) == 8 for c in codes)

    def test_use_recovery_code(self, app):
        """Kurtarma kodu kullanılabilmeli ve listeden kaldırılmalı."""
        from extensions import db
        from models import User

        with app.app_context():
            user = User.query.filter_by(username='testadmin').first()
            codes = user.generate_recovery_codes(count=4)
            db.session.commit()

            code_to_use = codes[0]
            assert user.use_recovery_code(code_to_use) is True
            # Tekrar kullanılamaz
            assert user.use_recovery_code(code_to_use) is False

    def test_recovery_code_case_insensitive(self, app):
        """Kurtarma kodları büyük/küçük harf duyarsız olmalı."""
        from extensions import db
        from models import User

        with app.app_context():
            user = User.query.filter_by(username='testadmin').first()
            codes = user.generate_recovery_codes(count=3)
            db.session.commit()

            # Küçük harfle dene
            assert user.use_recovery_code(codes[0].lower()) is True

    def test_invalid_recovery_code(self, app):
        """Geçersiz kurtarma kodu reddedilmeli."""
        from extensions import db
        from models import User

        with app.app_context():
            user = User.query.filter_by(username='testadmin').first()
            user.generate_recovery_codes(count=3)
            db.session.commit()
            assert user.use_recovery_code('INVALID1') is False
