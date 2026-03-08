# 🧠 EmareCloud — Proje Hafıza Dosyası

> 🔗 **Ortak Hafıza:** [`EMARE_ORTAK_HAFIZA.md`](/Users/emre/Desktop/Emare/EMARE_ORTAK_HAFIZA.md) — Tüm Emare ekosistemi, sunucu bilgileri, standartlar ve proje envanteri için bak.


> **Son Güncelleme:** 8 Mart 2026  
> **Versiyon:** v1.1.0 — Multi-Tenant Edition  
> **Durum:** 37/37 özellik + Multi-Tenant izolasyonu tamamlandı, production'da çalışıyor (185.189.54.107)  
> **Bu dosya yazılımın tüm detaylarını içerir. Nerede kaldığımızı ve ne yaptığımızı unutmamak için referans dosyasıdır.**

---

## 📋 İÇİNDEKİLER

1. [Proje Nedir?](#1-proje-nedir)
2. [Teknoloji Yığını](#2-teknoloji-yığını)
3. [Sunucu & Deploy Bilgileri](#3-sunucu--deploy-bilgileri)
4. [Mimari Yapı](#4-mimari-yapı)
5. [Veritabanı Modelleri](#5-veritabanı-modelleri)
6. [Tüm API Endpoint'leri](#6-tüm-api-endpointleri)
7. [Sayfa Route'ları (UI)](#7-sayfa-routeları-ui)
8. [Destek Modülleri](#8-destek-modülleri)
9. [Blueprint Listesi](#9-blueprint-listesi)
10. [Şablon (Template) Dosyaları](#10-şablon-template-dosyaları)
11. [RBAC — Rol ve Yetki Sistemi](#11-rbac--rol-ve-yetki-sistemi)
12. [Güvenlik Katmanları](#12-güvenlik-katmanları)
13. [Blockchain & EmareToken Ekosistemi](#13-blockchain--emaretoken-ekosistemi)
14. [Cloudflare Entegrasyonu](#14-cloudflare-entegrasyonu)
15. [Dosya Yapısı](#15-dosya-yapısı)
16. [Ortam Değişkenleri (.env)](#16-ortam-değişkenleri-env)
17. [Tamamlanan 37 Özellik](#17-tamamlanan-37-özellik)
18. [Aktif Çalışma Durumu — Nerede Kaldık?](#18-aktif-çalışma-durumu--nerede-kaldık)
19. [Bekleyen İşler](#19-bekleyen-işler)
20. [Diğer Sunucular & Altyapı](#20-diğer-sunucular--altyapı)
21. [Deploy Prosedürü](#21-deploy-prosedürü)
22. [Faydalı Komutlar](#22-faydalı-komutlar)

---

## 1. Proje Nedir?

**EmareCloud**, multi-tenant, güvenli ve ölçeklenebilir bir **Altyapı Yönetim Paneli** (Infrastructure Management Panel) yazılımıdır.

### Ne Yapar?
- Uzak sunucuları SSH üzerinden merkezi olarak yönetir
- Web tabanlı terminal erişimi sağlar (SocketIO + xterm.js)
- CPU, RAM, disk, ağ metriklerini gerçek zamanlı izler
- Firewall (UFW/firewalld) yönetimi yapar
- LXD container (sanal makine) yönetimi sağlar
- 42+ uygulama içeren marketplace ile tek tıkla kurulum yapar
- GitHub entegrasyonu ile repo arama/kurulumu destekler
- Otomatik yedekleme, zamanlama ve alarm sistemi içerir
- Cloudflare DNS, SSL, Cache, WAF, Analytics yönetimi yapar
- Blockchain tabanlı EmareToken (EMR) ödül sistemi sunar
- Multi-tenant organizasyon yapısı ile çoklu müşteri desteği verir
- RSA lisans sistemi ile plan bazlı kısıtlama yapar
- AI destekli 20+ akıllı modül sayfası içerir

### Hedef Kitle
- Sistem yöneticileri
- DevOps mühendisleri
- Hosting/cloud hizmeti sunan şirketler
- Birden fazla sunucu yöneten ekipler

---

## 2. Teknoloji Yığını

### Backend
| Teknoloji | Versiyon | Kullanım |
|-----------|----------|----------|
| **Python** | 3.11 | Ana programlama dili |
| **Flask** | 3.0.0 | Web framework |
| **Flask-SQLAlchemy** | 3.1.1 | ORM — veritabanı |
| **Flask-Login** | 0.6.3 | Oturum yönetimi |
| **Flask-SocketIO** | 5.3.6 | WebSocket (terminal) |
| **Paramiko** | 3.4.0 | SSH bağlantıları |
| **Gunicorn** | 21.2.0 | WSGI sunucu |
| **gevent** | 24.2.1 | Async worker |
| **gevent-websocket** | 0.10.1 | WebSocket desteği |
| **cryptography** | 41.0.7 | AES-256-GCM şifreleme |
| **psutil** | 5.9.7 | Sistem bilgileri |
| **pyotp** | 2.9.0 | 2FA (TOTP) |
| **qrcode** | 8.2 | 2FA QR kodu |
| **requests** | — | Cloudflare API HTTP çağrıları |

### Frontend
| Teknoloji | Kullanım |
|-----------|----------|
| **Jinja2** | Template engine (Flask entegre) |
| **Tailwind CSS** | UI framework (CDN) |
| **Alpine.js** | Reaktif JS micro-framework |
| **Chart.js** | Grafik/chart |
| **xterm.js** | Web terminal emülatörü |
| **Lucide Icons** | İkon seti |
| **Vanilla JS** | fetch() tabanlı API çağrıları |

### Veritabanı
- **SQLite** — `instance/emarecloud.db` (varsayılan)
- PostgreSQL/MySQL desteği `DATABASE_URL` env ile

### Deployment
- **Gunicorn** + **GeventWebSocketWorker** (production)
- **Docker** desteği (Dockerfile + docker-compose.yml)
- **systemd** service olarak çalışıyor (production sunucuda)
- **Nginx** reverse proxy (port 80 → 5555)

---

## 3. Sunucu & Deploy Bilgileri

### 🟢 Ana Production Sunucu (EmareCloud Panel)
| Bilgi | Değer |
|-------|-------|
| **IP** | `185.189.54.104` |
| **OS** | AlmaLinux 9.6 |
| **SSH** | `root` / `Emre2025!` |
| **Panel URL** | `http://185.189.54.104` |
| **Uygulama Yolu** | `/opt/emarecloud/` |
| **Venv** | `/opt/emarecloud/venv/` |
| **Servis** | `systemctl restart emarecloud` |
| **Port** | Gunicorn: `127.0.0.1:5555`, Nginx: `80` |
| **Veritabanı** | `/opt/emarecloud/instance/emarecloud.db` |
| **Master Key** | `/opt/emarecloud/.master.key` |
| **Env Dosyası** | `/opt/emarecloud/.env` |
| **Nginx Config** | `/etc/nginx/conf.d/emarecloud.conf` |

### Cloudflare Bilgileri (emarecloud.tr)
| Bilgi | Değer |
|-------|-------|
| **Domain** | `emarecloud.tr` |
| **Zone ID** | `a72e4fe4787b786fb91d41a3491949eb` |
| **Plan** | Free |
| **API Token** | `YSaZrmVvW07MDCEwJSPJNeYKXVUrpK1lykaLDSQ9` |
| **Token Yetkileri** | DNS edit, Zone Settings edit, SSL edit, Cache Purge, WAF edit, Analytics read, Page Rules edit |

### 🟡 Asistan Sunucu (77.92.152.3)
| Bilgi | Değer |
|-------|-------|
| **IP** | `77.92.152.3` (Firewall/NAT) |
| **Dahili IP** | `10.10.4.4` (asistan VM) |
| **OS** | Ubuntu 24.04 |
| **SSH** | `root` / `Emre2025*` |
| **Web Sunucu** | Nginx + Uvicorn (port 8000) |
| **SSL** | Cloudflare Origin sertifikaları (`/etc/ssl/cloudflare/`) |
| **DNS** | `asistan.emarecloud.tr` → Cloudflare Proxied |
| **NAT Port Forwarding** | :22→10.10.4.4:22, :443→10.10.4.4:443, :8000→10.10.4.4:8000, :3100→10.10.4.4:3100, :2222→10.10.4.3:22, :3000→10.10.4.3:3000 |
| **Eksik NAT Kuralı** | Port 80 forwarding YOK |

### 🔴 Yeni Oracle X6-2 Sunucu (Kurulum Aşamasında)
| Bilgi | Değer |
|-------|-------|
| **Donanım** | Oracle Sun Server X6-2 |
| **CPU** | 2x Intel Xeon E5-2690 V4 (28 Core / 56 Thread) |
| **RAM** | 64 GB DDR4 ECC |
| **Disk** | 2x 600GB SAS |
| **Ağ** | 4x 10GbE |
| **Planlanan OS** | AlmaLinux 10 Minimal (x86_64) |
| **Durum** | GRUB hatası — UEFI/Legacy BIOS mismatch |
| **Amaç** | EmareCloud + KVM sanallaştırma |

---

## 4. Mimari Yapı

```
┌─────────────────────────────────────────────────┐
│                    Nginx (port 80)               │
│              Reverse Proxy + SSL                 │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│          Gunicorn + GeventWebSocketWorker         │
│              (127.0.0.1:5555)                    │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│              Flask Application (app.py)           │
│                                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────┐ │
│  │ Auth + RBAC │  │  14 Blueprint │  │ SocketIO│ │
│  │ 2FA (TOTP)  │  │  (API Routes) │  │Terminal │ │
│  └─────────────┘  └──────────────┘  └─────────┘ │
│                                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────┐ │
│  │ Middleware   │  │ Multi-Tenant │  │Scheduler│ │
│  │ gzip+headers│  │  Isolation   │  │ Cron    │ │
│  └─────────────┘  └──────────────┘  └─────────┘ │
│                                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────┐ │
│  │ SSH Manager │  │Server Monitor│  │ Crypto  │ │
│  │ Paramiko    │  │ Metrics      │  │AES-256  │ │
│  └─────────────┘  └──────────────┘  └─────────┘ │
│                                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────┐ │
│  │ Blockchain  │  │ Marketplace  │  │Cloudflare│
│  │ EmareToken  │  │ 42+ Apps     │  │API Proxy│ │
│  └─────────────┘  └──────────────┘  └─────────┘ │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│              SQLite / PostgreSQL                   │
│           instance/emarecloud.db                  │
└───────────────────────────────────────────────────┘
```

### İstek Akışı
1. Kullanıcı → Nginx (port 80)
2. Nginx → Gunicorn (127.0.0.1:5555)
3. Gunicorn → Flask app
4. `before_request`: CSRF token, API token auth, tenant middleware
5. Route handler çalışır (RBAC kontrolü)
6. SSH Manager üzerinden uzak sunucuya bağlanır (gerekirse)
7. Response → `after_request`: gzip + security headers
8. Kullanıcıya cevap döner

---

## 5. Veritabanı Modelleri

### Tablo Listesi (16 model)

| Model | Tablo | Açıklama |
|-------|-------|----------|
| `Organization` | `organizations` | Multi-tenant organizasyon (müşteri) |
| `Plan` | `plans` | Fiyatlandırma planları (Community, Professional, Enterprise, Reseller) |
| `Subscription` | `subscriptions` | Organizasyon aboneliği (plan + süre + ödeme) |
| `ResourceQuota` | `resource_quotas` | Organizasyon kaynak kotaları (sunucu, kullanıcı, disk limitleri) |
| `User` | `users` | Kullanıcılar (username, email, password_hash, role, totp, org_id) |
| `AuditLog` | `audit_logs` | Denetim günlüğü (kim, ne yaptı, ne zaman, başarılı mı) |
| `ServerCredential` | `server_credentials` | Sunucu SSH bilgileri (host, port, şifreli password, SSH key) |
| `ApiToken` | `api_tokens` | API token'ları (Bearer auth, SHA-256 hash) |
| `AppSetting` | `app_settings` | Uygulama ayarları (key-value JSON) |
| `AlertRule` | `alert_rules` | Alarm kuralları (CPU>90%, RAM>80% vb.) |
| `AlertHistory` | `alert_history` | Tetiklenen alarm geçmişi |
| `WebhookConfig` | `webhook_configs` | Bildirim kanalları (Slack, Discord, Email, Custom) |
| `ScheduledTask` | `scheduled_tasks` | Zamanlanmış görevler (cron job yönetimi) |
| `BackupProfile` | `backup_profiles` | Otomatik yedekleme profilleri |
| `MetricSnapshot` | `metric_snapshots` | Periyodik metrik kaydı (trend analizi) |
| `UserWallet` | `user_wallets` | Blockchain cüzdan adresleri (0x... EVM) |
| `EmarePoint` | `emare_points` | EP (Emare Puanı) kazanım kayıtları |
| `TokenTransaction` | `token_transactions` | Blockchain işlem kayıtları (claim, transfer, purchase) |

### Kullanıcı Rolleri
- `super_admin` — Tam yetki (level 100)
- `admin` — Sunucu + kullanıcı yönetimi (level 75)
- `operator` — Komut çalıştırma, servis yönetimi (level 50)
- `read_only` — Sadece görüntüleme (level 10)

### Şifre Güvenliği
- Kullanıcı şifreleri: `scrypt` hash
- SSH sunucu şifreleri: `AES-256-GCM` şifreleme (master key ile)
- Master key: `.master.key` dosyası veya `MASTER_KEY` env
- 2FA: TOTP (Google Authenticator uyumlu) + 8 recovery code

---

## 6. Tüm API Endpoint'leri

### Auth (auth_routes.py — `auth_bp`)
| Method | URL | Açıklama |
|--------|-----|----------|
| GET/POST | `/login` | Giriş sayfası + doğrulama |
| GET/POST | `/verify-2fa` | 2FA doğrulama |
| GET | `/logout` | Çıkış |
| GET/POST | `/change-password` | Şifre değiştirme |
| GET | `/admin/users` | Kullanıcı yönetimi sayfası |
| POST | `/api/users` | Kullanıcı oluştur |
| PUT | `/api/users/<id>` | Kullanıcı güncelle |
| DELETE | `/api/users/<id>` | Kullanıcı sil |
| POST | `/api/users/<id>/reset-password` | Şifre sıfırla |
| GET | `/admin/audit` | Denetim günlüğü sayfası |
| GET | `/api/audit/logs` | Denetim logları (filtrelenebilir) |
| POST | `/api/2fa/setup` | 2FA kurulumu başlat (QR kodu) |
| POST | `/api/2fa/verify-setup` | 2FA doğrulama + aktifleştirme |
| POST | `/api/2fa/disable` | 2FA devre dışı bırak |
| GET | `/api/api-tokens` | API token listesi |
| POST | `/api/api-tokens` | Yeni API token oluştur |
| DELETE | `/api/api-tokens/<id>` | API token sil |

### Sunucular (routes/servers.py — `servers_bp`)
| Method | URL | Açıklama |
|--------|-----|----------|
| GET | `/api/servers` | Sunucu listesi (paralel erişilebilirlik kontrolü) |
| POST | `/api/servers` | Sunucu ekle (lisans limiti kontrolü) |
| DELETE | `/api/servers/<id>` | Sunucu sil |
| PUT | `/api/servers/<id>` | Sunucu güncelle |
| POST | `/api/servers/<id>/connect` | SSH bağlantısı kur |
| POST | `/api/servers/<id>/disconnect` | SSH bağlantısını kes |

### Komutlar (routes/commands.py — `commands_bp`)
| Method | URL | Açıklama |
|--------|-----|----------|
| POST | `/api/servers/<id>/execute` | Komut çalıştır (güvenlik kontrolü) |
| POST | `/api/servers/<id>/quick-action` | Hızlı aksiyon (reboot, update, restart vb.) |

### Firewall (routes/firewall.py — `firewall_bp`)
| Method | URL | Açıklama |
|--------|-----|----------|
| GET | `/api/servers/<id>/firewall/status` | Firewall durumu |
| POST | `/api/servers/<id>/firewall/enable` | Firewall aç |
| POST | `/api/servers/<id>/firewall/disable` | Firewall kapat |
| POST | `/api/servers/<id>/firewall/rules` | Kural ekle |
| DELETE | `/api/servers/<id>/firewall/rules/<idx>` | Kural sil |

### Marketplace (routes/market.py — `market_bp`)
| Method | URL | Açıklama |
|--------|-----|----------|
| GET | `/api/market/apps` | Uygulama kataloğu (42+ app) |
| POST | `/api/market/install` | Uygulama kur |
| GET | `/api/market/stacks` | Stack paketleri listele |
| GET | `/api/market/stacks/<id>` | Stack detayı |
| POST | `/api/market/stack/install` | Stack toplu kur |
| GET | `/api/market/github/search` | GitHub repo ara |
| GET | `/api/market/github/trending` | GitHub trending |
| GET | `/api/market/github/readme` | GitHub README çek |
| POST | `/api/market/github/install` | GitHub repo kur |

### Metrikler (routes/metrics.py — `metrics_bp`)
| Method | URL | Açıklama |
|--------|-----|----------|
| GET | `/api/servers/<id>/metrics` | Tüm metrikler |
| GET | `/api/servers/<id>/cpu` | CPU bilgisi |
| GET | `/api/servers/<id>/memory` | RAM bilgisi |
| GET | `/api/servers/<id>/disks` | Disk bilgisi (SMART) |
| GET | `/api/servers/<id>/processes` | İşlem listesi |
| GET | `/api/servers/<id>/services` | Servis durumları |
| GET | `/api/servers/<id>/security` | Güvenlik bilgisi |

### Monitoring (routes/monitoring.py — `monitoring_bp`)
| Method | URL | Açıklama |
|--------|-----|----------|
| GET | `/api/alerts/rules` | Alarm kuralları listele |
| POST | `/api/alerts/rules` | Alarm kuralı oluştur |
| PUT | `/api/alerts/rules/<id>` | Alarm kuralı güncelle |
| DELETE | `/api/alerts/rules/<id>` | Alarm kuralı sil |
| GET | `/api/alerts/history` | Alarm geçmişi |
| POST | `/api/alerts/history/<id>/acknowledge` | Alarmı onayla |
| GET | `/api/alerts/stats` | Alarm istatistikleri |
| GET/POST/PUT/DELETE | `/api/webhooks[/<id>]` | Webhook CRUD |
| POST | `/api/webhooks/<id>/test` | Test bildirimi gönder |
| GET/POST/PUT/DELETE | `/api/tasks[/<id>]` | Zamanlanmış görev CRUD |
| POST | `/api/tasks/<id>/run` | Görevi hemen çalıştır |
| GET/POST/PUT/DELETE | `/api/backups[/<id>]` | Yedekleme profili CRUD |
| POST | `/api/backups/<id>/run` | Yedeklemeyi hemen çalıştır |
| GET | `/api/metrics/history/<id>` | Metrik geçmişi (720 saat) |
| GET | `/api/metrics/summary` | Tüm sunucuların son metrikleri |
| GET | `/api/monitoring/overview` | Dashboard özeti |

### Organizasyonlar (routes/organizations.py — `org_bp`)
| Method | URL | Açıklama |
|--------|-----|----------|
| GET | `/api/organizations` | Organizasyon listesi |
| POST | `/api/organizations` | Organizasyon oluştur |
| GET | `/api/organizations/<id>` | Organizasyon detayı |
| PUT | `/api/organizations/<id>` | Organizasyon güncelle |
| DELETE | `/api/organizations/<id>` | Organizasyon sil |
| GET | `/api/organizations/<id>/members` | Üye listesi |
| POST | `/api/organizations/<id>/members` | Üye ekle |
| DELETE | `/api/organizations/<id>/members/<uid>` | Üye çıkar |
| GET | `/api/plans` | Plan listesi (herkes görebilir) |
| GET | `/api/organizations/<id>/subscription` | Abonelik bilgisi |
| PUT | `/api/organizations/<id>/subscription` | Plan değiştir |

### Storage (routes/storage.py — `storage_bp`)
| Method | URL | Açıklama |
|--------|-----|----------|
| GET | `/api/raid-protocols` | RAID protokolleri |
| POST | `/api/raid-protocols` | RAID protokolü oluştur |
| PUT | `/api/raid-protocols/<id>` | RAID protokolü güncelle |
| DELETE | `/api/raid-protocols/<id>` | RAID protokolü sil |
| GET | `/api/servers/<id>/storage-status` | Disk + RAID durumu |

### Terminal (routes/terminal.py — `terminal_bp`)
SocketIO event tabanlı:
| Event | Yön | Açıklama |
|-------|-----|----------|
| `terminal_connect` | → Server | SSH bağlantısı kur |
| `terminal_input` | → Server | Komut çalıştır (güvenlik kontrolü) |
| `terminal_output` | ← Client | Komut çıktısı |
| `watch_start` | → Server | Canlı izleme başlat (1-60s) |
| `watch_stop` | → Server | Canlı izleme durdur |
| `watch_output` | ← Client | Periyodik çıktı |
| `ai_assist` | → Server | AI asistanına soru sor |
| `ai_quick_prompts` | → Server | AI prompt şablonları |

### Token / Blockchain (routes/token.py — `token_bp`)
| Method | URL | Açıklama |
|--------|-----|----------|
| GET | `/api/token/info` | EMR token bilgisi |
| GET | `/api/token/balance` | Kullanıcı token bakiyesi |
| POST | `/api/wallet/connect` | Cüzdan bağla |
| POST | `/api/wallet/disconnect` | Cüzdan ayır |
| GET | `/api/wallet/list` | Cüzdan listesi |
| GET | `/api/ep/summary` | EP özeti |
| GET | `/api/ep/history` | EP geçmişi |
| GET | `/api/reward-pool/info` | RewardPool bilgisi |
| GET | `/api/reward-pool/user` | On-chain ödül bilgisi |
| GET | `/api/token-marketplace/stats` | Marketplace istatistikleri |
| GET | `/api/token-marketplace/product/<id>` | Ürün detayı |
| GET | `/api/settlement/order/<id>` | Escrow sipariş durumu |
| GET | `/api/settlement/stats` | Settlement istatistikleri |
| GET | `/api/admin/blockchain/status` | Blockchain entegrasyon durumu |

### Sanallaştırma (routes/virtualization.py — `vms_bp`)
| Method | URL | Açıklama |
|--------|-----|----------|
| GET | `/api/servers/<id>/vms` | LXD container listesi |
| GET | `/api/servers/<id>/vms/images` | Kullanılabilir imajlar |
| POST | `/api/servers/<id>/vms` | Container oluştur |
| POST | `/api/servers/<id>/vms/<name>/start` | Container başlat |
| POST | `/api/servers/<id>/vms/<name>/stop` | Container durdur |
| DELETE | `/api/servers/<id>/vms/<name>` | Container sil |
| POST | `/api/servers/<id>/vms/<name>/exec` | Container içinde komut çalıştır |

### Cloudflare (routes/cloudflare.py — `cloudflare_bp`)
| Method | URL | Açıklama |
|--------|-----|----------|
| POST | `/api/cloudflare/verify` | API token doğrula |
| POST | `/api/cloudflare/zones` | Zone listesi |
| POST | `/api/cloudflare/dns` | DNS kayıtları |
| POST | `/api/cloudflare/dns/create` | DNS kaydı oluştur |
| PUT | `/api/cloudflare/dns/update` | DNS kaydı güncelle |
| DELETE | `/api/cloudflare/dns/delete` | DNS kaydı sil |
| POST | `/api/cloudflare/ssl` | SSL modu + sertifika bilgisi |
| PATCH | `/api/cloudflare/ssl/mode` | SSL modu değiştir |
| POST | `/api/cloudflare/cache/purge` | Cache temizle |
| POST | `/api/cloudflare/cache/settings` | Cache ayarları |
| PATCH | `/api/cloudflare/cache/settings/update` | Cache ayarı güncelle |
| PATCH | `/api/cloudflare/dev-mode` | Development modu aç/kapa |
| POST | `/api/cloudflare/firewall/rules` | WAF kuralları |
| POST | `/api/cloudflare/firewall/rules/create` | WAF kuralı ekle |
| DELETE | `/api/cloudflare/firewall/rules/delete` | WAF kuralı sil |
| PATCH | `/api/cloudflare/firewall/rules/toggle` | WAF kuralı aç/kapa |
| POST | `/api/cloudflare/analytics` | Zone analitikleri |
| POST | `/api/cloudflare/pagerules` | Page rule listesi |
| POST | `/api/cloudflare/pagerules/create` | Page rule oluştur |
| DELETE | `/api/cloudflare/pagerules/delete` | Page rule sil |
| POST | `/api/cloudflare/settings` | Zone ayarları |
| PATCH | `/api/cloudflare/settings/update` | Zone ayarı güncelle |

---

## 7. Sayfa Route'ları (UI)

### Ana Sayfalar
| URL | Sayfa |
|-----|-------|
| `/landing` | Marketing landing page |
| `/` | Dashboard (giriş sonrası ana sayfa) |
| `/login` | Giriş sayfası |
| `/market` | Marketplace |
| `/monitoring` | Monitoring dashboard |
| `/virtualization` | Sanallaştırma yönetimi |
| `/storage` | Depolama yönetimi |
| `/cloudflare` | Cloudflare DNS & CDN |
| `/server/<id>` | Sunucu detay sayfası |
| `/terminal/<id>` | Web terminal |
| `/admin/users` | Kullanıcı yönetimi |
| `/admin/audit` | Denetim günlüğü |
| `/server-map` | Sunucu haritası (görsel mimari) |

### AI Modül Sayfaları (20+)
| URL | Sayfa |
|-----|-------|
| `/app-builder` | No-Code AI App Builder |
| `/ai-wizard` | AI Use-Case Wizard |
| `/ai-cost` | AI Cost Forecasting |
| `/ai-logs` | AI Log Intelligence |
| `/ai-revenue` | AI Revenue Sharing Dashboard |
| `/ai-server-recommend` | AI Server Recommendation |
| `/ai-performance` | AI Model Performance Score |
| `/ai-security` | AI Security & Compliance |
| `/ai-optimizer` | Auto AI Resource Optimizer |
| `/ai-marketplace` | AI Model Marketplace |
| `/ai-saas-builder` | One-Click AI SaaS Builder |
| `/ai-gpu-pool` | AI Auto-Scaling GPU Pool |
| `/ai-whitelabel` | White-Label AI Platform |
| `/ai-community-templates` | Community AI Templates |
| `/ai-training` | AI Model Training Lab |
| `/ai-orchestrator` | Multi-AI Model Orchestrator |
| `/ai-backup` | AI-Based Auto Backup |
| `/ai-isolation` | Multi-Tenant Isolation Guard |
| `/ai-migration` | Zero-Downtime Migration |
| `/ai-voice` | Voice-Controlled AI Admin |
| `/ai-market-intel` | AI Marketplace Intelligence |
| `/ai-self-healing` | Self-Healing AI Infrastructure |
| `/ai-landing-gen` | AI Landing Page Generator |
| `/ai-cross-cloud` | Cross-Cloud AI Sync |
| `/ai-ethics` | AI Ethics & Bias Auditor |
| `/ai-mastery` | Gamified AI Mastery Path |
| `/ai-sandbox` | Instant AI Demo Sandbox |

---

## 8. Destek Modülleri

### ssh_manager.py
SSH bağlantı havuzu yönetimi. Paramiko kullanarak uzak sunuculara bağlanır. RSA 4096 key pair otomatik oluşturur, ilk parola ile bağlanıldığında SSH key'i sunucuya deploy eder. Thread-safe connection pool.
- Sınıf: `SSHManager` — `.connect()`, `.disconnect()`, `.execute_command()`, `.is_connected()`, `.check_server_reachable()`

### server_monitor.py
SSH üzerinden sunucu metrikleri toplar — CPU, RAM, disk (SMART health), işlemler, servisler, ağ, uptime, güvenlik. Tek SSH çağrısında birden fazla sistem sorgusunu birleştirir.
- Sınıf: `ServerMonitor` — `.get_all_metrics()`, `.get_cpu_info()`, `.get_memory_info()`, `.get_disk_info()`, `.get_raid_status()`

### firewall_manager.py
UFW (Ubuntu/Debian) veya firewalld (RHEL/CentOS) otomatik algılar. Birleşik arayüz: durum, aç, kapa, kural ekle, kural sil.

### backup_manager.py
SSH tabanlı otomatik yedekleme. tar + gzip/bzip2 sıkıştırma. Retention tabanlı eski yedek temizleme. Cron-like zamanlama.

### alert_manager.py
Eşik tabanlı alarm motoru. Slack, Discord, Email (SMTP), Custom webhook bildirimleri. Cooldown mekanizması.

### market_apps.py
42+ uygulama kataloğu: veritabanları, web sunucuları, CMS, AI araçları, DevOps. Çoklu distro kurulum scriptleri (apt, dnf, yum, zypper, apk). Stack paketleri. GitHub entegrasyonu.

### virtualization_manager.py
LXD container yönetimi: liste, oluştur, başlat, durdur, sil, içinde komut çalıştır. CPU/RAM limitleri desteği.

### command_security.py
Rol bazlı komut filtreleme. Fork bomb, disk overwrite, reverse shell engelleme. Operatör/admin allowlist. Super admin tam erişim (bloklu komutlar hariç).

### license_manager.py
RSA imzalı JSON lisans doğrulama. Süre kontrolü, sunucu sayısı limiti. Geçerli lisans yoksa Community planı (3 sunucu).

### crypto.py
AES-256-GCM şifreleme/çözme. Master key'i env veya `.master.key` dosyasından alır. SSH sunucu şifrelerini güvenli saklar.

### core/middleware.py
Gzip sıkıştırma (>500 byte, level 6) ve güvenlik header'ları (X-Content-Type-Options, X-XSS-Protection, Referrer-Policy, X-Frame-Options, Cache-Control).

### core/tenant.py
Multi-tenant izolasyon middleware. Organizasyon bazlı veri filtreleme. Super admin global erişim, normal kullanıcılar kendi org'larıyla sınırlı. Kota kontrolü.

### core/logging_config.py
Production: JSON formatında, RotatingFileHandler (10MB, 5 backup). Development: renkli, okunabilir format. Per-request access logging.

### core/helpers.py
Paylaşılan `ssh_mgr` (SSHManager) ve `monitor` (ServerMonitor) instance'ları. Sunucu lookup, sidebar verileri, paralel erişilebilirlik kontrolü.

### core/database.py
Veritabanı oluşturma, varsayılan admin oluşturma, config.json'dan veri migrasyon, varsayılan planlar ve organizasyon oluşturma.

### core/config_io.py
config.json dosyası okuma/yazma yardımcıları.

### scheduler.py
Arka plan zamanlayıcı. Threading tabanlı. 5dk'da bir metrik toplama, 2dk'da bir alarm kontrolü, 1dk'da bir yedekleme ve görev kontrolü.

### audit.py
Denetim günlüğü kayıt fonksiyonu. `log_action()` — her önemli işlemi kaydeder.

---

## 9. Blueprint Listesi

Flask uygulaması 14 blueprint ile çalışır:

| # | Blueprint | Dosya | Açıklama |
|---|-----------|-------|----------|
| 1 | `auth_bp` | `auth_routes.py` | Kimlik doğrulama, kullanıcı yönetimi, 2FA, API token |
| 2 | `pages_bp` | `routes/pages.py` | Sayfa render'ları, dashboard, AI modülleri |
| 3 | `servers_bp` | `routes/servers.py` | Sunucu CRUD |
| 4 | `metrics_bp` | `routes/metrics.py` | Sunucu metrikleri |
| 5 | `firewall_bp` | `routes/firewall.py` | Firewall yönetimi |
| 6 | `vms_bp` | `routes/virtualization.py` | Sanallaştırma (LXD) |
| 7 | `commands_bp` | `routes/commands.py` | Komut çalıştırma |
| 8 | `storage_bp` | `routes/storage.py` | RAID/storage |
| 9 | `market_bp` | `routes/market.py` | Marketplace |
| 10 | `terminal_bp` | `routes/terminal.py` | Web terminal (SocketIO) |
| 11 | `monitoring_bp` | `routes/monitoring.py` | Monitoring, alarm, webhook, backup, task |
| 12 | `org_bp` | `routes/organizations.py` | Organizasyon, plan, abonelik |
| 13 | `token_bp` | `routes/token.py` | Blockchain, token, cüzdan, EP |
| 14 | `cloudflare_bp` | `routes/cloudflare.py` | Cloudflare API proxy |

---

## 10. Şablon (Template) Dosyaları

```
templates/
├── base.html              ← Ana layout (sidebar, navbar, scripts)
├── dashboard.html         ← Ana dashboard
├── landing.html           ← Marketing sayfası
├── market.html            ← Marketplace UI
├── monitoring.html        ← Monitoring dashboard
├── server_detail.html     ← Sunucu detay sayfası
├── storage.html           ← Depolama yönetimi
├── terminal.html          ← Web terminal (xterm.js)
├── virtualization.html    ← Sanallaştırma yönetimi
├── cloudflare.html        ← Cloudflare DNS/CDN yönetimi
├── admin/
│   ├── audit.html         ← Denetim günlüğü
│   └── users.html         ← Kullanıcı yönetimi
└── auth/
    ├── login.html         ← Giriş sayfası
    ├── change_password.html
    └── verify_2fa.html    ← 2FA doğrulama
```

### Statik Dosyalar
```
static/
├── css/
│   └── style.css          ← Ana CSS
└── js/
    └── app.js             ← Ana JavaScript
```

---

## 11. RBAC — Rol ve Yetki Sistemi

### Roller ve Seviyeleri
| Rol | Seviye | Açıklama |
|-----|--------|----------|
| `super_admin` | 100 | Tam yetki — her şeyi yapabilir |
| `admin` | 75 | Sunucu yönetimi, kullanıcı görüntüleme, org yönetimi |
| `operator` | 50 | Komut çalıştırma, servis yönetimi, market kurulum |
| `read_only` | 10 | Sadece görüntüleme |

### Yetki Matrisi (Permissions)
```
super_admin: * (tüm yetkiler)

admin:
  server.view, server.add, server.edit, server.delete,
  server.connect, server.disconnect, server.execute, server.metrics,
  server.quick_action, firewall.view, firewall.manage,
  vm.view, vm.manage, market.view, market.install,
  storage.view, storage.manage, terminal.access,
  user.view, audit.view, raid.view, raid.manage,
  monitoring.view, monitoring.manage,
  org.view, org.manage, org.members, plan.view, token.manage

operator:
  server.view, server.connect, server.disconnect,
  server.execute, server.metrics, server.quick_action,
  firewall.view, vm.view, vm.manage,
  market.view, market.install, storage.view,
  terminal.access, raid.view, monitoring.view,
  org.view, plan.view, token.manage

read_only:
  server.view, server.metrics, firewall.view,
  vm.view, market.view, storage.view,
  raid.view, monitoring.view, org.view, plan.view
```

### Dekoratörler
- `@role_required('super_admin', 'admin')` — Belirtilen rollerden birini zorunlu kılar
- `@permission_required('server.add')` — Belirli bir yetkiyi zorunlu kılar
- `@login_required` — Sadece giriş yapmış olma kontrolü

---

## 12. Güvenlik Katmanları

1. **Kimlik Doğrulama**: Flask-Login + Session + Bearer Token (API)
2. **2FA**: TOTP (Google Authenticator) + 8 Recovery Code
3. **Şifre Politikası**: Min 8 karakter, büyük/küçük harf, rakam, özel karakter
4. **CSRF Koruması**: Her formda `csrf_token` kontrolü
5. **Rate Limiting**: 5 deneme / 5 dakika (brute force koruması)
6. **RBAC**: 4 seviyeli rol tabanlı erişim kontrolü
7. **Komut Güvenliği**: Fork bomb, reverse shell engelleme, rol bazlı allowlist
8. **Şifreleme**: AES-256-GCM (sunucu SSH şifreleri)
9. **Multi-Tenant İzolasyon**: Organizasyon bazlı veri filtreleme
10. **HTTP Güvenlik Header'ları**: X-Content-Type-Options, X-XSS-Protection, X-Frame-Options
11. **Gzip Sıkıştırma**: Response body >500 byte
12. **Denetim Günlüğü**: Tüm önemli işlemler loglanır (IP, user-agent dahil)
13. **SSH Key Auth**: RSA 4096 otomatik key deployment
14. **Lisans Doğrulama**: RSA imzalı JSON lisans

---

## 13. Blockchain & EmareToken Ekosistemi

### Genel Yapı
- **EmareToken (EMR)**: ERC-20 token (BSC — Binance Smart Chain)
- **Chain**: BSC Testnet (97) / BSC Mainnet (56)
- **Web3.py** ile blockchain etkileşimi

### Akıllı Kontratlar (Smart Contracts)
| Kontrat | Açıklama |
|---------|----------|
| **EmareToken** | ERC-20 token — mint, burn, pause, minter role |
| **RewardPool** | Oracle tabanlı ödül dağıtımı — EP → EMR dönüşümü |
| **Marketplace** | On-chain ürün listeleme, satın alma, gelir paylaşımı |
| **Settlement** | Escrow tabanlı sipariş sistemi |

### EP (Emare Points) Sistemi
Kullanıcı aksiyonlarına göre puan kazanımı:
- `server_added` → 50 EP
- `subscription_payment` → 100 EP
- `marketplace_purchase` → cashback EP
- `ai_ops` → EP
- `referral` → EP
- Günlük limit: 5000 EP
- EP'ler birikir → RewardPool üzerinden EMR token'a dönüştürülür

### Emare Token Kontrat Dosyaları
```
Emare Token/emare-token/
├── contracts/         ← Solidity akıllı kontratları
├── scripts/           ← Hardhat deploy scriptleri
├── test/              ← Test dosyaları
├── hardhat.config.ts  ← Hardhat yapılandırması
├── typechain-types/   ← TypeScript type definitions
└── artifacts/         ← Derlenmiş kontrat ABI'leri
```

---

## 14. Cloudflare Entegrasyonu

### Yapı
- `routes/cloudflare.py` (28KB) — Cloudflare API v4 proxy endpointleri
- `templates/cloudflare.html` — Frontend UI (Tailwind + fetch API)
- Tüm istekler backend üzerinden geçer (token güvenliği)

### Desteklenen Özellikler
1. **API Token Doğrulama** — Token bağlan, zone seç
2. **DNS Yönetimi** — A, AAAA, CNAME, MX, TXT, SRV kayıtları CRUD
3. **SSL/TLS** — Mod değiştirme (Off/Flexible/Full/Strict), sertifika bilgisi
4. **Cache** — Tam temizle, URL bazlı temizle, minify, brotli, dev mode
5. **WAF / Firewall** — Kural oluştur/sil/toggle (block, challenge, allow)
6. **Analytics** — İstek sayıları, bant genişliği, tehdiler, sayfa görüntüleme
7. **Page Rules** — URL bazlı kural oluştur/sil
8. **Zone Settings** — Tüm zone ayarları okuma/yazma

### Mevcut Cloudflare DNS Kayıtları (emarecloud.tr)
- `asistan.emarecloud.tr` → A kaydı → `77.92.152.3` (Proxied)

---

## 15. Dosya Yapısı

```
emarecloud/
├── app.py                      ← Ana uygulama (Flask factory)
├── config.py                   ← Yapılandırma sınıfı
├── extensions.py               ← Flask extension'ları (db, login_manager)
├── models.py                   ← 16 veritabanı modeli (863 satır)
├── rbac.py                     ← Rol/yetki matrisi + dekoratörler
├── auth_routes.py              ← Auth blueprint (526 satır)
├── crypto.py                   ← AES-256-GCM şifreleme
├── ssh_manager.py              ← SSH bağlantı havuzu
├── server_monitor.py           ← Sunucu metrik toplama
├── firewall_manager.py         ← UFW/firewalld yönetimi
├── backup_manager.py           ← Otomatik yedekleme
├── alert_manager.py            ← Alarm motoru + webhook
├── market_apps.py              ← 42+ app kataloğu
├── virtualization_manager.py   ← LXD container yönetimi
├── command_security.py         ← Komut filtreleme
├── license_manager.py          ← RSA lisans doğrulama
├── scheduler.py                ← Arka plan zamanlayıcı
├── audit.py                    ← Denetim günlüğü
├── gunicorn.conf.py            ← Gunicorn production config
├── _diag.py                    ← Diagnostik araçlar
├── config.json                 ← Sunucu yapılandırma (legacy)
├── requirements.txt            ← Python bağımlılıkları
├── requirements-dev.txt        ← Geliştirme bağımlılıkları
├── pyproject.toml              ← Proje metadata
├── Dockerfile                  ← Docker imajı
├── docker-compose.yml          ← Docker Compose
├── setup.sh                    ← Kurulum scripti
│
├── core/                       ← Çekirdek modüller
│   ├── __init__.py
│   ├── database.py             ← Veritabanı başlatma
│   ├── middleware.py            ← Gzip + güvenlik header
│   ├── tenant.py               ← Multi-tenant izolasyon
│   ├── logging_config.py       ← Structured logging
│   ├── helpers.py              ← Yardımcı fonksiyonlar
│   └── config_io.py            ← Config dosyası I/O
│
├── routes/                     ← API Blueprint'leri
│   ├── __init__.py             ← Blueprint kayıt fonksiyonu
│   ├── servers.py              ← Sunucu CRUD
│   ├── commands.py             ← Komut çalıştırma
│   ├── firewall.py             ← Firewall yönetimi
│   ├── market.py               ← Marketplace
│   ├── metrics.py              ← Sunucu metrikleri
│   ├── monitoring.py           ← Monitoring, alarm, backup, task
│   ├── organizations.py        ← Organizasyon, plan, abonelik
│   ├── pages.py                ← Sayfa render'ları
│   ├── storage.py              ← RAID/storage
│   ├── terminal.py             ← Web terminal (SocketIO)
│   ├── token.py                ← Blockchain/token
│   ├── virtualization.py       ← LXD container
│   └── cloudflare.py           ← Cloudflare API proxy (28KB)
│
├── blockchain/                 ← Blockchain modülleri
│   ├── __init__.py
│   ├── service.py              ← Web3 servis katmanı
│   ├── reward_engine.py        ← EP ödül motoru
│   └── contracts.py            ← Akıllı kontrat ABI'leri
│
├── templates/                  ← Jinja2 şablonları
│   ├── base.html
│   ├── dashboard.html
│   ├── landing.html
│   ├── market.html
│   ├── monitoring.html
│   ├── server_detail.html
│   ├── storage.html
│   ├── terminal.html
│   ├── virtualization.html
│   ├── cloudflare.html
│   ├── admin/
│   └── auth/
│
├── static/                     ← Statik dosyalar
│   ├── css/style.css
│   └── js/app.js
│
├── tests/                      ← Test dosyaları
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_2fa.py
│   ├── test_api_token.py
│   ├── test_config.py
│   ├── test_market.py
│   ├── test_monitoring.py
│   ├── test_organization.py
│   ├── test_pages.py
│   ├── test_rbac.py
│   └── test_server.py
│
├── instance/                   ← SQLite veritabanı
│   └── emarecloud.db
│
├── Emare Token/                ← Blockchain kontrat projesi
│   └── emare-token/
│       ├── contracts/
│       ├── scripts/
│       ├── test/
│       └── hardhat.config.ts
│
└── docs/                       ← Dokümantasyon
    ├── 00_INDEX.md
    ├── 01_GENEL_BAKIS.md
    ├── 02_KURULUM_VE_HIZLI_BASLANGIC.md
    ├── 03_KULLANIM_REHBERI.md
    ├── 04_API_VE_MODULLER.md
    ├── 05_YAZILIM_GELISTIRME_YOL_HARITASI.md
    ├── AI_ANAYASASI.md
    ├── AI_PLATFORM_TASARIMI.md
    ├── BLOCKCHAIN_ENTEGRASYON.md
    ├── BUSINESS_BUILDER_VIZYON.md
    ├── FATURALANDIRMA_SISTEMI.md
    ├── HOSTING_BUILDER.md
    ├── MULTI_TENANT_MIMARI.md
    ├── MVP_KAPSAM.md
    ├── RBAC_ENDPOINT_MATRIX.md
    ├── REFACTOR_PLANI.md
    └── TLS_REVERSE_PROXY.md
```

---

## 16. Ortam Değişkenleri (.env)

### Temel
| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `SECRET_KEY` | random | Flask secret key |
| `FLASK_ENV` | development | Ortam (development/production) |
| `HOST` | 0.0.0.0 | Dinleme adresi |
| `PORT` | 5555 | Dinleme portu |
| `FLASK_DEBUG` | false | Debug modu |

### Veritabanı
| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `DATABASE_URL` | sqlite:///instance/emarecloud.db | Veritabanı URI |
| `MASTER_KEY` | (otomatik) | AES-256 master key |

### Oturum & Güvenlik
| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `SESSION_LIFETIME_HOURS` | 8 | Oturum süresi |
| `SESSION_COOKIE_SECURE` | false | HTTPS-only cookie |
| `RATE_LIMIT_LOGIN` | 5 | Dakikada max login denemesi |
| `RATE_LIMIT_API` | 60 | Dakikada max API çağrısı |

### SSH
| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `SSH_TIMEOUT` | 10 | SSH bağlantı timeout (saniye) |
| `MAX_CONCURRENT_CONNECTIONS` | 5 | Max eşzamanlı SSH |

### Admin
| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `DEFAULT_ADMIN_USERNAME` | admin | İlk admin kullanıcı adı |
| `DEFAULT_ADMIN_PASSWORD` | — | İlk admin şifresi |
| `DEFAULT_ADMIN_EMAIL` | admin@emarecloud.com | İlk admin e-posta |

### Blockchain
| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `BLOCKCHAIN_ENABLED` | false | Blockchain aktif mi |
| `BLOCKCHAIN_RPC_URL` | — | BSC RPC URL |
| `BLOCKCHAIN_CHAIN_ID` | 97 | BSC chain ID |
| `EMARE_TOKEN_ADDRESS` | — | EMR token kontrat adresi |
| `EMARE_REWARD_POOL_ADDRESS` | — | RewardPool kontrat adresi |
| `EMARE_MARKETPLACE_ADDRESS` | — | Marketplace kontrat adresi |
| `EMARE_SETTLEMENT_ADDRESS` | — | Settlement kontrat adresi |
| `BLOCKCHAIN_ORACLE_PRIVATE_KEY` | — | Oracle private key |

### Cloudflare
| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `CLOUDFLARE_API_TOKEN` | — | Cloudflare API token |
| `CLOUDFLARE_ZONE_ID` | — | Varsayılan zone ID |

### Gunicorn
| Değişken | Varsayılan | Açıklama |
|----------|-----------|----------|
| `GUNICORN_WORKERS` | 2 | Worker sayısı |
| `LOG_LEVEL` | info | Log seviyesi |

---

## 17. Tamamlanan 37 Özellik

### Faz 1 — Temel Özellikler (✅ Tamamlandı)
1. ✅ Flask temel uygulama mimarisi
2. ✅ SQLAlchemy ORM veritabanı
3. ✅ Flask-Login oturum yönetimi
4. ✅ RBAC (4 rol, yetki matrisi, dekoratörler)
5. ✅ AES-256-GCM şifreleme (sunucu şifreleri)
6. ✅ SSH Manager (Paramiko, bağlantı havuzu, key auth)
7. ✅ Sunucu CRUD (ekle, düzenle, sil, bağlan)
8. ✅ Sunucu metrikleri (CPU, RAM, disk, ağ, servisler)
9. ✅ Web terminal (SocketIO + xterm.js)
10. ✅ Firewall yönetimi (UFW/firewalld)
11. ✅ Komut güvenliği (blocklist, allowlist, rol bazlı)
12. ✅ CSRF koruması
13. ✅ Rate limiting (brute force)
14. ✅ HTTP güvenlik header'ları + gzip
15. ✅ Denetim günlüğü (audit log)

### Faz 2 — İleri Özellikler (✅ Tamamlandı)
16. ✅ 2FA (TOTP + recovery codes)
17. ✅ API Token sistemi (Bearer auth, SHA-256)
18. ✅ Marketplace (42+ app, GitHub entegrasyonu, stack'ler)
19. ✅ LXD sanallaştırma yönetimi
20. ✅ RAID/Storage yönetimi
21. ✅ Monitoring dashboard (alarm, webhook, backup, task)
22. ✅ Alarm kuralları (CPU/RAM/disk eşikleri)
23. ✅ Webhook bildirimleri (Slack, Discord, Email, Custom)
24. ✅ Zamanlanmış görevler (cron-style)
25. ✅ Otomatik yedekleme profilleri
26. ✅ Metrik snapshot geçmişi
27. ✅ Multi-tenant organizasyonlar
28. ✅ Plan/abonelik sistemi
29. ✅ Kaynak kotaları
30. ✅ RSA lisans sistemi
31. ✅ Structured logging (JSON + rotating files)
32. ✅ Background scheduler

### Faz 3 — Blockchain & AI (✅ Tamamlandı)
33. ✅ EmareToken ERC-20 akıllı kontratlar (Solidity + Hardhat)
34. ✅ Web3 servis katmanı (RewardPool, Marketplace, Settlement)
35. ✅ EP (Emare Points) ödül sistemi
36. ✅ 20+ AI modül sayfası (landing page'ler)
37. ✅ Cloudflare gerçek API entegrasyonu (DNS, SSL, Cache, WAF, Analytics, Page Rules)

---

## 18. Aktif Çalışma Durumu — Nerede Kaldık?

### Son Durum (8 Mart 2026)

#### ✅ Multi-Tenant İzolasyonu TAMAMLANDI (v1.1.0)
- **65+ lokasyonda** tenant izolasyonu uygulandı
- `core/helpers.py`: `_build_tenant_query(model)` ve `get_server_obj_with_access(server_id)` merkezi fonksiyonlar
- `core/tenant.py`: Request bazlı middleware — `g.tenant_id`, `g.is_global` ayarlar
- `models.py`: AlertRule, WebhookConfig, ScheduledTask, BackupProfile, AuditLog'a `org_id` eklendi
- **Tüm route'lar tenant-aware**: servers, auth, monitoring, metrics, commands, firewall, virtualization, storage, terminal, datacenters, scoreboard, feedback
- `migrate_tenant.py`: Mevcut verileri "Emare" organizasyonuna atama scripti çalıştırıldı
- **Production (107) üzerinde deploy + test edildi, izolasyon onaylandı**

#### Tenant Mimarisi Özet
```
Organization (tablo) → org_id FK → her modelde
Middleware: g.tenant_id = current_user.org_id
Super Admin: is_global=True, org_id scope veya tüm orglar
Normal Kullanıcı: sadece kendi org_id'sine ait verileri görür
```

#### Mevcut Organizasyonlar (107 sunucu)
| ID | İsim | Slug | Açıklama |
|----|------|------|----------|
| 1 | Varsayılan Organizasyon | default | Boş |
| 2 | Emare | emare | Ana org — 4 kullanıcı, 3 sunucu |

#### ✅ Önceden Tamamlanan İşler
- EmareCloud yazılımı 37/37 özellik ile çalışır durumda
- 107 sunucusuna (185.189.54.107) tam deploy: EmareCloud, EmareAPI, emare-dapp, nginx, SSL
- Cloudflare gerçek API entegrasyonu tamamlandı
- emarecloud.tr domain'i 107'ye yönlendirildi
- DC-3 (Google Cloud 34.90.186.48) veritabanı migration tamamlandı
- EmareFirewall standalone paket olarak çıkarıldı
- Dervişler arası mesajlaşma sistemi kuruldu

---

## 19. Bekleyen İşler

### 🔴 Acil (Blocker)
1. [ ] **GitHub push token yenilenmeli** — Mevcut PAT (`github_pat_11BTKMVTY...`) write yetkisi yok, sadece read. GitHub'dan yeni token oluştur (repo write + workflow scope). Hem local hem 107 sunucusunda güncelle.

### 🟡 Kısa Vadeli (Öncelikli)
2. [ ] **İkinci org oluştur + test et** — UI veya API ile "Test Firması" org oluştur, yeni kullanıcı ata, login olup Emare'nin verilerini GÖREMEMESI gerektiğini doğrula
3. [ ] **Org Yönetim Paneli** — Admin UI'da org CRUD sayfası (oluştur/düzenle/sil/üyeleri yönet)
4. [ ] **Kullanıcı-Org atama UI** — Admin panelde kullanıcı düzenlerken org seçimi dropdown
5. [ ] **Org bazlı kaynak kotası** — Plan limitleri (max sunucu, max kullanıcı) dashboard'da göster
6. [ ] **2FA (TOTP) backend** — Google Authenticator entegrasyonu (models.py'de totp_secret zaten var, UI eksik)

### 🟢 Orta Vadeli
7. [ ] **PostgreSQL'e geçiş** — SQLite → PostgreSQL (production DB ölçekleme)
8. [ ] **Docker/Kubernetes deployment** — Containerized deploy
9. [ ] **CI/CD pipeline** — GitHub Actions: lint + test + auto-deploy to 107
10. [ ] **SSL sertifikası iyileştirme** — Let's Encrypt wildcard veya Cloudflare Origin cert
11. [ ] **Oracle X6-2 sunucu** — AlmaLinux kurulumu (UEFI fix) + EmareCloud + KVM
12. [ ] **Blockchain kontratları** — BSC Mainnet'e deploy (EmareToken, NodeReward)
13. [ ] **Port 80 NAT forwarding** — 77.92.152.3:80 → 10.10.4.4:80 (Cloudflare proxy)

### 🔵 Uzun Vadeli (Vizyon)
14. [ ] **AI modülleri gerçek backend** — ai_optimizer, ai_security, ai_backup vb. gerçek implementasyon
15. [ ] **Ödeme sistemi** — Stripe/Iyzico entegrasyonu + plan faturalandırma
16. [ ] **Mobile app** — React Native veya Flutter (EmareCloud mobil)
17. [ ] **Kubernetes cluster yönetimi** — kubectl entegrasyonu
18. [ ] **Prometheus/Grafana** — Harici metrik toplama entegrasyonu
19. [ ] **White-label mode** — Logo, renk, domain, branding müşteri bazlı özelleştirme
20. [ ] **Provider Edition** — Hosting iş kurucu (müşteri CRUD, paket şablonları, faturalandırma)

### 📌 Teknik Borç
- [ ] `EMARE_ORTAK_HAFIZA.md`'de EmareCloud sunucu bilgisi hâlâ 104 → 107 olarak güncellenmeli (symlink, dikkatli düzenleme)
- [ ] Test coverage artırılmalı (mevcut %46 → hedef %70+)
- [ ] routes/deploy.py, routes/webdizayn.py admin-only endpoint'lerde tenant kontrolü (düşük öncelik)
- [ ] AlertHistory modeline org_id eklenebilir (şu an server_id üzerinden filtreleniyor)

---

## 20. Diğer Sunucular & Altyapı

### NAT Firewall Yapısı (77.92.152.3)
```
İnternet → 77.92.152.3 (Firewall/NAT)
    ├── :22   → 10.10.4.4:22    (Asistan SSH)
    ├── :443  → 10.10.4.4:443   (HTTPS)
    ├── :8000 → 10.10.4.4:8000  (Uvicorn/Panel)
    ├── :3100 → 10.10.4.4:3100  (WhatsApp Panel)
    ├── :2222 → 10.10.4.3:22    (SIRRI SSH)
    └── :3000 → 10.10.4.3:3000  (Flora)
```
**Eksik:** :80 → 10.10.4.4:80 (HTTP — Cloudflare proxy için gerekli)

### Dahili VM'ler
| VM | IP | Rol |
|----|-----|-----|
| Asistan | 10.10.4.4 | Web sunucu (nginx + uvicorn) |
| SIRRI | 10.10.4.3 | Flora uygulaması |

---

## 21. Deploy Prosedürü

### Production'a Deploy (185.189.54.107)

```bash
# 1. Dosyaları sunucuya kopyala
scp -r ./* root@185.189.54.107:/tmp/emarecloud_deploy/

# 2. SSH ile bağlan
ssh root@185.189.54.107

# 3. Dosyaları kopyala
cp -r /tmp/emarecloud_deploy/* /opt/emarecloud/

# 4. Cache temizle
find /opt/emarecloud -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null

# 5. Servisi yeniden başlat
systemctl restart emarecloud

# 6. Durum kontrolü
systemctl status emarecloud
curl -s http://localhost:5555/health
```

### Yeni Bağımlılık Eklendiğinde
```bash
ssh root@185.189.54.107
pip3 install <paket_adı>
systemctl restart emarecloud
```

---

## 22. Faydalı Komutlar

### Production Sunucu (185.189.54.107)
```bash
# Servis yönetimi
systemctl restart emarecloud
systemctl status emarecloud
journalctl -u emarecloud -f          # Canlı loglar

# Nginx
nginx -t                              # Config test
systemctl restart nginx

# Veritabanı
sqlite3 /opt/emarecloud/instance/emarecloud.db ".tables"
sqlite3 /opt/emarecloud/instance/emarecloud.db "SELECT * FROM users;"
sqlite3 /opt/emarecloud/instance/emarecloud.db "SELECT id,name,slug FROM organizations;"

# Python (sistem Python3.11)
pip3 install <paket>
systemctl restart emarecloud
```

### Cloudflare API Test
```bash
# Token doğrula
curl -s "https://api.cloudflare.com/client/v4/user/tokens/verify" \
  -H "Authorization: Bearer YSaZrmVvW07MDCEwJSPJNeYKXVUrpK1lykaLDSQ9" | python3 -m json.tool

# Zone listesi
curl -s "https://api.cloudflare.com/client/v4/zones" \
  -H "Authorization: Bearer YSaZrmVvW07MDCEwJSPJNeYKXVUrpK1lykaLDSQ9" | python3 -m json.tool

# DNS kayıtları
curl -s "https://api.cloudflare.com/client/v4/zones/a72e4fe4787b786fb91d41a3491949eb/dns_records" \
  -H "Authorization: Bearer YSaZrmVvW07MDCEwJSPJNeYKXVUrpK1lykaLDSQ9" | python3 -m json.tool
```

### Asistan Sunucu (77.92.152.3)
```bash
ssh root@77.92.152.3              # Şifre: Emre2025*
nginx -t
systemctl restart nginx
systemctl status nginx
cat /etc/nginx/sites-enabled/emarecloud.tr
cat /etc/nginx/sites-enabled/cloud.tr
```

---

## 📝 Notlar

- **Varsayılan admin**: kullanıcı `admin`, şifre `.env`'den veya `admin123`
- **config.json**: Eski format — ilk açılışta sunucular otomatik DB'ye migre edilir
- **SSH Key**: İlk bağlantıda otomatik RSA 4096 key oluşturulur ve sunucuya deploy edilir
- **SocketIO async_mode**: gevent yüklüyse `gevent`, yoksa `threading`
- **Gunicorn worker**: `GeventWebSocketWorker` (WebSocket desteği için)
- **Veritabanı migrasyon**: `db.create_all()` ile otomatik (SQLAlchemy)

---

> **Bu dosya, EmareCloud projesinin tüm yazılım detaylarını içerir.**
> **Nerede kaldığımızı hatırlamak ve projeye hızlıca devam edebilmek için kullanılır.**
> **Her önemli değişiklikte güncellenmelidir.**
