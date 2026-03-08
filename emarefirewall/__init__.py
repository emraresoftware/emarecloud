"""
EmareFirewall — Bağımsız Güvenlik Duvarı Yönetim Paketi
========================================================

Herhangi bir Flask uygulamasına veya CLI'dan bağımsız kullanılabilir.
UFW (Ubuntu/Debian) ve firewalld (RHEL/CentOS/AlmaLinux) destekler.

Kullanım (Standalone):
    from emarefirewall import FirewallManager
    fw = FirewallManager(ssh_executor=my_ssh_func)
    status = fw.get_status("server1")

Kullanım (Flask):
    from emarefirewall.routes import create_blueprint
    bp = create_blueprint(ssh_executor=my_ssh_func)
    app.register_blueprint(bp)

Kullanım (CLI):
    python -m emarefirewall status --host 1.2.3.4 --user root
"""

__version__ = "1.0.0"
__author__ = "Emare Collective"

from emarefirewall.manager import FirewallManager

__all__ = ["FirewallManager", "__version__"]
