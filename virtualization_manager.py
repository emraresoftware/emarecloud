"""
Sanal Makine Yönetimi - LXD (Linux Containers) ile ana sunucuda onlarca sanal makine.
LXD kurulu sunucularda container listeleme, oluşturma, başlatma, durdurma, silme.
"""

import json
import re
from typing import Any


def _exec(ssh_mgr, server_id: str, command: str, timeout: int = 60) -> tuple[bool, str, str]:
    return ssh_mgr.execute_command(server_id, command, timeout=timeout)


def is_lxd_available(ssh_mgr, server_id: str) -> tuple[bool, str]:
    """LXD kurulu mu kontrol eder."""
    ok, out, err = _exec(ssh_mgr, server_id, "which lxc 2>/dev/null && lxc version 2>/dev/null | head -1")
    if ok and out and "lxc" in out.lower():
        return True, out.strip()
    return False, "LXD (lxc) bulunamadı. Uygulama Pazarından 'LXD' kurun."


def list_containers(ssh_mgr, server_id: str) -> dict[str, Any]:
    """
    Tüm container'ları listeler. LXD yoksa { available: False } döner.
    """
    result = {"available": False, "message": "", "version": "", "containers": []}
    ok, msg = is_lxd_available(ssh_mgr, server_id)
    if not ok:
        result["message"] = msg
        return result
    result["available"] = True
    result["version"] = (msg or "").strip()

    # lxc list --format json (LXD 4+)
    ok, out, err = _exec(ssh_mgr, server_id, "lxc list --format json 2>/dev/null")
    if ok and out.strip():
        try:
            data = json.loads(out)
            for item in data:
                name = item.get("name", "")
                state = item.get("status") or item.get("state", "UNKNOWN")
                config = item.get("state", {}) or item.get("State", {}) or {}
                network = config.get("network", {}) or {}
                eth0 = network.get("eth0", {}) or network.get("eno1", {}) or {}
                addrs = eth0.get("addresses", []) or []
                ipv4 = ""
                for a in addrs:
                    if a.get("family") == "inet" and a.get("scope") == "global":
                        ipv4 = a.get("address", "")
                        break
                result["containers"].append({
                    "name": name,
                    "state": state.upper(),
                    "ipv4": ipv4,
                    "type": item.get("type", "container"),
                })
            return result
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback: lxc list (metin çıktısı)
    ok, out, err = _exec(ssh_mgr, server_id, "lxc list 2>/dev/null")
    if ok and out:
        # "+------+---------+------+..." then "| NAME | STATE  | ..."
        lines = out.strip().split("\n")
        for line in lines[2:]:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 2:
                result["containers"].append({
                    "name": parts[0],
                    "state": parts[1].upper() if len(parts) > 1 else "UNKNOWN",
                    "ipv4": parts[2] if len(parts) > 2 else "",
                    "type": "container",
                })
    return result


def get_images(ssh_mgr, server_id: str) -> list[str]:
    """Kullanılabilir LXD image'ları (kısa liste)."""
    ok, _ = is_lxd_available(ssh_mgr, server_id)
    if not ok:
        return []
    # Önceden bilinen sık kullanılan image'lar + sunucudaki listeyi al
    ok, out, err = _exec(ssh_mgr, server_id,
        r"lxc image list images: 2>/dev/null | head -30 | awk '{print $2}' | grep -E '^\|' | sed 's/|//g' | tr -d ' ' | grep -v '^$'")
    images = []
    if ok and out:
        for line in out.strip().split("\n"):
            alias = line.strip()
            if alias and "|" not in alias:
                images.append(alias)
    default = ["ubuntu:22.04", "ubuntu:20.04", "debian:12", "debian:11", "alpine:edge", "alpine:3.19"]
    for d in default:
        if d not in images:
            images.insert(0, d)
    return images[:20]


def create_container(
    ssh_mgr,
    server_id: str,
    name: str,
    image: str = "ubuntu:22.04",
    memory: str = "1GB",
    cpu: str = "1",
    disk: str = "10GB",
) -> tuple[bool, str]:
    """
    Yeni container oluşturur. İsim sadece harf/rakam/- kabul edilir.
    """
    name = (name or "").strip()
    if not name or not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$", name):
        return False, "Geçerli bir isim girin (harf, rakam, tire, alt çizgi)."
    ok, _ = is_lxd_available(ssh_mgr, server_id)
    if not ok:
        return False, "LXD kurulu değil."
    # lxc init IMAGE NAME
    cmd = f"lxc init {image} {name} 2>&1"
    ok, out, err = _exec(ssh_mgr, server_id, cmd, timeout=120)
    if not ok:
        return False, (out + " " + err).strip() or "Container oluşturulamadı."
    # Limitler (opsiyonel)
    if memory or cpu or disk:
        try:
            if memory:
                _exec(ssh_mgr, server_id, f"lxc config set {name} limits.memory {memory} 2>&1")
            if cpu:
                _exec(ssh_mgr, server_id, f"lxc config set {name} limits.cpu {cpu} 2>&1")
        except Exception:
            pass
    return True, f"Container '{name}' oluşturuldu. Başlatmak için Start'a tıklayın."


def start_container(ssh_mgr, server_id: str, name: str) -> tuple[bool, str]:
    name = (name or "").strip()
    if not name:
        return False, "İsim gerekli."
    ok, out, err = _exec(ssh_mgr, server_id, f"lxc start {name} 2>&1")
    if ok:
        return True, f"'{name}' başlatıldı."
    return False, (out + " " + err).strip()


def stop_container(ssh_mgr, server_id: str, name: str, force: bool = False) -> tuple[bool, str]:
    name = (name or "").strip()
    if not name:
        return False, "İsim gerekli."
    cmd = f"lxc stop {name} --force 2>&1" if force else f"lxc stop {name} 2>&1"
    ok, out, err = _exec(ssh_mgr, server_id, cmd, timeout=30)
    if ok:
        return True, f"'{name}' durduruldu."
    return False, (out + " " + err).strip()


def delete_container(ssh_mgr, server_id: str, name: str, force: bool = True) -> tuple[bool, str]:
    name = (name or "").strip()
    if not name:
        return False, "İsim gerekli."
    cmd = f"lxc delete {name} --force 2>&1" if force else f"lxc delete {name} 2>&1"
    ok, out, err = _exec(ssh_mgr, server_id, cmd, timeout=30)
    if ok:
        return True, f"'{name}' silindi."
    return False, (out + " " + err).strip()


def exec_in_container(ssh_mgr, server_id: str, name: str, command: str, timeout: int = 30) -> tuple[bool, str, str]:
    """Container içinde komut çalıştırır. lxc exec NAME -- bash -c '...'"""
    name = (name or "").strip()
    if not name:
        return False, "", "İsim gerekli."
    if not (command or "").strip():
        return False, "", "Komut gerekli."
    # Kabuk özel karakterlerinden kaçınmak için base64 ile gönder
    import base64
    cmd_b64 = base64.b64encode(command.strip().encode("utf-8")).decode("ascii")
    full = f"lxc exec {name} -- bash -c 'echo {cmd_b64} | base64 -d | bash' 2>&1"
    ok, out, err = _exec(ssh_mgr, server_id, full, timeout=timeout)
    return ok, out, err
