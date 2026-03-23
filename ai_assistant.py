"""
EmareCloud — AI Terminal Asistanı
Gemini AI destekli akıllı asistan: terminal çıkıntısı analizi, log açıklama,
komut önerisi, optimizasyon tavsiyeleri.
Gemini erişilemezse kural tabanlı sistemle yanıt verir.
"""

import logging
import re

logger = logging.getLogger('emarecloud.ai_assistant')

# ============================================================
# GEMINI ENTEGRASYONU — anahtarlar.py üzerinden
# ============================================================

_GEMINI_MODEL = "gemini-2.5-flash"    # Hızlı, ücretsiz kota yüksek

_SYSTEM_PROMPT = """Sen EmareCloud platformunun yerleşik AI asistanısın. Adın "Emare AI".

EmareCloud; Linux/AlmaLinux/Ubuntu sunucuları SSH ile yöneten, Docker, Nginx, PHP,
LXD sanal makine, firewall, RBAC, market uygulamaları ve blockchain/token özelliklerine
sahip bir cloud panel platformudur.

Görevin:
- Terminal çıktılarındaki hataları Türkçe açıklamak ve çözmek
- Linux komutlarını açıklamak, optimizasyon önerileri sunmak
- SSH/nginx/php/docker/systemd konularında rehberlik etmek
- Yanıtları kısa, net, actionable tutmak (liste + komut blokları kullan)
- Şüphe duyduğunda `journalctl -xe`, `systemctl status`, `tail -f` gibi teşhis komutları öner

Yanıt formatı:
- Markdown kullan (başlık, kod bloğu, liste)
- Kod örneklerini ```bash ... ``` içinde ver
- Maksimum 400 kelime
- Türkçe yanıt ver
"""


def _gemini_analyze(question: str, context: str = '') -> dict | None:
    """Gemini API ile analiz. Başarısız olursa None döner."""
    try:
        from anahtarlar import gemini_key
        api_key = str(gemini_key)
        if not api_key or api_key.startswith('<') or len(api_key) < 10:
            return None
    except Exception:
        return None

    prompt_parts = []
    if context and context.strip():
        prompt_parts.append(f"**Terminal Çıktısı (son bölüm):**\n```\n{context[-2000:]}\n```\n")
    if question and question.strip():
        prompt_parts.append(f"**Soru:** {question}")

    if not prompt_parts:
        return None

    full_prompt = "\n\n".join(prompt_parts)

    # SDK denemesi — yeni google-genai paketi (>= 0.8)
    try:
        from google import genai as _genai
        from google.genai import types as _gtypes
        client = _genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=full_prompt,
            config=_gtypes.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                max_output_tokens=800,
                temperature=0.4,
            ),
        )
        text = resp.text.strip()
        return {
            'response': text,
            'suggestions': _extract_commands(text),
            'model': _GEMINI_MODEL,
        }
    except ImportError:
        pass
    except Exception as e:
        logger.debug("Gemini SDK hatası: %s", e)

    # Fallback: doğrudan REST
    try:
        import json as _json
        import urllib.request as _req
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{_GEMINI_MODEL}:generateContent?key={api_key}"
        )
        payload = _json.dumps({
            "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {"maxOutputTokens": 800, "temperature": 0.4},
        }).encode()
        request = _req.Request(url, data=payload,
                               headers={"Content-Type": "application/json"},
                               method="POST")
        with _req.urlopen(request, timeout=15) as resp:
            data = _json.loads(resp.read())
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return {
            'response': text,
            'suggestions': _extract_commands(text),
            'model': _GEMINI_MODEL,
        }
    except Exception as e:
        logger.debug("Gemini REST hatası: %s", e)
        return None


def _extract_commands(text: str) -> list:
    """Markdown kod bloklarından bash komutlarını çıkarır."""
    cmds = re.findall(r'```(?:bash|shell|sh)?\s*\n?(.*?)```', text, re.DOTALL)
    result = []
    for block in cmds:
        for line in block.strip().splitlines():
            line = line.strip().lstrip('$').strip()
            if line and not line.startswith('#') and len(line) < 120:
                result.append(line)
    return result[:5]


# ============================================================
# PATTERN TABANLARI — Hata tanıma, komut açıklama
# ============================================================

ERROR_PATTERNS = [
    # Permission / Yetki
    (r'permission denied|eacces|operation not permitted',
     '🔒 **Yetki Hatası**: Komut yeterli izinle çalıştırılmamış.\n\n'
     '**Çözüm:**\n'
     '- `sudo` ile tekrar deneyin\n'
     '- Dosya izinlerini kontrol edin: `ls -la <dosya>`\n'
     '- Kullanıcıyı ilgili gruba ekleyin: `usermod -aG <grup> <kullanıcı>`'),

    # Disk Dolu
    (r'no space left on device|disk full|enospc',
     '💾 **Disk Dolu**: Disk alanı tükendi.\n\n'
     '**Çözüm:**\n'
     '- Disk durumunu kontrol edin: `df -h`\n'
     '- Büyük dosyaları bulun: `du -sh /* | sort -rh | head -20`\n'
     '- Log dosyalarını temizleyin: `journalctl --vacuum-size=100M`\n'
     '- Docker temizliği: `docker system prune -af`'),

    # Komut Bulunamadı
    (r'command not found|komut bulunamad',
     '❓ **Komut Bulunamadı**: Program kurulu değil veya PATH\'de yok.\n\n'
     '**Çözüm:**\n'
     '- Paket kurun: `dnf install <paket>` veya `apt install <paket>`\n'
     '- PATH kontrol: `echo $PATH`\n'
     '- Tam yol deneyin: `which <komut>` veya `find / -name <komut> 2>/dev/null`'),

    # Port Çakışması
    (r'address already in use|port.*already|eaddrinuse|bind.*failed',
     '🔌 **Port Çakışması**: İstenen port başka bir servis tarafından kullanılıyor.\n\n'
     '**Çözüm:**\n'
     '- Portu kullanan servisi bulun: `ss -tlnp | grep <port>` veya `lsof -i :<port>`\n'
     '- Servisi durdurun: `kill -9 <PID>` veya `systemctl stop <servis>`\n'
     '- Farklı port kullanın'),

    # Bellek Yetersiz
    (r'out of memory|oom|cannot allocate|killed.*memory|enomem',
     '🧠 **Bellek Yetersiz**: RAM tükendi, işlem OOM Killer tarafından sonlandırıldı.\n\n'
     '**Çözüm:**\n'
     '- Bellek durumu: `free -h`\n'
     '- En çok RAM kullanan: `ps aux --sort=-%mem | head -10`\n'
     '- Swap ekleyin: `fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`\n'
     '- Gereksiz servisleri durdurun'),

    # DNS / Bağlantı
    (r'could not resolve|name or service not known|dns|no route to host|connection refused|connection timed out',
     '🌐 **Ağ/DNS Hatası**: Hedef sunucuya ulaşılamıyor.\n\n'
     '**Çözüm:**\n'
     '- DNS kontrol: `cat /etc/resolv.conf` ve `dig <domain>`\n'
     '- Ağ testi: `ping 8.8.8.8` ve `curl -I https://google.com`\n'
     '- Firewall kontrol: `firewall-cmd --list-all` veya `iptables -L -n`\n'
     '- DNS değiştir: `echo "nameserver 8.8.8.8" >> /etc/resolv.conf`'),

    # SSL / Sertifika
    (r'ssl|certificate|tls.*error|ssl_error|cert.*expired|verify failed',
     '🔐 **SSL/Sertifika Hatası**: TLS bağlantısı kurulamıyor veya sertifika geçersiz.\n\n'
     '**Çözüm:**\n'
     '- Sertifika kontrol: `openssl s_client -connect <host>:443`\n'
     '- Let\'s Encrypt yenileme: `certbot renew --force-renewal`\n'
     '- Sistem CA güncelle: `update-ca-trust` (RHEL) veya `update-ca-certificates` (Debian)'),

    # Servis Hatası
    (r'failed to start|service.*failed|systemctl.*failed|exit-code|activating.*failed',
     '⚙️ **Servis Başlatma Hatası**: Systemd servisi başlatılamadı.\n\n'
     '**Çözüm:**\n'
     '- Detaylı log: `journalctl -u <servis> -n 50 --no-pager`\n'
     '- Yapılandırma kontrol: `systemctl cat <servis>`\n'
     '- Status: `systemctl status <servis>`\n'
     '- Yeniden dene: `systemctl daemon-reload && systemctl restart <servis>`'),

    # Docker Hataları
    (r'docker.*error|container.*exit|image.*not found|docker.*denied|daemon.*not running',
     '🐳 **Docker Hatası**: Docker servisi veya container ile sorun var.\n\n'
     '**Çözüm:**\n'
     '- Docker servis durumu: `systemctl status docker`\n'
     '- Container logları: `docker logs <container>`\n'
     '- Yeniden başlat: `systemctl restart docker`\n'
     '- Temizlik: `docker system prune -af`'),

    # Paket Yönetimi
    (r'yum.*error|dnf.*error|apt.*error|dpkg.*error|rpm.*error|repository.*not found|no package',
     '📦 **Paket Yöneticisi Hatası**: Paket kurulumu/güncelleme başarısız.\n\n'
     '**Çözüm:**\n'
     '- Cache temizle: `dnf clean all` veya `apt-get clean`\n'
     '- Repo kontrol: `dnf repolist` veya `apt-get update`\n'
     '- Bağımlılık onar: `dnf install -f` veya `apt --fix-broken install`'),

    # SELinux
    (r'selinux|avc.*denied|scontext|tcontext|sestatus',
     '🛡️ **SELinux Engeli**: İşlem SELinux politikası tarafından engellendi.\n\n'
     '**Çözüm:**\n'
     '- Durum kontrol: `sestatus` ve `getenforce`\n'
     '- Son engeller: `ausearch -m avc -ts recent`\n'
     '- İzin ver: `setsebool -P <boolean> on`\n'
     '- Port ekle: `semanage port -a -t http_port_t -p tcp <port>`'),
]

COMMAND_EXPLANATIONS = {
    'top': '📊 **top**: Gerçek zamanlı CPU, RAM ve süreç kullanımını gösterir.\n- `q` ile çık\n- `M` bellek sırala, `P` CPU sırala\n- `k` ile PID girerek süreç sonlandır',
    'htop': '📊 **htop**: top\'un gelişmiş versiyonu — renkli, etkileşimli süreç yöneticisi.',
    'df': '💾 **df**: Disk dosya sistemi kullanımını gösterir.\n- `-h` okunabilir boyutlar\n- `-T` dosya sistemi tipini göster\n- `-i` inode kullanımı',
    'du': '💾 **du**: Klasör/dosya boyutlarını gösterir.\n- `-sh *` mevcut dizindeki boyutlar\n- `-sh /* | sort -rh | head` en büyük klasörler',
    'free': '🧠 **free**: RAM ve swap kullanımını gösterir.\n- `-h` okunabilir\n- `available` sütunu asıl kullanılabilir bellek',
    'ps': '⚙️ **ps**: Çalışan süreçleri listeler.\n- `ps aux` tüm süreçler\n- `--sort=-%cpu` CPU sırala\n- `--sort=-%mem` RAM sırala',
    'netstat': '🌐 **netstat**: Ağ bağlantılarını ve portları gösterir.\n- `-tlnp` dinleyen TCP portları\n- `-anp` tüm bağlantılar',
    'ss': '🌐 **ss**: netstat\'ın modern alternatifi.\n- `-tlnp` dinleyen portlar\n- `-s` istatistik özeti',
    'systemctl': '⚙️ **systemctl**: Systemd servis yönetimi.\n- `status <srv>` durum\n- `restart <srv>` yeniden başlat\n- `enable <srv>` açılışta başlat\n- `list-units --type=service` tüm servisler',
    'journalctl': '📋 **journalctl**: Systemd log görüntüleyici.\n- `-u <srv>` servis logu\n- `-f` canlı takip\n- `-n 50` son 50 satır\n- `--since "1 hour ago"` zaman filtresi',
    'docker': '🐳 **docker**: Container yönetimi.\n- `docker ps` çalışan container\'lar\n- `docker logs <c>` loglar\n- `docker exec -it <c> bash` shell aç\n- `docker system prune -af` temizlik',
    'nginx': '🌐 **nginx**: Web sunucusu / reverse proxy.\n- `nginx -t` yapılandırma testi\n- `nginx -s reload` yeniden yükle\n- Config: `/etc/nginx/`',
    'firewall-cmd': '🔥 **firewall-cmd**: Firewalld yönetimi.\n- `--list-all` tüm kurallar\n- `--add-port=80/tcp --permanent` port aç\n- `--reload` kuralları uygula',
    'tail': '📋 **tail**: Dosya sonunu gösterir.\n- `-f` canlı takip\n- `-n 100` son 100 satır\n- `-F` dosya yeniden oluşturulursa da takip et',
    'grep': '🔍 **grep**: Metin arama.\n- `-r` dizinde recursive ara\n- `-i` büyük/küçük harf duyarsız\n- `-n` satır numarası göster\n- `-c` eşleşme sayısı',
    'find': '🔍 **find**: Dosya arama.\n- `-name "*.log"` isme göre\n- `-size +100M` boyuta göre\n- `-mtime -7` son 7 gün değişen\n- `-exec rm {} \\;` bulunanları sil',
    'chmod': '🔒 **chmod**: Dosya izinleri.\n- `755` rwxr-xr-x\n- `644` rw-r--r--\n- `-R` recursive\n- `+x` çalıştırılabilir yap',
    'chown': '🔒 **chown**: Dosya sahipliği.\n- `user:group dosya`\n- `-R` recursive\n- Örnek: `chown -R nginx:nginx /var/www`',
    'curl': '🌐 **curl**: HTTP istemcisi.\n- `-I` sadece header\n- `-o dosya` kaydet\n- `-X POST` metod\n- `-H "Content-Type: application/json"` header',
    'wget': '🌐 **wget**: Dosya indirici.\n- `-O dosya` farklı isimle kaydet\n- `-q` sessiz\n- `-r` recursive indir',
    'tar': '📦 **tar**: Arşiv yönetimi.\n- `-czf arsiv.tar.gz klasor/` oluştur\n- `-xzf arsiv.tar.gz` aç\n- `-tf arsiv.tar.gz` içeriği listele',
    'crontab': '⏰ **crontab**: Zamanlanmış görevler.\n- `-e` düzenle\n- `-l` listele\n- Format: `dakika saat gün ay haftaGünü komut`\n- Örnek: `0 */6 * * * /opt/backup.sh`',
}

OPTIMIZATION_TIPS = {
    'cpu': [
        '🔧 **CPU Optimizasyonu:**',
        '- En çok CPU kullanan süreçler: `ps aux --sort=-%cpu | head -10`',
        '- nice/renice ile öncelik ayarla: `renice -n 10 -p <PID>`',
        '- Gereksiz servisleri kapat: `systemctl disable --now <srv>`',
        '- CPU governor: `cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor`',
    ],
    'memory': [
        '🧠 **Bellek Optimizasyonu:**',
        '- Swap ekle: `fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`',
        '- OOM skoru ayarla: `echo -1000 > /proc/<PID>/oom_score_adj`',
        '- Cache temizle: `sync && echo 3 > /proc/sys/vm/drop_caches`',
        '- vm.swappiness: `sysctl vm.swappiness=10`',
    ],
    'disk': [
        '💾 **Disk Optimizasyonu:**',
        '- Büyük dosyalar: `find / -type f -size +100M -exec ls -lh {} \\; 2>/dev/null | head -20`',
        '- Eski logları temizle: `journalctl --vacuum-size=200M`',
        '- Docker temizlik: `docker system prune -af --volumes`',
        '- Paket cache temizle: `dnf clean all` veya `apt-get clean`',
    ],
    'network': [
        '🌐 **Ağ Optimizasyonu:**',
        '- Bağlantı limitleri: `sysctl net.core.somaxconn=65535`',
        '- TCP tuning: `sysctl net.ipv4.tcp_tw_reuse=1`',
        '- Açık bağlantılar: `ss -s`',
        '- Bandwidth test: `iperf3 -s` (sunucu) / `iperf3 -c <IP>` (istemci)',
    ],
    'security': [
        '🛡️ **Güvenlik Optimizasyonu:**',
        '- SSH hardening: `PermitRootLogin no`, `PasswordAuthentication no`',
        '- Fail2ban kur: MarketYi kullan veya `dnf install fail2ban`',
        '- Firewall kontrol: `firewall-cmd --list-all`',
        '- Açık portlar: `ss -tlnp`',
        '- Güncellemeleri kur: `dnf update -y`',
    ],
    'ai': [
        '🤖 **AI Sunucu Optimizasyonu:**',
        '- GPU kontrol: `nvidia-smi` veya `lspci | grep -i nvidia`',
        '- CUDA kontrol: `nvcc --version`',
        '- Ollama model listesi: `ollama list`',
        '- GPU bellek: `nvidia-smi --query-gpu=memory.free --format=csv`',
        '- SWAP artır (büyük modeller için): `swapoff -a && fallocate -l 16G /swapfile && mkswap /swapfile && swapon /swapfile`',
    ],
}

AI_QUICK_PROMPTS = [
    {"label": "Bu hatayı açıkla", "prompt": "Bu çıktıdaki hatayı açıkla ve çözüm öner"},
    {"label": "Sunucuyu optimize et", "prompt": "Sunucuyu genel olarak optimize etmek için ne yapmalıyım?"},
    {"label": "Güvenlik kontrol", "prompt": "Sunucunun güvenlik durumunu kontrol etmek için komutlar öner"},
    {"label": "Disk temizliği", "prompt": "Disk alanı açmak için ne yapabilirim?"},
    {"label": "AI için optimize et", "prompt": "Sunucuyu AI/LLM çalıştırmak için optimize et"},
    {"label": "Performans analizi", "prompt": "Sunucu performansını analiz etmek için komutlar öner"},
]


PROGRAM_KNOWLEDGE = {
    'overview': (
        '🏢 **EmareCloud Nedir?**\n\n'
        'EmareCloud; çok kiracılı (multi-tenant), rol bazlı yetkilendirme (RBAC), '
        'sunucu yönetimi, güvenlik, otomasyon ve AI modullerini tek panelde toplayan '
        'altyapı yönetim platformudur.\n\n'
        '**Ana Omurga:**\n'
        '- Kimlik ve yetki: Login + RBAC + 2FA\n'
        '- Tenant izolasyonu: Organization bazlı veri ayrımı\n'
        '- Sunucu yönetimi: SSH, terminal, monitoring, firewall, storage, VM\n'
        '- Uygulama pazarı: Hazır uygulamalar ve stack kurulumları\n'
        '- AI modulleri: maliyet, log analizi, guvenlik, wizard, optimizer\n'
        '- Token/abonelik: planlar, kota, EMARE token odeme akisları'
    ),
    'modules': (
        '🧩 **Moduller ve Sayfalar**\n\n'
        '- Dashboard: genel saglik ve sunucu ozeti\n'
        '- Market: uygulama/stack kurulumu\n'
        '- Monitoring + Metrics: kaynak takibi\n'
        '- Firewall: kural, IP engel, guvenlik tarama\n'
        '- Virtualization/Storage: VM ve depolama yonetimi\n'
        '- Organizations: tenant, uye, kota, abonelik\n'
        '- AI Suite: wizard, maliyet, log intelligence, optimizer, security'
    ),
    'security': (
        '🛡️ **Guvenlik Katmanı**\n\n'
        '- RBAC: super_admin, admin, reseller, sub_reseller, operator, read_only\n'
        '- API token auth + session auth\n'
        '- 2FA (TOTP) destegi\n'
        '- Tenant filtreleme ile org bazlı izolasyon\n'
        '- Audit log ile kritik islem izleme\n'
        '- Firewall ve komut guvenlik allowlist kontrolleri'
    ),
    'database': (
        '🗄️ **Veri ve Kalıcılık**\n\n'
        '- SQLAlchemy tabanlı model yapısı\n'
        '- Organization merkezli multi-tenant tasarım\n'
        '- Plan/Subscription/Quota tabloları ile lisans-kota yonetimi\n'
        '- Feedback, audit, token islemleri ve operasyon kayıtları DB uzerinde\n'
        '- Ortam degiskenine gore SQLite veya PostgreSQL calisma modeli'
    ),
}


def _match_platform_info(question: str, context: str = '') -> str | None:
    """Program/urun hakkındaki genel sorulara detaylı platform ozeti dondurur."""
    q = (question or '').lower()
    c = (context or '').lower()
    text = f'{q} {c}'

    ask_overview = any(k in text for k in [
        'emarecloud nedir', 'program', 'sistem', 'platform', 'ne ise yarar', 'tum detay', 'detayli anlat',
    ])
    ask_modules = any(k in text for k in ['modul', 'ozellik', 'menu', 'sayfa', 'hangi bolum'])
    ask_security = any(k in text for k in ['guvenlik', 'rbac', 'rol', 'izin', '2fa', 'tenant'])
    ask_db = any(k in text for k in ['veritabani', 'database', 'sqlite', 'postgres', 'kalici'])

    sections = []
    if ask_overview:
        sections.append(PROGRAM_KNOWLEDGE['overview'])
    if ask_modules:
        sections.append(PROGRAM_KNOWLEDGE['modules'])
    if ask_security:
        sections.append(PROGRAM_KNOWLEDGE['security'])
    if ask_db:
        sections.append(PROGRAM_KNOWLEDGE['database'])

    if not sections and any(k in text for k in ['emare', 'platform', 'panel']):
        sections = [PROGRAM_KNOWLEDGE['overview'], PROGRAM_KNOWLEDGE['modules']]

    if not sections:
        return None

    sections.append(
        '📌 **Hizli Yonlendirme**\n'
        '- "Rol bazli izinleri anlat"\n'
        '- "Organizations modulunu adim adim anlat"\n'
        '- "AI modullerini kullanim sirasina gore ozetle"\n'
        '- "Veritabani gecis stratejisini ozetle"'
    )
    return '\n\n---\n\n'.join(sections)


def _match_error(text):
    """Terminal çıktısındaki hata kalıplarını tespit eder."""
    text_lower = text.lower()
    matches = []
    for pattern, explanation in ERROR_PATTERNS:
        if re.search(pattern, text_lower):
            matches.append(explanation)
    return matches


def _match_command(question):
    """Sorulan sorudan ilgili komut açıklamasını bulur."""
    q_lower = question.lower().strip()
    for cmd, explanation in COMMAND_EXPLANATIONS.items():
        if cmd in q_lower:
            return explanation
    return None


def _match_optimization(question):
    """Optimizasyon sorusuna uygun tavsiyeleri döndürür."""
    q_lower = question.lower()
    tips = []

    keyword_map = {
        'cpu': ['cpu', 'işlemci', 'yavaş', 'slow', 'performance', 'performans'],
        'memory': ['ram', 'bellek', 'memory', 'oom', 'swap', 'hafıza'],
        'disk': ['disk', 'alan', 'space', 'temizle', 'clean', 'storage', 'dolu'],
        'network': ['ağ', 'network', 'bağlantı', 'port', 'bandwidth', 'internet'],
        'security': ['güvenlik', 'security', 'firewall', 'hack', 'koruma', 'ssl', 'sertleştir'],
        'ai': ['ai', 'yapay zeka', 'gpu', 'llm', 'ollama', 'model', 'cuda'],
    }

    for category, keywords in keyword_map.items():
        if any(kw in q_lower for kw in keywords):
            tips.extend(OPTIMIZATION_TIPS[category])
            tips.append('')

    if not tips and any(w in q_lower for w in ['optimiz', 'iyileştir', 'hızlandır', 'improve', 'optimize']):
        # Genel optimizasyon
        tips.append('🔧 **Genel Sunucu Optimizasyonu:**\n')
        for cat in ['cpu', 'memory', 'disk', 'security']:
            tips.extend(OPTIMIZATION_TIPS[cat][:2])
            tips.append('')

    return '\n'.join(tips) if tips else None


def ai_analyze(question, context=''):
    """
    Ana AI analiz fonksiyonu.
    1) Gemini API ile analiz dener (anahtarlar.py üzerinden)
    2) Başarısız olursa kural tabanlı sisteme düşer

    Args:
        question: Kullanıcının sorusu
        context: Terminal çıktısının son kısmı (opsiyonel)

    Returns:
        dict: {'response': str, 'suggestions': list[str], 'model': str}
    """
    # ── Gemini ile dene ─────────────────────────────────────
    gemini_result = _gemini_analyze(question, context)
    if gemini_result:
        logger.debug("Gemini yanıtı alındı (%d karakter)", len(gemini_result['response']))
        return gemini_result

    # ── Kural tabanlı fallback ──────────────────────────────
    logger.debug("Kural tabanlı sisteme düşüldü")
    response_parts = []
    suggestions = []

    # 1) Kontekstteki hataları tespit et
    if context:
        errors = _match_error(context)
        if errors:
            response_parts.extend(errors)

    # 2) Soru içindeki hata kalıplarını kontrol et
    if question:
        q_errors = _match_error(question)
        for err in q_errors:
            if err not in response_parts:
                response_parts.append(err)

    # 3) Komut açıklaması
    cmd_explain = _match_command(question)
    if cmd_explain:
        response_parts.append(cmd_explain)

    # 4) Optimizasyon tavsiyeleri
    opt_tips = _match_optimization(question)
    if opt_tips:
        response_parts.append(opt_tips)

    # 4.5) Program/urun detay bilgisi
    platform_info = _match_platform_info(question, context)
    if platform_info:
        response_parts.append(platform_info)

    # 5) Özel soru kalıpları
    q_lower = question.lower() if question else ''

    if any(w in q_lower for w in ['log', 'günlük', 'kayıt']):
        if not response_parts:
            response_parts.append(
                '📋 **Log İnceleme Komutları:**\n'
                '- Sistem logu: `journalctl -n 100 --no-pager`\n'
                '- Servis logu: `journalctl -u <servis> -n 50`\n'
                '- Canlı takip: `journalctl -f`\n'
                '- Auth log: `tail -100 /var/log/secure`\n'
                '- Nginx log: `tail -100 /var/log/nginx/error.log`'
            )
        suggestions.extend(['journalctl -n 50 --no-pager', 'tail -50 /var/log/messages'])

    if any(w in q_lower for w in ['yedek', 'backup', 'geri yükle', 'restore']):
        response_parts.append(
            '💾 **Yedekleme Önerileri:**\n'
            '- Market\'ten Restic veya BorgBackup kurabilirsiniz\n'
            '- Hızlı yedek: `tar -czf /tmp/backup-$(date +%Y%m%d).tar.gz /opt/ /etc/`\n'
            '- Veritabanı: `mysqldump -u root -p --all-databases > /tmp/db-backup.sql`\n'
            '- Otomatik: crontab\'a ekleyin'
        )

    if any(w in q_lower for w in ['servis', 'service', 'çalışan', 'başlat', 'durdur']):
        if not cmd_explain:
            response_parts.append(
                '⚙️ **Servis Yönetimi:**\n'
                '- Tüm servisler: `systemctl list-units --type=service --state=running`\n'
                '- Durum kontrol: `systemctl status <servis>`\n'
                '- Başlat: `systemctl start <servis>`\n'
                '- Durdur: `systemctl stop <servis>`\n'
                '- Yeniden başlat: `systemctl restart <servis>`'
            )
        suggestions.extend(['systemctl list-units --type=service --state=running'])

    if any(w in q_lower for w in ['kim bağlı', 'oturum', 'login', 'giriş', 'who']):
        response_parts.append(
            '👥 **Bağlı Kullanıcılar:**\n'
            '- Şu an bağlı: `who` veya `w`\n'
            '- Son girişler: `last -20`\n'
            '- Başarısız girişler: `lastb -20 2>/dev/null || journalctl -u sshd | grep Failed | tail -20`'
        )
        suggestions.extend(['who', 'last -10'])

    # 6) Hiçbir eşleşme yoksa genel yardım
    if not response_parts:
        response_parts.append(
            '🤖 **EmareCloud AI Asistan**\n\n'
            'Size şu konularda yardımcı olabilirim:\n\n'
            '- 🔴 **Hata açıklama**: Terminaldeki hata mesajını yapıştırın\n'
            '- ⚙️ **Komut açıklama**: Bir komutun ne yaptığını sorun\n'
            '- 🔧 **Optimizasyon**: "CPU optimize et", "disk temizle" gibi sorular\n'
            '- 🛡️ **Güvenlik**: "güvenlik kontrol", "firewall ayarla"\n'
            '- 🤖 **AI Kurulum**: "sunucuyu AI için hazırla"\n'
            '- 📋 **Log analiz**: "logları incele", "hata ara"\n\n'
            '💡 **İpucu**: Terminal çıktısıyla birlikte sorun, daha doğru yanıt alırsınız!'
        )
        suggestions.extend([
            'uptime && free -h && df -h',
            'systemctl list-units --type=service --state=failed',
            'journalctl -p err -n 20 --no-pager',
        ])

    # Komut önerileri ekle (eğer henüz yoksa)
    if context and not suggestions:
        # Bağlama göre takip komutları öner
        ctx_lower = context.lower()
        if 'nginx' in ctx_lower:
            suggestions.append('nginx -t && systemctl reload nginx')
        if 'docker' in ctx_lower:
            suggestions.append('docker ps -a && docker system df')
        if 'mysql' in ctx_lower or 'mariadb' in ctx_lower:
            suggestions.append('mysqladmin status')
        if 'failed' in ctx_lower:
            suggestions.append('systemctl list-units --state=failed')

    return {
        'response': '\n\n---\n\n'.join(response_parts),
        'suggestions': suggestions[:5],
        'model': 'rule-based',
    }


def get_quick_prompts():
    """Hazır soru şablonlarını döndürür."""
    return AI_QUICK_PROMPTS
