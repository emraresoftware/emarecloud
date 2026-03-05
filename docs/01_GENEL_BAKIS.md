# EmareCloud — Genel Bakış

Bu proje, birden fazla Linux sunucuyu tek arayüzden yönetmek için geliştirilmiş **kurumsal düzey** Flask tabanlı bir altyapı yönetim panelidir.

## Amaç

- Sunucuları tek noktadan izlemek ve yönetmek
- SSH üzerinden güvenli bağlantı ve komut çalıştırma
- Kurulum/operasyon işlerini hızlandırmak
- Güvenlik duvarı ve sanallaştırma işlemlerini merkezileştirmek
- **RBAC tabanlı yetkilendirme** ile kontrollü erişim sağlamak
- **AES-256-GCM** ile SSH kimlik bilgilerini güvenli saklamak

## Temel Özellikler

- **Dashboard:** toplam/çevrimiçi/bağlı sunucu görünümü
- **Kimlik doğrulama:** Login ekranı, session tabanlı oturum, brute-force koruması
- **RBAC:** 4 seviye rol (super_admin, admin, operator, read_only) — 57 endpoint korumalı
- **Sunucu detay:** CPU, RAM, disk (kullanım + SMART sağlık), ağ, süreç, servis; kurulum bilgileri; sunucu düzenleme
- **Web Terminal:** tarayıcıdan WebSocket tabanlı komut yürütme
- **Uygulama Pazarı:** 58+ uygulama — Veritabanı, Web Sunucu, Altyapı, Geliştirme, Sanallaştırma, Güvenlik, Monitoring, AI/Yapay Zeka, İletişim, Otomasyon
- **Güvenlik Duvarı:** UFW ve firewalld yönetimi
- **Sanallaştırma:** LXD container listesi, oluşturma, başlat/durdur, komut çalıştırma
- **Depolama:** RAID protokolleri; sunucu diskleri (SMART sağlık, otomatik yenileme); yazılım RAID (mdadm) durumu
- **Lisans sistemi:** RSA-4096 imzalı lisans doğrulama (Community / Professional / Enterprise)
- **Landing page:** Ürün tanıtım sayfası (`/landing`)

## Güvenlik Mimarisi

| Katman | Teknoloji |
|--------|-----------|
| Kimlik doğrulama | Session tabanlı login, şifre karmaşıklık kuralları |
| Yetkilendirme | RBAC — 4 seviye rol, endpoint bazlı erişim kontrolü |
| Şifreleme | AES-256-GCM (SSH bilgileri), MASTER_KEY ile |
| Güvenlik başlıkları | CSP, X-Frame-Options, X-Content-Type-Options, HSTS |
| Brute-force | Ardışık başarısız giriş sonrası hesap kilitleme |
| CSRF | Token tabanlı form koruması |
| Audit | Yapılandırılmış loglama (JSON + human-readable, rotasyonlu) |

## Teknoloji Özeti

- Backend: Flask 3.0 + Flask-SocketIO (factory pattern: `create_app()`)
- SSH: Paramiko + AES-256-GCM şifreleme
- Frontend: Jinja2 + Vanilla JS + CSS
- Veri: JSON tabanlı yerel yapılandırma (`config.json`) + SQLite (auth)
- Loglama: Yapılandırılmış JSON (üretim) + renkli human-readable (geliştirme)
- Lisans: RSA-4096 imzalı JSON lisans doğrulama

## Proje Yapısı (Modüler Mimari)

```
├── app.py                    # Factory pattern (create_app) — ~95 satır
├── config.py                 # CORS, debug, secret yapılandırma
├── auth_routes.py            # Kimlik doğrulama, RBAC, şifre kuralları
├── license_manager.py        # RSA-4096 lisans doğrulama
├── setup.sh                  # İnteraktif 7 adımlı kurulum wizard'ı
│
├── core/                     # Çekirdek modüller
│   ├── middleware.py          # Gzip sıkıştırma + güvenlik başlıkları
│   ├── database.py            # Veritabanı init & migrasyon
│   ├── helpers.py             # Sunucu yardımcıları, SSH yönetici, ayarlar
│   ├── config_io.py           # RAID config JSON I/O
│   └── logging_config.py     # JSONFormatter + HumanReadableFormatter
│
├── routes/                   # Blueprint'ler (10 modül)
│   ├── __init__.py            # register_blueprints() — lazy import
│   ├── pages.py               # Sayfa route'ları (dashboard, market, landing, health)
│   ├── servers.py             # Sunucu CRUD + bağlantı + lisans kontrolü
│   ├── metrics.py             # CPU/RAM/disk/süreç/servis/güvenlik metrikleri
│   ├── firewall.py            # Güvenlik duvarı yönetimi
│   ├── virtualization.py      # LXD VM CRUD + exec
│   ├── commands.py            # Komut çalıştırma + hızlı eylemler
│   ├── storage.py             # RAID protokolleri + depolama durumu
│   ├── market.py              # Uygulama pazarı + GitHub API
│   └── terminal.py            # WebSocket terminal olayları
│
├── ssh_manager.py             # SSH bağlantı yönetimi
├── server_monitor.py          # Metrik toplama, SMART, mdadm
├── market_apps.py             # 58+ uygulama tanımı
├── firewall_manager.py        # UFW/firewalld işlemleri
├── virtualization_manager.py  # LXD container işlemleri
│
├── templates/                 # HTML şablonlar
├── static/                    # CSS ve JavaScript
└── docs/                      # Dokümantasyon
```

## Mevcut Döküman Kapsamı

Bu `docs/` klasörü ve kök dizindeki `.md` dosyaları proje dokümantasyonunu oluşturur:

- **docs/00_INDEX.md** — Tüm doküman listesi ve hızlı bağlantılar
- **docs/01_GENEL_BAKIS.md** — Genel bakış (bu dosya)
- **docs/02_KURULUM_VE_HIZLI_BASLANGIC.md** — Kurulum, setup.sh, hızlı başlangıç
- **docs/03_KULLANIM_REHBERI.md** — Kullanım rehberi
- **docs/04_API_VE_MODULLER.md** — Modüler mimari ve API uçları
- **docs/05_YAZILIM_GELISTIRME_YOL_HARITASI.md** — Yazılım geliştirme yol haritası
- **docs/MVP_KAPSAM.md** — Satılabilir MVP kapsam dokümanı
- **docs/RBAC_ENDPOINT_MATRIX.md** — 57 endpoint RBAC yetki matrisi
- **docs/REFACTOR_PLANI.md** — Blueprint refactor planı (tamamlandı ✅)
- **docs/TLS_REVERSE_PROXY.md** — Nginx + Let's Encrypt TLS rehberi

Kök dizinde: **README.md**, **KULLANIM_KILAVUZU.md**, **SANAL_MAKINE_YONETIMI.md**, **YAZILIM_GELISTIRME.md**, **PRODUCT_ROADMAP.md**.
