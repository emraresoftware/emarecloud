# Kurulum ve Hızlı Başlangıç

Bu doküman, EmareCloud panelinin sıfırdan ayağa kaldırılması için gerekli adımları içerir.

## Gereksinimler

- Python 3.10+
- SSH ile erişilebilir Linux sunucular
- İnternet erişimi (bağımlılık kurulumu için)

## Kurulum

### Otomatik Kurulum (Önerilen)

```bash
chmod +x setup.sh
./setup.sh
```

`setup.sh` interaktif wizard 7 adımda kurulumu tamamlar:

1. **Sistem kontrolü:** Python 3.10+ ve pip doğrulama
2. **Bağımlılıklar:** `requirements.txt` paketleri otomatik kurulum
3. **Master key:** AES-256-GCM şifreleme için `MASTER_KEY` oluşturma
4. **Admin kullanıcı:** İlk admin hesabı (kullanıcı adı + şifre) belirleme
5. **Port ayarı:** Panel portu (varsayılan 5555)
6. **Veritabanı:** SQLite auth veritabanı başlatma
7. **`.env` dosyası:** Tüm ayarları `.env` dosyasına yazma

### Manuel Kurulum

Proje klasöründe:

- `python3 -m venv venv`
- `source venv/bin/activate` (Windows: `venv\Scripts\activate`)
- `pip install -r requirements.txt`
- `.env` dosyası oluşturun (MASTER_KEY, SECRET_KEY, PORT)
- `python app.py`

Panel varsayılan olarak:

- `http://localhost:5555`

adresinde çalışır.

### Üretim Ortamı

```bash
gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
  -w 1 -b 0.0.0.0:5555 "app:create_app()"
```

TLS/SSL için: [TLS_REVERSE_PROXY.md](TLS_REVERSE_PROXY.md)

## Sağlık Kontrolü

- `GET /health`
- Başarılı yanıt: `{"ok": true, "message": "Panel çalışıyor"}`

## İlk Kullanım

1. Giriş ekranında admin kullanıcı ile oturum açın.
2. Dashboard açılır.
3. Sol alttan **Sunucu Ekle** ile ilk sunucuyu tanımlayın (isteğe bağlı: rol, lokasyon, kurulum tarihi, sorumlu).
4. Sunucu kartından **Bağlan** ile SSH bağlantısı kurun.
5. Sunucu detay, terminal, Uygulama Pazarı, Sanallaştırma, Depolama modüllerini kullanın.

**Not:** Community lisansı ile 3 sunucuya kadar ücretsiz kullanılabilir. Daha fazlası için Professional veya Enterprise lisansı gerekir.

## Bağımlılıklar

`requirements.txt` içinde öne çıkanlar:

- `flask` — Web framework (factory pattern)
- `flask-socketio` — WebSocket desteği (terminal)
- `paramiko` — SSH bağlantıları
- `gevent` — Async worker
- `cryptography` — AES-256-GCM şifreleme

## Ortam Değişkenleri (`.env`)

| Değişken | Açıklama | Varsayılan |
|----------|----------|------------|
| `MASTER_KEY` | AES-256-GCM şifreleme anahtarı (zorunlu) | — |
| `SECRET_KEY` | Flask session secret | Otomatik |
| `PORT` | Panel portu | 5555 |
| `CORS_ALLOWED_ORIGINS` | İzin verilen CORS origin'leri | `*` (geliştirme) |

## Sık Karşılaşılan Sorunlar

### 1) Panel açılmıyor

- Sanal ortam aktif mi?
- Paketler kurulu mu?
- Port 5555 kullanımda mı?
- `.env` dosyası var mı?

### 2) Giriş yapılamıyor

- Admin kullanıcı oluşturulmuş mu? (`setup.sh` veya `/register`)
- Şifre karmaşıklık kurallarına uyuyor mu? (min 8 kar., büyük/küçük harf, rakam, özel karakter)
- Hesap kilitlenmiş olabilir (5 başarısız deneme)

### 3) Sunucuya bağlanamıyor

- IP/hostname doğru mu?
- Port (22 vb.) doğru mu?
- Kullanıcı adı/şifre doğru mu?
- Sunucuda SSH servisi açık mı?

### 4) Komutlarda yetki hatası

- Gerekli işlemler için `sudo` yetkisi gerekir.
- RBAC rolünüz yeterli mi? (operator ve read_only kullanıcılar kısıtlıdır)

## Üretim Ortamı İçin Kontrol Listesi

- ✅ `debug=False`
- ✅ CORS kısıtlı origin (`CORS_ALLOWED_ORIGINS`)
- ✅ Reverse proxy (Nginx) — [rehber](TLS_REVERSE_PROXY.md)
- ✅ TLS/HTTPS
- ✅ Yapılandırılmış loglama (JSON formatı, log rotasyonu)
- ✅ `.env` ve `config.json` dosyaları `.gitignore`'da
- ✅ Güçlü `MASTER_KEY` ve `SECRET_KEY`
- ⬜ Düzenli yedekleme
