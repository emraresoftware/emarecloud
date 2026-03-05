# EmareCloud — AI Anayasası

> **Versiyon:** 1.0
> **Yürürlük:** Mart 2026
> **Kapsam:** EmareCloud platformunda geliştirilen, sunulan ve yönetilen tüm AI servisleri, modeller ve otomasyon süreçleri.

---

## Önsöz

EmareCloud, altyapıyı hizmete dönüştüren bir **Infrastructure Business Engine**'dir.
AI teknolojilerini platformun merkezine koyarken, bu gücün **sorumlu, şeffaf,
güvenli ve adil** kullanılmasını garanti altına almak için bu anayasayı ilan eder.

Bu anayasa, EmareCloud ekibini, platform kullanıcılarını, API tüketicilerini ve
üçüncü parti geliştiricileri bağlar.

---

## Madde 1 — Temel İlkeler

### 1.1 İnsan Önceliği
AI, insanın yerini almaz — insanı güçlendirir. EmareCloud'daki her AI özelliği,
kullanıcının **karar verme yeteneğini artırmak** için tasarlanır, kararı onun
yerine almak için değil.

### 1.2 Şeffaflık
- Kullanıcıya her zaman **AI tarafından üretilen içerik** açıkça belirtilir.
- Hangi modelin, hangi versiyon ile ve hangi parametrelerle çalıştığı görünür olur.
- AI kararlarının gerekçesi (explainability) erişilebilir tutulur.

### 1.3 Gizlilik & Veri Egemenliği
- Kullanıcı verileri, kullanıcının **açık izni olmadan** AI model eğitiminde kullanılmaz.
- Self-hosted mimaride veriler müşterinin kendi sunucusundan dışarı çıkmaz.
- Veri işleme süreçleri KVKK ve GDPR uyumludur.

### 1.4 Adalet & Tarafsızlık
- AI modelleri, belirli kullanıcı gruplarını ayrımcılığa uğratacak şekilde çalıştırılmaz.
- Model çıktılarında bias tespiti için periyodik denetim yapılır.
- Tüm kullanıcılara eşit kalitede AI hizmeti sunulur (plan limitleri dahilinde).

### 1.5 Güvenlik
- AI sistemleri, prompt injection, data poisoning ve model extraction gibi saldırılara karşı korunur.
- AI Gateway üzerinden geçen tüm trafik şifrelenir (TLS 1.3+).
- Model erişimi kimlik doğrulama ve yetkilendirme ile kontrol edilir.

---

## Madde 2 — AI Veri Politikası

### 2.1 Veri Sınıflandırma

| Sınıf | Tanım | AI Kullanım İzni |
|-------|-------|-------------------|
| **Herkese Açık** | Dokümantasyon, genel metrikler | ✅ Serbest |
| **Organizasyon** | Sunucu konfigürasyonları, loglar | ⚠️ Yalnızca org sahibinin izniyle |
| **Kişisel** | Kullanıcı bilgileri, SSH anahtarları | ❌ Asla AI'a beslenmez |
| **Gizli** | Şifreleme anahtarları, credential'lar | ❌ Kesinlikle yasak |

### 2.2 Veri Yaşam Döngüsü

```
Veri Girişi → Sınıflandırma → İzin Kontrolü → AI İşleme → Sonuç → Temizleme
     │              │                │              │          │         │
     ▼              ▼                ▼              ▼          ▼         ▼
  Audit Log    Auto-Label      RBAC Check     Sandbox     Filtreleme  TTL Expire
```

### 2.3 Veri Saklama Kuralları
- AI API çağrı logları: **90 gün** (yapılandırılabilir)
- Token kullanım kayıtları: **365 gün** (faturalandırma amaçlı)
- Model giriş/çıkış verileri: **varsayılan olarak saklanmaz** (opt-in)
- Kullanıcı açıkça talep ederse: konuşma geçmişi şifreli olarak saklanır

---

## Madde 3 — AI Model Yönetişimi

### 3.1 Model Kayıt Süreci

Platform üzerinde sunulacak her AI modeli aşağıdaki süreçten geçer:

```
Aday Model → Güvenlik Taraması → Bias Testi → Performans Testi → Onay → Registry
                   │                  │              │              │
                   ▼                  ▼              ▼              ▼
             Zafiyet yok?       Adil mi?      SLA karşılar mı?   Yayına al
```

### 3.2 Model Kartı (Model Card)

Her model için aşağıdaki bilgiler zorunlu olarak yayınlanır:

| Alan | Açıklama |
|------|----------|
| **Model Adı** | Tanımlayıcı isim ve versiyon |
| **Sağlayıcı** | OpenAI, Anthropic, yerel, vb. |
| **Kullanım Amacı** | Metin üretimi, kod, analiz, vb. |
| **Bilinen Sınırlamalar** | Hallucination riski, dil desteği, vb. |
| **Veri Politikası** | Veri nereye gider, saklama süresi |
| **Maliyet** | Token başına birim fiyat |
| **SLA** | Uptime garantisi, yanıt süresi |

### 3.3 Model Versiyonlama
- Her model güncellemesi **versiyon numarası** alır
- Breaking change'lerde kullanıcılar **en az 30 gün önceden** bilgilendirilir
- Eski versiyonlar **deprecation süreci** ile aşamalı olarak kaldırılır
- Kritik güvenlik yamaları hariç, zorla güncelleme yapılmaz

---

## Madde 4 — AI Güvenlik Politikası

### 4.1 Tehdit Modeli

| Tehdit | Açıklama | Koruma |
|--------|----------|--------|
| **Prompt Injection** | Kötü niyetli input ile model davranışını değiştirme | Input sanitization + guardrails |
| **Data Poisoning** | Eğitim verisini manipüle etme | Veri bütünlük kontrolü |
| **Model Extraction** | Model ağırlıklarını çalma | API rate limit + erişim kontrolü |
| **PII Leakage** | Kişisel bilgilerin model çıktısında sızması | Output filtreleme + PII taraması |
| **Denial of Service** | Aşırı istek ile hizmeti çökertme | Rate limiting + token quota |
| **Jailbreak** | Model güvenlik kurallarını aşma | Multi-layer content filtering |

### 4.2 Güvenlik Katmanları

```
┌─────────────────────────────────────────────┐
│          Katman 1: API Gateway              │
│   Rate Limit · API Key · IP Allowlist       │
├─────────────────────────────────────────────┤
│          Katman 2: Input Guard              │
│   Prompt Sanitize · PII Detect · Blocklist  │
├─────────────────────────────────────────────┤
│          Katman 3: Model Sandbox            │
│   İzole çalışma · Kaynak limiti · Timeout   │
├─────────────────────────────────────────────┤
│          Katman 4: Output Filter            │
│   PII Masking · Content Policy · Watermark  │
├─────────────────────────────────────────────┤
│          Katman 5: Audit & Monitor          │
│   Tüm çağrılar loglanır · Anomali tespiti  │
└─────────────────────────────────────────────┘
```

### 4.3 Olay Müdahale Planı
1. **Tespit:** Anomali algılama sistemi veya kullanıcı bildirimi
2. **Sınıflandırma:** Düşük / Orta / Yüksek / Kritik
3. **İzolasyon:** Etkilenen modeli devre dışı bırak
4. **Analiz:** Root cause analizi
5. **Düzeltme:** Yama veya model geri alma
6. **Bildirim:** Etkilenen kullanıcılara 24 saat içinde bildirim
7. **Rapor:** Post-mortem raporu yayınla

---

## Madde 5 — AI Kullanım Etik Kuralları

### 5.1 Yasaklanan Kullanımlar

EmareCloud AI servisleri aşağıdaki amaçlarla **kesinlikle kullanılamaz:**

| # | Yasak Kullanım |
|---|----------------|
| 1 | Kişilerin izinsiz gözetlenmesi veya takibi |
| 2 | Dezenformasyon, sahte içerik veya deepfake üretimi |
| 3 | Silah, patlayıcı veya zararlı madde üretim talimatları |
| 4 | Çocuk istismarı içeriği (CSAM) |
| 5 | Nefret söylemi, ayrımcılık veya şiddete teşvik |
| 6 | Yetkisiz kişisel veri toplama veya profilleme |
| 7 | Otonom silah sistemleri veya askeri otomasyon |
| 8 | Finansal manipülasyon veya piyasa dolandırıcılığı |
| 9 | Seçim manipülasyonu veya siyasi propaganda otomasyonu |
| 10 | Telif hakkı ihlali amacıyla sistematik içerik kopyalama |

### 5.2 İhlal Müeyyideleri

| Seviye | Eylem | Müeyyide |
|--------|-------|----------|
| **Uyarı** | İlk ihlal, düşük risk | Yazılı uyarı + 24h kısıtlama |
| **Askıya Alma** | Tekrarlanan ihlal | AI servislerinin 30 gün askıya alınması |
| **Kalıcı Yasaklama** | Ciddi ihlal | AI API erişiminin kalıcı olarak kapatılması |
| **Hukuki Süreç** | Yasa dışı kullanım | İlgili makamlara bildirim |

---

## Madde 6 — AI Token Ekonomisi & Adalet

### 6.1 Adil Fiyatlandırma İlkeleri
- Token fiyatları **maliyet + makul marj** formülüyle belirlenir
- Fiyat değişiklikleri **en az 30 gün önceden** duyurulur
- Gizli maliyet uygulanmaz — fatura detayları tam şeffaftır
- Ücretsiz tier her zaman sunulur (makul limitlerle)

### 6.2 Kaynak Adaleti

```
┌─────────────────────────────────────────┐
│         Token Tahsis Politikası          │
│                                          │
│  Starter:     10K token/ay  (ücretsiz)   │
│  Professional: 100K token/ay             │
│  Enterprise:  Sınırsız (fair-use)        │
│                                          │
│  ⚖️ Fair-Use Kuralı:                     │
│  Tek kullanıcı toplam kapasitenin        │
│  %20'sinden fazlasını tüketemez          │
│  (diğer kullanıcıları korumak için)      │
└─────────────────────────────────────────┘
```

### 6.3 Hizmet Seviyesi Garantileri

| Metrik | Starter | Professional | Enterprise |
|--------|---------|-------------|------------|
| Uptime | %99 | %99.5 | %99.9 |
| Yanıt Süresi | < 5s | < 3s | < 1s |
| Rate Limit | 10 req/dk | 60 req/dk | 300 req/dk |
| Destek | Community | Email (24h) | Dedicated (1h) |
| Model Erişimi | Temel | Tüm modeller | Tüm + Early Access |

---

## Madde 7 — Şeffaflık & Raporlama

### 7.1 Periyodik Şeffaflık Raporu

EmareCloud, **her çeyrekte** aşağıdaki bilgileri içeren şeffaflık raporu yayınlar:

- 📊 Toplam AI API çağrı sayısı
- 🚫 Engellenen kötü amaçlı istek sayısı
- 🐛 Tespit edilen güvenlik olayları ve alınan aksiyonlar
- 📈 Model performans metrikleri (doğruluk, yanıt süresi)
- ⚖️ Bias denetim sonuçları
- 🔄 Model güncelleme ve deprecation logları

### 7.2 Kullanıcı Hakları

Her EmareCloud kullanıcısı aşağıdaki haklara sahiptir:

| Hak | Açıklama |
|-----|----------|
| **Bilgilenme** | AI'ın ne yaptığını ve nasıl çalıştığını bilme |
| **Veri Erişimi** | Kendisine ait AI kullanım verilerini indirme |
| **Veri Silme** | AI loglarının kalıcı olarak silinmesini talep etme |
| **İtiraz** | AI kararlarına itiraz edip insan incelemesi isteme |
| **Opt-out** | AI özelliklerini tamamen kapatma |
| **Taşınabilirlik** | Verilerini başka platforma export etme |

---

## Madde 8 — Otomasyon Güvenlik Sınırları

### 8.1 AI Destekli Otomasyon Kuralları

EmareCloud'da AI, sunucu yönetim otomasyonlarını güçlendirir. Bu güç sınırlandırılmalıdır:

| Otomasyon | İzin | Koşul |
|-----------|------|-------|
| Metrik analizi ve anomali tespiti | ✅ Otomatik | — |
| Alert ve bildirim tetikleme | ✅ Otomatik | Kullanıcı kurallarına göre |
| Yedekleme zamanlama önerisi | ✅ Otomatik | — |
| Firewall kural önerisi | ⚠️ Öneri | Kullanıcı onayı gerekli |
| Sunucu yeniden başlatma | ⚠️ Öneri | Açık kullanıcı onayı gerekli |
| Kaynak ölçeklendirme | ⚠️ Öneri | Maliyet etkisi gösterilmeli |
| Veri silme / disk format | ❌ Yasak | AI asla tetikleyemez |
| SSH credential değiştirme | ❌ Yasak | AI asla tetikleyemez |
| Kullanıcı hesabı kapatma | ❌ Yasak | AI asla tetikleyemez |

### 8.2 Geri Alınamazlık Kuralı (Irreversibility Rule)
> **AI, geri alınamaz (irreversible) hiçbir işlemi insan onayı olmadan çalıştıramaz.**
> Bu kural, herhangi bir yapılandırma veya politika tarafından geçersiz kılınamaz.

---

## Madde 9 — Üçüncü Parti AI Entegrasyonları

### 9.1 Provider Değerlendirme Kriterleri

EmareCloud AI Gateway'e eklenecek her üçüncü parti provider:

- [ ] Veri işleme sözleşmesi (DPA) imzalamalı
- [ ] KVKK / GDPR uyumluluğunu belgelemeli
- [ ] Veriyi eğitim için kullanmama taahhüdü vermeli
- [ ] API uptime SLA'si en az %99 olmalı
- [ ] Güvenlik denetiminden (SOC2 veya eşdeğeri) geçmiş olmalı

### 9.2 Provider İzleme
- Her provider için **sağlık skoru** hesaplanır (uptime, latency, error rate)
- Skor %95'in altına düşerse otomatik uyarı
- Skor %90'ın altına düşerse fallback provider'a geçiş
- Ciddi ihlallerde provider platformdan çıkarılır

---

## Madde 10 — Yönetişim & Güncelleme

### 10.1 Anayasa Yönetim Kurulu

| Rol | Sorumluluk |
|-----|------------|
| **AI Etik Sorumlusu** | Etik kuralların uygulanması, ihlal inceleme |
| **Güvenlik Mühendisi** | Tehdit modeli güncelleme, olay müdahale |
| **Ürün Yöneticisi** | Kullanıcı hakları ve deneyim dengesi |
| **Hukuk Danışmanı** | Yasal uyumluluk (KVKK, GDPR, AI Act) |

### 10.2 Güncelleme Süreci
1. Değişiklik teklifi (RFC formatında)
2. 30 gün topluluk yorumu (açık kaynak)
3. Etik kurul değerlendirmesi
4. Versiyon numarası artışı
5. Tüm kullanıcılara bildirim
6. 60 gün geçiş süresi

### 10.3 Yasal Uyumluluk Takvimi

| Düzenleme | Kapsam | Hedef Tarih |
|-----------|--------|-------------|
| **KVKK** | Kişisel veri koruma | ✅ Mevcut |
| **GDPR** | AB veri koruma | ✅ Mevcut |
| **EU AI Act** | AI risk sınıflandırması | Q3 2026 |
| **Digital Services Act** | Dijital hizmet düzenlemesi | Q4 2026 |
| **ISO 42001** | AI yönetim sistemi sertifikası | 2027 |

---

## Madde 11 — Taahhüt

> **EmareCloud olarak taahhüt ederiz:**
>
> 🤝 AI'ı insanlığın yararına kullanmak,
>
> 🔍 Her kararımızda şeffaf olmak,
>
> 🛡️ Kullanıcı verilerini en yüksek standartta korumak,
>
> ⚖️ Adaletli ve tarafsız AI hizmetleri sunmak,
>
> 🌱 Sorumlu AI inovasyonunu teşvik etmek,
>
> 📖 Bu anayasayı sürekli iyileştirmek ve uygulamak.

---

*Doküman: EmareCloud — AI Anayasası v1.0*
*Yürürlük: Mart 2026*
*Sonraki Gözden Geçirme: Haziran 2026*
