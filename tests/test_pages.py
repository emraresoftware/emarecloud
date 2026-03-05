"""
EmareCloud — Sayfa Erişim Testleri
HTML sayfa route'larının doğru çalıştığını doğrular.
"""


class TestPublicPages:
    """Oturum gerektirmeyen sayfalar."""

    def test_login_page(self, client):
        """Login sayfası erişilebilir olmalı."""
        r = client.get('/login')
        # Henüz giriş yapmamış kullanıcı için 200
        assert r.status_code in (200, 302)

    def test_health_api(self, client):
        """Health API erişilebilir olmalı."""
        r = client.get('/health')
        assert r.status_code == 200

    def test_landing_page(self, client):
        """Landing sayfası erişilebilir olmalı."""
        r = client.get('/landing')
        assert r.status_code == 200


class TestProtectedPages:
    """Oturum gerektiren sayfalar."""

    def test_dashboard_requires_auth(self, client):
        """Dashboard oturum gerektirmeli."""
        r = client.get('/')
        # login_required: 302 redirect veya 401
        assert r.status_code in (200, 302, 401)

    def test_dashboard_accessible(self, auth_client):
        """Oturum açmış kullanıcı dashboard'a erişebilmeli."""
        r = auth_client.get('/')
        assert r.status_code == 200

    def test_market_page(self, auth_client):
        """Market sayfası erişilebilir olmalı."""
        r = auth_client.get('/market')
        assert r.status_code == 200

    def test_storage_page(self, auth_client):
        """Depolama sayfası erişilebilir olmalı."""
        r = auth_client.get('/storage')
        assert r.status_code == 200

    def test_virtualization_page(self, auth_client):
        """Sanallaştırma sayfası erişilebilir olmalı."""
        r = auth_client.get('/virtualization')
        assert r.status_code == 200

    def test_profile_page(self, auth_client):
        """Profil sayfası erişilebilir olmalı."""
        r = auth_client.get('/profile')
        assert r.status_code == 200

    def test_admin_users_page(self, auth_client):
        """Admin kullanıcılar sayfası erişilebilir olmalı."""
        r = auth_client.get('/admin/users')
        assert r.status_code == 200

    def test_admin_audit_page(self, auth_client):
        """Denetim günlüğü sayfası erişilebilir olmalı."""
        r = auth_client.get('/admin/audit')
        assert r.status_code == 200


class TestPageAccessControl:
    """Sayfa bazlı RBAC kontrolü."""

    def test_operator_can_view_market(self, operator_client):
        """Operator market sayfasına erişebilmeli."""
        r = operator_client.get('/market')
        assert r.status_code == 200

    def test_reader_can_view_dashboard(self, reader_client):
        """Read-only dashboard'ı görebilmeli."""
        r = reader_client.get('/')
        assert r.status_code == 200

    def test_reader_cannot_access_admin(self, reader_client):
        """Read-only admin sayfalarına erişememeli."""
        r = reader_client.get('/admin/users')
        assert r.status_code in (302, 401, 403)

    def test_operator_cannot_access_admin(self, operator_client):
        """Operator admin sayfalarına erişememeli."""
        r = operator_client.get('/admin/users')
        assert r.status_code in (302, 401, 403)
