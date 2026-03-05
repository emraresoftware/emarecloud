# API ve Modül Referansı

Bu doküman, EmareCloud'in modüler mimarisini, Blueprint yapısını ve API uçlarını özetler.

## Mimari Genel Bakış

Proje **factory pattern** (`create_app()`) ile başlatılır. İş mantığı `core/` çekirdek modüllerine, route'lar `routes/` Blueprint'lerine ayrılmıştır.

## Çekirdek Modüller (`core/`)

### `core/middleware.py`

- Gzip sıkıştırma (response)
- Güvenlik başlıkları (CSP, X-Frame-Options, X-Content-Type-Options, HSTS)

### `core/database.py`

- SQLite veritabanı başlatma
- Şema migrasyon yönetimi

### `core/helpers.py`

- Sunucu yardımcı fonksiyonları
- SSH yönetici (SSHManager) erişimi
- Ayarlar yükleme/kaydetme
- ThreadPoolExecutor yönetimi

### `core/config_io.py`

- RAID config JSON okuma/yazma

### `core/logging_config.py`

- `JSONFormatter`: Üretim ortamı için yapılandırılmış JSON log
- `HumanReadableFormatter`: Geliştirme ortamı için renkli log
- `RotatingFileHandler`: Log rotasyonu

## Uygulama Modülleri

### `app.py`

- Factory pattern (`create_app()`) — ~95 satır
- Blueprint kayıt, middleware init, SocketIO init

### `config.py`

- CORS izin listesi (`CORS_ALLOWED_ORIGINS`)
- Debug/üretim modu ayarları
- Secret key yönetimi

### `auth_routes.py`

- Login / logout / register endpoint'leri
- Session tabanlı kimlik doğrulama
- RBAC dekoratörü (`@role_required`)
- `validate_password()`: 5 kural (uzunluk, büyük harf, küçük harf, rakam, özel karakter)
- Brute-force koruması

### `license_manager.py`

- RSA-4096 imzalı JSON lisans doğrulama
- `LicenseInfo` veri sınıfı
- `verify_license()`, `check_server_limit()`, `check_feature()`
- Planlar: Community (3 sunucu), Professional (25), Enterprise (sınırsız)

## Blueprint'ler (`routes/`)

### `routes/pages.py`

- Sayfa route'ları: dashboard, market, server_detail, terminal, virtualization, storage, landing
- `GET /health` — sağlık kontrolü
- `GET /api/license` — lisans bilgisi

### `routes/servers.py`

- Sunucu CRUD + SSH bağlantı yönetimi
- Lisans sunucu limiti kontrolü

### `routes/metrics.py`

- CPU, RAM, disk, süreç, servis, güvenlik metrikleri

### `routes/firewall.py`

- UFW/firewalld durum, etkinleştirme, kural ekleme/silme

### `routes/virtualization.py`

- LXD container listeleme, oluşturma, başlat/durdur/sil, komut çalıştırma

### `routes/commands.py`

- Komut çalıştırma (`execute`)
- Hızlı eylemler (`quick-action`)

### `routes/storage.py`

- RAID protokolleri CRUD
- Depolama durumu

### `routes/market.py`

- 58+ uygulama listesi
- Market kurulum + GitHub API entegrasyonu

### `routes/terminal.py`

- WebSocket terminal olayları (`register_terminal_events()`)

### `routes/monitoring.py`

- Alert kuralları CRUD (eşik değerli alarm tanımlama)
- Alert geçmişi + istatistikler + onaylama
- Webhook yapılandırma CRUD + test gönderimi
- Zamanlanmış görev CRUD + manuel çalıştırma
- Yedekleme profili CRUD + manuel çalıştırma
- Metrik geçmişi ve özet

## Yardımcı Modüller

### `ssh_manager.py`

- SSH bağlantısı aç/kapat
- Bağlantı durumu kontrolü
- Komut çalıştırma
- Erişilebilirlik kontrolü (host/port)

### `server_monitor.py`

- Sistem, CPU, RAM, disk, ağ metrikleri
- Disk: kullanım + SMART sağlık (smartctl); yazılım RAID (mdadm) durumu
- Süreç ve servis bilgileri
- Güvenlik özetleri

### `market_apps.py`

- 58+ market uygulama tanımları (10 kategori)
- Kurulum scripti üretimi

### `firewall_manager.py`

- UFW/firewalld durum tespiti
- Etkinleştirme/devre dışı bırakma
- Kural ekleme/silme

### `virtualization_manager.py`

- LXD uygunluk kontrolü
- Container listeleme
- Oluşturma/başlatma/durdurma/silme
- Container içi komut çalıştırma

### `alert_manager.py`

- Metrik değeri çıkarma (`extract_metric_value()`)
- Koşul operatörleri (>, <, >=, <=, ==, !=)
- Alert kuralı kontrolü + cooldown
- Webhook dağıtımı (Slack, Discord, SMTP e-posta, özel HTTP)
- Metrik snapshot koleksiyonu

### `backup_manager.py`

- SSH üzerinden tar/gzip/bzip2 yedekleme
- Retention politikası (eski yedek silme)
- Cron zamanlama eşleştirme (`_should_run()`)
- Yedek boyutu formatı

### `scheduler.py`

- Threading daemon arka plan scheduler
- 4 periyodik görev: alert check (2dk), metrik (5dk), backup (1dk), task (1dk)
- Cron eşleştirme (`_cron_matches()`)
- Graceful stop (`stop_scheduler()`)

## API Özet Uçlar

## Sayfa Uçları

- `GET /` — Dashboard
- `GET /market` — Uygulama Pazarı
- `GET /server/<server_id>` — Sunucu detay
- `GET /terminal/<server_id>` — Web terminal
- `GET /virtualization` — Sanallaştırma
- `GET /storage` — Depolama
- `GET /landing` — Landing page (ürün tanıtım)
- `GET /health` — Sağlık kontrolü

## Kimlik Doğrulama

- `GET /login` — Giriş sayfası
- `POST /login` — Oturum aç
- `GET /logout` — Oturum kapat
- `GET /register` — Kayıt sayfası
- `POST /register` — Yeni kullanıcı oluştur

## Sunucu Yönetimi

- `GET /api/servers`
- `POST /api/servers`
- `PUT /api/servers/<server_id>`
- `DELETE /api/servers/<server_id>`
- `POST /api/servers/<server_id>/connect`
- `POST /api/servers/<server_id>/disconnect`

## Metrik ve Depolama Uçları

- `GET /api/servers/<server_id>/metrics`
- `GET /api/servers/<server_id>/cpu`
- `GET /api/servers/<server_id>/memory`
- `GET /api/servers/<server_id>/disks`
- `GET /api/servers/<server_id>/storage-status` — disk listesi + RAID (mdadm) durumu
- `GET /api/servers/<server_id>/processes`
- `GET /api/servers/<server_id>/services`
- `GET /api/servers/<server_id>/security`

## Komut ve Hızlı Eylem

- `POST /api/servers/<server_id>/execute`
- `POST /api/servers/<server_id>/quick-action`

## Market

- `GET /api/market/apps`
- `POST /api/market/install`

## Firewall

- `GET /api/servers/<server_id>/firewall/status`
- `POST /api/servers/<server_id>/firewall/enable`
- `POST /api/servers/<server_id>/firewall/disable`
- `POST /api/servers/<server_id>/firewall/rules`
- `DELETE /api/servers/<server_id>/firewall/rules/<rule_index>`

## Sanallaştırma

- `GET /api/servers/<server_id>/vms`
- `GET /api/servers/<server_id>/vms/images`
- `POST /api/servers/<server_id>/vms`
- `POST /api/servers/<server_id>/vms/<name>/start`
- `POST /api/servers/<server_id>/vms/<name>/stop`
- `DELETE /api/servers/<server_id>/vms/<name>`
- `POST /api/servers/<server_id>/vms/<name>/exec`

## RAID Protokolleri

- `GET /api/raid-protocols`
- `POST /api/raid-protocols`
- `PUT /api/raid-protocols/<protocol_id>`
- `DELETE /api/raid-protocols/<protocol_id>`

## Socket Olayları

- `terminal_connect`
- `terminal_input`

## Lisans

- `GET /api/license` — Aktif lisans bilgisi

## Monitoring ve Otomasyon

### Alert Kuralları
- `GET /api/alerts/rules` — Tüm alarm kurallarını listele
- `POST /api/alerts/rules` — Yeni alarm kuralı oluştur
- `PUT /api/alerts/rules/<id>` — Alarm kuralı güncelle
- `DELETE /api/alerts/rules/<id>` — Alarm kuralı sil

### Alert Geçmişi
- `GET /api/alerts/history` — Alarm geçmişi (son 100)
- `POST /api/alerts/history/<id>/acknowledge` — Alarmı onayla
- `GET /api/alerts/stats` — Son 24 saat alarm istatistikleri

### Webhook Yapılandırma
- `GET /api/webhooks` — Webhook listesi
- `POST /api/webhooks` — Yeni webhook oluştur
- `PUT /api/webhooks/<id>` — Webhook güncelle
- `DELETE /api/webhooks/<id>` — Webhook sil
- `POST /api/webhooks/<id>/test` — Test bildirimi gönder

### Zamanlanmış Görevler
- `GET /api/tasks` — Görev listesi
- `POST /api/tasks` — Yeni görev oluştur
- `PUT /api/tasks/<id>` — Görev güncelle
- `DELETE /api/tasks/<id>` — Görev sil
- `POST /api/tasks/<id>/run` — Görevi manuel çalıştır

### Yedekleme Profilleri
- `GET /api/backups` — Yedekleme profilleri
- `POST /api/backups` — Yeni profil oluştur
- `PUT /api/backups/<id>` — Profil güncelle
- `DELETE /api/backups/<id>` — Profil sil
- `POST /api/backups/<id>/run` — Yedeği manuel çalıştır

### Metrik Geçmişi
- `GET /api/metrics/history/<server_id>` — Sunucu metrik geçmişi
- `GET /api/metrics/summary` — Tüm sunucular özet

### Genel Bakış
- `GET /api/monitoring/overview` — Dashboard özet verisi

## Güvenlik Notu

Tüm API uçları **session tabanlı kimlik doğrulama** ve **RBAC yetkilendirme** ile korunmaktadır. Her endpoint'in hangi role açık olduğu [RBAC_ENDPOINT_MATRIX.md](RBAC_ENDPOINT_MATRIX.md) dokümanında detaylandırılmıştır. Güvenlik başlıkları (CSP, X-Frame-Options, HSTS) `core/middleware.py` tarafından otomatik eklenir.
