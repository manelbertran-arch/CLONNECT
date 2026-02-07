"""Tests for Webhook Routing - Multi-creator isolation and ID extraction."""

import pytest

from core.webhook_routing import extract_all_instagram_ids


class TestExtractInstagramIds:
    """Test ID extraction from various webhook payload formats."""

    def test_standard_messaging_payload(self):
        payload = {
            "entry": [
                {
                    "id": "page_111",
                    "messaging": [
                        {
                            "sender": {"id": "user_999"},
                            "recipient": {"id": "page_111"},
                            "message": {"text": "Hola"},
                        }
                    ],
                }
            ]
        }
        ids = extract_all_instagram_ids(payload)
        assert "page_111" in ids

    def test_multiple_entries(self):
        payload = {
            "entry": [
                {"id": "page_111", "messaging": []},
                {"id": "page_222", "messaging": []},
            ]
        }
        ids = extract_all_instagram_ids(payload)
        assert "page_111" in ids
        assert "page_222" in ids

    def test_empty_payload(self):
        ids = extract_all_instagram_ids({})
        assert isinstance(ids, list)
        assert len(ids) == 0

    def test_empty_entry(self):
        ids = extract_all_instagram_ids({"entry": []})
        assert isinstance(ids, list)
        assert len(ids) == 0

    def test_changes_payload(self):
        """Test comment/reaction webhook format with changes."""
        payload = {
            "entry": [
                {
                    "id": "page_333",
                    "changes": [
                        {
                            "value": {
                                "from": {"id": "commenter_444"},
                                "to": {"id": "page_333"},
                            }
                        }
                    ],
                }
            ]
        }
        ids = extract_all_instagram_ids(payload)
        assert "page_333" in ids

    def test_no_duplicate_ids(self):
        """Extracted IDs should not contain duplicates."""
        payload = {
            "entry": [
                {
                    "id": "page_111",
                    "messaging": [
                        {
                            "sender": {"id": "user_999"},
                            "recipient": {"id": "page_111"},
                        },
                        {
                            "sender": {"id": "user_999"},
                            "recipient": {"id": "page_111"},
                        },
                    ],
                }
            ]
        }
        ids = extract_all_instagram_ids(payload)
        assert len(ids) == len(set(ids)), "IDs contain duplicates"


class TestRoutingIsolation:
    """Test that routing correctly isolates creators."""

    def test_extract_different_pages(self):
        """Different page IDs in separate payloads should produce different ID lists."""
        payload_a = {"entry": [{"id": "page_AAA", "messaging": []}]}
        payload_b = {"entry": [{"id": "page_BBB", "messaging": []}]}

        ids_a = extract_all_instagram_ids(payload_a)
        ids_b = extract_all_instagram_ids(payload_b)

        assert "page_AAA" in ids_a
        assert "page_BBB" in ids_b
        assert "page_BBB" not in ids_a
        assert "page_AAA" not in ids_b


class TestPayloadEdgeCases:
    """Test edge cases in webhook payloads."""

    def test_missing_messaging(self):
        """Entry without messaging key should not crash."""
        payload = {"entry": [{"id": "page_123"}]}
        ids = extract_all_instagram_ids(payload)
        assert "page_123" in ids

    def test_very_large_payload(self):
        """Should handle large payloads without issues."""
        messaging = [
            {"sender": {"id": f"user_{i}"}, "recipient": {"id": "page_123"}}
            for i in range(100)
        ]
        payload = {"entry": [{"id": "page_123", "messaging": messaging}]}
        ids = extract_all_instagram_ids(payload)
        assert "page_123" in ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
