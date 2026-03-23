# Emare Security OS — AI Agent Görev Dağılımı ve Koordinasyon

> Bu dosya, birden fazla AI ajanının aynı projede güvenli ve verimli çalışmasını sağlar.

## 🎯 Koordinasyon Stratejisi

### Temel İlke: "Modüler Sorumluluk Alanları"
Her AI ajanı belirli bir modül veya katman üzerinde çalışır.
Aynı dosyanın aynı bölgesinde iki ajan aynı anda çalışmaz.

### Dosya Bölge Haritası

#### manager.py (~3960 satır) — Bölgesel Sorumluluk
```
L1–L222      : Modül fonksiyonları (validators, parsers) — ⛔ PAYLAŞIMLI, dikkatli ol
L223–L316    : __init__, _exec, _exec_multi, cache — 🔒 KRİTİK ALTYAPI
L317–L644    : get_status (3 FW parse) — 🔒 DOKUNMA
L645–L1000   : Temel CRUD — Kurallar, Servisler, Routing, ARP, DHCP
L1001–L1400  : IP block, Port forward, Zones, Fail2ban, Connections
L1401–L1720  : Security scan, Geo block
L1721–L3000  : L7 Protection Engine (28 koruma tipi)
L3001–L3470  : Backup/Restore
L3471–L3959  : Network Analyser (11 metot)
L3960+       : 🟢 YENİ ÖZELLİKLER BURAYA EKLENIR
```

#### routes.py (~1430 satır) — Ekleme Noktası
```
L1–L240      : Imports, rate limiter, CSRF, helpers — 🔒 DOKUNMA
L241–L1218   : Mevcut endpoint'ler
L1219–L1425  : Network Analyser endpoint'leri
L1425–L1432  : return bp — ✅ YENİ ENDPOINT'LER BURADAN ÖNCE
```

#### firewall.html (~1560 satır) — Ekleme Noktaları
```
L1–L150      : HTML head, CSS — ⚠️ DİKKATLİ
L151–L185    : Tab bar — ✅ Son tab'dan sonra yeni tab ekle
L186–L530    : Panel HTML'leri — ✅ Son panel'den sonra yeni panel
L531–L620    : Core JS (fwApi, fwTab, fwCachedApi) — 🔒 DOKUNMA
L620–L1560   : Feature JS fonksiyonları — ✅ </script> öncesine yeni JS
```

#### app.py (~770 satır) — Mock Ekleme Noktaları
```
L1–L180      : Mock veri değişkenleri (_eo_*, _ufw_*) — ✅ Yeni veri sonuna
L181–L232    : mock_ssh_executor dispatcher — 🔒 DOKUNMA
L233–L491    : _mock_emareos — ✅ "Generic" satırından ÖNCE
L492–L716    : _mock_ufw — ✅ "Generic commands" satırından ÖNCE
L717–L772    : create_app — ⚠️ DİKKATLİ
```

## 📋 Ajan Görev Atama Kuralları

### Görev Alırken
1. **Önce `.instructions.md` ve bu dosyayı oku**
2. Hangi dosyaların hangi bölgelerinde çalışacağını belirle
3. Mevcut kodu oku ve anla (en az 50 satır bağlam)
4. Değişiklik yap
5. Docker build + test
6. CHANGELOG.md güncelle

### Çakışma Önleme Kuralları
1. **Append-only ekleme:** Yeni kod her zaman ilgili bölgenin SONUNA eklenir
2. **Mevcut imzaları koruma:** Public metot parametreleri ve return formatları değiştirilmez
3. **Interface uyumluluğu:** `cache.py`, `store.py`, `ssh.py` public metotları değiştirilmez
4. **Config geriye uyumluluk:** Yeni config eklenebilir, mevcut isimler/varsayılanlar değiştirilmez

### Bir AI Ajanı Başka Bir Ajanın Koduna Dokunmak Zorundaysa
1. Önce mevcut kodu tamamen oku ve anla
2. Değişikliğin neden gerektiğini belirt (CHANGELOG'a)
3. Mevcut testlerin hala çalıştığından emin ol
4. Minimum değişiklik yap — refactor yapma

## 🔄 Yeni Özellik Ekleme Akışı (Standart)

```
1. manager.py  →  Dosya sonuna iş mantığı metotları ekle
                   Pattern: dual-mode (emareos + linux)
                   Güvenlik: input validation + _sq() escape
                   
2. routes.py   →  `return bp` öncesine endpoint'ler ekle
                   Pattern: rate_err → csrf_err → validate → manager → jsonify
                   
3. firewall.html → Tab butonu (tab bar sonuna)
                   Panel HTML (son panel sonrasına)
                   JS fonksiyonları (</script> öncesine)
                   fwTab() fonksiyonuna lazy-load hook
                   
4. app.py      →  Mock veri (dosya başına _eo_ tuple)
                   _mock_emareos (Generic öncesine)
                   _mock_ufw (Generic commands öncesine)
                   
5. Test        →  docker compose build + up
                   curl emare-router-1 (Emare OS)
                   curl ufw-server-1 (Linux)
                   
6. CHANGELOG   →  Tarih + özellik açıklaması
7. Version     →  pyproject.toml semver bump
```

## 🧩 Modül Ekleme (Yeni Dosya Gerekiyorsa)

Yeni Python modülü eklemek gerekiyorsa:
1. Proje kök dizinine `modül_adı.py` olarak oluştur
2. `__init__.py`'ye import ekle
3. `app.py` → `create_app()` içinde initialize et
4. Bu dosyaya modül bilgisini ekle
5. `.instructions.md`'yi güncelle

## 🏷️ Versiyon Yönetimi (Semver)

| Değişiklik | Versiyon Bump | Örnek |
|---|---|---|
| Bug fix | PATCH | 1.4.0 → 1.4.1 |
| Yeni özellik (geriye uyumlu) | MINOR | 1.4.0 → 1.5.0 |
| Breaking change (API/interface) | MAJOR | 1.4.0 → 2.0.0 |

## 🤖 Aktif AI Ajan Görevleri

### Ajan A (Ana — ISP/Core)
- **Sorumluluk:** Core firewall, ISP multi-tenant, genel altyapı
- **Tamamlananlar:** v1.5.0 ISP özellikleri (tenants.py, 26 ISP endpoint, Redis circuit breaker)
- **Dokunduğu dosyalar:** manager.py, routes.py (ISP bölgesi), tenants.py, cache.py, config.py, app.py

### Ajan B (5651 Compliance)
- **Sorumluluk:** 5651 log saklama yasal uyumluluk modülü
- **Görev dosyası:** `5651/TASK.md` — detaylı talimatlar burada
- **Dokunacağı dosyalar:**
  - `routes.py` — SADECE 5651 endpoint'leri (`return bp` öncesine, ISP bölgesinden sonra)
  - `app.py` — SADECE `create_app()` içinde Law5651Stamper init (store oluştuktan sonra, tenant_store öncesine)
  - `firewall.html` — SADECE 5651 tab (opsiyonel)
- **DOKUNMAYACAĞI dosyalar:** `law5651.py` (tamamlandı), `store.py` (5651 entegrasyonu hazır), `tenants.py`, `manager.py`

### Çakışma Matrisi
| Dosya | Ajan A | Ajan B |
|---|---|---|
| `routes.py` ISP bölgesi (L1425-2008) | ✅ Sahip | ⛔ Dokunma |
| `routes.py` 5651 bölgesi (L2008 öncesi, yeni) | ⛔ Dokunma | ✅ Sahip |
| `app.py` create_app() | ⚠️ Tamamlandı | ✅ Sadece stamper init |
| `tenants.py` | ✅ Sahip | ⛔ Dokunma |
| `law5651.py` | ⛔ Tamamlandı | ⛔ Tamamlandı |
| `store.py` 5651 metotları | ⛔ Tamamlandı | ⛔ Tamamlandı |
| `firewall.html` 5651 tab | ⛔ Dokunma | ✅ Sahip (opsiyonel) |

## 📊 Mevcut Durum (v1.5.0 — Güncel)

| Modül | Durum | Satır |
|---|---|---|
| Core Firewall (rules, services, enable/disable) | ✅ Tamamlandı | ~700 |
| IP Block / Port Forward | ✅ Tamamlandı | ~400 |
| Zones / Fail2ban | ✅ Tamamlandı | ~300 |
| Connections / Security Scan | ✅ Tamamlandı | ~350 |
| L7 Protection (28 tip) | ✅ Tamamlandı | ~1280 |
| Routing / ARP / DHCP / QoS / Bridge / DNS Static | ✅ Tamamlandı | ~500 |
| Backup / Restore | ✅ Tamamlandı | ~470 |
| Network Analyser (11 araç) | ✅ Tamamlandı | ~500 |
| Log System (SQLite/PostgreSQL) | ✅ Tamamlandı | ~550 |
| ISP Scale (Redis/Postgres/Gunicorn) | ✅ Tamamlandı | ~250 |
| ISP Multi-Tenant (tenants.py) | ✅ Tamamlandı | ~950 |
| ISP API (26 endpoint) | ✅ Tamamlandı | ~580 |
| 5651 Stamper (law5651.py) | ✅ Tamamlandı | ~350 |
| 5651 Store Entegrasyonu | ✅ Tamamlandı | ~50 |
| 5651 API Endpoint'leri | ✅ Tamamlandı | ~30 |
| 5651 UI Tab | ✅ Tamamlandı | ~60 |
| CLI (22 komut) | ✅ Tamamlandı | ~284 |
| Docker (standalone + ISP) | ✅ Tamamlandı | ~120 |

## ⚡ Sık Yapılan Hatalar ve Çözümleri

| Hata | Çözüm |
|---|---|
| `_parse_terse` bulunamıyor | Doğru isim: `_parse_emareos_terse()` |
| Mock veri eşleşmiyor (boş sonuç) | Daha spesifik `if` kontrolü ÖNCE gelmeli |
| `_exec_multi` tek sonuç döndürüyor | SEP marker yoksa fallback ile tek tek çalıştırır |
| Emare OS komutu çalışmıyor | `/emare` ile başlamalı (slash gerekli) |
| Linux komutu mock'ta eşleşmiyor | `_mock_ufw()` fonksiyonundaki `if/elif` sırasını kontrol et |
| UI tab görünmüyor | `fwTab()` fonksiyonuna lazy-load hook eklendi mi? |
| API 404 döndürüyor | `routes.py`'de Blueprint'te register edildi mi? |
| Network API URL yanlış | Firewall: `fwApi()`, Network: `fwNetApi()` — farklı prefix |
| `_rate_limit_check` bulunamıyor | Doğru isim: `_rate_limited()` — TASK.md'deki örnek yanlış |
| ISP/Log API `d.data` boş dönüyor | Her endpoint farklı key kullanır: `tenants`, `entries`, `dashboard`, `audit_logs` vb. |
