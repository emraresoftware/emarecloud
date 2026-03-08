# Sanal Makineleri Nasıl Yönetirsiniz?

Sanal makineler (LXD container'lar) **sunucu detay** sayfasında veya **Sanallaştırma** sayfasında yönetilir.

## 1. Nerede?

- **Sunucu detay:** Sol menüden bir sunucu seçin → sayfada **「Sanal Makineler」** bölümü.
- **Sanallaştırma sayfası:** Sol menüden **Sanallaştırma** → sunucu seçin → aynı işlemler (listele, yeni makine, başlat/durdur, komut, sil).
- Önce sunucuya **Bağlan**, gerekirse Uygulama Pazarından **LXD** kurun.

## 2. Listeleme

- **「Listeyi Getir」** → O sunucudaki tüm container'lar listelenir (Ad, Durum, IP).
- Liste boşsa: LXD kurulu değildir veya henüz container yok.

## 3. Yeni Sanal Makine

- **「Yeni Sanal Makine」** → Modal açılır.
- **Container adı:** Örn. `web01`, `db02` (sadece harf, rakam, tire, alt çizgi).
- **Image:** Örn. `ubuntu:22.04`, `debian:12`, `alpine:3.19`.
- **RAM / CPU / Disk:** Örn. `1GB`, `1`, `10GB`.
- **「Oluştur」** → Container oluşur (henüz durdurulmuş). Listeden **「Başlat」** ile açar, **「Durdur」** ile kapatırsınız.

## 4. Başlat / Durdur / Sil

- Her satırda:
  - **Başlat** – Container’ı açar (RUNNING).
  - **Durdur** – Container’ı kapatır (STOPPED).
  - **Terminal ikonu** – Container **içinde** komut çalıştırma penceresini açar.
  - **Sil** – Container’ı kalıcı siler (onay gerekir).

## 5. Container İçinde Komut Çalıştırma

- Çalışan bir container’ın satırında **terminal (komut)** ikonuna tıklayın.
- Açılan pencerede komutu yazın (örn. `apt update`, `df -h`, `hostname`).
- **「Çalıştır」** → Çıktı aynı pencerede gösterilir. Böylece sanal makineyi panelden yönetebilirsiniz.

## 6. Özet

| İşlem           | Nasıl?                                      |
|-----------------|---------------------------------------------|
| Listele         | Listeyi Getir                               |
| Yeni VM         | Yeni Sanal Makine → formu doldur → Oluştur  |
| Aç / Kapat      | Başlat / Durdur                             |
| İçinde komut    | Terminal ikonu → komut yaz → Çalıştır       |
| Sil             | Sil (onay verin)                            |

Tüm işlemler **seçili sunucu** üzerinde yapılır; her sunucunun kendi LXD’i ve container listesi vardır.
