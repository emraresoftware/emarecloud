"""
EmareCloud — Backup Manager
SSH üzerinden otomatik yedekleme: tar/gzip, retention, zamanlama.
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger('emarecloud.backup')


def run_backup(app, profile):
    """Tek bir yedekleme profilini çalıştırır."""
    from extensions import db

    with app.app_context():
        from core.helpers import ssh_mgr

        if not ssh_mgr.is_connected(profile.server_id):
            profile.last_status = 'failed'
            profile.last_run = datetime.utcnow()
            profile.last_size = None
            db.session.commit()
            logger.warning("Backup atlandı — sunucu bağlı değil: %s", profile.server_id)
            return False

        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        ext_map = {'gzip': 'tar.gz', 'bzip2': 'tar.bz2', 'none': 'tar'}
        ext = ext_map.get(profile.compression, 'tar.gz')
        filename = f"backup_{profile.server_id}_{timestamp}.{ext}"
        dest_file = f"{profile.dest_path.rstrip('/')}/{filename}"

        # Sıkıştırma bayrağı
        flag_map = {'gzip': '-czf', 'bzip2': '-cjf', 'none': '-cf'}
        tar_flag = flag_map.get(profile.compression, '-czf')

        # Hedef dizini oluştur + tar komutu
        cmd = (
            f"mkdir -p {profile.dest_path} && "
            f"tar {tar_flag} {dest_file} -C / {profile.source_path.lstrip('/')} 2>&1 && "
            f"stat --printf='%s' {dest_file} 2>/dev/null || wc -c < {dest_file}"
        )

        try:
            ok, out, err = ssh_mgr.execute_command(profile.server_id, cmd)

            if ok:
                # Boyutu al
                size_bytes = 0
                for line in (out or '').strip().split('\n'):
                    line = line.strip()
                    if line.isdigit():
                        size_bytes = int(line)

                profile.last_status = 'success'
                profile.last_size = _format_size(size_bytes)
                logger.info("Backup tamamlandı: %s → %s (%s)",
                            profile.source_path, dest_file, profile.last_size)
            else:
                profile.last_status = 'failed'
                profile.last_size = None
                logger.error("Backup hatası [%s]: %s", profile.name, err or out)

        except Exception as e:
            profile.last_status = 'failed'
            profile.last_size = None
            logger.error("Backup exception [%s]: %s", profile.name, e)

        profile.last_run = datetime.utcnow()
        db.session.commit()

        # Retention — eski yedekleri temizle
        if profile.last_status == 'success' and profile.retention_days > 0:
            _cleanup_old_backups(ssh_mgr, profile)

        return profile.last_status == 'success'


def _cleanup_old_backups(ssh_mgr, profile):
    """Retention süresini aşan eski yedekleri siler."""
    try:
        cmd = f"find {profile.dest_path} -name 'backup_{profile.server_id}_*' -mtime +{profile.retention_days} -delete 2>&1"
        ssh_mgr.execute_command(profile.server_id, cmd)
        logger.info("Eski yedekler temizlendi: %s (>%d gün)", profile.dest_path, profile.retention_days)
    except Exception as e:
        logger.debug("Eski yedek temizleme hatası: %s", e)


def check_backup_schedules(app):
    """Zamanı gelmiş yedekleme profillerini kontrol eder ve çalıştırır."""
    from models import BackupProfile

    with app.app_context():
        profiles = BackupProfile.query.filter_by(is_active=True).all()
        now = datetime.utcnow()

        for profile in profiles:
            if not _should_run(profile, now):
                continue
            try:
                run_backup(app, profile)
            except Exception as e:
                logger.error("Backup schedule hatası [%s]: %s", profile.name, e)


def _should_run(profile, now: datetime) -> bool:
    """Cron schedule'a göre profilin çalıştırılması gerekip gerekmediğini kontrol eder."""
    if not profile.schedule:
        return False

    # Son çalışma yoksa hemen çalıştır
    if not profile.last_run:
        return True

    # Basit cron ayrıştırma: "dakika saat gün ay haftanın_günü"
    try:
        parts = profile.schedule.strip().split()
        if len(parts) < 5:
            return False

        minute, hour, day, month, dow = parts[:5]

        # Dakika ve saat eşleşmesi
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

        # Son çalışmadan 60+ saniye geçmiş olmalı (spam önleme)
        return not (profile.last_run and (now - profile.last_run) < timedelta(seconds=60))
    except (ValueError, IndexError):
        return False


def _format_size(size_bytes: int) -> str:
    """Byte değerini okunabilir formata çevirir."""
    if size_bytes <= 0:
        return '0 B'
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"
