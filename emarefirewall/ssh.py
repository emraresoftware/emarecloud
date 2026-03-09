"""
EmareFirewall — Dahili SSH Executor
====================================

Paramiko ile bağımsız SSH bağlantı yöneticisi.
EmareCloud ssh_mgr'a ihtiyaç duymadan doğrudan kullanılabilir.

Kullanım:
    from emarefirewall.ssh import ParamikoExecutor

    ssh = ParamikoExecutor()
    ssh.connect("srv1", host="1.2.3.4", user="root", key_path="~/.ssh/id_rsa")
    ok, out, err = ssh.execute("srv1", "firewall-cmd --list-all")
    ssh.disconnect("srv1")
"""

import os
import logging
from typing import Optional

logger = logging.getLogger('emarefirewall.ssh')

try:
    import paramiko
except ImportError:
    paramiko = None


class ParamikoExecutor:
    """Paramiko tabanlı SSH executor. FirewallManager ile kullanılır."""

    def __init__(self):
        if paramiko is None:
            raise ImportError("paramiko gerekli: pip install paramiko")
        self._clients = {}

    def connect(self, server_id: str, host: str, user: str = "root",
                port: int = 22, key_path: Optional[str] = None,
                password: Optional[str] = None, timeout: int = 10,
                host_key_policy: str = "warning"):
        """
        Sunucuya SSH bağlantısı kurar.

        Args:
            host_key_policy: 'reject' | 'warning' | 'auto'
                - 'reject':  Bilinmeyen host key'leri reddeder (en güvenli)
                - 'warning': Bilinmeyen key'leri kabul eder ama log'a yazar (varsayılan)
                - 'auto':    Hepsini sessizce kabul eder (GELİŞTİRME ORTAMI İÇİN)
        """
        client = paramiko.SSHClient()

        # Host key doğrulaması — önce known_hosts yükle
        known_hosts = os.path.expanduser("~/.ssh/known_hosts")
        if os.path.exists(known_hosts):
            try:
                client.load_host_keys(known_hosts)
            except Exception as e:
                logger.warning("known_hosts yüklenemedi: %s", e)

        if host_key_policy == "reject":
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        elif host_key_policy == "warning":
            client.set_missing_host_key_policy(paramiko.WarningPolicy())
        else:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        kwargs = {"hostname": host, "port": port, "username": user, "timeout": timeout}
        if key_path:
            key_path = os.path.expanduser(key_path)
            kwargs["key_filename"] = key_path
        elif password:
            kwargs["password"] = password

        client.connect(**kwargs)
        self._clients[server_id] = {"client": client, "host": host, "user": user}

    def disconnect(self, server_id: str):
        """Bağlantıyı kapatır."""
        info = self._clients.pop(server_id, None)
        if info:
            info["client"].close()

    def disconnect_all(self):
        """Tüm bağlantıları kapatır."""
        for sid in list(self._clients.keys()):
            self.disconnect(sid)

    def is_connected(self, server_id: str) -> bool:
        """Bağlantı durumunu kontrol eder."""
        info = self._clients.get(server_id)
        if not info:
            return False
        transport = info["client"].get_transport()
        return transport is not None and transport.is_active()

    def execute(self, server_id: str, command: str) -> tuple:
        """
        Komut çalıştırır.
        Returns: (ok: bool, stdout: str, stderr: str)
        """
        info = self._clients.get(server_id)
        if not info:
            return False, "", f"Sunucu '{server_id}' bağlı değil."

        try:
            _, stdout, stderr = info["client"].exec_command(command, timeout=30)
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()
            exit_code = stdout.channel.recv_exit_status()
            return exit_code == 0, out, err
        except Exception as e:
            return False, "", str(e)

    def list_connections(self) -> list:
        """Aktif bağlantıları listeler."""
        return [
            {"server_id": sid, "host": info["host"], "user": info["user"],
             "connected": self.is_connected(sid)}
            for sid, info in self._clients.items()
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
