"""Tests for Post Persona Alignment (PPA) module."""

import asyncio
import json
import os
import pytest
from unittest.mock import AsyncMock, patch

from core.reasoning.ppa import (
    compute_alignment_score,
    find_similar_examples,
    build_refinement_prompt,
    apply_ppa,
    FORBIDDEN_PHRASES,
    PPAResult,
)

# Load real calibration for testing
CALIBRATION_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "calibrations", "iris_bertran.json"
)

@pytest.fixture
def calibration():
    with open(CALIBRATION_PATH) as f:
        return json.load(f)


class TestAlignmentScore:
    """Test compute_alignment_score."""

    def test_generic_response_scores_low(self, calibration):
        """Generic bot response should score below 0.7."""
        score, dims = compute_alignment_score(
            "Hola, cuéntame en qué puedo ayudarte. Estoy aquí para resolver todas tus dudas.",
            calibration,
        )
        assert score < 0.7, f"Generic response scored {score}, expected < 0.7"
        assert dims["forbidden"] == 0.0, "Should detect forbidden phrase"

    def test_iris_style_response_scores_high(self, calibration):
        """Iris-style brief response should score >= 0.7."""
        score, dims = compute_alignment_score(
            "Oka nena! 🩷",
            calibration,
        )
        assert score >= 0.7, f"Iris-style response scored {score}, expected >= 0.7"
        assert dims["length"] == 1.0
        assert dims["emoji"] == 1.0
        assert dims["forbidden"] == 1.0

    def test_too_long_response(self, calibration):
        """Very long response should get low length score."""
        long_resp = "Hola! " * 30 + "😊"
        score, dims = compute_alignment_score(long_resp, calibration)
        assert dims["length"] < 0.5, f"Long response length score: {dims['length']}"

    def test_forbidden_phrase_zero(self, calibration):
        """Response with forbidden phrase should get 0 on forbidden dimension."""
        score, dims = compute_alignment_score(
            "No dudes en contactarme si necesitas algo más 😊",
            calibration,
        )
        assert dims["forbidden"] == 0.0

    def test_formal_register_zero(self, calibration):
        """Formal register should get 0 on formality dimension."""
        score, dims = compute_alignment_score(
            "Estimada señora, le informo que su solicitud ha sido procesada.",
            calibration,
        )
        assert dims["formality"] == 0.0

    def test_short_emoji_response(self, calibration):
        """Short response with emoji — typical Iris."""
        score, dims = compute_alignment_score("Brutaaal 😂😂😂", calibration)
        assert score >= 0.7
        assert dims["length"] == 1.0
        assert dims["emoji"] == 1.0

    def test_no_emoji_mild_penalty(self, calibration):
        """Response without emoji gets mild penalty, not fatal."""
        score, dims = compute_alignment_score("Dale genial!", calibration)
        assert dims["emoji"] == 0.4  # Penalty but not zero
        # Overall should still be decent if everything else is fine
        assert score >= 0.5


class TestFindSimilarExamples:
    """Test few-shot example retrieval."""

    def test_finds_examples(self, calibration):
        examples = find_similar_examples("Hola que tal", calibration, n=3)
        assert len(examples) == 3

    def test_returns_dicts_with_response(self, calibration):
        examples = find_similar_examples("precio", calibration, n=2)
        for ex in examples:
            assert "response" in ex
            assert "user_message" in ex

    def test_empty_calibration(self):
        examples = find_similar_examples("test", {}, n=3)
        assert examples == []


class TestBuildRefinementPrompt:
    def test_prompt_contains_examples(self, calibration):
        examples = find_similar_examples("hola", calibration, n=3)
        prompt = build_refinement_prompt("Hello how can I help?", examples, "Maria")
        assert "Maria" in prompt
        assert "Iris" in prompt
        assert "Hello how can I help?" in prompt
        for ex in examples:
            assert ex["response"] in prompt


class TestApplyPPA:
    """Test the full apply_ppa flow."""

    @pytest.mark.asyncio
    async def test_good_response_not_refined(self, calibration):
        """Iris-style response should pass through without LLM call."""
        result = await apply_ppa(
            response="Oka nena! 🩷",
            calibration=calibration,
        )
        assert not result.was_refined
        assert result.alignment_score >= 0.7
        assert result.response == "Oka nena! 🩷"

    @pytest.mark.asyncio
    async def test_generic_response_triggers_refinement(self, calibration):
        """Generic response should trigger refinement LLM call."""
        mock_result = {
            "content": "Ey! Que vols saber? 🩷",
            "model": "test",
            "provider": "test",
        }
        with patch(
            "core.providers.gemini_provider.generate_dm_response",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_llm:
            result = await apply_ppa(
                response="Hola, cuéntame en qué puedo ayudarte. Estoy aquí para resolver tus dudas.",
                calibration=calibration,
                lead_name="Maria",
            )
            assert result.was_refined
            assert result.response == "Ey! Que vols saber? 🩷"
            mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_calibration_passthrough(self):
        """No calibration → pass through."""
        result = await apply_ppa(
            response="Whatever response",
            calibration={},
        )
        assert not result.was_refined
        assert result.response == "Whatever response"

    @pytest.mark.asyncio
    async def test_refinement_with_forbidden_rejected(self, calibration):
        """If LLM refinement contains forbidden phrases, reject it."""
        mock_result = {
            "content": "No dudes en contactarme si necesitas algo",
            "model": "test",
            "provider": "test",
        }
        with patch(
            "core.providers.gemini_provider.generate_dm_response",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            result = await apply_ppa(
                response="Hola, cuéntame en qué puedo ayudarte.",
                calibration=calibration,
            )
            # Refinement rejected → original returned
            assert not result.was_refined

    @pytest.mark.asyncio
    async def test_llm_failure_returns_original(self, calibration):
        """If LLM call fails, return original response."""
        with patch(
            "core.providers.gemini_provider.generate_dm_response",
            new_callable=AsyncMock,
            side_effect=Exception("LLM down"),
        ):
            result = await apply_ppa(
                response="Hola, cuéntame en qué puedo ayudarte.",
                calibration=calibration,
            )
            assert not result.was_refined
            assert "en qué puedo ayudarte" in result.response
