"""
Tests for resolved_externally feature — learning from creator direct replies.

Tests:
1. _compute_similarity with identical, different, and empty strings
2. auto_discard_pending_for_lead with and without creator_response
3. resolved_externally autolearning confidence
4. Feature flag respect
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.copilot_service import CopilotService


# =========================================================================
# Test: _compute_similarity
# =========================================================================
class TestComputeSimilarity:
    """Test text similarity calculation."""

    def test_compute_similarity_identical(self):
        """Identical strings should return 1.0."""
        service = CopilotService()
        result = service._compute_similarity("Hola, como estas?", "Hola, como estas?")
        assert result == 1.0

    def test_compute_similarity_different(self):
        """Different strings should return 0 < x < 1."""
        service = CopilotService()
        result = service._compute_similarity(
            "Hola! Te cuento sobre el curso de yoga",
            "Buenas! El curso de yoga tiene dos niveles",
        )
        assert 0.0 < result < 1.0

    def test_compute_similarity_completely_different(self):
        """Completely different strings should return a low score."""
        service = CopilotService()
        result = service._compute_similarity("abc", "xyz")
        assert result < 0.5

    def test_compute_similarity_empty(self):
        """Empty strings should return 0.0."""
        service = CopilotService()
        assert service._compute_similarity("", "hello") == 0.0
        assert service._compute_similarity("hello", "") == 0.0
        assert service._compute_similarity("", "") == 0.0
        assert service._compute_similarity(None, "hello") == 0.0
        assert service._compute_similarity("hello", None) == 0.0


# =========================================================================
# Test: auto_discard_pending_for_lead with creator_response
# =========================================================================
class TestAutoDiscardWithCreatorResponse:
    """Test that auto_discard marks as resolved_externally when creator_response is provided."""

    def _make_pending_msg(self, suggested="Bot suggestion here"):
        msg = MagicMock()
        msg.id = "msg-123"
        msg.status = "pending_approval"
        msg.copilot_action = None
        msg.suggested_response = suggested
        msg.content = suggested
        msg.msg_metadata = None
        msg.approved_at = None
        msg.response_time_ms = None
        msg.intent = "greeting"
        msg.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        return msg

    def _make_mock_session(self, pending_msgs):
        mock_session = MagicMock()
        query_chain = MagicMock()
        query_chain.filter.return_value = query_chain
        query_chain.all.return_value = pending_msgs
        mock_session.query.return_value = query_chain
        return mock_session

    def test_auto_discard_with_creator_response(self):
        """When creator_response is provided, should set resolved_externally status."""
        service = CopilotService()
        msg = self._make_pending_msg("Hola! Como te puedo ayudar?")
        mock_session = self._make_mock_session([msg])

        # Patch asyncio.create_task to avoid actual autolearning fire
        with patch("core.copilot_service.asyncio.create_task"):
            count = service.auto_discard_pending_for_lead(
                lead_id="lead-1",
                session=mock_session,
                creator_response="Buenas! Dime en que te ayudo",
                creator_id="test_creator",
            )

        assert count == 1
        assert msg.status == "resolved_externally"
        assert msg.copilot_action == "resolved_externally"
        assert msg.content == "Buenas! Dime en que te ayudo"
        assert msg.approved_at is not None
        assert msg.response_time_ms is not None

        # Check metadata
        meta = msg.msg_metadata
        assert meta["creator_actual_response"] == "Buenas! Dime en que te ayudo"
        assert 0.0 <= meta["similarity_score"] <= 1.0
        assert meta["resolved_source"] == "direct_reply"

    def test_auto_discard_without_creator_response(self):
        """Without creator_response, should keep old behavior (manual_override/discarded)."""
        service = CopilotService()
        msg = self._make_pending_msg()
        mock_session = self._make_mock_session([msg])

        count = service.auto_discard_pending_for_lead(
            lead_id="lead-1",
            session=mock_session,
        )

        assert count == 1
        assert msg.status == "discarded"
        assert msg.copilot_action == "manual_override"

    def test_auto_discard_no_pending(self):
        """When no pending messages exist, should return 0."""
        service = CopilotService()
        mock_session = self._make_mock_session([])

        count = service.auto_discard_pending_for_lead(
            lead_id="lead-1",
            session=mock_session,
            creator_response="test",
            creator_id="creator",
        )

        assert count == 0


# =========================================================================
# Test: resolved_externally autolearning handler
# =========================================================================
class TestResolvedExternallyAutolearning:
    """Test that resolved_externally uses 0.7 confidence in autolearning."""

    @pytest.mark.asyncio
    async def test_resolved_externally_confidence(self):
        """resolved_externally handler should call _store_rule with confidence=0.7."""
        from services.autolearning_analyzer import _handle_resolved_externally

        with patch("services.autolearning_analyzer._llm_extract_rule", new_callable=AsyncMock) as mock_llm, \
             patch("services.autolearning_analyzer._store_rule") as mock_store:
            mock_llm.return_value = {
                "rule_text": "Usar tono mas informal",
                "pattern": "tone_more_casual",
                "example_bad": "Hola, como te puedo ayudar?",
                "example_good": "Buenas! Dime en que te ayudo",
            }

            await _handle_resolved_externally(
                creator_db_id="db-123",
                suggested_response="Hola, como te puedo ayudar?",
                final_response="Buenas! Dime en que te ayudo",
                intent="greeting",
                lead_stage="nuevo",
                relationship_type=None,
                source_message_id="msg-456",
            )

            mock_store.assert_called_once()
            call_kwargs = mock_store.call_args
            # confidence should be 0.7
            assert call_kwargs[1]["confidence"] == 0.7 or call_kwargs[0][2] == 0.7

    @pytest.mark.asyncio
    async def test_resolved_externally_skips_empty(self):
        """Should skip if neither suggested nor final response exist."""
        from services.autolearning_analyzer import _handle_resolved_externally

        with patch("services.autolearning_analyzer._llm_extract_rule", new_callable=AsyncMock) as mock_llm:
            await _handle_resolved_externally(
                creator_db_id="db-123",
                suggested_response=None,
                final_response=None,
                intent="greeting",
                lead_stage="nuevo",
                relationship_type=None,
                source_message_id=None,
            )

            mock_llm.assert_not_called()


# =========================================================================
# Test: Feature flag respect
# =========================================================================
class TestResolvedExternallyFeatureFlag:
    """Test that resolved_externally respects ENABLE_AUTOLEARNING flag."""

    @pytest.mark.asyncio
    async def test_respects_feature_flag(self):
        """When ENABLE_AUTOLEARNING is false, analyze_creator_action should return immediately."""
        from services.autolearning_analyzer import analyze_creator_action

        with patch("services.autolearning_analyzer.ENABLE_AUTOLEARNING", False), \
             patch("services.autolearning_analyzer._handle_resolved_externally", new_callable=AsyncMock) as mock_handler:
            await analyze_creator_action(
                action="resolved_externally",
                creator_id="test",
                creator_db_id="db-123",
                suggested_response="test",
                final_response="test",
            )

            mock_handler.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatches_when_enabled(self):
        """When ENABLE_AUTOLEARNING is true, should dispatch to handler."""
        from services.autolearning_analyzer import analyze_creator_action

        with patch("services.autolearning_analyzer.ENABLE_AUTOLEARNING", True), \
             patch("services.autolearning_analyzer._handle_resolved_externally", new_callable=AsyncMock) as mock_handler:
            await analyze_creator_action(
                action="resolved_externally",
                creator_id="test",
                creator_db_id="db-123",
                suggested_response="bot text",
                final_response="creator text",
                intent="greeting",
                lead_stage="nuevo",
            )

            mock_handler.assert_called_once()
