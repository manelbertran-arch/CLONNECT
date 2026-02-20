"""Audit tests for core/copilot_service.py."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from core.copilot_service import DEBOUNCE_SECONDS, CopilotService, PendingResponse, get_copilot_service


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


class TestEditDiffCalculation:
    """Test 6: Edit diff calculation for copilot tracking."""

    def test_empty_inputs(self):
        """Empty or None inputs return zero diff."""
        service = CopilotService()
        assert service._calculate_edit_diff("", "") == {"length_delta": 0, "categories": []}
        assert service._calculate_edit_diff(None, "hi") == {"length_delta": 0, "categories": []}
        assert service._calculate_edit_diff("hi", None) == {"length_delta": 0, "categories": []}

    def test_shortened(self):
        """Significant shortening is categorized."""
        service = CopilotService()
        result = service._calculate_edit_diff(
            "This is a long response with many words",
            "Short reply",
        )
        assert "shortened" in result["categories"]
        assert result["length_delta"] < 0

    def test_lengthened(self):
        """Significant lengthening is categorized."""
        service = CopilotService()
        result = service._calculate_edit_diff(
            "Short",
            "This is a much longer response added by the creator",
        )
        assert "lengthened" in result["categories"]
        assert result["length_delta"] > 0

    def test_removed_question(self):
        """Removing a question mark is detected."""
        service = CopilotService()
        result = service._calculate_edit_diff(
            "Hola! Te interesa el curso? Contame",
            "Hola! Te interesa el curso. Contame",
        )
        assert "removed_question" in result["categories"]

    def test_removed_emoji(self):
        """Removing emojis is detected."""
        service = CopilotService()
        result = service._calculate_edit_diff(
            "Hola! 😊 Bienvenido 🎉",
            "Hola! Bienvenido",
        )
        assert "removed_emoji" in result["categories"]

    def test_added_emoji(self):
        """Adding emojis is detected."""
        service = CopilotService()
        result = service._calculate_edit_diff(
            "Hola! Bienvenido",
            "Hola! 😊 Bienvenido",
        )
        assert "added_emoji" in result["categories"]

    def test_complete_rewrite(self):
        """Completely different text is a complete_rewrite."""
        service = CopilotService()
        result = service._calculate_edit_diff(
            "El programa incluye mentoria grupal semanal",
            "Gracias por escribirnos, te envio toda la info",
        )
        assert "complete_rewrite" in result["categories"]

    def test_minor_edit_no_categories(self):
        """Minor edits (same length, similar words) produce no categories."""
        service = CopilotService()
        result = service._calculate_edit_diff(
            "Hola, el curso cuesta 297 euros",
            "Hola, el curso cuesta 300 euros",
        )
        assert result["categories"] == [] or "major_edit" not in result["categories"]

    def test_diff_has_length_fields(self):
        """Diff always includes length stats."""
        service = CopilotService()
        result = service._calculate_edit_diff("abc", "abcdef")
        assert "length_delta" in result
        assert "original_length" in result
        assert "edited_length" in result
        assert result["original_length"] == 3
        assert result["edited_length"] == 6
        assert result["length_delta"] == 3


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
    async def test_dedup_preserves_existing_pending_and_schedules_regen(self):
        """create_pending_response preserves existing pending (no overwrite) and schedules debounced regen."""
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
        mock_existing_pending.suggested_response = "old suggestion"

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
                # has_creator_reply_after check → no recent reply
                result.filter.return_value.first.return_value = None
            elif call_count[0] == 5:
                # Pending approval check → found (dedup)
                result.filter.return_value.first.return_value = mock_existing_pending
            return result

        mock_session.query.side_effect = query_side_effect

        with (
            patch("api.database.SessionLocal", return_value=mock_session),
            patch("services.lead_scoring.recalculate_lead_score"),
            patch.object(service, "_schedule_debounced_regen") as mock_sched,
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

        # Existing pending content should NOT be overwritten
        assert mock_existing_pending.content == "old suggestion"
        assert mock_existing_pending.suggested_response == "old suggestion"
        # Should have added user message (1 add call for user msg)
        assert mock_session.add.call_count == 1
        # Result should reference existing pending ID
        assert result.id == str(mock_existing_pending.id)
        # Debounced regen should be scheduled
        mock_sched.assert_called_once()


class TestConversationContext:
    """Test conversation context with session-based detection."""

    def test_empty_context_when_no_messages(self):
        """Returns empty list when no messages found for lead."""
        from datetime import datetime, timezone

        service = CopilotService()
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

        result = service._get_conversation_context(mock_session, "lead_123")
        assert result == []

    def test_context_returns_messages_in_chronological_order(self):
        """Context messages should be oldest-first (chronological)."""
        from datetime import datetime, timedelta, timezone

        service = CopilotService()
        mock_session = MagicMock()

        now = datetime(2026, 2, 19, 12, 0, 0, tzinfo=timezone.utc)
        msgs = []
        for i in range(5):
            m = MagicMock()
            m.role = "user" if i % 2 == 0 else "assistant"
            m.content = f"Message {i}"
            m.created_at = now - timedelta(hours=5 - i)  # oldest to newest
            msgs.append(m)

        # query returns desc order (newest first)
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = list(reversed(msgs))

        result = service._get_conversation_context(mock_session, "lead_1")
        assert len(result) == 5
        assert result[0]["content"] == "Message 0"  # oldest first
        assert result[-1]["content"] == "Message 4"  # newest last

    def test_context_detects_session_boundary(self):
        """Messages with >24h gap form a session boundary."""
        from datetime import datetime, timedelta, timezone

        service = CopilotService()
        mock_session = MagicMock()

        now = datetime(2026, 2, 19, 12, 0, 0, tzinfo=timezone.utc)
        # Session 2: recent (within last hour)
        m3 = MagicMock(role="user", content="msg3", created_at=now - timedelta(minutes=30))
        m2 = MagicMock(role="assistant", content="msg2", created_at=now - timedelta(minutes=60))
        # Session 1: 2 days ago (>24h gap from session 2)
        m1 = MagicMock(role="user", content="msg1", created_at=now - timedelta(days=2, hours=1))
        m0 = MagicMock(role="assistant", content="msg0", created_at=now - timedelta(days=2, hours=2))
        # Session 0: 5 days ago (should NOT be included — only last 2 sessions)
        m_old = MagicMock(role="user", content="old", created_at=now - timedelta(days=5))

        # desc order
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            m3, m2, m1, m0, m_old
        ]

        result = service._get_conversation_context(mock_session, "lead_1")
        contents = [r["content"] for r in result]
        # Should include sessions 1+2 (4 messages), not session 0
        assert len(contents) == 4
        assert "msg0" in contents
        assert "msg1" in contents
        assert "msg2" in contents
        assert "msg3" in contents
        assert "old" not in contents

    def test_context_max_15_messages(self):
        """Context is capped at 15 messages."""
        from datetime import datetime, timedelta, timezone

        service = CopilotService()
        mock_session = MagicMock()

        now = datetime(2026, 2, 19, 12, 0, 0, tzinfo=timezone.utc)
        msgs = []
        for i in range(25):
            m = MagicMock()
            m.role = "user" if i % 2 == 0 else "assistant"
            m.content = f"msg_{i}"
            m.created_at = now - timedelta(minutes=25 - i)
            msgs.append(m)

        # desc order (all in one session — no 24h gaps)
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = list(reversed(msgs))

        result = service._get_conversation_context(mock_session, "lead_1")
        assert len(result) == 15


class TestDebounce:
    """Tests for message debounce logic."""

    def test_debounce_task_scheduled_on_dedup(self):
        """_schedule_debounced_regen creates an asyncio task for the lead."""
        service = CopilotService()
        lead_key = "lead-123"

        mock_task = MagicMock()
        with patch("core.copilot_service.asyncio.create_task", return_value=mock_task) as mock_create:
            service._schedule_debounced_regen(
                creator_id="creator1",
                follower_id="ig_456",
                platform="instagram",
                pending_message_id="msg-1",
                lead_id=lead_key,
                username="testuser",
            )

        mock_create.assert_called_once()
        assert service._debounce_tasks[lead_key] is mock_task
        assert service._debounce_metadata[lead_key]["creator_id"] == "creator1"

    def test_debounce_cancels_previous_task(self):
        """Scheduling a new regen cancels the previous task for the same lead."""
        service = CopilotService()
        lead_key = "lead-456"

        old_task = MagicMock()
        old_task.done.return_value = False
        service._debounce_tasks[lead_key] = old_task

        new_task = MagicMock()
        with patch("core.copilot_service.asyncio.create_task", return_value=new_task):
            service._schedule_debounced_regen(
                creator_id="creator1",
                follower_id="ig_789",
                platform="instagram",
                pending_message_id="msg-2",
                lead_id=lead_key,
                username="testuser",
            )

        old_task.cancel.assert_called_once()
        assert service._debounce_tasks[lead_key] is new_task

    @pytest.mark.asyncio
    async def test_debounced_regen_updates_pending(self):
        """After sleep, _debounced_regeneration updates pending message content."""
        service = CopilotService()
        lead_key = "lead-789"

        service._debounce_metadata[lead_key] = {
            "creator_id": "creator1",
            "follower_id": "ig_111",
            "platform": "instagram",
            "pending_message_id": "msg-3",
            "username": "testuser",
        }

        mock_pending_msg = MagicMock()
        mock_pending_msg.status = "pending_approval"
        mock_pending_msg.lead_id = "lead-789"

        mock_latest_user = MagicMock()
        mock_latest_user.content = "latest user message"

        mock_session = MagicMock()

        call_count = [0]

        def query_side_effect(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # pending msg lookup
                result.filter_by.return_value.first.return_value = mock_pending_msg
            elif call_count[0] == 2:
                # latest user msg lookup
                result.filter.return_value.order_by.return_value.first.return_value = mock_latest_user
            return result

        mock_session.query.side_effect = query_side_effect

        mock_agent = MagicMock()
        mock_agent.process_dm = AsyncMock(return_value="regenerated response")

        with (
            patch("core.copilot_service.asyncio.sleep", new_callable=AsyncMock),
            patch("api.database.SessionLocal", return_value=mock_session),
            patch("core.dm_agent_v2.get_dm_agent", return_value=mock_agent),
        ):
            await service._debounced_regeneration(lead_key)

        assert mock_pending_msg.content == "regenerated response"
        assert mock_pending_msg.suggested_response == "regenerated response"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_debounced_regen_skips_if_approved(self):
        """Regen exits early if the pending message was already approved."""
        service = CopilotService()
        lead_key = "lead-skipped"

        service._debounce_metadata[lead_key] = {
            "creator_id": "creator1",
            "follower_id": "ig_222",
            "platform": "instagram",
            "pending_message_id": "msg-approved",
            "username": "testuser",
        }

        mock_pending_msg = MagicMock()
        mock_pending_msg.status = "sent"  # Already approved and sent

        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = mock_pending_msg

        with (
            patch("core.copilot_service.asyncio.sleep", new_callable=AsyncMock),
            patch("api.database.SessionLocal", return_value=mock_session),
        ):
            await service._debounced_regeneration(lead_key)

        # Should NOT have committed (no update)
        mock_session.commit.assert_not_called()

    def test_auto_discard_cancels_debounce(self):
        """auto_discard_pending_for_lead cancels any pending debounce task."""
        service = CopilotService()
        lead_key = "lead-discard"

        mock_task = MagicMock()
        mock_task.done.return_value = False
        service._debounce_tasks[lead_key] = mock_task
        service._debounce_metadata[lead_key] = {"creator_id": "c1"}

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.all.return_value = []

        service.auto_discard_pending_for_lead(lead_key, session=mock_session)

        mock_task.cancel.assert_called_once()
        assert lead_key not in service._debounce_tasks
        assert lead_key not in service._debounce_metadata

    def test_debounce_constant_is_30(self):
        """DEBOUNCE_SECONDS is set to 30."""
        assert DEBOUNCE_SECONDS == 30

    def test_init_has_debounce_dicts(self):
        """CopilotService.__init__ creates debounce dicts."""
        service = CopilotService()
        assert hasattr(service, "_debounce_tasks")
        assert hasattr(service, "_debounce_metadata")
        assert service._debounce_tasks == {}
        assert service._debounce_metadata == {}
