"""
EmareCloud — Veritabanı Başlatma
İlk kurulum, migrasyon ve varsayılan admin oluşturma.
"""

import json
import logging
import os
import uuid

from extensions import db
from models import AppSetting, Organization, Plan, ResourceQuota, ServerCredential, Subscription, User

logger = logging.getLogger('emarecloud.database')

CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config.json')


def init_database(app):
    """Veritabanını oluştur, varsayılan admin oluştur, config.json'dan veri aktar."""
    with app.app_context():
        db.create_all()

        # Varsayılan admin oluştur
        if not User.query.first():
            admin_pw = app.config.get('DEFAULT_ADMIN_PASSWORD') or 'admin123'
            admin = User(
                username=app.config.get('DEFAULT_ADMIN_USERNAME', 'admin'),
                email=app.config.get('DEFAULT_ADMIN_EMAIL', 'admin@emarecloud.com'),
                role='super_admin',
            )
            admin.set_password(admin_pw)
            db.session.add(admin)
            db.session.commit()
            logger.info("=" * 60)
            logger.info("  🏢 EmareCloud — Secure Core Edition v1.0.0")
            logger.info("=" * 60)
            logger.info("  ✅ Varsayılan admin oluşturuldu")
            logger.info(f"  👤 Kullanıcı: {admin.username}")
            logger.info(f"  🔑 Şifre: {admin_pw}")
            logger.warning("  ⚠️  İlk girişte şifrenizi DEĞİŞTİRİN!")
            logger.info("=" * 60)

        # config.json'dan sunucuları DB'ye aktar
        if not ServerCredential.query.first():
            _migrate_servers_from_config(app)

        # Ayarları aktar
        if not AppSetting.query.first():
            _migrate_settings_from_config()

        # Varsayılan planları oluştur
        if not Plan.query.first():
            _create_default_plans()

        # Varsayılan organizasyonu oluştur
        if not Organization.query.first():
            _create_default_org()


def _migrate_servers_from_config(app):
    """config.json'daki sunucuları veritabanına aktarır (şifreler AES-256 ile şifrelenir)."""
    if not os.path.exists(CONFIG_FILE):
        return
    try:
        with open(CONFIG_FILE, encoding='utf-8') as f:
            config = json.load(f)
        servers = config.get('servers', [])
        if not servers:
            return
        for s in servers:
            srv = ServerCredential(
                id=s.get('id', f"srv-{uuid.uuid4().hex[:6]}"),
                name=s.get('name', ''),
                host=s.get('host', ''),
                port=int(s.get('port', 22)),
                username=s.get('username', 'root'),
                group_name=s.get('group', 'Genel'),
                description=s.get('description', ''),
                tags=json.dumps(s.get('tags', [])),
                role=s.get('role', ''),
                location=s.get('location', ''),
                installed_at=s.get('installed_at', ''),
                responsible=s.get('responsible', ''),
                os_planned=s.get('os_planned', ''),
            )
            password = s.get('password', '')
            if password:
                srv.set_password(password)
            db.session.add(srv)
        db.session.commit()
        logger.info(f"  ✅ {len(servers)} sunucu config.json'dan DB'ye aktarıldı (AES-256 şifreli)")

        # config.json'dan şifreleri temizle
        for s in config.get('servers', []):
            s['password'] = '*** encrypted in database ***'
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        logger.info("  🔒 config.json'daki düz metin şifreler temizlendi")
    except Exception as e:
        logger.error(f"  ⚠️  Sunucu aktarımı hatası: {e}")
        db.session.rollback()


def _migrate_settings_from_config():
    """config.json'daki ayarları veritabanına aktarır."""
    if not os.path.exists(CONFIG_FILE):
        return
    try:
        with open(CONFIG_FILE, encoding='utf-8') as f:
            config = json.load(f)
        for key, value in config.get('settings', {}).items():
            s = AppSetting(key=key, value=json.dumps(value))
            db.session.add(s)
        db.session.commit()
    except Exception:
        db.session.rollback()


def _create_default_plans():
    """Varsayılan fiyatlandırma planlarını oluşturur."""
    # Token fiyatları: 1 EMARE ≈ $0.1 — USD * 10 = EMARE/ay
    plans = [
        Plan(
            name='community', display_name='Community',
            price_monthly=0, price_yearly=0,
            price_token_monthly=0, price_token_yearly=0,
            max_servers=3, max_users=1, max_storage_gb=10, max_backups=3,
            features_json=json.dumps([
                'Temel sunucu yönetimi', '3 sunucu limiti',
                'Topluluk desteği', 'Temel izleme',
            ]),
            sort_order=0,
        ),
        Plan(
            name='professional', display_name='Professional',
            price_monthly=49, price_yearly=490,
            price_token_monthly=490, price_token_yearly=4900,
            max_servers=25, max_users=5, max_storage_gb=100, max_backups=10,
            features_json=json.dumps([
                'Gelişmiş sunucu yönetimi', '25 sunucu',
                'E-posta desteği', 'Gelişmiş izleme',
                'Otomatik yedekleme', 'Alarm sistemi',
                'EMARE Token ödemesi',
            ]),
            sort_order=1,
        ),
        Plan(
            name='enterprise', display_name='Enterprise',
            price_monthly=199, price_yearly=1990,
            price_token_monthly=1990, price_token_yearly=19900,
            max_servers=100, max_users=25, max_storage_gb=500, max_backups=50,
            features_json=json.dumps([
                'Sınırsız sunucu yönetimi', '100 sunucu',
                'Öncelikli destek', 'AI izleme',
                'Otomatik yedekleme', 'Alarm + webhook',
                'API erişimi', 'Docker yönetimi',
                'EMARE Token ödemesi (%10 indirim)',
            ]),
            sort_order=2,
        ),
        Plan(
            name='reseller', display_name='Reseller',
            price_monthly=499, price_yearly=4990,
            price_token_monthly=4990, price_token_yearly=49900,
            max_servers=500, max_users=100, max_storage_gb=2000, max_backups=200,
            features_json=json.dumps([
                'White-label panel', '500 sunucu',
                'Bayi paneli', 'Alt müşteri yönetimi',
                'Tüm Enterprise özellikleri', 'Özel destek',
                'EMARE Token ödemesi (%15 indirim)',
            ]),
            sort_order=3,
        ),
    ]
    for plan in plans:
        db.session.add(plan)
    db.session.commit()
    logger.info("  ✅ Varsayılan planlar oluşturuldu (Community, Professional, Enterprise, Reseller)")
    logger.info("  💎 EMARE Token fiyatları: Professional=490, Enterprise=1990, Reseller=4990 EMARE/ay")


def _create_default_org():
    """Varsayılan organizasyonu oluşturur ve admin'i bu org'a atar."""
    admin = User.query.filter_by(role='super_admin').first()
    community = Plan.query.filter_by(name='community').first()

    org = Organization(
        name='Varsayılan Organizasyon',
        slug='default',
        owner_id=admin.id if admin else None,
        is_active=True,
    )
    db.session.add(org)
    db.session.flush()  # ID oluşsun

    # Admin'i bu org'a ata
    if admin:
        admin.org_id = org.id

    # Kaynak kotası oluştur
    if community:
        quota = ResourceQuota(
            org_id=org.id,
            max_servers=community.max_servers,
            max_users=community.max_users,
            max_storage_gb=community.max_storage_gb,
            max_backups=community.max_backups,
        )
        db.session.add(quota)

        # Abonelik oluştur
        sub = Subscription(
            org_id=org.id,
            plan_id=community.id,
            status='active',
            billing_cycle='monthly',
        )
        db.session.add(sub)

    db.session.commit()
    logger.info("  ✅ Varsayılan organizasyon oluşturuldu (slug: default)")
