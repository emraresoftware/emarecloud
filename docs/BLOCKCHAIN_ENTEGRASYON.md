# EmareToken Blockchain Entegrasyonu

> EmareCloud OS — EMARE token ekosistemiyle on-chain entegrasyon mimarisi.
> Cüzdan yönetimi, EP ödül sistemi, RewardPool, Marketplace ve Settlement bağlantısı.

---

## 1. Genel Bakış

EmareCloud, **EmareToken (EMARE/EMR)** ERC20 token ekosistemiyle entegre çalışır.
Bu entegrasyon, Cloud platformu kullanıcılarının:

- 🪙 **EMARE token bakiyelerini** görüntülemesini
- 💰 **Emare Puanı (EP)** kazanarak EMR token elde etmesini
- 🛒 **On-chain Marketplace** ürünlerini keşfetmesini
- 🔐 **Settlement (Escrow)** siparişlerini takip etmesini

sağlar.

### Ekosistem Haritası

```
┌────────────────────────────────────────────────────────────────┐
│                    EmareCloud Platform                          │
│                                                                │
│  ┌──────────┐  ┌───────────┐  ┌───────────┐  ┌────────────┐  │
│  │ Sunucu   │  │   Market   │  │ İzleme    │  │ AI Platform│  │
│  │ Yönetimi │  │ (58+ App)  │  │ & Alarm   │  │ (Gateway)  │  │
│  └────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬──────┘  │
│       │              │              │              │          │
│       └──────────────┼──────────────┼──────────────┘          │
│                      │              │                          │
│               ┌──────▼──────────────▼──────┐                  │
│               │    blockchain/ modülü       │                  │
│               │                             │                  │
│               │  service.py    → Web3 RPC   │                  │
│               │  contracts.py  → ABI        │                  │
│               │  reward_engine → EP motoru  │                  │
│               └──────────────┬──────────────┘                  │
│                              │                                 │
└──────────────────────────────┼─────────────────────────────────┘
                               │ Web3.py (HTTP/WS RPC)
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                   Blockchain (BSC / EVM)                         │
│                                                                  │
│  ┌──────────────┐ ┌──────────────┐ ┌───────────┐ ┌───────────┐ │
│  │ EmareToken   │ │ RewardPool   │ │Marketplace│ │Settlement │ │
│  │ (ERC20)      │ │ (EP→EMR)     │ │(Ürün Satış│ │(Escrow)   │ │
│  │              │ │              │ │           │ │           │ │
│  │ 1B MAX_SUPPLY│ │ Oracle+Merkle│ │ %70/%20/%10│ │ Hakem sist│ │
│  │ Mint/Burn/   │ │ Anti-fraud   │ │ Rating    │ │ Dispute   │ │
│  │ Pause/Permit │ │ 7 gün cool.  │ │ İade      │ │ Timeout   │ │
│  └──────────────┘ └──────────────┘ └───────────┘ └───────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Dosya Yapısı

```
blockchain/
├── __init__.py          →  Modül init
├── contracts.py         →  4 kontratın minimal ABI tanımları
├── service.py           →  BlockchainService sınıfı (Web3 RPC işlemleri)
└── reward_engine.py     →  RewardEngine sınıfı (EP hesaplama + oracle claim)

routes/
└── token.py             →  Token & Blockchain API endpoint'leri (Blueprint)

models.py                →  +3 yeni model: UserWallet, EmarePoint, TokenTransaction
config.py                →  +8 yeni blockchain ayarı
```

---

## 3. Veritabanı Modelleri

### UserWallet
Kullanıcı EVM cüzdan adresleri. Her kullanıcının birden fazla cüzdanı olabilir, biri `is_primary`.

### EmarePoint
EP kazanım kayıtları. Kullanıcı aksiyonlarına göre (sunucu ekleme, ödeme, uptime vb.) 
biriktirilir. Periyodik olarak RewardPool kontratına oracle claim gönderilir.

### TokenTransaction
Blockchain işlem logları. Off-chain takip için kullanılır (claim, transfer, purchase).

---

## 4. API Endpoint'leri

| Method | Endpoint | Yetki | Açıklama |
|--------|----------|-------|----------|
| GET | `/api/token/info` | Login | EMARE token genel bilgileri |
| GET | `/api/token/balance` | Login | Kullanıcı token bakiyesi |
| POST | `/api/wallet/connect` | Login | Cüzdan bağlama |
| POST | `/api/wallet/disconnect` | Login | Cüzdan kaldırma |
| GET | `/api/wallet/list` | Login | Cüzdan listesi |
| GET | `/api/ep/summary` | Login | EP özet (toplam, günlük, claim durumu) |
| GET | `/api/ep/history` | Login | EP kazanım geçmişi (paginated) |
| GET | `/api/reward-pool/info` | Login | RewardPool kontrat bilgileri |
| GET | `/api/reward-pool/user` | Login | Kullanıcı on-chain ödül verileri |
| GET | `/api/token-marketplace/stats` | Login | On-chain marketplace istatistikleri |
| GET | `/api/token-marketplace/product/:id` | Login | On-chain ürün detayı |
| GET | `/api/settlement/order/:id` | Login | Escrow sipariş durumu |
| GET | `/api/settlement/stats` | Admin | Settlement istatistikleri |
| GET | `/api/admin/blockchain/status` | Admin | Blockchain bağlantı durumu |

---

## 5. EP Ödül Sistemi

### 5.1 Kazanım Tablosu

| Aksiyon | EP | Tip | Cooldown |
|---------|-----|-----|----------|
| Plan ödemesi | 100 | cashback | — |
| Uygulama satın alma | 50 | cashback | — |
| Kaynak yükseltme | 75 | cashback | — |
| Sunucu ekleme | 20 | work | 5 dk |
| Template paylaşma | 200 | marketplace | 1 saat |
| Hata raporu | 50 | work | — |
| %99+ uptime (aylık) | 150 | work | — |
| Alarm kuralı | 10 | work | — |
| Yedekleme profili | 15 | work | — |
| Referans kayıt | 500 | work | — |
| Referans ödeme | 1000 | work | — |
| Ürün listeleme | 30 | marketplace | 10 dk |
| Satış | 100 | marketplace | — |
| 5 yıldız | 25 | marketplace | — |

**Günlük Limit:** 5,000 EP / kullanıcı

### 5.2 EP → EMR Dönüşüm

$$EMR = \frac{EP}{epToEmrRate}$$

Varsayılan oran: 100 EP = 1 EMR

### 5.3 Claim Akışı

1. Kullanıcı Cloud platformunda aksiyonlar gerçekleştirir
2. `reward_engine.award_ep()` çağrılır → EmarePoint DB kaydı
3. Scheduler periyodik olarak `process_pending_claims()` çalıştırır
4. Unclaimed EP'leri olan kullanıcılar için `oracleClaim()` gönderilir
5. Kullanıcının cüzdanına EMR token aktarılır

---

## 6. Yapılandırma

### Ortam Değişkenleri

```bash
# .env dosyasına eklenecek:
BLOCKCHAIN_ENABLED=true
BLOCKCHAIN_RPC_URL=https://data-seed-prebsc-1-s1.binance.org:8545
BLOCKCHAIN_CHAIN_ID=97
EMARE_TOKEN_ADDRESS=0x...
EMARE_REWARD_POOL_ADDRESS=0x...
EMARE_MARKETPLACE_ADDRESS=0x...
EMARE_SETTLEMENT_ADDRESS=0x...
BLOCKCHAIN_ORACLE_PRIVATE_KEY=0x...
```

### Python Bağımlılığı

```
web3>=6.0.0
```

---

## 7. Güvenlik

| Katman | Uygulama |
|--------|----------|
| Private Key | Ortam değişkeni, asla DB'de veya kodda tutulmaz |
| Oracle Yetki | Sadece kayıtlı oracle adreslerinin yazma yetkisi var |
| Cüzdan Doğrulama | Faz 2'de EIP-712 imza doğrulama eklenecek |
| Fraud Koruması | 7 katman: kayıt bekleme, günlük limit, aylık tavan, fraud skoru, kara liste, Merkle proof, pausable |
| Rate Limiting | Cloud API rate limit + on-chain günlük claim limit |
| Audit | Tüm cüzdan ve token işlemleri audit log'a kaydedilir |

---

## 8. Gelecek Fazlar

- **Faz 2:** MetaMask imza doğrulama, token ile plan ödemesi, marketplace yazma işlemleri
- **Faz 3:** Event listener (WebSocket), gerçek zamanlı token takibi, bildirimler
- **Faz 4:** Cross-chain bridge, multi-chain desteği
