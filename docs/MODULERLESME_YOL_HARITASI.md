# EmareCloud Modulerlesme Yol Haritasi

Bu dokuman, mevcut moduler monolit yapisini bozmadan projeyi parcalara ayirmanin en dusuk riskli yolunu verir.

## 1. Neden Bu Yol?

Projede zaten `routes/` ve `core/` ayrimi var. Bu nedenle en mantikli strateji:

1. Yeniden yazim yapmamak
2. Moduller arasi bagimliliklari azaltmak
3. Her alani test edilebilir sinirlara cekmek
4. Son asamada gerekirse mikroservis cikarmak

Bu yaklasim, Strangler Fig deseninin moduler monolit uygulamasidir.

## 1.1 Mikroservis Karari (Net)

Tum ozellikler dogrudan bagimsiz mikroservis olmayacak.

Ilk hedef: tek deploy icinde moduler monolit yapisini tam oturtmak.

Mikroservise ayirma sadece su kosullarda yapilir:

1. Bagimsiz olceklenme ihtiyaci (trafik/CPU ciddi farkli)
2. Bagimsiz deploy ihtiyaci (sik degisen alan)
3. Teknik bagimlilik farki (farkli runtime veya altyapi)
4. Operasyonel sinir netligi (ayri ekip/sahiplik)

Bu kosullari saglamayan alanlar moduler monolit icinde kalir.

Onerilen hedef mimari (hybrid):

1. Cekirdek alanlar monolitte kalir: auth, tenant, org, rbac
2. Servis olarak cikma adayi alanlar: monitoring/alert, deploy runner, terminal worker
3. Her servis cikarimi Strangler adimi ile ve geri donus planiyla yapilir

## 2. Hedef Sinirlar (Domain Alanlari)

1. Kimlik ve Yetki
2. Tenant ve Organizasyon
3. Sunucu Yonetimi
4. Ag ve Guvenlik
5. Monitoring ve Alarm
6. Market ve Deploy
7. Token ve Odul Sistemi

Kural: Bir alan diger alandan dogrudan route import etmez. Ortak ihtiyaclar `core/` veya servis katmanina tasinir.

## 3. 4 Sprintlik Plan

### Sprint 1 - Bagimlilik Temizligi (1 hafta)

1. Route-to-route importlarini sifirla
2. Ortak helper'lari `core/helpers.py` icine topla
3. `routes/*` dosyalarinda sadece su katmanlara izin ver:
   - `core/*`
   - `models.py`
   - `rbac.py`
   - servis dosyalari (`*_manager.py`)
4. Smoke testleri her degisimde kos

Basari olcutu:
- `rg "from routes\." routes -n` sonucu sadece `routes/__init__.py` ve teknik kayitlar olmalı

### Sprint 2 - Domain Paketleme (1 hafta)

1. Route dosyalarini domain klasorlerine ayir:
   - `routes/domain_identity/`
   - `routes/domain_infra/`
   - `routes/domain_network/`
   - `routes/domain_ops/`
2. Mevcut endpoint URL'leri degismez
3. `routes/__init__.py` sadece registry gorevi yapar

Guncel durum:
- Ilk tasima tamamlandi: `routes/network.py` -> `routes/domain_network/network.py`
- Registry importu yeni yola cekildi
- Ikinci tasima tamamlandi: `routes/metrics.py` -> `routes/domain_ops/metrics.py`
- Ucuncu tasima tamamlandi: `routes/storage.py` -> `routes/domain_ops/storage.py`
- Dorduncu tasima tamamlandi: `routes/commands.py` -> `routes/domain_ops/commands.py`
- Besinci tasima tamamlandi: `routes/virtualization.py` -> `routes/domain_infra/virtualization.py`
- Altinci tasima tamamlandi: `routes/monitoring.py` -> `routes/domain_ops/monitoring.py`

Basari olcutu:
- Endpoint davranisi degismeden dosya dagilimi netlesmis olur

### Sprint 3 - Servis Arayuzu Sertlestirme (1-2 hafta)

1. SSH, monitoring, firewall ve deploy islemlerini servis arayuzu ile cagir
2. Route icindeki is kurali miktarini azalt
3. Hata donus formatlarini standartlastir

Basari olcutu:
- Route dosyalari daha ince, testler servis seviyesinde agirlik kazanir

### Sprint 4 - Veri Katmani Ayrimi (1-2 hafta)

1. SQLAlchemy sorgularini repository benzeri fonksiyonlara tasima
2. Tenant filtrelerini tek merkezde toplama
3. PostgreSQL gecisi ile birlikte baglanti havuzu ayarlari

Basari olcutu:
- DB degisimi route seviyesine dokunmadan ilerler

## 4. Operasyonel Kurallar

1. Her degisim kucuk PR boyutunda olmalı
2. Her adimda rollback net olmalı
3. Endpoint sozlesmesi bozulmamalı
4. Once calisirlik, sonra guzel mimari

## 5. Hemen Uygulanacak Kontroller

```bash
# 0) Otomatik katman sinir denetimi
python3 tools/check_modular_boundaries.py

# 1) Cikmasi gereken bagimlilik listesi
rg "from routes\\.|import routes\\." routes core app.py -n

# 2) Derleme/syntax kontrol
python -m compileall app.py routes core

# 3) Testler
pytest tests/ -q
```

## 6. Not

Bu planin amaci buyuk bir "rewrite" degil, mevcut calisan sistemi parcalara ayirirken riski minimumda tutmaktir.
