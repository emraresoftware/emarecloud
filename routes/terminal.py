"""
EmareCloud — SocketIO Terminal Route'ları
WebSocket tabanlı web terminal event'leri + canlı izleme (live watch).
"""

import threading
import time

from flask import Blueprint, request
from flask_login import current_user
from flask_socketio import emit

from ai_assistant import ai_analyze, get_quick_prompts
from audit import log_action
from command_security import is_command_allowed
from core.helpers import connect_server_ssh, get_server_by_id, get_server_obj_with_access, ssh_mgr
from rbac import check_permission

terminal_bp = Blueprint('terminal', __name__)

# ═══════════════════════════════════════════════════════════════
#  LIVE WATCH — arka plan izleme thread'leri yönetimi
# ═══════════════════════════════════════════════════════════════
_active_watchers: dict[str, dict] = {}   # sid -> watcher bilgisi
_watcher_lock = threading.Lock()


def _watcher_key(sid: str) -> str:
    """Her socket oturumu için benzersiz anahtar."""
    return sid


def _stop_watcher(sid: str) -> None:
    """Belirli bir oturum için izlemeyi durdurur."""
    with _watcher_lock:
        watcher = _active_watchers.pop(sid, None)
    if watcher:
        watcher['stop_event'].set()


def register_terminal_events(socketio):
    """SocketIO terminal event'lerini kaydeder."""

    # ─── Terminal bağlantısı ───
    @socketio.on('terminal_connect')
    def handle_terminal_connect(data):
        server_id = data.get('server_id')
        if not current_user.is_authenticated:
            emit('terminal_output', {'output': '\r\n❌ Oturum açmalısınız\r\n$ '})
            return
        if not check_permission(current_user.role, 'terminal.access'):
            emit('terminal_output', {'output': '\r\n❌ Terminal erişim yetkiniz yok\r\n$ '})
            return
        if not server_id:
            emit('terminal_output', {'output': '\r\n❌ Geçersiz sunucu\r\n$ '})
            return
        server = get_server_by_id(server_id)
        if not server:
            emit('terminal_output', {'output': '\r\n❌ Sunucu bulunamadı\r\n$ '})
            return
        if not ssh_mgr.is_connected(server_id):
            success, msg = connect_server_ssh(server_id, server)
            if not success:
                emit('terminal_output', {'output': f'\r\n❌ Bağlantı hatası: {msg}\r\n$ '})
                return
        log_action('terminal.connect', target_type='server', target_id=server_id)
        emit('terminal_output', {'output': '\r\n✅ Sunucuya bağlanıldı\r\n$ '})

    # ─── Komut çalıştırma ───
    @socketio.on('terminal_input')
    def handle_terminal_input(data):
        server_id = data.get('server_id')
        command = data.get('command', '').strip()

        if not current_user.is_authenticated:
            emit('terminal_output', {'output': '\r\n❌ Oturum açmalısınız\r\n$ '})
            return

        if not command:
            emit('terminal_output', {'output': '\r\n$ '})
            return

        # Tenant erişim kontrolü
        srv = get_server_obj_with_access(server_id)
        if not srv:
            emit('terminal_output', {'output': '\r\n❌ Sunucu bulunamadı veya erişim yetkiniz yok\r\n$ '})
            return

        if not ssh_mgr.is_connected(server_id):
            emit('terminal_output', {'output': '\r\n❌ Bağlantı yok\r\n$ '})
            return

        # Komut güvenlik kontrolü
        allowed, reason = is_command_allowed(command, current_user.role)
        if not allowed:
            log_action('command.blocked', target_type='server', target_id=server_id,
                      details={'command': command[:200], 'reason': reason, 'via': 'terminal'}, success=False)
            emit('terminal_output', {'output': f'\r\n🚫 {reason}\r\n$ '})
            return

        success, stdout, stderr = ssh_mgr.execute_command(server_id, command)
        output = ''
        if stdout:
            output += stdout
        if stderr:
            output += stderr
        if not output:
            output = '(çıktı yok)'
        output = output.replace('\n', '\r\n')
        log_action('command.terminal', target_type='server', target_id=server_id,
                  details={'command': command[:200]}, success=success)
        emit('terminal_output', {'output': f'\r\n{output}\r\n$ '})

    # ─── Canlı İzleme Başlat ───
    @socketio.on('watch_start')
    def handle_watch_start(data):
        """Belirtilen komutu periyodik olarak çalıştırır ve çıktıyı yayınlar."""
        sid = request.sid
        server_id = data.get('server_id')
        command = data.get('command', '').strip()
        interval = data.get('interval', 2)

        if not current_user.is_authenticated:
            emit('watch_output', {'error': 'Oturum açmalısınız'})
            return
        if not check_permission(current_user.role, 'terminal.access'):
            emit('watch_output', {'error': 'Terminal erişim yetkiniz yok'})
            return
        if not command:
            emit('watch_output', {'error': 'Komut belirtilmedi'})
            return
        if not server_id or not ssh_mgr.is_connected(server_id):
            emit('watch_output', {'error': 'Sunucu bağlı değil'})
            return

        # Güvenlik kontrolü
        allowed, reason = is_command_allowed(command, current_user.role)
        if not allowed:
            emit('watch_output', {'error': f'🚫 {reason}'})
            return

        # Interval sınırla (1-60 saniye)
        try:
            interval = max(1, min(60, int(interval)))
        except (TypeError, ValueError):
            interval = 2

        # Önceki watcher'ı durdur
        _stop_watcher(sid)

        stop_event = threading.Event()
        watcher_info = {
            'server_id': server_id,
            'command': command,
            'interval': interval,
            'stop_event': stop_event,
            'sid': sid,
        }
        with _watcher_lock:
            _active_watchers[sid] = watcher_info

        log_action('watch.start', target_type='server', target_id=server_id,
                  details={'command': command[:200], 'interval': interval})

        def _run_watcher():
            """Background thread: komutu periyodik çalıştırır."""
            tick = 0
            while not stop_event.is_set():
                tick += 1
                if not ssh_mgr.is_connected(server_id):
                    socketio.emit('watch_output', {
                        'error': 'Sunucu bağlantısı kesildi',
                        'stopped': True
                    }, to=sid)
                    break

                success, stdout, stderr = ssh_mgr.execute_command(
                    server_id, command, timeout=max(interval - 1, 5)
                )
                output = stdout or ''
                if stderr:
                    output += stderr
                if not output:
                    output = '(çıktı yok)'

                ts = time.strftime('%H:%M:%S')
                socketio.emit('watch_output', {
                    'output': output,
                    'timestamp': ts,
                    'tick': tick,
                    'command': command,
                    'interval': interval,
                }, to=sid)

                stop_event.wait(interval)

            # Temizlik
            with _watcher_lock:
                _active_watchers.pop(sid, None)

        thread = threading.Thread(target=_run_watcher, daemon=True, name=f'watcher-{sid[:8]}')
        thread.start()

        emit('watch_started', {
            'command': command,
            'interval': interval,
            'message': f'✅ İzleme başlatıldı: her {interval}s → {command}'
        })

    # ─── Canlı İzleme Durdur ───
    @socketio.on('watch_stop')
    def handle_watch_stop(_data=None):
        sid = request.sid
        _stop_watcher(sid)
        emit('watch_stopped', {'message': '⏹ İzleme durduruldu'})

    # ─── Bağlantı koptuğunda watcher'ı da durdur ───
    @socketio.on('disconnect')
    def handle_disconnect():
        sid = request.sid
        _stop_watcher(sid)

    # ─── AI Terminal Asistanı ───
    @socketio.on('ai_assist')
    def handle_ai_assist(data):
        """AI asistana soru sor — terminal bağlamıyla birlikte."""
        if not current_user.is_authenticated:
            emit('ai_response', {'error': 'Oturum açmalısınız'})
            return
        question = (data.get('question') or '').strip()
        context = (data.get('context') or '').strip()
        if not question:
            emit('ai_response', {'error': 'Soru boş olamaz'})
            return
        try:
            result = ai_analyze(question, context)
            emit('ai_response', {
                'response': result['response'],
                'suggestions': result.get('suggestions', []),
            })
        except Exception as e:
            emit('ai_response', {'error': f'AI hatası: {str(e)}'})

    @socketio.on('ai_quick_prompts')
    def handle_ai_prompts(_data=None):
        """Hazır soru şablonlarını döndürür."""
        emit('ai_prompts', {'prompts': get_quick_prompts()})
