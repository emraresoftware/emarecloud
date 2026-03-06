"""
EmareCloud — Route Blueprint'leri
Tüm blueprint'leri topluca kaydeden register fonksiyonu.
"""


def register_blueprints(app):
    """Tüm blueprint'leri uygulamaya kaydeder."""
    from auth_routes import auth_bp
    from routes.commands import commands_bp
    from routes.firewall import firewall_bp
    from routes.market import market_bp
    from routes.metrics import metrics_bp
    from routes.monitoring import monitoring_bp
    from routes.organizations import org_bp
    from routes.pages import pages_bp
    from routes.servers import servers_bp
    from routes.storage import storage_bp
    from routes.terminal import terminal_bp
    from routes.token import token_bp
    from routes.virtualization import vms_bp
    from routes.cloudflare import cloudflare_bp
    from routes.datacenters import dc_bp
    from routes.scoreboard import scoreboard_bp
    from routes.ide import ide_bp
    from routes.feedback import feedback_bp
    from routes.webdizayn import webdizayn_bp

    blueprints = [
        auth_bp,
        pages_bp,
        servers_bp,
        metrics_bp,
        firewall_bp,
        vms_bp,
        commands_bp,
        storage_bp,
        market_bp,
        terminal_bp,
        monitoring_bp,
        org_bp,
        token_bp,
        cloudflare_bp,
        dc_bp,
        scoreboard_bp,
        ide_bp,
        feedback_bp,
        webdizayn_bp,
    ]

    for bp in blueprints:
        app.register_blueprint(bp)
