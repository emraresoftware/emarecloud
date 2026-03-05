"""
EmareCloud — Test Yapılandırması
pytest fixture'ları ve test yardımcıları.
"""

import os
import sys

import pytest

# Proje kökünü Python path'ine ekle
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from extensions import db as _db
from models import User

# ==================== YARDIMCI FONKSİYONLAR ====================

def _login(client, username, password):
    """CSRF token alıp login yapar. Session'ı başlatır."""
    # 1) GET /login → CSRF token session'a yazılır
    client.get('/login')
    # Session'dan CSRF token'ı al
    with client.session_transaction() as sess:
        csrf = sess.get('csrf_token', '')
    # 2) POST /login (CSRF token dahil)
    return client.post('/login', data={
        'username': username,
        'password': password,
        'csrf_token': csrf,
    }, follow_redirects=True)


def get_csrf(client):
    """Mevcut session'dan CSRF token'ı döndürür."""
    with client.session_transaction() as sess:
        return sess.get('csrf_token', '')


# ==================== FIXTURES ====================

@pytest.fixture
def app():
    """Test uygulaması — her test için izole in-memory SQLite."""
    flask_app, _ = create_app(config_overrides={
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
    })
    with flask_app.app_context():
        _db.create_all()

        # Test admin (super_admin)
        admin = User(
            username='testadmin',
            email='test@emarecloud.com',
            role='super_admin',
        )
        admin.set_password('TestPass123!')
        _db.session.add(admin)

        # Test admin (admin rolü)
        admin2 = User(
            username='testadmin2',
            email='admin2@emarecloud.com',
            role='admin',
        )
        admin2.set_password('TestPass123!')
        _db.session.add(admin2)

        # Test operator
        operator = User(
            username='testoperator',
            email='op@emarecloud.com',
            role='operator',
        )
        operator.set_password('TestPass123!')
        _db.session.add(operator)

        # Test read_only
        reader = User(
            username='testreader',
            email='reader@emarecloud.com',
            role='read_only',
        )
        reader.set_password('TestPass123!')
        _db.session.add(reader)

        _db.session.commit()
        yield flask_app
        _db.drop_all()


@pytest.fixture
def client(app):
    """Test HTTP istemcisi."""
    return app.test_client()


@pytest.fixture
def auth_client(app):
    """Oturum açmış super_admin test istemcisi — bağımsız client."""
    c = app.test_client()
    _login(c, 'testadmin', 'TestPass123!')
    return c


@pytest.fixture
def admin_client(app):
    """Oturum açmış admin test istemcisi — bağımsız client."""
    c = app.test_client()
    _login(c, 'testadmin2', 'TestPass123!')
    return c


@pytest.fixture
def operator_client(app):
    """Oturum açmış operator test istemcisi — bağımsız client."""
    c = app.test_client()
    _login(c, 'testoperator', 'TestPass123!')
    return c


@pytest.fixture
def reader_client(app):
    """Oturum açmış read_only test istemcisi — bağımsız client."""
    c = app.test_client()
    _login(c, 'testreader', 'TestPass123!')
    return c
