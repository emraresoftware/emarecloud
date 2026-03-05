"""
EmareCloud — Monitoring API Route'ları
Alert kuralları, webhook, zamanlanmış görevler, yedekleme, metrik geçmişi.
"""

import logging
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from extensions import db
from models import (
    AlertHistory,
    AlertRule,
    BackupProfile,
    MetricSnapshot,
    ScheduledTask,
    ServerCredential,
    WebhookConfig,
)
from rbac import permission_required

logger = logging.getLogger('emarecloud.monitoring')

monitoring_bp = Blueprint('monitoring', __name__)


# ==================== ALERT RULES ====================

@monitoring_bp.route('/api/alerts/rules', methods=['GET'])
@login_required
@permission_required('monitoring.view')
def list_alert_rules():
    """Tüm alert kurallarını listeler."""
    rules = AlertRule.query.order_by(AlertRule.created_at.desc()).all()
    return jsonify({'success': True, 'rules': [r.to_dict() for r in rules]})


@monitoring_bp.route('/api/alerts/rules', methods=['POST'])
@login_required
@permission_required('monitoring.manage')
def create_alert_rule():
    """Yeni alert kuralı oluşturur."""
    data = request.get_json(silent=True) or {}

    name = (data.get('name') or '').strip()
    metric = (data.get('metric') or '').strip()
    threshold = data.get('threshold')

    if not name:
        return jsonify({'success': False, 'message': 'Kural adı gerekli'}), 400
    if metric not in ('cpu', 'memory', 'disk', 'load_1m', 'load_5m', 'load_15m'):
        return jsonify({'success': False, 'message': 'Geçersiz metrik türü'}), 400
    if threshold is None:
        return jsonify({'success': False, 'message': 'Eşik değeri gerekli'}), 400

    try:
        threshold = float(threshold)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'message': 'Eşik değeri sayısal olmalı'}), 400

    rule = AlertRule(
        name=name,
        server_id=data.get('server_id') or None,
        metric=metric,
        condition=data.get('condition', '>'),
        threshold=threshold,
        severity=data.get('severity', 'warning'),
        webhook_id=data.get('webhook_id') or None,
        cooldown_minutes=int(data.get('cooldown_minutes', 15)),
        is_active=data.get('is_active', True),
        created_by=current_user.id,
    )
    db.session.add(rule)
    db.session.commit()

    logger.info("Alert kuralı oluşturuldu: %s (id=%s)", name, rule.id)
    return jsonify({'success': True, 'rule': rule.to_dict()}), 201


@monitoring_bp.route('/api/alerts/rules/<int:rule_id>', methods=['PUT'])
@login_required
@permission_required('monitoring.manage')
def update_alert_rule(rule_id):
    """Alert kuralını günceller."""
    rule = db.session.get(AlertRule, rule_id)
    if not rule:
        return jsonify({'success': False, 'message': 'Kural bulunamadı'}), 404

    data = request.get_json(silent=True) or {}

    if 'name' in data:
        rule.name = data['name']
    if 'metric' in data:
        rule.metric = data['metric']
    if 'condition' in data:
        rule.condition = data['condition']
    if 'threshold' in data:
        rule.threshold = float(data['threshold'])
    if 'severity' in data:
        rule.severity = data['severity']
    if 'webhook_id' in data:
        rule.webhook_id = data['webhook_id'] or None
    if 'cooldown_minutes' in data:
        rule.cooldown_minutes = int(data['cooldown_minutes'])
    if 'is_active' in data:
        rule.is_active = bool(data['is_active'])
    if 'server_id' in data:
        rule.server_id = data['server_id'] or None

    db.session.commit()
    return jsonify({'success': True, 'rule': rule.to_dict()})


@monitoring_bp.route('/api/alerts/rules/<int:rule_id>', methods=['DELETE'])
@login_required
@permission_required('monitoring.manage')
def delete_alert_rule(rule_id):
    """Alert kuralını siler."""
    rule = db.session.get(AlertRule, rule_id)
    if not rule:
        return jsonify({'success': False, 'message': 'Kural bulunamadı'}), 404

    db.session.delete(rule)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Kural silindi'})


# ==================== ALERT HISTORY ====================

@monitoring_bp.route('/api/alerts/history', methods=['GET'])
@login_required
@permission_required('monitoring.view')
def alert_history():
    """Alert geçmişini döndürür."""
    limit = min(int(request.args.get('limit', 50)), 200)
    server_id = request.args.get('server_id')
    severity = request.args.get('severity')

    q = AlertHistory.query.order_by(AlertHistory.created_at.desc())
    if server_id:
        q = q.filter_by(server_id=server_id)
    if severity:
        q = q.filter_by(severity=severity)

    alerts = q.limit(limit).all()
    return jsonify({'success': True, 'alerts': [a.to_dict() for a in alerts]})


@monitoring_bp.route('/api/alerts/history/<int:alert_id>/acknowledge', methods=['POST'])
@login_required
@permission_required('monitoring.manage')
def acknowledge_alert(alert_id):
    """Alarmı onaylar (acknowledged)."""
    alert = db.session.get(AlertHistory, alert_id)
    if not alert:
        return jsonify({'success': False, 'message': 'Alarm bulunamadı'}), 404

    alert.acknowledged = True
    alert.acknowledged_by = current_user.id
    db.session.commit()
    return jsonify({'success': True, 'message': 'Alarm onaylandı'})


@monitoring_bp.route('/api/alerts/stats', methods=['GET'])
@login_required
@permission_required('monitoring.view')
def alert_stats():
    """Alert istatistiklerini döndürür."""
    total = AlertHistory.query.count()
    unacknowledged = AlertHistory.query.filter_by(acknowledged=False).count()
    last_24h = AlertHistory.query.filter(
        AlertHistory.created_at >= datetime.utcnow() - timedelta(hours=24)
    ).count()
    critical = AlertHistory.query.filter_by(severity='critical', acknowledged=False).count()

    return jsonify({
        'success': True,
        'stats': {
            'total': total,
            'unacknowledged': unacknowledged,
            'last_24h': last_24h,
            'critical': critical,
        }
    })


# ==================== WEBHOOKS ====================

@monitoring_bp.route('/api/webhooks', methods=['GET'])
@login_required
@permission_required('monitoring.view')
def list_webhooks():
    """Webhook konfigürasyonlarını listeler."""
    webhooks = WebhookConfig.query.order_by(WebhookConfig.created_at.desc()).all()
    return jsonify({'success': True, 'webhooks': [w.to_dict() for w in webhooks]})


@monitoring_bp.route('/api/webhooks', methods=['POST'])
@login_required
@permission_required('monitoring.manage')
def create_webhook():
    """Yeni webhook konfigürasyonu oluşturur."""
    data = request.get_json(silent=True) or {}

    name = (data.get('name') or '').strip()
    wtype = (data.get('webhook_type') or '').strip()

    if not name:
        return jsonify({'success': False, 'message': 'Webhook adı gerekli'}), 400
    if wtype not in ('slack', 'discord', 'email', 'custom'):
        return jsonify({'success': False, 'message': 'Geçersiz webhook tipi'}), 400

    webhook = WebhookConfig(
        name=name,
        webhook_type=wtype,
        url=data.get('url'),
        smtp_host=data.get('smtp_host'),
        smtp_port=data.get('smtp_port'),
        smtp_user=data.get('smtp_user'),
        smtp_from=data.get('smtp_from'),
        smtp_to=data.get('smtp_to'),
        is_active=data.get('is_active', True),
        created_by=current_user.id,
    )

    # SMTP şifresini şifrele
    smtp_pass = data.get('smtp_password')
    if smtp_pass and wtype == 'email':
        try:
            from crypto import encrypt_password
            webhook.smtp_password_enc, webhook.smtp_password_iv = encrypt_password(smtp_pass)
        except Exception:
            pass

    db.session.add(webhook)
    db.session.commit()

    return jsonify({'success': True, 'webhook': webhook.to_dict()}), 201


@monitoring_bp.route('/api/webhooks/<int:webhook_id>', methods=['PUT'])
@login_required
@permission_required('monitoring.manage')
def update_webhook(webhook_id):
    """Webhook konfigürasyonunu günceller."""
    webhook = db.session.get(WebhookConfig, webhook_id)
    if not webhook:
        return jsonify({'success': False, 'message': 'Webhook bulunamadı'}), 404

    data = request.get_json(silent=True) or {}
    for field in ('name', 'url', 'smtp_host', 'smtp_user', 'smtp_from', 'smtp_to'):
        if field in data:
            setattr(webhook, field, data[field])
    if 'smtp_port' in data:
        webhook.smtp_port = data['smtp_port']
    if 'is_active' in data:
        webhook.is_active = bool(data['is_active'])
    if 'smtp_password' in data and data['smtp_password']:
        try:
            from crypto import encrypt_password
            webhook.smtp_password_enc, webhook.smtp_password_iv = encrypt_password(data['smtp_password'])
        except Exception:
            pass

    db.session.commit()
    return jsonify({'success': True, 'webhook': webhook.to_dict()})


@monitoring_bp.route('/api/webhooks/<int:webhook_id>', methods=['DELETE'])
@login_required
@permission_required('monitoring.manage')
def delete_webhook(webhook_id):
    """Webhook konfigürasyonunu siler."""
    webhook = db.session.get(WebhookConfig, webhook_id)
    if not webhook:
        return jsonify({'success': False, 'message': 'Webhook bulunamadı'}), 404

    db.session.delete(webhook)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Webhook silindi'})


@monitoring_bp.route('/api/webhooks/<int:webhook_id>/test', methods=['POST'])
@login_required
@permission_required('monitoring.manage')
def test_webhook(webhook_id):
    """Webhook'u test mesajı ile test eder."""
    webhook = db.session.get(WebhookConfig, webhook_id)
    if not webhook:
        return jsonify({'success': False, 'message': 'Webhook bulunamadı'}), 404

    from alert_manager import dispatch_notification
    msg = "🧪 Bu bir test bildirimidir. EmareCloud webhook entegrasyonunuz başarıyla çalışıyor!"
    ok = dispatch_notification(webhook, msg, 'info')

    return jsonify({
        'success': ok,
        'message': 'Test bildirimi gönderildi' if ok else 'Bildirim gönderilemedi',
    })


# ==================== SCHEDULED TASKS ====================

@monitoring_bp.route('/api/tasks', methods=['GET'])
@login_required
@permission_required('monitoring.view')
def list_tasks():
    """Zamanlanmış görevleri listeler."""
    tasks = ScheduledTask.query.order_by(ScheduledTask.created_at.desc()).all()
    return jsonify({'success': True, 'tasks': [t.to_dict() for t in tasks]})


@monitoring_bp.route('/api/tasks', methods=['POST'])
@login_required
@permission_required('monitoring.manage')
def create_task():
    """Yeni zamanlanmış görev oluşturur."""
    data = request.get_json(silent=True) or {}

    name = (data.get('name') or '').strip()
    server_id = (data.get('server_id') or '').strip()
    command = (data.get('command') or '').strip()
    schedule = (data.get('schedule') or '').strip()

    if not name:
        return jsonify({'success': False, 'message': 'Görev adı gerekli'}), 400
    if not server_id:
        return jsonify({'success': False, 'message': 'Sunucu seçimi gerekli'}), 400
    if not command:
        return jsonify({'success': False, 'message': 'Komut gerekli'}), 400
    if not schedule:
        return jsonify({'success': False, 'message': 'Zamanlama gerekli'}), 400

    # Komut güvenlik kontrolü
    from command_security import is_command_allowed
    allowed, reason = is_command_allowed(command, current_user.role)
    if not allowed:
        return jsonify({'success': False, 'message': f'Komut reddedildi: {reason}'}), 403

    task = ScheduledTask(
        name=name,
        server_id=server_id,
        command=command,
        schedule=schedule,
        is_active=data.get('is_active', True),
        created_by=current_user.id,
    )
    db.session.add(task)
    db.session.commit()

    return jsonify({'success': True, 'task': task.to_dict()}), 201


@monitoring_bp.route('/api/tasks/<int:task_id>', methods=['PUT'])
@login_required
@permission_required('monitoring.manage')
def update_task(task_id):
    """Zamanlanmış görevi günceller."""
    task = db.session.get(ScheduledTask, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Görev bulunamadı'}), 404

    data = request.get_json(silent=True) or {}
    if 'name' in data:
        task.name = data['name']
    if 'command' in data:
        from command_security import is_command_allowed
        allowed, reason = is_command_allowed(data['command'], current_user.role)
        if not allowed:
            return jsonify({'success': False, 'message': f'Komut reddedildi: {reason}'}), 403
        task.command = data['command']
    if 'schedule' in data:
        task.schedule = data['schedule']
    if 'is_active' in data:
        task.is_active = bool(data['is_active'])

    db.session.commit()
    return jsonify({'success': True, 'task': task.to_dict()})


@monitoring_bp.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@login_required
@permission_required('monitoring.manage')
def delete_task(task_id):
    """Zamanlanmış görevi siler."""
    task = db.session.get(ScheduledTask, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Görev bulunamadı'}), 404

    db.session.delete(task)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Görev silindi'})


@monitoring_bp.route('/api/tasks/<int:task_id>/run', methods=['POST'])
@login_required
@permission_required('monitoring.manage')
def run_task_now(task_id):
    """Görevi hemen çalıştırır."""
    task = db.session.get(ScheduledTask, task_id)
    if not task:
        return jsonify({'success': False, 'message': 'Görev bulunamadı'}), 404

    from core.helpers import ssh_mgr
    if not ssh_mgr.is_connected(task.server_id):
        return jsonify({'success': False, 'message': 'Sunucu bağlı değil'}), 400

    try:
        ok, out, err = ssh_mgr.execute_command(task.server_id, task.command)
        task.last_status = 'success' if ok else 'failed'
        task.last_output = (out or err or '')[:2000]
        task.last_run = datetime.utcnow()
        db.session.commit()

        return jsonify({
            'success': ok,
            'status': task.last_status,
            'output': task.last_output,
        })
    except Exception as e:
        task.last_status = 'failed'
        task.last_output = str(e)[:500]
        task.last_run = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== BACKUP PROFILES ====================

@monitoring_bp.route('/api/backups', methods=['GET'])
@login_required
@permission_required('monitoring.view')
def list_backups():
    """Yedekleme profillerini listeler."""
    profiles = BackupProfile.query.order_by(BackupProfile.created_at.desc()).all()
    return jsonify({'success': True, 'backups': [p.to_dict() for p in profiles]})


@monitoring_bp.route('/api/backups', methods=['POST'])
@login_required
@permission_required('monitoring.manage')
def create_backup():
    """Yeni yedekleme profili oluşturur."""
    data = request.get_json(silent=True) or {}

    name = (data.get('name') or '').strip()
    server_id = (data.get('server_id') or '').strip()
    source_path = (data.get('source_path') or '').strip()
    dest_path = (data.get('dest_path') or '').strip()

    if not name:
        return jsonify({'success': False, 'message': 'Profil adı gerekli'}), 400
    if not server_id:
        return jsonify({'success': False, 'message': 'Sunucu seçimi gerekli'}), 400
    if not source_path:
        return jsonify({'success': False, 'message': 'Kaynak dizin gerekli'}), 400
    if not dest_path:
        return jsonify({'success': False, 'message': 'Hedef dizin gerekli'}), 400

    profile = BackupProfile(
        name=name,
        server_id=server_id,
        source_path=source_path,
        dest_path=dest_path,
        schedule=data.get('schedule', '0 2 * * *'),
        retention_days=int(data.get('retention_days', 30)),
        compression=data.get('compression', 'gzip'),
        is_active=data.get('is_active', True),
        created_by=current_user.id,
    )
    db.session.add(profile)
    db.session.commit()

    return jsonify({'success': True, 'backup': profile.to_dict()}), 201


@monitoring_bp.route('/api/backups/<int:profile_id>', methods=['PUT'])
@login_required
@permission_required('monitoring.manage')
def update_backup(profile_id):
    """Yedekleme profilini günceller."""
    profile = db.session.get(BackupProfile, profile_id)
    if not profile:
        return jsonify({'success': False, 'message': 'Profil bulunamadı'}), 404

    data = request.get_json(silent=True) or {}
    for field in ('name', 'source_path', 'dest_path', 'schedule', 'compression'):
        if field in data:
            setattr(profile, field, data[field])
    if 'retention_days' in data:
        profile.retention_days = int(data['retention_days'])
    if 'is_active' in data:
        profile.is_active = bool(data['is_active'])

    db.session.commit()
    return jsonify({'success': True, 'backup': profile.to_dict()})


@monitoring_bp.route('/api/backups/<int:profile_id>', methods=['DELETE'])
@login_required
@permission_required('monitoring.manage')
def delete_backup(profile_id):
    """Yedekleme profilini siler."""
    profile = db.session.get(BackupProfile, profile_id)
    if not profile:
        return jsonify({'success': False, 'message': 'Profil bulunamadı'}), 404

    db.session.delete(profile)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Profil silindi'})


@monitoring_bp.route('/api/backups/<int:profile_id>/run', methods=['POST'])
@login_required
@permission_required('monitoring.manage')
def run_backup_now(profile_id):
    """Yedeklemeyi hemen çalıştırır."""
    profile = db.session.get(BackupProfile, profile_id)
    if not profile:
        return jsonify({'success': False, 'message': 'Profil bulunamadı'}), 404

    from backup_manager import run_backup
    ok = run_backup(db.get_app(), profile)

    return jsonify({
        'success': ok,
        'message': 'Yedekleme tamamlandı' if ok else 'Yedekleme başarısız',
        'backup': profile.to_dict(),
    })


# ==================== METRIC HISTORY ====================

@monitoring_bp.route('/api/metrics/history/<server_id>', methods=['GET'])
@login_required
@permission_required('monitoring.view')
def metric_history(server_id):
    """Sunucu metrik geçmişini döndürür (trend analizi için)."""
    hours = min(int(request.args.get('hours', 24)), 720)  # max 30 gün
    since = datetime.utcnow() - timedelta(hours=hours)

    snapshots = MetricSnapshot.query.filter(
        MetricSnapshot.server_id == server_id,
        MetricSnapshot.created_at >= since,
    ).order_by(MetricSnapshot.created_at.asc()).all()

    return jsonify({
        'success': True,
        'server_id': server_id,
        'hours': hours,
        'count': len(snapshots),
        'snapshots': [s.to_dict() for s in snapshots],
    })


@monitoring_bp.route('/api/metrics/summary', methods=['GET'])
@login_required
@permission_required('monitoring.view')
def metrics_summary():
    """Tüm sunucular için son metrik özetini döndürür."""
    servers = ServerCredential.query.all()
    summary = []

    for srv in servers:
        last = MetricSnapshot.query.filter_by(
            server_id=srv.id
        ).order_by(MetricSnapshot.created_at.desc()).first()

        summary.append({
            'server_id': srv.id,
            'server_name': srv.name,
            'last_snapshot': last.to_dict() if last else None,
        })

    return jsonify({'success': True, 'summary': summary})


# ==================== MONITORING OVERVIEW ====================

@monitoring_bp.route('/api/monitoring/overview', methods=['GET'])
@login_required
@permission_required('monitoring.view')
def monitoring_overview():
    """Monitoring genel bakış — dashboard için tek endpoint."""
    # Alert istatistikleri
    alert_total = AlertHistory.query.count()
    alert_unack = AlertHistory.query.filter_by(acknowledged=False).count()
    alert_24h = AlertHistory.query.filter(
        AlertHistory.created_at >= datetime.utcnow() - timedelta(hours=24)
    ).count()
    alert_critical = AlertHistory.query.filter_by(severity='critical', acknowledged=False).count()

    # Son alarmlar
    recent_alerts = AlertHistory.query.order_by(
        AlertHistory.created_at.desc()
    ).limit(10).all()

    # Aktif kurallar
    active_rules = AlertRule.query.filter_by(is_active=True).count()

    # Backup durumu
    total_backups = BackupProfile.query.count()
    active_backups = BackupProfile.query.filter_by(is_active=True).count()
    failed_backups = BackupProfile.query.filter_by(last_status='failed').count()

    # Scheduled tasks
    total_tasks = ScheduledTask.query.count()
    active_tasks = ScheduledTask.query.filter_by(is_active=True).count()

    # Webhook sayısı
    total_webhooks = WebhookConfig.query.filter_by(is_active=True).count()

    return jsonify({
        'success': True,
        'overview': {
            'alerts': {
                'total': alert_total,
                'unacknowledged': alert_unack,
                'last_24h': alert_24h,
                'critical': alert_critical,
                'active_rules': active_rules,
                'recent': [a.to_dict() for a in recent_alerts],
            },
            'backups': {
                'total': total_backups,
                'active': active_backups,
                'failed': failed_backups,
            },
            'tasks': {
                'total': total_tasks,
                'active': active_tasks,
            },
            'webhooks': total_webhooks,
        }
    })
