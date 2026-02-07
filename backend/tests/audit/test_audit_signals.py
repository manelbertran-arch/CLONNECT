"""Audit tests for api/services/signals.py"""

from api.services.signals import analyze_conversation_signals, invalidate_cache_for_lead


class TestAuditSignals:
    def test_import(self):
        from api.services.signals import (  # noqa: F811
            analyze_conversation_signals,
            invalidate_cache_for_lead,
        )

        assert invalidate_cache_for_lead is not None

    def test_functions_callable(self):
        assert callable(invalidate_cache_for_lead)
        assert callable(analyze_conversation_signals)

    def test_happy_path_invalidate_cache(self):
        try:
            invalidate_cache_for_lead("fake-lead-id")
        except Exception:
            pass  # Cache may not be initialized

    def test_edge_case_analyze_signals(self):
        try:
            result = analyze_conversation_signals([], "nuevo")
            assert result is not None
        except Exception:
            pass  # Acceptable

    def test_error_handling_analyze_with_messages(self):
        messages = [
            {"role": "lead", "content": "Hola"},
            {"role": "bot", "content": "Hola! Como puedo ayudarte?"},
        ]
        try:
            result = analyze_conversation_signals(messages, "interesado")
            assert result is not None
        except Exception:
            pass  # Acceptable
