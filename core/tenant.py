"""
EmareCloud — Multi-Tenant Middleware
Request bazlı tenant çözümleme ve row-level izolasyon.
"""

import logging

from flask import g, request
from flask_login import current_user

logger = logging.getLogger('emarecloud.tenant')


def register_tenant_middleware(app):
    """Tenant middleware'ini uygulamaya kaydeder."""

    @app.before_request
    def resolve_tenant():
        """Her request'te mevcut kullanıcının organizasyonunu çözümler.

        g.tenant_id    → Aktif organizasyon ID'si (None ise global/süper admin)
        g.tenant       → Organization nesnesi (lazy load)
        g.is_global    → Süper admin global erişim mi?
        """
        g.tenant_id = None
        g.tenant = None
        g.is_global = False

        # Statik dosyalar ve login sayfaları tenant gerektirmez
        if request.path.startswith(('/static/', '/login', '/landing', '/favicon')):
            return

        if not current_user or not current_user.is_authenticated:
            # API token ile gelen request'leri kontrol et
            _resolve_api_token_tenant()
            return

        # Süper admin global erişime sahip
        if current_user.role == 'super_admin':
            g.is_global = True
            # Süper admin belirli bir org context'inde çalışabilir
            org_id = request.headers.get('X-Org-Id') or request.args.get('org_id')
            if org_id:
                try:
                    g.tenant_id = int(org_id)
                except (ValueError, TypeError):
                    pass
            elif current_user.org_id:
                g.tenant_id = current_user.org_id
            return

        # Normal kullanıcılar kendi org'larına bağlı
        if current_user.org_id:
            g.tenant_id = current_user.org_id
        # org_id yoksa (eski veriler) → None kalır, uyumluluk modu


def _resolve_api_token_tenant():
    """API token'dan tenant bilgisini çözümler."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return

    from models import ApiToken
    raw_token = auth_header[7:]
    token = ApiToken.find_by_raw_token(raw_token)
    if token and token.org_id:
        g.tenant_id = token.org_id


def get_tenant_id() -> int | None:
    """Mevcut request'in tenant ID'sini döndürür."""
    return getattr(g, 'tenant_id', None)


def is_global_access() -> bool:
    """Süper admin global erişim mi kontrol eder."""
    return getattr(g, 'is_global', False)


def tenant_filter(query, model, allow_global: bool = True):
    """
    Sorguya tenant filtresi uygular.

    Args:
        query: SQLAlchemy sorgusu
        model: Filtrelenecek model (org_id alanı olmalı)
        allow_global: True ise süper admin tüm verileri görebilir

    Returns:
        Filtrelenmiş sorgu
    """
    tenant_id = get_tenant_id()

    # Süper admin global erişimde → filtre uygulanmaz
    if allow_global and is_global_access() and not tenant_id:
        return query

    # Tenant ID varsa filtrele
    if tenant_id:
        return query.filter(model.org_id == tenant_id)

    # org_id olmayan kayıtlar (geriye uyumluluk)
    return query.filter(model.org_id.is_(None))


def check_tenant_access(obj) -> bool:
    """
    Bir nesneye tenant erişim kontrolü yapar.

    Args:
        obj: Kontrol edilecek nesne (org_id alanı olmalı)

    Returns:
        True → erişim var, False → yok
    """
    # Süper admin her şeye erişebilir
    if is_global_access():
        return True

    tenant_id = get_tenant_id()
    obj_org_id = getattr(obj, 'org_id', None)

    # Her ikisi de None → uyumluluk modu
    if tenant_id is None and obj_org_id is None:
        return True

    return obj_org_id == tenant_id


def check_quota(org_id: int, resource: str) -> tuple[bool, str]:
    """
    Organizasyonun kaynak kotasını kontrol eder.

    Args:
        org_id: Organizasyon ID
        resource: Kaynak adı (servers, users, storage_gb, backups, vms)

    Returns:
        (True, '') → limit aşılmamış
        (False, 'hata mesajı') → limit aşılmış
    """
    from models import ResourceQuota, ServerCredential, User

    quota = ResourceQuota.query.filter_by(org_id=org_id).first()
    if not quota:
        return True, ''

    resource_counts = {
        'servers': lambda: ServerCredential.query.filter_by(org_id=org_id).count(),
        'users': lambda: User.query.filter_by(org_id=org_id).count(),
    }

    counter = resource_counts.get(resource)
    if not counter:
        return True, ''

    current = counter()
    limit = getattr(quota, f'max_{resource}', None)
    if limit is not None and current >= limit:
        return False, f'{resource} kotası aşıldı (mevcut: {current}, limit: {limit})'

    return True, ''
