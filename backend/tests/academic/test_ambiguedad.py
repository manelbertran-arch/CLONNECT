"""
Tests for Category 3: RAZONAMIENTO - Ambiguity handling.

Validates that the DM bot handles ambiguous, vague, or open-ended input
without making incorrect assumptions. Tests false-positive prevention
and graceful handling of unclear user intent.

All tests are FAST: no LLM calls, no DB access.
"""

from core.context_detector import DetectedContext, detect_all, detect_interest_level
from core.intent_classifier import Intent, IntentClassifier, classify_intent_simple
from core.sensitive_detector import SensitiveType, detect_sensitive_content


class TestAmbiguedad:
    """Test ambiguity handling in reasoning modules."""

    def test_maneja_pregunta_vaga(self):
        """
        Vague message 'Me interesa' should be classified as soft interest,
        not as strong purchase intent. The system should not over-commit.

        Validates:
        - classify_intent_simple returns 'interest_soft' (not 'interest_strong')
        - detect_interest_level returns 'soft' (not 'strong')
        """
        message = "Me interesa"

        intent_simple = classify_intent_simple(message)
        interest = detect_interest_level(message)
        ctx = detect_all(message, is_first_message=False)

        # 'me interesa' is explicitly in interest_soft keywords
        assert (
            intent_simple == "interest_soft"
        ), f"Vague interest should be 'interest_soft', got '{intent_simple}'"
        assert interest == "soft", f"Vague interest level should be 'soft', got '{interest}'"
        # Should NOT be strong - that would be over-interpreting
        assert (
            ctx.interest_level != "strong"
        ), "Vague 'me interesa' should not be classified as strong interest"

    def test_pide_clarificacion(self):
        """
        Vague input should result in the classifier suggesting a 'clarify'
        or 'nurture_and_qualify' action, not a direct sale close.

        Validates:
        - IntentClassifier (pattern-based) maps soft interest to 'nurture_and_qualify'
        - The system does NOT map vague input to 'close_sale'
        """
        classifier = IntentClassifier()
        message = "Me interesa"

        # Quick classify uses pattern matching
        result = classifier._quick_classify(message)

        assert result is not None, "Pattern match should detect 'me interesa'"
        assert result.intent == Intent.INTEREST_SOFT, f"Expected INTEREST_SOFT, got {result.intent}"
        # The suggested action for INTEREST_SOFT is 'nurture_and_qualify'
        expected_action = IntentClassifier.INTENT_ACTIONS[Intent.INTEREST_SOFT]
        assert (
            result.suggested_action == expected_action
        ), f"Expected action '{expected_action}', got '{result.suggested_action}'"
        # Should NOT suggest closing the sale on vague input
        assert (
            result.suggested_action != "close_sale"
        ), "Vague input should not trigger 'close_sale' action"

    def test_no_asume_incorrectamente(self):
        """
        Ambiguous message 'ok' should not be forced into a wrong specific
        intent. It should be classified as OTHER or a low-confidence match.

        Validates:
        - classify_intent_simple returns 'other' for truly ambiguous input
        - IntentClassifier._quick_classify returns None (no pattern match)
        """
        classifier = IntentClassifier()
        message = "ok"

        intent_simple = classify_intent_simple(message)
        quick = classifier._quick_classify(message)

        # 'ok' alone should not match any specific pattern
        assert intent_simple == "other", f"Ambiguous 'ok' should be 'other', got '{intent_simple}'"
        # Quick classify should return None (no confident match)
        assert quick is None, f"Ambiguous 'ok' should not match any quick pattern, got {quick}"

    def test_maneja_doble_sentido(self):
        """
        Colloquial 'Me muero por saber el precio' should NOT be detected
        as self-harm crisis. It's a figure of speech expressing excitement.

        Validates:
        - detect_sensitive_content does NOT flag this as SELF_HARM
        - The intent should be interest/purchase, not crisis
        """
        message = "Me muero por saber el precio"

        sensitive = detect_sensitive_content(message)
        intent_simple = classify_intent_simple(message)

        # This is a common Spanish expression, NOT a crisis signal
        assert sensitive.type != SensitiveType.SELF_HARM, (
            "Colloquial 'me muero por saber' should NOT be flagged as "
            f"self-harm, got type={sensitive.type}"
        )
        # Should be detected as purchase interest (mentions 'precio')
        assert intent_simple in ("purchase", "interest_strong", "interest_soft"), (
            "Expected purchase/interest intent for price inquiry, " f"got '{intent_simple}'"
        )

    def test_responde_pregunta_abierta(self):
        """
        Open-ended 'Que opinas?' should be handled gracefully without
        crashing or forcing a wrong classification. The system should
        classify it as OTHER or QUESTION_GENERAL.

        Validates:
        - classify_intent_simple returns a valid classification
        - detect_all returns a valid DetectedContext without errors
        - No frustration or sensitive content detected
        """
        message = "Que opinas?"

        intent_simple = classify_intent_simple(message)
        ctx = detect_all(message, is_first_message=False)
        sensitive = detect_sensitive_content(message)

        # Should get a valid classification, not crash
        assert intent_simple in ("other", "greeting", "question_product", "interest_soft"), (
            "Open-ended question should be 'other' or question-like, " f"got '{intent_simple}'"
        )

        # Context should be valid and neutral
        assert isinstance(ctx, DetectedContext), "detect_all should return a valid DetectedContext"
        assert ctx.frustration_level == "none", "Open-ended question should not trigger frustration"

        # Should not be sensitive content
        assert sensitive.type == SensitiveType.NONE, (
            "Open-ended question should not be sensitive, " f"got type={sensitive.type}"
        )
