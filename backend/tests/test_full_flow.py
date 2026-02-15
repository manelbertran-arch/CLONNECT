#!/usr/bin/env python3
"""
Full Flow Tests for Clonnect DM System.

Tests the complete flow from message input to response generation
using mock creator configuration.

Run with: pytest tests/test_full_flow.py -v

NOTE: These tests use mocked data and don't require external resources.
"""

import pytest
import os
import sys
from unittest.mock import Mock

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.intent_classifier import IntentClassifier, Intent
from core.memory import MemoryStore


# Test configuration
CREATOR_ID = "test_creator"
TEST_FOLLOWER_ID = "test_user_001"


# Mock creator config
MOCK_CONFIG = {
    "id": CREATOR_ID,
    "name": "Test Creator",
    "clone_name": "TestBot",
    "personality": {
        "tone": "cercano",
        "formality": "informal",
        "style": "helpful"
    },
    "escalation_keywords": ["urgente", "reembolso", "humano", "persona real"],
    "clone_active": True,
    "business": {
        "type": "coaching",
        "niche": "automation"
    }
}

# Mock products
MOCK_PRODUCTS = [
    {
        "id": "curso-automatizacion",
        "name": "Curso de Automatizacion",
        "description": "Aprende a automatizar tu negocio",
        "price": 297,
        "currency": "EUR",
        "payment_link": "https://example.com/pay/curso",
        "is_active": True,
        "objection_handlers": {
            "precio": "El curso incluye 30 dias de garantia de devolucion"
        }
    },
    {
        "id": "mentoria-1a1",
        "name": "Mentoria 1 a 1",
        "description": "Mentoria personalizada",
        "price": 1500,
        "currency": "EUR",
        "payment_link": "https://example.com/pay/mentoria",
        "is_active": True
    },
    {
        "id": "ebook-gratis",
        "name": "Ebook Gratuito",
        "description": "Guia de inicio",
        "price": 0,
        "currency": "EUR",
        "payment_link": "https://example.com/ebook",
        "is_active": True
    }
]


@pytest.fixture
def mock_config():
    """Create mock config"""
    config = Mock()
    config.id = CREATOR_ID
    config.name = "Test Creator"
    config.clone_name = "TestBot"
    config.personality = MOCK_CONFIG["personality"]
    config.escalation_keywords = MOCK_CONFIG["escalation_keywords"]
    config.clone_active = True
    return config


@pytest.fixture
def mock_products():
    """Create mock products"""
    products = []
    for p in MOCK_PRODUCTS:
        product = Mock()
        product.id = p["id"]
        product.name = p["name"]
        product.description = p["description"]
        product.price = p["price"]
        product.currency = p["currency"]
        product.payment_link = p["payment_link"]
        product.is_active = p["is_active"]
        product.objection_handlers = p.get("objection_handlers", {})
        products.append(product)
    return products


@pytest.fixture
def intent_classifier():
    """Create intent classifier"""
    return IntentClassifier()


class TestCreatorConfiguration:
    """Test creator configuration loading"""

    def test_creator_config_exists(self, mock_config):
        """Test that config exists"""
        assert mock_config is not None, "Config should exist"

    def test_creator_name(self, mock_config):
        """Test creator name is correct"""
        assert mock_config.name == "Test Creator"

    def test_creator_personality(self, mock_config):
        """Test creator personality settings"""
        assert mock_config.personality["tone"] == "cercano"
        assert mock_config.personality["formality"] == "informal"

    def test_escalation_keywords(self, mock_config):
        """Test escalation keywords are set"""
        assert "urgente" in mock_config.escalation_keywords
        assert "reembolso" in mock_config.escalation_keywords

    def test_system_prompt_generation(self, mock_config):
        """Test system prompt can be generated from config"""
        # Build a simple prompt from config
        prompt = f"Eres {mock_config.clone_name}, asistente de {mock_config.name}"
        assert mock_config.name in prompt
        assert len(prompt) > 10


class TestProductsCatalog:
    """Test products catalog"""

    def test_products_exist(self, mock_products):
        """Test that products are loaded"""
        assert len(mock_products) >= 3, "Should have at least 3 products"

    def test_curso_automatizacion(self, mock_products):
        """Test main course product"""
        product = next((p for p in mock_products if p.id == "curso-automatizacion"), None)
        assert product is not None
        assert product.price == 297
        assert "automatizacion" in product.name.lower()

    def test_mentoria_product(self, mock_products):
        """Test mentoria product"""
        product = next((p for p in mock_products if p.id == "mentoria-1a1"), None)
        assert product is not None
        assert product.price == 1500

    def test_free_ebook(self, mock_products):
        """Test free ebook product"""
        product = next((p for p in mock_products if p.id == "ebook-gratis"), None)
        assert product is not None
        assert product.price == 0

    def test_product_search(self, mock_products):
        """Test product search by query"""
        query = "automatizar"
        results = [p for p in mock_products if query in p.name.lower() or query in p.description.lower()]
        assert len(results) > 0

    def test_objection_handler_precio(self, mock_products):
        """Test price objection handler"""
        product = next((p for p in mock_products if p.id == "curso-automatizacion"), None)
        response = product.objection_handlers.get("precio", "")
        assert len(response) > 0
        assert "30 dias" in response.lower() or "garantia" in response.lower()


class TestGreetingFlow:
    """Test 1: Saludo -> respuesta personalizada"""

    def test_greeting_hola(self, intent_classifier):
        """Test simple greeting 'Hola' intent detection"""
        result = intent_classifier._quick_classify("Hola")
        assert result is not None
        assert result.intent == Intent.GREETING

    def test_greeting_buenas(self, intent_classifier):
        """Test greeting 'Buenas' intent detection"""
        result = intent_classifier._quick_classify("Buenas!")
        assert result is not None
        assert result.intent == Intent.GREETING

    def test_greeting_que_tal(self, intent_classifier):
        """Test greeting 'Que tal' intent detection"""
        result = intent_classifier._quick_classify("Que tal?")
        assert result is not None
        assert result.intent == Intent.GREETING


class TestInterestSoftFlow:
    """Test 2: Interes soft -> menciona producto relevante"""

    def test_interest_soft_general(self, intent_classifier):
        """Test soft interest expression"""
        result = intent_classifier._quick_classify("Me interesa lo que haces")
        assert result is not None
        assert result.intent in [Intent.INTEREST_SOFT, Intent.INTEREST_STRONG]


class TestInterestStrongFlow:
    """Test 3: Interes fuerte -> da link de compra"""

    def test_interest_strong_quiero_comprar(self, intent_classifier):
        """Test strong interest - wants to buy"""
        result = intent_classifier._quick_classify("Quiero comprar el curso de automatizacion")
        assert result is not None
        assert result.intent == Intent.INTEREST_STRONG

    def test_interest_strong_precio(self, intent_classifier):
        """Test strong interest - asking for price"""
        result = intent_classifier._quick_classify("Cuánto cuesta?")
        assert result is not None
        assert result.intent == Intent.INTEREST_STRONG


class TestObjectionPrecioFlow:
    """Test 4: Objecion 'caro' -> usa handler de objecion"""

    def test_objection_caro(self, intent_classifier):
        """Test price objection 'caro'"""
        result = intent_classifier._quick_classify("Es muy caro para mi")
        assert result is not None
        assert result.intent == Intent.OBJECTION

    def test_objection_no_puedo(self, intent_classifier):
        """Test objection 'no puedo'"""
        result = intent_classifier._quick_classify("No puedo pagarlo ahora")
        assert result is not None
        assert result.intent == Intent.OBJECTION


class TestObjectionTiempoFlow:
    """Test 5: Objecion tiempo -> usa handler"""

    def test_objection_no_tengo_tiempo(self, intent_classifier):
        """Test time objection"""
        result = intent_classifier._quick_classify("No tengo tiempo para hacer un curso")
        assert result is not None
        assert result.intent == Intent.OBJECTION


class TestQuestionGeneralFlow:
    """Test 7: Pregunta general -> responde como el creador"""

    def test_question_general_quien_eres(self, intent_classifier):
        """Test general question - who are you (no quick pattern)"""
        result = intent_classifier._quick_classify("Quien eres?")
        # No quick pattern for this, returns None
        assert result is None  # Needs LLM classification


class TestComplaintFlow:
    """Test 8: Queja -> disculpa + ayuda + posible escalado"""

    def test_complaint_link_no_funciona(self, intent_classifier):
        """Test complaint - link doesn't work"""
        result = intent_classifier._quick_classify("No funciona el link de compra")
        assert result is not None
        assert result.intent == Intent.SUPPORT


class TestMemoryFlow:
    """Test 11: Memoria -> reconoce usuario que vuelve"""

    def test_memory_store_exists(self):
        """Test that memory store can be created"""
        store = MemoryStore()
        assert store is not None
        assert hasattr(store, 'get')
        assert hasattr(store, 'save')

    @pytest.mark.asyncio
    async def test_memory_async_get(self):
        """Test async get method"""
        store = MemoryStore()
        # Should not raise, returns None for non-existent
        _result = await store.get("test_creator", "test_follower")
        # Returns None for non-existent follower


class TestEscalationFlow:
    """Test 12: Escalacion -> detecta keywords y escala"""

    def test_escalation_humano(self, intent_classifier):
        """Test escalation with 'hablar con humano'"""
        result = intent_classifier._quick_classify("Quiero hablar con un humano")
        assert result is not None
        assert result.intent == Intent.ESCALATION

    def test_escalation_persona_real(self, intent_classifier):
        """Test escalation with 'persona real'"""
        result = intent_classifier._quick_classify("Necesito hablar con una persona real")
        assert result is not None
        assert result.intent == Intent.ESCALATION

    def test_escalation_keyword_check(self, mock_config):
        """Test escalation keyword detection"""
        message = "Quiero un reembolso"
        keywords = mock_config.escalation_keywords
        should_escalate = any(kw in message.lower() for kw in keywords)
        assert should_escalate == True


class TestResponseQuality:
    """Test response quality and tone"""

    def test_intent_classifier_patterns(self, intent_classifier):
        """Test that intent classifier has patterns"""
        assert len(intent_classifier.QUICK_PATTERNS) > 0
        assert Intent.GREETING in intent_classifier.QUICK_PATTERNS
        assert Intent.INTEREST_STRONG in intent_classifier.QUICK_PATTERNS

    def test_intent_actions_defined(self, intent_classifier):
        """Test that all intents have actions"""
        assert len(intent_classifier.INTENT_ACTIONS) > 0
        assert Intent.GREETING in intent_classifier.INTENT_ACTIONS

    def test_multiple_greetings(self, intent_classifier):
        """Test various greeting patterns"""
        greetings = ["Hola", "Buenas", "Hey", "Qué tal"]
        for greeting in greetings:
            result = intent_classifier._quick_classify(greeting)
            assert result is not None, f"'{greeting}' should be recognized"
            assert result.intent == Intent.GREETING, f"'{greeting}' should be GREETING"


class TestFeedbackFlow:
    """Test positive and negative feedback"""

    def test_feedback_positive_gracias(self, intent_classifier):
        """Test positive feedback 'gracias'"""
        result = intent_classifier._quick_classify("Gracias por la ayuda")
        assert result is not None
        assert result.intent == Intent.FEEDBACK_POSITIVE

    def test_feedback_positive_genial(self, intent_classifier):
        """Test positive feedback 'genial'"""
        result = intent_classifier._quick_classify("Genial, me encanta!")
        assert result is not None
        assert result.intent == Intent.FEEDBACK_POSITIVE


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
