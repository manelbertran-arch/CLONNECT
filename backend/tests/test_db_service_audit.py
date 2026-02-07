"""Audit tests for api/services/db_service.py."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# 1. Init / Import
# ---------------------------------------------------------------------------
class TestDbServiceImport:
    """Verify that the service module and its key symbols can be imported."""

    def test_module_imports_successfully(self):
        """Core public functions are importable without side-effects."""
        from api.services.db_service import (
            get_creator_by_name,
            get_instagram_credentials,
            get_leads,
            get_or_create_creator,
            get_session,
            toggle_bot,
            update_creator,
        )

        # All symbols should be callable
        assert callable(get_session)
        assert callable(get_creator_by_name)
        assert callable(get_leads)
        assert callable(get_or_create_creator)
        assert callable(update_creator)
        assert callable(toggle_bot)
        assert callable(get_instagram_credentials)


# ---------------------------------------------------------------------------
# 2. Happy Path -- Lead CRUD (mocked DB)
# ---------------------------------------------------------------------------
class TestLeadCrudMock:
    """Test lead retrieval returns correctly-shaped results when DB is mocked."""

    @patch("api.services.db_service.get_session")
    def test_get_leads_returns_list_for_valid_creator(self, mock_get_session):
        """get_leads should return a list of lead dicts when creator exists."""
        from api.services.db_service import get_leads

        # Build mock objects
        mock_session = MagicMock()
        mock_get_session.return_value = mock_session

        mock_creator = MagicMock()
        mock_creator.id = uuid.uuid4()
        mock_creator.name = "test_creator"

        # Lead mock
        mock_lead = MagicMock()
        mock_lead.id = uuid.uuid4()
        mock_lead.platform_user_id = "ig_123"
        mock_lead.platform = "instagram"
        mock_lead.username = "testuser"
        mock_lead.full_name = "Test User"
        mock_lead.status = "new"
        mock_lead.score = 0.5
        mock_lead.purchase_intent = 0.3
        mock_lead.last_contact_at = datetime.now(timezone.utc)
        mock_lead.context = {}
        mock_lead.email = None
        mock_lead.phone = None
        mock_lead.notes = None
        mock_lead.tags = None
        mock_lead.deal_value = None

        # Wire query chain
        mock_query = mock_session.query.return_value
        mock_query.filter_by.return_value.first.return_value = mock_creator
        filter_result = mock_query.filter_by.return_value.filter.return_value
        filter_result.order_by.return_value.limit.return_value.all.return_value = [mock_lead]

        # Mock the message query (for last_messages)
        mock_session.query.return_value.filter.return_value.distinct.return_value.order_by.return_value.all.return_value = (
            []
        )

        result = get_leads("test_creator")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["username"] == "testuser"
        assert result[0]["platform"] == "instagram"


# ---------------------------------------------------------------------------
# 3. Edge Case -- Empty results
# ---------------------------------------------------------------------------
class TestEmptyResultHandling:
    """Edge cases where database returns no data."""

    @patch("api.services.db_service.get_session")
    def test_get_leads_returns_empty_when_creator_not_found(self, mock_get_session):
        """get_leads returns [] when the creator does not exist in DB."""
        from api.services.db_service import get_leads

        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        result = get_leads("nonexistent_creator")
        assert result == []

    @patch("api.services.db_service.get_session")
    def test_get_creator_by_name_returns_none_when_missing(self, mock_get_session):
        """get_creator_by_name returns None for a non-existent creator."""
        from api.services.db_service import get_creator_by_name

        mock_session = MagicMock()
        mock_get_session.return_value = mock_session
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        result = get_creator_by_name("ghost")
        assert result is None


# ---------------------------------------------------------------------------
# 4. Error Handling
# ---------------------------------------------------------------------------
class TestErrorHandling:
    """Verify graceful failure when the DB session is unavailable."""

    @patch("api.services.db_service.get_session", return_value=None)
    def test_get_leads_returns_empty_without_session(self, _mock):
        """When get_session returns None, get_leads should return []."""
        from api.services.db_service import get_leads

        result = get_leads("any_creator")
        assert result == []

    @patch("api.services.db_service.get_session", return_value=None)
    def test_get_instagram_credentials_without_session(self, _mock):
        """When DB is unavailable, credentials return success=False."""
        from api.services.db_service import get_instagram_credentials

        result = get_instagram_credentials("any_creator")
        assert result["success"] is False
        assert result["token"] is None
        assert "Database not available" in result["error"]

    @patch("api.services.db_service.get_session", return_value=None)
    def test_toggle_bot_returns_none_without_session(self, _mock):
        """toggle_bot should return None when the DB is down."""
        from api.services.db_service import toggle_bot

        result = toggle_bot("any_creator", True)
        assert result is None


# ---------------------------------------------------------------------------
# 5. Integration Check -- Pagination logic
# ---------------------------------------------------------------------------
class TestPaginationLogic:
    """Verify that get_leads passes the limit parameter correctly."""

    @patch("api.services.db_service.get_session")
    def test_get_leads_passes_limit_to_query(self, mock_get_session):
        """The limit argument should be forwarded to SQLAlchemy .limit()."""
        from api.services.db_service import get_leads

        mock_session = MagicMock()
        mock_get_session.return_value = mock_session

        mock_creator = MagicMock()
        mock_creator.id = uuid.uuid4()

        mock_query = mock_session.query.return_value
        mock_query.filter_by.return_value.first.return_value = mock_creator
        filter_chain = mock_query.filter_by.return_value.filter.return_value
        order_chain = filter_chain.order_by.return_value
        limit_chain = order_chain.limit.return_value
        limit_chain.all.return_value = []

        # Mock message subquery
        mock_session.query.return_value.filter.return_value.distinct.return_value.order_by.return_value.all.return_value = (
            []
        )

        get_leads("creator", limit=25)

        # Verify .limit(25) was called
        order_chain.limit.assert_called_once_with(25)
