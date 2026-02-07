"""
Category 2: CALIDAD DE RESPUESTA - Test Completitud
Tests that verify the DM bot produces complete, non-truncated responses.

Validates that:
- Responses are not improperly truncated
- Multi-question input is detected correctly
- Sales context prompts include CTA guidance
- Prompts include next-step suggestions
- Length controller allows sufficient length for complete responses
"""

import pytest
from core.context_detector import detect_all
from core.creator_data_loader import (
    BookingInfo,
    CreatorData,
    CreatorProfile,
    ProductInfo,
    ToneProfileInfo,
)
from core.output_validator import smart_truncate
from core.prompt_builder import build_system_prompt
from core.user_context_loader import UserContext
from services.length_controller import classify_lead_context, enforce_length, get_context_rule

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def creator_data() -> CreatorData:
    """Creator with products and booking for completeness tests."""
    data = CreatorData(creator_id="test_creator")
    data.profile = CreatorProfile(
        id="uuid-test",
        name="TestCreator",
        clone_name="TestCreator",
        clone_tone="friendly",
    )
    data.products = [
        ProductInfo(
            id="prod-1",
            name="Coaching Premium",
            description="8-week 1:1 coaching programme with exercises.",
            short_description="8-week coaching",
            price=497.0,
            currency="EUR",
            payment_link="https://pay.hotmart.com/coaching",
        ),
    ]
    data.booking_links = [
        BookingInfo(
            id="book-1",
            meeting_type="discovery",
            title="Free Discovery Call",
            url="https://calendly.com/test/discovery",
            duration_minutes=30,
        ),
    ]
    data.tone_profile = ToneProfileInfo(dialect="neutral", formality="informal")
    return data


@pytest.fixture
def user_context() -> UserContext:
    return UserContext(
        follower_id="ig_user_456",
        creator_id="test_creator",
        username="completeness_tester",
        name="Carlos",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCompletitud:
    """Test that responses are complete and not improperly truncated."""

    def test_responde_todas_preguntas(self):
        """Smart truncate preserves responses that contain important content like URLs."""
        # A response with a URL should NOT be truncated even if long
        response = (
            "El coaching incluye 8 sesiones semanales de 1 hora. "
            "Ademas tienes acceso al grupo privado de soporte. "
            "Si quieres apuntarte, aqui tienes el link: "
            "https://pay.hotmart.com/coaching "
            "Tiene un precio de 497 euros con garantia de 30 dias. "
            "Cualquier duda me dices!"
        )

        truncated, was_truncated = smart_truncate(response, max_chars=200)

        # Should NOT truncate because response contains a URL
        assert was_truncated is False
        assert "https://pay.hotmart.com/coaching" in truncated

    def test_no_deja_preguntas_sin_responder(self):
        """Multi-question input is properly detected as a question context."""
        # A message with multiple questions should be detected appropriately
        message = "Cuanto cuesta? Y que incluye? Y cuanto dura?"
        context = classify_lead_context(message)

        # The price keyword should trigger pregunta_precio (checked first)
        assert context == "pregunta_precio"

    def test_incluye_call_to_action(self, creator_data: CreatorData, user_context: UserContext):
        """Sales context prompts include CTA guidance via conversion instructions."""
        detected = detect_all(
            message="Me interesa el coaching, suena genial",
            is_first_message=False,
        )

        prompt = build_system_prompt(
            creator_data=creator_data,
            user_context=user_context,
            detected_context=detected,
            include_conversion_instructions=True,
        )

        # Conversion instruction must be present (contains CTA guidance)
        assert "CONVERSI" in prompt.upper()  # Matches CONVERSIÓN with accent
        # The CTA examples must be present
        assert (
            "siguiente paso" in prompt.lower() or "Te cuento" in prompt or "link" in prompt.lower()
        )

    def test_incluye_siguiente_paso(self, creator_data: CreatorData, user_context: UserContext):
        """When user shows strong interest, prompt includes proactive close with next steps."""
        detected = detect_all(
            message="Quiero comprar el coaching, como pago?",
            is_first_message=False,
        )

        prompt = build_system_prompt(
            creator_data=creator_data,
            user_context=user_context,
            detected_context=detected,
            include_conversion_instructions=True,
        )

        # Strong interest should trigger proactive close instruction
        assert "CIERRE PROACTIVO" in prompt
        # The proactive close must include guidance for next steps
        assert "siguiente paso" in prompt.lower() or "link" in prompt.lower()

    def test_respuesta_completa_no_truncada(self):
        """Length controller allows sufficient length for different contexts."""
        # Objection context allows the longest responses (hard_max = 277)
        objection_rule = get_context_rule("objecion")
        assert objection_rule.hard_max >= 200  # Must allow detailed objection handling

        # A normal-length objection response should not be truncated
        response = (
            "Entiendo que te parezca una inversion importante. "
            "Pero piensa que en solo 8 semanas vas a tener todas las "
            "herramientas para crecer tu cuenta. Ademas tienes garantia "
            "de 30 dias, asi que no hay riesgo."
        )

        result = enforce_length(
            response=response,
            lead_message="Es muy caro, no se si vale la pena",
            context="objecion",
        )

        # Response should NOT be truncated for objection context
        assert result == response
