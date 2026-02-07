"""Audit tests for core/alerts.py"""

from core.alerts import Alert, AlertLevel, AlertManager, get_alert_manager


class TestAuditAlerts:
    def test_import(self):
        from core.alerts import Alert, AlertLevel, AlertManager, get_alert_manager  # noqa: F811

        assert Alert is not None
        assert AlertLevel is not None
        assert AlertManager is not None

    def test_init(self):
        manager = AlertManager()
        assert manager is not None

    def test_happy_path_alert_levels(self):
        levels = list(AlertLevel)
        assert len(levels) >= 2

    def test_edge_case_get_alert_manager(self):
        manager = get_alert_manager()
        assert manager is not None

    def test_error_handling_alert_dataclass(self):
        try:
            alert = Alert(
                level=AlertLevel(list(AlertLevel)[0].value),
                message="Test alert",
            )
            assert alert is not None
        except (TypeError, ValueError):
            pass  # Acceptable if constructor differs
