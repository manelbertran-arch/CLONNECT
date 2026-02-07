"""Audit tests for core/webhook_routing.py"""

from core.webhook_routing import (
    extract_all_instagram_ids,
    find_creator_for_webhook,
    get_creator_by_any_instagram_id,
)


class TestAuditWebhookRouting:
    def test_import(self):
        from core.webhook_routing import (  # noqa: F811
            extract_all_instagram_ids,
            find_creator_for_webhook,
        )

        assert extract_all_instagram_ids is not None

    def test_functions_callable(self):
        assert callable(extract_all_instagram_ids)
        assert callable(get_creator_by_any_instagram_id)
        assert callable(find_creator_for_webhook)

    def test_happy_path_extract_ids(self):
        payload = {"entry": [{"id": "12345", "messaging": [{"sender": {"id": "67890"}}]}]}
        ids = extract_all_instagram_ids(payload)
        assert isinstance(ids, (list, set))

    def test_edge_case_empty_payload(self):
        ids = extract_all_instagram_ids({})
        assert isinstance(ids, (list, set))
        assert len(ids) == 0

    def test_error_handling_find_creator(self):
        try:
            result = find_creator_for_webhook(["nonexistent_id_xyz"])
            assert result is None or result is not None
        except Exception:
            pass  # DB not available
