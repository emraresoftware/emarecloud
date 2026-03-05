# AI Platform Extension Tasarımı

> EmareCloud OS — AI Market'ten AI Platform'a dönüşüm. Model-as-API, token yönetimi, kullanım ölçümü.

---

## 1. Mevcut Durum → Hedef

| Özellik | Şu An (AI Market) | Hedef (AI Platform) |
|---------|-------------------|---------------------|
| Kurulum | Tek tıkla sunucuya kur | Tek tıkla kur + API expose |
| Erişim | Sadece sunucu sahibi | API key ile dış erişim |
| Kullanım takibi | Yok | Token/istek bazlı metering |
| Rate limit | Yok | Plan bazlı throttling |
| Faturalandırma | Yok | Kullanım bazlı billing |
| Model yönetimi | Manuel | UI'dan model CRUD |
| Multi-model | Ayrı ayrı kurulum | Tek gateway, çoklu model |

---

## 2. Mimari Genel Bakış

```
                     ┌─────────────────────────────────┐
                     │      EmareCloud AI Gateway     │
                     │    (Reverse Proxy + Auth + Rate) │
                     └────────────┬────────────────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              │                   │                   │
         ┌────▼────┐        ┌────▼────┐        ┌────▼────┐
         │ Ollama  │        │ Whisper │        │ TGW UI  │
         │ Server  │        │ Server  │        │ Server  │
         │ :11434  │        │ :9000   │        │ :7860   │
         └─────────┘        └─────────┘        └─────────┘
         Sunucu A            Sunucu B           Sunucu C

Dış Kullanıcı Akışı:
────────────────────
API Request → Gateway Auth → Rate Limit → Model Router → Backend → Response
     │              │             │              │
     ▼              ▼             ▼              ▼
  API Key       Token check   Quota check    Load balance
  Header        + org scope   + throttle     + failover
```

---

## 3. Bileşenler

### 3.1 AI Gateway (Yeni Modül)

```python
# ai_platform/gateway.py

"""
AI Gateway — Tüm AI model isteklerini karşılayan reverse proxy.
OpenAI-uyumlu API formatı kullanır.
"""

from flask import Blueprint, request, jsonify, g
from .auth import validate_api_key, check_rate_limit
from .router import route_to_model
from .metering import record_usage

ai_gateway = Blueprint('ai_gateway', __name__, url_prefix='/api/v1/ai')

@ai_gateway.before_request
def authenticate():
    """API key doğrulama ve rate limit kontrolü."""
    api_key = request.headers.get('Authorization', '').replace('Bearer ', '')
    
    if not api_key:
        return jsonify({'error': 'API key gerekli'}), 401
    
    key_info = validate_api_key(api_key)
    if not key_info:
        return jsonify({'error': 'Geçersiz API key'}), 401
    
    # Rate limit kontrolü
    allowed, remaining, reset = check_rate_limit(key_info)
    if not allowed:
        return jsonify({
            'error': 'Rate limit aşıldı',
            'retry_after': reset
        }), 429
    
    g.api_key = key_info
    g.org_id = key_info['org_id']


@ai_gateway.route('/chat/completions', methods=['POST'])
def chat_completions():
    """OpenAI-uyumlu chat completion endpoint."""
    data = request.json
    model_name = data.get('model', 'default')
    
    # Model'i bul ve yönlendir
    model = get_model_config(g.org_id, model_name)
    if not model:
        return jsonify({'error': f'Model bulunamadı: {model_name}'}), 404
    
    # Backend'e isteği yönlendir
    response = route_to_model(model, data)
    
    # Kullanım kaydet
    usage = response.get('usage', {})
    record_usage(
        org_id=g.org_id,
        api_key_id=g.api_key['id'],
        model=model_name,
        prompt_tokens=usage.get('prompt_tokens', 0),
        completion_tokens=usage.get('completion_tokens', 0),
        request_type='chat'
    )
    
    return jsonify(response)


@ai_gateway.route('/models', methods=['GET'])
def list_models():
    """Kullanılabilir modelleri listele."""
    models = get_org_models(g.org_id)
    return jsonify({
        'object': 'list',
        'data': [
            {
                'id': m['name'],
                'object': 'model',
                'owned_by': g.api_key['org_slug'],
                'ready': m['status'] == 'running'
            }
            for m in models
        ]
    })


@ai_gateway.route('/embeddings', methods=['POST'])
def embeddings():
    """Embedding endpoint."""
    data = request.json
    model_name = data.get('model', 'default-embedding')
    
    model = get_model_config(g.org_id, model_name)
    response = route_to_model(model, data, endpoint='embeddings')
    
    record_usage(
        org_id=g.org_id,
        api_key_id=g.api_key['id'],
        model=model_name,
        prompt_tokens=response.get('usage', {}).get('total_tokens', 0),
        request_type='embedding'
    )
    
    return jsonify(response)


@ai_gateway.route('/audio/transcriptions', methods=['POST'])
def transcriptions():
    """Whisper ses→metin endpoint."""
    audio_file = request.files.get('file')
    model_name = request.form.get('model', 'whisper-1')
    
    model = get_model_config(g.org_id, model_name)
    response = route_to_model(model, audio_file, endpoint='transcribe')
    
    # Ses süresi bazlı kullanım
    duration_seconds = response.get('duration', 0)
    record_usage(
        org_id=g.org_id,
        api_key_id=g.api_key['id'],
        model=model_name,
        audio_seconds=duration_seconds,
        request_type='transcription'
    )
    
    return jsonify(response)
```

### 3.2 Model Router

```python
# ai_platform/router.py

"""
Model Router — İsteği doğru backend sunucusuna yönlendirir.
"""

import requests
from dataclasses import dataclass

@dataclass
class ModelEndpoint:
    host: str           # Sunucu IP
    port: int           # Model portu
    path: str           # API path
    protocol: str       # http | https
    type: str           # ollama | openai | whisper | tgw
    ssh_tunnel: bool    # SSH tüneli gerekli mi?

MODEL_TYPE_CONFIGS = {
    'ollama': {
        'chat_path': '/api/chat',
        'generate_path': '/api/generate',
        'embeddings_path': '/api/embeddings',
        'models_path': '/api/tags',
    },
    'openai_compatible': {
        'chat_path': '/v1/chat/completions',
        'embeddings_path': '/v1/embeddings',
    },
    'whisper': {
        'transcribe_path': '/asr',
    }
}

def route_to_model(model_config: dict, data: dict, endpoint: str = 'chat') -> dict:
    """İsteği model backend'ine yönlendir."""
    
    ep = ModelEndpoint(**model_config['endpoint'])
    type_config = MODEL_TYPE_CONFIGS[ep.type]
    
    # SSH tüneli gerekiyorsa
    if ep.ssh_tunnel:
        ensure_ssh_tunnel(ep.host, ep.port)
    
    # URL oluştur
    path_key = f'{endpoint}_path'
    path = type_config.get(path_key, type_config.get('chat_path'))
    url = f"{ep.protocol}://{ep.host}:{ep.port}{path}"
    
    # İsteği yönlendir
    response = requests.post(
        url,
        json=data,
        timeout=120,
        headers={'Content-Type': 'application/json'}
    )
    
    return response.json()
```

### 3.3 API Key Yönetimi

```python
# ai_platform/auth.py

"""
API Key authentication ve rate limiting.
"""

import hashlib
import secrets
import time
from collections import defaultdict

# In-memory rate limit counter (production'da Redis kullanılır)
_rate_counters = defaultdict(lambda: {'count': 0, 'window_start': 0})

def generate_api_key(org_id: str, name: str, permissions: list = None) -> dict:
    """Yeni API key oluştur."""
    raw_key = f"emh_{'live' if not DEBUG else 'test'}_{secrets.token_hex(24)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:16]
    
    key_record = {
        'id': generate_uuid(),
        'org_id': org_id,
        'name': name,
        'key_hash': key_hash,
        'key_prefix': key_prefix,
        'permissions': permissions or ['ai:read', 'ai:write'],
        'rate_limit': 1000,  # requests/hour (plan'a göre değişir)
        'created_at': datetime.utcnow().isoformat()
    }
    
    db.create_api_key(key_record)
    
    # Raw key sadece bu sefer gösterilir
    return {
        'key': raw_key,
        'prefix': key_prefix,
        'name': name,
        'id': key_record['id']
    }


def validate_api_key(raw_key: str) -> dict:
    """API key doğrula."""
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_record = db.get_api_key_by_hash(key_hash)
    
    if not key_record:
        return None
    
    if key_record.get('expires_at') and key_record['expires_at'] < datetime.utcnow():
        return None
    
    # Son kullanım zamanını güncelle
    db.update_api_key_last_used(key_record['id'])
    
    return key_record


def check_rate_limit(key_info: dict) -> tuple:
    """Rate limit kontrol. Returns (allowed, remaining, reset_time)."""
    key_id = key_info['id']
    limit = key_info.get('rate_limit', 1000)
    window = 3600  # 1 saat
    
    now = time.time()
    counter = _rate_counters[key_id]
    
    # Pencere sıfırla
    if now - counter['window_start'] > window:
        counter['count'] = 0
        counter['window_start'] = now
    
    counter['count'] += 1
    remaining = max(0, limit - counter['count'])
    reset = int(counter['window_start'] + window)
    
    return (counter['count'] <= limit, remaining, reset)
```

---

## 4. Veritabanı Şeması

### 4.1 ai_models (Model kayıtları)

```sql
CREATE TABLE ai_models (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    server_id       TEXT NOT NULL,           -- Modelin çalıştığı sunucu
    
    name            TEXT NOT NULL,           -- "llama3.2" (API'de kullanılacak isim)
    display_name    TEXT,                    -- "Llama 3.2 70B"
    type            TEXT NOT NULL,           -- "ollama" | "openai_compatible" | "whisper" | "tgw"
    
    -- Endpoint bilgileri
    host            TEXT NOT NULL,
    port            INTEGER NOT NULL,
    path            TEXT DEFAULT '/',
    protocol        TEXT DEFAULT 'http',
    ssh_tunnel      BOOLEAN DEFAULT TRUE,
    
    -- Model meta
    context_length  INTEGER DEFAULT 4096,
    supports_streaming BOOLEAN DEFAULT TRUE,
    supports_vision BOOLEAN DEFAULT FALSE,
    
    -- Durum
    status          TEXT DEFAULT 'stopped',  -- stopped | starting | running | error
    last_health_check DATETIME,
    
    -- Fiyatlandırma
    price_per_1k_input  INTEGER DEFAULT 0,   -- cent / 1K input token
    price_per_1k_output INTEGER DEFAULT 0,   -- cent / 1K output token
    price_per_minute_audio INTEGER DEFAULT 0, -- cent / dakika (whisper)
    
    -- Erişim
    is_public       BOOLEAN DEFAULT FALSE,   -- Tüm org kullanıcıları erişebilir mi?
    allowed_keys    TEXT DEFAULT '[]',       -- JSON: belirli API key ID'leri
    
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(org_id, name),
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);
```

### 4.2 ai_usage_logs (Kullanım kayıtları)

```sql
CREATE TABLE ai_usage_logs (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    api_key_id      TEXT NOT NULL,
    model_name      TEXT NOT NULL,
    
    -- İstek detayları
    request_type    TEXT NOT NULL,           -- "chat" | "completion" | "embedding" | "transcription"
    prompt_tokens   INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens    INTEGER DEFAULT 0,
    audio_seconds   REAL DEFAULT 0,
    
    -- Performans
    latency_ms      INTEGER,
    status_code     INTEGER DEFAULT 200,
    
    -- Fiyatlandırma (anlık hesaplama)
    cost_cents      INTEGER DEFAULT 0,
    
    -- IP ve user agent (güvenlik)
    client_ip       TEXT,
    user_agent      TEXT,
    
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (org_id) REFERENCES organizations(id),
    FOREIGN KEY (api_key_id) REFERENCES org_api_keys(id)
);

-- Hızlı sorgular için index
CREATE INDEX idx_ai_usage_org_date ON ai_usage_logs(org_id, created_at);
CREATE INDEX idx_ai_usage_key ON ai_usage_logs(api_key_id, created_at);
CREATE INDEX idx_ai_usage_model ON ai_usage_logs(model_name, created_at);
```

### 4.3 ai_usage_daily (Günlük özet)

```sql
CREATE TABLE ai_usage_daily (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL,
    date            DATE NOT NULL,
    model_name      TEXT NOT NULL,
    
    total_requests  INTEGER DEFAULT 0,
    total_tokens    INTEGER DEFAULT 0,
    total_audio_sec REAL DEFAULT 0,
    total_cost      INTEGER DEFAULT 0,       -- cent
    avg_latency_ms  INTEGER DEFAULT 0,
    error_count     INTEGER DEFAULT 0,
    
    UNIQUE(org_id, date, model_name)
);
```

---

## 5. API Key Yönetimi UI

### API Key Oluşturma

```
┌─────────────────────────────────────────────┐
│ 🔑 Yeni API Key Oluştur                    │
├─────────────────────────────────────────────┤
│ Ad:        [Production AI Key          ]    │
│                                             │
│ İzinler:                                    │
│ ☑ Chat Completions                          │
│ ☑ Embeddings                                │
│ ☐ Audio Transcriptions                      │
│ ☑ Model Listesi                             │
│                                             │
│ Rate Limit: [1000] istek/saat               │
│                                             │
│ Son kullanma: [Süresiz ▼]                   │
│                                             │
│ Modeller:                                   │
│ ☑ Tümü                                      │
│ ☐ Seçili: [llama3.2] [whisper-1]           │
│                                             │
│         [İptal]  [✅ Oluştur]               │
└─────────────────────────────────────────────┘
```

### API Key Listesi

```
┌──────────────────────────────────────────────────────────────────┐
│ 🔑 API Keys                                   [+ Yeni Key]     │
├──────────┬─────────────────┬───────────┬────────────┬───────────┤
│ Ad       │ Key             │ İstekler  │ Son Kullanım│          │
├──────────┼─────────────────┼───────────┼────────────┼───────────┤
│ Prod     │ emh_live_abc... │ 12,847    │ 2 dk önce  │ 🗑️ Sil   │
│ Test     │ emh_test_xyz... │ 342       │ 3 gün önce │ 🗑️ Sil   │
│ Mobile   │ emh_live_def... │ 5,621     │ 1 saat önce│ 🗑️ Sil   │
└──────────┴─────────────────┴───────────┴────────────┴───────────┘
```

---

## 6. Kullanım Dashboard'u

```
┌─────────────────────────────────────────────────────────┐
│ 🤖 AI Platform — Kullanım Özeti              Mart 2026 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  📊 Bu Ay                                               │
│  ┌──────────┬──────────┬──────────┬──────────┐          │
│  │ İstekler │ Tokenler │ Maliyet  │ Modeller │          │
│  │  45,231  │  2.1M    │  $42.50  │   3      │          │
│  └──────────┴──────────┴──────────┴──────────┘          │
│                                                         │
│  📈 Günlük İstek Grafiği                                │
│  ┌─────────────────────────────────────────┐            │
│  │    ╭──╮                                 │            │
│  │ ╭──╯  ╰─╮     ╭──╮                     │            │
│  │─╯       ╰─╮╭──╯  ╰──╮  ╭──╮           │            │
│  │           ╰╯         ╰──╯  ╰──         │            │
│  └─────────────────────────────────────────┘            │
│  1 Mar                              28 Mar              │
│                                                         │
│  🏆 En Çok Kullanılan Modeller                          │
│  1. llama3.2         32,100 istek   $28.40              │
│  2. whisper-1         8,540 istek    $9.80              │
│  3. nomic-embed       4,591 istek    $4.30              │
│                                                         │
│  🔑 En Aktif API Key'ler                                │
│  1. Production       38,200 istek   emh_live_abc...     │
│  2. Mobile App        5,621 istek   emh_live_def...     │
│  3. Test              1,410 istek   emh_test_xyz...     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 7. OpenAI SDK Uyumluluğu

Kullanıcılar mevcut OpenAI SDK'larını EmareCloud AI Gateway ile kullanabilir:

### Python

```python
from openai import OpenAI

client = OpenAI(
    api_key="emh_live_abc123...",
    base_url="https://ai.emarecloud.com/api/v1/ai"
)

response = client.chat.completions.create(
    model="llama3.2",
    messages=[
        {"role": "user", "content": "Merhaba!"}
    ]
)
print(response.choices[0].message.content)
```

### JavaScript

```javascript
import OpenAI from 'openai';

const client = new OpenAI({
    apiKey: 'emh_live_abc123...',
    baseURL: 'https://ai.emarecloud.com/api/v1/ai'
});

const response = await client.chat.completions.create({
    model: 'llama3.2',
    messages: [{ role: 'user', content: 'Merhaba!' }]
});
```

### cURL

```bash
curl https://ai.emarecloud.com/api/v1/ai/chat/completions \
  -H "Authorization: Bearer emh_live_abc123..." \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.2",
    "messages": [{"role": "user", "content": "Merhaba!"}]
  }'
```

---

## 8. Model Yaşam Döngüsü

```
Market'ten Kur → Model Kaydet → Sağlık Kontrolü → API Expose → İzleme
      │               │               │                │           │
      ▼               ▼               ▼                ▼           ▼
  SSH ile         ai_models       30 sn'de bir     Gateway'e     Usage
  sunucuya        tablosuna       /health ping     route ekle    metering
  kurulum         kayıt                             
```

### Model Health Check

```python
# ai_platform/health.py

import requests
from apscheduler.schedulers.background import BackgroundScheduler

def check_model_health():
    """Tüm aktif modellerin sağlık durumunu kontrol et."""
    models = db.get_active_models()
    
    for model in models:
        try:
            url = f"{model['protocol']}://{model['host']}:{model['port']}/health"
            resp = requests.get(url, timeout=5)
            
            if resp.status_code == 200:
                db.update_model_status(model['id'], 'running')
            else:
                db.update_model_status(model['id'], 'error')
        except Exception:
            db.update_model_status(model['id'], 'error')
            notify_org_admin(model['org_id'], f"Model {model['name']} yanıt vermiyor")

# Her 30 saniyede kontrol
scheduler = BackgroundScheduler()
scheduler.add_job(check_model_health, 'interval', seconds=30)
```

---

## 9. Güvenlik

| Katman | Uygulama |
|--------|----------|
| Authentication | API key (Bearer token) — SHA-256 hash ile saklanır |
| Authorization | Key bazlı izinler (model erişimi, istek tipi) |
| Rate Limiting | Key bazlı + Org bazlı çift katmanlı |
| Data Isolation | Org-scoped model ve kullanım verileri |
| Transport | TLS zorunlu (API Gateway) |
| SSH Tunnel | Model backend'lere güvenli erişim |
| Input Validation | Prompt injection koruması (isteğe bağlı) |
| Audit | Tüm API istekleri loglanır |

---

## 10. Uygulama Öncelik Sırası

| Sıra | Modül | Karmaşıklık | Süre | Bağımlılık |
|------|-------|-------------|------|------------|
| 1 | ai_models tablosu + CRUD | Düşük | 3 gün | — |
| 2 | API key oluşturma/doğrulama | Orta | 1 hafta | Multi-tenant |
| 3 | AI Gateway (chat endpoint) | Yüksek | 2 hafta | #1, #2 |
| 4 | Rate limiting | Orta | 3 gün | #2 |
| 5 | Usage metering + logging | Orta | 1 hafta | #3 |
| 6 | Model health check | Düşük | 3 gün | #1 |
| 7 | Kullanım dashboard UI | Orta | 1 hafta | #5 |
| 8 | Embeddings + Whisper endpoint | Orta | 1 hafta | #3 |
| 9 | Streaming response desteği | Yüksek | 1 hafta | #3 |
| 10 | Billing hook entegrasyonu | Orta | 3 gün | Billing sistemi |

**Toplam tahmini süre: 8-10 hafta**

---

## 11. Rekabet Avantajı

| Rakip | Ne Sunuyor | EmareCloud Farkı |
|-------|-----------|-------------------|
| OpenAI | Cloud API | **Self-hosted**, veri kontrolü |
| Replicate | Cloud GPU | **Kendi sunucunuzda**, maliyet kontrolü |
| Ollama | CLI araç | **Web UI + API Gateway + billing** |
| LocalAI | OpenAI drop-in | **Multi-tenant + kullanım takibi** |

> EmareCloud AI Platform: "Kendi AI API servisini, kendi sunucunda, kendi markanda sun."

---

*Doküman: EmareCloud OS — AI Platform Extension Tasarımı v1.0*
*Tarih: Mart 2026*
