"""
EmareCloud — Komut Güvenliği
Komut allowlist, yasaklı komutlar ve rol bazlı erişim kontrolü.
"""

import re

# ==================== KESİNLİKLE YASAKLI KOMUTLAR ====================
# Hiçbir rol (super_admin dahil UI'dan) çalıştıramaz

BLOCKED_PATTERNS = [
    r'rm\s+-rf\s+/\s*$',           # rm -rf /
    r'rm\s+-rf\s+/\*',             # rm -rf /*
    r'mkfs\s+/dev/sd',             # format disk
    r'dd\s+if=/dev/(zero|random)\s+of=/dev/sd',  # disk overwrite
    r':\(\)\s*\{.*\}',             # fork bomb
    r'>\s*/dev/sd[a-z]',           # redirect to disk
    r'chmod\s+-R\s+777\s+/',       # 777 everything
    r'wget\s+.*\|\s*(ba)?sh',      # download & execute
    r'curl\s+.*\|\s*(ba)?sh',      # download & execute
    r'echo\s+.*\|\s*base64\s+-d\s*\|\s*(ba)?sh',  # encoded exec
    r'/dev/tcp/',                   # reverse shell
    r'nc\s+-e',                    # netcat shell
    r'python.*-c.*import\s+os.*system',  # python shell
]

# ==================== OPERATÖR İZİNLİ KOMUTLAR ====================

OPERATOR_ALLOWED = [
    # Bilgi/görüntüleme
    r'^(ls|cat|head|tail|grep|find|wc|df|du|free|top|htop|ps|uptime|whoami|hostname|date|uname)(\s|$)',
    r'^(dmesg|last|w|who|id|groups|lsof)(\s|$)',
    # Servis yönetimi
    r'^systemctl\s+(status|restart|start|stop)\s+\w+',
    r'^service\s+\w+\s+(status|restart|start|stop)',
    r'^journalctl\b',
    # Docker (okuma + restart)
    r'^docker\s+(ps|logs|stats|inspect|images|top|port)\b',
    r'^docker\s+(restart|start|stop)\s+\w+',
    r'^docker\s+compose\s+(ps|logs|top)\b',
    # Paket bilgi
    r'^(apt|yum|dnf)\s+(list|show|search|info)\b',
    # Ağ bilgi
    r'^(ping|traceroute|tracepath|nslookup|dig|host|mtr)\s+',
    r'^(netstat|ss|ip|ifconfig)\b',
    r'^curl\s+',  # curl without pipe to sh (blocked above)
    # Disk bilgi
    r'^(lsblk|fdisk\s+-l|blkid|mount|findmnt|smartctl)\b',
    r'^mdadm\s+--detail\b',
]

# ==================== ADMİN EK İZİNLER ====================

ADMIN_EXTRA = [
    # Paket yönetimi
    r'^(apt|apt-get)\s+(update|upgrade|install|remove|purge|autoremove|autoclean)\b',
    r'^(yum|dnf)\s+(update|install|remove|groupinstall)\b',
    # Docker tam erişim
    r'^docker\s+(run|rm|rmi|pull|push|build|exec|cp|network|volume)\b',
    r'^docker\s+compose\s+(up|down|restart|build|pull)\b',
    # Dosya işlemleri
    r'^(mkdir|cp|mv|rm|touch|chmod|chown|ln)\s+',
    r'^(nano|vim|vi)\s+',
    r'^(tar|zip|unzip|gzip|gunzip)\s+',
    # Sistem yönetimi
    r'^systemctl\s+(enable|disable|mask|unmask)\s+\w+',
    r'^(useradd|usermod|userdel|groupadd|passwd)\b',
    r'^crontab\b',
    # Güvenlik duvarı
    r'^(iptables|ip6tables|nft|ufw|firewall-cmd)\b',
    # Git
    r'^git\s+',
]


def is_command_blocked(command: str) -> bool:
    """Komutun kesinlikle yasaklı olup olmadığını kontrol eder."""
    cmd = command.strip()
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return True
    return False


def is_command_allowed(command: str, role: str) -> tuple[bool, str]:
    """
    Komutun belirtilen rol tarafından çalıştırılıp çalıştırılamayacağını kontrol eder.

    Returns:
        (allowed: bool, reason: str)
    """
    cmd = command.strip()

    # 0) Boş komut kontrolü
    if not cmd:
        return False, 'Boş komut çalıştırılamaz'

    # 1) Kesinlikle yasaklı komut kontrolü
    if is_command_blocked(cmd):
        return False, 'Bu komut güvenlik nedeniyle engellenmiştir'

    # 2) Super admin her şeyi çalıştırabilir (yasaklılar hariç)
    if role == 'super_admin':
        return True, 'Süper admin yetkisi'

    # 3) Read-only kullanıcı hiçbir komut çalıştıramaz
    if role == 'read_only':
        return False, 'Salt okunur kullanıcılar komut çalıştıramaz'

    # 4) Admin — genişletilmiş allowlist
    if role == 'admin':
        all_patterns = OPERATOR_ALLOWED + ADMIN_EXTRA
        for pattern in all_patterns:
            if re.match(pattern, cmd, re.IGNORECASE):
                return True, 'İzin verilen komut'
        # Admin: allowlist dışındaki komutlar da çalıştırılabilir (onay ile)
        return True, 'Admin özel komut yetkisi'

    # 5) Operator — sadece allowlist
    if role == 'operator':
        for pattern in OPERATOR_ALLOWED:
            if re.match(pattern, cmd, re.IGNORECASE):
                return True, 'İzin verilen komut'
        return False, 'Bu komut operatör yetkiniz dahilinde değil. Yöneticinize başvurun.'

    return False, 'Bilinmeyen rol'
