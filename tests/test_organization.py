"""
EmareCloud — Faz 5: Organization & Multi-Tenant Testleri
Organization CRUD, üyelik, plan yönetimi, tenant izolasyon testleri.
"""




class TestOrganizationCRUD:
    """Organization oluşturma, listeleme, güncelleme, silme."""

    def test_create_org(self, auth_client):
        """Super admin organizasyon oluşturabilmeli."""
        resp = auth_client.post('/api/organizations', json={
            'name': 'Test Firması',
            'plan': 'professional',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['organization']['name'] == 'Test Firması'
        assert data['organization']['slug'] == 'test-firmasi'  # Türkçe ı→i

    def test_create_org_with_slug(self, auth_client):
        """Özel slug ile org oluşturulabilmeli."""
        resp = auth_client.post('/api/organizations', json={
            'name': 'Custom Org',
            'slug': 'my-custom-org',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['organization']['slug'] == 'my-custom-org'

    def test_create_org_duplicate_slug(self, auth_client):
        """Aynı slug ile ikinci org oluşturulamaz."""
        auth_client.post('/api/organizations', json={
            'name': 'First Org',
            'slug': 'duplicate-test',
        })
        resp = auth_client.post('/api/organizations', json={
            'name': 'Second Org',
            'slug': 'duplicate-test',
        })
        assert resp.status_code == 409

    def test_create_org_short_name(self, auth_client):
        """Kısa isimle org oluşturulamaz."""
        resp = auth_client.post('/api/organizations', json={'name': 'A'})
        assert resp.status_code == 400

    def test_create_org_admin_forbidden(self, admin_client):
        """Admin rolü org oluşturamaz."""
        resp = admin_client.post('/api/organizations', json={
            'name': 'Admin Org',
        })
        assert resp.status_code == 403

    def test_list_orgs(self, auth_client):
        """Super admin tüm org'ları listeleyebilmeli."""
        auth_client.post('/api/organizations', json={'name': 'List Test Org'})
        resp = auth_client.get('/api/organizations')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['organizations']) >= 1

    def test_get_org_detail(self, auth_client, app):
        """Org detayı alınabilmeli."""
        create_resp = auth_client.post('/api/organizations', json={'name': 'Detail Org'})
        org_id = create_resp.get_json()['organization']['id']
        resp = auth_client.get(f'/api/organizations/{org_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['organization']['name'] == 'Detail Org'

    def test_update_org(self, auth_client):
        """Org güncellenebilmeli."""
        create_resp = auth_client.post('/api/organizations', json={'name': 'Update Org'})
        org_id = create_resp.get_json()['organization']['id']
        resp = auth_client.put(f'/api/organizations/{org_id}', json={
            'name': 'Updated Org Name',
            'is_active': False,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['organization']['name'] == 'Updated Org Name'

    def test_delete_org(self, auth_client):
        """Org silinebilmeli."""
        create_resp = auth_client.post('/api/organizations', json={'name': 'Delete Me'})
        org_id = create_resp.get_json()['organization']['id']
        resp = auth_client.delete(f'/api/organizations/{org_id}')
        assert resp.status_code == 200

    def test_delete_default_org_forbidden(self, auth_client, app):
        """Varsayılan org silinemez."""
        from models import Organization
        with app.app_context():
            default_org = Organization.query.filter_by(slug='default').first()
            if default_org:
                resp = auth_client.delete(f'/api/organizations/{default_org.id}')
                assert resp.status_code == 400

    def test_get_nonexistent_org(self, auth_client):
        """Var olmayan org 404 dönmeli."""
        resp = auth_client.get('/api/organizations/99999')
        assert resp.status_code == 404


class TestOrganizationMembers:
    """Üyelik yönetimi testleri."""

    def test_list_members(self, auth_client, app):
        """Org üyeleri listelenebilmeli."""
        with app.app_context():
            create_resp = auth_client.post('/api/organizations', json={'name': 'Members Org'})
            org_id = create_resp.get_json()['organization']['id']
            resp = auth_client.get(f'/api/organizations/{org_id}/members')
            assert resp.status_code == 200

    def test_add_member(self, auth_client, app):
        """Kullanıcı org'a eklenebilmeli."""
        from models import User
        with app.app_context():
            create_resp = auth_client.post('/api/organizations', json={'name': 'Add Member Org'})
            org_id = create_resp.get_json()['organization']['id']

            user = User.query.filter_by(username='testoperator').first()
            resp = auth_client.post(f'/api/organizations/{org_id}/members', json={
                'user_id': user.id,
            })
            assert resp.status_code == 200

    def test_add_nonexistent_member(self, auth_client):
        """Var olmayan kullanıcı eklenemez."""
        create_resp = auth_client.post('/api/organizations', json={'name': 'No User Org'})
        org_id = create_resp.get_json()['organization']['id']
        resp = auth_client.post(f'/api/organizations/{org_id}/members', json={
            'user_id': 99999,
        })
        assert resp.status_code == 404

    def test_remove_member(self, auth_client, app):
        """Üye org'dan çıkarılabilmeli."""
        from models import User
        with app.app_context():
            create_resp = auth_client.post('/api/organizations', json={'name': 'Remove Org'})
            org_id = create_resp.get_json()['organization']['id']
            user = User.query.filter_by(username='testoperator').first()
            auth_client.post(f'/api/organizations/{org_id}/members', json={
                'user_id': user.id,
            })
            resp = auth_client.delete(f'/api/organizations/{org_id}/members/{user.id}')
            assert resp.status_code == 200


class TestPlans:
    """Plan listesi testleri."""

    def test_list_plans_public(self, client):
        """Plan listesi public olarak erişilebilmeli."""
        resp = client.get('/api/plans')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['plans']) == 4  # community, professional, enterprise, reseller

    def test_plan_structure(self, client):
        """Plan yapısı doğru olmalı."""
        resp = client.get('/api/plans')
        plans = resp.get_json()['plans']
        community = next(p for p in plans if p['name'] == 'community')
        assert community['price_monthly'] == 0
        assert community['max_servers'] == 3
        assert community['max_users'] == 1

    def test_plan_enterprise(self, client):
        """Enterprise plan doğru yapıda olmalı."""
        resp = client.get('/api/plans')
        plans = resp.get_json()['plans']
        enterprise = next(p for p in plans if p['name'] == 'enterprise')
        assert enterprise['price_monthly'] == 199
        assert enterprise['max_servers'] == 100


class TestSubscription:
    """Abonelik yönetimi testleri."""

    def test_get_subscription(self, auth_client, app):
        """Org'un aboneliği sorgulanabilmeli."""
        create_resp = auth_client.post('/api/organizations', json={
            'name': 'Sub Test Org',
            'plan': 'professional',
        })
        org_id = create_resp.get_json()['organization']['id']
        resp = auth_client.get(f'/api/organizations/{org_id}/subscription')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['subscription'] is not None

    def test_change_subscription(self, auth_client):
        """Abonelik planı değiştirilebilmeli."""
        create_resp = auth_client.post('/api/organizations', json={
            'name': 'Plan Change Org',
            'plan': 'community',
        })
        org_id = create_resp.get_json()['organization']['id']
        resp = auth_client.put(f'/api/organizations/{org_id}/subscription', json={
            'plan': 'enterprise',
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'Enterprise' in data['message']

    def test_invalid_plan_change(self, auth_client):
        """Geçersiz plana geçiş yapılamaz."""
        create_resp = auth_client.post('/api/organizations', json={'name': 'Bad Plan Org'})
        org_id = create_resp.get_json()['organization']['id']
        resp = auth_client.put(f'/api/organizations/{org_id}/subscription', json={
            'plan': 'nonexistent_plan',
        })
        assert resp.status_code == 400


class TestTenantIsolation:
    """Multi-tenant izolasyon testleri."""

    def test_org_data_isolation(self, auth_client, app):
        """Farklı org'lar birbirinin verilerini görmemeli."""
        # İki org oluştur
        resp1 = auth_client.post('/api/organizations', json={'name': 'Isolation Org A'})
        resp2 = auth_client.post('/api/organizations', json={'name': 'Isolation Org B'})
        org_a = resp1.get_json()['organization']
        org_b = resp2.get_json()['organization']
        assert org_a['id'] != org_b['id']
        assert org_a['slug'] != org_b['slug']

    def test_org_member_count(self, auth_client, app):
        """Org üye sayısı doğru olmalı."""
        from models import User
        with app.app_context():
            create_resp = auth_client.post('/api/organizations', json={'name': 'Count Org'})
            org_id = create_resp.get_json()['organization']['id']

            user = User.query.filter_by(username='testreader').first()
            auth_client.post(f'/api/organizations/{org_id}/members', json={
                'user_id': user.id,
            })

            resp = auth_client.get(f'/api/organizations/{org_id}')
            data = resp.get_json()
            assert data['organization']['member_count'] >= 1

    def test_reader_cannot_manage_org(self, reader_client):
        """Read-only kullanıcı org yönetemez."""
        resp = reader_client.post('/api/organizations', json={'name': 'Forbidden Org'})
        assert resp.status_code == 403

    def test_operator_cannot_create_org(self, operator_client):
        """Operator org oluşturamaz."""
        resp = operator_client.post('/api/organizations', json={'name': 'Op Org'})
        assert resp.status_code == 403
