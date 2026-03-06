"""
EmareCloud — Veritabanı Modelleri
User, AuditLog, ServerCredential, AppSetting
"""

import json
import uuid
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db

# ==================== ORGANIZATION (TENANT) ====================

class Organization(db.Model):
    """Multi-tenant organizasyon modeli — her müşteri bir tenant."""
    __tablename__ = 'organizations'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    owner_id = db.Column(db.Integer, nullable=True)  # İlk oluşturan kullanıcı
    is_active = db.Column(db.Boolean, default=True)
    settings_json = db.Column(db.Text, default='{}')
    logo_url = db.Column(db.String(500), nullable=True)
    domain = db.Column(db.String(255), nullable=True, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # İlişkiler
    members = db.relationship('User', backref='organization', lazy='dynamic',
                               foreign_keys='User.org_id')
    servers = db.relationship('ServerCredential', backref='organization', lazy='dynamic',
                               foreign_keys='ServerCredential.org_id')
    subscriptions = db.relationship('Subscription', backref='organization', lazy='dynamic',
                                      cascade='all, delete-orphan')
    resource_quota = db.relationship('ResourceQuota', backref='organization', uselist=False,
                                     cascade='all, delete-orphan')

    @staticmethod
    def generate_slug(name: str) -> str:
        """Benzersiz slug üretir."""
        import re
        # Türkçe karakter dönüşümü
        tr_map = str.maketrans('çğıöşüÇĞİÖŞÜ', 'cgiosuCGIOSU')
        slug_text = name.translate(tr_map)
        base = re.sub(r'[^a-z0-9]+', '-', slug_text.lower()).strip('-')
        slug = base
        counter = 1
        while Organization.query.filter_by(slug=slug).first():
            slug = f"{base}-{counter}"
            counter += 1
        return slug

    @property
    def settings(self) -> dict:
        try:
            return json.loads(self.settings_json or '{}')
        except (json.JSONDecodeError, TypeError):
            return {}

    @settings.setter
    def settings(self, value: dict):
        self.settings_json = json.dumps(value, ensure_ascii=False)

    @property
    def active_subscription(self):
        """Aktif aboneliği döndürür."""
        return Subscription.query.filter_by(
            org_id=self.id, status='active'
        ).first()

    @property
    def plan_name(self) -> str:
        sub = self.active_subscription
        if sub and sub.plan:
            return sub.plan.name
        return 'community'

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'owner_id': self.owner_id,
            'is_active': self.is_active,
            'logo_url': self.logo_url,
            'domain': self.domain,
            'plan': self.plan_name,
            'member_count': self.members.count(),
            'server_count': self.servers.count(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ==================== PLAN ====================

class Plan(db.Model):
    """Fiyatlandırma planları — Community, Professional, Enterprise, Reseller."""
    __tablename__ = 'plans'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)  # community, professional, enterprise, reseller
    display_name = db.Column(db.String(100), nullable=False)
    price_monthly = db.Column(db.Float, default=0.0)
    price_yearly = db.Column(db.Float, default=0.0)
    # EmareToken (EMARE) fiyatları — 1 EMARE ≈ $0.1
    price_token_monthly = db.Column(db.Float, default=0.0)  # EMARE/ay
    price_token_yearly = db.Column(db.Float, default=0.0)   # EMARE/yıl
    max_servers = db.Column(db.Integer, default=3)
    max_users = db.Column(db.Integer, default=1)
    max_storage_gb = db.Column(db.Integer, default=10)
    max_backups = db.Column(db.Integer, default=3)
    features_json = db.Column(db.Text, default='[]')  # JSON array of feature strings
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    subscriptions = db.relationship('Subscription', backref='plan', lazy='dynamic')

    @property
    def features(self) -> list:
        try:
            return json.loads(self.features_json or '[]')
        except (json.JSONDecodeError, TypeError):
            return []

    @features.setter
    def features(self, value: list):
        self.features_json = json.dumps(value, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'display_name': self.display_name,
            'price_monthly': self.price_monthly,
            'price_yearly': self.price_yearly,
            'price_token_monthly': self.price_token_monthly,
            'price_token_yearly': self.price_token_yearly,
            'max_servers': self.max_servers,
            'max_users': self.max_users,
            'max_storage_gb': self.max_storage_gb,
            'max_backups': self.max_backups,
            'features': self.features,
            'is_active': self.is_active,
        }


# ==================== SUBSCRIPTION ====================

class Subscription(db.Model):
    """Organizasyon abonelik kaydı."""
    __tablename__ = 'subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False, index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('plans.id'), nullable=False)
    status = db.Column(db.String(20), default='active')  # active, expired, cancelled, trial
    billing_cycle = db.Column(db.String(20), default='monthly')  # monthly, yearly
    starts_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)
    payment_ref = db.Column(db.String(200), nullable=True)  # Stripe/Iyzico referans
    # EmareToken ödeme alanları
    payment_method = db.Column(db.String(20), default='none')  # none, token, stripe, iyzico
    token_tx_hash = db.Column(db.String(100), nullable=True)   # Blockchain TX hash
    token_amount_paid = db.Column(db.Float, nullable=True)     # Ödenen EMARE miktarı
    payer_wallet = db.Column(db.String(100), nullable=True)    # Ödeme yapan cüzdan adresi
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def is_expired(self) -> bool:
        return bool(self.expires_at and datetime.utcnow() > self.expires_at)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'org_id': self.org_id,
            'plan_id': self.plan_id,
            'plan_name': self.plan.name if self.plan else None,
            'status': self.status,
            'billing_cycle': self.billing_cycle,
            'payment_method': self.payment_method,
            'token_tx_hash': self.token_tx_hash,
            'token_amount_paid': self.token_amount_paid,
            'payer_wallet': self.payer_wallet,
            'starts_at': self.starts_at.isoformat() if self.starts_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ==================== RESOURCE QUOTA ====================

class ResourceQuota(db.Model):
    """Organizasyon kaynak kotaları — plan limitlerini özelleştirir."""
    __tablename__ = 'resource_quotas'

    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=False, unique=True, index=True)
    max_servers = db.Column(db.Integer, default=3)
    max_users = db.Column(db.Integer, default=1)
    max_storage_gb = db.Column(db.Integer, default=10)
    max_backups = db.Column(db.Integer, default=3)
    max_vms = db.Column(db.Integer, default=0)
    custom_limits_json = db.Column(db.Text, default='{}')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            'org_id': self.org_id,
            'max_servers': self.max_servers,
            'max_users': self.max_users,
            'max_storage_gb': self.max_storage_gb,
            'max_backups': self.max_backups,
            'max_vms': self.max_vms,
        }

    def check_limit(self, resource: str, current_count: int) -> bool:
        """Kota limitini kontrol eder. True = limit aşılmamış."""
        limit = getattr(self, f'max_{resource}', None)
        if limit is None:
            return True
        return current_count < limit

# ==================== USER ====================

class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='read_only')
    is_active_user = db.Column(db.Boolean, default=True)
    # Multi-tenant
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True, index=True)
    # 2FA (TOTP)
    totp_secret = db.Column(db.String(32), nullable=True)
    totp_enabled = db.Column(db.Boolean, default=False)
    recovery_codes_json = db.Column(db.Text, nullable=True)  # JSON array
    # Özelleştirilmiş modül yetkileri (super_admin tarafından atanır)
    # None → rol bazlı varsayılan kullanılır  |  JSON array → bu liste geçerli olur
    custom_permissions_json = db.Column(db.Text, default=None, nullable=True)
    # Emare Token (ET) bakiyesi — yeni kullanıcılara 100.000 ET hediye edilir
    et_balance = db.Column(db.Float, default=0.0, nullable=False)
    # Zaman damgaları
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    last_seen = db.Column(db.DateTime, nullable=True)
    current_activity = db.Column(db.String(200), nullable=True)   # Şu an ne yapıyor
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # İlişkiler
    audit_logs = db.relationship('AuditLog', backref='user', lazy='dynamic',
                                  foreign_keys='AuditLog.user_id')

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password, method='scrypt')

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return self.is_active_user

    @property
    def is_online(self):
        """Son 5 dakikada aktiflik varsa çevrimiçi kabul et."""
        if not self.last_seen:
            return False
        return (datetime.utcnow() - self.last_seen).total_seconds() < 300

    @property
    def is_super_admin(self):
        return self.role == 'super_admin'

    @property
    def is_admin(self):
        return self.role in ('super_admin', 'admin')

    def has_permission(self, permission: str) -> bool:
        from rbac import check_permission
        # super_admin her zaman tam yetkili
        if self.role == 'super_admin':
            return True
        # Eğer özelleştirilmiş izin listesi varsa, onu kullan
        if self.custom_permissions_json:
            try:
                custom = json.loads(self.custom_permissions_json)
                return permission in custom
            except (json.JSONDecodeError, TypeError):
                pass
        # Standart rol bazlı kontrol
        return check_permission(self.role, permission)

    @property
    def custom_permissions(self) -> list:
        """Özel izin listesini döndürür (boşsa rol varsayılanı kullanılır)."""
        try:
            return json.loads(self.custom_permissions_json or '[]')
        except (json.JSONDecodeError, TypeError):
            return []

    @custom_permissions.setter
    def custom_permissions(self, perms: list):
        self.custom_permissions_json = json.dumps(perms) if perms is not None else None

    @property
    def recovery_codes(self) -> list:
        try:
            return json.loads(self.recovery_codes_json or '[]')
        except (json.JSONDecodeError, TypeError):
            return []

    @recovery_codes.setter
    def recovery_codes(self, codes: list):
        self.recovery_codes_json = json.dumps(codes)

    def generate_recovery_codes(self, count: int = 8) -> list:
        """Yeni kurtarma kodları üretir."""
        codes = [uuid.uuid4().hex[:8].upper() for _ in range(count)]
        self.recovery_codes = codes
        return codes

    def use_recovery_code(self, code: str) -> bool:
        """Kurtarma kodu kullanır. Başarılıysa True döndürür."""
        codes = self.recovery_codes
        upper_code = code.upper().strip()
        if upper_code in codes:
            codes.remove(upper_code)
            self.recovery_codes = codes
            return True
        return False

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'is_active': self.is_active_user,
            'is_online': self.is_online,
            'org_id': self.org_id,
            'totp_enabled': self.totp_enabled,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'last_seen': self.last_seen.isoformat() if self.last_seen else None,
            'current_activity': self.current_activity,
            'custom_permissions': self.custom_permissions,
            'has_custom_perms': self.custom_permissions_json is not None,
            'et_balance': self.et_balance,
        }


# ==================== AUDIT LOG ====================

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    username = db.Column(db.String(80))          # Denormalized — hızlı sorgu için
    action = db.Column(db.String(100), nullable=False, index=True)
    target_type = db.Column(db.String(50))       # server, user, firewall, vm, market
    target_id = db.Column(db.String(100))
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(300))
    details = db.Column(db.Text)                 # JSON
    success = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'username': self.username or 'anonim',
            'action': self.action,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'ip_address': self.ip_address,
            'details': self.details,
            'success': self.success,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


# ==================== DATA CENTER ====================

class DataCenter(db.Model):
    """Veri merkezi tanımı — birden fazla DC tek panelden yönetilir."""
    __tablename__ = 'data_centers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)           # "İstanbul DC-1"
    code = db.Column(db.String(20), unique=True, nullable=False)  # "ist-1", "fra-1"
    location = db.Column(db.String(200), default='')           # "İstanbul, Türkiye"
    provider = db.Column(db.String(100), default='')           # "Hetzner", "OVH", "Custom"
    ip_range = db.Column(db.String(200), default='')           # "185.189.54.0/24"
    description = db.Column(db.Text, default='')
    status = db.Column(db.String(20), default='active')        # active, maintenance, offline
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    settings_json = db.Column(db.Text, default='{}')
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    servers = db.relationship('ServerCredential', backref='datacenter', lazy='dynamic')

    @property
    def settings(self) -> dict:
        try:
            return json.loads(self.settings_json or '{}')
        except (json.JSONDecodeError, TypeError):
            return {}

    @settings.setter
    def settings(self, value: dict):
        self.settings_json = json.dumps(value, ensure_ascii=False)

    @property
    def server_count(self) -> int:
        return self.servers.count()

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'location': self.location or '',
            'provider': self.provider or '',
            'ip_range': self.ip_range or '',
            'description': self.description or '',
            'status': self.status,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'server_count': self.server_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ==================== SERVER CREDENTIAL ====================

class ServerCredential(db.Model):
    __tablename__ = 'server_credentials'

    id = db.Column(db.String(20), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    host = db.Column(db.String(255), nullable=False)
    port = db.Column(db.Integer, default=22)
    username = db.Column(db.String(100), nullable=False, default='root')
    encrypted_password = db.Column(db.LargeBinary, nullable=True)
    encryption_iv = db.Column(db.LargeBinary, nullable=True)
    ssh_key = db.Column(db.Text, nullable=True)          # PEM encoded (Faz 2)
    group_name = db.Column(db.String(50), default='Genel')
    description = db.Column(db.Text, default='')
    tags = db.Column(db.Text, default='[]')              # JSON array
    role = db.Column(db.String(50), default='')
    location = db.Column(db.String(100), default='')
    dc_id = db.Column(db.Integer, db.ForeignKey('data_centers.id'), nullable=True, index=True)
    installed_at = db.Column(db.String(20), default='')
    responsible = db.Column(db.String(100), default='')
    os_planned = db.Column(db.String(200), default='')
    # Multi-tenant
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True, index=True)
    added_at = db.Column(db.DateTime, default=datetime.utcnow)
    added_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    def get_password(self) -> str:
        """Şifreyi çözerek döndürür."""
        if self.encrypted_password and self.encryption_iv:
            from crypto import decrypt_password
            return decrypt_password(self.encrypted_password, self.encryption_iv)
        return ''

    def set_password(self, password: str):
        """Şifreyi AES-256-GCM ile şifreler."""
        from crypto import encrypt_password
        self.encrypted_password, self.encryption_iv = encrypt_password(password)

    def to_dict(self, include_password: bool = False) -> dict:
        """Sunucu bilgilerini dict olarak döndürür."""
        d = {
            'id': self.id,
            'name': self.name,
            'host': self.host,
            'port': self.port,
            'username': self.username,
            'group': self.group_name,
            'description': self.description or '',
            'tags': json.loads(self.tags) if self.tags else [],
            'role': self.role or '',
            'location': self.location or '',
            'dc_id': self.dc_id,
            'dc_name': self.datacenter.name if self.datacenter else None,
            'dc_code': self.datacenter.code if self.datacenter else None,
            'installed_at': self.installed_at or '',
            'responsible': self.responsible or '',
            'os_planned': self.os_planned or '',
            'added_at': self.added_at.strftime('%Y-%m-%d %H:%M') if self.added_at else '',
        }
        if include_password:
            d['password'] = self.get_password()
            d['ssh_key'] = self.ssh_key or ''
        return d


# ==================== API TOKEN ====================

class ApiToken(db.Model):
    __tablename__ = 'api_tokens'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True, index=True)
    token_hash = db.Column(db.String(256), nullable=False, unique=True)
    token_prefix = db.Column(db.String(10), nullable=True)  # İlk 8 karakter (tanıma için)
    name = db.Column(db.String(100))
    permissions = db.Column(db.Text, default='[]')       # JSON array
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    last_used = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)

    user = db.relationship('User', backref='api_tokens')

    @staticmethod
    def generate_token() -> tuple:
        """Yeni API token üretir. (raw_token, token_hash, prefix) döndürür."""
        import hashlib
        import secrets
        raw = f"emc_{secrets.token_urlsafe(42)}"
        hashed = hashlib.sha256(raw.encode()).hexdigest()
        prefix = raw[:8]
        return raw, hashed, prefix

    @staticmethod
    def find_by_raw_token(raw_token: str):
        """Ham token ile kayıt bulur."""
        import hashlib
        hashed = hashlib.sha256(raw_token.encode()).hexdigest()
        return ApiToken.query.filter_by(token_hash=hashed, is_active=True).first()

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'token_prefix': self.token_prefix,
            'permissions': json.loads(self.permissions or '[]'),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'is_active': self.is_active,
        }


# ==================== APP SETTING ====================

class AppSetting(db.Model):
    __tablename__ = 'app_settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    @staticmethod
    def get(key: str, default=None):
        """Ayar değerini döndürür."""
        setting = AppSetting.query.filter_by(key=key).first()
        if setting:
            try:
                return json.loads(setting.value)
            except (json.JSONDecodeError, TypeError):
                return setting.value
        return default

    @staticmethod
    def set(key: str, value, user_id: int = None):
        """Ayar değerini kaydeder."""
        setting = AppSetting.query.filter_by(key=key).first()
        val_str = json.dumps(value) if not isinstance(value, str) else value
        if setting:
            setting.value = val_str
            setting.updated_by = user_id
        else:
            setting = AppSetting(key=key, value=val_str, updated_by=user_id)
            db.session.add(setting)
        db.session.commit()


# ==================== ALERT RULE ====================

class AlertRule(db.Model):
    """Metrik eşik kuralları — CPU, RAM, disk alarmları."""
    __tablename__ = 'alert_rules'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    server_id = db.Column(db.String(20), nullable=True)    # null = tüm sunucular
    metric = db.Column(db.String(50), nullable=False)       # cpu, memory, disk
    condition = db.Column(db.String(10), default='>')       # >, <, >=, <=
    threshold = db.Column(db.Float, nullable=False)
    severity = db.Column(db.String(20), default='warning')  # info, warning, critical
    webhook_id = db.Column(db.Integer, db.ForeignKey('webhook_configs.id'), nullable=True)
    cooldown_minutes = db.Column(db.Integer, default=15)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    last_triggered = db.Column(db.DateTime, nullable=True)

    webhook = db.relationship('WebhookConfig', backref='alert_rules', lazy='select')

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'server_id': self.server_id,
            'metric': self.metric,
            'condition': self.condition,
            'threshold': self.threshold,
            'severity': self.severity,
            'webhook_id': self.webhook_id,
            'cooldown_minutes': self.cooldown_minutes,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'last_triggered': self.last_triggered.strftime('%Y-%m-%d %H:%M:%S') if self.last_triggered else None,
        }


# ==================== ALERT HISTORY ====================

class AlertHistory(db.Model):
    """Tetiklenen alarm geçmişi."""
    __tablename__ = 'alert_history'

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey('alert_rules.id'), nullable=True)
    server_id = db.Column(db.String(20), nullable=False)
    metric = db.Column(db.String(50), nullable=False)
    current_value = db.Column(db.Float, nullable=False)
    threshold = db.Column(db.Float, nullable=False)
    severity = db.Column(db.String(20), default='warning')
    message = db.Column(db.Text)
    notified = db.Column(db.Boolean, default=False)
    acknowledged = db.Column(db.Boolean, default=False)
    acknowledged_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    rule = db.relationship('AlertRule', backref='history', lazy='select')

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'rule_id': self.rule_id,
            'server_id': self.server_id,
            'metric': self.metric,
            'current_value': self.current_value,
            'threshold': self.threshold,
            'severity': self.severity,
            'message': self.message,
            'notified': self.notified,
            'acknowledged': self.acknowledged,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


# ==================== WEBHOOK CONFIG ====================

class WebhookConfig(db.Model):
    """Bildirim kanalları — Slack, Discord, E-posta, özel webhook."""
    __tablename__ = 'webhook_configs'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    webhook_type = db.Column(db.String(20), nullable=False)  # slack, discord, email, custom
    url = db.Column(db.String(500), nullable=True)           # webhook URL
    # SMTP alanları (email tipi için)
    smtp_host = db.Column(db.String(200), nullable=True)
    smtp_port = db.Column(db.Integer, nullable=True)
    smtp_user = db.Column(db.String(200), nullable=True)
    smtp_password_enc = db.Column(db.LargeBinary, nullable=True)
    smtp_password_iv = db.Column(db.LargeBinary, nullable=True)
    smtp_from = db.Column(db.String(200), nullable=True)
    smtp_to = db.Column(db.Text, nullable=True)              # virgülle ayrılmış
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'webhook_type': self.webhook_type,
            'url': self.url or '',
            'smtp_host': self.smtp_host or '',
            'smtp_port': self.smtp_port,
            'smtp_user': self.smtp_user or '',
            'smtp_from': self.smtp_from or '',
            'smtp_to': self.smtp_to or '',
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


# ==================== SCHEDULED TASK ====================

class ScheduledTask(db.Model):
    """Zamanlanmış görevler — sunucu üzerinde cron job yönetimi."""
    __tablename__ = 'scheduled_tasks'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    server_id = db.Column(db.String(20), nullable=False)
    command = db.Column(db.Text, nullable=False)
    schedule = db.Column(db.String(100), nullable=False)     # cron format: "0 2 * * *"
    is_active = db.Column(db.Boolean, default=True)
    last_run = db.Column(db.DateTime, nullable=True)
    last_status = db.Column(db.String(20), nullable=True)    # success, failed, running
    last_output = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'server_id': self.server_id,
            'command': self.command,
            'schedule': self.schedule,
            'is_active': self.is_active,
            'last_run': self.last_run.strftime('%Y-%m-%d %H:%M:%S') if self.last_run else None,
            'last_status': self.last_status,
            'last_output': (self.last_output or '')[:500],
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


# ==================== BACKUP PROFILE ====================

class BackupProfile(db.Model):
    """Otomatik yedekleme profilleri."""
    __tablename__ = 'backup_profiles'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    server_id = db.Column(db.String(20), nullable=False)
    source_path = db.Column(db.String(500), nullable=False)
    dest_path = db.Column(db.String(500), nullable=False)
    schedule = db.Column(db.String(100), default='0 2 * * *')  # cron format
    retention_days = db.Column(db.Integer, default=30)
    compression = db.Column(db.String(20), default='gzip')     # gzip, bzip2, none
    is_active = db.Column(db.Boolean, default=True)
    last_run = db.Column(db.DateTime, nullable=True)
    last_status = db.Column(db.String(20), nullable=True)
    last_size = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'server_id': self.server_id,
            'source_path': self.source_path,
            'dest_path': self.dest_path,
            'schedule': self.schedule,
            'retention_days': self.retention_days,
            'compression': self.compression,
            'is_active': self.is_active,
            'last_run': self.last_run.strftime('%Y-%m-%d %H:%M:%S') if self.last_run else None,
            'last_status': self.last_status,
            'last_size': self.last_size,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


# ==================== METRIC SNAPSHOT ====================

class MetricSnapshot(db.Model):
    """Periyodik metrik kaydı — trend analizi ve grafikler için."""
    __tablename__ = 'metric_snapshots'

    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.String(20), nullable=False, index=True)
    cpu_percent = db.Column(db.Float, nullable=True)
    memory_percent = db.Column(db.Float, nullable=True)
    disk_percent = db.Column(db.Float, nullable=True)
    network_rx = db.Column(db.BigInteger, nullable=True)
    network_tx = db.Column(db.BigInteger, nullable=True)
    load_1m = db.Column(db.Float, nullable=True)
    load_5m = db.Column(db.Float, nullable=True)
    load_15m = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            'server_id': self.server_id,
            'cpu_percent': self.cpu_percent,
            'memory_percent': self.memory_percent,
            'disk_percent': self.disk_percent,
            'network_rx': self.network_rx,
            'network_tx': self.network_tx,
            'load_1m': self.load_1m,
            'load_5m': self.load_5m,
            'load_15m': self.load_15m,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


# ==================== USER WALLET (Blockchain) ====================

class UserWallet(db.Model):
    """Kullanıcı cüzdan adresleri — EmareToken ekosistemi bağlantısı."""
    __tablename__ = 'user_wallets'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    wallet_address = db.Column(db.String(42), nullable=False, index=True)  # 0x... EVM adresi
    is_primary = db.Column(db.Boolean, default=False)
    chain_id = db.Column(db.Integer, default=97)  # 97=BSC Testnet, 56=BSC Mainnet
    label = db.Column(db.String(100), nullable=True)  # "Ana Cüzdan", "MetaMask" vb.
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True, index=True)
    verified = db.Column(db.Boolean, default=False)  # İmza ile doğrulandı mı
    registered_on_chain = db.Column(db.Boolean, default=False)  # RewardPool'a kaydedildi mi
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='wallets')

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'user_id': self.user_id,
            'wallet_address': self.wallet_address,
            'is_primary': self.is_primary,
            'chain_id': self.chain_id,
            'label': self.label,
            'verified': self.verified,
            'registered_on_chain': self.registered_on_chain,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ==================== EMARE POINT (EP — Ödül Puanı) ====================

class EmarePoint(db.Model):
    """
    Emare Puanı (EP) kayıtları — kullanıcı aksiyonlarına göre kazanılan puanlar.
    EP'ler birikir ve RewardPool kontratı üzerinden EMR token'a dönüştürülür.
    """
    __tablename__ = 'emare_points'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False, index=True)  # server_added, subscription_payment vb.
    ep_amount = db.Column(db.Integer, nullable=False)              # Kazanılan EP miktarı
    claim_type = db.Column(db.String(20), default='work')          # cashback, marketplace, work
    is_claimed = db.Column(db.Boolean, default=False)              # On-chain claim edildi mi
    claim_tx_hash = db.Column(db.String(66), nullable=True)        # Blockchain tx hash
    metadata_json = db.Column(db.Text, default='{}')               # Ek bilgi (product_id, tx_ref vb.)
    org_id = db.Column(db.Integer, db.ForeignKey('organizations.id'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User', backref='emare_points')

    @staticmethod
    def get_total_ep(user_id: int) -> int:
        """Kullanıcının toplam EP miktarını döndürür."""
        from sqlalchemy import func
        result = db.session.query(func.sum(EmarePoint.ep_amount)).filter_by(user_id=user_id).scalar()
        return result or 0

    @staticmethod
    def get_unclaimed_ep(user_id: int) -> int:
        """Kullanıcının claim edilmemiş EP miktarını döndürür."""
        from sqlalchemy import func
        result = db.session.query(func.sum(EmarePoint.ep_amount)).filter_by(
            user_id=user_id, is_claimed=False
        ).scalar()
        return result or 0

    @staticmethod
    def get_claimed_ep(user_id: int) -> int:
        """Kullanıcının claim edilmiş EP miktarını döndürür."""
        from sqlalchemy import func
        result = db.session.query(func.sum(EmarePoint.ep_amount)).filter_by(
            user_id=user_id, is_claimed=True
        ).scalar()
        return result or 0

    @staticmethod
    def get_daily_total(user_id: int) -> int:
        """Kullanıcının bugün kazandığı EP miktarını döndürür."""
        from sqlalchemy import func
        today = datetime.utcnow().date()
        result = db.session.query(func.sum(EmarePoint.ep_amount)).filter(
            EmarePoint.user_id == user_id,
            db.func.date(EmarePoint.created_at) == today,
        ).scalar()
        return result or 0

    @staticmethod
    def get_last_action(user_id: int, action: str):
        """Kullanıcının belirli bir aksiyonun son kaydını döndürür."""
        return EmarePoint.query.filter_by(
            user_id=user_id, action=action
        ).order_by(EmarePoint.created_at.desc()).first()

    @staticmethod
    def get_unclaimed_users():
        """Claim edilmemiş EP'leri olan kullanıcıları döndürür."""
        from sqlalchemy import func
        return db.session.query(
            EmarePoint.user_id,
            func.sum(EmarePoint.ep_amount).label('total_ep'),
        ).filter_by(is_claimed=False).group_by(EmarePoint.user_id).all()

    @staticmethod
    def mark_claimed(user_id: int, tx_hash: str):
        """Kullanıcının tüm unclaimed EP'lerini claimed olarak işaretler."""
        EmarePoint.query.filter_by(
            user_id=user_id, is_claimed=False
        ).update({'is_claimed': True, 'claim_tx_hash': tx_hash})
        db.session.commit()

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'action': self.action,
            'ep_amount': self.ep_amount,
            'claim_type': self.claim_type,
            'is_claimed': self.is_claimed,
            'claim_tx_hash': self.claim_tx_hash,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


# ==================== TOKEN TRANSACTION LOG ====================

class TokenTransaction(db.Model):
    """
    Token işlem kayıtları — blockchain tx'lerinin off-chain takibi.
    Kullanıcı cüzdanıyla ilgili önemli işlemleri (claim, transfer, purchase) izler.
    """
    __tablename__ = 'token_transactions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    tx_hash = db.Column(db.String(66), unique=True, nullable=False)  # 0x... transaction hash
    tx_type = db.Column(db.String(30), nullable=False, index=True)   # claim, transfer, purchase, refund, escrow
    from_address = db.Column(db.String(42), nullable=True)
    to_address = db.Column(db.String(42), nullable=True)
    amount = db.Column(db.String(78), nullable=True)                 # Wei cinsinden (büyük sayı)
    amount_human = db.Column(db.String(50), nullable=True)           # İnsan okunabilir (örn: "100.5")
    status = db.Column(db.String(20), default='pending')             # pending, confirmed, failed
    block_number = db.Column(db.BigInteger, nullable=True)
    chain_id = db.Column(db.Integer, default=97)
    metadata_json = db.Column(db.Text, default='{}')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    confirmed_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'tx_hash': self.tx_hash,
            'tx_type': self.tx_type,
            'from_address': self.from_address,
            'to_address': self.to_address,
            'amount_human': self.amount_human,
            'status': self.status,
            'block_number': self.block_number,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


# ==================== FEEDBACK ====================

class Feedback(db.Model):
    """Kullanıcı geri bildirim / destek bildirimi modeli."""
    __tablename__ = 'feedback'

    CATEGORIES = ('bug', 'suggestion', 'question', 'other')
    PRIORITIES = ('low', 'normal', 'high', 'critical')
    STATUSES = ('open', 'in_progress', 'resolved', 'closed')

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    message     = db.Column(db.Text, nullable=False)
    category    = db.Column(db.String(20), default='bug', index=True)
    priority    = db.Column(db.String(20), default='normal', index=True)
    page_url    = db.Column(db.String(500), nullable=True)
    status      = db.Column(db.String(20), default='open', index=True)
    admin_reply = db.Column(db.Text, nullable=True)
    replied_by  = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    replied_at  = db.Column(db.DateTime, nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # ilişkiler
    user        = db.relationship('User', foreign_keys=[user_id], backref=db.backref('feedbacks', lazy='dynamic'))
    replied_user= db.relationship('User', foreign_keys=[replied_by])

    # ── yardımcı etiketler ───────────────────────────────────────
    CATEGORY_META = {
        'bug':        ('Hata',  'fa-bug',           'red',    'bg-red-100 text-red-700'),
        'suggestion': ('Öneri', 'fa-lightbulb',     'blue',   'bg-blue-100 text-blue-700'),
        'question':   ('Soru',  'fa-question-circle','purple', 'bg-purple-100 text-purple-700'),
        'other':      ('Diğer', 'fa-comment',       'gray',   'bg-gray-100 text-gray-700'),
    }
    STATUS_META = {
        'open':        ('Açık',         'bg-yellow-100 text-yellow-700'),
        'in_progress': ('İnceleniyor',  'bg-blue-100 text-blue-700'),
        'resolved':    ('Çözüldü',      'bg-green-100 text-green-700'),
        'closed':      ('Kapatıldı',    'bg-gray-100 text-gray-500'),
    }
    PRIORITY_META = {
        'low':      ('Düşük',  'bg-gray-100 text-gray-500'),
        'normal':   ('Normal', 'bg-blue-100 text-blue-600'),
        'high':     ('Yüksek', 'bg-orange-100 text-orange-700'),
        'critical': ('Kritik', 'bg-red-100 text-red-700'),
    }

    @property
    def category_label(self): return self.CATEGORY_META.get(self.category, ('Diğer','fa-comment','gray',''))[0]
    @property
    def category_icon(self):  return self.CATEGORY_META.get(self.category, ('','fa-comment','',''))[1]
    @property
    def category_color(self): return self.CATEGORY_META.get(self.category, ('','','gray',''))[2]
    @property
    def category_badge(self): return self.CATEGORY_META.get(self.category, ('','','','bg-gray-100 text-gray-700'))[3]
    @property
    def status_label(self):   return self.STATUS_META.get(self.status, ('Bilinmiyor',''))[0]
    @property
    def status_badge(self):   return self.STATUS_META.get(self.status, ('','bg-gray-100 text-gray-500'))[1]
    @property
    def priority_label(self): return self.PRIORITY_META.get(self.priority, ('Normal',''))[0]
    @property
    def priority_badge(self): return self.PRIORITY_META.get(self.priority, ('','bg-blue-100 text-blue-600'))[1]

    def to_dict(self) -> dict:
        return {
            'id':             self.id,
            'message':        self.message,
            'category':       self.category,
            'category_label': self.category_label,
            'category_icon':  self.category_icon,
            'category_color': self.category_color,
            'category_badge': self.category_badge,
            'priority':       self.priority,
            'priority_label': self.priority_label,
            'priority_badge': self.priority_badge,
            'page_url':       self.page_url,
            'status':         self.status,
            'status_label':   self.status_label,
            'status_badge':   self.status_badge,
            'admin_reply':    self.admin_reply,
            'replied_at':     self.replied_at.strftime('%d.%m.%Y %H:%M') if self.replied_at else None,
            'created_at':     self.created_at.strftime('%d.%m.%Y %H:%M') if self.created_at else None,
        }


# ==================== WEB DİZAYN MÜŞTERİLERİ ====================

class WebDizaynClient(db.Model):
    """Emare Web Dizayn — Müşteri web sitesi kaydı."""
    __tablename__ = 'webdizayn_clients'

    id         = db.Column(db.Integer, primary_key=True)
    slug       = db.Column(db.String(100), unique=True, nullable=False, index=True)
    name       = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    contact    = db.Column(db.String(200), default='')   # tel/email/adres
    is_active  = db.Column(db.Boolean, default=True)
    added_by   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    WEB_ROOT = '/var/www/webdizayn'

    @property
    def public_url(self):
        return f'https://webdizayn.emarecloud.tr/{self.slug}'

    @property
    def site_path(self):
        import pathlib
        return pathlib.Path(self.WEB_ROOT) / self.slug

    @property
    def has_files(self):
        try:
            p = self.site_path
            return p.exists() and any(p.iterdir())
        except Exception:
            return False

    def to_dict(self) -> dict:
        return {
            'id':          self.id,
            'slug':        self.slug,
            'name':        self.name,
            'description': self.description,
            'contact':     self.contact,
            'is_active':   self.is_active,
            'has_files':   self.has_files,
            'public_url':  self.public_url,
            'added_by':    self.added_by,
            'created_at':  self.created_at.strftime('%d.%m.%Y') if self.created_at else None,
        }

