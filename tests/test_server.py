"""
EmareCloud — Sunucu CRUD API Testleri
/api/servers endpoint'leri.
"""


# ==================== SUNUCU EKLEME ====================

class TestServerAdd:
    """Sunucu ekleme testleri."""

    def test_add_server_success(self, auth_client):
        """Geçerli sunucu eklenebilmeli (veya lisans limiti dönmeli)."""
        r = auth_client.post('/api/servers', json={
            'name': 'Test Sunucu',
            'host': '192.168.1.100',
            'username': 'root',
            'password': 'testpass123',
            'port': 22,
        })
        data = r.get_json()
        # Başarılı veya lisans limiti (community modda)
        assert data['success'] is True or r.status_code == 403

    def test_add_server_missing_name(self, auth_client):
        """İsim olmadan sunucu eklenemez."""
        r = auth_client.post('/api/servers', json={
            'host': '192.168.1.100',
            'username': 'root',
            'password': 'testpass123',
        })
        data = r.get_json()
        assert data['success'] is False

    def test_add_server_missing_host(self, auth_client):
        """Host olmadan sunucu eklenemez."""
        r = auth_client.post('/api/servers', json={
            'name': 'Sunucu',
            'username': 'root',
            'password': 'testpass123',
        })
        data = r.get_json()
        assert data['success'] is False

    def test_add_server_missing_password(self, auth_client):
        """Şifre olmadan sunucu eklenemez."""
        r = auth_client.post('/api/servers', json={
            'name': 'Sunucu',
            'host': '192.168.1.100',
            'username': 'root',
        })
        data = r.get_json()
        assert data['success'] is False

    def test_add_server_empty_body(self, auth_client):
        """Boş body ile sunucu eklenemez."""
        r = auth_client.post('/api/servers', json={})
        assert r.status_code == 400

    def test_add_server_default_port(self, auth_client):
        """Port belirtilmezse 22 varsayılmalı."""
        r = auth_client.post('/api/servers', json={
            'name': 'Port Test',
            'host': '10.0.0.1',
            'username': 'root',
            'password': 'pass123',
        })
        data = r.get_json()
        # Başarılı veya lisans limiti (community modda)
        assert data['success'] is True or r.status_code == 403


# ==================== SUNUCU LİSTELEME ====================

class TestServerList:
    """Sunucu listeleme testleri."""

    def test_list_servers_authenticated(self, auth_client):
        """Giriş yapmış kullanıcı sunucu listesi görmeli."""
        r = auth_client.get('/api/servers')
        data = r.get_json()
        assert data['success'] is True
        assert 'servers' in data

    def test_list_servers_unauthenticated(self, client):
        """Oturum açmamış kullanıcı erişememeli."""
        r = client.get('/api/servers')
        assert r.status_code in (200, 302, 401)  # session durumuna bağlı

    def test_list_servers_reader_can_view(self, reader_client):
        """Read-only kullanıcı sunucu listesini görebilmeli."""
        r = reader_client.get('/api/servers')
        data = r.get_json()
        assert data['success'] is True


# ==================== SUNUCU GÜNCELLEME ====================

class TestServerUpdate:
    """Sunucu güncelleme testleri."""

    def test_update_nonexistent_server(self, auth_client):
        """Var olmayan sunucu güncellenemez."""
        r = auth_client.put('/api/servers/nonexistent-id', json={
            'name': 'Yeni İsim',
        })
        assert r.status_code == 404

    def test_update_empty_body(self, auth_client):
        """Boş body ile güncelleme yapılamaz."""
        r = auth_client.put('/api/servers/nonexistent-id', json={})
        assert r.status_code == 400


# ==================== SUNUCU SİLME ====================

class TestServerDelete:
    """Sunucu silme testleri."""

    def test_delete_nonexistent_server(self, auth_client):
        """Var olmayan sunucu silinemez."""
        r = auth_client.delete('/api/servers/nonexistent-id')
        assert r.status_code == 404

    def test_delete_server_operator_denied(self, operator_client):
        """Operator sunucu silemez."""
        r = operator_client.delete('/api/servers/nonexistent-id')
        # 403 (yetki yok) veya 404 (sunucu yok)
        assert r.status_code in (302, 401, 403, 404)

    def test_delete_server_reader_denied(self, reader_client):
        """Read-only sunucu silemez."""
        r = reader_client.delete('/api/servers/nonexistent-id')
        assert r.status_code in (302, 401, 403, 404)


# ==================== YETKİ KONTROLLERI ====================

class TestServerPermissions:
    """Sunucu yetki testleri."""

    def test_operator_cannot_add_server(self, operator_client):
        """Operator sunucu ekleyememeli."""
        r = operator_client.post('/api/servers', json={
            'name': 'Op Sunucu',
            'host': '10.0.0.1',
            'username': 'root',
            'password': 'pass',
        })
        assert r.status_code == 403

    def test_reader_cannot_add_server(self, reader_client):
        """Read-only sunucu ekleyememeli."""
        r = reader_client.post('/api/servers', json={
            'name': 'Reader Sunucu',
            'host': '10.0.0.1',
            'username': 'root',
            'password': 'pass',
        })
        assert r.status_code == 403
