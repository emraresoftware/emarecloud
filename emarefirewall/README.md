# �️ Emare Security OS — Birleşik Güvenlik Platformu

**Versiyon:** 1.11.0  
**Lisans:** Emare Collective  
**Uyumluluk:** Python 3.8+, UFW (Ubuntu/Debian), firewalld (RHEL/CentOS/AlmaLinux), Emare OS

---

## 📦 Ne İçerir?

| Dosya | Açıklama |
|-------|----------|
| `manager.py` | Core güvenlik duvarı yönetim sınıfı (40+ metot, UFW/firewalld/Emare, çok katmanlı koruma) |
| `ssh.py` | Dahili SSH executor (Paramiko + Subprocess) |
| `routes.py` | Flask Blueprint (herhangi bir Flask app'e takılabilir) |
| `cli.py` | Komut satırı arayüzü |
| `templates/firewall.html` | Bağımsız web UI (CDN'den Font Awesome) |
| `__main__.py` | `python -m emarefirewall` desteği |

---

## 🚀 Kurulum

```bash
# PyPI'dan (gelecek)
pip install emarefirewall

# Kaynak koddan
cd emarefirewall
pip install -e .

# Veya sadece kopyala
cp -r emarefirewall/ /your/project/
```

## 🌍 Production Domain ve Deploy Yolu

Emare Security OS icin production hedefi:

- Domain: `emaresecurityos.emarecloud.tr`
- Uygulama dizini: `/var/www/emaresecurityos`
- Runtime venv: `/opt/emaresecurityos-venv`
- Servis: `emaresecurityos.service`
- Nginx vhost: `/etc/nginx/conf.d/emaresecurityos.emarecloud.tr.conf`
- Internal port: `127.0.0.1:8202`

Hazir deploy dosyalari bu klasordedir:

- `deploy/.env.example`
- `deploy/emaresecurityos.service`
- `deploy/emaresecurityos.emarecloud.tr.conf`
- `deploy/deploy.sh`

Sunucuda hizli deploy:

```bash
cd /var/www/emaresecurityos
bash deploy/deploy.sh
```

**Bağımlılıklar:**
- `paramiko` — SSH bağlantısı için (opsiyonel, yerel kullanımda gerekmez)
- `flask` — Web API kullanacaksanız (opsiyonel)

---

## 🧾 5651 Uyumlu Loglama + TÜBİTAK Zaman Damgası

Emare Security OS log katmanı artık 5651 için zincir-hash üretir ve RFC3161 TSA ile
zaman damgası ekleyebilir.

- Her log kaydı `prev_hash -> entry_hash -> chain_hash` zincirine bağlanır.
- `extra.law_5651` alanına doğrulama metadatası yazılır.
- TÜBİTAK KamuSM TSA için `openssl ts` tabanlı istemci desteği vardır.
- Zincir bütünlüğü API üzerinden doğrulanabilir.

### Ortam Değişkenleri

```bash
EMARE_5651_ENABLED=1
EMARE_5651_ORGANIZATION="Emare Security OS"
EMARE_5651_STAMP_EVERY=1

# TÜBİTAK TSA (RFC3161)
EMARE_5651_TSA_URL="https://<tsa-endpoint>"
EMARE_5651_TSA_USERNAME=""
EMARE_5651_TSA_PASSWORD=""
EMARE_5651_TSA_TIMEOUT=10
EMARE_5651_TSA_DRY_RUN=1
EMARE_5651_TSA_CA_FILE="/path/to/tsa-ca.pem"
```

### 5651 API Uçları

- `GET /api/firewall/logs/5651/status`
- `GET /api/firewall/logs/5651/verify?limit=5000`
- `POST /api/firewall/logs/5651/seal`

---

## 🔧 Kullanım Yöntemleri

### 1. Python API (Standalone)

```python
from emarefirewall import FirewallManager
from emarefirewall.ssh import ParamikoExecutor

# SSH bağlantısı kur
ssh = ParamikoExecutor()
ssh.connect("srv1", host="185.189.54.107", user="root", key_path="~/.ssh/id_rsa")

# FirewallManager oluştur
fw = FirewallManager(ssh_executor=ssh.execute)

# Durum al
status = fw.get_status("srv1")
print(f"Tip: {status['type']}, Aktif: {status['active']}")

# Kural ekle
ok, msg = fw.add_rule("srv1", port="8080", protocol="tcp")
print(msg)

# IP engelle
ok, msg = fw.block_ip("srv1", "5.6.7.8", reason="Brute-force")
print(msg)

# Güvenlik taraması
scan = fw.security_scan("srv1")
print(f"Skor: {scan['score']}/100")

# Temizle
ssh.disconnect_all()
```

### 2. Emare OS

```python
from emarefirewall import FirewallManager
from emarefirewall.ssh import ParamikoExecutor

# Emare SSH bağlantısı
ssh = ParamikoExecutor()
ssh.connect("emareos1", host="192.168.88.1", user="admin", password="")

fw = FirewallManager(ssh_executor=ssh.execute)

# Otomatik Emare algılama
status = fw.get_status("emareos1")
print(f"Tip: {status['type']}")  # -> emareos
print(f"Versiyon: {status['version']}")
print(f"Cihaz: {status['identity']}")

# Filter kuralı ekle (chain=input, action=accept)
ok, msg = fw.add_rule("emareos1", port="8080", protocol="tcp")

# IP engelle (blocklist üzerinden)
ok, msg = fw.block_ip("emareos1", "5.6.7.8", reason="Brute-force")

# Port yönlendirme (dstnat)
ok, msg = fw.add_port_forward("emareos1", port="8080", to_port="80",
                              to_addr="192.168.88.10", protocol="tcp")

# Emare OS servis yönetimi
ok, msg = fw.add_service("emareos1", "ssh")
ok, msg = fw.remove_service("emareos1", "telnet")

# Emare güvenlik taraması
scan = fw.security_scan("emareos1")
print(f"Skor: {scan['score']}/100")
# Kontroller: tehlikeli servisler, varsayılan admin, filtre kuralları,
#   input chain drop kuralı, MAC Emare Desktop, Emare OS sürümü, DNS amplification

ssh.disconnect_all()
```

### 3. Yerel Sunucu (SSH'sız)

```python
from emarefirewall import FirewallManager
from emarefirewall.ssh import SubprocessExecutor

local = SubprocessExecutor()
fw = FirewallManager(ssh_executor=local.execute)

# Yerel firewall durumu
status = fw.get_status("localhost")
print(status)
```

### 4. Komut Satırı (CLI)

```bash
# Durum
python -m emarefirewall status --host 185.189.54.107 --user root

# Kurallar listesi
python -m emarefirewall rules --host 185.189.54.107

# Port aç
python -m emarefirewall add-rule --host 185.189.54.107 --rule-port 8080 --proto tcp

# IP engelle
python -m emarefirewall block-ip --host 185.189.54.107 --ip 5.6.7.8

# Güvenlik taraması
python -m emarefirewall scan --host 185.189.54.107

# Fail2ban durumu
python -m emarefirewall fail2ban --host 185.189.54.107

# Bağlantı istatistikleri
python -m emarefirewall conn-stats --host 185.189.54.107

# Ülke engelle
python -m emarefirewall geo-block --host 185.189.54.107 --country CN

# JSON çıktı
python -m emarefirewall status --host 185.189.54.107 --json

# Yerel sunucu
python -m emarefirewall status --host localhost
```

### 5. Flask Entegrasyonu

```python
from flask import Flask
from emarefirewall.routes import create_blueprint
from emarefirewall.ssh import ParamikoExecutor

app = Flask(__name__)
ssh = ParamikoExecutor()
ssh.connect("srv1", host="1.2.3.4", user="root", key_path="~/.ssh/id_rsa")

# Basit — auth yok
bp = create_blueprint(ssh_executor=ssh.execute)
app.register_blueprint(bp)

# Kalıcı loglama ile (SQLite)
bp = create_blueprint(
    ssh_executor=ssh.execute,
    log_db_path='/var/lib/emarefirewall/logs.db',
    log_retention_days=30,
)
app.register_blueprint(bp)

# Gelişmiş — auth + permission + audit
from flask_login import login_required

def my_permission(perm):
    def decorator(fn):
        # Kendi yetki kontrol mantığınız
        return fn
    return decorator

def my_audit(action, **kw):
    print(f"[AUDIT] {action}: {kw}")

bp = create_blueprint(
    ssh_executor=ssh.execute,
    auth_decorator=login_required,
    permission_decorator=my_permission,
    audit_fn=my_audit,
)
app.register_blueprint(bp)
```

### 6. Özel SSH Executor

Kendi SSH implementasyonunuzu kullanabilirsiniz:

```python
from emarefirewall import FirewallManager

def my_executor(server_id: str, command: str) -> tuple:
    """
    Kendi SSH/exec mantığınız.
    Returns: (ok: bool, stdout: str, stderr: str)
    """
    import subprocess
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return result.returncode == 0, result.stdout, result.stderr

fw = FirewallManager(ssh_executor=my_executor)
```

---

## 📋 API Referansı (FirewallManager Metotları)

### Durum
| Metot | Açıklama |
|-------|----------|
| `get_status(server_id)` | Tam güvenlik duvarı durumu |
| `enable(server_id)` | Firewall'u etkinleştir |
| `disable(server_id)` | Firewall'u devre dışı bırak |

### Kural Yönetimi
| Metot | Açıklama |
|-------|----------|
| `add_rule(server_id, port, protocol, action, from_ip)` | Port kuralı ekle |
| `delete_rule(server_id, rule_index)` | Kural sil |
| `add_service(server_id, service)` | Servis kuralı ekle |
| `remove_service(server_id, service)` | Servis kaldır |

### IP Engelleme
| Metot | Açıklama |
|-------|----------|
| `block_ip(server_id, ip, reason)` | IP engelle (drop) |
| `unblock_ip(server_id, ip)` | IP engeli kaldır |
| `get_blocked_ips(server_id)` | Engelli IP listesi |

### Port Yönlendirme
| Metot | Açıklama |
|-------|----------|
| `add_port_forward(server_id, port, to_port, to_addr, protocol)` | Port yönlendirme ekle |
| `remove_port_forward(server_id, port, to_port, to_addr, protocol)` | Yönlendirme kaldır |

### Zone Yönetimi (firewalld)
| Metot | Açıklama |
|-------|----------|
| `get_zones(server_id)` | Zone listesi |
| `set_default_zone(server_id, zone)` | Varsayılan zone değiştir |
| `get_zone_detail(server_id, zone)` | Zone detayları |

### Rich Rule (firewalld)
| Metot | Açıklama |
|-------|----------|
| `add_rich_rule(server_id, rule)` | Rich rule ekle |
| `remove_rich_rule(server_id, rule)` | Rich rule kaldır |

### Emare OS
| Özellik | Açıklama |
|---------|----------|
| Otomatik algılama | `/emare system info` ile cihaz tespit edilir |
| Filter kuralları | `/emare firewall rules` — chain=input/forward/output |
| Address list | IP engelleme `blocked` listesi üzerinden yapılır |
| NAT/dstnat | Port yönlendirme `/emare firewall nat` ile |
| Servis yönetimi | `/emare services enable/disable` (ssh, telnet, www, api, emare-desktop...) |
| Bağlantı izleme | `/emare firewall connections` tablosu |
| Güvenlik taraması | 7 kontrol: tehlikeli servisler, admin, filtre, drop kuralı, MAC Emare Desktop, versiyon, DNS |

### Fail2ban
| Metot | Açıklama |
|-------|----------|
| `get_fail2ban_status(server_id)` | Durum + jail bilgisi |
| `fail2ban_ban(server_id, jail, ip)` | IP ban et |
| `fail2ban_unban(server_id, jail, ip)` | IP unban et |

### Bağlantı İzleme
| Metot | Açıklama |
|-------|----------|
| `get_connections(server_id, limit)` | Aktif bağlantılar |
| `get_connection_stats(server_id)` | İstatistikler |

### Güvenlik
| Metot | Açıklama |
|-------|----------|
| `security_scan(server_id)` | Güvenlik taraması + skor |
| `geo_block_country(server_id, country_code)` | Ülke engelle |

### L7 Koruma
| Metot | Açıklama |
|-------|----------|
| `get_l7_status(server_id)` | Tüm katman koruma durumunu al |
| `apply_l7_protection(server_id, protections)` | Koruma uygula (L3/L4/L7) |
| `remove_l7_protection(server_id, prot)` | Korumayı kaldır |
| `l7_security_scan(server_id)` | Çok katmanlı güvenlik taraması |
| `collect_l7_events(server_id)` | Saldırı olaylarını topla |

### Yedekleme
| Metot | Açıklama |
|-------|----------|
| `backup_firewall(server_id, name)` | Yapılandırmayı yedekle |
| `restore_firewall(server_id, backup_id)` | Yedeği geri yükle |
| `list_backups(server_id)` | Yedekleri listele |
| `delete_backup(server_id, backup_id)` | Yedeği sil |

---

## 🌐 REST API Endpoint'leri (Flask Blueprint)

| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/api/servers/<id>/firewall/status` | Durum |
| POST | `/api/servers/<id>/firewall/enable` | Etkinleştir |
| POST | `/api/servers/<id>/firewall/disable` | Devre dışı bırak |
| POST | `/api/servers/<id>/firewall/rules` | Kural ekle |
| DELETE | `/api/servers/<id>/firewall/rules/<idx>` | Kural sil |
| POST | `/api/servers/<id>/firewall/services` | Servis ekle |
| DELETE | `/api/servers/<id>/firewall/services/<name>` | Servis kaldır |
| POST | `/api/servers/<id>/firewall/block-ip` | IP engelle |
| POST | `/api/servers/<id>/firewall/unblock-ip` | IP engeli kaldır |
| GET | `/api/servers/<id>/firewall/blocked-ips` | Engelli IP'ler |
| POST | `/api/servers/<id>/firewall/port-forward` | Port yönlendirme |
| DELETE | `/api/servers/<id>/firewall/port-forward` | Yönlendirme kaldır |
| GET | `/api/servers/<id>/firewall/zones` | Zone'lar |
| GET | `/api/servers/<id>/firewall/zones/<zone>` | Zone detayı |
| POST | `/api/servers/<id>/firewall/zones/default` | Varsayılan zone |
| POST | `/api/servers/<id>/firewall/rich-rules` | Rich rule ekle |
| DELETE | `/api/servers/<id>/firewall/rich-rules` | Rich rule kaldır |
| GET | `/api/servers/<id>/firewall/fail2ban` | Fail2ban durumu |
| POST | `/api/servers/<id>/firewall/fail2ban/ban` | F2B ban |
| POST | `/api/servers/<id>/firewall/fail2ban/unban` | F2B unban |
| GET | `/api/servers/<id>/firewall/connections` | Bağlantılar |
| GET | `/api/servers/<id>/firewall/connection-stats` | İstatistikler |
| GET | `/api/servers/<id>/firewall/security-scan` | Güvenlik taraması |
| POST | `/api/servers/<id>/firewall/geo-block` | Geo-block |

### L7 Koruma (Legacy — geriye uyumlu)
| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/api/servers/<id>/firewall/l7/status` | Koruma durumu |
| POST | `/api/servers/<id>/firewall/l7/apply` | Koruma uygula |
| POST | `/api/servers/<id>/firewall/l7/apply-all` | Tüm korumaları uygula |
| POST | `/api/servers/<id>/firewall/l7/remove` | Koruma kaldır |
| GET | `/api/servers/<id>/firewall/l7/scan` | Güvenlik taraması |
| GET | `/api/servers/<id>/firewall/l7/events` | Saldırı olayları topla |

### Çok Katmanlı Koruma (v1.3.0+)
| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/api/servers/<id>/firewall/protection/status` | L3/L4/L7 koruma durumu (katmanlı) |
| POST | `/api/servers/<id>/firewall/protection/apply` | Herhangi katman koruma uygula |
| POST | `/api/servers/<id>/firewall/protection/apply-all` | Tüm katmanlarda tüm korumaları uygula |
| POST | `/api/servers/<id>/firewall/protection/remove` | Koruma kaldır |
| GET | `/api/servers/<id>/firewall/protection/scan` | Çok katmanlı güvenlik taraması |

### Yedekleme / Geri Yükleme
| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/api/servers/<id>/firewall/backups` | Yedekleri listele |
| POST | `/api/servers/<id>/firewall/backups` | Yeni yedek oluştur |
| POST | `/api/servers/<id>/firewall/backups/restore` | Yedeği geri yükle |
| DELETE | `/api/servers/<id>/firewall/backups/<backup_id>` | Yedeği sil |

### Log & Monitoring
| Method | Endpoint | Açıklama |
|--------|----------|----------|
| GET | `/api/firewall/health` | Sistem sağlık kontrolü |
| GET | `/api/firewall/logs` | Log sorgulama |
| GET | `/api/firewall/logs/stats` | İstatistikler |
| GET | `/api/firewall/logs/ips` | IP listesi |
| GET | `/api/firewall/logs/ips/<ip>` | IP detay raporu |
| GET | `/api/firewall/logs/l7-summary` | L7 saldırı özeti |
| GET | `/api/firewall/logs/export` | Log dışa aktarma (JSON/CSV) |
| GET | `/api/firewall/logs/db-info` | Veritabanı bilgileri |
| DELETE | `/api/firewall/logs` | Logları temizle |

---

## 🛡️ Çok Katmanlı Koruma Türleri (v1.3.0)

### L3 — Ağ Katmanı
| Koruma | Açıklama | Linux | Emare |
|--------|----------|-------|----------|
| `l3_bogon_filter` | Sahte/rezerve IP bloklarını engeller (16 CIDR bloğu) | ✅ iptables chain | ✅ blocklist |
| `l3_fragment_protection` | IP fragmantasyon saldırılarını engeller | ✅ iptables | ✅ filter rule |
| `l3_ip_options` | IP kaynak yönlendirme seçeneklerini engeller (SSRR/LSRR/RR/TS) | ✅ ipv4options | ✅ filter rule |
| `l3_spoof_protection` | IP spoofing + martian paketleri engeller (rp_filter=strict) | ✅ sysctl | ✅ rp-filter |

### L4 — Transport Katmanı
| Koruma | Açıklama | Linux | Emare |
|--------|----------|-------|----------|
| `l4_udp_flood` | UDP taşkın saldırılarını hashlimit ile sınırlar (50/s) | ✅ iptables chain | ✅ filter chain |
| `l4_protocol_filter` | SCTP/DCCP/GRE kullanılmayan protokolleri engeller | ✅ iptables | ✅ filter rule |
| `l4_mss_clamp` | TCP MSS'yi PMTU'ya göre ayarlar (black hole önleme) | ✅ mangle table | ✅ mangle rule |
| `l4_tcp_timestamps` | TCP timestamp bilgi sızıntısını önler | ✅ sysctl | ℹ️ Emare OS yönetir |

### L7 — Uygulama Katmanı (Ağ Seviyesi)
| Koruma | Açıklama | Linux | Emare |
|--------|----------|-------|----------|
| `syn_flood` | SYN taşkın saldırısı koruması | ✅ | ✅ |
| `http_flood` | HTTP DDoS saldırısı koruması | ✅ | ✅ |
| `slowloris` | Yavaş bağlantı saldırısı koruması | ✅ | ✅ |
| `icmp_flood` | ICMP flood koruması | ✅ | ✅ |
| `port_scan` | Port tarama tespit ve engelleme | ✅ | ✅ |
| `bogus_tcp` | Geçersiz TCP flag kombinasyonları engelleme | ✅ | ✅ |
| `connection_limit` | IP başına max bağlantı sayısı | ✅ | ✅ |
| `kernel_hardening` | Kernel sysctl güvenlik ayarları | ✅ | ✅ |
| `l7_dns_amplification` | DNS amplifikasyon saldırısı koruması | ✅ hashlimit | ✅ rate limit |

### L7 — Web Sunucu Korumaları (Nginx)
| Koruma | Açıklama |
|--------|----------|
| `nginx_rate_limit` | İstek hızı sınırlama |
| `nginx_bad_bots` | Kötü bot / scanner engelleme |
| `nginx_sql_injection` | SQLi saldırısı engelleme |
| `nginx_xss` | XSS engelleme |
| `nginx_path_traversal` | Dizin gezinme saldırısı engelleme |
| `nginx_method_filter` | Tehlikeli HTTP metot engelleme |
| `nginx_request_size` | Max body size + timeout limiti |
| `nginx_waf` | ModSecurity web app firewall |
| `l7_hsts` | HSTS + güvenlik header'ları + TLS sertleştirme |
| `l7_smuggling` | HTTP istek kaçırma koruması |
| `l7_gzip_bomb` | Sıkıştırma bomba koruması |

---

## 🏗️ Mimari

```
emarefirewall/
├── __init__.py          ← Paket init, versiyon, kolay import
├── __main__.py          ← python -m emarefirewall desteği
├── manager.py           ← Core: FirewallManager sınıfı (40+ metot, UFW/firewalld/Emare)
├── ssh.py               ← ParamikoExecutor + SubprocessExecutor
├── routes.py            ← Flask Blueprint factory (create_blueprint) + LogStore (SQLite)
├── cli.py               ← Komut satırı arayüzü (22 komut)
├── templates/
│   ├── firewall.html    ← Firewall Yönetim UI (9 tab)
│   └── logs.html        ← Log & Monitoring Dashboard (7 tab)
├── pyproject.toml       ← Build config
├── requirements.txt     ← Bağımlılıklar
└── README.md            ← Bu dosya
```

**Tasarım Prensipleri:**
- **Sıfır zorunlu bağımlılık** — Core manager sadece Python stdlib kullanır
- **Dependency Injection** — SSH executor dışarıdan verilir
- **Plug & Play** — Flask Blueprint herhangi bir app'e takılabilir
- **CLI Ready** — Terminalde `python -m emarefirewall` ile kullanılabilir
- **Triple Backend** — UFW, firewalld ve Emare OS otomatik algılanır
- **Kalıcı Loglama** — Opsiyonel SQLite backend, otomatik retention policy

---

## 🛡️ Güvenlik Özellikleri

| Özellik | Açıklama |
|---------|----------|
| Input Validation | Tüm girdiler (IP, port, servis, zone) regex ile doğrulanır |
| Rate Limiting | IP bazlı dakika başına istek sınırı |
| CSRF Koruması | XHR header kontrolü veya harici CSRF token desteği |
| Command Injection | `shlex.quote()` ile tüm komut parametreleri sanitize edilir |
| Audit Trail | Tüm yönetim işlemleri loglanır |
| L7 Koruma | SYN flood, HTTP flood, Slowloris, port scan vb. 16 koruma türü |
| Çok Katmanlı Koruma | L3 (bogon, fragment, spoof), L4 (UDP flood, protocol filter, MSS), L7+ (DNS amp, HSTS, smuggling) — toplam 28 koruma |
| Yapılandırma Yedekleme | Otomatik pre-restore backup ile güvenli geri yükleme |

---

## 📊 Log Dashboard

7 sekmeli gelişmiş monitoring paneli:

1. **Canlı Loglar** — Real-time polling, seviye/kategori/IP filtreleme
2. **Analitik** — Saatlik trafik, HTTP method/status, kategori ve L7 dağılımı
3. **Güvenlik Olayları** — Rate limit, CSRF, L7 saldırı logları
4. **Audit Trail** — Admin işlem geçmişi
5. **Gelişmiş Arama** — Çoklu filtre + CSV/JSON dışa aktarma
6. **L7 Saldırılar** — L7 engelleme özeti, tür dağılımı, son olaylar
7. **IP İzleme** — IP bazlı detaylı risk raporu

---

## 🔌 EmareCloud Entegrasyonu

EmareCloud projesinde bu paket otomatik olarak kullanılır:

```python
# firewall_manager.py → emarefirewall.manager'dan import eder
# routes/firewall.py → emarefirewall.routes'tan Blueprint kullanır
```

---

*Emare Collective — Derviş Çeyizi*
