"""Tests for Commitment Tracker and Relationship Adapter.

Part of ECHO Engine Sprint 4 — Harmonize layer.
"""
import pytest
from datetime import datetime, timedelta, timezone


# =========================================================================
# COMMITMENT TRACKER TESTS
# =========================================================================

class TestCommitmentDetection:
    """Test regex-based commitment detection."""

    def test_delivery_commitment(self):
        from services.commitment_tracker import detect_commitments_regex
        results = detect_commitments_regex("Dale, te envío el link mañana")
        assert len(results) >= 1
        assert results[0]["commitment_type"] == "delivery"
        assert results[0]["due_days"] == 1  # mañana

    def test_info_request_commitment(self):
        from services.commitment_tracker import detect_commitments_regex
        results = detect_commitments_regex("Te confirmo la disponibilidad esta semana")
        assert len(results) >= 1
        assert results[0]["commitment_type"] == "info_request"

    def test_meeting_commitment(self):
        from services.commitment_tracker import detect_commitments_regex
        results = detect_commitments_regex("Quedamos el martes a las 10 para revisar")
        assert len(results) >= 1
        assert results[0]["commitment_type"] == "meeting"

    def test_follow_up_commitment(self):
        from services.commitment_tracker import detect_commitments_regex
        results = detect_commitments_regex("Te escribo mañana con más detalles")
        assert len(results) >= 1
        assert results[0]["commitment_type"] == "follow_up"
        assert results[0]["due_days"] == 1

    def test_promise_commitment(self):
        from services.commitment_tracker import detect_commitments_regex
        results = detect_commitments_regex("Sin falta te paso la info")
        assert len(results) >= 1

    def test_no_commitment_in_user_message(self):
        from services.commitment_tracker import detect_commitments_regex
        results = detect_commitments_regex("Te envío el link mañana", sender="user")
        assert len(results) == 0

    def test_no_commitment_in_normal_message(self):
        from services.commitment_tracker import detect_commitments_regex
        results = detect_commitments_regex("Hola! Cómo estás?")
        assert len(results) == 0

    def test_temporal_extraction_hoy(self):
        from services.commitment_tracker import detect_commitments_regex
        results = detect_commitments_regex("Te paso el link hoy sin falta")
        assert len(results) >= 1
        # Should find "hoy" = 0 days
        due_days = [r["due_days"] for r in results if r["due_days"] is not None]
        assert 0 in due_days

    def test_temporal_extraction_esta_semana(self):
        from services.commitment_tracker import detect_commitments_regex
        results = detect_commitments_regex("Te mando la info esta semana")
        assert len(results) >= 1
        assert results[0]["due_days"] == 5

    def test_context_extraction(self):
        """Commitment text should include context around the match."""
        from services.commitment_tracker import detect_commitments_regex
        msg = "Perfecto! Entonces te envío el PDF del curso mañana a primera hora"
        results = detect_commitments_regex(msg)
        assert len(results) >= 1
        # Context should include surrounding text
        assert len(results[0]["commitment_text"]) > 10

    def test_dedup_same_type(self):
        """Only one commitment per type per message."""
        from services.commitment_tracker import detect_commitments_regex
        msg = "Te envío el link y te mando también el PDF"
        results = detect_commitments_regex(msg)
        types = [r["commitment_type"] for r in results]
        # Should not have duplicate "delivery" type
        assert len(set(types)) == len(types)


class TestCommitmentPendingText:
    """Test pending text formatting (without DB)."""

    def test_format_with_due_dates(self):
        """Test the text formatting logic directly."""
        from services.commitment_tracker import CommitmentTrackerService
        from unittest.mock import MagicMock, patch

        now = datetime.now(timezone.utc)
        mock_commitments = [
            MagicMock(
                commitment_text="te envío el link del curso",
                created_at=now - timedelta(days=1),
                due_date=now + timedelta(days=1),
            ),
            MagicMock(
                commitment_text="te confirmo la disponibilidad",
                created_at=now,
                due_date=None,
            ),
        ]

        tracker = CommitmentTrackerService()
        with patch.object(tracker, "get_pending_for_lead", return_value=mock_commitments):
            text = tracker.get_pending_text("lead-uuid")

        assert "ayer" in text
        assert "hoy" in text
        assert "link" in text.lower()
        assert "confirmo" in text.lower()


# =========================================================================
# RELATIONSHIP ADAPTER TESTS
# =========================================================================

class TestRelationshipAdapter:
    """Test RelationshipAdapter behavior."""

    def test_nuevo_lead_context(self):
        from services.relationship_adapter import RelationshipAdapter
        adapter = RelationshipAdapter()
        ctx = adapter.get_relational_context(lead_status="nuevo")

        assert ctx.lead_status == "nuevo"
        assert "NUEVO" in ctx.prompt_instructions
        assert ctx.sales_push_score == 0.1
        assert ctx.warmth_score == 0.5
        assert ctx.llm_temperature == 0.6
        assert ctx.max_questions == 1

    def test_caliente_lead_context(self):
        from services.relationship_adapter import RelationshipAdapter
        adapter = RelationshipAdapter()
        ctx = adapter.get_relational_context(lead_status="caliente")

        assert ctx.lead_status == "caliente"
        assert ctx.sales_push_score == 0.7
        assert ctx.warmth_score == 0.85
        assert ctx.llm_max_tokens == 300

    def test_cliente_lead_context(self):
        from services.relationship_adapter import RelationshipAdapter
        adapter = RelationshipAdapter()
        ctx = adapter.get_relational_context(lead_status="cliente")

        assert ctx.lead_status == "cliente"
        assert ctx.warmth_score == 0.95
        assert "YA ES CLIENTE" in ctx.prompt_instructions

    def test_fantasma_lead_context(self):
        from services.relationship_adapter import RelationshipAdapter
        adapter = RelationshipAdapter()
        ctx = adapter.get_relational_context(lead_status="fantasma")

        assert ctx.lead_status == "fantasma"
        assert ctx.sales_push_score == 0.0
        assert "SIN RESPONDER" in ctx.prompt_instructions

    def test_unknown_status_defaults_to_nuevo(self):
        from services.relationship_adapter import RelationshipAdapter
        adapter = RelationshipAdapter()
        ctx = adapter.get_relational_context(lead_status="INVALID_STATUS")

        assert ctx.lead_status == "nuevo"

    def test_family_override_no_sales(self):
        from services.relationship_adapter import RelationshipAdapter
        adapter = RelationshipAdapter()
        ctx = adapter.get_relational_context(
            lead_status="caliente",
            relationship_type="FAMILIA",
        )

        assert "NINGÚN intento de venta" in ctx.prompt_instructions

    def test_commitment_injection(self):
        from services.relationship_adapter import RelationshipAdapter
        adapter = RelationshipAdapter()
        ctx = adapter.get_relational_context(
            lead_status="interesado",
            commitment_text="- [ayer] te envío el link del curso (vence hoy)",
        )

        assert "COMPROMISOS PENDIENTES" in ctx.prompt_instructions
        assert "link del curso" in ctx.prompt_instructions

    def test_memory_injection(self):
        from services.relationship_adapter import RelationshipAdapter
        adapter = RelationshipAdapter()
        ctx = adapter.get_relational_context(
            lead_status="cliente",
            lead_memory_summary="Le interesa yoga y meditación. Compró el curso básico.",
        )

        assert "RECUERDA:" in ctx.prompt_instructions
        assert "yoga" in ctx.prompt_instructions

    def test_lead_name_personalization(self):
        from services.relationship_adapter import RelationshipAdapter
        adapter = RelationshipAdapter()
        ctx = adapter.get_relational_context(
            lead_status="interesado",
            lead_name="María",
            message_count=10,
        )

        assert "María" in ctx.prompt_instructions

    def test_lead_name_not_shown_early(self):
        """Don't use name in early messages (< 3)."""
        from services.relationship_adapter import RelationshipAdapter
        adapter = RelationshipAdapter()
        ctx = adapter.get_relational_context(
            lead_status="nuevo",
            lead_name="María",
            message_count=2,
        )

        assert "María" not in ctx.prompt_instructions

    def test_style_profile_modulates_emoji(self):
        from services.relationship_adapter import (
            RelationshipAdapter, StyleProfile
        )
        adapter = RelationshipAdapter()

        # High emoji creator
        sp_high = StyleProfile(emoji_ratio=0.5)
        ctx_high = adapter.get_relational_context(
            lead_status="nuevo", style_profile=sp_high
        )

        # Low emoji creator
        sp_low = StyleProfile(emoji_ratio=0.02)
        ctx_low = adapter.get_relational_context(
            lead_status="nuevo", style_profile=sp_low
        )

        # Same profile (nuevo, emoji_multiplier=0.7), different emoji targets
        assert ctx_high.emoji_target_ratio > ctx_low.emoji_target_ratio

    def test_prohibitions_included(self):
        from services.relationship_adapter import RelationshipAdapter
        adapter = RelationshipAdapter()
        ctx = adapter.get_relational_context(lead_status="nuevo")

        assert len(ctx.prohibited_actions) > 0
        assert "PROHIBIDO" in ctx.prompt_instructions


class TestStyleProfileConverter:
    """Test conversion from Style Analyzer output to StyleProfile dataclass."""

    def test_conversion_from_analyzer_data(self):
        from services.relationship_adapter import style_profile_from_analyzer

        analyzer_output = {
            "quantitative": {
                "length": {"char_mean": 38.5},
                "emoji": {"avg_per_message": 0.58, "top_20": [["🔥", 45], ["❤️", 32]]},
                "punctuation": {"question_pct": 12.1, "exclamation_pct": 35.2},
                "muletillas_top_20": [["dale", 22], ["claro", 18]],
            }
        }

        sp = style_profile_from_analyzer(analyzer_output)
        assert sp is not None
        assert sp.avg_message_length == 38.5
        assert sp.emoji_ratio == 0.58
        assert "🔥" in sp.emoji_favorites
        assert "dale" in sp.muletillas

    def test_conversion_handles_none(self):
        from services.relationship_adapter import style_profile_from_analyzer
        assert style_profile_from_analyzer(None) is None

    def test_conversion_handles_empty(self):
        from services.relationship_adapter import style_profile_from_analyzer
        # Empty dict is falsy, so returns None (same as None input)
        sp = style_profile_from_analyzer({})
        assert sp is None
