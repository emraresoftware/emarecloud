"""
Sunucu İzleme Modülü
SSH üzerinden sunucu metriklerini (CPU, RAM, Disk, Ağ, Uptime vb.) toplar.
"""

import re
from typing import Any

from ssh_manager import SSHManager


class ServerMonitor:
    """Sunucu metriklerini SSH üzerinden toplar."""

    def __init__(self, ssh_manager: SSHManager):
        self.ssh = ssh_manager

    def get_system_info(self, server_id: str) -> dict[str, Any]:
        """Temel sistem bilgilerini toplar — tek SSH çağrısı ile."""
        info = {}
        # Tüm sistem bilgilerini tek komutta topla
        combined = (
            "echo '===HOSTNAME===' && hostname && "
            "echo '===OS===' && cat /etc/os-release 2>/dev/null | head -5 && "
            "echo '===KERNEL===' && uname -r && "
            "echo '===ARCH===' && uname -m && "
            "echo '===UPTIME===' && uptime -p 2>/dev/null || uptime && "
            "echo '===BOOT===' && who -b 2>/dev/null | awk '{print $3, $4}'"
        )
        ok, out, _ = self.ssh.execute_command(server_id, combined)
        if not ok:
            return info
        sections = out.split('===')
        for i, section in enumerate(sections):
            section = section.strip()
            if section == 'HOSTNAME' and i + 1 < len(sections):
                val = sections[i + 1].replace('===', '').strip()
                if val:
                    info['hostname'] = val.split('\n')[0].strip()
            elif section == 'OS' and i + 1 < len(sections):
                val = sections[i + 1].replace('===', '').strip()
                for line in val.split('\n'):
                    if line.startswith('PRETTY_NAME='):
                        info['os'] = line.split('=', 1)[1].strip('"')
                        break
            elif section == 'KERNEL' and i + 1 < len(sections):
                val = sections[i + 1].replace('===', '').strip()
                if val:
                    info['kernel'] = val.split('\n')[0].strip()
            elif section == 'ARCH' and i + 1 < len(sections):
                val = sections[i + 1].replace('===', '').strip()
                if val:
                    info['arch'] = val.split('\n')[0].strip()
            elif section == 'UPTIME' and i + 1 < len(sections):
                val = sections[i + 1].replace('===', '').strip()
                if val:
                    info['uptime'] = val.split('\n')[0].strip()
            elif section == 'BOOT' and i + 1 < len(sections):
                val = sections[i + 1].replace('===', '').strip()
                if val:
                    info['last_boot'] = val.split('\n')[0].strip()
        return info

    def get_cpu_info(self, server_id: str) -> dict[str, Any]:
        """CPU bilgilerini toplar — tek SSH çağrısı ile."""
        cpu = {}
        combined = (
            "echo '===LSCPU===' && lscpu 2>/dev/null | grep -E 'Model name|CPU\\(s\\)|Thread|Core|Socket' | head -6 && "
            "echo '===CPUUSAGE===' && top -bn1 | grep 'Cpu(s)' | awk '{print $2 + $4}' && "
            "echo '===LOADAVG===' && cat /proc/loadavg"
        )
        ok, out, _ = self.ssh.execute_command(server_id, combined)
        if not ok:
            return cpu
        sections = out.split('===')
        for i, section in enumerate(sections):
            section = section.strip()
            if section == 'LSCPU' and i + 1 < len(sections):
                val = sections[i + 1].replace('===', '').strip()
                for line in val.split('\n'):
                    if ':' in line:
                        key, v = line.split(':', 1)
                        key = key.strip()
                        v = v.strip()
                        if 'Model name' in key:
                            cpu['model'] = v
                        elif key == 'CPU(s)':
                            try:
                                cpu['cores'] = int(v)
                            except (ValueError, TypeError):
                                pass
            elif section == 'CPUUSAGE' and i + 1 < len(sections):
                val = sections[i + 1].replace('===', '').strip()
                try:
                    cpu['usage_percent'] = round(float(val.split('\n')[0].strip()), 1)
                except ValueError:
                    cpu['usage_percent'] = 0.0
            elif section == 'LOADAVG' and i + 1 < len(sections):
                val = sections[i + 1].replace('===', '').strip()
                parts = val.split('\n')[0].strip().split()
                if len(parts) >= 3:
                    try:
                        cpu['load_1m'] = float(parts[0])
                        cpu['load_5m'] = float(parts[1])
                        cpu['load_15m'] = float(parts[2])
                    except (ValueError, TypeError):
                        pass
        return cpu

    def get_memory_info(self, server_id: str) -> dict[str, Any]:
        """RAM bilgilerini toplar — tek SSH çağrısı ile."""
        memory = {}
        ok, out, _ = self.ssh.execute_command(server_id, "free -b")
        if not ok:
            return memory
        for line in out.strip().split('\n'):
            if line.startswith('Mem:') or line.strip().startswith('Mem:'):
                parts = line.split()
                if len(parts) >= 3:
                    total = int(parts[1])
                    used = int(parts[2])
                    memory['total'] = total
                    memory['used'] = used
                    memory['free'] = total - used
                    memory['usage_percent'] = round((used / total) * 100, 1) if total > 0 else 0
                    memory['total_hr'] = self._format_bytes(total)
                    memory['used_hr'] = self._format_bytes(used)
                    memory['free_hr'] = self._format_bytes(total - used)
            elif line.startswith('Swap:') or line.strip().startswith('Swap:'):
                parts = line.split()
                if len(parts) >= 3:
                    swap_total = int(parts[1])
                    swap_used = int(parts[2])
                    memory['swap_total'] = swap_total
                    memory['swap_used'] = swap_used
                    memory['swap_total_hr'] = self._format_bytes(swap_total)
                    memory['swap_used_hr'] = self._format_bytes(swap_used)
                    memory['swap_percent'] = round((swap_used / swap_total) * 100, 1) if swap_total > 0 else 0
        return memory

    def _base_disk_device(self, device: str) -> str:
        """Partition cihazından ana disk cihazını çıkarır: /dev/sda1 -> /dev/sda, /dev/nvme0n1p1 -> /dev/nvme0n1"""
        if not device:
            return device
        # nvme: /dev/nvme0n1p1 -> /dev/nvme0n1
        s = re.sub(r'p\d+$', '', device)
        # sd/vd: /dev/sda1 -> /dev/sda
        s = re.sub(r'\d+$', '', s)
        return s or device

    def get_disk_info(self, server_id: str) -> list:
        """Disk bilgilerini toplar. Kapasite + SMART sağlık (smartctl varsa)."""
        disks = []
        health_map: dict[str, str] = {}

        # Tek komutla df + sağlık: önce df, sonra base cihazlara smartctl -H
        cmd = (
            "echo '---DF---'; df -B1 --output=source,size,used,avail,pcent,target 2>/dev/null | grep -E '^/dev/' ; "
            "echo '---HEALTH---'; "
            "bases=$(df -B1 --output=source 2>/dev/null | grep -E '^/dev/' | awk '{print $1}' | sed 's/p[0-9]*$//' | sed 's/[0-9]*$//' | sort -u); "
            "for d in $bases; do r=$(smartctl -H $d 2>/dev/null | grep -oE 'PASSED|FAILED' | head -1); echo \"$d ${r:-UNKNOWN}\"; done"
        )
        ok, out, _ = self.ssh.execute_command(server_id, cmd, timeout=30)
        if not ok or not out:
            # Fallback: sadece df (sağlık yok)
            ok2, out2, _ = self.ssh.execute_command(server_id,
                "df -B1 --output=source,size,used,avail,pcent,target 2>/dev/null | grep -E '^/dev/'")
            if ok2 and out2:
                out = "---DF---\n" + out2 + "\n---HEALTH---\n"
            else:
                return []

        parts_block = out.split("---HEALTH---")
        df_block = parts_block[0].replace("---DF---", "").strip()
        health_block = parts_block[1].strip() if len(parts_block) > 1 else ""

        for line in health_block.split("\n"):
            line = line.strip()
            if not line:
                continue
            # "/dev/sda PASSED" veya "H /dev/sda PASSED"
            tokens = line.split()
            if len(tokens) >= 2:
                dev = tokens[0].lstrip("H")
                status = tokens[1].upper()
                health_map[dev] = "PASSED" if status == "PASSED" else ("FAILED" if status == "FAILED" else "—")

        for line in df_block.split("\n"):
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 6:
                try:
                    usage_pct = float(parts[4].replace("%", ""))
                except (ValueError, TypeError):
                    usage_pct = 0.0
                device = parts[0]
                base = self._base_disk_device(device)
                health = health_map.get(base, "—")
                disks.append({
                    "device": device,
                    "total": int(parts[1]),
                    "used": int(parts[2]),
                    "available": int(parts[3]),
                    "usage_percent": usage_pct,
                    "mount": parts[5],
                    "total_hr": self._format_bytes(int(parts[1])),
                    "used_hr": self._format_bytes(int(parts[2])),
                    "available_hr": self._format_bytes(int(parts[3])),
                    "health": health,
                })
        return disks

    def get_raid_status(self, server_id: str) -> dict[str, Any]:
        """Yazılım RAID (mdadm) durumunu döndürür. /proc/mdstat okur."""
        result = {"available": False, "raw": "", "arrays": []}
        ok, out, _ = self.ssh.execute_command(server_id, "cat /proc/mdstat 2>/dev/null")
        if not ok or not out:
            return result
        result["raw"] = out.strip()
        result["available"] = True
        # Örnek: md0 : active raid1 sda1[0] sdb1[1]
        for line in out.split("\n"):
            line = line.strip()
            if not line or line.startswith("Personalities") or line.startswith("unused"):
                continue
            # md0 : active raid1 sda1[0] sdb1[1]
            m = re.match(r"(md\d+)\s*:\s*(\w+)\s+(raid\d+|linear)\s+(.+)", line)
            if m:
                name, state, level, rest = m.group(1), m.group(2), m.group(3), m.group(4)
                devices = re.findall(r"(\S+?)\[\d+\]", rest)
                result["arrays"].append({
                    "name": name,
                    "state": state,
                    "level": level,
                    "devices": devices,
                })
        return result

    def get_network_info(self, server_id: str) -> dict[str, Any]:
        """Ağ bilgilerini toplar — tek SSH çağrısı ile."""
        network = {}
        combined = (
            "echo '===IPADDR===' && ip -4 addr show | grep inet | grep -v '127.0.0.1' | awk '{print $NF, $2}' && "
            "echo '===CONNS===' && ss -tun | tail -n +2 | wc -l && "
            "echo '===TRAFFIC===' && cat /proc/net/dev | grep -v 'lo:' | tail -n +3 | head -5"
        )
        ok, out, _ = self.ssh.execute_command(server_id, combined)
        if not ok:
            return network
        sections = out.split('===')
        for i, section in enumerate(sections):
            section = section.strip()
            if section == 'IPADDR' and i + 1 < len(sections):
                val = sections[i + 1].replace('===', '').strip()
                interfaces = []
                for line in val.split('\n'):
                    if line.strip():
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            interfaces.append({'name': parts[0], 'ip': parts[1]})
                network['interfaces'] = interfaces
            elif section == 'CONNS' and i + 1 < len(sections):
                val = sections[i + 1].replace('===', '').strip()
                try:
                    network['active_connections'] = int(val.split('\n')[0].strip())
                except ValueError:
                    network['active_connections'] = 0
            elif section == 'TRAFFIC' and i + 1 < len(sections):
                val = sections[i + 1].replace('===', '').strip()
                traffic = []
                for line in val.split('\n'):
                    if ':' in line:
                        parts = line.split(':')
                        iface = parts[0].strip()
                        values = parts[1].split()
                        if len(values) >= 9:
                            traffic.append({
                                'interface': iface,
                                'rx_bytes': int(values[0]),
                                'tx_bytes': int(values[8]),
                                'rx_hr': self._format_bytes(int(values[0])),
                                'tx_hr': self._format_bytes(int(values[8]))
                            })
                network['traffic'] = traffic
        return network

    def get_process_list(self, server_id: str, limit: int = 15) -> list:
        """En çok kaynak kullanan süreçleri listeler."""
        processes = []

        ok, out, _ = self.ssh.execute_command(server_id,
            f"ps aux --sort=-%cpu | head -n {limit + 1}")
        if ok:
            lines = out.strip().split('\n')
            for line in lines[1:]:  # Başlık satırını atla
                parts = line.split(None, 10)
                if len(parts) >= 11:
                    try:
                        processes.append({
                            'user': parts[0],
                            'pid': parts[1],
                            'cpu': float(parts[2]),
                            'mem': float(parts[3]),
                            'command': parts[10][:80]
                        })
                    except (ValueError, TypeError, IndexError):
                        pass

        return processes

    def get_service_status(self, server_id: str, services: list = None) -> list:
        """Servis durumlarını kontrol eder — tek SSH çağrısı ile batch kontrol."""
        if services is None:
            services = ['sshd', 'nginx', 'apache2', 'httpd', 'mysql', 'mariadb',
                        'postgresql', 'docker', 'redis', 'firewalld', 'ufw']

        # Her servis için değişken kullanmadan direkt kontrol
        cmd_parts = []
        for srv in services:
            cmd_parts.append(f"printf '{srv}:' && systemctl is-active {srv} 2>/dev/null || echo 'not-found'")
        combined_cmd = ' ; '.join(cmd_parts)

        ok, out, _ = self.ssh.execute_command(server_id, combined_cmd)
        results = []
        if ok and out:
            for line in out.strip().split('\n'):
                line = line.strip()
                if ':' in line:
                    name, status = line.split(':', 1)
                    status = status.strip()
                    if status in ['active', 'inactive', 'failed']:
                        results.append({'name': name.strip(), 'status': status})
                elif line in ['active', 'inactive', 'failed', 'not-found']:
                    # printf'siz fallback
                    pass

        # Eğer batch başarısızsa fallback (eski yöntem)
        if not results:
            for service in services:
                ok2, out2, _ = self.ssh.execute_command(server_id,
                    f"systemctl is-active {service} 2>/dev/null")
                status = out2.strip() if ok2 else 'not-found'
                if status in ['active', 'inactive', 'failed']:
                    results.append({'name': service, 'status': status})

        return results

    def get_security_info(self, server_id: str) -> dict[str, Any]:
        """Güvenlik bilgilerini toplar."""
        security = {}

        # Son başarısız giriş denemeleri
        ok, out, _ = self.ssh.execute_command(server_id,
            "lastb 2>/dev/null | head -5 | awk '{print $1, $3, $4, $5, $6}'")
        if ok:
            security['failed_logins'] = out.strip().split('\n') if out.strip() else []

        # Son başarılı girişler
        ok, out, _ = self.ssh.execute_command(server_id,
            "last -5 2>/dev/null | head -5")
        if ok:
            security['recent_logins'] = out.strip().split('\n') if out.strip() else []

        # Açık portlar
        ok, out, _ = self.ssh.execute_command(server_id,
            "ss -tlnp 2>/dev/null | tail -n +2 | awk '{print $4, $6}' | head -20")
        if ok:
            ports = []
            for line in out.strip().split('\n'):
                if line.strip():
                    ports.append(line.strip())
            security['open_ports'] = ports

        return security

    def get_all_metrics(self, server_id: str) -> dict[str, Any]:
        """Tüm metrikleri paralel olarak toplar — %60 daha hızlı."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        results = {}
        tasks = {
            'system': self.get_system_info,
            'cpu': self.get_cpu_info,
            'memory': self.get_memory_info,
            'disks': self.get_disk_info,
            'network': self.get_network_info,
            'processes': self.get_process_list,
            'services': self.get_service_status
        }
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix='metric') as pool:
            futures = {pool.submit(fn, server_id): key for key, fn in tasks.items()}
            for future in as_completed(futures):
                key = futures[future]
                try:
                    results[key] = future.result()
                except Exception:
                    results[key] = {} if key not in ('disks', 'processes', 'services') else []
        return results

    @staticmethod
    def _format_bytes(bytes_val: int) -> str:
        """Byte değerini okunabilir formata çevirir."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if abs(bytes_val) < 1024.0:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.1f} PB"
