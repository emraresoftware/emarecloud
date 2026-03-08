"""
EmareFirewall Dervişi — Güvenlik Duvarı Yönetimi (Uyumluluk Katmanı)
=====================================================================

Bu dosya geriye dönük uyumluluk için korunmuştur.
Tüm işlevler emarefirewall paketine delege edilir.

Bağımsız kullanım için: from emarefirewall import FirewallManager
"""

from typing import Any

from emarefirewall.manager import FirewallManager


def _make_fw(ssh_mgr) -> FirewallManager:
    """ssh_mgr nesnesinden FirewallManager oluşturur."""
    return FirewallManager(ssh_executor=lambda sid, cmd: ssh_mgr.execute_command(sid, cmd))


def get_status(ssh_mgr, server_id: str) -> dict:
    """Güvenlik duvarı tam durumunu döndürür."""
    result = {
        "type": None,
        "active": False,
        "default_incoming": "deny",
        "default_outgoing": "allow",
        "rules": [],
        "zones": [],
        "active_zone": "",
        "services": [],
        "ports": [],
        "rich_rules": [],
        "blocked_ips": [],
        "forward_ports": [],
        "masquerade": False,
        "interfaces": [],
        "message": "",
    }

    # ── UFW ──
    ok, out, err = _exec(ssh_mgr, server_id, "which ufw 2>/dev/null && ufw status verbose 2>/dev/null | head -80")
    if ok and out and "ufw" in out:
        result["type"] = "ufw"
        if "Status: active" in out:
            result["active"] = True
        elif "Status: inactive" in out:
            result["active"] = False
        if "Default:" in out:
            if "incoming (deny)" in out or "Incoming: deny" in out:
                result["default_incoming"] = "deny"
            elif "incoming (allow)" in out or "Incoming: allow" in out:
                result["default_incoming"] = "allow"
            if "outgoing (allow)" in out or "Outgoing: allow" in out:
                result["default_outgoing"] = "allow"
        ok2, out2, _ = _exec(ssh_mgr, server_id, "ufw status numbered 2>/dev/null")
        if ok2 and out2:
            for line in out2.split("\n"):
                line = line.strip()
                m = re.match(r"\[\s*(\d+)\]\s+(.+)", line)
                if m:
                    rule_text = m.group(2).strip()
                    result["rules"].append({
                        "index": int(m.group(1)),
                        "rule": rule_text,
                        "type": _classify_ufw_rule(rule_text),
                    })
        return result

    # ── firewalld ──
    ok, out, err = _exec(ssh_mgr, server_id, "which firewall-cmd 2>/dev/null && firewall-cmd --state 2>/dev/null")
    if ok and out and "running" in out:
        result["type"] = "firewalld"
        result["active"] = True
        _parse_firewalld_full(ssh_mgr, server_id, result)
        return result

    result["message"] = "Bu sunucuda UFW veya firewalld bulunamadı."
    return result


def _classify_ufw_rule(rule_text: str) -> str:
    """UFW kuralını sınıflandır: port | service | ip_block | forward"""
    if "DENY" in rule_text and "from" in rule_text.lower():
        return "ip_block"
    if "ALLOW" in rule_text or "DENY" in rule_text:
        return "port"
    return "other"


def _parse_firewalld_full(ssh_mgr, server_id: str, result: dict):
    """firewalld tam durumunu parse et."""
    # Aktif zone
    ok, out, _ = _exec(ssh_mgr, server_id, "firewall-cmd --get-active-zones 2>/dev/null")
    if ok and out:
        for line in out.split("\n"):
            line = line.strip()
            if line and not line.startswith("interfaces:") and not line.startswith("sources:"):
                result["active_zone"] = line
                break

    # Tüm zone'lar
    ok, out, _ = _exec(ssh_mgr, server_id, "firewall-cmd --get-zones 2>/dev/null")
    if ok and out:
        result["zones"] = [z.strip() for z in out.split() if z.strip()]

    # Detaylı bilgi
    ok, out, _ = _exec(ssh_mgr, server_id, "firewall-cmd --list-all 2>/dev/null")
    if ok and out:
        rules = []
        idx = 0
        for line in out.split("\n"):
            stripped = line.strip()
            if stripped.startswith("services:"):
                svcs = stripped.replace("services:", "").strip()
                if svcs:
                    result["services"] = svcs.split()
                    for svc in result["services"]:
                        idx += 1
                        rules.append({"index": idx, "rule": f"service {svc}", "type": "service"})
            elif stripped.startswith("ports:"):
                ports = stripped.replace("ports:", "").strip()
                if ports:
                    result["ports"] = ports.split()
                    for p in result["ports"]:
                        idx += 1
                        rules.append({"index": idx, "rule": f"port {p}", "type": "port"})
            elif stripped.startswith("rich rules:"):
                pass  # rich rule'lar aşağıda
            elif stripped.startswith("rule "):
                idx += 1
                result["rich_rules"].append(stripped)
                rules.append({"index": idx, "rule": stripped, "type": "rich_rule"})
            elif stripped.startswith("forward-ports:"):
                fwd = stripped.replace("forward-ports:", "").strip()
                if fwd:
                    for fp in fwd.split():
                        idx += 1
                        result["forward_ports"].append(fp)
                        rules.append({"index": idx, "rule": f"forward {fp}", "type": "forward"})
            elif stripped.startswith("masquerade:"):
                result["masquerade"] = "yes" in stripped
            elif stripped.startswith("interfaces:"):
                ifaces = stripped.replace("interfaces:", "").strip()
                if ifaces:
                    result["interfaces"] = ifaces.split()
        result["rules"] = rules

    # Rich rule'ları ayrıca çek (detaylı)
    ok, out, _ = _exec(ssh_mgr, server_id, "firewall-cmd --list-rich-rules 2>/dev/null")
    if ok and out:
        rich = [r.strip() for r in out.split("\n") if r.strip()]
        if rich and not result["rich_rules"]:
            result["rich_rules"] = rich
            for r in rich:
                result["rules"].append({
                    "index": len(result["rules"]) + 1,
                    "rule": r,
                    "type": "rich_rule",
                })


# ─────────────────── ETKİNLEŞTİR / KAPAT ───────────────────

def enable_firewall(ssh_mgr, server_id: str) -> tuple[bool, str]:
    """Güvenlik duvarını etkinleştirir."""
    fw_type = _detect_type(ssh_mgr, server_id)
    if fw_type == "ufw":
        ok, out, err = _exec(ssh_mgr, server_id, "echo 'y' | sudo ufw enable 2>&1")
        if ok or "already active" in (out + err).lower():
            return True, "UFW etkinleştirildi."
        return False, (out + " " + err).strip() or "UFW etkinleştirilemedi"
    if fw_type == "firewalld":
        ok, out, err = _exec(ssh_mgr, server_id,
                              "sudo systemctl start firewalld 2>&1 && sudo systemctl enable firewalld 2>&1")
        return ok, (out + " " + err).strip() or "firewalld başlatıldı."
    return False, "Desteklenen güvenlik duvarı bulunamadı."


def disable_firewall(ssh_mgr, server_id: str) -> tuple[bool, str]:
    """Güvenlik duvarını devre dışı bırakır."""
    fw_type = _detect_type(ssh_mgr, server_id)
    if fw_type == "ufw":
        ok, out, err = _exec(ssh_mgr, server_id, "sudo ufw disable 2>&1")
        return ok, (out + " " + err).strip() or "UFW devre dışı bırakıldı."
    if fw_type == "firewalld":
        ok, out, err = _exec(ssh_mgr, server_id,
                              "sudo systemctl stop firewalld 2>&1 && sudo systemctl disable firewalld 2>&1")
        return ok, (out + " " + err).strip()
    return False, "Desteklenen güvenlik duvarı bulunamadı."


# ─────────────────── PORT / SERVİS KURAL EKLE ───────────────────

def add_rule(
    ssh_mgr, server_id: str, direction: str, action: str,
    port: str, protocol: str = "tcp", from_ip: str = "",
) -> tuple[bool, str]:
    """Port/servis kuralı ekler."""
    fw_type = _detect_type(ssh_mgr, server_id)
    if not fw_type:
        return False, "Desteklenen güvenlik duvarı bulunamadı."
    port = (port or "").strip()
    if not port:
        return False, "Port veya servis belirtin (örn: 22, 80/tcp, 443)."

    if fw_type == "ufw":
        rule_spec = port if "/" in port else f"{port}/{protocol}"
        from_part = f" from {from_ip.strip()}" if from_ip and from_ip.strip() else ""
        cmd = f"sudo ufw {action} {rule_spec}{from_part} 2>&1"
        ok, out, err = _exec(ssh_mgr, server_id, cmd)
        msg = (out + " " + err).strip()
        if ok or "existing" in msg.lower() or "added" in msg.lower():
            return True, msg or "Kural eklendi."
        return False, msg

    if fw_type == "firewalld":
        port_proto = port if "/" in port else f"{port}/{protocol}"
        cmd = f"sudo firewall-cmd --permanent --add-port={port_proto} 2>&1"
        ok, out, err = _exec(ssh_mgr, server_id, cmd)
        if ok:
            _exec(ssh_mgr, server_id, "sudo firewall-cmd --reload 2>&1")
        msg = (out + " " + err).strip()
        return ok, msg or "Kural eklendi."
    return False, "Desteklenmiyor."


def add_service(ssh_mgr, server_id: str, service: str) -> tuple[bool, str]:
    """Servis kuralı ekler (http, https, ssh, ftp vs.)."""
    fw_type = _detect_type(ssh_mgr, server_id)
    service = (service or "").strip()
    if not service:
        return False, "Servis adı belirtin."

    if fw_type == "ufw":
        ok, out, err = _exec(ssh_mgr, server_id, f"sudo ufw allow {service} 2>&1")
        msg = (out + " " + err).strip()
        return ok or "added" in msg.lower(), msg or "Servis eklendi."

    if fw_type == "firewalld":
        cmd = f"sudo firewall-cmd --permanent --add-service={service} 2>&1"
        ok, out, err = _exec(ssh_mgr, server_id, cmd)
        if ok:
            _exec(ssh_mgr, server_id, "sudo firewall-cmd --reload 2>&1")
        msg = (out + " " + err).strip()
        return ok, msg or "Servis eklendi."
    return False, "Desteklenen güvenlik duvarı bulunamadı."


def remove_service(ssh_mgr, server_id: str, service: str) -> tuple[bool, str]:
    """Servis kuralını kaldırır."""
    fw_type = _detect_type(ssh_mgr, server_id)
    service = (service or "").strip()
    if not service:
        return False, "Servis adı belirtin."

    if fw_type == "ufw":
        ok, out, err = _exec(ssh_mgr, server_id, f"sudo ufw delete allow {service} 2>&1")
        return ok, (out + " " + err).strip() or "Servis kaldırıldı."

    if fw_type == "firewalld":
        cmd = f"sudo firewall-cmd --permanent --remove-service={service} 2>&1"
        ok, out, err = _exec(ssh_mgr, server_id, cmd)
        if ok:
            _exec(ssh_mgr, server_id, "sudo firewall-cmd --reload 2>&1")
        return ok, (out + " " + err).strip() or "Servis kaldırıldı."
    return False, "Desteklenen güvenlik duvarı bulunamadı."


# ─────────────────── KURAL SİL ───────────────────

def delete_rule(ssh_mgr, server_id: str, rule_index: int) -> tuple[bool, str]:
    """Numaraya göre kural siler."""
    status = get_status(ssh_mgr, server_id)
    if not status["type"]:
        return False, status.get("message", "Durum bilinmiyor.")

    if status["type"] == "ufw":
        ok, out, err = _exec(ssh_mgr, server_id, f"echo 'y' | sudo ufw delete {rule_index} 2>&1")
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
            port_proto = rule_str.replace("port", "").strip()
            cmd = f"sudo firewall-cmd --permanent --remove-port={port_proto} 2>&1"
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

        ok, out, err = _exec(ssh_mgr, server_id, cmd)
        if ok:
            _exec(ssh_mgr, server_id, "sudo firewall-cmd --reload 2>&1")
        return ok, (out + " " + err).strip() or "Kural silindi."
    return False, "Desteklenmiyor."


# ─────────────────── IP ENGELLEME ───────────────────

def block_ip(ssh_mgr, server_id: str, ip: str, reason: str = "") -> tuple[bool, str]:
    """IP adresini engeller (drop)."""
    fw_type = _detect_type(ssh_mgr, server_id)
    ip = (ip or "").strip()
    if not ip:
        return False, "IP adresi belirtin."

    if fw_type == "ufw":
        ok, out, err = _exec(ssh_mgr, server_id, f"sudo ufw deny from {ip} 2>&1")
        msg = (out + " " + err).strip()
        return ok or "added" in msg.lower(), msg or f"{ip} engellendi."

    if fw_type == "firewalld":
        rich = f"rule family='ipv4' source address='{ip}' drop"
        cmd = f"sudo firewall-cmd --permanent --add-rich-rule=\"{rich}\" 2>&1"
        ok, out, err = _exec(ssh_mgr, server_id, cmd)
        if ok:
            _exec(ssh_mgr, server_id, "sudo firewall-cmd --reload 2>&1")
        msg = (out + " " + err).strip()
        return ok, msg or f"{ip} engellendi."
    return False, "Desteklenen güvenlik duvarı bulunamadı."


def unblock_ip(ssh_mgr, server_id: str, ip: str) -> tuple[bool, str]:
    """IP engelini kaldırır."""
    fw_type = _detect_type(ssh_mgr, server_id)
    ip = (ip or "").strip()
    if not ip:
        return False, "IP adresi belirtin."

    if fw_type == "ufw":
        ok, out, err = _exec(ssh_mgr, server_id, f"sudo ufw delete deny from {ip} 2>&1")
        return ok, (out + " " + err).strip() or f"{ip} engeli kaldırıldı."

    if fw_type == "firewalld":
        rich = f"rule family='ipv4' source address='{ip}' drop"
        cmd = f"sudo firewall-cmd --permanent --remove-rich-rule=\"{rich}\" 2>&1"
        ok, out, err = _exec(ssh_mgr, server_id, cmd)
        if ok:
            _exec(ssh_mgr, server_id, "sudo firewall-cmd --reload 2>&1")
        return ok, (out + " " + err).strip() or f"{ip} engeli kaldırıldı."
    return False, "Desteklenen güvenlik duvarı bulunamadı."


def get_blocked_ips(ssh_mgr, server_id: str) -> list[dict]:
    """Engelli IP'leri listeler."""
    fw_type = _detect_type(ssh_mgr, server_id)
    blocked = []

    if fw_type == "ufw":
        ok, out, _ = _exec(ssh_mgr, server_id, "ufw status numbered 2>/dev/null")
        if ok and out:
            for line in out.split("\n"):
                m = re.match(r"\[\s*(\d+)\]\s+.*DENY\s+IN\s+(.+)", line.strip())
                if m:
                    blocked.append({"index": int(m.group(1)), "ip": m.group(2).strip()})

    elif fw_type == "firewalld":
        ok, out, _ = _exec(ssh_mgr, server_id, "firewall-cmd --list-rich-rules 2>/dev/null")
        if ok and out:
            idx = 0
            for line in out.split("\n"):
                line = line.strip()
                # rule family="ipv4" source address="1.2.3.4" drop
                m = re.search(r"source address=['\"]([^'\"]+)['\"].*drop", line)
                if m:
                    idx += 1
                    blocked.append({"index": idx, "ip": m.group(1), "rule": line})
    return blocked


# ─────────────────── PORT YÖNLENDİRME ───────────────────

def add_port_forward(
    ssh_mgr, server_id: str, port: str, to_port: str,
    to_addr: str = "", protocol: str = "tcp"
) -> tuple[bool, str]:
    """Port yönlendirme kuralı ekler."""
    fw_type = _detect_type(ssh_mgr, server_id)
    port = (port or "").strip()
    to_port = (to_port or "").strip()
    if not port or not to_port:
        return False, "Kaynak port ve hedef port belirtin."

    if fw_type == "ufw":
        # UFW ile port forwarding: /etc/ufw/before.rules'a yazılır, basit değil
        return False, "UFW ile port yönlendirme desteklenmiyor. firewalld kullanın."

    if fw_type == "firewalld":
        to_part = f":toport={to_port}"
        if to_addr and to_addr.strip():
            to_part += f":toaddr={to_addr.strip()}"
        cmd = (f"sudo firewall-cmd --permanent "
               f"--add-forward-port=port={port}:proto={protocol}{to_part} 2>&1")
        ok, out, err = _exec(ssh_mgr, server_id, cmd)
        if ok:
            # Masquerade gerekebilir
            _exec(ssh_mgr, server_id, "sudo firewall-cmd --permanent --add-masquerade 2>&1")
            _exec(ssh_mgr, server_id, "sudo firewall-cmd --reload 2>&1")
        msg = (out + " " + err).strip()
        return ok, msg or "Port yönlendirme eklendi."
    return False, "Desteklenen güvenlik duvarı bulunamadı."


def remove_port_forward(
    ssh_mgr, server_id: str, port: str, to_port: str,
    to_addr: str = "", protocol: str = "tcp"
) -> tuple[bool, str]:
    """Port yönlendirme kuralını kaldırır."""
    fw_type = _detect_type(ssh_mgr, server_id)
    if fw_type != "firewalld":
        return False, "Sadece firewalld destekleniyor."

    to_part = f":toport={to_port}"
    if to_addr and to_addr.strip():
        to_part += f":toaddr={to_addr.strip()}"
    cmd = (f"sudo firewall-cmd --permanent "
           f"--remove-forward-port=port={port}:proto={protocol}{to_part} 2>&1")
    ok, out, err = _exec(ssh_mgr, server_id, cmd)
    if ok:
        _exec(ssh_mgr, server_id, "sudo firewall-cmd --reload 2>&1")
    return ok, (out + " " + err).strip() or "Port yönlendirme kaldırıldı."


# ─────────────────── ZONE YÖNETİMİ ───────────────────

def get_zones(ssh_mgr, server_id: str) -> dict[str, Any]:
    """Tüm zone'ları ve aktif zone'u döndürür."""
    fw_type = _detect_type(ssh_mgr, server_id)
    if fw_type != "firewalld":
        return {"zones": [], "active": "", "message": "Zone yönetimi sadece firewalld'de desteklenir."}

    ok, out, _ = _exec(ssh_mgr, server_id, "firewall-cmd --get-zones 2>/dev/null")
    zones = out.split() if ok and out else []

    ok2, out2, _ = _exec(ssh_mgr, server_id, "firewall-cmd --get-active-zones 2>/dev/null")
    active = ""
    if ok2 and out2:
        for line in out2.split("\n"):
            line = line.strip()
            if line and not line.startswith("interfaces:") and not line.startswith("sources:"):
                active = line
                break

    ok3, out3, _ = _exec(ssh_mgr, server_id, "firewall-cmd --get-default-zone 2>/dev/null")
    default = out3.strip() if ok3 and out3 else ""

    return {"zones": zones, "active": active, "default": default}


def set_default_zone(ssh_mgr, server_id: str, zone: str) -> tuple[bool, str]:
    """Varsayılan zone'u değiştirir."""
    fw_type = _detect_type(ssh_mgr, server_id)
    if fw_type != "firewalld":
        return False, "Zone yönetimi sadece firewalld'de desteklenir."

    zone = (zone or "").strip()
    if not zone:
        return False, "Zone adı belirtin."

    ok, out, err = _exec(ssh_mgr, server_id, f"sudo firewall-cmd --set-default-zone={zone} 2>&1")
    return ok, (out + " " + err).strip() or f"Varsayılan zone: {zone}"


def get_zone_detail(ssh_mgr, server_id: str, zone: str) -> dict[str, Any]:
    """Belirli zone'un detaylarını döndürür."""
    fw_type = _detect_type(ssh_mgr, server_id)
    if fw_type != "firewalld":
        return {"error": "Sadece firewalld desteklenir."}

    ok, out, _ = _exec(ssh_mgr, server_id, f"firewall-cmd --zone={zone} --list-all 2>/dev/null")
    if not ok or not out:
        return {"error": f"Zone '{zone}' bilgisi alınamadı."}

    detail = {"zone": zone, "services": [], "ports": [], "rich_rules": [],
              "interfaces": [], "masquerade": False, "forward_ports": []}
    for line in out.split("\n"):
        s = line.strip()
        if s.startswith("services:"):
            svcs = s.replace("services:", "").strip()
            detail["services"] = svcs.split() if svcs else []
        elif s.startswith("ports:"):
            ports = s.replace("ports:", "").strip()
            detail["ports"] = ports.split() if ports else []
        elif s.startswith("interfaces:"):
            ifaces = s.replace("interfaces:", "").strip()
            detail["interfaces"] = ifaces.split() if ifaces else []
        elif s.startswith("masquerade:"):
            detail["masquerade"] = "yes" in s
        elif s.startswith("forward-ports:"):
            fwd = s.replace("forward-ports:", "").strip()
            detail["forward_ports"] = fwd.split() if fwd else []
        elif s.startswith("rule "):
            detail["rich_rules"].append(s)
    return detail


# ─────────────────── RICH RULE (GELİŞMİŞ KURAL) ───────────────────

def add_rich_rule(ssh_mgr, server_id: str, rule: str) -> tuple[bool, str]:
    """Rich rule ekler (firewalld)."""
    fw_type = _detect_type(ssh_mgr, server_id)
    rule = (rule or "").strip()
    if not rule:
        return False, "Kural belirtin."

    if fw_type == "ufw":
        return False, "Rich rule sadece firewalld'de desteklenir."
    if fw_type == "firewalld":
        cmd = f"sudo firewall-cmd --permanent --add-rich-rule='{rule}' 2>&1"
        ok, out, err = _exec(ssh_mgr, server_id, cmd)
        if ok:
            _exec(ssh_mgr, server_id, "sudo firewall-cmd --reload 2>&1")
        msg = (out + " " + err).strip()
        return ok, msg or "Rich rule eklendi."
    return False, "Desteklenen güvenlik duvarı bulunamadı."


def remove_rich_rule(ssh_mgr, server_id: str, rule: str) -> tuple[bool, str]:
    """Rich rule kaldırır (firewalld)."""
    fw_type = _detect_type(ssh_mgr, server_id)
    if fw_type != "firewalld":
        return False, "Rich rule sadece firewalld'de desteklenir."

    rule = (rule or "").strip()
    if not rule:
        return False, "Kural belirtin."

    cmd = f"sudo firewall-cmd --permanent --remove-rich-rule='{rule}' 2>&1"
    ok, out, err = _exec(ssh_mgr, server_id, cmd)
    if ok:
        _exec(ssh_mgr, server_id, "sudo firewall-cmd --reload 2>&1")
    return ok, (out + " " + err).strip() or "Rich rule kaldırıldı."


# ─────────────────── FAIL2BAN ENTEGRASYONU ───────────────────

def get_fail2ban_status(ssh_mgr, server_id: str) -> dict[str, Any]:
    """Fail2ban durumunu döndürür."""
    result = {"installed": False, "active": False, "jails": [], "banned_ips": {}}

    ok, out, _ = _exec(ssh_mgr, server_id, "which fail2ban-client 2>/dev/null")
    if not ok or not out or "fail2ban" not in out:
        return result
    result["installed"] = True

    ok, out, _ = _exec(ssh_mgr, server_id, "systemctl is-active fail2ban 2>/dev/null")
    if ok and out and "active" in out:
        result["active"] = True

    ok, out, _ = _exec(ssh_mgr, server_id, "sudo fail2ban-client status 2>/dev/null")
    if ok and out:
        m = re.search(r"Jail list:\s+(.+)", out)
        if m:
            result["jails"] = [j.strip() for j in m.group(1).split(",") if j.strip()]

    # Her jail'in detayı
    for jail in result["jails"]:
        ok, out, _ = _exec(ssh_mgr, server_id, f"sudo fail2ban-client status {jail} 2>/dev/null")
        if ok and out:
            info = {"currently_banned": 0, "total_banned": 0, "banned_list": []}
            m1 = re.search(r"Currently banned:\s+(\d+)", out)
            if m1:
                info["currently_banned"] = int(m1.group(1))
            m2 = re.search(r"Total banned:\s+(\d+)", out)
            if m2:
                info["total_banned"] = int(m2.group(1))
            m3 = re.search(r"Banned IP list:\s+(.+)", out)
            if m3:
                info["banned_list"] = m3.group(1).strip().split()
            result["banned_ips"][jail] = info
    return result


def fail2ban_unban(ssh_mgr, server_id: str, jail: str, ip: str) -> tuple[bool, str]:
    """Fail2ban'dan IP'yi unban eder."""
    ip = (ip or "").strip()
    jail = (jail or "").strip()
    if not ip or not jail:
        return False, "Jail ve IP belirtin."

    cmd = f"sudo fail2ban-client set {jail} unbanip {ip} 2>&1"
    ok, out, err = _exec(ssh_mgr, server_id, cmd)
    return ok, (out + " " + err).strip() or f"{ip} unban edildi."


def fail2ban_ban(ssh_mgr, server_id: str, jail: str, ip: str) -> tuple[bool, str]:
    """Fail2ban ile IP'yi ban eder."""
    ip = (ip or "").strip()
    jail = (jail or "").strip()
    if not ip or not jail:
        return False, "Jail ve IP belirtin."

    cmd = f"sudo fail2ban-client set {jail} banip {ip} 2>&1"
    ok, out, err = _exec(ssh_mgr, server_id, cmd)
    return ok, (out + " " + err).strip() or f"{ip} ban edildi."


# ─────────────────── BAĞLANTI İZLEME ───────────────────

def get_connections(ssh_mgr, server_id: str, limit: int = 50) -> list[dict]:
    """Aktif ağ bağlantılarını listeler (ss/netstat)."""
    connections = []
    cmd = f"ss -tunap 2>/dev/null | head -{limit + 1}"
    ok, out, _ = _exec(ssh_mgr, server_id, cmd)
    if not ok or not out:
        return connections

    lines = out.strip().split("\n")
    for line in lines[1:]:  # Header atla
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


def get_connection_stats(ssh_mgr, server_id: str) -> dict[str, Any]:
    """Bağlantı istatistiklerini döndürür."""
    stats = {"total": 0, "established": 0, "listening": 0, "time_wait": 0,
             "close_wait": 0, "by_port": {}, "by_ip": {}}

    cmd = "ss -tan 2>/dev/null | tail -n +2"
    ok, out, _ = _exec(ssh_mgr, server_id, cmd)
    if not ok or not out:
        return stats

    for line in out.strip().split("\n"):
        if not line.strip():
            continue
        stats["total"] += 1
        parts = line.split()
        if len(parts) >= 1:
            state = parts[0].upper()
            if "ESTAB" in state:
                stats["established"] += 1
            elif "LISTEN" in state:
                stats["listening"] += 1
            elif "TIME" in state:
                stats["time_wait"] += 1
            elif "CLOSE" in state:
                stats["close_wait"] += 1

        # Port bazlı
        if len(parts) >= 4:
            local = parts[3]
            port = local.rsplit(":", 1)[-1] if ":" in local else ""
            if port.isdigit():
                stats["by_port"][port] = stats["by_port"].get(port, 0) + 1

        # IP bazlı
        if len(parts) >= 5:
            peer = parts[4]
            ip = peer.rsplit(":", 1)[0] if ":" in peer else peer
            ip = ip.strip("[]")
            if ip and ip != "*" and ip != "0.0.0.0":
                stats["by_ip"][ip] = stats["by_ip"].get(ip, 0) + 1

    # En çok bağlanan IP'ler (top 10)
    stats["top_ips"] = sorted(stats["by_ip"].items(), key=lambda x: x[1], reverse=True)[:10]
    stats["top_ports"] = sorted(stats["by_port"].items(), key=lambda x: x[1], reverse=True)[:10]

    return stats


# ─────────────────── GÜVENLİK TARAMASİ ───────────────────

def security_scan(ssh_mgr, server_id: str) -> dict[str, Any]:
    """Temel güvenlik taraması yapar."""
    scan = {
        "timestamp": datetime.utcnow().isoformat(),
        "score": 100,
        "findings": [],
        "recommendations": [],
    }

    # 1. Firewall aktif mi?
    status = get_status(ssh_mgr, server_id)
    if not status["active"]:
        scan["score"] -= 30
        scan["findings"].append({"severity": "critical", "title": "Güvenlik duvarı kapalı",
                                  "detail": "Sunucuda güvenlik duvarı aktif değil."})
        scan["recommendations"].append("Güvenlik duvarını hemen etkinleştirin.")

    # 2. SSH root login?
    ok, out, _ = _exec(ssh_mgr, server_id, "grep -i '^PermitRootLogin' /etc/ssh/sshd_config 2>/dev/null")
    if ok and out and "yes" in out.lower():
        scan["score"] -= 15
        scan["findings"].append({"severity": "high", "title": "Root SSH izinli",
                                  "detail": "PermitRootLogin = yes"})
        scan["recommendations"].append("PermitRootLogin'i 'no' veya 'prohibit-password' yapın.")

    # 3. SSH password auth?
    ok, out, _ = _exec(ssh_mgr, server_id, "grep -i '^PasswordAuthentication' /etc/ssh/sshd_config 2>/dev/null")
    if ok and out and "yes" in out.lower():
        scan["score"] -= 10
        scan["findings"].append({"severity": "medium", "title": "Parola ile SSH izinli",
                                  "detail": "PasswordAuthentication = yes"})
        scan["recommendations"].append("Key-based auth kullanın, parola auth kapatın.")

    # 4. Fail2ban aktif mi?
    f2b = get_fail2ban_status(ssh_mgr, server_id)
    if not f2b["installed"]:
        scan["score"] -= 10
        scan["findings"].append({"severity": "medium", "title": "Fail2ban kurulu değil",
                                  "detail": "Brute-force koruması yok."})
        scan["recommendations"].append("Fail2ban kurun: yum install fail2ban / apt install fail2ban")
    elif not f2b["active"]:
        scan["score"] -= 10
        scan["findings"].append({"severity": "medium", "title": "Fail2ban kapalı",
                                  "detail": "Fail2ban kurulu ama çalışmıyor."})
        scan["recommendations"].append("Fail2ban'ı başlatın: systemctl start fail2ban")

    # 5. Açık tehlikeli portlar (telnet, ftp, mysql vs.)
    risky_ports = {"23": "Telnet", "21": "FTP", "3306": "MySQL", "5432": "PostgreSQL",
                   "6379": "Redis", "27017": "MongoDB", "9200": "Elasticsearch"}
    ok, out, _ = _exec(ssh_mgr, server_id, "ss -tlnp 2>/dev/null | awk '{print $4}'")
    if ok and out:
        for line in out.split("\n"):
            port = line.rsplit(":", 1)[-1].strip() if ":" in line else ""
            if port in risky_ports:
                scan["score"] -= 5
                scan["findings"].append({
                    "severity": "medium",
                    "title": f"{risky_ports[port]} portu açık ({port})",
                    "detail": f"Port {port} ({risky_ports[port]}) dışarıdan erişilebilir.",
                })
                scan["recommendations"].append(
                    f"Port {port}'i sadece localhost'a bağlayın veya firewall'dan kapatın.")

    # 6. Kernel güncel mi?
    ok, out, _ = _exec(ssh_mgr, server_id, "needs-restarting -r 2>/dev/null || echo 'n/a'")
    if ok and out and "Reboot is required" in out:
        scan["score"] -= 5
        scan["findings"].append({"severity": "low", "title": "Reboot gerekli",
                                  "detail": "Kernel güncellemesi reboot bekliyor."})
        scan["recommendations"].append("Sunucuyu yeniden başlatın.")

    scan["score"] = max(0, scan["score"])
    return scan


# ─────────────────── GEO-BLOCK ───────────────────

def geo_block_country(ssh_mgr, server_id: str, country_code: str) -> tuple[bool, str]:
    """Ülke bazlı engelleme (ipset + firewalld rich rule)."""
    fw_type = _detect_type(ssh_mgr, server_id)
    cc = (country_code or "").strip().upper()
    if not cc or len(cc) != 2:
        return False, "Geçerli 2 harfli ülke kodu girin (örn: CN, RU)."

    if fw_type != "firewalld":
        return False, "Geo-block şu an sadece firewalld'de destekleniyor."

    # ipset oluştur ve IP listesini indir
    cmds = [
        f"sudo ipset create geoblock_{cc} hash:net 2>/dev/null || true",
        f"sudo wget -qO /tmp/{cc}.zone https://www.ipdeny.com/ipblocks/data/countries/{cc.lower()}.zone 2>/dev/null",
        f"sudo bash -c 'for ip in $(cat /tmp/{cc}.zone 2>/dev/null); do ipset add geoblock_{cc} $ip 2>/dev/null; done'",
        f"sudo firewall-cmd --permanent --add-rich-rule=\"rule source ipset='geoblock_{cc}' drop\" 2>&1",
        "sudo firewall-cmd --reload 2>&1",
    ]
    for cmd in cmds:
        ok, out, err = _exec(ssh_mgr, server_id, cmd)
    return True, f"{cc} ülkesi engellendi (ipset: geoblock_{cc})."
