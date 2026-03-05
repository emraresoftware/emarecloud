# Multi-Tenant Mimari Şeması

> EmareCloud OS — Tek organizasyondan çoklu kiracı (multi-tenant) yapıya geçiş.

---

## 1. Mevcut Durum vs. Hedef

| Özellik | Şu An (v1.0) | Hedef (v2.0+) |
|---------|--------------|---------------|
| Organizasyon | Tek | Çoklu (multi-tenant) |
| Kullanıcı hiyerarşisi | Düz (user → role) | Ağaç (org → team → user) |
| Kaynak izolasyonu | Yok | Tenant bazlı kota |
| Veri izolasyonu | Tek config.json | Tenant-scoped DB |
| Faturalama | Yok | Tenant bazlı usage |
| Domain | Manuel | Tenant başına otomatik |

---

## 2. Tenant Hiyerarşisi

```
Platform (EmareCloud OS)
│
├── Organization (Tenant)          ← Müşteri şirketi
│   ├── Owner (super_admin)        ← Org sahibi
│   ├── Team                       ← Ekip (opsiyonel gruplama)
│   │   ├── Admin
│   │   ├── Operator
│   │   └── Viewer
│   ├── Servers[]                  ← Bu org'a atanmış sunucular
│   ├── Packages[]                 ← Bu org'un tanımladığı paketler
│   ├── Customers[]                ← Bu org'un alt müşterileri
│   │   ├── Sub-user
│   │   └── Allocated Resources
│   ├── API Keys[]                 ← Org seviyesi API anahtarları
│   └── Billing                    ← Fatura/ödeme bilgileri
│
├── Organization B (Tenant)
│   └── ...
│
└── Platform Admin (God Mode)
    ├── Tüm tenant'ları görebilir
    ├── Lisans yönetimi
    ├── Platform metrikleri
    └── Global ayarlar
```

---

## 3. Veritabanı Şeması (Yeni Tablolar)

### 3.1 organizations

```sql
CREATE TABLE organizations (
    id              TEXT PRIMARY KEY,        -- UUID
    name            TEXT NOT NULL,           -- "Acme Hosting"
    slug            TEXT UNIQUE NOT NULL,    -- "acme-hosting" (subdomain)
    plan            TEXT DEFAULT 'starter',  -- starter | growth | enterprise
    status          TEXT DEFAULT 'active',   -- active | suspended | cancelled
    owner_id        TEXT NOT NULL,           -- users.id FK
    
    -- Kaynak limitleri
    max_servers     INTEGER DEFAULT 5,
    max_users       INTEGER DEFAULT 10,
    max_customers   INTEGER DEFAULT 0,      -- 0 = hosting builder kapalı
    max_storage_gb  INTEGER DEFAULT 100,
    max_bandwidth_gb INTEGER DEFAULT 500,
    
    -- Ayarlar
    custom_domain   TEXT,                    -- "panel.acmehosting.com"
    logo_url        TEXT,
    primary_color   TEXT DEFAULT '#6C63FF',
    
    -- Meta
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    trial_ends_at   DATETIME,
    
    FOREIGN KEY (owner_id) REFERENCES users(id)
);
```

### 3.2 org_members

```sql
CREATE TABLE org_members (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    role            TEXT NOT NULL,           -- owner | admin | operator | viewer
    team_id         TEXT,                    -- teams.id FK (opsiyonel)
    invited_by      TEXT,
    joined_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(org_id, user_id),
    FOREIGN KEY (org_id) REFERENCES organizations(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### 3.3 teams

```sql
CREATE TABLE teams (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    name            TEXT NOT NULL,           -- "DevOps", "Frontend"
    description     TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(org_id, name),
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);
```

### 3.4 org_servers (sunucu-tenant ilişkisi)

```sql
CREATE TABLE org_servers (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    server_id       TEXT NOT NULL,           -- config.json'daki sunucu ID
    
    -- Kaynak kotası (bu sunucu için)
    cpu_limit       INTEGER,                 -- vCPU sayısı
    ram_limit_mb    INTEGER,                 -- MB cinsinden
    disk_limit_gb   INTEGER,                 -- GB cinsinden
    bandwidth_limit_gb INTEGER,
    
    assigned_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    assigned_by     TEXT,
    
    UNIQUE(org_id, server_id),
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);
```

### 3.5 org_api_keys

```sql
CREATE TABLE org_api_keys (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    name            TEXT NOT NULL,           -- "Production API Key"
    key_hash        TEXT NOT NULL,           -- SHA-256 hash
    key_prefix      TEXT NOT NULL,           -- "emh_live_abc..." (ilk 8 karakter)
    permissions     TEXT DEFAULT '[]',       -- JSON array: ["servers:read", "metrics:read"]
    
    rate_limit      INTEGER DEFAULT 1000,    -- requests/hour
    last_used_at    DATETIME,
    expires_at      DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);
```

---

## 4. Veri İzolasyon Stratejisi

### Yaklaşım: Shared Database, Tenant-Scoped Queries

Her sorgu tenant bağlamında çalışır. Middleware seviyesinde `g.current_org` set edilir.

```python
# core/tenant.py — Tenant context middleware

from flask import g, session, abort
from functools import wraps

def resolve_tenant():
    """Her request'te çalışır, aktif tenant'ı belirler."""
    user_id = session.get('user_id')
    if not user_id:
        return
    
    # Kullanıcının aktif organizasyonu
    org_id = session.get('active_org_id')
    if org_id:
        org = db.get_organization(org_id)
        if org and org['status'] == 'active':
            g.current_org = org
            g.current_org_id = org['id']
            return
    
    # Varsayılan: kullanıcının ilk org'u
    orgs = db.get_user_organizations(user_id)
    if orgs:
        g.current_org = orgs[0]
        g.current_org_id = orgs[0]['id']

def tenant_required(f):
    """Endpoint'in tenant bağlamında çalışmasını zorunlu kılar."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not hasattr(g, 'current_org') or not g.current_org:
            abort(403, 'Organizasyon bağlamı gerekli')
        return f(*args, **kwargs)
    return decorated

def tenant_scoped_query(query, params=None):
    """Sorguya otomatik org_id filtresi ekler."""
    org_id = getattr(g, 'current_org_id', None)
    if not org_id:
        raise ValueError('Tenant context yok')
    # ... query'ye WHERE org_id = ? ekle
```

### İzolasyon Seviyeleri

| Veri Tipi | İzolasyon | Açıklama |
|-----------|-----------|----------|
| Sunucular | Tenant-scoped | org_servers tablosu ile |
| Kullanıcılar | Tenant-scoped | org_members tablosu ile |
| Config | Tenant-scoped | JSON → org bazlı partition |
| SSH bağlantıları | Tenant-scoped | Sadece kendi sunucularına |
| Metrikler | Tenant-scoped | Sadece kendi sunucu metrikleri |
| Market kurulumları | Tenant-scoped | Kendi sunucularında |
| API keys | Tenant-scoped | org_api_keys tablosu |
| Audit log | Tenant-scoped | org_id sütunu eklenir |
| Platform ayarları | Global | Platform admin erişimli |

---

## 5. RBAC Genişleme

### Mevcut (v1.0) → Yeni (v2.0)

```
v1.0 Rolleri:              v2.0 Rolleri:
─────────────              ─────────────
super_admin    ───────►    platform_admin (God mode)
                           org_owner
admin          ───────►    org_admin
operator       ───────►    org_operator
read_only      ───────►    org_viewer
                           customer (alt müşteri)
                           api_key (programatik erişim)
```

### Yetki Matrisi (Genişletilmiş)

| İşlem | platform_admin | org_owner | org_admin | org_operator | org_viewer | customer |
|-------|---------------|-----------|-----------|-------------|------------|----------|
| Org oluştur | ✅ | — | — | — | — | — |
| Org ayarları | ✅ | ✅ | — | — | — | — |
| Üye davet | ✅ | ✅ | ✅ | — | — | — |
| Sunucu ekle | ✅ | ✅ | ✅ | — | — | — |
| Sunucu bağlan | ✅ | ✅ | ✅ | ✅ | — | — |
| Metrik gör | ✅ | ✅ | ✅ | ✅ | ✅ | 🔒* |
| Terminal | ✅ | ✅ | ✅ | ✅ | — | — |
| Market kur | ✅ | ✅ | ✅ | — | — | — |
| Müşteri yönet | ✅ | ✅ | ✅ | — | — | — |
| API key oluştur | ✅ | ✅ | ✅ | — | — | — |
| Fatura gör | ✅ | ✅ | — | — | — | ✅ |

🔒* = Sadece kendisine atanmış kaynaklar

---

## 6. URL Yapısı

### Seçenek A: Subdomain Bazlı (Önerilen)

```
https://app.emarecloud.com/           → Platform dashboard
https://acme.emarecloud.com/          → Acme org dashboard
https://panel.acmehosting.com/          → Custom domain (white-label)
```

### Seçenek B: Path Bazlı (Daha Kolay Uygulama, İlk Faz)

```
https://panel.emarecloud.com/org/acme/dashboard
https://panel.emarecloud.com/org/acme/servers
https://panel.emarecloud.com/org/acme/billing
https://panel.emarecloud.com/org/acme/customers
```

### API URL Yapısı

```
GET  /api/v2/org/{org_id}/servers
POST /api/v2/org/{org_id}/servers
GET  /api/v2/org/{org_id}/servers/{id}/metrics
GET  /api/v2/org/{org_id}/customers
POST /api/v2/org/{org_id}/api-keys
GET  /api/v2/org/{org_id}/billing/usage
```

---

## 7. White-Label Desteği

Enterprise tenant'lar kendi markalarını kullanabilir:

```python
# Tenant tema yapılandırması
{
    "org_id": "acme-123",
    "branding": {
        "name": "AcmeCloud",
        "logo": "/uploads/acme/logo.svg",
        "favicon": "/uploads/acme/favicon.ico",
        "primary_color": "#FF6B35",
        "accent_color": "#004E89",
        "custom_domain": "panel.acmecloud.io",
        "footer_text": "© 2026 AcmeCloud",
        "hide_emarecloud_badge": true  # Enterprise only
    }
}
```

### Jinja2 Template Adaptasyonu

```html
<!-- base.html — White-label desteği -->
<title>{{ g.current_org.branding.name | default('EmareCloud') }}</title>
<link rel="icon" href="{{ g.current_org.branding.favicon | default('/static/favicon.ico') }}">
<style>
  :root {
    --primary: {{ g.current_org.branding.primary_color | default('#6C63FF') }};
    --accent: {{ g.current_org.branding.accent_color | default('#5A52D5') }};
  }
</style>
```

---

## 8. Migrasyon Stratejisi (v1 → v2)

### Adım 1: Varsayılan Organizasyon Oluştur

```python
def migrate_to_multi_tenant():
    """Mevcut tek-tenant veriyi multi-tenant'a dönüştür."""
    
    # 1. Varsayılan org oluştur
    default_org = {
        'id': generate_uuid(),
        'name': 'Default Organization',
        'slug': 'default',
        'plan': 'enterprise',  # Mevcut tüm özellikler açık
        'owner_id': get_first_super_admin_id(),
        'max_servers': 999,
    }
    db.create_organization(default_org)
    
    # 2. Mevcut kullanıcıları org'a ata
    for user in db.get_all_users():
        db.add_org_member(default_org['id'], user['id'], user['role'])
    
    # 3. Mevcut sunucuları org'a ata
    for server in config.get_servers():
        db.assign_server_to_org(default_org['id'], server['id'])
    
    # 4. Audit log'lara org_id ekle
    db.backfill_audit_logs(default_org['id'])
```

### Adım 2: Geriye Uyumlu API

```python
# Eski API (v1) — geriye uyumlu kalır
@app.route('/api/servers')
@login_required
def list_servers_v1():
    # Otomatik olarak aktif org'un sunucularını döndür
    return list_servers_for_org(g.current_org_id)

# Yeni API (v2) — explicit org context
@app.route('/api/v2/org/<org_id>/servers')
@login_required
@tenant_required
def list_servers_v2(org_id):
    verify_org_access(org_id)
    return list_servers_for_org(org_id)
```

---

## 9. Kaynak Kotası ve İzleme

### Kota Kontrol Akışı

```
İstek → Auth → Tenant Resolve → Kota Kontrol → İşlem → Usage Log
                    │                  │                    │
                    ▼                  ▼                    ▼
              g.current_org    Limit aşıldı?         usage_logs tablosu
                               ├── Hayır → Devam
                               └── Evet → 429 Too Many Resources
```

### usage_logs tablosu

```sql
CREATE TABLE usage_logs (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL,
    metric      TEXT NOT NULL,       -- "servers" | "bandwidth" | "storage" | "api_calls"
    value       REAL NOT NULL,       -- Metrik değeri
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

-- Günlük özet
CREATE TABLE usage_daily (
    id          TEXT PRIMARY KEY,
    org_id      TEXT NOT NULL,
    date        DATE NOT NULL,
    metric      TEXT NOT NULL,
    total       REAL NOT NULL,
    peak        REAL NOT NULL,
    
    UNIQUE(org_id, date, metric)
);
```

---

## 10. Uygulama Öncelik Sırası

| Sıra | Modül | Karmaşıklık | Süre | Bağımlılık |
|------|-------|-------------|------|------------|
| 1 | organizations tablosu + CRUD | Düşük | 1 hafta | — |
| 2 | org_members + tenant middleware | Orta | 1 hafta | #1 |
| 3 | Sunucu-tenant ilişkisi (org_servers) | Orta | 1 hafta | #1 |
| 4 | Tenant-scoped sorgular (tüm route'lar) | Yüksek | 2 hafta | #2, #3 |
| 5 | v1 → v2 migrasyon scripti | Orta | 3 gün | #1-4 |
| 6 | Org switcher UI | Düşük | 3 gün | #2 |
| 7 | White-label tema | Düşük | 1 hafta | #1 |
| 8 | API key sistemi | Orta | 1 hafta | #2 |
| 9 | Kaynak kotası + usage tracking | Yüksek | 2 hafta | #3, #4 |

**Toplam tahmini süre: 8-10 hafta**

---

## 11. Güvenlik Hususları

- **Tenant leakage önleme:** Tüm DB sorguları `org_id` filtreli olmalı. ORM kullanılıyorsa default scope.
- **Cross-tenant erişim:** Farklı org'un sunucusuna/verisine erişim 403 ile engellenecek.
- **API key izolasyonu:** Her API key sadece kendi org'unun kaynaklarına erişebilir.
- **Audit:** Tenant-scoped audit log — hangi org'da kim ne yaptı.
- **Data deletion:** Org silindiğinde tüm bağlı veriler kaskad silinmeli (GDPR uyumlu).
- **Rate limiting:** Tenant bazlı API rate limit (plan'a göre değişken).

---

*Doküman: EmareCloud OS — Multi-Tenant Mimari Şeması v1.0*
*Tarih: Mart 2026*
