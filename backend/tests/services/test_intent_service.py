"""
Intent Service tests - Written BEFORE implementation (TDD).
Run these tests FIRST - they should FAIL until service is created.
"""
import pytest


class TestIntentServiceImport:
    """Test Intent service can be imported."""

    def test_intent_service_module_exists(self):
        """Intent service module should exist."""
        import services.intent_service
        assert services.intent_service is not None

    def test_intent_service_class_exists(self):
        """IntentClassifier class should exist."""
        from services.intent_service import IntentClassifier
        assert IntentClassifier is not None

    def test_intent_enum_exists(self):
        """Intent enum should exist in service."""
        from services.intent_service import Intent
        assert Intent is not None

    def test_intent_classifier_has_classify_method(self):
        """IntentClassifier should have classify method."""
        from services.intent_service import IntentClassifier
        assert hasattr(IntentClassifier, 'classify')


class TestIntentServiceFunctionality:
    """Test Intent service functionality."""

    def test_intent_classifier_instantiation(self):
        """IntentClassifier should be instantiable."""
        from services.intent_service import IntentClassifier
        classifier = IntentClassifier()
        assert classifier is not None

    def test_classify_returns_intent(self):
        """classify should return an Intent enum value."""
        from services.intent_service import IntentClassifier, Intent
        classifier = IntentClassifier()
        result = classifier.classify("Hola, quiero información sobre tus productos")
        assert isinstance(result, Intent)

    def test_classify_greeting(self):
        """Should classify greetings correctly."""
        from services.intent_service import IntentClassifier, Intent
        classifier = IntentClassifier()
        result = classifier.classify("Hola!")
        assert result in [Intent.GREETING, Intent.GENERAL_CHAT]

    def test_classify_purchase_intent(self):
        """Should classify purchase intent correctly."""
        from services.intent_service import IntentClassifier, Intent
        classifier = IntentClassifier()
        result = classifier.classify("Quiero comprar el curso")
        assert result in [Intent.PURCHASE_INTENT, Intent.PRODUCT_QUESTION]
