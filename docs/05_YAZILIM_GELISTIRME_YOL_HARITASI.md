# Yazılım Geliştirme Yol Haritası

Bu plan, projenin güvenli, sürdürülebilir ve ölçeklenebilir şekilde geliştirilmesi için izlenen ve planlanan adımları içerir.

## Faz 1 - Güvenlik Sertleştirme ✅ TAMAMLANDI

1. ✅ Kimlik doğrulama (login + session)
2. ✅ Yetkilendirme (RBAC — 4 seviye rol, 57 endpoint korumalı)
3. ✅ Secret yönetimi (AES-256-GCM şifreleme, MASTER_KEY)
4. ✅ Production config ayrımı (config.py, .env)
5. ✅ Komut yürütme güvenlik politikası (tehlikeli komut engelleme)
6. ✅ Şifre karmaşıklık kuralları (5 regex kural)
7. ✅ Brute-force koruması
8. ✅ CSRF koruması
9. ✅ Güvenlik başlıkları (CSP, X-Frame-Options, X-Content-Type-Options, HSTS)

Çıktı:
- Yetkisiz erişimler engellendi
- Kritik endpoint'ler RBAC ile korunuyor
- SSH bilgileri şifreli saklanıyor

## Faz 2 - Mimari İyileştirme ✅ TAMAMLANDI

1. ✅ `app.py` dosyası modüler Blueprint yapısına ayrıldı (1182 → ~95 satır)
2. ✅ `core/` çekirdek modüller (middleware, database, helpers, config_io, logging_config)
3. ✅ `routes/` Blueprint'ler (10 modül, lazy import)
4. ✅ Factory pattern (`create_app()`)
5. ✅ Yapılandırılmış loglama (JSON + human-readable, RotatingFileHandler)
6. ✅ CORS kısıtlama (CORS_ALLOWED_ORIGINS)
7. ✅ RSA-4096 lisans sistemi (license_manager.py)
8. ✅ Landing page (/landing)
9. ✅ setup.sh kurulum wizard'ı
10. ✅ TLS reverse proxy rehberi (docs/TLS_REVERSE_PROXY.md)

Çıktı:
- Kod okunabilirliği ve bakım maliyetinde büyük düşüş
- Modüler ve genişletilebilir yapı
- Ticari kullanıma hazır lisans altyapısı

## Faz 3 - Test ve Kalite Süreci ✅ TAMAMLANDI

1. ✅ `pytest` tabanlı test altyapısı (pytest 9.0 + pytest-cov 7.0)
2. ✅ Kritik akış testleri — 111 test, 6 modül:
   - `test_auth.py` (23 test) — login, logout, CSRF, RBAC, user CRUD, şifre doğrulama
   - `test_rbac.py` (21 test) — rol izinleri, komut güvenliği, tehlikeli komut engelleme
   - `test_server.py` (14 test) — sunucu CRUD, validation, RBAC izinleri
   - `test_market.py` (12 test) — market listeleme, kategori, kurulum doğrulama, RBAC
   - `test_config.py` (26 test) — Config sınıfları, AES-256-GCM kripto, lisans, User model
   - `test_pages.py` (15 test) — sayfa erişimi, authentication, RBAC kontrol
3. ✅ Lint/format standardı (`ruff` 0.15+ — 0 hata, pyproject.toml yapılandırması)
4. ✅ CI pipeline (`.github/workflows/ci.yml` — lint + test, Python 3.10/3.11/3.12)
5. ✅ Test fixture altyapısı (CSRF-aware login, session isolation, function-scoped app)
6. ✅ `pyproject.toml` birleşik yapılandırma (pytest + coverage + ruff)
7. ✅ `requirements-dev.txt` geliştirme bağımlılıkları

Çıktı:
- 111 test başarılı, 0 başarısız
- %46 kod kapsama oranı (SSH-bağımlı modüller hariç kritik modüller %68-100)
- Ruff lint: 0 hata
- GitHub Actions CI: her push'ta otomatik lint + test
- Regresyon riskleri minimize edildi

## Faz 4 - Monitoring ve Otomasyon ✅ TAMAMLANDI

1. ✅ Gerçek zamanlı alert sistemi (CPU, RAM, disk, ağ eşik değerleri, koşullu kurallar)
2. ✅ Webhook entegrasyonu (Slack, Discord, SMTP e-posta, özel HTTP webhook)
3. ✅ Zamanlanmış görev yönetimi (cron tabanlı, uzak sunucularda SSH ile komut çalıştırma)
4. ✅ Otomatik yedekleme sistemi (SSH üzerinden tar/gzip/bzip2, retention politikası)
5. ✅ Metrik snapshot koleksiyonu (CPU, RAM, disk, ağ, load — trend analizi için)
6. ✅ Arka plan scheduler (threading daemon — alert/metrik/backup/task döngüsü)
7. ✅ 6 sekmeli monitoring dashboard (Genel Bakış, Alarmlar, Webhook, Görevler, Yedekleme, Trendler)
8. ✅ RBAC entegrasyonu (monitoring.view + monitoring.manage izinleri)
9. ✅ 67 yeni test (7 test sınıfı), toplam 178 test

Yeni Modüller:
- `alert_manager.py` — Alert motoru + webhook dağıtıcı + metrik snapshot toplayıcı
- `backup_manager.py` — SSH tabanlı yedekleme, tar sıkıştırma, retention temizliği, cron zamanlama
- `scheduler.py` — Threading daemon scheduler (alert 2dk, metrik 5dk, backup 1dk, task 1dk)
- `routes/monitoring.py` — 20+ API endpoint (CRUD: alert/webhook/task/backup/metrik)
- `templates/monitoring.html` — 6 sekmeli dashboard (overview, alarmlar, webhook, görevler, yedekleme, trendler)

Yeni DB Modelleri:
- `AlertRule` — alarm kuralları (metrik, koşul, eşik, sunucu, webhook bağlantısı, cooldown)
- `AlertHistory` — tetiklenen alarmlar, onaylama durumu
- `WebhookConfig` — webhook yapılandırması (Slack, Discord, e-posta, özel)
- `ScheduledTask` — zamanlanmış görev tanımları (cron, komut, çalışma durumu)
- `BackupProfile` — yedekleme profilleri (kaynak, hedef, zamanlama, sıkıştırma, retention)
- `MetricSnapshot` — anlık metrik kayıtları (cpu, memory, disk, network, load)

Çıktı:
- Sunucular gerçek zamanlı izleniyor, eşik aşımlarında otomatik bildirim
- Slack/Discord/e-posta webhook entegrasyonu çalışır durumda
- SSH üzerinden otomatik yedekleme sistemi (retention ile)
- Zamanlanmış görevler cron formatında tanımlanabiliyor
- Trend analizi için metrik geçmişi kaydediliyor
- 178 test başarılı, 0 lint hatası

## Mevcut Mimari

```
├── app.py                    # Factory pattern (create_app)
├── core/                     # Çekirdek modüller (5 dosya)
├── routes/                   # Blueprint'ler (11 modül)
│   └── monitoring.py         # Monitoring API (20+ endpoint)
├── auth_routes.py            # RBAC + auth
├── alert_manager.py          # Alert motoru + webhook dağıtıcı
├── backup_manager.py         # Otomatik yedekleme (SSH)
├── scheduler.py              # Arka plan daemon scheduler
├── license_manager.py        # Lisans doğrulama
├── config.py                 # Yapılandırma
├── models.py                 # DB modelleri (12 model)
├── templates/
│   └── monitoring.html       # 6 sekmeli monitoring dashboard
├── tests/                    # 7 test modülü, 178 test
│   ├── conftest.py           # CSRF-aware fixture'lar
│   ├── test_auth.py          # Auth testleri (23)
│   ├── test_rbac.py          # RBAC + komut güvenliği (21)
│   ├── test_server.py        # Sunucu CRUD testleri (14)
│   ├── test_market.py        # Market testleri (12)
│   ├── test_config.py        # Config/kripto/model testleri (26)
│   ├── test_pages.py         # Sayfa erişim testleri (15)
│   └── test_monitoring.py    # Monitoring testleri (67)
├── pyproject.toml            # pytest + ruff + coverage yapılandırması
├── requirements-dev.txt      # Geliştirme bağımlılıkları
└── .github/workflows/ci.yml  # CI pipeline
```

## Tamamlanan Sprint Görevleri (Faz 4) ✅

- [x] AlertRule, AlertHistory, WebhookConfig, ScheduledTask, BackupProfile, MetricSnapshot modelleri
- [x] Alert motoru — koşul operatörleri (>, <, >=, <=, ==, !=), metrik çıkarma, cooldown
- [x] Webhook dağıtıcı — Slack, Discord, SMTP e-posta, özel HTTP POST
- [x] SSH tabanlı yedekleme — tar sıkıştırma, retention temizliği, cron zamanlama
- [x] Threading daemon scheduler — 4 periyodik görev (alert, metrik, backup, task)
- [x] Monitoring API — 20+ endpoint, tam CRUD, RBAC korumalı
- [x] 6 sekmeli monitoring dashboard (Vue-style SPA-like tabs)
- [x] RBAC — monitoring.view (tüm roller), monitoring.manage (sadece admin)
- [x] 67 yeni test (7 sınıf), toplam 178 test
- [x] Ruff lint: 0 hata

## Tamamlanan Sprint Görevleri (Faz 3) ✅

- [x] pytest altyapısı kurulumu
- [x] Auth akışı testleri (login, register, RBAC)
- [x] Sunucu CRUD testleri
- [x] Market kurulum testleri
- [x] Config/kripto/model testleri
- [x] Sayfa erişim testleri
- [x] `ruff` lint kuralları (0 hata)
- [x] GitHub Actions CI pipeline
- [x] pyproject.toml yapılandırması
- [x] requirements-dev.txt

## Başarı Ölçütleri

- ✅ Yetkisiz erişim oranı: 0
- ✅ Kritik endpoint RBAC koruması: %100
- ✅ Lint hatası: 0 (ruff)
- ✅ Test sayısı: 178 (7 modül)
- ✅ Test başarı oranı: %100 (178/178)
- ✅ Kod kapsama: %46+ (SSH-bağımlı modüller hariç kritik modüller %68-100)
- ✅ CI pipeline: GitHub Actions (lint + test, Python 3.10/3.11/3.12)
- ✅ Alert sistemi: 6 koşul operatörü, cooldown, webhook entegrasyonu
- ✅ Webhook kanalları: 4 (Slack, Discord, e-posta, özel)
- ✅ Arka plan scheduler: 4 periyodik görev (alert, metrik, backup, task)

## Sonraki Sprint Önerisi (Faz 5 — Ölçekleme ve İleri Düzey)

- [ ] Container yönetimi (Docker/Podman entegrasyonu)
- [ ] Multi-tenant mimarisi (müşteri izolasyonu)
- [ ] Faturalandırma sistemi (WHMCS benzeri)
- [ ] API gateway / rate limiting
- [ ] Log aggregation (merkezi log yönetimi)
- [ ] AI destekli anomali tespiti

## Sonuç

Faz 1 (Güvenlik), Faz 2 (Mimari), Faz 3 (Test & Kalite) ve Faz 4 (Monitoring & Otomasyon) başarıyla tamamlanmıştır. Proje **EmareCloud v1.0 — Monitoring Edition** olarak tam operasyonel izleme ve otomasyon yeteneklerine sahiptir. 178 test ile regresyon riskleri minimize edilmiş, CI pipeline ile her değişiklik otomatik olarak doğrulanmaktadır. Gerçek zamanlı alert, webhook bildirim, otomatik yedekleme ve zamanlanmış görev altyapısı ile üretim ortamı yönetimi için hazırdır.
