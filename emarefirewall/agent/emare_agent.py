"""
Emare Security OS — Windows/Linux RMM Agent
=============================================
Sunucuya bağlanır, metrik gönderir, görev yürütür.

Kullanım:
    python emare_agent.py --server https://emaresecurityos.emarecloud.tr

İlk çalıştırmada otomatik register olur, agent_key dosyaya kaydedilir.
Sonraki çalışmalarda key dosyasını okuyarak devam eder.

Windows servis olarak kurma:
    python emare_agent.py --install-service
    python emare_agent.py --uninstall-service
"""

import argparse
import json
import logging
import os
import platform
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error

# ── Config ──

VERSION = "1.1.0"
CONFIG_DIR = os.path.join(os.environ.get("PROGRAMDATA", "/etc"), "EmareAgent")
KEY_FILE = os.path.join(CONFIG_DIR, "agent.key")
CONFIG_FILE = os.path.join(CONFIG_DIR, "agent.conf")
LOG_FILE = os.path.join(CONFIG_DIR, "agent.log")
HEARTBEAT_INTERVAL = 60          # saniye
TASK_POLL_INTERVAL = 30          # saniye
MAX_RETRY_DELAY = 300            # max geri çekilme süresi (saniye)
SERVICE_NAME = "EmareAgent"
SERVICE_DISPLAY = "Emare Security OS Agent"

# ── Logging ──

os.makedirs(CONFIG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("emare-agent")


# ── Platform Metrikler ──

def get_cpu_percent():
    """CPU kullanımı — psutil olmadan basit ölçüm."""
    try:
        import psutil
        return psutil.cpu_percent(interval=1)
    except ImportError:
        pass
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "(Get-CimInstance Win32_Processor).LoadPercentage"],
                stderr=subprocess.DEVNULL, timeout=10,
            ).decode().strip()
            if out.isdigit():
                return float(out)
        except Exception:
            pass
    else:
        try:
            with open("/proc/stat") as f:
                a = f.readline().split()[1:]
            time.sleep(1)
            with open("/proc/stat") as f:
                b = f.readline().split()[1:]
            a = list(map(int, a))
            b = list(map(int, b))
            delta = [b[i] - a[i] for i in range(len(a))]
            idle = delta[3]
            total = sum(delta)
            return round((1 - idle / total) * 100, 1) if total else 0.0
        except Exception:
            pass
    return 0.0


def get_ram_percent():
    """RAM kullanımı."""
    try:
        import psutil
        return psutil.virtual_memory().percent
    except ImportError:
        pass
    if sys.platform == "win32":
        try:
            cmd = (
                '$os=Get-CimInstance Win32_OperatingSystem;'
                '"$($os.FreePhysicalMemory)|$($os.TotalVisibleMemorySize)"'
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                stderr=subprocess.DEVNULL, timeout=10,
            ).decode().strip()
            if "|" in out:
                free_kb, total_kb = out.split("|", 1)
                return round((1 - int(free_kb) / int(total_kb)) * 100, 1)
        except Exception:
            pass
    else:
        try:
            with open("/proc/meminfo") as f:
                info = {}
                for line in f:
                    k, v = line.split(":")
                    info[k.strip()] = int(v.strip().split()[0])
            total = info.get("MemTotal", 1)
            avail = info.get("MemAvailable", info.get("MemFree", 0))
            return round((1 - avail / total) * 100, 1)
        except Exception:
            pass
    return 0.0


def get_disk_percent():
    """Disk kullanımı (sistem diski)."""
    try:
        import psutil
        return psutil.disk_usage("/").percent
    except ImportError:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            free = ctypes.c_ulonglong(0)
            total = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                "C:\\", None, ctypes.pointer(total), ctypes.pointer(free)
            )
            return round((1 - free.value / total.value) * 100, 1)
        except Exception:
            pass
    else:
        try:
            st = os.statvfs("/")
            total = st.f_blocks * st.f_frsize
            free = st.f_bavail * st.f_frsize
            return round((1 - free / total) * 100, 1) if total else 0.0
        except Exception:
            pass
    return 0.0


def get_net_bytes():
    """Network in/out bytes."""
    try:
        import psutil
        n = psutil.net_io_counters()
        return n.bytes_recv, n.bytes_sent
    except ImportError:
        pass
    if sys.platform == "win32":
        try:
            cmd = (
                'Get-NetAdapterStatistics | '
                'Measure-Object -Property ReceivedBytes,SentBytes -Sum | '
                'ForEach-Object { $_.Sum }'
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                stderr=subprocess.DEVNULL, timeout=10,
            ).decode().strip()
            lines = [l.strip() for l in out.splitlines() if l.strip()]
            if len(lines) >= 2:
                return int(float(lines[0])), int(float(lines[1]))
        except Exception:
            pass
    else:
        try:
            with open("/proc/net/dev") as f:
                rx, tx = 0, 0
                for line in f:
                    if ":" in line:
                        parts = line.split(":")[1].split()
                        rx += int(parts[0])
                        tx += int(parts[8])
                return rx, tx
        except Exception:
            pass
    return 0, 0


def get_extra_info():
    """Ek bilgiler."""
    extra = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "hostname": socket.gethostname(),
    }
    try:
        extra["uptime"] = int(time.time() - _boot_time())
    except Exception:
        pass
    try:
        extra["process_count"] = _process_count()
    except Exception:
        pass
    try:
        extra["logged_users"] = _logged_users()
    except Exception:
        pass
    return extra


# ── UEBA: Kullanıcı Davranışı İzleme ──

_last_event_ts = {}   # her event tipi için son toplanan zaman damgası
_known_usb = set()    # bilinen USB cihazları
_known_procs = set()  # bilinen süreç PID'leri

def collect_ueba_events():
    """Tüm UEBA olaylarını topla ve döndür."""
    events = []
    collectors = [
        _collect_logon_events,
        _collect_usb_events,
        _collect_new_processes,
        _collect_network_connections,
        _collect_installed_software,
        _collect_file_audit_events,
    ]
    for fn in collectors:
        try:
            evts = fn()
            if evts:
                events.extend(evts)
        except Exception as e:
            log.debug("UEBA collector %s hatasi: %s", fn.__name__, e)
    return events


def _ts():
    """ISO timestamp."""
    import datetime
    return datetime.datetime.now().isoformat()


def _collect_logon_events():
    """Giriş/çıkış olayları — Windows Event Log veya Linux utmp/wtmp."""
    events = []
    if sys.platform == "win32":
        try:
            # Windows Security Event Log: 4624=Logon, 4634=Logoff, 4647=User initiated logoff
            cmd = (
                'Get-WinEvent -FilterHashtable @{LogName="Security";Id=4624,4634,4647} '
                '-MaxEvents 20 -ErrorAction SilentlyContinue | '
                'Select-Object Id,'
                '@{N="TS";E={$_.TimeCreated.ToString("o")}},'
                '@{N="User";E={$_.Properties[5].Value}},'
                '@{N="LogonType";E={$_.Properties[8].Value}} '
                '| ConvertTo-Json -Compress'
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                stderr=subprocess.DEVNULL, timeout=15,
            ).decode("utf-8", errors="replace")
            records = json.loads(out) if out.strip() else []
            if isinstance(records, dict):
                records = [records]
            last_ts = _last_event_ts.get("logon", "")
            newest = last_ts
            logon_types = {"2": "Interactive", "3": "Network", "7": "Unlock",
                           "10": "RemoteDesktop", "11": "CachedInteractive"}
            for r in records:
                ts = str(r.get("TS", ""))
                if ts <= last_ts:
                    continue
                if ts > newest:
                    newest = ts
                eid = r.get("Id", 0)
                user = r.get("User", "SYSTEM")
                lt = str(r.get("LogonType", ""))
                action = "logon" if eid == 4624 else "logoff"
                events.append({
                    "type": "logon",
                    "action": action,
                    "user": user,
                    "logon_type": logon_types.get(lt, lt),
                    "timestamp": ts,
                })
            if newest > last_ts:
                _last_event_ts["logon"] = newest
        except Exception as e:
            log.debug("Windows logon events: %s", e)
    else:
        # Linux: last komutu
        try:
            out = subprocess.check_output(
                ["last", "-n", "20", "-F"],
                stderr=subprocess.DEVNULL, timeout=10,
            ).decode("utf-8", errors="replace")
            for line in out.strip().splitlines():
                if not line.strip() or line.startswith("wtmp") or line.startswith("reboot"):
                    continue
                parts = line.split()
                if len(parts) >= 3:
                    user = parts[0]
                    terminal = parts[1]
                    still_in = "still logged in" in line
                    events.append({
                        "type": "logon",
                        "action": "logon" if still_in else "logoff",
                        "user": user,
                        "terminal": terminal,
                        "timestamp": _ts(),
                    })
        except Exception as e:
            log.debug("Linux logon events: %s", e)
    return events


def _collect_usb_events():
    """USB cihaz takma/çıkarma izleme."""
    global _known_usb
    events = []
    current_usb = set()

    if sys.platform == "win32":
        try:
            cmd = (
                'Get-PnpDevice -PresentOnly -Class USB 2>$null | '
                'Select-Object InstanceId,FriendlyName,Status | '
                'ConvertTo-Json -Compress'
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                stderr=subprocess.DEVNULL, timeout=15,
            ).decode("utf-8", errors="replace")
            devices = json.loads(out) if out.strip() else []
            if isinstance(devices, dict):
                devices = [devices]
            for d in devices:
                uid = d.get("InstanceId", "")
                name = d.get("FriendlyName", "Bilinmeyen USB")
                if uid:
                    current_usb.add(uid)
                    if _known_usb and uid not in _known_usb:
                        events.append({
                            "type": "usb",
                            "action": "connected",
                            "device_id": uid,
                            "device_name": name,
                            "timestamp": _ts(),
                        })
        except Exception as e:
            log.debug("Windows USB: %s", e)
    else:
        # Linux: /sys/bus/usb/devices
        try:
            usb_path = "/sys/bus/usb/devices"
            if os.path.exists(usb_path):
                for dev in os.listdir(usb_path):
                    prod_file = os.path.join(usb_path, dev, "product")
                    if os.path.exists(prod_file):
                        with open(prod_file) as f:
                            name = f.read().strip()
                        current_usb.add(dev)
                        if _known_usb and dev not in _known_usb:
                            events.append({
                                "type": "usb",
                                "action": "connected",
                                "device_id": dev,
                                "device_name": name,
                                "timestamp": _ts(),
                            })
        except Exception as e:
            log.debug("Linux USB: %s", e)

    # Çıkarılan USB cihazları
    if _known_usb:
        removed = _known_usb - current_usb
        for uid in removed:
            events.append({
                "type": "usb",
                "action": "disconnected",
                "device_id": uid,
                "timestamp": _ts(),
            })

    _known_usb = current_usb
    return events


def _collect_new_processes():
    """Yeni başlatılan süreçleri tespit et."""
    global _known_procs
    events = []
    current_procs = {}

    if sys.platform == "win32":
        try:
            cmd = (
                'Get-Process -ErrorAction SilentlyContinue | '
                'Select-Object Id,ProcessName,'
                '@{N="Exe";E={try{$_.Path}catch{$null}}} '
                '| ConvertTo-Json -Compress'
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                stderr=subprocess.DEVNULL, timeout=15,
            ).decode("utf-8", errors="replace")
            procs = json.loads(out) if out.strip() else []
            if isinstance(procs, dict):
                procs = [procs]
            for p in procs:
                pid = p.get("Id", 0)
                current_procs[pid] = {
                    "name": p.get("ProcessName", ""),
                    "path": p.get("Exe") or "",
                }
        except Exception as e:
            log.debug("Windows process list: %s", e)
    else:
        try:
            out = subprocess.check_output(
                ["ps", "-eo", "pid,comm,args", "--no-headers"],
                stderr=subprocess.DEVNULL, timeout=10,
            ).decode("utf-8", errors="replace")
            for line in out.strip().splitlines():
                parts = line.split(None, 2)
                if len(parts) >= 2 and parts[0].isdigit():
                    pid = int(parts[0])
                    current_procs[pid] = {
                        "name": parts[1],
                        "path": parts[2] if len(parts) > 2 else "",
                    }
        except Exception as e:
            log.debug("Linux process list: %s", e)

    # Yeni süreçler (ilk çalıştırmada hepsini bilinen olarak kaydet)
    if _known_procs:
        new_pids = set(current_procs.keys()) - _known_procs
        # Sadece ilginç olanları raporla (sistem süreçleri hariç)
        skip = {"svchost", "conhost", "csrss", "wininit", "services",
                "lsass", "smss", "kworker", "ksoftirqd", "migration"}
        for pid in new_pids:
            info = current_procs[pid]
            if info["name"].lower() in skip:
                continue
            events.append({
                "type": "process_start",
                "pid": pid,
                "process_name": info["name"],
                "process_path": info["path"][:500],
                "timestamp": _ts(),
            })
            if len(events) >= 50:
                break

    _known_procs = set(current_procs.keys())
    return events


def _collect_network_connections():
    """Aktif ağ bağlantıları — dışa açık bağlantılar."""
    events = []
    try:
        if sys.platform == "win32":
            cmd = (
                'Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue | '
                'Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,OwningProcess '
                '| ConvertTo-Json -Compress'
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                stderr=subprocess.DEVNULL, timeout=10,
            ).decode("utf-8", errors="replace")
        else:
            out = subprocess.check_output(
                ["ss", "-tunp", "--no-header"],
                stderr=subprocess.DEVNULL, timeout=10,
            ).decode("utf-8", errors="replace")

        connections = []
        if sys.platform == "win32":
            items = json.loads(out) if out.strip() else []
            if isinstance(items, dict):
                items = [items]
            for c in items:
                la = c.get("LocalAddress", "")
                lp = c.get("LocalPort", 0)
                ra = c.get("RemoteAddress", "")
                rp = c.get("RemotePort", 0)
                pid = c.get("OwningProcess", 0)
                connections.append({
                    "local": f"{la}:{lp}", "remote": f"{ra}:{rp}",
                    "pid": int(pid) if str(pid).isdigit() else 0
                })
        else:
            for line in out.strip().splitlines():
                parts = line.split()
                if len(parts) >= 5:
                    connections.append({"local": parts[3], "remote": parts[4]})

        # Sadece dış IP bağlantılarını raporla
        for c in connections[:30]:
            remote = c.get("remote", "")
            if remote and not remote.startswith(("127.", "0.0.0.0", "::1", "[::1]", "*")):
                events.append({
                    "type": "network_connection",
                    "local": c.get("local", ""),
                    "remote": remote,
                    "pid": c.get("pid", 0),
                    "timestamp": _ts(),
                })
    except Exception as e:
        log.debug("Network connections: %s", e)
    return events


def _collect_installed_software():
    """Yüklü yazılım listesi (her 10 heartbeat'te bir, ~10 dk)."""
    if _last_event_ts.get("_sw_counter", 0) % 10 != 0:
        _last_event_ts["_sw_counter"] = _last_event_ts.get("_sw_counter", 0) + 1
        return []
    _last_event_ts["_sw_counter"] = _last_event_ts.get("_sw_counter", 0) + 1

    software = []
    if sys.platform == "win32":
        try:
            cmd = (
                'Get-ItemProperty HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\* '
                '| Select-Object DisplayName,DisplayVersion,Publisher,InstallDate '
                '| Where-Object {$_.DisplayName} | ConvertTo-Json -Compress'
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                stderr=subprocess.DEVNULL, timeout=20,
            ).decode("utf-8", errors="replace")
            items = json.loads(out) if out.strip() else []
            if isinstance(items, dict):
                items = [items]
            for s in items[:100]:
                software.append({
                    "name": s.get("DisplayName", ""),
                    "version": s.get("DisplayVersion", ""),
                    "publisher": s.get("Publisher", ""),
                })
        except Exception:
            pass
    else:
        # Linux: dpkg veya rpm
        try:
            if os.path.exists("/usr/bin/dpkg"):
                out = subprocess.check_output(
                    ["dpkg", "-l"], stderr=subprocess.DEVNULL, timeout=15,
                ).decode("utf-8", errors="replace")
                for line in out.strip().splitlines():
                    if line.startswith("ii"):
                        parts = line.split(None, 4)
                        if len(parts) >= 3:
                            software.append({"name": parts[1], "version": parts[2]})
            elif os.path.exists("/usr/bin/rpm"):
                out = subprocess.check_output(
                    ["rpm", "-qa", "--qf", "%{NAME}|%{VERSION}\n"],
                    stderr=subprocess.DEVNULL, timeout=15,
                ).decode("utf-8", errors="replace")
                for line in out.strip().splitlines():
                    if "|" in line:
                        n, v = line.split("|", 1)
                        software.append({"name": n, "version": v})
        except Exception:
            pass

    if software:
        return [{"type": "software_inventory", "software": software[:100], "timestamp": _ts()}]
    return []


def _collect_file_audit_events():
    """Dosya denetim olayları — Windows Security log veya Linux auditd."""
    events = []
    if sys.platform == "win32":
        try:
            # Event ID 4663: Dosya erişimi, 4656: Handle isteği
            cmd = (
                'Get-WinEvent -FilterHashtable @{LogName="Security";Id=4663} '
                '-MaxEvents 20 -ErrorAction SilentlyContinue | '
                'Select-Object @{N="TS";E={$_.TimeCreated.ToString("o")}},'
                '@{N="User";E={$_.Properties[1].Value}},'
                '@{N="ObjectName";E={$_.Properties[6].Value}},'
                '@{N="AccessMask";E={$_.Properties[9].Value}} '
                '| ConvertTo-Json -Compress'
            )
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                stderr=subprocess.DEVNULL, timeout=15,
            ).decode("utf-8", errors="replace")
            records = json.loads(out) if out.strip() else []
            if isinstance(records, dict):
                records = [records]
            last_ts = _last_event_ts.get("file_audit", "")
            newest = last_ts
            for r in records:
                ts = str(r.get("TS", ""))
                if ts <= last_ts:
                    continue
                if ts > newest:
                    newest = ts
                obj = r.get("ObjectName", "")
                # USB sürücü veya önemli dizin kontrolü
                is_interesting = any(p in obj.lower() for p in [
                    "\\users\\", "\\desktop\\", "\\documents\\",
                    "\\downloads\\", "d:\\", "e:\\", "f:\\",
                ])
                if not is_interesting:
                    continue
                events.append({
                    "type": "file_access",
                    "user": r.get("User", ""),
                    "file_path": obj[:500],
                    "access_mask": r.get("AccessMask", ""),
                    "timestamp": ts,
                })
            if newest > last_ts:
                _last_event_ts["file_audit"] = newest
        except Exception as e:
            log.debug("Windows file audit: %s", e)
    else:
        # Linux: ausearch (auditd gerekir)
        try:
            out = subprocess.check_output(
                ["ausearch", "-m", "SYSCALL", "-i", "--just-one", "-ts", "recent"],
                stderr=subprocess.DEVNULL, timeout=10,
            ).decode("utf-8", errors="replace")
            if out.strip():
                events.append({
                    "type": "file_access",
                    "raw": out[:2000],
                    "timestamp": _ts(),
                })
        except Exception:
            pass
    return events


def _boot_time():
    try:
        import psutil
        return psutil.boot_time()
    except ImportError:
        pass
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "([DateTimeOffset]::Now.ToUnixTimeSeconds())-"
                 "([DateTimeOffset](Get-CimInstance Win32_OperatingSystem)"
                 ".LastBootUpTime).ToUnixTimeSeconds()"],
                stderr=subprocess.DEVNULL, timeout=10,
            ).decode().strip()
            return time.time() - int(out)
        except Exception:
            pass
    else:
        try:
            with open("/proc/uptime") as f:
                return time.time() - float(f.read().split()[0])
        except Exception:
            pass
    return time.time()


def _process_count():
    try:
        import psutil
        return len(psutil.pids())
    except ImportError:
        pass
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "(Get-Process).Count"],
                stderr=subprocess.DEVNULL, timeout=10,
            ).decode().strip()
            return int(out)
        except Exception:
            return 0
    else:
        try:
            return len([p for p in os.listdir("/proc") if p.isdigit()])
        except Exception:
            return 0


def _logged_users():
    try:
        import psutil
        return list(set(u.name for u in psutil.users()))
    except ImportError:
        pass
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "(query user 2>$null) -replace '\\s{2,}','|' | "
                 "ConvertFrom-Csv -Delimiter '|' | "
                 "Select-Object -ExpandProperty USERNAME"],
                stderr=subprocess.DEVNULL, timeout=10,
            ).decode("utf-8", errors="replace")
            users = [u.strip().lstrip('>') for u in out.strip().splitlines() if u.strip()]
            return list(set(users)) if users else []
        except Exception:
            pass
    else:
        try:
            out = subprocess.check_output(["who"], stderr=subprocess.DEVNULL, timeout=5).decode()
            return list(set(l.split()[0] for l in out.strip().splitlines() if l.strip()))
        except Exception:
            pass
    return []


# ── HTTP Client ──

class EmareClient:
    """Emare Security OS sunucusuyla iletişim."""

    def __init__(self, server_url):
        self.server = server_url.rstrip("/")
        self.agent_key = None

    def _request(self, path, method="GET", data=None, auth=True):
        url = f"{self.server}/api/rmm/{path}"
        headers = {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
        if auth and self.agent_key:
            headers["X-Agent-Key"] = self.agent_key

        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            log.error("HTTP %d: %s — %s", e.code, url, err_body[:200])
            return None
        except Exception as e:
            log.error("İstek hatası: %s — %s", url, e)
            return None

    def register(self, hostname, os_type, os_version, ip_address):
        """Sunucuya register ol, agent_key al."""
        data = {
            "hostname": hostname,
            "os_type": os_type,
            "os_version": os_version,
            "ip_address": ip_address,
            "agent_version": VERSION,
            "tags": [os_type, platform.machine()],
        }
        r = self._request("agent/register", method="POST", data=data, auth=False)
        if r and r.get("success"):
            self.agent_key = r["agent_key"]
            log.info("Kayıt başarılı — device_id: %s", r["id"])
            return r
        log.error("Kayıt başarısız: %s", r)
        return None

    def heartbeat(self, cpu, ram, disk, net_in, net_out, extra=None):
        """Metrik gönder."""
        data = {
            "cpu": round(cpu, 1),
            "ram": round(ram, 1),
            "disk": round(disk, 1),
            "net_in": net_in,
            "net_out": net_out,
            "extra": extra or {},
        }
        return self._request("agent/heartbeat", method="POST", data=data)

    def get_tasks(self):
        """Bekleyen görevleri çek."""
        r = self._request("agent/tasks")
        if r and r.get("success"):
            return r.get("tasks", [])
        return []

    def send_task_result(self, task_id, result, success=True):
        """Görev sonucunu gönder."""
        data = {"task_id": task_id, "result": result, "success": success}
        return self._request("agent/task-result", method="POST", data=data)


# ── Task Executor ──

SAFE_TASK_TYPES = {"shell_exec", "powershell_exec", "sysinfo_collect",
                   "event_log", "registry_query", "sysmon_collect"}

def execute_task(task):
    """Görevi çalıştır, sonuç döndür."""
    task_type = task.get("task_type", "")
    payload = task.get("payload", {})

    if task_type not in SAFE_TASK_TYPES:
        return False, f"Desteklenmeyen görev tipi: {task_type}"

    try:
        if task_type == "shell_exec":
            cmd = str(payload.get("command", ""))
            if not cmd:
                return False, "Komut boş"
            timeout = min(int(payload.get("timeout", 60)), 300)
            out = subprocess.check_output(
                cmd, shell=True, stderr=subprocess.STDOUT,
                timeout=timeout,
            ).decode("utf-8", errors="replace")
            return True, out[:10000]

        elif task_type == "powershell_exec":
            cmd = str(payload.get("command", ""))
            if not cmd:
                return False, "Komut boş"
            timeout = min(int(payload.get("timeout", 60)), 300)
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                stderr=subprocess.STDOUT, timeout=timeout,
            ).decode("utf-8", errors="replace")
            return True, out[:10000]

        elif task_type == "sysinfo_collect":
            info = {
                "hostname": socket.gethostname(),
                "platform": platform.platform(),
                "architecture": platform.machine(),
                "processor": platform.processor(),
                "python": platform.python_version(),
                "cpu_count": os.cpu_count(),
            }
            return True, json.dumps(info, indent=2)

        elif task_type == "event_log":
            if sys.platform == "win32":
                log_name = str(payload.get("log", "System"))
                count = min(int(payload.get("count", 20)), 100)
                cmd = (f'Get-EventLog -LogName {log_name} -Newest {count} '
                       f'| Format-Table -AutoSize | Out-String -Width 200')
                out = subprocess.check_output(
                    ["powershell", "-NoProfile", "-Command", cmd],
                    stderr=subprocess.STDOUT, timeout=30,
                ).decode("utf-8", errors="replace")
                return True, out[:10000]
            return False, "Event log sadece Windows'ta desteklenir"

        elif task_type == "registry_query":
            if sys.platform == "win32":
                key = str(payload.get("key", ""))
                if not key:
                    return False, "Registry key boş"
                out = subprocess.check_output(
                    ["reg", "query", key],
                    stderr=subprocess.STDOUT, timeout=15,
                ).decode("utf-8", errors="replace")
                return True, out[:10000]
            return False, "Registry sadece Windows'ta desteklenir"

        elif task_type == "sysmon_collect":
            if sys.platform == "win32":
                count = min(int(payload.get("count", 50)), 500)
                cmd = (f'Get-WinEvent -LogName "Microsoft-Windows-Sysmon/Operational" '
                       f'-MaxEvents {count} | Select-Object Id,TimeCreated,Message '
                       f'| ConvertTo-Json')
                out = subprocess.check_output(
                    ["powershell", "-NoProfile", "-Command", cmd],
                    stderr=subprocess.STDOUT, timeout=30,
                ).decode("utf-8", errors="replace")
                return True, out[:10000]
            return False, "Sysmon sadece Windows'ta desteklenir"

    except subprocess.TimeoutExpired:
        return False, "Görev zaman aşımına uğradı"
    except Exception as e:
        return False, str(e)[:5000]

    return False, "Bilinmeyen hata"


# ── Agent Key Yönetimi ──

def save_key(agent_key, device_id):
    data = json.dumps({"agent_key": agent_key, "device_id": device_id})
    with open(KEY_FILE, "w") as f:
        f.write(data)
    log.info("Agent key kaydedildi: %s", KEY_FILE)


def load_key():
    if not os.path.exists(KEY_FILE):
        return None, None
    try:
        with open(KEY_FILE) as f:
            d = json.loads(f.read())
        return d.get("agent_key"), d.get("device_id")
    except Exception:
        return None, None


def save_config(server_url):
    """Sunucu adresini config dosyasına kaydet."""
    data = json.dumps({"server": server_url})
    with open(CONFIG_FILE, "w") as f:
        f.write(data)
    log.info("Config kaydedildi: %s", CONFIG_FILE)


def load_config():
    """Config dosyasından sunucu adresini oku."""
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE) as f:
            d = json.loads(f.read())
        return d.get("server")
    except Exception:
        return None


# ── Network Info ──

def get_local_ip():
    """Yerel IP adresini tespit et."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 53))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ── Ana Döngü ──

def main_loop(client):
    """Heartbeat + görev polling döngüsü."""
    last_heartbeat = 0
    last_task_poll = 0
    retry_delay = 5
    prev_net = get_net_bytes()

    log.info("Ana döngü başlatıldı — HB:%ds  TASK:%ds",
             HEARTBEAT_INTERVAL, TASK_POLL_INTERVAL)

    while True:
        now = time.time()

        # ── Heartbeat ──
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            try:
                cpu = get_cpu_percent()
                ram = get_ram_percent()
                disk = get_disk_percent()
                cur_net = get_net_bytes()
                net_in = max(0, cur_net[0] - prev_net[0])
                net_out = max(0, cur_net[1] - prev_net[1])
                prev_net = cur_net
                extra = get_extra_info()

                # UEBA olaylarını topla ve extra'ya ekle
                try:
                    ueba_events = collect_ueba_events()
                    if ueba_events:
                        extra["events"] = ueba_events
                        log.info("🔍 %d UEBA olayı toplandı", len(ueba_events))
                except Exception as ue:
                    log.debug("UEBA toplama hatası: %s", ue)

                r = client.heartbeat(cpu, ram, disk, net_in, net_out, extra)
                if r and r.get("success"):
                    log.info("♥ HB OK — CPU:%.1f%%  RAM:%.1f%%  DISK:%.1f%%",
                             cpu, ram, disk)
                    retry_delay = 5
                    last_heartbeat = time.time()
                else:
                    log.warning("Heartbeat başarısız, %ds sonra tekrar", retry_delay)
                    retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)
            except Exception as e:
                log.error("Heartbeat hatası: %s", e)
                retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY)

        # ── Task Polling ──
        if now - last_task_poll >= TASK_POLL_INTERVAL:
            try:
                tasks = client.get_tasks()
                if tasks:
                    log.info("📋 %d görev alındı", len(tasks))
                for task in tasks:
                    tid = task.get("id", "?")
                    ttype = task.get("task_type", "?")
                    log.info("▶ Görev çalıştırılıyor: %s (%s)", tid, ttype)
                    success, result = execute_task(task)
                    client.send_task_result(tid, result, success)
                    status = "✅ Başarılı" if success else "❌ Başarısız"
                    log.info("  %s: %s — %s", tid, status, result[:100])
                last_task_poll = time.time()
            except Exception as e:
                log.error("Task polling hatası: %s", e)

        time.sleep(5)


# ── Windows Service ──

def install_service(server_url=None):
    """Agent'ı Windows servisi olarak kur."""
    if sys.platform != "win32":
        print("Bu komut sadece Windows'ta çalışır.")
        return
    # Sunucu adresini config'e kaydet
    srv = server_url or load_config() or "https://emaresecurityos.emarecloud.tr"
    save_config(srv)
    python = sys.executable
    script = os.path.abspath(__file__)
    cmd = f'sc create {SERVICE_NAME} binpath= "{python} {script} --run" start= auto displayname= "{SERVICE_DISPLAY}"'
    os.system(cmd)
    os.system(f'sc description {SERVICE_NAME} "Emare Security OS RMM Agent — monitoring ve görev yürütme servisi"')
    os.system(f'sc start {SERVICE_NAME}')
    print(f"Servis kuruldu ve başlatıldı: {SERVICE_NAME}")
    print(f"Sunucu: {srv}")
    print(f"Config: {CONFIG_FILE}")
    print(f"Log: {LOG_FILE}")


def uninstall_service():
    """Windows servisini kaldır."""
    if sys.platform != "win32":
        print("Bu komut sadece Windows'ta çalışır.")
        return
    os.system(f'sc stop {SERVICE_NAME}')
    os.system(f'sc delete {SERVICE_NAME}')
    print(f"Servis kaldırıldı: {SERVICE_NAME}")


# ── Main ──

def main():
    parser = argparse.ArgumentParser(description="Emare Security OS Agent")
    parser.add_argument("--server", default=None,
                        help="Sunucu URL'si")
    parser.add_argument("--run", action="store_true", help="Agent'ı başlat")
    parser.add_argument("--install-service", action="store_true",
                        help="Windows servisi olarak kur")
    parser.add_argument("--uninstall-service", action="store_true",
                        help="Windows servisini kaldır")
    parser.add_argument("--test", action="store_true",
                        help="Tek seferlik test (register + 1 heartbeat)")
    args = parser.parse_args()

    # Sunucu adresi: --server > config dosyası > varsayılan
    server_url = (args.server
                  or load_config()
                  or "https://emaresecurityos.emarecloud.tr")

    if args.install_service:
        install_service(server_url)
        return
    if args.uninstall_service:
        uninstall_service()
        return

    # Sunucu adresini config'e kaydet (sonraki çalışmalar için)
    save_config(server_url)

    log.info("═" * 50)
    log.info("Emare Security OS Agent v%s", VERSION)
    log.info("Sunucu: %s", server_url)
    log.info("Config: %s", CONFIG_DIR)
    log.info("Platform: %s", platform.platform())
    log.info("Hostname: %s", socket.gethostname())
    log.info("═" * 50)

    client = EmareClient(server_url)

    # Key yükleme veya register
    agent_key, device_id = load_key()
    if agent_key:
        client.agent_key = agent_key
        log.info("Mevcut key yüklendi — device: %s", device_id)
        # Auth test
        r = client.heartbeat(0, 0, 0, 0, 0, {"startup": True})
        if not r or not r.get("success"):
            log.warning("Mevcut key geçersiz, yeniden register olunuyor...")
            agent_key = None

    if not agent_key:
        hostname = socket.gethostname()
        os_type = "windows" if sys.platform == "win32" else "linux"
        os_version = platform.platform()
        ip_address = get_local_ip()
        r = client.register(hostname, os_type, os_version, ip_address)
        if not r:
            log.error("Kayıt başarısız! Sunucu erişilebilir mi?")
            sys.exit(1)
        save_key(r["agent_key"], r["id"])

    if args.test:
        log.info("── Test modu: tek heartbeat ──")
        cpu = get_cpu_percent()
        ram = get_ram_percent()
        disk = get_disk_percent()
        net = get_net_bytes()
        extra = get_extra_info()
        r = client.heartbeat(cpu, ram, disk, net[0], net[1], extra)
        log.info("Heartbeat sonucu: %s", r)
        log.info("CPU: %.1f%%  RAM: %.1f%%  Disk: %.1f%%", cpu, ram, disk)
        log.info("Test tamamlandı.")
        return

    # Normal çalışma
    main_loop(client)


if __name__ == "__main__":
    # Argüman yoksa --run varsay
    if len(sys.argv) == 1:
        sys.argv.append("--run")
    main()
