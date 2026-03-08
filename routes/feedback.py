"""
EmareCloud — Geri Bildirim Sistemi
Kullanıcılar hata bildirir, öneri gönderir; adminler yanıtlar.
---
GET  /feedback              → Admin liste sayfası
GET  /api/feedback/my       → Kullanıcının kendi geri bildirimleri (JSON)
POST /api/feedback          → Yeni geri bildirim gönder
POST /api/ai/chat           → CloudBot AI (Gemini / kural‑tabanlı)
PATCH /api/feedback/<id>/status  → Admin: durum güncelle
POST  /api/feedback/<id>/reply   → Admin: yanıt ver
"""

from datetime import datetime

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from audit import log_action
from core.tenant import get_tenant_id, is_global_access
from extensions import db
from models import Feedback, User
from rbac import permission_required

feedback_bp = Blueprint('feedback', __name__)

def _tenant_feedback_query():
    """Tenant filtrelenmiş Feedback sorgusu (User.org_id üzerinden)."""
    query = Feedback.query
    if is_global_access() and not get_tenant_id():
        return query
    tenant_id = get_tenant_id()
    if tenant_id is not None:
        query = query.join(User, Feedback.user_id == User.id).filter(User.org_id == tenant_id)
    else:
        query = query.join(User, Feedback.user_id == User.id).filter(User.org_id.is_(None))
    return query


def _get_feedback_with_access(fb_id):
    """Feedback nesnesini tenant erişim kontrolü ile döndürür."""
    fb = db.session.get(Feedback, fb_id)
    if not fb:
        return None
    if is_global_access() and not get_tenant_id():
        return fb
    tenant_id = get_tenant_id()
    user = db.session.get(User, fb.user_id)
    if not user:
        return None
    if tenant_id is not None:
        return fb if user.org_id == tenant_id else None
    return fb if user.org_id is None else None

# ═══════════════════════════════════════════════════════════
#  KULLANICI ENDPOINTLERİ
# ═══════════════════════════════════════════════════════════

@feedback_bp.route('/api/feedback', methods=['POST'])
@login_required
def submit_feedback():
    """Yeni geri bildirim gönder."""
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message or len(message) < 3:
        return jsonify(success=False, message='Açıklama en az 3 karakter olmalı.'), 400
    if len(message) > 2000:
        return jsonify(success=False, message='Açıklama en fazla 2000 karakter.'), 400

    category = data.get('category', 'bug')
    if category not in Feedback.CATEGORIES:
        category = 'bug'
    priority = data.get('priority', 'normal')
    if priority not in Feedback.PRIORITIES:
        priority = 'normal'

    fb = Feedback(
        user_id=current_user.id,
        message=message,
        category=category,
        priority=priority,
        page_url=(data.get('page_url') or '')[:500],
        status='open',
    )
    db.session.add(fb)
    db.session.commit()

    log_action('feedback_submit', current_user.id, details={
        'feedback_id': fb.id,
        'category': category,
        'priority': priority,
    })

    return jsonify(success=True,
                   message='Geri bildiriminiz alındı. Teşekkür ederiz!',
                   feedback=fb.to_dict())


@feedback_bp.route('/api/feedback/my')
@login_required
def my_feedback():
    """Kullanıcının kendi geri bildirimleri (JSON)."""
    items = (Feedback.query
             .filter_by(user_id=current_user.id)
             .order_by(Feedback.created_at.desc())
             .limit(50)
             .all())
    # okunmamış admin yanıtı sayısı
    unread = sum(1 for f in items if f.admin_reply and f.status == 'in_progress')
    return jsonify(success=True,
                   messages=[f.to_dict() for f in items],
                   unread=unread)


# ═══════════════════════════════════════════════════════════
#  ADMİN ENDPOINTLERİ
# ═══════════════════════════════════════════════════════════

@feedback_bp.route('/feedback')
@login_required
@permission_required('admin.access')
def feedback_admin():
    """Admin geri bildirim yönetim sayfası."""
    status_filter   = request.args.get('status', '')
    category_filter = request.args.get('category', '')
    priority_filter = request.args.get('priority', '')
    search          = request.args.get('q', '').strip()

    query = _tenant_feedback_query()

    if status_filter:
        query = query.filter(Feedback.status == status_filter)
    if category_filter:
        query = query.filter(Feedback.category == category_filter)
    if priority_filter:
        query = query.filter(Feedback.priority == priority_filter)
    if search:
        query = query.filter(Feedback.message.ilike(f'%{search}%'))

    items = query.order_by(Feedback.created_at.desc()).all()

    base = _tenant_feedback_query()
    stats = {
        'total':       base.count(),
        'open':        base.filter(Feedback.status == 'open').count(),
        'in_progress': base.filter(Feedback.status == 'in_progress').count(),
        'resolved':    base.filter(Feedback.status == 'resolved').count(),
        'bugs':        base.filter(Feedback.category == 'bug', Feedback.status == 'open').count(),
    }

    return render_template('feedback_admin.html',
                           feedbacks=items,
                           stats=stats,
                           status_filter=status_filter,
                           category_filter=category_filter,
                           priority_filter=priority_filter,
                           search=search)


@feedback_bp.route('/api/feedback/<int:fb_id>/status', methods=['PATCH'])
@login_required
@permission_required('admin.access')
def update_feedback_status(fb_id):
    """Admin: Durum güncelle."""
    fb = _get_feedback_with_access(fb_id)
    if not fb:
        return jsonify(success=False, message='Geri bildirim bulunamadı'), 404
    data = request.get_json(silent=True) or {}
    status = data.get('status', '')
    if status not in Feedback.STATUSES:
        return jsonify(success=False, message='Geçersiz durum.'), 400

    fb.status = status
    db.session.commit()
    log_action('feedback_status_update', current_user.id,
               details={'feedback_id': fb_id, 'status': status})
    return jsonify(success=True, status=status, status_label=fb.status_label)


@feedback_bp.route('/api/feedback/<int:fb_id>/reply', methods=['POST'])
@login_required
@permission_required('admin.access')
def reply_feedback(fb_id):
    """Admin: Yanıt ver."""
    fb = _get_feedback_with_access(fb_id)
    if not fb:
        return jsonify(success=False, message='Geri bildirim bulunamadı'), 404
    data = request.get_json(silent=True) or {}
    reply = (data.get('reply') or '').strip()
    if not reply or len(reply) < 2:
        return jsonify(success=False, message='Yanıt boş olamaz.'), 400

    fb.admin_reply = reply
    fb.replied_by  = current_user.id
    fb.replied_at  = datetime.utcnow()
    if fb.status == 'open':
        fb.status = 'in_progress'
    db.session.commit()

    log_action('feedback_reply', current_user.id,
               details={'feedback_id': fb_id})
    return jsonify(success=True, message='Yanıt gönderildi.')


# ═══════════════════════════════════════════════════════════
#  CLOUDBOT — AI Chat API  (EmareAPI → Gemini)
# ═══════════════════════════════════════════════════════════

@feedback_bp.route('/api/ai/chat', methods=['POST'])
@login_required
def ai_chat():
    """
    Floating CloudBot için AI chat endpoint.
    Gemini'ye EmareAPI üzerinden bağlanır; başarısız olursa kural‑tabanlıya düşer.
    """
    data = request.get_json(silent=True) or {}
    question = (data.get('message') or '').strip()
    if not question:
        return jsonify(success=False, message='Mesaj boş.'), 400

    # Kullanıcı bağlamı (ET bakiyesi, plan bilgisi vs.)
    context_lines = []
    try:
        context_lines.append(f'Kullanıcı: {current_user.username}')
        context_lines.append(f'Rol: {current_user.role}')
        if hasattr(current_user, 'et_balance'):
            context_lines.append(f'ET Bakiye: {int(current_user.et_balance):,} ET')
    except Exception:
        pass
    user_context = '\n'.join(context_lines)

    try:
        from ai_assistant import ai_analyze
        result = ai_analyze(question, user_context)
        return jsonify(
            success=True,
            response=result.get('response', ''),
            suggestions=result.get('suggestions', []),
            model=result.get('model', 'rule-based'),
        )
    except Exception as e:
        return jsonify(success=False,
                       message=f'AI hatası: {str(e)}'), 500
