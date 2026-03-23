# Emare Security OS RMM Agent — Çapraz Platform (Windows / Linux / macOS)

Emare Cloud uzaktan izleme ve yönetim agent'ı. Tüm platformlarda 18 kategori derin telemetri.

## Özellikler

| Kategori | Toplanan Veri |
|---|---|
| **CPU** | Kullanım %, çekirdek/thread sayısı, mimari, saat hızı |
| **RAM** | Kullanım %, toplam/kullanılan/boş GB, sayfa dosyası |
| **Disk** | Her sürücü (kullanım, dosya sistemi), Disk I/O (read/write/IOPS/queue) |
| **Ağ** | Arayüz listesi (MAC, hız, IP, rx/tx), DNS, TCP bağlantı durumları |
| **GPU** | NVIDIA (sıcaklık, kullanım, VRAM, fan, güç) + WMI fallback |
| **Güvenlik** | Firewall profilleri, antivirüs, Windows Update, yerel kullanıcılar, paylaşımlar, RDP, UAC |
| **Olay Günlüğü** | System/Security/Application – son 24 saat hata/uyarı/kritik, oturum olayları |
| **Sysmon** | 29 Event ID (ProcessCreate, NetworkConnect, DnsQuery, FileCreate, RegistryOps, CreateRemoteThread, ProcessAccess, ProcessTampering, DriverLoad, ImageLoad, WMI, PipeOps, ClipboardChange, FileDelete, FileBlock...), tehdit uyarıları, istatistik özeti |
| **Açık Portlar** | TCP/UDP dinleyiciler, riskli port tespiti (21,23,445,3389...) |
| **Süreçler** | Top 25 (CPU/RAM), toplam süreç sayısı |
| **Servisler** | Tüm servisler, kritik servis durumu (WinDefend, EventLog, RpcSs...) |
| **Yazılımlar** | Yüklü yazılım listesi (ad, sürüm, yayıncı, boyut) |
| **Oturumlar** | Aktif kullanıcı oturumları (RDP dahil) |
| **Başlangıç** | Registry Run key'leri, zamanlanmış görevler |
| **Sıcaklık** | WMI thermal zone, NVIDIA GPU sıcaklığı |
| **Batarya** | Şarj %, durum, kalan süre |

## Platform Desteği

| Özellik | Windows | Linux | macOS |
|---|---|---|---|
| CPU (kullanım, çekirdek, model) | WMI/CIM | `/proc/stat`, `/proc/cpuinfo` | `sysctl`, `ps` |
| RAM (kullanım, swap) | WMI | `/proc/meminfo` | `vm_stat`, `sysctl` |
| Disk (I/O, hacim) | WMI, PerfCounter | `df`, `iostat` | `df`, `iostat` |
| Ağ (arayüz, TCP, DNS) | NetAdapter | `/proc/net`, `ss`, `ip` | `ifconfig`, `netstat` |
| GPU | nvidia-smi + WMI | nvidia-smi + lspci | nvidia-smi + system_profiler |
| Güvenlik | Firewall+AV+UAC+RDP | ufw/firewalld/SELinux/AppArmor | PF + SIP + Gatekeeper + FileVault + XProtect |
| Olay Günlüğü | Get-WinEvent (3 log) | journalctl | `log show` |
| Audit/Sysmon | Sysmon 29 Event ID | auditd (ausearch) | OpenBSM + ESF |
| Yazılımlar | Registry | dpkg/rpm/pacman | brew + /Applications |
| Servisler | Get-Service | systemctl | launchctl |
| Başlangıç | Run keys + Tasks | systemd enable + cron + init.d | LaunchDaemons + LaunchAgents + LoginItems |
| Sıcaklık | WMI thermal + nvidia | /sys/class/thermal + lm-sensors | osx-cpu-temp + nvidia |
| Batarya | WMI Win32_Battery | /sys/class/power_supply | pmset |

---

## Windows Kurulum

### Tıkla Çalıştır (Önerilen)

`Kur-EmareAgent.bat` dosyasına çift tıklayın. Yönetici yetkisi otomatik istenir,
sunucu adresi sorulur, agent kurulup başlatılır.

### PowerShell ile kurulum (Yönetici PowerShell)

```powershell
.\Install-EmareAgent.ps1 -ServerUrl "https://firewall.example.com" -Action Install
```

### 2. Manuel çalıştırma (test için)

```powershell
.\EmareAgent.ps1 -Server "https://firewall.example.com"
```

### 3. Tek seferlik derin tarama

```powershell
.\EmareAgent.ps1 -DeepScan
# Sonuç: %USERPROFILE%\Desktop\EmareDeepScan.json
```

## Yönetim

```powershell
# Durum kontrolü
.\Install-EmareAgent.ps1 -ServerUrl "..." -Action Status

# Durdur
.\Install-EmareAgent.ps1 -ServerUrl "..." -Action Stop

# Yeniden başlat
.\Install-EmareAgent.ps1 -ServerUrl "..." -Action Restart

# Kaldır
.\Install-EmareAgent.ps1 -ServerUrl "..." -Action Uninstall
```

## Zamanlama

| İşlem | Aralık | Açıklama |
|---|---|---|
| Heartbeat | 60 saniye | CPU, RAM, Disk, Network temel metrikleri |
| Görev Kontrolü | 30 saniye | Bekleyen görevleri çek ve çalıştır |
| Derin Telemetri | 5 dakika | 18 kategoride tüm veriler (Sysmon dahil, ekstra alanında) |

## Desteklenen Görev Tipleri (Tüm Platformlar)

| Tip | Parametre | Açıklama |
|---|---|---|
| `shell_exec` | `{"cmd": "ipconfig /all"}` | CMD komutu çalıştır |
| `powershell_exec` | `{"script": "Get-Service \| ConvertTo-Json"}` | PowerShell scripti |
| `sysinfo_collect` | `{}` | 17 kategoride derin tarama |
| `registry_query` | `{"path": "HKLM:\\SOFTWARE\\..."}` | Registry sorgusu |
| `event_log` | `{"log": "Security", "max_events": 50}` | Olay günlüğü dışa aktar |
| `sysmon_collect` | `{"hours": 1, "max_per_category": 50, "event_ids": [1,3,22]}` | Sysmon verisi topla (29 Event ID) |
| `restart_service` | `{"service": "wuauserv"}` | Servis yeniden başlat |
| `install_software` | `{"url": "https://...", "args": "/S"}` | Yazılım kur |
| `uninstall_software` | `{"name": "Software Name"}` | Yazılım kaldır |
| `file_collect` | `{"path": "C:\\Logs\\app.log"}` | Dosya topla (max 5MB, base64) |
| `update_agent` | `{"url": "..."}` | Agent güncelle |
| `custom` | `{"script": "..."}` | Özel PowerShell/Bash |

## Dosya Konumları

### Windows
| Dosya | Konum |
|---|---|
| Agent scripti | `%ProgramData%\EmareAgent\EmareAgent.ps1` |
| Yapılandırma | `%ProgramData%\EmareAgent\config.json` |
| Agent key | `%ProgramData%\EmareAgent\agent.key` |
| Log dosyası | `%ProgramData%\EmareAgent\agent.log` |

### Linux / macOS
| Dosya | Konum |
|---|---|
| Agent scripti | `/var/lib/emare-agent/EmareAgent.sh` |
| Yapılandırma | `/var/lib/emare-agent/config.json` |
| Agent key | `/var/lib/emare-agent/agent.key` |
| Log dosyası | `/var/log/emare-agent.log` |
| Systemd unit | `/etc/systemd/system/emare-agent.service` (Linux) |
| LaunchDaemon | `/Library/LaunchDaemons/com.emare.agent.plist` (macOS) |

## Linux / macOS Kurulum

### Tıkla Çalıştır (macOS — Önerilen)

`Kur-EmareAgent.command` dosyasına Finder'da çift tıklayın. Terminal otomatik açılır,
sunucu adresi sorulur, yönetici parolası istenir, agent kurulup başlatılır.

### Tek komutla kurulum (root)

```bash
sudo ./install-emareagent.sh --server https://firewall.example.com --action install
```

### Manuel çalıştırma (test için)

```bash
sudo ./EmareAgent.sh -s https://firewall.example.com
```

### Tek seferlik derin tarama

```bash
./EmareAgent.sh --deep-scan
# Sonuç: ~/EmareDeepScan.json
```

### Linux / macOS Yönetim

```bash
# Durum kontrolü
sudo ./install-emareagent.sh --action status

# Durdur
sudo ./install-emareagent.sh --action stop

# Yeniden başlat
sudo ./install-emareagent.sh --action restart

# Kaldır
sudo ./install-emareagent.sh --action uninstall
```

## Gereksinimler

### Windows
- Windows 10/11 veya Windows Server 2016+
- PowerShell 5.1+
- Yönetici hakları (kurulum için)
- Sunucuya HTTP/HTTPS erişimi

### Linux
- Bash 4.0+, curl
- systemd (kurulum için)
- Desteklenen dağıtımlar: Ubuntu 18+, Debian 10+, CentOS 7+, RHEL 7+, Fedora, Arch
- `python3` (görev parse için önerilir)
- root hakları (kurulum ve bazı veri toplama için)

### macOS
- macOS 10.15+ (Catalina+)
- Bash/Zsh, curl
- root hakları (kurulum için)
- `python3` (varsayılan olarak mevcut)

## Güvenlik

- Agent key (`eak_...`) her cihaza özel, sunucu tarafında oluşturulur
- Tüm iletişim HTTPS üzerinden
- Kimlik bilgisi saklanmaz — sadece token
- Log rotasyonu (max 10MB)
- Key dosyası `%ProgramData%` altında korunur
