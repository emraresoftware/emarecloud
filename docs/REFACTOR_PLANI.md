# EmareCloud — Modüler Refactor Planı

> **Hedef:** `app.py` (1181 satır) → Blueprint yapısına geçiş  
> **Tarih:** Mart 2026  
> **Strateji:** Risk azaltan sıra — her adımda testler geçmeli, uygulama çalışmalı

---

## 1. Mevcut Durum

### app.py İç Yapısı (1181 satır)

```
Satır   1-48    İmportlar + bağımlılıklar
Satır  49-76    Uygulama oluşturma (create_app benzeri)
Satır  77-90    User loader + auth
Satır  91-107   CSRF + template globals
Satır 108-205   Veritabanı başlatma + migration
Satır 206-252   Güvenlik middleware (gzip + headers)
Satır 253-350   Yardımcı fonksiyonlar (server helpers, config I/O)
Satır 351-442   Sayfa route'ları (7 sayfa)
Satır 443-534   RAID protokolleri API (5 endpoint)
Satır 535-694   Sunucu yönetim API (8 endpoint)
Satır 695-759   Metrik API (7 endpoint)
Satır 760-831   Firewall API (5 endpoint)
Satır 832-918   VM (LXD) API (7 endpoint)
Satır 919-977   Komut çalıştırma API (2 endpoint)
Satır 978-1106  Market + GitHub API (6 endpoint)
Satır 1107-1172 SocketIO terminal (2 event)
Satır 1173-1181 Main entry point
```

### Mevcut Bağımsız Modüller (dokunulmayacak)

| Dosya | Satır | Sorumluluk |
|-------|-------|------------|
| `auth_routes.py` | ~280 | Auth blueprint (zaten ayrık ✅) |
| `rbac.py` | ~85 | Rol & yetki tanımları |
| `command_security.py` | ~120 | Komut güvenlik politikası |
| `crypto.py` | ~60 | AES-256-GCM şifreleme |
| `audit.py` | ~65 | Denetim günlüğü |
| `models.py` | ~210 | DB modelleri |
| `config.py` | ~75 | Yapılandırma sınıfları |
| `extensions.py` | ~15 | Flask uzantıları |
| `ssh_manager.py` | ~300 | SSH bağlantı yönetimi |
| `server_monitor.py` | ~400 | Metrik toplama |
| `firewall_manager.py` | ~200 | UFW/firewalld yönetimi |
| `virtualization_manager.py` | ~350 | LXD yönetimi |
| `market_apps.py` | ~900 | Market kataloğu + GitHub |

---

## 2. Hedef Yapı

```
emarecloud/
├── app.py                      # ~80 satır — create_app() + main
├── extensions.py               # Flask uzantıları (mevcut)
├── config.py                   # Yapılandırma (mevcut)
├── models.py                   # DB modelleri (mevcut)
├── crypto.py                   # Şifreleme (mevcut)
├── rbac.py                     # RBAC (mevcut)
├── command_security.py         # Komut güvenliği (mevcut)
├── audit.py                    # Denetim günlüğü (mevcut)
│
├── core/
│   ├── __init__.py
│   ├── middleware.py            # gzip + security headers (~50 satır)
│   ├── database.py             # init_database + migration (~100 satır)
│   ├── helpers.py              # get_server_by_id, get_servers_for_sidebar (~80 satır)
│   └── config_io.py            # load_config, save_config (~20 satır)
│
├── routes/
│   ├── __init__.py             # register_blueprints() fonksiyonu
│   ├── auth.py                 # (mevcut auth_routes.py → taşınacak)
│   ├── pages.py                # Sayfa route'ları: /, /market, /server, /terminal... (~90 satır)
│   ├── servers.py              # /api/servers/* CRUD + connect/disconnect (~160 satır)
│   ├── metrics.py              # /api/servers/<id>/cpu|memory|disks|... (~65 satır)
│   ├── firewall.py             # /api/servers/<id>/firewall/* (~75 satır)
│   ├── virtualization.py       # /api/servers/<id>/vms/* (~90 satır)
│   ├── commands.py             # /api/servers/<id>/execute + quick-action (~60 satır)
│   ├── storage.py              # /api/raid-protocols/* + storage-status (~95 satır)
│   ├── market.py               # /api/market/* + GitHub API (~130 satır)
│   └── terminal.py             # SocketIO events (~70 satır)
│
├── services/                   # (mevcut dosyalar, isimleri korunur)
│   ├── ssh_manager.py
│   ├── server_monitor.py
│   ├── firewall_manager.py
│   ├── virtualization_manager.py
│   └── market_apps.py
│
├── templates/                  # (mevcut, değişiklik yok)
├── static/                     # (mevcut, değişiklik yok)
├── tests/                      # (mevcut, import path'leri güncellenecek)
├── docs/                       # (mevcut)
├── instance/                   # SQLite DB
├── docker-compose.yml
├── gunicorn.conf.py
├── Dockerfile
└── requirements.txt
```

---

## 3. Refactor Adımları (Risk Azaltan Sıra)

### Prensip

```
Her adımda:
  1. Kodu taşı
  2. Import'ları güncelle
  3. pytest çalıştır → hepsi geçmeli
  4. Sunucuyu başlat → hatasız çalışmalı
  5. Commit at
```

---

### Adım 0: Hazırlık (15 dakika)

**Risk: ⚪ Sıfır** — Hiçbir kodu değiştirmiyoruz

- [ ] Git'te yeni branch: `git checkout -b refactor/modular-blueprints`
- [ ] Mevcut testlerin tamamının geçtiğini doğrula: `pytest tests/ -v`
- [ ] `core/` ve `routes/` klasörlerini oluştur
- [ ] `core/__init__.py` ve `routes/__init__.py` boş dosyaları oluştur

```bash
mkdir -p core routes
touch core/__init__.py routes/__init__.py
pytest tests/ -v
```

---

### Adım 1: Middleware'leri Ayır (20 dakika)

**Risk: 🟢 Düşük** — Bağımsız fonksiyonlar, yan etkisi yok

**Taşınacak:** `compress_response()` + `add_security_headers()`  
**Kaynak:** `app.py` satır 206-252  
**Hedef:** `core/middleware.py`

```python
# core/middleware.py
import gzip
from flask import request

def register_middleware(app):
    """After-request middleware'lerini kaydet."""

    @app.after_request
    def compress_response(response):
        # ... mevcut compress_response kodu ...

    @app.after_request
    def add_security_headers(response):
        # ... mevcut add_security_headers kodu ...
```

**app.py'deki değişiklik:**
```python
# Eski kod silinir, yerine:
from core.middleware import register_middleware
register_middleware(app)
```

**Doğrulama:**
```bash
pytest tests/ -v
python3 app.py  # hatasız başlamalı
curl -I http://localhost:5555/login  # güvenlik header'ları gelmeliq
```

---

### Adım 2: Veritabanı Başlatma & Migration'ı Ayır (25 dakika)

**Risk: 🟢 Düşük** — Startup fonksiyonları, runtime'da çağrılmaz

**Taşınacak:** `init_database()`, `_migrate_servers_from_config()`, `_migrate_settings_from_config()`  
**Kaynak:** `app.py` satır 108-205  
**Hedef:** `core/database.py`

```python
# core/database.py
from extensions import db
from models import User, ServerCredential, AppSettings
from crypto import encrypt_value
from audit import log_action

def init_database(app):
    """Veritabanını oluştur ve migration'ları çalıştır."""
    with app.app_context():
        db.create_all()
        _create_default_admin()
        _migrate_servers_from_config()
        _migrate_settings_from_config()

def _create_default_admin():
    # ... mevcut kod ...

def _migrate_servers_from_config():
    # ... mevcut kod ...

def _migrate_settings_from_config():
    # ... mevcut kod ...
```

**Doğrulama:**
```bash
pytest tests/ -v
python3 app.py  # DB migration hatasız çalışmalı
```

---

### Adım 3: Yardımcı Fonksiyonları Ayır (15 dakika)

**Risk: 🟢 Düşük** — Saf fonksiyonlar, dependency yok

**Taşınacak:** `get_server_by_id()`, `get_servers_for_sidebar()`, `get_app_settings()`, `_connect_server_ssh()`, `_check_single_server()`  
**Kaynak:** `app.py` satır 253-350  
**Hedef:** `core/helpers.py`

**Taşınacak:** `load_config()`, `save_config()`  
**Kaynak:** `app.py` satır 335-350  
**Hedef:** `core/config_io.py`

**Bu fonksiyonlar route'lar tarafından kullanılacak — import path'i önemli:**
```python
# routes/*.py dosyalarından:
from core.helpers import get_server_by_id, get_servers_for_sidebar
from core.config_io import load_config, save_config
```

---

### Adım 4: Metrik API Blueprint (20 dakika)

**Risk: 🟢 Düşük** — En basit blueprint, sadece GET endpoint'leri

**Neden bu ilk?** En az bağımlılığı var (sadece `get_server_by_id` + `server_monitor`), yan etkisi yok.

**Taşınacak:** 7 GET endpoint (satır 695-759)  
**Hedef:** `routes/metrics.py`

```python
# routes/metrics.py
from flask import Blueprint, jsonify
from flask_login import login_required
from rbac import permission_required
from core.helpers import get_server_by_id
import server_monitor

metrics_bp = Blueprint('metrics', __name__)

@metrics_bp.route('/api/servers/<server_id>/metrics', methods=['GET'])
@login_required
@permission_required('server.metrics')
def api_server_metrics(server_id):
    server = get_server_by_id(server_id)
    if not server: return jsonify({'success': False, 'message': 'Sunucu bulunamadı'}), 404
    return jsonify(server_monitor.get_metrics(server))
# ... diğer 6 endpoint ...
```

**Doğrulama:**
```bash
pytest tests/ -v
curl http://localhost:5555/api/servers/srv-xxx/metrics  # 200 veya 302
```

---

### Adım 5: Firewall API Blueprint (20 dakika)

**Risk: 🟡 Orta** — POST endpoint'leri var ama basit

**Taşınacak:** 5 endpoint (satır 760-831)  
**Hedef:** `routes/firewall.py`

```python
# routes/firewall.py
from flask import Blueprint, request, jsonify
from flask_login import login_required
from rbac import permission_required
from core.helpers import get_server_by_id
from audit import log_action
import firewall_manager

firewall_bp = Blueprint('firewall', __name__)
# ... 5 endpoint ...
```

---

### Adım 6: VM (LXD) API Blueprint (20 dakika)

**Risk: 🟡 Orta** — CRUD + exec endpoint'i

**Taşınacak:** 7 endpoint (satır 832-918)  
**Hedef:** `routes/virtualization.py`

---

### Adım 7: Depolama/RAID API Blueprint (20 dakika)

**Risk: 🟡 Orta** — Config dosyası I/O var

**Taşınacak:** 5 RAID endpoint + 1 storage-status (satır 443-534)  
**Hedef:** `routes/storage.py`

**Bağımlılık:** `core/config_io.py` (load_config, save_config)

---

### Adım 8: Sunucu CRUD API Blueprint (30 dakika)

**Risk: 🟡 Orta** — En çok bağımlılığı olan blueprint

**Taşınacak:** 8 endpoint (satır 535-694)  
**Hedef:** `routes/servers.py`

**Bağımlılıklar:** `get_server_by_id`, `_connect_server_ssh`, `_check_single_server`, `ServerCredential`, `encrypt_value`, `audit.log_action`

**Dikkat:** `api_add_server()` ve `api_update_server()` fonksiyonları en karmaşık olanlar — özellikle credential şifreleme mantığı.

---

### Adım 9: Komut Çalıştırma API Blueprint (20 dakika)

**Risk: 🔴 Yüksek** — Kritik güvenlik yüzeyi

**Taşınacak:** 2 endpoint (satır 919-977)  
**Hedef:** `routes/commands.py`

```python
# routes/commands.py
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from rbac import permission_required
from command_security import check_command
from audit import log_action
from core.helpers import get_server_by_id
import ssh_manager

commands_bp = Blueprint('commands', __name__)

@commands_bp.route('/api/servers/<server_id>/execute', methods=['POST'])
@login_required
@permission_required('server.execute')
def api_execute_command(server_id):
    # ... command_security kontrolü + audit log ...
```

**Doğrulama (ekstra):**
```bash
pytest tests/test_security.py -v  # Tüm komut güvenlik testleri geçmeli
```

---

### Adım 10: Market + GitHub API Blueprint (25 dakika)

**Risk: 🟡 Orta** — Dış API çağrıları var

**Taşınacak:** 6 endpoint (satır 978-1106)  
**Hedef:** `routes/market.py`

---

### Adım 11: SocketIO Terminal Blueprint (25 dakika)

**Risk: 🔴 Yüksek** — WebSocket, threading, SSH channel

**Taşınacak:** 2 SocketIO event handler (satır 1107-1172)  
**Hedef:** `routes/terminal.py`

**Dikkat:** SocketIO event'leri Blueprint ile farklı çalışır:

```python
# routes/terminal.py
from flask_socketio import emit
from flask_login import current_user
import ssh_manager
import threading

def register_socketio_events(socketio):
    """SocketIO event'lerini kaydet."""

    @socketio.on('terminal_connect')
    def handle_terminal_connect(data):
        # ... mevcut kod ...

    @socketio.on('terminal_input')
    def handle_terminal_input(data):
        # ... mevcut kod ...
```

**app.py'de:**
```python
from routes.terminal import register_socketio_events
register_socketio_events(socketio)
```

---

### Adım 12: Sayfa Route'ları Blueprint (15 dakika)

**Risk: 🟢 Düşük** — Sadece render_template çağrıları

**Taşınacak:** 7 sayfa route (satır 351-442)  
**Hedef:** `routes/pages.py`

```python
# routes/pages.py
from flask import Blueprint, render_template, redirect, url_for, jsonify
from flask_login import login_required
from rbac import permission_required
from core.helpers import get_servers_for_sidebar
from market_apps import get_all_apps, get_categories, get_apps_by_category

pages_bp = Blueprint('pages', __name__)

@pages_bp.route('/health')
def health():
    return jsonify({'status': 'ok'})

@pages_bp.route('/')
@login_required
def dashboard():
    # ...
```

---

### Adım 13: Blueprint Kayıt + app.py Temizlik (20 dakika)

**Risk: 🟡 Orta** — Final entegrasyon

**Hedef:** `routes/__init__.py`

```python
# routes/__init__.py
def register_blueprints(app, socketio):
    """Tüm blueprint'leri kaydet."""
    from routes.pages import pages_bp
    from routes.servers import servers_bp
    from routes.metrics import metrics_bp
    from routes.firewall import firewall_bp
    from routes.virtualization import vms_bp
    from routes.commands import commands_bp
    from routes.storage import storage_bp
    from routes.market import market_bp
    from routes.terminal import register_socketio_events
    from auth_routes import auth_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(servers_bp)
    app.register_blueprint(metrics_bp)
    app.register_blueprint(firewall_bp)
    app.register_blueprint(vms_bp)
    app.register_blueprint(commands_bp)
    app.register_blueprint(storage_bp)
    app.register_blueprint(market_bp)

    register_socketio_events(socketio)
```

**Final app.py (~80 satır):**

```python
# app.py — EmareCloud Ana Giriş Noktası
import os
from flask import Flask
from flask_socketio import SocketIO
from flask_login import LoginManager, current_user

from config import get_config
from extensions import db
from models import User

def create_app():
    app = Flask(__name__)
    app.config.from_object(get_config())

    # Uzantılar
    db.init_app(app)
    login_manager = LoginManager(app)
    login_manager.login_view = 'auth.login_page'
    login_manager.login_message = 'Lütfen giriş yapın.'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        from flask import request, redirect, url_for, jsonify
        if request.is_json or request.path.startswith('/api/'):
            return jsonify({'success': False, 'message': 'Giriş gerekli'}), 401
        return redirect(url_for('auth.login_page', next=request.url))

    # CSRF + template globals
    from core.middleware import register_middleware, register_context
    register_context(app)
    register_middleware(app)

    # Veritabanı başlatma
    from core.database import init_database
    init_database(app)

    # Blueprint'ler
    socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')
    from routes import register_blueprints
    register_blueprints(app, socketio)

    return app, socketio

app, socketio = create_app()

if __name__ == '__main__':
    print("=" * 60)
    print("  🏢 EmareCloud — Altyapı Yönetim Paneli")
    print(f"  📍 http://localhost:{app.config.get('PORT', 5555)}")
    print("  🔒 Auth: Aktif | RBAC: Aktif | Encryption: AES-256-GCM")
    print("=" * 60)
    socketio.run(app, host='0.0.0.0', port=int(app.config.get('PORT', 5555)),
                 debug=app.config.get('DEBUG', False), allow_unsafe_werkzeug=True)
```

**Doğrulama (final):**
```bash
pytest tests/ -v                           # Tüm testler geçmeli
python3 app.py                             # Hatasız başlamalı
curl -I http://localhost:5555/login         # 200 + güvenlik header'ları
curl http://localhost:5555/health           # {"status": "ok"}
```

---

### Adım 14: Test Import'larını Güncelle (15 dakika)

**Risk: 🟢 Düşük** — Sadece import path değişiklikleri

```python
# tests/conftest.py — güncelle:
# from app import app → from app import create_app
@pytest.fixture
def app():
    app, socketio = create_app()
    app.config['TESTING'] = True
    # ...
```

---

### Adım 15: print → logging Geçişi (30 dakika)

**Risk: 🟢 Düşük** — Fonksiyonel değişiklik yok

```python
# core/logging.py
import logging
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'module': record.module,
            'message': record.getMessage(),
            'extra': getattr(record, 'extra', {})
        })

def setup_logging(app):
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    app.logger.handlers = [handler]
    app.logger.setLevel(logging.INFO if not app.debug else logging.DEBUG)

    # Tüm print() çağrılarını logger ile değiştir
    # grep -rn "print(" *.py | wc -l → kaç tane var kontrol et
```

**Toplu değiştirme:**
```bash
# Her modülde:
# print(f"...") → app.logger.info("...")  veya  logger.info("...")
```

---

## 4. Refactor Zaman Çizelgesi

| Gün | Adımlar | Tahmini Süre | Risk |
|-----|---------|-------------|------|
| **Gün 1** | Adım 0-3 (Hazırlık + core/) | 1.5 saat | 🟢 |
| **Gün 1** | Adım 4-5 (Metrik + Firewall) | 40 dakika | 🟢 |
| **Gün 2** | Adım 6-8 (VM + Storage + Servers) | 1.5 saat | 🟡 |
| **Gün 2** | Adım 9-10 (Commands + Market) | 45 dakika | 🟡-🔴 |
| **Gün 3** | Adım 11-13 (Terminal + Pages + Kayıt) | 1 saat | 🔴 |
| **Gün 3** | Adım 14-15 (Tests + Logging) | 45 dakika | 🟢 |

**Toplam: ~6.5 saat (3 iş günü)**

---

## 5. Geri Dönüş Planı

Her adımda ayrı commit atıldığı için:

```bash
# Herhangi bir adımda sorun çıkarsa:
git log --oneline -10           # Son commit'leri gör
git revert <commit-hash>        # Sorunlu adımı geri al
# veya
git reset --hard <safe-commit>  # Güvenli noktaya dön
```

---

## 6. Refactor Sonrası Metrikler

| Metrik | Önce | Sonra | İyileşme |
|--------|------|-------|----------|
| `app.py` satır sayısı | 1181 | ~80 | **%93 azalma** |
| Blueprint sayısı | 1 (auth_routes) | 10 | Modüler yapı |
| En büyük dosya | app.py (1181) | servers.py (~160) | **%86 azalma** |
| Test coverage | ~28 test | ~28 test (korunur) | Aynı |
| Import depth | Düz | 2 seviye (routes/core) | Temiz |

---

## 7. Refactor Sonrası YAPILACAKLAR

Refactor tamamlandıktan sonra:

1. **CORS kısıtlama:** `SocketIO(app, cors_allowed_origins=['http://localhost:5555'])` 
2. **Alembic migration:** `flask db init && flask db migrate`
3. **Şifre karmaşıklık:** `auth_routes.py`'de regex doğrulama
4. **WebSocket auth:** `terminal.py`'de `@socketio.on` event'lerine `has_permission` kontrolü
5. **Rate limiting:** `Flask-Limiter` + Redis backend
6. **Setup wizard:** `setup.sh` veya `/setup` ilk kurulum route'u
7. **Lisans modülü:** `core/licensing.py` + RSA-signed JSON
