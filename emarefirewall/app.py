"""
Emare Security OS — Standalone Demo App (Docker/Test)
==================================================

Mock SSH executor ile çalışarak UI'ı gerçek sunucu olmadan test etmenizi sağlar.
İki demo sunucu: UFW (Linux) ve Emare (Emare OS) — her ikisini de test edebilirsiniz.
"""

import re
import json
import random
from flask import Flask
from emarefirewall.routes import create_blueprint

# ── Mock Veriler ──

_ufw_rules = [
    "[ 1] 22/tcp                     ALLOW IN    Anywhere",
    "[ 2] 80/tcp                     ALLOW IN    Anywhere",
    "[ 3] 443/tcp                    ALLOW IN    Anywhere",
    "[ 4] 8080/tcp                   DENY IN     Anywhere",
    "[ 5] 22/tcp (v6)                ALLOW IN    Anywhere (v6)",
    "[ 6] 80/tcp (v6)                ALLOW IN    Anywhere (v6)",
    "[ 7] 443/tcp (v6)               ALLOW IN    Anywhere (v6)",
]

_blocked_ips = ["192.168.1.100", "10.0.0.55", "172.16.0.99"]

# ── Emare OS Mock Verileri ──

_eo_filter_rules = (
    " 0   chain=input action=accept protocol=tcp dst-port=22 comment=\"SSH Access\"\n"
    " 1   chain=input action=accept protocol=tcp dst-port=8291 comment=\"Emare Desktop\"\n"
    " 2   chain=input action=accept protocol=tcp dst-port=80 comment=\"HTTP\"\n"
    " 3   chain=input action=accept protocol=tcp dst-port=443 comment=\"HTTPS\"\n"
    " 4   chain=input action=accept connection-state=established,related comment=\"Established\"\n"
    " 5   chain=input action=drop src-blocklist=blocked comment=\"Block listed IPs\"\n"
    " 6   chain=forward action=accept connection-state=established,related\n"
    " 7   chain=forward action=drop connection-state=invalid comment=\"Drop invalid\"\n"
    " 8   chain=input action=drop comment=\"Drop all other input\"\n"
)

_eo_nat_rules = (
    " 0   chain=srcnat action=masquerade out-interface=ether1 comment=\"Masquerade\"\n"
    " 1   chain=dstnat action=dst-nat protocol=tcp dst-port=8080 to-addresses=192.168.88.10 to-ports=80 comment=\"Web Server Forward\"\n"
    " 2   chain=dstnat action=dst-nat protocol=tcp dst-port=2222 to-addresses=192.168.88.20 to-ports=22 comment=\"SSH Forward\"\n"
)

_eo_services = (
    " 0   name=telnet port=23 disabled=yes\n"
    " 1   name=ftp port=21 disabled=yes\n"
    " 2   name=www port=80 disabled=no\n"
    " 3   name=ssh port=22 disabled=no\n"
    " 4   name=www-ssl port=443 disabled=no\n"
    " 5   name=api port=8728 disabled=yes\n"
    " 6   name=api-ssl port=8729 disabled=no\n"
    " 7   name=emare-desktop port=8291 disabled=no\n"
)

_eo_address_list = (
    " 0   list=blocked address=192.168.1.100 comment=\"Brute force\"\n"
    " 1   list=blocked address=10.0.0.55 comment=\"Port scan detected\"\n"
    " 2   list=blocked address=172.16.0.99 comment=\"Manual block\"\n"
)

_eo_connections = (
    " 0   protocol=tcp src-address=203.0.113.50:54321 dst-address=192.168.88.1:22 tcp-state=established\n"
    " 1   protocol=tcp src-address=198.51.100.22:8080 dst-address=192.168.88.1:443 tcp-state=established\n"
    " 2   protocol=tcp src-address=192.0.2.100:12345 dst-address=192.168.88.1:80 tcp-state=established\n"
    " 3   protocol=udp src-address=192.168.88.5:53211 dst-address=8.8.8.8:53\n"
    " 4   protocol=tcp src-address=192.168.88.10:80 dst-address=203.0.113.10:55123 tcp-state=established\n"
    " 5   protocol=tcp src-address=172.217.0.1:443 dst-address=192.168.88.1:33445 tcp-state=time-wait\n"
)

_eo_interfaces = (
    " 0   name=ether1 type=ether running=yes disabled=no\n"
    " 1   name=ether2 type=ether running=yes disabled=no\n"
    " 2   name=ether3 type=ether running=no disabled=no\n"
    " 3   name=ether4 type=ether running=no disabled=no\n"
    " 4   name=ether5 type=ether running=no disabled=no\n"
    " 5   name=bridge1 type=bridge running=yes disabled=no\n"
    " 6   name=wlan1 type=wlan running=yes disabled=no\n"
)

_eo_users = (
    " 0   name=admin group=full\n"
    " 1   name=emarefw group=full\n"
)

_eo_resource = (
    "                   uptime: 45d12h30m15s\n"
    "                  version: 7.14.3 (stable)\n"
    "               build-time: 2026-02-10 10:00:00\n"
    "         factory-software: 7.1\n"
    "              free-memory: 180.5MiB\n"
    "             total-memory: 256.0MiB\n"
    "                      cpu: ARM Cortex-A72\n"
    "                cpu-count: 2\n"
    "            cpu-frequency: 880MHz\n"
    "                 cpu-load: 12%\n"
    "           free-hdd-space: 98.3MiB\n"
    "          total-hdd-space: 128.0MiB\n"
    "  architecture-name: arm64\n"
    "               device-model: Emare GW-200\n"
    "                 platform: Emare\n"
)

# ── Emare OS Routing / Ağ Verileri ──

_eo_routes = (
    " 0   dst-address=0.0.0.0/0 gateway=192.168.88.1 distance=1 comment=\"Default Gateway\"\n"
    " 1   dst-address=192.168.88.0/24 gateway=ether1 distance=0\n"
    " 2   dst-address=10.10.0.0/16 gateway=192.168.88.254 distance=10 comment=\"Branch Office\"\n"
    " 3   dst-address=172.16.0.0/12 gateway=192.168.88.253 distance=20 comment=\"VPN Network\"\n"
)

_eo_ip_addresses = (
    " 0   address=192.168.88.1/24 network=192.168.88.0 interface=bridge1 disabled=no\n"
    " 1   address=10.0.0.1/30 network=10.0.0.0 interface=ether1 disabled=no\n"
    " 2   address=172.16.1.1/24 network=172.16.1.0 interface=ether2 disabled=no\n"
    " 3   address=192.168.1.100/24 network=192.168.1.0 interface=wlan1 disabled=no\n"
)

_eo_arp = (
    " 0   address=192.168.88.10 mac-address=AA:BB:CC:DD:EE:01 interface=bridge1\n"
    " 1   address=192.168.88.20 mac-address=AA:BB:CC:DD:EE:02 interface=bridge1\n"
    " 2   address=192.168.88.30 mac-address=AA:BB:CC:DD:EE:03 interface=bridge1\n"
    " 3   address=10.0.0.2 mac-address=11:22:33:44:55:66 interface=ether1\n"
    " 4 D address=192.168.88.50 mac-address=AA:BB:CC:DD:EE:05 interface=bridge1\n"
)

_eo_dhcp_server = (
    " 0   name=dhcp1 interface=bridge1 address-pool=pool1 disabled=no\n"
)

_eo_dhcp_leases = (
    " 0   address=192.168.88.10 mac-address=AA:BB:CC:DD:EE:01 host-name=pc-ahmet status=bound server=dhcp1\n"
    " 1   address=192.168.88.20 mac-address=AA:BB:CC:DD:EE:02 host-name=laptop-ayse status=bound server=dhcp1\n"
    " 2   address=192.168.88.30 mac-address=AA:BB:CC:DD:EE:03 host-name=phone-mehmet status=bound server=dhcp1\n"
    " 3   address=192.168.88.50 mac-address=AA:BB:CC:DD:EE:05 host-name=printer status=waiting server=dhcp1\n"
)

_eo_dhcp_network = (
    " 0   address=192.168.88.0/24 gateway=192.168.88.1 dns-server=8.8.8.8,8.8.4.4\n"
)

_eo_ip_pools = (
    " 0   name=pool1 ranges=192.168.88.10-192.168.88.254\n"
)

_eo_queues = (
    " 0   name=download-limit target=192.168.88.10/32 max-limit=10M/20M disabled=no comment=\"Ahmet PC\"\n"
    " 1   name=upload-limit target=192.168.88.20/32 max-limit=5M/10M disabled=no comment=\"Ayse Laptop\"\n"
    " 2   name=guest-limit target=192.168.88.0/24 max-limit=2M/5M disabled=yes comment=\"Misafir Ağı\"\n"
)

_eo_bridges = (
    " 0   name=bridge1 protocol-mode=rstp disabled=no\n"
)

_eo_bridge_ports = (
    " 0   interface=ether2 bridge=bridge1 disabled=no\n"
    " 1   interface=ether3 bridge=bridge1 disabled=no\n"
    " 2   interface=ether4 bridge=bridge1 disabled=no\n"
    " 3   interface=ether5 bridge=bridge1 disabled=no\n"
    " 4   interface=wlan1 bridge=bridge1 disabled=no\n"
)

_eo_dns_static = (
    " 0   name=router.local address=192.168.88.1\n"
    " 1   name=nas.local address=192.168.88.200\n"
    " 2   name=printer.local address=192.168.88.50\n"
)

_eo_neighbors = (
    " 0   interface=ether1 address=10.0.0.2 mac-address=11:22:33:44:55:66 identity=ISP-Router platform=Emare version=7.12\n"
    " 1   interface=bridge1 address=192.168.88.10 mac-address=AA:BB:CC:DD:EE:01 identity=PC-Ahmet platform=Windows\n"
)

_eo_zones = (
    " 0   name=lan interfaces=bridge1,ether2,ether3,ether4,ether5 default=yes\n"
    " 1   name=wan interfaces=ether1 default=no\n"
    " 2   name=dmz interfaces= default=no\n"
    " 3   name=guest interfaces=wlan1 default=no\n"
)

_eo_zone_details = {
    "lan": (
        "interfaces: bridge1,ether2,ether3,ether4,ether5\n"
        "services: ssh,www,dns,dhcp,emare-desktop\n"
        "ports: 22/tcp,80/tcp,443/tcp,53/udp,67/udp\n"
        "masquerade: no\n"
        "forward-ports: none\n"
        "rules: accept src 192.168.88.0/24; drop src 0.0.0.0/0\n"
    ),
    "wan": (
        "interfaces: ether1\n"
        "services: ssh\n"
        "ports: 22/tcp\n"
        "masquerade: yes\n"
        "forward-ports: 8080->192.168.88.200:80,8443->192.168.88.200:443\n"
        "rules: drop src 10.0.0.0/8 proto icmp; accept dst-port 22 limit 5/min\n"
    ),
    "dmz": (
        "interfaces: \n"
        "services: www\n"
        "ports: 80/tcp,443/tcp\n"
        "masquerade: no\n"
        "forward-ports: none\n"
        "rules: none\n"
    ),
    "guest": (
        "interfaces: wlan1\n"
        "services: dns,dhcp\n"
        "ports: 53/udp,67/udp\n"
        "masquerade: yes\n"
        "forward-ports: none\n"
        "rules: drop dst 192.168.88.0/24; accept dst-port 53; accept dst-port 80; accept dst-port 443\n"
    ),
}

_eo_intrusion_status = (
    "enabled: yes\n"
    "active: yes\n"
    "mode: aggressive\n"
    "log: yes\n"
)

_eo_intrusion_jails = (
    " 0   name=ssh max-retry=3 find-time=600 ban-time=3600 currently-banned=2 total-banned=18\n"
    " 1   name=web max-retry=10 find-time=300 ban-time=1800 currently-banned=1 total-banned=42\n"
    " 2   name=dns max-retry=50 find-time=60 ban-time=600 currently-banned=0 total-banned=7\n"
)

_eo_intrusion_banned = {
    "ssh": "203.0.113.50\n185.220.101.33\n",
    "web": "45.33.32.156\n",
    "dns": "",
}

_eo_geo_blocked = (
    " 0   country=CN list=geoblock_CN count=8456\n"
    " 1   country=RU list=geoblock_RU count=5234\n"
)


# ══════════════════════════════════════════════════════════════
#  MOCK SSH EXECUTOR — server_id'ye göre UFW veya Emare
# ══════════════════════════════════════════════════════════════

def mock_ssh_executor(server_id: str, command: str):
    """Gerçek SSH bağlantısı olmadan komutları simüle eder."""

    cmd = command.strip()
    is_mt = 'emare' in server_id.lower()

    # ──────────── Emare OS ────────────
    if is_mt:
        return _mock_emareos(cmd)

    # ──────────── Linux / UFW ────────────
    return _mock_ufw(cmd)


def _mock_emareos(cmd: str):
    """Emare OS komut simülasyonu."""

    # ── Firewall Tipi Algılama ──
    if "which ufw" in cmd:
        return (False, "", "not found")
    if "which firewall-cmd" in cmd:
        return (False, "", "not found")

    # ── Intrusion Detection (Fail2ban equivalent) — system xxx'ten ÖNCE ──
    if "/emare system intrusion-detection status" in cmd:
        return (True, _eo_intrusion_status, "")
    if "/emare system intrusion-detection jail print" in cmd:
        return (True, _eo_intrusion_jails, "")
    if "/emare system intrusion-detection jail banned" in cmd:
        import re as _re
        m = _re.search(r'name=(\S+)', cmd)
        jname = m.group(1).strip('"') if m else ""
        return (True, _eo_intrusion_banned.get(jname, ""), "")
    if "/emare system intrusion-detection jail ban" in cmd:
        return (True, "1", "")
    if "/emare system intrusion-detection jail unban" in cmd:
        return (True, "1", "")

    # ── System Identity ──
    if "/emare system identity" in cmd:
        return (True, "       name: EmareRouter-01", "")

    # ── System Update Check ──
    if "/emare system update check" in cmd or "/emare system update info" in cmd:
        return (True, (
            "          channel: stable\n"
            "   installed-version: 7.14.3\n"
            "      latest-version: 7.15\n"
            "           status: New version is available\n"
        ), "")

    if "/emare system info" in cmd or cmd.startswith("/emare system"):
        return (True, _eo_resource, "")

    # ── Filter Rules ──
    if "/emare firewall rules print" in cmd:
        if "stats" in cmd:
            # Stats ile — L7 event collection
            lines = []
            for line in _eo_filter_rules.strip().splitlines():
                pkts = random.randint(0, 5000)
                bts = pkts * random.randint(60, 1500)
                lines.append(f"{line.strip()} bytes={bts} packets={pkts}")
            return (True, "\n".join(lines), "")
        return (True, _eo_filter_rules, "")

    # ── Filter Enable/Disable ──
    if "/emare firewall rules enable" in cmd:
        return (True, "", "")
    if "/emare firewall rules disable" in cmd:
        return (True, "", "")
    if "/emare firewall rules add" in cmd:
        return (True, "", "")
    if "/emare firewall rules remove" in cmd:
        return (True, "", "")

    # ── NAT Rules ──
    if "/emare firewall nat print" in cmd:
        return (True, _eo_nat_rules, "")
    if "/emare firewall nat add" in cmd:
        return (True, "", "")
    if "/emare firewall nat remove" in cmd:
        return (True, "", "")

    # ── Mangle ──
    if "/emare firewall mangle print" in cmd:
        return (True, "", "")
    if "/emare firewall mangle add" in cmd:
        return (True, "", "")
    if "/emare firewall mangle remove" in cmd:
        return (True, "", "")

    # ── Address Lists ──
    if "/emare firewall blocklist print" in cmd:
        if "blocked" in cmd:
            return (True, _eo_address_list, "")
        if "bogon" in cmd:
            return (True, "", "")
        return (True, _eo_address_list, "")
    if "/emare firewall blocklist add" in cmd:
        return (True, "", "")
    if "/emare firewall blocklist remove" in cmd:
        return (True, "", "")

    # ── Connections ──
    if "/emare firewall connections print" in cmd:
        return (True, _eo_connections, "")
    if "/emare firewall connections" in cmd:
        return (True, _eo_connections, "")

    # ── Services ──
    if "/emare services print" in cmd:
        return (True, _eo_services, "")
    if "/emare services disable" in cmd:
        return (True, "", "")
    if "/emare services enable" in cmd:
        return (True, "", "")
    if "/emare services set" in cmd:
        return (True, "", "")

    # ── Interfaces ──
    if "/emare network interfaces print" in cmd:
        if "stats" in cmd:
            return (True,
                " 0   name=ether1 rx-byte=1547823940 tx-byte=982736521 rx-packet=12893047 tx-packet=8294710 rx-error=0 tx-error=0 rx-drop=12 tx-drop=0\n"
                " 1   name=ether2 rx-byte=82736521 tx-byte=5472310 rx-packet=647321 tx-packet=321654 rx-error=3 tx-error=0 rx-drop=0 tx-drop=0\n"
                " 2   name=bridge1 rx-byte=2147483640 tx-byte=1547823940 rx-packet=18234567 tx-packet=14567890 rx-error=0 tx-error=0 rx-drop=1 tx-drop=0\n"
                " 3   name=wlan1 rx-byte=547823940 tx-byte=182736521 rx-packet=4523810 tx-packet=2894730 rx-error=5 tx-error=2 rx-drop=45 tx-drop=3\n",
            "")
        if "terse" in cmd:
            return (True, _eo_interfaces, "")
        return (True, _eo_interfaces, "")

    # ── Users (security scan) ──
    if "/emare users print" in cmd:
        return (True, _eo_users, "")

    # ── IP Settings ──
    if "/emare settings print" in cmd:
        return (True, (
            "        tcp-syncookies: yes\n"
            "          rp-filter: strict\n"
            "   accept-source-route: no\n"
        ), "")
    if "/emare settings set" in cmd:
        return (True, "", "")

    # ── DNS ──
    if "/emare dns config print" in cmd:
        return (True, (
            "              servers: 8.8.8.8,8.8.4.4\n"
            "    allow-remote-requests: no\n"
            "          cache-size: 2048KiB\n"
        ), "")
    if "/emare dns config set" in cmd:
        return (True, "", "")

    # ── MAC Server (security scan) ──
    if "/emare tools mac-access print" in cmd:
        return (True, "   disabled: yes", "")
    if "/emare tools mac-desktop print" in cmd:
        return (True, "   disabled: yes", "")

    # ── Backup / Export ──
    if "/emare firewall rules export" in cmd:
        return (True, (
            "/emare firewall rules\n"
            "add chain=input action=accept protocol=tcp dst-port=22 comment=\"SSH\"\n"
            "add chain=input action=accept protocol=tcp dst-port=8291 comment=\"Emare Desktop\"\n"
            "add chain=input action=accept connection-state=established,related\n"
            "add chain=input action=drop comment=\"Drop all\"\n"
        ), "")
    if "/emare firewall nat export" in cmd:
        return (True, (
            "/emare firewall nat\n"
            "add chain=srcnat action=masquerade out-interface=ether1\n"
            "add chain=dstnat action=dst-nat protocol=tcp dst-port=8080 to-addresses=192.168.88.10 to-ports=80\n"
        ), "")
    if "/emare firewall mangle export" in cmd:
        return (True, "", "")
    if "/emare firewall blocklist export" in cmd:
        return (True, (
            "/emare firewall blocklist\n"
            "add list=blocked address=192.168.1.100 comment=\"Brute force\"\n"
        ), "")
    if "/emare services export" in cmd:
        return (True, (
            "/emare services\n"
            "set telnet disabled=yes\n"
            "set ftp disabled=yes\n"
            "set api disabled=yes\n"
        ), "")

    # ── Routes ──
    if "/emare network routes print" in cmd:
        return (True, _eo_routes, "")
    if "/emare network routes add" in cmd:
        return (True, "", "")
    if "/emare network routes remove" in cmd:
        return (True, "", "")

    # ── IP Addresses ──
    if "/emare network addresses print" in cmd:
        return (True, _eo_ip_addresses, "")
    if "/emare network addresses add" in cmd:
        return (True, "", "")
    if "/emare network addresses remove" in cmd:
        return (True, "", "")

    # ── ARP ──
    if "/emare network arp print" in cmd:
        return (True, _eo_arp, "")
    if "/emare network arp add" in cmd:
        return (True, "", "")
    if "/emare network arp remove" in cmd:
        return (True, "", "")

    # ── DHCP Server ──
    if "/emare network dhcp lease print" in cmd:
        return (True, _eo_dhcp_leases, "")
    if "/emare network dhcp network print" in cmd:
        return (True, _eo_dhcp_network, "")
    if "/emare network dhcp server print" in cmd:
        return (True, _eo_dhcp_server, "")
    if "/emare network dhcp lease" in cmd:
        return (True, "", "")

    # ── IP Pool ──
    if "/emare network pools print" in cmd:
        return (True, _eo_ip_pools, "")
    if "/emare network pools add" in cmd:
        return (True, "", "")
    if "/emare network pools remove" in cmd:
        return (True, "", "")

    # ── Queues ──
    if "/emare queue print" in cmd:
        return (True, _eo_queues, "")
    if "/emare queue add" in cmd:
        return (True, "", "")
    if "/emare queue remove" in cmd:
        return (True, "", "")

    # ── Bridge ──
    if "/emare network bridge-ports print" in cmd:
        return (True, _eo_bridge_ports, "")
    if "/emare network bridges print" in cmd:
        return (True, _eo_bridges, "")

    # ── DNS Static ──
    if "/emare dns static print" in cmd:
        return (True, _eo_dns_static, "")
    if "/emare dns static add" in cmd:
        return (True, "", "")
    if "/emare dns static remove" in cmd:
        return (True, "", "")

    # ── Neighbors ──
    if "/emare network neighbors print" in cmd:
        return (True, _eo_neighbors, "")

    # ── Network Analyser: tools ──
    if "/emare tools ping" in cmd:
        import random
        _cnt = 4
        _m = re.search(r'count=(\d+)', cmd)
        if _m:
            _cnt = min(int(_m.group(1)), 500)
        if _cnt <= 0:
            _cnt = 4
        _lines = "  SEQ HOST                                     SIZE TTL TIME  STATUS\n"
        _times = []
        for _i in range(_cnt):
            _t = round(random.uniform(10.0, 15.0), 1)
            _times.append(_t)
            _lines += f"    {_i} 8.8.8.8                                    56  55 {_t}ms\n"
        _min_t = min(_times)
        _avg_t = round(sum(_times) / len(_times), 1)
        _max_t = max(_times)
        _lines += f"    sent={_cnt} received={_cnt} packet-loss=0% min-rtt={_min_t}ms avg-rtt={_avg_t}ms max-rtt={_max_t}ms\n"
        return (True, _lines, "")
    if "/emare tools traceroute" in cmd:
        return (True,
            " 1  gateway (192.168.88.1) 1.2ms\n"
            " 2  10.0.0.1 (10.0.0.1) 3.5ms\n"
            " 3  isp-gw.example.net (172.16.0.1) 5.8ms\n"
            " 4  core-router.example.net (203.0.113.1) 12.1ms\n"
            " 5  dns.google (8.8.8.8) 14.3ms\n",
        "")
    if "/emare tools dns-lookup" in cmd:
        if "type=MX" in cmd:
            return (True, "10 mail.example.com.\n20 mail2.example.com.\n", "")
        if "type=NS" in cmd:
            return (True, "ns1.example.com.\nns2.example.com.\n", "")
        if "type=TXT" in cmd:
            return (True, "\"v=spf1 include:_spf.google.com ~all\"\n", "")
        return (True, "93.184.216.34\n2606:2800:220:1:248:1893:25c8:1946\n", "")
    if "/emare tools port-check" in cmd:
        return (True, "port=443 protocol=tcp status=open\n", "")
    if "/emare tools packet-sniffer" in cmd:
        return (True,
            "12:30:01.123 ether1 192.168.88.10 > 8.8.8.8 TCP 443 SYN\n"
            "12:30:01.135 ether1 8.8.8.8 > 192.168.88.10 TCP 443 SYN-ACK\n"
            "12:30:01.136 ether1 192.168.88.10 > 8.8.8.8 TCP 443 ACK\n"
            "12:30:01.200 ether1 192.168.88.10 > 8.8.8.8 TCP 443 PSH-ACK\n"
            "12:30:01.245 ether1 8.8.8.8 > 192.168.88.10 TCP 443 ACK\n",
        "")
    if "/emare tools bandwidth-test" in cmd:
        return (True,
            "  status: done\n  duration: 5s\n  tx-current: 94.5Mbps\n  rx-current: 92.1Mbps\n"
            "  direction: both\n  download: 92.1 Mbps\n  upload: 94.5 Mbps\n",
        "")
    if "whois " in cmd:
        return (True,
            "domain:       EXAMPLE.COM\n"
            "organisation: Internet Assigned Numbers Authority\n"
            "created:      1995-08-14\n"
            "source:       IANA\n"
            "registrar:    RESERVED-Internet Assigned Numbers Authority\n"
            "status:       active\n"
            "nameserver:   a.iana-servers.net\n",
        "")

    # ── Zone Management ──
    if "/emare firewall zone print" in cmd:
        return (True, _eo_zones, "")
    if "/emare firewall zone detail" in cmd:
        import re as _re
        m = _re.search(r'name=(\S+)', cmd)
        zname = m.group(1).strip('"') if m else ""
        if zname in _eo_zone_details:
            return (True, _eo_zone_details[zname], "")
        return (False, "", f"zone '{zname}' not found")
    if "/emare firewall zone set" in cmd:
        return (True, "", "")
    if "/emare firewall zone rule add" in cmd:
        return (True, "", "")
    if "/emare firewall zone rule remove" in cmd:
        return (True, "", "")

    # ── Geo-Block ──
    if "/emare firewall geo-block print" in cmd:
        return (True, _eo_geo_blocked, "")
    if "/emare firewall geo-block add" in cmd:
        return (True, "", "")
    if "/emare firewall geo-block remove" in cmd:
        return (True, "", "")

    # ── Generic ──
    if "mkdir" in cmd or "tee " in cmd or "sudo " in cmd or "cat " in cmd:
        return (True, "", "")
    if "ls " in cmd:
        return (True, "", "")

    return (True, "", "")


def _mock_ufw(cmd: str):
    """Linux UFW komut simülasyonu."""

    # ── UFW Status (birleşik komut: which ufw && ufw status verbose) ──
    if "which ufw" in cmd and "ufw status verbose" in cmd:
        lines = [
            "/usr/sbin/ufw",
            "Status: active",
            "Logging: on (low)",
            "Default: deny (incoming), allow (outgoing), disabled (routed)",
            "New profiles: skip",
            "",
            "To                         Action      From",
            "--                         ------      ----",
        ] + _ufw_rules
        return (True, "\n".join(lines), "")

    if "ufw status verbose" in cmd:
        lines = [
            "Status: active",
            "Logging: on (low)",
            "Default: deny (incoming), allow (outgoing), disabled (routed)",
            "New profiles: skip",
            "",
            "To                         Action      From",
            "--                         ------      ----",
        ] + _ufw_rules
        return (True, "\n".join(lines), "")

    # ── UFW Enable/Disable ──
    if "ufw enable" in cmd:
        return (True, "Firewall is active and enabled on system startup", "")
    if "ufw disable" in cmd:
        return (True, "Firewall stopped and disabled on system startup", "")

    # ── UFW Status Numbered ──
    if "ufw status numbered" in cmd:
        lines = [
            "Status: active",
            "",
            "     To                         Action      From",
            "     --                         ------      ----",
        ] + _ufw_rules
        return (True, "\n".join(lines), "")

    # ── UFW Rule Operations ──
    if "ufw allow" in cmd or "ufw deny" in cmd or "ufw reject" in cmd or "ufw limit" in cmd:
        return (True, "Rule added", "")
    if "ufw delete" in cmd:
        return (True, "Rule deleted", "")
    if "ufw insert" in cmd:
        return (True, "Rule inserted", "")

    # ── Blocked IPs ──
    if "ufw status" in cmd and "grep -i 'deny'" in cmd:
        lines = [f"Anywhere                   DENY        {ip}" for ip in _blocked_ips]
        return (True, "\n".join(lines), "")

    # ── Which firewall ──
    if "which ufw" in cmd:
        return (True, "/usr/sbin/ufw", "")
    if "which firewall-cmd" in cmd:
        return (False, "", "not found")
    if "/emare system info" in cmd:
        return (False, "", "not found")

    # ── Connections ──
    if "ss -tunapO" in cmd or "ss -tunap" in cmd:
        conns = [
            "ESTAB  0  0  10.0.0.1:22    203.0.113.50:54321  users:((\"sshd\",pid=1234,fd=3))",
            "ESTAB  0  0  10.0.0.1:443   198.51.100.22:8080  users:((\"nginx\",pid=5678,fd=5))",
            "ESTAB  0  0  10.0.0.1:80    192.0.2.100:12345   users:((\"nginx\",pid=5678,fd=7))",
            "LISTEN 0  128 0.0.0.0:22    0.0.0.0:*           users:((\"sshd\",pid=1234,fd=4))",
            "LISTEN 0  128 0.0.0.0:80    0.0.0.0:*           users:((\"nginx\",pid=5678,fd=6))",
            "LISTEN 0  128 0.0.0.0:443   0.0.0.0:*           users:((\"nginx\",pid=5678,fd=8))",
            "TIME-WAIT 0  0  10.0.0.1:80  192.0.2.55:33211",
            "SYN-RECV  0  0  10.0.0.1:443 203.0.113.99:44100",
        ]
        return (True, "\n".join(conns), "")

    # ── Top Talkers (ss -tn) ──
    if "ss -tn" in cmd:
        lines = [
            "      2 203.0.113.50",
            "      2 192.0.2.100",
            "      1 198.51.100.22",
        ]
        return (True, "\n".join(lines), "")

    # ── Listening Ports (ss -tlnp) ──
    if "ss -tlnp" in cmd:
        lines = [
            "State  Recv-Q  Send-Q  Local Address:Port  Peer Address:Port  Process",
            "LISTEN 0  128  0.0.0.0:22   0.0.0.0:*  users:((\"sshd\",pid=1234,fd=4))",
            "LISTEN 0  128  0.0.0.0:80   0.0.0.0:*  users:((\"nginx\",pid=5678,fd=6))",
            "LISTEN 0  128  0.0.0.0:443  0.0.0.0:*  users:((\"nginx\",pid=5678,fd=8))",
        ]
        return (True, "\n".join(lines), "")

    # ── Connection Stats ──
    if "ss -s" in cmd:
        return (True, (
            "Total: 156\n"
            "TCP:   42 (estab 8, closed 12, orphaned 0, timewait 5)\n"
            "UDP:   6\n"
        ), "")

    # ── iptables checks ──
    if "iptables -L" in cmd and "SYN_FLOOD" in cmd:
        return (True, "Chain SYN_FLOOD (1 references)\ntarget prot opt source destination\nRETURN all -- anywhere anywhere limit: avg 25/sec burst 50", "")
    if "iptables -L" in cmd and "HTTP_FLOOD" in cmd:
        return (True, "", "iptables: No chain/target/match by that name.")
    if "iptables -L" in cmd and "UDP_FLOOD" in cmd:
        return (True, "", "")
    if "iptables -L" in cmd and "BOGON_FILTER" in cmd:
        return (True, "", "")
    if "iptables" in cmd:
        return (True, "", "")

    # ── sysctl checks ──
    if "sysctl" in cmd:
        if "net.ipv4.tcp_syncookies" in cmd:
            return (True, "net.ipv4.tcp_syncookies = 1", "")
        if "net.ipv4.icmp_echo_ignore_all" in cmd:
            return (True, "net.ipv4.icmp_echo_ignore_all = 0", "")
        if "net.ipv4.conf.all.rp_filter" in cmd:
            return (True, "net.ipv4.conf.all.rp_filter = 1", "")
        if "net.ipv4.tcp_timestamps" in cmd:
            return (True, "net.ipv4.tcp_timestamps = 1", "")
        if "net.ipv4.conf.all.accept_source_route" in cmd:
            return (True, "net.ipv4.conf.all.accept_source_route = 0", "")
        return (True, "", "")

    # ── nginx checks ──
    if "nginx -T" in cmd or "cat /etc/nginx" in cmd:
        return (True, "# nginx config\nserver {\n    listen 80;\n}\n", "")
    if "grep -r" in cmd and "nginx" in cmd:
        return (True, "", "")

    # ── Fail2Ban ──
    if "fail2ban-client status" in cmd:
        if "sshd" in cmd:
            return (True, (
                "Status for the jail: sshd\n"
                "|- Filter\n|  |- Currently failed: 3\n|  |- Total failed: 127\n"
                "|  `- File list: /var/log/auth.log\n"
                "`- Actions\n   |- Currently banned: 2\n   |- Total banned: 45\n"
                "   `- Banned IP list: 192.168.1.100 10.0.0.55"
            ), "")
        return (True, "Status\n|- Number of jail: 1\n`- Jail list: sshd", "")
    if "fail2ban-client set" in cmd and "banip" in cmd:
        return (True, "1", "")
    if "fail2ban-client set" in cmd and "unbanip" in cmd:
        return (True, "1", "")

    # ── Security Scan ──
    if "cat /etc/ssh/sshd_config" in cmd:
        return (True, (
            "Port 22\n"
            "PermitRootLogin no\n"
            "PasswordAuthentication yes\n"
            "PubkeyAuthentication yes\n"
            "X11Forwarding no\n"
        ), "")

    # ── Firewalld zones ──
    if "firewall-cmd --get-zones" in cmd:
        return (False, "", "command not found")
    if "firewall-cmd" in cmd:
        return (False, "", "command not found")

    # ── Network Analyser: Linux tools ──
    if cmd.startswith("ping ") or "ping -c" in cmd:
        import random
        _cnt = 4
        _m = re.search(r'-c\s+(\d+)', cmd)
        if _m:
            _cnt = min(int(_m.group(1)), 500)
        _lines = "PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.\n"
        _times = []
        for _i in range(1, _cnt + 1):
            _t = round(random.uniform(10.0, 15.0), 1)
            _times.append(_t)
            _lines += f"64 bytes from 8.8.8.8: icmp_seq={_i} ttl=55 time={_t} ms\n"
        _min_t = min(_times)
        _avg_t = round(sum(_times) / len(_times), 1)
        _max_t = max(_times)
        _mdev = round((_max_t - _min_t) / 2, 1)
        _lines += f"\n--- 8.8.8.8 ping statistics ---\n"
        _lines += f"{_cnt} packets transmitted, {_cnt} received, 0% packet loss, time {_cnt * 1001}ms\n"
        _lines += f"rtt min/avg/max/mdev = {_min_t}/{_avg_t}/{_max_t}/{_mdev} ms\n"
        return (True, _lines, "")
    if cmd.startswith("traceroute ") or "traceroute -m" in cmd or "tracepath " in cmd:
        return (True,
            "traceroute to 8.8.8.8 (8.8.8.8), 20 hops max, 60 byte packets\n"
            " 1  gateway (192.168.88.1)  1.234 ms\n"
            " 2  10.0.0.1 (10.0.0.1)  3.567 ms\n"
            " 3  isp-gw.example.net (172.16.0.1)  5.891 ms\n"
            " 4  * * *\n"
            " 5  core-router.example.net (203.0.113.1)  12.345 ms\n"
            " 6  dns.google (8.8.8.8)  14.567 ms\n",
        "")
    if cmd.startswith("dig ") or "dig +short" in cmd:
        return (True, "93.184.216.34\n", "")
    if cmd.startswith("nslookup ") or "nslookup -type" in cmd:
        return (True, "93.184.216.34\n", "")
    if cmd.startswith("host ") or "host -t" in cmd:
        return (True, "example.com has address 93.184.216.34\n", "")
    if "echo >/dev/tcp" in cmd or "nc -zu" in cmd:
        return (True, "OPEN\n", "")
    if cmd.startswith("whois ") or "whois " in cmd:
        return (True,
            "% IANA WHOIS server\n"
            "domain:       EXAMPLE.COM\n"
            "organisation: Internet Assigned Numbers Authority\n"
            "created:      1995-08-14\n"
            "source:       IANA\n"
            "registrar:    RESERVED-Internet Assigned Numbers Authority\n"
            "status:       active\n"
            "nameserver:   a.iana-servers.net\n"
            "nameserver:   b.iana-servers.net\n",
        "")
    if "tcpdump" in cmd:
        return (True,
            "12:30:01.123456 IP 192.168.88.10.54321 > 8.8.8.8.443: Flags [S], seq 1234567890\n"
            "12:30:01.135678 IP 8.8.8.8.443 > 192.168.88.10.54321: Flags [S.], seq 987654321, ack 1234567891\n"
            "12:30:01.135789 IP 192.168.88.10.54321 > 8.8.8.8.443: Flags [.], ack 987654322\n"
            "12:30:01.200123 IP 192.168.88.10.54321 > 8.8.8.8.443: Flags [P.], seq 1:50, ack 1\n"
            "12:30:01.245456 IP 8.8.8.8.443 > 192.168.88.10.54321: Flags [.], ack 50\n"
            "5 packets captured\n",
        "")
    if "iperf3" in cmd:
        return (True, "iperf3_unavailable", "")
    if "cat /proc/net/dev" in cmd:
        return (True,
            "Inter-|   Receive                                                |  Transmit\n"
            " face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed\n"
            "    lo: 1234567890  123456    0    0    0     0          0         0 1234567890  123456    0    0    0     0       0          0\n"
            "  eth0: 1547823940 12893047    0   12    0     0          0         0  982736521  8294710    0    0    0     0       0          0\n"
            "  eth1:   82736521   647321    3    0    0     0          0         0    5472310   321654    0    0    0     0       0          0\n",
        "")

    # ── Generic commands ──
    if cmd.startswith("echo "):
        return (True, "", "")
    if cmd.startswith("cat "):
        return (True, "", "")
    if cmd.startswith("test "):
        return (True, "", "")
    if "mkdir" in cmd or "tee " in cmd or "sudo " in cmd:
        return (True, "", "")
    if "date" in cmd:
        return (True, "2026-03-21T10:30:00+00:00", "")
    if "ls " in cmd:
        return (True, "", "")

    # ── Varsayılan ──
    return (True, "", "")


def create_app():
    """Flask uygulamasını oluşturur."""
    import os
    from emarefirewall.law5651 import Law5651Stamper, TubitakTimestampClient
    base_dir = os.path.dirname(os.path.abspath(__file__))
    tmpl_dir = os.path.join(base_dir, 'templates')
    # Eğer templates burada yoksa, emarefirewall/ altında ara
    if not os.path.isdir(tmpl_dir):
        tmpl_dir = os.path.join(base_dir, 'emarefirewall', 'templates')

    static_dir = os.path.join(tmpl_dir, 'static')

    app = Flask(__name__,
                template_folder=tmpl_dir,
                static_folder=static_dir,
                static_url_path='/static')

    from emarefirewall import config as cfg
    from emarefirewall.cache import create_cache
    from emarefirewall.store import create_store
    from emarefirewall.tenants import create_tenant_store, WebhookDispatcher
    from emarefirewall.rmm import RMMStore

    app.config['SECRET_KEY'] = cfg.SECRET_KEY
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'
    if not cfg.DEBUG:
        app.config['SESSION_COOKIE_SECURE'] = True

    # Cache ve Store backend'lerini mod'a göre oluştur
    cache = create_cache(cfg.CACHE_BACKEND, redis_url=cfg.REDIS_URL)
    store = create_store(
        cfg.DB_BACKEND,
        db_path=cfg.SQLITE_PATH,
        postgres_url=cfg.POSTGRES_URL,
    )

    # 5651 log damgalama (TSA_URL yoksa dry-run ile hash-zinciri aktif kalir)
    tsa_client = TubitakTimestampClient(
        tsa_url=os.environ.get('TSA_URL', ''),
        username=os.environ.get('TSA_USERNAME', ''),
        password=os.environ.get('TSA_PASSWORD', ''),
        dry_run=not bool(os.environ.get('TSA_URL', '')),
    )
    stamper = Law5651Stamper(
        organization=os.environ.get('TSA_ORG', 'Emare Security OS'),
        tsa_client=tsa_client,
        enabled=True,
        stamp_every=int(os.environ.get('TSA_STAMP_EVERY', '1')),
    )
    store.set_5651_stamper(stamper)

    # ISP Tenant store
    tenant_store = create_tenant_store(
        db_backend=store._backend if cfg.TENANT_MODE and hasattr(store, '_backend') else None
    )
    webhook_dispatcher = WebhookDispatcher(tenant_store)

    # RMM + ITSM store
    rmm_db_path = os.path.join(os.path.dirname(cfg.SQLITE_PATH or 'data/logs.db'), 'rmm.db')
    rmm_store = RMMStore(db_path=rmm_db_path)
    rmm_store.init()

    # Demo RMM verisi
    _demo_devices = [
        ('WIN-PC-01', 'windows', '11 Pro 23H2', '192.168.1.50', '1.0.0',
         {'cpu_name': 'Intel i7-13700K', 'cpu_cores': 16, 'mem_total_gb': 32,
          'disk_volumes': 3, 'domain': 'EMARE.LOCAL', 'logged_user': 'emre'}),
        ('WIN-SRV-01', 'windows', 'Server 2022', '10.0.0.10', '1.0.0',
         {'cpu_name': 'Xeon E-2388G', 'cpu_cores': 8, 'mem_total_gb': 64,
          'disk_volumes': 4, 'domain': 'EMARE.LOCAL', 'uptime_hours': 720}),
        ('LINUX-WEB-01', 'linux', 'Ubuntu 22.04', '10.0.0.20', '1.0.0',
         {'cpu_cores': 4, 'mem_total_gb': 16, 'uptime_hours': 2160}),
        ('LINUX-DB-01', 'linux', 'Rocky 9.3', '10.0.0.30', '1.0.0',
         {'cpu_cores': 8, 'mem_total_gb': 64, 'connections': 247}),
        ('MAC-DEV-01', 'macos', 'Sonoma 14.4', '192.168.1.80', '1.0.0',
         {'cpu_name': 'Apple M3 Pro', 'cpu_cores': 12, 'mem_total_gb': 36}),
    ]
    import random
    for hostname, os_type, os_ver, ip, agent_ver, extra in _demo_devices:
        existing = rmm_store.list_devices()
        if not any(d['hostname'] == hostname for d in existing):
            _cpu = random.uniform(5, 85)
            _ram = random.uniform(20, 90)
            _disk = random.uniform(15, 70)
            # DB sunucusunu yüksek disk ile oluştur (alert tetiklemek için)
            if hostname == 'LINUX-DB-01':
                _disk = random.uniform(88, 94)
            if hostname == 'WIN-SRV-01':
                _cpu = random.uniform(82, 93)
            info = rmm_store.register_device(
                hostname=hostname, os_type=os_type, os_version=os_ver,
                ip_address=ip, agent_version=agent_ver,
                tags=['demo'])
            extra['label'] = {'WIN-PC-01': "Emre'nin PC'si",
                              'WIN-SRV-01': 'Ana Sunucu',
                              'LINUX-WEB-01': 'Web Sunucusu',
                              'LINUX-DB-01': 'Veritabanı Sunucusu',
                              'MAC-DEV-01': 'Geliştirici Mac'}.get(hostname, '')
            rmm_store.heartbeat(info['id'],
                                cpu=_cpu, ram=_ram, disk=_disk,
                                net_in=random.randint(100, 50000),
                                net_out=random.randint(100, 30000),
                                extra=extra)
            # Demo görev sonuçları
            if hostname == 'WIN-PC-01':
                t1 = rmm_store.create_task(info['id'], 'sysinfo_collect', {})
                rmm_store.complete_task(t1, result=json.dumps({
                    'İşlemci': {'Model': 'Intel i7-13700K', 'Çekirdek': 16, 'Hız': '5.4 GHz'},
                    'Bellek': {'Toplam': '32 GB', 'Kullanılan': '18.4 GB', 'Boş': '13.6 GB'},
                    'Disk': {'C:': '512 GB SSD (%45)', 'D:': '2 TB HDD (%23)', 'E:': '1 TB NVMe (%67)'},
                    'Ağ': {'IP': '192.168.1.50', 'DNS': '8.8.8.8', 'Gateway': '192.168.1.1'}
                }, ensure_ascii=False))
                t2 = rmm_store.create_task(info['id'], 'event_log', {'log': 'System'})
                rmm_store.complete_task(t2, result=json.dumps([
                    {'id': 7036, 'level': 'Information', 'source': 'Service Control Manager', 'message': 'Windows Update servisi çalışıyor durumuna geçti.', 'timestamp': '2026-03-23T08:15:00Z'},
                    {'id': 1014, 'level': 'Warning', 'source': 'DNS Client', 'message': 'DNS isim çözümü zaman aşımına uğradı.', 'timestamp': '2026-03-23T07:45:00Z'},
                    {'id': 41, 'level': 'Critical', 'source': 'Kernel-Power', 'message': 'Sistem beklenmeyen kapanma sonrası yeniden başladı.', 'timestamp': '2026-03-22T23:10:00Z'},
                    {'id': 10016, 'level': 'Error', 'source': 'DCOM', 'message': 'DCOM izin hatası — uygulama erişimi reddedildi.', 'timestamp': '2026-03-22T18:30:00Z'},
                ], ensure_ascii=False))
            if hostname == 'WIN-SRV-01':
                t3 = rmm_store.create_task(info['id'], 'sysmon_collect', {'hours': 1})
                rmm_store.complete_task(t3, result=json.dumps([
                    {'event_id': 1, 'message': 'Process Create: powershell.exe -File backup.ps1', 'timestamp': '2026-03-23T09:00:00Z'},
                    {'event_id': 3, 'message': 'Network Connection: svchost.exe → 10.0.0.30:5432 TCP', 'timestamp': '2026-03-23T09:01:00Z'},
                    {'event_id': 11, 'message': 'FileCreate: C:\\Backup\\db_2026-03-23.bak', 'timestamp': '2026-03-23T09:02:00Z'},
                    {'event_id': 22, 'message': 'DNSEvent: query updates.emare.com.tr → 104.21.55.12', 'timestamp': '2026-03-23T09:05:00Z'},
                    {'event_id': 1, 'message': 'Process Create: wsmprovhost.exe (WinRM remote session)', 'timestamp': '2026-03-23T09:10:00Z'},
                ], ensure_ascii=False))

    # Demo ITSM ticket'ları
    if not rmm_store.list_tickets():
        rmm_store.create_ticket('VPN bağlantı hatası', 'Merkez ofis VPN düşüyor', 'high', 'incident')
        rmm_store.create_ticket('Yeni kullanıcı hesabı', 'Pazarlama ekibi yeni başlayan', 'medium', 'request')
        rmm_store.create_ticket('Disk alanı uyarısı', 'DB sunucusu %90 dolu', 'critical', 'incident')

    # Varsayılan alarm yapılandırması
    rmm_store.save_alert_config({
        'cpu_warning': 80, 'cpu_critical': 95,
        'ram_warning': 80, 'ram_critical': 95,
        'disk_warning': 85, 'disk_critical': 95,
        'enabled': True, 'cooldown_minutes': 30,
        'auto_ticket': True
    })

    # ── SIEM Demo Verileri ──

    # Tehdit İstihbaratı
    _demo_threats = [
        ('185.220.101.34', 'ip', 'AbuseIPDB', 'malicious', ['tor-exit', 'brute-force']),
        ('45.155.205.233', 'ip', 'VirusTotal', 'malicious', ['c2-server', 'apt']),
        ('91.240.118.172', 'ip', 'AbuseIPDB', 'suspicious', ['scanner']),
        ('evil-payload.xyz', 'domain', 'VirusTotal', 'malicious', ['phishing', 'malware']),
        ('d41d8cd98f00b204e9800998ecf8427e', 'hash', 'VirusTotal', 'malicious', ['ransomware']),
        ('suspicious-login.com', 'domain', 'manual', 'suspicious', ['credential-theft']),
        ('10.0.0.99', 'ip', 'internal', 'clean', ['whitelisted']),
    ]
    if not rmm_store.list_threats():
        for ind, itype, src, rep, tags in _demo_threats:
            rmm_store.add_threat_indicator(
                indicator=ind, indicator_type=itype,
                source=src, reputation=rep, tags=tags)

    # Korelasyon Kuralları
    if not rmm_store.list_correlation_rules():
        rmm_store.create_correlation_rule(
            name='CPU Aşırı Yüklenme',
            description='10 dakikada 3 kez CPU %95 üstü → kritik alarm',
            rule_type='threshold',
            conditions={'metric': 'cpu', 'operator': '>=', 'value': 95,
                        'count': 3, 'window_minutes': 10},
            severity='critical')
        rmm_store.create_correlation_rule(
            name='Disk Tekrarlayan Uyarı',
            description='1 saatte 5 kez disk uyarısı → olay',
            rule_type='frequency',
            conditions={'alert_type': 'disk', 'count': 5,
                        'window_minutes': 60},
            severity='warning')
        rmm_store.create_correlation_rule(
            name='RAM Sürekli Yüksek',
            description='30 dakikada 5 kez RAM %90 üstü',
            rule_type='threshold',
            conditions={'metric': 'ram', 'operator': '>=', 'value': 90,
                        'count': 5, 'window_minutes': 30},
            severity='critical')

    # Risk puanları — demo cihazlar için başlangıç
    existing_devices = rmm_store.list_devices()
    existing_risks = rmm_store.list_risk_scores()
    if not existing_risks and existing_devices:
        for dev in existing_devices:
            base_risk = 0
            if dev['disk_usage'] > 85:
                base_risk += 15
            if dev['cpu_usage'] > 80:
                base_risk += 10
            if dev['ram_usage'] > 80:
                base_risk += 10
            if base_risk > 0:
                rmm_store._add_risk_factor(
                    dev['id'], 'initial_assessment', base_risk)

    # SOAR Demo Playbook'ları
    if not rmm_store.list_playbooks():
        rmm_store.create_playbook(
            name='Kritik Alarm → IP Engelle + Kayıt',
            trigger_type='alert',
            trigger_conditions={'severity': 'critical'},
            actions=[
                {'action_type': 'block_ip', 'params': {}},
                {'action_type': 'create_ticket',
                 'params': {'title': 'Otomatik: Kritik alarm',
                            'priority': 'critical'}},
            ],
            description='Kritik alarm geldiğinde IP engelle ve kayıt oluştur')
        rmm_store.create_playbook(
            name='Anomali → Tehdit Listesine Ekle',
            trigger_type='anomaly',
            trigger_conditions={},
            actions=[
                {'action_type': 'add_threat',
                 'params': {'ioc_type': 'ipv4-addr'}},
            ],
            description='UEBA anomalisi tespit edildiğinde tehdide ekle')
        rmm_store.create_playbook(
            name='Korelasyon → Kayıt Oluştur',
            trigger_type='correlation',
            trigger_conditions={},
            actions=[
                {'action_type': 'create_ticket',
                 'params': {'title': 'Korelasyon Eşleşmesi',
                            'priority': 'high'}},
            ],
            description='Korelasyon kuralı tetiklendiğinde kayıt oluştur')

    # Demo Vakalar (Case Management)
    if not rmm_store.list_cases():
        rmm_store.create_case(
            title='Şüpheli Giriş Denemesi — 192.168.1.50',
            description='Birden fazla başarısız giriş denemesi tespit edildi',
            severity='high', assignee='admin', created_by='system')
        rmm_store.create_case(
            title='Ransomware İndikatörü — evil-payload.xyz',
            description='Tehdit istihbaratı eşleşmesi: bilinen ransomware domain',
            severity='critical', assignee='soc-analyst', created_by='system')

    # Blueprint oluştur
    fw_bp = create_blueprint(
        ssh_executor=mock_ssh_executor,
        rate_limit_per_minute=cfg.RATE_LIMIT_PER_MINUTE,
        cache_backend=cache,
        log_store=store,
        tenant_store=tenant_store,
        webhook_dispatcher=webhook_dispatcher,
        rmm_store=rmm_store,
    )
    app.register_blueprint(fw_bp)

    # Ana sayfa → firewall.html
    @app.route('/')
    def index():
        from flask import render_template
        return render_template('firewall.html')

    return app


if __name__ == '__main__':
    from emarefirewall import config as _cfg
    app = create_app()
    print("\n�️ Emare Security OS Demo — http://localhost:5555\n")
    app.run(host=_cfg.HOST, port=_cfg.PORT, debug=_cfg.DEBUG)
