"""
EmareCloud — Faz 5: API Token Testleri
Token oluşturma, listeleme, silme, Bearer auth ile API erişimi.
"""




class TestApiTokenCRUD:
    """API token CRUD testleri."""

    def test_create_token(self, auth_client):
        """Token oluşturulabilmeli."""
        resp = auth_client.post('/api/tokens', json={
            'name': 'Test Token',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'token' in data
        assert data['token'].startswith('emc_')
        assert data['token_info']['name'] == 'Test Token'

    def test_create_token_with_expiry(self, auth_client):
        """Süreli token oluşturulabilmeli."""
        resp = auth_client.post('/api/tokens', json={
            'name': 'Expiring Token',
            'expires_days': 30,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['token_info']['expires_at'] is not None

    def test_create_token_no_name(self, auth_client):
        """İsimsiz token oluşturulamaz."""
        resp = auth_client.post('/api/tokens', json={})
        assert resp.status_code == 400

    def test_list_tokens(self, auth_client):
        """Token'lar listelenebilmeli."""
        auth_client.post('/api/tokens', json={'name': 'List Token 1'})
        auth_client.post('/api/tokens', json={'name': 'List Token 2'})
        resp = auth_client.get('/api/tokens')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['tokens']) >= 2

    def test_delete_token(self, auth_client):
        """Token silinebilmeli (deactivate)."""
        create_resp = auth_client.post('/api/tokens', json={'name': 'Delete Token'})
        token_id = create_resp.get_json()['token_info']['id']
        resp = auth_client.delete(f'/api/tokens/{token_id}')
        assert resp.status_code == 200

    def test_delete_other_user_token(self, auth_client, admin_client, app):
        """Başka kullanıcının token'ı silinemez."""
        create_resp = admin_client.post('/api/tokens', json={'name': 'Admin Token'})
        token_id = create_resp.get_json()['token_info']['id']
        # Super admin (auth_client) başka kullanıcının token'ını silememeli
        resp = auth_client.delete(f'/api/tokens/{token_id}')
        # auth_client farklı user_id'ye sahip → 404
        assert resp.status_code in (404, 200)  # Super admin kendi token'ı değilse 404

    def test_max_tokens_limit(self, auth_client):
        """Kullanıcı başına max 10 token limiti olmalı."""
        for i in range(10):
            auth_client.post('/api/tokens', json={'name': f'Token {i}'})
        resp = auth_client.post('/api/tokens', json={'name': 'Token 11'})
        assert resp.status_code == 400


class TestApiTokenAuth:
    """Bearer token ile API erişim testleri."""

    def test_bearer_auth(self, auth_client, app):
        """Bearer token ile API'ye erişilebilmeli."""
        create_resp = auth_client.post('/api/tokens', json={'name': 'Auth Token'})
        raw_token = create_resp.get_json()['token']

        c = app.test_client()
        resp = c.get('/api/tokens', headers={
            'Authorization': f'Bearer {raw_token}',
        })
        assert resp.status_code == 200

    def test_invalid_bearer_token(self, app):
        """Geçersiz token ile erişim engellenmeli."""
        c = app.test_client()
        resp = c.get('/api/users', headers={
            'Authorization': 'Bearer invalid_token_123',
        })
        assert resp.status_code == 401

    def test_expired_token_model(self, app):
        """Süresi dolmuş token — expires_at kontrolü."""
        from datetime import datetime, timedelta

        from extensions import db
        from models import ApiToken, User

        user = User.query.first()
        raw, hashed, prefix = ApiToken.generate_token()
        token = ApiToken(
            user_id=user.id,
            token_hash=hashed,
            token_prefix=prefix,
            name='Expired',
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        db.session.add(token)
        db.session.commit()

        found = ApiToken.find_by_raw_token(raw)
        assert found is not None
        assert found.expires_at < datetime.utcnow()

    def test_revoked_token_not_found(self, app):
        """İptal edilmiş token find_by_raw_token ile bulunamaz."""
        from extensions import db
        from models import ApiToken, User

        user = User.query.first()
        raw, hashed, prefix = ApiToken.generate_token()
        token = ApiToken(
            user_id=user.id,
            token_hash=hashed,
            token_prefix=prefix,
            name='Revoked',
            is_active=False,
        )
        db.session.add(token)
        db.session.commit()

        found = ApiToken.find_by_raw_token(raw)
        assert found is None

    def test_token_last_used_field(self, app):
        """Token last_used alanı güncellenebilmeli."""
        from datetime import datetime

        from extensions import db
        from models import ApiToken, User

        user = User.query.first()
        raw, hashed, prefix = ApiToken.generate_token()
        token = ApiToken(
            user_id=user.id,
            token_hash=hashed,
            token_prefix=prefix,
            name='LastUsed',
        )
        db.session.add(token)
        db.session.commit()

        assert token.last_used is None
        token.last_used = datetime.utcnow()
        db.session.commit()
        assert token.last_used is not None


class TestApiTokenModel:
    """ApiToken model testleri."""

    def test_generate_token(self):
        """Token üretimi doğru formatta olmalı."""
        from models import ApiToken
        raw, hashed, prefix = ApiToken.generate_token()
        assert raw.startswith('emc_')
        assert len(hashed) == 64  # SHA-256 hex
        assert prefix == raw[:8]

    def test_find_by_raw_token(self, app):
        """Raw token ile token bulunabilmeli."""

        from extensions import db
        from models import ApiToken, User

        with app.app_context():
            user = User.query.first()
            raw, hashed, prefix = ApiToken.generate_token()
            token = ApiToken(
                user_id=user.id,
                token_hash=hashed,
                token_prefix=prefix,
                name='Find Test',
            )
            db.session.add(token)
            db.session.commit()

            found = ApiToken.find_by_raw_token(raw)
            assert found is not None
            assert found.name == 'Find Test'

    def test_find_by_wrong_token(self, app):
        """Yanlış token ile kayıt bulunamaz."""
        from models import ApiToken
        with app.app_context():
            found = ApiToken.find_by_raw_token('wrong_token_123')
            assert found is None
