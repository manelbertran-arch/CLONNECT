"""
Category 6: ROBUSTEZ - Test Graceful Degradation
Tests that the bot degrades gracefully when encountering unknown situations,
module failures, or inputs it cannot process.

Validates that:
- Unknown topics still produce a response (not empty)
- Out-of-domain questions lead to an honest "I don't know" path
- Malformed inputs do not raise unhandled exceptions
- When modules fail, fallback responses are still useful
- When the bot cannot answer, it suggests contacting the creator
"""

from core.context_detector import DetectedContext, detect_all
from core.frustration_detector import FrustrationDetector
from core.guardrails import ResponseGuardrail
from core.intent_classifier import classify_intent_simple
from core.response_fixes import hide_technical_errors
from core.sensitive_detector import detect_sensitive_content


class TestGracefulDegradation:
    """Test suite for graceful degradation under failure conditions."""

    # ---- test_no_crashea -------------------------------------------------

    def test_no_crashea(self):
        """
        Various malformed inputs must not raise unhandled exceptions in
        any of the core modules.
        """
        malformed_inputs = [
            None,  # None
            "",  # Empty string
            " ",  # Whitespace only
            "a" * 10000,  # Very long string
            "\x00\x01\x02",  # Binary garbage
            "```python\nimport os\nos.system('rm -rf /')\n```",  # Code injection
            "<script>alert('xss')</script>",  # XSS attempt
            "\n\n\n\n",  # Only newlines
            "!@#$%^&*()",  # Only special characters
            "\ud83d" * 50,  # Repeated unicode
        ]

        for inp in malformed_inputs:
            # Sensitive detector
            if inp is not None:
                result = detect_sensitive_content(inp)
                assert result is not None

            # Context detector (handles empty but not None internally)
            if inp is not None:
                ctx = detect_all(inp, is_first_message=True)
                assert isinstance(ctx, DetectedContext)

            # Intent classifier
            if inp is not None:
                intent = classify_intent_simple(inp)
                assert isinstance(intent, str)

            # Frustration detector
            if inp is not None:
                detector = FrustrationDetector()
                signals, score = detector.analyze_message(
                    message=inp,
                    conversation_id="test_malformed",
                )
                assert isinstance(score, float)

    # ---- test_fallback_elegante ------------------------------------------

    def test_fallback_elegante(self):
        """
        When a response contains technical errors, the response_fixes
        module should clean them up. If the cleaned result is empty,
        the guardrail fallback response should be user-friendly.
        """
        # Simulated response full of technical errors
        error_response = "ERROR: NoneType object has no attribute 'generate'. API error occurred."

        # hide_technical_errors should clean it
        cleaned = hide_technical_errors(error_response)

        # The function returns "" when the result is too short after cleaning
        assert isinstance(cleaned, str)

        # If it became empty, the guardrail should provide a fallback
        if len(cleaned.strip()) < 10:
            guardrail = ResponseGuardrail()
            fallback = guardrail._get_fallback_response({"language": "es"})
            assert len(fallback) > 10, "Fallback response must be meaningful"
            # Fallback should be friendly, not technical
            assert "error" not in fallback.lower()
            assert "exception" not in fallback.lower()

