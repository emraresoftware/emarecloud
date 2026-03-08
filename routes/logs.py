"""
EmareCloud — Log Intelligence API
==================================
Gerçek log dosyalarını ve audit kayıtlarını okuyan API endpoint'leri.
Diğer dervişler bu blueprint'i import edip kendi projelerine ekleyebilir.

Kullanım (herhangi bir Flask projesi):
    from routes.logs import logs_bp
    app.register_blueprint(logs_bp)

Gerekli:
    - core/logging_config.py  (setup_logging çağrılmış olmalı)
    - models.py → AuditLog modeli
    - audit.py → log_action fonksiyonu
"""

import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user  # type: ignore

logs_bp = Blueprint('logs', __name__)

# ── Yardımcılar ──────────────────────────────────────────

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'emarecloud.log')


def _parse_json_log_line(line: str) -> Optional[dict]:
    """JSON formatlı bir log satırını parse et."""
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        # JSON değilse plain text olarak dön
        return {
            'timestamp': None,
            'level': 'INFO',
            'message': line,
            'module': None,
            'function': None,
            'line': None,
        }


def _read_log_lines(max_lines: int = 500, level_filter: Optional[str] = None,
                     search: Optional[str] = None, since_hours: int = 24) -> list:
    """
    Log dosyasından son N satırı oku, filtrele ve döndür.
    Ters kronolojik sırada (en yeni önce).
    """
    if not os.path.exists(LOG_FILE):
        return []

    cutoff = datetime.utcnow() - timedelta(hours=since_hours)
    results = []

    # Dosyanın sonundan oku (verimli — büyük dosyalar için)
    try:
        with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
            # Son 10000 satırı oku (performa dikkat)
            lines = f.readlines()[-10000:]
    except Exception:
        return []

    for raw_line in reversed(lines):
        entry = _parse_json_log_line(raw_line)
        if not entry:
            continue

        # Zaman filtresi
        ts = entry.get('timestamp')
        if ts:
            try:
                log_time = datetime.fromisoformat(ts.replace('Z', '+00:00').replace('+00:00', ''))
                if log_time < cutoff:
                    continue
            except (ValueError, TypeError):
                pass

        # Seviye filtresi
        if level_filter:
            entry_level = (entry.get('level') or '').upper()
            if level_filter.upper() == 'ERROR' and entry_level not in ('ERROR', 'CRITICAL'):
                continue
            elif level_filter.upper() == 'WARNING' and entry_level not in ('WARNING', 'WARN'):
                continue
            elif level_filter.upper() == 'INFO' and entry_level != 'INFO':
                continue

        # Arama filtresi
        if search:
            msg = (entry.get('message') or '').lower()
            mod = (entry.get('module') or '').lower()
            if search.lower() not in msg and search.lower() not in mod:
                continue

        results.append(entry)
        if len(results) >= max_lines:
            break

    return results


def _compute_log_stats(entries: list) -> dict:
    """Log girişlerinden istatistik hesapla."""
    level_counts = Counter()
    module_counts = Counter()
    hour_counts = Counter()
    error_patterns = Counter()

    for entry in entries:
        level = (entry.get('level') or 'UNKNOWN').upper()
        level_counts[level] += 1

        module = entry.get('module') or 'unknown'
        module_counts[module] += 1

        ts = entry.get('timestamp')
        if ts:
            try:
                log_time = datetime.fromisoformat(ts.replace('Z', '+00:00').replace('+00:00', ''))
                hour_counts[log_time.hour] += 1
            except (ValueError, TypeError):
                pass

        # Error pattern analizi
        if level in ('ERROR', 'CRITICAL'):
            msg = entry.get('message', '')
            # Basit pattern çıkarımı
            pattern = re.sub(r'\d+', 'N', msg)[:80]
            error_patterns[pattern] += 1

    # Sağlık skoru hesapla
    total = len(entries) or 1
    error_count = level_counts.get('ERROR', 0) + level_counts.get('CRITICAL', 0)
    warning_count = level_counts.get('WARNING', 0) + level_counts.get('WARN', 0)
    health_score = max(0, 100 - (error_count * 5) - (warning_count * 1))

    return {
        'toplam': len(entries),
        'seviyeler': dict(level_counts),
        'kritik': level_counts.get('CRITICAL', 0),
        'hata': level_counts.get('ERROR', 0),
        'uyari': warning_count,
        'bilgi': level_counts.get('INFO', 0),
        'debug': level_counts.get('DEBUG', 0),
        'saglik_skoru': min(health_score, 100),
        'modüller': dict(module_counts.most_common(10)),
        'saat_dagilimi': dict(sorted(hour_counts.items())),
        'hata_paternleri': dict(error_patterns.most_common(10)),
    }


# ── API Endpoint'leri ────────────────────────────────────

@logs_bp.route('/api/logs', methods=['GET'])
@login_required
def get_logs():
    """
    Log dosyasından kayıtları getir.

    Query params:
        limit   — max satır (varsayılan 200, max 1000)
        level   — ERROR / WARNING / INFO / DEBUG
        search  — metin arama
        hours   — son kaç saatlik (varsayılan 24)
    """
    limit = min(int(request.args.get('limit', 200)), 1000)
    level = request.args.get('level')
    search = request.args.get('search')
    hours = int(request.args.get('hours', 24))

    entries = _read_log_lines(max_lines=limit, level_filter=level,
                              search=search, since_hours=hours)

    return jsonify({
        'ok': True,
        'count': len(entries),
        'logs': entries,
    })


@logs_bp.route('/api/logs/stats', methods=['GET'])
@login_required
def get_log_stats():
    """
    Son 24 saatlik log istatistikleri + sağlık skoru.

    Query params:
        hours — kaç saatlik istatistik (varsayılan 24)
    """
    hours = int(request.args.get('hours', 24))
    entries = _read_log_lines(max_lines=5000, since_hours=hours)
    stats = _compute_log_stats(entries)
    return jsonify({'ok': True, **stats})


@logs_bp.route('/api/logs/live', methods=['GET'])
@login_required
def get_live_logs():
    """
    Son N log satırını canlı akış için getir.
    Frontend bu endpoint'i polling ile çağırır.

    Query params:
        limit — max satır (varsayılan 30, max 100)
        after — bu timestamp'ten sonrakiler (ISO format)
    """
    limit = min(int(request.args.get('limit', 30)), 100)
    after = request.args.get('after')

    entries = _read_log_lines(max_lines=limit, since_hours=1)

    if after:
        try:
            after_dt = datetime.fromisoformat(after.replace('Z', '+00:00').replace('+00:00', ''))
            entries = [
                e for e in entries
                if e.get('timestamp') and
                datetime.fromisoformat(
                    e['timestamp'].replace('Z', '+00:00').replace('+00:00', '')
                ) > after_dt
            ]
        except (ValueError, TypeError):
            pass

    return jsonify({
        'ok': True,
        'count': len(entries),
        'logs': entries,
    })


# ── Audit Log API ────────────────────────────────────────

@logs_bp.route('/api/audit-logs', methods=['GET'])
@login_required
def get_audit_logs():
    """
    Veritabanından audit logları getir (multi-tenant).

    Query params:
        limit    — max kayıt (varsayılan 100, max 500)
        offset   — sayfalama
        action   — aksiyon filtresi (ör: server.connect)
        success  — true/false
        search   — kullanıcı adı veya detayda arama
        hours    — son kaç saat (varsayılan 168 = 7 gün)
    """
    from extensions import db
    from models import AuditLog

    limit = min(int(request.args.get('limit', 100)), 500)
    offset = int(request.args.get('offset', 0))
    action_filter = request.args.get('action')
    success_filter = request.args.get('success')
    search = request.args.get('search')
    hours = int(request.args.get('hours', 168))

    q = AuditLog.query

    # Multi-tenant: sadece kendi org'unu gör (super admin hariç)
    from core.helpers import is_global_access
    if not is_global_access():
        q = q.filter(AuditLog.org_id == current_user.org_id)

    # Zaman filtresi
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    q = q.filter(AuditLog.created_at >= cutoff)

    # Aksiyon filtresi
    if action_filter:
        q = q.filter(AuditLog.action.ilike(f'%{action_filter}%'))

    # Başarı filtresi
    if success_filter is not None:
        q = q.filter(AuditLog.success == (success_filter.lower() == 'true'))

    # Arama
    if search:
        q = q.filter(
            db.or_(
                AuditLog.username.ilike(f'%{search}%'),
                AuditLog.details.ilike(f'%{search}%'),
                AuditLog.action.ilike(f'%{search}%'),
            )
        )

    total = q.count()
    entries = q.order_by(AuditLog.created_at.desc()) \
               .offset(offset).limit(limit).all()

    return jsonify({
        'ok': True,
        'total': total,
        'count': len(entries),
        'offset': offset,
        'audit_logs': [e.to_dict() for e in entries],
    })


@logs_bp.route('/api/audit-logs/stats', methods=['GET'])
@login_required
def get_audit_stats():
    """
    Audit log istatistikleri: en çok yapılan aksiyonlar, aktif kullanıcılar, başarısız işlemler.
    """
    from extensions import db
    from models import AuditLog
    from core.helpers import is_global_access

    hours = int(request.args.get('hours', 168))
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    q = AuditLog.query.filter(AuditLog.created_at >= cutoff)
    if not is_global_access():
        q = q.filter(AuditLog.org_id == current_user.org_id)

    entries = q.all()

    action_counts = Counter()
    user_counts = Counter()
    failed_actions = Counter()
    daily_counts = Counter()

    for e in entries:
        action_counts[e.action] += 1
        user_counts[e.username or 'anonim'] += 1
        if not e.success:
            failed_actions[e.action] += 1
        if e.created_at:
            day_key = e.created_at.strftime('%Y-%m-%d')
            daily_counts[day_key] += 1

    return jsonify({
        'ok': True,
        'toplam': len(entries),
        'basarisiz': sum(1 for e in entries if not e.success),
        'aksiyonlar': dict(action_counts.most_common(15)),
        'kullanicilar': dict(user_counts.most_common(10)),
        'basarisiz_aksiyonlar': dict(failed_actions.most_common(10)),
        'gunluk_dagilim': dict(sorted(daily_counts.items())),
    })


@logs_bp.route('/api/audit-logs/actions', methods=['GET'])
@login_required
def get_audit_actions():
    """Benzersiz aksiyon isimlerini döndür (filtre için)."""
    from models import AuditLog
    from core.helpers import is_global_access

    q = AuditLog.query
    if not is_global_access():
        q = q.filter(AuditLog.org_id == current_user.org_id)

    actions = q.with_entities(AuditLog.action).distinct().all()
    return jsonify({
        'ok': True,
        'actions': sorted(set(a[0] for a in actions if a[0])),
    })
