"""Audit tests for core/copilot_service.py."""

import time
from unittest.mock import MagicMock, patch

import pytest
from core.copilot_service import CopilotService, PendingResponse, get_copilot_service


class TestCopilotInit:
    """Test 1: Initialization and imports."""

    def test_copilot_service_init_empty_caches(self):
        """CopilotService initializes with empty caches."""
        service = CopilotService()
        assert service._pending_responses == {}
        assert service._copilot_mode_cache == {}
        assert service._copilot_mode_cache_ttl == {}
        assert service._CACHE_TTL == 60

    def test_pending_response_dataclass(self):
        """PendingResponse dataclass stores all fields."""
        pr = PendingResponse(
            id="pr_1",
            lead_id="lead_1",
            follower_id="f1",
            platform="instagram",
            user_message="Hello",
            user_message_id="umid_1",
            suggested_response="Hi there!",
            intent="greeting",
            confidence=0.95,
            created_at="2026-01-01T00:00:00",
            username="testuser",
            full_name="Test User",
        )
        assert pr.id == "pr_1"
        assert pr.platform == "instagram"
        assert pr.confidence == 0.95

    def test_get_copilot_service_returns_instance(self):
        """get_copilot_service returns a CopilotService instance."""
        import core.copilot_service as mod

        original = mod._copilot_service
        mod._copilot_service = None
        try:
            service = get_copilot_service()
            assert isinstance(service, CopilotService)
        finally:
            mod._copilot_service = original

    def test_invalidate_copilot_cache(self):
        """invalidate_copilot_cache removes cached values."""
        service = CopilotService()
        service._copilot_mode_cache["creator1"] = True
        service._copilot_mode_cache_ttl["creator1"] = time.time()
        service.invalidate_copilot_cache("creator1")
        assert "creator1" not in service._copilot_mode_cache
        assert "creator1" not in service._copilot_mode_cache_ttl

    def test_invalidate_cache_noop_for_unknown_creator(self):
        """invalidate_copilot_cache does not raise for unknown creator."""
        service = CopilotService()
        service.invalidate_copilot_cache("nonexistent")  # Should not raise


class TestPendingMessageRetrieval:
    """Test 2: Happy path - pending message retrieval (mocked DB)."""

    @pytest.mark.asyncio
    async def test_get_pending_responses_empty_when_no_creator(self):
        """get_pending_responses returns empty when creator not found."""
        service = CopilotService()
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        with patch("api.database.SessionLocal", return_value=mock_session):
            result = await service.get_pending_responses("unknown_creator")
        assert result["pending"] == []
        assert result["total_count"] == 0
        assert result["has_more"] is False

    @pytest.mark.asyncio
    async def test_get_pending_responses_returns_structure(self):
        """get_pending_responses returns dict with pending, total_count, has_more."""
        service = CopilotService()
        mock_session = MagicMock()
        mock_creator_row = MagicMock()
        mock_creator_row.__getitem__ = lambda self, idx: 1  # creator.id = 1

        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_creator_row

        # Mock the pending messages query chain
        mock_query = MagicMock()
        mock_session.query.return_value.join.return_value.filter.return_value = mock_query
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = (
            []
        )

        with patch("api.database.SessionLocal", return_value=mock_session):
            result = await service.get_pending_responses("creator1")

        assert isinstance(result, dict)
        assert "pending" in result
        assert "has_more" in result

    @pytest.mark.asyncio
    async def test_get_pending_handles_db_exception(self):
        """get_pending_responses returns empty on DB exception."""
        service = CopilotService()
        mock_session = MagicMock()
        mock_session.query.side_effect = RuntimeError("DB error")

        with patch("api.database.SessionLocal", return_value=mock_session):
            result = await service.get_pending_responses("creator1")
        assert result["pending"] == []
        assert result["total_count"] == 0


class TestApprovalFlow:
    """Test 3: Edge case - approval flow logic."""

    def test_calculate_purchase_intent_greeting(self):
        """Greeting intent gives low purchase score."""
        service = CopilotService()
        result = service._calculate_purchase_intent(0.0, "greeting")
        assert result == pytest.approx(0.10)

    def test_calculate_purchase_intent_strong_interest(self):
        """Strong interest intent raises purchase score to 0.75."""
        service = CopilotService()
        result = service._calculate_purchase_intent(0.0, "interest_strong")
        assert result == pytest.approx(0.75)

    def test_calculate_purchase_intent_objection_decreases(self):
        """Objection intent decreases purchase score."""
        service = CopilotService()
        result = service._calculate_purchase_intent(0.50, "objection")
        assert result == pytest.approx(0.40)

    def test_calculate_purchase_intent_capped_at_one(self):
        """Purchase intent never exceeds 1.0."""
        service = CopilotService()
        result = service._calculate_purchase_intent(0.95, "purchase")
        assert result <= 1.0

    def test_calculate_purchase_intent_non_string_intent(self):
        """Non-string intent is handled gracefully (converted to string)."""
        service = CopilotService()
        result = service._calculate_purchase_intent(0.0, None)
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0


class TestRejectionHandling:
    """Test 4: Error handling - discard/rejection flow."""

    @pytest.mark.asyncio
    async def test_discard_response_message_not_found(self):
        """discard_response returns error when message not found."""
        service = CopilotService()
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        with patch("api.database.SessionLocal", return_value=mock_session):
            result = await service.discard_response("creator1", "nonexistent_msg")
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_discard_response_db_exception(self):
        """discard_response handles DB exception gracefully."""
        service = CopilotService()
        mock_session = MagicMock()
        mock_session.query.side_effect = RuntimeError("DB connection lost")

        with patch("api.database.SessionLocal", return_value=mock_session):
            result = await service.discard_response("creator1", "msg_1")
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_approve_response_creator_not_found(self):
        """approve_response returns error when creator not found."""
        service = CopilotService()
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None

        with patch("api.database.SessionLocal", return_value=mock_session):
            result = await service.approve_response("unknown_creator", "msg_1")
        assert result["success"] is False
        assert "creator" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_approve_response_wrong_status(self):
        """approve_response rejects message not in pending_approval status."""
        service = CopilotService()
        mock_session = MagicMock()

        mock_creator = MagicMock()
        mock_msg = MagicMock()
        mock_msg.status = "sent"  # Not pending_approval

        # First call returns creator, second returns message
        mock_session.query.return_value.filter_by.return_value.first.side_effect = [
            mock_creator,
            mock_msg,
        ]

        with patch("api.database.SessionLocal", return_value=mock_session):
            result = await service.approve_response("creator1", "msg_1")
        assert result["success"] is False
        assert "not pending" in result["error"].lower()


class TestEmptyQueue:
    """Test 5: Integration check - empty queue and lead status calculation."""

    def test_lead_status_hot(self):
        """Purchase intent >= 0.75 maps to 'hot' status."""
        service = CopilotService()
        assert service._calculate_lead_status(0.75) == "hot"
        assert service._calculate_lead_status(0.90) == "hot"

    def test_lead_status_active(self):
        """Purchase intent 0.35-0.74 maps to 'active' status."""
        service = CopilotService()
        assert service._calculate_lead_status(0.35) == "active"
        assert service._calculate_lead_status(0.50) == "active"

    def test_lead_status_warm(self):
        """Purchase intent 0.15-0.34 maps to 'warm' status."""
        service = CopilotService()
        assert service._calculate_lead_status(0.15) == "warm"
        assert service._calculate_lead_status(0.34) == "warm"

    def test_lead_status_new(self):
        """Purchase intent < 0.15 maps to 'new' status."""
        service = CopilotService()
        assert service._calculate_lead_status(0.0) == "new"
        assert service._calculate_lead_status(0.14) == "new"

    def test_copilot_mode_cache_hit(self):
        """Cached copilot mode is returned without DB query."""
        service = CopilotService()
        service._copilot_mode_cache["creator1"] = False
        service._copilot_mode_cache_ttl["creator1"] = time.time()

        # If DB were called, it would fail because we're not mocking it
        # The cache hit should prevent DB access
        with patch("api.database.SessionLocal", side_effect=RuntimeError("should not be called")):
            result = service.is_copilot_enabled("creator1")
        assert result is False


class TestDedupChecks:
    """Test 6: Dedup logic in create_pending_response."""

    @pytest.mark.asyncio
    async def test_dedup_skips_when_platform_message_id_exists(self):
        """create_pending_response skips if user_message_id already in DB."""
        service = CopilotService()
        mock_session = MagicMock()

        # Creator found
        mock_creator = MagicMock()
        mock_creator.id = 1

        # First query().filter_by() = creator lookup
        # Second query().filter() = platform_message_id check → found
        call_count = [0]
        original_query = mock_session.query

        def query_side_effect(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # Creator lookup
                result.filter_by.return_value.first.return_value = mock_creator
            elif call_count[0] == 2:
                # platform_message_id check → found (dedup hit)
                result.filter.return_value.first.return_value = MagicMock(id="existing_msg")
            return result

        mock_session.query.side_effect = query_side_effect

        with patch("api.database.SessionLocal", return_value=mock_session):
            result = await service.create_pending_response(
                creator_id="creator1",
                lead_id="",
                follower_id="ig_123",
                platform="instagram",
                user_message="Hello",
                user_message_id="mid_existing",
                suggested_response="Hi!",
                intent="greeting",
                confidence=0.9,
            )

        # Should return without creating new messages (no session.add calls)
        assert mock_session.add.call_count == 0

    @pytest.mark.asyncio
    async def test_dedup_updates_existing_pending_when_lead_has_one(self):
        """create_pending_response updates existing pending instead of creating new."""
        import uuid

        service = CopilotService()
        mock_session = MagicMock()

        mock_creator = MagicMock()
        mock_creator.id = uuid.uuid4()

        mock_lead = MagicMock()
        mock_lead.id = uuid.uuid4()
        mock_lead.phone = None
        mock_lead.purchase_intent = 0.0
        mock_lead.status = "new"

        mock_existing_pending = MagicMock()
        mock_existing_pending.id = uuid.uuid4()
        mock_existing_pending.content = "old suggestion"

        call_count = [0]

        def query_side_effect(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # Creator lookup
                result.filter_by.return_value.first.return_value = mock_creator
            elif call_count[0] == 2:
                # platform_message_id check → not found
                result.filter.return_value.first.return_value = None
            elif call_count[0] == 3:
                # Lead lookup → found
                result.filter.return_value.first.return_value = mock_lead
            elif call_count[0] == 4:
                # Pending approval check → found (dedup)
                result.filter.return_value.first.return_value = mock_existing_pending
            return result

        mock_session.query.side_effect = query_side_effect

        with (
            patch("api.database.SessionLocal", return_value=mock_session),
            patch("services.lead_scoring.recalculate_lead_score"),
        ):
            result = await service.create_pending_response(
                creator_id="creator1",
                lead_id="",
                follower_id="ig_456",
                platform="instagram",
                user_message="New message",
                user_message_id="mid_new",
                suggested_response="New suggestion",
                intent="question_product",
                confidence=0.8,
            )

        # Should have updated existing pending's content
        assert mock_existing_pending.content == "New suggestion"
        assert mock_existing_pending.suggested_response == "New suggestion"
        # Should have added user message (1 add call for user msg)
        assert mock_session.add.call_count == 1
        # Result should reference existing pending ID
        assert result.id == str(mock_existing_pending.id)
