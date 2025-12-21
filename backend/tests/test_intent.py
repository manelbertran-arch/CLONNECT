"""
Tests para el clasificador de intencion
"""

import pytest
from core.intent_classifier import IntentClassifier, Intent, IntentResult


class TestIntentClassifier:
    """Tests para IntentClassifier"""

    def setup_method(self):
        """Setup antes de cada test"""
        self.classifier = IntentClassifier(llm_client=None)

    def test_quick_classify_greeting(self):
        """Test clasificacion rapida de saludo"""
        result = self.classifier._quick_classify("Hola!")
        assert result is not None
        assert result.intent == Intent.GREETING

    def test_quick_classify_interest_strong(self):
        """Test clasificacion rapida de interes fuerte"""
        result = self.classifier._quick_classify("Quiero comprar tu curso")
        assert result is not None
        assert result.intent == Intent.INTEREST_STRONG

    def test_quick_classify_interest_soft(self):
        """Test clasificacion rapida de interes suave"""
        result = self.classifier._quick_classify("Me interesa saber mas")
        assert result is not None
        assert result.intent == Intent.INTEREST_SOFT

    def test_quick_classify_objection(self):
        """Test clasificacion rapida de objecion"""
        result = self.classifier._quick_classify("Es muy caro para mi")
        assert result is not None
        assert result.intent == Intent.OBJECTION

    def test_quick_classify_positive_feedback(self):
        """Test clasificacion rapida de feedback positivo"""
        result = self.classifier._quick_classify("Gracias, genial!")
        assert result is not None
        assert result.intent == Intent.FEEDBACK_POSITIVE

    def test_quick_classify_support(self):
        """Test clasificacion rapida de soporte"""
        result = self.classifier._quick_classify("No funciona el acceso")
        assert result is not None
        assert result.intent == Intent.SUPPORT

    def test_quick_classify_spam(self):
        """Test clasificacion rapida de spam"""
        result = self.classifier._quick_classify("Compra bitcoin y gana dinero http://spam.com")
        assert result is not None
        assert result.intent == Intent.SPAM

    def test_quick_classify_no_match(self):
        """Test cuando no hay match de patron"""
        result = self.classifier._quick_classify("xyz abc 123")
        assert result is None

    def test_get_action(self):
        """Test obtener accion sugerida"""
        assert self.classifier.get_action(Intent.GREETING) == "greet_and_discover"
        assert self.classifier.get_action(Intent.INTEREST_STRONG) == "close_sale"
        assert self.classifier.get_action(Intent.OBJECTION) == "handle_objection"

    def test_get_intent_description(self):
        """Test obtener descripcion de intencion"""
        assert IntentClassifier.get_intent_description(Intent.GREETING) == "Saludo inicial"
        assert IntentClassifier.get_intent_description(Intent.INTEREST_STRONG) == "Alta intención de compra"


@pytest.mark.asyncio
async def test_classify_without_llm():
    """Test clasificacion sin LLM"""
    classifier = IntentClassifier(llm_client=None)

    # Debe usar clasificacion rapida
    result = await classifier.classify("Hola!", use_llm=False)
    assert result.intent == Intent.GREETING

    # Sin match, debe devolver OTHER
    result = await classifier.classify("xyz abc", use_llm=False)
    assert result.intent == Intent.OTHER
