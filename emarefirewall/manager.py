"""
EmareFirewall — Core Manager (Bağımsız)
========================================

Hiçbir Flask/EmareCloud bağımlılığı yoktur.
Tek gereksinim: bir SSH executor fonksiyonu.

SSH Executor Arayüzü:
    def executor(server_id: str, command: str) -> tuple[bool, str, str]:
        '''Komut çalıştır, (ok, stdout, stderr) döndür.'''

Paramiko ile Kullanım:
    from emarefirewall import FirewallManager
    from emarefirewall.ssh import ParamikoExecutor

    ssh = ParamikoExecutor()
    ssh.connect("srv1", host="1.2.3.4", user="root", key_path="~/.ssh/id_rsa")
    fw = FirewallManager(ssh_executor=ssh.execute)
    print(fw.get_status("srv1"))
"""

import re
import shlex
from datetime import datetime, timezone
from typing import Callable, Optional

# Tip: SSH executor fonksiyon imzası
SSHExecutor = Callable[[str, str], tuple]

# ═══════════════════ GÜVENLİK: Input Validation ═══════════════════

# İzin verilen port formatları: 80, 443, 8000-9000, 80/tcp
_VALID_PORT_RE = re.compile(r'^\d{1,5}(-\d{1,5})?(/(?:tcp|udp))?$')
# İzin verilen IP formatları: IPv4, IPv4/CIDR
_VALID_IP_RE = re.compile(
    r'^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}'
    r'(?:25[0-5]|2[0-4]\d|[01]?\d\d?)'
    r'(?:/(?:[12]?\d|3[0-2]))?$'
)
# İzin verilen servis adları: sadece harf, rakam, tire
_VALID_SERVICE_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$')
# İzin verilen zone adları
_VALID_ZONE_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$')
# İzin verilen protokoller
_VALID_PROTOCOLS = {'tcp', 'udp', 'tcp/udp'}
# İzin verilen ufw action'ları
_VALID_ACTIONS = {'allow', 'deny', 'reject', 'limit'}
# İzin verilen ülke kodları (2 büyük harf)
_VALID_COUNTRY_RE = re.compile(r'^[A-Z]{2}$')
# İzin verilen jail adları
_VALID_JAIL_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{0,63}$')


def _validate_port(port: str) -> str:
    """Port değerini doğrular. Geçersizse ValueError fırlatır."""
    port = (port or '').strip()
    if not port:
        raise ValueError('Port belirtin.')
    # Birden fazla port virgülle ayrılabilir
    for p in port.split(','):
        p = p.strip()
        if not _VALID_PORT_RE.match(p):
            raise ValueError(f'Geçersiz port formatı: {p}')
        # Port numarası aralık kontrolü
        nums = re.findall(r'\d+', p)
        for n in nums:
            if int(n) < 1 or int(n) > 65535:
                raise ValueError(f'Port 1-65535 arasında olmalı: {n}')
    return port


def _validate_ip(ip: str) -> str:
    """IP adresini doğrular. Geçersizse ValueError fırlatır."""
    ip = (ip or '').strip()
    if not ip:
        raise ValueError('IP adresi belirtin.')
    if not _VALID_IP_RE.match(ip):
        raise ValueError(f'Geçersiz IP formatı: {ip}')
    return ip


def _validate_service(service: str) -> str:
    """Servis adını doğrular."""
    service = (service or '').strip()
    if not service:
        raise ValueError('Servis adı belirtin.')
    if not _VALID_SERVICE_RE.match(service):
        raise ValueError(f'Geçersiz servis adı: {service}')
    return service


def _validate_protocol(proto: str) -> str:
    """Protokolü doğrular."""
    proto = (proto or 'tcp').strip().lower()
    if proto not in _VALID_PROTOCOLS:
        raise ValueError(f'Geçersiz protokol: {proto}. İzin verilenler: {_VALID_PROTOCOLS}')
    return proto


def _validate_action(action: str) -> str:
    """UFW action'ı doğrular."""
    action = (action or 'allow').strip().lower()
    if action not in _VALID_ACTIONS:
        raise ValueError(f'Geçersiz işlem: {action}. İzin verilenler: {_VALID_ACTIONS}')
    return action


def _validate_zone(zone: str) -> str:
    """Zone adını doğrular."""
    zone = (zone or '').strip()
    if not zone:
        raise ValueError('Zone adı belirtin.')
    if not _VALID_ZONE_RE.match(zone):
        raise ValueError(f'Geçersiz zone adı: {zone}')
    return zone


def _validate_country(cc: str) -> str:
    """Ülke kodunu doğrular."""
    cc = (cc or '').strip().upper()
    if not cc or not _VALID_COUNTRY_RE.match(cc):
        raise ValueError('Geçerli 2 harfli ülke kodu girin (örn: CN, RU).')
    return cc


def _validate_jail(jail: str) -> str:
    """Fail2ban jail adını doğrular."""
    jail = (jail or '').strip()
    if not jail:
        raise ValueError('Jail adı belirtin.')
    if not _VALID_JAIL_RE.match(jail):
        raise ValueError(f'Geçersiz jail adı: {jail}')
    return jail


def _validate_rich_rule(rule: str) -> str:
    """Rich rule sözdizimini temel düzeyde doğrular."""
    rule = (rule or '').strip()
    if not rule:
        raise ValueError('Kural belirtin.')
    # Shell-tehlikeli karakterleri engelle
    dangerous = [';', '&&', '||', '`', '$(',  '${', '>', '<', '|', '\n', '\r']
    for d in dangerous:
        if d in rule:
            raise ValueError(f'Kuraldaki güvenlik dışı karakter: {d}')
    return rule


def _sq(value: str) -> str:
    """Shell-safe quoting (shlex.quote wrapper)."""
    return shlex.quote(value)


class FirewallManager:
    """
    Bağımsız güvenlik duvarı yöneticisi.
    UFW ve firewalld desteği, fail2ban entegrasyonu, güvenlik taraması.
    """

    def __init__(self, ssh_executor: SSHExecutor):
        """
        Args:
            ssh_executor: (server_id, command) -> (ok: bool, stdout: str, stderr: str)
        """
        self._exec_fn = ssh_executor
        self._type_cache = {}  # server_id -> fw_type cache

    def _exec(self, server_id: str, command: str) -> tuple:
        """SSH ile komut çalıştır."""
        return self._exec_fn(server_id, command)

    def _detect_type(self, server_id: str, force: bool = False) -> Optional[str]:
        """Firewall tipini tespit et: 'ufw' | 'firewalld' | None (cache'li)"""
        if not force and server_id in self._type_cache:
            return self._type_cache[server_id]
        ok, out, _ = self._exec(server_id, "which ufw 2>/dev/null")
        if ok and out and "ufw" in out:
            self._type_cache[server_id] = "ufw"
            return "ufw"
        ok, out, _ = self._exec(server_id, "which firewall-cmd 2>/dev/null")
        if ok and out and "firewall-cmd" in out:
            self._type_cache[server_id] = "firewalld"
            return "firewalld"
        self._type_cache[server_id] = None
        return None

    # ═══════════════════ DURUM ═══════════════════

    def get_status(self, server_id: str) -> dict:
        """Güvenlik duvarı tam durumunu döndürür."""
        result = {
            "type": None, "active": False,
            "default_incoming": "deny", "default_outgoing": "allow",
            "rules": [], "zones": [], "active_zone": "",
            "services": [], "ports": [], "rich_rules": [],
            "blocked_ips": [], "forward_ports": [],
            "masquerade": False, "interfaces": [], "message": "",
        }

        # ── UFW ──
        ok, out, err = self._exec(server_id,
            "which ufw 2>/dev/null && ufw status verbose 2>/dev/null | head -80")
        if ok and out and "ufw" in out:
            result["type"] = "ufw"
            result["active"] = "Status: active" in out
            if "Default:" in out:
                if "incoming (deny)" in out or "Incoming: deny" in out:
                    result["default_incoming"] = "deny"
                elif "incoming (allow)" in out or "Incoming: allow" in out:
                    result["default_incoming"] = "allow"
                if "outgoing (allow)" in out or "Outgoing: allow" in out:
                    result["default_outgoing"] = "allow"
            ok2, out2, _ = self._exec(server_id, "ufw status numbered 2>/dev/null")
            if ok2 and out2:
                for line in out2.split("\n"):
                    m = re.match(r"\[\s*(\d+)\]\s+(.+)", line.strip())
                    if m:
                        rule_text = m.group(2).strip()
                        result["rules"].append({
                            "index": int(m.group(1)),
                            "rule": rule_text,
                            "type": self._classify_ufw_rule(rule_text),
                        })
            return result

        # ── firewalld ──
        ok, out, err = self._exec(server_id,
            "which firewall-cmd 2>/dev/null && firewall-cmd --state 2>/dev/null")
        if ok and out and "running" in out:
            result["type"] = "firewalld"
            result["active"] = True
            self._parse_firewalld_full(server_id, result)
            return result

        result["message"] = "Bu sunucuda UFW veya firewalld bulunamadı."
        return result

    @staticmethod
    def _classify_ufw_rule(rule_text: str) -> str:
        if "DENY" in rule_text and "from" in rule_text.lower():
            return "ip_block"
        if "ALLOW" in rule_text or "DENY" in rule_text:
            return "port"
        return "other"

    def _parse_firewalld_full(self, server_id: str, result: dict):
        """firewalld tam durumunu parse et."""
        # Aktif zone
        ok, out, _ = self._exec(server_id, "firewall-cmd --get-active-zones 2>/dev/null")
        if ok and out:
            for line in out.split("\n"):
                line = line.strip()
                if line and not line.startswith("interfaces:") and not line.startswith("sources:"):
                    result["active_zone"] = line
                    break

        # Tüm zone'lar
        ok, out, _ = self._exec(server_id, "firewall-cmd --get-zones 2>/dev/null")
        if ok and out:
            result["zones"] = [z.strip() for z in out.split() if z.strip()]

        # Detaylı bilgi
        ok, out, _ = self._exec(server_id, "firewall-cmd --list-all 2>/dev/null")
        if ok and out:
            rules = []
            idx = 0
            for line in out.split("\n"):
                s = line.strip()
                if s.startswith("services:"):
                    svcs = s.replace("services:", "").strip()
                    if svcs:
                        result["services"] = svcs.split()
                        for svc in result["services"]:
                            idx += 1
                            rules.append({"index": idx, "rule": f"service {svc}", "type": "service"})
                elif s.startswith("ports:"):
                    ports = s.replace("ports:", "").strip()
                    if ports:
                        result["ports"] = ports.split()
                        for p in result["ports"]:
                            idx += 1
                            rules.append({"index": idx, "rule": f"port {p}", "type": "port"})
                elif s.startswith("rule "):
                    idx += 1
                    result["rich_rules"].append(s)
                    rules.append({"index": idx, "rule": s, "type": "rich_rule"})
                elif s.startswith("forward-ports:"):
                    fwd = s.replace("forward-ports:", "").strip()
                    if fwd:
                        for fp in fwd.split():
                            idx += 1
                            result["forward_ports"].append(fp)
                            rules.append({"index": idx, "rule": f"forward {fp}", "type": "forward"})
                elif s.startswith("masquerade:"):
                    result["masquerade"] = "yes" in s
                elif s.startswith("interfaces:"):
                    ifaces = s.replace("interfaces:", "").strip()
                    if ifaces:
                        result["interfaces"] = ifaces.split()
            result["rules"] = rules

        # Rich rule'ları ayrıca çek
        ok, out, _ = self._exec(server_id, "firewall-cmd --list-rich-rules 2>/dev/null")
        if ok and out:
            rich = [r.strip() for r in out.split("\n") if r.strip()]
            if rich and not result["rich_rules"]:
                result["rich_rules"] = rich
                for r in rich:
                    result["rules"].append({
                        "index": len(result["rules"]) + 1,
                        "rule": r, "type": "rich_rule",
                    })

    # ═══════════════════ ETKİNLEŞTİR / KAPAT ═══════════════════

    def enable(self, server_id: str) -> tuple:
        """Güvenlik duvarını etkinleştirir. -> (ok, msg)"""
        fw = self._detect_type(server_id)
        if fw == "ufw":
            ok, out, err = self._exec(server_id, "echo 'y' | sudo ufw enable 2>&1")
            if ok or "already active" in (out + err).lower():
                return True, "UFW etkinleştirildi."
            return False, (out + " " + err).strip() or "UFW etkinleştirilemedi"
        if fw == "firewalld":
            ok, out, err = self._exec(server_id,
                "sudo systemctl start firewalld 2>&1 && sudo systemctl enable firewalld 2>&1")
            return ok, (out + " " + err).strip() or "firewalld başlatıldı."
        return False, "Desteklenen güvenlik duvarı bulunamadı."

    def disable(self, server_id: str) -> tuple:
        """Güvenlik duvarını devre dışı bırakır. -> (ok, msg)"""
        fw = self._detect_type(server_id)
        if fw == "ufw":
            ok, out, err = self._exec(server_id, "sudo ufw disable 2>&1")
            return ok, (out + " " + err).strip() or "UFW devre dışı bırakıldı."
        if fw == "firewalld":
            ok, out, err = self._exec(server_id,
                "sudo systemctl stop firewalld 2>&1 && sudo systemctl disable firewalld 2>&1")
            return ok, (out + " " + err).strip()
        return False, "Desteklenen güvenlik duvarı bulunamadı."

    # ═══════════════════ PORT / SERVİS KURAL ═══════════════════

    def add_rule(self, server_id: str, port: str, protocol: str = "tcp",
                 action: str = "allow", direction: str = "in",
                 from_ip: str = "") -> tuple:
        """Port kuralı ekler. -> (ok, msg)"""
        fw = self._detect_type(server_id)
        if not fw:
            return False, "Desteklenen güvenlik duvarı bulunamadı."
        try:
            port = _validate_port(port)
            protocol = _validate_protocol(protocol)
            action = _validate_action(action)
            if from_ip and from_ip.strip():
                from_ip = _validate_ip(from_ip)
        except ValueError as e:
            return False, str(e)

        if fw == "ufw":
            spec = port if "/" in port else f"{port}/{protocol}"
            from_part = f" from {_sq(from_ip)}" if from_ip and from_ip.strip() else ""
            ok, out, err = self._exec(server_id, f"sudo ufw {_sq(action)} {_sq(spec)}{from_part} 2>&1")
            msg = (out + " " + err).strip()
            if ok or "existing" in msg.lower() or "added" in msg.lower():
                return True, msg or "Kural eklendi."
            return False, msg

        if fw == "firewalld":
            pp = port if "/" in port else f"{port}/{protocol}"
            ok, out, err = self._exec(server_id,
                f"sudo firewall-cmd --permanent --add-port={_sq(pp)} 2>&1")
            if ok:
                self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
            return ok, (out + " " + err).strip() or "Kural eklendi."
        return False, "Desteklenmiyor."

    def add_service(self, server_id: str, service: str) -> tuple:
        """Servis kuralı ekler. -> (ok, msg)"""
        fw = self._detect_type(server_id)
        try:
            service = _validate_service(service)
        except ValueError as e:
            return False, str(e)
        if fw == "ufw":
            ok, out, err = self._exec(server_id, f"sudo ufw allow {_sq(service)} 2>&1")
            msg = (out + " " + err).strip()
            return ok or "added" in msg.lower(), msg or "Servis eklendi."
        if fw == "firewalld":
            ok, out, err = self._exec(server_id,
                f"sudo firewall-cmd --permanent --add-service={_sq(service)} 2>&1")
            if ok:
                self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
            return ok, (out + " " + err).strip() or "Servis eklendi."
        return False, "Desteklenen güvenlik duvarı bulunamadı."

    def remove_service(self, server_id: str, service: str) -> tuple:
        """Servis kuralını kaldırır. -> (ok, msg)"""
        fw = self._detect_type(server_id)
        try:
            service = _validate_service(service)
        except ValueError as e:
            return False, str(e)
        if fw == "ufw":
            ok, out, err = self._exec(server_id, f"sudo ufw delete allow {_sq(service)} 2>&1")
            return ok, (out + " " + err).strip() or "Servis kaldırıldı."
        if fw == "firewalld":
            ok, out, err = self._exec(server_id,
                f"sudo firewall-cmd --permanent --remove-service={_sq(service)} 2>&1")
            if ok:
                self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
            return ok, (out + " " + err).strip() or "Servis kaldırıldı."
        return False, "Desteklenen güvenlik duvarı bulunamadı."

    def delete_rule(self, server_id: str, rule_index: int) -> tuple:
        """İndeks bazlı kural siler. -> (ok, msg)"""
        rule_index = int(rule_index)  # Tam sayı garantisi
        status = self.get_status(server_id)
        if not status["type"]:
            return False, status.get("message", "Durum bilinmiyor.")

        if status["type"] == "ufw":
            ok, out, err = self._exec(server_id,
                f"echo 'y' | sudo ufw delete {int(rule_index)} 2>&1")
            msg = (out + " " + err).strip()
            return ok or "deleted" in msg.lower(), msg

        if status["type"] == "firewalld":
            rules = status.get("rules", [])
            r = next((x for x in rules if x.get("index") == rule_index), None)
            if not r:
                return False, "Kural bulunamadı."
            rule_str = r.get("rule", "")
            rule_type = r.get("type", "")

            if rule_type == "port" or "port " in rule_str:
                pp = rule_str.replace("port", "").strip()
                cmd = f"sudo firewall-cmd --permanent --remove-port={_sq(pp)} 2>&1"
            elif rule_type == "service" or "service " in rule_str:
                svc = rule_str.replace("service", "").strip()
                cmd = f"sudo firewall-cmd --permanent --remove-service={_sq(svc)} 2>&1"
            elif rule_type == "rich_rule":
                cmd = f"sudo firewall-cmd --permanent --remove-rich-rule={_sq(rule_str)} 2>&1"
            elif rule_type == "forward" or "forward " in rule_str:
                fwd = rule_str.replace("forward", "").strip()
                cmd = f"sudo firewall-cmd --permanent --remove-forward-port={_sq(fwd)} 2>&1"
            else:
                return False, "Bu kural tipi otomatik silinemez."

            ok, out, err = self._exec(server_id, cmd)
            if ok:
                self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
            return ok, (out + " " + err).strip() or "Kural silindi."
        return False, "Desteklenmiyor."

    # ═══════════════════ IP ENGELLEME ═══════════════════

    def block_ip(self, server_id: str, ip: str, reason: str = "") -> tuple:
        """IP adresini engeller (drop). -> (ok, msg)"""
        fw = self._detect_type(server_id)
        try:
            ip = _validate_ip(ip)
        except ValueError as e:
            return False, str(e)
        if fw == "ufw":
            ok, out, err = self._exec(server_id, f"sudo ufw deny from {_sq(ip)} 2>&1")
            msg = (out + " " + err).strip()
            return ok or "added" in msg.lower(), msg or f"{ip} engellendi."
        if fw == "firewalld":
            rich = f"rule family='ipv4' source address='{ip}' drop"
            ok, out, err = self._exec(server_id,
                f'sudo firewall-cmd --permanent --add-rich-rule={_sq(rich)} 2>&1')
            if ok:
                self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
            return ok, (out + " " + err).strip() or f"{ip} engellendi."
        return False, "Desteklenen güvenlik duvarı bulunamadı."

    def unblock_ip(self, server_id: str, ip: str) -> tuple:
        """IP engelini kaldırır. -> (ok, msg)"""
        fw = self._detect_type(server_id)
        try:
            ip = _validate_ip(ip)
        except ValueError as e:
            return False, str(e)
        if fw == "ufw":
            ok, out, err = self._exec(server_id, f"sudo ufw delete deny from {_sq(ip)} 2>&1")
            return ok, (out + " " + err).strip() or f"{ip} engeli kaldırıldı."
        if fw == "firewalld":
            rich = f"rule family='ipv4' source address='{ip}' drop"
            ok, out, err = self._exec(server_id,
                f'sudo firewall-cmd --permanent --remove-rich-rule={_sq(rich)} 2>&1')
            if ok:
                self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
            return ok, (out + " " + err).strip() or f"{ip} engeli kaldırıldı."
        return False, "Desteklenen güvenlik duvarı bulunamadı."

    def get_blocked_ips(self, server_id: str) -> list:
        """Engelli IP'leri listeler."""
        fw = self._detect_type(server_id)
        blocked = []
        if fw == "ufw":
            ok, out, _ = self._exec(server_id, "ufw status numbered 2>/dev/null")
            if ok and out:
                for line in out.split("\n"):
                    m = re.match(r"\[\s*(\d+)\]\s+.*DENY\s+IN\s+(.+)", line.strip())
                    if m:
                        blocked.append({"index": int(m.group(1)), "ip": m.group(2).strip()})
        elif fw == "firewalld":
            ok, out, _ = self._exec(server_id, "firewall-cmd --list-rich-rules 2>/dev/null")
            if ok and out:
                idx = 0
                for line in out.split("\n"):
                    m = re.search(r"source address=['\"]([^'\"]+)['\"].*drop", line.strip())
                    if m:
                        idx += 1
                        blocked.append({"index": idx, "ip": m.group(1), "rule": line.strip()})
        return blocked

    # ═══════════════════ PORT YÖNLENDİRME ═══════════════════

    def add_port_forward(self, server_id: str, port: str, to_port: str,
                         to_addr: str = "", protocol: str = "tcp") -> tuple:
        """Port yönlendirme ekler. -> (ok, msg)"""
        fw = self._detect_type(server_id)
        try:
            port = _validate_port(port)
            to_port = _validate_port(to_port)
            protocol = _validate_protocol(protocol)
            if to_addr and to_addr.strip():
                to_addr = _validate_ip(to_addr)
        except ValueError as e:
            return False, str(e)
        if fw == "ufw":
            return False, "UFW ile port yönlendirme desteklenmiyor. firewalld kullanın."
        if fw == "firewalld":
            to_part = f":toport={to_port}"
            if to_addr and to_addr.strip():
                to_part += f":toaddr={to_addr}"
            fwd_spec = f"port={port}:proto={protocol}{to_part}"
            cmd = f"sudo firewall-cmd --permanent --add-forward-port={_sq(fwd_spec)} 2>&1"
            ok, out, err = self._exec(server_id, cmd)
            if ok:
                self._exec(server_id, "sudo firewall-cmd --permanent --add-masquerade 2>&1")
                self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
            return ok, (out + " " + err).strip() or "Port yönlendirme eklendi."
        return False, "Desteklenen güvenlik duvarı bulunamadı."

    def remove_port_forward(self, server_id: str, port: str, to_port: str,
                            to_addr: str = "", protocol: str = "tcp") -> tuple:
        """Port yönlendirme kaldırır. -> (ok, msg)"""
        fw = self._detect_type(server_id)
        if fw != "firewalld":
            return False, "Sadece firewalld destekleniyor."
        try:
            port = _validate_port(port)
            to_port = _validate_port(to_port)
            protocol = _validate_protocol(protocol)
            if to_addr and to_addr.strip():
                to_addr = _validate_ip(to_addr)
        except ValueError as e:
            return False, str(e)
        to_part = f":toport={to_port}"
        if to_addr and to_addr.strip():
            to_part += f":toaddr={to_addr}"
        fwd_spec = f"port={port}:proto={protocol}{to_part}"
        cmd = f"sudo firewall-cmd --permanent --remove-forward-port={_sq(fwd_spec)} 2>&1"
        ok, out, err = self._exec(server_id, cmd)
        if ok:
            self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
        return ok, (out + " " + err).strip() or "Port yönlendirme kaldırıldı."

    # ═══════════════════ ZONE YÖNETİMİ ═══════════════════

    def get_zones(self, server_id: str) -> dict:
        """Tüm zone'ları döndürür."""
        fw = self._detect_type(server_id)
        if fw != "firewalld":
            return {"zones": [], "active": "", "default": "",
                    "message": "Zone yönetimi sadece firewalld'de desteklenir."}
        ok, out, _ = self._exec(server_id, "firewall-cmd --get-zones 2>/dev/null")
        zones = out.split() if ok and out else []
        ok2, out2, _ = self._exec(server_id, "firewall-cmd --get-active-zones 2>/dev/null")
        active = ""
        if ok2 and out2:
            for line in out2.split("\n"):
                line = line.strip()
                if line and not line.startswith("interfaces:") and not line.startswith("sources:"):
                    active = line
                    break
        ok3, out3, _ = self._exec(server_id, "firewall-cmd --get-default-zone 2>/dev/null")
        default = out3.strip() if ok3 and out3 else ""
        return {"zones": zones, "active": active, "default": default}

    def set_default_zone(self, server_id: str, zone: str) -> tuple:
        """Varsayılan zone'u değiştirir. -> (ok, msg)"""
        fw = self._detect_type(server_id)
        if fw != "firewalld":
            return False, "Zone yönetimi sadece firewalld'de desteklenir."
        try:
            zone = _validate_zone(zone)
        except ValueError as e:
            return False, str(e)
        ok, out, err = self._exec(server_id,
            f"sudo firewall-cmd --set-default-zone={_sq(zone)} 2>&1")
        return ok, (out + " " + err).strip() or f"Varsayılan zone: {zone}"

    def get_zone_detail(self, server_id: str, zone: str) -> dict:
        """Zone detaylarını döndürür."""
        fw = self._detect_type(server_id)
        if fw != "firewalld":
            return {"error": "Sadece firewalld desteklenir."}
        try:
            zone = _validate_zone(zone)
        except ValueError:
            return {"error": "Geçersiz zone adı."}
        ok, out, _ = self._exec(server_id,
            f"firewall-cmd --zone={_sq(zone)} --list-all 2>/dev/null")
        if not ok or not out:
            return {"error": f"Zone '{zone}' bilgisi alınamadı."}
        detail = {"zone": zone, "services": [], "ports": [], "rich_rules": [],
                  "interfaces": [], "masquerade": False, "forward_ports": []}
        for line in out.split("\n"):
            s = line.strip()
            if s.startswith("services:"):
                v = s.replace("services:", "").strip()
                detail["services"] = v.split() if v else []
            elif s.startswith("ports:"):
                v = s.replace("ports:", "").strip()
                detail["ports"] = v.split() if v else []
            elif s.startswith("interfaces:"):
                v = s.replace("interfaces:", "").strip()
                detail["interfaces"] = v.split() if v else []
            elif s.startswith("masquerade:"):
                detail["masquerade"] = "yes" in s
            elif s.startswith("forward-ports:"):
                v = s.replace("forward-ports:", "").strip()
                detail["forward_ports"] = v.split() if v else []
            elif s.startswith("rule "):
                detail["rich_rules"].append(s)
        return detail

    # ═══════════════════ RICH RULE ═══════════════════

    def add_rich_rule(self, server_id: str, rule: str) -> tuple:
        """Rich rule ekler (firewalld). -> (ok, msg)"""
        fw = self._detect_type(server_id)
        try:
            rule = _validate_rich_rule(rule)
        except ValueError as e:
            return False, str(e)
        if fw == "ufw":
            return False, "Rich rule sadece firewalld'de desteklenir."
        if fw == "firewalld":
            ok, out, err = self._exec(server_id,
                f"sudo firewall-cmd --permanent --add-rich-rule={_sq(rule)} 2>&1")
            if ok:
                self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
            return ok, (out + " " + err).strip() or "Rich rule eklendi."
        return False, "Desteklenen güvenlik duvarı bulunamadı."

    def remove_rich_rule(self, server_id: str, rule: str) -> tuple:
        """Rich rule kaldırır (firewalld). -> (ok, msg)"""
        fw = self._detect_type(server_id)
        if fw != "firewalld":
            return False, "Rich rule sadece firewalld'de desteklenir."
        try:
            rule = _validate_rich_rule(rule)
        except ValueError as e:
            return False, str(e)
        ok, out, err = self._exec(server_id,
            f"sudo firewall-cmd --permanent --remove-rich-rule={_sq(rule)} 2>&1")
        if ok:
            self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
        return ok, (out + " " + err).strip() or "Rich rule kaldırıldı."

    # ═══════════════════ FAIL2BAN ═══════════════════

    def get_fail2ban_status(self, server_id: str) -> dict:
        """Fail2ban durumunu döndürür."""
        result = {"installed": False, "active": False, "jails": [], "banned_ips": {}}
        ok, out, _ = self._exec(server_id, "which fail2ban-client 2>/dev/null")
        if not ok or not out or "fail2ban" not in out:
            return result
        result["installed"] = True
        ok, out, _ = self._exec(server_id, "systemctl is-active fail2ban 2>/dev/null")
        if ok and out and "active" in out:
            result["active"] = True
        ok, out, _ = self._exec(server_id, "sudo fail2ban-client status 2>/dev/null")
        if ok and out:
            m = re.search(r"Jail list:\s+(.+)", out)
            if m:
                result["jails"] = [j.strip() for j in m.group(1).split(",") if j.strip()]
        for jail in result["jails"]:
            safe_jail = _sq(jail)
            ok, out, _ = self._exec(server_id,
                f"sudo fail2ban-client status {safe_jail} 2>/dev/null")
            if ok and out:
                info = {"currently_banned": 0, "total_banned": 0, "banned_list": []}
                m1 = re.search(r"Currently banned:\s+(\d+)", out)
                if m1: info["currently_banned"] = int(m1.group(1))
                m2 = re.search(r"Total banned:\s+(\d+)", out)
                if m2: info["total_banned"] = int(m2.group(1))
                m3 = re.search(r"Banned IP list:\s+(.+)", out)
                if m3: info["banned_list"] = m3.group(1).strip().split()
                result["banned_ips"][jail] = info
        return result

    def fail2ban_ban(self, server_id: str, jail: str, ip: str) -> tuple:
        """Fail2ban ile IP ban eder. -> (ok, msg)"""
        try:
            ip = _validate_ip(ip)
            jail = _validate_jail(jail)
        except ValueError as e:
            return False, str(e)
        ok, out, err = self._exec(server_id,
            f"sudo fail2ban-client set {_sq(jail)} banip {_sq(ip)} 2>&1")
        return ok, (out + " " + err).strip() or f"{ip} ban edildi."

    def fail2ban_unban(self, server_id: str, jail: str, ip: str) -> tuple:
        """Fail2ban'dan IP unban eder. -> (ok, msg)"""
        try:
            ip = _validate_ip(ip)
            jail = _validate_jail(jail)
        except ValueError as e:
            return False, str(e)
        ok, out, err = self._exec(server_id,
            f"sudo fail2ban-client set {_sq(jail)} unbanip {_sq(ip)} 2>&1")
        return ok, (out + " " + err).strip() or f"{ip} unban edildi."

    # ═══════════════════ BAĞLANTI İZLEME ═══════════════════

    def get_connections(self, server_id: str, limit: int = 50) -> list:
        """Aktif ağ bağlantılarını listeler."""
        limit = max(1, min(int(limit), 500))  # 1-500 arasında sınırla
        connections = []
        ok, out, _ = self._exec(server_id, f"ss -tunap 2>/dev/null | head -{limit + 1}")
        if not ok or not out:
            return connections
        for line in out.strip().split("\n")[1:]:
            parts = line.split()
            if len(parts) >= 5:
                connections.append({
                    "proto": parts[0],
                    "state": parts[1] if len(parts) > 1 else "",
                    "recv_q": parts[2] if len(parts) > 2 else "",
                    "send_q": parts[3] if len(parts) > 3 else "",
                    "local": parts[4] if len(parts) > 4 else "",
                    "peer": parts[5] if len(parts) > 5 else "",
                    "process": parts[6] if len(parts) > 6 else "",
                })
        return connections

    def get_connection_stats(self, server_id: str) -> dict:
        """Bağlantı istatistiklerini döndürür."""
        stats = {"total": 0, "established": 0, "listening": 0,
                 "time_wait": 0, "close_wait": 0,
                 "by_port": {}, "by_ip": {}, "top_ips": [], "top_ports": []}
        ok, out, _ = self._exec(server_id, "ss -tan 2>/dev/null | tail -n +2")
        if not ok or not out:
            return stats
        for line in out.strip().split("\n"):
            if not line.strip():
                continue
            stats["total"] += 1
            parts = line.split()
            if parts:
                state = parts[0].upper()
                if "ESTAB" in state: stats["established"] += 1
                elif "LISTEN" in state: stats["listening"] += 1
                elif "TIME" in state: stats["time_wait"] += 1
                elif "CLOSE" in state: stats["close_wait"] += 1
            if len(parts) >= 4:
                port = parts[3].rsplit(":", 1)[-1] if ":" in parts[3] else ""
                if port.isdigit():
                    stats["by_port"][port] = stats["by_port"].get(port, 0) + 1
            if len(parts) >= 5:
                peer = parts[4]
                ip = peer.rsplit(":", 1)[0] if ":" in peer else peer
                ip = ip.strip("[]")
                if ip and ip not in ("*", "0.0.0.0"):
                    stats["by_ip"][ip] = stats["by_ip"].get(ip, 0) + 1
        stats["top_ips"] = sorted(stats["by_ip"].items(), key=lambda x: x[1], reverse=True)[:10]
        stats["top_ports"] = sorted(stats["by_port"].items(), key=lambda x: x[1], reverse=True)[:10]
        return stats

    # ═══════════════════ GÜVENLİK TARAMASI ═══════════════════

    def security_scan(self, server_id: str) -> dict:
        """Temel güvenlik taraması yapar."""
        scan = {"timestamp": datetime.now(timezone.utc).isoformat(),
                "score": 100, "findings": [], "recommendations": []}

        # 1. Firewall aktif mi?
        status = self.get_status(server_id)
        if not status["active"]:
            scan["score"] -= 30
            scan["findings"].append({"severity": "critical",
                "title": "Güvenlik duvarı kapalı",
                "detail": "Sunucuda güvenlik duvarı aktif değil."})
            scan["recommendations"].append("Güvenlik duvarını hemen etkinleştirin.")

        # 2. SSH root login?
        ok, out, _ = self._exec(server_id,
            "grep -i '^PermitRootLogin' /etc/ssh/sshd_config 2>/dev/null")
        if ok and out and "yes" in out.lower():
            scan["score"] -= 15
            scan["findings"].append({"severity": "high",
                "title": "Root SSH izinli", "detail": "PermitRootLogin = yes"})
            scan["recommendations"].append(
                "PermitRootLogin'i 'no' veya 'prohibit-password' yapın.")

        # 3. SSH password auth?
        ok, out, _ = self._exec(server_id,
            "grep -i '^PasswordAuthentication' /etc/ssh/sshd_config 2>/dev/null")
        if ok and out and "yes" in out.lower():
            scan["score"] -= 10
            scan["findings"].append({"severity": "medium",
                "title": "Parola ile SSH izinli",
                "detail": "PasswordAuthentication = yes"})
            scan["recommendations"].append("Key-based auth kullanın, parola auth kapatın.")

        # 4. Fail2ban aktif mi?
        f2b = self.get_fail2ban_status(server_id)
        if not f2b["installed"]:
            scan["score"] -= 10
            scan["findings"].append({"severity": "medium",
                "title": "Fail2ban kurulu değil",
                "detail": "Brute-force koruması yok."})
            scan["recommendations"].append(
                "Fail2ban kurun: yum install fail2ban / apt install fail2ban")
        elif not f2b["active"]:
            scan["score"] -= 10
            scan["findings"].append({"severity": "medium",
                "title": "Fail2ban kapalı",
                "detail": "Fail2ban kurulu ama çalışmıyor."})
            scan["recommendations"].append("Fail2ban'ı başlatın: systemctl start fail2ban")

        # 5. Tehlikeli portlar
        risky = {"23": "Telnet", "21": "FTP", "3306": "MySQL",
                 "5432": "PostgreSQL", "6379": "Redis",
                 "27017": "MongoDB", "9200": "Elasticsearch"}
        ok, out, _ = self._exec(server_id, "ss -tlnp 2>/dev/null | awk '{print $4}'")
        if ok and out:
            for line in out.split("\n"):
                port = line.rsplit(":", 1)[-1].strip() if ":" in line else ""
                if port in risky:
                    scan["score"] -= 5
                    scan["findings"].append({"severity": "medium",
                        "title": f"{risky[port]} portu açık ({port})",
                        "detail": f"Port {port} ({risky[port]}) dışarıdan erişilebilir."})
                    scan["recommendations"].append(
                        f"Port {port}'i localhost'a bağlayın veya firewall'dan kapatın.")

        # 6. Kernel reboot?
        ok, out, _ = self._exec(server_id,
            "needs-restarting -r 2>/dev/null || echo 'n/a'")
        if ok and out and "Reboot is required" in out:
            scan["score"] -= 5
            scan["findings"].append({"severity": "low",
                "title": "Reboot gerekli",
                "detail": "Kernel güncellemesi reboot bekliyor."})
            scan["recommendations"].append("Sunucuyu yeniden başlatın.")

        scan["score"] = max(0, scan["score"])
        return scan

    # ═══════════════════ GEO-BLOCK ═══════════════════

    def geo_block_country(self, server_id: str, country_code: str) -> tuple:
        """Ülke bazlı engelleme (ipset + firewalld). -> (ok, msg)"""
        fw = self._detect_type(server_id)
        try:
            cc = _validate_country(country_code)
        except ValueError as e:
            return False, str(e)
        if fw != "firewalld":
            return False, "Geo-block şu an sadece firewalld'de destekleniyor."
        ipset_name = f"geoblock_{cc}"
        zone_url = f"https://www.ipdeny.com/ipblocks/data/countries/{cc.lower()}.zone"
        cmds = [
            f"sudo ipset create {_sq(ipset_name)} hash:net 2>/dev/null || true",
            f"sudo wget -qO /tmp/{_sq(cc)}.zone {_sq(zone_url)} 2>/dev/null",
            f"sudo bash -c 'for ip in $(cat /tmp/{cc}.zone 2>/dev/null); "
            f"do ipset add {_sq(ipset_name)} $ip 2>/dev/null; done'",
            f"sudo firewall-cmd --permanent "
            f"--add-rich-rule={_sq(f'rule source ipset={ipset_name} drop')} 2>&1",
            "sudo firewall-cmd --reload 2>&1",
        ]
        for cmd in cmds:
            self._exec(server_id, cmd)
        return True, f"{cc} ülkesi engellendi (ipset: {ipset_name})."
