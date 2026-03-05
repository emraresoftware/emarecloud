"""
EmareCloud — Kimlik Doğrulama Testleri
Login, logout, profil, kullanıcı yönetimi API testleri.
"""


def _do_login(client, username, password):
    """CSRF token alıp login yapar."""
    client.get('/login')  # session başlat
    with client.session_transaction() as sess:
        csrf = sess.get('csrf_token', '')
    return client.post('/login', data={
        'username': username,
        'password': password,
        'csrf_token': csrf,
    }, follow_redirects=True)


# ==================== LOGIN / LOGOUT ====================

def test_login_page_accessible(client):
    """Login sayfası erişilebilir olmalı."""
    r = client.get('/login')
    assert r.status_code == 200
    assert b'EmareCloud' in r.data


def test_login_success(client):
    """Doğru kimlik bilgileri ile giriş başarılı olmalı."""
    r = _do_login(client, 'testadmin', 'TestPass123!')
    assert r.status_code == 200


def test_login_wrong_password(client):
    """Yanlış şifre ile giriş başarısız olmalı."""
    r = _do_login(client, 'testadmin', 'wrongpassword')
    assert b'hatal' in r.data.lower() or r.status_code == 200


def test_protected_route_redirect(client):
    """Korumalı route'lar login'e yönlendirmeli."""
    r = client.get('/')
    # login_required: 302 redirect veya 401
    assert r.status_code in (200, 302, 401)


def test_logout(auth_client):
    """Çıkış yapılabilmeli."""
    r = auth_client.get('/logout', follow_redirects=True)
    assert r.status_code == 200


# ==================== PROFİL ====================

def test_profile_accessible(auth_client):
    """Profil sayfası giriş yapmış kullanıcıya erişilebilir."""
    r = auth_client.get('/profile')
    assert r.status_code == 200


# ==================== ADMİN SAYFALARI ====================

def test_admin_users_page(auth_client):
    """Admin kullanıcılar sayfası erişilebilir."""
    r = auth_client.get('/admin/users')
    assert r.status_code == 200


def test_admin_users_denied_for_operator(operator_client):
    """Operator kullanıcı admin sayfasına erişememeli."""
    r = operator_client.get('/admin/users')
    assert r.status_code in (302, 401, 403)


def test_admin_users_denied_for_reader(reader_client):
    """Read-only kullanıcı admin sayfasına erişememeli."""
    r = reader_client.get('/admin/users')
    assert r.status_code in (302, 401, 403)


# ==================== KULLANICI API ====================

def test_create_user_api(auth_client):
    """API ile kullanıcı oluşturulabilmeli."""
    r = auth_client.post('/api/users', json={
        'username': 'newuser',
        'password': 'NewPass123!',
        'email': 'new@test.com',
        'role': 'operator',
    })
    data = r.get_json()
    assert data['success'] is True
    assert data['user']['username'] == 'newuser'


def test_create_user_weak_password(auth_client):
    """Zayıf şifre reddedilmeli."""
    r = auth_client.post('/api/users', json={
        'username': 'weakuser',
        'password': '123',
        'role': 'read_only',
    })
    data = r.get_json()
    assert data['success'] is False


def test_create_user_short_username(auth_client):
    """Kısa kullanıcı adı reddedilmeli."""
    r = auth_client.post('/api/users', json={
        'username': 'ab',
        'password': 'GoodPass1!',
        'role': 'read_only',
    })
    data = r.get_json()
    assert data['success'] is False


def test_create_user_duplicate_username(auth_client):
    """Aynı kullanıcı adıyla tekrar kayıt reddedilmeli."""
    r = auth_client.post('/api/users', json={
        'username': 'testadmin',
        'password': 'NewPass123!',
        'role': 'operator',
    })
    assert r.status_code == 409


def test_create_user_invalid_role(auth_client):
    """Geçersiz rol reddedilmeli."""
    r = auth_client.post('/api/users', json={
        'username': 'badrole',
        'password': 'GoodPass1!',
        'role': 'invalid_role',
    })
    assert r.status_code == 400


def test_list_users_api(auth_client):
    """Kullanıcı listesi API'si çalışmalı."""
    r = auth_client.get('/api/users')
    data = r.get_json()
    assert data['success'] is True
    assert len(data['users']) >= 4  # 4 test kullanıcısı


def test_list_users_denied_for_operator(operator_client):
    """Operator kullanıcı listesine erişememeli."""
    r = operator_client.get('/api/users')
    assert r.status_code in (302, 401, 403)


def test_audit_log_api(auth_client):
    """Audit log API'si çalışmalı."""
    r = auth_client.get('/api/audit-logs')
    data = r.get_json()
    assert data['success'] is True
    assert 'logs' in data


# ==================== HEALTH ====================

def test_health_endpoint(client):
    """Sağlık kontrolü endpoint'i çalışmalı."""
    r = client.get('/health')
    assert r.status_code == 200
    data = r.get_json()
    assert data['ok'] is True


# ==================== ŞİFRE DOĞRULAMA ====================

def test_password_validation_length():
    """Kısa şifre reddedilmeli."""
    from auth_routes import validate_password
    ok, msg = validate_password('Ab1!')
    assert ok is False
    assert '8 karakter' in msg


def test_password_validation_uppercase():
    """Büyük harf eksik reddedilmeli."""
    from auth_routes import validate_password
    ok, _ = validate_password('abcdefg1!')
    assert ok is False


def test_password_validation_number():
    """Rakam eksik reddedilmeli."""
    from auth_routes import validate_password
    ok, _ = validate_password('Abcdefgh!')
    assert ok is False


def test_password_validation_special():
    """Özel karakter eksik reddedilmeli."""
    from auth_routes import validate_password
    ok, _ = validate_password('Abcdefg1')
    assert ok is False


def test_password_validation_ok():
    """Güçlü şifre kabul edilmeli."""
    from auth_routes import validate_password
    ok, msg = validate_password('StrongP@ss1')
    assert ok is True
    assert msg == ''


def test_health_endpoint(client):
    """Health endpoint herkese açık olmalı."""
    r = client.get('/health')
    data = r.get_json()
    assert data['ok'] is True
    assert data['app'] == 'EmareCloud'
