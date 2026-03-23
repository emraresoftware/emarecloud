# Emare Security OS Production Deploy

Bu klasor, emaresecurityos.emarecloud.tr icin gerekli production artefaktlarini icerir.

## Hedef
- Domain: emaresecurityos.emarecloud.tr
- Sunucu: 185.189.54.104
- Uygulama yolu: /var/www/emaresecurityos
- Servis: emaresecurityos.service
- Internal app port: 127.0.0.1:8202

## Dosyalar
- .env.example: Ornek ortam degiskenleri
- emaresecurityos.service: Gunicorn systemd unit
- emaresecurityos.emarecloud.tr.conf: Nginx reverse proxy vhost
- deploy.sh: Sunucuda calisacak deploy scripti

## Hızlı Akış
1. Kodu /var/www/emaresecurityos altina kopyala.
2. `.env.example` dosyasini `.env` olarak kopyala ve secret degerleri guncelle.
3. `deploy.sh` calistir.
4. DNS A kaydini 185.189.54.104'e yonlendir.
5. Sertifika al:
   - HTTP-01: certbot --nginx -d emaresecurityos.emarecloud.tr
   - Gerekirse DNS-01 fallback.

## Deploy Komutu (Sunucu)
```bash
cd /var/www/emaresecurityos
bash deploy/deploy.sh
```
