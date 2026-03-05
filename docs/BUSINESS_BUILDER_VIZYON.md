# EmareCloud OS — Business Builder Vizyon Dokümanı

> "Sunucuyu yönetmek değil, iş kurmayı kolaylaştırmak."

---

## 1. Marka Konumlandırma

### Eski Konum
> "Çoklu sunucu yönetim paneli"

### Yeni Konum
> **"Self-Hosted Infrastructure-as-a-Business Platform"**
>
> EmareCloud, teknik altyapıyı iş fırsatına dönüştüren açık kaynak platformdur.
> Kendi sunucunuzda, kendi markanızla, kendi işinizi kurun.

### Tek Cümle Tanım
> EmareCloud — Kendi hosting şirketinizi, AI API servisinizi veya SaaS altyapınızı
> kurabileceğiniz, uçtan uca self-hosted iş platformu.

---

## 2. Vizyon

```
"Her girişimcinin, teknik bilgisi ne olursa olsun,
kendi dijital altyapı işini 30 dakikada kurabilmesi."
```

### Misyon

EmareCloud olarak misyonumuz:

1. **Demokratikleştirmek** — Büyük şirketlere özgü altyapı araçlarını herkese açmak
2. **Basitleştirmek** — Karmaşık sunucu yönetimini sezgisel arayüzle sunmak
3. **Güçlendirmek** — Müşterilerimize kendi işlerini kurma araçları vermek
4. **Bağımsızlaştırmak** — Cloud vendor lock-in'den kurtarmak, self-hosted özgürlük

---

## 3. Hedef Kitle

### Birincil Kitle (Faz A)

| Segment | Profil | Acı Noktası | EmareCloud Çözümü |
|---------|--------|-------------|---------------------|
| **DevOps Mühendisi** | 5-50 sunucu yönetiyor | SSH karmaşası, dağınık araçlar | Tek panel, RBAC, market |
| **Küçük Hosting Şirketi** | 10-100 müşterisi var | cPanel pahalı, eski, kısıtlı | Modern panel, white-label, Docker |
| **Startup CTO** | Altyapı kuruyor | AWS faturası yüksek, karmaşık | Self-hosted, maliyet kontrolü |

### İkincil Kitle (Faz B)

| Segment | Profil | Acı Noktası | EmareCloud Çözümü |
|---------|--------|-------------|---------------------|
| **AI Girişimci** | Model serve etmek istiyor | OpenAI pahalı, veri kontrolü yok | Kendi model API'si, self-hosted |
| **Web Ajansı** | Müşteri siteleri host ediyor | Her müşteri için ayrı ayar | Otomatik domain, SSL, deploy |
| **Freelancer** | Müşteri projeleri | Basit ve ucuz panel yok | Ücretsiz başlangıç, kolay kullanım |

### Üçüncül Kitle (Faz C)

| Segment | Profil | Acı Noktası | EmareCloud Çözümü |
|---------|--------|-------------|---------------------|
| **SaaS Geliştirici** | Multi-tenant uygulama deploy | Deployment karmaşası | Docker deploy, env yönetimi |
| **Eğitim Kurumu** | Lab ortamları yönetimi | Her öğrenciye ayrı ortam | LXD container, kota yönetimi |
| **Kurumsal IT** | İç araçlar host | Güvenlik, izolasyon | RBAC, audit, on-premise |

---

## 4. Ürün Katmanları

```
╔══════════════════════════════════════════════════════════════╗
║                    EmareCloud OS                           ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  ┌─────────────────────────────────────────────────────┐     ║
║  │            🏢 İŞ KURMA KATMANI (Faz B-C)            │     ║
║  │                                                     │     ║
║  │  Hosting Builder │ AI Platform │ SaaS Deployer      │     ║
║  │  Müşteri Yönetim │ API Gateway │ Docker Deploy      │     ║
║  │  Paket & Fatura  │ Token Mgmt  │ Domain & SSL       │     ║
║  └─────────────────────────────────────────────────────┘     ║
║                          ▲                                   ║
║  ┌─────────────────────────────────────────────────────┐     ║
║  │           🔐 TİCARİ KATMAN (Tamamlandı)             │     ║
║  │                                                     │     ║
║  │  RBAC (4 seviye) │ AES-256 Şifreleme │ Lisans       │     ║
║  │  Audit Logging   │ Brute-force Koruma │ CSRF         │     ║
║  │  Güvenlik Headers│ Session Yönetimi   │ White-label  │     ║
║  └─────────────────────────────────────────────────────┘     ║
║                          ▲                                   ║
║  ┌─────────────────────────────────────────────────────┐     ║
║  │           🧱 ALTYAPI KATMANI (Tamamlandı)           │     ║
║  │                                                     │     ║
║  │  SSH Orchestration │ Web Terminal │ Metrik İzleme   │     ║
║  │  Güvenlik Duvarı   │ LXD/VM Mgmt │ RAID & SMART    │     ║
║  │  58+ App Market    │ Depolama    │ Modüler Mimari   │     ║
║  └─────────────────────────────────────────────────────┘     ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 5. Stratejik Yol Haritası

### Aşama 1: Infrastructure Control Panel (0-6 ay) ✅ ŞU AN

**Pazar konumu:** "Self-hosted infrastructure management panel"

**Hedef:** Erken benimseyiciler ve DevOps profesyonelleri

**Tamamlanan:**
- ✅ Secure Core (RBAC, AES-256, audit, CSRF)
- ✅ Modüler Blueprint mimarisi
- ✅ 58+ uygulama pazarı (AI dahil)
- ✅ LXD sanallaştırma
- ✅ RAID/SMART/depolama
- ✅ RSA-4096 lisans sistemi
- ✅ Landing page
- ✅ Setup wizard

**Fiyatlandırma:**
- Community: Ücretsiz (3 sunucu)
- Professional: $29/ay (25 sunucu)
- Enterprise: $99/ay (sınırsız)

**KPI:**
- 500+ GitHub yıldız
- 100+ aktif kurulum
- 10+ ödeme yapan müşteri

---

### Aşama 2: AI Platform Mode (6-12 ay)

**Pazar konumu:** "Self-hosted AI infrastructure platform"

**Hedef:** AI girişimciler, veri bilimciler, mahremiyetçi şirketler

**Yapılacaklar:**
- [ ] AI Gateway (OpenAI-uyumlu API)
- [ ] API key oluşturma/yönetimi
- [ ] Rate limiting (key/org bazlı)
- [ ] Token bazlı kullanım ölçümü
- [ ] Model health monitoring
- [ ] AI kullanım dashboard'u
- [ ] Streaming response desteği
- [ ] Billing hook (kullanım → fatura)

**Fiyatlandırma (AI eklenti):**
- AI Starter: +$19/ay (1 model, 10K istek)
- AI Pro: +$49/ay (5 model, 100K istek)
- AI Enterprise: +$149/ay (sınırsız)

**KPI:**
- 50+ AI API kullanıcı
- 1M+ aylık API isteği
- $5K+ MRR (AI geliri)

---

### Aşama 3: Hosting Builder (12-18 ay)

**Pazar konumu:** "Self-hosted business infrastructure platform"

**Hedef:** Hosting girişimcileri, web ajansları, freelancerlar

**Yapılacaklar:**
- [ ] Multi-tenant mimari
- [ ] Customer management
- [ ] Package manager
- [ ] Domain & SSL otomasyon
- [ ] Resource quota system
- [ ] Müşteri portalı (self-service)
- [ ] White-label (tam)
- [ ] Faturalandırma sistemi (Stripe + Iyzico)

**Fiyatlandırma:**
- Starter: $29/ay (5 sunucu, 3 kullanıcı)
- Growth: $99/ay (25 sunucu, 15 kullanıcı, 50 müşteri)
- Enterprise: $299/ay (sınırsız, white-label, özel destek)

**KPI:**
- 25+ hosting şirketi müşterisi
- $25K+ MRR
- 5+ white-label kurulum

---

### Aşama 4: SaaS Deployment Engine (18-24 ay)

**Pazar konumu:** "The self-hosted Heroku alternative"

**Hedef:** SaaS geliştiriciler, startup'lar

**Yapılacaklar:**
- [ ] Git-based deployment
- [ ] Docker Compose deploy UI
- [ ] Environment variable yönetimi
- [ ] Rolling restart & rollback
- [ ] Deploy log & monitoring
- [ ] Custom buildpack desteği
- [ ] CI/CD entegrasyonu (GitHub Actions, GitLab CI)

---

## 6. Rekabet Haritası

```
                    İş Kurma Yeteneği
                         ▲
                         │
              Plesk      │      EmareCloud OS
              ●──────────┼──────────●
                         │         (Hedef konum)
                         │
         cPanel ●        │
                         │
                         │        Railway ●
    CloudPanel ●─────────┼──────────● Coolify
                         │
              Portainer ●│
                         │
                         │
    ─────────────────────┼────────────────────► Modernlik
                         │
                     Webmin ●
```

### Detaylı Karşılaştırma

| Özellik | cPanel | Plesk | Coolify | Railway | **EmareCloud** |
|---------|--------|-------|---------|---------|-----------------|
| Self-hosted | ✅ | ✅ | ✅ | ❌ | ✅ |
| Multi-tenant | ✅ | ✅ | ❌ | ❌ | ✅ (planlanıyor) |
| Docker deploy | ❌ | Uzantı | ✅ | ✅ | ✅ (planlanıyor) |
| AI platform | ❌ | ❌ | ❌ | ❌ | ✅ |
| SSH terminal | ❌ | ✅ | ❌ | ❌ | ✅ |
| LXD yönetimi | ❌ | ❌ | ❌ | ❌ | ✅ |
| Modern UI | ❌ | Orta | ✅ | ✅ | ✅ |
| White-label | 💰 | 💰 | ❌ | ❌ | ✅ |
| App market | ❌ | ✅ | ❌ | ❌ | ✅ (58+) |
| Türkçe | ❌ | ✅ | ❌ | ❌ | ✅ |
| Açık kaynak | ❌ | ❌ | ✅ | ❌ | ✅ |
| Fiyat | $15+ | $11+ | Ücretsiz | $5+ | **Ücretsiz başlangıç** |

### Benzersiz Değer Önerisi (UVP)

> **"EmareCloud, kendi sunucunuzda hosting şirketi, AI API servisi veya SaaS altyapısı kurmanızı sağlayan tek açık kaynak platformdur."**

Hiçbir rakip bu üçünü birlikte sunmuyor:
1. ✅ Hosting business (müşteri + paket + fatura)
2. ✅ AI-as-a-Service (model API + billing)
3. ✅ SaaS deployment (Docker + domain + SSL)

---

## 7. Gelir Modeli

### Katmanlı Fiyatlandırma

```
┌──────────────────────────────────────────────────────────────┐
│                   EmareCloud Fiyatlandırma                  │
├──────────────┬──────────────┬──────────────┬─────────────────┤
│              │  Community   │   Growth     │   Enterprise    │
│              │  (Ücretsiz)  │   ($99/ay)   │   ($299+/ay)    │
├──────────────┼──────────────┼──────────────┼─────────────────┤
│ Sunucu       │ 3            │ 25           │ Sınırsız        │
│ Kullanıcı    │ 1            │ 15           │ Sınırsız        │
│ Müşteri      │ —            │ 50           │ Sınırsız        │
│ AI model     │ —            │ 5            │ Sınırsız        │
│ API istek/ay │ —            │ 100K         │ Sınırsız        │
│ White-label  │ —            │ Logo + Renk  │ Tam (badge yok) │
│ Destek       │ Community    │ E-posta      │ Özel kanal      │
│ SLA          │ —            │ %99.5        │ %99.9           │
├──────────────┼──────────────┼──────────────┼─────────────────┤
│ Hedef kitle  │ Geliştirici  │ Küçük şirket │ Hosting/ajans   │
│              │ & hobi       │ & startup    │ & kurumsal      │
└──────────────┴──────────────┴──────────────┴─────────────────┘
```

### Gelir Projeksiyonu (24 ay)

| Ay | Community | Growth | Enterprise | MRR | ARR |
|----|-----------|--------|-----------|-----|-----|
| 6  | 200       | 15     | 2         | $2,083 | $25K |
| 12 | 500       | 50     | 8         | $7,342 | $88K |
| 18 | 1,000     | 120    | 20        | $17,880 | $215K |
| 24 | 2,000     | 250    | 40        | $36,750 | $441K |

### Ek Gelir Kanalları

1. **Marketplace komisyon** — Ücretli eklentiler için %30 komisyon
2. **Profesyonel hizmetler** — Kurulum, migrasyon, özel geliştirme ($150/saat)
3. **Eğitim** — Video kurslar, sertifika programı
4. **Partner programı** — Hosting şirketlerine white-label lisans (toplu indirim)

---

## 8. Go-to-Market Stratejisi

### Kanal 1: Açık Kaynak + Community

- GitHub'da proje yayınlama
- Türkçe + İngilizce dokümantasyon
- Discord/Slack community
- YouTube tutorial serisi
- Blog: "cPanel'den EmareCloud'e Geçiş", "Kendi AI API Servisini Kur"

### Kanal 2: İçerik Pazarlama

- SEO: "self-hosted panel", "cpanel alternative", "self-hosted AI API"
- Karşılaştırma yazıları: "EmareCloud vs cPanel vs Plesk"
- Use case çalışmaları: "Ali hosting şirketini EmareCloud ile kurdu"

### Kanal 3: Topluluk ve Etkinlik

- Türkiye: DevFest, Webrazzi, Linux Kullanıcıları Derneği
- Global: ProductHunt launch, Hacker News, Reddit r/selfhosted
- Türk hosting forumları ve grupları

### Kanal 4: Stratejik Ortaklıklar

- VPS sağlayıcılar (Hetzner, Contabo, DigitalOcean) — "pre-installed EmareCloud" imajları
- Domain registrar'lar — Entegre kurulum
- Hosting forumları — Sponsorluk ve referans programı

---

## 9. Marka Kimliği

### İsim: EmareCloud

**Anlamı:** "Emare" = İşaret, gösterge (Türkçe) — Altyapı yönetiminde yol gösterici.

### Slogan Alternatifleri

| Slogan | Ton |
|--------|-----|
| "Altyapıdan İşe." | Kısa, güçlü |
| "Kendi İşini, Kendi Sunucunda." | Bağımsızlık |
| "Build Your Infrastructure Business" | Global |
| "From Server to Business in Minutes" | Hız vurgusu |
| "Self-Hosted. Self-Made." | Minimal |

### Önerilen: **"Altyapıdan İşe."**

Kısa, Türkçe, vizyonu özetliyor.
İngilizce karşılık: **"From Infrastructure to Business."**

### Renk Paleti

| Renk | Hex | Kullanım |
|------|-----|----------|
| Primary | `#6C63FF` | Ana marka rengi, butonlar |
| Dark | `#1A1A2E` | Arka plan, header |
| Accent | `#00D9FF` | Vurgular, linkler |
| Success | `#00C853` | Başarı, aktif durum |
| Warning | `#FFB300` | Uyarılar |
| Danger | `#FF1744` | Hatalar, silme |

---

## 10. Başarı Metrikleri

### Ürün Metrikleri

| Metrik | 6 ay | 12 ay | 24 ay |
|--------|------|-------|-------|
| GitHub yıldız | 500 | 2,000 | 10,000 |
| Aktif kurulum | 100 | 500 | 2,000 |
| Ödeme yapan müşteri | 10 | 58 | 290 |
| MRR | $2K | $7K | $37K |
| Churn rate | <%10 | <%8 | <%5 |
| NPS | >30 | >40 | >50 |

### Teknik Metrikler

| Metrik | Hedef |
|--------|-------|
| Uptime | %99.9 |
| Ortalama yanıt süresi | <200ms |
| API başarı oranı | >%99 |
| Güvenlik açığı | 0 kritik |
| Test kapsama | >%80 |

---

## 11. Risk Analizi

| Risk | Olasılık | Etki | Azaltma |
|------|----------|------|---------|
| Güvenlik açığı | Orta | Yüksek | Düzenli pentest, bug bounty |
| cPanel/Plesk fiyat indirimi | Düşük | Orta | AI + deployment farkı korur |
| Coolify hızlı büyümesi | Orta | Orta | Multi-tenant + AI fark |
| Teknik borç birikimi | Orta | Orta | Faz 3 test sürecini başlat |
| Yetersiz dokümantasyon | Yüksek | Orta | Community-driven docs |
| Tek geliştirici riski | Yüksek | Yüksek | Açık kaynak, contributor çekimi |

---

## 12. Sonuç

EmareCloud bugün güçlü bir altyapı paneli. Yarın bir iş kurma platformu olacak.

Bu dönüşüm:

- **Teknik olarak mümkün** — Modüler mimari hazır, katman katman büyütülebilir.
- **Pazar açığı var** — Hiçbir rakip hosting + AI + SaaS deployment'ı birlikte sunmuyor.
- **Gelir potansiyeli yüksek** — Self-hosted B2B SaaS, düşük churn, yüksek LTV.
- **Topluluk avantajı** — Açık kaynak + Türkçe pazar → hızlı benimseme.

Anahtar başarı faktörü:

> **Aşama aşama ilerlemek. Her aşamada gelir üretmek.
> Altyapıyı satarak iş kurma platformu finanse etmek.**

---

*Doküman: EmareCloud OS — Business Builder Vizyon Dokümanı v1.0*
*Tarih: Mart 2026*
*"Altyapıdan İşe."*
