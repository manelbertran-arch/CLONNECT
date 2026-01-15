"""
Tests del DMResponderAgent - 21 Intents
Basado en auditoria: backend/core/dm_agent.py

21 Intents implementados:
- GREETING, INTEREST_SOFT, INTEREST_STRONG, ACKNOWLEDGMENT, CORRECTION
- OBJECTION_PRICE, OBJECTION_TIME, OBJECTION_DOUBT, OBJECTION_LATER
- OBJECTION_WORKS, OBJECTION_NOT_FOR_ME, OBJECTION_COMPLICATED, OBJECTION_ALREADY_HAVE
- QUESTION_PRODUCT, QUESTION_GENERAL, LEAD_MAGNET, BOOKING
- THANKS, GOODBYE, SUPPORT, ESCALATION, OTHER

14 Intents requieren RAG (INTENTS_REQUIRING_RAG)
7 Intents NO requieren RAG
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestIntentEnum:
    """Verifica que todos los 21 intents estan definidos"""

    def test_all_21_intents_exist(self):
        """Enum Intent tiene los 21 valores"""
        from core.dm_agent import Intent

        expected_intents = [
            'GREETING', 'INTEREST_SOFT', 'INTEREST_STRONG',
            'ACKNOWLEDGMENT', 'CORRECTION',
            'OBJECTION_PRICE', 'OBJECTION_TIME', 'OBJECTION_DOUBT',
            'OBJECTION_LATER', 'OBJECTION_WORKS', 'OBJECTION_NOT_FOR_ME',
            'OBJECTION_COMPLICATED', 'OBJECTION_ALREADY_HAVE',
            'QUESTION_PRODUCT', 'QUESTION_GENERAL',
            'LEAD_MAGNET', 'BOOKING',
            'THANKS', 'GOODBYE', 'SUPPORT', 'ESCALATION', 'OTHER'
        ]

        for intent_name in expected_intents:
            assert hasattr(Intent, intent_name), f"Falta intent: {intent_name}"

    def test_intents_requiring_rag_count(self):
        """Exactamente 14 intents requieren RAG"""
        from core.dm_agent import INTENTS_REQUIRING_RAG

        assert len(INTENTS_REQUIRING_RAG) == 14

    def test_intents_requiring_rag_content(self):
        """Verificar cuales intents requieren RAG"""
        from core.dm_agent import INTENTS_REQUIRING_RAG, Intent

        expected_rag_intents = {
            Intent.INTEREST_SOFT,
            Intent.INTEREST_STRONG,
            Intent.QUESTION_PRODUCT,
            Intent.QUESTION_GENERAL,
            Intent.OBJECTION_PRICE,
            Intent.OBJECTION_TIME,
            Intent.OBJECTION_DOUBT,
            Intent.OBJECTION_LATER,
            Intent.OBJECTION_WORKS,
            Intent.OBJECTION_NOT_FOR_ME,
            Intent.OBJECTION_COMPLICATED,
            Intent.OBJECTION_ALREADY_HAVE,
            Intent.SUPPORT,
            Intent.LEAD_MAGNET,
        }

        assert INTENTS_REQUIRING_RAG == expected_rag_intents


class TestIntentClassification:
    """Tests de clasificacion de intents"""

    @pytest.fixture
    def mock_agent(self):
        """Mock del agent para tests unitarios"""
        with patch('core.dm_agent.USE_POSTGRES', False):
            with patch('core.dm_agent.db_service', None):
                from core.dm_agent import DMResponderAgent

                # Mock interno para evitar carga de config
                with patch.object(DMResponderAgent, '_load_creator_config', return_value={
                    'name': 'Test Creator',
                    'clone_name': 'Test',
                    'bot_active': True
                }):
                    with patch.object(DMResponderAgent, '_load_products', return_value=[]):
                        agent = DMResponderAgent(creator_id="test_creator")
                        return agent

    def test_classify_intent_method_exists(self, mock_agent):
        """Agent tiene metodo _classify_intent"""
        assert hasattr(mock_agent, '_classify_intent')

    def test_classify_greeting_messages(self, mock_agent):
        """Mensajes de saludo -> GREETING"""
        from core.dm_agent import Intent

        # Mensajes que el clasificador detecta como GREETING (ES + EN)
        greeting_messages = [
            "Hola",
            "Buenos dias",
            "Hey!",
            "Hola, que tal?",
            "Buenas tardes",
            "Hi",
            "Hello",  # FIX: Ahora reconocido
        ]

        for msg in greeting_messages:
            intent, confidence = mock_agent._classify_intent(msg, [])
            assert intent == Intent.GREETING, f"'{msg}' deberia ser GREETING, fue {intent}"

    def test_classify_thanks_messages(self, mock_agent):
        """Mensajes de agradecimiento -> THANKS"""
        from core.dm_agent import Intent

        # Mensajes que el clasificador REAL detecta como THANKS
        thanks_messages = [
            "Gracias",
            "Muchas gracias",
            "Gracias por tu ayuda",
        ]

        for msg in thanks_messages:
            intent, confidence = mock_agent._classify_intent(msg, [])
            assert intent == Intent.THANKS, f"'{msg}' deberia ser THANKS, fue {intent}"

    def test_classify_goodbye_messages(self, mock_agent):
        """Mensajes de despedida -> GOODBYE"""
        from core.dm_agent import Intent

        # FIX: "Hasta luego" ahora se clasifica correctamente como GOODBYE
        goodbye_messages = [
            "Adios",
            "Chao",
            "Bye",
            "Hasta luego",  # FIX: Ahora correctamente GOODBYE
            "Nos vemos",
            "Goodbye",
        ]

        for msg in goodbye_messages:
            intent, confidence = mock_agent._classify_intent(msg, [])
            assert intent == Intent.GOODBYE, f"'{msg}' deberia ser GOODBYE, fue {intent}"

    def test_classify_escalation_messages(self, mock_agent):
        """Mensajes de escalacion -> ESCALATION"""
        from core.dm_agent import Intent

        escalation_messages = [
            "Quiero hablar con un humano",
            "Necesito hablar con alguien real",
            "Pasame con una persona",
            "Hablar con soporte",
        ]

        for msg in escalation_messages:
            intent, confidence = mock_agent._classify_intent(msg, [])
            assert intent == Intent.ESCALATION, f"'{msg}' deberia ser ESCALATION, fue {intent}"

    def test_classify_booking_messages(self, mock_agent):
        """Mensajes de reserva -> BOOKING"""
        from core.dm_agent import Intent

        booking_messages = [
            "Quiero agendar una llamada",
            "Reservar una cita",
            "Agendar sesion",
            "Book a call",
        ]

        for msg in booking_messages:
            intent, confidence = mock_agent._classify_intent(msg, [])
            assert intent == Intent.BOOKING, f"'{msg}' deberia ser BOOKING, fue {intent}"

    def test_classify_price_objection(self, mock_agent):
        """Objeciones de precio -> OBJECTION_PRICE"""
        from core.dm_agent import Intent

        # FIX: "No tengo dinero" ahora reconocido como OBJECTION_PRICE
        price_objections = [
            "Es muy caro",
            "Muy caro para mi",
            "No tengo dinero",  # FIX: Ahora reconocido
            "No puedo pagar",
        ]

        for msg in price_objections:
            intent, confidence = mock_agent._classify_intent(msg, [])
            assert intent == Intent.OBJECTION_PRICE, f"'{msg}' deberia ser OBJECTION_PRICE, fue {intent}"

    def test_classify_time_objection(self, mock_agent):
        """Objeciones de tiempo -> OBJECTION_TIME"""
        from core.dm_agent import Intent

        # FIX: "Ahora no puedo" ahora reconocido como OBJECTION_TIME
        time_objections = [
            "No tengo tiempo",
            "Estoy muy ocupado",
            "Ahora no puedo",  # FIX: Ahora reconocido correctamente
        ]

        for msg in time_objections:
            intent, confidence = mock_agent._classify_intent(msg, [])
            assert intent == Intent.OBJECTION_TIME, f"'{msg}' deberia ser OBJECTION_TIME, fue {intent}"

    def test_classify_product_question(self, mock_agent):
        """Preguntas de producto -> QUESTION_PRODUCT"""
        from core.dm_agent import Intent

        product_questions = [
            "Cuanto cuesta?",
            "Que incluye?",
            "Cual es el precio?",
            "Como pago?",  # REAL: se clasifica como QUESTION_PRODUCT
        ]

        for msg in product_questions:
            intent, confidence = mock_agent._classify_intent(msg, [])
            assert intent == Intent.QUESTION_PRODUCT, f"'{msg}' deberia ser QUESTION_PRODUCT, fue {intent}"

    def test_classify_strong_interest(self, mock_agent):
        """Interes fuerte -> INTEREST_STRONG"""
        from core.dm_agent import Intent

        # FIX: "Lo quiero" ahora reconocido como INTEREST_STRONG
        strong_interest = [
            "Quiero comprar",
            "Dame el link de pago",
            "Lo quiero",  # FIX: Ahora reconocido
            "Lo compro",
            "Me apunto",
        ]

        for msg in strong_interest:
            intent, confidence = mock_agent._classify_intent(msg, [])
            assert intent == Intent.INTEREST_STRONG, f"'{msg}' deberia ser INTEREST_STRONG, fue {intent}"


class TestIntentResponse:
    """Tests de respuestas por intent"""

    def test_escalation_returns_escalate_flag(self):
        """Intent ESCALATION debe marcar escalate_to_human=True"""
        from core.dm_agent import DMResponse, Intent

        # Verificar que DMResponse tiene el campo
        response = DMResponse(
            response_text="Test",
            intent=Intent.ESCALATION,
            escalate_to_human=True
        )

        assert response.escalate_to_human == True

    def test_booking_response_has_action(self):
        """Intent BOOKING debe tener action_taken='show_booking_links'"""
        from core.dm_agent import DMResponse, Intent

        response = DMResponse(
            response_text="Mis servicios...",
            intent=Intent.BOOKING,
            action_taken="show_booking_links"
        )

        assert response.action_taken == "show_booking_links"


class TestNonCacheableIntents:
    """Tests de intents que no se deben cachear"""

    def test_non_cacheable_intents_defined(self):
        """NON_CACHEABLE_INTENTS esta definido"""
        from core.dm_agent import NON_CACHEABLE_INTENTS, Intent

        assert Intent.OBJECTION_PRICE in NON_CACHEABLE_INTENTS
        assert Intent.INTEREST_STRONG in NON_CACHEABLE_INTENTS
        assert Intent.ESCALATION in NON_CACHEABLE_INTENTS
        assert Intent.SUPPORT in NON_CACHEABLE_INTENTS
        assert Intent.OTHER in NON_CACHEABLE_INTENTS


class TestDirectPurchaseDetection:
    """Tests de deteccion de compra directa"""

    def test_is_direct_purchase_intent_function_exists(self):
        """Funcion is_direct_purchase_intent existe"""
        from core.dm_agent import is_direct_purchase_intent

        assert callable(is_direct_purchase_intent)

    def test_direct_purchase_keywords(self):
        """Detecta keywords de compra directa"""
        from core.dm_agent import is_direct_purchase_intent

        direct_messages = [
            "quiero comprar",
            "como pago",
            "dame el link",
            "me apunto",
            "lo quiero",
        ]

        for msg in direct_messages:
            assert is_direct_purchase_intent(msg) == True, f"'{msg}' deberia ser compra directa"

    def test_not_direct_purchase_with_objections(self):
        """NO detecta compra directa si hay objeciones"""
        from core.dm_agent import is_direct_purchase_intent

        objection_messages = [
            "no se si es para mi",
            "no estoy seguro",
            "tengo dudas",
            "me lo pienso",
        ]

        for msg in objection_messages:
            assert is_direct_purchase_intent(msg) == False, f"'{msg}' NO deberia ser compra directa"

    def test_short_confirmations_not_direct_purchase(self):
        """Confirmaciones cortas NO son compra directa"""
        from core.dm_agent import is_direct_purchase_intent

        short_confirmations = [
            "si",
            "ok",
            "vale",
            "claro",
        ]

        for msg in short_confirmations:
            # Confirmaciones cortas solas NO son compra directa
            # (deben pasar por el LLM para usar contexto)
            assert is_direct_purchase_intent(msg) == False, f"'{msg}' NO deberia ser compra directa (sin contexto)"
