"""
EmareCloud — Role-Based Access Control (RBAC)
Rol tanımları, yetki matrisi ve dekoratörler.
"""

from functools import wraps

from flask import abort, jsonify, request
from flask_login import current_user

# ==================== ROL TANIMLARI ====================

ROLES = {
    'super_admin': {
        'label': 'Süper Admin',
        'level': 100,
        'description': 'Tam yetki — tüm işlemler',
        'color': '#f87171',
    },
    'admin': {
        'label': 'Admin',
        'level': 75,
        'description': 'Sunucu yönetimi, kullanıcı görüntüleme',
        'color': '#fbbf24',
    },
    'operator': {
        'label': 'Operatör',
        'level': 50,
        'description': 'Komut çalıştırma, servis yönetimi',
        'color': '#4c8dff',
    },
    'read_only': {
        'label': 'Salt Okunur',
        'level': 10,
        'description': 'Sadece görüntüleme',
        'color': '#8b8fa3',
    },
}


# ==================== YETKİ MATRİSİ ====================

# Tüm mevcut modül yetkilerinin tam listesi — admin panel'de seçilebilir
ALL_PERMISSIONS = [
    # Sunucu
    'server.view', 'server.add', 'server.edit', 'server.delete',
    'server.connect', 'server.disconnect', 'server.execute',
    'server.metrics', 'server.quick_action',
    # Güvenlik Duvarı
    'firewall.view', 'firewall.manage',
    # Sanal Makine
    'vm.view', 'vm.manage',
    # Uygulama Pazarı
    'market.view', 'market.install',
    # Depolama
    'storage.view', 'storage.manage',
    # Terminal
    'terminal.access',
    # İzleme
    'monitoring.view', 'monitoring.manage',
    # RAID
    'raid.view', 'raid.manage',
    # AI Araçları
    'ai.view', 'ai.manage',
    # Kullanıcı
    'user.view',
    # Denetim
    'audit.view',
    # Organizasyon
    'org.view', 'org.manage', 'org.members',
    # Plan & Abonelik
    'plan.view',
    # Token
    'token.manage',
    # Cloudflare
    'cloudflare.view',
    # Veri Merkezi (DC)
    'dc.view', 'dc.manage',
    # Geliştirici Panosu
    'scoreboard.view',
    # Admin Panel
    'admin_panel',
]

# Modül grupları — admin panelde kategoriler halinde gösterim
PERMISSION_GROUPS = [
    {
        'key': 'server',
        'label': 'Sunucu Yönetimi',
        'icon': '🖥️',
        'perms': [
            ('server.view', 'Görüntüle'),
            ('server.add', 'Ekle'),
            ('server.edit', 'Düzenle'),
            ('server.delete', 'Sil'),
            ('server.connect', 'Bağlan'),
            ('server.disconnect', 'Bağlantıyı Kes'),
            ('server.execute', 'Komut Çalıştır'),
            ('server.metrics', 'Metrikler'),
            ('server.quick_action', 'Hızlı Eylem'),
        ],
    },
    {
        'key': 'firewall',
        'label': 'Güvenlik Duvarı',
        'icon': '🛡️',
        'perms': [
            ('firewall.view', 'Görüntüle'),
            ('firewall.manage', 'Yönet'),
        ],
    },
    {
        'key': 'vm',
        'label': 'Sanal Makine (LXD)',
        'icon': '📦',
        'perms': [
            ('vm.view', 'Görüntüle'),
            ('vm.manage', 'Yönet'),
        ],
    },
    {
        'key': 'market',
        'label': 'Uygulama Pazarı',
        'icon': '🏪',
        'perms': [
            ('market.view', 'Görüntüle'),
            ('market.install', 'Kur / Sil'),
        ],
    },
    {
        'key': 'storage',
        'label': 'Depolama',
        'icon': '💾',
        'perms': [
            ('storage.view', 'Görüntüle'),
            ('storage.manage', 'Yönet'),
        ],
    },
    {
        'key': 'terminal',
        'label': 'Terminal',
        'icon': '⌨️',
        'perms': [
            ('terminal.access', 'Erişim'),
        ],
    },
    {
        'key': 'monitoring',
        'label': 'İzleme & Alarm',
        'icon': '📊',
        'perms': [
            ('monitoring.view', 'Görüntüle'),
            ('monitoring.manage', 'Yönet'),
        ],
    },
    {
        'key': 'raid',
        'label': 'RAID Yönetimi',
        'icon': '🗄️',
        'perms': [
            ('raid.view', 'Görüntüle'),
            ('raid.manage', 'Yönet'),
        ],
    },
    {
        'key': 'ai',
        'label': 'AI Araçları',
        'icon': '🧠',
        'perms': [
            ('ai.view', 'Görüntüle'),
            ('ai.manage', 'Yönet'),
        ],
    },
    {
        'key': 'user',
        'label': 'Kullanıcı Yönetimi',
        'icon': '👥',
        'perms': [
            ('user.view', 'Kullanıcıları Gör'),
        ],
    },
    {
        'key': 'audit',
        'label': 'Denetim Günlüğü',
        'icon': '📋',
        'perms': [
            ('audit.view', 'Görüntüle'),
        ],
    },
    {
        'key': 'org',
        'label': 'Organizasyon',
        'icon': '🏢',
        'perms': [
            ('org.view', 'Görüntüle'),
            ('org.manage', 'Yönet'),
            ('org.members', 'Üye Yönetimi'),
        ],
    },
    {
        'key': 'plan',
        'label': 'Plan & Abonelik',
        'icon': '💳',
        'perms': [
            ('plan.view', 'Görüntüle'),
        ],
    },
    {
        'key': 'token',
        'label': 'EMARE Token',
        'icon': '💎',
        'perms': [
            ('token.manage', 'Yönet'),
        ],
    },
    {
        'key': 'cloudflare',
        'label': 'Cloudflare DNS',
        'icon': '☁️',
        'perms': [
            ('cloudflare.view', 'Görüntüle'),
        ],
    },
    {
        'key': 'dc',
        'label': 'Veri Merkezi (DC)',
        'icon': '🏗️',
        'perms': [
            ('dc.view', 'Görüntüle'),
            ('dc.manage', 'Yönet'),
        ],
    },
    {
        'key': 'scoreboard',
        'label': 'Geliştirici Panosu',
        'icon': '🏆',
        'perms': [
            ('scoreboard.view', 'Panoyu Görüntüle'),
        ],
    },
    {
        'key': 'admin',
        'label': 'Admin Panel',
        'icon': '⚙️',
        'perms': [
            ('admin_panel', 'Admin Panele Eriş'),
        ],
    },
]

PERMISSIONS = {
    'super_admin': {'*'},  # Tüm yetkiler

    'admin': {
        'server.view', 'server.add', 'server.edit', 'server.delete',
        'server.connect', 'server.disconnect', 'server.execute', 'server.metrics',
        'server.quick_action',
        'firewall.view', 'firewall.manage',
        'vm.view', 'vm.manage',
        'market.view', 'market.install',
        'storage.view', 'storage.manage',
        'terminal.access',
        'user.view',
        'audit.view',
        'raid.view', 'raid.manage',
        'monitoring.view', 'monitoring.manage',
        'ai.view', 'ai.manage',
        'org.view', 'org.manage', 'org.members',
        'plan.view',
        'token.manage',
        'cloudflare.view',
        'dc.view', 'dc.manage',
        'scoreboard.view',
    },

    'operator': {
        'server.view', 'server.connect', 'server.disconnect',
        'server.execute', 'server.metrics', 'server.quick_action',
        'firewall.view',
        'dc.view',
        'vm.view', 'vm.manage',
        'market.view', 'market.install',
        'storage.view',
        'terminal.access',
        'raid.view',
        'monitoring.view',
        'ai.view',
        'org.view',
        'plan.view',
        'token.manage',
        'scoreboard.view',
    },

    'read_only': {
        'server.view', 'server.metrics',
        'firewall.view',
        'vm.view',
        'market.view',
        'storage.view',
        'raid.view',
        'monitoring.view',
        'org.view',
        'plan.view',
        'scoreboard.view',
    },
}


# ==================== YARDIMCI FONKSİYONLAR ====================

def check_permission(role: str, permission: str) -> bool:
    """Rolün belirli bir yetkiye sahip olup olmadığını kontrol eder."""
    perms = PERMISSIONS.get(role, set())
    return '*' in perms or permission in perms


def get_role_info(role: str) -> dict:
    """Rol bilgisi döndürür."""
    return ROLES.get(role, {'label': role, 'level': 0, 'description': '', 'color': '#8b8fa3'})


def get_all_roles() -> list:
    """Tüm rolleri listeler."""
    return [{'key': k, **v} for k, v in ROLES.items()]


def get_permissions_for_role(role: str) -> set:
    """Rol için tüm yetkileri döndürür."""
    return PERMISSIONS.get(role, set())


# ==================== DEKORATÖRLER ====================

def role_required(*roles):
    """Belirtilen rollerden birine sahip olmayı zorunlu kılar.

    Kullanım:
        @role_required('super_admin', 'admin')
        def admin_only_view():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.is_json:
                    return jsonify({'success': False, 'message': 'Giriş yapmalısınız'}), 401
                abort(401)
            if current_user.role not in roles and current_user.role != 'super_admin':
                if request.is_json:
                    return jsonify({'success': False, 'message': 'Bu işlem için yetkiniz yok'}), 403
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


def permission_required(permission: str):
    """Belirli bir yetkiye sahip olmayı zorunlu kılar.

    Kullanım:
        @permission_required('server.add')
        def add_server():
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.is_json:
                    return jsonify({'success': False, 'message': 'Giriş yapmalısınız'}), 401
                abort(401)
            if not check_permission(current_user.role, permission):
                if request.is_json:
                    return jsonify({
                        'success': False,
                        'message': f'Bu işlem için yetkiniz yok ({permission})'
                    }), 403
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator
