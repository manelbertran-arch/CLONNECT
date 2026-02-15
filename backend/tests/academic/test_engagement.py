"""
Category 5: EXPERIENCIA USUARIO - Test Engagement
Tests that verify the bot's engagement strategies keep conversations alive
and guide the user toward conversion.

Validates that:
- Sales context includes question prompts to keep conversation going
- Intent analysis for engagement suggests follow-up questions
- Response guidelines include continuation phrases (CTAs)
- Non-farewell context does not prematurely close the conversation
- Product info context includes engaging details (benefits, prices, links)
"""

import pytest
from core.context_detector import detect_all
from core.creator_data_loader import (
    BookingInfo,
    CreatorData,
    CreatorProfile,
    ProductInfo,
    ToneProfileInfo,
    format_products_for_prompt,
)
from core.intent_classifier import Intent, classify_intent_simple
from core.prompt_builder import CONVERSION_INSTRUCTION, PROACTIVE_CLOSE_INSTRUCTION
from core.user_context_loader import UserContext

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def creator_data() -> CreatorData:
    """Creator with products and booking for engagement tests."""
    data = CreatorData(creator_id="test_engagement")
    data.profile = CreatorProfile(
        id="uuid-eng",
        name="EngagementCreator",
        clone_name="Maria",
        clone_tone="friendly",
    )
    data.products = [
        ProductInfo(
            id="prod-eng-1",
            name="Masterclass Ventas",
            description="Aprende a vender por Instagram con estrategias reales.",
            short_description="Masterclass de ventas en Instagram",
            price=197.0,
            currency="EUR",
            payment_link="https://pay.hotmart.com/masterclass-ventas",
            category="product",
        ),
    ]
    data.booking_links = [
        BookingInfo(
            id="book-1",
            meeting_type="discovery",
            title="Llamada de descubrimiento",
            description="30 min free call",
            duration_minutes=30,
            url="https://calendly.com/maria/discovery",
        ),
    ]
    data.tone_profile = ToneProfileInfo(
        dialect="neutral", formality="informal", energy="high", humor=True
    )
    return data


@pytest.fixture
def user_context() -> UserContext:
    return UserContext(
        follower_id="ig_eng_user",
        creator_id="test_engagement",
        username="engaged_follower",
        name="Carlos",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEngagement:
    """Bot must keep conversations alive and guide toward conversion."""

    def test_genera_respuesta_usuario(self, creator_data):
        """Sales context includes question prompts to keep user engaged.

        The CONVERSION_INSTRUCTION constant, which is injected into the
        system prompt, must contain CTAs and engagement patterns.
        """
        # The conversion instruction must include question-style CTAs
        engagement_phrases = [
            "Te cuento más",
            "Quieres que te pase",
            "Reservamos",
        ]
        found = sum(
            1 for phrase in engagement_phrases if phrase.lower() in CONVERSION_INSTRUCTION.lower()
        )
        assert found >= 2, (
            "CONVERSION_INSTRUCTION should include at least 2 engagement "
            f"question prompts, found {found}"
        )

        # Also verify the instruction mentions responding + adding value
        assert (
            "valor" in CONVERSION_INSTRUCTION.lower()
        ), "CONVERSION_INSTRUCTION should mention adding value in responses"
        assert (
            "siguiente paso" in CONVERSION_INSTRUCTION.lower()
        ), "CONVERSION_INSTRUCTION should mention next step"

    def test_hace_preguntas(self):
        """Intent analysis for engagement triggers follow-up suggestions.

        When a user shows soft interest, the intent classification should
        return 'interest_soft' which maps to the 'nurture_and_qualify'
        action -- meaning the bot should ask qualifying questions.
        """
        soft_interest_messages = [
            "Me interesa, cuentame mas",
            "Suena interesante, que incluye?",
            "Quiero saber mas informacion",
        ]

        for msg in soft_interest_messages:
            intent = classify_intent_simple(msg)
            assert intent in ("interest_soft", "question_product"), (
                f"Message '{msg}' should classify as interest_soft or "
                f"question_product, got '{intent}'"
            )

        # Verify the action mapping for interest_soft is nurture-oriented
        from core.intent_classifier import IntentClassifier

        action = IntentClassifier.INTENT_ACTIONS[Intent.INTEREST_SOFT]
        assert (
            "nurture" in action or "qualify" in action
        ), f"INTEREST_SOFT action should be nurture/qualify, got '{action}'"

    def test_invita_continuar(self, creator_data):
        """Response guidelines include continuation phrases.

        The system prompt instructions (CONVERSION_INSTRUCTION,
        PROACTIVE_CLOSE_INSTRUCTION) must contain phrases that invite
        the user to continue the conversation.
        """
        continuation_indicators = [
            "link",
            "siguiente paso",
            "reservar",
            "apuntarte",
        ]

        all_instructions = (CONVERSION_INSTRUCTION + PROACTIVE_CLOSE_INSTRUCTION).lower()

        found = sum(1 for phrase in continuation_indicators if phrase in all_instructions)
        assert found >= 3, (
            "Instructions should contain at least 3 continuation indicators, " f"found {found}"
        )

    def test_no_cierra_conversacion_pronto(self):
        """Non-farewell context does not trigger premature closing.

        When user sends a product question or interest signal, detect_all
        must NOT return a farewell/closing intent.
        """
        active_messages = [
            "Cuanto cuesta el programa?",
            "Me interesa, que incluye?",
            "Hola! Quiero saber mas del curso",
            "Suena bien, como funciona?",
        ]

        for msg in active_messages:
            ctx = detect_all(msg, history=None, is_first_message=False)
            # Intent should NOT be farewell-related
            assert ctx.intent != Intent.OTHER or ctx.interest_level != "none", (
                f"Message '{msg}' should show engagement signals, "
                f"got intent={ctx.intent.value}, interest={ctx.interest_level}"
            )

            # Sentiment should not be negative
            assert (
                ctx.sentiment != "frustrated"
            ), f"Active message '{msg}' should not be classified as frustrated"

    def test_mantiene_interes(self, creator_data):
        """Product info context includes engaging details.

        When product data is formatted for the LLM prompt, it must include
        the price, payment link, and description -- the key elements that
        help the bot provide engaging, actionable responses.
        """
        products_prompt = format_products_for_prompt(creator_data)

        # Must include product name
        assert "Masterclass Ventas" in products_prompt, "Product prompt should include product name"
        # Must include price for transparency
        assert "197" in products_prompt, "Product prompt should include product price"
        # Must include payment link for conversion
        assert "hotmart.com" in products_prompt, "Product prompt should include payment link"
        # Must include description for engagement
        assert (
            "vender" in products_prompt.lower() or "Instagram" in products_prompt
        ), "Product prompt should include descriptive details"
