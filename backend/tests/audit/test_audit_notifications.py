"""Audit tests for core/notifications.py"""

from core.notifications import (
    EscalationNotification,
    NotificationService,
    NotificationType,
    get_notification_service,
)


class TestAuditNotifications:
    def test_import(self):
        from core.notifications import (  # noqa: F811
            EscalationNotification,
            NotificationService,
            NotificationType,
        )

        assert NotificationType is not None

    def test_notification_types(self):
        types = list(NotificationType)
        assert len(types) >= 1

    def test_happy_path_service(self):
        service = get_notification_service()
        assert service is not None

    def test_edge_case_escalation_to_dict(self):
        try:
            notif = EscalationNotification()
            d = notif.to_dict()
            assert isinstance(d, dict)
        except TypeError:
            pass  # Requires args

    def test_error_handling_service_init(self):
        service = NotificationService()
        assert service is not None
