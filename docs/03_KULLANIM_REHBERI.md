# Kullanım Rehberi

Bu doküman, EmareCloud panelinin günlük kullanım akışını açıklar.

## 0. Giriş ve Yetkilendirme

Panel açıldığında **giriş ekranı** karşılar. Kullanıcı adı ve şifre ile oturum açılır.

### RBAC Rolleri

| Rol | Yetkiler |
|-----|----------|
| **super_admin** | Tüm işlemler, kullanıcı yönetimi, lisans, sistem ayarları |
| **admin** | Sunucu CRUD, bağlantı, komut, market kurulum, firewall, VM yönetimi |
| **operator** | Sunucu bağlantı, metrik görüntüleme, sınırlı komut çalıştırma |
| **read_only** | Sadece dashboard ve metrik görüntüleme |

Şifre kuralları: minimum 8 karakter, büyük/küçük harf, rakam, özel karakter zorunludur.

Detaylı yetki matrisi: [RBAC_ENDPOINT_MATRIX.md](RBAC_ENDPOINT_MATRIX.md)

## 1. Dashboard

- Toplam sunucu
- Çevrimiçi/çevrimdışı durumu
- SSH bağlı sunucu sayısı
- Sunucu kartları ve hızlı işlemler

Sunucu kartı işlemleri:
- Detaylar
- Terminal
- Sil
- Bağlan/Bağlantıyı kes

## 2. Sunucu Ekleme ve Düzenleme

Zorunlu alanlar:
- Sunucu adı
- Host/IP
- Kullanıcı adı
- Şifre

Opsiyonel / kurulum alanları:
- Port, Grup, Açıklama
- **Rol** (Web, Veritabanı, Cache, Yedekleme, Uygulama, Genel)
- **Lokasyon**, **Kurulum tarihi**, **Sorumlu**, **Hedef / Kurulum notu**

Sunucu detay sayfasında **Sunucuyu düzenle** ile aynı alanlar güncellenebilir; şifre boş bırakılırsa değişmez.

## 3. Sunucu Detay Sayfası

Bağlı durumda görülen bilgiler:
- Sistem: hostname, OS, kernel, uptime
- CPU kullanımı ve yük ortalaması
- RAM/swap
- Disk kullanım oranları
- Ağ arayüzleri, trafik, aktif bağlantı
- Süreçler (CPU bazlı)
- Servis durumları

## 4. Hızlı Eylemler

Örnek eylemler:
- Güncelleme kontrolü
- Sistem güncelleme
- Önbellek temizleme
- Disk temizlik
- Servis restart
- Reboot / Shutdown

## 5. Web Terminal

- Sayfa açıldığında sunucuya socket bağlantısı kurulur.
- Komutlar SSH üzerinden çalıştırılır.
- Hızlı komut butonları ile rutin kontroller yapılabilir.

## 6. Uygulama Pazarı

Akış:
1. Uygulama seç (Veritabanı, Web Sunucu, Altyapı, Geliştirme, Sanallaştırma, Güvenlik, Monitoring, **AI / Yapay Zeka**, İletişim, Otomasyon)
2. Sunucu seç
3. Opsiyonları gir
4. Kurulumu başlat (kurulum sırasında animasyon gösterilir)

**58+ uygulama** akordeon kategoriler halinde listelenir. AI kategorisinde: Ollama, Python AI (PyTorch), Whisper, Open WebUI, code-server, Text Generation WebUI. Kurulum scriptleri backend tarafında oluşturulur ve sunucuda çalıştırılır.

## 7. Güvenlik Duvarı Yönetimi

Desteklenen altyapılar:
- UFW
- firewalld

İşlemler:
- Durum getir
- Etkinleştir/devre dışı bırak
- Kural ekle (port/protokol/kaynak)
- Kural sil

## 8. Sanallaştırma (LXD)

- **Sunucu detay** veya **Sanallaştırma** sayfasından (sol menü) erişilir.
- İşlemler: Sunucu seçimi, LXD kontrolü, container listesi, yeni container oluşturma, Başlat / Durdur / Sil, container içinde komut çalıştırma.

## 9. Depolama

**RAID Protokolleri:**
- Protokol adı, diskler arası gecikme (ms), RAID seviyesi, minimum disk sayısı, açıklama, notlar.
- Ekle, düzenle, sil.

**Sunucu diskleri (sekme):**
- Sunucu seç → Bağlan (gerekirse) → Diskleri getir.
- Tablo: bağlama noktası, cihaz, kullanım %, kullanılan/toplam/boş, **SMART sağlık** (PASSED/FAILED/—).
- Özet satırı: birim sayısı, toplam/kullanılan kapasite, uyarı sayısı.
- **Anlık güncelleme (30 sn)** ile otomatik yenileme.

**RAID durumu (sekme):**
- Sunucu seç → RAID durumunu getir → mdadm dizileri ve `/proc/mdstat` çıktısı.

## 10. Operasyon Önerileri

- Üretimde kritik aksiyonlar için onay akışı kullanın.
- Düzenli sunucu envanteri ve erişim temizliği yapın.
- RBAC rolleri ile hızlı eylemleri sınırlandırın.
- Audit log'ları düzenli kontrol edin.
- TLS/SSL yapılandırması için: [TLS_REVERSE_PROXY.md](TLS_REVERSE_PROXY.md)
