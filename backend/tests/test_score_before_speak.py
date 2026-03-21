"""Tests for Score Before You Speak (SBS) — PPA extension."""

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.reasoning.ppa import (
    ALIGNMENT_THRESHOLD,
    PPAResult,
    SBSResult,
    compute_alignment_score,
    score_before_speak,
)

# Minimal calibration for testing
CALIBRATION = {
    "baseline": {
        "median_length": 35,
        "emoji_pct": 18.0,
        "exclamation_pct": 12.0,
        "soft_max": 60,
    },
    "few_shot_examples": [
        {"user_message": "Hola que tal", "response": "Holaa reina", "context": "saludo"},
        {"user_message": "Quiero reservar", "response": "Ya estas flor", "context": "lead"},
        {"user_message": "Bon dia", "response": "Bon diaa cuca", "context": "saludo"},
    ],
}


class TestComputeAlignmentScore:
    """Tests for the alignment scoring function."""

    def test_good_short_response_scores_high(self):
        """A short, informal response with emoji should score well."""
        score, dims = compute_alignment_score(
            "Holaa reina! Com va tot?", CALIBRATION, "ca"
        )
        assert score >= 0.7, f"Expected >= 0.7, got {score}"
        assert dims["length"] == 1.0
        assert dims["forbidden"] == 1.0
        assert dims["formality"] == 1.0

    def test_long_formal_response_scores_low(self):
        """A long, formal bot-like response should score low."""
        score, dims = compute_alignment_score(
            "Hola, estoy aquí para ayudarte con cualquier consulta que tengas. "
            "No dudes en escribirme si necesitas algo más. Estaré encantada de asistirte.",
            CALIBRATION, "es"
        )
        assert score < 0.5, f"Expected < 0.5, got {score}"
        assert dims["forbidden"] == 0.0  # Contains forbidden phrases
        assert dims["length"] == 0.2  # Way too long

    def test_forbidden_phrase_zeroes_dimension(self):
        """Any forbidden phrase should zero out that dimension."""
        score, dims = compute_alignment_score(
            "No dudes en preguntarme!", CALIBRATION, "es"
        )
        assert dims["forbidden"] == 0.0

    def test_formal_register_zeroes_dimension(self):
        """Formal markers like 'usted' should zero formality."""
        score, dims = compute_alignment_score(
            "Estimada cliente, le informo que...", CALIBRATION, "es"
        )
        assert dims["formality"] == 0.0

    def test_emoji_presence_affects_score(self):
        """Response with emoji should score higher on emoji dimension."""
        score_with, dims_with = compute_alignment_score("Hola nena! 😂", CALIBRATION, "es")
        score_without, dims_without = compute_alignment_score("Hola nena!", CALIBRATION, "es")
        assert dims_with["emoji"] > dims_without["emoji"]


class TestScoreBeforeSpeak:
    """Tests for the full SBS flow."""

    @pytest.mark.asyncio
    async def test_good_response_passes_through(self):
        """A well-aligned response should pass through with 0 extra calls."""
        result = await score_before_speak(
            response="Holaa reina! Com va tot? 😂",
            calibration=CALIBRATION,
            system_prompt="",
            user_prompt="",
        )
        assert isinstance(result, SBSResult)
        assert result.path == "pass"
        assert result.total_llm_calls == 0
        assert result.alignment_score >= ALIGNMENT_THRESHOLD

    @pytest.mark.asyncio
    async def test_bad_response_triggers_refinement(self):
        """A misaligned response should trigger PPA refinement."""
        # Mock apply_ppa to simulate successful refinement
        refined_result = PPAResult(
            response="Tranqui flor 😂",
            alignment_score=0.85,
            was_refined=True,
            scores={"length": 1.0, "emoji": 1.0, "language": 1.0, "forbidden": 1.0, "formality": 1.0},
        )
        with patch("core.reasoning.ppa.apply_ppa", new_callable=AsyncMock, return_value=refined_result):
            result = await score_before_speak(
                response="Estimada cliente, estoy aquí para ayudarte con cualquier consulta que tengas sobre nuestros servicios.",
                calibration=CALIBRATION,
                system_prompt="",
                user_prompt="",
            )
        assert result.path == "refined"
        assert result.total_llm_calls >= 1
        assert result.response == "Tranqui flor 😂"

    @pytest.mark.asyncio
    async def test_failed_refinement_triggers_retry(self):
        """If PPA refinement is still below threshold, retry generation."""
        # Mock apply_ppa returning low score
        bad_ppa = PPAResult(
            response="Lo siento mucho, no puedo ayudarte",
            alignment_score=0.4,
            was_refined=True,
            scores={"length": 0.5, "emoji": 0.4, "language": 0.6, "forbidden": 0.0, "formality": 1.0},
        )
        # Mock retry generation returning a better response
        retry_llm_result = {"content": "Tranqui nena 😂😂"}

        with patch("core.reasoning.ppa.apply_ppa", new_callable=AsyncMock, return_value=bad_ppa):
            with patch("core.providers.gemini_provider.generate_dm_response", new_callable=AsyncMock, return_value=retry_llm_result):
                result = await score_before_speak(
                    response="Lo siento, no puedo ayudarte con eso. Estoy aquí para lo que necesites.",
                    calibration=CALIBRATION,
                    system_prompt="system",
                    user_prompt="user",
                )

        assert result.path == "retried"
        assert result.total_llm_calls >= 2
        assert len(result.candidates) == 3  # initial + ppa + retry

    @pytest.mark.asyncio
    async def test_no_calibration_passes_through(self):
        """Without calibration data, should pass through immediately."""
        result = await score_before_speak(
            response="Whatever response",
            calibration={},
            system_prompt="",
            user_prompt="",
        )
        assert result.path == "pass"
        assert result.total_llm_calls == 0
        assert result.alignment_score == 1.0

    @pytest.mark.asyncio
    async def test_candidates_tracked(self):
        """All candidate responses should be tracked in result.candidates."""
        # Force path through to retry
        bad_ppa = PPAResult(
            response="Still bad", alignment_score=0.3,
            was_refined=True, scores={},
        )
        retry_result = {"content": "Ok cuca 😂"}

        with patch("core.reasoning.ppa.apply_ppa", new_callable=AsyncMock, return_value=bad_ppa):
            with patch("core.providers.gemini_provider.generate_dm_response", new_callable=AsyncMock, return_value=retry_result):
                result = await score_before_speak(
                    response="Estimada cliente, estoy aquí para ayudarte con cualquier consulta que tengas sobre nuestros servicios de fitness y bienestar personal.",
                    calibration=CALIBRATION,
                    system_prompt="sys",
                    user_prompt="usr",
                )

        # Should have initial + ppa_refined + retry_t05
        sources = [c["source"] for c in result.candidates]
        assert "initial" in sources
        assert result.path == "retried"
        # Best candidate should be selected by highest score
        best_score = max(c["score"] for c in result.candidates)
        assert result.alignment_score == best_score
