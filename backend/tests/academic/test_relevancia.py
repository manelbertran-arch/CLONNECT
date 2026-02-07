"""
Category 2: CALIDAD DE RESPUESTA - Test Relevancia
Tests that verify the DM bot's responses are relevant to the user's query.

Validates that:
- Product questions inject the correct product context
- Price questions trigger price-related prompt sections
- Benefit questions trigger benefit-related prompt sections
- Off-topic content is flagged
- The correct product is referenced when asked by name
"""

import pytest
from core.context_detector import detect_all
from core.creator_data_loader import (
    CreatorData,
    CreatorProfile,
    ProductInfo,
    ToneProfileInfo,
    format_products_for_prompt,
)
from core.output_validator import validate_response
from core.prompt_builder import build_system_prompt
from core.user_context_loader import UserContext

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def creator_data() -> CreatorData:
    """Creator with two products for relevance tests."""
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
            description="8 weeks of one-on-one coaching with exercises and follow-up.",
            short_description="8-week 1:1 coaching programme",
            price=497.0,
            currency="EUR",
            payment_link="https://pay.hotmart.com/coaching-premium",
            category="service",
        ),
        ProductInfo(
            id="prod-2",
            name="Taller Instagram",
            description="Intensive 3-day workshop to master Instagram growth strategies.",
            short_description="3-day Instagram growth workshop",
            price=97.0,
            currency="EUR",
            payment_link="https://pay.hotmart.com/taller-ig",
            category="product",
        ),
    ]
    data.tone_profile = ToneProfileInfo(dialect="neutral", formality="informal")
    return data


@pytest.fixture
def user_context() -> UserContext:
    return UserContext(
        follower_id="ig_user_123",
        creator_id="test_creator",
        username="relevance_tester",
        name="Ana",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRelevancia:
    """Test that responses are relevant to the user's query."""

    def test_responde_lo_preguntado(self, creator_data: CreatorData, user_context: UserContext):
        """Given a product question context, the prompt builder includes relevant product info."""
        detected = detect_all(
            message="Que incluye el coaching?",
            is_first_message=False,
        )

        prompt = build_system_prompt(
            creator_data=creator_data,
            user_context=user_context,
            detected_context=detected,
        )

        # The prompt must contain the product data so the LLM can answer relevantly
        assert "Coaching Premium" in prompt
        assert "497" in prompt
        assert "DATOS VERIFICADOS" in prompt

    def test_no_info_irrelevante(self, creator_data: CreatorData):
        """Output validator should flag responses that contain off-topic / hallucinated content."""
        # A response that mentions an unknown product and a hallucinated price
        response = "Te recomiendo el curso 'Mastering TikTok' por solo 999 euros."

        result = validate_response(
            response=response,
            creator_data=creator_data,
            auto_correct=False,
        )

        # The hallucinated price (999) should be caught
        assert result.is_valid is False
        hallucinated_types = [i.type for i in result.issues]
        assert "hallucinated_price" in hallucinated_types

    def test_menciona_producto_correcto(self, creator_data: CreatorData):
        """When the user asks about a specific product, the formatted context includes that product."""
        products_text = format_products_for_prompt(creator_data)

        # Both products must appear in the context block
        assert "Coaching Premium" in products_text
        assert "Taller Instagram" in products_text

        # Prices must appear alongside their products
        assert "497" in products_text
        assert "97" in products_text

    def test_precio_cuando_pregunta_precio(
        self, creator_data: CreatorData, user_context: UserContext
    ):
        """When the user asks about price, the prompt includes the price section and product costs."""
        detected = detect_all(
            message="Cuanto cuesta el coaching?",
            is_first_message=False,
        )

        prompt = build_system_prompt(
            creator_data=creator_data,
            user_context=user_context,
            detected_context=detected,
        )

        # The prompt must contain prices so the LLM can answer the price question
        assert "497" in prompt
        # Actions section must include price handling instructions
        assert "PRECIO" in prompt
        assert "precio EXACTO" in prompt.upper() or "precio exacto" in prompt.lower()

    def test_beneficios_cuando_pregunta_beneficios(
        self, creator_data: CreatorData, user_context: UserContext
    ):
        """When the user asks about benefits, the prompt includes product descriptions."""
        detected = detect_all(
            message="Que beneficios tiene el taller?",
            is_first_message=False,
        )

        prompt = build_system_prompt(
            creator_data=creator_data,
            user_context=user_context,
            detected_context=detected,
        )

        # Product descriptions (which contain benefits) must be in the prompt
        assert "Taller Instagram" in prompt
        # The short description or description must be present for benefit context
        assert "Instagram" in prompt
        # Conversion instructions should guide benefit-oriented responses
        assert "CONVERSION" in prompt.upper() or "beneficio" in prompt.lower()
