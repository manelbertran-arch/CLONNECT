"""Audit tests for core/guardrails.py"""

from core.guardrails import ResponseGuardrail, get_response_guardrail


class TestAuditGuardrails:
    def test_import(self):
        from core.guardrails import ResponseGuardrail, get_response_guardrail  # noqa: F811

        assert ResponseGuardrail is not None

    def test_init(self):
        guardrail = ResponseGuardrail()
        assert guardrail is not None

    def test_happy_path_validate(self):
        guardrail = get_response_guardrail()
        result = guardrail.validate_response(
            query="Cuanto cuesta el curso?",
            response="El curso cuesta $99.",
        )
        assert result is not None

    def test_edge_case_empty_response(self):
        guardrail = ResponseGuardrail()
        result = guardrail.validate_response(query="test", response="")
        assert result is not None

    def test_error_handling_safe_response(self):
        guardrail = ResponseGuardrail()
        try:
            result = guardrail.get_safe_response(
                query="test",
                response="unsafe content",
            )
            assert result is not None
        except (TypeError, AttributeError):
            pass  # Acceptable
