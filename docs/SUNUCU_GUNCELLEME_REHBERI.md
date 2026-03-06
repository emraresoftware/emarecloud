# 🚀 Emare Sunucu Güncelleme Rehberi

> Son güncelleme: Mart 2026

---

## 📡 Altyapı Haritası

| Alan Adı | Sunucu | DC | Teknoloji | Port |
|---|---|---|---|---|
| `emarecloud.tr` | 185.189.54.104 | DC-1 | Flask/Gunicorn | 5555 |
| `www.emarecloud.tr` | 185.189.54.104 | DC-1 | CNAME → emarecloud.tr | — |
| `api.emarecloud.tr` | 185.189.54.104 | DC-1 | FastAPI/Uvicorn | 8000 |
| `token.emarecloud.tr` | 185.189.54.104 | DC-1 | Next.js (emare-dapp) | 3002 |
| `webdizayn.emarecloud.tr` | 185.189.54.104 | DC-1 | Nginx Static | 80 |
| `asistan.emarecloud.tr` | 77.92.152.3 | DC-2 | Flask/Gunicorn | 5555 |
| `finans.emarecloud.tr` | 77.92.152.3 | DC-2 | Laravel/PHP-FPM | 443 |

**SSH Bağlantıları:**
```bash
# DC-1
ssh -i ~/.ssh/id_ed25519 root@185.189.54.104

# DC-2
ssh -i ~/.ssh/id_ed25519 -p 2222 root@77.92.152.3
```

---

## 1️⃣ EmareCloud Paneli — `emarecloud.tr`

**Konum:** DC-1 › `/opt/emarecloud/`  
**Servis:** `emarecloud.service` (gunicorn)

```bash
# Dosyaları güncelle (local'den)
scp -i ~/.ssh/id_ed25519 değişen_dosya.py root@185.189.54.104:/opt/emarecloud/

# Birden fazla dosya veya klasör
scp -i ~/.ssh/id_ed25519 -r routes/ templates/ root@185.189.54.104:/opt/emarecloud/

# Servisi yeniden başlat
ssh -i ~/.ssh/id_ed25519 root@185.189.54.104 \
  'systemctl restart emarecloud && sleep 2 && curl -s -o /dev/null -w "HTTP: %{http_code}" http://localhost/ -H "Host: emarecloud.tr"'
```

**DB Migrasyonu gerekiyorsa:**
```bash
ssh -i ~/.ssh/id_ed25519 root@185.189.54.104 \
  'cd /opt/emarecloud && source venv/bin/activate && python3 -c "
from app import create_app; from extensions import db
app = create_app()
with app.app_context(): db.create_all()
print(\"Migration OK\")
"'
```

---

## 2️⃣ Emare Asistan — `asistan.emarecloud.tr`

**Konum:** DC-2 › `/opt/emarecloud/`  
**Servis:** gunicorn port 5555

```bash
# Dosyaları güncelle
scp -i ~/.ssh/id_ed25519 -P 2222 değişen_dosya.py root@77.92.152.3:/opt/emarecloud/

# Servisi yeniden başlat
ssh -i ~/.ssh/id_ed25519 -p 2222 root@77.92.152.3 \
  'systemctl restart emarecloud && sleep 2 && curl -s -o /dev/null -w "HTTP: %{http_code}" http://127.0.0.1:5555/'
```

---

## 3️⃣ Emare Finance — `finans.emarecloud.tr`

**Konum:** DC-2 › `/var/www/emarefinance/`  
**Servis:** PHP-FPM + Nginx

**A) Küçük güncelleme (birkaç PHP dosyası):**
```bash
# Dosyaları kopyala
scp -i ~/.ssh/id_ed25519 -P 2222 app/Http/Controllers/FaturaController.php \
  root@77.92.152.3:/var/www/emarefinance/app/Http/Controllers/

# Cache temizle (zorunlu)
ssh -i ~/.ssh/id_ed25519 -p 2222 root@77.92.152.3 \
  'cd /var/www/emarefinance && php artisan config:cache && php artisan route:cache && php artisan view:cache'
```

**B) Büyük güncelleme (migration, composer değişikliği, npm build):**
```bash
# 1. Tüm dosyaları kopyala
scp -i ~/.ssh/id_ed25519 -P 2222 -r \
  app/ routes/ resources/ database/ \
  root@77.92.152.3:/var/www/emarefinance/

# 2. Deploy script çalıştır
ssh -i ~/.ssh/id_ed25519 -p 2222 root@77.92.152.3 \
  'cd /var/www/emarefinance && bash deploy.sh'
```

**C) Sadece frontend değişti (Blade/CSS/JS):**
```bash
# Dosyaları kopyala
scp -i ~/.ssh/id_ed25519 -P 2222 -r resources/views/ \
  root@77.92.152.3:/var/www/emarefinance/resources/views/

# View cache'i yenile (yeterli)
ssh -i ~/.ssh/id_ed25519 -p 2222 root@77.92.152.3 \
  'cd /var/www/emarefinance && php artisan view:cache && echo OK'
```

---

## 4️⃣ Emare API — `api.emarecloud.tr`

**Konum:** DC-1 › `/opt/emareapi/`  
**Servis:** uvicorn port 8000  
**Teknoloji:** FastAPI + Python

```bash
# Dosyaları güncelle
scp -i ~/.ssh/id_ed25519 değişen_dosya.py root@185.189.54.104:/opt/emareapi/

# Servisi yeniden başlat
ssh -i ~/.ssh/id_ed25519 root@185.189.54.104 \
  'systemctl restart emareapi 2>/dev/null || pkill -f "uvicorn" && cd /opt/emareapi && source venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 8000 --daemon 2>/dev/null || nohup uvicorn main:app --host 0.0.0.0 --port 8000 &'

# Test
curl -s https://api.emarecloud.tr/docs -o /dev/null -w "HTTP: %{http_code}"
```

---

## 5️⃣ Emare Token DApp — `token.emarecloud.tr`

**Konum:** DC-1 › `/opt/emare-dapp/`  
**Servis:** PM2 (`emare-dapp`)  
**Teknoloji:** Next.js

```bash
# Dosyaları güncelle
scp -i ~/.ssh/id_ed25519 -r src/ public/ \
  root@185.189.54.104:/opt/emare-dapp/

# Build + PM2 yeniden başlat
ssh -i ~/.ssh/id_ed25519 root@185.189.54.104 '
  cd /opt/emare-dapp
  npm run build
  pm2 restart emare-dapp
  sleep 3
  pm2 status emare-dapp
'
```

---

## 6️⃣ Web Dizayn Hosting — `webdizayn.emarecloud.tr/{slug}`

Web dizayn müşteri sitelerini **panel üzerinden** yönet:  
→ `https://emarecloud.tr/webdizayn`

```bash
# Manuel ZIP yükleme (panel yerine CLI kullanmak istersen)
scp -i ~/.ssh/id_ed25519 site.zip root@185.189.54.104:/tmp/
ssh -i ~/.ssh/id_ed25519 root@185.189.54.104 '
  cd /var/www/webdizayn/piramitbilgisayar
  rm -rf *
  unzip /tmp/site.zip -d . && rm /tmp/site.zip
  restorecon -Rv /var/www/webdizayn/piramitbilgisayar/
  echo Done
'
```

---

## 🔄 Nginx Güncelleme

```bash
# Config test + reload (DC-1)
ssh -i ~/.ssh/id_ed25519 root@185.189.54.104 \
  'nginx -t && systemctl reload nginx && echo OK'

# Config test + reload (DC-2)
ssh -i ~/.ssh/id_ed25519 -p 2222 root@77.92.152.3 \
  'nginx -t && systemctl reload nginx && echo OK'
```

---

## 🌐 Cloudflare DNS Yönetimi

```bash
# Yeni subdomain ekle
curl -s -X POST "https://api.cloudflare.com/client/v4/zones/a72e4fe4787b786fb91d41a3491949eb/dns_records" \
  -H "Authorization: Bearer YSaZrmVvW07MDCEwJSPJNeYKXVUrpK1lykaLDSQ9" \
  -H "Content-Type: application/json" \
  --data '{"type":"A","name":"yenisubdomain","content":"185.189.54.104","ttl":1,"proxied":true}'

# Tüm kayıtları listele
curl -s "https://api.cloudflare.com/client/v4/zones/a72e4fe4787b786fb91d41a3491949eb/dns_records?per_page=100" \
  -H "Authorization: Bearer YSaZrmVvW07MDCEwJSPJNeYKXVUrpK1lykaLDSQ9" | \
  python3 -c "import json,sys; [print(r['type'], r['name'], '→', r['content']) for r in json.load(sys.stdin)['result']]"
```

---

## ✅ Güncelleme Sonrası Kontrol Listesi

```bash
# Tüm servisleri hızlı test
for domain in emarecloud.tr asistan.emarecloud.tr finans.emarecloud.tr api.emarecloud.tr token.emarecloud.tr webdizayn.emarecloud.tr; do
  code=$(curl -m 10 -s -o /dev/null -w "%{http_code}" https://$domain)
  printf "%-40s → %s\n" "$domain" "$code"
done
```

**Beklenen sonuçlar:**
| Alan Adı | Beklenen |
|---|---|
| `emarecloud.tr` | 200 veya 302 |
| `asistan.emarecloud.tr` | 200 veya 301 |
| `finans.emarecloud.tr` | 200 |
| `api.emarecloud.tr` | 200 (FastAPI docs) |
| `token.emarecloud.tr` | 404 normal (root yok, /dashboard kullan) |
| `webdizayn.emarecloud.tr` | 302 (panele yönlenir) |

---

## ⚠️ SELinux Notları (AlmaLinux/CentOS)

Yeni dosya kopyaladıktan sonra nginx okuyamıyorsa:
```bash
# /var/www altı için
restorecon -Rv /var/www/webdizayn/

# /opt altı için (zaten httpd_sys_content_t değilse)
semanage fcontext -a -t httpd_sys_content_t "/opt/emareapi(/.*)?"
restorecon -Rv /opt/emareapi/
```

---

## 🚨 Acil Durum

```bash
# DC-1 servislerini kontrol et
ssh -i ~/.ssh/id_ed25519 root@185.189.54.104 \
  'systemctl status emarecloud nginx && pm2 status'

# DC-2 servislerini kontrol et
ssh -i ~/.ssh/id_ed25519 -p 2222 root@77.92.152.3 \
  'systemctl status emarecloud nginx php-fpm'

# Hata logları
ssh -i ~/.ssh/id_ed25519 root@185.189.54.104 'journalctl -u emarecloud -n 30'
ssh -i ~/.ssh/id_ed25519 -p 2222 root@77.92.152.3 'tail -20 /var/www/emarefinance/storage/logs/laravel.log'
```
