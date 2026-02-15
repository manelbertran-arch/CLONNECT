"""
Tests for nurturing PostgreSQL storage.

Tests the NurturingDBStorage class and its integration with NurturingManager.
Uses mocking to avoid requiring a real database connection.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.nurturing import FollowUp, NurturingManager, SequenceType


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_followup():
    """Create a sample FollowUp for testing."""
    now = datetime.now()
    return FollowUp(
        id="test_creator_123_interest_cold_0_1234567890",
        creator_id="test_creator",
        follower_id="123",
        sequence_type="interest_cold",
        step=0,
        scheduled_at=now.isoformat(),
        message_template="Hello {product_name}!",
        status="pending",
        created_at=now.isoformat(),
        sent_at=None,
        metadata={"product_name": "Test Product"}
    )


@pytest.fixture
def sample_followups():
    """Create multiple sample followups."""
    now = datetime.now()
    return [
        FollowUp(
            id=f"test_creator_123_interest_cold_{i}_1234567890",
            creator_id="test_creator",
            follower_id="123",
            sequence_type="interest_cold",
            step=i,
            scheduled_at=(now + timedelta(hours=24 * i)).isoformat(),
            message_template=f"Message {i}",
            status="pending" if i < 2 else "sent",
            created_at=now.isoformat(),
            metadata={"product_name": "Test Product"}
        )
        for i in range(3)
    ]


# =============================================================================
# FollowUp Tests
# =============================================================================

class TestFollowUp:
    """Tests for the FollowUp dataclass."""

    def test_to_dict(self, sample_followup):
        """Test FollowUp.to_dict() returns all fields."""
        data = sample_followup.to_dict()

        assert data["id"] == sample_followup.id
        assert data["creator_id"] == sample_followup.creator_id
        assert data["follower_id"] == sample_followup.follower_id
        assert data["sequence_type"] == sample_followup.sequence_type
        assert data["step"] == sample_followup.step
        assert data["scheduled_at"] == sample_followup.scheduled_at
        assert data["message_template"] == sample_followup.message_template
        assert data["status"] == sample_followup.status
        assert data["metadata"] == sample_followup.metadata

    def test_from_dict(self, sample_followup):
        """Test FollowUp.from_dict() creates correct instance."""
        data = sample_followup.to_dict()
        restored = FollowUp.from_dict(data)

        assert restored.id == sample_followup.id
        assert restored.creator_id == sample_followup.creator_id
        assert restored.follower_id == sample_followup.follower_id
        assert restored.status == sample_followup.status

    def test_from_dict_ignores_extra_fields(self):
        """Test FollowUp.from_dict() ignores unknown fields."""
        data = {
            "id": "test_id",
            "creator_id": "creator",
            "follower_id": "follower",
            "sequence_type": "interest_cold",
            "step": 0,
            "scheduled_at": datetime.now().isoformat(),
            "message_template": "test",
            "unknown_field": "should be ignored"
        }
        followup = FollowUp.from_dict(data)
        assert followup.id == "test_id"
        assert not hasattr(followup, "unknown_field")


# =============================================================================
# NurturingDBStorage Tests (Mocked)
# =============================================================================

class TestNurturingDBStorageMocked:
    """Tests for NurturingDBStorage with mocked database."""

    @patch('core.nurturing_db.SessionLocal', None)
    def test_is_available_when_db_not_configured(self):
        """Test is_available returns False when DB not configured."""
        from core.nurturing_db import NurturingDBStorage
        storage = NurturingDBStorage()
        assert not storage.is_available()

    @patch('core.nurturing_db.SessionLocal')
    @patch('core.nurturing_db.NURTURING_USE_DB', True)
    def test_is_available_when_db_configured(self, mock_session_local):
        """Test is_available returns True when DB configured and enabled."""
        mock_session_local.return_value = MagicMock()
        from core.nurturing_db import NurturingDBStorage
        storage = NurturingDBStorage()
        assert storage.is_available()

    @patch('core.nurturing_db.SessionLocal')
    @patch('core.nurturing_db.NURTURING_USE_DB', False)
    def test_is_available_when_feature_disabled(self, mock_session_local):
        """Test is_available returns False when feature flag is disabled."""
        mock_session_local.return_value = MagicMock()
        from core.nurturing_db import NurturingDBStorage
        storage = NurturingDBStorage()
        assert not storage.is_available()


# =============================================================================
# NurturingManager Integration Tests (Feature Flag)
# =============================================================================

class TestNurturingManagerDBIntegration:
    """Tests for NurturingManager with DB storage integration."""

    @patch('core.nurturing._get_db_storage')
    def test_manager_uses_json_when_db_disabled(self, mock_get_db):
        """Test manager uses JSON storage when DB is disabled."""
        mock_get_db.return_value = None

        with patch('os.path.exists', return_value=False):
            manager = NurturingManager()
            followups = manager._load_followups("test_creator")

        assert followups == []
        mock_get_db.assert_called()

    @patch('core.nurturing._get_db_storage')
    def test_manager_uses_db_when_enabled(self, mock_get_db):
        """Test manager uses DB storage when enabled."""
        mock_db_storage = MagicMock()
        mock_db_storage.load_followups.return_value = [
            {"id": "test", "creator_id": "test_creator", "follower_id": "123",
             "sequence_type": "interest_cold", "step": 0,
             "scheduled_at": datetime.now().isoformat(),
             "message_template": "test", "status": "pending",
             "created_at": datetime.now().isoformat(), "metadata": {}}
        ]
        mock_get_db.return_value = mock_db_storage

        manager = NurturingManager()
        manager._db_storage = mock_db_storage
        followups = manager._load_followups("test_creator")

        assert len(followups) == 1
        mock_db_storage.load_followups.assert_called_once_with("test_creator")

    @patch('core.nurturing._get_db_storage')
    def test_manager_fallback_to_json_on_db_error(self, mock_get_db):
        """Test manager falls back to JSON when DB fails."""
        mock_db_storage = MagicMock()
        mock_db_storage.load_followups.side_effect = Exception("DB Error")
        mock_get_db.return_value = mock_db_storage

        with patch('os.path.exists', return_value=False):
            manager = NurturingManager()
            manager._db_storage = mock_db_storage
            followups = manager._load_followups("test_creator")

        assert followups == []

    @patch('core.nurturing._get_db_storage')
    def test_save_writes_to_both_db_and_json(self, mock_get_db, sample_followups, tmp_path):
        """Test save writes to both DB and JSON file."""
        mock_db_storage = MagicMock()
        mock_db_storage.save_followups.return_value = True
        mock_get_db.return_value = mock_db_storage

        manager = NurturingManager(storage_path=str(tmp_path))
        manager._db_storage = mock_db_storage
        manager._save_followups("test_creator", sample_followups)

        # Check DB was called
        mock_db_storage.save_followups.assert_called_once()

        # Check JSON file was created
        json_file = tmp_path / "test_creator_followups.json"
        assert json_file.exists()

    @patch('core.nurturing._get_db_storage')
    def test_get_pending_uses_db_query(self, mock_get_db):
        """Test get_pending_followups uses efficient DB query."""
        now = datetime.now()
        mock_db_storage = MagicMock()
        mock_db_storage.get_pending_followups.return_value = [
            {"id": "test", "creator_id": "test_creator", "follower_id": "123",
             "sequence_type": "interest_cold", "step": 0,
             "scheduled_at": (now - timedelta(hours=1)).isoformat(),
             "message_template": "test", "status": "pending",
             "created_at": now.isoformat(), "metadata": {}}
        ]
        mock_get_db.return_value = mock_db_storage

        manager = NurturingManager()
        manager._db_storage = mock_db_storage
        pending = manager.get_pending_followups("test_creator")

        assert len(pending) == 1
        mock_db_storage.get_pending_followups.assert_called_once_with("test_creator")


# =============================================================================
# Sequence Type Tests
# =============================================================================

class TestSequenceTypes:
    """Tests for sequence type enum and configurations."""

    def test_all_sequence_types_defined(self):
        """Test all expected sequence types are defined."""
        expected = [
            "interest_cold", "objection_price", "objection_time",
            "objection_doubt", "objection_later", "abandoned",
            "re_engagement", "post_purchase", "discount_urgency",
            "spots_limited", "offer_expiring", "flash_sale"
        ]
        actual = [st.value for st in SequenceType]
        for expected_type in expected:
            assert expected_type in actual, f"Missing sequence type: {expected_type}"

    def test_sequence_type_values_are_strings(self):
        """Test all sequence type values are valid strings."""
        for st in SequenceType:
            assert isinstance(st.value, str)
            assert len(st.value) > 0


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_followup_with_none_sent_at(self):
        """Test FollowUp handles None sent_at correctly."""
        followup = FollowUp(
            id="test",
            creator_id="creator",
            follower_id="follower",
            sequence_type="interest_cold",
            step=0,
            scheduled_at=datetime.now().isoformat(),
            message_template="test",
            sent_at=None
        )
        data = followup.to_dict()
        assert data["sent_at"] is None

    def test_followup_with_empty_metadata(self):
        """Test FollowUp handles empty metadata correctly."""
        followup = FollowUp(
            id="test",
            creator_id="creator",
            follower_id="follower",
            sequence_type="interest_cold",
            step=0,
            scheduled_at=datetime.now().isoformat(),
            message_template="test"
        )
        assert followup.metadata == {}

    @patch('core.nurturing._get_db_storage')
    def test_manager_handles_empty_creator_list(self, mock_get_db, tmp_path):
        """Test manager handles case with no creators."""
        mock_get_db.return_value = None

        manager = NurturingManager(storage_path=str(tmp_path))
        pending = manager.get_pending_followups()

        assert pending == []


# =============================================================================
# Stats Tests
# =============================================================================

class TestStats:
    """Tests for statistics calculations."""

    @patch('core.nurturing._get_db_storage')
    def test_get_stats_empty(self, mock_get_db, tmp_path):
        """Test get_stats returns correct structure for empty data."""
        mock_get_db.return_value = None

        manager = NurturingManager(storage_path=str(tmp_path))
        stats = manager.get_stats("test_creator")

        assert stats["total"] == 0
        assert stats["pending"] == 0
        assert stats["sent"] == 0
        assert stats["cancelled"] == 0
        assert stats["by_sequence"] == {}

    @patch('core.nurturing._get_db_storage')
    def test_get_stats_with_data(self, mock_get_db, sample_followups, tmp_path):
        """Test get_stats returns correct counts."""
        mock_get_db.return_value = None

        manager = NurturingManager(storage_path=str(tmp_path))
        manager._cache["test_creator"] = sample_followups
        stats = manager.get_stats("test_creator")

        assert stats["total"] == 3
        assert stats["pending"] == 2
        assert stats["sent"] == 1
        assert stats["cancelled"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
