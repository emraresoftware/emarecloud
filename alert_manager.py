"""
EmareCloud — Alert & Webhook Manager
Eşik değer kontrolü, alarm tetikleme ve bildirim gönderimi.
"""

import json
import logging
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.request import Request, urlopen

logger = logging.getLogger('emarecloud.alerts')


# ==================== WEBHOOK DİSPATCHER ====================

def send_slack(url: str, message: str, severity: str = 'warning') -> bool:
    """Slack webhook'una bildirim gönderir."""
    color_map = {'info': '#36a64f', 'warning': '#ff9900', 'critical': '#ff0000'}
    payload = {
        'attachments': [{
            'color': color_map.get(severity, '#ff9900'),
            'title': f'🔔 EmareCloud Alert [{severity.upper()}]',
            'text': message,
            'ts': int(datetime.utcnow().timestamp()),
        }]
    }
    return _post_json(url, payload)


def send_discord(url: str, message: str, severity: str = 'warning') -> bool:
    """Discord webhook'una bildirim gönderir."""
    color_map = {'info': 0x36A64F, 'warning': 0xFF9900, 'critical': 0xFF0000}
    payload = {
        'embeds': [{
            'title': f'🔔 EmareCloud Alert [{severity.upper()}]',
            'description': message,
            'color': color_map.get(severity, 0xFF9900),
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }]
    }
    return _post_json(url, payload)


def send_email(smtp_host: str, smtp_port: int, smtp_user: str, smtp_pass: str,
               from_addr: str, to_addrs: str, message: str, severity: str = 'warning') -> bool:
    """SMTP üzerinden e-posta bildirimi gönderir."""
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f'[EmareCloud] {severity.upper()} Alert'
        msg['From'] = from_addr
        recipients = [a.strip() for a in to_addrs.split(',') if a.strip()]
        msg['To'] = ', '.join(recipients)

        html = f"""
        <div style="font-family:sans-serif;max-width:600px;margin:0 auto;">
            <div style="background:{'#ff0000' if severity == 'critical' else '#ff9900'};
                        color:#fff;padding:15px 20px;border-radius:8px 8px 0 0;">
                <h2 style="margin:0;">🔔 EmareCloud Alert — {severity.upper()}</h2>
            </div>
            <div style="background:#1a1a2e;color:#e0e0e0;padding:20px;border-radius:0 0 8px 8px;">
                <p style="font-size:15px;line-height:1.6;">{message}</p>
                <hr style="border-color:#333;">
                <small style="color:#888;">{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</small>
            </div>
        </div>
        """
        msg.attach(MIMEText(html, 'html'))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.ehlo()
            if smtp_port != 25:
                server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.sendmail(from_addr, recipients, msg.as_string())
        logger.info("E-posta bildirimi gönderildi: %s", recipients)
        return True
    except Exception as e:
        logger.error("E-posta gönderim hatası: %s", e)
        return False


def send_custom_webhook(url: str, message: str, severity: str = 'warning') -> bool:
    """Özel webhook URL'sine JSON POST gönderir."""
    payload = {
        'source': 'EmareCloud',
        'severity': severity,
        'message': message,
        'timestamp': datetime.utcnow().isoformat() + 'Z',
    }
    return _post_json(url, payload)


def _post_json(url: str, payload: dict) -> bool:
    """URL'ye JSON POST isteği gönderir."""
    try:
        data = json.dumps(payload).encode('utf-8')
        req = Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(req, timeout=10) as resp:  # noqa: S310
            return resp.status < 400
    except Exception as e:
        logger.error("Webhook gönderim hatası [%s]: %s", url[:50], e)
        return False


def dispatch_notification(webhook, message: str, severity: str = 'warning') -> bool:
    """WebhookConfig nesnesine göre bildirim gönderir."""
    wtype = webhook.webhook_type
    if wtype == 'slack' and webhook.url:
        return send_slack(webhook.url, message, severity)
    if wtype == 'discord' and webhook.url:
        return send_discord(webhook.url, message, severity)
    if wtype == 'email':
        smtp_pass = ''
        if webhook.smtp_password_enc and webhook.smtp_password_iv:
            try:
                from crypto import decrypt_password
                smtp_pass = decrypt_password(webhook.smtp_password_enc, webhook.smtp_password_iv)
            except Exception:
                pass
        return send_email(
            webhook.smtp_host or 'localhost', webhook.smtp_port or 587,
            webhook.smtp_user or '', smtp_pass,
            webhook.smtp_from or 'noreply@emarecloud.com',
            webhook.smtp_to or '', message, severity,
        )
    if wtype == 'custom' and webhook.url:
        return send_custom_webhook(webhook.url, message, severity)
    logger.warning("Bilinmeyen webhook tipi: %s", wtype)
    return False


# ==================== ALERT MOTORU ====================

METRIC_LABELS = {
    'cpu': 'CPU Kullanımı',
    'memory': 'RAM Kullanımı',
    'disk': 'Disk Kullanımı',
    'load_1m': 'Yük Ortalaması (1dk)',
    'load_5m': 'Yük Ortalaması (5dk)',
}

CONDITION_OPS = {
    '>': lambda v, t: v > t,
    '>=': lambda v, t: v >= t,
    '<': lambda v, t: v < t,
    '<=': lambda v, t: v <= t,
    '==': lambda v, t: abs(v - t) < 0.01,
}


def extract_metric_value(metrics: dict, metric_name: str) -> float | None:
    """Metrik sözlüğünden istenen değeri çıkarır."""
    if not metrics:
        return None

    if metric_name == 'cpu':
        cpu = metrics.get('cpu', {})
        return cpu.get('usage_percent')
    if metric_name == 'memory':
        mem = metrics.get('memory', {})
        return mem.get('percent')
    if metric_name == 'disk':
        disks = metrics.get('disks', [])
        if disks:
            return max(d.get('percent', 0) for d in disks if isinstance(d, dict))
        return None
    if metric_name.startswith('load_'):
        cpu = metrics.get('cpu', {})
        loads = cpu.get('load_average', [])
        idx = {'load_1m': 0, 'load_5m': 1, 'load_15m': 2}.get(metric_name, 0)
        if loads and len(loads) > idx:
            try:
                return float(loads[idx])
            except (ValueError, TypeError):
                return None
    return None


def check_alert_rules(app):
    """Tüm aktif alert kurallarını kontrol eder. Scheduler tarafından çağrılır."""
    from extensions import db
    from models import AlertHistory, AlertRule, ServerCredential

    with app.app_context():
        rules = AlertRule.query.filter_by(is_active=True).all()
        if not rules:
            return

        from core.helpers import monitor, ssh_mgr

        servers = ServerCredential.query.all()
        server_ids = [s.id for s in servers]

        for rule in rules:
            # Cooldown kontrolü
            if rule.last_triggered:
                cooldown_end = rule.last_triggered + timedelta(minutes=rule.cooldown_minutes)
                if datetime.utcnow() < cooldown_end:
                    continue

            target_ids = [rule.server_id] if rule.server_id else server_ids

            for sid in target_ids:
                if not ssh_mgr.is_connected(sid):
                    continue

                try:
                    metrics = monitor.get_all_metrics(sid)
                except Exception:
                    continue

                value = extract_metric_value(metrics, rule.metric)
                if value is None:
                    continue

                op_fn = CONDITION_OPS.get(rule.condition, CONDITION_OPS['>'])
                if not op_fn(value, rule.threshold):
                    continue

                # ALARM TETİKLENDİ
                label = METRIC_LABELS.get(rule.metric, rule.metric)
                srv = db.session.get(ServerCredential, sid)
                srv_name = srv.name if srv else sid

                msg = (
                    f"⚠️ {rule.name}\n"
                    f"Sunucu: {srv_name} ({sid})\n"
                    f"{label}: %{value:.1f} {rule.condition} %{rule.threshold:.0f}\n"
                    f"Önem: {rule.severity.upper()}"
                )

                # Geçmişe kaydet
                history = AlertHistory(
                    rule_id=rule.id,
                    server_id=sid,
                    metric=rule.metric,
                    current_value=value,
                    threshold=rule.threshold,
                    severity=rule.severity,
                    message=msg,
                )

                # Webhook bildirim
                notified = False
                if rule.webhook_id and rule.webhook:
                    try:
                        notified = dispatch_notification(rule.webhook, msg, rule.severity)
                    except Exception as e:
                        logger.error("Webhook dispatch hatası: %s", e)

                history.notified = notified
                rule.last_triggered = datetime.utcnow()

                db.session.add(history)
                db.session.commit()

                logger.warning("Alert tetiklendi: %s — %s=%s (eşik: %s)",
                               rule.name, rule.metric, value, rule.threshold)


def collect_metric_snapshots(app):
    """Bağlı sunuculardan metrik snapshot'ı toplar. Scheduler tarafından çağrılır."""
    from extensions import db
    from models import MetricSnapshot, ServerCredential

    with app.app_context():
        from core.helpers import monitor, ssh_mgr

        servers = ServerCredential.query.all()
        for srv in servers:
            if not ssh_mgr.is_connected(srv.id):
                continue
            try:
                metrics = monitor.get_all_metrics(srv.id)
                if not metrics:
                    continue

                snap = MetricSnapshot(
                    server_id=srv.id,
                    cpu_percent=extract_metric_value(metrics, 'cpu'),
                    memory_percent=extract_metric_value(metrics, 'memory'),
                    disk_percent=extract_metric_value(metrics, 'disk'),
                    load_1m=extract_metric_value(metrics, 'load_1m'),
                    load_5m=extract_metric_value(metrics, 'load_5m'),
                    load_15m=extract_metric_value(metrics, 'load_15m'),
                )

                # Network
                net = metrics.get('network', {})
                if isinstance(net, dict):
                    snap.network_rx = net.get('rx_bytes')
                    snap.network_tx = net.get('tx_bytes')

                db.session.add(snap)
                db.session.commit()
            except Exception as e:
                logger.debug("Metrik snapshot hatası [%s]: %s", srv.id, e)

        # Eski snapshot'ları temizle (30 günden eski)
        cutoff = datetime.utcnow() - timedelta(days=30)
        MetricSnapshot.query.filter(MetricSnapshot.created_at < cutoff).delete()
        db.session.commit()
