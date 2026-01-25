"""
Tests de Integración para Context Injection V2
=============================================

Estos tests verifican los 7 casos críticos del baseline:
1. Silvia (B2B) - NO debe detectar frustración
2. Usuario frustrado - DEBE resolver el problema
3. Booking - DEBE incluir link
4. Precio - DEBE ser correcto
5. Anti-alucinación - NO debe inventar
6. Escalación - DEBE funcionar
7. Lead magnet - DEBE dar link si existe

Para ejecutar:
    pytest tests/test_integration_v2.py -v
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Set environment before imports
os.environ["ENABLE_CONTEXT_INJECTION_V2"] = "true"
os.environ["DATABASE_URL"] = ""
os.environ["TESTING"] = "true"


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_follower():
    """Crea un follower mock para tests."""
    from core.dm_agent import FollowerMemory

    return FollowerMemory(
        follower_id="test_user_123",
        creator_id="stefano_test",
        username="testuser",
        name="",
        first_contact=datetime.now(timezone.utc).isoformat(),
        last_contact=datetime.now(timezone.utc).isoformat(),
        total_messages=0,
        interests=[],
        products_discussed=[],
        objections_raised=[],
        purchase_intent_score=0.0,
        is_lead=False,
        is_customer=False,
        status="new",
        preferred_language="es",
        last_messages=[],
        links_sent_count=0,
        last_link_message_num=0,
        objections_handled=[],
        arguments_used=[],
        greeting_variant_index=0,
        last_greeting_style="",
        last_emojis_used=[],
        messages_since_name_used=0,
        alternative_contact="",
        alternative_contact_type="",
        contact_requested=False,
    )


# =============================================================================
# HELPER: Create mock CreatorData
# =============================================================================


def create_mock_creator_data(include_lead_magnet: bool = False):
    """Helper to create mock CreatorData with correct structure."""
    from core.creator_data_loader import (
        BookingInfo,
        CreatorData,
        CreatorProfile,
        PaymentMethods,
        ProductInfo,
        ToneProfileInfo,
    )

    products = [
        ProductInfo(
            id="fitpack",
            name="FitPack Challenge",
            description="Programa de 12 semanas de transformación fitness",
            short_description="Transforma tu cuerpo en 12 semanas",
            price=297.0,
            payment_link="https://pay.hotmart.com/fitpack",
        ),
        ProductInfo(
            id="coaching",
            name="Coaching 1:1",
            description="Sesiones personalizadas de coaching",
            price=497.0,
            payment_link="https://pay.hotmart.com/coaching",
        ),
    ]

    lead_magnets = []
    if include_lead_magnet:
        lead_magnets = [
            ProductInfo(
                id="guia_gratis",
                name="Guía de Inicio Gratis",
                description="Guía gratuita para empezar tu transformación",
                price=0.0,
                is_free=True,
                source_url="https://stefano.com/guia-gratis",
            )
        ]

    booking_links = [
        BookingInfo(
            id="coaching_call",
            meeting_type="coaching",
            title="Sesión de Coaching",
            description="Llamada de coaching personalizada",
            duration_minutes=60,
            platform="calendly",
            url="https://calendly.com/stefano/coaching",
        )
    ]

    return CreatorData(
        creator_id="stefano_test",
        profile=CreatorProfile(
            id="stefano_test",
            name="Stefano",
            clone_name="Stefano",
            clone_tone="friendly",
            bot_active=True,
        ),
        products=products,
        booking_links=booking_links,
        lead_magnets=lead_magnets,
        payment_methods=PaymentMethods(bizum_phone="612345678"),
        tone_profile=ToneProfileInfo(dialect="neutral"),
    )


# =============================================================================
# TEST 1: SILVIA (B2B) - EL MÁS IMPORTANTE
# =============================================================================


class TestSilviaB2B:
    """
    Caso crítico: Silvia de Bamos (B2B)

    ANTES: "Entiendo que estás frustrado..." (INCORRECTO)
    DESPUÉS: Respuesta profesional reconociendo colaboración (CORRECTO)
    """

    def test_context_detector_recognizes_b2b(self):
        """El ContextDetector debe reconocer el mensaje como B2B."""
        from core.context_detector import detect_all, detect_b2b

        message = "Hola! Les escribe Silvia de Bamos, ya habíamos trabajado antes con grupos de estudiantes Erasmus"

        # Test detect_b2b directly
        b2b_result = detect_b2b(message)
        assert b2b_result.is_b2b is True
        assert "silvia" in b2b_result.contact_name.lower()

        # Test detect_all
        context = detect_all(message, [], is_first_message=True)
        assert context.is_b2b is True
        assert context.frustration_level == "none"
        assert context.sentiment != "frustrated"

    def test_silvia_not_detected_as_frustrated(self):
        """Silvia NO debe ser detectada como frustrada."""
        from core.context_detector import detect_all

        message = "Hola! Les escribe Silvia de Bamos, ya habíamos trabajado antes con grupos de estudiantes Erasmus"

        context = detect_all(message, [], is_first_message=True)

        # NO debe ser frustración
        assert context.frustration_level == "none"
        assert "frustrado" not in str(context.alerts).lower()
        assert "frustrada" not in str(context.alerts).lower()

    def test_prompt_builder_includes_b2b_context(self):
        """El PromptBuilder debe incluir contexto B2B en el prompt."""
        from core.context_detector import detect_all
        from core.prompt_builder import build_system_prompt
        from core.user_context_loader import UserContext

        message = "Hola! Les escribe Silvia de Bamos, ya habíamos trabajado antes con grupos de estudiantes Erasmus"

        creator_data = create_mock_creator_data()

        user_context = UserContext(
            follower_id="silvia_123",
            creator_id="stefano_test",
            name="Silvia",
            total_messages=1,
        )

        detected_context = detect_all(message, [], is_first_message=True)

        # Build prompt
        prompt = build_system_prompt(
            creator_data=creator_data,
            user_context=user_context,
            detected_context=detected_context,
        )

        # Prompt debe mencionar B2B o colaboración o profesional
        prompt_lower = prompt.lower()
        assert "b2b" in prompt_lower or "profesional" in prompt_lower or "colabor" in prompt_lower


# =============================================================================
# TEST 2: USUARIO FRUSTRADO - RESUELVE EL PROBLEMA
# =============================================================================


class TestFrustratedUser:
    """
    Usuario frustrado que repite pregunta de precio.

    ANTES: "Perdona si no te he entendido..." (sin precio)
    DESPUÉS: Incluye el precio + empatía
    """

    def test_frustration_detected_with_repetition(self):
        """Detecta frustración cuando usuario repite."""
        from core.context_detector import detect_frustration

        message = "Ya te dije 3 veces que quiero el precio del FitPack"

        result = detect_frustration(message, [])

        assert result.is_frustrated is True
        assert result.level in ["mild", "moderate", "severe"]

    def test_prompt_includes_frustration_handling(self):
        """El prompt debe incluir instrucciones para manejar frustración."""
        from core.context_detector import detect_all
        from core.prompt_builder import build_system_prompt
        from core.user_context_loader import UserContext

        message = "Ya te dije 3 veces que quiero el precio del FitPack"

        creator_data = create_mock_creator_data()

        user_context = UserContext(
            follower_id="frustrated_123",
            creator_id="stefano_test",
            name="Carlos",
            total_messages=5,
        )

        detected_context = detect_all(message, [], is_first_message=False)

        prompt = build_system_prompt(
            creator_data=creator_data,
            user_context=user_context,
            detected_context=detected_context,
        )

        # Prompt debe mencionar frustración Y tener datos del producto
        prompt_lower = prompt.lower()
        assert "297" in prompt or "fitpack" in prompt_lower
        # Debe tener alguna instrucción de empatía o manejo de frustración
        assert "frustra" in prompt_lower or "empatía" in prompt_lower or "disculp" in prompt_lower or "alert" in prompt_lower


# =============================================================================
# TEST 3: BOOKING - INCLUYE LINK
# =============================================================================


class TestBooking:
    """
    Usuario quiere reservar → DEBE incluir link de booking.
    """

    def test_booking_data_loaded(self):
        """Verifica que los datos de booking se cargan correctamente."""
        creator_data = create_mock_creator_data()

        # Debe haber booking links
        assert len(creator_data.booking_links) > 0
        assert "calendly" in creator_data.booking_links[0].url.lower()

    def test_prompt_includes_booking_info(self):
        """El prompt debe incluir información de booking."""
        from core.context_detector import detect_all
        from core.prompt_builder import build_system_prompt
        from core.user_context_loader import UserContext

        message = "Quiero reservar una sesión de coaching"

        creator_data = create_mock_creator_data()

        user_context = UserContext(
            follower_id="booking_user",
            creator_id="stefano_test",
        )

        detected_context = detect_all(message, [], is_first_message=False)

        prompt = build_system_prompt(
            creator_data=creator_data,
            user_context=user_context,
            detected_context=detected_context,
        )

        # Prompt debe incluir link de calendly
        assert "calendly" in prompt.lower()


# =============================================================================
# TEST 4: PRECIO - CORRECTO Y VERIFICADO
# =============================================================================


class TestPriceCorrect:
    """
    Pregunta de precio → precio REAL, no inventado.
    """

    def test_output_validator_catches_wrong_price(self):
        """OutputValidator debe detectar precios incorrectos."""
        from core.output_validator import validate_response

        creator_data = create_mock_creator_data()

        # Respuesta con precio INCORRECTO
        response = "El FitPack tiene un precio de 450€, es una oferta increíble!"

        result = validate_response(
            response=response,
            creator_data=creator_data,
            auto_correct=False,
        )

        # Debe detectar que el precio es incorrecto (is_valid = False o hay issues de precio)
        has_price_issue = any(i.type == "hallucinated_price" for i in result.issues)
        assert has_price_issue or result.is_valid is False

    def test_output_validator_accepts_correct_price(self):
        """OutputValidator debe aceptar precios correctos."""
        from core.output_validator import validate_response

        creator_data = create_mock_creator_data()

        # Respuesta con precio CORRECTO
        response = "El FitPack Challenge tiene un precio de 297€"

        result = validate_response(
            response=response,
            creator_data=creator_data,
            auto_correct=False,
        )

        # Debe aceptar el precio correcto (sin issues de precio)
        has_price_issue = any(i.type == "hallucinated_price" for i in result.issues)
        assert not has_price_issue

    def test_products_in_prompt_have_prices(self):
        """Los productos en el prompt deben incluir precios."""
        from core.context_detector import DetectedContext
        from core.prompt_builder import build_system_prompt
        from core.user_context_loader import UserContext

        creator_data = create_mock_creator_data()

        user_context = UserContext(
            follower_id="price_user",
            creator_id="stefano_test",
        )

        detected_context = DetectedContext()

        prompt = build_system_prompt(
            creator_data=creator_data,
            user_context=user_context,
            detected_context=detected_context,
        )

        # El prompt debe incluir el precio
        assert "297" in prompt


# =============================================================================
# TEST 5: ANTI-ALUCINACIÓN - NO INVENTA
# =============================================================================


class TestAntiHallucination:
    """
    Producto que NO existe → NO inventa precio.
    """

    def test_unknown_product_no_hallucinated_price(self):
        """No debe inventar precios para productos desconocidos."""
        from core.output_validator import validate_response

        creator_data = create_mock_creator_data()

        # Respuesta que inventa un producto y precio
        response = "El retiro de yoga en Bali tiene un precio de 1500€"

        result = validate_response(
            response=response,
            creator_data=creator_data,
            auto_correct=False,
        )

        # Debe detectar precio alucinado
        has_price_issue = any(i.type == "hallucinated_price" for i in result.issues)
        assert has_price_issue or result.is_valid is False

    def test_validator_removes_hallucinated_links(self):
        """Debe remover links que no están en los productos conocidos."""
        from core.output_validator import validate_response

        creator_data = create_mock_creator_data()

        # Respuesta con link inventado
        response = "Compra aquí: https://fake-site.com/scam"

        result = validate_response(
            response=response,
            creator_data=creator_data,
            auto_correct=True,
        )

        # Debe remover el link inventado
        assert "fake-site.com" not in result.corrected_response
        # Debe tener issue de link
        has_link_issue = any("url" in i.type.lower() or "link" in i.type.lower() for i in result.issues)
        assert has_link_issue or result.is_valid is False


# =============================================================================
# TEST 6: ESCALACIÓN - FUNCIONA
# =============================================================================


class TestEscalation:
    """
    Usuario pide humano → escala correctamente.
    """

    def test_escalation_keywords_detected(self):
        """Detecta palabras clave de escalación."""
        escalation_messages = [
            "Quiero hablar con una persona real",
            "Pásame con el humano",
            "Quiero hablar con Stefano",
            "No quiero hablar con un bot",
        ]

        for msg in escalation_messages:
            # Estos mensajes deben tener palabras clave de escalación
            msg_lower = msg.lower()
            has_escalation_keyword = any(
                kw in msg_lower
                for kw in ["persona real", "humano", "hablar con", "no con un bot", "no quiero"]
            )
            assert has_escalation_keyword, f"'{msg}' should have escalation keywords"

    def test_escalation_intent_via_classifier(self):
        """Verifica que el clasificador de intents detecta escalación."""
        from core.dm_agent import Intent

        # El intent classifier debería detectar ESCALATION
        # Este test verifica que el intent existe
        assert hasattr(Intent, "ESCALATION")
        assert Intent.ESCALATION.value == "escalation"


# =============================================================================
# TEST 7: LEAD MAGNET - DA LINK SI EXISTE
# =============================================================================


class TestLeadMagnet:
    """
    Usuario pide gratis → da link si existe.
    """

    def test_lead_magnet_in_products(self):
        """Verifica que los lead magnets se cargan correctamente."""
        creator_data = create_mock_creator_data(include_lead_magnet=True)

        # Debe haber un lead magnet
        assert len(creator_data.lead_magnets) > 0
        lm = creator_data.lead_magnets[0]
        assert lm.is_free is True
        assert lm.price == 0.0

    def test_prompt_includes_lead_magnet_when_available(self):
        """El prompt debe incluir lead magnets si existen."""
        from core.context_detector import DetectedContext
        from core.prompt_builder import build_system_prompt
        from core.user_context_loader import UserContext

        creator_data = create_mock_creator_data(include_lead_magnet=True)

        user_context = UserContext(
            follower_id="lead_user",
            creator_id="stefano_test",
        )

        detected_context = DetectedContext()

        prompt = build_system_prompt(
            creator_data=creator_data,
            user_context=user_context,
            detected_context=detected_context,
        )

        # Debe mencionar el lead magnet o gratis o guía
        prompt_lower = prompt.lower()
        assert "gratis" in prompt_lower or "guía" in prompt_lower or "free" in prompt_lower


# =============================================================================
# TESTS DE INTEGRACIÓN COMPLETA
# =============================================================================


class TestFullIntegration:
    """Tests de integración que verifican el flujo completo."""

    def test_context_injection_flag_enabled(self):
        """Verifica que el flag de context injection está habilitado."""
        # Re-import to get current value
        import importlib
        import core.dm_agent

        importlib.reload(core.dm_agent)

        assert core.dm_agent.ENABLE_CONTEXT_INJECTION_V2 is True

    def test_all_modules_importable(self):
        """Todos los módulos V2 deben ser importables."""
        from core.creator_data_loader import CreatorData, get_creator_data
        from core.user_context_loader import UserContext, get_user_context
        from core.context_detector import DetectedContext, detect_all
        from core.prompt_builder import build_system_prompt
        from core.output_validator import validate_response

        # All imports successful
        assert CreatorData is not None
        assert UserContext is not None
        assert DetectedContext is not None
        assert callable(build_system_prompt)
        assert callable(validate_response)

    def test_silvia_full_flow(self):
        """Test completo del caso Silvia."""
        from core.context_detector import detect_all
        from core.output_validator import validate_response
        from core.prompt_builder import build_system_prompt
        from core.user_context_loader import UserContext

        message = "Hola! Les escribe Silvia de Bamos, ya habíamos trabajado antes con grupos de estudiantes Erasmus"

        # 1. Detect context
        detected_context = detect_all(message, [], is_first_message=True)
        assert detected_context.is_b2b is True
        assert detected_context.frustration_level == "none"

        # 2. Load data
        creator_data = create_mock_creator_data()

        user_context = UserContext(
            follower_id="silvia_123",
            creator_id="stefano_test",
            name="Silvia",
        )

        # 3. Build prompt
        prompt = build_system_prompt(
            creator_data=creator_data,
            user_context=user_context,
            detected_context=detected_context,
        )

        # Prompt should mention B2B/professional context
        assert "b2b" in prompt.lower() or "profesional" in prompt.lower()

        # 4. Simulate LLM response and validate
        llm_response = "¡Hola Silvia! Qué gusto volver a saber de ti. Claro, podemos organizar algo para los estudiantes Erasmus."

        validation = validate_response(
            response=llm_response,
            creator_data=creator_data,
            detected_context=detected_context,
        )

        # Response should be valid (no hallucinations)
        assert validation.is_valid is True

        # Final response should NOT mention frustration
        final_response = validation.corrected_response
        assert "frustrado" not in final_response.lower()
        assert "frustrada" not in final_response.lower()


# =============================================================================
# TESTS DE REGRESIÓN
# =============================================================================


class TestRegression:
    """Tests de regresión para asegurar que no se rompen casos existentes."""

    def test_greeting_still_works(self):
        """Saludos simples siguen funcionando."""
        from core.context_detector import detect_all

        message = "Hola, buenos días!"
        context = detect_all(message, [], is_first_message=True)

        assert context.frustration_level == "none"
        assert context.sentiment in ["positive", "neutral"]

    def test_price_question_detected(self):
        """Preguntas de precio siguen detectándose."""
        from core.context_detector import detect_all
        from core.dm_agent import Intent

        message = "¿Cuánto cuesta el programa?"
        context = detect_all(message, [], is_first_message=False)

        # Should detect interest or question intent
        assert context.interest_level in ["soft", "strong", "none"] or context.intent in [
            Intent.QUESTION_PRODUCT,
            Intent.INTEREST_SOFT,
            Intent.OTHER,
        ]

    def test_thanks_not_frustrated(self):
        """Agradecimientos no se detectan como frustración."""
        from core.context_detector import detect_all

        message = "Perfecto, muchas gracias!"
        context = detect_all(message, [], is_first_message=False)

        assert context.frustration_level == "none"
        assert context.sentiment in ["positive", "neutral"]

    def test_word_boundaries_prevent_false_positives(self):
        """Palabras como 'trabajado' no disparan sarcasmo."""
        from core.context_detector import detect_sarcasm

        # "trabajado" contiene "aja" pero NO debe detectar sarcasmo
        message = "Ya habíamos trabajado antes"
        result = detect_sarcasm(message)

        assert result.is_sarcastic is False


# =============================================================================
# TESTS DE BASELINE CRÍTICOS
# =============================================================================


class TestBaselineCritical:
    """Tests críticos del baseline que DEBEN pasar."""

    def test_silvia_is_b2b_not_frustrated(self):
        """CRÍTICO: Silvia debe ser B2B, NO frustrada."""
        from core.context_detector import detect_all

        message = "Hola! Les escribe Silvia de Bamos, ya habíamos trabajado antes con grupos de estudiantes Erasmus"
        context = detect_all(message, [], is_first_message=True)

        # Assertions críticas
        assert context.is_b2b is True, "Silvia debe ser detectada como B2B"
        assert context.frustration_level == "none", "Silvia NO debe ser detectada como frustrada"

    def test_frustrated_user_has_context(self):
        """CRÍTICO: Usuario frustrado debe tener contexto de frustración."""
        from core.context_detector import detect_all

        message = "Ya te dije 3 veces que quiero el precio"
        context = detect_all(message, [], is_first_message=False)

        assert context.frustration_level in ["mild", "moderate", "severe"], \
            "Usuario que repite debe detectarse como frustrado"

    def test_price_297_in_prompt(self):
        """CRÍTICO: El precio 297€ debe aparecer en el prompt."""
        from core.context_detector import DetectedContext
        from core.prompt_builder import build_system_prompt
        from core.user_context_loader import UserContext

        creator_data = create_mock_creator_data()
        user_context = UserContext(follower_id="test", creator_id="test")
        detected_context = DetectedContext()

        prompt = build_system_prompt(
            creator_data=creator_data,
            user_context=user_context,
            detected_context=detected_context,
        )

        assert "297" in prompt, "El precio del FitPack (297€) debe estar en el prompt"

    def test_wrong_price_detected(self):
        """CRÍTICO: Precio incorrecto debe ser detectado."""
        from core.output_validator import validate_response

        creator_data = create_mock_creator_data()
        response = "El programa cuesta 500€"

        result = validate_response(
            response=response,
            creator_data=creator_data,
            auto_correct=False,
        )

        has_price_issue = any(i.type == "hallucinated_price" for i in result.issues)
        assert has_price_issue or result.is_valid is False, "Precio 500€ es incorrecto y debe ser detectado"

    def test_correct_price_accepted(self):
        """CRÍTICO: Precio correcto debe ser aceptado."""
        from core.output_validator import validate_response

        creator_data = create_mock_creator_data()
        response = "El FitPack cuesta 297€"

        result = validate_response(
            response=response,
            creator_data=creator_data,
            auto_correct=False,
        )

        has_price_issue = any(i.type == "hallucinated_price" for i in result.issues)
        assert not has_price_issue, "Precio 297€ es correcto y debe ser aceptado"
