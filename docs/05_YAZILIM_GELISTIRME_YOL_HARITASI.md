# EmareCloud — Yazılım Geliştirme Dokümanı

> **Vizyon:** "Sunucu Yönetim Paneli" değil, **Infrastructure Business Engine** —
> altyapıyı hizmete, hizmeti gelire dönüştüren iki taraflı platform.

---

## 1. Proje Özeti

| Özellik | Değer |
|---------|-------|
| **Ürün** | EmareCloud — Self-Hosted Altyapı İş Motoru |
| **Teknoloji** | Flask 3.0 · Python 3.10+ · SQLAlchemy · Flask-SocketIO |
| **Port** | 5555 |
| **Lisans** | RSA-4096 donanım kilitli |
| **Test** | 178 test · %100 geçiyor · pytest + pytest-cov |
| **Lint** | 0 hata · ruff |
| **CI** | GitHub Actions · Python 3.10 / 3.11 / 3.12 matrisi |

---

## 2. Tamamlanan Fazlar

### Faz 1 — Güvenlik Temeli ✅
- AES-256-GCM şifreleme (SSH credential, config)
- RBAC 4 seviye (admin → viewer), 57+ korumalı endpoint
- Brute-force koruması (rate limiting)
- Audit log sistemi (tüm kritik işlemler kayıt altında)
- RSA-4096 lisans doğrulama

### Faz 2 — Mimari Yeniden Yapılanma ✅
- Factory pattern (`create_app()`)
- Blueprint modüler yapı (11 blueprint)
- Config yönetimi (ortam bazlı)
- Hata yönetimi (merkezi handler)
- Veritabanı migration altyapısı

### Faz 3 — Test Altyapısı ✅
- 111 birim test yazıldı
- pytest + pytest-cov entegrasyonu
- CI/CD pipeline (GitHub Actions)
- Fixture tabanlı test mimarisi
- 7 test modülü

### Faz 4 — İzleme & Otomasyon ✅
- Gerçek zamanlı metrik toplama (CPU, RAM, Disk, Network)
- Eşik bazlı alarm sistemi (AlertRule + AlertHistory)
- Webhook entegrasyonu (Slack, Discord, Teams, generic)
- Zamanlanmış görevler (ScheduledTask + APScheduler)
- Otomatik yedekleme profilleri (BackupProfile)
- RAID izleme protokolü
- 67 yeni test → toplam 178 test

---

## 3. Mevcut Mimari

### 3.1 Veritabanı Modelleri (12)
```
User, Server, AuditLog, AlertRule, AlertHistory,
WebhookConfig, ScheduledTask, BackupProfile,
MetricSnapshot, RaidProtocol, MarketInstallation, LicenseInfo
```

### 3.2 Route Blueprint'leri (11)
```
main, auth, servers, firewall, terminal, market,
storage, virtualization, monitoring, alerts, api
```

### 3.3 Servis Katmanları
```
ssh_manager.py        → SSH bağlantı yönetimi
server_monitor.py     → Metrik toplama
firewall_manager.py   → UFW/iptables yönetimi
virtualization_manager.py → KVM/LXD sanallaştırma
market_apps.py        → Uygulama mağazası
```

### 3.4 Dizin Yapısı
```
├── app.py                    # Uygulama fabrikası
├── config.json               # Sunucu konfigürasyonu
├── models/                   # SQLAlchemy modelleri
├── routes/                   # 11 Blueprint
├── services/                 # İş mantığı katmanı
├── static/css|js/            # Frontend varlıkları
├── templates/                # Jinja2 şablonları
├── tests/                    # 7 test modülü
├── .github/workflows/        # CI pipeline
└── requirements.txt          # Bağımlılıklar
```

---

## 4. Kalite Metrikleri

| Metrik | Değer |
|--------|-------|
| Toplam Test | 178 |
| Test Başarı | %100 |
| Lint Hatası | 0 (ruff) |
| CI Durumu | ✅ Yeşil |
| Korumalı Endpoint | 57+ |
| DB Modeli | 12 |
| Blueprint | 11 |

---

## 5. Performans & Güvenlik Profili

| Alan | Mevcut Durum |
|------|-------------|
| Şifreleme | AES-256-GCM (credential + config) |
| Kimlik Doğrulama | Session tabanlı + RBAC |
| Rate Limiting | Brute-force koruması aktif |
| Metrik Toplama | Senkron (her istek) |
| Görev Kuyruğu | APScheduler (in-process) |
| WebSocket | Flask-SocketIO (terminal) |
| Veritabanı | SQLite (geliştirme) |

---

## 6. Platform Dönüşüm Motorları

> Mevcut monolitik panelden **iki taraflı iş platformuna** geçiş için
> 6 kritik motor inşa edilecek. Her motor bağımsız ama entegre çalışır.

### 6.1 🏢 Organizasyon Motoru (Organization Engine)

**Amaç:** Çok kiracılı (multi-tenant) izolasyon — her müşteri kendi evreninde.

**Mevcut Durum:** Tek tenant, `user_id` bazlı basit sahiplik.

**Hedef Mimari:**
- `Organization` modeli → `name`, `slug`, `plan_tier`, `owner_id`, `settings_json`
- Tüm mevcut entity'lere `organization_id` foreign key eklenmesi
- Row-level izolasyon: `@tenant_required` middleware → her sorguya `WHERE org_id = ?` otomatik enjeksiyon
- Organizasyon bazlı roller: `OrgRole` (org_admin, org_member, org_viewer)
- Organizasyon daveti: email ile davet, kabul akışı
- Plan limitleri: organizasyon bazlı sunucu/kullanıcı/kaynak kotası

**Teknik Adımlar:**
1. `Organization` + `OrgMembership` modelleri oluştur
2. Mevcut 12 modele `organization_id` migration'ı
3. `TenantMiddleware` — request başına org context ayarla
4. Tüm sorguları org-scoped hale getir
5. Admin panelinde org yönetim arayüzü

---

### 6.2 ⚙️ Kaynak Uygulama Motoru (Resource Enforcement Engine)

**Amaç:** Satılan kaynakların gerçek donanım seviyesinde zorunlu kılınması.

**Mevcut Durum:** Kaynak limitleri yok, sunuculara sınırsız erişim.

**Hedef Mimari:**

**LXD/Container Hard Limit'leri:**
| Kaynak | Uygulama Yöntemi |
|--------|-------------------|
| CPU | `limits.cpu` pinning |
| RAM | `limits.memory` hard cap |
| Disk | `root disk size` quota |
| Network | `limits.ingress` / `limits.egress` bandwidth cap |

**SSH Sandbox Politikaları:**
- Kısıtlı kullanıcı: `rbash` veya `restricted shell`
- Chroot jail: müşteri kendi dizin ağacında izole
- Root erişim politikası: plan bazlı (starter: yok, pro: sudo belirli komutlar, enterprise: full root)
- Komut beyaz listesi: plan tipine göre izin verilen komutlar

**Teknik Adımlar:**
1. `ResourceQuota` modeli → plan bazlı limit tanımları
2. LXD API entegrasyonu → container oluşturmada limit enjeksiyonu
3. SSH proxy katmanı → komut filtreleme
4. Kaynak aşım alarmları → mevcut alert sistemiyle entegrasyon
5. Kullanım dashboard'u → gerçek zamanlı kaynak tüketim grafiği

---

### 6.3 🤖 AI Platform Motoru (AI Gateway Engine)

**Amaç:** Müşterilere AI model erişimi sunma — model seçimi, API anahtarı,
kullanım takibi, token bazlı faturalandırma.

**Mevcut Durum:** AI altyapısı yok.

**Hedef Mimari:**
```
┌─────────────────────────────────────────────┐
│              AI Gateway API                  │
│  ┌─────────┐ ┌──────────┐ ┌──────────────┐  │
│  │ Model   │ │ API Key  │ │ Rate Limit   │  │
│  │ Registry│ │ Manager  │ │ & Throttle   │  │
│  └─────────┘ └──────────┘ └──────────────┘  │
│  ┌─────────┐ ┌──────────┐ ┌──────────────┐  │
│  │ Usage   │ │ Token    │ │ Load Balance │  │
│  │ Tracker │ │ Billing  │ │ & Fallback   │  │
│  └─────────┘ └──────────┘ └──────────────┘  │
└─────────────────────────────────────────────┘
```

**Bileşenler:**
- **Model Registry:** Desteklenen modellerin kaydı (OpenAI, Anthropic, yerel modeller), versiyon yönetimi
- **API Key Manager:** Organizasyon bazlı API anahtarı oluşturma, döndürme, iptal etme
- **Rate Limit & Throttle:** Plan bazlı istek/dakika, token/gün limitleri
- **Usage Tracker:** Her API çağrısında input/output token sayımı, model, süre kaydı
- **Token Billing:** Token kullanımı → maliyet hesaplama → fatura kalemine dönüştürme
- **Load Balancer & Fallback:** Birden fazla provider arasında yük dağılımı, provider çöktüğünde otomatik yedek

**Teknik Adımlar:**
1. `AIModel`, `AIApiKey`, `AIUsageLog` modelleri
2. Proxy endpoint: `/api/v1/ai/completions` → provider'a yönlendirme
3. Token sayım middleware'i
4. Kullanım dashboard'u (günlük/haftalık/aylık token grafikleri)
5. Provider sağlık kontrolü + otomatik failover

---

### 6.4 💰 Finansal Motor (Financial Engine)

**Amaç:** Abonelik, kullanım ölçümü, fazla kullanım faturalandırması,
komisyon paylaşımı — gelir akışının tam otomasyonu.

**Mevcut Durum:** Finansal altyapı yok.

**Hedef Mimari:**

**Abonelik Motoru:**
- Plan tanımlama: `Plan` modeli (starter, pro, enterprise, custom)
- Plan özellikleri: sunucu limiti, RAM/CPU/Disk kotası, AI token kotası, kullanıcı sayısı
- Abonelik yaşam döngüsü: deneme → aktif → askıya alma → iptal
- Yükseltme/düşürme: prorata hesaplama

**Kullanım Ölçümü (Usage Metering):**
- Saatlik snapshot: CPU-saat, RAM-saat, Disk-GB-saat, Network-GB, AI-token
- Kullanım biriktirme: aylık dönem içi toplam
- Fazla kullanım (overage): kota aşımında birim fiyat uygulaması

**Komisyon Paylaşımı (Commission Split):**
- Market uygulamaları gelir paylaşımı: platform %X — geliştirici %Y
- AI model kullanım paylaşımı: platform %X — provider %Y
- Otomatik ödeme: dönem sonunda hesaplama + dağıtım

**Ödeme Entegrasyonu:**
- Stripe (global), Iyzico (TR), Paddle (SaaS)
- Fatura oluşturma + PDF export
- Gelir dashboard'u: MRR, ARR, churn, LTV metrikleri

**Teknik Adımlar:**
1. `Plan`, `Subscription`, `Invoice`, `UsageRecord`, `PaymentMethod` modelleri
2. Metering servisi: mevcut MetricSnapshot verilerinden kullanım çıkarımı
3. Billing cron: aylık fatura oluşturma
4. Stripe/Iyzico webhook handler'ları
5. Gelir analytics dashboard'u

---

### 6.5 🎯 Deneyim Farklılaştırma Motoru (Experience Engine)

**Amaç:** 1-Click Business Template'leri ile "boş sunucu" yerine
"hazır iş çözümü" sunma — müşteri edinme süresini dakikaya indirme.

**Mevcut Durum:** Market uygulamaları tek tek kurulabiliyor (market_apps.py).

**Hedef Template Paketleri:**

| Paket | İçerik |
|-------|--------|
| **🚀 AI Startup Pack** | GPU sunucu + Jupyter + Model serving + API gateway + monitoring + auto-scale |
| **📝 WordPress Agency Pack** | Web sunucu + WordPress + SSL + CDN + staging ortamı + backup + uptime monitoring |
| **⚡ SaaS Backend Pack** | App sunucu + PostgreSQL + Redis + Celery + Nginx + CI/CD webhook + log aggregation |
| **🧠 GPU Model Hosting Pack** | GPU node + model registry + inference API + token metering + A/B test altyapısı |
| **🏪 E-Commerce Pack** | Web sunucu + WooCommerce/PrestaShop + SSL + payment gateway + inventory backup |

**Her Paketin Otomatik Konfigürasyonu:**
- Sunucu provisioning (uygun boyut)
- Firewall kuralları (sadece gerekli portlar)
- SSL sertifikası (Let's Encrypt)
- Monitoring profili (kritik metrikler)
- Backup programı (günlük/haftalık)
- Alert kuralları (downtime, disk dolu, CPU spike)
- Market uygulamaları (paket bileşenleri)

**Teknik Adımlar:**
1. `BusinessTemplate` modeli → paket tanımı JSON schema
2. Template executor servisi → adım adım provisioning
3. Template marketplace UI → kategori, arama, önizleme
4. Kurulum wizard'ı → müşteri parametreleri (domain, parola vb.)
5. Post-install doğrulama → sağlık kontrolü + rapor

---

### 6.6 🔒 Kurumsal Güvenlik Motoru (Enterprise Security Engine)

**Amaç:** Enterprise müşterilerin güvenlik ve uyumluluk gereksinimlerini
karşılama — SOC2, ISO 27001 uyumluluğuna zemin hazırlama.

**Mevcut Durum:** Temel güvenlik mevcut (AES-256, RBAC, audit log, rate limit).

**Ek Kurumsal Özellikler:**

| Özellik | Açıklama | Öncelik |
|---------|----------|---------|
| **2FA (TOTP)** | Google Authenticator / Authy ile iki faktörlü doğrulama | 🔴 Yüksek |
| **SSO** | SAML 2.0 ve OpenID Connect entegrasyonu | 🟡 Orta |
| **SIEM Export** | Audit loglarını Splunk/ELK/Datadog'a aktarma (syslog/webhook) | 🟡 Orta |
| **Immutable Logs** | Değiştirilemez audit kayıtları (append-only, hash chain) | 🟡 Orta |
| **API Token Sistemi** | Kullanıcı bazlı API anahtarı oluşturma, scope belirleme, süre sınırlama | 🔴 Yüksek |
| **IP Allowlist** | Organizasyon bazlı IP beyaz listesi — sadece belirli IP'lerden erişim | 🟢 Düşük |
| **Session Yönetimi** | Aktif oturumları listeleme, uzaktan oturum sonlandırma | 🟡 Orta |
| **Şifre Politikası** | Minimum uzunluk, karmaşıklık, geçmiş şifre kontrolü, zorunlu yenileme | 🟡 Orta |

**Teknik Adımlar:**
1. `TwoFactorAuth` modeli + pyotp entegrasyonu → QR code enrollment
2. `APIToken` modeli → token oluşturma, scope, expiry, revoke
3. SAML/OIDC handler → python3-saml veya authlib
4. Audit log hash chain → her kaydın bir önceki kaydın hash'ini içermesi
5. IP filtreleme middleware'i

---

## 7. Performans Evrim Yol Haritası

> Mevcut senkron + in-process mimariden **event-driven, async, dağıtık**
> mimariye geçiş planı.

### 7.1 Mevcut → Hedef Karşılaştırma

| Katman | Mevcut | Hedef |
|--------|--------|-------|
| Görev Kuyruğu | APScheduler (in-process) | **Celery + Redis** (dağıtık) |
| Metrik Toplama | Senkron (request içinde) | **Async collector** (background worker) |
| Mimari Desen | Request-response | **Event-driven** (pub/sub) |
| Gerçek Zamanlı | Flask-SocketIO (terminal) | **WebSocket streaming** (metrikler + alertler + loglar) |
| Veritabanı | SQLite | **PostgreSQL** (production) |
| Cache | Yok | **Redis** (session + query cache) |
| API | Monolitik | **RESTful v1** → **GraphQL** (opsiyonel) |

### 7.2 Celery + Redis Entegrasyonu

**Celery'ye Taşınacak Görevler:**
- Metrik toplama (her 60s, tüm sunucular)
- Yedekleme işlemleri (uzun süren)
- Alert değerlendirme (eşik kontrol)
- Webhook gönderimi (dış servislere)
- Market uygulama kurulumu (SSH üzerinden)
- AI API proxy istekleri
- Fatura oluşturma (aylık batch)
- Template provisioning (çok adımlı)

**Mimari:**
```
Flask App → Redis (broker) → Celery Worker(s)
                ↓
         Redis (result backend + cache)
                ↓
         Celery Beat (zamanlama)
```

### 7.3 WebSocket Streaming Genişletme

**Mevcut:** Sadece terminal çıktısı WebSocket üzerinden.

**Hedef:** Tüm gerçek zamanlı verilerin WebSocket üzerinden akışı:
- Sunucu metrikleri (CPU, RAM, Disk, Network) → canlı dashboard
- Alert bildirimleri → anlık pop-up
- Görev ilerlemesi → progress bar (yedekleme, kurulum)
- Log akışı → canlı log viewer
- AI kullanım metrikleri → token tüketim animasyonu

---

## 8. İki Taraflı Platform Vizyonu

### 8.1 Platform Yapısı

```
┌──────────────────────────────────────────────────────┐
│                 EmareCloud Platform                  │
│                                                        │
│   TALEP TARAFI              ARZ TARAFI                 │
│   (Müşteriler)              (Sağlayıcılar)            │
│   ┌──────────┐              ┌──────────────┐          │
│   │ Startup  │              │ Hosting      │          │
│   │ Ajans    │◄────────────►│ Veri Merkezi │          │
│   │ KOBİ     │  Eşleştirme │ GPU Provider │          │
│   │ Kurum    │              │ AI Provider  │          │
│   └──────────┘              └──────────────┘          │
│                                                        │
│   ┌────────────────────────────────────────────────┐  │
│   │         ORGANİZASYON KATMANI                   │  │
│   │  Tenant İzolasyonu · RBAC · Kota Yönetimi      │  │
│   └────────────────────────────────────────────────┘  │
│                                                        │
│   ┌────────────────────────────────────────────────┐  │
│   │         FİNANSAL KATMAN                        │  │
│   │  Abonelik · Kullanım · Fatura · Komisyon       │  │
│   └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

### 8.2 Müşteri Segmentasyonu & Plan Yapısı

| Segment | Plan | Sunucu | AI Token | Özellikler |
|---------|------|--------|----------|------------|
| Bireysel / Startup | Starter | 1-3 | 10K/ay | Temel panel, email destek |
| Ajans / KOBİ | Professional | 5-20 | 100K/ay | Çoklu organizasyon, API, öncelikli destek |
| Kurum / Enterprise | Enterprise | Sınırsız | Sınırsız | SSO, SLA, dedicated support, custom SLA |
| Bayii / White Label | Reseller | Sınırsız | Sınırsız | Kendi markası, alt müşteri yönetimi |

---

## 9. Stratejik Yol Haritası — 12 Aylık Master Plan

### 🟢 Faz 5 — Temel Platform (Ay 1-3)
> **Tema:** Organizasyon + Paket Motoru — çok kiracılı temeli atma

| # | Görev | Motor | Effort |
|---|-------|-------|--------|
| 1 | Organization modeli + migration | Organizasyon | 1 hafta |
| 2 | Tenant middleware + row-level izolasyon | Organizasyon | 1 hafta |
| 3 | 2FA (TOTP) entegrasyonu | Kurumsal Güvenlik | 3 gün |
| 4 | API Token sistemi | Kurumsal Güvenlik | 3 gün |
| 5 | Plan & Subscription modelleri | Finansal | 1 hafta |
| 6 | ResourceQuota + LXD hard limit | Kaynak Uygulama | 1 hafta |
| 7 | SSH Key yönetimi (CRUD) | Kurumsal Güvenlik | 3 gün |
| 8 | Docker container yönetimi (temel) | Deneyim | 1 hafta |
| 9 | 1-Click Template yapısı (ilk 2 paket) | Deneyim | 1 hafta |
| 10 | PostgreSQL migration (SQLite→PG) | Performans | 3 gün |
| 11 | Celery + Redis temel entegrasyonu | Performans | 1 hafta |
| 12 | Dashboard UI yenileme | Deneyim | 1 hafta |

**Faz 5 Çıktıları:**
- ✅ Çok kiracılı mimari çalışır durumda
- ✅ 2FA + API Token ile güvenlik seviyesi enterprise
- ✅ Temel abonelik yapısı hazır
- ✅ İlk 2 business template yayında
- ✅ Celery ile arka plan görevleri dağıtık

---

### 🟡 Faz 6 — AI Gateway + Kullanım Faturalandırma (Ay 3-6)
> **Tema:** AI servisi sunma + kullanım bazlı gelir modeli

| # | Görev | Motor | Effort |
|---|-------|-------|--------|
| 1 | AI Model Registry | AI Platform | 1 hafta |
| 2 | AI API Key yönetimi | AI Platform | 3 gün |
| 3 | AI Proxy endpoint + token sayımı | AI Platform | 1 hafta |
| 4 | Rate limiting (plan bazlı) | AI Platform | 3 gün |
| 5 | Provider load balancing + failover | AI Platform | 1 hafta |
| 6 | Usage metering servisi | Finansal | 1 hafta |
| 7 | Fatura oluşturma + PDF export | Finansal | 1 hafta |
| 8 | Stripe/Iyzico entegrasyonu | Finansal | 1 hafta |
| 9 | SSO (SAML/OIDC) | Kurumsal Güvenlik | 1 hafta |
| 10 | Immutable audit logs (hash chain) | Kurumsal Güvenlik | 3 gün |
| 11 | WebSocket streaming (metrikler) | Performans | 1 hafta |
| 12 | Kalan 3 business template | Deneyim | 1 hafta |
| 13 | Gelir dashboard'u (MRR, ARR, churn) | Finansal | 1 hafta |

**Faz 6 Çıktıları:**
- ✅ AI Gateway canlı — müşteriler API ile model kullanabiliyor
- ✅ Token bazlı faturalandırma çalışıyor
- ✅ Ödeme altyapısı aktif (Stripe + Iyzico)
- ✅ 5 business template yayında
- ✅ Gerçek zamanlı metrik streaming

---

### 🔴 Faz 7 — White Label + Marketplace (Ay 6-12)
> **Tema:** Platform etkisi yaratma — bayi ağı + geliştirici ekosistemi

| # | Görev | Motor | Effort |
|---|-------|-------|--------|
| 1 | White label altyapısı (logo, domain, tema) | Deneyim | 2 hafta |
| 2 | Bayi (reseller) paneli | Organizasyon | 2 hafta |
| 3 | Alt müşteri yönetimi | Organizasyon | 1 hafta |
| 4 | Komisyon paylaşım motoru | Finansal | 1 hafta |
| 5 | Developer marketplace (3rd party app) | Deneyim | 2 hafta |
| 6 | Marketplace API + SDK | Deneyim | 2 hafta |
| 7 | SIEM export (Splunk/ELK) | Kurumsal Güvenlik | 1 hafta |
| 8 | GraphQL API (opsiyonel) | Performans | 2 hafta |
| 9 | Kubernetes desteği (temel) | Kaynak Uygulama | 2 hafta |
| 10 | Multi-region desteği | Performans | 2 hafta |
| 11 | SLA yönetimi + uptime garantisi | Finansal | 1 hafta |
| 12 | IP allowlist + session yönetimi | Kurumsal Güvenlik | 1 hafta |

**Faz 7 Çıktıları:**
- ✅ Bayiler kendi markaları altında platform sunabiliyor
- ✅ 3rd party geliştiriciler uygulama yayınlayabiliyor
- ✅ Enterprise müşteriler SIEM entegrasyonu yapabiliyor
- ✅ Platform etkisi başlıyor — ağ etkisi ile büyüme

---

## 10. Boşluk Analizi — Mevcut vs Hedef

| Alan | Mevcut | Hedef | Gap Seviyesi |
|------|--------|-------|-------------|
| Multi-Tenancy | ❌ Yok | Organization + row-level izolasyon | 🔴 Kritik |
| Kaynak Limitleri | ❌ Yok | LXD hard limit + SSH sandbox | 🔴 Kritik |
| AI Servisi | ❌ Yok | AI Gateway + token billing | 🟡 Stratejik |
| Faturalandırma | ❌ Yok | Subscription + metering + payment | 🔴 Kritik |
| 2FA | ❌ Yok | TOTP (Google Auth) | 🔴 Kritik |
| API Token | ❌ Yok | Scoped API token sistemi | 🔴 Kritik |
| SSO | ❌ Yok | SAML + OIDC | 🟡 Stratejik |
| Docker | ❌ Yok | Container lifecycle yönetimi | 🟡 Stratejik |
| Görev Kuyruğu | ⚠️ APScheduler | Celery + Redis | 🟡 Stratejik |
| Veritabanı | ⚠️ SQLite | PostgreSQL | 🟡 Stratejik |
| WebSocket | ⚠️ Sadece terminal | Tüm gerçek zamanlı veriler | 🟢 İyileştirme |
| White Label | ❌ Yok | Tam marka özelleştirme | 🟢 Gelecek |
| Marketplace | ⚠️ Temel market | Developer marketplace + SDK | 🟢 Gelecek |

---

## 11. Marka Konumlandırma

### Eski Konumlandırma
> "Sunucu yönetim paneli" — teknik araç, sınırlı değer algısı.

### Yeni Konumlandırma
> **"Infrastructure Business Engine"** — altyapıyı hizmete, hizmeti gelire
> dönüştüren, AI destekli, iki taraflı iş platformu.

**Değer Önerisi Piramidi:**
```
         ┌─────────────┐
         │   GELİR     │  ← Faturalandırma, komisyon, MRR
         │   MOTORU    │
         ├─────────────┤
         │     AI      │  ← Model gateway, token billing
         │  PLATFORM   │
         ├─────────────┤
         │   İŞ        │  ← Template'ler, marketplace
         │ ŞABLONLARİ  │
         ├─────────────┤
         │  ORG +      │  ← Multi-tenant, RBAC, kota
         │  GÜVENLİK   │
         ├─────────────┤
         │  ALTYAPI    │  ← Sunucu, ağ, depolama, izleme
         │  YÖNETİMİ   │
         └─────────────┘
```

**Hedef Müşteri Mesajları:**
- **Startup'a:** "GPU sunucunu kur, AI modelini yayınla, API anahtarını sat — 15 dakikada."
- **Ajansa:** "Müşterilerinin sunucularını tek panelden yönet, her birine özel kota ver."
- **Kuruma:** "SSO ile giriş, SIEM ile uyumluluk, SLA ile garanti — kurumsal standartlarda."
- **Bayiye:** "Kendi markanla hosting + AI platformu sun, komisyonunu al."

---

## 12. İlgili Dokümanlar

| Doküman | İçerik |
|---------|--------|
| [README.md](README.md) | Genel tanıtım ve kurulum |
| [KULLANIM_KILAVUZU.md](KULLANIM_KILAVUZU.md) | Son kullanıcı kılavuzu |
| [SANAL_MAKINE_YONETIMI.md](SANAL_MAKINE_YONETIMI.md) | KVM/LXD sanallaştırma |
| [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) | Ürün yol haritası |
| [requirements.txt](requirements.txt) | Python bağımlılıkları |
| [docs/AI_ANAYASASI.md](docs/AI_ANAYASASI.md) | AI Anayasası — etik, güvenlik, veri politikası |

---

> **Son Güncelleme:** Haziran 2025
> **Durum:** Faz 1-4 tamamlandı · Faz 5 planlaması hazır · 6 motor tanımlandı
> **Sonraki Aksiyon:** Faz 5 — Organization modeli + 2FA + Celery entegrasyonu ile başla


---

# Teknik Sprint Takibi

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

## Sonraki Sprint Önerisi (Faz 6 — Ölçekleme ve İleri Düzey)

- [ ] Org yönetim paneli (admin UI: org CRUD + kullanıcı-org atama)
- [ ] Org bazlı kaynak kotası UI (plan limitleri)
- [ ] Container yönetimi (Docker/Podman entegrasyonu)
- [ ] Faturalandırma sistemi (WHMCS benzeri)
- [ ] API gateway / rate limiting
- [ ] Log aggregation (merkezi log yönetimi)
- [ ] AI destekli anomali tespiti
- [ ] PostgreSQL'e geçiş (production DB)

## Sonuç

Faz 1 (Güvenlik), Faz 2 (Mimari), Faz 3 (Test & Kalite), Faz 4 (Monitoring & Otomasyon) ve **Faz 5 (Multi-Tenant İzolasyonu)** başarıyla tamamlanmıştır. Proje **EmareCloud v1.1 — Multi-Tenant Edition** olarak tam multi-tenant veri izolasyonuna sahiptir. 65+ endpoint'te org_id bazlı row-level izolasyon uygulanmış, `_build_tenant_query(model)` merkezi fonksiyonu ile tüm modeller tenant-aware hale getirilmiştir. 107 sunucusunda deploy edilmiş ve test ile doğrulanmıştır.
