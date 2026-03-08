# 🔥 EmareFirewall Dervişi — Çeyiz Dosyası

## Kimlik
- **Proje**: EmareFirewall
- **Derviş Adı**: emarefirewall
- **Kuruluş Tarihi**: 8 Mart 2026
- **Yaratıcı**: emarecloud dervişi
- **Konum**: EmareCloud içinde entegre modül

## Görev Tanımı
EmareFirewall, Emare ekosistemindeki sunucuların güvenlik duvarı yönetiminden sorumlu dervişdir.
UFW (Ubuntu/Debian) ve firewalld (RHEL/CentOS/AlmaLinux) destekler.
Tek panelden tüm firewall operasyonlarını yönetir.

## Yetenekler (Çeyiz)

### 🛡️ Temel Firewall Yönetimi
- **Durum Görüntüleme**: Firewall tipi, aktiflik, zone, kural listesi
- **Etkinleştir / Devre Dışı Bırak**: Tek tıkla firewall aç/kapa
- **Port Kuralları**: Port aç/kapat (TCP/UDP, aralık desteği)
- **Servis Kuralları**: http, https, ssh, ftp, mysql, redis, mongodb vs.
- **Kural Silme**: İndeks bazlı veya tip bazlı kural kaldırma

### 🚫 IP Engelleme
- **IP Block**: Tekil IP veya CIDR blok engelleme (rich rule ile)
- **IP Unblock**: Engel kaldırma
- **Engelli IP Listesi**: Tüm engelli IP'leri görüntüleme
- **Geo-Block**: Ülke bazlı toplu IP engelleme (ipset + ipdeny.com)

### 🔄 Port Yönlendirme
- **Forward Port**: port:proto → toport:toaddr yönlendirme
- **Masquerade**: Otomatik masquerade etkinleştirme
- **Kaldırma**: Forward kuralı silme

### 🏗️ Zone Yönetimi (firewalld)
- **Zone Listesi**: Tüm zone'ları görüntüleme
- **Zone Detayı**: Servisler, portlar, rich rule'lar, forward'lar
- **Varsayılan Zone**: Değiştirme

### 🔒 Rich Rule (Gelişmiş Kurallar)
- **Ekleme**: Özel firewalld rich rule
- **Kaldırma**: Rich rule silme
- **Görüntüleme**: Aktif rich rule listesi

### 🚨 Fail2ban Entegrasyonu
- **Durum**: Jail listesi, ban sayıları
- **Ban/Unban**: Jail bazlı IP ban/unban
- **İstatistik**: Toplam ban, anlık ban

### 📊 Bağlantı İzleme
- **Aktif Bağlantılar**: ss/netstat ile canlı bağlantı listesi
- **İstatistikler**: ESTABLISHED, LISTENING, TIME_WAIT, CLOSE_WAIT
- **Top IP'ler**: En çok bağlanan IP'ler
- **Top Portlar**: En çok kullanılan portlar

### 🔍 Güvenlik Taraması
- **Skor Bazlı**: 0-100 arası güvenlik puanı
- **Kontroller**:
  - Firewall aktifliği
  - SSH root login kontrolü
  - SSH password auth kontrolü
  - Fail2ban durumu
  - Tehlikeli port kontrolü (Telnet, FTP, MySQL, Redis, MongoDB, Elasticsearch)
  - Kernel güncelleme durumu
- **Bulgular**: Severity bazlı (critical, high, medium, low)
- **Öneriler**: Her bulgu için çözüm önerisi

## API Endpoint'leri

| Metod | Endpoint | Açıklama | Yetki |
|-------|----------|----------|-------|
| GET | `/api/servers/<id>/firewall/status` | Durum | firewall.view |
| POST | `/api/servers/<id>/firewall/enable` | Etkinleştir | firewall.manage |
| POST | `/api/servers/<id>/firewall/disable` | Devre dışı | firewall.manage |
| POST | `/api/servers/<id>/firewall/rules` | Port kuralı ekle | firewall.manage |
| DELETE | `/api/servers/<id>/firewall/rules/<idx>` | Kural sil | firewall.manage |
| POST | `/api/servers/<id>/firewall/services` | Servis ekle | firewall.manage |
| DELETE | `/api/servers/<id>/firewall/services/<name>` | Servis kaldır | firewall.manage |
| POST | `/api/servers/<id>/firewall/block-ip` | IP engelle | firewall.manage |
| POST | `/api/servers/<id>/firewall/unblock-ip` | IP engel kaldır | firewall.manage |
| GET | `/api/servers/<id>/firewall/blocked-ips` | Engelli IP'ler | firewall.view |
| POST | `/api/servers/<id>/firewall/port-forward` | Port yönlendirme | firewall.manage |
| DELETE | `/api/servers/<id>/firewall/port-forward` | Forward kaldır | firewall.manage |
| GET | `/api/servers/<id>/firewall/zones` | Zone listesi | firewall.view |
| GET | `/api/servers/<id>/firewall/zones/<name>` | Zone detayı | firewall.view |
| POST | `/api/servers/<id>/firewall/zones/default` | Default zone | firewall.manage |
| POST | `/api/servers/<id>/firewall/rich-rules` | Rich rule ekle | firewall.manage |
| DELETE | `/api/servers/<id>/firewall/rich-rules` | Rich rule kaldır | firewall.manage |
| GET | `/api/servers/<id>/firewall/fail2ban` | Fail2ban durumu | firewall.view |
| POST | `/api/servers/<id>/firewall/fail2ban/ban` | F2B ban | firewall.manage |
| POST | `/api/servers/<id>/firewall/fail2ban/unban` | F2B unban | firewall.manage |
| GET | `/api/servers/<id>/firewall/connections` | Aktif bağlantılar | firewall.view |
| GET | `/api/servers/<id>/firewall/connection-stats` | Bağlantı istatistik | firewall.view |
| GET | `/api/servers/<id>/firewall/security-scan` | Güvenlik taraması | firewall.view |
| POST | `/api/servers/<id>/firewall/geo-block` | Ülke engelleme | firewall.manage |

## Arayüz (Web UI)
- **URL**: `/firewall`
- **Sidebar**: Altyapı bölümünde "Güvenlik Duvarı" menüsü
- **7 Tab**: Kurallar, IP Engelle, Port Yönlendirme, Zone'lar, Fail2ban, Bağlantılar, Güvenlik Taraması
- **Gerçek Zamanlı**: Sunucu değiştirince otomatik yükleme
- **Responsive**: Mobil uyumlu tasarım
- **Toast**: İşlem sonuçları bildirim

## Dosya Yapısı
```
emarecloud/
├── firewall_manager.py        # Backend: 29 fonksiyon, ~600 satır
├── routes/firewall.py         # API: 24 endpoint
├── templates/firewall.html    # Frontend: 7 tab, ~700 satır
├── templates/base.html        # Sidebar menü entegrasyonu
└── routes/pages.py            # /firewall sayfa route'u
```

## RBAC Yetkileri
- `firewall.view` — Durum görüntüleme, bağlantı izleme, güvenlik taraması
- `firewall.manage` — Kural ekleme/silme, IP engelleme, zone değiştirme

## Desteklenen Firewall'lar
| Tip | Distro | Durum |
|-----|--------|-------|
| firewalld | AlmaLinux, CentOS, RHEL, Fedora | ✅ Tam destek |
| UFW | Ubuntu, Debian | ✅ Tam destek |

## Bağımlılıklar
- **ssh_mgr**: SSH bağlantısı üzerinden komut çalıştırma
- **audit**: Tüm işlemler audit log'a yazılır
- **rbac**: Yetki bazlı erişim kontrolü
- **flask_login**: Oturum doğrulama

## Emare Anayasası Uyumu
- ✅ Madde 1: Türkçe docstring ve açıklamalar
- ✅ Madde 3: Audit log entegrasyonu
- ✅ Madde 5: RBAC yetki kontrolü
- ✅ Madde 7: SSH üzerinden güvenli komut çalıştırma
- ✅ Madde 12: Modüler yapı (manager → route → template)
