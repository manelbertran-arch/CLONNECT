"""
Tests for webhook routing functions.

Tests the multi-creator webhook routing system that handles
different Instagram ID formats from Meta.
"""

import uuid
from unittest.mock import MagicMock, patch


class TestExtractAllInstagramIds:
    """Tests for extract_all_instagram_ids function."""

    def test_extract_from_entry_id(self):
        """Should extract ID from entry.id"""
        from core.webhook_routing import extract_all_instagram_ids

        payload = {"object": "instagram", "entry": [{"id": "17841400506734756"}]}

        result = extract_all_instagram_ids(payload)
        assert "17841400506734756" in result

    def test_extract_from_messaging_recipient(self):
        """Should extract recipient ID from messaging events"""
        from core.webhook_routing import extract_all_instagram_ids

        payload = {
            "object": "instagram",
            "entry": [
                {
                    "id": "123",
                    "messaging": [
                        {"recipient": {"id": "25734915742865411"}, "sender": {"id": "user123"}}
                    ],
                }
            ],
        }

        result = extract_all_instagram_ids(payload)
        assert "25734915742865411" in result
        assert "user123" in result
        assert "123" in result

    def test_extract_from_changes(self):
        """Should extract IDs from changes (comments, etc.)"""
        from core.webhook_routing import extract_all_instagram_ids

        payload = {
            "object": "instagram",
            "entry": [
                {
                    "id": "page123",
                    "changes": [{"value": {"from": {"id": "commenter456"}, "page_id": "page789"}}],
                }
            ],
        }

        result = extract_all_instagram_ids(payload)
        assert "page123" in result
        assert "commenter456" in result
        assert "page789" in result

    def test_extract_empty_payload(self):
        """Should return empty list for empty payload"""
        from core.webhook_routing import extract_all_instagram_ids

        result = extract_all_instagram_ids({})
        assert result == []

        result = extract_all_instagram_ids({"entry": []})
        assert result == []

    def test_extract_handles_missing_fields(self):
        """Should handle missing fields gracefully"""
        from core.webhook_routing import extract_all_instagram_ids

        payload = {
            "object": "instagram",
            "entry": [{"messaging": [{}]}],  # Missing recipient/sender
        }

        # Should not raise, just return what it finds
        result = extract_all_instagram_ids(payload)
        assert isinstance(result, list)

    def test_extract_deduplicates(self):
        """Should return unique IDs only"""
        from core.webhook_routing import extract_all_instagram_ids

        payload = {
            "object": "instagram",
            "entry": [
                {"id": "same123"},
                {"id": "same123"},  # Duplicate
                {"messaging": [{"recipient": {"id": "same123"}}]},  # Same ID
            ],
        }

        result = extract_all_instagram_ids(payload)
        assert result.count("same123") == 1  # Only one occurrence


class TestGetCreatorByAnyInstagramId:
    """Tests for get_creator_by_any_instagram_id function."""

    @patch("api.database.SessionLocal")
    def test_find_by_page_id(self, mock_session_local):
        """Should find creator by instagram_page_id"""
        from core.webhook_routing import clear_routing_cache, get_creator_by_any_instagram_id

        clear_routing_cache()

        # Mock creator
        mock_creator = MagicMock()
        mock_creator.name = "test_creator"
        mock_creator.id = uuid.uuid4()
        mock_creator.instagram_token = "token123"
        mock_creator.instagram_page_id = "page123"
        mock_creator.instagram_user_id = None
        mock_creator.instagram_additional_ids = []
        mock_creator.bot_active = True
        mock_creator.copilot_mode = False

        # Mock session
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_creator
        mock_session_local.return_value = mock_session

        result = get_creator_by_any_instagram_id("page123")

        assert result is not None
        assert result["creator_id"] == "test_creator"
        assert result["bot_active"] is True

    @patch("api.database.SessionLocal")
    def test_find_by_user_id_fallback(self, mock_session_local):
        """Should fall back to instagram_user_id if page_id not found"""
        from core.webhook_routing import clear_routing_cache, get_creator_by_any_instagram_id

        clear_routing_cache()

        mock_creator = MagicMock()
        mock_creator.name = "test_creator"
        mock_creator.id = uuid.uuid4()
        mock_creator.instagram_token = "token123"
        mock_creator.instagram_page_id = None
        mock_creator.instagram_user_id = "user456"
        mock_creator.instagram_additional_ids = []
        mock_creator.bot_active = True
        mock_creator.copilot_mode = False

        mock_session = MagicMock()
        # First call (page_id) returns None, second call (user_id) returns creator
        mock_session.query.return_value.filter_by.return_value.first.side_effect = [
            None,
            mock_creator,
        ]
        mock_session_local.return_value = mock_session

        result = get_creator_by_any_instagram_id("user456")

        assert result is not None
        assert result["creator_id"] == "test_creator"

    @patch("api.database.SessionLocal")
    def test_not_found_returns_none(self, mock_session_local):
        """Should return None if no creator found"""
        from core.webhook_routing import clear_routing_cache, get_creator_by_any_instagram_id

        clear_routing_cache()

        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_session_local.return_value = mock_session

        result = get_creator_by_any_instagram_id("unknown123")

        assert result is None

    def test_cache_works(self):
        """Should use cache for repeated lookups"""
        from core.webhook_routing import (
            _creator_cache,
            clear_routing_cache,
            get_creator_by_any_instagram_id,
        )

        clear_routing_cache()

        # Manually populate cache
        import time

        cached_creator = {"creator_id": "cached_creator", "bot_active": True}
        _creator_cache["ig_any:cached123"] = (cached_creator, time.time())

        # Should return cached value without DB call
        result = get_creator_by_any_instagram_id("cached123")

        assert result is not None
        assert result["creator_id"] == "cached_creator"


class TestFindCreatorForWebhook:
    """Tests for find_creator_for_webhook function."""

    @patch("core.webhook_routing.get_creator_by_any_instagram_id")
    def test_finds_first_match(self, mock_get_creator):
        """Should return first matching creator"""
        from core.webhook_routing import find_creator_for_webhook

        mock_get_creator.side_effect = [
            None,  # First ID not found
            {"creator_id": "found_creator"},  # Second ID matches
        ]

        creator_info, matched_id = find_creator_for_webhook(["id1", "id2", "id3"])

        assert creator_info is not None
        assert creator_info["creator_id"] == "found_creator"
        assert matched_id == "id2"

    @patch("core.webhook_routing.get_creator_by_any_instagram_id")
    def test_returns_none_if_no_match(self, mock_get_creator):
        """Should return (None, None) if no IDs match"""
        from core.webhook_routing import find_creator_for_webhook

        mock_get_creator.return_value = None

        creator_info, matched_id = find_creator_for_webhook(["id1", "id2"])

        assert creator_info is None
        assert matched_id is None

    def test_handles_empty_list(self):
        """Should handle empty ID list"""
        from core.webhook_routing import find_creator_for_webhook

        creator_info, matched_id = find_creator_for_webhook([])

        assert creator_info is None
        assert matched_id is None


class TestSaveUnmatchedWebhook:
    """Tests for save_unmatched_webhook function."""

    @patch("api.database.SessionLocal")
    def test_saves_webhook(self, mock_session_local):
        """Should save unmatched webhook to database"""
        from core.webhook_routing import save_unmatched_webhook

        mock_session = MagicMock()
        mock_session_local.return_value = mock_session

        # Mock the UnmatchedWebhook to have an id after add
        def set_id(obj):
            obj.id = uuid.uuid4()

        mock_session.add.side_effect = set_id

        result = save_unmatched_webhook(
            instagram_ids=["id1", "id2"], payload={"object": "instagram", "entry": [{"id": "123"}]}
        )

        assert result is not None
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @patch("api.database.SessionLocal")
    def test_creates_sanitized_summary(self, mock_session_local):
        """Should create sanitized payload summary"""
        from core.webhook_routing import save_unmatched_webhook

        mock_session = MagicMock()
        mock_session_local.return_value = mock_session

        saved_obj = None

        def capture_add(obj):
            nonlocal saved_obj
            saved_obj = obj
            obj.id = uuid.uuid4()

        mock_session.add.side_effect = capture_add

        payload = {
            "object": "instagram",
            "entry": [
                {"id": "entry1", "messaging": [{"message": "secret text"}]},
                {"id": "entry2", "changes": [{}]},
            ],
        }

        save_unmatched_webhook(["id1"], payload)

        # Check that summary doesn't contain sensitive data
        summary = saved_obj.payload_summary
        assert "secret text" not in str(summary)
        assert summary["object"] == "instagram"
        assert summary["entry_count"] == 2
        assert summary["has_messaging"] is True
        assert summary["has_changes"] is True


class TestUpdateCreatorWebhookStats:
    """Tests for update_creator_webhook_stats function."""

    @patch("api.database.SessionLocal")
    def test_updates_stats(self, mock_session_local):
        """Should increment webhook_count and update timestamp"""
        from core.webhook_routing import update_creator_webhook_stats

        mock_creator = MagicMock()
        mock_creator.webhook_count = 5
        mock_creator.webhook_last_received = None

        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_creator
        mock_session_local.return_value = mock_session

        result = update_creator_webhook_stats("test_creator")

        assert result is True
        assert mock_creator.webhook_count == 6
        assert mock_creator.webhook_last_received is not None
        mock_session.commit.assert_called_once()

    @patch("api.database.SessionLocal")
    def test_handles_none_count(self, mock_session_local):
        """Should handle None webhook_count"""
        from core.webhook_routing import update_creator_webhook_stats

        mock_creator = MagicMock()
        mock_creator.webhook_count = None

        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_creator
        mock_session_local.return_value = mock_session

        result = update_creator_webhook_stats("test_creator")

        assert result is True
        assert mock_creator.webhook_count == 1


class TestAddInstagramIdToCreator:
    """Tests for add_instagram_id_to_creator function."""

    @patch("api.database.SessionLocal")
    def test_adds_id_to_empty_list(self, mock_session_local):
        """Should add ID to empty additional_ids list"""
        from core.webhook_routing import add_instagram_id_to_creator, clear_routing_cache

        clear_routing_cache()

        mock_creator = MagicMock()
        mock_creator.instagram_additional_ids = None

        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_creator
        mock_session_local.return_value = mock_session

        result = add_instagram_id_to_creator("test_creator", "new_id")

        assert result is True
        assert "new_id" in mock_creator.instagram_additional_ids

    @patch("api.database.SessionLocal")
    def test_doesnt_add_duplicate(self, mock_session_local):
        """Should not add duplicate ID"""
        from core.webhook_routing import add_instagram_id_to_creator

        mock_creator = MagicMock()
        mock_creator.instagram_additional_ids = ["existing_id"]

        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_creator
        mock_session_local.return_value = mock_session

        result = add_instagram_id_to_creator("test_creator", "existing_id")

        assert result is True
        # Should still have only one occurrence
        assert mock_creator.instagram_additional_ids.count("existing_id") == 1
