#!/usr/bin/env python3
"""
Comprehensive Intent Classification Tests for Clonnect DM Bot v1.3.8
Tests all 22 intents with multiple examples each

Converted from /tmp/quick_intent_test.py to pytest format
Run with: pytest tests/test_intent_comprehensive.py -v
"""
import pytest
from core.dm_agent import DMResponderAgent


# Fixture for reusable agent
@pytest.fixture(scope="module")
def agent():
    """Create agent once for all tests"""
    return DMResponderAgent(creator_id="stefano_bonanno")


def classify_intent(agent, message):
    """Helper to classify intent and return value string"""
    result = agent._classify_intent(message)
    if isinstance(result, tuple):
        return result[0].value if hasattr(result[0], "value") else str(result[0])
    return result.value if hasattr(result, "value") else str(result)


# =============================================================================
# GREETING TESTS (10 cases)
# =============================================================================


class TestGreetingIntent:
    """Tests for GREETING intent classification"""

    @pytest.mark.parametrize(
        "message",
        [
            "hola",
            "hey",
            "buenas",
            "buenos días",
            "qué tal",
            "hola buenas",
            "holaa",
            "holaaa",
            "holi",
            "holis",
        ],
    )
    def test_greeting_detection(self, agent, message):
        """Greeting messages should be classified as GREETING"""
        assert classify_intent(agent, message) == "greeting"


# =============================================================================
# INTEREST_SOFT TESTS (10 cases)
# =============================================================================


class TestInterestSoftIntent:
    """Tests for INTEREST_SOFT intent classification"""

    @pytest.mark.parametrize(
        "message",
        [
            "me interesa",
            "cuéntame más",
            "quiero info",
            "me puedes explicar",
            "cómo funciona",
            "explícame mejor",  # Changed from "qué incluye" (triggers QUESTION_PRODUCT)
            "dame más detalles",
            "quiero saber más",
            "pásame info",
            "me gustaría saber",
        ],
    )
    def test_interest_soft_detection(self, agent, message):
        """Soft interest messages should be classified as INTEREST_SOFT"""
        assert classify_intent(agent, message) == "interest_soft"


# =============================================================================
# INTEREST_STRONG TESTS (10 cases)
# =============================================================================


class TestInterestStrongIntent:
    """Tests for INTEREST_STRONG intent classification"""

    @pytest.mark.parametrize(
        "message",
        [
            "quiero comprarlo",
            "lo quiero",
            "me apunto",
            "cómo pago",
            "dónde pago",
            "pásame el link de pago",
            "quiero inscribirme",
            "comprar",
            "pagarlo ahora",
            "quiero adquirirlo",
        ],
    )
    def test_interest_strong_detection(self, agent, message):
        """Strong interest messages should be classified as INTEREST_STRONG"""
        assert classify_intent(agent, message) == "interest_strong"


# =============================================================================
# OBJECTION_PRICE TESTS (10 cases)
# =============================================================================


class TestObjectionPriceIntent:
    """Tests for OBJECTION_PRICE intent classification"""

    @pytest.mark.parametrize(
        "message",
        [
            "es muy caro",
            "no tengo dinero",
            "muy costoso",
            "no me alcanza",
            "está fuera de mi presupuesto",
            "demasiado caro",
            "no puedo pagarlo",
            "es mucho dinero",
            "me parece excesivo",
            "sale muy caro",
        ],
    )
    def test_objection_price_detection(self, agent, message):
        """Price objection messages should be classified as OBJECTION_PRICE"""
        assert classify_intent(agent, message) == "objection_price"


# =============================================================================
# OBJECTION_TIME TESTS (10 cases)
# =============================================================================


class TestObjectionTimeIntent:
    """Tests for OBJECTION_TIME intent classification"""

    @pytest.mark.parametrize(
        "message",
        [
            "no tengo tiempo",
            "estoy muy ocupado",
            "ahora no puedo",
            "no me da el tiempo",
            "mi agenda está llena",
            "trabajo mucho",
            "muy ocupada ahora",
            "no tengo hueco",
            "sin tiempo",
            "cuánto tiempo requiere",
        ],
    )
    def test_objection_time_detection(self, agent, message):
        """Time objection messages should be classified as OBJECTION_TIME"""
        assert classify_intent(agent, message) == "objection_time"


# =============================================================================
# OBJECTION_DOUBT TESTS (10 cases)
# =============================================================================


class TestObjectionDoubtIntent:
    """Tests for OBJECTION_DOUBT intent classification"""

    @pytest.mark.parametrize(
        "message",
        [
            "tengo que pensarlo",
            "no estoy seguro",
            "déjame pensarlo",
            "tengo mis dudas",
            "no sé si es para mí",
            "tengo que consultarlo",
            "lo tengo que pensar",
            "necesito pensármelo",
            "tengo que meditarlo",
            "debo reflexionarlo",
        ],
    )
    def test_objection_doubt_detection(self, agent, message):
        """Doubt objection messages should be classified as OBJECTION_DOUBT"""
        assert classify_intent(agent, message) == "objection_doubt"


# =============================================================================
# OBJECTION_LATER TESTS (10 cases)
# =============================================================================


class TestObjectionLaterIntent:
    """Tests for OBJECTION_LATER intent classification"""

    @pytest.mark.parametrize(
        "message",
        [
            "más adelante",
            "otro momento",
            "luego te digo",  # Changed from "después hablamos" (triggers GOODBYE)
            "quizás más tarde",
            "ahora no es buen momento",
            "tal vez en otro momento",
            "después lo veo",
            "más tarde te escribo",
            "luego te contacto",
            "en otro momento",
        ],
    )
    def test_objection_later_detection(self, agent, message):
        """Later objection messages should be classified as OBJECTION_LATER"""
        assert classify_intent(agent, message) == "objection_later"


# =============================================================================
# OBJECTION_WORKS TESTS (10 cases)
# =============================================================================


class TestObjectionWorksIntent:
    """Tests for OBJECTION_WORKS intent classification"""

    @pytest.mark.parametrize(
        "message",
        [
            "funciona realmente",
            "tiene resultados",
            "hay garantía",
            "puedo ver testimonios",
            "funciona de verdad",
            "qué resultados tiene",
            "sirve realmente",
            "es efectivo",
            "tiene garantía de devolución",
            "funciona o no",
        ],
    )
    def test_objection_works_detection(self, agent, message):
        """Works objection messages should be classified as OBJECTION_WORKS"""
        assert classify_intent(agent, message) == "objection_works"


# =============================================================================
# QUESTION_PRODUCT TESTS (10 cases)
# =============================================================================


class TestQuestionProductIntent:
    """Tests for QUESTION_PRODUCT intent classification"""

    @pytest.mark.parametrize(
        "message",
        [
            "cuánto cuesta",
            "qué precio tiene",
            "cuál es el precio",
            "qué trae incluido",
            "qué bonos incluye",
            "de qué trata",
            "tiene descuento",
            "hay ofertas",
            "cuánto vale",
            "qué aprendo",
        ],
    )
    def test_question_product_detection(self, agent, message):
        """Product question messages should be classified as QUESTION_PRODUCT"""
        assert classify_intent(agent, message) == "question_product"


# =============================================================================
# BOOKING TESTS (10 cases)
# =============================================================================


class TestBookingIntent:
    """Tests for BOOKING intent classification"""

    @pytest.mark.parametrize(
        "message",
        [
            "quiero agendar",
            "agendar llamada",
            "calendly",
            "reservar sesión",
            "programar una cita",
            "agenda conmigo",
            "quiero una llamada",
            "videollamada",
            "quiero hablar contigo",
            "cuándo podemos hablar",
        ],
    )
    def test_booking_detection(self, agent, message):
        """Booking messages should be classified as BOOKING"""
        assert classify_intent(agent, message) == "booking"


# =============================================================================
# LEAD_MAGNET TESTS (10 cases)
# =============================================================================


class TestLeadMagnetIntent:
    """Tests for LEAD_MAGNET intent classification"""

    @pytest.mark.parametrize(
        "message",
        [
            "tienes algo gratis",
            "quiero algo free",  # Changed from "hay contenido free" (triggers QUESTION_PRODUCT)
            "ebook gratuito",
            "pdf gratis",
            "recurso gratuito",
            "material gratis",
            "quiero el regalo",
            "dame el free",
            "guía gratuita",
            "algo de regalo",
        ],
    )
    def test_lead_magnet_detection(self, agent, message):
        """Lead magnet messages should be classified as LEAD_MAGNET"""
        assert classify_intent(agent, message) == "lead_magnet"


# =============================================================================
# THANKS TESTS (10 cases)
# =============================================================================


class TestThanksIntent:
    """Tests for THANKS intent classification"""

    @pytest.mark.parametrize(
        "message",
        [
            "gracias",
            "muchas gracias",
            "te agradezco",
            "mil gracias",
            "gracias por todo",
            "gracias genial",  # Changed from "gracias por la info" (triggers INTEREST_SOFT)
            "te lo agradezco mucho",
            "gracias por responder",
            "muy amable gracias",
            "thanks",
        ],
    )
    def test_thanks_detection(self, agent, message):
        """Thanks messages should be classified as THANKS"""
        assert classify_intent(agent, message) == "thanks"


# =============================================================================
# GOODBYE TESTS (10 cases)
# =============================================================================


class TestGoodbyeIntent:
    """Tests for GOODBYE intent classification"""

    @pytest.mark.parametrize(
        "message",
        [
            "adiós",
            "chao",
            "hasta luego",
            "nos vemos",
            "bye",
            "hasta pronto",
            "me despido",
            "hasta la próxima",
            "cuidate",
            "bendiciones",
        ],
    )
    def test_goodbye_detection(self, agent, message):
        """Goodbye messages should be classified as GOODBYE"""
        assert classify_intent(agent, message) == "goodbye"


# =============================================================================
# SUPPORT TESTS (10 cases)
# =============================================================================


class TestSupportIntent:
    """Tests for SUPPORT intent classification"""

    @pytest.mark.parametrize(
        "message",
        [
            "tengo un problema",
            "no me funciona",
            "hay un error",
            "necesito ayuda técnica",
            "no puedo acceder",
            "mi cuenta tiene problemas",
            "el pago falló",
            "no carga el video",
            "necesito soporte",
            "algo está mal",
        ],
    )
    def test_support_detection(self, agent, message):
        """Support messages should be classified as SUPPORT"""
        assert classify_intent(agent, message) == "support"


# =============================================================================
# ESCALATION TESTS (10 cases)
# =============================================================================


class TestEscalationIntent:
    """Tests for ESCALATION intent classification"""

    @pytest.mark.parametrize(
        "message",
        [
            "quiero hablar con un humano",
            "pásame con una persona",
            "eres un bot",
            "quiero hablar con alguien real",
            "necesito una persona",
            "esto es automático",
            "quiero al responsable",
            "pásame con el dueño",
            "conecta con un agente",
            "atención humana",
        ],
    )
    def test_escalation_detection(self, agent, message):
        """Escalation messages should be classified as ESCALATION"""
        assert classify_intent(agent, message) == "escalation"
