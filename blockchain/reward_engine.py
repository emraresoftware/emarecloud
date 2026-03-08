"""
EmareCloud — Ödül Motoru (Reward Engine)
Kullanıcı aksiyonlarına göre EP (Emare Puanı) hesaplayan ve
RewardPool kontratına oracle claim gönderen modül.

EP Kazanım Modelleri:
  A) Cashback — Cloud harcamalarına göre EMR geri ödeme
  B) Marketplace — Dijital ürün satışından EP
  C) Useful Work — Doğrulanmış iş karşılığı EP (sunucu izleme, template paylaşımı vb.)
"""

import logging
from datetime import datetime

logger = logging.getLogger('emarecloud.blockchain.rewards')

# ==================== EP KAZANIM TABLOLARI ====================

# Aksiyon bazlı EP ödül miktarları
EP_REWARDS = {
    # Cashback modeli — ödeme/abonelik bazlı
    'subscription_payment': 100,     # Plan ödemesi başına 100 EP
    'marketplace_purchase': 50,      # Market uygulama satın alma başına 50 EP
    'resource_upgrade': 75,          # Kaynak yükseltme başına 75 EP

    # Useful Work modeli — platform katkısı
    'server_added': 20,              # Yeni sunucu ekleme
    'template_shared': 200,          # Template paylaşma (marketplace'e)
    'bug_report': 50,                # Doğrulanmış hata raporu
    'uptime_99_monthly': 150,        # Aylık %99+ uptime başarımı
    'monitoring_alert_setup': 10,    # Alarm kuralı oluşturma
    'backup_configured': 15,         # Yedekleme profili oluşturma

    # AI / Yapay Zeka ödülleri
    'ai_app_installed': 30,          # AI uygulaması kurulumu
    'stack_builder_used': 50,        # Stack Builder ile paket kurulumu
    'ai_stack_completed': 100,       # AI stack paketini tamamen kurma
    'ai_assistant_used': 5,          # AI Terminal Asistanı kullanımı
    'app_published_market': 300,     # Kendi uygulamasını markete yayınlama
    'ai_model_deployed': 75,         # AI model deploy etme (Ollama, SD vb.)

    # Referral / Sosyal
    'referral_signup': 500,          # Referans ile gelen yeni kullanıcı
    'referral_paid': 1000,           # Referans kullanıcı ödeme yaptığında

    # Marketplace (satıcı tarafı)
    'product_listed': 30,            # Yeni ürün listeleme
    'product_sale': 100,             # Her satış başına
    'five_star_review': 25,          # 5 yıldız aldığında
}

# Günlük EP kazanım limiti (abuse önleme)
DAILY_EP_LIMIT = 5000

# Anti-fraud: Aynı aksiyonun tekrarı için cooldown (saniye)
ACTION_COOLDOWNS = {
    'server_added': 300,             # 5 dakika
    'template_shared': 3600,         # 1 saat
    'product_listed': 600,           # 10 dakika
    'ai_app_installed': 120,         # 2 dakika
    'ai_assistant_used': 30,         # 30 saniye
    'stack_builder_used': 300,       # 5 dakika
}


class RewardEngine:
    """
    EP kazanım ve dağıtım motoru.

    Kullanım:
        from blockchain.reward_engine import reward_engine
        reward_engine.award_ep(user_id=1, action='server_added')
    """

    def __init__(self):
        self._db = None

    def init_app(self, app, db):
        """Flask uygulamasıyla entegre eder."""
        self._db = db

    def award_ep(self, user_id: int, action: str, metadata: dict = None) -> dict | None:
        """
        Kullanıcıya EP ödülü verir.

        Args:
            user_id: Kullanıcı ID
            action: Aksiyon adı (EP_REWARDS tablosundan)
            metadata: Ek bilgi (tx_hash, product_id vb.)

        Returns:
            {'ep_awarded': int, 'total_ep': int, 'action': str} veya None
        """
        if action not in EP_REWARDS:
            logger.warning(f"Tanımsız EP aksiyonu: {action}")
            return None

        if not self._db:
            logger.error("RewardEngine veritabanı bağlantısı yok")
            return None

        from models import EmarePoint

        ep_amount = EP_REWARDS[action]

        # Günlük limit kontrolü
        today_total = EmarePoint.get_daily_total(user_id)
        if today_total + ep_amount > DAILY_EP_LIMIT:
            logger.warning(f"Günlük EP limiti aşıldı: user={user_id}, bugün={today_total}")
            return None

        # Cooldown kontrolü
        if action in ACTION_COOLDOWNS:
            last_action = EmarePoint.get_last_action(user_id, action)
            if last_action:
                elapsed = (datetime.utcnow() - last_action.created_at).total_seconds()
                if elapsed < ACTION_COOLDOWNS[action]:
                    logger.info(f"EP cooldown: user={user_id}, action={action}, kalan={ACTION_COOLDOWNS[action] - elapsed:.0f}s")
                    return None

        # EP kaydı oluştur
        import json
        ep_record = EmarePoint(
            user_id=user_id,
            action=action,
            ep_amount=ep_amount,
            claim_type=self._get_claim_type(action),
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        )
        self._db.session.add(ep_record)
        self._db.session.commit()

        new_total = EmarePoint.get_total_ep(user_id)
        logger.info(f"⭐ EP ödülü: user={user_id}, action={action}, ep={ep_amount}, toplam={new_total}")

        return {
            'ep_awarded': ep_amount,
            'total_ep': new_total,
            'action': action,
            'claim_type': ep_record.claim_type,
        }

    def _get_claim_type(self, action: str) -> str:
        """Aksiyon adından claim tipini belirler."""
        cashback_actions = {'subscription_payment', 'marketplace_purchase', 'resource_upgrade'}
        marketplace_actions = {'product_listed', 'product_sale', 'five_star_review'}
        ai_actions = {'ai_app_installed', 'stack_builder_used', 'ai_stack_completed',
                      'ai_assistant_used', 'app_published_market', 'ai_model_deployed'}

        if action in cashback_actions:
            return 'cashback'
        if action in marketplace_actions:
            return 'marketplace'
        if action in ai_actions:
            return 'ai_work'
        return 'work'

    def process_pending_claims(self) -> int:
        """
        Bekleyen EP'leri toplar ve RewardPool kontratına oracle claim gönderir.
        Scheduler tarafından periyodik çağrılır.

        Returns:
            İşlenen claim sayısı
        """
        from blockchain.service import blockchain_service
        from models import EmarePoint, UserWallet

        if not blockchain_service.is_available:
            return 0

        # Unclaimed EP'leri olan kullanıcıları bul
        unclaimed = EmarePoint.get_unclaimed_users()
        processed = 0

        for user_id, total_ep in unclaimed:
            wallet = UserWallet.query.filter_by(user_id=user_id, is_primary=True).first()
            if not wallet:
                continue

            # Oracle claim gönder
            tx_hash = blockchain_service.oracle_claim_reward(
                user_address=wallet.wallet_address,
                ep_amount=total_ep,
                claim_type='cashback',  # Dominant tip
            )

            if tx_hash:
                EmarePoint.mark_claimed(user_id, tx_hash)
                processed += 1
                logger.info(f"⛓️  EP claim işlendi: user={user_id}, ep={total_ep}, tx={tx_hash}")

        return processed

    def get_user_ep_summary(self, user_id: int) -> dict:
        """Kullanıcının EP özetini döndürür."""
        from models import EmarePoint
        return {
            'total_ep': EmarePoint.get_total_ep(user_id),
            'unclaimed_ep': EmarePoint.get_unclaimed_ep(user_id),
            'claimed_ep': EmarePoint.get_claimed_ep(user_id),
            'daily_earned': EmarePoint.get_daily_total(user_id),
            'daily_limit': DAILY_EP_LIMIT,
            'ep_rewards_table': EP_REWARDS,
        }


# Singleton instance
reward_engine = RewardEngine()
