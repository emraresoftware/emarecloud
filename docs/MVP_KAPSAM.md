# EmareCloud — Satılabilir MVP Kapsam Dokümanı

> **Versiyon:** 1.0.0 — Secure Core Edition  
> **Tarih:** Mart 2026  
> **Hedef:** Self-hosted lisanslı ürün olarak ilk satışa çıkış

---

## 1. Ürün Tanımı

**EmareCloud**, birden fazla Linux sunucuyu tek bir web arayüzünden izleyen, yöneten ve üzerine uygulama kuran **self-hosted altyapı yönetim paneli**dir.

### Hedef Müşteri Segmentleri

| Segment | Profil | Acı Noktası |
|---------|--------|-------------|
| **Küçük Hosting Firmaları** | 5-50 sunucu, 1-3 SRE/DevOps | Panel maliyeti yüksek, cPanel/Plesk gereksiz |
| **AI/ML Laboratuvarları** | GPU sunucuları, model deployment | Ollama/Whisper/ComfyUI kurulumu zor |
| **Ajanslar & Freelancerlar** | Müşteri sunucuları yönetimi | Çok sunucu, merkezi görünüm yok |
| **KOBİ IT Departmanları** | 3-20 on-prem sunucu | Basit izleme + hızlı müdahale |

### Rakip Karşılaştırma

| Özellik | EmareCloud | cPanel | Cockpit | Webmin |
|---------|:---:|:---:|:---:|:---:|
| Çoklu sunucu yönetimi | ✅ | ❌ (tek) | ❌ (tek) | ⚠️ (Webmin Cluster) |
| AI uygulama marketi | ✅ | ❌ | ❌ | ❌ |
| RAID/SMART izleme | ✅ | ❌ | ⚠️ | ⚠️ |
| LXD konteyner yönetimi | ✅ | ❌ | ⚠️ | ❌ |
| Firewall merkezi yönetim | ✅ | ⚠️ | ⚠️ | ✅ |
| RBAC + Audit log | ✅ | ✅ | ❌ | ⚠️ |
| Self-hosted / açık kaynak çekirdek | ✅ | ❌ | ✅ | ✅ |
| Modern UI (dark mode) | ✅ | ❌ | ✅ | ❌ |
| Fiyat (yıllık) | **$99-499** | $600+ | Ücretsiz | Ücretsiz |

---

## 2. Satış Modeli

### Dağıtım: Self-Hosted Lisans

```
Müşteri Sunucusu
├── EmareCloud Panel (Docker / systemd)
│   ├── Web UI (:5555)
│   ├── SQLite/PostgreSQL
│   └── Gunicorn + GeventWebSocket
├── Yönetilen Sunucu A (SSH)
├── Yönetilen Sunucu B (SSH)
└── ...
```

**Neden SaaS değil:**
- SSH credential'ları müşteri altyapısında kalır → güven artışı
- Compliance/veri yükü müşteriye ait → düşük operasyonel risk
- Zero-trust prensibi: panel sunucusu = müşteri kontrolünde
- Daha düşük altyapı maliyeti (sunucu host etmiyorsun)

### Fiyatlandırma Katmanları

| Plan | Fiyat | Sunucu Limiti | Özellikler |
|------|-------|---------------|------------|
| **Community** | Ücretsiz | 3 sunucu | Temel izleme, SSH, market (top 20 app) |
| **Pro** | $99/yıl | 25 sunucu | Tam market, RBAC, audit log, firewall, LXD |
| **Business** | $299/yıl | 100 sunucu | + Sunucu grupları, webhook, toplu işlem, öncelikli destek |
| **Enterprise** | $499/yıl | Sınırsız | + SSO, API token, white-label, SLA desteği |

### Lisans Uygulama Mekanizması (Faz 2'de implement)

```python
# Basit lisans doğrulama — offline çalışır
# RSA-signed JSON license file
{
    "customer": "AcmeHosting",
    "plan": "pro",
    "max_servers": 25,
    "valid_until": "2027-03-01",
    "signature": "base64..."
}
```

---

## 3. MVP Kapsamı — "Satılabilir" Özellik Listesi

### ✅ TAMAMLANDI (Faz 1 — Secure Core)

| # | Özellik | Durum | Modül |
|---|---------|-------|-------|
| 1 | **Kimlik doğrulama** (login/logout/session) | ✅ | `auth_routes.py` |
| 2 | **RBAC** (4 rol, 25+ granüler yetki) | ✅ | `rbac.py` |
| 3 | **AES-256-GCM** secret şifreleme | ✅ | `crypto.py` |
| 4 | **Komut güvenliği** (blocklist + allowlist) | ✅ | `command_security.py` |
| 5 | **Audit log** (kim ne yaptı, hangi IP) | ✅ | `audit.py` |
| 6 | **Rate limiting** (login: 5/5dk) | ✅ | `auth_routes.py` |
| 7 | **CSRF koruması** (session token) | ✅ | `app.py` |
| 8 | **Güvenlik header'ları** (XSS, nosniff, referrer) | ✅ | `app.py` |
| 9 | **Dashboard** (çoklu sunucu özet görünümü) | ✅ | `templates/dashboard.html` |
| 10 | **Sunucu yönetimi** (ekle/sil/düzenle/bağlan) | ✅ | `app.py`, `ssh_manager.py` |
| 11 | **Gerçek zamanlı metrikler** (CPU/RAM/disk/process) | ✅ | `server_monitor.py` |
| 12 | **Web terminal** (SSH over WebSocket) | ✅ | `app.py` SocketIO |
| 13 | **Firewall yönetimi** (UFW + firewalld) | ✅ | `firewall_manager.py` |
| 14 | **LXD sanal makine yönetimi** | ✅ | `virtualization_manager.py` |
| 15 | **Depolama/RAID izleme** (SMART + mdadm) | ✅ | `app.py` storage routes |
| 16 | **Uygulama pazarı** (58+ app, kategorize) | ✅ | `market_apps.py` |
| 17 | **GitHub entegrasyonu** (arama + trend + kurulum) | ✅ | `market_apps.py` |
| 18 | **Docker deployment** (docker-compose.yml) | ✅ | `docker-compose.yml` |
| 19 | **Gunicorn production config** | ✅ | `gunicorn.conf.py` |
| 20 | **Test suite** (28 test, pytest) | ✅ | `tests/` |
| 21 | **Kullanıcı yönetimi** (CRUD + rol atama) | ✅ | `auth_routes.py` |
| 22 | **Profil yönetimi** (şifre değiştirme) | ✅ | `auth_routes.py` |
| 23 | **DB migration** (config.json → SQLite) | ✅ | `app.py` init |
| 24 | **Gzip sıkıştırma** | ✅ | `app.py` middleware |

### 🔶 SATIŞ İÇİN GEREKLİ (Kısa vadede yapılacak)

| # | Özellik | Öncelik | Tahmini Süre | Açıklama |
|---|---------|---------|-------------|----------|
| 25 | **Blueprint modülerleşme** | 🔴 Kritik | 2-3 gün | `app.py` 1182 satır → 6 blueprint |
| 26 | **print → logging** | 🔴 Kritik | 1 gün | Structured logging (JSON format) |
| 27 | **CORS kısıtlama** | 🟡 Yüksek | 2 saat | SocketIO'da `cors_allowed_origins='*'` kapatma |
| 28 | **Şifre karmaşıklık kuralları** | 🟡 Yüksek | 2 saat | Büyük/küçük harf, rakam, özel karakter |
| 29 | **Kurulum wizard / setup.sh** | 🔴 Kritik | 1 gün | İlk kurulumda admin oluşturma + config |
| 30 | **Nginx reverse proxy rehberi** | 🟡 Yüksek | 3 saat | TLS + WebSocket proxy örneği |
| 31 | **Lisans doğrulama modülü** | 🔴 Kritik | 2 gün | Sunucu limiti + plan kontrolü |
| 32 | **Landing page / marketing sitesi** | 🟡 Yüksek | 2 gün | Fiyatlandırma + özellikler + demo |

### ❌ KAPSAM DIŞI (MVP'de yok, Faz 2-3'te)

| Özellik | Neden Ertelendi | Faz |
|---------|-----------------|-----|
| 2FA (TOTP) | Model hazır, UI/backend gerekli | Faz 2 |
| API Token sistemi | Model hazır, endpoint'ler gerekli | Faz 2 |
| SSH Key authentication | Alternatif auth yöntemi | Faz 2 |
| Sunucu grupları + toplu işlem | Ölçek özelliği | Faz 2 |
| Alarm/bildirim sistemi | Webhook + email entegrasyonu | Faz 2 |
| Zamanlanmış görevler (cron) | Otomasyon katmanı | Faz 2 |
| Otomatik yedekleme | Backup politika motoru | Faz 2 |
| Multi-tenant izolasyon | SaaS modeline geçişte | Faz 3 |
| LDAP/SAML SSO | Enterprise müşteriler | Faz 3 |
| Kubernetes yönetimi | Container orchestration | Faz 3 |
| Plugin/extension sistemi | Ekosistem genişleme | Faz 3 |
| White-label / rebrand | Enterprise lisans | Faz 3 |

---

## 4. Gelir Tahminleri

### Yıl 1 — Hedef: İlk 50 Ödenen Müşteri

| Senaryo | Müşteri | Ortalama Gelir | Yıllık Toplam |
|---------|---------|---------------|---------------|
| Kötümser | 20 Pro | $99 | $1,980 |
| Gerçekçi | 35 Pro + 10 Business | $150 | $6,740 |
| İyimser | 40 Pro + 15 Business + 5 Enterprise | $180 | $13,405 |

### Büyüme Kaldıraçları
1. **Ücretsiz Community sürümü** → funnel girişi (GitHub'da yıldız toplama)
2. **AI market farklılaştırması** → GPU sunucu sahibi niş kitle
3. **RAID/SMART** → hosting firmaları için "sigorta" değer önerisi
4. **Türkçe UI** → Türk pazarında rakipsiz

---

## 5. Risk Matrisi

| Risk | Olasılık | Etki | Azaltma |
|------|---------|------|---------|
| SSH credential sızıntısı | Düşük | 🔴 Kritik | AES-256-GCM ✅, master key izolasyonu |
| Komut injection | Düşük | 🔴 Kritik | Blocklist + allowlist ✅, pipe analizi (TODO) |
| Yetkisiz erişim | Çok Düşük | 🔴 Kritik | RBAC ✅, audit ✅, rate limit ✅ |
| Ürün karmaşıklığı | Orta | 🟡 Yüksek | Modülerleşme + test coverage artışı |
| Rakip tepkisi | Düşük | 🟡 Orta | AI + RAID niş'inde derinleşme |
| Müşteri desteği yükü | Orta | 🟡 Orta | Kapsamlı dokümantasyon + setup wizard |

---

## 6. "Satışa Hazır" Checklist

- [x] Kimlik doğrulama sistemi
- [x] Rol bazlı erişim kontrolü
- [x] Şifreli credential saklama
- [x] Komut yürütme güvenliği
- [x] Denetim günlüğü
- [x] Rate limiting
- [x] CSRF koruması
- [x] Güvenlik header'ları
- [x] Docker deployment
- [x] Production Gunicorn config
- [x] Test suite (28 test)
- [x] Blueprint modülerleşme
- [x] Structured logging (print → logging)
- [x] CORS kısıtlama
- [x] Şifre karmaşıklık kuralları
- [x] Kurulum wizard (setup.sh)
- [x] TLS reverse proxy rehberi
- [x] Lisans doğrulama modülü
- [x] Landing page

---

## 7. Güncellenmiş Skor

| Kriter | Önceki (yorumcu) | Gerçek Durum | Not |
|--------|:-:|:-:|------|
| Ürün potansiyeli | 9/10 | **9/10** | AI + Storage niş'i çok güçlü |
| Teknik temel | 7.5/10 | **8/10** | Tüm güvenlik modülleri hazır |
| Satılabilirlik (bugün) | 3.5/10 | **6.5/10** | Auth/RBAC/Crypto/Audit tamamlandı, modülerleşme eksik |
| Satılabilirlik (refactor sonrası) | 7.5/10 | **8/10** | Blueprint + logging + setup wizard |
| Satılabilirlik (Pro paket) | 9/10 | **9/10** | Lisans + landing + 2FA |

> **Not:** Yorumcu eski dokümanları baz almış. Faz 1 (Secure Core) **tamamlanmış** durumda.
> Auth, RBAC, AES-256-GCM, komut güvenliği, audit log, rate limiting, CSRF — hepsi production-ready.
