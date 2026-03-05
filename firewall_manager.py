"""
Güvenlik Duvarı Yönetimi - UFW ve firewalld desteği.
Sunucuda hangisi yüklüyse onu kullanır (UFW öncelikli, Ubuntu/Debian için).
"""

import re
from typing import Any


def _exec(ssh_mgr, server_id: str, command: str) -> tuple[bool, str, str]:
    """SSH ile komut çalıştırır."""
    return ssh_mgr.execute_command(server_id, command)


def get_status(ssh_mgr, server_id: str) -> dict[str, Any]:
    """
    Güvenlik duvarı durumunu döndürür.
    ssh_mgr: SSHManager örneği (execute_command(server_id, cmd) döner).
    """
    result = {
        "type": None,
        "active": False,
        "default_incoming": "deny",
        "default_outgoing": "allow",
        "rules": [],
        "message": "",
    }

    # Önce UFW kontrol et (Ubuntu/Debian)
    ok, out, err = _exec(ssh_mgr, server_id, "which ufw 2>/dev/null && ufw status verbose 2>/dev/null | head -80")
    if ok and out and "ufw" in out:
        result["type"] = "ufw"
        if "Status: active" in out:
            result["active"] = True
        elif "Status: inactive" in out:
            result["active"] = False
        # Default policies
        if "Default:" in out:
            if "incoming (deny)" in out or "Incoming: deny" in out:
                result["default_incoming"] = "deny"
            elif "incoming (allow)" in out or "Incoming: allow" in out:
                result["default_incoming"] = "allow"
            if "outgoing (allow)" in out or "Outgoing: allow" in out:
                result["default_outgoing"] = "allow"
        # Kurallar: "num" ile başlayan satırlar veya To/Action/From
        ok2, out2, _ = _exec(ssh_mgr, server_id, "ufw status numbered 2>/dev/null")
        if ok2 and out2:
            rules = []
            for line in out2.split("\n"):
                line = line.strip()
                # " [ 1] 22/tcp    ALLOW IN    Anywhere" formatı
                m = re.match(r"\[\s*(\d+)\]\s+(.+)", line)
                if m:
                    rules.append({"index": int(m.group(1)), "rule": m.group(2).strip()})
            result["rules"] = rules
        return result

    # firewalld dene (RHEL/CentOS/Fedora)
    ok, out, err = _exec(ssh_mgr, server_id, "which firewall-cmd 2>/dev/null && firewall-cmd --state 2>/dev/null")
    if ok and out and "running" in out:
        result["type"] = "firewalld"
        result["active"] = True
        ok2, out2, _ = _exec(ssh_mgr, server_id, "firewall-cmd --list-all 2>/dev/null")
        if ok2 and out2:
            rules = []
            for line in out2.split("\n"):
                if line.strip().startswith("ports:") and "ports:" in line:
                    # ports: 22/tcp 80/tcp
                    p = line.replace("ports:", "").strip()
                    if p:
                        for part in p.split():
                            rules.append({"index": len(rules) + 1, "rule": f"port {part}"})
                elif line.strip().startswith("services:") and "services:" in line:
                    s = line.replace("services:", "").strip()
                    if s:
                        for svc in s.split():
                            rules.append({"index": len(rules) + 1, "rule": f"service {svc}"})
            result["rules"] = rules
        return result

    # Hiçbiri yoksa
    ok3, out3, _ = _exec(ssh_mgr, server_id, "which ufw firewall-cmd 2>/dev/null; echo '---'; ufw status 2>&1; firewall-cmd --state 2>&1")
    result["message"] = "Bu sunucuda UFW veya firewalld bulunamadı. Önce UFW kurabilirsiniz: apt install ufw"
    return result


def enable_firewall(ssh_mgr, server_id: str) -> tuple[bool, str]:
    """Güvenlik duvarını etkinleştirir."""
    status = get_status(ssh_mgr, server_id)
    if status["type"] == "ufw":
        ok, out, err = _exec(ssh_mgr, server_id, "echo 'y' | sudo ufw enable 2>&1")
        if ok or "already active" in (out + err).lower():
            return True, "UFW etkinleştirildi."
        return False, (out + " " + err).strip() or "UFW etkinleştirilemedi"
    if status["type"] == "firewalld":
        ok, out, err = _exec(ssh_mgr, server_id, "sudo systemctl start firewalld 2>&1; sudo systemctl enable firewalld 2>&1")
        return ok, (out + " " + err).strip() or "firewalld başlatıldı."
    return False, status.get("message", "Desteklenen güvenlik duvarı yok.")


def disable_firewall(ssh_mgr, server_id: str) -> tuple[bool, str]:
    """Güvenlik duvarını devre dışı bırakır."""
    status = get_status(ssh_mgr, server_id)
    if status["type"] == "ufw":
        ok, out, err = _exec(ssh_mgr, server_id, "sudo ufw disable 2>&1")
        return ok, (out + " " + err).strip() or "UFW devre dışı bırakıldı."
    if status["type"] == "firewalld":
        ok, out, err = _exec(ssh_mgr, server_id, "sudo systemctl stop firewalld 2>&1; sudo systemctl disable firewalld 2>&1")
        return ok, (out + " " + err).strip()
    return False, status.get("message", "Desteklenen güvenlik duvarı yok.")


def add_rule(
    ssh_mgr,
    server_id: str,
    direction: str,
    action: str,
    port: str,
    protocol: str = "tcp",
    from_ip: str = "",
) -> tuple[bool, str]:
    """
    Kural ekler. UFW için: allow/deny, port (22 veya 80/tcp), from_ip opsiyonel.
    direction: 'in' | 'out'
    action: 'allow' | 'deny'
    """
    status = get_status(ssh_mgr, server_id)
    if not status["type"]:
        return False, status.get("message", "Önce güvenlik duvarı durumunu yükleyin.")

    port = (port or "").strip()
    if not port:
        return False, "Port veya servis belirtin (örn: 22, 80/tcp, 443)."

    if status["type"] == "ufw":
        # UFW: ufw allow 22/tcp, ufw deny from 1.2.3.4
        rule_spec = port if "/" in port else f"{port}/{protocol}"
        from_part = f" from {from_ip.strip()}" if from_ip and from_ip.strip() else ""
        cmd = f"sudo ufw {action} {rule_spec}{from_part} 2>&1"
        ok, out, err = _exec(ssh_mgr, server_id, cmd)
        msg = (out + " " + err).strip()
        if ok or "existing" in msg.lower() or "added" in msg.lower():
            return True, msg or "Kural eklendi."
        return False, msg
    if status["type"] == "firewalld":
        # firewalld: firewall-cmd --add-port=80/tcp --permanent
        if "/" in port:
            port_proto = port
        else:
            port_proto = f"{port}/{protocol}"
        cmd = f"sudo firewall-cmd --permanent --add-port={port_proto} 2>&1"
        ok, out, err = _exec(ssh_mgr, server_id, cmd)
        if ok:
            _exec(ssh_mgr, server_id, "sudo firewall-cmd --reload 2>&1")
        msg = (out + " " + err).strip()
        return ok, msg or "Kural eklendi."
    return False, "Desteklenmiyor."


def delete_rule(ssh_mgr, server_id: str, rule_index: int) -> tuple[bool, str]:
    """Numaraya göre kural siler (UFW numbered)."""
    status = get_status(ssh_mgr, server_id)
    if not status["type"]:
        return False, status.get("message", "Durum bilinmiyor.")
    if status["type"] == "ufw":
        # UFW numbered'da silince numaralar kayar, en yüksek numaradan silmek güvenli
        ok, out, err = _exec(ssh_mgr, server_id, f"echo 'y' | sudo ufw delete {rule_index} 2>&1")
        msg = (out + " " + err).strip()
        return ok or "deleted" in msg.lower(), msg
    if status["type"] == "firewalld":
        # firewalld'de port kaldırma: --remove-port=80/tcp
        rules = status.get("rules", [])
        r = next((x for x in rules if x.get("index") == rule_index), None)
        if not r:
            return False, "Kural bulunamadı."
        rule_str = r.get("rule", "")
        if "port " in rule_str:
            port_proto = rule_str.replace("port", "").strip()
            ok, out, err = _exec(ssh_mgr, server_id, f"sudo firewall-cmd --permanent --remove-port={port_proto} 2>&1")
            if ok:
                _exec(ssh_mgr, server_id, "sudo firewall-cmd --reload 2>&1")
            return ok, (out + " " + err).strip()
        return False, "Bu kural tipi silinemiyor (manuel yapın)."
    return False, "Desteklenmiyor."
