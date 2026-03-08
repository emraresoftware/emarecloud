# 🔥 EmareFirewall — Bağımsız Güvenlik Duvarı Yönetim Paketi

**Versiyon:** 1.0.0  
**Lisans:** Emare Collective  
**Uyumluluk:** Python 3.8+, UFW (Ubuntu/Debian), firewalld (RHEL/CentOS/AlmaLinux)

---

## 📦 Ne İçerir?

| Dosya | Açıklama |
|-------|----------|
| `manager.py` | Core güvenlik duvarı yönetim sınıfı (29 metot, sıfır dış bağımlılık) |
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

**Bağımlılıklar:**
- `paramiko` — SSH bağlantısı için (opsiyonel, yerel kullanımda gerekmez)
- `flask` — Web API kullanacaksanız (opsiyonel)

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

### 2. Yerel Sunucu (SSH'sız)

```python
from emarefirewall import FirewallManager
from emarefirewall.ssh import SubprocessExecutor

local = SubprocessExecutor()
fw = FirewallManager(ssh_executor=local.execute)

# Yerel firewall durumu
status = fw.get_status("localhost")
print(status)
```

### 3. Komut Satırı (CLI)

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

### 4. Flask Entegrasyonu

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

### 5. Özel SSH Executor

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

---

## 🏗️ Mimari

```
emarefirewall/
├── __init__.py          ← Paket init, versiyon, kolay import
├── __main__.py          ← python -m emarefirewall desteği
├── manager.py           ← Core: FirewallManager sınıfı (29 metot)
├── ssh.py               ← ParamikoExecutor + SubprocessExecutor
├── routes.py            ← Flask Blueprint factory (create_blueprint)
├── cli.py               ← Komut satırı arayüzü (22 komut)
├── templates/
│   └── firewall.html    ← Bağımsız Web UI (7 tab)
├── pyproject.toml       ← Build config
├── requirements.txt     ← Bağımlılıklar
└── README.md            ← Bu dosya
```

**Tasarım Prensipleri:**
- **Sıfır zorunlu bağımlılık** — Core manager sadece Python stdlib kullanır
- **Dependency Injection** — SSH executor dışarıdan verilir
- **Plug & Play** — Flask Blueprint herhangi bir app'e takılabilir
- **CLI Ready** — Terminalde `python -m emarefirewall` ile kullanılabilir
- **Dual Backend** — UFW ve firewalld otomatik algılanır

---

## 🔌 EmareCloud Entegrasyonu

EmareCloud projesinde bu paket otomatik olarak kullanılır:

```python
# firewall_manager.py → emarefirewall.manager'dan import eder
# routes/firewall.py → emarefirewall.routes'tan Blueprint kullanır
```

---

*Emare Collective — Derviş Çeyizi*
