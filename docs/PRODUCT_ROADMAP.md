# EmareCloud — Ürün Yol Haritası

> **Not:** Bu belge ürün vizyonu ve hedef sürümleri tanımlar. Güncel panel özellikleri (sunucu yönetimi, pazar, AI araçları, depolama, sanallaştırma) için **[README.md](README.md)** ve **[KULLANIM_KILAVUZU.md](KULLANIM_KILAVUZU.md)** dosyalarına bakın.

## 🏢 Vizyon
Modern, hafif, güvenli altyapı yönetim paneli. Küçük-orta ölçekli hosting firmaları,
freelancer sysadmin'ler, ajanslar ve AI/LLM sunucu yöneten ekipler için tasarlandı.

---

## Faz 1: Secure Core Edition ✅ (v1.0.0)
**Hedef:** Güvenli, tek sunucu-çoklu kullanıcı yönetim paneli.

### Tamamlanan Özellikler
- [x] **Auth Sistemi** — Flask-Login, oturum tabanlı kimlik doğrulama
- [x] **RBAC** — 4 seviyeli rol sistemi (Super Admin, Admin, Operator, Read-only)
- [x] **Yetki Matrisi** — 25+ granüler yetki, rol bazlı erişim kontrolü
- [x] **Secret Yönetimi** — AES-256-GCM ile SSH şifre şifreleme
- [x] **Komut Güvenliği** — Allowlist/blocklist, rol bazlı komut erişimi
- [x] **Audit Log** — Tüm kritik işlemlerin kaydı
- [x] **Rate Limiting** — Brute force koruması (5 deneme / 5 dakika)
- [x] **CSRF Koruması** — Form tabanlı isteklerde token doğrulama
- [x] **Güvenlik Header'ları** — X-Content-Type-Options, X-Frame-Options, XSS Protection
- [x] **DB Migrasyonu** — JSON config'den SQLAlchemy DB'ye otomatik aktarım
- [x] **Docker Desteği** — Dockerfile, docker-compose, gunicorn
- [x] **Test Altyapısı** — pytest, auth/RBAC testleri

### Teknik Altyapı
| Katman | Teknoloji |
|--------|-----------|
| Backend | Flask 3.0, Flask-SocketIO |
| Veritabanı | SQLAlchemy (SQLite/PostgreSQL) |
| Şifreleme | AES-256-GCM (cryptography) |
| Auth | Flask-Login, session-based |
| SSH | Paramiko |
| Frontend | Vanilla JS, CSS Variables |
| Deploy | Docker, Gunicorn |

---

## Faz 2: Pro Edition (v2.0.0) 🔜
**Hedef:** Multi-sunucu yönetimi, gelişmiş izleme, otomasyon.

### Tamamlanan Özellikler (Monitoring & Otomasyon)
- [x] **Alert Sistemi** — CPU/RAM/disk/ağ eşik alarmları, 6 koşul operatörü, cooldown
- [x] **Webhook Entegrasyonu** — Slack, Discord, SMTP e-posta, özel HTTP
- [x] **Zamanlanmış Görevler** — Cron tabanlı planlı SSH komutları
- [x] **Backup Yönetimi** — Otomatik yedekleme, tar/gzip/bzip2, retention
- [x] **Metrik Geçmişi** — CPU, RAM, disk, ağ, load snapshot'ları, trend analizi
- [x] **Monitoring Dashboard** — 6 sekmeli UI (Genel Bakış, Alarmlar, Webhook, Görevler, Yedekleme, Trendler)

### Planlanan Özellikler
- [ ] **2FA (TOTP)** — Google Authenticator ile iki faktörlü kimlik doğrulama
- [ ] **API Token Sistemi** — REST API erişimi için token yönetimi
- [ ] **SSH Key Desteği** — Şifre yerine SSH key ile bağlantı
- [ ] **Sunucu Grupları** — Tag ve grup bazlı sunucu organizasyonu
- [ ] **Toplu İşlemler** — Birden fazla sunucuya aynı anda komut çalıştırma
- [ ] **Dashboard Widget'ları** — Özelleştirilebilir dashboard

---

## Faz 3: Enterprise Edition (v3.0.0) � DEVAM EDİYOR
**Hedef:** Kurumsal ölçekte çoklu-kiracı (multi-tenant) yönetim.

### Tamamlanan Özellikler
- [x] **Multi-Tenant Veri İzolasyonu** — Organizasyon bazlı row-level izolasyon (65+ endpoint, org_id FK)
- [x] **Tenant Middleware** — Request bazlı g.tenant_id çözümleme, super admin global erişim
- [x] **Merkezi Query Builder** — `_build_tenant_query(model)` tüm modeller için tenant filtre
- [x] **Migration Script** — Mevcut verileri organizasyona atama (`migrate_tenant.py`)

### Planlanan Özellikler
- [ ] **Org Yönetim Paneli** — Admin UI ile organizasyon CRUD (oluştur/düzenle/sil)
- [ ] **Kullanıcı-Org Atama UI** — Kullanıcıları organizasyona ata/çıkar
- [ ] **Org Bazlı Kaynak Kotası** — Plan limitleri (sunucu sayısı, kullanıcı sayısı)
- [ ] **LDAP/SAML SSO** — Kurumsal kimlik doğrulama entegrasyonu
- [ ] **Terraform Entegrasyonu** — Infrastructure as Code desteği
- [ ] **Kubernetes Yönetimi** — K8s cluster izleme ve yönetim
- [ ] **Compliance Raporları** — SOC2, ISO27001 uyumluluk raporları
- [ ] **Gelişmiş Audit** — Detaylı olay analizi ve dışa aktarım
- [ ] **Plugin Sistemi** — Üçüncü parti eklenti desteği
- [ ] **White-label** — Marka özelleştirme (logo, renk, domain)
- [ ] **HA (High Availability)** — Aktif-pasif cluster desteği

---

## Faz 4: Provider Edition (v4.0.0) 📋
**Hedef:** "Hosting işini 7 günde kur" — Provider için SaaS-in-a-box.

### Planlanan Özellikler
- [ ] **Organization Katmanı** — Provider entity modeli
- [ ] **Customer CRUD** — Provider'a bağlı müşteri yönetimi
- [ ] **Paket Şablonları** — CPU/RAM/Disk kaynak paketleri oluşturma
- [ ] **Kaynak Atama** — Sunucu → müşteri mapping, cgroups/LXD quota
- [ ] **Müşteri Self-Service Portal** — Kısıtlı panel görünümü
- [ ] **Basit Faturalandırma** — Abonelik/plan yönetimi

---

## Faz 5: Marketplace Edition (v5.0.0) 📋
**Hedef:** Two-sided infrastructure & AI compute marketplace.

### Planlanan Özellikler
- [ ] **White-Label Mode** — Logo, renk, domain, branding özelleştirme
- [ ] **Provider Discovery** — Provider vitrin/listeleme sayfası
- [ ] **Komisyon Motoru** — Her satıştan %10-20 platform payı
- [ ] **Payment Gateway** — Stripe/Iyzico entegrasyonu, komisyon split
- [ ] **AI Compute Marketplace** — GPU kiralama (spot/on-demand)
- [ ] **Provider Rating** — Review ve uptime SLA izleme
- [ ] **Cross-Tenant Routing** — Multi-provider yük dengeleme

---

## 🎯 Hedef Kitle
| Segment | Özellik |
|---------|---------|
| Küçük Hosting Firmaları | 5-50 sunucu, 2-5 teknisyen |
| Freelancer SysAdmin'ler | Çoklu müşteri sunucu yönetimi |
| Ajanslar | WordPress/e-ticaret sunucu yönetimi |
| AI/LLM Ekipleri | GPU sunucu yönetimi, model deployment |
| Homelab & Startup | Hızlı kurulum, düşük maliyet |

---

## 📦 Kurulum

### Hızlı Başlangıç (Development)
```bash
git clone https://github.com/emarecloud/panel.git
cd panel
pip install -r requirements.txt
python app.py
```

### Docker ile Production
```bash
cp .env.example .env
# .env dosyasını düzenleyin (SECRET_KEY, MASTER_KEY, admin şifresi)
docker-compose up -d
```

### İlk Giriş
- URL: `http://localhost:5555`
- Kullanıcı: `admin`
- Şifre: `.env` dosyasındaki `DEFAULT_ADMIN_PASSWORD` veya `admin123`
- **⚠️ İlk girişte şifrenizi değiştirin!**

---

## 🔒 Güvenlik Modeli

### Rol Hiyerarşisi
```
Super Admin (100) → Tam yetki, kullanıcı yönetimi
    └─ Admin (75) → Sunucu CRUD, yapılandırma
        └─ Operator (50) → Komut çalıştırma, servis yönetimi
            └─ Read-only (10) → Sadece görüntüleme
```

### Komut Güvenlik Katmanları
1. **Global Blocklist** — rm -rf /, fork bomb, reverse shell → %100 engel
2. **Rol Allowlist** — Operator: bilgi + servis komutları
3. **Admin Genişletilmiş** — apt install, docker, dosya işlemleri
4. **Super Admin** — Blocklist hariç her şey
5. **Audit Log** — Her komut kayıt altında

### Şifreleme
- SSH şifreleri: AES-256-GCM
- Master key: Ortam değişkeni veya `.master.key` dosyası
- Oturum çerezleri: HttpOnly, SameSite=Lax, Secure (prod)
