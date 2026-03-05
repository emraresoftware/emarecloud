"""
EmareCloud — Monitoring & Otomasyon Testleri
Alert kuralları, webhook, zamanlanmış görevler, yedekleme, metrik geçmişi.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

# ==================== ALERT MANAGER UNIT TESTS ====================

class TestAlertManager:
    """alert_manager.py birim testleri."""

    def test_extract_metric_cpu(self):
        from alert_manager import extract_metric_value
        metrics = {'cpu': {'usage_percent': 85.5}}
        assert extract_metric_value(metrics, 'cpu') == 85.5

    def test_extract_metric_memory(self):
        from alert_manager import extract_metric_value
        metrics = {'memory': {'percent': 72.3}}
        assert extract_metric_value(metrics, 'memory') == 72.3

    def test_extract_metric_disk(self):
        from alert_manager import extract_metric_value
        metrics = {'disks': [{'percent': 50}, {'percent': 90}]}
        assert extract_metric_value(metrics, 'disk') == 90

    def test_extract_metric_disk_empty(self):
        from alert_manager import extract_metric_value
        metrics = {'disks': []}
        assert extract_metric_value(metrics, 'disk') is None

    def test_extract_metric_load(self):
        from alert_manager import extract_metric_value
        metrics = {'cpu': {'load_average': ['1.5', '2.0', '3.0']}}
        assert extract_metric_value(metrics, 'load_1m') == 1.5
        assert extract_metric_value(metrics, 'load_5m') == 2.0

    def test_extract_metric_unknown(self):
        from alert_manager import extract_metric_value
        metrics = {'cpu': {'usage_percent': 50}}
        assert extract_metric_value(metrics, 'unknown_metric') is None

    def test_extract_metric_none(self):
        from alert_manager import extract_metric_value
        assert extract_metric_value(None, 'cpu') is None
        assert extract_metric_value({}, 'cpu') is None

    def test_condition_operators(self):
        from alert_manager import CONDITION_OPS
        assert CONDITION_OPS['>'](90, 80) is True
        assert CONDITION_OPS['>'](70, 80) is False
        assert CONDITION_OPS['>='](80, 80) is True
        assert CONDITION_OPS['<'](50, 80) is True
        assert CONDITION_OPS['<='](80, 80) is True
        assert CONDITION_OPS['=='](80, 80) is True
        assert CONDITION_OPS['=='](80, 81) is False

    def test_metric_labels_exist(self):
        from alert_manager import METRIC_LABELS
        assert 'cpu' in METRIC_LABELS
        assert 'memory' in METRIC_LABELS
        assert 'disk' in METRIC_LABELS


# ==================== BACKUP MANAGER UNIT TESTS ====================

class TestBackupManager:
    """backup_manager.py birim testleri."""

    def test_format_size_bytes(self):
        from backup_manager import _format_size
        assert 'B' in _format_size(500)

    def test_format_size_kb(self):
        from backup_manager import _format_size
        assert 'KB' in _format_size(2048)

    def test_format_size_mb(self):
        from backup_manager import _format_size
        assert 'MB' in _format_size(5 * 1024 * 1024)

    def test_format_size_gb(self):
        from backup_manager import _format_size
        assert 'GB' in _format_size(2 * 1024 * 1024 * 1024)

    def test_format_size_zero(self):
        from backup_manager import _format_size
        assert _format_size(0) == '0 B'

    def test_should_run_no_schedule(self):
        from backup_manager import _should_run
        profile = MagicMock()
        profile.schedule = ''
        profile.last_run = None
        assert _should_run(profile, datetime.utcnow()) is False

    def test_should_run_first_time(self):
        from backup_manager import _should_run
        profile = MagicMock()
        profile.schedule = '0 2 * * *'
        profile.last_run = None
        assert _should_run(profile, datetime.utcnow()) is True

    def test_should_run_invalid_schedule(self):
        from backup_manager import _should_run
        profile = MagicMock()
        profile.schedule = 'invalid'
        profile.last_run = datetime.utcnow() - timedelta(hours=1)  # last_run set so parse is reached
        assert _should_run(profile, datetime.utcnow()) is False

    def test_should_run_spam_prevention(self):
        from backup_manager import _should_run
        now = datetime.utcnow()
        profile = MagicMock()
        profile.schedule = f'{now.minute} {now.hour} * * *'
        profile.last_run = now - timedelta(seconds=10)
        assert _should_run(profile, now) is False


# ==================== SCHEDULER UNIT TESTS ====================

class TestScheduler:
    """scheduler.py birim testleri."""

    def test_cron_matches_valid(self):
        from scheduler import _cron_matches
        now = datetime(2026, 3, 1, 14, 30)
        assert _cron_matches('30 14 * * *', now) is True

    def test_cron_matches_wrong_minute(self):
        from scheduler import _cron_matches
        now = datetime(2026, 3, 1, 14, 30)
        assert _cron_matches('0 14 * * *', now) is False

    def test_cron_matches_wrong_hour(self):
        from scheduler import _cron_matches
        now = datetime(2026, 3, 1, 14, 30)
        assert _cron_matches('30 2 * * *', now) is False

    def test_cron_matches_wildcard(self):
        from scheduler import _cron_matches
        now = datetime(2026, 3, 1, 14, 30)
        assert _cron_matches('* * * * *', now) is True

    def test_cron_matches_empty(self):
        from scheduler import _cron_matches
        assert _cron_matches('', datetime.utcnow()) is False

    def test_cron_matches_invalid(self):
        from scheduler import _cron_matches
        assert _cron_matches('abc', datetime.utcnow()) is False

    def test_cron_matches_too_recent(self):
        from scheduler import _cron_matches
        now = datetime(2026, 3, 1, 14, 30)
        last_run = now - timedelta(seconds=30)
        assert _cron_matches('30 14 * * *', now, last_run) is False


# ==================== MONITORING API TESTS ====================

class TestMonitoringAPI:
    """Monitoring API endpoint testleri."""

    @pytest.fixture(autouse=True)
    def setup(self, app, auth_client):
        self.app = app
        self.client = auth_client

    def _csrf(self):
        with self.client.session_transaction() as sess:
            return sess.get('csrf_token', '')

    def test_list_alert_rules(self):
        r = self.client.get('/api/alerts/rules')
        assert r.status_code == 200
        d = r.get_json()
        assert d['success'] is True
        assert 'rules' in d

    def test_create_alert_rule(self):
        r = self.client.post('/api/alerts/rules',
                             data=json.dumps({
                                 'name': 'Test CPU Alert',
                                 'metric': 'cpu',
                                 'threshold': 90,
                                 'severity': 'warning',
                             }),
                             content_type='application/json')
        assert r.status_code == 201
        d = r.get_json()
        assert d['success'] is True
        assert d['rule']['name'] == 'Test CPU Alert'

    def test_create_alert_rule_missing_name(self):
        r = self.client.post('/api/alerts/rules',
                             data=json.dumps({'metric': 'cpu', 'threshold': 90}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_create_alert_rule_invalid_metric(self):
        r = self.client.post('/api/alerts/rules',
                             data=json.dumps({'name': 'Test', 'metric': 'invalid', 'threshold': 90}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_create_alert_rule_missing_threshold(self):
        r = self.client.post('/api/alerts/rules',
                             data=json.dumps({'name': 'Test', 'metric': 'cpu'}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_update_alert_rule(self):
        # Oluştur
        r = self.client.post('/api/alerts/rules',
                             data=json.dumps({'name': 'Update Test', 'metric': 'memory', 'threshold': 80}),
                             content_type='application/json')
        rule_id = r.get_json()['rule']['id']

        # Güncelle
        r = self.client.put(f'/api/alerts/rules/{rule_id}',
                            data=json.dumps({'threshold': 85}),
                            content_type='application/json')
        assert r.status_code == 200
        assert r.get_json()['rule']['threshold'] == 85

    def test_delete_alert_rule(self):
        r = self.client.post('/api/alerts/rules',
                             data=json.dumps({'name': 'Delete Test', 'metric': 'disk', 'threshold': 95}),
                             content_type='application/json')
        rule_id = r.get_json()['rule']['id']

        r = self.client.delete(f'/api/alerts/rules/{rule_id}')
        assert r.status_code == 200

    def test_delete_nonexistent_rule(self):
        r = self.client.delete('/api/alerts/rules/99999')
        assert r.status_code == 404

    def test_alert_history(self):
        r = self.client.get('/api/alerts/history')
        assert r.status_code == 200
        d = r.get_json()
        assert d['success'] is True
        assert 'alerts' in d

    def test_alert_stats(self):
        r = self.client.get('/api/alerts/stats')
        assert r.status_code == 200
        d = r.get_json()
        assert 'total' in d['stats']
        assert 'critical' in d['stats']

    def test_list_webhooks(self):
        r = self.client.get('/api/webhooks')
        assert r.status_code == 200
        d = r.get_json()
        assert d['success'] is True
        assert 'webhooks' in d

    def test_create_webhook_slack(self):
        r = self.client.post('/api/webhooks',
                             data=json.dumps({
                                 'name': 'Test Slack',
                                 'webhook_type': 'slack',
                                 'url': 'https://hooks.slack.com/test',
                             }),
                             content_type='application/json')
        assert r.status_code == 201
        d = r.get_json()
        assert d['webhook']['webhook_type'] == 'slack'

    def test_create_webhook_invalid_type(self):
        r = self.client.post('/api/webhooks',
                             data=json.dumps({'name': 'Test', 'webhook_type': 'invalid'}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_create_webhook_missing_name(self):
        r = self.client.post('/api/webhooks',
                             data=json.dumps({'webhook_type': 'slack'}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_delete_webhook(self):
        r = self.client.post('/api/webhooks',
                             data=json.dumps({'name': 'Del Test', 'webhook_type': 'discord', 'url': 'https://discord.com/test'}),
                             content_type='application/json')
        wid = r.get_json()['webhook']['id']
        r = self.client.delete(f'/api/webhooks/{wid}')
        assert r.status_code == 200

    def test_list_tasks(self):
        r = self.client.get('/api/tasks')
        assert r.status_code == 200
        d = r.get_json()
        assert d['success'] is True

    def test_create_task(self):
        r = self.client.post('/api/tasks',
                             data=json.dumps({
                                 'name': 'Test Task',
                                 'server_id': 'srv1',
                                 'command': 'ls -la /tmp',
                                 'schedule': '0 2 * * *',
                             }),
                             content_type='application/json')
        assert r.status_code == 201

    def test_create_task_missing_name(self):
        r = self.client.post('/api/tasks',
                             data=json.dumps({'server_id': 'srv1', 'command': 'ls', 'schedule': '0 2 * * *'}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_create_task_dangerous_command(self):
        r = self.client.post('/api/tasks',
                             data=json.dumps({
                                 'name': 'Bad Task',
                                 'server_id': 'srv1',
                                 'command': 'rm -rf /',
                                 'schedule': '0 2 * * *',
                             }),
                             content_type='application/json')
        assert r.status_code == 403

    def test_delete_task(self):
        r = self.client.post('/api/tasks',
                             data=json.dumps({
                                 'name': 'Del Task',
                                 'server_id': 'srv1',
                                 'command': 'echo hello',
                                 'schedule': '0 3 * * *',
                             }),
                             content_type='application/json')
        tid = r.get_json()['task']['id']
        r = self.client.delete(f'/api/tasks/{tid}')
        assert r.status_code == 200

    def test_list_backups(self):
        r = self.client.get('/api/backups')
        assert r.status_code == 200
        d = r.get_json()
        assert d['success'] is True

    def test_create_backup(self):
        r = self.client.post('/api/backups',
                             data=json.dumps({
                                 'name': 'Test Backup',
                                 'server_id': 'srv1',
                                 'source_path': '/var/www',
                                 'dest_path': '/backups',
                             }),
                             content_type='application/json')
        assert r.status_code == 201
        d = r.get_json()
        assert d['backup']['compression'] == 'gzip'

    def test_create_backup_missing_fields(self):
        r = self.client.post('/api/backups',
                             data=json.dumps({'name': 'Test'}),
                             content_type='application/json')
        assert r.status_code == 400

    def test_delete_backup(self):
        r = self.client.post('/api/backups',
                             data=json.dumps({
                                 'name': 'Del Backup',
                                 'server_id': 'srv1',
                                 'source_path': '/data',
                                 'dest_path': '/backups',
                             }),
                             content_type='application/json')
        bid = r.get_json()['backup']['id']
        r = self.client.delete(f'/api/backups/{bid}')
        assert r.status_code == 200

    def test_metric_history(self):
        r = self.client.get('/api/metrics/history/srv1?hours=24')
        assert r.status_code == 200
        d = r.get_json()
        assert d['success'] is True
        assert d['server_id'] == 'srv1'

    def test_metrics_summary(self):
        r = self.client.get('/api/metrics/summary')
        assert r.status_code == 200
        d = r.get_json()
        assert d['success'] is True
        assert 'summary' in d

    def test_monitoring_overview(self):
        r = self.client.get('/api/monitoring/overview')
        assert r.status_code == 200
        d = r.get_json()
        assert d['success'] is True
        overview = d['overview']
        assert 'alerts' in overview
        assert 'backups' in overview
        assert 'tasks' in overview
        assert 'webhooks' in overview


# ==================== MONITORING PAGE TESTS ====================

class TestMonitoringPage:
    """Monitoring sayfa erişim testleri."""

    def test_monitoring_page_requires_auth(self, client):
        r = client.get('/monitoring')
        assert r.status_code in (302, 401)

    def test_monitoring_page_accessible(self, auth_client):
        r = auth_client.get('/monitoring')
        assert r.status_code == 200

    def test_monitoring_page_reader_can_view(self, reader_client):
        r = reader_client.get('/monitoring')
        assert r.status_code == 200


# ==================== RBAC MONITORING TESTS ====================

class TestMonitoringRBAC:
    """Monitoring RBAC izin testleri."""

    def test_reader_cannot_create_rule(self, reader_client):
        r = reader_client.post('/api/alerts/rules',
                               data=json.dumps({'name': 'Test', 'metric': 'cpu', 'threshold': 90}),
                               content_type='application/json')
        assert r.status_code == 403

    def test_reader_can_view_rules(self, reader_client):
        r = reader_client.get('/api/alerts/rules')
        assert r.status_code == 200

    def test_reader_cannot_create_webhook(self, reader_client):
        r = reader_client.post('/api/webhooks',
                               data=json.dumps({'name': 'Test', 'webhook_type': 'slack', 'url': 'https://test'}),
                               content_type='application/json')
        assert r.status_code == 403

    def test_reader_cannot_create_task(self, reader_client):
        r = reader_client.post('/api/tasks',
                               data=json.dumps({'name': 'Test', 'server_id': 'srv1', 'command': 'ls', 'schedule': '* * * * *'}),
                               content_type='application/json')
        assert r.status_code == 403

    def test_reader_cannot_create_backup(self, reader_client):
        r = reader_client.post('/api/backups',
                               data=json.dumps({'name': 'Test', 'server_id': 'srv1', 'source_path': '/a', 'dest_path': '/b'}),
                               content_type='application/json')
        assert r.status_code == 403

    def test_operator_can_view_overview(self, operator_client):
        r = operator_client.get('/api/monitoring/overview')
        assert r.status_code == 200


# ==================== MODEL TESTS ====================

class TestMonitoringModels:
    """Monitoring model testleri."""

    def test_alert_rule_to_dict(self, app):
        from models import AlertRule
        rule = AlertRule(
            name='Test Rule',
            metric='cpu',
            condition='>',
            threshold=90.0,
            severity='critical',
        )
        d = rule.to_dict()
        assert d['name'] == 'Test Rule'
        assert d['metric'] == 'cpu'
        assert d['threshold'] == 90.0

    def test_webhook_config_to_dict(self, app):
        from models import WebhookConfig
        wh = WebhookConfig(
            name='Test Slack',
            webhook_type='slack',
            url='https://hooks.slack.com/test',
        )
        d = wh.to_dict()
        assert d['webhook_type'] == 'slack'
        assert d['url'] == 'https://hooks.slack.com/test'

    def test_scheduled_task_to_dict(self, app):
        from models import ScheduledTask
        task = ScheduledTask(
            name='Test Task',
            server_id='srv1',
            command='echo hello',
            schedule='0 2 * * *',
        )
        d = task.to_dict()
        assert d['command'] == 'echo hello'
        assert d['schedule'] == '0 2 * * *'

    def test_backup_profile_to_dict(self, app):
        from models import BackupProfile
        profile = BackupProfile(
            name='Test Backup',
            server_id='srv1',
            source_path='/var/www',
            dest_path='/backups',
            compression='gzip',
            retention_days=30,
        )
        d = profile.to_dict()
        assert d['source_path'] == '/var/www'
        assert d['compression'] == 'gzip'
        assert d['retention_days'] == 30

    def test_metric_snapshot_to_dict(self, app):
        from models import MetricSnapshot
        snap = MetricSnapshot(
            server_id='srv1',
            cpu_percent=45.2,
            memory_percent=62.8,
            disk_percent=33.1,
        )
        d = snap.to_dict()
        assert d['cpu_percent'] == 45.2
        assert d['memory_percent'] == 62.8
        assert d['server_id'] == 'srv1'

    def test_alert_history_to_dict(self, app):
        from models import AlertHistory
        ah = AlertHistory(
            server_id='srv1',
            metric='cpu',
            current_value=95.3,
            threshold=90.0,
            severity='critical',
            message='CPU yüksek!',
        )
        d = ah.to_dict()
        assert d['current_value'] == 95.3
        assert d['severity'] == 'critical'
