"""Tests for core/confidence_scorer.py."""

from unittest.mock import patch

from core.confidence_scorer import (
    _score_blacklist,
    _score_length,
    calculate_confidence,
)


class TestCalculateConfidence:
    """Test multi-factor confidence calculation."""

    def test_greeting_high_confidence(self):
        """Greetings with clean text score high."""
        score = calculate_confidence(
            intent="greeting",
            response_text="Hola! Bienvenido, en qué te puedo ayudar?",
            response_type="pool_match",
        )
        assert score >= 0.7

    def test_error_intent_very_low(self):
        """ERROR intent produces low confidence."""
        score = calculate_confidence(
            intent="ERROR",
            response_text="Lo siento, hubo un error.",
            response_type="error_fallback",
        )
        # intent=0.0, type=0.05, hist=0.70(default), length=1.0, blacklist=1.0
        # 0.30*0.0 + 0.20*0.05 + 0.30*0.70 + 0.10*1.0 + 0.10*1.0 = 0.42
        assert score < 0.5

    def test_edge_escalation_low(self):
        """Edge case escalation has below-average confidence."""
        score = calculate_confidence(
            intent="edge_case_escalation",
            response_text="Déjame consultarlo y te respondo.",
            response_type="edge_escalation",
        )
        # intent=0.25, type=0.30, hist=0.70, length=1.0, blacklist=1.0
        # = 0.075 + 0.06 + 0.21 + 0.10 + 0.10 = 0.545
        assert score < 0.6

    def test_empty_response_zero(self):
        """Empty response returns 0.0."""
        assert calculate_confidence("greeting", "", "pool_match") == 0.0

    def test_pool_match_higher_than_llm(self):
        """Pool match should score higher than LLM for same intent and text."""
        pool_score = calculate_confidence(
            intent="greeting",
            response_text="Hola! Bienvenido al perfil.",
            response_type="pool_match",
        )
        llm_score = calculate_confidence(
            intent="greeting",
            response_text="Hola! Bienvenido al perfil.",
            response_type="llm_generation",
        )
        assert pool_score > llm_score

    def test_score_between_zero_and_one(self):
        """Score is always in [0, 1]."""
        for intent in ["greeting", "purchase", "objection", "other", "ERROR"]:
            score = calculate_confidence(intent, "Test response text", "llm_generation")
            assert 0.0 <= score <= 1.0

    def test_unknown_intent_uses_default(self):
        """Unknown intent still returns a valid score."""
        score = calculate_confidence(
            intent="totally_new_intent",
            response_text="Some response here for testing",
            response_type="llm_generation",
        )
        assert 0.0 <= score <= 1.0

    def test_none_intent_handled(self):
        """None intent is handled gracefully."""
        score = calculate_confidence(
            intent=None,
            response_text="Valid response",
            response_type="llm_generation",
        )
        assert 0.0 <= score <= 1.0


class TestLengthScoring:
    """Test length quality factor."""

    def test_very_short_low(self):
        """Very short (<5 chars) gets low score."""
        assert _score_length("hi") < 0.3

    def test_short_moderate(self):
        """Short (5-20 chars) gets moderate score."""
        assert _score_length("Hola, qué tal?") == 0.5

    def test_ideal_length_full(self):
        """Ideal length (20-200) gets 1.0."""
        assert _score_length("Hola! Bienvenido, te cuento sobre el curso.") == 1.0

    def test_medium_length_good(self):
        """200-400 chars gets 0.7."""
        text = "A" * 300
        assert _score_length(text) == 0.7

    def test_very_long_penalized(self):
        """Very long (>400) gets penalized."""
        text = "A" * 500
        assert _score_length(text) == 0.4


class TestBlacklistScoring:
    """Test blacklist pattern detection."""

    def test_clean_text_full_score(self):
        """Clean text with no blacklisted patterns gets 1.0."""
        assert _score_blacklist("Hola! El curso tiene 20 horas de contenido.") == 1.0

    def test_one_pattern_halved(self):
        """One blacklisted pattern drops to 0.5."""
        assert _score_blacklist("ERROR: Connection failed. Pero sigue intentando.") == 0.5

    def test_multiple_patterns_very_low(self):
        """Multiple blacklisted patterns drop to 0.1."""
        text = "Soy Stefano. ERROR: algo falló. COMPRA AHORA."
        assert _score_blacklist(text) == 0.1

    def test_catchphrase_detected(self):
        """Catchphrase 'qué te llamó la atención' is caught."""
        score = _score_blacklist("Hola! Qué te llamó la atención? Contame!")
        assert score < 1.0

    def test_broken_link_detected(self):
        """Broken link pattern is caught."""
        score = _score_blacklist("Mira ://www.example.com para más info")
        assert score < 1.0
