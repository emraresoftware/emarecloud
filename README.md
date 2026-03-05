# EmareCloud — Altyapı Yönetim Paneli

Birden fazla Linux sunucuyu tek arayüzden izleyip yönetmenizi sağlayan **kurumsal düzey** Flask tabanlı panel. SSH üzerinden bağlanır; metrikler, terminal, uygulama pazarı (58+ uygulama, AI araçları dahil), güvenlik duvarı, sanal makine (LXD), depolama yönetimi ve **RBAC tabanlı yetkilendirme** sunar.

## ✨ Öne Çıkan Özellikler

- 🔐 **4 seviye RBAC** (super_admin, admin, operator, read_only)
- 🔑 **AES-256-GCM** ile SSH kimlik bilgisi şifreleme
- 🛡️ CSRF koruması, brute-force engelleme, güvenlik başlıkları (CSP, X-Frame-Options)
- 📦 **Modüler Blueprint mimarisi** (10 blueprint, 4 çekirdek modül)
- 📊 Yapılandırılmış loglama (JSON + human-readable, rotasyonlu)
- 🏪 58+ hazır uygulama pazarı (AI/ML araçları dahil)
- 📜 **RSA-4096 tabanlı lisans sistemi** (Community / Professional / Enterprise)
- 🌐 Landing page (`/landing`) — ürün tanıtım sayfası

## Hızlı Başlangıç

### Otomatik Kurulum (Önerilen)

```bash
chmod +x setup.sh
./setup.sh
```

`setup.sh` interaktif wizard ile 7 adımda kurulumu tamamlar:
1. Sistem gereksinimleri kontrolü
2. Python bağımlılıkları kurulumu
3. Master encryption key oluşturma
4. Admin kullanıcı yapılandırma
5. Port ayarı (varsayılan 5555)
6. Veritabanı başlatma
7. `.env` dosyası oluşturma

### Manuel Kurulum

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Tarayıcıda: **http://localhost:5555**

### Üretim Ortamı

```bash
gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
  -w 1 -b 0.0.0.0:5555 "app:create_app()"
```

TLS/SSL yapılandırması için: [docs/TLS_REVERSE_PROXY.md](docs/TLS_REVERSE_PROXY.md)

## Kullanım Kılavuzu

Tüm özelliklerin adım adım anlatımı için:

- **[KULLANIM_KILAVUZU.md](KULLANIM_KILAVUZU.md)** – Giriş, RBAC, dashboard, sunucu yönetimi, terminal, uygulama pazarı, güvenlik duvarı, sanallaştırma, depolama, SSS.

Sadece sanal makine (LXD) yönetimi için:

- **[SANAL_MAKINE_YONETIMI.md](SANAL_MAKINE_YONETIMI.md)** – Sanal makineleri listeleme, oluşturma, başlat/durdur, içinde komut çalıştırma.

## Özellikler

### Yönetim & İzleme
- **Dashboard:** sunucu listesi, çevrimiçi/bağlı durumu, özet kartlar
- **Sunucu detay:** CPU, RAM, disk (kullanım + SMART sağlık), ağ, süreçler, servisler; kurulum bilgileri; sunucuyu düzenleme
- **Web terminal:** SSH üzerinden gerçek zamanlı komut (WebSocket)
- **Depolama:** RAID protokolleri, sunucu diskleri (SMART sağlık, otomatik yenileme), yazılım RAID (mdadm) durumu

### Uygulama Pazarı
- **58+ uygulama:** Veritabanı, Web Sunucu, Altyapı, Geliştirme, Sanallaştırma, Güvenlik, Monitoring, AI/Yapay Zeka, İletişim, Otomasyon
- **AI araçları:** Ollama, Python AI/PyTorch, Whisper, Open WebUI, code-server, Text Generation WebUI
- Tek tıkla kurulum, akordeon kategoriler

### Güvenlik
- **Kimlik doğrulama:** Login ekranı, session tabanlı oturum yönetimi
- **RBAC:** 4 seviye yetkilendirme (57 endpoint korumalı)
- **Şifre kuralları:** Minimum 8 karakter, büyük/küçük harf, rakam, özel karakter
- **Şifreleme:** AES-256-GCM ile SSH kimlik bilgileri koruması
- **Güvenlik başlıkları:** CSP, X-Frame-Options, X-Content-Type-Options, HSTS
- **Audit log:** Tüm kritik işlemler kayıt altında
- **CSRF & brute-force koruması**

### Altyapı
- **Güvenlik duvarı:** UFW / firewalld kural yönetimi
- **Sanallaştırma:** LXD container yönetimi (oluşturma, başlat/durdur, komut çalıştırma)
- **Lisans sistemi:** RSA-4096 imzalı lisans doğrulama (Community: 3, Professional: 25, Enterprise: sınırsız sunucu)

### Monitoring ve Otomasyon
- **Alert sistemi:** CPU, RAM, disk, ağ eşik değerli alarm kuralları (6 koşul operatörü, cooldown)
- **Webhook entegrasyonu:** Slack, Discord, SMTP e-posta, özel HTTP webhook
- **Zamanlanmış görevler:** Cron tabanlı uzak sunucu komut yönetimi
- **Otomatik yedekleme:** SSH üzerinden tar/gzip/bzip2, retention politikası
- **Metrik geçmişi:** Trend analizi için CPU, RAM, disk, ağ, load snapshot’ları
- **Monitoring dashboard:** 6 sekmeli (Özet, Alarmlar, Webhook, Görevler, Yedekleme, Trendler)

## Mimari

```
├── app.py                    # Factory pattern (create_app)
├── config.py                 # Yapılandırma (CORS, debug, secret)
├── auth_routes.py            # Kimlik doğrulama & RBAC
├── license_manager.py        # RSA-4096 lisans doğrulama
├── setup.sh                  # İnteraktif kurulum wizard'ı
│
├── core/                     # Çekirdek modüller
│   ├── middleware.py          # Gzip + güvenlik başlıkları
│   ├── database.py            # Veritabanı init & migrasyon
│   ├── helpers.py             # Sunucu yardımcıları, SSH, ayarlar
│   ├── config_io.py           # RAID config JSON I/O
│   └── logging_config.py     # Yapılandırılmış loglama
│
├── routes/                   # Blueprint'ler (11 modül)
│   ├── pages.py               # Sayfa route'ları
│   ├── servers.py             # Sunucu CRUD + bağlantı
│   ├── metrics.py             # CPU/RAM/disk/süreç metrikleri
│   ├── firewall.py            # Güvenlik duvarı yönetimi
│   ├── virtualization.py      # LXD VM CRUD
│   ├── commands.py            # Komut çalıştırma
│   ├── storage.py             # RAID & depolama
│   ├── market.py              # Uygulama pazarı
│   ├── terminal.py            # WebSocket terminal olayları
│   └── monitoring.py          # Monitoring API (20+ endpoint)
│
├── ssh_manager.py             # SSH bağlantı yönetimi
├── server_monitor.py          # Metrik toplama, SMART, mdadm
├── alert_manager.py           # Alert motoru + webhook dağıtıcı
├── backup_manager.py          # Otomatik yedekleme (SSH)
├── scheduler.py               # Arka plan daemon scheduler
├── market_apps.py             # 58+ uygulama tanımı
├── firewall_manager.py        # UFW/firewalld işlemleri
└── virtualization_manager.py  # LXD container işlemleri
```

## Dokümantasyon

| Dosya | İçerik |
|-------|--------|
| [README.md](README.md) | Bu dosya — hızlı başlangıç ve özellik özeti |
| [KULLANIM_KILAVUZU.md](KULLANIM_KILAVUZU.md) | Giriş, RBAC, arayüz, sunucu yönetimi, terminal, pazar, güvenlik duvarı, sanallaştırma, depolama, SSS |
| [SANAL_MAKINE_YONETIMI.md](SANAL_MAKINE_YONETIMI.md) | LXD sanal makine yönetimi |
| [docs/00_INDEX.md](docs/00_INDEX.md) | Tüm dokümantasyon listesi ve hızlı bağlantılar |
| [docs/01_GENEL_BAKIS.md](docs/01_GENEL_BAKIS.md) | Amaç, özellikler, teknoloji, proje yapısı |
| [docs/02_KURULUM_VE_HIZLI_BASLANGIC.md](docs/02_KURULUM_VE_HIZLI_BASLANGIC.md) | Gereksinimler, setup.sh, kurulum, ilk kullanım |
| [docs/03_KULLANIM_REHBERI.md](docs/03_KULLANIM_REHBERI.md) | Giriş, dashboard, sunucu, terminal, pazar, güvenlik duvarı, sanallaştırma, depolama |
| [docs/04_API_VE_MODULLER.md](docs/04_API_VE_MODULLER.md) | Modüler mimari, Blueprint'ler, API uçları |
| [docs/05_YAZILIM_GELISTIRME_YOL_HARITASI.md](docs/05_YAZILIM_GELISTIRME_YOL_HARITASI.md) | Faz 1 ✅, Faz 2 ✅, Faz 3 ✅, Faz 4 ✅ yol haritası |
| [docs/MVP_KAPSAM.md](docs/MVP_KAPSAM.md) | Satılabilir MVP kapsam dokümanı |
| [docs/RBAC_ENDPOINT_MATRIX.md](docs/RBAC_ENDPOINT_MATRIX.md) | 57 endpoint RBAC yetki matrisi |
| [docs/TLS_REVERSE_PROXY.md](docs/TLS_REVERSE_PROXY.md) | Nginx + Let's Encrypt + WebSocket TLS rehberi |
| [YAZILIM_GELISTIRME.md](YAZILIM_GELISTIRME.md) | Geliştirme planı, performans iyileştirmeleri |
| [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) | Ürün vizyonu ve hedef sürümler |
| [docs/AI_ANAYASASI.md](docs/AI_ANAYASASI.md) | AI Anayasası — veri politikası, etik kurallar, güvenlik, model yönetişimi |

## Gereksinimler

- Python 3.10+
- Yönetilecek sunuculara SSH erişimi (kullanıcı/şifre)
- `.env` dosyası (setup.sh ile otomatik oluşturulur)

## Lisans

Community sürümü ücretsiz (3 sunucu sınırı). Professional ve Enterprise planları için: [Landing Page](/landing)

© EmareCloud — Tüm hakları saklıdır.
