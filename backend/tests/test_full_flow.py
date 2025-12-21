#!/usr/bin/env python3
"""
Full Flow Tests for Clonnect DM System.

Tests the complete flow from message input to response generation
using the Manel creator configuration.

Run with: pytest tests/test_full_flow.py -v
"""

import pytest
import asyncio
import os
import sys

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dm_agent import DMResponderAgent, DMResponse
from core.dm_agent import Intent
from core.products import ProductManager
from core.creator_config import CreatorConfigManager
from core.memory import MemoryStore


# Test configuration
CREATOR_ID = "manel"
TEST_FOLLOWER_ID = "test_user_001"


@pytest.fixture
def dm_agent():
    """Create DM agent for testing"""
    return DMResponderAgent(creator_id=CREATOR_ID)


@pytest.fixture
def product_manager():
    """Create product manager for testing"""
    return ProductManager()


@pytest.fixture
def config_manager():
    """Create config manager for testing"""
    return CreatorConfigManager()


@pytest.fixture
def memory_store():
    """Create memory store for testing"""
    return MemoryStore()


class TestCreatorConfiguration:
    """Test creator configuration loading"""

    def test_creator_config_exists(self, config_manager):
        """Test that Manel config exists"""
        config = config_manager.get_config(CREATOR_ID)
        assert config is not None, "Manel config should exist"

    def test_creator_name(self, config_manager):
        """Test creator name is correct"""
        config = config_manager.get_config(CREATOR_ID)
        assert config.name == "Manel"

    def test_creator_personality(self, config_manager):
        """Test creator personality settings"""
        config = config_manager.get_config(CREATOR_ID)
        assert config.personality["tone"] == "cercano"
        assert config.personality["formality"] == "informal"

    def test_escalation_keywords(self, config_manager):
        """Test escalation keywords are set"""
        config = config_manager.get_config(CREATOR_ID)
        assert "urgente" in config.escalation_keywords
        assert "reembolso" in config.escalation_keywords

    def test_system_prompt_generation(self, config_manager):
        """Test system prompt is generated"""
        prompt = config_manager.generate_system_prompt(CREATOR_ID)
        assert "Manel" in prompt
        assert len(prompt) > 100


class TestProductsCatalog:
    """Test products catalog"""

    def test_products_exist(self, product_manager):
        """Test that products are loaded"""
        products = product_manager.get_products(CREATOR_ID)
        assert len(products) >= 3, "Should have at least 3 products"

    def test_curso_automatizacion(self, product_manager):
        """Test main course product"""
        product = product_manager.get_product_by_id(CREATOR_ID, "curso-automatizacion")
        assert product is not None
        assert product.price == 297
        assert "automatizacion" in product.name.lower()

    def test_mentoria_product(self, product_manager):
        """Test mentoria product"""
        product = product_manager.get_product_by_id(CREATOR_ID, "mentoria-1a1")
        assert product is not None
        assert product.price == 1500

    def test_free_ebook(self, product_manager):
        """Test free ebook product"""
        product = product_manager.get_product_by_id(CREATOR_ID, "ebook-gratis")
        assert product is not None
        assert product.price == 0

    def test_product_search(self, product_manager):
        """Test product search by query"""
        results = product_manager.search_products(CREATOR_ID, "automatizar")
        assert len(results) > 0
        # First result should be the automation course
        assert results[0][0].id == "curso-automatizacion"

    def test_objection_handler_precio(self, product_manager):
        """Test price objection handler"""
        response = product_manager.get_objection_response(
            CREATOR_ID, "curso-automatizacion", "precio"
        )
        assert len(response) > 0
        assert "30 dias" in response.lower() or "garantia" in response.lower()


class TestGreetingFlow:
    """Test 1: Saludo -> respuesta personalizada"""

    @pytest.mark.asyncio
    async def test_greeting_hola(self, dm_agent):
        """Test simple greeting 'Hola'"""
        response = await dm_agent.process_dm(
            sender_id=TEST_FOLLOWER_ID,
            message_text="Hola",
            message_id="test_001"
        )
        assert response is not None
        assert response.intent == Intent.GREETING
        assert len(response.response_text) > 0

    @pytest.mark.asyncio
    async def test_greeting_buenas(self, dm_agent):
        """Test greeting 'Buenas'"""
        response = await dm_agent.process_dm(
            sender_id=TEST_FOLLOWER_ID,
            message_text="Buenas!",
            message_id="test_002"
        )
        assert response.intent == Intent.GREETING

    @pytest.mark.asyncio
    async def test_greeting_que_tal(self, dm_agent):
        """Test greeting 'Que tal'"""
        response = await dm_agent.process_dm(
            sender_id=TEST_FOLLOWER_ID,
            message_text="Que tal?",
            message_id="test_003"
        )
        assert response.intent == Intent.GREETING


class TestInterestSoftFlow:
    """Test 2: Interes soft -> menciona producto relevante"""

    @pytest.mark.asyncio
    async def test_interest_soft_general(self, dm_agent):
        """Test soft interest expression"""
        response = await dm_agent.process_dm(
            sender_id="test_interest_001",
            message_text="Me interesa lo que haces",
            message_id="test_010"
        )
        assert response is not None
        assert response.intent in [Intent.INTEREST_SOFT, Intent.INTEREST_STRONG]

    @pytest.mark.asyncio
    async def test_interest_soft_automatizacion(self, dm_agent):
        """Test interest in automation"""
        response = await dm_agent.process_dm(
            sender_id="test_interest_002",
            message_text="Me gustaria aprender a automatizar mi negocio",
            message_id="test_011"
        )
        assert response is not None
        # Should mention product or ask follow-up


class TestInterestStrongFlow:
    """Test 3: Interes fuerte -> da link de compra"""

    @pytest.mark.asyncio
    async def test_interest_strong_quiero_comprar(self, dm_agent):
        """Test strong interest - wants to buy"""
        response = await dm_agent.process_dm(
            sender_id="test_strong_001",
            message_text="Quiero comprar el curso de automatizacion",
            message_id="test_020"
        )
        assert response is not None
        assert response.intent == Intent.INTEREST_STRONG

    @pytest.mark.asyncio
    async def test_interest_strong_donde_compro(self, dm_agent):
        """Test strong interest - where to buy"""
        response = await dm_agent.process_dm(
            sender_id="test_strong_002",
            message_text="Donde puedo comprar el curso?",
            message_id="test_021"
        )
        assert response is not None


class TestObjectionPrecioFlow:
    """Test 4: Objecion 'caro' -> usa handler de objecion"""

    @pytest.mark.asyncio
    async def test_objection_caro(self, dm_agent):
        """Test price objection 'caro'"""
        response = await dm_agent.process_dm(
            sender_id="test_objection_001",
            message_text="Es muy caro para mi",
            message_id="test_030"
        )
        assert response is not None
        assert response.intent == Intent.OBJECTION_PRICE

    @pytest.mark.asyncio
    async def test_objection_no_tengo_dinero(self, dm_agent):
        """Test price objection 'no tengo dinero'"""
        response = await dm_agent.process_dm(
            sender_id="test_objection_002",
            message_text="No tengo dinero para eso",
            message_id="test_031"
        )
        assert response is not None


class TestObjectionTiempoFlow:
    """Test 5: Objecion tiempo -> usa handler"""

    @pytest.mark.asyncio
    async def test_objection_no_tengo_tiempo(self, dm_agent):
        """Test time objection"""
        response = await dm_agent.process_dm(
            sender_id="test_tiempo_001",
            message_text="No tengo tiempo para hacer un curso",
            message_id="test_040"
        )
        assert response is not None
        assert response.intent == Intent.OBJECTION_TIME


class TestQuestionProductFlow:
    """Test 6: Pregunta producto -> responde con beneficios"""

    @pytest.mark.asyncio
    async def test_question_que_incluye(self, dm_agent):
        """Test product question - what's included"""
        response = await dm_agent.process_dm(
            sender_id="test_question_001",
            message_text="Que incluye la mentoria?",
            message_id="test_050"
        )
        assert response is not None
        assert response.intent == Intent.QUESTION_PRODUCT

    @pytest.mark.asyncio
    async def test_question_cuanto_cuesta(self, dm_agent):
        """Test product question - price"""
        response = await dm_agent.process_dm(
            sender_id="test_question_002",
            message_text="Cuanto cuesta el curso?",
            message_id="test_051"
        )
        assert response is not None

    @pytest.mark.asyncio
    async def test_question_como_funciona(self, dm_agent):
        """Test product question - how it works"""
        response = await dm_agent.process_dm(
            sender_id="test_question_003",
            message_text="Como funciona el curso de automatizacion?",
            message_id="test_052"
        )
        assert response is not None


class TestQuestionGeneralFlow:
    """Test 7: Pregunta general -> responde como el creador"""

    @pytest.mark.asyncio
    async def test_question_general_quien_eres(self, dm_agent):
        """Test general question - who are you"""
        response = await dm_agent.process_dm(
            sender_id="test_general_001",
            message_text="Quien eres?",
            message_id="test_060"
        )
        assert response is not None
        assert response.intent == Intent.QUESTION_GENERAL

    @pytest.mark.asyncio
    async def test_question_general_a_que_te_dedicas(self, dm_agent):
        """Test general question - what do you do"""
        response = await dm_agent.process_dm(
            sender_id="test_general_002",
            message_text="A que te dedicas?",
            message_id="test_061"
        )
        assert response is not None


class TestLeadMagnetFlow:
    """Test 7b: Lead magnet -> ofrece ebook gratuito"""

    @pytest.mark.asyncio
    async def test_lead_magnet_algo_gratis(self, dm_agent):
        """Test lead magnet request"""
        response = await dm_agent.process_dm(
            sender_id="test_lead_001",
            message_text="Tienes algo gratis para empezar?",
            message_id="test_070"
        )
        assert response is not None


class TestComplaintFlow:
    """Test 8: Queja -> disculpa + ayuda + posible escalado"""

    @pytest.mark.asyncio
    async def test_complaint_link_no_funciona(self, dm_agent):
        """Test complaint - link doesn't work"""
        response = await dm_agent.process_dm(
            sender_id="test_complaint_001",
            message_text="No funciona el link de compra",
            message_id="test_080"
        )
        assert response is not None
        assert response.intent in [Intent.SUPPORT, Intent.INTEREST_STRONG]

    @pytest.mark.asyncio
    async def test_complaint_problema_acceso(self, dm_agent):
        """Test complaint - access problem"""
        response = await dm_agent.process_dm(
            sender_id="test_complaint_002",
            message_text="Tengo un problema con el acceso al curso",
            message_id="test_081"
        )
        assert response is not None


class TestSpamFlow:
    """Test 9: Spam -> ignora o respuesta minima"""

    @pytest.mark.asyncio
    async def test_spam_message(self, dm_agent):
        """Test spam message handling"""
        response = await dm_agent.process_dm(
            sender_id="test_spam_001",
            message_text="Compra mi producto increible ahora!!!",
            message_id="test_090"
        )
        assert response is not None
        # Should not escalate for spam


class TestGoodbyeFlow:
    """Test 10: Despedida -> cierra conversacion amablemente"""

    @pytest.mark.asyncio
    async def test_goodbye_adios(self, dm_agent):
        """Test goodbye 'adios'"""
        response = await dm_agent.process_dm(
            sender_id="test_bye_001",
            message_text="Adios, gracias por la info",
            message_id="test_100"
        )
        assert response is not None

    @pytest.mark.asyncio
    async def test_goodbye_hasta_luego(self, dm_agent):
        """Test goodbye 'hasta luego'"""
        response = await dm_agent.process_dm(
            sender_id="test_bye_002",
            message_text="Hasta luego!",
            message_id="test_101"
        )
        assert response is not None


class TestMemoryFlow:
    """Test 11: Memoria -> reconoce usuario que vuelve"""

    @pytest.mark.asyncio
    async def test_memory_returning_user(self, dm_agent):
        """Test memory for returning user"""
        follower_id = "test_memory_001"

        # First message
        response1 = await dm_agent.process_dm(
            sender_id=follower_id,
            message_text="Hola, me interesa el curso de automatizacion",
            message_id="test_110"
        )
        assert response1 is not None

        # Second message - should remember
        response2 = await dm_agent.process_dm(
            sender_id=follower_id,
            message_text="Cuanto cuesta?",
            message_id="test_111"
        )
        assert response2 is not None

        # Third message
        response3 = await dm_agent.process_dm(
            sender_id=follower_id,
            message_text="Gracias por la info",
            message_id="test_112"
        )
        assert response3 is not None

    @pytest.mark.asyncio
    async def test_memory_conversation_count(self, dm_agent):
        """Test that conversation count increases"""
        follower_id = "test_memory_002"

        # Send multiple messages
        for i in range(3):
            await dm_agent.process_dm(
                sender_id=follower_id,
                message_text=f"Mensaje {i+1}",
                message_id=f"test_120_{i}"
            )

        # Check follower memory
        follower = await dm_agent.memory_store.get(CREATOR_ID, follower_id)
        assert follower is not None
        assert follower.total_messages >= 3


class TestEscalationFlow:
    """Test 12: Escalacion -> detecta keywords y escala"""

    @pytest.mark.asyncio
    async def test_escalation_urgente(self, dm_agent):
        """Test escalation with 'urgente'"""
        response = await dm_agent.process_dm(
            sender_id="test_escalate_001",
            message_text="Es urgente, necesito hablar contigo",
            message_id="test_130"
        )
        assert response is not None
        assert response.escalate_to_human == True

    @pytest.mark.asyncio
    async def test_escalation_reembolso(self, dm_agent):
        """Test escalation with 'reembolso'"""
        response = await dm_agent.process_dm(
            sender_id="test_escalate_002",
            message_text="Quiero un reembolso",
            message_id="test_131"
        )
        assert response is not None
        assert response.escalate_to_human == True


class TestResponseQuality:
    """Test response quality and tone"""

    @pytest.mark.asyncio
    async def test_response_not_empty(self, dm_agent):
        """Test responses are never empty"""
        messages = ["Hola", "Info", "Precio", "Gracias"]
        for i, msg in enumerate(messages):
            response = await dm_agent.process_dm(
                sender_id=f"test_quality_{i}",
                message_text=msg,
                message_id=f"test_140_{i}"
            )
            assert response.response_text is not None
            assert len(response.response_text) > 0

    @pytest.mark.asyncio
    async def test_response_reasonable_length(self, dm_agent):
        """Test responses are reasonably sized"""
        response = await dm_agent.process_dm(
            sender_id="test_length_001",
            message_text="Cuentame sobre el curso",
            message_id="test_150"
        )
        # Response should be between 10 and 1000 characters
        assert 10 < len(response.response_text) < 1000


class TestIntentClassification:
    """Test intent classification accuracy"""

    @pytest.mark.asyncio
    async def test_intent_greeting(self, dm_agent):
        """Test greeting intents"""
        greetings = ["Hola", "Buenos dias", "Que tal", "Hey"]
        for greeting in greetings:
            response = await dm_agent.process_dm(
                sender_id="test_intent_001",
                message_text=greeting,
                message_id=f"test_160_{greeting}"
            )
            assert response.intent == Intent.GREETING, f"'{greeting}' should be GREETING"

    @pytest.mark.asyncio
    async def test_intent_product_question(self, dm_agent):
        """Test product question intents"""
        questions = [
            "Que incluye el curso?",
            "Cuanto cuesta la mentoria?",
            "Que beneficios tiene?"
        ]
        for q in questions:
            response = await dm_agent.process_dm(
                sender_id="test_intent_002",
                message_text=q,
                message_id=f"test_161_{hash(q)}"
            )
            assert response.intent == Intent.QUESTION_PRODUCT, f"'{q}' should be QUESTION_PRODUCT"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
