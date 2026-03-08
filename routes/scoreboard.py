"""
EmareCloud — Geliştirici Scoreboard API
Aktif geliştirici durumları, online/offline bilgisi, üye istatistikleri.
"""

from datetime import datetime, timedelta

from flask import Blueprint, jsonify
from flask_login import login_required

from core.helpers import _build_tenant_query
from extensions import db
from models import User
from rbac import permission_required

scoreboard_bp = Blueprint('scoreboard', __name__)


@scoreboard_bp.route('/api/scoreboard', methods=['GET'])
@login_required
@permission_required('scoreboard.view')
def scoreboard_data():
    """Tüm geliştirici durumlarını döndürür."""
    users = _build_tenant_query(User).filter_by(is_active_user=True).all()
    five_min_ago = datetime.utcnow() - timedelta(minutes=5)

    developers = []
    online_count = 0
    for u in users:
        is_online = u.last_seen and u.last_seen > five_min_ago
        if is_online:
            online_count += 1

        # Son görülme zamanı insana okunur format
        if u.last_seen:
            delta = datetime.utcnow() - u.last_seen
            if delta.total_seconds() < 60:
                seen_text = 'Şu an aktif'
            elif delta.total_seconds() < 3600:
                seen_text = f'{int(delta.total_seconds() // 60)} dk önce'
            elif delta.total_seconds() < 86400:
                seen_text = f'{int(delta.total_seconds() // 3600)} saat önce'
            else:
                seen_text = f'{int(delta.days)} gün önce'
        else:
            seen_text = 'Hiç giriş yapmadı'

        developers.append({
            'id': u.id,
            'username': u.username,
            'email': u.email,
            'role': u.role,
            'is_online': is_online,
            'last_seen': u.last_seen.isoformat() if u.last_seen else None,
            'last_seen_text': seen_text,
            'current_activity': u.current_activity or '-',
            'last_login': u.last_login.isoformat() if u.last_login else None,
            'created_at': u.created_at.isoformat() if u.created_at else None,
        })

    # Online olanlar üstte, sonra son görülmeye göre sıralama
    developers.sort(key=lambda d: (not d['is_online'], d['last_seen'] or ''), reverse=False)
    developers.sort(key=lambda d: (not d['is_online'],))

    return jsonify({
        'success': True,
        'stats': {
            'total_members': len(users),
            'online_now': online_count,
            'offline': len(users) - online_count,
            'today_active': sum(
                1 for u in users
                if u.last_seen and u.last_seen > datetime.utcnow() - timedelta(hours=24)
            ),
        },
        'developers': developers,
    })


@scoreboard_bp.route('/api/scoreboard/heartbeat', methods=['POST'])
@login_required
def scoreboard_heartbeat():
    """Frontend'den heartbeat gelir — kullanıcının hâlâ aktif olduğunu doğrular."""
    from flask_login import current_user
    current_user.last_seen = datetime.utcnow()
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    return jsonify({'success': True})
