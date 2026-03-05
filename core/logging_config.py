"""
EmareCloud — Structured Logging Yapılandırması
JSON formatlı, seviye bazlı loglama.
"""

import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime

from flask import request
from flask_login import current_user


class JSONFormatter(logging.Formatter):
    """Yapılandırılmış JSON log formatı."""

    def format(self, record):
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        if record.exc_info and record.exc_info[0]:
            log_entry['exception'] = self.formatException(record.exc_info)
        # Ekstra alanlar
        for key in ('request_id', 'user', 'ip', 'method', 'path', 'status_code'):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val
        return json.dumps(log_entry, ensure_ascii=False)


class HumanReadableFormatter(logging.Formatter):
    """Geliştirme ortamı için okunabilir log formatı."""

    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'

    def format(self, record):
        color = self.COLORS.get(record.levelname, '')
        timestamp = datetime.utcnow().strftime('%H:%M:%S')
        msg = record.getMessage()
        return f"{color}[{timestamp}] {record.levelname:8s}{self.RESET} {record.name}: {msg}"


def setup_logging(app):
    """Uygulama loglama yapılandırmasını kurar."""
    root_logger = logging.getLogger('emarecloud')
    root_logger.setLevel(logging.DEBUG if app.debug else logging.INFO)

    # Mevcut handler'ları temizle
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if app.debug else logging.INFO)

    if app.debug:
        console_handler.setFormatter(HumanReadableFormatter())
    else:
        console_handler.setFormatter(JSONFormatter())

    root_logger.addHandler(console_handler)

    # Dosya handler (production)
    if not app.debug:
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, 'emarecloud.log'),
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8',
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)

    # Flask'ın kendi logger'ını da yapılandır
    app.logger.handlers = root_logger.handlers
    app.logger.setLevel(root_logger.level)

    # Werkzeug log seviyesini ayarla (aşırı verbose olmasın)
    logging.getLogger('werkzeug').setLevel(logging.WARNING if not app.debug else logging.INFO)

    # Request loglama
    @app.after_request
    def log_request(response):
        logger = logging.getLogger('emarecloud.access')
        logger.info(
            '%s %s → %s',
            request.method, request.path, response.status_code,
            extra={
                'method': request.method,
                'path': request.path,
                'status_code': response.status_code,
                'ip': request.remote_addr,
                'user': getattr(current_user, 'username', None) if hasattr(current_user, 'username') else None,
            }
        )
        return response

    return root_logger
