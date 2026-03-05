# EmareCloud — TLS Reverse Proxy Rehberi

> Production ortamında HTTPS ve WebSocket desteği için Nginx reverse proxy yapılandırması.

---

## 1. Gereksinimler

- Nginx 1.18+
- SSL sertifikası (Let's Encrypt veya ticari)
- Domain adı (ör: `panel.emarecloud.com`)

---

## 2. Let's Encrypt SSL Sertifikası (Ücretsiz)

```bash
# Certbot kurulumu
sudo apt update && sudo apt install -y certbot python3-certbot-nginx

# Sertifika oluştur
sudo certbot certonly --standalone -d panel.emarecloud.com

# Otomatik yenileme (crontab)
echo "0 3 * * * certbot renew --quiet" | sudo crontab -
```

---

## 3. Nginx Yapılandırması

`/etc/nginx/sites-available/emarecloud` dosyasını oluşturun:

```nginx
# ============================================
# EmareCloud — Nginx Reverse Proxy + TLS
# ============================================

# HTTP → HTTPS yönlendirme
server {
    listen 80;
    server_name panel.emarecloud.com;
    return 301 https://$host$request_uri;
}

# HTTPS + WebSocket
server {
    listen 443 ssl http2;
    server_name panel.emarecloud.com;

    # ── SSL Sertifikaları ──
    ssl_certificate     /etc/letsencrypt/live/panel.emarecloud.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/panel.emarecloud.com/privkey.pem;

    # ── SSL Güvenlik Ayarları ──
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;
    ssl_session_tickets off;

    # HSTS (1 yıl)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # ── Güvenlik Header'ları ──
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; font-src 'self' https://cdnjs.cloudflare.com; img-src 'self' data: https:; connect-src 'self' wss://$host;" always;

    # ── Genel Ayarlar ──
    client_max_body_size 50M;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;

    # ── Ana Uygulama (Flask) ──
    location / {
        proxy_pass http://127.0.0.1:5555;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Gzip sıkıştırma (Flask'takine ek olarak)
        gzip on;
        gzip_types text/plain text/css application/json application/javascript text/xml;
        gzip_min_length 256;
    }

    # ── WebSocket (SocketIO Terminal) ──
    location /socket.io/ {
        proxy_pass http://127.0.0.1:5555/socket.io/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket timeout (terminal oturumları için)
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }

    # ── Static Dosyalar (Nginx doğrudan sunabilir) ──
    location /static/ {
        alias /opt/emarecloud/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # ── Loglama ──
    access_log /var/log/nginx/emarecloud_access.log;
    error_log  /var/log/nginx/emarecloud_error.log warn;
}
```

---

## 4. Aktivasyon

```bash
# Symlink oluştur
sudo ln -s /etc/nginx/sites-available/emarecloud /etc/nginx/sites-enabled/

# Yapılandırmayı test et
sudo nginx -t

# Nginx'i yeniden başlat
sudo systemctl reload nginx
```

---

## 5. EmareCloud .env Güncellemesi

```bash
# .env dosyasına ekleyin:
SESSION_COOKIE_SECURE=true
CORS_ALLOWED_ORIGINS=https://panel.emarecloud.com
```

---

## 6. Gunicorn ile Production Çalıştırma

```bash
# Systemd servisi: /etc/systemd/system/emarecloud.service
[Unit]
Description=EmareCloud Panel
After=network.target

[Service]
Type=notify
User=emarecloud
Group=emarecloud
WorkingDirectory=/opt/emarecloud
Environment="PATH=/opt/emarecloud/venv/bin"
EnvironmentFile=/opt/emarecloud/.env
ExecStart=/opt/emarecloud/venv/bin/gunicorn -c gunicorn.conf.py app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable emarecloud
sudo systemctl start emarecloud
```

---

## 7. Firewall Kuralları

```bash
# UFW ile (sunucunun kendi firewall'u)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 5555/tcp    # Doğrudan erişimi kapat
```

---

## 8. SSL Test

```bash
# SSL Labs test (A+ hedeflenmeli)
# https://www.ssllabs.com/ssltest/analyze.html?d=panel.emarecloud.com

# Komut satırından
curl -I https://panel.emarecloud.com
# Beklenen: HTTP/2 200, Strict-Transport-Security header
```

---

## 9. Sorun Giderme

| Sorun | Çözüm |
|-------|-------|
| 502 Bad Gateway | EmareCloud servisi çalışıyor mu? `systemctl status emarecloud` |
| WebSocket bağlanmıyor | `proxy_http_version 1.1` + `Upgrade` header'larını kontrol edin |
| Mixed Content uyarısı | `.env`'de `SESSION_COOKIE_SECURE=true` ayarlayın |
| Sertifika hatası | `certbot renew` çalıştırın |
| Yavaş yanıt | `proxy_read_timeout` değerini artırın |
