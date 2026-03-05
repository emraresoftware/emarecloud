"""
EmareCloud — Audit Log Sistemi
Her kritik işlem kaydedilir: kullanıcı, aksiyon, hedef, IP, zaman damgası, sonuç.
"""

import json
from datetime import datetime
from functools import wraps

from flask import request
from flask_login import current_user


def log_action(action: str, target_type: str = None, target_id: str = None,
               details: dict = None, success: bool = True):
    """
    Bir aksiyonu audit log'a kaydeder.

    Args:
        action: Aksiyon adı (ör: 'server.connect', 'firewall.add_rule')
        target_type: Hedef türü (ör: 'server', 'user', 'firewall')
        target_id: Hedef ID (ör: server_id)
        details: Ek detaylar (dict → JSON olarak kaydedilir)
        success: İşlem başarılı mı
    """
    from extensions import db
    from models import AuditLog

    try:
        entry = AuditLog(
            user_id=current_user.id if current_user and current_user.is_authenticated else None,
            username=current_user.username if current_user and current_user.is_authenticated else 'anonymous',
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id else None,
            ip_address=request.remote_addr if request else None,
            user_agent=str(request.user_agent)[:300] if request else None,
            details=json.dumps(details, ensure_ascii=False) if details else None,
            success=success,
            created_at=datetime.utcnow(),
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass


def audit_action(action_name: str, target_type: str = None):
    """
    Fonksiyon çağrılarını otomatik olarak audit log'a kaydeden dekoratör.

    Kullanım:
        @audit_action('server.connect', 'server')
        def connect_server(server_id):
            ...
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            # URL parametrelerinden target_id çıkar
            target_id = (
                kwargs.get('server_id') or
                kwargs.get('name') or
                kwargs.get('protocol_id') or
                kwargs.get('user_id')
            )
            try:
                result = f(*args, **kwargs)
                log_action(action_name, target_type=target_type,
                          target_id=target_id, success=True)
                return result
            except Exception as e:
                log_action(action_name, target_type=target_type,
                          target_id=target_id,
                          details={'error': str(e)}, success=False)
                raise
        return decorated
    return decorator
