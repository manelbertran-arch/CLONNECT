"""
End-to-end tests for the Copilot + Autolearning pipeline.

Tests the complete flow from DM processing → copilot pending →
approve/edit/discard → tracking → confidence scoring → pattern detection.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.autolearning_evaluator import (
    _detect_daily_patterns,
    _generate_weekly_recommendations,
)
from core.confidence_scorer import calculate_confidence
from core.copilot_service import CopilotService
from core.response_fixes import apply_all_response_fixes, remove_catchphrases


# =========================================================================
# E2E Test 1: Full copilot flow — create → approve → memory update
# =========================================================================
class TestCopilotFullFlow:
    """Test the complete copilot approve/edit/discard lifecycle."""

    def test_edit_diff_calculated_on_approval(self):
        """When a creator edits a suggestion, edit_diff is computed."""
        service = CopilotService()
        diff = service._calculate_edit_diff(
            "El programa incluye mentoria grupal semanal y contenido exclusivo",
            "Hola! Te cuento sobre el programa",
        )
        assert isinstance(diff, dict)
        assert "length_delta" in diff
        assert "categories" in diff
        assert diff["length_delta"] < 0  # Shortened

    def test_approval_tracking_fields_set(self):
        """Approved message should have copilot_action and response_time_ms."""
        # Simulate the tracking that happens in approve_response
        msg = MagicMock()
        msg.status = "pending_approval"
        msg.suggested_response = "Hola! El curso tiene 20 horas."
        msg.content = "Hola! El curso tiene 20 horas."
        msg.created_at = datetime.now(timezone.utc) - timedelta(minutes=2)

        # Simulate approve logic
        now = datetime.now(timezone.utc)
        msg.copilot_action = "approved"
        delta = now - msg.created_at
        msg.response_time_ms = int(delta.total_seconds() * 1000)

        assert msg.copilot_action == "approved"
        assert msg.response_time_ms > 0

    def test_discard_tracking_fields_set(self):
        """Discarded message should have copilot_action set."""
        msg = MagicMock()
        msg.created_at = datetime.now(timezone.utc) - timedelta(seconds=30)

        now = datetime.now(timezone.utc)
        msg.copilot_action = "discarded"
        delta = now - msg.created_at
        msg.response_time_ms = int(delta.total_seconds() * 1000)

        assert msg.copilot_action == "discarded"
        assert msg.response_time_ms >= 30000


# =========================================================================
# E2E Test 2: Confidence scoring integrates correctly
# =========================================================================
class TestConfidenceScoringIntegration:
    """Test confidence scoring across all response types."""

    def test_pool_match_greeting_highest(self):
        """Pool-matched greeting should have highest confidence."""
        score = calculate_confidence(
            intent="greeting",
            response_text="Hola! Bienvenido, en qué te puedo ayudar?",
            response_type="pool_match",
        )
        assert score >= 0.8

    def test_llm_objection_moderate(self):
        """LLM-generated objection response has moderate confidence."""
        score = calculate_confidence(
            intent="objection",
            response_text="Entiendo tu preocupación. El programa tiene garantía de devolución.",
            response_type="llm_generation",
        )
        assert 0.4 <= score <= 0.8

    def test_blacklisted_text_lowers_confidence(self):
        """Response with blacklisted patterns scores lower than clean."""
        clean_score = calculate_confidence(
            "greeting",
            "Hola! Bienvenido al perfil.",
            "llm_generation",
        )
        dirty_score = calculate_confidence(
            "greeting",
            "Soy Stefano. Hola! COMPRA AHORA.",
            "llm_generation",
        )
        assert dirty_score < clean_score

    def test_very_long_response_penalized(self):
        """Extremely long responses get lower confidence."""
        short_score = calculate_confidence(
            "greeting",
            "Hola! Bienvenido, contame en qué te puedo ayudar.",
            "llm_generation",
        )
        long_score = calculate_confidence(
            "greeting",
            "A" * 500,
            "llm_generation",
        )
        assert long_score < short_score


# =========================================================================
# E2E Test 3: Response fixes → confidence scoring pipeline
# =========================================================================
class TestResponseFixesAndConfidence:
    """Test that response fixes clean up text before confidence scoring."""

    def test_catchphrase_removed_before_scoring(self):
        """Catchphrase is removed by response_fixes."""
        raw = "Hola! Qué te llamó la atención? Me encanta ayudarte!"
        fixed = remove_catchphrases(raw)
        assert "llamó la atención" not in fixed
        assert "Me encanta ayudarte" in fixed

    def test_broken_link_fixed_before_scoring(self):
        """Broken links are fixed by response_fixes."""
        raw = "Mira ://www.example.com para más info"
        fixed = apply_all_response_fixes(raw)
        assert "https://www.example.com" in fixed

    def test_identity_claim_passthrough(self):
        """Fix 4 (identity rewrite) is disabled — response passes through unchanged."""
        # Fix 4 disabled 2026-03-26: breaks first-person creators (Iris). Re-enable
        # conditionally if a creator ever needs bot_mode="assistant".
        raw = "Soy Stefano y te voy a ayudar con todo"
        fixed = apply_all_response_fixes(raw, creator_name="Stefano")
        assert "Stefano" in fixed  # identity preserved, not rewritten

    def test_clean_response_confidence_is_high(self):
        """A clean, post-processed response should score well."""
        fixed = apply_all_response_fixes(
            "Hola! Te cuento que el programa incluye 20 horas de contenido."
        )
        score = calculate_confidence(
            intent="greeting",
            response_text=fixed,
            response_type="llm_generation",
        )
        assert score >= 0.6


# =========================================================================
# E2E Test 4: Autolearning pattern detection accuracy
# =========================================================================
class TestAutolearningPatterns:
    """Test that pattern detection works across realistic data."""

    def test_shortening_pattern_from_real_edits(self):
        """Simulate real edit patterns where creator consistently shortens."""
        mock_session = MagicMock()
        since = datetime(2026, 2, 18, 0, 0, tzinfo=timezone.utc)
        until = datetime(2026, 2, 19, 0, 0, tzinfo=timezone.utc)

        # Simulate 6 edits where 4 are shortened
        diffs = [
            ({"length_delta": -45, "categories": ["shortened"]},),
            ({"length_delta": -30, "categories": ["shortened"]},),
            ({"length_delta": -20, "categories": ["shortened"]},),
            ({"length_delta": -50, "categories": ["shortened", "removed_question"]},),
            ({"length_delta": 5, "categories": []},),
            ({"length_delta": 10, "categories": ["lengthened"]},),
        ]
        mock_session.query.return_value.join.return_value.filter.return_value.all.return_value = diffs

        patterns = _detect_daily_patterns(mock_session, "c1", since, until)
        pattern_types = [p["type"] for p in patterns]
        assert "consistent_shortening" in pattern_types

        # Check avg_delta is negative
        shortening = next(p for p in patterns if p["type"] == "consistent_shortening")
        assert shortening["avg_delta"] < 0
        assert shortening["frequency"] >= 0.5

    def test_weekly_trend_detection(self):
        """Detect improving trend when approval rate increases over the week."""
        # First 3 days: low approval; last 3 days: high approval
        evals = []
        for i, rate in enumerate([0.4, 0.45, 0.5, 0.75, 0.8, 0.85]):
            ev = MagicMock()
            ev.metrics = {"approval_rate": rate, "total_actions": 10}
            ev.patterns = []
            evals.append(ev)

        metrics = {
            "avg_approval_rate": 0.625,
            "avg_edit_rate": 0.2,
            "avg_discard_rate": 0.175,
            "total_actions": 60,
        }
        recs = _generate_weekly_recommendations(evals, metrics)
        rec_types = [r["type"] for r in recs]
        assert "improving_trend" in rec_types

    def test_degrading_trend_detection(self):
        """Detect degrading trend when approval rate drops."""
        evals = []
        for rate in [0.9, 0.85, 0.8, 0.5, 0.45, 0.4]:
            ev = MagicMock()
            ev.metrics = {"approval_rate": rate, "total_actions": 10}
            ev.patterns = []
            evals.append(ev)

        metrics = {
            "avg_approval_rate": 0.65,
            "avg_edit_rate": 0.2,
            "avg_discard_rate": 0.15,
            "total_actions": 60,
        }
        recs = _generate_weekly_recommendations(evals, metrics)
        rec_types = [r["type"] for r in recs]
        assert "degrading_trend" in rec_types


# =========================================================================
# E2E Test 5: Dedup + tracking work together
# =========================================================================
class TestDedupAndTracking:
    """Test that dedup checks don't interfere with tracking."""

    def test_edit_diff_for_empty_original(self):
        """Edit diff handles edge case where original is empty."""
        service = CopilotService()
        diff = service._calculate_edit_diff("", "New content from creator")
        assert diff["categories"] == []
        assert diff["length_delta"] == 0

    def test_edit_diff_for_identical_text(self):
        """Edit diff for identical text has zero delta and no categories."""
        service = CopilotService()
        diff = service._calculate_edit_diff(
            "Same text here",
            "Same text here",
        )
        assert diff["length_delta"] == 0
        assert diff["categories"] == []

    def test_manual_override_diff_captures_full_rewrite(self):
        """Manual override with completely different text is a complete_rewrite."""
        service = CopilotService()
        diff = service._calculate_edit_diff(
            "El programa incluye mentoria grupal semanal y contenido exclusivo",
            "Gracias por escribirnos, te envio la info completa por correo",
        )
        assert "complete_rewrite" in diff["categories"]

    @pytest.mark.asyncio
    async def test_create_pending_dedup_protects_tracking(self):
        """Platform message dedup returns early but doesn't crash tracking."""
        service = CopilotService()
        mock_session = MagicMock()
        mock_creator = MagicMock()
        mock_creator.id = 1

        call_count = [0]
        def query_side(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.filter_by.return_value.first.return_value = mock_creator
            elif call_count[0] == 2:
                result.filter.return_value.first.return_value = MagicMock(id="dup")
            return result

        mock_session.query.side_effect = query_side

        with patch("api.database.SessionLocal", return_value=mock_session):
            result = await service.create_pending_response(
                creator_id="c1", lead_id="", follower_id="ig_123",
                platform="instagram", user_message="Hello",
                user_message_id="existing_mid",
                suggested_response="Hi!", intent="greeting", confidence=0.9,
            )

        # Should return without error, tracking fields don't apply to deduped messages
        assert result is not None
        assert mock_session.add.call_count == 0


# =========================================================================
# E2E Test 6: Full pipeline — response fixes → confidence → copilot tracking
# =========================================================================
class TestFullPipelineIntegration:
    """Test the entire pipeline from raw response to tracked copilot action."""

    def test_pipeline_flow(self):
        """Simulate: raw response → fixes → confidence → edit diff."""
        # Step 1: Raw bot response
        raw_response = (
            "Soy Stefano. El precio es 297? "
            "Mira ://www.example.com. COMPRA AHORA!"
        )

        # Step 2: Apply response fixes
        fixed = apply_all_response_fixes(raw_response, creator_name="Stefano")

        # Verify fixes applied
        # FIX 4 disabled (2026-03-26) — identity preserved, not rewritten
        assert "Stefano" in fixed
        assert "COMPRA AHORA" not in fixed
        assert "https://www.example.com" in fixed

        # Step 3: Calculate confidence on the fixed response
        confidence = calculate_confidence(
            intent="interest_soft",
            response_text=fixed,
            response_type="llm_generation",
        )
        assert 0.0 <= confidence <= 1.0

        # Step 4: Creator edits the response
        creator_edit = "Hola! Te paso el link del programa: https://www.example.com"

        # Step 5: Calculate edit diff
        service = CopilotService()
        diff = service._calculate_edit_diff(fixed, creator_edit)
        assert isinstance(diff, dict)
        assert "length_delta" in diff
        assert "categories" in diff

    def test_catchphrase_removal_pipeline(self):
        """Catchphrase is removed, then clean text scores well."""
        raw = "Hola! ¿Qué te llamó la atención? Contame de lo que comparto!"
        fixed = apply_all_response_fixes(raw)
        assert "llamó la atención" not in fixed

        # Clean text should have reasonable confidence
        score = calculate_confidence(
            intent="greeting",
            response_text=fixed,
            response_type="pool_match",
        )
        assert score >= 0.7

    def test_error_response_pipeline(self):
        """Error responses get low confidence and should be tracked."""
        error_text = "Lo siento, hubo un error procesando tu mensaje."
        confidence = calculate_confidence(
            intent="ERROR",
            response_text=error_text,
            response_type="error_fallback",
        )
        # Error responses should have below-average confidence
        assert confidence < 0.5

        # If creator discards, diff is irrelevant
        service = CopilotService()
        diff = service._calculate_edit_diff(error_text, "")
        assert diff["categories"] == []
