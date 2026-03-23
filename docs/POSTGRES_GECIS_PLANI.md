# EmareCloud PostgreSQL Gecis Plani

Bu plan, mevcut SQLite kullanan EmareCloud sistemini kesintiyi minimumda tutarak merkezi PostgreSQL sunucusuna tasimak icindir.

## 1) Hazirlik (tamamlandi)

- Ayrı PostgreSQL sunucusu kuruldu: `185.189.54.107`
- Emare DB ve kullanici olusturuldu:
  - DB: `emarecloud_db`
  - Kullanici: `emarecloud_user`
- Uygulama sunucusundan baglanti testi gecti (`185.189.54.104 -> 185.189.54.107:5432`).

## 2) Kademeli Gecis Stratejisi

1. **Driver hazirligi**
   - `requirements.txt` icinde `psycopg2-binary` aktif olmalidir.

2. **Cift ortama hazir config**
   - Uygulama zaten `DATABASE_URL` varsa PostgreSQL, yoksa SQLite kullanir.
   - Bu sayede rollback kolaydir.

3. **Staging dogrulama**
   - Staging/yan instance'ta `DATABASE_URL` PostgreSQL'e alinir.
   - `db.create_all()` ile schema olusumu dogrulanir.
   - Kritik endpoint smoke testleri calistirilir.

4. **Canli gecis (kisa bakım penceresi)**
   - Uygulama yazma trafigi kisa sure dondurulur.
   - SQLite verisi PostgreSQL'e tasinir.
   - Uygulama env'de `DATABASE_URL` PostgreSQL olarak ayarlanir.
   - Servis yeniden baslatilir.

5. **Gecis sonrasi izleme**
   - Login, org, server, token, audit akislarinda hata logu kontrol edilir.
   - DB baglanti/hata oranlari izlenir.

## 3) Ornek DATABASE_URL

```
postgresql+psycopg2://emarecloud_user:EmarePg2026X@185.189.54.107:5432/emarecloud_db
```

## 4) Sunucu Komutlari (Uygulama Sunucusu)

### Paket guncelle

```bash
cd /path/to/emarecloud
pip install -r requirements.txt
```

### Gecici test (tek shell)

```bash
export DATABASE_URL='postgresql+psycopg2://emarecloud_user:EmarePg2026X@185.189.54.107:5432/emarecloud_db'
python -c "from app import create_app; from extensions import db; app=create_app();\
with app.app_context():\
    db.engine.connect().execute(db.text('select 1'));\
    print('PG OK')"
```

### Kalici ayar

- `.env` veya servis ortamina `DATABASE_URL` eklenir.
- Uygulama servisi restart edilir.

## 5) Rollback Plani

- `DATABASE_URL` satiri kaldirilir veya bosaltilir.
- Servis yeniden baslatilir.
- Uygulama otomatik olarak SQLite dosyasina geri doner.

## 6) Notlar

- PostgreSQL sunucusu tek merkez oldugu icin yedekleme zorunludur.
- Sonraki adim: otomatik nightly backup + PITR (point-in-time recovery).
- Sonraki adim: uygulama tarafinda SQLAlchemy pool ayarlari (`pool_pre_ping`, `pool_recycle`) eklenebilir.
