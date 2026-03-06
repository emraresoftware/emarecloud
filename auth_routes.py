"""
EmareCloud — Auth Blueprint
Kimlik doğrulama, oturum yönetimi, kullanıcı yönetimi, denetim günlüğü.
"""

import json
import re
import time
from collections import defaultdict
from datetime import datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from audit import log_action
from extensions import db
from models import ApiToken, AuditLog, User
from rbac import PERMISSION_GROUPS, get_all_roles, role_required

auth_bp = Blueprint('auth', __name__)

# ==================== ŞİFRE KARMAŞIKLIK KURALLARI ====================

_PASSWORD_RULES = [
    (r'.{8,}', 'Şifre en az 8 karakter olmalı'),
    (r'[A-Z]', 'Şifre en az 1 büyük harf içermeli'),
    (r'[a-z]', 'Şifre en az 1 küçük harf içermeli'),
    (r'[0-9]', 'Şifre en az 1 rakam içermeli'),
    (r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/~`]', 'Şifre en az 1 özel karakter içermeli'),
]


def validate_password(password: str) -> tuple[bool, str]:
    """Şifre karmaşıklık kurallarını kontrol eder. (ok, hata_mesajı) döndürür."""
    for pattern, message in _PASSWORD_RULES:
        if not re.search(pattern, password):
            return False, message
    return True, ''

# ==================== RATE LIMITING (Brute Force Koruması) ====================

_login_attempts: dict[str, list[float]] = defaultdict(list)
_MAX_LOGIN_ATTEMPTS = 5
_LOGIN_WINDOW = 300  # 5 dakika


def _is_rate_limited(ip: str) -> bool:
    now = time.time()
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < _LOGIN_WINDOW]
    return len(_login_attempts[ip]) >= _MAX_LOGIN_ATTEMPTS


def _record_attempt(ip: str):
    _login_attempts[ip].append(time.time())


# ==================== CSRF Doğrulama ====================

def _validate_csrf():
    """Form gönderimlerinde CSRF token doğrulaması."""
    token = request.form.get('csrf_token', '')
    if not token or token != session.get('csrf_token'):
        from flask import abort
        abort(403)


# ==================== AUTH ROUTES ====================

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Giriş sayfası."""
    if current_user.is_authenticated:
        return redirect(url_for('pages.dashboard'))

    if request.method == 'POST':
        _validate_csrf()
        ip = request.remote_addr

        # Rate limiting
        if _is_rate_limited(ip):
            log_action('auth.login_rate_limited', details={'ip': ip}, success=False)
            flash('Çok fazla başarısız deneme. 5 dakika bekleyin.', 'error')
            return render_template('auth/login.html'), 429

        username = (request.form.get('username') or '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password) and user.is_active:
            # 2FA kontrolü
            if user.totp_enabled and user.totp_secret:
                # 2FA doğrulaması gerekiyor → geçici session'a kaydet
                session['_2fa_user_id'] = user.id
                session['_2fa_remember'] = remember
                return redirect(url_for('auth.verify_2fa'))

            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            log_action('auth.login', target_type='user', target_id=user.id)

            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('pages.dashboard'))

        _record_attempt(ip)
        log_action('auth.login_failed', details={'username': username}, success=False)
        flash('Kullanıcı adı veya şifre hatalı.', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Üye ol sayfası."""
    if current_user.is_authenticated:
        return redirect(url_for('pages.dashboard'))

    if request.method == 'POST':
        _validate_csrf()
        username  = (request.form.get('username') or '').strip()
        email     = (request.form.get('email') or '').strip() or None
        password  = request.form.get('password', '')
        password2 = request.form.get('password2', '')

        # Validasyon
        if not username or len(username) < 3:
            flash('Kullanıcı adı en az 3 karakter olmalı.', 'error')
            return render_template('auth/register.html')

        if User.query.filter_by(username=username).first():
            flash('Bu kullanıcı adı zaten alınmış.', 'error')
            return render_template('auth/register.html')

        if email and User.query.filter_by(email=email).first():
            flash('Bu e-posta adresi zaten kayıtlı.', 'error')
            return render_template('auth/register.html')

        if password != password2:
            flash('Şifreler eşleşmiyor.', 'error')
            return render_template('auth/register.html')

        for pattern, msg in _PASSWORD_RULES:
            if not re.search(pattern, password):
                flash(msg, 'error')
                return render_template('auth/register.html')

        user = User(
            username=username,
            email=email,
            role='read_only',
            is_active_user=True,
            et_balance=100000.0,   # 🎁 Hoş geldin hediyesi — 100.000 ET
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        log_action('auth.register', target_type='user', target_id=user.id,
                   details={'username': username, 'et_welcome_gift': 100000})
        flash('Hesabınız oluşturuldu! 🎁 100.000 ET hoş geldin hediyeniz hesabınıza eklendi.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    """Çıkış."""
    log_action('auth.logout')
    logout_user()
    flash('Oturumunuz kapatıldı.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """Profil sayfası — şifre değiştir, e-posta güncelle."""
    if request.method == 'POST':
        _validate_csrf()
        action = request.form.get('action')

        if action == 'change_password':
            current_pw = request.form.get('current_password', '')
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')

            if not current_user.check_password(current_pw):
                flash('Mevcut şifre hatalı.', 'error')
            else:
                pw_ok, pw_err = validate_password(new_pw)
                if not pw_ok:
                    flash(pw_err, 'error')
                elif new_pw != confirm_pw:
                    flash('Yeni şifreler eşleşmiyor.', 'error')
                else:
                    current_user.set_password(new_pw)
                    db.session.commit()
                    log_action('auth.password_change', target_type='user',
                              target_id=current_user.id)
                    flash('Şifreniz başarıyla değiştirildi.', 'success')

        elif action == 'update_profile':
            email = (request.form.get('email') or '').strip()
            if email:
                existing = User.query.filter(
                    User.email == email, User.id != current_user.id
                ).first()
                if existing:
                    flash('Bu e-posta adresi zaten kullanılıyor.', 'error')
                else:
                    current_user.email = email
                    db.session.commit()
                    log_action('auth.profile_update', target_type='user',
                              target_id=current_user.id)
                    flash('Profil güncellendi.', 'success')

    return render_template('auth/profile.html')


# ==================== ADMIN: KULLANICI YÖNETİMİ ====================

@auth_bp.route('/admin/users')
@login_required
@role_required('super_admin', 'admin')
def admin_users():
    """Kullanıcı yönetimi sayfası."""
    users = User.query.order_by(User.created_at.desc()).all()
    roles = get_all_roles()
    return render_template('admin/users.html', users=users, roles=roles)


@auth_bp.route('/admin/audit')
@login_required
@role_required('super_admin', 'admin')
def audit_logs_page():
    """Denetim günlüğü sayfası."""
    return render_template('admin/audit.html')


@auth_bp.route('/admin/panel')
@login_required
@role_required('super_admin')
def admin_panel():
    """Süper yönetici kontrol paneli — kullanıcı & modül yetki yönetimi."""
    users = User.query.order_by(User.created_at.desc()).all()
    roles = get_all_roles()
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active_user=True).count()
    return render_template(
        'admin/panel.html',
        users=users,
        roles=roles,
        perm_groups=PERMISSION_GROUPS,
        total_users=total_users,
        active_users=active_users,
    )


# ==================== KULLANICI API ====================

@auth_bp.route('/api/users', methods=['GET'])
@login_required
@role_required('super_admin', 'admin')
def api_list_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify({'success': True, 'users': [u.to_dict() for u in users]})


@auth_bp.route('/api/users', methods=['POST'])
@login_required
@role_required('super_admin')
def api_create_user():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password', '')
    email = (data.get('email') or '').strip()
    role = data.get('role', 'read_only')

    if not username or not password:
        return jsonify({'success': False, 'message': 'Kullanıcı adı ve şifre gerekli'}), 400
    pw_ok, pw_err = validate_password(password)
    if not pw_ok:
        return jsonify({'success': False, 'message': pw_err}), 400
    if len(username) < 3:
        return jsonify({'success': False, 'message': 'Kullanıcı adı en az 3 karakter olmalı'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'success': False, 'message': 'Bu kullanıcı adı zaten mevcut'}), 409
    if role not in ('super_admin', 'admin', 'operator', 'read_only', 'custom'):
        return jsonify({'success': False, 'message': 'Geçersiz rol'}), 400

    # Custom rol için en az bir izin zorunlu
    permissions = data.get('permissions')
    if role == 'custom' and (not permissions or not isinstance(permissions, list) or len(permissions) == 0):
        return jsonify({'success': False, 'message': 'Custom rol için en az bir modül seçmelisiniz'}), 400

    # Custom rol → read_only base + custom_permissions override
    stored_role = 'read_only' if role == 'custom' else role

    user = User(
        username=username,
        email=email or None,
        role=stored_role,
        created_by=current_user.id,
    )
    user.set_password(password)

    # Özel modül izinleri (custom rol için zorunlu, diğerleri opsiyonel)
    if permissions and isinstance(permissions, list) and len(permissions) > 0:
        user.custom_permissions_json = json.dumps(sorted(set(permissions)))

    db.session.add(user)
    db.session.commit()

    log_action('user.create', target_type='user', target_id=user.id,
              details={'username': username, 'role': role,
                       'stored_role': stored_role,
                       'custom_perms': bool(permissions)})
    return jsonify({'success': True, 'message': 'Kullanıcı oluşturuldu', 'user': user.to_dict()})


@auth_bp.route('/api/users/<int:user_id>', methods=['PUT'])
@login_required
@role_required('super_admin')
def api_update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı'}), 404

    data = request.get_json(silent=True) or {}
    changes = {}

    if 'role' in data:
        if user.id == current_user.id:
            return jsonify({'success': False, 'message': 'Kendi rolünüzü değiştiremezsiniz'}), 400
        user.role = data['role']
        changes['role'] = data['role']

    if 'is_active' in data:
        if user.id == current_user.id:
            return jsonify({'success': False, 'message': 'Kendinizi devre dışı bırakamazsınız'}), 400
        user.is_active_user = bool(data['is_active'])
        changes['is_active'] = data['is_active']

    if data.get('password'):
        pw_ok, pw_err = validate_password(data['password'])
        if not pw_ok:
            return jsonify({'success': False, 'message': pw_err}), 400
        user.set_password(data['password'])
        changes['password_changed'] = True

    if 'email' in data:
        user.email = (data['email'] or '').strip() or None
        changes['email'] = data.get('email')

    db.session.commit()
    log_action('user.update', target_type='user', target_id=user_id, details=changes)
    return jsonify({'success': True, 'message': 'Kullanıcı güncellendi', 'user': user.to_dict()})


@auth_bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
@role_required('super_admin')
def api_delete_user(user_id):
    if user_id == current_user.id:
        return jsonify({'success': False, 'message': 'Kendinizi silemezsiniz'}), 400
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı'}), 404
    username = user.username
    db.session.delete(user)
    db.session.commit()
    log_action('user.delete', target_type='user', target_id=user_id,
              details={'username': username})
    return jsonify({'success': True, 'message': f'{username} silindi'})


# ==================== AUDIT LOG API ====================

@auth_bp.route('/api/audit-logs', methods=['GET'])
@login_required
@role_required('super_admin', 'admin')
def api_audit_logs():
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 50, type=int), 200)
    action_filter = request.args.get('action', '')
    user_filter = request.args.get('username', '')

    query = AuditLog.query.order_by(AuditLog.created_at.desc())
    if action_filter:
        query = query.filter(AuditLog.action.like(f'%{action_filter}%'))
    if user_filter:
        query = query.filter(AuditLog.username.like(f'%{user_filter}%'))

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'success': True,
        'logs': [log.to_dict() for log in pagination.items],
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page,
    })


# ==================== 2FA (TOTP) ====================

@auth_bp.route('/2fa/verify', methods=['GET', 'POST'])
def verify_2fa():
    """2FA doğrulama sayfası — login sonrası TOTP kodu girer."""
    user_id = session.get('_2fa_user_id')
    if not user_id:
        return redirect(url_for('auth.login'))

    user = db.session.get(User, user_id)
    if not user:
        session.pop('_2fa_user_id', None)
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        code = (request.form.get('code') or '').strip()
        remember = session.get('_2fa_remember', False)

        verified = False
        # TOTP kodu dene
        if code and len(code) == 6:
            import pyotp
            totp = pyotp.TOTP(user.totp_secret)
            verified = totp.verify(code, valid_window=1)

        # Kurtarma kodu dene
        if not verified and code:
            verified = user.use_recovery_code(code)

        if verified:
            session.pop('_2fa_user_id', None)
            session.pop('_2fa_remember', None)
            login_user(user, remember=remember)
            user.last_login = datetime.utcnow()
            db.session.commit()
            log_action('auth.login_2fa', target_type='user', target_id=user.id)
            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('pages.dashboard'))

        log_action('auth.2fa_failed', target_type='user', target_id=user.id, success=False)
        flash('Geçersiz doğrulama kodu.', 'error')

    return render_template('auth/verify_2fa.html')


@auth_bp.route('/api/2fa/setup', methods=['POST'])
@login_required
def api_2fa_setup():
    """2FA kurulumu — QR kod + secret döndürür."""
    import pyotp
    if current_user.totp_enabled:
        return jsonify({'success': False, 'message': '2FA zaten aktif'}), 400

    secret = pyotp.random_base32()
    current_user.totp_secret = secret
    db.session.commit()

    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=current_user.email or current_user.username,
        issuer_name='EmareCloud'
    )

    # QR code → base64
    import base64
    import io

    import qrcode
    qr = qrcode.make(provisioning_uri)
    buf = io.BytesIO()
    qr.save(buf, format='PNG')
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    log_action('auth.2fa_setup_initiated', target_type='user', target_id=current_user.id)
    return jsonify({
        'success': True,
        'secret': secret,
        'qr_code': f'data:image/png;base64,{qr_b64}',
        'provisioning_uri': provisioning_uri,
    })


@auth_bp.route('/api/2fa/enable', methods=['POST'])
@login_required
def api_2fa_enable():
    """2FA'yı doğrulayıp aktifleştirir — kurulum kodunu onaylar."""
    import pyotp
    data = request.get_json(silent=True) or {}
    code = (data.get('code') or '').strip()

    if not current_user.totp_secret:
        return jsonify({'success': False, 'message': 'Önce 2FA kurulumu yapın'}), 400
    if current_user.totp_enabled:
        return jsonify({'success': False, 'message': '2FA zaten aktif'}), 400

    totp = pyotp.TOTP(current_user.totp_secret)
    if not totp.verify(code, valid_window=1):
        return jsonify({'success': False, 'message': 'Geçersiz kod'}), 400

    current_user.totp_enabled = True
    recovery_codes = current_user.generate_recovery_codes()
    db.session.commit()

    log_action('auth.2fa_enabled', target_type='user', target_id=current_user.id)
    return jsonify({
        'success': True,
        'message': '2FA başarıyla aktifleştirildi',
        'recovery_codes': recovery_codes,
    })


@auth_bp.route('/api/2fa/disable', methods=['POST'])
@login_required
def api_2fa_disable():
    """2FA'yı devre dışı bırakır — şifre doğrulaması gerektirir."""
    data = request.get_json(silent=True) or {}
    password = data.get('password', '')

    if not current_user.check_password(password):
        return jsonify({'success': False, 'message': 'Şifre hatalı'}), 400

    current_user.totp_enabled = False
    current_user.totp_secret = None
    current_user.recovery_codes_json = None
    db.session.commit()

    log_action('auth.2fa_disabled', target_type='user', target_id=current_user.id)
    return jsonify({'success': True, 'message': '2FA devre dışı bırakıldı'})


# ==================== API TOKEN SİSTEMİ ====================

@auth_bp.route('/api/tokens', methods=['GET'])
@login_required
def api_list_tokens():
    """Kullanıcının API token'larını listeler."""
    tokens = ApiToken.query.filter_by(
        user_id=current_user.id, is_active=True
    ).order_by(ApiToken.created_at.desc()).all()
    return jsonify({'success': True, 'tokens': [t.to_dict() for t in tokens]})


@auth_bp.route('/api/tokens', methods=['POST'])
@login_required
def api_create_token():
    """Yeni API token oluşturur."""
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'message': 'Token adı gerekli'}), 400

    # Kullanıcı başına max 10 aktif token
    active_count = ApiToken.query.filter_by(
        user_id=current_user.id, is_active=True
    ).count()
    if active_count >= 10:
        return jsonify({'success': False, 'message': 'Maksimum 10 aktif token oluşturabilirsiniz'}), 400

    raw_token, token_hash, prefix = ApiToken.generate_token()

    # Opsiyonel süre (gün cinsinden)
    expires_days = data.get('expires_days')
    expires_at = None
    if expires_days:
        from datetime import timedelta
        expires_at = datetime.utcnow() + timedelta(days=int(expires_days))

    token = ApiToken(
        user_id=current_user.id,
        org_id=current_user.org_id,
        token_hash=token_hash,
        token_prefix=prefix,
        name=name,
        permissions=json.dumps(data.get('permissions', [])),
        expires_at=expires_at,
    )
    db.session.add(token)
    db.session.commit()

    log_action('token.create', target_type='token', target_id=token.id,
              details={'name': name})
    return jsonify({
        'success': True,
        'message': 'Token oluşturuldu',
        'token': raw_token,  # Sadece bir kez gösterilir!
        'token_info': token.to_dict(),
    })


@auth_bp.route('/api/tokens/<int:token_id>', methods=['DELETE'])
@login_required
def api_delete_token(token_id):
    """API token'ı iptal eder."""
    token = db.session.get(ApiToken, token_id)
    if not token or token.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Token bulunamadı'}), 404

    token.is_active = False
    db.session.commit()

    log_action('token.revoke', target_type='token', target_id=token_id)
    return jsonify({'success': True, 'message': 'Token iptal edildi'})


# ==================== ADMIN PANEL: İZİN YÖNETİMİ ====================

@auth_bp.route('/api/users/<int:user_id>/permissions', methods=['GET'])
@login_required
@role_required('super_admin')
def api_get_user_permissions(user_id):
    """Kullanıcının özel izin listesini döndürür."""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı'}), 404
    from rbac import get_permissions_for_role
    role_perms = list(get_permissions_for_role(user.role))
    return jsonify({
        'success': True,
        'user_id': user_id,
        'role': user.role,
        'has_custom_perms': bool(user.custom_permissions_json),
        'permissions': user.custom_permissions,
        'role_permissions': role_perms,
    })


@auth_bp.route('/api/users/<int:user_id>/permissions', methods=['PUT'])
@login_required
@role_required('super_admin')
def api_set_user_permissions(user_id):
    """Kullanıcıya özel modül izinlerini kaydeder."""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı'}), 404

    data = request.get_json(silent=True) or {}
    # permissions: liste — boş gönderilirse özel izin kaldırılır (rol bazlı fallback)
    perms = data.get('permissions')
    if perms is None:
        return jsonify({'success': False, 'message': '"permissions" alanı gerekli'}), 400

    if perms:
        user.custom_permissions = list(set(perms))  # tekrar temizle
    else:
        user.custom_permissions_json = None  # özel izni kaldır

    db.session.commit()
    log_action('user.permissions_update', target_type='user', target_id=user_id,
              details={'permissions': perms or 'rol_bazli_sifirlandi'})
    return jsonify({
        'success': True,
        'message': 'İzinler güncellendi',
        'permissions': user.custom_permissions,
    })


@auth_bp.route('/api/users/<int:user_id>/toggle-active', methods=['POST'])
@login_required
@role_required('super_admin')
def api_toggle_user_active(user_id):
    """Kullanıcıyı aktif / pasif yapar."""
    if user_id == current_user.id:
        return jsonify({'success': False, 'message': 'Kendinizi devre dışı bırakamazsınız'}), 400
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı'}), 404
    user.is_active_user = not user.is_active_user
    db.session.commit()
    state = 'aktif' if user.is_active_user else 'pasif'
    log_action('user.toggle_active', target_type='user', target_id=user_id,
              details={'state': state})
    return jsonify({'success': True, 'message': f'Kullanıcı {state} yapıldı', 'is_active': user.is_active_user})


@auth_bp.route('/api/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
@role_required('super_admin')
def api_reset_user_password(user_id):
    """Kullanıcı şifresini sıfırlar (doğrulama bypass)."""
    if user_id == current_user.id:
        return jsonify({'success': False, 'message': 'Kendi şifrenizi buradan değiştiremezsiniz'}), 400
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı'}), 404
    data = request.get_json(silent=True) or {}
    new_password = data.get('password', '').strip()
    if len(new_password) < 6:
        return jsonify({'success': False, 'message': 'Şifre en az 6 karakter olmalı'}), 400
    user.set_password(new_password)
    db.session.commit()
    log_action('user.password_reset', target_type='user', target_id=user_id)
    return jsonify({'success': True, 'message': 'Şifre güncellendi'})


@auth_bp.route('/api/users/<int:user_id>/impersonate', methods=['POST'])
@login_required
@role_required('super_admin')
def api_impersonate_user(user_id):
    """Super admin olarak başka bir kullanıcının hesabına geçiş yapar."""
    if user_id == current_user.id:
        return jsonify({'success': False, 'message': 'Zaten kendi hesabınızdasınız'}), 400
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'success': False, 'message': 'Kullanıcı bulunamadı'}), 404
    if not user.is_active_user:
        return jsonify({'success': False, 'message': 'Pasif kullanıcıya geçiş yapılamaz'}), 400

    # Mevcut admin oturumunu kaydet
    session['_impersonate_admin_id'] = current_user.id
    log_action('user.impersonate', target_type='user', target_id=user_id,
              details={'target_username': user.username})

    # Hedef kullanıcı olarak giriş yap
    login_user(user)
    return jsonify({'success': True, 'message': f'{user.username} olarak giriş yapıldı', 'redirect': '/dashboard'})


@auth_bp.route('/admin/return', methods=['GET'])
@login_required
def return_from_impersonate():
    """Impersonate modundan çıkıp admin hesabına geri döner."""
    admin_id = session.pop('_impersonate_admin_id', None)
    if not admin_id:
        flash('Geçiş oturumu bulunamadı.', 'error')
        return redirect(url_for('pages.dashboard'))

    admin_user = db.session.get(User, admin_id)
    if not admin_user:
        flash('Admin hesabı bulunamadı.', 'error')
        return redirect(url_for('auth.login'))

    log_action('user.impersonate_return', target_type='user', target_id=admin_id)
    login_user(admin_user)
    flash('Admin hesabınıza geri döndünüz.', 'success')
    return redirect(url_for('auth.admin_panel'))
