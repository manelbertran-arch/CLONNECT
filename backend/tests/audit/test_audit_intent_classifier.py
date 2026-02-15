"""Audit tests for core/intent_classifier.py"""

import asyncio

from core.intent_classifier import IntentClassifier, IntentResult


class TestAuditIntentClassifier:
    def test_import(self):
        from core.intent_classifier import Intent, IntentClassifier  # noqa: F811

        assert Intent is not None
        assert IntentClassifier is not None

    def test_init(self):
        classifier = IntentClassifier()
        assert classifier is not None

    def test_happy_path_classify(self):
        classifier = IntentClassifier()
        result = asyncio.get_event_loop().run_until_complete(
            classifier.classify("Hola, buenos dias!")
        )
        assert isinstance(result, IntentResult)
        assert result.intent is not None

    def test_edge_case_empty_message(self):
        classifier = IntentClassifier()
        result = asyncio.get_event_loop().run_until_complete(classifier.classify(""))
        assert isinstance(result, IntentResult)

    def test_error_handling_none_input(self):
        classifier = IntentClassifier()
        try:
            result = asyncio.get_event_loop().run_until_complete(classifier.classify(None))
            assert isinstance(result, IntentResult)
        except (TypeError, AttributeError):
            pass  # Acceptable to raise on None
