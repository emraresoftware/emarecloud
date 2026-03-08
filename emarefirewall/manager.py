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
from datetime import datetime
from typing import Callable

# Tip: SSH executor fonksiyon imzası
SSHExecutor = Callable[[str, str], tuple]


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

    def _exec(self, server_id: str, command: str) -> tuple:
        """SSH ile komut çalıştır."""
        return self._exec_fn(server_id, command)

    def _detect_type(self, server_id: str) -> str | None:
        """Firewall tipini tespit et: 'ufw' | 'firewalld' | None"""
        ok, out, _ = self._exec(server_id, "which ufw 2>/dev/null")
        if ok and out and "ufw" in out:
            return "ufw"
        ok, out, _ = self._exec(server_id, "which firewall-cmd 2>/dev/null")
        if ok and out and "firewall-cmd" in out:
            return "firewalld"
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
        port = (port or "").strip()
        if not port:
            return False, "Port belirtin."

        if fw == "ufw":
            spec = port if "/" in port else f"{port}/{protocol}"
            from_part = f" from {from_ip.strip()}" if from_ip and from_ip.strip() else ""
            ok, out, err = self._exec(server_id, f"sudo ufw {action} {spec}{from_part} 2>&1")
            msg = (out + " " + err).strip()
            if ok or "existing" in msg.lower() or "added" in msg.lower():
                return True, msg or "Kural eklendi."
            return False, msg

        if fw == "firewalld":
            pp = port if "/" in port else f"{port}/{protocol}"
            ok, out, err = self._exec(server_id,
                f"sudo firewall-cmd --permanent --add-port={pp} 2>&1")
            if ok:
                self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
            return ok, (out + " " + err).strip() or "Kural eklendi."
        return False, "Desteklenmiyor."

    def add_service(self, server_id: str, service: str) -> tuple:
        """Servis kuralı ekler. -> (ok, msg)"""
        fw = self._detect_type(server_id)
        service = (service or "").strip()
        if not service:
            return False, "Servis adı belirtin."
        if fw == "ufw":
            ok, out, err = self._exec(server_id, f"sudo ufw allow {service} 2>&1")
            msg = (out + " " + err).strip()
            return ok or "added" in msg.lower(), msg or "Servis eklendi."
        if fw == "firewalld":
            ok, out, err = self._exec(server_id,
                f"sudo firewall-cmd --permanent --add-service={service} 2>&1")
            if ok:
                self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
            return ok, (out + " " + err).strip() or "Servis eklendi."
        return False, "Desteklenen güvenlik duvarı bulunamadı."

    def remove_service(self, server_id: str, service: str) -> tuple:
        """Servis kuralını kaldırır. -> (ok, msg)"""
        fw = self._detect_type(server_id)
        service = (service or "").strip()
        if not service:
            return False, "Servis adı belirtin."
        if fw == "ufw":
            ok, out, err = self._exec(server_id, f"sudo ufw delete allow {service} 2>&1")
            return ok, (out + " " + err).strip() or "Servis kaldırıldı."
        if fw == "firewalld":
            ok, out, err = self._exec(server_id,
                f"sudo firewall-cmd --permanent --remove-service={service} 2>&1")
            if ok:
                self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
            return ok, (out + " " + err).strip() or "Servis kaldırıldı."
        return False, "Desteklenen güvenlik duvarı bulunamadı."

    def delete_rule(self, server_id: str, rule_index: int) -> tuple:
        """İndeks bazlı kural siler. -> (ok, msg)"""
        status = self.get_status(server_id)
        if not status["type"]:
            return False, status.get("message", "Durum bilinmiyor.")

        if status["type"] == "ufw":
            ok, out, err = self._exec(server_id,
                f"echo 'y' | sudo ufw delete {rule_index} 2>&1")
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
                cmd = f"sudo firewall-cmd --permanent --remove-port={pp} 2>&1"
            elif rule_type == "service" or "service " in rule_str:
                svc = rule_str.replace("service", "").strip()
                cmd = f"sudo firewall-cmd --permanent --remove-service={svc} 2>&1"
            elif rule_type == "rich_rule":
                cmd = f"sudo firewall-cmd --permanent --remove-rich-rule='{rule_str}' 2>&1"
            elif rule_type == "forward" or "forward " in rule_str:
                fwd = rule_str.replace("forward", "").strip()
                cmd = f"sudo firewall-cmd --permanent --remove-forward-port='{fwd}' 2>&1"
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
        ip = (ip or "").strip()
        if not ip:
            return False, "IP adresi belirtin."
        if fw == "ufw":
            ok, out, err = self._exec(server_id, f"sudo ufw deny from {ip} 2>&1")
            msg = (out + " " + err).strip()
            return ok or "added" in msg.lower(), msg or f"{ip} engellendi."
        if fw == "firewalld":
            rich = f"rule family='ipv4' source address='{ip}' drop"
            ok, out, err = self._exec(server_id,
                f'sudo firewall-cmd --permanent --add-rich-rule="{rich}" 2>&1')
            if ok:
                self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
            return ok, (out + " " + err).strip() or f"{ip} engellendi."
        return False, "Desteklenen güvenlik duvarı bulunamadı."

    def unblock_ip(self, server_id: str, ip: str) -> tuple:
        """IP engelini kaldırır. -> (ok, msg)"""
        fw = self._detect_type(server_id)
        ip = (ip or "").strip()
        if not ip:
            return False, "IP adresi belirtin."
        if fw == "ufw":
            ok, out, err = self._exec(server_id, f"sudo ufw delete deny from {ip} 2>&1")
            return ok, (out + " " + err).strip() or f"{ip} engeli kaldırıldı."
        if fw == "firewalld":
            rich = f"rule family='ipv4' source address='{ip}' drop"
            ok, out, err = self._exec(server_id,
                f'sudo firewall-cmd --permanent --remove-rich-rule="{rich}" 2>&1')
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
        port, to_port = (port or "").strip(), (to_port or "").strip()
        if not port or not to_port:
            return False, "Kaynak port ve hedef port belirtin."
        if fw == "ufw":
            return False, "UFW ile port yönlendirme desteklenmiyor. firewalld kullanın."
        if fw == "firewalld":
            to_part = f":toport={to_port}"
            if to_addr and to_addr.strip():
                to_part += f":toaddr={to_addr.strip()}"
            cmd = (f"sudo firewall-cmd --permanent "
                   f"--add-forward-port=port={port}:proto={protocol}{to_part} 2>&1")
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
        to_part = f":toport={to_port}"
        if to_addr and to_addr.strip():
            to_part += f":toaddr={to_addr.strip()}"
        cmd = (f"sudo firewall-cmd --permanent "
               f"--remove-forward-port=port={port}:proto={protocol}{to_part} 2>&1")
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
        zone = (zone or "").strip()
        if not zone:
            return False, "Zone adı belirtin."
        ok, out, err = self._exec(server_id,
            f"sudo firewall-cmd --set-default-zone={zone} 2>&1")
        return ok, (out + " " + err).strip() or f"Varsayılan zone: {zone}"

    def get_zone_detail(self, server_id: str, zone: str) -> dict:
        """Zone detaylarını döndürür."""
        fw = self._detect_type(server_id)
        if fw != "firewalld":
            return {"error": "Sadece firewalld desteklenir."}
        ok, out, _ = self._exec(server_id,
            f"firewall-cmd --zone={zone} --list-all 2>/dev/null")
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
        rule = (rule or "").strip()
        if not rule:
            return False, "Kural belirtin."
        if fw == "ufw":
            return False, "Rich rule sadece firewalld'de desteklenir."
        if fw == "firewalld":
            ok, out, err = self._exec(server_id,
                f"sudo firewall-cmd --permanent --add-rich-rule='{rule}' 2>&1")
            if ok:
                self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
            return ok, (out + " " + err).strip() or "Rich rule eklendi."
        return False, "Desteklenen güvenlik duvarı bulunamadı."

    def remove_rich_rule(self, server_id: str, rule: str) -> tuple:
        """Rich rule kaldırır (firewalld). -> (ok, msg)"""
        fw = self._detect_type(server_id)
        if fw != "firewalld":
            return False, "Rich rule sadece firewalld'de desteklenir."
        rule = (rule or "").strip()
        if not rule:
            return False, "Kural belirtin."
        ok, out, err = self._exec(server_id,
            f"sudo firewall-cmd --permanent --remove-rich-rule='{rule}' 2>&1")
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
            ok, out, _ = self._exec(server_id,
                f"sudo fail2ban-client status {jail} 2>/dev/null")
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
        ip, jail = (ip or "").strip(), (jail or "").strip()
        if not ip or not jail:
            return False, "Jail ve IP belirtin."
        ok, out, err = self._exec(server_id,
            f"sudo fail2ban-client set {jail} banip {ip} 2>&1")
        return ok, (out + " " + err).strip() or f"{ip} ban edildi."

    def fail2ban_unban(self, server_id: str, jail: str, ip: str) -> tuple:
        """Fail2ban'dan IP unban eder. -> (ok, msg)"""
        ip, jail = (ip or "").strip(), (jail or "").strip()
        if not ip or not jail:
            return False, "Jail ve IP belirtin."
        ok, out, err = self._exec(server_id,
            f"sudo fail2ban-client set {jail} unbanip {ip} 2>&1")
        return ok, (out + " " + err).strip() or f"{ip} unban edildi."

    # ═══════════════════ BAĞLANTI İZLEME ═══════════════════

    def get_connections(self, server_id: str, limit: int = 50) -> list:
        """Aktif ağ bağlantılarını listeler."""
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
        scan = {"timestamp": datetime.utcnow().isoformat(),
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
        cc = (country_code or "").strip().upper()
        if not cc or len(cc) != 2:
            return False, "Geçerli 2 harfli ülke kodu girin (örn: CN, RU)."
        if fw != "firewalld":
            return False, "Geo-block şu an sadece firewalld'de destekleniyor."
        cmds = [
            f"sudo ipset create geoblock_{cc} hash:net 2>/dev/null || true",
            f"sudo wget -qO /tmp/{cc}.zone "
            f"https://www.ipdeny.com/ipblocks/data/countries/{cc.lower()}.zone 2>/dev/null",
            f"sudo bash -c 'for ip in $(cat /tmp/{cc}.zone 2>/dev/null); "
            f"do ipset add geoblock_{cc} $ip 2>/dev/null; done'",
            f'sudo firewall-cmd --permanent '
            f'--add-rich-rule="rule source ipset=\'geoblock_{cc}\' drop" 2>&1',
            "sudo firewall-cmd --reload 2>&1",
        ]
        for cmd in cmds:
            self._exec(server_id, cmd)
        return True, f"{cc} ülkesi engellendi (ipset: geoblock_{cc})."
