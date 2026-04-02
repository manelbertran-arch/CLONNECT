"""
Category 2: CALIDAD DE RESPUESTA - Test Especificidad
Tests that verify the DM bot produces specific, personalised responses.

Validates that:
- Generic responses are detected / avoided
- Product details are included in the context
- User name and context are injected into the prompt
- Response variation is achieved (no copy-paste)
- Context detector adapts to different situations (different fields per context)
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
from core.frustration_detector import FrustrationDetector
from core.guardrails import ResponseGuardrail
from core.user_context_loader import UserContext, format_user_context_for_prompt
from services.length_controller import get_length_guidance_prompt

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def creator_data() -> CreatorData:
    """Creator with products for specificity tests."""
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
            description="8-week personalised coaching with weekly sessions, "
            "exercise workbook and private Telegram group.",
            short_description="8-week 1:1 coaching programme",
            price=297.0,
            currency="EUR",
            payment_link="https://pay.hotmart.com/coaching",
        ),
    ]
    data.booking_links = [
        BookingInfo(
            id="book-1",
            meeting_type="discovery",
            title="Discovery Call",
            url="https://calendly.com/test/discovery",
            duration_minutes=30,
        ),
    ]
    data.tone_profile = ToneProfileInfo(
        dialect="neutral",
        formality="informal",
        energy="high",
        emojis="moderate",
        signature_phrases=["vamos!", "dale!"],
    )
    return data


@pytest.fixture
def user_context_named() -> UserContext:
    """User context with name and interests for personalisation tests."""
    return UserContext(
        follower_id="ig_maria_789",
        creator_id="test_creator",
        username="maria_fitness",
        name="Maria",
        top_interests=["fitness", "nutrition"],
        products_discussed=["Coaching Premium"],
    )


@pytest.fixture
def user_context_anonymous() -> UserContext:
    """User context without name for comparison."""
    return UserContext(
        follower_id="ig_anon_000",
        creator_id="test_creator",
    )


@pytest.fixture
def guardrail() -> ResponseGuardrail:
    return ResponseGuardrail()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEspecificidad:
    """Test that responses are specific, personalised, and situation-aware."""

    def test_no_respuesta_generica(self, guardrail: ResponseGuardrail):
        """Guardrail detects off-topic content when user asks about irrelevant subjects."""
        # The guardrail should redirect off-topic queries
        query = "Que opinas del bitcoin?"
        response = "Bitcoin es una criptomoneda descentralizada que fue creada en 2009."

        safe = guardrail.get_safe_response(query, response, context={})

        # The guardrail should redirect to the creator's domain
        assert "fuera de mi" in safe.lower() or "especialidad" in safe.lower()

    def test_menciona_detalles_concretos(self, creator_data: CreatorData):
        """Product details (price, link, description) are included in the formatted context."""
        products_text = format_products_for_prompt(creator_data)

        # Specific details must be present, not generic
        assert "297" in products_text  # Exact price
        assert "hotmart.com" in products_text  # Real link domain
        assert "8-week" in products_text or "8 week" in products_text.lower()  # Duration

    def test_personaliza_respuesta(
        self,
        creator_data: CreatorData,
        user_context_named: UserContext,
        user_context_anonymous: UserContext,
    ):
        """User name and context are included in the prompt when available."""
        # Named user context should include name
        named_section = format_user_context_for_prompt(user_context_named)
        assert "Maria" in named_section
        assert "fitness" in named_section.lower() or "nutrition" in named_section.lower()
        assert "Coaching Premium" in named_section

        # Anonymous user context should be minimal or empty
        anon_section = format_user_context_for_prompt(user_context_anonymous)
        # Should not contain specific personal details (empty context returns "")
        assert "Maria" not in anon_section

    def test_no_copia_paste(self):
        """Length guidance produces different instructions for different contexts."""
        # Different contexts must produce different length guidance
        guidance_saludo = get_length_guidance_prompt("Hola! Como estas?")
        guidance_objecion = get_length_guidance_prompt("Es muy caro, no se si me lo puedo permitir")
        guidance_interes = get_length_guidance_prompt("Me apunto, como pago?")

        # Each guidance should be different (different context, different target)
        assert guidance_saludo != guidance_objecion
        assert guidance_objecion != guidance_interes

        # Greeting guidance should mention short/warm
        assert "greeting" in guidance_saludo.lower() or "short" in guidance_saludo.lower()
        # Objection guidance should mention convincing/value
        assert "objection" in guidance_objecion.lower() or "value" in guidance_objecion.lower()

    def test_adapta_a_situacion(self):
        """Context detector produces different DetectedContext fields for different user situations.

        The new context detector populates context_notes only for: B2B, user name,
        meta-message, correction, objection. Frustration is handled by FrustrationDetector.
        We verify that different situations produce different field values.
        """
        # Greeting
        ctx_greeting = detect_all("Hola, buenas tardes!", is_first_message=True)
        assert ctx_greeting.is_first_message is True

        # Strong purchase interest
        ctx_buy = detect_all("Quiero comprar el coaching, como pago?", is_first_message=False)
        assert ctx_buy.interest_level == "strong"

        # Objection with price concern
        ctx_objection = detect_all("Es muy caro, no puedo pagarlo", is_first_message=False)
        assert ctx_objection.objection_type == "price"

        # Frustration — use FrustrationDetector directly (context_detector stub returns nothing)
        detector = FrustrationDetector()
        # v3: language-agnostic; needs numeric COUNT_RE or burst to trigger
        signals, score = detector.analyze_message(
            "No me entiendes, ya te lo dije 3 veces!!!",
            conversation_id="test_especificidad",
        )
        assert signals.level > 0, f"Expected frustration level > 0, got {signals.level}"

        # B2B context
        ctx_b2b = detect_all(
            "Les escribe Silvia de Bamos, queriamos una colaboracion",
            is_first_message=True,
        )
        assert ctx_b2b.is_b2b is True
        assert ctx_b2b.company_context != ""

        # Each context must produce different field values — verify key distinguishing fields
        # Greeting: is_first_message=True, interest_level="none"
        assert ctx_greeting.interest_level == "none"
        # Buy: interest_level="strong"
        assert ctx_buy.interest_level == "strong"
        # Objection: objection_type="price"
        assert ctx_objection.objection_type == "price"
        # B2B: is_b2b=True
        assert ctx_b2b.is_b2b is True

        # context_notes should differ across contexts that produce them
        all_notes = [
            ctx_greeting.context_notes,
            ctx_buy.context_notes,
            ctx_objection.context_notes,
            ctx_b2b.context_notes,
        ]
        note_strings = [str(sorted(n)) for n in all_notes]
        # At least objection and B2B should have unique context_notes
        assert note_strings[2] != note_strings[0], (
            "Objection and greeting should have different context_notes"
        )
        assert note_strings[3] != note_strings[0], (
            "B2B and greeting should have different context_notes"
        )
