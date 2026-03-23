"""
EmareCloud — Ağ Cihazı Yöneticisi
Router, Switch, Firewall gibi ağ donanımlarına SSH üzerinden bağlanıp
marka/model bazlı komutlar çalıştırır.

Desteklenen markalar/OS'lar:
    cisco_ios   → Cisco IOS / IOS-XE
    cisco_nxos  → Cisco NX-OS (Nexus)
    mikrotik    → MikroTik RouterOS
    juniper     → Juniper JunOS
    huawei      → Huawei VRP
    fortinet    → Fortinet FortiOS
    palo_alto   → Palo Alto PAN-OS
    hp_aruba    → HP / Aruba ProCurve
    ubiquiti    → Ubiquiti (EdgeOS/UniFi)
    pfsense     → pfSense / OPNsense
    generic     → Bilinmeyen / diğer
"""

import logging
import socket
import threading
import time
from typing import Optional

import paramiko

logger = logging.getLogger('emarecloud.network')

# ─────────────────────────────────────────────────────────────
# Marka → komut mapping
# ─────────────────────────────────────────────────────────────
BRAND_COMMANDS = {
    'cisco_ios': {
        'disable_paging': 'terminal length 0',
        'show_version':   'show version',
        'show_interfaces':'show interfaces brief',
        'show_running':   'show running-config',
        'show_startup':   'show startup-config',
        'show_arp':       'show arp',
        'show_routing':   'show ip route',
        'show_mac':       'show mac address-table',
        'show_cdp':       'show cdp neighbors',
        'show_ospf':      'show ip ospf neighbor',
        'show_bgp':       'show ip bgp summary',
        'show_vlan':      'show vlan brief',
        'save_config':    'write memory',
        'show_vlans':     'show vlan brief',
    },
    'cisco_nxos': {
        'disable_paging': 'terminal length 0',
        'show_version':   'show version',
        'show_interfaces':'show interface brief',
        'show_running':   'show running-config',
        'show_startup':   'show startup-config',
        'show_arp':       'show ip arp',
        'show_routing':   'show ip route',
        'show_mac':       'show mac address-table',
        'show_cdp':       'show cdp neighbors',
        'show_vlan':      'show vlan brief',
        'save_config':    'copy running-config startup-config',
    },
    'mikrotik': {
        'disable_paging': '',
        'show_version':   '/system resource print',
        'show_interfaces':'/interface print',
        'show_running':   '/export',
        'show_startup':   '/export',
        'show_arp':       '/ip arp print',
        'show_routing':   '/ip route print',
        'show_mac':       '/interface bridge host print',
        'save_config':    '/system backup save name=emarecloud-backup',
        'show_vlans':     '/interface vlan print',
        'show_dhcp':      '/ip dhcp-server lease print',
        'show_firewall':  '/ip firewall filter print',
        'show_nat':       '/ip firewall nat print',
    },
    'juniper': {
        'disable_paging': 'set cli screen-length 0',
        'show_version':   'show version',
        'show_interfaces':'show interfaces terse',
        'show_running':   'show configuration',
        'show_startup':   'show configuration',
        'show_arp':       'show arp',
        'show_routing':   'show route',
        'show_mac':       'show ethernet-switching table',
        'show_ospf':      'show ospf neighbor',
        'show_bgp':       'show bgp summary',
        'show_vlan':      'show vlans',
        'save_config':    'commit',
    },
    'huawei': {
        'disable_paging': 'screen-length 0 temporary',
        'show_version':   'display version',
        'show_interfaces':'display interface brief',
        'show_running':   'display current-configuration',
        'show_startup':   'display saved-configuration',
        'show_arp':       'display arp all',
        'show_routing':   'display ip routing-table',
        'show_mac':       'display mac-address',
        'show_ospf':      'display ospf peer brief',
        'show_bgp':       'display bgp peer',
        'show_vlan':      'display vlan all',
        'save_config':    'save',
    },
    'fortinet': {
        'disable_paging': 'config system console\nset output standard\nend',
        'show_version':   'get system status',
        'show_interfaces':'get system interface physical',
        'show_running':   'show full-configuration',
        'show_startup':   'show full-configuration',
        'show_arp':       'get system arp',
        'show_routing':   'get router info routing-table all',
        'show_firewall':  'show firewall policy',
        'show_nat':       'show firewall ippool',
        'save_config':    'execute backup running-config flash backup.cfg',
    },
    'palo_alto': {
        'disable_paging': 'set cli pager off',
        'show_version':   'show system info',
        'show_interfaces':'show interface all',
        'show_running':   'show config running',
        'show_startup':   'show config startup',
        'show_arp':       'show arp all',
        'show_routing':   'show routing route',
        'show_firewall':  'show running security-policy',
        'show_nat':       'show running nat-policy',
    },
    'hp_aruba': {
        'disable_paging': 'no page',
        'show_version':   'show version',
        'show_interfaces':'show interfaces brief',
        'show_running':   'show running-config',
        'show_startup':   'show startup-config',
        'show_arp':       'show arp',
        'show_routing':   'show ip route',
        'show_mac':       'show mac-address',
        'show_vlan':      'show vlan',
        'save_config':    'write memory',
    },
    'ubiquiti': {
        'disable_paging': '',
        'show_version':   'mca-cli-op show version',
        'show_interfaces':'ip addr show',
        'show_running':   'cat /config/config.gateway.json 2>/dev/null || ip a',
        'show_arp':       'arp -n',
        'show_routing':   'ip route show',
        'show_mac':       'ip neigh show',
    },
    'pfsense': {
        'disable_paging': '',
        'show_version':   'php -r "require_once(\"globals.inc\"); echo g_get(\"product_version\");"',
        'show_interfaces':'ifconfig',
        'show_running':   'cat /cf/conf/config.xml | head -200',
        'show_arp':       'arp -na',
        'show_routing':   'netstat -rn',
        'show_firewall':  'pfctl -sr',
        'show_nat':       'pfctl -sn',
    },
    'generic': {
        'disable_paging': '',
        'show_version':   'uname -a',
        'show_interfaces':'ip addr show 2>/dev/null || ifconfig',
        'show_running':   '',
        'show_arp':       'arp -na',
        'show_routing':   'ip route show 2>/dev/null || netstat -rn',
        'show_mac':       'ip neigh show 2>/dev/null || arp -n',
    },
}

# Cihaz tipi ikonu
DEVICE_TYPE_ICONS = {
    'router':    'fa-route',
    'switch':    'fa-network-wired',
    'firewall':  'fa-shield-halved',
    'ap':        'fa-wifi',
    'lb':        'fa-arrows-split-up-and-left',
    'other':     'fa-microchip',
}

BRAND_LABELS = {
    'cisco_ios':   'Cisco IOS',
    'cisco_nxos':  'Cisco NX-OS',
    'mikrotik':    'MikroTik',
    'juniper':     'Juniper',
    'huawei':      'Huawei',
    'fortinet':    'Fortinet',
    'palo_alto':   'Palo Alto',
    'hp_aruba':    'HP / Aruba',
    'ubiquiti':    'Ubiquiti',
    'pfsense':     'pfSense / OPN',
    'generic':     'Genel / Diğer',
}


def get_brand_commands(brand: str) -> dict:
    return BRAND_COMMANDS.get(brand, BRAND_COMMANDS['generic'])


def get_command(brand: str, key: str) -> str:
    return BRAND_COMMANDS.get(brand, BRAND_COMMANDS['generic']).get(key, '')


# ─────────────────────────────────────────────────────────────
# NetworkDeviceManager — bağlantı ve komut çalıştırma
# ─────────────────────────────────────────────────────────────

class NetworkDeviceManager:
    """Ağ cihazlarına SSH bağlantısı ve komut yönetimi."""

    _lock = threading.Lock()
    _clients: dict = {}   # device_id → paramiko.SSHClient

    # ── Erişilebilirlik kontrolü ──────────────────────────────

    @staticmethod
    def ping(host: str, port: int = 22, timeout: float = 3.0) -> tuple[bool, float]:
        """TCP bağlantı testi ile erişilebilirliği ve gecikmeyi ölç."""
        t0 = time.monotonic()
        try:
            sock = socket.create_connection((host, int(port)), timeout=timeout)
            sock.close()
            return True, round((time.monotonic() - t0) * 1000, 1)
        except Exception:
            return False, 0.0

    # ── Bağlantı yönetimi ────────────────────────────────────

    def connect(self, device_id: str, host: str, port: int,
                username: str, password: str, brand: str = 'generic',
                timeout: float = 15.0) -> tuple[bool, str]:
        """Cihaza SSH bağlantısı kur ve paging'i devre dışı bırak."""
        with self._lock:
            if device_id in self._clients:
                try:
                    transport = self._clients[device_id].get_transport()
                    if transport and transport.is_active():
                        return True, 'Zaten bağlı'
                except Exception:
                    pass
                self._clients.pop(device_id, None)

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=host,
                port=int(port),
                username=username,
                password=password,
                timeout=timeout,
                allow_agent=False,
                look_for_keys=False,
                banner_timeout=20,
            )
        except paramiko.AuthenticationException:
            return False, 'Kimlik doğrulama hatası — kullanıcı adı/şifre yanlış'
        except paramiko.SSHException as e:
            return False, f'SSH hatası: {e}'
        except socket.timeout:
            return False, 'Bağlantı zaman aşımı'
        except Exception as e:
            return False, f'Bağlantı kurulamadı: {e}'

        # Paging devre dışı
        disable_cmd = get_command(brand, 'disable_paging')
        if disable_cmd:
            for cmd in disable_cmd.split('\n'):
                cmd = cmd.strip()
                if cmd:
                    try:
                        _, stdout, _ = client.exec_command(cmd, timeout=5)
                        stdout.read()
                    except Exception:
                        pass

        with self._lock:
            self._clients[device_id] = client

        logger.info('Ağ cihazı bağlandı: %s (%s)', device_id, host)
        return True, 'Bağlantı kuruldu'

    def disconnect(self, device_id: str):
        with self._lock:
            client = self._clients.pop(device_id, None)
        if client:
            try:
                client.close()
            except Exception:
                pass

    def is_connected(self, device_id: str) -> bool:
        with self._lock:
            client = self._clients.get(device_id)
        if not client:
            return False
        try:
            transport = client.get_transport()
            return transport is not None and transport.is_active()
        except Exception:
            return False

    # ── Komut çalıştırma ─────────────────────────────────────

    def execute(self, device_id: str, command: str,
                timeout: float = 30.0) -> tuple[bool, str]:
        """Bağlı cihazda komut çalıştır, çıktıyı döndür."""
        with self._lock:
            client = self._clients.get(device_id)
        if not client:
            return False, 'Cihaz bağlı değil'
        try:
            _, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode('utf-8', errors='replace')
            err = stderr.read().decode('utf-8', errors='replace')
            output = out or err
            return True, output
        except Exception as e:
            return False, f'Komut çalıştırma hatası: {e}'

    def execute_auto_connect(self, device_id: str, host: str, port: int,
                             username: str, password: str, brand: str,
                             command: str, timeout: float = 30.0) -> tuple[bool, str]:
        """Gerekirse bağlantı kur, komutu çalıştır."""
        if not self.is_connected(device_id):
            ok, msg = self.connect(device_id, host, port, username, password, brand)
            if not ok:
                return False, msg
        return self.execute(device_id, command, timeout=timeout)

    # ── Hazır sorgu methodları ────────────────────────────────

    def get_interfaces(self, device_id: str, host: str, port: int,
                       username: str, password: str, brand: str) -> tuple[bool, str]:
        cmd = get_command(brand, 'show_interfaces')
        if not cmd:
            return False, 'Bu marka için arayüz komutu tanımlı değil'
        return self.execute_auto_connect(device_id, host, port, username, password, brand, cmd)

    def get_version(self, device_id: str, host: str, port: int,
                    username: str, password: str, brand: str) -> tuple[bool, str]:
        cmd = get_command(brand, 'show_version')
        if not cmd:
            return False, 'Bu marka için versiyon komutu tanımlı değil'
        return self.execute_auto_connect(device_id, host, port, username, password, brand, cmd)

    def get_running_config(self, device_id: str, host: str, port: int,
                           username: str, password: str, brand: str) -> tuple[bool, str]:
        cmd = get_command(brand, 'show_running')
        if not cmd:
            return False, 'Bu marka için config komutu tanımlı değil'
        return self.execute_auto_connect(device_id, host, port, username, password, brand, cmd, timeout=60.0)


# Global singleton
net_mgr = NetworkDeviceManager()
