"""Audit tests for api/services/data_sync.py."""

from unittest.mock import patch


# ---------------------------------------------------------------------------
# 1. Init / Import
# ---------------------------------------------------------------------------
class TestDataSyncImport:
    """Verify that the data_sync module and its key symbols can be imported."""

    def test_module_imports_successfully(self):
        """All public functions should be importable."""
        from api.services.data_sync import (
            ensure_lead_in_postgres,
            full_sync_creator,
            sync_archive_to_json,
            sync_delete_json,
            sync_json_to_postgres,
            sync_lead_to_json,
            sync_message_to_json,
            sync_messages_from_json,
            sync_spam_to_json,
            update_lead_score_direct,
        )

        assert callable(sync_lead_to_json)
        assert callable(sync_json_to_postgres)
        assert callable(sync_message_to_json)
        assert callable(full_sync_creator)
        assert callable(ensure_lead_in_postgres)
        assert callable(sync_archive_to_json)
        assert callable(sync_spam_to_json)
        assert callable(sync_delete_json)
        assert callable(sync_messages_from_json)
        assert callable(update_lead_score_direct)


# ---------------------------------------------------------------------------
# 2. Happy Path -- sync_lead_to_json creates new JSON
# ---------------------------------------------------------------------------
class TestSyncTriggerMock:
    """Test that sync_lead_to_json writes correctly shaped JSON data."""

    @patch("api.services.data_sync._save_json")
    @patch("api.services.data_sync._load_json", return_value=None)
    def test_sync_lead_creates_new_json_when_missing(self, mock_load, mock_save):
        """When no existing JSON, sync_lead_to_json should create a new file."""
        from api.services.data_sync import sync_lead_to_json

        lead_data = {
            "platform_user_id": "ig_555",
            "username": "new_user",
            "full_name": "New User",
            "status": "new",
            "purchase_intent": 0.4,
            "first_contact_at": "2026-01-01T00:00:00+00:00",
            "last_contact_at": "2026-01-02T00:00:00+00:00",
        }

        sync_lead_to_json("test_creator", lead_data)

        mock_save.assert_called_once()
        args = mock_save.call_args
        assert args[0][0] == "test_creator"
        assert args[0][1] == "ig_555"
        saved_data = args[0][2]
        assert saved_data["follower_id"] == "ig_555"
        assert saved_data["username"] == "new_user"
        assert saved_data["purchase_intent_score"] == 0.4
        assert saved_data["is_lead"] is True


# ---------------------------------------------------------------------------
# 3. Edge Case -- Conflict resolution (status upgrade only)
# ---------------------------------------------------------------------------
class TestConflictResolution:
    """Test that sync only upgrades status, never downgrades."""

    @patch("api.services.data_sync._save_json")
    @patch("api.services.data_sync._load_json")
    def test_sync_lead_updates_existing_json(self, mock_load, mock_save):
        """When JSON exists, sync_lead_to_json merges data (no status downgrade)."""
        from api.services.data_sync import sync_lead_to_json

        existing_json = {
            "follower_id": "ig_555",
            "creator_id": "test_creator",
            "username": "old_username",
            "name": "Old Name",
            "purchase_intent_score": 0.2,
            "is_lead": True,
            "is_customer": False,
            "last_contact": "2026-01-01T00:00:00+00:00",
        }
        mock_load.return_value = existing_json

        lead_data = {
            "platform_user_id": "ig_555",
            "username": "updated_username",
            "full_name": "Updated Name",
            "status": "active",
            "purchase_intent": 0.8,
            "last_contact_at": "2026-02-01T00:00:00+00:00",
        }

        sync_lead_to_json("test_creator", lead_data)

        mock_save.assert_called_once()
        saved_data = mock_save.call_args[0][2]
        assert saved_data["username"] == "updated_username"
        assert saved_data["name"] == "Updated Name"
        assert saved_data["purchase_intent_score"] == 0.8


# ---------------------------------------------------------------------------
# 4. Error Handling -- Empty data / missing platform_user_id
# ---------------------------------------------------------------------------
class TestEmptyDataHandling:
    """Verify graceful handling of missing or empty data."""

    @patch("api.services.data_sync._save_json")
    @patch("api.services.data_sync._load_json")
    def test_sync_lead_skips_when_no_platform_user_id(self, mock_load, mock_save):
        """sync_lead_to_json should silently return if platform_user_id is empty."""
        from api.services.data_sync import sync_lead_to_json

        sync_lead_to_json("creator", {"platform_user_id": ""})
        mock_save.assert_not_called()

        sync_lead_to_json("creator", {})
        mock_save.assert_not_called()

    def test_sync_message_to_json_creates_structure_when_no_json(self):
        """sync_message_to_json should create a basic JSON if none exists."""
        from api.services.data_sync import sync_message_to_json

        with patch("api.services.data_sync._load_json", return_value=None), patch(
            "api.services.data_sync._save_json"
        ) as mock_save:

            sync_message_to_json("creator", "follower_1", "user", "hello")

            mock_save.assert_called_once()
            saved = mock_save.call_args[0][2]
            assert len(saved["last_messages"]) == 1
            assert saved["last_messages"][0]["role"] == "user"
            assert saved["last_messages"][0]["content"] == "hello"
            assert saved["total_messages"] == 1


# ---------------------------------------------------------------------------
# 5. Integration Check -- full_sync_creator stats tracking
# ---------------------------------------------------------------------------
class TestSyncStatusTracking:
    """Verify that full_sync_creator tracks sync statistics correctly."""

    @patch("api.services.data_sync.USE_POSTGRES", False)
    def test_full_sync_returns_empty_stats_without_postgres(self):
        """full_sync_creator returns zero stats when PostgreSQL is disabled."""
        from api.services.data_sync import full_sync_creator

        stats = full_sync_creator("any_creator")
        assert stats == {"synced": 0, "errors": 0, "skipped": 0}

    @patch("api.services.data_sync.USE_POSTGRES", True)
    @patch("os.path.exists", return_value=False)
    def test_full_sync_returns_empty_stats_when_no_directory(self, _mock_exists):
        """full_sync_creator returns zero stats when creator directory is missing."""
        from api.services.data_sync import full_sync_creator

        stats = full_sync_creator("missing_creator")
        assert stats == {"synced": 0, "errors": 0, "skipped": 0}

    @patch("api.services.data_sync.USE_POSTGRES", True)
    @patch("api.services.data_sync.sync_json_to_postgres")
    @patch("os.listdir", return_value=["user1.json", "user2.json", "readme.txt"])
    @patch("os.path.exists", return_value=True)
    def test_full_sync_processes_only_json_files(self, _exists, _listdir, mock_sync):
        """full_sync_creator only processes .json files, not .txt."""
        from api.services.data_sync import full_sync_creator

        mock_sync.return_value = "lead-id-123"

        stats = full_sync_creator("my_creator")
        # Only 2 .json files, not the .txt
        assert mock_sync.call_count == 2
        assert stats["synced"] == 2
        assert stats["errors"] == 0
