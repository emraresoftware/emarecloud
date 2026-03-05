"""
EmareCloud — Organization Blueprint
Multi-tenant organizasyon CRUD ve yönetimi.
"""

from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from audit import log_action
from blockchain.service import blockchain_service
from core.tenant import check_quota, get_tenant_id, is_global_access
from extensions import db
from models import Organization, Plan, ResourceQuota, Subscription, User
from rbac import role_required

org_bp = Blueprint('org', __name__)


# ==================== ORGANİZASYON CRUD ====================

@org_bp.route('/api/organizations', methods=['GET'])
@login_required
@role_required('super_admin', 'admin')
def api_list_orgs():
    """Organizasyonları listeler. Super admin: tümü, admin: kendi org'u."""
    if is_global_access():
        orgs = Organization.query.order_by(Organization.created_at.desc()).all()
    else:
        org_id = get_tenant_id()
        if org_id:
            orgs = Organization.query.filter_by(id=org_id).all()
        else:
            orgs = []

    return jsonify({'success': True, 'organizations': [o.to_dict() for o in orgs]})


@org_bp.route('/api/organizations', methods=['POST'])
@login_required
@role_required('super_admin')
def api_create_org():
    """Yeni organizasyon oluşturur (sadece super_admin)."""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()

    if not name or len(name) < 2:
        return jsonify({'success': False, 'message': 'Organizasyon adı en az 2 karakter olmalı'}), 400

    slug = data.get('slug') or Organization.generate_slug(name)
    if Organization.query.filter_by(slug=slug).first():
        return jsonify({'success': False, 'message': 'Bu slug zaten kullanılıyor'}), 409

    org = Organization(
        name=name,
        slug=slug,
        owner_id=data.get('owner_id') or current_user.id,
        is_active=True,
        domain=data.get('domain'),
        logo_url=data.get('logo_url'),
    )
    db.session.add(org)
    db.session.flush()

    # Plan ve abonelik oluştur
    plan_name = data.get('plan', 'community')
    plan = Plan.query.filter_by(name=plan_name).first()
    if plan:
        sub = Subscription(
            org_id=org.id,
            plan_id=plan.id,
            status='active',
            billing_cycle=data.get('billing_cycle', 'monthly'),
        )
        db.session.add(sub)

        # Kaynak kotası
        quota = ResourceQuota(
            org_id=org.id,
            max_servers=plan.max_servers,
            max_users=plan.max_users,
            max_storage_gb=plan.max_storage_gb,
            max_backups=plan.max_backups,
        )
        db.session.add(quota)

    db.session.commit()

    log_action('org.create', target_type='organization', target_id=org.id,
              details={'name': name, 'slug': slug, 'plan': plan_name})
    return jsonify({
        'success': True,
        'message': 'Organizasyon oluşturuldu',
        'organization': org.to_dict(),
    })


@org_bp.route('/api/organizations/<int:org_id>', methods=['GET'])
@login_required
def api_get_org(org_id):
    """Organizasyon detayı."""
    org = db.session.get(Organization, org_id)
    if not org:
        return jsonify({'success': False, 'message': 'Organizasyon bulunamadı'}), 404

    # Yetki kontrolü
    if not is_global_access() and get_tenant_id() != org_id:
        return jsonify({'success': False, 'message': 'Bu organizasyona erişiminiz yok'}), 403

    result = org.to_dict()
    # Abonelik bilgisi
    sub = org.active_subscription
    result['subscription'] = sub.to_dict() if sub else None
    # Kota bilgisi
    quota = org.resource_quota
    result['quota'] = quota.to_dict() if quota else None

    return jsonify({'success': True, 'organization': result})


@org_bp.route('/api/organizations/<int:org_id>', methods=['PUT'])
@login_required
@role_required('super_admin')
def api_update_org(org_id):
    """Organizasyonu günceller."""
    org = db.session.get(Organization, org_id)
    if not org:
        return jsonify({'success': False, 'message': 'Organizasyon bulunamadı'}), 404

    data = request.get_json(silent=True) or {}
    changes = {}

    if 'name' in data:
        org.name = data['name']
        changes['name'] = data['name']
    if 'is_active' in data:
        org.is_active = bool(data['is_active'])
        changes['is_active'] = data['is_active']
    if 'domain' in data:
        org.domain = data['domain'] or None
        changes['domain'] = data['domain']
    if 'logo_url' in data:
        org.logo_url = data['logo_url'] or None
        changes['logo_url'] = data['logo_url']

    db.session.commit()
    log_action('org.update', target_type='organization', target_id=org_id, details=changes)
    return jsonify({'success': True, 'message': 'Organizasyon güncellendi', 'organization': org.to_dict()})


@org_bp.route('/api/organizations/<int:org_id>', methods=['DELETE'])
@login_required
@role_required('super_admin')
def api_delete_org(org_id):
    """Organizasyonu siler (sadece super_admin)."""
    org = db.session.get(Organization, org_id)
    if not org:
        return jsonify({'success': False, 'message': 'Organizasyon bulunamadı'}), 404

    if org.slug == 'default':
        return jsonify({'success': False, 'message': 'Varsayılan organizasyon silinemez'}), 400

    # Üyeleri org'dan çıkar
    User.query.filter_by(org_id=org_id).update({'org_id': None})

    name = org.name
    db.session.delete(org)
    db.session.commit()

    log_action('org.delete', target_type='organization', target_id=org_id,
              details={'name': name})
    return jsonify({'success': True, 'message': f'{name} silindi'})


# ==================== ORGANİZASYON ÜYELİK ====================

@org_bp.route('/api/organizations/<int:org_id>/members', methods=['GET'])
@login_required
def api_list_members(org_id):
    """Organizasyon üyelerini listeler."""
    if not is_global_access() and get_tenant_id() != org_id:
        return jsonify({'success': False, 'message': 'Erişim engellendi'}), 403

    members = User.query.filter_by(org_id=org_id).order_by(User.created_at.desc()).all()
    return jsonify({'success': True, 'members': [m.to_dict() for m in members]})


@org_bp.route('/api/organizations/<int:org_id>/members', methods=['POST'])
@login_required
@role_required('super_admin', 'admin')
def api_add_member(org_id):
    """Kullanıcıyı organizasyona ekler."""
    org = db.session.get(Organization, org_id)
    if not org:
        return jsonify({'success': False, 'message': 'Organizasyon bulunamadı'}), 404

    if not is_global_access() and get_tenant_id() != org_id:
        return jsonify({'success': False, 'message': 'Erişim engellendi'}), 403

    # Kota kontrolü
    ok, msg = check_quota(org_id, 'users')
    if not ok:
        return jsonify({'success': False, 'message': msg}), 403

    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id')
    user = db.session.get(User, user_id) if user_id else None
    if not user:
        return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı'}), 404

    user.org_id = org_id
    db.session.commit()

    log_action('org.add_member', target_type='organization', target_id=org_id,
              details={'user_id': user_id, 'username': user.username})
    return jsonify({'success': True, 'message': f'{user.username} eklendi'})


@org_bp.route('/api/organizations/<int:org_id>/members/<int:user_id>', methods=['DELETE'])
@login_required
@role_required('super_admin', 'admin')
def api_remove_member(org_id, user_id):
    """Kullanıcıyı organizasyondan çıkarır."""
    if not is_global_access() and get_tenant_id() != org_id:
        return jsonify({'success': False, 'message': 'Erişim engellendi'}), 403

    user = db.session.get(User, user_id)
    if not user or user.org_id != org_id:
        return jsonify({'success': False, 'message': 'Üye bulunamadı'}), 404

    user.org_id = None
    db.session.commit()

    log_action('org.remove_member', target_type='organization', target_id=org_id,
              details={'user_id': user_id, 'username': user.username})
    return jsonify({'success': True, 'message': f'{user.username} çıkarıldı'})


# ==================== PLAN & ABONELİK ====================

@org_bp.route('/api/plans', methods=['GET'])
def api_list_plans():
    """Tüm aktif planları listeler (public)."""
    plans = Plan.query.filter_by(is_active=True).order_by(Plan.sort_order).all()
    return jsonify({'success': True, 'plans': [p.to_dict() for p in plans]})


@org_bp.route('/api/organizations/<int:org_id>/subscription', methods=['GET'])
@login_required
def api_get_subscription(org_id):
    """Organizasyonun aktif aboneliğini döndürür."""
    if not is_global_access() and get_tenant_id() != org_id:
        return jsonify({'success': False, 'message': 'Erişim engellendi'}), 403

    org = db.session.get(Organization, org_id)
    if not org:
        return jsonify({'success': False, 'message': 'Organizasyon bulunamadı'}), 404

    sub = org.active_subscription
    return jsonify({
        'success': True,
        'subscription': sub.to_dict() if sub else None,
        'quota': org.resource_quota.to_dict() if org.resource_quota else None,
    })


@org_bp.route('/api/organizations/<int:org_id>/subscription', methods=['PUT'])
@login_required
@role_required('super_admin')
def api_update_subscription(org_id):
    """Abonelik planını değiştirir (super_admin)."""
    org = db.session.get(Organization, org_id)
    if not org:
        return jsonify({'success': False, 'message': 'Organizasyon bulunamadı'}), 404

    data = request.get_json(silent=True) or {}
    plan_name = data.get('plan')
    plan = Plan.query.filter_by(name=plan_name).first() if plan_name else None
    if not plan:
        return jsonify({'success': False, 'message': 'Geçersiz plan'}), 400

    # Eski aboneliği iptal et
    old_sub = org.active_subscription
    if old_sub:
        old_sub.status = 'cancelled'
        old_sub.cancelled_at = datetime.utcnow()

    # Yeni abonelik oluştur
    new_sub = Subscription(
        org_id=org_id,
        plan_id=plan.id,
        status='active',
        billing_cycle=data.get('billing_cycle', 'monthly'),
    )
    db.session.add(new_sub)

    # Kotaları güncelle
    quota = org.resource_quota
    if quota:
        quota.max_servers = plan.max_servers
        quota.max_users = plan.max_users
        quota.max_storage_gb = plan.max_storage_gb
        quota.max_backups = plan.max_backups
    else:
        quota = ResourceQuota(
            org_id=org_id,
            max_servers=plan.max_servers,
            max_users=plan.max_users,
            max_storage_gb=plan.max_storage_gb,
            max_backups=plan.max_backups,
        )
        db.session.add(quota)

    db.session.commit()

    log_action('org.plan_change', target_type='organization', target_id=org_id,
              details={'plan': plan_name})
    return jsonify({
        'success': True,
        'message': f'Plan {plan.display_name} olarak güncellendi',
        'subscription': new_sub.to_dict(),
    })


# ==================== TOKEN ÖDEMESİ İLE ABONELİK ====================

@org_bp.route('/api/organizations/<int:org_id>/subscription/token-pay', methods=['POST'])
@login_required
def api_token_pay_subscription(org_id):
    """
    EMARE Token ile abonelik planı satın alır.

    Request body:
        tx_hash: str          — Blockchain işlem hash'i
        plan_name: str        — community | professional | enterprise | reseller
        billing_cycle: str    — monthly | yearly
        wallet_address: str   — Ödeme yapan cüzdan adresi
    """
    # Yetki kontrolü — kendi org'una veya süper admin
    if not is_global_access() and get_tenant_id() != org_id:
        return jsonify({'success': False, 'message': 'Bu organizasyona erişim yetkiniz yok'}), 403

    org = db.session.get(Organization, org_id)
    if not org:
        return jsonify({'success': False, 'message': 'Organizasyon bulunamadı'}), 404

    data = request.get_json(silent=True) or {}
    tx_hash = (data.get('tx_hash') or '').strip()
    plan_name = (data.get('plan_name') or '').strip()
    billing_cycle = data.get('billing_cycle', 'monthly')
    wallet_address = (data.get('wallet_address') or '').strip()

    # Zorunlu alanlar
    if not tx_hash or not tx_hash.startswith('0x'):
        return jsonify({'success': False, 'message': 'Geçersiz tx_hash formatı (0x ile başlamalı)'}), 400
    if not wallet_address or not wallet_address.startswith('0x'):
        return jsonify({'success': False, 'message': 'Geçersiz wallet_address formatı'}), 400

    # Plan kontrol
    plan = Plan.query.filter_by(name=plan_name, is_active=True).first()
    if not plan:
        return jsonify({'success': False, 'message': f'Geçersiz plan: {plan_name}'}), 400

    if plan.name == 'community':
        return jsonify({'success': False, 'message': 'Community plan ücretsizdir, token ödemesi gerekmez'}), 400

    # Token miktarı belirle
    if billing_cycle == 'yearly':
        expected_amount = plan.price_token_yearly
    else:
        expected_amount = plan.price_token_monthly

    if expected_amount <= 0:
        return jsonify({'success': False, 'message': 'Bu plan için token fiyatı tanımlı değil'}), 400

    # Daha önce bu tx_hash kullanıldı mı?
    existing = Subscription.query.filter_by(token_tx_hash=tx_hash).first()
    if existing:
        return jsonify({'success': False, 'message': 'Bu işlem hash daha önce kullanıldı'}), 409

    # Blockchain entegrasyonu etkin mi?
    payment_address = blockchain_service.get_payment_address()

    if blockchain_service.is_available and payment_address:
        # On-chain doğrulama
        result = blockchain_service.verify_token_payment(
            tx_hash=tx_hash,
            expected_from=wallet_address,
            expected_to=payment_address,
            expected_amount_emare=expected_amount,
        )

        if not result['valid']:
            log_action('subscription.token_pay_failed', target_type='organization', target_id=org_id,
                      details={'reason': result['reason'], 'tx_hash': tx_hash, 'plan': plan_name})
            return jsonify({
                'success': False,
                'message': f'Ödeme doğrulanamadı: {result["reason"]}',
                'tx_hash': tx_hash,
            }), 400

        actual_amount = result['actual_amount']
    else:
        # Blockchain kapalıysa — dev/test modu: tx hash'i kabul et
        actual_amount = expected_amount

    # ---- Abonelik güncelle ----
    old_sub = org.active_subscription
    if old_sub:
        old_sub.status = 'cancelled'
        old_sub.cancelled_at = datetime.utcnow()

    # Süre hesapla
    now = datetime.utcnow()
    if billing_cycle == 'yearly':
        expires_at = now + timedelta(days=365)
    else:
        expires_at = now + timedelta(days=30)

    new_sub = Subscription(
        org_id=org_id,
        plan_id=plan.id,
        status='active',
        billing_cycle=billing_cycle,
        starts_at=now,
        expires_at=expires_at,
        payment_method='token',
        token_tx_hash=tx_hash,
        token_amount_paid=actual_amount,
        payer_wallet=wallet_address,
    )
    db.session.add(new_sub)

    # Kotaları güncelle
    quota = org.resource_quota
    if quota:
        quota.max_servers = plan.max_servers
        quota.max_users = plan.max_users
        quota.max_storage_gb = plan.max_storage_gb
        quota.max_backups = plan.max_backups
    else:
        quota = ResourceQuota(
            org_id=org_id,
            max_servers=plan.max_servers,
            max_users=plan.max_users,
            max_storage_gb=plan.max_storage_gb,
            max_backups=plan.max_backups,
        )
        db.session.add(quota)

    db.session.commit()

    log_action('subscription.token_payment', target_type='organization', target_id=org_id,
              details={
                  'plan': plan_name,
                  'billing_cycle': billing_cycle,
                  'amount': actual_amount,
                  'wallet': wallet_address,
                  'tx_hash': tx_hash,
              })

    return jsonify({
        'success': True,
        'message': f'✅ {plan.display_name} planı aktif edildi — {actual_amount:.1f} EMARE ödendi',
        'subscription': new_sub.to_dict(),
        'expires_at': expires_at.isoformat(),
        'token_amount': actual_amount,
    })


@org_bp.route('/api/token-payment/info', methods=['GET'])
@login_required
def api_token_payment_info():
    """Token ödeme için gerekli bilgileri döndürür (adres, token adresi, planlar)."""
    from flask import current_app

    payment_address = blockchain_service.get_payment_address()
    token_address = current_app.config.get('EMARE_TOKEN_ADDRESS', '')
    chain_id = current_app.config.get('BLOCKCHAIN_CHAIN_ID', 31337)
    rpc_url = current_app.config.get('BLOCKCHAIN_RPC_URL', '')
    blockchain_enabled = current_app.config.get('BLOCKCHAIN_ENABLED', False)

    plans = Plan.query.filter_by(is_active=True).order_by(Plan.sort_order).all()
    paid_plans = [
        {
            **p.to_dict(),
            'price_token_monthly': p.price_token_monthly,
            'price_token_yearly': p.price_token_yearly,
        }
        for p in plans
        if p.name != 'community'
    ]

    return jsonify({
        'success': True,
        'blockchain_enabled': blockchain_enabled,
        'payment_address': payment_address,
        'token_address': token_address,
        'chain_id': chain_id,
        'rpc_url': rpc_url,
        'plans': paid_plans,
        'note': 'Token transfer yaptıktan sonra tx_hash ile /api/organizations/{id}/subscription/token-pay endpoint\'ini çağırın',
    })
