# EmareCloud — Kapsamlı Proje Brifing Belgesi
> **Hazırlayan:** EmareCloud AI Asistanı | **Tarih:** 6 Mart 2026  
> **Hedef Kitle:** EmareGoogle DC-3 Sistemi — Tüm modüllerin sunucuda çalışması için teknik altyapı sağlanacak

---

## 1. PROJE KİMLİĞİ

**EmareCloud**, küçük ve orta ölçekli teknoloji şirketlerine (SaaS, hosting firmaları, DevOps ekipleri) kendi altyapılarını tek bir web panelinden yönetme imkânı sunan **multi-tenant, güvenli, ölçeklenebilir bir sunucu yönetim platformudur.**

- **Teknoloji Stack:** Python 3.11+ / Flask 3.0 / Flask-SocketIO / SQLAlchemy / SQLite (tek sunucu) → PostgreSQL (ölçeklenme)
- **Frontend:** Jinja2 şablonları, vanilla JS, Socket.IO 4.7, Monaco Editor, xterm.js
- **Deploy:** Gunicorn + gevent-websocket, Nginx reverse proxy
- **Domain:** `emarecloud.tr` → Cloudflare proxy → `185.189.54.104` (DC-1)

---

## 2. MEVCUT ALTYAPI (3 SUNUCU — 3 DC)

| DC | Sunucu | IP | OS | Port | Durum |
|---|---|---|---|---|---|
| **DC-1** | Ana Panel | `185.189.54.104` | AlmaLinux 9.6 | 80 (nginx) / 5555 (gunicorn) | ✅ Aktif |
| **DC-2** | İkincil | `77.92.152.3` | AlmaLinux 9.7 | 80+3000 (nginx) / 5555 (gunicorn) | ✅ Aktif |
| **DC-3** | Google (YENİ) | TBD | TBD | TBD | 🔜 Kurulacak |

**DC-1 detayları:**
```
Kullanıcı: root
Şifre: As5327804227..
SSH: 22 (standart)
Uygulama: /opt/emarecloud/
Venv: /opt/emarecloud/venv/
Systemd servisi: emarecloud.service
WSGI dosyası: /opt/emarecloud/wsgi.py
Log dizini: /opt/emarecloud/logs/
```

**DC-2 detayları:**
```
Kullanıcı: root
Şifre: Emre205*
SSH Port: 2222 (standart değil!)
Uygulama: /opt/emarecloud/
Venv: /opt/emarecloud/venv/
Başlatma: gunicorn (HUP ile reload)
```

**Ortak admin hesabı (her DC):**
```
Kullanıcı adı: admin
Şifre: VefaSultan34*
Rol: super_admin
```

---

## 3. PROJE MİMARİSİ

### 3.1 Uygulama Fabrikası
```
app.py → create_app() → Flask uygulaması döndürür
         ├── SQLAlchemy (db.init_app)
         ├── Flask-Login (login_manager)
         ├── SocketIO (gevent async_mode)
         ├── CSRF koruması
         ├── API Token Bearer auth
         ├── Gzip + güvenlik header'ları (core/middleware.py)
         ├── Multi-tenant middleware (core/tenant.py)
         ├── 17 Blueprint kaydı
         └── Terminal SocketIO event'leri
```

### 3.2 Dizin Yapısı
```
/opt/emarecloud/
├── app.py                    # Ana uygulama factory
├── models.py                 # 14 veritabanı modeli (976 satır)
├── rbac.py                   # RBAC sistemi (4 rol, 36+ yetki)
├── config.py                 # Ortam bazlı yapılandırma
├── config.json               # Sunucu kimlik bilgileri (şifreli)
├── auth_routes.py            # Kimlik doğrulama route'ları
├── ssh_manager.py            # Paramiko SSH bağlantı yöneticisi
├── crypto.py                 # AES-256-GCM şifreleme
├── alert_manager.py          # Metrik alarm sistemi
├── backup_manager.py         # Yedekleme profil yöneticisi
├── scheduler.py              # Zamanlanmış görev çalıştırıcı
├── market_apps.py            # Uygulama pazarı + EmareCode projeleri
├── extensions.py             # SQLAlchemy, LoginManager objeleri
├── core/
│   ├── database.py           # DB migrations / init
│   ├── helpers.py            # get_server_by_id(), ssh_mgr global
│   ├── logging_config.py     # Yapılandırılmış loglama
│   ├── middleware.py         # Gzip sıkıştırma, güvenlik header'ları
│   └── tenant.py             # Tenant context middleware
├── routes/                   # 17 blueprint modülü (aşağıda detay)
├── templates/                # 70+ Jinja2 şablonu
├── static/css/               # style.css (ana stil dosyası)
├── blockchain/               # EMR Token akıllı kontrat entegrasyonu
├── instance/                 # SQLite DB (sunucu başına ayrı)
└── wsgi.py                   # Gunicorn WSGI giriş noktası
```

---

## 4. VERİTABANI MODELLERİ (14 Model)

| Model | Tablo | Açıklama |
|---|---|---|
| `Organization` | organizations | Multi-tenant ana birimi — her müşteri bir tenant |
| `Plan` | plans | Community / Professional / Enterprise / Reseller planları |
| `Subscription` | subscriptions | Org→Plan aboneliği, EMARE Token ödeme desteği |
| `ResourceQuota` | resource_quotas | Org başına özelleştirilebilir limitler |
| `User` | users | Kullanıcılar — 2FA, RBAC, custom permissions, online tracking |
| `AuditLog` | audit_logs | Tüm kullanıcı aksiyonlarının tam kayıtları |
| `DataCenter` | data_centers | DC tanımları (kod, lokasyon, sağlayıcı, koordinat) |
| `ServerCredential` | server_credentials | Sunucu bilgileri — AES-256-GCM şifreli parola |
| `ApiToken` | api_tokens | REST API erişim token'ları (Bearer auth) |
| `AppSetting` | app_settings | Anahtar-değer uygulama ayarları |
| `AlertRule` | alert_rules | CPU/RAM/disk eşik alarm kuralları |
| `AlertHistory` | alert_history | Tetiklenen alarm geçmişi |
| `WebhookConfig` | webhook_configs | Slack/Discord/e-posta/özel bildirim kanalları |
| `ScheduledTask` | scheduled_tasks | Cron job yönetimi (sunucu üzerinde) |
| `BackupProfile` | backup_profiles | Otomatik yedekleme profilleri |
| `MetricSnapshot` | metric_snapshots | Periyodik CPU/RAM/disk/ağ metrik kayıtları |
| `UserWallet` | user_wallets | EVM cüzdan adresleri (BSC mainnet/testnet) |
| `EmarePoint` | emare_points | EP ödül puanı kayıtları (token'a dönüştürülür) |
| `TokenTransaction` | token_transactions | Blockchain TX off-chain takip |

---

## 5. ROUTE BLUEPRINT'LERİ (17 Modül)

### 5.1 Kimlik Doğrulama — `auth_routes.py`
- `POST /login` — Kullanıcı girişi (2FA TOTP desteği)
- `POST /logout` — Çıkış
- `GET /admin/users` — Kullanıcı yönetimi paneli
- `POST /admin/users/create` — Kullanıcı oluştur
- `POST /admin/users/<id>/update-permissions` — Özel izin ata
- `POST /admin/users/<id>/impersonate` — Kullanıcı kimliğine bür
- `GET /admin/audit` — Denetim günlüğü

### 5.2 Sunucu Yönetimi — `routes/servers.py`
- `GET /api/servers` — Sunucu listesi (ping/latency ile)
- `POST /api/servers` — Sunucu ekle (AES şifreli parola kaydı)
- `PUT /api/servers/<id>` — Sunucu güncelle
- `DELETE /api/servers/<id>` — Sunucu sil
- `POST /api/servers/<id>/connect` — SSH bağlantısı kur
- `POST /api/servers/<id>/disconnect` — Bağlantıyı kes
- `GET /api/servers/<id>/detail` — Sunucu detayı

### 5.3 Gerçek Zamanlı Metrikler — `routes/metrics.py`
- `GET /api/metrics/<server_id>` — Anlık CPU, RAM, disk, ağ, yük
- `GET /api/metrics/<server_id>/history` — Tarihsel metrik verileri
- Metrikler SSH üzerinden `psutil` komutları ile toplanır

### 5.4 SSH Terminal — `routes/terminal.py`
- SocketIO event'leri:
  - `terminal_connect` — SSH kanalı aç
  - `terminal_input` — Tuş/komut gönder → SSH → çıktı → istemci
  - `watch_start` — Canlı izleme (log dosyası, komut çıktısı)
  - `watch_stop` — İzlemeyi durdur
  - `ai_assist` — Kod hakkında AI'ya soru sor
- Paramiko tabanlı SSH kanal yönetimi

### 5.5 Web IDE — `routes/ide.py` (YENİ)
- `GET /api/ide/<server_id>/ls?path=` — Dizin listele
- `GET /api/ide/<server_id>/read?path=` — Dosya içeriği oku (5MB sınır)
- `POST /api/ide/<server_id>/write` — Dosya kaydet (base64, otomatik .bak)
- `GET /api/ide/<server_id>/search?q=&path=` — Dosya içeriği ara (grep)
- `POST /api/ide/<server_id>/create` — Dosya/klasör oluştur
- `POST /api/ide/<server_id>/delete` — Güvenli sil (kritik yollar korumalı)
- `POST /api/ide/<server_id>/rename` — Yeniden adlandır/taşı
- **Güvenlik:** Path traversal koruması, BLOCKED_PATHS seti

### 5.6 Güvenlik Duvarı — `routes/firewall.py`
- UFW/iptables kural CRUD via SSH
- `GET /api/firewall/<id>/rules` — Aktif kurallar
- `POST /api/firewall/<id>/rule` — Kural ekle/sil

### 5.7 Sanal Makine — `routes/virtualization.py`
- LXC/Docker konteyner yönetimi via SSH
- Konteyner listele, başlat, durdur, oluştur, sil

### 5.8 Depolama — `routes/storage.py`
- Disk bölümü ve dosya sistemi bilgileri
- Disk kullanım grafikler, büyük dosya analizi

### 5.9 Monitoring — `routes/monitoring.py`
- Alert kuralı CRUD (AlertRule modeli)
- Webhook konfigürasyonu (Slack/Discord/email)
- Alarm tetikleme geçmişi (AlertHistory)
- Zamanlanmış görev yönetimi (ScheduledTask)

### 5.10 Komutlar — `routes/commands.py`
- Önceden tanımlı komut kütüphanesi
- Toplu komut çalıştırma (birden fazla sunucu)
- Komut favorileri, güvenlik filtresi (`command_security.py`)

### 5.11 Uygulama Pazarı — `routes/market.py`
- 40+ hazır uygulama (Nginx, MySQL, Redis, WordPress, Docker, Node.js, vb.)
- `POST /api/market/install` — SSH ile tek tıkla kurulum
- `GET /api/market/apps` — Kategori bazlı uygulama listesi
- **EmareCode Projeleri:** 35 EmareCode ile yazılmış proje (ilerleme yüzdeleriyle)

### 5.12 Cloudflare DNS — `routes/cloudflare.py`
- Cloudflare API v4 entegrasyonu
- DNS kayıt yönetimi (A, CNAME, MX, TXT, vb.)
- SSL/TLS mod yönetimi (strict, full, flexible)
- Proxy durumu (turuncu bulut) toggle

### 5.13 Veri Merkezleri — `routes/datacenters.py`
- DataCenter modeli CRUD
- Sunucuları DC'ye atama
- Lokasyon, sağlayıcı, IP range, koordinat bilgileri

### 5.14 Organizasyon Yönetimi — `routes/organizations.py`
- Tenant oluşturma, düzenleme, silme
- Üye yönetimi (davet, rol atama)
- Plan & abonelik görüntüleme

### 5.15 Token Ödemeleri — `routes/token.py`
- EMARE Token ile ödeme akışı
- BSC ağı üzerinde on-chain ödeme takibi
- Plan abonelik aktivasyonu

### 5.16 Geliştirici Panosu — `routes/scoreboard.py`
- Gerçek zamanlı geliştirici aktivite takibi
- `last_seen`, `current_activity` ile online durum
- Liderlik tablosu (pull request, commit, çalışma saati)

### 5.17 Sayfalar — `routes/pages.py`
- Tüm görsel sayfa render'larını yönetir (~490 satır)
- Dashboard, sunucu detay, terminal, IDE, market, AI araçları, vb.
- Her sayfa için login + RBAC permission kontrolü

---

## 6. RBAC — ROL BAZLI ERİŞİM KONTROLÜ

### 6.1 Roller
| Rol | Seviye | Açıklama |
|---|---|---|
| `super_admin` | 100 | Tam yetki, tüm module erişim |
| `admin` | 75 | Sunucu yönetimi, kullanıcı görüntüleme |
| `operator` | 50 | Komut çalıştırma, servis yönetimi |
| `read_only` | 10 | Sadece görüntüleme |

### 6.2 Yetki Grupları (36+ Permission)
```
Sunucu:      server.view / add / edit / delete / connect / execute / metrics / quick_action
Güvenlik:    firewall.view / manage
VM:          vm.view / manage
Pazar:       market.view / install
Depolama:    storage.view / manage
Terminal:    terminal.access
İzleme:      monitoring.view / manage
AI:          ai.view / manage
Kullanıcı:  user.view
Denetim:     audit.view
Org:         org.view / manage / members
Plan:        plan.view
Token:       token.manage
Cloudflare:  cloudflare.view
DC:          dc.view / manage
Pano:        scoreboard.view
Admin:       admin_panel
IDE:         terminal.access (re-uses)
```

### 6.3 Özellik: Özelleştirilmiş İzinler
- super_admin, herhangi bir kullanıcıya rol bağımsız özel izin listesi atayabilir
- `User.custom_permissions_json` sütununda JSON olarak saklanır

---

## 7. GÜVENLİK MİMARİSİ

### 7.1 Parola Güvenliği
```python
# Sunucu parolaları AES-256-GCM ile şifrelenir
ServerCredential.encrypted_password  # Şifreli parola bytes
ServerCredential.encryption_iv       # Her kayıt için eşsiz IV
# DB'de hiçbir zaman plaintext parola yok
```

### 7.2 Kimlik Doğrulama Katmanları
1. **Şifre + TOTP 2FA** (pyotp) — Google Authenticator uyumlu
2. **Kurtarma kodları** — 8 adet tek kullanımlık kod
3. **API Token (Bearer)** — SHA-256 hashlenen token, `emc_` prefix
4. **CSRF koruması** — Tüm POST isteklerinde session token doğrulaması

### 7.3 Denetim Loglama
- Her kritik aksiyon AuditLog'a yazılır
- `user_id, action, target_type, target_id, ip_address, user_agent, success`
- Silme, bağlantı, komut çalıştırma, login başarısız gibi olaylar

### 7.4 Komut Güvenliği (`command_security.py`)
- Tehlikeli komutlar engellenir: `rm -rf /`, `dd if=`, `mkfs`, vb.
- Her komut çalıştırılmadan önce pattern eşleşmesi kontrolü

---

## 8. SSH BAĞLANTI YÖNETİCİSİ (`ssh_manager.py`)

```python
class SSHManager:
    # Otomatik SSH key pair üretimi + sunucuya deploy eder
    # Paramiko tabanlı bağlantı havuzu
    # Her sunucu için persistent channel
    
    def execute_command(server_id, command, timeout=30) -> (bool, str, str):
        # returns (ok, stdout, stderr)
    
    def is_connected(server_id) -> bool
    def check_server_reachable(host, port) -> (bool, float)  # (ok, latency_ms)
```

**Bağlantı Akışı:**
1. `config.json`'dan sunucu kimlik bilgileri yüklenir
2. SSH key varsa key auth denenır
3. Key yoksa parola auth kullanılır
4. Key auth başarılıysa ileride key deploy edilir (parola gerekmez)

---

## 9. FRONTEND MİMARİSİ

### 9.1 Temel Şablon (`templates/base.html` — 493 satır)
- Tüm sayfalar bu şablonu extend eder
- Kenar çubuğu (sidebar): RBAC'a göre dinamik menü
- Global AI Chat asistanı (sağ alt köşe)
- Sunucu ekleme modal
- Aktivite takip middleware entegrasyonu

### 9.2 Kritik Template'ler
| Şablon | Satır | Açıklama |
|---|---|---|
| `base.html` | 493 | Tüm sayfaların ana iskeleti |
| `ide.html` | ~1400 | VS Code benzeri Web IDE |
| `terminal.html` | ~1000 | SSH terminal + izleme paneli |
| `market.html` | ~1080 | Uygulama pazarı + EmareCode projeleri |
| `admin/panel.html` | ~800 | Süper admin kontrol paneli |
| `admin/users.html` | ~600 | Kullanıcı yönetimi |
| `datacenters.html` | ~500 | DC yönetimi + sunucu haritası |
| `scoreboard.html` | ~450 | Geliştirici aktivite panosu |

### 9.3 Yüklenen Kütüphaneler (CDN)
- **Socket.IO 4.7.2** — Terminal ve AI chat için gerçek zamanlı iletişim
- **Monaco Editor 0.45.0** — VS Code çekirdek editörü (Web IDE'de)
- **xterm.js 5.3.0 + FitAddon** — Terminal emülatörü (Web IDE'de)
- **Font Awesome 6.5.1** — İkonlar
- **Cloudflare Fonts** — Inter, JetBrains Mono

---

## 10. WEB IDE (SON EKLENTİ)

Web IDE, tarayıcıdan VS Code deneyimi sunar:

```
├── Sol Panel:   Dosya Explorer (lazy-load ağaç, sağ tık context menu)
├── Orta Panel:  Monaco Editor (çoklu tab, syntax highlight, minimap)
├── Alt Panel:   xterm.js Terminal (SocketIO ile gerçek SSH)
└── Sağ Panel:   AI Chat (kod analizi, bug bulma, optimizasyon)
```

**Kısayollar:** `Ctrl+S` Kaydet | `Ctrl+B` Dosyalar | `` Ctrl+` `` Terminal | `Ctrl+Shift+I` AI Chat

**Güvenlik:**
- Path traversal koruması (`/`, `/etc`, `/bin`, `/sbin`, `/lib` engellendi)
- Kritik sistem dizinlerine yazma yasak
- Dosya boyutu limiti: 5MB

---

## 11. BLOCKCHAIN & EMARE TOKEN EKOSİSTEMİ

### 11.1 EMARE Token (EMR)
- BSC ağında ERC-20 token
- 1 EMARE ≈ $0.1
- Abonelik ödemelerinde kullanım desteği

### 11.2 Emare Puanı (EP)
- Kullanıcı aksiyonlarına göre kazanılan puan
- `server_added`, `subscription_payment`, `daily_login` gibi aksiyonlar
- EP → EMR dönüşümü: RewardPool akıllı kontratı üzerinden on-chain claim

### 11.3 Smart Contract Entegrasyonu (`blockchain/`)
```
contracts.py      # ABI ve kontrat adresleri
reward_engine.py  # EP hesaplama mantığı
service.py        # Web3.py bağlantısı (şu an devre dışı — BLOCKCHAIN_ENABLED=false)
```

---

## 12. YAPILANDIRMA SİSTEMİ

### 12.1 `config.py` — Ortam Bazlı Config
```python
class DevelopmentConfig:
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///emarecloud.db'
    
class ProductionConfig:
    DEBUG = False
    # Ortam değişkenlerinden okur
```

### 12.2 `config.json` — Sunucu Bilgileri
```json
{
  "servers": [
    {
      "id": "srv-001",
      "name": "DC-1 Ana Sunucu",
      "host": "185.189.54.104",
      "port": 22,
      "username": "root",
      "password": "<AES-256-GCM şifreli>"
    }
  ]
}
```
> ⚠️ `config.json` deploy sırasında `rsync --exclude='config.json'` ile ASLA üzerine yazılmaz.

---

## 13. DEPLOY SÜRECİ

### 13.1 Standart Deploy Komutu
```bash
# Lokal → Sunucu senkronizasyonu
rsync -avz \
  --exclude='.venv' \
  --exclude='instance' \
  --exclude='.env' \
  --exclude='config.json' \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='node_modules' \
  --exclude='venv' \
  /Users/emre/Desktop/Emare/emarecloud/ \
  root@<SUNUCU_IP>:/opt/emarecloud/
```

### 13.2 Servis Yönetimi
```bash
# DC-1 (systemd)
systemctl restart emarecloud

# DC-2 (manuel gunicorn)
kill -HUP $(pgrep -f "gunicorn.*wsgi:app" | head -1)

# Yeni DC için kurulum scripti
/opt/emarecloud/setup.sh
```

### 13.3 DB Migration
```bash
cd /opt/emarecloud
venv/bin/python -c "
from app import create_app
from extensions import db
app, _ = create_app()
with app.app_context():
    db.create_all()
    print('DB hazır')
"
```

---

## 14. DC-3 (GOOGLE) — KURULUM GEREKSİNİMLERİ

EmareCloud'un DC-3'te çalışabilmesi için gereken adımlar:

### 14.1 Sistem Gereksinimleri
```
OS: AlmaLinux 9.x / Rocky Linux 9.x / Ubuntu 22.04 LTS
Python: 3.11+
RAM: Minimum 1GB (önerilen 2GB+)
Disk: Minimum 20GB
Port: 80 (nginx), 5555 (gunicorn iç), 22 (SSH)
```

### 14.2 Kurulum Adımları
```bash
# 1. Dizin yapısı
mkdir -p /opt/emarecloud/logs
useradd -r -s /bin/false emarecloud  # veya root kullanılabilir

# 2. Python venv
python3.11 -m venv /opt/emarecloud/venv
/opt/emarecloud/venv/pip install -r /opt/emarecloud/requirements.txt

# 3. Gunicorn başlatma
cd /opt/emarecloud
venv/bin/gunicorn \
  --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
  --workers 1 --bind 0.0.0.0:5555 \
  --timeout 120 --keep-alive 5 \
  wsgi:app

# 4. wsgi.py içeriği
cat > /opt/emarecloud/wsgi.py << 'EOF'
from app import create_app
app, _ = create_app()
EOF

# 5. Nginx config (80 → 5555 proxy)
# WebSocket upgrade desteği gerekli!
```

### 14.3 Nginx Gereksinimi (Kritik)
```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 80;
    server_name <DC3_DOMAIN>;
    
    location / {
        proxy_pass http://127.0.0.1:5555;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_read_timeout 86400;
    }
}
```
> ⚠️ `proxy_set_header Connection "upgrade"` şeklinde sabit değer YAZILMAZ — oturum kesilmelerine yol açar. `$connection_upgrade` değişkeni kullanılmalıdır.

### 14.4 Python Requirements
```
flask==3.0.0
flask-sqlalchemy==3.1.1
flask-login==0.6.3
paramiko==3.4.0           # SSH bağlantıları için kritik
psutil==5.9.7
flask-socketio==5.3.6
gevent==24.2.1            # Async worker
gevent-websocket==0.10.1  # WebSocket desteği
cryptography==41.0.7      # AES şifreleme
gunicorn==21.2.0
pyotp==2.9.0              # 2FA desteği
qrcode==8.2
```

---

## 15. MEVCUT SORUNLAR & GELİŞTİRME İHTİYAÇLARI

### 15.1 Frontend (Demo → Gerçek)
Şu anda birçok AI modülü sadece frontend demo'dur, gerçek backend entegrasyonu yok:
- AI Wizard, AI Cost Estimation, AI Logs Intelligence, AI Performance Score, vb.
- Bu modüllerin gerçek çalışması için:
  - Google Gemini API veya OpenAI API entegrasyonu
  - `/api/ai/analyze`, `/api/ai/cost`, `/api/ai/optimize` endpoint'leri
  - Gerçek sunucu metrik verisi ile AI çıktısı üretimi

### 15.2 Veritabanı Ölçeklenme
- Şu an SQLite (sunucu başına ayrı DB, tenant izolasyonu yok)
- Ölçeklenme için: PostgreSQL + connection pooling
- Multi-DC için: Merkezi bir DB (veya replikasyon)

### 15.3 Terminal Emülatörü
- Web IDE terminali: xterm.js + SocketIO (GERÇEK PTY)
- Eski terminal.html: Custom div+input (sınırlı, PTY değil)
- IDE terminali production'a taşınmalı

### 15.4 Gerçek Zamanlı Metrik Akışı
- Şu an: HTTP polling (manuel yenile veya interval)
- Geliştirme: WebSocket üzerinden sürekli metrik push (MetricSnapshot + SocketIO)

### 15.5 Blockchain (Devre Dışı)
- `BLOCKCHAIN_ENABLED=false` → tüm EP/EMR işlemleri frontend sayfası
- Aktifleştirmek için: `web3.py` paketi + BSC RPC URL + kontrat adresleri

---

## 16. CLOUDFLARE ENTEGRASYONU

```
API Token: YSaZrmVvW07MDCEwJSPJNeYKXVUrpK1lykaLDSQ9
Zone ID:   a72e4fe4787b786fb91d41a3491949eb
SSL Mode:  flexible (origin HTTP, Cloudflare HTTPS → ziyaretçi)

DNS Kayıtları:
  A     emarecloud.tr       → 185.189.54.104   (proxied)
  CNAME www.emarecloud.tr   → emarecloud.tr     (proxied)
  A     asistan.emarecloud.tr → 77.92.152.3    (DC-2)
  A     api-user.emarecloud.tr → 78.135.86.97
  A     user.emarecloud.tr    → 78.135.86.97
```

---

## 17. PROJE YOL HARİTASI (PRODUCT_ROADMAP.md'den)

| Faz | Durum | İçerik |
|---|---|---|
| MVP | ✅ Tamamlandı | Sunucu yönetimi, SSH terminal, RBAC, metrikler |
| Faz 2 | ✅ Tamamlandı | Multi-tenant, organizasyon, abonelik planları |
| Faz 3 | 🔄 Devam ediyor | AI entegrasyonları, Web IDE, Geliştirici panosu |
| Faz 4 | 📋 Planlandı | PostgreSQL, gerçek AI, blockchain aktifleştirme |
| Faz 5 | 📋 Planlandı | Mobil app, API marketplace, reseller modülü |

---

## 18. EMARECLOUD'UN TANIM CÜMLESI

> EmareCloud; sunucu yönetimini, güvenliği, izlemeyi, yedeklemeyi, terminal erişimini, firewall yönetimini, DNS yönetimini ve geliştirici araçlarını **tek bir güvenli web panelinde** birleştiren, multi-tenant mimarisi ile birden fazla şirketin aynı platformu kendi izole alanında kullanabildiği, EMARE Token blockchain ekosistemiyle entegre çalışabilen, **tam stack bir altyapı yönetim platformudur.**

---

## 19. DC-3 GOOGLE İÇİN ÖZET YAPILACAKLAR

```
☐ 1. Google Cloud VM oluştur (Compute Engine veya GKE)
☐ 2. AlmaLinux/Ubuntu kurulumu
☐ 3. Python 3.11+ + venv + requirements.txt
☐ 4. rsync ile /opt/emarecloud/ senkronizasyonu
☐ 5. wsgi.py oluşturma
☐ 6. gunicorn başlatma (geventwebsocket worker)
☐ 7. Nginx kurulum + WebSocket config (map $connection_upgrade MANDATEd!)
☐ 8. DB migration (db.create_all())
☐ 9. Admin şifresi ayarla (VefaSultan34* veya yeni)
☐ 10. EmareCloud panelinden "DC Ekle" → yeni DC kaydı
☐ 11. Cloudflare'de yeni A kaydı (dc3.emarecloud.tr)
☐ 12. Systemd service tanımı (otomatik başlatma için)
```

---

*Bu belge EmareCloud projesinin 6 Mart 2026 itibarıyla tam durumunu yansıtır.*  
*Herhangi bir modül için ek detay istenirse `routes/`, `templates/` ve `models.py` referans alınmalıdır.*
