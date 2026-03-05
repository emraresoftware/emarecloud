# 📁 EmareCloud — Dosya Yapısı

> **Oluşturulma:** Otomatik  
> **Amaç:** Yapay zekalar kod yazmadan önce mevcut dosya yapısını incelemeli

---

## Proje Dosya Ağacı

```
/Users/emre/Desktop/Emare/emarecloud
├── .DS_Store
├── .coverage
├── .env.example
├── .github
│   └── workflows
│       └── ci.yml
├── .gitignore
├── .master.key
├── .pytest_cache
│   ├── .DS_Store
│   ├── .gitignore
│   ├── CACHEDIR.TAG
│   ├── README.md
│   └── v
│       ├── .DS_Store
│       └── cache
│           ├── lastfailed
│           └── nodeids
├── .ruff_cache
│   ├── .DS_Store
│   ├── .gitignore
│   ├── 0.15.4
│   │   ├── 11769362577780937454
│   │   ├── 14258909697906082855
│   │   ├── 14609678311717336435
│   │   ├── 16299831348104910745
│   │   ├── 16691333989523458449
│   │   ├── 1839087634039603776
│   │   ├── 2562534587137098541
│   │   ├── 2638191268474823350
│   │   ├── 4935058739576022294
│   │   ├── 7595672946193918431
│   │   ├── 80959239858002692
│   │   └── 8240099598702691558
│   └── CACHEDIR.TAG
├── DESIGN_GUIDE.md
├── DOSYA_YAPISI.md
├── Dockerfile
├── EMARE_AI_COLLECTIVE.md
├── EMARE_ANAYASA.md
├── EMARE_ORTAK_CALISMA -> /Users/emre/Desktop/Emare/EMARE_ORTAK_CALISMA
├── EMARE_ORTAK_HAFIZA.md
├── Emare Token
│   ├── .DS_Store
│   └── emare-token
│       ├── .DS_Store
│       ├── .env
│       ├── .env.example
│       ├── .eslintrc.json
│       ├── .gitignore
│       ├── .prettierrc
│       ├── .solhint.json
│       ├── .vscode
│       │   └── settings.json
│       ├── EmareCloud Token — Frontend & Deploy Paketi
│       │   ├── .DS_Store
│       │   ├── COPILOT_BEYIN.md
│       │   ├── EmareCloud Token — Frontend & Deploy Paketi.md
│       │   ├── INCELEME_RAPORU.md
│       │   ├── README.md
│       │   ├── dapp
│       │   └── website
│       ├── README.md
│       ├── artifacts
│       │   ├── @openzeppelin
│       │   ├── build-info
│       │   └── contracts
│       ├── cache
│       │   └── solidity-files-cache.json
│       ├── contracts
│       │   ├── EmareGovernance.sol
│       │   ├── EmareMarketplace.sol
│       │   ├── EmareRewardPool.sol
│       │   ├── EmareSettlement.sol
│       │   ├── EmareStaking.sol
│       │   ├── EmareToken.sol
│       │   └── EmareVesting.sol
│       ├── docs
│       │   ├── 01-proje-genel-bakis.md
│       │   ├── 02-akilli-kontratlar.md
│       │   ├── 03-deploy-rehberi.md
│       │   ├── 04-test-ve-is-akisi.md
│       │   ├── 05-gelistirme-ortami.md
│       │   ├── 06-reward-pool.md
│       │   ├── 07-marketplace.md
│       │   ├── 08-cloud-entegrasyon.md
│       │   ├── 09-tokenomics.md
│       │   ├── 10-security-audit-prep.md
│       │   ├── GOREV_LISTESI.md
│       │   └── WHITEPAPER.md
│       ├── gas-report.txt
│       ├── hardhat.config.ts
│       ├── package-lock.json
│       ├── package.json
│       ├── scripts
│       │   ├── deploy-all.ts
│       │   ├── deploy-marketplace.ts
│       │   ├── deploy-reward-pool.ts
│       │   ├── deploy-settlement.ts
│       │   ├── deploy-token.ts
│       │   └── update-addresses.ts
│       ├── test
│       │   ├── governance.test.ts
│       │   ├── integration.test.ts
│       │   ├── marketplace.test.ts
│       │   ├── reward-pool.test.ts
│       │   ├── settlement.test.ts
│       │   ├── staking.test.ts
│       │   ├── token.test.ts
│       │   └── vesting.test.ts
│       ├── tsconfig.json
│       └── typechain-types
│           ├── @openzeppelin
│           ├── common.ts
│           ├── contracts
│           ├── factories
│           ├── hardhat.d.ts
│           └── index.ts
├── Emarecloud hafıza.md
├── KULLANIM_KILAVUZU.md
├── PRODUCT_ROADMAP.md
├── README.md
├── SANAL_MAKINE_YONETIMI.md
├── YAZILIM_GELISTIRME.md
├── _diag.py
├── ai_assistant.py
├── alert_manager.py
├── app.py
├── audit.py
├── auth_routes.py
├── backup_manager.py
├── blockchain
│   ├── __init__.py
│   ├── contracts.py
│   ├── reward_engine.py
│   └── service.py
├── command_security.py
├── config.json
├── config.py
├── core
│   ├── .DS_Store
│   ├── __init__.py
│   ├── config_io.py
│   ├── database.py
│   ├── helpers.py
│   ├── logging_config.py
│   ├── middleware.py
│   └── tenant.py
├── crypto.py
├── docker-compose.yml
├── docs
│   ├── 00_INDEX.md
│   ├── 01_GENEL_BAKIS.md
│   ├── 02_KURULUM_VE_HIZLI_BASLANGIC.md
│   ├── 03_KULLANIM_REHBERI.md
│   ├── 04_API_VE_MODULLER.md
│   ├── 05_YAZILIM_GELISTIRME_YOL_HARITASI.md
│   ├── AI_ANAYASASI.md
│   ├── AI_PLATFORM_TASARIMI.md
│   ├── BLOCKCHAIN_ENTEGRASYON.md
│   ├── BUSINESS_BUILDER_VIZYON.md
│   ├── FATURALANDIRMA_SISTEMI.md
│   ├── HOSTING_BUILDER.md
│   ├── MULTI_TENANT_MIMARI.md
│   ├── MVP_KAPSAM.md
│   ├── RBAC_ENDPOINT_MATRIX.md
│   ├── REFACTOR_PLANI.md
│   └── TLS_REVERSE_PROXY.md
├── extensions.py
├── firewall_manager.py
├── gunicorn.conf.py
├── instance
│   ├── .ssh
│   │   ├── emarecloud_rsa
│   │   └── emarecloud_rsa.pub
│   ├── emarecloud.db
│   └── emarehosting.db
├── license_manager.py
├── market_apps.py
├── market_apps.py.bak
├── models.py
├── pyproject.toml
├── rbac.py
├── requirements-dev.txt
├── requirements.txt
├── routes
│   ├── .DS_Store
│   ├── __init__.py
│   ├── cloudflare.py
│   ├── commands.py
│   ├── firewall.py
│   ├── market.py
│   ├── metrics.py
│   ├── monitoring.py
│   ├── organizations.py
│   ├── pages.py
│   ├── servers.py
│   ├── storage.py
│   ├── terminal.py
│   ├── token.py
│   └── virtualization.py
├── scheduler.py
├── server_monitor.py
├── setup.sh
├── ssh_manager.py
├── static
│   ├── .DS_Store
│   ├── css
│   │   └── style.css
│   └── js
│       └── app.js
├── templates
│   ├── .DS_Store
│   ├── admin
│   │   ├── audit.html
│   │   └── users.html
│   ├── ai_backup.html
│   ├── ai_community_templates.html
│   ├── ai_cost.html
│   ├── ai_cross_cloud.html
│   ├── ai_ethics.html
│   ├── ai_gpu_pool.html
│   ├── ai_isolation.html
│   ├── ai_landing_gen.html
│   ├── ai_logs.html
│   ├── ai_market_intel.html
│   ├── ai_marketplace.html
│   ├── ai_mastery.html
│   ├── ai_migration.html
│   ├── ai_optimizer.html
│   ├── ai_orchestrator.html
│   ├── ai_performance.html
│   ├── ai_revenue.html
│   ├── ai_saas_builder.html
│   ├── ai_sandbox.html
│   ├── ai_security.html
│   ├── ai_self_healing.html
│   ├── ai_server_recommend.html
│   ├── ai_training.html
│   ├── ai_voice.html
│   ├── ai_whitelabel.html
│   ├── ai_wizard.html
│   ├── app_builder.html
│   ├── auth
│   │   ├── login.html
│   │   ├── profile.html
│   │   └── verify_2fa.html
│   ├── base.html
│   ├── cloudflare.html
│   ├── dashboard.html
│   ├── landing.html
│   ├── market.html
│   ├── monitoring.html
│   ├── server_detail.html
│   ├── server_map.html
│   ├── storage.html
│   ├── terminal.html
│   └── virtualization.html
├── tests
│   ├── .DS_Store
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_2fa.py
│   ├── test_api_token.py
│   ├── test_auth.py
│   ├── test_config.py
│   ├── test_market.py
│   ├── test_monitoring.py
│   ├── test_organization.py
│   ├── test_pages.py
│   ├── test_rbac.py
│   └── test_server.py
├── virtualization_manager.py
└── yeni fikirler.md

41 directories, 234 files

```

---

## 📌 Kullanım Talimatları (AI İçin)

Bu dosya, kod üretmeden önce projenin mevcut yapısını kontrol etmek içindir:

1. **Yeni dosya oluşturmadan önce:** Bu ağaçta benzer bir dosya var mı kontrol et
2. **Yeni klasör oluşturmadan önce:** Mevcut klasör yapısına uygun mu kontrol et
3. **Import/require yapmadan önce:** Dosya yolu doğru mu kontrol et
4. **Kod kopyalamadan önce:** Aynı fonksiyon başka dosyada var mı kontrol et

**Örnek:**
- ❌ "Yeni bir auth.py oluşturalım" → ✅ Kontrol et, zaten `app/auth.py` var mı?
- ❌ "config/ klasörü oluşturalım" → ✅ Kontrol et, zaten `config/` var mı?
- ❌ `from utils import helper` → ✅ Kontrol et, `utils/helper.py` gerçekten var mı?

---

**Not:** Bu dosya otomatik oluşturulmuştur. Proje yapısı değiştikçe güncellenmelidir.

```bash
# Güncelleme komutu
python3 /Users/emre/Desktop/Emare/create_dosya_yapisi.py
```
