"""
EmareFirewall — CLI Arayüzü
=============================

Komut satırından bağımsız firewall yönetimi.

Kullanım:
    python -m emarefirewall status --host 1.2.3.4 --user root
    python -m emarefirewall rules --host 1.2.3.4
    python -m emarefirewall add-rule --host 1.2.3.4 --port 80 --proto tcp
    python -m emarefirewall block-ip --host 1.2.3.4 --ip 5.6.7.8
    python -m emarefirewall scan --host 1.2.3.4
    python -m emarefirewall fail2ban --host 1.2.3.4
    python -m emarefirewall connections --host 1.2.3.4
    python -m emarefirewall zones --host 1.2.3.4
"""

import argparse
import json
import os
import sys


def get_executor(args):
    """SSH executor oluştur."""
    if args.host == "localhost" or args.host == "127.0.0.1":
        from emarefirewall.ssh import SubprocessExecutor
        return SubprocessExecutor().execute, "localhost"

    from emarefirewall.ssh import ParamikoExecutor
    ssh = ParamikoExecutor()
    key_path = args.key or os.path.expanduser("~/.ssh/id_rsa")
    ssh.connect("target", host=args.host, user=args.user,
                port=args.port, key_path=key_path if os.path.exists(key_path) else None,
                password=args.password)
    return ssh.execute, "target"


def print_json(data):
    """JSON çıktısı."""
    print(json.dumps(data, indent=2, ensure_ascii=False))


def print_table(rows, headers):
    """Basit tablo çıktısı."""
    if not rows:
        print("  (boş)")
        return
    widths = [max(len(str(h)), max(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print(fmt.format(*[str(r[i]) for i in range(len(headers))]))


def main():
    parser = argparse.ArgumentParser(
        prog="emarefirewall",
        description="🔥 EmareFirewall — Bağımsız Güvenlik Duvarı Yönetimi"
    )
    parser.add_argument("command", choices=[
        "status", "rules", "enable", "disable",
        "add-rule", "delete-rule", "add-service", "remove-service",
        "block-ip", "unblock-ip", "blocked",
        "port-forward", "zones", "zone-detail",
        "rich-rule", "fail2ban", "f2b-ban", "f2b-unban",
        "connections", "conn-stats", "scan", "geo-block",
    ], help="Çalıştırılacak komut")
    parser.add_argument("--host", required=True, help="Hedef sunucu IP/hostname")
    parser.add_argument("--user", default="root", help="SSH kullanıcısı (varsayılan: root)")
    parser.add_argument("--port", type=int, default=22, help="SSH portu (varsayılan: 22)")
    parser.add_argument("--key", help="SSH private key dosyası")
    parser.add_argument("--password", help="SSH parolası (key yoksa)")
    parser.add_argument("--json", action="store_true", dest="json_output", help="JSON çıktı")

    # Komut parametreleri
    parser.add_argument("--rule-port", help="Port (add-rule, delete-rule)")
    parser.add_argument("--proto", default="tcp", help="Protokol: tcp/udp")
    parser.add_argument("--action", default="allow", help="İşlem: allow/deny")
    parser.add_argument("--from-ip", help="Kaynak IP (add-rule)")
    parser.add_argument("--rule-index", type=int, help="Kural indeksi (delete-rule)")
    parser.add_argument("--service", help="Servis adı (add-service, remove-service)")
    parser.add_argument("--ip", help="IP adresi (block-ip, unblock-ip)")
    parser.add_argument("--reason", help="Engelleme sebebi")
    parser.add_argument("--to-port", help="Hedef port (port-forward)")
    parser.add_argument("--to-addr", help="Hedef adres (port-forward)")
    parser.add_argument("--zone", help="Zone adı (zone-detail)")
    parser.add_argument("--rich", help="Rich rule metni")
    parser.add_argument("--jail", help="Fail2ban jail adı")
    parser.add_argument("--country", help="Ülke kodu (geo-block, örn: CN)")
    parser.add_argument("--limit", type=int, default=50, help="Bağlantı limiti")

    args = parser.parse_args()

    try:
        executor, server_id = get_executor(args)
    except Exception as e:
        print(f"❌ SSH bağlantı hatası: {e}", file=sys.stderr)
        sys.exit(1)

    from emarefirewall.manager import FirewallManager
    fw = FirewallManager(ssh_executor=executor)

    cmd = args.command

    try:
        if cmd == "status":
            result = fw.get_status(server_id)
            if args.json_output:
                print_json(result)
            else:
                print(f"🔥 Firewall Tipi: {result['type'] or 'Bulunamadı'}")
                print(f"   Durum: {'✅ Aktif' if result['active'] else '❌ Kapalı'}")
                print(f"   Zone: {result.get('active_zone', '-')}")
                print(f"   Kurallar: {len(result['rules'])}")
                print(f"   Servisler: {', '.join(result.get('services', [])) or '-'}")
                print(f"   Portlar: {', '.join(result.get('ports', [])) or '-'}")

        elif cmd == "rules":
            result = fw.get_status(server_id)
            if args.json_output:
                print_json(result["rules"])
            else:
                print(f"🔥 Firewall Kuralları ({result['type'] or '?'}):")
                rows = [(r["index"], r.get("type","?"), r["rule"]) for r in result["rules"]]
                print_table(rows, ["#", "Tip", "Kural"])

        elif cmd == "enable":
            ok, msg = fw.enable(server_id)
            print(f"{'✅' if ok else '❌'} {msg}")

        elif cmd == "disable":
            ok, msg = fw.disable(server_id)
            print(f"{'✅' if ok else '❌'} {msg}")

        elif cmd == "add-rule":
            if not args.rule_port:
                print("❌ --rule-port gerekli", file=sys.stderr); sys.exit(1)
            ok, msg = fw.add_rule(server_id, args.rule_port, args.proto, args.action, from_ip=args.from_ip or "")
            print(f"{'✅' if ok else '❌'} {msg}")

        elif cmd == "delete-rule":
            if not args.rule_index:
                print("❌ --rule-index gerekli", file=sys.stderr); sys.exit(1)
            ok, msg = fw.delete_rule(server_id, args.rule_index)
            print(f"{'✅' if ok else '❌'} {msg}")

        elif cmd == "add-service":
            if not args.service:
                print("❌ --service gerekli", file=sys.stderr); sys.exit(1)
            ok, msg = fw.add_service(server_id, args.service)
            print(f"{'✅' if ok else '❌'} {msg}")

        elif cmd == "remove-service":
            if not args.service:
                print("❌ --service gerekli", file=sys.stderr); sys.exit(1)
            ok, msg = fw.remove_service(server_id, args.service)
            print(f"{'✅' if ok else '❌'} {msg}")

        elif cmd == "block-ip":
            if not args.ip:
                print("❌ --ip gerekli", file=sys.stderr); sys.exit(1)
            ok, msg = fw.block_ip(server_id, args.ip, args.reason or "")
            print(f"{'✅' if ok else '❌'} {msg}")

        elif cmd == "unblock-ip":
            if not args.ip:
                print("❌ --ip gerekli", file=sys.stderr); sys.exit(1)
            ok, msg = fw.unblock_ip(server_id, args.ip)
            print(f"{'✅' if ok else '❌'} {msg}")

        elif cmd == "blocked":
            result = fw.get_blocked_ips(server_id)
            if args.json_output:
                print_json(result)
            else:
                print("🚫 Engelli IP'ler:")
                rows = [(b["index"], b["ip"]) for b in result]
                print_table(rows, ["#", "IP"])

        elif cmd == "port-forward":
            if not args.rule_port or not args.to_port:
                print("❌ --rule-port ve --to-port gerekli", file=sys.stderr); sys.exit(1)
            ok, msg = fw.add_port_forward(server_id, args.rule_port, args.to_port,
                                           args.to_addr or "", args.proto)
            print(f"{'✅' if ok else '❌'} {msg}")

        elif cmd == "zones":
            result = fw.get_zones(server_id)
            if args.json_output:
                print_json(result)
            else:
                print(f"🏗️ Zone'lar: {', '.join(result.get('zones', []))}")
                print(f"   Aktif: {result.get('active', '-')}")
                print(f"   Varsayılan: {result.get('default', '-')}")

        elif cmd == "zone-detail":
            if not args.zone:
                print("❌ --zone gerekli", file=sys.stderr); sys.exit(1)
            result = fw.get_zone_detail(server_id, args.zone)
            print_json(result) if args.json_output else print_json(result)

        elif cmd == "rich-rule":
            if not args.rich:
                print("❌ --rich gerekli", file=sys.stderr); sys.exit(1)
            ok, msg = fw.add_rich_rule(server_id, args.rich)
            print(f"{'✅' if ok else '❌'} {msg}")

        elif cmd == "fail2ban":
            result = fw.get_fail2ban_status(server_id)
            if args.json_output:
                print_json(result)
            else:
                print(f"🔒 Fail2ban: {'✅ Aktif' if result['active'] else '❌ Kapalı'}")
                print(f"   Jail'ler: {', '.join(result['jails']) or '-'}")
                for jail, info in result.get("banned_ips", {}).items():
                    print(f"   [{jail}] Anlık: {info['currently_banned']}, "
                          f"Toplam: {info['total_banned']}")
                    if info.get("banned_list"):
                        print(f"    → {', '.join(info['banned_list'])}")

        elif cmd == "f2b-ban":
            if not args.jail or not args.ip:
                print("❌ --jail ve --ip gerekli", file=sys.stderr); sys.exit(1)
            ok, msg = fw.fail2ban_ban(server_id, args.jail, args.ip)
            print(f"{'✅' if ok else '❌'} {msg}")

        elif cmd == "f2b-unban":
            if not args.jail or not args.ip:
                print("❌ --jail ve --ip gerekli", file=sys.stderr); sys.exit(1)
            ok, msg = fw.fail2ban_unban(server_id, args.jail, args.ip)
            print(f"{'✅' if ok else '❌'} {msg}")

        elif cmd == "connections":
            result = fw.get_connections(server_id, args.limit)
            if args.json_output:
                print_json(result)
            else:
                print(f"🌐 Aktif Bağlantılar ({len(result)}):")
                rows = [(c["proto"], c["state"], c["local"], c["peer"]) for c in result[:30]]
                print_table(rows, ["Proto", "Durum", "Yerel", "Uzak"])

        elif cmd == "conn-stats":
            result = fw.get_connection_stats(server_id)
            if args.json_output:
                print_json(result)
            else:
                print(f"📊 Bağlantı İstatistikleri:")
                print(f"   Toplam: {result['total']}")
                print(f"   ESTABLISHED: {result['established']}")
                print(f"   LISTENING: {result['listening']}")
                print(f"   TIME_WAIT: {result['time_wait']}")
                print(f"   CLOSE_WAIT: {result['close_wait']}")

        elif cmd == "scan":
            result = fw.security_scan(server_id)
            if args.json_output:
                print_json(result)
            else:
                score = result["score"]
                emoji = "🟢" if score >= 80 else "🟡" if score >= 50 else "🔴"
                print(f"{emoji} Güvenlik Skoru: {score}/100")
                for f in result.get("findings", []):
                    icon = {"critical":"🚨","high":"⚠️","medium":"🟡","low":"ℹ️"}.get(f["severity"],"?")
                    print(f"  {icon} [{f['severity'].upper()}] {f['title']}: {f['detail']}")
                if result.get("recommendations"):
                    print("\n💡 Öneriler:")
                    for r in result["recommendations"]:
                        print(f"  → {r}")

        elif cmd == "geo-block":
            if not args.country:
                print("❌ --country gerekli (örn: CN, RU)", file=sys.stderr); sys.exit(1)
            ok, msg = fw.geo_block_country(server_id, args.country)
            print(f"{'✅' if ok else '❌'} {msg}")

    except Exception as e:
        print(f"❌ Hata: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
