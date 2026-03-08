"""
SSH Bağlantı Yöneticisi
Sunuculara SSH üzerinden bağlanıp komut çalıştırma ve bilgi toplama.
İlk parola girişinden sonra SSH key pair üretip sunucuya yükler,
sonraki bağlantılarda key ile otomatik bağlanır.
"""

import io
import logging
import os
import socket
import threading
import time

import paramiko

logger = logging.getLogger('emarecloud.ssh')

# Uygulama SSH key pair'inin saklandığı dizin
_SSH_KEY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', '.ssh')
_SSH_PRIVATE_KEY = os.path.join(_SSH_KEY_DIR, 'emarecloud_rsa')
_SSH_PUBLIC_KEY = os.path.join(_SSH_KEY_DIR, 'emarecloud_rsa.pub')


def _ensure_app_keypair() -> tuple[paramiko.RSAKey, str]:
    """EmareCloud uygulama SSH key pair'ini döndürür. Yoksa oluşturur.

    Returns:
        (private_key_obj, public_key_str)
    """
    os.makedirs(_SSH_KEY_DIR, mode=0o700, exist_ok=True)

    if os.path.exists(_SSH_PRIVATE_KEY):
        pkey = paramiko.RSAKey.from_private_key_file(_SSH_PRIVATE_KEY)
        pub_str = f"ssh-rsa {pkey.get_base64()} emarecloud@panel"
        # Public key dosyası yoksa yeniden yaz
        if not os.path.exists(_SSH_PUBLIC_KEY):
            with open(_SSH_PUBLIC_KEY, 'w') as f:
                f.write(pub_str + '\n')
            os.chmod(_SSH_PUBLIC_KEY, 0o644)
        return pkey, pub_str

    # Yeni 4096 bit RSA key pair üret
    logger.info("🔑 SSH key pair üretiliyor (RSA 4096)...")
    pkey = paramiko.RSAKey.generate(4096)
    pkey.write_private_key_file(_SSH_PRIVATE_KEY)
    os.chmod(_SSH_PRIVATE_KEY, 0o600)

    pub_str = f"ssh-rsa {pkey.get_base64()} emarecloud@panel"
    with open(_SSH_PUBLIC_KEY, 'w') as f:
        f.write(pub_str + '\n')
    os.chmod(_SSH_PUBLIC_KEY, 0o644)

    logger.info("✅ SSH key pair oluşturuldu: %s", _SSH_PRIVATE_KEY)
    return pkey, pub_str


def _deploy_key_to_server(client: paramiko.SSHClient, pub_key: str) -> bool:
    """Bağlı SSH client üzerinden public key'i sunucuya yükler.

    authorized_keys'e zaten varsa tekrar eklemez.
    """
    try:
        # ~/.ssh dizinini oluştur ve izinleri ayarla
        setup_cmds = (
            'mkdir -p ~/.ssh && chmod 700 ~/.ssh && '
            'touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
        )
        client.exec_command(setup_cmds, timeout=10)
        time.sleep(0.3)

        # Zaten yüklü mü kontrol et
        marker = pub_key.split()[1][:40]  # base64'ün ilk 40 karakteri
        _, stdout, _ = client.exec_command(
            f'grep -c "{marker}" ~/.ssh/authorized_keys 2>/dev/null || echo 0',
            timeout=10,
        )
        count = stdout.read().decode().strip()
        if count != '0':
            logger.debug("🔑 SSH key zaten sunucuda mevcut")
            return True

        # Key'i ekle
        escaped = pub_key.replace('"', '\\"')
        _, stdout, stderr = client.exec_command(
            f'echo "{escaped}" >> ~/.ssh/authorized_keys',
            timeout=10,
        )
        err = stderr.read().decode().strip()
        if err:
            logger.warning("SSH key yükleme stderr: %s", err)
            return False

        logger.info("✅ SSH key sunucuya yüklendi")
        return True
    except Exception as e:
        logger.warning("SSH key yükleme hatası: %s", e)
        return False


class SSHManager:
    """SSH bağlantılarını yönetir. İlk bağlantıda parola ile girer,
    SSH key'i otomatik yükler ve sonraki bağlantılarda key kullanır."""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self._connections: dict[str, paramiko.SSHClient] = {}
        self._lock = threading.Lock()
        self._last_check: dict[str, float] = {}  # son bağlantı kontrolü zamanı
        self._CHECK_INTERVAL = 5  # saniye — is_connected kontrolü minimum aralığı
        self._last_check_result: dict[str, bool] = {}  # son kontrol sonucu cache
        # Key pair'i uygulama başlangıcında hazırla
        try:
            self._app_key, self._app_pub = _ensure_app_keypair()
        except Exception as e:
            logger.error("SSH key pair oluşturulamadı: %s", e)
            self._app_key = None
            self._app_pub = None

    # ── Key-deployed takibi (sunucu DB alanı ile senkron) ──
    _key_deployed: set[str] = set()  # server_id'ler

    def _try_key_connect(self, host: str, port: int,
                         username: str) -> paramiko.SSHClient | None:
        """SSH key ile bağlanmayı dener. Başarısızsa None döner."""
        if not self._app_key:
            return None
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=host,
                port=port,
                username=username,
                pkey=self._app_key,
                timeout=self.timeout,
                allow_agent=False,
                look_for_keys=False,
                banner_timeout=30,
                auth_timeout=30,
            )
            return client
        except Exception:
            return None

    def connect(self, server_id: str, host: str, port: int,
                username: str, password: str,
                ssh_key_pem: str | None = None) -> tuple[bool, str]:
        """Sunucuya SSH bağlantısı kurar.

        Öncelik sırası:
        1. Uygulama SSH key ile bağlan (daha önce deploy edildiyse)
        2. Sunucuya özel ssh_key_pem varsa onunla bağlan
        3. Parola ile bağlan → ardından SSH key'i otomatik deploy et
        """
        host = (host or "").strip()
        if not host:
            return False, "Host adresi boş"
        try:
            port = int(port) if port is not None else 22
        except (TypeError, ValueError):
            port = 22
        if not (1 <= port <= 65535):
            port = 22
        username = (username or "").strip() or "root"
        password = password if password is not None else ""

        client = None
        auth_method = None

        try:
            # ── 1) Uygulama key ile dene ──
            if self._app_key and server_id in self._key_deployed:
                client = self._try_key_connect(host, port, username)
                if client:
                    auth_method = 'app_key'

            # ── 2) Sunucuya özel PEM key ile dene ──
            if not client and ssh_key_pem:
                try:
                    pkey = paramiko.RSAKey.from_private_key(io.StringIO(ssh_key_pem))
                    c = paramiko.SSHClient()
                    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    c.connect(
                        hostname=host, port=port, username=username,
                        pkey=pkey, timeout=self.timeout,
                        allow_agent=False, look_for_keys=False,
                        banner_timeout=30, auth_timeout=30,
                    )
                    client = c
                    auth_method = 'server_key'
                except Exception:
                    pass

            # ── 3) Uygulama key ile dene (ilk sefer — key_deployed set'inde yok ama sunucuda olabilir) ──
            if not client and self._app_key and server_id not in self._key_deployed:
                client = self._try_key_connect(host, port, username)
                if client:
                    auth_method = 'app_key'
                    self._key_deployed.add(server_id)

            # ── 4) Parola ile bağlan ──
            if not client:
                c = paramiko.SSHClient()
                c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                c.connect(
                    hostname=host,
                    port=port,
                    username=username,
                    password=password,
                    timeout=self.timeout,
                    allow_agent=False,
                    look_for_keys=False,
                    banner_timeout=30,
                    auth_timeout=30,
                )
                client = c
                auth_method = 'password'

            # ── Bağlantı havuzuna ekle ──
            with self._lock:
                if server_id in self._connections:
                    try:
                        self._connections[server_id].close()
                    except Exception:
                        pass
                self._connections[server_id] = client

            # ── Parola ile bağlandıysa key deploy et ──
            if auth_method == 'password' and self._app_pub:
                deployed = _deploy_key_to_server(client, self._app_pub)
                if deployed:
                    self._key_deployed.add(server_id)
                    logger.info("🔑 Sunucu %s: SSH key yüklendi, sonraki bağlantılarda parola gerekmeyecek", server_id)

            method_labels = {
                'app_key': '🔑 SSH key ile bağlandı (parolasız)',
                'server_key': '🔑 Özel SSH key ile bağlandı',
                'password': '🔐 Parola ile bağlandı',
            }
            msg = method_labels.get(auth_method, 'Bağlantı başarılı')
            return True, msg

        except paramiko.AuthenticationException as e:
            return False, f"Kimlik doğrulama hatası: {str(e) or 'Kullanıcı adı veya şifre yanlış'}"
        except paramiko.SSHException as e:
            return False, f"SSH hatası: {str(e)}"
        except TimeoutError:
            return False, "Bağlantı zaman aşımına uğradı (sunucu yanıt vermiyor)"
        except socket.gaierror as e:
            return False, f"Host bulunamadı: {host} ({str(e)})"
        except OSError as e:
            err = str(e)
            if "Connection refused" in err or "Bağlantı reddedildi" in err:
                return False, f"Bağlantı reddedildi. SSH servisi {host}:{port} üzerinde çalışıyor mu?"
            if "timed out" in err.lower() or "timeout" in err.lower():
                return False, "Bağlantı zaman aşımı. Ağ erişimi veya güvenlik duvarı kontrol edin."
            return False, f"Ağ hatası: {err}"
        except Exception as e:
            return False, f"Hata: {type(e).__name__}: {str(e)}"

    def disconnect(self, server_id: str):
        """Sunucu bağlantısını kapatır."""
        with self._lock:
            if server_id in self._connections:
                try:
                    self._connections[server_id].close()
                except Exception:
                    pass
                del self._connections[server_id]
            # Cache'i temizle
            self._last_check.pop(server_id, None)
            self._last_check_result.pop(server_id, None)

    def is_connected(self, server_id: str) -> bool:
        """Bağlantı durumunu kontrol eder — cache ile optimize."""
        now = time.time()
        # Son kontrolden bu yana yeterli zaman geçmediyse cache'den dön
        last = self._last_check.get(server_id, 0)
        if (now - last) < self._CHECK_INTERVAL and server_id in self._last_check_result:
            return self._last_check_result[server_id]

        with self._lock:
            if server_id not in self._connections:
                self._last_check_result[server_id] = False
                self._last_check[server_id] = now
                return False
            try:
                transport = self._connections[server_id].get_transport()
                if transport and transport.is_active():
                    transport.send_ignore()
                    self._last_check_result[server_id] = True
                    self._last_check[server_id] = now
                    return True
                self._last_check_result[server_id] = False
                self._last_check[server_id] = now
                return False
            except Exception:
                self._last_check_result[server_id] = False
                self._last_check[server_id] = now
                return False

    def execute_command(self, server_id: str, command: str,
                        timeout: int = 30) -> tuple[bool, str, str]:
        """Sunucuda komut çalıştırır. (başarı, stdout, stderr) döndürür."""
        if not self.is_connected(server_id):
            return False, "", "Sunucu bağlı değil"
        try:
            client = self._connections[server_id]
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode('utf-8', errors='replace')
            err = stderr.read().decode('utf-8', errors='replace')
            exit_code = stdout.channel.recv_exit_status()
            return exit_code == 0, out, err
        except Exception as e:
            return False, "", f"Komut çalıştırma hatası: {str(e)}"

    def check_server_reachable(self, host: str, port: int = 22) -> tuple[bool, float]:
        """Sunucunun SSH portu erişilebilir mi kontrol eder.

        connect_ex() başarılı olsa bile SSH banner okuyarak gerçek bir SSH
        servisi çalıştığını doğrular. Bu sayede port açık ama SSH olmayan
        servisler veya yarı-açık bağlantılar 'online' olarak gösterilmez.
        """
        if not host or not str(host).strip():
            return False, 0.0
        host = str(host).strip()
        try:
            port = int(port) if port else 22
        except (TypeError, ValueError):
            port = 22

        sock = None
        try:
            start = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((host, port))
            elapsed = round((time.time() - start) * 1000, 2)  # ms

            if result != 0:
                return False, 0.0

            # Port açık — gerçek SSH servisi mi doğrula (banner oku)
            try:
                sock.settimeout(2)
                banner = sock.recv(64)
                # SSH sunucuları "SSH-2.0-..." veya "SSH-1.99-..." banner'ı gönderir
                if banner and b'SSH' in banner.upper():
                    return True, elapsed
                # Banner geldi ama SSH değil
                return False, 0.0
            except (TimeoutError, OSError):
                # Banner okuma timeout — port açık ama yanıt yok, güvenilmez
                return False, 0.0

        except (socket.gaierror, socket.herror):
            # DNS çözümleme hatası
            return False, 0.0
        except Exception:
            return False, 0.0
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass

    def disconnect_all(self):
        """Tüm bağlantıları kapatır."""
        with self._lock:
            for server_id in list(self._connections.keys()):
                try:
                    self._connections[server_id].close()
                except Exception:
                    pass
            self._connections.clear()

    def get_connected_count(self) -> int:
        """Aktif bağlantı sayısını döndürür. (Lock içinde is_connected çağrılmaz; deadlock önlenir.)"""
        count = 0
        with self._lock:
            for sid in list(self._connections.keys()):
                try:
                    transport = self._connections[sid].get_transport()
                    if transport and transport.is_active():
                        count += 1
                except Exception:
                    pass
        return count
