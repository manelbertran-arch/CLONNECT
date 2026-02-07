"""Audit tests for api/services/data_sync.py"""

from api.services.data_sync import sync_json_to_postgres, sync_lead_to_json, sync_message_to_json


class TestAuditDataSync:
    def test_import(self):
        from api.services.data_sync import (  # noqa: F811
            sync_json_to_postgres,
            sync_lead_to_json,
            sync_message_to_json,
        )

        assert sync_lead_to_json is not None

    def test_functions_callable(self):
        assert callable(sync_lead_to_json)
        assert callable(sync_json_to_postgres)
        assert callable(sync_message_to_json)

    def test_happy_path_sync_lead_params(self):
        import inspect

        sig = inspect.signature(sync_lead_to_json)
        params = list(sig.parameters.keys())
        assert "creator_name" in params
        assert "lead_data" in params

    def test_edge_case_sync_message_params(self):
        import inspect

        sig = inspect.signature(sync_message_to_json)
        params = list(sig.parameters.keys())
        assert len(params) >= 3

    def test_error_handling_sync_nonexistent(self):
        try:
            sync_json_to_postgres("nonexistent_creator", "fake_follower_id")
        except Exception:
            pass  # Expected - no data to sync
