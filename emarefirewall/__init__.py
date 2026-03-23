"""
Emare Security OS — Birleşik Güvenlik Platformu
========================================================

Firewall, L7 Koruma, Ağ Analizi, RMM, ITSM, 5651 Uyumluluk.
UFW (Ubuntu/Debian), firewalld (RHEL/CentOS/AlmaLinux) ve Emare OS destekler.

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

__version__ = "1.5.0"
__author__ = "Emare Collective"

from emarefirewall.manager import FirewallManager
from emarefirewall.tenants import (
    TenantStore, DictTenantStore, WebhookDispatcher, create_tenant_store,
)
from emarefirewall.rmm import RMMStore
from emarefirewall import config as config

__all__ = ["FirewallManager", "RMMStore", "config", "__version__"]
