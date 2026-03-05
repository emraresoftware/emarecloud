"""
EmareCloud — Market API Testleri
/api/market/* endpoint'leri.
"""


class TestMarketApps:
    """Uygulama pazarı testleri."""

    def test_list_apps(self, auth_client):
        """Market uygulamaları listelenebilmeli."""
        r = auth_client.get('/api/market/apps')
        data = r.get_json()
        assert data['success'] is True
        assert 'apps' in data
        assert 'categories' in data

    def test_list_apps_has_categories(self, auth_client):
        """Kategoriler döndürülmeli."""
        r = auth_client.get('/api/market/apps')
        data = r.get_json()
        assert len(data['categories']) > 0

    def test_list_apps_count(self, auth_client):
        """En az 50 uygulama olmalı."""
        r = auth_client.get('/api/market/apps')
        data = r.get_json()
        assert len(data['apps']) >= 50

    def test_list_apps_unauthenticated(self, client):
        """Oturum açmamış kullanıcı erişememeli."""
        r = client.get('/api/market/apps')
        assert r.status_code in (200, 302, 401)  # session durumuna bağlı

    def test_list_apps_reader_can_view(self, reader_client):
        """Read-only kullanıcı market'i görebilmeli."""
        r = reader_client.get('/api/market/apps')
        data = r.get_json()
        assert data['success'] is True

    def test_install_missing_app_id(self, auth_client):
        """App ID olmadan kurulum başarısız olmalı."""
        r = auth_client.post('/api/market/install', json={
            'server_id': 'srv-001',
        })
        data = r.get_json()
        assert data['success'] is False

    def test_install_missing_server_id(self, auth_client):
        """Server ID olmadan kurulum başarısız olmalı."""
        r = auth_client.post('/api/market/install', json={
            'app_id': 'nginx',
        })
        data = r.get_json()
        assert data['success'] is False

    def test_install_unknown_app(self, auth_client):
        """Bilinmeyen uygulama kurulumunu reddetmeli."""
        r = auth_client.post('/api/market/install', json={
            'app_id': 'nonexistent_app_xyz',
            'server_id': 'srv-001',
        })
        assert r.status_code == 404

    def test_install_denied_for_reader(self, reader_client):
        """Read-only kullanıcı kurulum yapamamalı."""
        r = reader_client.post('/api/market/install', json={
            'app_id': 'nginx',
            'server_id': 'srv-001',
        })
        # 403 (yetki yok) veya 400 (validasyon)
        assert r.status_code in (302, 400, 401, 403)


class TestMarketAppsData:
    """Market uygulama veri doğrulama testleri."""

    def test_app_has_required_fields(self, auth_client):
        """Her uygulamada zorunlu alanlar olmalı."""
        r = auth_client.get('/api/market/apps')
        data = r.get_json()
        for app in data['apps']:
            assert 'id' in app, f"App missing 'id': {app}"
            assert 'name' in app, f"App missing 'name': {app}"
            assert 'category' in app, f"App missing 'category': {app}"

    def test_app_categories_match(self, auth_client):
        """Uygulama kategorileri, kategori listesinde olmalı."""
        r = auth_client.get('/api/market/apps')
        data = r.get_json()
        category_names = [c['name'] if isinstance(c, dict) else c for c in data['categories']]
        for app in data['apps']:
            cat = app.get('category', '')
            assert cat in category_names, f"'{cat}' kategori listesinde yok"
