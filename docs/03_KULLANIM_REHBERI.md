# EmareCloud — Kullanım Kılavuzu

Bu kılavuz, **EmareCloud Altyapı Yönetim Paneli** yazılımının kurulumu ve günlük kullanımını anlatır.

---

## 1. Panel Nedir?

EmareCloud paneli ile:

- Birden fazla sunucuyu tek arayüzden izleyebilir,
- **Güvenli giriş** (login) ve **RBAC tabanlı yetkilendirme** ile kontrollü erişim sağlayabilir,
- SSH ile bağlanıp metrik (CPU, RAM, disk, ağ) ve disk sağlık (SMART) görebilir,
- 58+ hazır uygulamayı (MySQL, Nginx, Docker, **Ollama, Whisper** vb. AI araçları dahil) tek tıkla kurabilir,
- Güvenlik duvarı (UFW/firewalld) kurallarını yönetebilir,
- LXD ile sanal makineler (container) oluşturup yönetebilir,
- Depolama sayfasından RAID protokollerini, sunucu disklerini ve yazılım RAID durumunu takip edebilir,
- Web terminal ile sunucuda komut çalıştırabilirsiniz.

**Güvenlik:** SSH kimlik bilgileri AES-256-GCM ile şifreli saklanır. Tüm API uçları RBAC ile korunur.

---

## 2. Kurulum ve Çalıştırma

### Gereksinimler

- Python 3.10+
- Proje klasöründe `requirements.txt` ile belirtilen paketler

### Otomatik Kurulum (Önerilen)

```bash
chmod +x setup.sh
./setup.sh
```

`setup.sh` interaktif wizard 7 adımda kurulumu tamamlar: sistem kontrolü, bağımlılıklar, master encryption key, admin kullanıcı, port ayarı, veritabanı başlatma, `.env` dosyası oluşturma.

### Manuel Kurulum

```bash
cd "sunucu yönetimi"
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Paneli Başlatma

```bash
source venv/bin/activate
python app.py
```

Tarayıcıda açın: **http://localhost:5555** veya **http://127.0.0.1:5555**

Sunucunun çalıştığını kontrol etmek için: **http://localhost:5555/health**

### Üretim Ortamı

```bash
gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker \
  -w 1 -b 0.0.0.0:5555 "app:create_app()"
```

TLS/SSL için Nginx reverse proxy rehberi: [docs/TLS_REVERSE_PROXY.md](docs/TLS_REVERSE_PROXY.md)

---

## 3. Arayüz Genel Bakış

- **Giriş ekranı:** Panel açıldığında kullanıcı adı ve şifre ile giriş yapılır.
- **Sol menü (sidebar):** Dashboard, Uygulama Pazarı, Sanallaştırma, Depolama, sunucu listesi, Sunucu Ekle butonu.
- **Üst çubuk:** Sayfa başlığı, saat, tema (aydınlık/karanlık), yenile, çıkış.
- **İçerik alanı:** Seçilen sayfaya göre değişir.

Klavye: **ESC** = açık modali kapatır, **Ctrl+K** = Sunucu Ekle modalını açar.

---

## 3b. Giriş ve Yetkilendirme (RBAC)

### Giriş Yapma

Panel açıldığında **giriş ekranı** karşılar. Admin kullanıcı, `setup.sh` wizard'ı ile veya `/register` sayfasından oluşturulur.

### Şifre Kuralları

Şifre aşağıdaki tüm kurallara uymalıdır:
- Minimum **8 karakter**
- En az **1 büyük harf** (A-Z)
- En az **1 küçük harf** (a-z)
- En az **1 rakam** (0-9)
- En az **1 özel karakter** (!@#$%^&* vb.)

### Roller ve Yetkiler

Panel **4 seviye rol** sunar:

| Rol | Yetkiler |
|-----|----------|
| **super_admin** | Tüm işlemler, kullanıcı yönetimi, lisans, sistem ayarları |
| **admin** | Sunucu CRUD, bağlantı, komut çalıştırma, market kurulum, güvenlik duvarı, VM yönetimi |
| **operator** | Sunucu bağlantı, metrik görüntüleme, komut çalıştırma (sınırlı) |
| **read_only** | Sadece dashboard ve metrik görüntüleme, değişiklik yapamaz |

Her API endpoint'i hangi rolün erişebileceğine göre korunur. Detaylar: [docs/RBAC_ENDPOINT_MATRIX.md](docs/RBAC_ENDPOINT_MATRIX.md)

### Audit Log

Tüm kritik işlemler (sunucu ekleme/silme, bağlantı, komut çalıştırma, ayar değişikliği) audit log'a kaydedilir.

---

## 4. Dashboard

- **Özet kartlar:** Toplam sunucu, çevrimiçi, çevrimdışı, SSH ile bağlı sayısı.
- **Sunucu kartları:** Her sunucu için durum (çevrimiçi/çevrimdışı), gecikme, host, grup.
- Karttaki **üç nokta (⋮):** Detaylar, Terminal, Sil.
- Karta tıklayarak veya **Detaylar** ile sunucu detay sayfasına gidersiniz.

---

## 5. Sunucu Ekleme ve Temel Yönetim

### Sunucu Ekleme

1. Sol altta **「+ Sunucu Ekle」** veya **Ctrl+K**.
2. Formu doldurun:
   - **Sunucu adı** (zorunlu)
   - **Grup** (örn. Üretim, Test)
   - **IP / hostname** (zorunlu)
   - **Port** (varsayılan 22)
   - **Kullanıcı adı** ve **şifre** (zorunlu)
   - **Rol** (Web, Veritabanı, Cache, Yedekleme, Uygulama, Genel)
   - **Lokasyon** (örn. İstanbul, DC1)
   - **Kurulum tarihi**, **Sorumlu**, **Hedef / Kurulum notu**
   - İsteğe bağlı: Açıklama
3. **Kaydet** → Sunucu listeye eklenir.

### Sunucu Düzenleme

- Sunucu **detay** sayfasında **「Sunucuyu düzenle」** butonu ile aynı alanları (ad, grup, host, port, kullanıcı, rol, lokasyon, kurulum tarihi, sorumlu, hedef/not, açıklama) güncelleyebilirsiniz. Şifre alanı boş bırakılırsa mevcut şifre değişmez.

### Sunucu Silme

- Dashboard’da ilgili sunucu kartında **⋮** → **Sil** → Onaylayın.

### Sunucuya Bağlanma

- Sunucu **detay** sayfasında veya kartta **Bağlan** butonu.
- Bağlantı başarılı olunca metrikler, terminal, güvenlik duvarı ve sanal makineler kullanılabilir.

---

## 6. Sunucu Detay Sayfası

Sol menüden bir sunucu seçince açılır. Sırayla:

- **Üst bilgi:** Çevrimiçi/çevrimdışı, IP:port, gecikme. **Bağlan**, **Terminal**, **Yenile**, **Sunucuyu düzenle**.
- **Kurulum / Bizim ayarlar:** Sunucuya rol, lokasyon, kurulum tarihi, sorumlu veya hedef/not tanımladıysanız bu blokta görünür.
- **Sistem bilgisi:** Hostname, işletim sistemi, kernel, uptime (sunucuya bağlıyken).
- **Metrikler:** CPU, RAM, disk kullanımı (ve SMART sağlık durumu, sunucuda smartctl varsa), ağ, süreçler, servisler.
- **Hızlı eylemler:** Güncelleme kontrolü, güncelle, önbellek temizle, disk temizliği, Nginx/Docker yeniden başlat, yeniden başlat, kapat (sunucuya bağlıyken).
- **Güvenlik Duvarı:** Her zaman görünür; bağlıyken **Durumu Getir** ile UFW/firewalld yönetimi.
- **Sanal Makineler:** Her zaman görünür; bağlıyken **Listeyi Getir** ile LXD container listesi ve yönetimi.

---

## 7. Web Terminal

- Sunucu detayda **Terminal** veya kart menüsünden **Terminal**.
- Açılan sayfada komut yazıp Enter ile sunucuda çalıştırırsınız.
- **Hızlı komutlar** butonları: uptime, df -h, free -h, top, docker ps vb. tek tıkla gönderir.

Not: Önce sunucuya **Bağlan** demeniz gerekebilir; terminal sayfası gerekirse otomatik bağlanmayı dener.

---

## 8. Uygulama Pazarı (Market)

- Sol menüden **Uygulama Pazarı**.
- **58+ hazır uygulama** akordeon kategoriler halinde listelenir:
  - **Veritabanı:** MySQL, PostgreSQL, Redis, MongoDB, MariaDB, InfluxDB, CouchDB vb.
  - **Web Sunucu:** Nginx, Apache, Caddy, Traefik, HAProxy vb.
  - **Altyapı:** Docker, Docker Compose, Kubernetes (K3s), Portainer vb.
  - **Geliştirme:** Node.js, PHP, Python, Go, Ruby, Rust vb.
  - **Sanallaştırma:** LXD, Proxmox, QEMU/KVM vb.
  - **Güvenlik:** UFW, Fail2Ban, CrowdSec, WireGuard, OpenVPN vb.
  - **Monitoring:** Prometheus, Grafana, Netdata, Zabbix vb.
  - **AI / Yapay Zeka:** Ollama, Python AI (PyTorch), OpenAI Whisper, Open WebUI, code-server, Text Generation WebUI
  - **İletişim:** Mattermost, Rocket.Chat vb.
  - **Otomasyon:** Ansible, Terraform, Jenkins, GitLab Runner vb.
- **Kur** → Sunucu seçin → İstenen seçenekleri doldurun (şifre, port vb.) → **Kurulumu Başlat**.
- Kurulum sırasında animasyon gösterilir; çıktı aynı pencerede gösterilir.

Sunucuya bağlı olmanız gerekir; gerekirse kurulum adımında bağlantı otomatik denenir.

---

## 9. Güvenlik Duvarı

- **Nerede:** Sunucu detay sayfasında, **Güvenlik Duvarı** bölümü (bağlı olmasanız da görünür).
- **İlk adım:** Sunucuya **Bağlan** → **Durumu Getir**.
- Desteklenen: **UFW** (Ubuntu/Debian), **firewalld** (RHEL/CentOS). Hangisi kuruluysa o kullanılır.
- **Etkinleştir / Devre Dışı Bırak:** Güvenlik duvarını açar/kapatır.
- **Kurallar tablosu:** Mevcut kurallar listelenir; **Sil** ile kural silebilirsiniz.
- **Kural ekle:** Port (örn. 22, 80/tcp), protokol (TCP/UDP), İzin ver/Engelle, isteğe bağlı kaynak IP → **Ekle**.

UFW yoksa: Uygulama Pazarından **「UFW (Güvenlik Duvarı)」** ile kurabilirsiniz.

---

## 10. Sanal Makineler (LXD)

- **Nerede:** Sunucu detay sayfasında, **Sanal Makineler** bölümü.
- **Ön koşul:** Sunucuya bağlı olun; sunucuda **LXD** kurulu olsun (yoksa Uygulama Pazarından **「LXD (Sanal Makineler)」** ile kurun).

### Listeleme

- **Listeyi Getir** → O sunucudaki tüm container’lar (ad, durum, IP) listelenir.

### Yeni sanal makine

- **Yeni Sanal Makine** → Container adı (örn. web01, db02), image (örn. ubuntu:22.04), RAM/CPU/disk → **Oluştur**.
- Oluşturulan container önce durdurulmuş olur; listeden **Başlat** ile açar, **Durdur** ile kapatırsınız.

### Yönetim

- **Başlat / Durdur:** Container’ı açar veya kapatır.
- **Terminal ikonu:** Container **içinde** komut çalıştırma penceresini açar; komutu yazıp **Çalıştır** dersiniz.
- **Sil:** Container’ı kalıcı siler (onay gerekir).

Detaylı adımlar için proje içindeki **SANAL_MAKINE_YONETIMI.md** dosyasına bakabilirsiniz.

**Sanallaştırma sayfası:** Sol menüden **Sanallaştırma** ile tüm sunucular için tek ekrandan sunucu seçip LXD container listesini getirebilir, yeni makine oluşturup başlat/durdur/komut/sil yapabilirsiniz.

---

## 10b. Depolama Sayfası

- Sol menüden **Depolama**.
- **RAID Protokolleri:** Diskler arası gecikme (örn. 4 ms) ile protokol tanımlayın; listele, ekle, düzenle, sil.
- **Sunucu diskleri:** Sunucu seçin → **Bağlan** (gerekirse) → **Diskleri getir**. Kapasite (kullanım %, çubuk), kullanılan/toplam/boş, **SMART sağlık** (PASSED/FAILED/—) görünür. **Anlık güncelleme (30 sn)** ile otomatik yenileme açılabilir.
- **RAID durumu:** Sunucu seçip **RAID durumunu getir** ile yazılım RAID (mdadm) dizileri ve ham `/proc/mdstat` çıktısı gösterilir.

---

## 11. Sık Karşılaşılan Durumlar

| Durum | Ne yapmalı? |
|--------|--------------|
| Sayfa açılmıyor | Panel çalışıyor mu kontrol edin (`python app.py` veya Gunicorn). Tarayıcıda http://127.0.0.1:5555 ve http://localhost:5555/health deneyin. |
| Giriş yapamıyorum | Kullanıcı adı ve şifreyi kontrol edin. Şifre kurallarına uygun mu? 5 başarısız denemeden sonra hesap kilitlenir. |
| Sunucuya bağlanamıyorum | SSH bilgileri (IP, port, kullanıcı, şifre) doğru mu? Aynı bilgilerle `ssh kullanici@ip` deneyin. Paneldeki hata mesajını okuyun. |
| Yeni sunucu eklerken hata | config.json yazılabilir mi? Klasör izinlerini kontrol edin. Toast’taki hata mesajına bakın. |
| Güvenlik duvarı bölümü boş | Önce **Bağlan**, sonra **Durumu Getir**. UFW/firewalld yüklü değilse Market’ten UFW veya ilgili paketi kurun. |
| Sanal makine listesi boş | Sunucuya bağlı mı? LXD kurulu mu? Market’ten **LXD** kurun, sonra **Listeyi Getir**. |
| Disk sağlığı "—" veya "UNKNOWN" | Sunucuda **smartmontools** (smartctl) yüklü değildir; `apt install smartmontools` veya `yum install smartmontools` ile kurabilirsiniz. |
| Tehlikeli komut engellendi | Panel bazı komutları (örn. rm -rf /) güvenlik nedeniyle engeller. Gerekirse Web Terminal üzerinden dikkatli kullanın. |

---

## 12. Dosya Yapısı (Bilgi)

| Dosya / Klasör | Açıklama |
|----------------|----------|
| `app.py` | Factory pattern giriş noktası (`create_app()`) |
| `config.py` | Uygulama yapılandırması (CORS, debug, secret) |
| `auth_routes.py` | Kimlik doğrulama, RBAC, şifre kuralları |
| `license_manager.py` | RSA-4096 lisans doğrulama sistemi |
| `setup.sh` | İnteraktif 7 adımlı kurulum wizard'ı |
| `config.json` | Kayıtlı sunucular, ayarlar, raid_protocols |
| `core/` | Çekirdek modüller (middleware, database, helpers, config_io, logging_config) |
| `routes/` | Blueprint'ler (pages, servers, metrics, firewall, virtualization, commands, storage, market, terminal) |
| `ssh_manager.py` | SSH bağlantı yönetimi |
| `server_monitor.py` | CPU, RAM, disk (SMART sağlık), mdadm RAID, metrik toplama |
| `market_apps.py` | 58+ uygulama pazarı tanımları |
| `firewall_manager.py` | UFW/firewalld yönetimi |
| `virtualization_manager.py` | LXD container yönetimi |
| `templates/` | HTML şablonları (dashboard, market, server_detail, virtualization, storage, terminal, landing) |
| `static/` | CSS ve JavaScript |
| `docs/` | Dokümantasyon (genel bakış, kurulum, kullanım, API, yol haritası, MVP, RBAC matrisi, TLS rehberi) |
| `KULLANIM_KILAVUZU.md` | Bu kılavuz |
| `SANAL_MAKINE_YONETIMI.md` | Sanal makine yönetimi özeti |

---

## 13. Güvenlik Notları

- **Şifreleme:** SSH kimlik bilgileri `config.json` içinde **AES-256-GCM** ile şifrelenmiş saklanır. Master key `.env` dosyasında tutulur.
- **Kimlik doğrulama:** Panel giriş ekranı ile korunur; tüm API uçları session tabanlı yetkilendirme gerektirir.
- **RBAC:** 4 seviye rol ile endpoint erişimi kontrol edilir (detay: [docs/RBAC_ENDPOINT_MATRIX.md](docs/RBAC_ENDPOINT_MATRIX.md)).
- **Güvenlik başlıkları:** CSP, X-Frame-Options, X-Content-Type-Options, Strict-Transport-Security otomatik eklenir.
- **Brute-force koruması:** Ardışık başarısız giriş denemelerinde hesap kilitlenir.
- **CSRF koruması:** Form tabanlı işlemler CSRF token ile korunur.
- **Audit log:** Kritik işlemler yapılandırılmış loglama ile kaydedilir (JSON formatı, log rotasyonu).
- Canlı ortamda Gunicorn + Nginx reverse proxy + TLS kullanın (rehber: [docs/TLS_REVERSE_PROXY.md](docs/TLS_REVERSE_PROXY.md)).
- `.env` ve `config.json` dosyalarını `.gitignore`'a ekleyin.

---

*Son güncelleme: EmareCloud v1.0 — Secure Core Edition. Güncel davranış için arayüzü ve hata mesajlarını referans alın.*
