#!/usr/bin/env python3
"""Emare Security OS — Tam endpoint testi. Tüm 84 endpoint'i test eder."""
import json, urllib.request, urllib.error, sys

BASE = "http://localhost:5555"
EO = "emare-router-1"
UF = "ufw-server-1"
results = {"ok": 0, "fail": 0, "errors": []}

def test(label, method, path, body=None, expect_success=True, expect_html=False):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode()
            if expect_html:
                if "<!DOCTYPE" in raw or "<html" in raw:
                    results["ok"] += 1
                    print(f"  ✅ {label}")
                else:
                    results["fail"] += 1
                    results["errors"].append(f"{label}: HTML beklendi")
                    print(f"  ❌ {label} — HTML beklendi")
                return None
            d = json.loads(raw)
            if isinstance(d, list):
                success = True
            else:
                success = d.get("success", d.get("status") == "healthy")
            if success or not expect_success:
                results["ok"] += 1
                print(f"  ✅ {label}")
            else:
                results["fail"] += 1
                err_msg = d.get("message", d.get("error", "unknown"))
                results["errors"].append(f"{label}: {err_msg}")
                print(f"  ❌ {label} — {err_msg}")
            return d
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        results["fail"] += 1
        # Try to get error from response
        try:
            d = json.loads(raw)
            err_msg = d.get("error", str(e.code))
        except:
            err_msg = f"HTTP {e.code}"
            if "NameError" in raw or "Error" in raw:
                import re
                m = re.search(r"<title>(.*?)</title>", raw)
                err_msg = m.group(1) if m else err_msg
        results["errors"].append(f"{label}: {err_msg}")
        print(f"  ❌ {label} — {err_msg}")
        return None
    except Exception as e:
        results["fail"] += 1
        results["errors"].append(f"{label}: {e}")
        print(f"  ❌ {label} — {e}")
        return None

print("\n🔍 Emare Security OS v1.11.0 — Tam Endpoint Testi\n")

# === HEALTH ===
print("📡 Health & UI")
test("Health", "GET", "/api/firewall/health")
test("UI Page", "GET", "/", expect_html=True)

# === STATUS ===
print("\n📊 Status")
test("Status EO", "GET", f"/api/servers/{EO}/firewall/status")
test("Status UF", "GET", f"/api/servers/{UF}/firewall/status")

# === ENABLE/DISABLE ===
print("\n🔛 Enable/Disable")
test("Enable EO", "POST", f"/api/servers/{EO}/firewall/enable")
test("Enable UF", "POST", f"/api/servers/{UF}/firewall/enable")
test("Disable EO", "POST", f"/api/servers/{EO}/firewall/disable")
test("Disable UF", "POST", f"/api/servers/{UF}/firewall/disable")

# === RULES ===
print("\n📋 Rules")
test("Add Rule EO", "POST", f"/api/servers/{EO}/firewall/rules",
     {"port": "8080", "protocol": "tcp", "action": "accept", "direction": "in"})
test("Add Rule UF", "POST", f"/api/servers/{UF}/firewall/rules",
     {"port": "8080", "protocol": "tcp", "action": "allow", "direction": "in"})
test("Delete Rule EO", "DELETE", f"/api/servers/{EO}/firewall/rules/0")
test("Delete Rule UF", "DELETE", f"/api/servers/{UF}/firewall/rules/0")
test("Toggle Rule EO", "POST", f"/api/servers/{EO}/firewall/rules/0/toggle")

# === SERVICES ===
print("\n🔧 Services")
test("Add Service EO", "POST", f"/api/servers/{EO}/firewall/services", {"service": "http"})
test("Add Service UF", "POST", f"/api/servers/{UF}/firewall/services", {"service": "http"})
test("Remove Service EO", "DELETE", f"/api/servers/{EO}/firewall/services/http")
test("Remove Service UF", "DELETE", f"/api/servers/{UF}/firewall/services/http")

# === IP BLOCK ===
print("\n🚫 IP Block")
test("Block IP EO", "POST", f"/api/servers/{EO}/firewall/block-ip",
     {"ip": "1.2.3.4", "comment": "test"})
test("Block IP UF", "POST", f"/api/servers/{UF}/firewall/block-ip",
     {"ip": "1.2.3.4", "comment": "test"})
test("Blocked IPs EO", "GET", f"/api/servers/{EO}/firewall/blocked-ips")
test("Blocked IPs UF", "GET", f"/api/servers/{UF}/firewall/blocked-ips")
test("Unblock IP EO", "POST", f"/api/servers/{EO}/firewall/unblock-ip", {"ip": "1.2.3.4"})
test("Unblock IP UF", "POST", f"/api/servers/{UF}/firewall/unblock-ip", {"ip": "1.2.3.4"})

# === PORT FORWARD ===
print("\n🔀 Port Forward")
test("Add Forward EO", "POST", f"/api/servers/{EO}/firewall/port-forward",
     {"port": "8080", "to_addr": "192.168.1.100", "to_port": "80", "protocol": "tcp"})
test("Add Forward UF", "POST", f"/api/servers/{UF}/firewall/port-forward",
     {"port": "8080", "to_addr": "192.168.1.100", "to_port": "80", "protocol": "tcp"}, expect_success=False)
test("Delete Forward EO", "DELETE", f"/api/servers/{EO}/firewall/port-forward",
     {"port": "8080", "protocol": "tcp"})
test("Delete Forward UF", "DELETE", f"/api/servers/{UF}/firewall/port-forward",
     {"port": "8080", "protocol": "tcp"}, expect_success=False)

# === DNS ===
print("\n🌐 DNS")
test("Set DNS EO", "POST", f"/api/servers/{EO}/firewall/dns",
     {"servers": "8.8.8.8,1.1.1.1"})

# === ROUTES ===
print("\n🛤️ Routes")
test("Get Routes EO", "GET", f"/api/servers/{EO}/firewall/routes")
test("Get Routes UF", "GET", f"/api/servers/{UF}/firewall/routes")
test("Add Route EO", "POST", f"/api/servers/{EO}/firewall/routes",
     {"dst": "10.0.0.0/24", "gateway": "192.168.1.1"})
test("Delete Route EO", "DELETE", f"/api/servers/{EO}/firewall/routes/0")

# === IP ADDRESSES ===
print("\n📍 IP Addresses")
test("Get IPs EO", "GET", f"/api/servers/{EO}/firewall/ip-addresses")
test("Add IP EO", "POST", f"/api/servers/{EO}/firewall/ip-addresses",
     {"address": "10.0.0.1/24", "interface": "ether1"})
test("Delete IP EO", "DELETE", f"/api/servers/{EO}/firewall/ip-addresses/0")

# === ARP ===
print("\n📝 ARP")
test("Get ARP EO", "GET", f"/api/servers/{EO}/firewall/arp")
test("Add ARP EO", "POST", f"/api/servers/{EO}/firewall/arp",
     {"address": "192.168.1.100", "mac": "AA:BB:CC:DD:EE:FF", "interface": "ether1"})
test("Delete ARP EO", "DELETE", f"/api/servers/{EO}/firewall/arp/0")

# === DHCP ===
print("\n🏠 DHCP")
test("Get DHCP EO", "GET", f"/api/servers/{EO}/firewall/dhcp")

# === IP POOLS ===
print("\n🏊 IP Pools")
test("Get Pools EO", "GET", f"/api/servers/{EO}/firewall/ip-pools")
test("Add Pool EO", "POST", f"/api/servers/{EO}/firewall/ip-pools",
     {"name": "test-pool", "ranges": "10.0.0.100-10.0.0.200"})
test("Delete Pool EO", "DELETE", f"/api/servers/{EO}/firewall/ip-pools/0")

# === QUEUES ===
print("\n📊 Queues")
test("Get Queues EO", "GET", f"/api/servers/{EO}/firewall/queues")
test("Add Queue EO", "POST", f"/api/servers/{EO}/firewall/queues",
     {"name": "test-q", "target": "192.168.1.0/24", "max_limit": "10M/10M"})
test("Delete Queue EO", "DELETE", f"/api/servers/{EO}/firewall/queues/0")

# === BRIDGES ===
print("\n🌉 Bridges")
test("Get Bridges EO", "GET", f"/api/servers/{EO}/firewall/bridges")

# === DNS STATIC ===
print("\n📘 DNS Static")
test("Get DNS Static EO", "GET", f"/api/servers/{EO}/firewall/dns-static")
test("Add DNS Static EO", "POST", f"/api/servers/{EO}/firewall/dns-static",
     {"name": "test.local", "address": "192.168.1.50"})
test("Delete DNS Static EO", "DELETE", f"/api/servers/{EO}/firewall/dns-static/0")

# === NEIGHBORS ===
print("\n👥 Neighbors")
test("Get Neighbors EO", "GET", f"/api/servers/{EO}/firewall/neighbors")

# === ZONES ===
print("\n🗺️ Zones")
test("Get Zones EO", "GET", f"/api/servers/{EO}/firewall/zones")
test("Get Zones UF", "GET", f"/api/servers/{UF}/firewall/zones")
test("Get Zone Detail UF", "GET", f"/api/servers/{UF}/firewall/zones/public")
test("Set Default Zone UF", "POST", f"/api/servers/{UF}/firewall/zones/default",
     {"zone": "public"}, expect_success=False)

# === RICH RULES ===
print("\n📜 Rich Rules")
test("Add Rich Rule UF", "POST", f"/api/servers/{UF}/firewall/rich-rules",
     {"rule": "rule family=ipv4 source address=10.0.0.0/8 accept"}, expect_success=False)
test("Remove Rich Rule UF", "DELETE", f"/api/servers/{UF}/firewall/rich-rules",
     {"rule": "rule family=ipv4 source address=10.0.0.0/8 accept"}, expect_success=False)

# === FAIL2BAN ===
print("\n🔒 Fail2ban")
test("F2B Status EO", "GET", f"/api/servers/{EO}/firewall/fail2ban")
test("F2B Status UF", "GET", f"/api/servers/{UF}/firewall/fail2ban")
test("F2B Ban UF", "POST", f"/api/servers/{UF}/firewall/fail2ban/ban",
     {"ip": "1.2.3.4", "jail": "sshd"})
test("F2B Unban UF", "POST", f"/api/servers/{UF}/firewall/fail2ban/unban",
     {"ip": "1.2.3.4", "jail": "sshd"})

# === CONNECTIONS ===
print("\n🔗 Connections")
test("Connections EO", "GET", f"/api/servers/{EO}/firewall/connections")
test("Connections UF", "GET", f"/api/servers/{UF}/firewall/connections")
test("Conn Stats EO", "GET", f"/api/servers/{EO}/firewall/connection-stats")
test("Conn Stats UF", "GET", f"/api/servers/{UF}/firewall/connection-stats")

# === SECURITY SCAN ===
print("\n🛡️ Security Scan")
test("Scan EO", "GET", f"/api/servers/{EO}/firewall/security-scan")
test("Scan UF", "GET", f"/api/servers/{UF}/firewall/security-scan")

# === GEO BLOCK ===
print("\n🌍 Geo Block")
test("Geo Block EO", "POST", f"/api/servers/{EO}/firewall/geo-block",
     {"country_code": "CN"}, expect_success=False)
test("Geo Block UF", "POST", f"/api/servers/{UF}/firewall/geo-block",
     {"country_code": "CN"}, expect_success=False)

# === L7 PROTECTION ===
print("\n🛡️ L7 Protection")
test("L7 Status EO", "GET", f"/api/servers/{EO}/firewall/l7/status")
test("L7 Status UF", "GET", f"/api/servers/{UF}/firewall/l7/status")
test("L7 Scan EO", "GET", f"/api/servers/{EO}/firewall/l7/scan")
test("L7 Scan UF", "GET", f"/api/servers/{UF}/firewall/l7/scan")
test("L7 Apply EO", "POST", f"/api/servers/{EO}/firewall/l7/apply",
     {"protections": ["syn_flood"]})
test("L7 Apply UF", "POST", f"/api/servers/{UF}/firewall/l7/apply",
     {"protections": ["syn_flood"]})
test("L7 Remove EO", "POST", f"/api/servers/{EO}/firewall/l7/remove",
     {"protection": "syn_flood"})
test("L7 Events EO", "GET", f"/api/servers/{EO}/firewall/l7/events")

# === UNIFIED PROTECTION ===
print("\n🔰 Unified Protection")
test("Prot Status EO", "GET", f"/api/servers/{EO}/firewall/protection/status")
test("Prot Status UF", "GET", f"/api/servers/{UF}/firewall/protection/status")
test("Prot Scan EO", "GET", f"/api/servers/{EO}/firewall/protection/scan")
test("Prot Apply EO", "POST", f"/api/servers/{EO}/firewall/protection/apply",
     {"protections": ["syn_flood"]})
test("Prot Remove EO", "POST", f"/api/servers/{EO}/firewall/protection/remove",
     {"protection": "syn_flood"})
test("Prot Apply All EO", "POST", f"/api/servers/{EO}/firewall/protection/apply-all",
     {"protections": {"syn_flood": {"enabled": True}}})

# === L7 APPLY ALL ===
test("L7 Apply All EO", "POST", f"/api/servers/{EO}/firewall/l7/apply-all",
     {"protections": {"syn_flood": {"enabled": True}}})

# === BACKUPS ===
print("\n💾 Backups")
test("Create Backup EO", "POST", f"/api/servers/{EO}/firewall/backups")
test("Create Backup UF", "POST", f"/api/servers/{UF}/firewall/backups")
test("List Backups EO", "GET", f"/api/servers/{EO}/firewall/backups")
test("List Backups UF", "GET", f"/api/servers/{UF}/firewall/backups")
test("Restore Backup EO", "POST", f"/api/servers/{EO}/firewall/backups/restore",
     {"backup_id": "nonexistent"}, expect_success=False)
test("Delete Backup EO", "DELETE", f"/api/servers/{EO}/firewall/backups/nonexistent",
     expect_success=False)

# === NETWORK ANALYSER ===
print("\n📡 Network Analyser")
test("Net Summary EO", "GET", f"/api/servers/{EO}/network/summary")
test("Net Summary UF", "GET", f"/api/servers/{UF}/network/summary")
test("Net Bandwidth EO", "GET", f"/api/servers/{EO}/network/bandwidth")
test("Net Bandwidth UF", "GET", f"/api/servers/{UF}/network/bandwidth")
test("Net Top Talkers EO", "GET", f"/api/servers/{EO}/network/top-talkers")
test("Net Listening EO", "GET", f"/api/servers/{EO}/network/listening-ports")
test("Net Ping EO", "POST", f"/api/servers/{EO}/network/ping",
     {"target": "8.8.8.8", "count": 4})
test("Net Ping UF", "POST", f"/api/servers/{UF}/network/ping",
     {"target": "8.8.8.8", "count": 4})
test("Net Traceroute EO", "POST", f"/api/servers/{EO}/network/traceroute",
     {"target": "8.8.8.8"})
test("Net DNS EO", "POST", f"/api/servers/{EO}/network/dns-lookup",
     {"domain": "example.com", "type": "A"})
test("Net Port Check EO", "POST", f"/api/servers/{EO}/network/port-check",
     {"target": "8.8.8.8", "port": 443, "protocol": "tcp"})
test("Net Capture EO", "POST", f"/api/servers/{EO}/network/packet-capture",
     {"interface": "any", "count": 5})
test("Net Speed EO", "POST", f"/api/servers/{EO}/network/speed-test",
     {"target": "8.8.8.8", "duration": 3})
test("Net WHOIS EO", "POST", f"/api/servers/{EO}/network/whois",
     {"target": "example.com"})

# === LOGS ===
print("\n📝 Logs")
test("Logs", "GET", "/api/firewall/logs")
test("Log Stats", "GET", "/api/firewall/logs/stats")
test("Log IPs", "GET", "/api/firewall/logs/ips")
test("Log L7 Summary", "GET", "/api/firewall/logs/l7-summary")
test("Log DB Info", "GET", "/api/firewall/logs/db-info")
test("Log Export", "GET", "/api/firewall/logs/export")
test("5651 Status", "GET", "/api/firewall/logs/5651/status")
test("5651 Verify", "GET", "/api/firewall/logs/5651/verify")
test("5651 Seal", "POST", "/api/firewall/logs/5651/seal", {"note": "test-seal"})
test("Logs Page", "GET", "/firewall/logs", expect_html=True)

# === ISP MULTI-TENANT ===
print("\n🏢 ISP Multi-Tenant")
test("ISP Create Tenant", "POST", "/api/isp/tenants",
     {"name": "Test ISP Co", "email": "admin@test.com", "plan": "silver"})
test("ISP List Tenants", "GET", "/api/isp/tenants")
test("ISP Get Tenant", "GET", "/api/isp/tenants/1")
test("ISP Update Tenant", "PUT", "/api/isp/tenants/1",
     {"name": "Updated ISP", "plan": "gold"})
test("ISP Regenerate Key", "POST", "/api/isp/tenants/1/regenerate-key")
test("ISP Add Server", "POST", "/api/isp/tenants/1/servers",
     {"server_id": "srv-test", "ssh_host": "10.0.0.1", "label": "Test"})
test("ISP List Servers", "GET", "/api/isp/tenants/1/servers")
test("ISP Remove Server", "DELETE", "/api/isp/tenants/1/servers/srv-test")

# === ISP ALERTS ===
print("\n🔔 ISP Alerts")
_alert_res = test("ISP Create Alert", "POST", "/api/isp/tenants/1/alerts",
     {"alert_type": "ddos_detected", "message": "Test alert", "severity": "warning"})
test("ISP List Alerts", "GET", "/api/isp/tenants/1/alerts")
_alert_id = _alert_res.get("alert_id", 1) if _alert_res else 1
test("ISP Ack Alert", "POST", f"/api/isp/tenants/1/alerts/{_alert_id}/ack")

# === ISP WEBHOOKS ===
print("\n🔗 ISP Webhooks")
test("ISP Add Webhook", "POST", "/api/isp/tenants/1/webhooks",
     {"url": "https://hooks.example.com/fw", "events": ["rule_change"]})
test("ISP List Webhooks", "GET", "/api/isp/tenants/1/webhooks")

# === ISP SCHEDULED ===
print("\n⏰ ISP Scheduled Tasks")
test("ISP Add Scheduled", "POST", "/api/isp/tenants/1/scheduled",
     {"task_type": "backup", "cron_expr": "0 2 * * *", "server_id": "srv-01"})
test("ISP List Scheduled", "GET", "/api/isp/tenants/1/scheduled")

# === ISP CGNAT ===
print("\n🌐 ISP CGNAT")
test("ISP Add CGNAT Pool", "POST", "/api/isp/tenants/1/cgnat/pools",
     {"pool_name": "pool-test", "public_ip": "203.0.113.1", "ports_per_subscriber": 512})
test("ISP List CGNAT Pools", "GET", "/api/isp/tenants/1/cgnat/pools")

# === ISP IPAM ===
print("\n📋 ISP IPAM")
test("ISP Add IPAM Block", "POST", "/api/isp/tenants/1/ipam/blocks",
     {"cidr": "10.0.0.0/24", "description": "Test LAN", "gateway": "10.0.0.1"})
test("ISP List IPAM Blocks", "GET", "/api/isp/tenants/1/ipam/blocks")

# === ISP DASHBOARD ===
print("\n📊 ISP Dashboard")
test("ISP Dashboard", "GET", "/api/isp/dashboard")
test("ISP Tenant Report", "GET", "/api/isp/tenants/1/report")

# === ISP AUDIT ===
print("\n📜 ISP Audit")
test("ISP Audit Logs", "GET", "/api/isp/audit?limit=10")

# === ISP BULK ===
print("\n📦 ISP Bulk")
test("ISP Bulk History", "GET", "/api/isp/tenants/1/bulk/history")

# === SUMMARY ===
print(f"\n{'='*50}")
print(f"📊 Toplam: {results['ok'] + results['fail']} test")
print(f"   ✅ Başarılı: {results['ok']}")
print(f"   ❌ Başarısız: {results['fail']}")
if results["errors"]:
    print(f"\n🔴 Hatalar:")
    for e in results["errors"]:
        print(f"   • {e}")

sys.exit(0 if results["fail"] == 0 else 1)
