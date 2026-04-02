"""Audit tests for core/frustration_detector.py."""

from core.frustration_detector import (
    FrustrationDetector,
    FrustrationSignals,
    get_frustration_detector,
)


# ---------------------------------------------------------------------------
# Test 1: init / import
# ---------------------------------------------------------------------------
class TestFrustrationDetectorInit:
    """Verify module initialisation and singleton."""

    def test_import_classes(self):
        from core.frustration_detector import FrustrationDetector, FrustrationSignals

        assert FrustrationDetector is not None
        assert FrustrationSignals is not None

    def test_detector_init_state(self):
        detector = FrustrationDetector()
        assert isinstance(detector._conversation_history, dict)
        assert len(detector._conversation_history) == 0
        # v3: compiled lists are empty (detection via functional helpers, not compiled regex)
        assert isinstance(detector._frustration_compiled, list)
        assert isinstance(detector._negative_compiled, list)

    def test_singleton_returns_same_instance(self):
        d1 = get_frustration_detector()
        d2 = get_frustration_detector()
        assert d1 is d2

    def test_frustration_signals_defaults(self):
        signals = FrustrationSignals()
        assert signals.repeated_questions == 0
        assert signals.negative_markers == 0
        assert signals.caps_ratio == 0.0
        assert signals.explicit_frustration is False
        assert signals.short_responses == 0
        assert signals.question_marks_excess == 0

    def test_signals_score_zero_by_default(self):
        signals = FrustrationSignals()
        assert signals.get_score() == 0.0


# ---------------------------------------------------------------------------
# Test 2: happy path - frustrated message detection
# ---------------------------------------------------------------------------
class TestFrustrationDetectorHappyPath:
    """Detect frustration in clearly frustrated messages."""

    def test_explicit_frustration_count_signal(self):
        # "tres veces" triggers COUNT_RE → explicit_frustration=True, score > 0.2
        detector = FrustrationDetector()
        signals, score = detector.analyze_message(
            "Ya te dije 3 veces, no me entiendes!", "conv_1"
        )
        assert signals.explicit_frustration is True
        assert score > 0.2

    def test_explicit_frustration_emoji(self):
        # Language-agnostic: frustration emoji triggers explicit_frustration
        detector = FrustrationDetector()
        signals, score = detector.analyze_message(
            "I already told you, this doesn't work 😡", "conv_2"
        )
        assert signals.explicit_frustration is True
        assert score > 0.2

    def test_explicit_frustration_punctuation_burst(self):
        # Language-agnostic: punctuation burst triggers a score > 0
        detector = FrustrationDetector()
        signals, score = detector.analyze_message(
            "I already told you, this doesn't work!!!", "conv_2b"
        )
        assert score > 0.0

    def test_caps_increases_score(self):
        # CAPS is one of many language-agnostic signals; alone it contributes 0.15
        detector = FrustrationDetector()
        signals, score = detector.analyze_message("NO ME AYUDAS CON NADA YA TE DIJE", "conv_3")
        assert signals.caps_ratio > 0.3
        assert score >= 0.10  # CAPS alone → 0.15; combined with other signals → higher

    def test_repeated_question_detected(self):
        # Repetition detection is lexical overlap — messages must share content words.
        # "cuanto cuesta el curso" and "precio del curso" share "curso" → overlap
        # Use messages that share enough content words to cross the 0.4 threshold.
        detector = FrustrationDetector()
        previous = [
            "que precio tiene el curso online?",
            "cuanto cuesta el curso online?",
        ]
        signals, score = detector.analyze_message(
            "el precio del curso online?", "conv_4", previous_messages=previous
        )
        assert signals.repeated_questions >= 1

    def test_multiple_question_marks(self):
        detector = FrustrationDetector()
        signals, score = detector.analyze_message("En serio??? Otra vez lo mismo???", "conv_5")
        assert signals.question_marks_excess >= 1


# ---------------------------------------------------------------------------
# Test 3: calm message - no match
# ---------------------------------------------------------------------------
class TestFrustrationDetectorCalmMessage:
    """Calm, positive messages should produce low or zero scores."""

    def test_friendly_greeting(self):
        detector = FrustrationDetector()
        signals, score = detector.analyze_message(
            "Hola! Me encanta tu contenido, quiero saber mas", "conv_calm_1"
        )
        assert signals.explicit_frustration is False
        assert score < 0.3

    def test_simple_question(self):
        detector = FrustrationDetector()
        signals, score = detector.analyze_message(
            "Tienes disponible el programa de nutricion?", "conv_calm_2"
        )
        assert signals.explicit_frustration is False
        assert score < 0.2

    def test_positive_message(self):
        detector = FrustrationDetector()
        signals, score = detector.analyze_message(
            "Genial, muchas gracias por tu ayuda!", "conv_calm_3"
        )
        assert signals.explicit_frustration is False
        assert score < 0.2

    def test_empty_message(self):
        detector = FrustrationDetector()
        signals, score = detector.analyze_message("", "conv_calm_4")
        assert score == 0.0

    def test_single_word_message(self):
        detector = FrustrationDetector()
        signals, score = detector.analyze_message("ok", "conv_calm_5")
        assert score < 0.2


# ---------------------------------------------------------------------------
# Test 4: edge case - mixed signals and non-string inputs
# ---------------------------------------------------------------------------
class TestFrustrationDetectorEdgeCases:
    """Edge cases: mixed signals, dict input, None, non-string."""

    def test_mixed_signals_moderate_score(self):
        detector = FrustrationDetector()
        signals, score = detector.analyze_message(
            "No entiendo bien pero esta todo ok, no hay problema", "conv_edge_1"
        )
        # Has negative words (no) but no explicit frustration
        assert signals.explicit_frustration is False
        assert score < 0.5

    def test_dict_input_handled(self):
        """analyze_message should handle dict input defensively."""
        detector = FrustrationDetector()
        signals, score = detector.analyze_message(
            {"text": "esto no funciona, ya te dije"}, "conv_edge_2"
        )
        # Should not raise; it extracts text from dict
        assert isinstance(score, float)

    def test_none_input_handled(self):
        detector = FrustrationDetector()
        signals, score = detector.analyze_message(None, "conv_edge_3")
        assert isinstance(score, float)
        assert score == 0.0

    def test_numeric_input_handled(self):
        detector = FrustrationDetector()
        signals, score = detector.analyze_message(12345, "conv_edge_4")
        assert isinstance(score, float)

    def test_clear_conversation(self):
        detector = FrustrationDetector()
        detector.analyze_message("test message", "conv_clear")
        assert "conv_clear" in detector._conversation_history
        detector.clear_conversation("conv_clear")
        assert "conv_clear" not in detector._conversation_history


# ---------------------------------------------------------------------------
# Test 5: confidence score range and frustration context
# ---------------------------------------------------------------------------
class TestFrustrationDetectorConfidenceAndContext:
    """Verify score is always 0-1 and context generation works."""

    def test_score_capped_at_one(self):
        """Even with all signals maxed, score should not exceed 1.0."""
        signals = FrustrationSignals(
            repeated_questions=10,
            negative_markers=10,
            caps_ratio=1.0,
            explicit_frustration=True,
            question_marks_excess=20,
        )
        score = signals.get_score()
        assert score == 1.0

    def test_score_zero_for_empty_signals(self):
        signals = FrustrationSignals()
        assert signals.get_score() == 0.0

    def test_context_empty_for_low_score(self):
        detector = FrustrationDetector()
        signals = FrustrationSignals()
        context = detector.get_frustration_context(0.1, signals)
        assert context == ""

    def test_context_high_frustration(self):
        detector = FrustrationDetector()
        signals = FrustrationSignals(explicit_frustration=True, repeated_questions=3)
        context = detector.get_frustration_context(0.7, signals)
        assert "ALTO" in context
        assert "FRUSTRACION" in context
        assert "repetido" in context.lower() or "repetid" in context.lower()

    def test_context_medium_frustration(self):
        detector = FrustrationDetector()
        signals = FrustrationSignals(caps_ratio=0.8)
        context = detector.get_frustration_context(0.45, signals)
        assert "MEDIO" in context
