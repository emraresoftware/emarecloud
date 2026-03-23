# Changelog

Bu projede yapılan tüm değişikliklerin kaydı. [Semver](https://semver.org/) kullanılır.

## [1.13.0] — 2026-03-23

### Eklendi — SIEM Modülü (5 Özellik)
- **Otomatik Alert → Ticket:** Eşik aşımında otomatik ITSM ticket oluşturma (auto_ticket config flag)
- **Tehdit İstihbaratı (Threat Intelligence):** IP/domain/hash gösterge veritabanı, tehdit ekleme/silme/kontrol API + UI paneli, AbuseIPDB/VirusTotal kaynak desteği
- **Olay Korelasyonu (Event Correlation):** Rule-based correlation engine — threshold ve frequency kural tipleri, zaman penceresi bazlı otomatik değerlendirme, heartbeat sırasında çalışır
- **MITRE ATT&CK Haritası:** 22 Sysmon Event ID → MITRE tactic/technique eşleme, heatmap görselleştirme, teknik bazlı analiz
- **Risk Bazlı Değerlendirme (RBA):** Cihaz başına kümülatif risk puanı, alert/korelasyon/tehdit bazlı puan artışı, zaman bazlı çürüme (decay), 4 seviyeli risk sınıflandırması (kritik/yüksek/orta/düşük)

### API Endpoint'leri (15 yeni)
- `GET/POST /api/rmm/threats` — Tehdit listesi ve ekleme
- `POST /api/rmm/threats/check` — Gösterge kontrol
- `DELETE /api/rmm/threats/<id>` — Gösterge silme
- `GET/POST /api/rmm/correlation/rules` — Korelasyon kuralları
- `PUT/DELETE /api/rmm/correlation/rules/<id>` — Kural güncelle/sil
- `GET /api/rmm/correlation/events` — Korelasyon olayları
- `GET /api/rmm/mitre/summary` — MITRE taktik özeti
- `GET /api/rmm/mitre/heatmap` — MITRE heatmap verisi
- `GET /api/rmm/risk` — Risk dashboard
- `GET /api/rmm/risk/<device_id>` — Cihaz risk detayı
- `POST /api/rmm/risk/decay` — Risk çürümesi uygula

### UI
- Sidebar'da yeni **SIEM** grup menüsü (4 alt sekme)
- Tehdit İstihbaratı paneli: gösterge ekleme, kontrol formu, liste
- Korelasyon paneli: kural oluşturma (frequency/threshold), kural listesi, olay görüntüleyici
- MITRE ATT&CK paneli: taktik heatmap, teknik tablosu
- Risk paneli: 4 seviyeli özet kartları, ilerleme çubuklu cihaz risk tablosu, çürüme butonu

### Demo Verileri
- 7 tehdit göstergesi (IP, domain, hash — AbuseIPDB/VirusTotal kaynakları)
- 3 korelasyon kuralı (CPU threshold, Disk frequency, RAM threshold)
- Otomatik risk puanı hesaplaması

## [1.12.0] — 2026-03-23

### Eklenen
- **RMM Alarm Sistemi:** CPU/RAM/Disk eşik tabanlı otomatik alarm üretimi
  - Heartbeat sırasında eşik kontrolü (warning + critical seviyeleri)
  - Alarm listesi, onaylama (acknowledge), yapılandırılabilir eşikler
  - Bekleme süresi (cooldown) ile tekrar eden alarm önleme
  - Dashboard'da kırmızı alarm banner'ı (aktif alarm sayısı)
  - Alarm eşikleri panelinden CPU/RAM/Disk uyarı ve kritik değerleri ayarlanabilir
- **Görev Sonuçları Görüntüleyici:** Tamamlanan görevlerin sonuçları UI'da görüntülenebilir
  - Sysmon Event Viewer — Sysmon olayları (Event ID, tip, zaman, detay) tablo formatında
  - Event Log Viewer — Windows Event Log kayıtları (seviye renkleriyle) tablo formatında
  - Sistem Bilgisi Viewer — Kategorilere ayrılmış donanım/yazılım bilgileri grid formatında
  - Shell/PowerShell çıktıları düz metin olarak gösterilir
  - JSON sonuçları otomatik pretty-print edilir
- **Donanım & Sistem Detayları:** Agent'dan gelen extra alanlar (cpu_name, cpu_cores, mem_total_gb, vb.) cihaz detayında gösterilir
- **Cihaz Sahiplik Ataması:** Her cihaza etiket (label) ve tenant ID atanabilir
  - Cihaz listesinde etiket sütunu
  - Cihaz detayında düzenlenebilir etiket ve tenant alanları
  - PUT /api/rmm/devices/<id> endpoint'i ile güncelleme
- **Yeni API Endpoint'leri:**
  - GET /api/rmm/alerts — Alarm listesi + istatistikler
  - PUT /api/rmm/alerts/<id>/ack — Alarm onaylama
  - GET /api/rmm/alert-config — Alarm yapılandırması okuma
  - POST /api/rmm/alert-config — Alarm yapılandırması kaydetme
  - PUT /api/rmm/devices/<id> — Cihaz etiket/tenant güncelleme
- **Demo Veri Zenginleştirme:**
  - Windows cihazlarda donanım bilgileri (cpu_name, cpu_cores, mem_total_gb vb.)
  - Demo görev sonuçları (sysinfo_collect, event_log, sysmon_collect)
  - Etiket atamaları ("Emre'nin PC'si", "Ana Sunucu" vb.)
  - Yüksek CPU/Disk değerleri ile otomatik alarm tetikleme

### Veritabanı
- alerts tablosu: device_id, alert_type, threshold, current_value, severity, acknowledged
- alert_config tablosu: cpu/ram/disk warning/critical eşikleri, enabled, cooldown

## [1.11.0] — 2026-03-23

### Değişiklik
- **Proje yeniden adlandırıldı:** EmareFirewall → **Emare Security OS**
- Tüm UI, CLI, agent, dokümantasyon ve nginx config yorumları güncellendi
- pyproject.toml: paket adı `emare-security-os`, CLI komutu `emare-security-os` (eski `emarefirewall` de çalışır)
- Python paket dizin adı (`emarefirewall`) geriye uyumluluk için korundu
- 5651 organizasyon varsayılanı "Emare Security OS" olarak güncellendi
- Sidebar brand: "Emare Security OS — Birleşik Güvenlik Platformu"
- Agent scriptleri (Windows/Linux/macOS): tüm branding güncellendi
- Nginx L7 koruma snippet'leri: `emarefirewall_*.conf` → `emare_security_*.conf`
- Firewall kural yorumları: `emarefirewall:` → `emare-security-os:`

## [1.10.4] — 2026-03-23

### Değişiklik
- **UI Sidebar Menü:** Yatay tab bar kaldırıldı, solda dikey sidebar menü eklendi
- 7 kategoriye gruplanmış 17 özellik: Genel Bakış, Güvenlik Duvarı, Koruma, Ağ, Kayıtlar, Yedekleme, Yönetim
- Collapsible (açılır/kapanır) grup başlıkları
- Mobil uyumlu: hamburger menü + overlay + otomatik kapanma
- Font Awesome ikonları tüm menü öğelerinde
- Kullanılmayan .fw-hero CSS kuralları temizlendi

### Düzeltme
- **Ping paket sayısı:** UI'dan count parametresi gönderilmiyordu (hep 4 paket) — düzeltildi
- **Ping sınırsız mod:** count=0 seçeneği → 1000 paket, max limit 10→10000'e yükseltildi
- **Ping sonuç formatı:** Raw JSON yerine formatlı istatistik kartları (Min/Ort/Maks RTT, kayıp oranı)
- **Traceroute/Whois çıktı hatası:** `d.output` → `d.data?.output` düzeltildi (raw JSON gösteriyordu)
- **Yüksek paket sayısı optimizasyonu:** count>20 ise `-i 0.2` interval ile hızlı ping

## [1.10.3] — 2026-03-23

### Kapsamlı Hata Düzeltme — Proje Denetimi
- **[DÜZELTME]** `_run_cmds` — 28 L7 koruma tipi komut hatalarını sessizce yutuyordu, artık hata döndürüyor
- **[DÜZELTME]** `_nginx_add_snippet` — `echo` yerine `tee` + heredoc; nginx `$` değişkenleri (`$binary_remote_addr`, `$http_user_agent` vb.) shell expansion'a uğrayıp bozuluyordu. 10 nginx tabanlı koruma (rate_limit, bad_bots, sql_injection, xss, path_traversal, method_filter, request_size, hsts, smuggling, gzip_bomb) etkileniyordu
- **[DÜZELTME]** `network_apply_rule` — CRUD metotları tuple döndürüyor ama `.get()` çağrılıyordu → AttributeError. Artık tuple/dict iki format da destekleniyor
- **[DÜZELTME]** `network_get_statuses` — `get_status()` dict'inde `success`/`firewall` key'leri yok, yanlış key'ler okunuyordu → her zaman boş döndürüyordu
- **[DÜZELTME]** `net_port_check` — Linux `/dev/tcp/` yolunda `_sq()` tek tırnak ekliyordu → yol bozuluyordu
- **[DÜZELTME]** ISP bulk operation — `fw.l7_enable_protection()` / `fw.l7_disable_protection()` metotları yoktu → `apply_l7_protection` / `remove_l7_protection` ile değiştirildi
- **[DÜZELTME]** ISP bulk `add_rule` — dict geçiliyordu ama metot ayrı parametreler bekliyor → parametreler açıldı
- **[DÜZELTME]** ISP bulk `delete_rule` — string geçiliyordu ama int bekleniyor → int'e dönüştürüldü
- **[DÜZELTME]** Frontend `fwL7Apply` — `{protection_type}` gönderiyordu ama route `{protections: []}` bekliyor → düzeltildi
- **[DÜZELTME]** Frontend `fwL7Remove` — `{protection_type}` gönderiyordu ama route `{protection}` bekliyor → düzeltildi
- **[DÜZELTME]** Frontend `fwNetDns` — `{target}` gönderiyordu ama route `{domain}` bekliyor → düzeltildi; yanıt `d.data` ile okunuyor
- **[GÜVENLİK]** Backup POST/DELETE endpoint'lerine CSRF kontrolü eklendi (3 endpoint)
- **[GÜVENLİK]** 9 GET endpoint'e `@perm_view` dekoratörü eklendi (routes, ip-addresses, arp, dhcp, ip-pools, queues, bridges, dns-static, neighbors)
- **[DÜZELTME]** app.py mock sıralama — `/emare system identity` ve `/emare system update check` catch-all'dan ÖNCEYE taşındı (dead code sorunu)
- **[DÜZELTME]** app.py mock — `update info` → `update check` komut ismi düzeltildi (manager.py ile uyumlu)
- **[DÜZELTME]** Linux mock'a `ss -tn` (top talkers) ve `ss -tlnp` (listening ports) pattern'ları eklendi

## [1.10.2] — 2026-03-23

### Linux/macOS Çapraz Platform Agent
- **[YENİ]** `agent/EmareAgent.sh` — Birleşik Linux/macOS derin izleme agentı (2002 satır, Bash 4.0+)
- **[YENİ]** 18 kategori derin telemetri: CPU (/proc/stat vs sysctl), RAM (/proc/meminfo vs vm_stat), Disk (df+iostat), Ağ (/proc/net+ss vs ifconfig+netstat), GPU (nvidia-smi+lspci / system_profiler), Güvenlik Linux (ufw/firewalld/iptables, ClamAV, SELinux, AppArmor, SSH config), Güvenlik macOS (PF firewall, SIP, Gatekeeper, FileVault, XProtect), Olay Günlüğü (journalctl / log show), Açık Portlar (ss/lsof + riskli port tespiti), Süreçler (ps aux top 25), Servisler (systemctl/launchctl), Yazılımlar (dpkg/rpm/pacman/brew), Oturumlar (w/who), Başlangıç (systemd+cron / LaunchDaemons+LaunchAgents+LoginItems), Sıcaklık (/sys/class/thermal / osx-cpu-temp), Batarya (/sys/class/power_supply / pmset), Audit Linux (auditd: EXECVE/OPEN/SOCKADDR/USER_AUTH/ANOM), Audit macOS (OpenBSM + Endpoint Security log show)
- **[YENİ]** `agent/install-emareagent.sh` — Çapraz platform installer (296 satır): Linux=systemd unit (güvenlik sertelleştirmeli), macOS=LaunchDaemon plist
- **[YENİ]** 12 görev tipi desteği: shell_exec, script_exec, sysinfo_collect, config_query, event_log, audit_collect/sysmon_collect, restart_service, install_software, uninstall_software, file_collect, update_agent, custom
- **[YENİ]** macOS `log show` komutlarına 10s timeout (run_with_timeout helper — gtimeout/timeout/background+kill fallback)
- **[YENİ]** JSON yardımcıları (json_obj, json_escape, json_arr) — jq bağımlılığı yok, pure bash
- **[DÜZELTME]** `set -euo pipefail` → `set -eo pipefail` (macOS bash 3.2 boş array uyumsuzluğu)
- **[DÜZELTME]** `grep -c || echo 0` double-output bugı (0 match’te `0\n0` üretiyordu)
- **[DÜZELTME]** `log_msg` stdout kirliliği (tüm log çıktısı stderr’e yönlendirildi)
- **[YENİ]** `agent/Kur-EmareAgent.command` — macOS/Linux tıkla-çalıştır kurulum (Finder'da çift tıkla)
- **[YENİ]** `agent/Kur-EmareAgent.bat` — Windows tıkla-çalıştır kurulum (çift tıkla, otomatik yönetici yetkisi)
- **[DÜZELTME]** Non-root LOG_FILE + AGENT_DIR izin sorunu (/tmp ve ~/.emare-agent fallback)\n- **[DÜZELTME]** `grep -oP` macOS uyumsuzluğu (BSD grep'te -P yok → sed ile değiştirildi)
- **[GÜNCELLEME]** `agent/README.md` çapraz platform dokümantasyonu (platform karşılaştırma tablosu, kurulum talimatları)

## [1.10.1] — 2026-03-23

### Sysmon Tam Entegrasyon
- **[YENİ]** `Get-SysmonData` — 29 Sysmon Event ID’nin tamamını toplayan collector (ProcessCreate, NetworkConnect, DnsQuery, RegistryOps, CreateRemoteThread, ProcessAccess, ProcessTampering, DriverLoad, ImageLoad, FileCreate/Delete, WMI, Pipe, ClipboardChange, FileBlock…)
- **[YENİ]** `Get-SysmonStatus` — Sysmon servis/driver/versiyon durumu kontrolü
- **[YENİ]** `Parse-SysmonEvent` — Her Event ID için XML’den yapısal JSON parse (commandline, hash, src/dst IP, pipe name, registry path vb.)
- **[YENİ]** Tehdit uyarı sistemi: CreateRemoteThread (ID 8), ProcessAccess (ID 10), ProcessTampering (ID 25) otomatik HIGH uyarı; yüksek hacimli NetworkConnect/DnsQuery MEDIUM uyarı
- **[YENİ]** `sysmon_collect` görev tipi — Uzaktan Sysmon verisi toplama (saat, kategori başı limit, Event ID filtresi)
- **[GÜNCELLEME]** Derin telemetri 17→18 kategori (sysmon eklendi, her 5dk’da otomatik)
- **[GÜNCELLEME]** `rmm.py` VALID_TASK_TYPES’a `sysmon_collect` eklendi

## [1.10.0] — 2026-03-23

### Windows Deep Monitoring Agent
- **[YENİ]** `agent/EmareAgent.ps1` — Tam teşekküllü Windows RMM agent'ı (1174 satır, PowerShell 5.1+)
- **[YENİ]** 17 kategori derin telemetri: CPU (çekirdek/thread/mimari/saat hızı), RAM (sayfa dosyası dahil), Disk (I/O, IOPS, kuyruk), Ağ (arayüzler/DNS/TCP bağlantıları), GPU (NVIDIA nvidia-smi + WMI fallback), Güvenlik (firewall profilleri, antivirüs, Windows Update, yerel kullanıcılar, paylaşımlar, RDP, UAC), Olay Günlüğü (System/Security/Application son 24s), Açık Portlar (riskli port tespiti: 21,23,445,3389...), Süreçler (top 25), Servisler (kritik servis izleme), Yazılımlar (registry tabanlı envanter), Oturumlar (RDP dahil), Başlangıç (Run keys + scheduled tasks), Sıcaklık (WMI thermal + nvidia-smi), Batarya
- **[YENİ]** 3 katmanlı zamanlama: heartbeat (60s temel metrikler), görev kontrolü (30s polling), derin telemetri (5dk tüm katmanlar)
- **[YENİ]** 11 görev tipi yürütücü: shell_exec, powershell_exec, sysinfo_collect, registry_query, event_log, restart_service, install_software, uninstall_software, file_collect (base64, max 5MB), update_agent, custom
- **[YENİ]** `agent/Install-EmareAgent.ps1` — Tek komutla kurulum scripti (Windows Scheduled Task olarak SYSTEM hesabıyla)
- **[YENİ]** Agent yönetim komutları: Install/Uninstall/Status/Start/Stop/Restart
- **[YENİ]** Tek seferlik derin tarama modu: `EmareAgent.ps1 -DeepScan` → masaüstüne JSON rapor
- **[GÜVENLİK]** Agent key dosya tabanlı saklama (`%ProgramData%\EmareAgent`), log rotasyonu (max 10MB), TLS 1.2 zorunlu

## [1.9.2] — 2026-03-23

### Dashboard Görsel İyileştirmeler + Sunucu Seçimi
- **[UI]** Dashboard grafik kartları yeniden tasarlandı — gradient arka plan, üst kenar renk şeridi, hover efekti (translateY + box-shadow)
- **[UI]** KPI kartları geliştirildi — Font Awesome ikonlar, gradient alt şerit, hover animasyonu
- **[UI]** Chart.js konfigürasyonu premium seviyeye çıkarıldı — gradient fill (line/bar), rounded bar (borderRadius:6), doughnut cutout %62, custom tooltip (dark glass), usePointStyle legend, point styling
- **[UI]** Trafik grafiği tam genişlik (grid-column: 1/-1) yapıldı
- **[UI]** Emoji başlıklar Font Awesome ikonlu badge'lerle değiştirildi (10 grafik kartı)
- **[UI]** Bar grafiklerde her sütun farklı renk paleti (Top IPs, Top Paths)
- **[DÜZELTME]** Sunucu seçimi boş geliyordu — Emare OS varsayılan sunucu olarak otomatik seçili yapıldı (`server_id: emare-os`)
- **[DÜZELTME]** Sayfa açılışında otomatik `fwRefresh()` çağrısı eklendi — artık seçim yapmaya gerek yok

## [1.9.1] — 2026-03-23

### Emare OS Tam Platform Paritesi — Zone Yönetimi, Saldırı Tespit, Geo-Block
- **[YENİ]** Emare OS Zone Yönetimi — `get_zones()`, `set_default_zone()`, `get_zone_detail()` Emare OS desteği (4 zone: lan/wan/dmz/guest, interface atama, servis/port/masquerade/forward-ports/rich-rules detay)
- **[YENİ]** Emare OS Saldırı Tespit (Fail2ban muadili) — `/emare system intrusion-detection` ile 3 jail (ssh/web/dns), ban/unban, ban listesi, istatistikler
- **[YENİ]** Emare OS Geo-Block — ülke bazı IP engelleme `/emare firewall geo-block` + blocklist entegrasyonu, CIDR yükleme, drop kuralı otomasyonu
- **[YENİ]** `geo_unblock_country()` metodu — ülke engelini kaldırma (Emare OS + firewalld)
- **[YENİ]** `get_geo_blocked()` metodu — engelli ülke listesi (Emare OS + firewalld)
- **[YENİ]** `GET/DELETE /api/servers/<id>/firewall/geo-block` endpoint’leri — geo-block listeleme ve kaldırma
- **[YENİ]** Emare OS Rich Rule desteği — `add_rich_rule()` / `remove_rich_rule()` Emare OS dalı
- **[UI]** Geo-block paneli geliştirildi — engelli ülke listesi, unblock butonları, 8 ülke seçeneği
- **[MOCK]** 5 yeni Emare OS mock veri seti: zones (4 zone + detaylar), intrusion-detection (3 jail + banned IPs), geo-block (2 ülke)
- **[DÜZELTME]** app.py mock komut sıralaması düzeltildi — `/emare system intrusion-detection` komutları generic `/emare system` öncesine taşındı

## [1.9.0] — 2026-03-23

### RMM + ITSM Modülü (Remote Monitoring & Management + IT Service Management)
- **[YENİ]** `rmm.py` — Bağımsız RMM+ITSM motoru (SQLite, ~350 satır, sıfır dış bağımlılık)
- **[YENİ]** Agent iletişim protokolü — HTTP JSON API, `X-Agent-Key` header auth, polling model
- **[YENİ]** Cihaz yönetimi — kayıt, heartbeat, otomatik online/offline durum takibi
- **[YENİ]** Metrik toplama — CPU, RAM, Disk, Network I/O zaman serisi (SQLite)
- **[YENİ]** Görev yönetimi — 11 görev tipi (shell_exec, powershell_exec, file_collect, registry_query, event_log, sysinfo_collect, install/uninstall_software, restart_service, update_agent, custom)
- **[YENİ]** ITSM ticket sistemi — öncelik (critical/high/medium/low), durum (open/in_progress/resolved/closed), kategori (general/incident/request/change/problem), not geçmişi
- **[YENİ]** RMM Dashboard — cihaz özeti, OS dağılımı, bekleyen görevler, ticket istatistikleri
- **[YENİ]** 15+ yeni API endpoint (agent register/heartbeat/tasks, device CRUD, ticket CRUD)
- **[YENİ]** RMM + ITSM UI tabları — cihaz grid'i (CPU/RAM/Disk bar), metrik grafiği (Chart.js), görev gönderme, ticket oluşturma/güncelleme
- **[YENİ]** Symon Windows Agent uyumluluğu — platform bağımsız HTTP API, PowerShell görev desteği
- **[GÜVENLİK]** Agent key format: `eak_` prefix + token_hex(24), tüm SQL parametrize, input uzunluk limitleri

## [1.8.2] — 2026-03-23

### Derin Güvenlik Denetimi — 3. Tur (Deep Security Audit Round 3)
- **[KRİTİK]** Heredoc injection düzeltildi — `backup_firewall()` ve `restore_firewall()` içindeki sabit EOF marker'lar `secrets.token_hex(16)` ile rastgele üretiliyor, içerik sanitize ediliyor
- **[YÜKSEK]** Negatif limit DoS düzeltildi — tüm `limit` parametreleri `max(1, min(value, üst_sınır))` ile korunuyor (8 endpoint)
- **[YÜKSEK]** Zone detay XSS düzeltildi — `det.services/ports/interfaces/rich_rules` dizileri `esc()` ile escape ediliyor
- **[YÜKSEK]** Tenant ID XSS düzeltildi — `t.id` innerHTML ve onclick'te `esc()` / `escAttr()` ile korunuyor
- **[ORTA]** Network ID XSS düzeltildi — `n.id` onclick handler'larında `escAttr()` ile escape, DNS listesi `esc()` ile korunuyor
- **[ORTA]** TSA sertifika doğrulama eklendi — `law5651.py` urlopen'a `ssl.create_default_context()` ile SSL doğrulama
- **[DÜŞÜK]** SQLite bağlantı temizliği — `SQLiteBackend.close()` metodu eklendi

## [1.8.1] — 2026-03-23

### Güvenlik Sertleştirme (Security Hardening)
- **[KRİTİK]** XSS açığı kapatıldı — tüm onclick handler'larında `escAttr()` ile attribute-safe escape
- **[YÜKSEK]** Güvenlik response header'ları eklendi (X-Frame-Options: DENY, CSP, nosniff, Referrer-Policy, Permissions-Policy, HSTS)
- **[ORTA]** Session cookie güvenliği: HttpOnly, SameSite=Strict, Secure (HTTPS'te)
- **[KRITIK]** `debug=True` kaldırıldı — `config.DEBUG` (env: `EMARE_DEBUG=1`) üzerinden kontrol ediliyor
- **[KRITIK]** Rate limiting varsayılan olarak aktif (30/dk) — `config.RATE_LIMIT_PER_MINUTE`
- **[YÜKSEK]** `SECRET_KEY` artık `secrets.token_hex(32)` ile otomatik üretiliyor (env yoksa)
- **[YÜKSEK]** SSH varsayılan `host_key_policy` `'warning'` → `'reject'` olarak değiştirildi (MITM koruması)
- **[YÜKSEK]** PostgreSQL varsayılan şifresi kaldırıldı — `EMARE_POSTGRES_URL` env var zorunlu
- **[YÜKSEK]** ISP admin key boş bırakılamaz — otomatik `secrets.token_hex(24)` üretiliyor
- **[ORTA]** CSRF koruması güçlendirildi — token bazlı doğrulama eklendi (`/api/firewall/csrf-token`)
- **[ORTA]** Health endpoint bilgi sızıntısı kapatıldı — sadece `{"status":"healthy"}` döndürüyor

### Eklenen
- `GET /api/firewall/csrf-token` — CSRF token üretim endpoint'i
- Font Awesome 6.5.1 ve Chart.js 4.4.7 lokal bundle — dış CDN bağımlılığı sıfırlandı

## [1.8.0] — 2026-03-22

### Eklenen
- **Çoklu Ağ Yönetimi (Multi-Network Management)** — Birden fazla sunucuyu tek ağ altında gruplama ve toplu yönetim
  - Ağ oluşturma, düzenleme, silme (CRUD)
  - Üye sunucu ekleme/çıkarma
  - DNS sunucu yapılandırması (ağ bazlı)
  - Toplu kural uygulama (add_rule, delete_rule, block_ip, unblock_ip, port_forward)
  - Üye durum sorgulama (statuses)
  - Senkronizasyon kontrolü (common_rules, diverged_rules, sync_status)
  - manager.py: 3 yeni metot (network_apply_rule, network_get_statuses, network_sync_check)
  - routes.py: 11 yeni endpoint (/api/networks/*)
  - UI: Ağ Yönetimi paneli — kart grid, detay görünümü, DNS ayarları, bulk işlem

### Düzeltilen
- `api_network_statuses` endpoint'indeki `jsonify()` çift `success` parametresi hatası düzeltildi
- firewall.html tüm özelliklerle yeniden inşa edildi (1195 satır)

## [1.7.0] — 2026-03-22

### Eklenen
- **Gelişmiş Analitik Dashboard** — Chart.js 4.4.7 ile 10 interaktif grafik
  - **Anlık Trafik Grafiği** — Son 60 ölçüm, otomatik yenileme (5s/10s/30s/1dk), 3 seri (İstekler, Engellenen, L7)
  - **HTTP Metot Dağılımı** — Doughnut grafik (GET/POST/DELETE/PUT)
  - **Durum Kodu Dağılımı** — Yatay bar grafik (HTTP 200, 201, 400, vb.)
  - **Önem Seviyeleri** — Polar area grafik (INFO/WARNING/ERROR/CRITICAL)
  - **L7 Saldırı Tipleri** — Radar grafik (BOGUS_TCP, CONNLIMIT, HTTP_FLOOD, vb.)
  - **Saatlik İstek Dağılımı** — 24 saatlik bar grafik, yoğunluk renklendirmesi
  - **En Aktif IP'ler** — Top 10 IP yatay bar grafik
  - **En Çok Erişilen Yollar** — Top 10 path yatay bar grafik
  - **Kategori Dağılımı** — Tüm log kategorileri bar grafik
  - **IP Risk Analizi Tablosu** — Risk skoru görsel bar, metot badge'leri, tarih bilgisi
- **6 KPI Kartı** — Toplam İstek, Engellenen, L7 Saldırı, Toplam Log, Hata, Uyarı (oran hesaplı)
- **Canlı Mod** — Yeşil pulse göstergesi, seçilebilir yenileme aralığı (Manuel/5s/10s/30s/1dk)
- **Dark Theme Uyumlu Grafikler** — Tüm Chart.js grafikleri koyu tema renk paletine uyumlu
- **Responsive Tasarım** — Mobil uyumlu 2-sütun grid, tek sütun daraltma

## [1.6.1] — 2026-03-22

### Eklenen
- **5651 API Endpoint'leri** — 3 yeni endpoint
  - `GET /api/firewall/logs/5651/status` — Damgalama durumu (enabled, dry_run, chain_index, total_stamped)
  - `GET /api/firewall/logs/5651/verify` — Zincir doğrulama (ok, verified, broken_at)
  - `POST /api/firewall/logs/5651/seal` — Manuel mühürleme (note parametresi ile)
- **5651 UI Tabı** — Tam işlevsel arayüz
  - 6 durum kartı (Damgalama, TSA Modu, Damgalı Kayıt, Zincir Uzunluğu, Organizasyon, Son Damga)
  - Zincir Doğrula butonu — görsel doğrulama sonucu (geçerli/bozuk, kontrol sayısı, ilk hata)
  - Manuel Mühürle butonu — not ile mühürleme
  - Detay tablosu (Son Zincir Hash, TSA URL, Damga Sıklığı)

### Düzeltilen
- TASK.md'deki `_rate_limit_check()` yanlış fonksiyon adı → doğrusu `_rate_limited()`

### Test
- 136/136 test başarılı (5651 testleri dahil)

## [1.6.0] — 2026-03-22

### Eklenen
- **Loglar Tabı** — Tam teşekküllü log görüntüleyici
  - İstatistik kartları (toplam log, hata, uyarı, tekil IP, istek sayısı)
  - Seviye/arama/limit filtreli log tablosu, sayfalaması ile
  - L7 saldirı özeti (lazy-load expandable)
  - IP analizi (risk skoru, istek oranı, engelleme butonu)
  - Veritabanı bilgisi (backend, saklama süresi, kayıt sayıları, 5651 durumu)
  - Log dışa aktarma (JSON) ve temizleme
- **ISP Yönetim Tabı** — Kapsamlı ISP yönetim paneli
  - Dashboard: 6 özet kartı (tenant, sunucu, alarm, denetim, CGNAT, IPAM)
  - Tenant CRUD: oluşturma formu, liste, detay paneli
  - Tenant detay: e-posta, API key, sunucu yönetimi, webhook yönetimi
  - API key yenileme (regenerate)
  - Alarmlar: tüm tenant'lardan alarm toplama, onaylama
  - CGNAT: havuz oluşturma/listeleme, tahsis/serbest bırakma, eşleme görüntüleme
  - IPAM: blok oluşturma/silme, IP atama/serbest bırakma, atama listesi
  - Denetim logu: zaman, tenant, işlem, kaynak, IP detaylı tablo
- **Hız Testi** — Ağ Analizi tabına eklenen yeni araç
  - Indirme/yükleme/her ikisi yön seçimi
  - Sonuç: indirme/yükleme hızı, gecikme, jitter
- **fwGlobalApi()** — Sunucu bağımsız API fonksiyonu (log + ISP endpoint'leri için)

## [1.5.1] — 2026-03-22

### Eklenen
- 5651 zaman damgasi baslatma akisi `app.py` icinde aktif edildi
  - `TubitakTimestampClient` ortam degiskenleriyle kurulur: `TSA_URL`, `TSA_USERNAME`, `TSA_PASSWORD`
  - `TSA_URL` tanimli degilse `dry_run=True` ile hash-zinciri kesintisiz calisir
  - `Law5651Stamper` store katmanina `set_5651_stamper(...)` ile baglandi

### Notlar
- 5651 API endpoint'leri `routes.py` icinde mevcuttur: durum, dogrulama ve manuel muhurleme

## [1.5.0] — 2026-03-22

### Eklenen
- **ISP Multi-Tenant sistemi** — `tenants.py` modülü (950+ satır)
  - Tenant CRUD (oluştur, listele, güncelle, sil)
  - API key üretimi (SHA-256 hash, kriptografik güvenli)
  - API key ile tenant doğrulama
  - Plan bazlı kota yönetimi (bronze/silver/gold/enterprise)
  - Sunucu tahsisi ve kota kontrolü
  - Audit trail (değişmez loglama)
- **Webhook sistemi** — Event-driven bildirimler
  - HMAC-SHA256 imzalı webhook tetikleme
  - Exponential backoff ile retry (3 deneme)
  - Auto-disable (10 ardışık hata sonrası)
  - 8 event tipi (rule_change, ip_blocked, ddos_detected, backup_created, l7_alert, connections_high, scan_complete, tenant_update)
- **Alert sistemi** — Tenant bazlı uyarılar
  - Alert oluşturma (tip, severity, server_id)
  - Acknowledge (okundu işaretleme)
- **Zamanlanmış görevler** — Cron tabanlı planlama
  - 6 görev tipi (backup, security_scan, l7_scan, rule_apply, rule_remove, log_cleanup)
  - 5 alanlı cron ifadesi desteği
- **Bulk işlemler** — Toplu kural yönetimi
  - Arka plan thread'de asenkron çalıştırma
  - 6 operasyon: rule_add, rule_delete, ip_block, ip_unblock, l7_enable, l7_disable
  - Job durumu takibi ve geçmiş
- **CGNAT yönetimi** — ISP ölçekli NAT
  - Havuz oluşturma (public IP, port aralığı, abone başına port)
  - Deterministik port bloğu tahsisi
  - Tahsis serbest bırakma
  - Kapasite takibi
- **IPAM (IP Adres Yönetimi)**
  - IP blok ekleme (CIDR, VLAN, gateway)
  - IP tahsisi (MAC adresi, atanan kişi, not)
  - IP serbest bırakma
- **ISP Dashboard** — Genel ve tenant bazlı raporlama
  - Toplam tenant, sunucu, alert, job sayıları
  - Plan dağılımı
  - Son 24 saat audit log sayısı
  - CGNAT ve IPAM istatistikleri
  - Tenant raporu (kota kullanımı yüzdeleri)
- **Batch import/export** — Kural toplu dışa/içe aktarım
  - Sunucu kurallarını JSON olarak dışa aktar
  - JSON kural listesi toplu içe aktar
- **26 yeni ISP API endpoint'i** — `/api/isp/` prefix altında
- **Redis circuit breaker** — cache.py'de otomatik fallback
  - 5 ardışık hata → DictCache'e otomatik geçiş
  - 30 saniye sonra half-open → tekrar Redis dene
  - Hem set hem get'te çift yazma (DictCache + Redis)
- **DictTenantStore** — Standalone/demo mod için in-memory tenant store

### Değiştirilen
- `config.py` — ISP tenant ayarları eklendi (TENANT_MODE, ALERT_WEBHOOK_URL, SCHEDULER_ENABLED, ISP_ADMIN_KEY)
- `cache.py` — RedisCache circuit breaker ve DictCache fallback eklendi
- `routes.py` — `create_blueprint()` tenant_store ve webhook_dispatcher parametreleri eklendi
- `app.py` — TenantStore ve WebhookDispatcher entegrasyonu
- `__init__.py` — TenantStore, DictTenantStore, WebhookDispatcher export'ları eklendi
- `Dockerfile` — tenants.py ve law5651.py COPY satırına eklendi
- Test sayısı: 110 → 136 (26 yeni ISP testi)

## [1.4.1] — 2026-03-22

### Düzeltilen
- **Health Version**: Hardcoded `1.3.0` yerine `__version__` kullanılarak dinamik versiyon gösterimi
- **Add Rule EO**: `_VALID_ACTIONS`'a `accept` ve `drop` eklendi — Emare OS'un kullandığı action'lar artık validation'dan geçiyor
- **Port Forward EO/UF**: Test'teki parametre isimleri API ile uyumlu hale getirildi (`src_port` → `port`, `dst_port` → `to_port`, `dst_ip` → `to_addr`)
- **Set DNS EO**: Test'teki parametre ismi düzeltildi (`primary/secondary` → `servers`)
- **Get Routes + 7 endpoint**: List dönen endpoint'ler `{'success': True, ...}` dict formatına sarıldı (routes, ip-addresses, arp, ip-pools, queues, bridges, dns-static, neighbors)
- **Rate Limiter**: Demo/test `app.py`'de rate limit 0 (sınırsız) yapıldı — 84 test sorunsuz çalışıyor
- **Test hata mesajı**: `d.get("error")` → `d.get("message")` ile gerçek hata mesajları görüntüleniyor
- **Test kapsamı**: 110 endpoint testi — 110/110 başarılı (Emare OS + UFW)

## [1.4.0] — 2026-03-22

### Eklenen
- **Network Analyser modülü** — 11 ağ analiz aracı
  - `net_bandwidth` — Interface trafik istatistikleri
  - `net_ping` — RTT ölçümü ile ping testi
  - `net_traceroute` — Hop-by-hop rota izleme
  - `net_dns_lookup` — DNS sorgusu (A/AAAA/MX/NS/TXT/CNAME/SOA/PTR/SRV)
  - `net_port_check` — TCP/UDP port erişilebilirlik testi
  - `net_top_talkers` — En aktif IP'ler
  - `net_listening_ports` — Dinleyen port ve servisler
  - `net_packet_capture` — tcpdump/packet-sniffer snapshot
  - `net_speed_test` — iperf3 tabanlı hız testi
  - `net_whois` — WHOIS sorgusu
  - `net_summary` — Ağ analiz dashboard özeti
- 10 yeni API endpoint (`/api/servers/<id>/network/`)
- "Ağ Analizi" UI tab'ı — ping, traceroute, DNS, port kontrol, WHOIS, paket yakalama

### Değiştirilen
- `_exec_multi` SEP fallback mekanizması iyileştirildi
- Mock executor'a tüm network komut yanıtları eklendi

## [1.3.0] — 2026-03-21

### Eklenen
- 12 yeni L7 koruma tipi (toplam 28)
- Birleşik çok katmanlı koruma tab'ı
- Multi-layer UI tab yapısı
- Docker demo kurulumu ve mock SSH executor
- MikroTik → Emare OS tam isim değişikliği
- Bağımsız Emare OS CLI mimarisi (205+ komut)

## [1.2.0] — 2026-03-20

### Eklenen
- Backup/restore sistemi
- SQLite persistence katmanı
- Health check endpoint
- ISP-scale mimari (Redis, PostgreSQL, Gunicorn)
- `config.py` — env-driven yapılandırma
- `cache.py` — DictCache/RedisCache soyutlama
- `store.py` — LogStore + SQLite/PostgreSQL backend
- SSH connection pool (Semaphore)
- Docker ISP profili (3 konteyner)
- Performans optimizasyonu (WAL, gzip, batch writes, TTL cache)

## [1.1.0] — 2026-03-19

### Eklenen
- L7 protection engine (ilk 16 tip)
- Monitoring dashboard
- Logging sistemi
- MikroTik RouterOS entegrasyonu
- Güvenlik taraması
- Bağlantı istatistikleri

## [1.0.0] — 2026-03-18

### Eklenen
- İlk sürüm
- UFW ve firewalld desteği
- Kural yönetimi (CRUD)
- IP engelleme/çözme
- Port yönlendirme
- Zone yönetimi
- Fail2ban entegrasyonu
- CLI arayüzü (22 komut)
- Web UI (Flask + Jinja2)
