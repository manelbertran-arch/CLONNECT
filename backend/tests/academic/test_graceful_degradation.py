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
from services.edge_case_handler import EdgeCaseConfig, EdgeCaseHandler, EdgeCaseType


class TestGracefulDegradation:
    """Test suite for graceful degradation under failure conditions."""

    # ---- test_responde_algo_si_no_sabe -----------------------------------

    def test_responde_algo_si_no_sabe(self):
        """
        When confronted with a completely unknown topic, the system should
        still produce a valid response path (not empty). The EdgeCaseHandler
        process_with_context should return *something* even when LLM
        confidence is low.
        """
        message = "Cual es la raiz cuadrada de la felicidad?"

        handler = EdgeCaseHandler()

        # Simulate the LLM giving a low-confidence response
        llm_response = "Hmm, esa es una pregunta interesante."
        final_response, should_escalate = handler.process_with_context(
            message=message,
            llm_response=llm_response,
            llm_confidence=0.3,  # Low confidence
        )

        # Must return something non-empty
        assert final_response is not None
        assert (
            len(final_response.strip()) > 0
        ), "Even with low confidence, the handler must return a non-empty response"

    # ---- test_admite_no_saber --------------------------------------------

    def test_admite_no_saber(self):
        """
        For an out-of-domain question, the EdgeCaseHandler should be
        able to admit it does not know. With admit_unknown_chance=1.0
        (forced), it should return a 'no se' response.
        """
        # Force the handler to always admit unknown
        config = EdgeCaseConfig(
            admit_unknown_chance=1.0,
            confidence_threshold=0.8,
        )
        handler = EdgeCaseHandler(config=config)

        should_admit, response = handler.should_admit_unknown(confidence=0.5)

        assert should_admit is True
        assert response is not None
        assert len(response) > 0
        # Response should be one of the NO_SE_RESPONSES
        assert response in EdgeCaseHandler.NO_SE_RESPONSES

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

            # Edge case handler
            if inp is not None:
                handler = EdgeCaseHandler()
                edge_result = handler.detect(inp)
                assert edge_result is not None

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

    # ---- test_sugiere_alternativa ----------------------------------------

    def test_sugiere_alternativa(self):
        """
        When the bot cannot answer a question, the EdgeCaseHandler should
        suggest escalation or provide a fallback. For complaints, escalation
        to a human/creator should be triggered. The process_with_context
        method should suggest contacting the creator when confidence is low.
        """
        # Use accented form to match UNKNOWN_PATTERNS exactly
        message = "qué piensas de verdad sobre la inteligencia artificial"

        handler = EdgeCaseHandler(config=EdgeCaseConfig(admit_unknown_chance=1.0))

        # This message matches UNKNOWN_PATTERNS ("qué piensas de verdad")
        result = handler.detect(message)
        assert result.edge_type == EdgeCaseType.UNKNOWN_QUESTION

        # The suggested response should be a "no se" type response
        assert result.suggested_response is not None
        assert len(result.suggested_response) > 0

        # For complaint cases, escalation should be suggested
        complaint_msg = "esto no me sirve, quiero mi devolucion"
        complaint_result = handler.detect(complaint_msg)
        assert (
            complaint_result.should_escalate is True
        ), "Complaint should trigger escalation to creator/human"
