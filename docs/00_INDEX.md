# Dokümantasyon İndeksi

EmareCloud — Altyapı Yönetim Paneli dokümantasyonu.

## Kök dizin

| Dosya | Açıklama |
|-------|----------|
| [README.md](../README.md) | Proje tanıtımı, hızlı başlangıç, özellikler, mimari, dokümantasyon tablosu |
| [KULLANIM_KILAVUZU.md](../KULLANIM_KILAVUZU.md) | Kullanım kılavuzu: giriş, RBAC, kurulum, arayüz, sunucu yönetimi, terminal, uygulama pazarı, güvenlik duvarı, sanal makineler, depolama, SSS |
| [SANAL_MAKINE_YONETIMI.md](../SANAL_MAKINE_YONETIMI.md) | LXD sanal makine yönetimi — listeleme, yeni VM, başlat/durdur/sil, container içinde komut |
| [YAZILIM_GELISTIRME.md](../YAZILIM_GELISTIRME.md) | Geliştirme planı, güvenlik/mimari/test yol haritası, performans iyileştirmeleri |
| [PRODUCT_ROADMAP.md](../PRODUCT_ROADMAP.md) | Ürün vizyonu ve hedef sürümler (Secure Core, Pro, Enterprise) |

## docs/ klasörü

| Dosya | Açıklama |
|-------|----------|
| [01_GENEL_BAKIS.md](01_GENEL_BAKIS.md) | Amaç, temel özellikler, teknoloji özeti, modüler proje yapısı, güvenlik mimarisi |
| [02_KURULUM_VE_HIZLI_BASLANGIC.md](02_KURULUM_VE_HIZLI_BASLANGIC.md) | Gereksinimler, setup.sh wizard, kurulum adımları, sağlık kontrolü, ilk kullanım |
| [03_KULLANIM_REHBERI.md](03_KULLANIM_REHBERI.md) | Giriş/RBAC, dashboard, sunucu yönetimi, terminal, pazar, güvenlik duvarı, sanallaştırma, depolama |
| [04_API_VE_MODULLER.md](04_API_VE_MODULLER.md) | Modüler mimari (core/ + routes/), Blueprint sorumlulukları, tüm API uçları |
| [05_YAZILIM_GELISTIRME_YOL_HARITASI.md](05_YAZILIM_GELISTIRME_YOL_HARITASI.md) | Faz 1 ✅ (güvenlik), Faz 2 ✅ (mimari), Faz 3 ✅ (test), Faz 4 ✅ (monitoring), başarı ölçütleri |

## Stratejik Vizyon Dokümanları (Business Builder)

| Dosya | Açıklama |
|-------|----------|
| [MULTI_TENANT_MIMARI.md](MULTI_TENANT_MIMARI.md) | Multi-tenant mimari şeması — organizasyon hiyerarşisi, DB tabloları, RBAC genişlemesi, white-label, quota sistemi |
| [FATURALANDIRMA_SISTEMI.md](FATURALANDIRMA_SISTEMI.md) | Faturalandırma sistemi taslağı — 3 fatura modeli, plan/abonelik/fatura tabloları, Stripe/Iyzico entegrasyonu |
| [AI_PLATFORM_TASARIMI.md](AI_PLATFORM_TASARIMI.md) | AI Platform extension tasarımı — OpenAI-uyumlu Gateway, model router, token metering, API key yönetimi |
| [HOSTING_BUILDER.md](HOSTING_BUILDER.md) | Hosting Builder modül mimarisi — müşteri yönetimi, paket yöneticisi, domain/SSL otomasyonu, Docker deployer |
| [BUSINESS_BUILDER_VIZYON.md](BUSINESS_BUILDER_VIZYON.md) | Business Builder marka konumlandırma — vizyon, hedef kitle, GTM stratejisi, gelir projeksiyonları, rekabet analizi |
| [AI_ANAYASASI.md](AI_ANAYASASI.md) | AI Anayasası — veri politikası, etik kurallar, güvenlik katmanları, model yönetişimi, kullanıcı hakları |

## Satılabilir Ürün Dokümanları

| Dosya | Açıklama |
|-------|----------|
| [MVP_KAPSAM.md](MVP_KAPSAM.md) | Satılabilir MVP kapsam dokümanı — özellikler, fiyatlama, hedef müşteri, risk matrisi |
| [RBAC_ENDPOINT_MATRIX.md](RBAC_ENDPOINT_MATRIX.md) | RBAC yetki matrisi — 57 endpoint'in tam rol/yetki haritalandırması, tehdit analizi |
| [REFACTOR_PLANI.md](REFACTOR_PLANI.md) | Modüler refactor planı — app.py'den Blueprint yapısına geçiş planı (tamamlandı ✅) |
| [TLS_REVERSE_PROXY.md](TLS_REVERSE_PROXY.md) | Nginx + Let's Encrypt + WebSocket reverse proxy yapılandırma rehberi |

## Blockchain & Token Entegrasyonu

| Dosya | Açıklama |
|-------|----------|
| [BLOCKCHAIN_ENTEGRASYON.md](BLOCKCHAIN_ENTEGRASYON.md) | EmareToken (ERC20) blockchain entegrasyon mimarisi — cüzdan yönetimi, EP ödül sistemi, RewardPool, Marketplace, Settlement bağlantısı |

## Anahtar Dosyalar

| Dosya | Açıklama |
|-------|----------|
| [setup.sh](../setup.sh) | İnteraktif 7 adımlı kurulum wizard'ı |
| [license_manager.py](../license_manager.py) | RSA-4096 tabanlı lisans doğrulama modülü |
| [auth_routes.py](../auth_routes.py) | Kimlik doğrulama, RBAC, şifre karmaşıklık kuralları |
| [config.py](../config.py) | Uygulama yapılandırması (CORS, secret, debug) |

## Hızlı bağlantılar

- **İlk kurulum:** [setup.sh](../setup.sh) veya [02_KURULUM_VE_HIZLI_BASLANGIC.md](02_KURULUM_VE_HIZLI_BASLANGIC.md)
- **TLS/SSL:** [TLS_REVERSE_PROXY.md](TLS_REVERSE_PROXY.md)
- **Günlük kullanım:** [KULLANIM_KILAVUZU.md](../KULLANIM_KILAVUZU.md) veya [03_KULLANIM_REHBERI.md](03_KULLANIM_REHBERI.md)
- **API referansı:** [04_API_VE_MODULLER.md](04_API_VE_MODULLER.md)
- **Sanal makineler:** [SANAL_MAKINE_YONETIMI.md](../SANAL_MAKINE_YONETIMI.md)
- **Ürün kapsamı:** [MVP_KAPSAM.md](MVP_KAPSAM.md)
- **Yetki matrisi:** [RBAC_ENDPOINT_MATRIX.md](RBAC_ENDPOINT_MATRIX.md)
- **Geliştirme:** [YAZILIM_GELISTIRME.md](../YAZILIM_GELISTIRME.md), [05_YAZILIM_GELISTIRME_YOL_HARITASI.md](05_YAZILIM_GELISTIRME_YOL_HARITASI.md)
- **Landing page:** http://localhost:5555/landing

### 🚀 Business Builder Stratejisi
- **Platform vizyonu:** [BUSINESS_BUILDER_VIZYON.md](BUSINESS_BUILDER_VIZYON.md)
- **Multi-tenant:** [MULTI_TENANT_MIMARI.md](MULTI_TENANT_MIMARI.md)
- **Faturalandırma:** [FATURALANDIRMA_SISTEMI.md](FATURALANDIRMA_SISTEMI.md)
- **AI Platform:** [AI_PLATFORM_TASARIMI.md](AI_PLATFORM_TASARIMI.md)
- **Hosting Builder:** [HOSTING_BUILDER.md](HOSTING_BUILDER.md)
- **AI Anayasası:** [AI_ANAYASASI.md](AI_ANAYASASI.md)
