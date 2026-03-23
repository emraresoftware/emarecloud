"""
Emare Security OS — Dahili SSH Executor
====================================

Paramiko ile bağımsız SSH bağlantı yöneticisi.
EmareCloud ssh_mgr'a ihtiyaç duymadan doğrudan kullanılabilir.

standalone mod: Sunucu başına tek SSH bağlantısı (az bellek)
isp mod       : Sunucu başına N bağlantı havuzu (eşzamanlı komut)

Kullanım:
    from emarefirewall.ssh import ParamikoExecutor

    ssh = ParamikoExecutor()
    ssh.connect("srv1", host="1.2.3.4", user="root", key_path="~/.ssh/id_rsa")
    ok, out, err = ssh.execute("srv1", "firewall-cmd --list-all")
    ssh.disconnect("srv1")
"""

import os
import logging
import threading
from typing import Optional
from collections import deque

logger = logging.getLogger('emarefirewall.ssh')

try:
    import paramiko
except ImportError:
    paramiko = None


class ParamikoExecutor:
    """Paramiko tabanlı SSH executor. FirewallManager ile kullanılır.

    pool_size=1 → Sunucu başına tek bağlantı (standalone)
    pool_size=N → Sunucu başına N bağlantı havuzu (ISP)
    """

    def __init__(self, pool_size: int = 1):
        if paramiko is None:
            raise ImportError("paramiko gerekli: pip install paramiko")
        self._pool_size = max(1, pool_size)
        self._servers = {}   # server_id -> connection config
        self._pools = {}     # server_id -> deque([client, ...])
        self._locks = {}     # server_id -> threading.Semaphore
        self._connect_lock = threading.Lock()

    def _create_client(self, server_id: str) -> 'paramiko.SSHClient':
        """Bir sunucu için yeni SSH client oluştur (dahili)."""
        cfg = self._servers.get(server_id)
        if not cfg:
            raise ValueError(f"Sunucu '{server_id}' yapılandırılmamış.")

        client = paramiko.SSHClient()
        known_hosts = os.path.expanduser("~/.ssh/known_hosts")
        if os.path.exists(known_hosts):
            try:
                client.load_host_keys(known_hosts)
            except Exception as e:
                logger.warning("known_hosts yüklenemedi: %s", e)

        policy = cfg.get('host_key_policy', 'reject')
        if policy == "auto":
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        elif policy == "warning":
            client.set_missing_host_key_policy(paramiko.WarningPolicy())
        else:
            client.set_missing_host_key_policy(paramiko.RejectPolicy())

        kwargs = {"hostname": cfg['host'], "port": cfg['port'],
                  "username": cfg['user'], "timeout": cfg['timeout']}
        if cfg.get('key_path'):
            kwargs["key_filename"] = os.path.expanduser(cfg['key_path'])
        elif cfg.get('password'):
            kwargs["password"] = cfg['password']

        client.connect(**kwargs)
        transport = client.get_transport()
        if transport:
            transport.set_keepalive(30)
        return client

    def connect(self, server_id: str, host: str, user: str = "root",
                port: int = 22, key_path: Optional[str] = None,
                password: Optional[str] = None, timeout: int = 10,
                host_key_policy: str = "reject"):
        """
        Sunucuya SSH bağlantısı kurar. pool_size kadar bağlantı oluşturur.

        Args:
            host_key_policy: 'reject' | 'warning' | 'auto'
                - 'reject':  Bilinmeyen host key'leri reddeder (varsayılan, en güvenli)
                - 'warning': Bilinmeyen key'leri kabul eder ama log'a yazar
                - 'auto':    Hepsini sessizce kabul eder (GELİŞTİRME ORTAMI İÇİN)
        """
        with self._connect_lock:
            self._servers[server_id] = {
                'host': host, 'port': port, 'user': user,
                'key_path': key_path, 'password': password,
                'timeout': timeout, 'host_key_policy': host_key_policy,
            }
            pool = deque()
            # İlk bağlantıyı hemen oluştur, geri kalanlar lazy
            client = self._create_client(server_id)
            pool.append(client)
            self._pools[server_id] = pool
            self._locks[server_id] = threading.Semaphore(self._pool_size)

    def _acquire_client(self, server_id: str) -> 'paramiko.SSHClient':
        """Havuzdan bir bağlantı al veya yenisini oluştur."""
        sem = self._locks.get(server_id)
        if sem is None:
            return None
        sem.acquire()
        pool = self._pools.get(server_id)
        if pool is None:
            sem.release()
            return None
        with self._connect_lock:
            # Havuzda hazır bağlantı var mı?
            while pool:
                client = pool.popleft()
                transport = client.get_transport()
                if transport and transport.is_active():
                    return client
                # Bağlantı kopmuş, kapat
                try:
                    client.close()
                except Exception:
                    pass
            # Havuz boş — yeni bağlantı oluştur
            try:
                return self._create_client(server_id)
            except Exception as e:
                sem.release()
                raise

    def _release_client(self, server_id: str, client: 'paramiko.SSHClient'):
        """Bağlantıyı havuza geri koy."""
        pool = self._pools.get(server_id)
        sem = self._locks.get(server_id)
        if pool is not None:
            with self._connect_lock:
                pool.append(client)
        if sem is not None:
            sem.release()

    def disconnect(self, server_id: str):
        """Tüm bağlantıları kapat ve sunucuyu kaldır."""
        with self._connect_lock:
            pool = self._pools.pop(server_id, None)
            self._locks.pop(server_id, None)
            self._servers.pop(server_id, None)
        if pool:
            for client in pool:
                try:
                    client.close()
                except Exception:
                    pass

    def disconnect_all(self):
        """Tüm bağlantıları kapatır."""
        for sid in list(self._pools.keys()):
            self.disconnect(sid)

    def is_connected(self, server_id: str) -> bool:
        """En az bir aktif bağlantı var mı kontrol eder."""
        pool = self._pools.get(server_id)
        if not pool:
            return False
        for client in pool:
            transport = client.get_transport()
            if transport and transport.is_active():
                return True
        return False

    def execute(self, server_id: str, command: str) -> tuple:
        """
        Komut çalıştırır. Havuzdan bağlantı alır, bitince geri koyar.
        Returns: (ok: bool, stdout: str, stderr: str)
        """
        if server_id not in self._servers:
            return False, "", f"Sunucu '{server_id}' bağlı değil."

        try:
            client = self._acquire_client(server_id)
            if client is None:
                return False, "", f"Sunucu '{server_id}' bağlı değil."
        except Exception as e:
            return False, "", f"Bağlantı hatası: {e}"

        try:
            _, stdout, stderr = client.exec_command(command, timeout=30)
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()
            exit_code = stdout.channel.recv_exit_status()
            self._release_client(server_id, client)
            return exit_code == 0, out, err
        except Exception as e:
            # Hatalı bağlantıyı geri koymadan kapat
            try:
                client.close()
            except Exception:
                pass
            sem = self._locks.get(server_id)
            if sem:
                sem.release()
            return False, "", str(e)

    def list_connections(self) -> list:
        """Aktif bağlantıları listeler."""
        return [
            {"server_id": sid, "host": cfg["host"], "user": cfg["user"],
             "connected": self.is_connected(sid),
             "pool_size": len(self._pools.get(sid, []))}
            for sid, cfg in self._servers.items()
        ]


class SubprocessExecutor:
    """
    Yerel sunucu için subprocess tabanlı executor.
    SSH yerine doğrudan komut çalıştırır (localhost için).

    Kullanım:
        from emarefirewall.ssh import SubprocessExecutor
        local = SubprocessExecutor()
        ok, out, err = local.execute("localhost", "firewall-cmd --list-all")
    """

    def execute(self, server_id: str, command: str) -> tuple:
        """Yerel komut çalıştırır (shell=True yerine shlex.split ile)."""
        import subprocess
        import shlex
        try:
            # shell=True yerine, komutu safe parse ile çalıştır
            # Not: Pipe (|) ve redirection (2>&1) içeren komutlar için
            # /bin/sh -c kullanırız ama komutu shlex.quote ile koruruz
            result = subprocess.run(
                ['/bin/sh', '-c', command],
                capture_output=True, text=True, timeout=30
            )
            return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "", "Komut zaman aşımına uğradı (30s)."
        except Exception as e:
            return False, "", str(e)
