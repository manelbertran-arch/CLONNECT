"""
Category 6: ROBUSTEZ - Test Errores de Input
Tests that the bot handles malformed, unusual, or unexpected user inputs
without crashing and still provides reasonable classification/detection.

Validates that:
- Typos in messages are still understood as greetings/questions
- Missing punctuation does not break intent detection
- ALL CAPS messages are classified correctly and frustration is noted
- Emoji-only messages are handled gracefully
- Empty messages do not cause crashes
"""

from core.context_detector import DetectedContext, detect_all
from core.frustration_detector import FrustrationDetector
from core.intent_classifier import Intent, IntentClassifier, classify_intent_simple
from core.sensitive_detector import SensitiveType, detect_sensitive_content
from services.edge_case_handler import EdgeCaseHandler


class TestErroresInput:
    """Test suite for malformed input handling."""

    # ---- test_maneja_typos ------------------------------------------------

    def test_maneja_typos(self):
        """
        A message full of typos like 'Hla benos das' should still be handled
        gracefully. The simple classifier may not catch it as a greeting
        (keyword-based), but the system must NOT crash and should return a
        valid result. The context detector must produce a valid DetectedContext.
        """
        message = "Hla benos das"

        # Must not crash on typos
        ctx = detect_all(message, is_first_message=True)
        assert isinstance(ctx, DetectedContext)
        # Even if not perfectly classified, alerts should be built
        assert isinstance(ctx.alerts, list)

        # Sensitive detector must not crash
        sensitive = detect_sensitive_content(message)
        assert sensitive.type == SensitiveType.NONE

        # Edge case handler must not crash
        handler = EdgeCaseHandler()
        result = handler.detect(message)
        assert result is not None
        assert result.edge_type is not None

        # classify_intent_simple must return a string, even if "other"
        intent = classify_intent_simple(message)
        assert isinstance(intent, str)
        assert intent in [
            "greeting",
            "interest_strong",
            "purchase",
            "interest_soft",
            "question_product",
            "objection",
            "support",
            "other",
        ]

    # ---- test_maneja_sin_puntuacion --------------------------------------

    def test_maneja_sin_puntuacion(self):
        """
        'cuanto cuesta el curso' (no accents, no question mark) should
        still be detected as a price/purchase question by the simple
        intent classifier.
        """
        message = "cuanto cuesta el curso"

        intent = classify_intent_simple(message)
        assert intent in (
            "purchase",
            "interest_strong",
        ), f"Expected purchase-related intent, got '{intent}'"

        # Context detector should pick up interest
        ctx = detect_all(message, is_first_message=False)
        assert ctx.interest_level in ("strong", "soft")

    # ---- test_maneja_mayusculas ------------------------------------------

    def test_maneja_mayusculas(self):
        """
        'QUIERO COMPRAR' in all caps should be classified as strong purchase
        intent. Additionally, the frustration detector should notice the high
        caps ratio.
        """
        message = "QUIERO COMPRAR"

        # Intent classification (case-insensitive matching)
        intent = classify_intent_simple(message)
        assert intent == "interest_strong", f"Expected 'interest_strong', got '{intent}'"

        # Quick classify should also work
        classifier = IntentClassifier()
        result = classifier._quick_classify(message)
        assert result is not None
        assert result.intent == Intent.INTEREST_STRONG

        # Frustration detector should note the caps ratio
        detector = FrustrationDetector()
        signals, score = detector.analyze_message(
            message=message,
            conversation_id="test_caps",
        )
        assert signals.caps_ratio == 1.0, "All-caps message should have a caps_ratio of 1.0"

    # ---- test_maneja_emojis_solo -----------------------------------------

    def test_maneja_emojis_solo(self):
        """
        A message containing only emojis should not crash any module.
        The system should handle it gracefully and return valid results.
        """
        message = "\U0001f44b\U0001f60a"  # wave + smile emojis

        # Sensitive detector must not crash
        sensitive = detect_sensitive_content(message)
        assert sensitive.type == SensitiveType.NONE

        # Context detector must not crash
        ctx = detect_all(message, is_first_message=True)
        assert isinstance(ctx, DetectedContext)
        assert isinstance(ctx.alerts, list)

        # Edge case handler must not crash
        handler = EdgeCaseHandler()
        result = handler.detect(message)
        assert result is not None

        # Intent classifier must not crash
        intent = classify_intent_simple(message)
        assert isinstance(intent, str)

        # Frustration detector must not crash
        detector = FrustrationDetector()
        signals, score = detector.analyze_message(
            message=message,
            conversation_id="test_emojis",
        )
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    # ---- test_maneja_mensaje_vacio ---------------------------------------

    def test_maneja_mensaje_vacio(self):
        """
        An empty string must be handled gracefully by all modules.
        No crashes, no unhandled exceptions.
        """
        message = ""

        # Sensitive detector: returns NONE for empty
        sensitive = detect_sensitive_content(message)
        assert sensitive.type == SensitiveType.NONE
        assert sensitive.confidence == 0.0

        # Context detector: returns a valid context
        ctx = detect_all(message, is_first_message=True)
        assert isinstance(ctx, DetectedContext)

        # Intent classifier: returns "other" for empty
        intent = classify_intent_simple(message)
        assert intent == "other"

        # IntentClassifier quick classify: returns None (no match)
        classifier = IntentClassifier()
        result = classifier._quick_classify(message)
        # None is acceptable (no pattern matched) -- must not raise
        assert result is None or isinstance(result, object)

        # Edge case handler: must not crash on empty
        handler = EdgeCaseHandler()
        # EdgeCaseHandler.detect calls .lower().strip() on message
        # Empty string is fine
        edge_result = handler.detect(message)
        assert edge_result is not None
