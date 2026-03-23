# Emare Security OS — Yazılım Geliştirme ve Farklılaştırma Yol Haritası

Bu belge, projeyi **teknik ve ürün açısından ayırt edici** kılacak yönleri tanımlar. Amaç: “bir firewall yöneticisi daha” olmaktan çıkıp, **Emare ekosistemi + operasyonel gerçeklik** ile örtüşen, tekrarlanması zor bir değer önerisi oluşturmak.

---

## 1. Vizyon: “Eşsiz” ne anlama geliyor?

Gerçekçi hedef: dünyada tek olmak yerine, **belirli bir segmentte rakipsiz** olmak — örneğin:

- **Emare OS + Linux hibrit** ortamlarda tek kontrol düzlemi
- **Küçük/orta ölçek ISP ve hosting** için uçtan uca (L3–L7 + log + politika) tek açık kaynak çekirdek
- **Türkçe birinci sınıf** dokümantasyon, hata mesajları ve operasyon runbook’ları

“Eşsiz” burada: **aynı üçlüyü (UFW + firewalld + Emare OS) tek API ve tek UI ile birleştiren**, log/analitik ile birleşik bir ürün olması.

---

## 2. Teknik farklılaştırıcılar (yüksek etki)

### 2.1 Politika motoru ve “kural as kodu”

- Kuralların **YAML/JSON şema** ile tanımlanması; sunucuya **idempotent uygulama** (Terraform benzeri plan → uygula → drift tespiti).
- **Drift detection:** Uzaktaki gerçek durum ile tanımlı politika arasında fark raporu (güvenlik denetimleri için güçlü).

### 2.2 Çok kiracılı (multi-tenant) ve organizasyon modeli

- Sunucuları **organizasyon / etiket / ortam** (prod, staging) ile gruplama; API’de kapsam filtreleri.
- **RBAC ile uyumlu** izin modeli: sadece görüntüle vs değiştir, belirli sunucu grupları.

### 2.3 Tehdit zekâsı ve bağlam farkındalığı (aşamalı)

- **Otomatik öneri:** Fail2ban / bağlantı loglarından “şu IP’yi geçici engelle” önerisi (insan onayı ile).
- **Feed entegrasyonu:** AbuseIPDB, Spamhaus DROP vb. için **opsiyonel** blok listeleri (açık/kapalı, kaynak etiketli).
- **Skorlama:** Mevcut `security_scan` çıktısını zaman serisi halinde saklayıp **trend grafikleri**.

### 2.4 Ağ topolojisi ve politika görselleştirmesi

- Sunucular ve **NAT / port yönlendirme** ilişkilerinin **graph** görünümü (D3/Cytoscape benzeri).
- “Bu port açılırsa hangi iç servise gider?” sorusuna **tek tık cevap** — operasyon ekipleri için güçlü fark.

### 2.5 Uyumluluk ve denetim paketleri

- **CIS / profil şablonları:** “Web sunucusu”, “DB sunucusu”, “VPN gateway” gibi **hazır politika setleri**.
- **Denetim raporu:** PDF/Markdown export — “şu kontroller geçti / kaldı” listesi (mevcut taramayı genişleterek).

### 2.6 Felaket kurtarma ve değişiklik güvenliği

- Yedekleme/geri yükleme (mevcut) üzerine: **değişiklik öncesi otomatik snapshot**, **tek tık rollback**.
- **Canary / aşamalı uygulama:** Önce tek sunucuda dene, sonra gruba yay.

### 2.7 Gözlemlenebilirlik (observability)

- **OpenTelemetry** ile span/metric (istek süreleri, SSH komut süreleri, hata oranları).
- **Prometheus metrikleri** endpoint’i (opsiyonel modül): entegrasyon seven müşteriler için kritik.

---

## 3. Emare OS’e özgü derinleştirme (rakiplerin kopyası zor)

- **Emare CLI sürüm matrisi:** Hangi Emare OS sürümünde hangi komut/kapasite var — otomatik uyumluluk tablosu.
- **Şablon kütüphanesi:** Sektöre özel (WISP, kurumsal WAN, kamu vb.) **Emare firewall profilleri**.
- **Gerçek zamanlı bağlantı + adres listesi** birleşik paneli — sadece “kural listesi” değil, **canlı trafik bağlamı**.

---

## 4. Ürün ve deneyim (UX)

- **Kılavuzlu akışlar:** “İlk kurulum sihirbazı”, “sadece SSH aç”, “sadece web aç” tek tık senaryoları.
- **Hata mesajları:** Her API hatasında **ne yapılır** (1–2 cümle) + dokümantasyon linki.
- **Karanlık mod + yoğun operasyon UI’si** (uzun süre ekranda çalışan NOC ekipleri için).

---

## 5. Kalite, güvenlik, sürdürülebilirlik

- **Sözleşme testleri:** OpenAPI şeması + **pytest** ile endpoint sözleşmeleri.
- **Güvenlik:** Bağımlılık taraması (Dependabot/Safety), SBOM, imzalı sürümler (isteğe bağlı).
- **Performans:** ISP modunda zaten Redis/Postgres var; **yük testi senaryoları** dokümante edilmeli.

---

## 6. Topluluk ve ekosistem

- **Plugin arayüzü:** Özel “komut sağlayıcıları” veya “notify webhook” (Slack, Telegram, EmareCloud olayları).
- **Örnek repo:** Docker Compose + örnek politika dosyaları + fake SSH (mevcut mock’un genişletilmiş hali) — “5 dakikada dene” deneyimi.

---

## 7. Önceliklendirme önerisi (kısa orta vade)

| Faz | Odak | Çıktı |
|-----|------|--------|
| A | Politika-as-kod + drift | Tekilleştirici teknik temel |
| B | Görsel topoloji + Emare derin entegrasyon | Görünür “wow” + savunulabilir niş |
| C | OpenTelemetry + Prometheus | Kurumsal satış / entegrasyon |
| D | Tehdit feed + öneri motoru (onaylı) | Günlük operasyon değeri |

---

## 8. Bilinçli olarak “yapmama” kararı

- Her şeye **yapay zeka etiketi** yapıştırmak yerine: ölçülebilir, güvenli ve **açıklanabilir** otomasyon.
- Tam **SIEM** veya **tam SD-WAN** ürününe dönüşmek (kapsam şişmesi) — bunun yerine **API ve export** ile yan ürünlerle entegrasyon.

---

*Bu belge canlı tutulmalı; her çeyrekte hedefler ve tamamlanan maddeler güncellenir.*
