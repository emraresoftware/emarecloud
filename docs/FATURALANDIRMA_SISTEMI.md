# Faturalandırma Sistemi Taslağı

> EmareCloud OS — Kullanım bazlı faturalandırma, paket yönetimi ve ödeme altyapısı.

---

## 1. Genel Bakış

EmareCloud'in 3 farklı faturalama modeli olacak:

| Model | Kime | Ne Faturalanır |
|-------|------|---------------|
| **Platform → Tenant** | EmareCloud müşterisi | Org planı (Starter/Growth/Enterprise) |
| **Tenant → Müşteri** | Tenant'ın kendi müşterisi | Hosting paketi, kaynak kullanımı |
| **AI Platform** | API kullanıcısı | Token/istek bazlı AI kullanımı |

---

## 2. Platform Plan Yapısı

### EmareCloud Planları

```
┌──────────────┬──────────────┬──────────────┬──────────────┐
│              │   Starter    │    Growth    │  Enterprise  │
├──────────────┼──────────────┼──────────────┼──────────────┤
│ Fiyat/ay     │ $29          │ $99          │ $299+        │
│ Sunucu       │ 5            │ 25           │ Sınırsız     │
│ Kullanıcı    │ 3            │ 15           │ Sınırsız     │
│ Müşteri      │ —            │ 50           │ Sınırsız     │
│ API istek/ay │ 10K          │ 100K         │ Sınırsız     │
│ AI model     │ 1            │ 5            │ Sınırsız     │
│ Depolama     │ 50 GB        │ 500 GB       │ Özel         │
│ White-label  │ —            │ Logo+Renk    │ Tam          │
│ Destek       │ E-posta      │ Öncelikli    │ Özel kanal   │
│ SLA          │ —            │ %99.5        │ %99.9        │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

---

## 3. Veritabanı Şeması

### 3.1 plans (Platform planları)

```sql
CREATE TABLE plans (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,           -- "Starter", "Growth", "Enterprise"
    slug            TEXT UNIQUE NOT NULL,    -- "starter", "growth", "enterprise"
    type            TEXT NOT NULL,           -- "platform" | "hosting" | "ai"
    
    -- Fiyatlandırma
    price_monthly   REAL NOT NULL,           -- Aylık fiyat (USD cent)
    price_yearly    REAL,                    -- Yıllık fiyat (indirimli)
    currency        TEXT DEFAULT 'USD',
    
    -- Limitler (JSON)
    limits          TEXT NOT NULL,           -- JSON: {"servers": 5, "users": 3, ...}
    
    -- Özellikler (JSON)
    features        TEXT NOT NULL,           -- JSON: ["ssh", "firewall", "market", ...]
    
    is_active       BOOLEAN DEFAULT TRUE,
    sort_order      INTEGER DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 3.2 subscriptions (Abonelikler)

```sql
CREATE TABLE subscriptions (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    plan_id         TEXT NOT NULL,
    status          TEXT DEFAULT 'active',   -- active | past_due | cancelled | trialing
    
    -- Dönem
    current_period_start DATETIME NOT NULL,
    current_period_end   DATETIME NOT NULL,
    trial_end       DATETIME,
    cancelled_at    DATETIME,
    
    -- Ödeme
    payment_method_id TEXT,
    payment_provider  TEXT,                  -- "stripe" | "iyzico" | "manual"
    external_id     TEXT,                    -- Stripe subscription ID vb.
    
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (org_id) REFERENCES organizations(id),
    FOREIGN KEY (plan_id) REFERENCES plans(id)
);
```

### 3.3 invoices (Faturalar)

```sql
CREATE TABLE invoices (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    subscription_id TEXT,
    
    -- Fatura bilgileri
    invoice_number  TEXT UNIQUE NOT NULL,    -- "EMH-2026-00001"
    status          TEXT DEFAULT 'draft',    -- draft | pending | paid | overdue | cancelled
    
    -- Tutarlar (cent cinsinden)
    subtotal        INTEGER NOT NULL,        -- Alt toplam
    tax_rate        REAL DEFAULT 0,          -- Vergi oranı (0.20 = %20)
    tax_amount      INTEGER DEFAULT 0,       -- Vergi tutarı
    discount_amount INTEGER DEFAULT 0,       -- İndirim
    total           INTEGER NOT NULL,        -- Genel toplam
    currency        TEXT DEFAULT 'USD',
    
    -- Tarihler
    issue_date      DATE NOT NULL,
    due_date        DATE NOT NULL,
    paid_at         DATETIME,
    
    -- Detay
    line_items      TEXT NOT NULL,           -- JSON array
    notes           TEXT,
    
    -- Müşteri bilgileri (snapshot)
    billing_name    TEXT,
    billing_email   TEXT,
    billing_address TEXT,                    -- JSON
    tax_id          TEXT,                    -- Vergi no
    
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (org_id) REFERENCES organizations(id),
    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
);
```

### 3.4 invoice_line_items (Fatura kalemleri)

```sql
CREATE TABLE invoice_line_items (
    id              TEXT PRIMARY KEY,
    invoice_id      TEXT NOT NULL,
    
    description     TEXT NOT NULL,           -- "Growth Plan - Mart 2026"
    type            TEXT NOT NULL,           -- "subscription" | "usage" | "addon" | "credit"
    quantity        REAL DEFAULT 1,
    unit_price      INTEGER NOT NULL,        -- Birim fiyat (cent)
    amount          INTEGER NOT NULL,        -- Toplam (cent)
    
    -- Kullanım bazlı ise
    usage_metric    TEXT,                    -- "api_calls" | "bandwidth_gb" | "ai_tokens"
    usage_quantity  REAL,
    
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);
```

### 3.5 payment_methods (Ödeme yöntemleri)

```sql
CREATE TABLE payment_methods (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    
    type            TEXT NOT NULL,           -- "card" | "bank_transfer" | "paypal"
    provider        TEXT NOT NULL,           -- "stripe" | "iyzico"
    external_id     TEXT,                    -- Provider token
    
    -- Kart bilgileri (maskelenmiş)
    last_four       TEXT,                    -- "4242"
    brand           TEXT,                    -- "visa" | "mastercard"
    exp_month       INTEGER,
    exp_year        INTEGER,
    
    is_default      BOOLEAN DEFAULT FALSE,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);
```

### 3.6 usage_records (Kullanım kayıtları)

```sql
CREATE TABLE usage_records (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    subscription_id TEXT,
    
    metric          TEXT NOT NULL,           -- "api_calls" | "bandwidth_gb" | "ai_tokens" | "storage_gb"
    quantity        REAL NOT NULL,
    unit_price      INTEGER,                -- Birim fiyat (cent) — usage billing için
    
    period_start    DATETIME NOT NULL,
    period_end      DATETIME NOT NULL,
    recorded_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    billed          BOOLEAN DEFAULT FALSE,   -- Faturalandı mı?
    invoice_id      TEXT,
    
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);
```

---

## 4. Faturalama Akışı

### 4.1 Abonelik Yaşam Döngüsü

```
Kayıt → Trial (14 gün) → Aktif Abonelik → Yenileme
                │                              │
                ▼                              ▼
        Trial bitti?              Ödeme başarılı?
        ├── Ödeme var → Aktif     ├── Evet → Yeni dönem
        └── Yok → Suspended      └── Hayır → Past Due
                                        │
                                        ▼ (3 gün sonra)
                                    Cancelled
```

### 4.2 Aylık Faturalama Süreci

```python
# billing/invoice_generator.py

def generate_monthly_invoices():
    """Her ay 1'inde çalışır — tüm aktif abonelikler için fatura oluşturur."""
    
    active_subs = db.get_active_subscriptions()
    
    for sub in active_subs:
        org = db.get_organization(sub['org_id'])
        plan = db.get_plan(sub['plan_id'])
        
        line_items = []
        
        # 1. Plan ücreti
        line_items.append({
            'description': f"{plan['name']} Plan — {current_month}",
            'type': 'subscription',
            'quantity': 1,
            'unit_price': plan['price_monthly'],
            'amount': plan['price_monthly']
        })
        
        # 2. Kullanım fazlası
        overages = calculate_overages(org['id'], sub['current_period_start'])
        for overage in overages:
            line_items.append({
                'description': f"Fazla kullanım: {overage['metric']}",
                'type': 'usage',
                'quantity': overage['excess'],
                'unit_price': overage['unit_price'],
                'amount': overage['total']
            })
        
        # 3. Fatura oluştur
        invoice = create_invoice(
            org_id=org['id'],
            subscription_id=sub['id'],
            line_items=line_items,
            due_date=calculate_due_date()
        )
        
        # 4. Otomatik ödeme dene
        if org.get('auto_pay') and org.get('default_payment_method'):
            try_auto_payment(invoice)
        else:
            send_invoice_email(org, invoice)
```

### 4.3 Kullanım Fazlası Hesaplama

```python
OVERAGE_PRICING = {
    'servers': {'unit': 'sunucu', 'price_per_unit': 500},        # $5/sunucu
    'api_calls': {'unit': '1000 istek', 'price_per_unit': 100},  # $1/1K istek
    'bandwidth_gb': {'unit': 'GB', 'price_per_unit': 10},        # $0.10/GB
    'ai_tokens': {'unit': '1K token', 'price_per_unit': 50},     # $0.50/1K token
    'storage_gb': {'unit': 'GB', 'price_per_unit': 5},           # $0.05/GB
}

def calculate_overages(org_id, period_start):
    """Kullanım limitini aşan metrikleri hesaplar."""
    org = db.get_organization(org_id)
    plan = db.get_plan(org['plan_id'])
    limits = json.loads(plan['limits'])
    
    overages = []
    for metric, limit in limits.items():
        actual_usage = db.get_usage_total(org_id, metric, period_start)
        if actual_usage > limit:
            excess = actual_usage - limit
            pricing = OVERAGE_PRICING.get(metric, {})
            overages.append({
                'metric': metric,
                'limit': limit,
                'actual': actual_usage,
                'excess': excess,
                'unit_price': pricing.get('price_per_unit', 0),
                'total': excess * pricing.get('price_per_unit', 0)
            })
    
    return overages
```

---

## 5. Ödeme Entegrasyonları

### 5.1 Desteklenecek Ödeme Sağlayıcıları

| Sağlayıcı | Bölge | Özellik |
|-----------|-------|---------|
| **Stripe** | Global | Kart, abonelik, fatura, webhook |
| **Iyzico** | Türkiye | Kart, BKM Express, havale |
| **PayPal** | Global | Kart, PayPal bakiye |
| **Havale/EFT** | Türkiye | Manuel onaylı |

### 5.2 Payment Provider Interface

```python
# billing/providers/base.py

from abc import ABC, abstractmethod

class PaymentProvider(ABC):
    """Ödeme sağlayıcı arayüzü."""
    
    @abstractmethod
    def create_customer(self, org_id: str, email: str, name: str) -> str:
        """Provider'da müşteri oluştur, external_id döndür."""
        pass
    
    @abstractmethod
    def add_payment_method(self, customer_id: str, token: str) -> dict:
        """Ödeme yöntemi ekle."""
        pass
    
    @abstractmethod
    def charge(self, customer_id: str, amount: int, currency: str, 
               description: str) -> dict:
        """Ödeme al. amount cent cinsinden."""
        pass
    
    @abstractmethod
    def create_subscription(self, customer_id: str, plan_id: str) -> dict:
        """Abonelik oluştur."""
        pass
    
    @abstractmethod
    def cancel_subscription(self, subscription_id: str) -> dict:
        """Abonelik iptal."""
        pass
    
    @abstractmethod
    def refund(self, charge_id: str, amount: int = None) -> dict:
        """İade. amount=None ise tam iade."""
        pass
    
    @abstractmethod
    def handle_webhook(self, payload: dict, signature: str) -> dict:
        """Webhook işle."""
        pass
```

### 5.3 Stripe Implementasyonu (Örnek)

```python
# billing/providers/stripe_provider.py

import stripe
from .base import PaymentProvider

class StripeProvider(PaymentProvider):
    def __init__(self, api_key: str):
        stripe.api_key = api_key
    
    def create_customer(self, org_id, email, name):
        customer = stripe.Customer.create(
            email=email,
            name=name,
            metadata={'org_id': org_id}
        )
        return customer.id
    
    def charge(self, customer_id, amount, currency, description):
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency=currency,
            customer=customer_id,
            description=description,
            confirm=True,
            off_session=True
        )
        return {
            'id': intent.id,
            'status': intent.status,
            'amount': intent.amount
        }
    
    def handle_webhook(self, payload, signature):
        event = stripe.Webhook.construct_event(
            payload, signature, self.webhook_secret
        )
        
        handlers = {
            'invoice.paid': self._handle_invoice_paid,
            'invoice.payment_failed': self._handle_payment_failed,
            'customer.subscription.deleted': self._handle_sub_cancelled,
        }
        
        handler = handlers.get(event['type'])
        if handler:
            return handler(event['data']['object'])
```

---

## 6. Webhook Olayları

### Dahili Webhook'lar (Tenant'a gönderilir)

```json
{
    "event": "invoice.created",
    "timestamp": "2026-03-01T00:00:00Z",
    "org_id": "acme-123",
    "data": {
        "invoice_id": "INV-2026-00042",
        "amount": 9900,
        "currency": "USD",
        "status": "pending",
        "due_date": "2026-03-15",
        "line_items": [
            {
                "description": "Growth Plan - Mart 2026",
                "amount": 9900
            }
        ]
    }
}
```

### Desteklenen Olaylar

| Olay | Tetikleyici |
|------|-------------|
| `invoice.created` | Yeni fatura oluştu |
| `invoice.paid` | Ödeme alındı |
| `invoice.overdue` | Ödeme vadesi geçti |
| `subscription.created` | Yeni abonelik |
| `subscription.renewed` | Abonelik yenilendi |
| `subscription.cancelled` | Abonelik iptal |
| `subscription.suspended` | Ödeme alamama — askıya alındı |
| `usage.limit_warning` | Kullanım %80'e ulaştı |
| `usage.limit_exceeded` | Kullanım limiti aşıldı |

---

## 7. Fatura UI Bileşenleri

### Dashboard Widget

```
┌─────────────────────────────────────┐
│ 💰 Faturalandırma Özeti             │
├─────────────────────────────────────┤
│ Plan: Growth         $99/ay        │
│ Dönem: 1-31 Mart 2026              │
│ Sonraki ödeme: 1 Nisan 2026        │
│                                     │
│ Kullanım:                           │
│ ████████░░ Sunucu    18/25          │
│ ██░░░░░░░░ API       12K/100K      │
│ █████░░░░░ Depolama  256/500 GB    │
│                                     │
│ [Faturalarım]  [Plan Değiştir]     │
└─────────────────────────────────────┘
```

### Fatura Listesi

```
┌───────────────────────────────────────────────────┐
│ 📄 Faturalar                                      │
├──────────┬────────────┬──────────┬────────┬───────┤
│ No       │ Tarih      │ Tutar    │ Durum  │       │
├──────────┼────────────┼──────────┼────────┼───────┤
│ EMH-0042 │ 01.03.2026 │ $99.00   │ ✅ Ödendi│ PDF  │
│ EMH-0035 │ 01.02.2026 │ $99.00   │ ✅ Ödendi│ PDF  │
│ EMH-0028 │ 01.01.2026 │ $109.50  │ ✅ Ödendi│ PDF  │
│ EMH-0021 │ 01.12.2025 │ $99.00   │ ✅ Ödendi│ PDF  │
└──────────┴────────────┴──────────┴────────┴───────┘
```

---

## 8. Tenant → Müşteri Faturalandırma

Hosting Builder modunda tenant kendi müşterilerine fatura kesebilir:

```python
# Tenant'ın kendi paket tanımları
tenant_packages = [
    {
        "name": "Başlangıç Hosting",
        "price": 4999,          # 49.99 TRY
        "currency": "TRY",
        "limits": {
            "disk_gb": 10,
            "bandwidth_gb": 100,
            "domains": 1,
            "email_accounts": 5
        }
    },
    {
        "name": "Profesyonel Hosting", 
        "price": 14999,         # 149.99 TRY
        "limits": {
            "disk_gb": 50,
            "bandwidth_gb": 500,
            "domains": 10,
            "email_accounts": 50
        }
    }
]
```

Tenant faturalama akışı:

```
Tenant Panel → Müşteri Paket Seç → Kaynak Ata → Fatura Oluştur → Ödeme Al
                                                        │
                                                        ▼
                                               Tenant'ın kendi
                                               ödeme entegrasyonu
                                               (Iyzico, Stripe, vb.)
```

---

## 9. Uygulama Öncelik Sırası

| Sıra | Modül | Karmaşıklık | Süre |
|------|-------|-------------|------|
| 1 | plans tablosu + CRUD | Düşük | 3 gün |
| 2 | subscriptions tablosu + yaşam döngüsü | Orta | 1 hafta |
| 3 | invoices + line_items oluşturma | Orta | 1 hafta |
| 4 | usage_records toplama + hesaplama | Yüksek | 2 hafta |
| 5 | Ödeme provider arayüzü (abstract) | Orta | 3 gün |
| 6 | Stripe entegrasyonu | Orta | 1 hafta |
| 7 | Fatura UI (liste + detay + PDF) | Orta | 1 hafta |
| 8 | Billing dashboard widget | Düşük | 3 gün |
| 9 | Webhook sistemi | Orta | 1 hafta |
| 10 | Iyzico entegrasyonu (TR pazar) | Orta | 1 hafta |

**Toplam tahmini süre: 8-10 hafta**

---

## 10. Güvenlik ve Uyumluk

- **PCI-DSS:** Kart bilgileri asla saklanmaz — tokenizasyon (Stripe/Iyzico) kullanılır.
- **KVKK/GDPR:** Fatura verileri şifreli saklanır, silme hakkı desteklenir.
- **Vergi:** Ülkeye göre KDV/VAT otomatik hesaplama.
- **Fatura numaralama:** Kesintisiz sıralı numara (yasal zorunluluk).
- **Audit trail:** Tüm fatura/ödeme işlemleri audit log'a kaydedilir.
- **Webhook imzalama:** Giden webhook'lar HMAC-SHA256 ile imzalanır.

---

*Doküman: EmareCloud OS — Faturalandırma Sistemi Taslağı v1.0*
*Tarih: Mart 2026*
