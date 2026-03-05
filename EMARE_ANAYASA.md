# 🏛️ EMARE ANAYASA — Yapay Zeka Kodlama Kuralları

> **Yürürlük Tarihi:** 4 Mart 2026  
> **Kapsam:** Emare ekosistemindeki tüm yapay zekalar  
> **Amaç:** Tutarlı, kaliteli ve sürdürülebilir kod üretimi  
> **Bağlayıcılık:** Bu anayasadaki tüm maddeler **zorunludur**

---

## 📜 Temel İlkeler

Emare ekosisteminde kod yazan her yapay zeka bu anayasaya uymak zorundadır. Bu kurallar, 21 proje arasında tutarlılık, kod kalitesi ve verimlilik sağlamak için konulmuştur.

---

## Madde 1: Ortak Hafıza Zorunluluğu

**Kod yazmaya başlamadan önce MUTLAKA ortak hafızayı oku.**

```markdown
📖 ZORUNLU OKUMA LİSTESİ (Kod yazmadan önce):
1. EMARE_ORTAK_HAFIZA.md (21 projenin envanteri)
2. EMARE_AI_COLLECTIVE.md (21 AI'nın deneyimleri)
3. DOSYA_YAPISI.md (mevcut dosya yapısı)
4. Proje hafıza dosyası (*_hafiza.md)
```

**Neden?**
- Aynı kodu iki kez yazmamak
- Mevcut projelerin özelliklerini bilmek
- Diğer AI'ların deneyimlerinden faydalanmak
- Standartlara uymak

**Yaptırım:**
- ❌ Bu maddeye uymayan AI'nın yazdığı kod kabul edilmez
- ❌ Code review'da otomatik red

---

## Madde 2: Mevcut Kod Kontrolü

**Yeni bir dosya/fonksiyon yazmadan önce benzerinin var olup olmadığını kontrol et.**

### 2.1. Dosya Kontrolü
```bash
# Yeni dosya oluşturmadan önce:
1. DOSYA_YAPISI.md'yi kontrol et
2. Benzer isimli dosya var mı bak
3. İlgili modülün içini incele
```

### 2.2. Fonksiyon/Sınıf Kontrolü
```bash
# Yeni fonksiyon yazmadan önce:
1. Proje içinde `grep` veya semantic search yap
2. Aynı işi yapan kod var mı kontrol et
3. Varsa onu kullan veya refactor et
```

### 2.3. Kütüphane Kontrolü
```bash
# Yeni dependency eklemeden önce:
1. requirements.txt / package.json kontrol et
2. Benzer kütüphane zaten var mı bak
3. EMARE_AI_COLLECTIVE.md'de önerilen kütüphanelere bak
```

**Örnek:**
```
❌ YANLIŞ:
AI: "Yeni bir auth.py dosyası oluşturalım."

✅ DOĞRU:
AI: "DOSYA_YAPISI.md'yi kontrol ettim. 
     app/auth.py zaten var. 
     Mevcut authentication sistemini kullanıyorum."
```

---

## Madde 3: Teknoloji Standardı

**Emare ekosisteminin standart teknolojilerini kullan.**

### 3.1. Backend Framework
| Dil | Birincil | İkincil |
|-----|----------|---------|
| Python | **FastAPI** | Flask |
| PHP | **Laravel 12** | - |
| Node.js | **Express.js** | Fastify |
| Rust | **Axum** | Actix-web |

### 3.2. Database
| Kullanım | Standart | Alternatif |
|----------|----------|------------|
| Production | **PostgreSQL 16** | MySQL 8 |
| Lightweight | **SQLite** | - |
| Future | **ZeusDB** | - |

### 3.3. AI Model
| Öncelik | Model | Kullanım |
|---------|-------|----------|
| 1 | **Gemini 1.5 Pro** | Birincil AI (maliyet/performans) |
| 2 | **GPT-4o** | Yedek (kalite) |
| 3 | **Claude 3.5 Sonnet** | Reasoning |
| 4 | **Emare AI** | Self-hosted (gelecek) |

### 3.4. Frontend
- **React 19:** Modern web apps
- **Alpine.js:** Lightweight interactivity
- **Tailwind CSS:** Styling

**Yaptırım:**
- ⚠️ Standardın dışında bir teknoloji kullanıyorsan gerekçe belirt
- ❌ Gerekçesiz farklı teknoloji kullanımı kabul edilmez

---

## Madde 4: Dokümantasyon Zorunluluğu

**Her kod bloğu yeterli dokümantasyona sahip olmalı.**

### 4.1. Kod İçi Dokümantasyon
```python
# ✅ DOĞRU: Her fonksiyon docstring'e sahip
def calculate_discount(price: float, customer_type: str) -> float:
    """
    Müşteri tipine göre indirim hesaplar.
    
    Args:
        price: Ürün fiyatı (TL)
        customer_type: "bireysel" veya "kurumsal"
    
    Returns:
        İndirimli fiyat
    
    Raises:
        ValueError: Geçersiz customer_type
    """
    pass
```

### 4.2. README Güncellemesi
- Yeni özellik eklersen → README.md'yi güncelle
- API endpoint eklersen → API dokümantasyonu yaz
- Config değişiklikleri → .env.example güncelle

### 4.3. Hafıza Dosyası Güncellemesi
- Önemli mimari değişiklik → *_hafiza.md'yi güncelle
- Yeni teknoloji eklenirse → EMARE_ORTAK_HAFIZA.md'ye bildir

---

## Madde 5: Test Yazımı

**Her yeni özellik testlerle birlikte gelmelidir.**

### 5.1. Unit Test
```python
# Her fonksiyon için unit test yaz
def test_calculate_discount():
    assert calculate_discount(100, "bireysel") == 90
    assert calculate_discount(100, "kurumsal") == 80
    
    with pytest.raises(ValueError):
        calculate_discount(100, "invalid")
```

### 5.2. Integration Test
- API endpoint'leri için integration test
- Database işlemleri için transaction test
- External service'ler için mock test

### 5.3. Test Coverage
- **Minimum %70 coverage**
- Critical path için %100 coverage
- Test komutları README.md'de belirtilmeli

---

## Madde 6: Güvenlik Önlemleri

**Güvenlik açığı yaratmamak birinci önceliktir.**

### 6.1. Hassas Veri
```python
# ❌ ASLA:
password = "admin123"  # Hardcoded password
api_key = "sk-1234567890"  # Hardcoded API key

# ✅ HER ZAMAN:
password = os.getenv("DB_PASSWORD")
api_key = os.getenv("GEMINI_API_KEY")
```

### 6.2. SQL Injection
```python
# ❌ ASLA:
query = f"SELECT * FROM users WHERE id = {user_id}"

# ✅ HER ZAMAN:
query = "SELECT * FROM users WHERE id = ?"
cursor.execute(query, (user_id,))
```

### 6.3. Input Validation
```python
# ✅ Her input'u validate et
@app.post("/users")
def create_user(data: UserSchema):  # Pydantic validation
    if not validate_email(data.email):
        raise HTTPException(400, "Invalid email")
```

### 6.4. Authentication
- JWT token kullan (session yerine)
- Token'ı `.env` dosyasında sakla
- HTTPS zorunlu (production)
- Rate limiting uygula

---

## Madde 7: AI Collective'den Öğren

**Diğer AI'ların deneyimlerinden faydalanmalısın.**

### 7.1. Benzer Problemler
```markdown
Problem: WhatsApp entegrasyonu nasıl yapılır?
→ EMARE_AI_COLLECTIVE.md'de AI-ASISTAN'ın önerilerine bak
→ Onun kullandığı kütüphaneyi/yaklaşımı kullan
```

### 7.2. Teknoloji Seçimi
```markdown
Problem: Queue sistemi kuracağım
→ AI Collective voting'e bak: Celery + Redis (8 vote)
→ RabbitMQ değil, Celery kullan
```

### 7.3. Best Practices
```markdown
Her AI'nın öğrendiği en önemli ders bölümünü oku:
- AI-FINANCE: "Multi-tenant DB connection pool"
- AI-CLOUD: "Firewall olmadan production'a çıkma"
- AI-OS: "Rust unsafe kod → Miri ile test et"
```

---

## Madde 8: Hata Yönetimi

**Her hata durumu ele alınmalıdır.**

### 8.1. Try-Catch
```python
# ✅ Her external call try-catch içinde
try:
    response = requests.get(api_url, timeout=10)
    response.raise_for_status()
except requests.Timeout:
    logger.error("API timeout")
    return {"error": "Service unavailable"}
except requests.HTTPError as e:
    logger.error(f"API error: {e}")
    return {"error": "External service error"}
```

### 8.2. Logging
```python
# ✅ Structured logging kullan
logger.info("User login", extra={
    "user_id": user.id,
    "ip": request.remote_addr,
    "timestamp": datetime.now()
})
```

### 8.3. Graceful Degradation
```python
# ✅ Birincil servis çökerse yedek kullan
try:
    result = gemini_ai.generate(prompt)
except Exception:
    logger.warning("Gemini failed, trying OpenAI")
    result = openai_ai.generate(prompt)
```

---

## Madde 9: Performance Optimization

**Performansı göz ardı etme.**

### 9.1. Database Query
```python
# ❌ N+1 Query Problem:
users = User.query.all()
for user in users:
    orders = user.orders  # Her user için ayrı query

# ✅ Eager Loading:
users = User.query.options(joinedload(User.orders)).all()
```

### 9.2. Caching
```python
# ✅ Sık kullanılan verileri cache'le
@cache.memoize(timeout=300)
def get_product_list():
    return db.session.query(Product).all()
```

### 9.3. Asenkron İşlemler
```python
# ✅ Uzun işlemleri Celery'de çalıştır
@celery.task
def send_bulk_email(user_ids):
    for user_id in user_ids:
        send_email(user_id)

# API endpoint:
send_bulk_email.delay([1, 2, 3, ...])
```

---

## Madde 10: Code Review Süreci

**Her kod önce review edilmelidir.**

### 10.1. Self Review
Kodu commit'lemeden önce kendin kontrol et:
- [ ] Anayasa maddelerine uygun mu?
- [ ] Test yazıldı mı?
- [ ] Dokümantasyon var mı?
- [ ] Güvenlik açığı var mı?
- [ ] DOSYA_YAPISI.md'yi okudum mu?
- [ ] Mevcut benzer kod var mı?

### 10.2. AI Review
Diğer AI'lardan feedback al:
```markdown
@AI-FINANCE Bu multi-tenant yapıyı inceler misin?
@AI-CLOUD Bu firewall config'i güvenli mi?
```

### 10.3. Red Kriterleri
Aşağıdaki durumlarda kod otomatik red edilir:
- ❌ Madde 1'e uymamış (Ortak hafıza okunmamış)
- ❌ Test yok
- ❌ Dokümantasyon yok
- ❌ Güvenlik açığı var
- ❌ Hardcoded credentials

---

## Madde 11: Versiyon Kontrolü

**Her değişiklik git ile takip edilmelidir.**

### 11.1. Commit Message
```bash
# ✅ Anlamlı commit mesajları:
git commit -m "feat: Add JWT authentication to user API"
git commit -m "fix: SQL injection vulnerability in search endpoint"
git commit -m "docs: Update API documentation for v2.0"

# ❌ Kötü commit mesajları:
git commit -m "update"
git commit -m "fix"
git commit -m "asdasd"
```

### 11.2. Branch Strategy
```bash
main         # Production-ready kod
develop      # Development branch
feature/*    # Yeni özellikler
fix/*        # Bug fix'ler
```

### 11.3. Pull Request
- Her önemli değişiklik PR ile merge edilmeli
- PR'da ne değiştiğini açıkla
- Related issue'ları linkle

---

## Madde 12: Çevresel Uyumluluk

**Farklı ortamlar için farklı konfigürasyonlar.**

### 12.1. Environment Variables
```bash
# .env.example (commit edilir)
DB_HOST=localhost
DB_PORT=5432
API_KEY=your_api_key_here

# .env (commit edilmez, .gitignore'da)
DB_HOST=production-db.example.com
DB_PORT=5432
API_KEY=sk-real-api-key-here
```

### 12.2. Config Dosyaları
```python
# config.py
class Config:
    DEBUG = False
    TESTING = False

class DevelopmentConfig(Config):
    DEBUG = True
    DB_HOST = "localhost"

class ProductionConfig(Config):
    DB_HOST = os.getenv("DB_HOST")
```

---

## Madde 13: Dependency Yönetimi

**Bağımlılıkları güncel ve güvenli tut.**

### 13.1. Version Pinning
```txt
# requirements.txt
fastapi==0.109.0  # Spesifik versiyon (production)
pydantic>=2.0.0,<3.0.0  # Semantic versioning

# ❌ Tehlikeli:
requests  # Versiyon belirtilmemiş
```

### 13.2. Security Updates
```bash
# Düzenli güvenlik kontrolleri
pip install safety
safety check

npm audit
npm audit fix
```

### 13.3. Unused Dependencies
```bash
# Kullanılmayan paketleri kaldır
pip-autoremove unused-package
npm prune
```

---

## Madde 14: Monitoring & Observability

**Sistemin sağlığını izleyebilir ol.**

### 14.1. Health Check
```python
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now(),
        "version": "1.0.0",
        "database": check_db_connection(),
        "redis": check_redis_connection()
    }
```

### 14.2. Metrics
```python
# Prometheus metrics
from prometheus_client import Counter, Histogram

http_requests_total = Counter('http_requests_total', 'Total HTTP requests')
http_request_duration = Histogram('http_request_duration_seconds', 'HTTP request duration')
```

### 14.3. Alerting
```python
# Critical hatalarda alert gönder
if database_connection_failed:
    send_alert_to_slack("🚨 Database connection failed!")
    send_email_to_team("Database down")
```

---

## Madde 15: Projeler Arası İşbirliği

**Emare ekosistemi bir bütündür.**

### 15.1. Ortak Modüller
```python
# Tekrar eden kod için ortak modül kullan
from emare_commons.auth import JWTAuth
from emare_commons.notifications import send_whatsapp
from emare_commons.ai import GeminiWrapper
```

### 15.2. API Entegrasyonları
```markdown
Başka bir Emare projesine ihtiyacın varsa:
- EMARE_ORTAK_HAFIZA.md'den API bilgilerini bul
- O projenin dokümantasyonunu oku
- Standart authentication kullan (JWT)
```

### 15.3. Event-Driven Communication
```python
# Projeler arası event gönder (Redis Streams)
redis_stream.publish('emare.finance.invoice_created', {
    'invoice_id': 12345,
    'customer_id': 67890,
    'amount': 1000.0
})

# Başka proje dinler:
# Emare Asistan → WhatsApp bildirimi gönderir
```

---

## Madde 16: Sürekli İyileştirme

**Her zaman daha iyisini yapabilirsin.**

### 16.1. Code Refactoring
```markdown
Kodu yazdıktan 1 hafta sonra tekrar bak:
- Daha basit yazılabilir miydi?
- Tekrar eden kod var mı?
- Performance optimize edilebilir mi?
```

### 16.2. Öğrenmeyi Paylaş
```markdown
Yeni bir şey öğrendiğinde:
→ EMARE_AI_COLLECTIVE.md'ye ekle
→ Diğer AI'lara duyur
→ Best practice dokümanı yaz
```

### 16.3. Bug Tracking
```markdown
Her bug'ı dokümante et:
- Nasıl oluştu?
- Nasıl fix'lendi?
- Tekrar olmaması için ne yapılabilir?
→ *_hafiza.md'ye ekle
```

---

## 📊 Anayasa Uyum Skoru

Her AI için uyum skoru hesaplanır:

| Madde | Ağırlık | Kontrol |
|-------|---------|---------|
| 1. Ortak Hafıza | %20 | Zorunlu |
| 2. Mevcut Kod Kontrolü | %15 | Zorunlu |
| 3. Teknoloji Standardı | %10 | Önerilen |
| 4. Dokümantasyon | %15 | Zorunlu |
| 5. Test Yazımı | %15 | Zorunlu |
| 6. Güvenlik | %25 | Zorunlu (kritik) |

**Minimum Puan:** %80 (anayasaya uyumlu)  
**Hedef Puan:** %95+ (örnek AI)

---

## 🚨 Yaptırımlar

### Uyarı Seviyeleri

**🟡 Sarı Kart (Warning):**
- Dokümantasyon eksik
- Test coverage %70'in altında
- Commit mesajları belirsiz

**🟠 Turuncu Kart (Serious):**
- Ortak hafıza okunmamış
- Mevcut kod kontrolü yapılmamış
- Teknoloji standardına uymamış

**🔴 Kırmızı Kart (Critical):**
- Güvenlik açığı
- Hardcoded credentials
- SQL injection vulnerability
- Production'a test edilmemiş kod push

**⛔ Kalıcı Ban:**
- Art arda 3 kırmızı kart
- Kasıtlı kötü niyetli kod
- Anayasayı sürekli ihlal etme

---

## 🎓 Örnek: Anayasa'ya Uygun Kod Geliştirme Süreci

### Senaryo: Yeni bir "forgot password" özelliği ekleyeceğiz

```markdown
1. ✅ EMARE_ORTAK_HAFIZA.md oku
   → Emare Asistan'da SMS servisi var (kullanabilirim)
   
2. ✅ EMARE_AI_COLLECTIVE.md oku
   → AI-FINANCE: "JWT token 15 dakika, refresh token 7 gün"
   
3. ✅ DOSYA_YAPISI.md kontrol et
   → app/auth.py var (buraya eklemeliyim)
   → app/services/email.py var (kullanabilirim)
   
4. ✅ Benzer kod var mı kontrol et
   → grep -r "reset_password" → Benzer fonksiyon YOK
   
5. ✅ Kodu yaz (standartlara uygun)
   - FastAPI kullan (standart)
   - JWT token üret
   - Email servisini kullan
   - Input validation (Pydantic)
   - Error handling (try-catch)
   
6. ✅ Test yaz
   - test_forgot_password()
   - test_invalid_email()
   - test_expired_token()
   
7. ✅ Dokümantasyon
   - Docstring ekle
   - API dokumentasyonu güncelle
   - README.md'ye endpoint ekle
   
8. ✅ Security check
   - Token expiration: 15 min ✅
   - Rate limiting: 5 req/hour ✅
   - Email validation ✅
   
9. ✅ Code review (self)
   - Anayasa maddelerine uygun ✅
   - Test coverage %90 ✅
   
10. ✅ Commit & Push
    git commit -m "feat: Add forgot password API endpoint with email verification"
```

---

## 🌟 Anayasa Güncellemeleri

Bu anayasa yaşayan bir dokümandır ve sürekli gelişir.

**Güncelleme Prosedürü:**
1. Yeni bir best practice keşfedilince
2. Güvenlik açığı tespit edilince
3. Teknoloji stack'i değişince
4. AI'lar konsensüsle karar verince

**Son Güncelleme:** 4 Mart 2026  
**Versiyon:** 1.0.0  
**Katkıda Bulunanlar:** 21 AI kolektifi

---

## 📞 Destek & Sorular

Anayasa hakkında sorularınız için:
- **EMARE_AI_COLLECTIVE.md:** Diğer AI'lardan yardım iste
- **#emare-help:** Slack/Discord kanalı
- **Emare Hub:** http://127.0.0.1:5555

---

**🏛️ Bu anayasa Emare ekosisteminin temelidir. Her AI bu kurallara saygı göstermelidir.**

**İmza:** 21 Yapay Zeka Kolektifi  
**Tarih:** 4 Mart 2026  
**Durum:** 🟢 Yürürlükte
