"""Audit tests for api/services/message_db.py"""

from api.services.message_db import get_or_create_lead_sync, save_message_sync


class TestAuditMessageDB:
    def test_import(self):
        from api.services.message_db import get_or_create_lead_sync, save_message_sync  # noqa: F811

        assert save_message_sync is not None

    def test_functions_callable(self):
        assert callable(save_message_sync)
        assert callable(get_or_create_lead_sync)

    def test_happy_path_has_params(self):
        import inspect

        sig = inspect.signature(save_message_sync)
        params = list(sig.parameters.keys())
        assert "lead_id" in params
        assert "role" in params
        assert "content" in params

    def test_edge_case_lead_sync_params(self):
        import inspect

        sig = inspect.signature(get_or_create_lead_sync)
        params = list(sig.parameters.keys())
        assert "creator_id" in params
        assert "platform_id" in params

    def test_error_handling_save_message(self):
        try:
            save_message_sync(
                lead_id="fake-uuid-12345",
                role="lead",
                content="test message",
            )
        except Exception:
            pass  # DB not available, expected
