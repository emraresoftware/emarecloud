"""
Emare Security OS — Core Manager (Bağımsız)
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
import json
import secrets
import shlex
import time as _time
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
_VALID_ACTIONS = {'allow', 'deny', 'reject', 'limit', 'accept', 'drop'}
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


# ═══════════════════ Emare: Doğrulama & Yardımcılar ═══════════════════

_VALID_EMAREOS_CHAINS = {'input', 'forward', 'output'}
_VALID_EMAREOS_ACTIONS_MAP = {
    'allow': 'accept', 'accept': 'accept',
    'deny': 'drop', 'drop': 'drop',
    'reject': 'reject', 'limit': 'accept',  # limit → accept + connection-limit
}


def _validate_emareos_chain(chain: str) -> str:
    """Emare filter chain doğrular."""
    chain = (chain or 'input').strip().lower()
    if chain not in _VALID_EMAREOS_CHAINS:
        raise ValueError(f'Geçersiz chain: {chain}. İzin verilenler: {_VALID_EMAREOS_CHAINS}')
    return chain


def _mq(value: str) -> str:
    """Emare OS CLI value quoting — komut enjeksiyonunu engeller."""
    if not value:
        return '""'
    dangerous = [';', '\n', '\r', '\x00']
    for d in dangerous:
        if d in value:
            raise ValueError('Emare OS değerinde geçersiz karakter.')
    if ' ' in value or '"' in value:
        value = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{value}"'
    return value


def _parse_emareos_terse(output: str) -> list:
    """
    Emare 'print terse' çıktısını parse eder.
    Her satır:  <index> [<flags>] key=value key=value ...
    Döndürür: [{'_index': int, '_flags': str, 'key': 'value', ...}, ...]
    """
    results = []
    for line in output.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('Columns:') or line.startswith('#') or line.startswith('Flags:'):
            continue
        m = re.match(r'\s*(\d+)\s+(.*)', line)
        if not m:
            continue
        idx = int(m.group(1))
        rest = m.group(2)
        # Flags: satır başındaki büyük harfler (X=disabled, D=dynamic, I=invalid)
        fm = re.match(r'^([A-Z]+)\s+(.*)', rest)
        if fm:
            flags = fm.group(1)
            rest = fm.group(2)
        else:
            flags = ''
        entry = {'_index': idx, '_flags': flags}
        # key=value çiftleri — "quoted value" ve unquoted value desteği
        for kv in re.finditer(r'([\w-]+)=(?:"((?:[^"\\]|\\.)*)"|(\S*))', rest):
            key = kv.group(1)
            value = kv.group(2) if kv.group(2) is not None else kv.group(3)
            entry[key] = value
        results.append(entry)
    return results


class FirewallManager:
    """
    Bağımsız güvenlik duvarı yöneticisi.
    UFW ve firewalld desteği, fail2ban entegrasyonu, güvenlik taraması.
    """

    def __init__(self, ssh_executor: SSHExecutor, cache_ttl: int = 5,
                 cache_backend=None):
        """
        Args:
            ssh_executor: (server_id, command) -> (ok: bool, stdout: str, stderr: str)
            cache_ttl: Durum cache süresi (saniye). 0 = cache kapalı.
            cache_backend: DictCache/RedisCache nesnesi. None ise yerel dict kullanılır.
        """
        self._exec_fn = ssh_executor
        self._cache = cache_backend
        self._cache_ttl = cache_ttl
        # Fallback: cache_backend yoksa eski stil yerel dict
        if self._cache is None:
            self._type_cache = {}
            self._status_cache = {}
            self._l7_cache = {}

    def _exec(self, server_id: str, command: str) -> tuple:
        """SSH ile komut çalıştır."""
        return self._exec_fn(server_id, command)

    def _exec_multi(self, server_id: str, commands: list, sep: str = '___SEP___') -> list:
        """Birden fazla komutu tek SSH çağrısında çalıştır.
        Komutları ayırıcı ile birleştirir, sonucu böler.
        Returns: [(ok, stdout, stderr), ...] — her komut için ayrı sonuç.
        Not: Herhangi bir komut başarısız olursa, tüm çıktı tek parça döner.
        """
        if len(commands) == 1:
            return [self._exec(server_id, commands[0])]
        combined = f" && echo '{sep}' && ".join(commands)
        ok, out, err = self._exec(server_id, combined)
        if not ok:
            # Başarısız olursa, her komutu ayrı çalıştır (fallback)
            return [self._exec(server_id, cmd) for cmd in commands]
        parts = out.split(sep)
        # SEP yeterli parça üretmediyse fallback (mock executor için)
        if len(parts) < len(commands):
            return [self._exec(server_id, cmd) for cmd in commands]
        results = []
        for part in parts:
            results.append((True, part.strip(), ''))
        # Eksik kalan kısımlar varsa boş ekle
        while len(results) < len(commands):
            results.append((True, '', ''))
        return results

    def _invalidate_cache(self, server_id: str):
        """Durum ve L7 cache'ini temizle (yazma işlemlerinden sonra çağrılır)."""
        if self._cache is not None:
            self._cache.delete(f'fws:{server_id}')
            self._cache.delete(f'fwl:{server_id}')
        else:
            self._status_cache.pop(server_id, None)
            self._l7_cache.pop(server_id, None)

    def _detect_type(self, server_id: str, force: bool = False) -> Optional[str]:
        """Firewall tipini tespit et: 'ufw' | 'firewalld' | 'emareos' | None (cache'li)"""
        if not force:
            if self._cache is not None:
                cached = self._cache.get(f'fwt:{server_id}')
                if cached is not None:
                    return cached
            elif server_id in self._type_cache:
                return self._type_cache[server_id]
        ok, out, _ = self._exec(server_id, "which ufw 2>/dev/null")
        if ok and out and "ufw" in out:
            self._set_type_cache(server_id, "ufw")
            return "ufw"
        ok, out, _ = self._exec(server_id, "which firewall-cmd 2>/dev/null")
        if ok and out and "firewall-cmd" in out:
            self._set_type_cache(server_id, "firewalld")
            return "firewalld"
        # Emare OS tespit — /emare system info
        ok, out, _ = self._exec(server_id, "/emare system info")
        if ok and out and ("uptime" in out.lower() or "version" in out.lower()
                          or "emareos" in out.lower() or "device-model" in out.lower()):
            self._set_type_cache(server_id, "emareos")
            return "emareos"
        self._set_type_cache(server_id, None)
        return None

    def _set_type_cache(self, server_id: str, fw_type):
        """Firewall tipini cache'e yaz."""
        if self._cache is not None:
            self._cache.set(f'fwt:{server_id}', fw_type, ttl=300)
        else:
            self._type_cache[server_id] = fw_type

    # ═══════════════════ DURUM ═══════════════════

    def get_status(self, server_id: str) -> dict:
        """Güvenlik duvarı tam durumunu döndürür (TTL cache'li)."""
        if self._cache_ttl > 0:
            if self._cache is not None:
                cached = self._cache.get(f'fws:{server_id}')
                if cached is not None:
                    return cached
            else:
                cached = self._status_cache.get(server_id)
                if cached and _time.monotonic() - cached[0] < self._cache_ttl:
                    return cached[1]
        result = self._get_status_uncached(server_id)
        if self._cache_ttl > 0:
            if self._cache is not None:
                self._cache.set(f'fws:{server_id}', result, ttl=self._cache_ttl)
            else:
                self._status_cache[server_id] = (_time.monotonic(), result)
        return result

    def _get_status_uncached(self, server_id: str) -> dict:
        """Güvenlik duvarı tam durumunu döndürür (cache'siz)."""
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

        # ── Emare OS ──
        ok, out, _ = self._exec(server_id, "/emare system info")
        if ok and out and ("uptime" in out.lower() or "version" in out.lower()):
            result["type"] = "emareos"
            self._parse_emareos_full(server_id, result, out)
            return result

        result["message"] = "Bu sunucuda UFW, firewalld veya Emare bulunamadı."
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

    def _parse_emareos_full(self, server_id: str, result: dict, resource_out: str):
        """Emare OS tam durumunu parse et."""
        # Sistem bilgisi — tüm resource alanlarını çıkar
        for line in resource_out.split('\n'):
            s = line.strip()
            if not s or ':' not in s:
                continue
            key_lower = s.split(':', 1)[0].strip().lower()
            val = s.split(':', 1)[1].strip()
            if key_lower == 'version':
                result['emareos_version'] = val
            elif key_lower == 'device-model':
                result['emareos_board'] = val
            elif key_lower == 'uptime':
                result['emareos_uptime'] = val
            elif key_lower == 'cpu-load':
                result['emareos_cpu_load'] = val
            elif key_lower == 'free-memory':
                result['emareos_free_memory'] = val
            elif key_lower == 'total-memory':
                result['emareos_total_memory'] = val
            elif key_lower == 'free-hdd-space':
                result['emareos_free_hdd'] = val
            elif key_lower == 'total-hdd-space':
                result['emareos_total_hdd'] = val
            elif key_lower == 'cpu':
                result['emareos_cpu'] = val
            elif key_lower == 'cpu-count':
                result['emareos_cpu_count'] = val
            elif key_lower == 'platform':
                result['emareos_platform'] = val
        # Identity
        ok, out, _ = self._exec(server_id, '/emare system identity')
        if ok and out:
            for line in out.split('\n'):
                if 'name' in line.lower() and ':' in line:
                    result['emareos_identity'] = line.split(':', 1)[1].strip()

        # ── Filter Kuralları ──
        ok, out, _ = self._exec(server_id,
            '/emare firewall rules print terse without-paging')
        rules = []
        idx = 0
        has_enabled = False
        if ok and out:
            entries = _parse_emareos_terse(out)
            for e in entries:
                idx += 1
                disabled = 'X' in e.get('_flags', '')
                if not disabled:
                    has_enabled = True
                chain = e.get('chain', '?')
                action = e.get('action', '?')
                proto = e.get('protocol', '')
                dst_port = e.get('dst-port', '')
                src_addr = e.get('src-address', '')
                src_list = e.get('src-blocklist', '')
                comment = e.get('comment', '')
                # Kural tipi belirle
                if src_list == 'blocked' or (action == 'drop' and src_addr):
                    rtype = 'ip_block'
                elif dst_port:
                    rtype = 'port'
                elif e.get('connection-state'):
                    rtype = 'other'
                else:
                    rtype = 'other'
                rule_text_parts = [f'chain={chain}', f'action={action}']
                if proto:
                    rule_text_parts.append(f'protocol={proto}')
                if dst_port:
                    rule_text_parts.append(f'dst-port={dst_port}')
                if src_addr:
                    rule_text_parts.append(f'src-address={src_addr}')
                if src_list:
                    rule_text_parts.append(f'src-blocklist={src_list}')
                if e.get('connection-state'):
                    rule_text_parts.append(f'connection-state={e["connection-state"]}')
                if comment:
                    rule_text_parts.append(f'comment="{comment}"')
                rule_text = ' '.join(rule_text_parts)
                if disabled:
                    rule_text = f'[X] {rule_text}'
                rules.append({
                    'index': e.get('_index', idx - 1),
                    'rule': rule_text,
                    'type': rtype,
                    'disabled': disabled,
                })
                if dst_port:
                    result['ports'].append(f'{dst_port}/{proto}' if proto else dst_port)

        result['active'] = has_enabled or idx > 0
        result['rules'] = rules

        # ── Servisler (Emare OS) — detaylı bilgi ──
        ok, out, _ = self._exec(server_id,
            '/emare services print terse without-paging')
        services_detail = []
        if ok and out:
            for e in _parse_emareos_terse(out):
                name = e.get('name', '')
                port = e.get('port', '')
                disabled = e.get('disabled', 'no') == 'yes' or 'X' in e.get('_flags', '')
                if name:
                    result['services'].append(name)
                    services_detail.append({
                        'name': name, 'port': port,
                        'disabled': disabled,
                        'index': e.get('_index', ''),
                    })
                    if not disabled:
                        result['ports'].append(f'{port}/tcp' if port else name)
        result['services_detail'] = services_detail

        # ── Address Lists (engelli IP'ler) ──
        ok, out, _ = self._exec(server_id,
            '/emare firewall blocklist print terse without-paging where list=blocked')
        if ok and out:
            for e in _parse_emareos_terse(out):
                addr = e.get('address', '')
                if addr:
                    result['blocked_ips'].append(addr)

        # ── NAT / Port Forward ──
        ok, out, _ = self._exec(server_id,
            '/emare firewall nat print terse without-paging')
        if ok and out:
            for e in _parse_emareos_terse(out):
                chain = e.get('chain', '')
                action = e.get('action', '')
                if chain == 'dstnat' and action == 'dst-nat':
                    dp = e.get('dst-port', '')
                    proto = e.get('protocol', 'tcp')
                    to_addr = e.get('to-addresses', '')
                    to_port = e.get('to-ports', '')
                    fwd = f'port={dp}:proto={proto}:toport={to_port}'
                    if to_addr:
                        fwd += f':toaddr={to_addr}'
                    result['forward_ports'].append(fwd)
                elif chain == 'srcnat' and action == 'masquerade':
                    result['masquerade'] = True

        # ── Interfaces — detaylı bilgi ──
        ok, out, _ = self._exec(server_id,
            '/emare network interfaces print terse without-paging')
        interfaces_detail = []
        if ok and out:
            for e in _parse_emareos_terse(out):
                name = e.get('name', '')
                itype = e.get('type', '')
                running = e.get('running', 'no')
                disabled = 'X' in e.get('_flags', '')
                if name:
                    interfaces_detail.append({
                        'name': name, 'type': itype,
                        'running': running == 'yes' or 'R' in e.get('_flags', ''),
                        'disabled': disabled,
                    })
                    if not disabled:
                        result['interfaces'].append(name)
        result['interfaces_detail'] = interfaces_detail

        # ── DNS Yapılandırması ──
        ok, out, _ = self._exec(server_id, '/emare dns config print')
        dns_config = {}
        if ok and out:
            for line in out.split('\n'):
                s = line.strip()
                if ':' in s:
                    k = s.split(':', 1)[0].strip().lower().replace('-', '_')
                    v = s.split(':', 1)[1].strip()
                    dns_config[k] = v
        result['dns_config'] = dns_config

    # ═══════════════════ ETKİNLEŞTİR / KAPAT ═══════════════════

    def enable(self, server_id: str) -> tuple:
        """Güvenlik duvarını etkinleştirir. -> (ok, msg)"""
        self._invalidate_cache(server_id)
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
        if fw == "emareos":
            ok, out, err = self._exec(server_id,
                '/emare firewall rules enable [find]')
            return ok, (out + " " + err).strip() or "Emare filter kuralları etkinleştirildi."
        return False, "Desteklenen güvenlik duvarı bulunamadı."

    def disable(self, server_id: str) -> tuple:
        """Güvenlik duvarını devre dışı bırakır. -> (ok, msg)"""
        self._invalidate_cache(server_id)
        fw = self._detect_type(server_id)
        if fw == "ufw":
            ok, out, err = self._exec(server_id, "sudo ufw disable 2>&1")
            return ok, (out + " " + err).strip() or "UFW devre dışı bırakıldı."
        if fw == "firewalld":
            ok, out, err = self._exec(server_id,
                "sudo systemctl stop firewalld 2>&1 && sudo systemctl disable firewalld 2>&1")
            return ok, (out + " " + err).strip()
        if fw == "emareos":
            ok, out, err = self._exec(server_id,
                '/emare firewall rules disable [find]')
            return ok, (out + " " + err).strip() or "Emare filter kuralları devre dışı bırakıldı."
        return False, "Desteklenen güvenlik duvarı bulunamadı."

    # ═══════════════════ PORT / SERVİS KURAL ═══════════════════

    def add_rule(self, server_id: str, port: str, protocol: str = "tcp",
                 action: str = "allow", direction: str = "in",
                 from_ip: str = "", to_port: str = "") -> tuple:
        """Port kuralı ekler. to_port verilirse port yönlendirme (DNAT) yapar. -> (ok, msg)"""
        self._invalidate_cache(server_id)
        fw = self._detect_type(server_id)
        if not fw:
            return False, "Desteklenen güvenlik duvarı bulunamadı."
        try:
            port = _validate_port(port)
            protocol = _validate_protocol(protocol)
            action = _validate_action(action)
            if from_ip and from_ip.strip():
                from_ip = _validate_ip(from_ip)
            if to_port and to_port.strip():
                to_port = _validate_port(to_port)
        except ValueError as e:
            return False, str(e)

        # ── Dış port ≠ İç port → port yönlendirme (DNAT) ──
        has_redirect = to_port and to_port.strip() and to_port.strip() != port.strip()

        if fw == "ufw":
            if has_redirect:
                # UFW: before.rules ile REDIRECT (aynı makine içi)
                ok, out, err = self._exec(server_id,
                    f"sudo iptables -t nat -A PREROUTING -p {_sq(protocol)} "
                    f"--dport {_sq(port)} -j REDIRECT --to-port {_sq(to_port)} 2>&1")
                msg = (out + " " + err).strip()
                if ok:
                    # İç portu da aç
                    spec = f"{to_port}/{protocol}"
                    self._exec(server_id, f"sudo ufw allow {_sq(spec)} 2>&1")
                    return True, msg or f"Dış port {port} → iç port {to_port} yönlendirme eklendi."
                return False, msg or "Port yönlendirme eklenemedi."
            spec = port if "/" in port else f"{port}/{protocol}"
            from_part = f" from {_sq(from_ip)}" if from_ip and from_ip.strip() else ""
            ok, out, err = self._exec(server_id, f"sudo ufw {_sq(action)} {_sq(spec)}{from_part} 2>&1")
            msg = (out + " " + err).strip()
            if ok or "existing" in msg.lower() or "added" in msg.lower():
                return True, msg or "Kural eklendi."
            return False, msg

        if fw == "firewalld":
            if has_redirect:
                # firewalld: forward-port
                fwd_spec = f"port={port}:proto={protocol}:toport={to_port}"
                ok, out, err = self._exec(server_id,
                    f"sudo firewall-cmd --permanent --add-forward-port={_sq(fwd_spec)} 2>&1")
                if ok:
                    self._exec(server_id, "sudo firewall-cmd --permanent --add-masquerade 2>&1")
                    self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
                return ok, (out + " " + err).strip() or f"Dış port {port} → iç port {to_port} yönlendirme eklendi."
            pp = port if "/" in port else f"{port}/{protocol}"
            ok, out, err = self._exec(server_id,
                f"sudo firewall-cmd --permanent --add-port={_sq(pp)} 2>&1")
            if ok:
                self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
            return ok, (out + " " + err).strip() or "Kural eklendi."

        if fw == "emareos":
            if has_redirect:
                # Emare: dst-nat kuralı
                cmd_parts = ['/emare firewall nat add chain=dstnat action=dst-nat',
                             f'protocol={_mq(protocol)}',
                             f'dst-port={_mq(port)}',
                             f'to-ports={_mq(to_port)}']
                if from_ip and from_ip.strip():
                    cmd_parts.append(f'src-address={_mq(from_ip)}')
                ok, out, err = self._exec(server_id, ' '.join(cmd_parts))
                return ok, (out + " " + err).strip() or f"Emare dış port {port} → iç port {to_port} yönlendirme eklendi."
            mt_action = _VALID_EMAREOS_ACTIONS_MAP.get(action, 'accept')
            chain = 'input'  # varsayılan chain
            cmd_parts = ['/emare firewall rules add',
                         f'chain={_mq(chain)}',
                         f'action={_mq(mt_action)}',
                         f'protocol={_mq(protocol)}']
            # Port aralığı Emare formatında: 80 veya 80-90
            mt_port = port.replace('/', '')
            if '/' in port:
                mt_port = port.split('/')[0]
            cmd_parts.append(f'dst-port={_mq(mt_port)}')
            if from_ip and from_ip.strip():
                cmd_parts.append(f'src-address={_mq(from_ip)}')
            ok, out, err = self._exec(server_id, ' '.join(cmd_parts))
            return ok, (out + " " + err).strip() or "Emare filter kuralı eklendi."
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
        if fw == "emareos":
            # Emare servisini etkinleştir
            ok, out, err = self._exec(server_id,
                f'/emare services enable [find name={_mq(service)}]')
            if ok:
                return True, f"Emare servisi '{service}' etkinleştirildi."
            # Servis bulunamadıysa, port bazlı filter rule ekle
            svc_ports = {'http': '80', 'https': '443', 'ssh': '22', 'ftp': '21',
                         'dns': '53', 'mysql': '3306', 'postgresql': '5432',
                         'redis': '6379', 'smtp': '25', 'imap': '143'}
            sp = svc_ports.get(service)
            if sp:
                return self.add_rule(server_id, sp, 'tcp', 'allow')
            return False, f"Emare servisi bulunamadı: {service}"
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
        if fw == "emareos":
            ok, out, err = self._exec(server_id,
                f'/emare services disable [find name={_mq(service)}]')
            return ok, (out + " " + err).strip() or f"Emare servisi '{service}' devre dışı bırakıldı."
        return False, "Desteklenen güvenlik duvarı bulunamadı."

    def toggle_rule(self, server_id: str, rule_index: int, enable: bool) -> tuple:
        """Emare kural enable/disable toggle. -> (ok, msg)"""
        fw = self._detect_type(server_id)
        if fw != 'emareos':
            return False, "Kural toggle sadece Emare için desteklenir."
        rule_index = int(rule_index)
        action = 'enable' if enable else 'disable'
        ok, out, err = self._exec(server_id,
            f'/emare firewall rules {action} {rule_index}')
        if ok:
            return True, f"Kural #{rule_index} {'etkinleştirildi' if enable else 'devre dışı bırakıldı'}."
        return False, (out + " " + err).strip() or f"Kural {action} başarısız."

    def set_dns(self, server_id: str, servers: str = None,
                allow_remote: bool = None) -> tuple:
        """Emare DNS ayarlarını günceller. -> (ok, msg)"""
        fw = self._detect_type(server_id)
        if fw != 'emareos':
            return False, "DNS yönetimi sadece Emare için desteklenir."
        parts = []
        if servers is not None:
            # Basit doğrulama
            for s in servers.split(','):
                s = s.strip()
                if s and not re.match(r'^[\d.]+$', s):
                    return False, f"Geçersiz DNS sunucu adresi: {s}"
            parts.append(f'servers={servers.strip()}')
        if allow_remote is not None:
            parts.append(f'allow-remote-requests={"yes" if allow_remote else "no"}')
        if not parts:
            return False, "Değişiklik yok."
        cmd = '/emare dns config set ' + ' '.join(parts)
        ok, out, err = self._exec(server_id, cmd)
        return ok, (out + " " + err).strip() or "DNS ayarları güncellendi."

    # ══════════════════════════════════════════════════════════════
    #  ROUTING / NETWORK YÖNETİMİ  (Emare OS)
    # ══════════════════════════════════════════════════════════════

    # ── Static Routes ──────────────────────────────────────────────

    def get_routes(self, server_id: str) -> list:
        ok, out, _ = self._exec(server_id,
            '/emare network routes print terse without-paging')
        return _parse_emareos_terse(out) if ok else []

    def add_route(self, server_id: str, dst: str,
                  gateway: str, distance: int = 1,
                  comment: str = '') -> tuple:
        parts = [f'/emare network routes add dst-address={_mq(dst)}',
                 f'gateway={_mq(gateway)}',
                 f'distance={int(distance)}']
        if comment:
            parts.append(f'comment={_mq(comment)}')
        ok, out, err = self._exec(server_id, ' '.join(parts))
        return ok, (out + " " + err).strip() or "Rota eklendi."

    def remove_route(self, server_id: str, index: int) -> tuple:
        ok, out, err = self._exec(server_id,
            f'/emare network routes remove numbers={int(index)}')
        return ok, (out + " " + err).strip() or "Rota silindi."

    # ── IP Address ─────────────────────────────────────────────────

    def get_ip_addresses(self, server_id: str) -> list:
        ok, out, _ = self._exec(server_id,
            '/emare network addresses print terse without-paging')
        return _parse_emareos_terse(out) if ok else []

    def add_ip_address(self, server_id: str, address: str,
                       interface: str, comment: str = '') -> tuple:
        parts = [f'/emare network addresses add address={_mq(address)}',
                 f'interface={_mq(interface)}']
        if comment:
            parts.append(f'comment={_mq(comment)}')
        ok, out, err = self._exec(server_id, ' '.join(parts))
        return ok, (out + " " + err).strip() or "IP adresi eklendi."

    def remove_ip_address(self, server_id: str, index: int) -> tuple:
        ok, out, err = self._exec(server_id,
            f'/emare network addresses remove numbers={int(index)}')
        return ok, (out + " " + err).strip() or "IP adresi silindi."

    # ── ARP ────────────────────────────────────────────────────────

    def get_arp_table(self, server_id: str) -> list:
        ok, out, _ = self._exec(server_id,
            '/emare network arp print terse without-paging')
        return _parse_emareos_terse(out) if ok else []

    def add_arp_entry(self, server_id: str, address: str,
                      mac: str, interface: str) -> tuple:
        cmd = (f'/emare network arp add address={_mq(address)}'
               f' mac-address={_mq(mac)}'
               f' interface={_mq(interface)}')
        ok, out, err = self._exec(server_id, cmd)
        return ok, (out + " " + err).strip() or "ARP kaydı eklendi."

    def remove_arp_entry(self, server_id: str, index: int) -> tuple:
        ok, out, err = self._exec(server_id,
            f'/emare network arp remove numbers={int(index)}')
        return ok, (out + " " + err).strip() or "ARP kaydı silindi."

    # ── DHCP ───────────────────────────────────────────────────────

    def get_dhcp_servers(self, server_id: str) -> list:
        ok, out, _ = self._exec(server_id,
            '/emare network dhcp server print terse without-paging')
        return _parse_emareos_terse(out) if ok else []

    def get_dhcp_leases(self, server_id: str) -> list:
        ok, out, _ = self._exec(server_id,
            '/emare network dhcp lease print terse without-paging')
        return _parse_emareos_terse(out) if ok else []

    def get_dhcp_networks(self, server_id: str) -> list:
        ok, out, _ = self._exec(server_id,
            '/emare network dhcp network print terse without-paging')
        return _parse_emareos_terse(out) if ok else []

    # ── IP Pool ────────────────────────────────────────────────────

    def get_ip_pools(self, server_id: str) -> list:
        ok, out, _ = self._exec(server_id,
            '/emare network pools print terse without-paging')
        return _parse_emareos_terse(out) if ok else []

    def add_ip_pool(self, server_id: str, name: str,
                    ranges: str) -> tuple:
        cmd = (f'/emare network pools add name={_mq(name)}'
               f' ranges={_mq(ranges)}')
        ok, out, err = self._exec(server_id, cmd)
        return ok, (out + " " + err).strip() or "IP havuzu eklendi."

    def remove_ip_pool(self, server_id: str, index: int) -> tuple:
        ok, out, err = self._exec(server_id,
            f'/emare network pools remove numbers={int(index)}')
        return ok, (out + " " + err).strip() or "IP havuzu silindi."

    # ── Queue (Bant Genişliği) ─────────────────────────────────────

    def get_queues(self, server_id: str) -> list:
        ok, out, _ = self._exec(server_id,
            '/emare queue print terse without-paging')
        return _parse_emareos_terse(out) if ok else []

    def add_queue(self, server_id: str, name: str,
                  target: str, max_limit: str,
                  comment: str = '') -> tuple:
        parts = [f'/emare queue add name={_mq(name)}',
                 f'target={_mq(target)}',
                 f'max-limit={_mq(max_limit)}']
        if comment:
            parts.append(f'comment={_mq(comment)}')
        ok, out, err = self._exec(server_id, ' '.join(parts))
        return ok, (out + " " + err).strip() or "Kuyruk eklendi."

    def remove_queue(self, server_id: str, index: int) -> tuple:
        ok, out, err = self._exec(server_id,
            f'/emare queue remove numbers={int(index)}')
        return ok, (out + " " + err).strip() or "Kuyruk silindi."

    # ── Bridge ─────────────────────────────────────────────────────

    def get_bridges(self, server_id: str) -> dict:
        ok1, out1, _ = self._exec(server_id,
            '/emare network bridges print terse without-paging')
        ok2, out2, _ = self._exec(server_id,
            '/emare network bridge-ports print terse without-paging')
        return {
            'bridges': _parse_emareos_terse(out1) if ok1 else [],
            'ports':   _parse_emareos_terse(out2) if ok2 else [],
        }

    # ── DNS Static Entries ─────────────────────────────────────────

    def get_dns_static(self, server_id: str) -> list:
        ok, out, _ = self._exec(server_id,
            '/emare dns static print terse without-paging')
        return _parse_emareos_terse(out) if ok else []

    def add_dns_static(self, server_id: str,
                       name: str, address: str) -> tuple:
        cmd = (f'/emare dns static add name={_mq(name)}'
               f' address={_mq(address)}')
        ok, out, err = self._exec(server_id, cmd)
        return ok, (out + " " + err).strip() or "DNS kaydı eklendi."

    def remove_dns_static(self, server_id: str, index: int) -> tuple:
        ok, out, err = self._exec(server_id,
            f'/emare dns static remove numbers={int(index)}')
        return ok, (out + " " + err).strip() or "DNS kaydı silindi."

    # ── Neighbors ──────────────────────────────────────────────────

    def get_neighbors(self, server_id: str) -> list:
        ok, out, _ = self._exec(server_id,
            '/emare network neighbors print terse without-paging')
        return _parse_emareos_terse(out) if ok else []

    def delete_rule(self, server_id: str, rule_index: int) -> tuple:
        """İndeks bazlı kural siler. -> (ok, msg)"""
        self._invalidate_cache(server_id)
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

        if status["type"] == "emareos":
            # Emare 0-based index ile remove
            ok, out, err = self._exec(server_id,
                f'/emare firewall rules remove numbers={int(rule_index)}')
            return ok, (out + " " + err).strip() or "Emare kuralı silindi."
        return False, "Desteklenmiyor."

    # ═══════════════════ IP ENGELLEME ═══════════════════

    def block_ip(self, server_id: str, ip: str, reason: str = "") -> tuple:
        """IP adresini engeller (drop). -> (ok, msg)"""
        self._invalidate_cache(server_id)
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
        if fw == "emareos":
            # Address list'e ekle
            comment = f'blocked by emare-security-os'
            if reason:
                comment += f': {reason[:64]}'
            ok, out, err = self._exec(server_id,
                f'/emare firewall blocklist add list=blocked address={_mq(ip)} '
                f'comment={_mq(comment)}')
            if not ok:
                return False, (out + " " + err).strip() or "Address list'e eklenemedi."
            # blocked listesi için drop kuralı var mı kontrol et, yoksa ekle
            ok2, out2, _ = self._exec(server_id,
                '/emare firewall rules print terse without-paging where '
                'src-blocklist=blocked action=drop')
            if not out2 or not out2.strip() or \
               'src-blocklist=blocked' not in (out2 or ''):
                self._exec(server_id,
                    '/emare firewall rules add chain=input action=drop '
                    'src-blocklist=blocked comment="emare-security-os: drop blocked"')
            return True, f"{ip} Emare engel listesi'e eklendi."
        return False, "Desteklenen güvenlik duvarı bulunamadı."

    def unblock_ip(self, server_id: str, ip: str) -> tuple:
        """IP engelini kaldırır. -> (ok, msg)"""
        self._invalidate_cache(server_id)
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
        if fw == "emareos":
            ok, out, err = self._exec(server_id,
                f'/emare firewall blocklist remove [find address={_mq(ip)} list=blocked]')
            return ok, (out + " " + err).strip() or f"{ip} Emare engeli kaldırıldı."
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
        elif fw == "emareos":
            ok, out, _ = self._exec(server_id,
                '/emare firewall blocklist print terse without-paging where list=blocked')
            if ok and out:
                idx = 0
                for e in _parse_emareos_terse(out):
                    addr = e.get('address', '')
                    if addr:
                        idx += 1
                        comment = e.get('comment', '')
                        blocked.append({"index": e.get('_index', idx),
                                        "ip": addr, "comment": comment})
        return blocked

    # ═══════════════════ PORT YÖNLENDİRME ═══════════════════

    def add_port_forward(self, server_id: str, port: str, to_port: str,
                         to_addr: str = "", protocol: str = "tcp") -> tuple:
        """Port yönlendirme ekler. -> (ok, msg)"""
        self._invalidate_cache(server_id)
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
        if fw == "emareos":
            cmd_parts = ['/emare firewall nat add chain=dstnat action=dst-nat',
                         f'protocol={_mq(protocol)}',
                         f'dst-port={_mq(port)}',
                         f'to-ports={_mq(to_port)}']
            if to_addr and to_addr.strip():
                cmd_parts.append(f'to-addresses={_mq(to_addr)}')
            ok, out, err = self._exec(server_id, ' '.join(cmd_parts))
            if ok:
                # Masquerade kuralı da ekle (yoksa)
                ok2, out2, _ = self._exec(server_id,
                    '/emare firewall nat print terse without-paging where '
                    'chain=srcnat action=masquerade')
                if not out2 or 'masquerade' not in (out2 or ''):
                    self._exec(server_id,
                        '/emare firewall nat add chain=srcnat action=masquerade '
                        'comment="emare-security-os: masquerade"')
            return ok, (out + " " + err).strip() or "Emare port yönlendirme eklendi."
        return False, "Desteklenen güvenlik duvarı bulunamadı."

    def remove_port_forward(self, server_id: str, port: str, to_port: str,
                            to_addr: str = "", protocol: str = "tcp") -> tuple:
        """Port yönlendirme kaldırır. -> (ok, msg)"""
        self._invalidate_cache(server_id)
        fw = self._detect_type(server_id)
        if fw == "emareos":
            try:
                port = _validate_port(port)
                protocol = _validate_protocol(protocol)
            except ValueError as e:
                return False, str(e)
            # NAT kuralını bul ve sil
            ok, out, _ = self._exec(server_id,
                '/emare firewall nat print terse without-paging where '
                f'chain=dstnat dst-port={_mq(port)} protocol={_mq(protocol)}')
            if ok and out:
                entries = _parse_emareos_terse(out)
                if entries:
                    idx = entries[0].get('_index', 0)
                    ok2, out2, err2 = self._exec(server_id,
                        f'/emare firewall nat remove numbers={int(idx)}')
                    return ok2, (out2 + " " + err2).strip() or "Emare NAT kuralı kaldırıldı."
            return False, "Emare NAT kuralı bulunamadı."
        if fw != "firewalld":
            return False, "Sadece firewalld ve Emare destekleniyor."
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
        if fw == "emareos":
            ok, out, _ = self._exec(server_id,
                '/emare firewall zone print terse without-paging')
            zones = []
            default_zone = ""
            if ok and out:
                for e in _parse_emareos_terse(out):
                    name = e.get('name', '')
                    if name:
                        zones.append(name)
                        if e.get('default', '') == 'yes':
                            default_zone = name
            active = default_zone
            return {"zones": zones, "active": active, "default": default_zone}
        if fw != "firewalld":
            return {"zones": [], "active": "", "default": "",
                    "message": "Zone yönetimi desteklenmiyor."}
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
        try:
            zone = _validate_zone(zone)
        except ValueError as e:
            return False, str(e)
        if fw == "emareos":
            ok, out, err = self._exec(server_id,
                f'/emare firewall zone set [find name={_mq(zone)}] default=yes')
            return ok, (out + " " + err).strip() or f"Varsayılan zone: {zone}"
        if fw != "firewalld":
            return False, "Zone yönetimi desteklenmiyor."
        ok, out, err = self._exec(server_id,
            f"sudo firewall-cmd --set-default-zone={_sq(zone)} 2>&1")
        return ok, (out + " " + err).strip() or f"Varsayılan zone: {zone}"

    def get_zone_detail(self, server_id: str, zone: str) -> dict:
        """Zone detaylarını döndürür."""
        fw = self._detect_type(server_id)
        try:
            zone = _validate_zone(zone)
        except ValueError:
            return {"error": "Geçersiz zone adı."}
        if fw == "emareos":
            ok, out, _ = self._exec(server_id,
                f'/emare firewall zone detail name={_mq(zone)}')
            if not ok or not out:
                return {"error": f"Zone '{zone}' bilgisi alınamadı."}
            detail = {"zone": zone, "services": [], "ports": [], "rich_rules": [],
                      "interfaces": [], "masquerade": False, "forward_ports": []}
            for line in out.strip().split('\n'):
                s = line.strip()
                if s.startswith('interfaces:'):
                    v = s.replace('interfaces:', '').strip()
                    detail['interfaces'] = v.split(',') if v else []
                elif s.startswith('services:'):
                    v = s.replace('services:', '').strip()
                    detail['services'] = v.split(',') if v else []
                elif s.startswith('ports:'):
                    v = s.replace('ports:', '').strip()
                    detail['ports'] = v.split(',') if v else []
                elif s.startswith('masquerade:'):
                    detail['masquerade'] = 'yes' in s
                elif s.startswith('forward-ports:'):
                    v = s.replace('forward-ports:', '').strip()
                    detail['forward_ports'] = v.split(',') if v and v != 'none' else []
                elif s.startswith('rules:'):
                    v = s.replace('rules:', '').strip()
                    if v and v != 'none':
                        detail['rich_rules'] = [r.strip() for r in v.split(';') if r.strip()]
            return detail
        if fw != "firewalld":
            return {"error": "Zone yönetimi desteklenmiyor."}
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
        """Rich rule ekler. -> (ok, msg)"""
        fw = self._detect_type(server_id)
        try:
            rule = _validate_rich_rule(rule)
        except ValueError as e:
            return False, str(e)
        if fw == "emareos":
            ok, out, err = self._exec(server_id,
                f'/emare firewall zone rule add rule={_mq(rule)}')
            return ok, (out + " " + err).strip() or "Kural eklendi."
        if fw == "ufw":
            return False, "Rich rule sadece firewalld/emareos'ta desteklenir."
        if fw == "firewalld":
            ok, out, err = self._exec(server_id,
                f"sudo firewall-cmd --permanent --add-rich-rule={_sq(rule)} 2>&1")
            if ok:
                self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
            return ok, (out + " " + err).strip() or "Rich rule eklendi."
        return False, "Desteklenen güvenlik duvarı bulunamadı."

    def remove_rich_rule(self, server_id: str, rule: str) -> tuple:
        """Rich rule kaldırır. -> (ok, msg)"""
        fw = self._detect_type(server_id)
        try:
            rule = _validate_rich_rule(rule)
        except ValueError as e:
            return False, str(e)
        if fw == "emareos":
            ok, out, err = self._exec(server_id,
                f'/emare firewall zone rule remove rule={_mq(rule)}')
            return ok, (out + " " + err).strip() or "Kural kaldırıldı."
        if fw != "firewalld":
            return False, "Rich rule desteklenmiyor."
        ok, out, err = self._exec(server_id,
            f"sudo firewall-cmd --permanent --remove-rich-rule={_sq(rule)} 2>&1")
        if ok:
            self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
        return ok, (out + " " + err).strip() or "Rich rule kaldırıldı."

    # ═══════════════════ FAIL2BAN ═══════════════════

    def get_fail2ban_status(self, server_id: str) -> dict:
        """Fail2ban / Emare OS saldırı tespit durumunu döndürür."""
        fw = self._detect_type(server_id)
        if fw == "emareos":
            result = {"installed": True, "active": False, "jails": [], "banned_ips": {}}
            ok, out, _ = self._exec(server_id,
                '/emare system intrusion-detection status')
            if ok and out:
                if 'enabled: yes' in out.lower() or 'active: yes' in out.lower():
                    result['active'] = True
            ok2, out2, _ = self._exec(server_id,
                '/emare system intrusion-detection jail print terse without-paging')
            if ok2 and out2:
                for e in _parse_emareos_terse(out2):
                    jail_name = e.get('name', '')
                    if jail_name:
                        result['jails'].append(jail_name)
                        info = {
                            'currently_banned': int(e.get('currently-banned', 0)),
                            'total_banned': int(e.get('total-banned', 0)),
                            'banned_list': []
                        }
                        ok3, out3, _ = self._exec(server_id,
                            f'/emare system intrusion-detection jail banned '
                            f'name={_mq(jail_name)}')
                        if ok3 and out3:
                            for ip_line in out3.strip().split('\n'):
                                ip_val = ip_line.strip()
                                if ip_val and _VALID_IP_RE.match(ip_val):
                                    info['banned_list'].append(ip_val)
                        result['banned_ips'][jail_name] = info
            return result
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
        """Fail2ban / Emare OS ile IP ban eder. -> (ok, msg)"""
        try:
            ip = _validate_ip(ip)
            jail = _validate_jail(jail)
        except ValueError as e:
            return False, str(e)
        fw = self._detect_type(server_id)
        if fw == "emareos":
            ok, out, err = self._exec(server_id,
                f'/emare system intrusion-detection jail ban '
                f'name={_mq(jail)} ip={_mq(ip)}')
            return ok, (out + " " + err).strip() or f"{ip} ban edildi."
        ok, out, err = self._exec(server_id,
            f"sudo fail2ban-client set {_sq(jail)} banip {_sq(ip)} 2>&1")
        return ok, (out + " " + err).strip() or f"{ip} ban edildi."

    def fail2ban_unban(self, server_id: str, jail: str, ip: str) -> tuple:
        """Fail2ban / Emare OS'tan IP unban eder. -> (ok, msg)"""
        try:
            ip = _validate_ip(ip)
            jail = _validate_jail(jail)
        except ValueError as e:
            return False, str(e)
        fw = self._detect_type(server_id)
        if fw == "emareos":
            ok, out, err = self._exec(server_id,
                f'/emare system intrusion-detection jail unban '
                f'name={_mq(jail)} ip={_mq(ip)}')
            return ok, (out + " " + err).strip() or f"{ip} unban edildi."
        ok, out, err = self._exec(server_id,
            f"sudo fail2ban-client set {_sq(jail)} unbanip {_sq(ip)} 2>&1")
        return ok, (out + " " + err).strip() or f"{ip} unban edildi."

    # ═══════════════════ BAĞLANTI İZLEME ═══════════════════

    def get_connections(self, server_id: str, limit: int = 50) -> list:
        """Aktif ağ bağlantılarını listeler."""
        limit = max(1, min(int(limit), 500))  # 1-500 arasında sınırla
        fw = self._detect_type(server_id)
        connections = []

        if fw == "emareos":
            ok, out, _ = self._exec(server_id,
                f'/emare firewall connections print terse without-paging count={limit}')
            if ok and out:
                for e in _parse_emareos_terse(out):
                    proto = e.get('protocol', '')
                    src = e.get('src-address', '')
                    dst = e.get('dst-address', '')
                    tcp_state = e.get('tcp-state', e.get('connection-state', ''))
                    connections.append({
                        'proto': proto,
                        'state': tcp_state,
                        'recv_q': '',
                        'send_q': '',
                        'local': dst,
                        'peer': src,
                        'process': e.get('orig-bytes', ''),
                    })
            return connections

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
        fw = self._detect_type(server_id)

        if fw == "emareos":
            ok, out, _ = self._exec(server_id,
                '/emare firewall connections print terse without-paging')
            if ok and out:
                for e in _parse_emareos_terse(out):
                    stats['total'] += 1
                    tcp_state = e.get('tcp-state', '').lower()
                    if 'established' in tcp_state:
                        stats['established'] += 1
                    elif 'time-wait' in tcp_state:
                        stats['time_wait'] += 1
                    elif 'close' in tcp_state:
                        stats['close_wait'] += 1
                    # src-address format: ip:port
                    src = e.get('src-address', '')
                    dst = e.get('dst-address', '')
                    if ':' in dst:
                        port = dst.rsplit(':', 1)[-1]
                        if port.isdigit():
                            stats['by_port'][port] = stats['by_port'].get(port, 0) + 1
                    if ':' in src:
                        ip = src.rsplit(':', 1)[0]
                        if ip:
                            stats['by_ip'][ip] = stats['by_ip'].get(ip, 0) + 1
            stats['top_ips'] = sorted(stats['by_ip'].items(), key=lambda x: x[1], reverse=True)[:10]
            stats['top_ports'] = sorted(stats['by_port'].items(), key=lambda x: x[1], reverse=True)[:10]
            return stats

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

        fw = status.get("type")

        # ── Emare özel güvenlik taraması ──
        if fw == "emareos":
            return self._security_scan_emareos(server_id, scan, status)

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

    def _security_scan_emareos(self, server_id: str, scan: dict, status: dict) -> dict:
        """Emare OS özel güvenlik taraması."""
        # 1. Tehlikeli servisler açık mı?
        dangerous_services = {'telnet': 23, 'ftp': 21, 'api': 8728, 'www': 80}
        ok, out, _ = self._exec(server_id,
            '/emare services print terse without-paging')
        if ok and out:
            for e in _parse_emareos_terse(out):
                name = e.get('name', '')
                disabled = e.get('disabled', 'no') == 'yes' or 'X' in e.get('_flags', '')
                if name in dangerous_services and not disabled:
                    scan['score'] -= 10
                    scan['findings'].append({'severity': 'high',
                        'title': f'{name.upper()} servisi açık',
                        'detail': f'Port {dangerous_services[name]} üzerinden {name} erişimi açık.'})
                    scan['recommendations'].append(
                        f"/emare services disable [find name={name}] ile kapatın.")

        # 2. Default admin şifresi?
        ok, out, _ = self._exec(server_id,
            '/emare users print terse without-paging')
        if ok and out:
            for e in _parse_emareos_terse(out):
                name = e.get('name', '')
                group = e.get('group', '')
                if name == 'admin' and group == 'full':
                    scan['score'] -= 5
                    scan['findings'].append({'severity': 'medium',
                        'title': 'Varsayılan admin kullanıcısı aktif',
                        'detail': 'admin kullanıcısı full yetkilerle mevcut.'})
                    scan['recommendations'].append(
                        "admin yerine özel bir kullanıcı oluşturun veya admin'i devre dışı bırakın.")

        # 3. Filter kuralları var mı?
        filter_rules = status.get('rules', [])
        enabled_rules = [r for r in filter_rules if not r.get('disabled', False)]
        if not enabled_rules:
            scan['score'] -= 20
            scan['findings'].append({'severity': 'critical',
                'title': 'Aktif filter kuralı yok',
                'detail': 'Emare\'te hiç aktif firewall filter kuralı bulunamadı.'})
            scan['recommendations'].append(
                "En azından temel input chain kuralları ekleyin.")

        # 4. Input chain drop kuralı var mı? (güvenli yapılandırma)
        has_input_drop = any(
            'chain=input' in r.get('rule', '') and 'action=drop' in r.get('rule', '')
            for r in enabled_rules
        )
        if enabled_rules and not has_input_drop:
            scan['score'] -= 10
            scan['findings'].append({'severity': 'high',
                'title': 'Input chain sonunda drop kuralı yok',
                'detail': 'Emare input chain sonunda catch-all drop kuralı eksik.'})
            scan['recommendations'].append(
                "/emare firewall rules add chain=input action=drop ile varsayılan drop ekleyin.")

        # 5. Emare Desktop erişimi MAC üzerinden açık mı?
        ok, out, _ = self._exec(server_id,
            '/emare tools mac-access print')
        if ok and out and 'disabled: no' in out.lower():
            scan['score'] -= 5
            scan['findings'].append({'severity': 'medium',
                'title': 'MAC Emare Desktop erişimi açık',
                'detail': 'Layer 2 üzerinden MAC-Emare Desktop erişimi aktif.'})
            scan['recommendations'].append(
                "/emare tools mac-access set disabled=yes ile kapatın.")

        # 6. Emare OS güncel mi?
        version = status.get('emareos_version', '')
        if version:
            ok, out, _ = self._exec(server_id,
                '/emare system update check')
            if ok and out and 'latest-version' in out.lower():
                import re as _re
                current = _re.search(r'installed-version:\s*(\S+)', out)
                latest = _re.search(r'latest-version:\s*(\S+)', out)
                if current and latest and current.group(1) != latest.group(1):
                    scan['score'] -= 5
                    scan['findings'].append({'severity': 'low',
                        'title': 'Emare OS güncel değil',
                        'detail': f'Mevcut: {current.group(1)}, Son: {latest.group(1)}'})
                    scan['recommendations'].append(
                        "/emare system update install ile güncelleyin.")

        # 7. DNS cache amplification?
        ok, out, _ = self._exec(server_id,
            '/emare dns config print')
        if ok and out:
            if 'allow-remote-requests: yes' in out.lower():
                scan['score'] -= 10
                scan['findings'].append({'severity': 'high',
                    'title': 'DNS uzak isteklere açık',
                    'detail': 'allow-remote-requests=yes — DNS amplification saldırısına açık.'})
                scan['recommendations'].append(
                    "/emare dns config set allow-remote-requests=no yapın veya sadece güvenli ağlara izin verin.")

        scan['score'] = max(0, scan['score'])
        return scan

    # ═══════════════════ GEO-BLOCK ═══════════════════

    def geo_block_country(self, server_id: str, country_code: str) -> tuple:
        """Ülke bazlı engelleme. -> (ok, msg)"""
        fw = self._detect_type(server_id)
        try:
            cc = _validate_country(country_code)
        except ValueError as e:
            return False, str(e)
        if fw == "emareos":
            list_name = f"geoblock_{cc}"
            # Liste oluştur ve CIDR'ları yükle
            self._exec(server_id,
                f'/emare firewall blocklist add list={_mq(list_name)} '
                f'address=0.0.0.0/0 comment={_mq(f"geo-block {cc} placeholder")}')
            self._exec(server_id,
                f'/emare firewall blocklist remove [find list={_mq(list_name)} '
                f'address=0.0.0.0/0]')
            ok, out, err = self._exec(server_id,
                f'/emare firewall geo-block add country={_mq(cc)} '
                f'list={_mq(list_name)}')
            if not ok:
                return False, (out + " " + err).strip() or f"{cc} engellenemedi."
            # Drop kuralı var mı kontrol et, yoksa ekle
            ok2, out2, _ = self._exec(server_id,
                f'/emare firewall rules print terse without-paging where '
                f'src-blocklist={_mq(list_name)} action=drop')
            if not out2 or list_name not in (out2 or ''):
                self._exec(server_id,
                    f'/emare firewall rules add chain=input action=drop '
                    f'src-blocklist={_mq(list_name)} '
                    f'comment={_mq(f"emare-security-os: geo-block {cc}")}')
            return True, f"{cc} ülkesi engellendi (liste: {list_name})."
        if fw != "firewalld":
            return False, "Geo-block desteklenmiyor."
        ipset_name = f"geoblock_{cc}"
        zone_url = f"https://www.ipdeny.com/ipblocks/data/countries/{cc.lower()}.zone"
        cmds = [
            f"sudo ipset create {_sq(ipset_name)} hash:net 2>/dev/null || true",
            f"sudo wget -qO /tmp/{_sq(cc)}.zone {_sq(zone_url)} 2>/dev/null",
            f"sudo bash -c 'for ip in $(cat /tmp/{_sq(cc)}.zone 2>/dev/null); "
            f"do ipset add {_sq(ipset_name)} $ip 2>/dev/null; done'",
            f"sudo firewall-cmd --permanent "
            f"--add-rich-rule={_sq(f'rule source ipset={ipset_name} drop')} 2>&1",
            "sudo firewall-cmd --reload 2>&1",
        ]
        for cmd in cmds:
            self._exec(server_id, cmd)
        return True, f"{cc} ülkesi engellendi (ipset: {ipset_name})."

    def geo_unblock_country(self, server_id: str, country_code: str) -> tuple:
        """Ülke engelini kaldırır. -> (ok, msg)"""
        fw = self._detect_type(server_id)
        try:
            cc = _validate_country(country_code)
        except ValueError as e:
            return False, str(e)
        list_name = f"geoblock_{cc}"
        if fw == "emareos":
            self._exec(server_id,
                f'/emare firewall rules remove [find src-blocklist={_mq(list_name)} '
                f'action=drop]')
            self._exec(server_id,
                f'/emare firewall geo-block remove country={_mq(cc)}')
            self._exec(server_id,
                f'/emare firewall blocklist remove [find list={_mq(list_name)}]')
            return True, f"{cc} engeli kaldırıldı."
        if fw == "firewalld":
            self._exec(server_id,
                f"sudo firewall-cmd --permanent "
                f"--remove-rich-rule={_sq(f'rule source ipset={list_name} drop')} 2>&1")
            self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
            self._exec(server_id,
                f"sudo ipset destroy {_sq(list_name)} 2>/dev/null")
            return True, f"{cc} engeli kaldırıldı."
        return False, "Geo-block desteklenmiyor."

    def get_geo_blocked(self, server_id: str) -> list:
        """Engelli ülkeleri listeler."""
        fw = self._detect_type(server_id)
        blocked = []
        if fw == "emareos":
            ok, out, _ = self._exec(server_id,
                '/emare firewall geo-block print terse without-paging')
            if ok and out:
                for e in _parse_emareos_terse(out):
                    cc = e.get('country', '')
                    if cc:
                        blocked.append({
                            'country': cc,
                            'list': e.get('list', f'geoblock_{cc}'),
                            'count': int(e.get('count', 0)),
                        })
        elif fw == "firewalld":
            ok, out, _ = self._exec(server_id,
                "sudo ipset list -name 2>/dev/null")
            if ok and out:
                for line in out.strip().split('\n'):
                    name = line.strip()
                    if name.startswith('geoblock_'):
                        cc = name.replace('geoblock_', '').upper()
                        count_ok, count_out, _ = self._exec(server_id,
                            f"sudo ipset list {_sq(name)} 2>/dev/null | "
                            f"grep -c '^[0-9]'")
                        cnt = 0
                        if count_ok and count_out:
                            try:
                                cnt = int(count_out.strip())
                            except ValueError:
                                pass
                        blocked.append({
                            'country': cc,
                            'list': name,
                            'count': cnt,
                        })
        return blocked

    # ═══════════════════ L7 (APPLICATION LAYER) KORUMASI ═══════════════════

    def get_l7_status(self, server_id: str) -> dict:
        """Sunucudaki tüm katman koruma durumunu kontrol eder (TTL cache'li)."""
        if self._cache_ttl > 0:
            if self._cache is not None:
                cached = self._cache.get(f'fwl:{server_id}')
                if cached is not None:
                    return cached
            else:
                cached = self._l7_cache.get(server_id)
                if cached and _time.monotonic() - cached[0] < self._cache_ttl:
                    return cached[1]
        result = self._get_l7_status_uncached(server_id)
        if self._cache_ttl > 0:
            if self._cache is not None:
                self._cache.set(f'fwl:{server_id}', result, ttl=self._cache_ttl)
            else:
                self._l7_cache[server_id] = (_time.monotonic(), result)
        return result

    def _get_l7_status_uncached(self, server_id: str) -> dict:
        """Sunucudaki tüm katman koruma durumunu kontrol eder."""
        result = {
            # L7 orijinal
            'syn_flood': False,
            'http_flood': False,
            'slowloris': False,
            'icmp_flood': False,
            'port_scan': False,
            'bogus_tcp': False,
            'connection_limit': False,
            'nginx_waf': False,
            'nginx_rate_limit': False,
            'nginx_bad_bots': False,
            'nginx_sql_injection': False,
            'nginx_xss': False,
            'nginx_path_traversal': False,
            'nginx_method_filter': False,
            'nginx_request_size': False,
            'kernel_hardening': False,
            # L3 — Ağ Katmanı
            'l3_bogon_filter': False,
            'l3_fragment_protection': False,
            'l3_ip_options': False,
            'l3_spoof_protection': False,
            # L4 — Transport Katmanı
            'l4_udp_flood': False,
            'l4_protocol_filter': False,
            'l4_mss_clamp': False,
            'l4_tcp_timestamps': False,
            # L7 — Ek
            'l7_dns_amplification': False,
            'l7_hsts': False,
            'l7_smuggling': False,
            'l7_gzip_bomb': False,
            'details': {},
        }
        fw = self._detect_type(server_id)

        # ── iptables + sysctl + nginx tespit — TEK SSH çağrısı ──
        ok, out, _ = self._exec(server_id, (
            "{"
            " echo '==IPTABLES=='; sudo iptables -L -n 2>/dev/null | head -200;"
            " echo '==MANGLE=='; sudo iptables -t mangle -L FORWARD -n 2>/dev/null | head -50;"
            " echo '==SYSCTL=='; sudo sysctl"
            " net.ipv4.tcp_fin_timeout"
            " net.ipv4.tcp_syncookies"
            " net.ipv4.conf.all.rp_filter"
            " net.ipv4.conf.all.log_martians"
            " net.ipv4.tcp_timestamps"
            " 2>/dev/null;"
            " echo '==NGINX==';"
            " if test -f /etc/nginx/nginx.conf; then"
            "   echo 'HAS_NGINX=yes';"
            "   sudo grep -rl 'modsecurity\\|naxsi\\|waf' /etc/nginx/ 2>/dev/null | head -1 && echo 'WAF=yes';"
            "   sudo grep -rl 'limit_req' /etc/nginx/ 2>/dev/null | head -1 && echo 'RATELIMIT=yes';"
            "   sudo grep -rl 'bot\\|crawler\\|spider' /etc/nginx/ 2>/dev/null | head -1 && echo 'BOTS=yes';"
            "   sudo grep -rlE 'select.*union|sql.*inject' /etc/nginx/ 2>/dev/null | head -1 && echo 'SQL=yes';"
            "   sudo grep -rlE 'script|xss|onerror' /etc/nginx/ 2>/dev/null | head -1 && echo 'XSS=yes';"
            "   sudo grep -rlE 'client_max_body_size' /etc/nginx/ 2>/dev/null | head -1 && echo 'REQSIZE=yes';"
            "   sudo grep -rlE 'limit_except|allow_methods' /etc/nginx/ 2>/dev/null | head -1 && echo 'METHOD=yes';"
            "   sudo grep -rlE '\\.\\./' /etc/nginx/ 2>/dev/null | head -1 && echo 'TRAVERSAL=yes';"
            "   sudo grep -rl 'Strict-Transport-Security' /etc/nginx/ 2>/dev/null | head -1 && echo 'HSTS=yes';"
            "   sudo grep -rl 'ignore_invalid_headers\\|underscores_in_headers' /etc/nginx/ 2>/dev/null | head -1 && echo 'SMUGGLING=yes';"
            "   test -f /etc/nginx/conf.d/emare_security_gzip.conf && echo 'GZIPBOMB=yes';"
            " else echo 'HAS_NGINX=no'; fi;"
            " echo '==END==';"
            "}"
        ))
        all_output = (out or '') if ok else ''
        # iptables kuralları parse
        ipt_section = ''
        mangle_section = ''
        sysctl_section = ''
        nginx_section = ''
        current = ''
        for line in all_output.split('\n'):
            ls = line.strip()
            if ls == '==IPTABLES==':
                current = 'ipt'; continue
            elif ls == '==MANGLE==':
                current = 'mangle'; continue
            elif ls == '==SYSCTL==':
                current = 'sysctl'; continue
            elif ls == '==NGINX==':
                current = 'nginx'; continue
            elif ls == '==END==':
                break
            if current == 'ipt':
                ipt_section += line + '\n'
            elif current == 'mangle':
                mangle_section += line + '\n'
            elif current == 'sysctl':
                sysctl_section += line + '\n'
            elif current == 'nginx':
                nginx_section += line + '\n'

        # ── iptables kuralları analizi ──
        rules = ipt_section.lower()
        if rules:
            if 'syn-flood' in rules or 'syn_flood' in rules or ('hashlimit' in rules and 'syn' in rules):
                result['syn_flood'] = True
            if 'http-flood' in rules or 'http_flood' in rules or ('hashlimit' in rules and 'http' in rules):
                result['http_flood'] = True
            if 'connlimit' in rules or 'conn-limit' in rules:
                result['connection_limit'] = True
            if 'portscan' in rules or 'port-scan' in rules or 'psd' in rules:
                result['port_scan'] = True
            if 'bogus' in rules or 'invalid' in rules:
                result['bogus_tcp'] = True
            if 'icmp' in rules and ('limit' in rules or 'drop' in rules):
                result['icmp_flood'] = True
            # L3 kontrolleri
            if 'bogon_filter' in rules or 'bogon' in rules:
                result['l3_bogon_filter'] = True
            if 'fragment' in rules:
                result['l3_fragment_protection'] = True
            if 'ipv4options' in rules:
                result['l3_ip_options'] = True
            # L4 kontrolleri
            if 'udp_flood' in rules or ('udp' in rules and 'hashlimit' in rules):
                result['l4_udp_flood'] = True
            if 'sctp' in rules and 'drop' in rules:
                result['l4_protocol_filter'] = True
            # L7 DNS
            if 'dns_amp' in rules or ('dport 53' in rules and 'hashlimit' in rules):
                result['l7_dns_amplification'] = True

        # ── Mangle tablosu ──
        if 'tcpmss' in mangle_section.lower():
            result['l4_mss_clamp'] = True

        # ── Sysctl analizi ──
        for line in sysctl_section.split('\n'):
            ls = line.strip()
            if 'tcp_fin_timeout' in ls:
                try:
                    val = int(ls.split('=')[-1].strip())
                    if val <= 15:
                        result['slowloris'] = True
                    result['details']['tcp_fin_timeout'] = val
                except (ValueError, IndexError):
                    pass
            elif 'tcp_syncookies' in ls and '= 1' in ls:
                result['kernel_hardening'] = True
            elif 'rp_filter' in ls and '= 1' in ls:
                result['l3_spoof_protection'] = True
            elif 'log_martians' in ls and '= 1' in ls:
                pass  # rp_filter + log_martians birlikte spoof protection
            elif 'tcp_timestamps' in ls and '= 0' in ls:
                result['l4_tcp_timestamps'] = True
        # rp_filter ve log_martians birlikte olmalı
        if result.get('l3_spoof_protection') and 'log_martians' in sysctl_section and '= 1' in sysctl_section:
            result['l3_spoof_protection'] = True
        elif 'rp_filter' not in sysctl_section:
            result['l3_spoof_protection'] = False

        # ── Nginx analizi ──
        has_nginx = 'HAS_NGINX=yes' in nginx_section
        if has_nginx:
            if 'WAF=yes' in nginx_section:
                result['nginx_waf'] = True
            if 'RATELIMIT=yes' in nginx_section:
                result['nginx_rate_limit'] = True
            if 'BOTS=yes' in nginx_section:
                result['nginx_bad_bots'] = True
            if 'SQL=yes' in nginx_section:
                result['nginx_sql_injection'] = True
            if 'XSS=yes' in nginx_section:
                result['nginx_xss'] = True
            if 'REQSIZE=yes' in nginx_section:
                result['nginx_request_size'] = True
            if 'METHOD=yes' in nginx_section:
                result['nginx_method_filter'] = True
            if 'TRAVERSAL=yes' in nginx_section:
                result['nginx_path_traversal'] = True
            if 'HSTS=yes' in nginx_section:
                result['l7_hsts'] = True
            if 'SMUGGLING=yes' in nginx_section:
                result['l7_smuggling'] = True
            if 'GZIPBOMB=yes' in nginx_section:
                result['l7_gzip_bomb'] = True

        # Emare ek L3/L4/L7 kontrolleri — tek SSH çağrısı
        if fw == 'emareos':
            eo_results = self._exec_multi(server_id, [
                '/emare firewall rules print terse without-paging',
                '/emare firewall rules print terse without-paging where comment~"emare-security-os"',
                '/emare firewall mangle print terse without-paging where comment~"emare-security-os"',
                '/emare firewall raw print terse without-paging 2>/dev/null',
            ])
            # [0] = tüm filter kuralları
            if eo_results[0][0] and eo_results[0][1]:
                eo_all = eo_results[0][1].lower()
                if 'syn-flood' in eo_all or ('tcp-flags' in eo_all and 'syn' in eo_all):
                    result['syn_flood'] = True
                if 'connection-limit' in eo_all:
                    result['connection_limit'] = True
                if 'icmp' in eo_all and ('limit' in eo_all or 'drop' in eo_all):
                    result['icmp_flood'] = True
                if 'port-scan' in eo_all or 'psd' in eo_all:
                    result['port_scan'] = True
                if 'tcp-flags' in eo_all and 'invalid' in eo_all:
                    result['bogus_tcp'] = True
            # [1] = emare-security-os comment'li kurallar
            if eo_results[1][0] and eo_results[1][1]:
                mt_rules = eo_results[1][1].lower()
                if 'bogon' in mt_rules:
                    result['l3_bogon_filter'] = True
                if 'fragment' in mt_rules:
                    result['l3_fragment_protection'] = True
                if 'ip options' in mt_rules:
                    result['l3_ip_options'] = True
                if 'spoof' in mt_rules:
                    result['l3_spoof_protection'] = True
                if 'udp' in mt_rules and ('flood' in mt_rules or 'rate' in mt_rules):
                    result['l4_udp_flood'] = True
                if 'sctp' in mt_rules or 'dccp' in mt_rules:
                    result['l4_protocol_filter'] = True
                if 'dns' in mt_rules and ('amp' in mt_rules or 'rate' in mt_rules):
                    result['l7_dns_amplification'] = True
            # [2] = mangle
            if eo_results[2][0] and eo_results[2][1] and 'mss' in eo_results[2][1].lower():
                result['l4_mss_clamp'] = True
            # [3] = raw
            if eo_results[3][0] and eo_results[3][1] and 'ddos' in eo_results[3][1].lower():
                result['http_flood'] = True

        result['details']['has_nginx'] = has_nginx
        result['details']['firewall_type'] = fw
        return result

    # ═══════ Tüm Katman Koruma Tipi Seti ═══════
    _ALL_PROTECTIONS = {
        # L7 (mevcut)
        'syn_flood', 'http_flood', 'slowloris', 'icmp_flood',
        'port_scan', 'bogus_tcp', 'connection_limit',
        'kernel_hardening', 'nginx_waf', 'nginx_rate_limit',
        'nginx_bad_bots', 'nginx_sql_injection', 'nginx_xss',
        'nginx_path_traversal', 'nginx_method_filter',
        'nginx_request_size',
        # L3 — Ağ Katmanı
        'l3_bogon_filter', 'l3_fragment_protection',
        'l3_ip_options', 'l3_spoof_protection',
        # L4 — Transport Katmanı
        'l4_udp_flood', 'l4_protocol_filter',
        'l4_mss_clamp', 'l4_tcp_timestamps',
        # L7 — Ek Uygulama Katmanı
        'l7_dns_amplification', 'l7_hsts',
        'l7_smuggling', 'l7_gzip_bomb',
    }

    def apply_l7_protection(self, server_id: str, protections: list) -> dict:
        """Seçilen koruma kurallarını sunucuya uygular (tüm katmanlar).

        Args:
            protections: Uygulanacak koruma listesi. L3/L4/L7 tüm tipler desteklenir.

        Returns:
            dict: Her koruma türü için ok/msg sonucu.
        """
        self._invalidate_cache(server_id)
        _VALID_PROTECTIONS = self._ALL_PROTECTIONS
        results = {}
        fw = self._detect_type(server_id)

        for prot in protections:
            if prot not in _VALID_PROTECTIONS:
                results[prot] = {'ok': False, 'msg': f'Bilinmeyen koruma türü: {prot}'}
                continue

            if fw == 'emareos':
                ok, msg = self._apply_l7_emareos(server_id, prot)
            else:
                ok, msg = self._apply_l7_linux(server_id, prot, fw)
            results[prot] = {'ok': ok, 'msg': msg}

        return results

    def _apply_l7_linux(self, server_id: str, prot: str, fw: str) -> tuple:
        """Linux sunucularda (UFW/firewalld) L7 koruma uygula."""

        if prot == 'syn_flood':
            cmds = [
                "sudo iptables -N SYN_FLOOD 2>/dev/null || true",
                "sudo iptables -F SYN_FLOOD 2>/dev/null || true",
                "sudo iptables -A SYN_FLOOD -p tcp --syn -m hashlimit "
                "--hashlimit-above 30/sec --hashlimit-burst 10 "
                "--hashlimit-mode srcip --hashlimit-name syn_flood "
                "-j DROP",
                "sudo iptables -A SYN_FLOOD -j RETURN",
                "sudo iptables -C INPUT -p tcp --syn -j SYN_FLOOD 2>/dev/null || "
                "sudo iptables -I INPUT -p tcp --syn -j SYN_FLOOD",
            ]
            return self._run_cmds(server_id, cmds, "SYN Flood koruması")

        if prot == 'http_flood':
            cmds = [
                "sudo iptables -N HTTP_FLOOD 2>/dev/null || true",
                "sudo iptables -F HTTP_FLOOD 2>/dev/null || true",
                "sudo iptables -A HTTP_FLOOD -p tcp --dport 80 -m hashlimit "
                "--hashlimit-above 50/sec --hashlimit-burst 100 "
                "--hashlimit-mode srcip --hashlimit-name http_flood "
                "-j DROP",
                "sudo iptables -A HTTP_FLOOD -p tcp --dport 443 -m hashlimit "
                "--hashlimit-above 50/sec --hashlimit-burst 100 "
                "--hashlimit-mode srcip --hashlimit-name https_flood "
                "-j DROP",
                "sudo iptables -A HTTP_FLOOD -j RETURN",
                "sudo iptables -C INPUT -p tcp -m multiport --dports 80,443 "
                "-j HTTP_FLOOD 2>/dev/null || "
                "sudo iptables -I INPUT -p tcp -m multiport --dports 80,443 "
                "-j HTTP_FLOOD",
            ]
            return self._run_cmds(server_id, cmds, "HTTP Flood koruması")

        if prot == 'slowloris':
            cmds = [
                "sudo sysctl -w net.ipv4.tcp_fin_timeout=10",
                "sudo sysctl -w net.ipv4.tcp_keepalive_time=300",
                "sudo sysctl -w net.ipv4.tcp_keepalive_probes=3",
                "sudo sysctl -w net.ipv4.tcp_keepalive_intvl=15",
                "sudo sysctl -w net.netfilter.nf_conntrack_tcp_timeout_established=600 "
                "2>/dev/null || true",
                # iptables: tek IP'den fazla bağlantı limitle
                "sudo iptables -C INPUT -p tcp --dport 80 -m connlimit "
                "--connlimit-above 50 -j DROP 2>/dev/null || "
                "sudo iptables -A INPUT -p tcp --dport 80 -m connlimit "
                "--connlimit-above 50 -j DROP",
                "sudo iptables -C INPUT -p tcp --dport 443 -m connlimit "
                "--connlimit-above 50 -j DROP 2>/dev/null || "
                "sudo iptables -A INPUT -p tcp --dport 443 -m connlimit "
                "--connlimit-above 50 -j DROP",
            ]
            return self._run_cmds(server_id, cmds, "Slowloris koruması")

        if prot == 'icmp_flood':
            cmds = [
                "sudo iptables -C INPUT -p icmp --icmp-type echo-request "
                "-m limit --limit 5/sec --limit-burst 10 -j ACCEPT 2>/dev/null || "
                "sudo iptables -A INPUT -p icmp --icmp-type echo-request "
                "-m limit --limit 5/sec --limit-burst 10 -j ACCEPT",
                "sudo iptables -C INPUT -p icmp --icmp-type echo-request "
                "-j DROP 2>/dev/null || "
                "sudo iptables -A INPUT -p icmp --icmp-type echo-request -j DROP",
            ]
            return self._run_cmds(server_id, cmds, "ICMP Flood koruması")

        if prot == 'port_scan':
            cmds = [
                "sudo iptables -N PORT_SCAN 2>/dev/null || true",
                "sudo iptables -F PORT_SCAN 2>/dev/null || true",
                "sudo iptables -A PORT_SCAN -p tcp --tcp-flags ALL NONE -j DROP",
                "sudo iptables -A PORT_SCAN -p tcp --tcp-flags ALL ALL -j DROP",
                "sudo iptables -A PORT_SCAN -p tcp --tcp-flags ALL FIN,URG,PSH -j DROP",
                "sudo iptables -A PORT_SCAN -p tcp --tcp-flags SYN,RST SYN,RST -j DROP",
                "sudo iptables -A PORT_SCAN -p tcp --tcp-flags SYN,FIN SYN,FIN -j DROP",
                "sudo iptables -A PORT_SCAN -j RETURN",
                "sudo iptables -C INPUT -j PORT_SCAN 2>/dev/null || "
                "sudo iptables -I INPUT -j PORT_SCAN",
            ]
            return self._run_cmds(server_id, cmds, "Port Scan koruması")

        if prot == 'bogus_tcp':
            cmds = [
                "sudo iptables -C INPUT -m conntrack --ctstate INVALID "
                "-j DROP 2>/dev/null || "
                "sudo iptables -I INPUT -m conntrack --ctstate INVALID -j DROP",
                "sudo iptables -C INPUT -p tcp ! --syn -m conntrack "
                "--ctstate NEW -j DROP 2>/dev/null || "
                "sudo iptables -I INPUT -p tcp ! --syn -m conntrack "
                "--ctstate NEW -j DROP",
            ]
            return self._run_cmds(server_id, cmds, "Bogus TCP koruması")

        if prot == 'connection_limit':
            cmds = [
                "sudo iptables -C INPUT -p tcp -m connlimit "
                "--connlimit-above 100 --connlimit-mask 32 "
                "-j REJECT 2>/dev/null || "
                "sudo iptables -A INPUT -p tcp -m connlimit "
                "--connlimit-above 100 --connlimit-mask 32 -j REJECT",
            ]
            return self._run_cmds(server_id, cmds, "Bağlantı limit koruması")

        if prot == 'kernel_hardening':
            cmds = [
                "sudo sysctl -w net.ipv4.tcp_syncookies=1",
                "sudo sysctl -w net.ipv4.conf.all.rp_filter=1",
                "sudo sysctl -w net.ipv4.conf.default.rp_filter=1",
                "sudo sysctl -w net.ipv4.icmp_echo_ignore_broadcasts=1",
                "sudo sysctl -w net.ipv4.conf.all.accept_redirects=0",
                "sudo sysctl -w net.ipv4.conf.default.accept_redirects=0",
                "sudo sysctl -w net.ipv4.conf.all.send_redirects=0",
                "sudo sysctl -w net.ipv4.conf.all.accept_source_route=0",
                "sudo sysctl -w net.ipv4.conf.all.log_martians=1",
                "sudo sysctl -w net.ipv4.tcp_max_syn_backlog=4096",
                "sudo sysctl -w net.ipv4.tcp_synack_retries=2",
            ]
            return self._run_cmds(server_id, cmds, "Kernel sertleştirme")

        # ── Nginx korumaları ──
        if prot == 'nginx_rate_limit':
            block = (
                "# Emare Security OS: Rate Limiting\n"
                "limit_req_zone $binary_remote_addr zone=general:10m rate=30r/s;\n"
                "limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;\n"
            )
            return self._nginx_add_snippet(server_id,
                'emare_security_ratelimit.conf', block,
                "Nginx rate limit koruması")

        if prot == 'nginx_bad_bots':
            block = (
                "# Emare Security OS: Bad Bot Blocker\n"
                "map $http_user_agent $bad_bot {\n"
                "    default 0;\n"
                "    ~*(?:bot|crawl|spider|scan|nikto|sqlmap|nmap|masscan|"
                "zgrab|nuclei|curl\\/|wget\\/|python-requests|go-http|"
                "libwww|httpclient|scrapy|phantomjs) 1;\n"
                "    '' 1;\n"
                "}\n"
            )
            return self._nginx_add_snippet(server_id,
                'emare_security_bad_bots.conf', block,
                "Nginx bot koruması")

        if prot == 'nginx_sql_injection':
            block = (
                "# Emare Security OS: SQL Injection Blocker\n"
                "set $block_sql_injections 0;\n"
                "if ($query_string ~ \"union.*select.*\\(\") { set $block_sql_injections 1; }\n"
                "if ($query_string ~ \"concat.*\\(\") { set $block_sql_injections 1; }\n"
                "if ($query_string ~ \"union.*all.*select\") { set $block_sql_injections 1; }\n"
                "if ($query_string ~* \"(['\\\";]|(--))\") { set $block_sql_injections 1; }\n"
                "if ($query_string ~* \"(;|<|>|'|\\\")\") { set $block_sql_injections 1; }\n"
                "if ($query_string ~* \"(\\b(select|union|insert|drop|update|"
                "delete|truncate|alter|create|exec|declare)\\b)\") "
                "{ set $block_sql_injections 1; }\n"
                "if ($block_sql_injections = 1) { return 403; }\n"
            )
            return self._nginx_add_snippet(server_id,
                'emare_security_sqli.conf', block,
                "Nginx SQL Injection koruması")

        if prot == 'nginx_xss':
            block = (
                "# Emare Security OS: XSS Blocker\n"
                "set $block_xss 0;\n"
                "if ($query_string ~* \"(<|%3C).*script.*(>|%3E)\") { set $block_xss 1; }\n"
                "if ($query_string ~* \"(javascript:)\") { set $block_xss 1; }\n"
                "if ($query_string ~* \"(onerror|onload|onclick|onmouseover)=\") "
                "{ set $block_xss 1; }\n"
                "if ($query_string ~* \"(document\\.(cookie|write|location))\") "
                "{ set $block_xss 1; }\n"
                "if ($query_string ~* \"(alert|confirm|prompt)\\s*\\(\") "
                "{ set $block_xss 1; }\n"
                "if ($block_xss = 1) { return 403; }\n"
            )
            return self._nginx_add_snippet(server_id,
                'emare_security_xss.conf', block,
                "Nginx XSS koruması")

        if prot == 'nginx_path_traversal':
            block = (
                "# Emare Security OS: Path Traversal Blocker\n"
                "if ($request_uri ~* \"(\\.\\.\\/|\\.\\.\\\\)\") { return 403; }\n"
                "if ($request_uri ~* \"(%2e%2e|\\.\\.\\.)\") { return 403; }\n"
                "if ($request_uri ~* \"(/etc/passwd|/etc/shadow|/proc/self)\") "
                "{ return 403; }\n"
                "if ($request_uri ~* \"(wp-admin|wp-login|phpmyadmin|"
                "shell\\.|eval\\(|base64)\") { return 403; }\n"
            )
            return self._nginx_add_snippet(server_id,
                'emare_security_traversal.conf', block,
                "Nginx path traversal koruması")

        if prot == 'nginx_method_filter':
            block = (
                "# Emare Security OS: HTTP Method Filter\n"
                "if ($request_method !~ ^(GET|POST|HEAD|PUT|PATCH|DELETE|OPTIONS)$) "
                "{ return 405; }\n"
            )
            return self._nginx_add_snippet(server_id,
                'emare_security_methods.conf', block,
                "Nginx HTTP metot filtresi")

        if prot == 'nginx_request_size':
            block = (
                "# Emare Security OS: Request Size Limiter\n"
                "client_max_body_size 10m;\n"
                "client_body_timeout 15s;\n"
                "client_header_timeout 15s;\n"
                "send_timeout 15s;\n"
                "large_client_header_buffers 4 8k;\n"
            )
            return self._nginx_add_snippet(server_id,
                'emare_security_reqsize.conf', block,
                "Nginx istek boyutu limiti")

        # ── L3 — Ağ Katmanı Korumaları ──

        if prot == 'l3_bogon_filter':
            cmds = [
                "sudo iptables -N BOGON_FILTER 2>/dev/null || true",
                "sudo iptables -F BOGON_FILTER 2>/dev/null || true",
                "sudo iptables -A BOGON_FILTER -s 0.0.0.0/8 -j DROP",
                "sudo iptables -A BOGON_FILTER -s 10.0.0.0/8 -j DROP",
                "sudo iptables -A BOGON_FILTER -s 100.64.0.0/10 -j DROP",
                "sudo iptables -A BOGON_FILTER -s 127.0.0.0/8 -j DROP",
                "sudo iptables -A BOGON_FILTER -s 169.254.0.0/16 -j DROP",
                "sudo iptables -A BOGON_FILTER -s 172.16.0.0/12 -j DROP",
                "sudo iptables -A BOGON_FILTER -s 192.0.0.0/24 -j DROP",
                "sudo iptables -A BOGON_FILTER -s 192.0.2.0/24 -j DROP",
                "sudo iptables -A BOGON_FILTER -s 192.168.0.0/16 -j DROP",
                "sudo iptables -A BOGON_FILTER -s 198.18.0.0/15 -j DROP",
                "sudo iptables -A BOGON_FILTER -s 198.51.100.0/24 -j DROP",
                "sudo iptables -A BOGON_FILTER -s 203.0.113.0/24 -j DROP",
                "sudo iptables -A BOGON_FILTER -s 224.0.0.0/4 -j DROP",
                "sudo iptables -A BOGON_FILTER -s 240.0.0.0/4 -j DROP",
                "sudo iptables -A BOGON_FILTER -j RETURN",
                "sudo iptables -C INPUT -j BOGON_FILTER 2>/dev/null || "
                "sudo iptables -I INPUT -j BOGON_FILTER",
            ]
            return self._run_cmds(server_id, cmds, "L3 Bogon filtresi")

        if prot == 'l3_fragment_protection':
            cmds = [
                "sudo iptables -C INPUT -f -j DROP 2>/dev/null || "
                "sudo iptables -A INPUT -f -j DROP",
            ]
            return self._run_cmds(server_id, cmds, "L3 Fragment koruması")

        if prot == 'l3_ip_options':
            cmds = [
                "sudo iptables -C INPUT -m ipv4options --ssrr -j DROP 2>/dev/null || "
                "sudo iptables -A INPUT -m ipv4options --ssrr -j DROP 2>/dev/null || true",
                "sudo iptables -C INPUT -m ipv4options --lsrr -j DROP 2>/dev/null || "
                "sudo iptables -A INPUT -m ipv4options --lsrr -j DROP 2>/dev/null || true",
                "sudo iptables -C INPUT -m ipv4options --rr -j DROP 2>/dev/null || "
                "sudo iptables -A INPUT -m ipv4options --rr -j DROP 2>/dev/null || true",
                "sudo iptables -C INPUT -m ipv4options --ts -j DROP 2>/dev/null || "
                "sudo iptables -A INPUT -m ipv4options --ts -j DROP 2>/dev/null || true",
            ]
            return self._run_cmds(server_id, cmds, "L3 IP Options filtresi")

        if prot == 'l3_spoof_protection':
            cmds = [
                "sudo sysctl -w net.ipv4.conf.all.rp_filter=1",
                "sudo sysctl -w net.ipv4.conf.default.rp_filter=1",
                "sudo sysctl -w net.ipv4.conf.all.log_martians=1",
                "sudo sysctl -w net.ipv4.conf.default.log_martians=1",
                "sudo sysctl -w net.ipv4.conf.all.accept_source_route=0",
                "sudo sysctl -w net.ipv4.conf.default.accept_source_route=0",
                "sudo sysctl -w net.ipv4.conf.all.accept_redirects=0",
                "sudo sysctl -w net.ipv4.conf.default.accept_redirects=0",
                "sudo sysctl -w net.ipv4.conf.all.send_redirects=0",
                "sudo sysctl -w net.ipv4.conf.default.send_redirects=0",
            ]
            return self._run_cmds(server_id, cmds, "L3 Spoof koruması")

        # ── L4 — Transport Katmanı Korumaları ──

        if prot == 'l4_udp_flood':
            cmds = [
                "sudo iptables -N UDP_FLOOD 2>/dev/null || true",
                "sudo iptables -F UDP_FLOOD 2>/dev/null || true",
                "sudo iptables -A UDP_FLOOD -p udp -m hashlimit "
                "--hashlimit-above 50/sec --hashlimit-burst 100 "
                "--hashlimit-mode srcip --hashlimit-name udp_flood "
                "-j DROP",
                "sudo iptables -A UDP_FLOOD -j RETURN",
                "sudo iptables -C INPUT -p udp -j UDP_FLOOD 2>/dev/null || "
                "sudo iptables -I INPUT -p udp -j UDP_FLOOD",
            ]
            return self._run_cmds(server_id, cmds, "L4 UDP Flood koruması")

        if prot == 'l4_protocol_filter':
            cmds = [
                "sudo iptables -C INPUT -p sctp -j DROP 2>/dev/null || "
                "sudo iptables -A INPUT -p sctp -j DROP",
                "sudo iptables -C INPUT -p dccp -j DROP 2>/dev/null || "
                "sudo iptables -A INPUT -p dccp -j DROP",
                "sudo iptables -C INPUT -p 47 -j DROP 2>/dev/null || "
                "sudo iptables -A INPUT -p 47 -j DROP",
            ]
            return self._run_cmds(server_id, cmds,
                "L4 Protokol filtresi (SCTP/DCCP/GRE)")

        if prot == 'l4_mss_clamp':
            cmds = [
                "sudo iptables -t mangle -C FORWARD -p tcp --tcp-flags SYN,RST SYN "
                "-j TCPMSS --clamp-mss-to-pmtu 2>/dev/null || "
                "sudo iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN "
                "-j TCPMSS --clamp-mss-to-pmtu",
            ]
            return self._run_cmds(server_id, cmds, "L4 TCP MSS clamping")

        if prot == 'l4_tcp_timestamps':
            cmds = [
                "sudo sysctl -w net.ipv4.tcp_timestamps=0",
            ]
            return self._run_cmds(server_id, cmds, "L4 TCP Timestamps devre dışı")

        # ── L7 — Ek Uygulama Katmanı Korumaları ──

        if prot == 'l7_dns_amplification':
            cmds = [
                "sudo iptables -C INPUT -p udp --dport 53 -m hashlimit "
                "--hashlimit-above 5/sec --hashlimit-burst 10 "
                "--hashlimit-mode srcip --hashlimit-name dns_amp "
                "-j DROP 2>/dev/null || "
                "sudo iptables -A INPUT -p udp --dport 53 -m hashlimit "
                "--hashlimit-above 5/sec --hashlimit-burst 10 "
                "--hashlimit-mode srcip --hashlimit-name dns_amp "
                "-j DROP",
                "sudo iptables -C INPUT -p tcp --dport 53 -m hashlimit "
                "--hashlimit-above 10/sec --hashlimit-burst 20 "
                "--hashlimit-mode srcip --hashlimit-name dns_amp_tcp "
                "-j DROP 2>/dev/null || "
                "sudo iptables -A INPUT -p tcp --dport 53 -m hashlimit "
                "--hashlimit-above 10/sec --hashlimit-burst 20 "
                "--hashlimit-mode srcip --hashlimit-name dns_amp_tcp "
                "-j DROP",
            ]
            return self._run_cmds(server_id, cmds, "L7 DNS Amplification koruması")

        if prot == 'l7_hsts':
            block = (
                "# Emare Security OS: HSTS & SSL/TLS Hardening\n"
                "add_header Strict-Transport-Security "
                "\"max-age=31536000; includeSubDomains; preload\" always;\n"
                "add_header X-Content-Type-Options \"nosniff\" always;\n"
                "add_header X-Frame-Options \"SAMEORIGIN\" always;\n"
                "add_header X-XSS-Protection \"1; mode=block\" always;\n"
                "add_header Referrer-Policy \"strict-origin-when-cross-origin\" always;\n"
                "ssl_protocols TLSv1.2 TLSv1.3;\n"
                "ssl_prefer_server_ciphers on;\n"
                "ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:"
                "ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';\n"
            )
            return self._nginx_add_snippet(server_id,
                'emare_security_hsts.conf', block,
                "L7 HSTS & SSL/TLS sertleştirme")

        if prot == 'l7_smuggling':
            block = (
                "# Emare Security OS: HTTP Smuggling Protection\n"
                "ignore_invalid_headers on;\n"
                "underscores_in_headers off;\n"
                "merge_slashes on;\n"
                "chunked_transfer_encoding on;\n"
            )
            return self._nginx_add_snippet(server_id,
                'emare_security_smuggling.conf', block,
                "L7 HTTP Smuggling koruması")

        if prot == 'l7_gzip_bomb':
            block = (
                "# Emare Security OS: Gzip/Compression Bomb Protection\n"
                "client_max_body_size 10m;\n"
                "client_body_buffer_size 16k;\n"
                "proxy_buffer_size 8k;\n"
                "proxy_buffers 8 8k;\n"
                "gzip_types text/plain text/css application/json "
                "application/javascript text/xml;\n"
                "gzip_vary on;\n"
                "gzip_comp_level 4;\n"
            )
            return self._nginx_add_snippet(server_id,
                'emare_security_gzip.conf', block,
                "L7 Gzip Bomb koruması")

        if prot == 'nginx_waf':
            # ModSecurity kurulumunu dene
            cmds = [
                "sudo apt-get install -y libmodsecurity3 "
                "libnginx-mod-security 2>/dev/null || "
                "sudo yum install -y mod_security 2>/dev/null || true",
            ]
            ok, _ = self._run_cmds(server_id, cmds, "Nginx WAF")
            if not ok:
                return False, "WAF kurulumu başarısız. Manuel kurulum gerekebilir."
            return True, "WAF (ModSecurity) kurulumu başlatıldı. Nginx restart gerekebilir."

        return False, f"Bilinmeyen koruma: {prot}"

    def _apply_l7_emareos(self, server_id: str, prot: str) -> tuple:
        """Emare OS L7 koruma kuralları."""

        if prot == 'syn_flood':
            cmds = [
                '/emare firewall rules add chain=input protocol=tcp '
                'tcp-flags=syn connection-state=new action=jump '
                'jump-target=SYN-Protect comment="emarefirewall: SYN flood protect"',
                '/emare firewall rules add chain=SYN-Protect protocol=tcp '
                'tcp-flags=syn limit=30,5:packet action=accept '
                'comment="emarefirewall: SYN rate accept"',
                '/emare firewall rules add chain=SYN-Protect protocol=tcp '
                'action=drop comment="emarefirewall: SYN flood drop"',
            ]
            return self._run_cmds(server_id, cmds, "Emare SYN Flood koruması")

        if prot == 'http_flood':
            cmds = [
                '/emare firewall rules add chain=input protocol=tcp dst-port=80,443 '
                'connection-state=new action=jump jump-target=HTTP-Protect '
                'comment="emarefirewall: HTTP flood protect"',
                '/emare firewall rules add chain=HTTP-Protect '
                'connection-limit=50,32 action=drop '
                'comment="emarefirewall: HTTP flood drop"',
                '/emare firewall rules add chain=HTTP-Protect action=accept '
                'comment="emarefirewall: HTTP accept"',
            ]
            return self._run_cmds(server_id, cmds, "Emare HTTP Flood koruması")

        if prot == 'icmp_flood':
            cmds = [
                '/emare firewall rules add chain=input protocol=icmp '
                'limit=5,10:packet action=accept '
                'comment="emarefirewall: ICMP rate limit"',
                '/emare firewall rules add chain=input protocol=icmp '
                'action=drop comment="emarefirewall: ICMP flood drop"',
            ]
            return self._run_cmds(server_id, cmds, "Emare ICMP Flood koruması")

        if prot == 'port_scan':
            cmds = [
                '/emare firewall rules add chain=input protocol=tcp '
                'tcp-flags=fin,syn,rst,psh,ack,urg action=drop '
                'comment="emarefirewall: port scan ALL flags"',
                '/emare firewall rules add chain=input protocol=tcp '
                'tcp-flags=!fin,!syn,!rst,!psh,!ack,!urg action=drop '
                'comment="emarefirewall: port scan NO flags"',
                '/emare firewall rules add chain=input protocol=tcp '
                'tcp-flags=syn,rst action=drop '
                'comment="emarefirewall: port scan SYN+RST"',
                '/emare firewall rules add chain=input protocol=tcp '
                'tcp-flags=syn,fin action=drop '
                'comment="emarefirewall: port scan SYN+FIN"',
            ]
            return self._run_cmds(server_id, cmds, "Emare Port Scan koruması")

        if prot == 'bogus_tcp':
            cmds = [
                '/emare firewall rules add chain=input connection-state=invalid '
                'action=drop comment="emarefirewall: invalid state drop"',
            ]
            return self._run_cmds(server_id, cmds, "Emare Bogus TCP koruması")

        if prot == 'connection_limit':
            cmds = [
                '/emare firewall rules add chain=input protocol=tcp '
                'connection-limit=100,32 action=drop '
                'comment="emarefirewall: connection limit"',
            ]
            return self._run_cmds(server_id, cmds, "Emare bağlantı limiti")

        if prot == 'slowloris':
            cmds = [
                '/emare firewall rules add chain=input protocol=tcp '
                'dst-port=80,443 connection-limit=50,32 action=drop '
                'comment="emarefirewall: slowloris protect"',
            ]
            return self._run_cmds(server_id, cmds, "Emare Slowloris koruması")

        if prot == 'kernel_hardening':
            cmds = [
                '/emare settings set tcp-syncookies=yes',
                '/emare settings set rp-filter=strict 2>/dev/null || true',
            ]
            return self._run_cmds(server_id, cmds, "Emare kernel sertleştirme")

        # ── L3 — Emare Ağ Katmanı ──

        if prot == 'l3_bogon_filter':
            cmds = [
                '/emare firewall blocklist add list=bogon address=0.0.0.0/8 '
                'comment="emarefirewall: bogon"',
                '/emare firewall blocklist add list=bogon address=10.0.0.0/8 '
                'comment="emarefirewall: bogon"',
                '/emare firewall blocklist add list=bogon address=100.64.0.0/10 '
                'comment="emarefirewall: bogon"',
                '/emare firewall blocklist add list=bogon address=127.0.0.0/8 '
                'comment="emarefirewall: bogon"',
                '/emare firewall blocklist add list=bogon address=169.254.0.0/16 '
                'comment="emarefirewall: bogon"',
                '/emare firewall blocklist add list=bogon address=172.16.0.0/12 '
                'comment="emarefirewall: bogon"',
                '/emare firewall blocklist add list=bogon address=192.0.0.0/24 '
                'comment="emarefirewall: bogon"',
                '/emare firewall blocklist add list=bogon address=192.0.2.0/24 '
                'comment="emarefirewall: bogon"',
                '/emare firewall blocklist add list=bogon address=192.168.0.0/16 '
                'comment="emarefirewall: bogon"',
                '/emare firewall blocklist add list=bogon address=198.18.0.0/15 '
                'comment="emarefirewall: bogon"',
                '/emare firewall blocklist add list=bogon address=224.0.0.0/4 '
                'comment="emarefirewall: bogon"',
                '/emare firewall blocklist add list=bogon address=240.0.0.0/4 '
                'comment="emarefirewall: bogon"',
                '/emare firewall rules add chain=input src-blocklist=bogon '
                'action=drop comment="emarefirewall: L3 bogon drop"',
            ]
            return self._run_cmds(server_id, cmds, "Emare L3 Bogon filtresi")

        if prot == 'l3_fragment_protection':
            cmds = [
                '/emare firewall rules add chain=input protocol=tcp fragment=yes '
                'action=drop comment="emarefirewall: L3 fragment drop"',
                '/emare firewall rules add chain=input protocol=udp fragment=yes '
                'action=drop comment="emarefirewall: L3 fragment drop"',
            ]
            return self._run_cmds(server_id, cmds, "Emare L3 Fragment koruması")

        if prot == 'l3_ip_options':
            cmds = [
                '/emare firewall rules add chain=input ip-options=any '
                'action=drop comment="emarefirewall: L3 IP options drop" '
                '2>/dev/null || true',
            ]
            return self._run_cmds(server_id, cmds, "Emare L3 IP Options filtresi")

        if prot == 'l3_spoof_protection':
            cmds = [
                '/emare settings set rp-filter=strict 2>/dev/null || true',
                '/emare firewall rules add chain=input src-address=0.0.0.0/8 '
                'action=drop comment="emarefirewall: L3 spoof 0.0.0.0/8"',
                '/emare firewall rules add chain=input src-address=127.0.0.0/8 '
                'action=drop in-interface-list=!loopback '
                'comment="emarefirewall: L3 spoof loopback" 2>/dev/null || true',
            ]
            return self._run_cmds(server_id, cmds, "Emare L3 Spoof koruması")

        # ── L4 — Emare Transport Katmanı ──

        if prot == 'l4_udp_flood':
            cmds = [
                '/emare firewall rules add chain=input protocol=udp '
                'action=jump jump-target=UDP-Protect '
                'comment="emarefirewall: L4 UDP flood protect"',
                '/emare firewall rules add chain=UDP-Protect protocol=udp '
                'limit=50,100:packet action=accept '
                'comment="emarefirewall: L4 UDP rate accept"',
                '/emare firewall rules add chain=UDP-Protect protocol=udp '
                'action=drop comment="emarefirewall: L4 UDP flood drop"',
            ]
            return self._run_cmds(server_id, cmds, "Emare L4 UDP Flood koruması")

        if prot == 'l4_protocol_filter':
            cmds = [
                '/emare firewall rules add chain=input protocol=sctp '
                'action=drop comment="emarefirewall: L4 SCTP drop"',
                '/emare firewall rules add chain=input protocol=dccp '
                'action=drop comment="emarefirewall: L4 DCCP drop"',
                '/emare firewall rules add chain=input protocol=gre '
                'action=drop comment="emarefirewall: L4 GRE drop"',
            ]
            return self._run_cmds(server_id, cmds,
                "Emare L4 Protokol filtresi (SCTP/DCCP/GRE)")

        if prot == 'l4_mss_clamp':
            cmds = [
                '/emare firewall mangle add chain=forward protocol=tcp '
                'tcp-flags=syn action=change-mss new-mss=clamp-to-pmtu '
                'comment="emarefirewall: L4 MSS clamp"',
            ]
            return self._run_cmds(server_id, cmds, "Emare L4 TCP MSS clamping")

        if prot == 'l4_tcp_timestamps':
            return True, "Emare TCP timestamps Emare OS tarafından yönetilir."

        # ── L7 Ek — Emare ──

        if prot == 'l7_dns_amplification':
            cmds = [
                '/emare dns config set allow-remote-requests=no',
                '/emare firewall rules add chain=input protocol=udp dst-port=53 '
                'limit=5,10:packet action=accept '
                'comment="emarefirewall: L7 DNS rate limit"',
                '/emare firewall rules add chain=input protocol=udp dst-port=53 '
                'action=drop comment="emarefirewall: L7 DNS amp drop"',
            ]
            return self._run_cmds(server_id, cmds,
                "Emare L7 DNS Amplification koruması")

        # Nginx korumaları Emare'e uygulanamaz
        if prot.startswith('nginx_') or prot in ('l7_hsts', 'l7_smuggling', 'l7_gzip_bomb'):
            return False, f"'{prot}' Emare routerlarda desteklenmiyor. Nginx gerektiren bir korumadır."

        return False, f"Emare: desteklenmeyen koruma: {prot}"

    def remove_l7_protection(self, server_id: str, prot: str) -> tuple:
        """Belirli bir koruma kuralını kaldırır (tüm katmanlar)."""
        if prot not in self._ALL_PROTECTIONS:
            return False, f"Bilinmeyen koruma: {prot}"

        fw = self._detect_type(server_id)

        if fw == 'emareos':
            return self._remove_l7_emareos(server_id, prot)

        # iptables chain bazlı kaldırma
        chain_map = {
            'syn_flood': 'SYN_FLOOD',
            'http_flood': 'HTTP_FLOOD',
            'port_scan': 'PORT_SCAN',
            'l3_bogon_filter': 'BOGON_FILTER',
            'l4_udp_flood': 'UDP_FLOOD',
        }
        if prot in chain_map:
            chain = chain_map[prot]
            cmds = [
                f"sudo iptables -D INPUT -j {chain} 2>/dev/null || true",
                f"sudo iptables -F {chain} 2>/dev/null || true",
                f"sudo iptables -X {chain} 2>/dev/null || true",
            ]
            return self._run_cmds(server_id, cmds, f"{prot} kaldırma")

        if prot == 'bogus_tcp':
            cmds = [
                "sudo iptables -D INPUT -m conntrack --ctstate INVALID "
                "-j DROP 2>/dev/null || true",
                "sudo iptables -D INPUT -p tcp ! --syn -m conntrack "
                "--ctstate NEW -j DROP 2>/dev/null || true",
            ]
            return self._run_cmds(server_id, cmds, "Bogus TCP kaldırma")

        if prot == 'connection_limit':
            cmds = [
                "sudo iptables -D INPUT -p tcp -m connlimit "
                "--connlimit-above 100 --connlimit-mask 32 "
                "-j REJECT 2>/dev/null || true",
            ]
            return self._run_cmds(server_id, cmds, "Bağlantı limit kaldırma")

        if prot == 'icmp_flood':
            cmds = [
                "sudo iptables -D INPUT -p icmp --icmp-type echo-request "
                "-m limit --limit 5/sec --limit-burst 10 -j ACCEPT 2>/dev/null || true",
                "sudo iptables -D INPUT -p icmp --icmp-type echo-request "
                "-j DROP 2>/dev/null || true",
            ]
            return self._run_cmds(server_id, cmds, "ICMP flood kaldırma")

        if prot == 'slowloris':
            cmds = [
                "sudo sysctl -w net.ipv4.tcp_fin_timeout=60",
                "sudo iptables -D INPUT -p tcp --dport 80 -m connlimit "
                "--connlimit-above 50 -j DROP 2>/dev/null || true",
                "sudo iptables -D INPUT -p tcp --dport 443 -m connlimit "
                "--connlimit-above 50 -j DROP 2>/dev/null || true",
            ]
            return self._run_cmds(server_id, cmds, "Slowloris kaldırma")

        if prot == 'kernel_hardening':
            return True, "Kernel ayarları sıfırlamak önerilmez. Reboot ile sıfırlanır."

        # Nginx snippet kaldırma
        nginx_file_map = {
            'nginx_rate_limit': 'emare_security_ratelimit.conf',
            'nginx_bad_bots': 'emare_security_bad_bots.conf',
            'nginx_sql_injection': 'emare_security_sqli.conf',
            'nginx_xss': 'emare_security_xss.conf',
            'nginx_path_traversal': 'emare_security_traversal.conf',
            'nginx_method_filter': 'emare_security_methods.conf',
            'nginx_request_size': 'emare_security_reqsize.conf',
            'l7_hsts': 'emare_security_hsts.conf',
            'l7_smuggling': 'emare_security_smuggling.conf',
            'l7_gzip_bomb': 'emare_security_gzip.conf',
        }
        if prot in nginx_file_map:
            fname = nginx_file_map[prot]
            cmds = [
                f"sudo rm -f /etc/nginx/conf.d/{fname}",
                "sudo nginx -t 2>&1 && sudo systemctl reload nginx 2>&1 || true",
            ]
            return self._run_cmds(server_id, cmds, f"Nginx {prot} kaldırma")

        if prot == 'nginx_waf':
            return False, "WAF kaldırma işlemi manuel yapılmalıdır."

        # L3 kaldırma
        if prot == 'l3_fragment_protection':
            cmds = [
                "sudo iptables -D INPUT -f -j DROP 2>/dev/null || true",
            ]
            return self._run_cmds(server_id, cmds, "L3 Fragment kaldırma")

        if prot in ('l3_ip_options',):
            cmds = [
                "sudo iptables -D INPUT -m ipv4options --ssrr -j DROP 2>/dev/null || true",
                "sudo iptables -D INPUT -m ipv4options --lsrr -j DROP 2>/dev/null || true",
                "sudo iptables -D INPUT -m ipv4options --rr -j DROP 2>/dev/null || true",
                "sudo iptables -D INPUT -m ipv4options --ts -j DROP 2>/dev/null || true",
            ]
            return self._run_cmds(server_id, cmds, "L3 IP Options kaldırma")

        if prot == 'l3_spoof_protection':
            return True, "Spoof koruması (sysctl) sıfırlamak önerilmez. Reboot ile sıfırlanır."

        # L4 kaldırma
        if prot == 'l4_protocol_filter':
            cmds = [
                "sudo iptables -D INPUT -p sctp -j DROP 2>/dev/null || true",
                "sudo iptables -D INPUT -p dccp -j DROP 2>/dev/null || true",
                "sudo iptables -D INPUT -p 47 -j DROP 2>/dev/null || true",
            ]
            return self._run_cmds(server_id, cmds, "L4 Protokol filtresi kaldırma")

        if prot == 'l4_mss_clamp':
            cmds = [
                "sudo iptables -t mangle -D FORWARD -p tcp --tcp-flags SYN,RST SYN "
                "-j TCPMSS --clamp-mss-to-pmtu 2>/dev/null || true",
            ]
            return self._run_cmds(server_id, cmds, "L4 MSS clamp kaldırma")

        if prot == 'l4_tcp_timestamps':
            cmds = [
                "sudo sysctl -w net.ipv4.tcp_timestamps=1",
            ]
            return self._run_cmds(server_id, cmds, "L4 TCP Timestamps etkinleştirildi")

        # L7 ek kaldırma
        if prot == 'l7_dns_amplification':
            cmds = [
                "sudo iptables -D INPUT -p udp --dport 53 -m hashlimit "
                "--hashlimit-above 5/sec --hashlimit-burst 10 "
                "--hashlimit-mode srcip --hashlimit-name dns_amp "
                "-j DROP 2>/dev/null || true",
                "sudo iptables -D INPUT -p tcp --dport 53 -m hashlimit "
                "--hashlimit-above 10/sec --hashlimit-burst 20 "
                "--hashlimit-mode srcip --hashlimit-name dns_amp_tcp "
                "-j DROP 2>/dev/null || true",
            ]
            return self._run_cmds(server_id, cmds, "L7 DNS Amplification kaldırma")

        return False, f"Kaldırma desteklenmiyor: {prot}"

    def _remove_l7_emareos(self, server_id: str, prot: str) -> tuple:
        """Emare'ten emarefirewall kurallarını kaldır (tüm katmanlar)."""
        # comment'e göre sil
        comment_map = {
            'syn_flood': 'SYN',
            'http_flood': 'HTTP',
            'icmp_flood': 'ICMP',
            'port_scan': 'port scan',
            'bogus_tcp': 'invalid state',
            'connection_limit': 'connection limit',
            'slowloris': 'slowloris',
            'l3_bogon_filter': 'bogon',
            'l3_fragment_protection': 'fragment',
            'l3_ip_options': 'IP options',
            'l3_spoof_protection': 'spoof',
            'l4_udp_flood': 'UDP',
            'l4_protocol_filter': 'SCTP\\|DCCP\\|GRE',
            'l7_dns_amplification': 'DNS',
        }
        keyword = comment_map.get(prot, '')
        if keyword:
            # Filter kurallarını kaldır
            self._exec(server_id,
                '/emare firewall rules remove [find where comment~"emarefirewall" '
                f'comment~"{keyword}"]')
            # L3 bogon: engel listesi'i de temizle
            if prot == 'l3_bogon_filter':
                self._exec(server_id,
                    '/emare firewall blocklist remove '
                    '[find where list=bogon comment~"emarefirewall"]')
            return True, f"Emare {prot} kuralları kaldırıldı."
        if prot == 'l4_mss_clamp':
            self._exec(server_id,
                '/emare firewall mangle remove [find where comment~"emarefirewall" '
                'comment~"MSS"]')
            return True, "Emare L4 MSS clamp kaldırıldı."
        if prot == 'kernel_hardening':
            return True, "Emare kernel ayarları sıfırlamak önerilmez."
        if prot == 'l4_tcp_timestamps':
            return True, "Emare TCP timestamps Emare OS tarafından yönetilir."
        if prot.startswith('nginx_') or prot in ('l7_hsts', 'l7_smuggling', 'l7_gzip_bomb'):
            return False, "Nginx korumaları Emare'te bulunmaz."
        return False, f"Kaldırma desteklenmiyor: {prot}"

    def l7_security_scan(self, server_id: str) -> dict:
        """Çok katmanlı koruma skoru hesaplar ve öneriler sunar."""
        status = self.get_l7_status(server_id)
        score = 100
        findings = []
        recommendations = []

        # ── L3 Ağ Katmanı kontrolleri ──
        l3_checks = [
            ('l3_bogon_filter', 8, 'yüksek', 'L3: Bogon filtresi yok',
             'Sahte/reserved IP blokları filtrelenmiyor. Spoof saldırılarına açık.'),
            ('l3_fragment_protection', 5, 'orta', 'L3: Fragment koruması yok',
             'IP fragment saldırılarına açık.'),
            ('l3_ip_options', 3, 'orta', 'L3: IP Options filtresi yok',
             'IP options ile gizli kanal / DoS saldırıları mümkün.'),
            ('l3_spoof_protection', 8, 'yüksek', 'L3: Spoof koruması yok',
             'RPF ve martian log kapalı. Kaynak IP sahteciliğine açık.'),
        ]

        # ── L4 Transport Katmanı kontrolleri ──
        l4_checks = [
            ('l4_udp_flood', 8, 'yüksek', 'L4: UDP Flood koruması yok',
             'UDP taşkın saldırılarına açık. Bant genişliği tükenebilir.'),
            ('l4_protocol_filter', 5, 'orta', 'L4: Protokol filtresi yok',
             'SCTP/DCCP/GRE gibi nadir protokoller filtrelenmiyor.'),
            ('l4_mss_clamp', 3, 'orta', 'L4: TCP MSS clamping yok',
             'PMTU sorunları ve SYN flood amplification riski.'),
            ('l4_tcp_timestamps', 3, 'orta', 'L4: TCP Timestamps devre dışı değil',
             'Timing side-channel saldırılarına açık.'),
        ]

        # ── Mevcut L7 Ağ seviyesi kontrolleri ──
        checks = [
            ('syn_flood', 10, 'kritik', 'SYN Flood koruması yok',
             'SYN flood saldırılarına açık. Hemen etkinleştirin.'),
            ('http_flood', 10, 'kritik', 'HTTP Flood koruması yok',
             'HTTP DDoS saldırılarına açık. Hemen etkinleştirin.'),
            ('bogus_tcp', 8, 'yüksek', 'Geçersiz TCP paket koruması yok',
             'Bogus TCP paketleri filtrelenmiyor.'),
            ('port_scan', 8, 'yüksek', 'Port Scan koruması yok',
             'Port tarama saldırıları tespit edilemiyor.'),
            ('slowloris', 8, 'yüksek', 'Slowloris koruması yok',
             'Slowloris saldırılarına açık. Timeout değerlerini düşürün.'),
            ('icmp_flood', 4, 'orta', 'ICMP Flood koruması yok',
             'Ping flood saldırılarına açık.'),
            ('connection_limit', 4, 'orta', 'Bağlantı limiti yok',
             'IP başına bağlantı sınırı tanımlı değil.'),
            ('kernel_hardening', 8, 'yüksek', 'Kernel sertleştirme yapılmamış',
             'SYN cookies, RP filter, ICMP redirect korumaları kapalı.'),
        ]

        # L3 + L4 + L7 ağ kontrolleri birleştir
        checks = l3_checks + l4_checks + checks

        is_nginx = status.get('details', {}).get('has_nginx', False)
        if is_nginx:
            checks.extend([
                ('nginx_rate_limit', 4, 'yüksek', 'Nginx rate limit yok',
                 'Web sunucusu seviyesinde istek limiti yok.'),
                ('nginx_bad_bots', 3, 'orta', 'Bot koruması yok',
                 'Kötü amaçlı botlar engellenmiyor.'),
                ('nginx_sql_injection', 4, 'kritik', 'SQL Injection koruması yok',
                 'SQL injection saldırılarına açık.'),
                ('nginx_xss', 4, 'kritik', 'XSS koruması yok',
                 'Cross-site scripting saldırılarına açık.'),
                ('nginx_path_traversal', 3, 'yüksek', 'Path traversal koruması yok',
                 'Dizin gezinme saldırılarına açık.'),
                ('nginx_method_filter', 2, 'orta', 'HTTP metot filtresi yok',
                 'Tehlikeli HTTP metotları (TRACE vb.) açık.'),
                ('nginx_request_size', 2, 'orta', 'İstek boyutu limiti yok',
                 'Büyük boyutlu isteklerle sunucu yorulabilir.'),
                # L7 Ek Nginx korumaları
                ('l7_hsts', 5, 'kritik', 'L7: HSTS/SSL sertleştirme yok',
                 'HSTS header eksik. SSL downgrade ve MitM saldırılarına açık.'),
                ('l7_smuggling', 4, 'yüksek', 'L7: HTTP Smuggling koruması yok',
                 'CL.TE request smuggling saldırılarına açık.'),
                ('l7_gzip_bomb', 3, 'orta', 'L7: Gzip Bomb koruması yok',
                 'Compression bomb saldırılarına açık.'),
            ])

        # L7 Ek ağ seviyesi kontrolleri (Nginx olmadan da çalışır)
        checks.append(('l7_dns_amplification', 5, 'yüksek',
            'L7: DNS Amplification koruması yok',
            'DNS amplification saldırılarına açık. 100x bant genişliği amplifikasyonu riski.'))

        for key, penalty, severity, title, desc in checks:
            if not status.get(key, False):
                score -= penalty
                findings.append({
                    'severity': severity,
                    'title': title,
                    'detail': desc,
                    'protection': key,
                })
                recommendations.append(f"{title} — korumayı etkinleştirin.")

        score = max(0, score)
        grade = ('A+' if score >= 95 else 'A' if score >= 85 else
                 'B' if score >= 70 else 'C' if score >= 50 else
                 'D' if score >= 30 else 'F')

        return {
            'score': score,
            'grade': grade,
            'status': status,
            'findings': findings,
            'recommendations': recommendations,
            'has_nginx': is_nginx,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

    def _run_cmds(self, server_id: str, cmds: list, label: str) -> tuple:
        """Komut listesini sırayla çalıştırır."""
        last_err = ''
        for cmd in cmds:
            ok, out, err = self._exec(server_id, cmd)
            if not ok and err:
                last_err = (err or '').strip()
        if last_err:
            return False, f"{label} başarısız: {last_err}"
        return True, f"{label} etkinleştirildi."

    def _nginx_add_snippet(self, server_id: str, filename: str,
                           content: str, label: str) -> tuple:
        """Nginx conf.d dizinine snippet ekler ve reload eder."""
        # Mevcut dosyayı kontrol et
        ok, out, _ = self._exec(server_id,
            f"cat /etc/nginx/conf.d/{filename} 2>/dev/null")
        if ok and out and out.strip():
            return True, f"{label} zaten etkin."

        # Dosya oluştur (heredoc ile — $ expansion önlenir)
        ok, out, err = self._exec(server_id,
            f"sudo tee /etc/nginx/conf.d/{filename} > /dev/null << 'EOFNGINX'\n{content}\nEOFNGINX")
        if not ok:
            return False, f"Snippet oluşturulamadı: {(err or '').strip()}"

        # Nginx test & reload
        ok, out, err = self._exec(server_id,
            "sudo nginx -t 2>&1")
        if ok and 'successful' in (out or '').lower():
            self._exec(server_id, "sudo systemctl reload nginx 2>&1")
            return True, f"{label} etkinleştirildi ve nginx yeniden yüklendi."
        else:
            # Hatalı config → geri al
            self._exec(server_id, f"sudo rm -f /etc/nginx/conf.d/{filename}")
            return False, f"Nginx config hatası: {(out + ' ' + err).strip()}"

    # ═══════════════════ L7 SALDIRI OLAY TOPLAMA ═══════════════════

    def collect_l7_events(self, server_id: str) -> list:
        """Sunucudan L7 saldırı olaylarını toplar.

        iptables counter'ları, drop logları ve nginx error loglarını okuyarak
        engellenen saldırı bilgilerini döndürür.

        Returns:
            list[dict]: Her olay şu alanları içerir:
                category, severity, title, detail, count, protection, ts
        """
        events = []
        fw = self._detect_type(server_id)
        ts = datetime.now(timezone.utc).isoformat()

        if fw == 'emareos':
            events.extend(self._collect_l7_events_emareos(server_id, ts))
        else:
            events.extend(self._collect_l7_events_linux(server_id, ts))

        return events

    def _collect_l7_events_linux(self, server_id: str, ts: str) -> list:
        """Linux: iptables verbose counter + kernel log + nginx log."""
        events = []

        # ── 1) iptables chain counter'ları ──
        chain_map = {
            'SYN_FLOOD': ('L7_SYN_FLOOD', 'SYN Flood engelleme'),
            'HTTP_FLOOD': ('L7_HTTP_FLOOD', 'HTTP Flood engelleme'),
            'PORT_SCAN': ('L7_PORTSCAN', 'Port Scan engelleme'),
        }
        ok, out, _ = self._exec(server_id,
            "sudo iptables -L -v -n 2>/dev/null")
        if ok and out:
            current_chain = ''
            for line in out.splitlines():
                stripped = line.strip()
                if stripped.startswith('Chain '):
                    current_chain = stripped.split()[1]
                elif current_chain in chain_map and 'DROP' in stripped.upper():
                    parts = stripped.split()
                    if len(parts) >= 2:
                        try:
                            pkts = self._parse_iptables_count(parts[0])
                            if pkts > 0:
                                cat, title = chain_map[current_chain]
                                events.append({
                                    'category': cat,
                                    'severity': 'WARNING',
                                    'title': title,
                                    'detail': f'{pkts} paket engellendi',
                                    'count': pkts,
                                    'protection': current_chain.lower(),
                                    'ts': ts,
                                })
                        except (ValueError, IndexError):
                            pass

        # ── 2) connlimit (slowloris / connection limit) DROP'ları ──
        ok, out, _ = self._exec(server_id,
            "sudo iptables -L INPUT -v -n 2>/dev/null | grep -i connlimit")
        if ok and out:
            total_drops = 0
            for line in out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and ('DROP' in line.upper() or 'REJECT' in line.upper()):
                    try:
                        total_drops += self._parse_iptables_count(parts[0])
                    except (ValueError, IndexError):
                        pass
            if total_drops > 0:
                events.append({
                    'category': 'L7_CONNLIMIT',
                    'severity': 'WARNING',
                    'title': 'Bağlantı limiti engelleme',
                    'detail': f'{total_drops} bağlantı reddedildi',
                    'count': total_drops,
                    'protection': 'connection_limit',
                    'ts': ts,
                })

        # ── 3) ICMP flood DROP counter ──
        ok, out, _ = self._exec(server_id,
            "sudo iptables -L INPUT -v -n 2>/dev/null | grep -i 'icmp.*drop'")
        if ok and out:
            for line in out.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        pkts = self._parse_iptables_count(parts[0])
                        if pkts > 0:
                            events.append({
                                'category': 'L7_ICMP_FLOOD',
                                'severity': 'INFO',
                                'title': 'ICMP Flood engelleme',
                                'detail': f'{pkts} ping paketi engellendi',
                                'count': pkts,
                                'protection': 'icmp_flood',
                                'ts': ts,
                            })
                    except (ValueError, IndexError):
                        pass
                    break  # İlk eşleşme yeterli

        # ── 4) Bogus TCP (INVALID state) DROP'ları ──
        ok, out, _ = self._exec(server_id,
            "sudo iptables -L INPUT -v -n 2>/dev/null | grep -i 'INVALID.*DROP'")
        if ok and out:
            parts = out.strip().split()
            if len(parts) >= 2:
                try:
                    pkts = self._parse_iptables_count(parts[0])
                    if pkts > 0:
                        events.append({
                            'category': 'L7_BOGUS_TCP',
                            'severity': 'WARNING',
                            'title': 'Geçersiz TCP paketi engelleme',
                            'detail': f'{pkts} geçersiz paket engellendi',
                            'count': pkts,
                            'protection': 'bogus_tcp',
                            'ts': ts,
                        })
                except (ValueError, IndexError):
                    pass

        # ── 5) Nginx erişim reddleri (403/444 Son 5dk) ──
        ok, out, _ = self._exec(server_id,
            "sudo awk -v d=\"$(date -d '5 min ago' '+%d/%b/%Y:%H:%M' "
            "2>/dev/null || date -v-5M '+%d/%b/%Y:%H:%M')\" "
            "'$0 >= d && ($9 == 403 || $9 == 444)' "
            "/var/log/nginx/access.log 2>/dev/null | wc -l")
        if ok and out:
            try:
                count = int(out.strip())
                if count > 0:
                    events.append({
                        'category': 'L7_NGINX_BLOCK',
                        'severity': 'WARNING' if count > 10 else 'INFO',
                        'title': 'Nginx tarafından engellenen istekler',
                        'detail': f'Son 5 dakikada {count} istek 403/444 ile reddedildi',
                        'count': count,
                        'protection': 'nginx_waf',
                        'ts': ts,
                    })
            except (ValueError, IndexError):
                pass

        # ── 6) Nginx error log → SQL/XSS desenleri ──
        ok, out, _ = self._exec(server_id,
            "sudo tail -200 /var/log/nginx/error.log 2>/dev/null "
            "| grep -ciE 'client denied|forbidden|limiting' 2>/dev/null")
        if ok and out:
            try:
                count = int(out.strip())
                if count > 0:
                    events.append({
                        'category': 'L7_NGINX_ERROR',
                        'severity': 'WARNING',
                        'title': 'Nginx hata logları',
                        'detail': f'Son logda {count} engelleme/hata kaydı',
                        'count': count,
                        'protection': 'nginx_waf',
                        'ts': ts,
                    })
            except (ValueError, IndexError):
                pass

        return events

    def _collect_l7_events_emareos(self, server_id: str, ts: str) -> list:
        """Emare: firewall counter'ları."""
        events = []
        ok, out, _ = self._exec(server_id,
            '/emare firewall rules print stats terse without-paging '
            'where comment~"emarefirewall"')
        if not ok or not out:
            return events

        for line in out.splitlines():
            line_lower = line.lower()
            if 'bytes=0' in line_lower and 'packets=0' in line_lower:
                continue  # Hiç eşleşme olmamış

            # packets= değerini bul
            pkts = 0
            for part in line.split():
                if part.startswith('packets='):
                    try:
                        pkts = int(part.split('=')[1])
                    except (ValueError, IndexError):
                        pass

            if pkts == 0:
                continue

            cat = 'L7_EMAREOS'
            title = 'Emare kural eşleşmesi'
            if 'syn' in line_lower:
                cat = 'L7_SYN_FLOOD'
                title = 'SYN Flood engelleme'
            elif 'http' in line_lower:
                cat = 'L7_HTTP_FLOOD'
                title = 'HTTP Flood engelleme'
            elif 'icmp' in line_lower:
                cat = 'L7_ICMP_FLOOD'
                title = 'ICMP Flood engelleme'
            elif 'port scan' in line_lower or 'port-scan' in line_lower:
                cat = 'L7_PORTSCAN'
                title = 'Port Scan engelleme'
            elif 'invalid' in line_lower:
                cat = 'L7_BOGUS_TCP'
                title = 'Geçersiz paket engelleme'
            elif 'connection' in line_lower:
                cat = 'L7_CONNLIMIT'
                title = 'Bağlantı limiti'
            elif 'slowloris' in line_lower:
                cat = 'L7_SLOWLORIS'
                title = 'Slowloris engelleme'

            events.append({
                'category': cat,
                'severity': 'WARNING' if pkts > 100 else 'INFO',
                'title': title,
                'detail': f'{pkts} paket eşleşti',
                'count': pkts,
                'protection': cat.replace('L7_', '').lower(),
                'ts': ts,
            })

        return events

    @staticmethod
    def _parse_iptables_count(val: str) -> int:
        """iptables kısaltmalarını parse eder: 1234, 5K, 2M, 1G."""
        val = val.strip().upper()
        if val.endswith('K'):
            return int(float(val[:-1]) * 1000)
        if val.endswith('M'):
            return int(float(val[:-1]) * 1_000_000)
        if val.endswith('G'):
            return int(float(val[:-1]) * 1_000_000_000)
        return int(val)

    # ═══════════════════ YEDEKLEME / GERİ YÜKLEME ═══════════════════

    _BACKUP_DIR = '/var/lib/emarefirewall/backups'

    def _ensure_backup_dir(self, server_id: str):
        """Yedekleme dizinini oluştur."""
        self._exec(server_id, f"sudo mkdir -p {self._BACKUP_DIR}")

    def backup_firewall(self, server_id: str, name: str = '') -> tuple:
        """Mevcut firewall yapılandırmasını yedekler. -> (ok, backup_info)"""
        fw = self._detect_type(server_id)
        if not fw:
            return False, "Firewall tespit edilemedi."
        self._ensure_backup_dir(server_id)
        ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '', name)[:64] if name else 'auto'
        backup_id = f"{fw}_{safe_name}_{ts}"
        backup_path = f"{self._BACKUP_DIR}/{backup_id}.json"

        data = {
            'id': backup_id,
            'type': fw,
            'name': safe_name,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'server_id': server_id,
        }

        if fw == 'ufw':
            ok, rules_out, _ = self._exec(server_id,
                "ufw status numbered 2>/dev/null")
            ok2, user_rules, _ = self._exec(server_id,
                "cat /etc/ufw/user.rules 2>/dev/null")
            ok3, user6_rules, _ = self._exec(server_id,
                "cat /etc/ufw/user6.rules 2>/dev/null")
            ok4, before_rules, _ = self._exec(server_id,
                "cat /etc/ufw/before.rules 2>/dev/null")
            ok5, defaults, _ = self._exec(server_id,
                "grep -E '^(DEFAULT_|IPV6=)' /etc/default/ufw 2>/dev/null")
            data['config'] = {
                'status_output': rules_out or '',
                'user_rules': user_rules or '',
                'user6_rules': user6_rules or '',
                'before_rules': before_rules or '',
                'defaults': defaults or '',
            }

        elif fw == 'firewalld':
            ok, zone_list, _ = self._exec(server_id,
                "firewall-cmd --get-zones 2>/dev/null")
            ok2, default_zone, _ = self._exec(server_id,
                "firewall-cmd --get-default-zone 2>/dev/null")
            zones_data = {}
            for z in (zone_list or '').split():
                z = z.strip()
                if not z:
                    continue
                _, xml, _ = self._exec(server_id,
                    f"cat /etc/firewalld/zones/{_sq(z)}.xml 2>/dev/null")
                if xml:
                    zones_data[z] = xml
            ok3, direct, _ = self._exec(server_id,
                "cat /etc/firewalld/direct.xml 2>/dev/null")
            data['config'] = {
                'default_zone': (default_zone or '').strip(),
                'zones': zones_data,
                'direct_rules': direct or '',
            }

        elif fw == 'emareos':
            ok, filter_rules, _ = self._exec(server_id,
                '/emare firewall rules export')
            ok2, nat_rules, _ = self._exec(server_id,
                '/emare firewall nat export')
            ok3, mangle_rules, _ = self._exec(server_id,
                '/emare firewall mangle export')
            ok4, addr_lists, _ = self._exec(server_id,
                '/emare firewall blocklist export')
            ok5, services, _ = self._exec(server_id,
                '/emare services export')
            data['config'] = {
                'filter_rules': filter_rules or '',
                'nat_rules': nat_rules or '',
                'mangle_rules': mangle_rules or '',
                'address_lists': addr_lists or '',
                'services': services or '',
            }

        # JSON olarak kaydet
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        # Güvenli yazma: heredoc ile (randomized EOF to prevent injection)
        eof_marker = f'EMAREFW_EOF_{secrets.token_hex(16)}'
        json_str = json_str.replace(eof_marker, '')  # sanitize content
        cmd = f"sudo tee {_sq(backup_path)} > /dev/null << '{eof_marker}'\n{json_str}\n{eof_marker}"
        ok, _, err = self._exec(server_id, cmd)
        if not ok:
            return False, f"Yedek dosyası yazılamadı: {err}"

        return True, {
            'id': backup_id,
            'type': fw,
            'name': safe_name,
            'created_at': data['created_at'],
            'path': backup_path,
        }

    def list_backups(self, server_id: str) -> list:
        """Sunucudaki yedekleri listeler."""
        self._ensure_backup_dir(server_id)
        ok, out, _ = self._exec(server_id,
            f"ls -1t {self._BACKUP_DIR}/*.json 2>/dev/null")
        if not ok or not out or 'No such file' in out:
            return []
        backups = []
        for fpath in out.strip().split('\n'):
            fpath = fpath.strip()
            if not fpath.endswith('.json'):
                continue
            ok2, content, _ = self._exec(server_id, f"cat {_sq(fpath)} 2>/dev/null")
            if ok2 and content:
                try:
                    info = json.loads(content)
                    backups.append({
                        'id': info.get('id', ''),
                        'type': info.get('type', ''),
                        'name': info.get('name', ''),
                        'created_at': info.get('created_at', ''),
                        'path': fpath,
                    })
                except (json.JSONDecodeError, KeyError):
                    continue
        return backups

    def restore_firewall(self, server_id: str, backup_id: str) -> tuple:
        """Yedeği geri yükler. -> (ok, msg)"""
        if not backup_id or not re.match(r'^[a-zA-Z0-9_-]+$', backup_id):
            return False, "Geçersiz yedek ID."
        backup_path = f"{self._BACKUP_DIR}/{backup_id}.json"
        ok, content, _ = self._exec(server_id, f"cat {_sq(backup_path)} 2>/dev/null")
        if not ok or not content:
            return False, "Yedek bulunamadı."
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return False, "Yedek dosyası bozuk."

        fw = data.get('type')
        cfg = data.get('config', {})
        if not fw or not cfg:
            return False, "Yedek verisi eksik."

        # Önce mevcut config'i otomatik yedekle
        self.backup_firewall(server_id, name='pre_restore')

        if fw == 'ufw':
            # user.rules ve user6.rules dosyalarını geri yaz
            if cfg.get('user_rules'):
                eof = f'EMAREFW_EOF_{secrets.token_hex(16)}'
                content = cfg['user_rules'].replace(eof, '')
                self._exec(server_id,
                    f"sudo tee /etc/ufw/user.rules > /dev/null << '{eof}'\n{content}\n{eof}")
            if cfg.get('user6_rules'):
                eof = f'EMAREFW_EOF_{secrets.token_hex(16)}'
                content = cfg['user6_rules'].replace(eof, '')
                self._exec(server_id,
                    f"sudo tee /etc/ufw/user6.rules > /dev/null << '{eof}'\n{content}\n{eof}")
            self._exec(server_id, "sudo ufw reload 2>&1")
            return True, "UFW yapılandırması geri yüklendi ve reload edildi."

        if fw == 'firewalld':
            # Zone XML dosyalarını geri yaz
            for zone_name, xml_content in cfg.get('zones', {}).items():
                safe_zone = re.sub(r'[^a-zA-Z0-9_-]', '', zone_name)
                eof = f'EMAREFW_EOF_{secrets.token_hex(16)}'
                content = xml_content.replace(eof, '')
                self._exec(server_id,
                    f"sudo tee /etc/firewalld/zones/{safe_zone}.xml > /dev/null << '{eof}'\n{content}\n{eof}")
            if cfg.get('direct_rules'):
                eof = f'EMAREFW_EOF_{secrets.token_hex(16)}'
                content = cfg['direct_rules'].replace(eof, '')
                self._exec(server_id,
                    f"sudo tee /etc/firewalld/direct.xml > /dev/null << '{eof}'\n{content}\n{eof}")
            if cfg.get('default_zone'):
                safe_z = re.sub(r'[^a-zA-Z0-9_-]', '', cfg['default_zone'])
                self._exec(server_id,
                    f"sudo firewall-cmd --set-default-zone={safe_z} 2>&1")
            self._exec(server_id, "sudo firewall-cmd --reload 2>&1")
            return True, "Firewalld yapılandırması geri yüklendi ve reload edildi."

        if fw == 'emareos':
            # Emare: filter kurallarını temizle ve import et
            warnings = []
            for section, export_key in [
                ('filter', 'filter_rules'),
                ('nat', 'nat_rules'),
                ('mangle', 'mangle_rules'),
            ]:
                export_data = cfg.get(export_key, '')
                if not export_data:
                    continue
                # Mevcut kuralları temizle
                self._exec(server_id,
                    f'/emare firewall {section} remove [find]')
                # Export satırlarını komut olarak çalıştır
                for line in export_data.strip().split('\n'):
                    line = line.strip()
                    if line.startswith('#') or not line:
                        continue
                    if line.startswith('/'):
                        continue  # section header
                    if line.startswith('add '):
                        cmd = f'/emare firewall {section} {line}'
                        ok2, _, err2 = self._exec(server_id, cmd)
                        if not ok2:
                            warnings.append(f'{section}: {err2}')
            # Address list
            if cfg.get('address_lists'):
                self._exec(server_id,
                    '/emare firewall blocklist remove [find where list=blocked]')
                for line in cfg['address_lists'].strip().split('\n'):
                    line = line.strip()
                    if line.startswith('add '):
                        cmd = f'/emare firewall blocklist {line}'
                        self._exec(server_id, cmd)
            msg = "Emare yapılandırması geri yüklendi."
            if warnings:
                msg += f" ({len(warnings)} uyarı)"
            return True, msg

        return False, f"Bilinmeyen firewall tipi: {fw}"

    def delete_backup(self, server_id: str, backup_id: str) -> tuple:
        """Yedeği siler. -> (ok, msg)"""
        if not backup_id or not re.match(r'^[a-zA-Z0-9_-]+$', backup_id):
            return False, "Geçersiz yedek ID."
        backup_path = f"{self._BACKUP_DIR}/{backup_id}.json"
        ok, _, err = self._exec(server_id, f"sudo rm -f {_sq(backup_path)} 2>&1")
        if ok:
            return True, "Yedek silindi."
        return False, f"Silinemedi: {err}"

    # ═══════════════════ NETWORK ANALYSER ═══════════════════

    def net_bandwidth(self, server_id: str) -> dict:
        """Tüm interface'lerin bant genişliği/trafik istatistiklerini döndürür."""
        fw = self._detect_type(server_id)
        interfaces = []

        if fw == 'emareos':
            # Emare OS: interface istatistikleri
            results = self._exec_multi(server_id, [
                '/emare network interfaces print terse without-paging',
                '/emare network interfaces print stats without-paging',
            ])
            ok1, out1, _ = results[0]
            ok2, out2, _ = results[1]
            iface_map = {}
            if ok1 and out1:
                for entry in _parse_emareos_terse(out1):
                    name = entry.get('name', '')
                    if name:
                        iface_map[name] = {
                            'name': name,
                            'type': entry.get('type', ''),
                            'running': entry.get('running', '') == 'yes',
                            'disabled': entry.get('disabled', '') == 'yes',
                            'rx_bytes': 0, 'tx_bytes': 0,
                            'rx_packets': 0, 'tx_packets': 0,
                            'rx_errors': 0, 'tx_errors': 0,
                            'rx_drops': 0, 'tx_drops': 0,
                        }
            if ok2 and out2:
                for entry in _parse_emareos_terse(out2):
                    name = entry.get('name', '')
                    if name in iface_map:
                        for k in ('rx-byte', 'tx-byte', 'rx-packet', 'tx-packet',
                                  'rx-error', 'tx-error', 'rx-drop', 'tx-drop'):
                            py_key = k.replace('-', '_').replace('byte', 'bytes').replace('packet', 'packets').replace('error', 'errors').replace('drop', 'drops')
                            iface_map[name][py_key] = int(entry.get(k, '0') or '0')
            interfaces = list(iface_map.values())
        else:
            # Linux: /proc/net/dev
            ok, out, _ = self._exec(server_id,
                "cat /proc/net/dev 2>/dev/null")
            if ok and out:
                for line in out.strip().split('\n')[2:]:  # İlk 2 satır başlık
                    parts = line.strip().split()
                    if len(parts) >= 10 and ':' in parts[0]:
                        name = parts[0].rstrip(':')
                        interfaces.append({
                            'name': name, 'type': '', 'running': True, 'disabled': False,
                            'rx_bytes': int(parts[1]), 'tx_bytes': int(parts[9]),
                            'rx_packets': int(parts[2]), 'tx_packets': int(parts[10]),
                            'rx_errors': int(parts[3]), 'tx_errors': int(parts[11]),
                            'rx_drops': int(parts[4]), 'tx_drops': int(parts[12]),
                        })

        return {'interfaces': interfaces, 'firewall_type': fw or 'unknown'}

    def net_ping(self, server_id: str, target: str, count: int = 4) -> dict:
        """Hedef adrese ping atar, gecikme ölçer."""
        # Güvenlik: target doğrulama — yalnızca IP veya hostname
        target = target.strip()
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,253}$', target):
            return {'success': False, 'error': 'Geçersiz hedef adres.'}
        if count <= 0:
            count = 1000
        count = min(count, 10000)

        fw = self._detect_type(server_id)
        if fw == 'emareos':
            cmd = f'/emare tools ping address={_sq(target)} count={count}'
        else:
            interval = '-i 0.2 ' if count > 20 else ''
            cmd = f'ping -c {count} {interval}-W 3 {_sq(target)} 2>&1'

        ok, out, err = self._exec(server_id, cmd)
        result = {
            'success': ok, 'target': target, 'count': count,
            'output': out or err or '', 'packets_sent': 0,
            'packets_received': 0, 'packet_loss': 100.0,
            'rtt_min': 0.0, 'rtt_avg': 0.0, 'rtt_max': 0.0,
        }
        if ok and out:
            # "X packets transmitted, Y received" ayrıştır
            m = re.search(r'(\d+)\s+packets?\s+transmitted.*?(\d+)\s+received', out)
            if m:
                result['packets_sent'] = int(m.group(1))
                result['packets_received'] = int(m.group(2))
                if result['packets_sent'] > 0:
                    result['packet_loss'] = round(
                        (1 - result['packets_received'] / result['packets_sent']) * 100, 1)
            # rtt min/avg/max ayrıştır
            m = re.search(r'(?:rtt|round-trip).*?=\s*([\d.]+)/([\d.]+)/([\d.]+)', out)
            if m:
                result['rtt_min'] = float(m.group(1))
                result['rtt_avg'] = float(m.group(2))
                result['rtt_max'] = float(m.group(3))
            # Emare OS formatı: "sent=4 received=4 ... min-rtt=1ms avg-rtt=2ms max-rtt=5ms"
            for key, field in [('packets_sent', 'sent'), ('packets_received', 'received')]:
                m2 = re.search(rf'{field}=(\d+)', out)
                if m2:
                    result[key] = int(m2.group(1))
            for key, field in [('rtt_min', 'min-rtt'), ('rtt_avg', 'avg-rtt'), ('rtt_max', 'max-rtt')]:
                m2 = re.search(rf'{field}=([\d.]+)', out)
                if m2:
                    result[key] = float(m2.group(1))
            if result['packets_sent'] > 0:
                result['packet_loss'] = round(
                    (1 - result['packets_received'] / result['packets_sent']) * 100, 1)
        return result

    def net_traceroute(self, server_id: str, target: str, max_hops: int = 20) -> dict:
        """Hedef adrese traceroute yapar."""
        target = target.strip()
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,253}$', target):
            return {'success': False, 'error': 'Geçersiz hedef adres.', 'hops': []}
        max_hops = max(5, min(max_hops, 30))

        fw = self._detect_type(server_id)
        if fw == 'emareos':
            cmd = f'/emare tools traceroute address={_sq(target)} count=1 max-hops={max_hops}'
        else:
            cmd = f'traceroute -m {max_hops} -w 3 {_sq(target)} 2>&1 || tracepath {_sq(target)} 2>&1'

        ok, out, err = self._exec(server_id, cmd)
        hops = []
        if ok and out:
            for line in out.strip().split('\n'):
                m = re.match(r'\s*(\d+)\s+(.+)', line)
                if m:
                    hop_num = int(m.group(1))
                    rest = m.group(2).strip()
                    # "* * *" — timeout
                    if rest.replace('*', '').replace(' ', '') == '':
                        hops.append({'hop': hop_num, 'host': '*', 'ip': '', 'rtt': None})
                        continue
                    # "hostname (IP) RTTms" veya "IP RTTms"
                    hm = re.search(r'([\w.-]+)\s+\(([\d.]+)\)\s+([\d.]+)\s*ms', rest)
                    if hm:
                        hops.append({'hop': hop_num, 'host': hm.group(1),
                                     'ip': hm.group(2), 'rtt': float(hm.group(3))})
                    else:
                        # Sadece IP
                        hm2 = re.search(r'([\d.]+)\s+([\d.]+)\s*ms', rest)
                        if hm2:
                            hops.append({'hop': hop_num, 'host': hm2.group(1),
                                         'ip': hm2.group(1), 'rtt': float(hm2.group(2))})
                        else:
                            hops.append({'hop': hop_num, 'host': rest.split()[0] if rest.split() else '*',
                                         'ip': '', 'rtt': None})

        return {'success': ok, 'target': target, 'max_hops': max_hops,
                'hops': hops, 'output': out or err or ''}

    def net_dns_lookup(self, server_id: str, domain: str, record_type: str = 'A') -> dict:
        """DNS sorgusu yapar (A, AAAA, MX, NS, TXT, CNAME, SOA, PTR)."""
        domain = domain.strip()
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._-]{0,253}$', domain):
            return {'success': False, 'error': 'Geçersiz domain.', 'records': []}
        record_type = record_type.upper().strip()
        if record_type not in ('A', 'AAAA', 'MX', 'NS', 'TXT', 'CNAME', 'SOA', 'PTR', 'SRV'):
            return {'success': False, 'error': 'Geçersiz kayıt tipi.', 'records': []}

        fw = self._detect_type(server_id)
        if fw == 'emareos':
            cmd = f'/emare tools dns-lookup name={_sq(domain)} type={record_type}'
        else:
            # dig > nslookup > host fallback
            cmd = (f'dig +short {_sq(domain)} {record_type} 2>/dev/null || '
                   f'nslookup -type={record_type} {_sq(domain)} 2>/dev/null || '
                   f'host -t {record_type} {_sq(domain)} 2>/dev/null')

        ok, out, err = self._exec(server_id, cmd)
        records = []
        if ok and out:
            for line in out.strip().split('\n'):
                line = line.strip()
                if line and not line.startswith(';') and not line.startswith('#'):
                    records.append(line)

        return {'success': ok, 'domain': domain, 'type': record_type,
                'records': records, 'output': out or err or ''}

    def net_port_check(self, server_id: str, target: str, port: int, protocol: str = 'tcp') -> dict:
        """Hedef adres:port'a bağlantı testi yapar."""
        target = target.strip()
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,253}$', target):
            return {'success': False, 'open': False, 'error': 'Geçersiz hedef.'}
        if not (1 <= port <= 65535):
            return {'success': False, 'open': False, 'error': 'Port 1-65535 arası olmalı.'}
        protocol = protocol.lower()
        if protocol not in ('tcp', 'udp'):
            return {'success': False, 'open': False, 'error': 'Protokol tcp veya udp olmalı.'}

        fw = self._detect_type(server_id)
        if fw == 'emareos':
            cmd = f'/emare tools port-check address={_sq(target)} port={port} protocol={protocol}'
        else:
            if protocol == 'tcp':
                cmd = (f'timeout 5 bash -c "echo >/dev/tcp/{target}/{port}" 2>&1 '
                       f'&& echo "OPEN" || echo "CLOSED"')
            else:
                cmd = f'nc -zu -w3 {_sq(target)} {port} 2>&1 && echo "OPEN" || echo "CLOSED"'

        ok, out, _ = self._exec(server_id, cmd)
        is_open = 'OPEN' in (out or '').upper() or 'open' in (out or '').lower()
        return {'success': ok, 'target': target, 'port': port,
                'protocol': protocol, 'open': is_open, 'output': out or ''}

    def net_top_talkers(self, server_id: str, limit: int = 20) -> dict:
        """En çok bağlantı kuran IP'leri döndürür."""
        limit = max(5, min(limit, 100))
        fw = self._detect_type(server_id)

        talkers = []
        if fw == 'emareos':
            ok, out, _ = self._exec(server_id,
                '/emare firewall connections print terse without-paging')
            if ok and out:
                ip_counts = {}
                for entry in _parse_emareos_terse(out):
                    src = entry.get('src-address', '')
                    ip = src.split(':')[0] if ':' in src else src
                    if ip:
                        ip_counts[ip] = ip_counts.get(ip, 0) + 1
                for ip, cnt in sorted(ip_counts.items(), key=lambda x: -x[1])[:limit]:
                    talkers.append({'ip': ip, 'connections': cnt})
        else:
            # Linux: ss veya netstat
            ok, out, _ = self._exec(server_id,
                f"ss -tn state established 2>/dev/null | awk '{{print $5}}' | "
                f"rev | cut -d: -f2- | rev | sort | uniq -c | sort -rn | head -{limit}")
            if ok and out:
                for line in out.strip().split('\n'):
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2:
                        try:
                            talkers.append({'ip': parts[1].strip(), 'connections': int(parts[0])})
                        except ValueError:
                            pass

        return {'talkers': talkers, 'firewall_type': fw or 'unknown'}

    def net_listening_ports(self, server_id: str) -> dict:
        """Dinleyen port ve servisleri listeler."""
        fw = self._detect_type(server_id)
        ports = []

        if fw == 'emareos':
            # services zaten servisleri listeler, ek olarak soket bilgisi
            ok, out, _ = self._exec(server_id,
                '/emare services print terse without-paging')
            if ok and out:
                for entry in _parse_emareos_terse(out):
                    if entry.get('disabled', 'yes') == 'no':
                        ports.append({
                            'port': int(entry.get('port', '0') or '0'),
                            'protocol': 'tcp',
                            'service': entry.get('name', ''),
                            'state': 'LISTEN',
                            'pid': '',
                        })
        else:
            ok, out, _ = self._exec(server_id,
                "ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null")
            if ok and out:
                for line in out.strip().split('\n')[1:]:  # Başlığı atla
                    parts = line.split()
                    if len(parts) >= 4:
                        state = parts[0] if parts[0] in ('LISTEN', 'tcp', 'tcp6') else ''
                        local = parts[3] if len(parts) > 3 else ''
                        # Portu ayıkla
                        port_str = local.rsplit(':', 1)[-1] if ':' in local else ''
                        proc = parts[-1] if len(parts) >= 6 else ''
                        try:
                            port_num = int(port_str)
                        except ValueError:
                            continue
                        ports.append({
                            'port': port_num, 'protocol': 'tcp',
                            'service': proc, 'state': 'LISTEN', 'pid': proc,
                        })

        return {'ports': ports, 'firewall_type': fw or 'unknown'}

    def net_packet_capture(self, server_id: str, interface: str = 'any',
                           count: int = 50, filter_expr: str = '') -> dict:
        """Kısa süreli paket yakalama (tcpdump snapshot)."""
        # Güvenlik: interface doğrulama
        interface = interface.strip()
        if not re.match(r'^[a-zA-Z0-9._-]{1,32}$', interface):
            return {'success': False, 'error': 'Geçersiz interface adı.', 'packets': []}
        count = max(1, min(count, 200))
        # Güvenlik: filter_expr'den tehlikeli karakter temizleme
        if filter_expr:
            filter_expr = filter_expr.strip()
            if not re.match(r'^[a-zA-Z0-9 .:/_-]{0,200}$', filter_expr):
                return {'success': False, 'error': 'Geçersiz filtre ifadesi.', 'packets': []}

        fw = self._detect_type(server_id)
        if fw == 'emareos':
            cmd = f'/emare tools packet-sniffer quick count={count}'
            if interface != 'any':
                cmd += f' interface={_sq(interface)}'
            if filter_expr:
                cmd += f' filter={_sq(filter_expr)}'
        else:
            iface = f'-i {_sq(interface)}'
            filt = f' {_sq(filter_expr)}' if filter_expr else ''
            cmd = f'sudo timeout 10 tcpdump {iface} -c {count} -nn -l 2>/dev/null{filt}'

        ok, out, err = self._exec(server_id, cmd)
        packets = []
        if ok and out:
            for line in out.strip().split('\n'):
                line = line.strip()
                if line and not line.startswith('tcpdump:') and not line.startswith('listening'):
                    packets.append(line)
                    if len(packets) >= count:
                        break

        return {'success': ok, 'interface': interface, 'count': len(packets),
                'packets': packets, 'output': out or err or ''}

    def net_speed_test(self, server_id: str, target: str = '8.8.8.8',
                       duration: int = 5) -> dict:
        """Basit hız tahmini — iperf3 veya indirme testi."""
        target = target.strip()
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,253}$', target):
            return {'success': False, 'error': 'Geçersiz hedef.'}
        duration = max(2, min(duration, 15))

        fw = self._detect_type(server_id)
        if fw == 'emareos':
            cmd = f'/emare tools bandwidth-test address={_sq(target)} duration={duration}'
        else:
            # iperf3 varsa kullan, yoksa dd+curl ile basit test
            cmd = (f'iperf3 -c {_sq(target)} -t {duration} -J 2>/dev/null || '
                   f'echo "iperf3_unavailable"')

        ok, out, err = self._exec(server_id, cmd)
        result = {'success': ok, 'target': target, 'duration': duration,
                  'output': out or err or '',
                  'download_mbps': 0.0, 'upload_mbps': 0.0}

        if ok and out and 'iperf3_unavailable' not in out:
            try:
                data = json.loads(out)
                end = data.get('end', {})
                recv = end.get('sum_received', {})
                sent = end.get('sum_sent', {})
                result['download_mbps'] = round(recv.get('bits_per_second', 0) / 1_000_000, 2)
                result['upload_mbps'] = round(sent.get('bits_per_second', 0) / 1_000_000, 2)
            except (json.JSONDecodeError, KeyError):
                # Emare OS veya düz metin çıktı
                m = re.search(r'(?:download|rx).*?([\d.]+)\s*(?:Mbps|mbps)', out, re.I)
                if m:
                    result['download_mbps'] = float(m.group(1))
                m = re.search(r'(?:upload|tx).*?([\d.]+)\s*(?:Mbps|mbps)', out, re.I)
                if m:
                    result['upload_mbps'] = float(m.group(1))

        return result

    def net_whois(self, server_id: str, target: str) -> dict:
        """IP veya domain WHOIS sorgusu."""
        target = target.strip()
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9._:-]{0,253}$', target):
            return {'success': False, 'error': 'Geçersiz hedef.', 'output': ''}

        ok, out, err = self._exec(server_id,
            f'whois {_sq(target)} 2>/dev/null | head -80')
        info = {}
        if ok and out:
            for line in out.strip().split('\n'):
                if ':' in line and not line.startswith('%') and not line.startswith('#'):
                    key, _, val = line.partition(':')
                    key = key.strip().lower()
                    val = val.strip()
                    if key and val:
                        info[key] = val

        return {'success': ok, 'target': target, 'info': info,
                'output': out or err or ''}

    def net_summary(self, server_id: str) -> dict:
        """Tüm ağ analizini tek çağrıda toplar (dashboard için)."""
        fw = self._detect_type(server_id)
        summary = {
            'firewall_type': fw or 'unknown',
            'interfaces': [],
            'top_talkers': [],
            'listening_ports': [],
            'total_connections': 0,
        }

        if fw == 'emareos':
            results = self._exec_multi(server_id, [
                '/emare network interfaces print terse without-paging',
                '/emare firewall connections print terse without-paging',
                '/emare services print terse without-paging',
            ])
            # Interfaces
            ok1, out1, _ = results[0]
            if ok1 and out1:
                for entry in _parse_emareos_terse(out1):
                    name = entry.get('name', '')
                    if name:
                        summary['interfaces'].append({
                            'name': name,
                            'type': entry.get('type', ''),
                            'running': entry.get('running', '') == 'yes',
                        })
            # Top talkers + connection count
            ok2, out2, _ = results[1]
            if ok2 and out2:
                ip_counts = {}
                total = 0
                for entry in _parse_emareos_terse(out2):
                    total += 1
                    src = entry.get('src-address', '')
                    ip = src.split(':')[0] if ':' in src else src
                    if ip:
                        ip_counts[ip] = ip_counts.get(ip, 0) + 1
                summary['total_connections'] = total
                for ip, cnt in sorted(ip_counts.items(), key=lambda x: -x[1])[:10]:
                    summary['top_talkers'].append({'ip': ip, 'connections': cnt})
            # Listening
            ok3, out3, _ = results[2]
            if ok3 and out3:
                for entry in _parse_emareos_terse(out3):
                    if entry.get('disabled', 'yes') == 'no':
                        summary['listening_ports'].append({
                            'port': int(entry.get('port', '0') or '0'),
                            'service': entry.get('name', ''),
                        })
        else:
            # Linux: tek komut zinciri
            results = self._exec_multi(server_id, [
                "cat /proc/net/dev 2>/dev/null | tail -n +3",
                "ss -tn state established 2>/dev/null | tail -n +2 | wc -l",
                "ss -tn state established 2>/dev/null | awk '{print $5}' | rev | cut -d: -f2- | rev | sort | uniq -c | sort -rn | head -10",
                "ss -tlnp 2>/dev/null | tail -n +2",
            ])
            # Interfaces
            ok1, out1, _ = results[0]
            if ok1 and out1:
                for line in out1.strip().split('\n'):
                    parts = line.strip().split()
                    if len(parts) >= 2 and ':' in parts[0]:
                        summary['interfaces'].append({
                            'name': parts[0].rstrip(':'),
                            'type': '', 'running': True,
                        })
            # Connection count
            ok2, out2, _ = results[1]
            if ok2 and out2:
                try:
                    summary['total_connections'] = int(out2.strip())
                except ValueError:
                    pass
            # Top talkers
            ok3, out3, _ = results[2]
            if ok3 and out3:
                for line in out3.strip().split('\n'):
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2:
                        try:
                            summary['top_talkers'].append({
                                'ip': parts[1].strip(), 'connections': int(parts[0])})
                        except ValueError:
                            pass
            # Listening ports
            ok4, out4, _ = results[3]
            if ok4 and out4:
                for line in out4.strip().split('\n'):
                    parts = line.split()
                    if len(parts) >= 4:
                        local = parts[3] if len(parts) > 3 else ''
                        p = local.rsplit(':', 1)[-1] if ':' in local else ''
                        try:
                            summary['listening_ports'].append({
                                'port': int(p), 'service': parts[-1] if len(parts) >= 6 else ''})
                        except ValueError:
                            pass

        return summary

    # ═══════════════════ NETWORK YÖNETİMİ ═══════════════════

    def network_apply_rule(self, server_ids: list, action: str,
                           rule_params: dict) -> dict:
        """Birden fazla sunucuya aynı kuralı uygula.

        Args:
            server_ids: Hedef sunucu ID listesi
            action: 'add_rule' | 'delete_rule' | 'block_ip' | 'unblock_ip' |
                    'add_port_forward' | 'delete_port_forward'
            rule_params: İlgili metoda geçilecek parametreler

        Returns:
            { success, results: [{server_id, success, message}...],
              total, succeeded, failed }
        """
        results = []
        for sid in server_ids:
            try:
                if action == 'add_rule':
                    r = self.add_rule(sid, **rule_params)
                elif action == 'delete_rule':
                    r = self.delete_rule(sid, **rule_params)
                elif action == 'block_ip':
                    r = self.block_ip(sid, **rule_params)
                elif action == 'unblock_ip':
                    r = self.unblock_ip(sid, **rule_params)
                elif action == 'add_port_forward':
                    r = self.add_port_forward(sid, **rule_params)
                elif action == 'delete_port_forward':
                    r = self.delete_port_forward(sid, **rule_params)
                else:
                    r = (False, f'Bilinmeyen aksiyon: {action}')
                if isinstance(r, tuple):
                    ok_r, msg_r = r[0], (r[1] if len(r) > 1 else '')
                else:
                    ok_r = r.get('success', False)
                    msg_r = r.get('message', '')
                results.append({
                    'server_id': sid,
                    'success': ok_r,
                    'message': msg_r
                })
            except Exception as e:
                results.append({
                    'server_id': sid,
                    'success': False,
                    'message': str(e)
                })
        succeeded = sum(1 for r in results if r['success'])
        return {
            'success': succeeded > 0,
            'results': results,
            'total': len(server_ids),
            'succeeded': succeeded,
            'failed': len(server_ids) - succeeded,
        }

    def network_get_statuses(self, server_ids: list) -> dict:
        """Birden fazla sunucunun durumunu toplu al.

        Returns:
            { success, statuses: [{server_id, success, firewall}...] }
        """
        statuses = []
        for sid in server_ids:
            try:
                st = self.get_status(sid)
                statuses.append({
                    'server_id': sid,
                    'success': st.get('type') is not None,
                    'firewall': st
                })
            except Exception as e:
                statuses.append({
                    'server_id': sid,
                    'success': False,
                    'firewall': {},
                    'error': str(e)
                })
        return {'success': True, 'statuses': statuses}

    def network_sync_check(self, server_ids: list) -> dict:
        """Ağ'daki sunucuların kural uyumluluğunu kontrol eder.

        Tüm sunuculardan kuralları alır, farkları raporlar.

        Returns:
            { success, sync_status: 'synced'|'diverged',
              servers: [{server_id, type, rule_count, active}...],
              common_rules: int, diverged_rules: [{rule, present_on, missing_on}...] }
        """
        statuses = self.network_get_statuses(server_ids)
        servers_info = []
        all_rule_sets = {}
        for s in statuses.get('statuses', []):
            sid = s['server_id']
            fw = s.get('firewall', {})
            rules = fw.get('rules', [])
            rule_strs = set()
            for r in rules:
                key = f"{r.get('type','?')}:{r.get('rule','?')}"
                rule_strs.add(key)
            all_rule_sets[sid] = rule_strs
            servers_info.append({
                'server_id': sid,
                'type': fw.get('type', 'unknown'),
                'rule_count': len(rules),
                'active': fw.get('active', False),
                'online': s.get('success', False)
            })

        # Find common and diverged rules
        if all_rule_sets:
            all_rules = set()
            for rs in all_rule_sets.values():
                all_rules |= rs
            common = 0
            diverged = []
            for rule in sorted(all_rules):
                present = [sid for sid, rs in all_rule_sets.items() if rule in rs]
                missing = [sid for sid, rs in all_rule_sets.items() if rule not in rs]
                if not missing:
                    common += 1
                else:
                    diverged.append({
                        'rule': rule,
                        'present_on': present,
                        'missing_on': missing
                    })
            sync_status = 'synced' if not diverged else 'diverged'
        else:
            common = 0
            diverged = []
            sync_status = 'unknown'

        return {
            'success': True,
            'sync_status': sync_status,
            'servers': servers_info,
            'common_rules': common,
            'diverged_rules': diverged[:50]
        }
