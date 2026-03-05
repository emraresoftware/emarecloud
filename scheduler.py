"""
EmareCloud — Background Scheduler
Periyodik görevler: metrik toplama, alert kontrol, yedekleme.
Threading tabanlı — ek bağımlılık gerektirmez.
"""

import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger('emarecloud.scheduler')

_scheduler_thread = None
_stop_event = threading.Event()

# Varsayılan aralıklar (saniye)
METRIC_INTERVAL = 300       # 5 dakika — metrik toplama
ALERT_INTERVAL = 120        # 2 dakika — alert kontrolü
BACKUP_INTERVAL = 60        # 1 dakika — backup schedule kontrolü
TASK_INTERVAL = 60          # 1 dakika — scheduled task kontrolü


def start_scheduler(app):
    """Arka plan scheduler'ını başlatır."""
    global _scheduler_thread

    if _scheduler_thread and _scheduler_thread.is_alive():
        logger.debug("Scheduler zaten çalışıyor")
        return

    _stop_event.clear()
    _scheduler_thread = threading.Thread(
        target=_scheduler_loop,
        args=(app,),
        name='emarecloud-scheduler',
        daemon=True,
    )
    _scheduler_thread.start()
    logger.info("📅 Background scheduler başlatıldı")


def stop_scheduler():
    """Scheduler'ı durdurur."""
    _stop_event.set()
    if _scheduler_thread:
        _scheduler_thread.join(timeout=5)
    logger.info("Scheduler durduruldu")


def _scheduler_loop(app):
    """Ana scheduler döngüsü — her 30 saniyede kontrol yapar."""
    last_metric = 0
    last_alert = 0
    last_backup = 0
    last_task = 0

    # İlk çalışmada 30 saniye bekle (uygulama başlangıcı)
    time.sleep(30)

    while not _stop_event.is_set():
        now = time.time()

        try:
            # Alert kontrolü
            if now - last_alert >= ALERT_INTERVAL:
                _run_alert_check(app)
                last_alert = now

            # Metrik snapshot
            if now - last_metric >= METRIC_INTERVAL:
                _run_metric_collection(app)
                last_metric = now

            # Backup schedule
            if now - last_backup >= BACKUP_INTERVAL:
                _run_backup_check(app)
                last_backup = now

            # Scheduled task kontrolü
            if now - last_task >= TASK_INTERVAL:
                _run_scheduled_tasks(app)
                last_task = now

        except Exception as e:
            logger.error("Scheduler döngü hatası: %s", e)

        # 30 saniye bekle
        _stop_event.wait(30)


def _run_alert_check(app):
    """Alert kurallarını kontrol eder."""
    try:
        from alert_manager import check_alert_rules
        check_alert_rules(app)
    except Exception as e:
        logger.error("Alert kontrol hatası: %s", e)


def _run_metric_collection(app):
    """Metrik snapshot'ları toplar."""
    try:
        from alert_manager import collect_metric_snapshots
        collect_metric_snapshots(app)
    except Exception as e:
        logger.error("Metrik toplama hatası: %s", e)


def _run_backup_check(app):
    """Backup schedule'ları kontrol eder."""
    try:
        from backup_manager import check_backup_schedules
        check_backup_schedules(app)
    except Exception as e:
        logger.error("Backup kontrol hatası: %s", e)


def _run_scheduled_tasks(app):
    """Zamanlanmış görevleri kontrol eder ve çalıştırır."""
    from extensions import db

    try:
        with app.app_context():
            from core.helpers import ssh_mgr
            from models import ScheduledTask

            tasks = ScheduledTask.query.filter_by(is_active=True).all()
            now = datetime.utcnow()

            for task in tasks:
                # Cron eşleşme kontrolü (BackupProfile ile aynı mantık)
                if not _cron_matches(task.schedule, now, task.last_run):
                    continue

                if not ssh_mgr.is_connected(task.server_id):
                    task.last_status = 'failed'
                    task.last_output = 'Sunucu bağlı değil'
                    task.last_run = now
                    db.session.commit()
                    continue

                try:
                    task.last_status = 'running'
                    db.session.commit()

                    ok, out, err = ssh_mgr.execute_command(task.server_id, task.command)
                    task.last_status = 'success' if ok else 'failed'
                    task.last_output = (out or err or '')[:2000]
                    task.last_run = datetime.utcnow()
                    db.session.commit()

                    logger.info("Scheduled task [%s] tamamlandı: %s", task.name, task.last_status)
                except Exception as e:
                    task.last_status = 'failed'
                    task.last_output = str(e)[:500]
                    task.last_run = datetime.utcnow()
                    db.session.commit()
                    logger.error("Scheduled task hatası [%s]: %s", task.name, e)

    except Exception as e:
        logger.error("Scheduled tasks kontrol hatası: %s", e)


def _cron_matches(schedule: str, now: datetime, last_run=None) -> bool:
    """Basit cron format eşleşme: 'dakika saat gün ay haftanın_günü'."""
    if not schedule:
        return False
    try:
        parts = schedule.strip().split()
        if len(parts) < 5:
            return False

        minute, hour, day, month, dow = parts[:5]

        if minute != '*' and int(minute) != now.minute:
            return False
        if hour != '*' and int(hour) != now.hour:
            return False
        if day != '*' and int(day) != now.day:
            return False
        if month != '*' and int(month) != now.month:
            return False
        if dow != '*' and int(dow) != now.weekday():
            return False

        # Son çalışmadan 55+ saniye geçmiş olmalı
        if last_run:
            from datetime import timedelta
            if (now - last_run) < timedelta(seconds=55):
                return False

        return True
    except (ValueError, IndexError):
        return False
