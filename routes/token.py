"""
EmareCloud — Token & Blockchain API Route'ları
EMARE token ekosistemiyle etkileşim endpoint'leri.
"""

import logging

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from audit import log_action
from rbac import permission_required

logger = logging.getLogger('emarecloud.routes.token')

token_bp = Blueprint('token', __name__)


# ==================== TOKEN BİLGİ ====================

@token_bp.route('/api/token/info', methods=['GET'])
@login_required
def token_info():
    """EMARE token genel bilgilerini döndürür."""
    from blockchain.service import blockchain_service

    if not blockchain_service.is_available:
        return jsonify({
            'success': False,
            'message': 'Blockchain servisi aktif değil',
            'data': {
                'enabled': False,
                'name': 'EmareToken',
                'symbol': 'EMARE',
                'info_url': 'https://emarecloud.com/token',
            }
        }), 200

    info = blockchain_service.get_token_info()
    if not info:
        return jsonify({'success': False, 'message': 'Token bilgileri alınamadı'}), 503

    return jsonify({'success': True, 'data': info})


@token_bp.route('/api/token/balance', methods=['GET'])
@login_required
def token_balance():
    """Mevcut kullanıcının EMARE token bakiyesini döndürür."""
    from blockchain.service import blockchain_service
    from models import UserWallet

    wallet = UserWallet.query.filter_by(user_id=current_user.id, is_primary=True).first()
    if not wallet:
        return jsonify({
            'success': False,
            'message': 'Cüzdan bağlanmamış',
            'data': {'has_wallet': False},
        }), 200

    if not blockchain_service.is_available:
        return jsonify({
            'success': True,
            'data': {
                'has_wallet': True,
                'wallet_address': wallet.wallet_address,
                'balance': None,
                'blockchain_offline': True,
            }
        })

    balance = blockchain_service.get_token_balance(wallet.wallet_address)
    return jsonify({
        'success': True,
        'data': {
            'has_wallet': True,
            'wallet_address': wallet.wallet_address,
            'balance': str(balance) if balance is not None else None,
            'symbol': 'EMARE',
        }
    })


# ==================== CÜZDAN YÖNETİMİ ====================

@token_bp.route('/api/wallet/connect', methods=['POST'])
@login_required
def connect_wallet():
    """Kullanıcıya cüzdan adresi bağlar."""
    from extensions import db
    from models import UserWallet

    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'JSON body gerekli'}), 400

    wallet_address = data.get('wallet_address', '').strip()
    if not wallet_address or len(wallet_address) != 42 or not wallet_address.startswith('0x'):
        return jsonify({'success': False, 'message': 'Geçersiz cüzdan adresi (0x... 42 karakter)'}), 400

    # Aynı adres başka kullanıcıda mı?
    existing = UserWallet.query.filter_by(wallet_address=wallet_address.lower()).first()
    if existing and existing.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Bu cüzdan başka bir hesaba bağlı'}), 409

    # Mevcut birincil cüzdanı kaldır
    UserWallet.query.filter_by(user_id=current_user.id, is_primary=True).update({'is_primary': False})

    # Yeni cüzdan ekle veya güncelle
    wallet = UserWallet.query.filter_by(user_id=current_user.id, wallet_address=wallet_address.lower()).first()
    if wallet:
        wallet.is_primary = True
    else:
        wallet = UserWallet(
            user_id=current_user.id,
            wallet_address=wallet_address.lower(),
            is_primary=True,
            org_id=getattr(current_user, 'org_id', None),
        )
        db.session.add(wallet)

    db.session.commit()

    log_action('wallet_connected', target_type='wallet', target_id=wallet_address)
    logger.info(f"Cüzdan bağlandı: user={current_user.username}, wallet={wallet_address}")

    # Blockchain'e kaydet (RewardPool)
    from blockchain.service import blockchain_service
    if blockchain_service.is_available:
        try:
            blockchain_service.register_user_on_chain(wallet_address)
        except Exception as e:
            logger.warning(f"On-chain kayıt başarısız (devam ediyor): {e}")

    return jsonify({
        'success': True,
        'message': 'Cüzdan başarıyla bağlandı',
        'data': wallet.to_dict(),
    })


@token_bp.route('/api/wallet/disconnect', methods=['POST'])
@login_required
def disconnect_wallet():
    """Kullanıcının birincil cüzdanını kaldırır."""
    from extensions import db
    from models import UserWallet

    wallet = UserWallet.query.filter_by(user_id=current_user.id, is_primary=True).first()
    if not wallet:
        return jsonify({'success': False, 'message': 'Bağlı cüzdan yok'}), 404

    wallet.is_primary = False
    db.session.commit()

    log_action('wallet_disconnected', target_type='wallet', target_id=wallet.wallet_address)
    return jsonify({'success': True, 'message': 'Cüzdan bağlantısı kaldırıldı'})


@token_bp.route('/api/wallet/list', methods=['GET'])
@login_required
def list_wallets():
    """Kullanıcının tüm cüzdanlarını listeler."""
    from models import UserWallet
    wallets = UserWallet.query.filter_by(user_id=current_user.id).all()
    return jsonify({
        'success': True,
        'data': [w.to_dict() for w in wallets],
    })


# ==================== EP (EMARE PUANI) ====================

@token_bp.route('/api/ep/summary', methods=['GET'])
@login_required
def ep_summary():
    """Kullanıcının Emare Puanı (EP) özetini döndürür."""
    from blockchain.reward_engine import reward_engine
    summary = reward_engine.get_user_ep_summary(current_user.id)
    return jsonify({'success': True, 'data': summary})


@token_bp.route('/api/ep/history', methods=['GET'])
@login_required
def ep_history():
    """Kullanıcının EP kazanım geçmişini döndürür."""
    from models import EmarePoint

    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    query = EmarePoint.query.filter_by(user_id=current_user.id)\
        .order_by(EmarePoint.created_at.desc())

    total = query.count()
    records = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify({
        'success': True,
        'data': [r.to_dict() for r in records],
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': (total + per_page - 1) // per_page,
        }
    })


# ==================== REWARD POOL ====================

@token_bp.route('/api/reward-pool/info', methods=['GET'])
@login_required
def reward_pool_info():
    """RewardPool kontrat bilgilerini döndürür."""
    from blockchain.service import blockchain_service

    if not blockchain_service.is_available:
        return jsonify({'success': False, 'message': 'Blockchain servisi aktif değil'}), 200

    info = blockchain_service.get_reward_pool_info()
    if not info:
        return jsonify({'success': False, 'message': 'RewardPool bilgileri alınamadı'}), 503

    return jsonify({'success': True, 'data': info})


@token_bp.route('/api/reward-pool/user', methods=['GET'])
@login_required
def reward_pool_user():
    """Kullanıcının on-chain ödül verilerini döndürür."""
    from blockchain.service import blockchain_service
    from models import UserWallet

    wallet = UserWallet.query.filter_by(user_id=current_user.id, is_primary=True).first()
    if not wallet:
        return jsonify({'success': False, 'message': 'Cüzdan bağlanmamış'}), 200

    if not blockchain_service.is_available:
        return jsonify({'success': False, 'message': 'Blockchain servisi aktif değil'}), 200

    info = blockchain_service.get_user_reward_info(wallet.wallet_address)
    return jsonify({'success': True, 'data': info})


# ==================== MARKETPLACE (ON-CHAIN) ====================

@token_bp.route('/api/token-marketplace/stats', methods=['GET'])
@login_required
def marketplace_stats():
    """On-chain marketplace istatistiklerini döndürür."""
    from blockchain.service import blockchain_service

    if not blockchain_service.is_available:
        return jsonify({'success': False, 'message': 'Blockchain servisi aktif değil'}), 200

    stats = blockchain_service.get_marketplace_stats()
    return jsonify({'success': True, 'data': stats})


@token_bp.route('/api/token-marketplace/product/<int:product_id>', methods=['GET'])
@login_required
def marketplace_product(product_id):
    """On-chain marketplace ürün detayını döndürür."""
    from blockchain.service import blockchain_service

    if not blockchain_service.is_available:
        return jsonify({'success': False, 'message': 'Blockchain servisi aktif değil'}), 200

    product = blockchain_service.get_marketplace_product(product_id)
    if not product:
        return jsonify({'success': False, 'message': 'Ürün bulunamadı'}), 404

    return jsonify({'success': True, 'data': product})


# ==================== SETTLEMENT (ESCROW) ====================

@token_bp.route('/api/settlement/order/<int:order_id>', methods=['GET'])
@login_required
def settlement_order(order_id):
    """Escrow sipariş durumunu döndürür."""
    from blockchain.service import blockchain_service

    if not blockchain_service.is_available:
        return jsonify({'success': False, 'message': 'Blockchain servisi aktif değil'}), 200

    order = blockchain_service.get_settlement_order(order_id)
    if not order:
        return jsonify({'success': False, 'message': 'Sipariş bulunamadı'}), 404

    return jsonify({'success': True, 'data': order})


@token_bp.route('/api/settlement/stats', methods=['GET'])
@login_required
@permission_required('admin_panel')
def settlement_stats():
    """Settlement genel istatistiklerini döndürür (admin)."""
    from blockchain.service import blockchain_service

    if not blockchain_service.is_available:
        return jsonify({'success': False, 'message': 'Blockchain servisi aktif değil'}), 200

    stats = blockchain_service.get_settlement_stats()
    return jsonify({'success': True, 'data': stats})


# ==================== ADMIN ====================

@token_bp.route('/api/admin/blockchain/status', methods=['GET'])
@login_required
@permission_required('admin_panel')
def blockchain_status():
    """Blockchain entegrasyon durumunu döndürür (admin)."""
    from blockchain.service import blockchain_service

    data = {
        'enabled': blockchain_service._config.get('enabled', False),
        'connected': blockchain_service.is_available,
        'chain_id': blockchain_service._config.get('chain_id'),
        'contracts': {
            'token': bool(blockchain_service._config.get('token_address')),
            'reward_pool': bool(blockchain_service._config.get('reward_pool_address')),
            'marketplace': bool(blockchain_service._config.get('marketplace_address')),
            'settlement': bool(blockchain_service._config.get('settlement_address')),
        },
    }

    return jsonify({'success': True, 'data': data})
