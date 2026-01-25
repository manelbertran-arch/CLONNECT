"""
Tests for core/prompt_builder.py

Tests the Prompt Builder module that constructs the complete system prompt
for LLM by combining creator data, user context, and detected context.

Part of refactor/context-injection-v2
"""

import pytest

from core.context_detector import DetectedContext
from core.creator_data_loader import (
    BookingInfo,
    CreatorData,
    CreatorProfile,
    FAQInfo,
    PaymentMethods,
    ProductInfo,
    ToneProfileInfo,
)
from core.intent_classifier import Intent
from core.prompt_builder import (
    COHERENCE_INSTRUCTION,
    CONVERSION_INSTRUCTION,
    NO_REPETITION_INSTRUCTION,
    PROACTIVE_CLOSE_INSTRUCTION,
    build_actions_section,
    build_alerts_section,
    build_b2b_section,
    build_data_section,
    build_frustration_section,
    build_identity_section,
    build_rules_section,
    build_system_prompt,
    build_user_section,
    get_prompt_summary,
    validate_prompt,
)
from core.user_context_loader import LeadInfo, UserContext, UserPreferences


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_creator_data():
    """Create sample creator data for testing."""
    data = CreatorData(creator_id="test_creator")
    data.profile = CreatorProfile(
        id="test_creator",
        name="Stefano",
        clone_name="Stefano",
        clone_tone="friendly",
    )
    data.tone_profile = ToneProfileInfo(
        dialect="neutral",
        formality="informal",
        energy="high",
        emojis="moderate",
        vocabulary=["dale", "vamos", "genial"],
        signature_phrases=["vamos a por ello"],
    )
    data.products = [
        ProductInfo(
            id="1",
            name="FitPack Challenge",
            price=97.0,
            currency="EUR",
            payment_link="https://pay.example.com/fitpack",
            short_description="12-week fitness transformation",
        ),
        ProductInfo(
            id="2",
            name="Mentoria Premium",
            price=497.0,
            currency="EUR",
            payment_link="https://pay.example.com/mentoria",
            short_description="1:1 coaching for 3 months",
        ),
    ]
    data.booking_links = [
        BookingInfo(
            id="1",
            meeting_type="discovery",
            title="Discovery Call",
            duration_minutes=30,
            price=0,
            url="https://cal.example.com/discovery",
        ),
    ]
    data.payment_methods = PaymentMethods(
        bizum_enabled=True,
        bizum_phone="666123456",
        bank_enabled=True,
        bank_iban="ES1234567890123456789012",
        bank_holder="Stefano Fitness SL",
    )
    data.lead_magnets = [
        ProductInfo(
            id="3",
            name="Guia Gratuita de Fitness",
            price=0.0,
            is_free=True,
            payment_link="https://example.com/guia-gratis",
        ),
    ]
    data.faqs = [
        FAQInfo(
            id="1",
            question="How long is the program?",
            answer="12 weeks of structured content",
        ),
    ]
    return data


@pytest.fixture
def sample_user_context():
    """Create sample user context for testing."""
    ctx = UserContext(
        follower_id="test_follower",
        creator_id="test_creator",
        username="@maria_fit",
        name="Maria",
        preferences=UserPreferences(
            language="es",
            response_style="concise",
            communication_tone="friendly",
        ),
        interests=["fitness", "nutrition"],
        is_first_message=False,
        is_returning_user=True,
        total_messages=5,
        engagement_score=0.7,
        purchase_intent_score=0.6,
    )
    ctx.lead_info = LeadInfo(
        status="active",
        score=75,
        tags=["interested"],
    )
    return ctx


@pytest.fixture
def sample_detected_context():
    """Create sample detected context for testing."""
    ctx = DetectedContext(
        sentiment="neutral",
        frustration_level="none",
        is_b2b=False,
        intent=Intent.QUESTION_PRODUCT,
        intent_confidence=0.85,
        interest_level="soft",
        user_name="Maria",
        is_first_message=False,
    )
    ctx.build_alerts()
    return ctx


# =============================================================================
# TEST INSTRUCTION CONSTANTS
# =============================================================================


class TestInstructionConstants:
    """Tests for instruction constants."""

    def test_proactive_close_instruction_exists(self):
        assert "CIERRE PROACTIVO" in PROACTIVE_CLOSE_INSTRUCTION
        assert "INTERÉS FUERTE" in PROACTIVE_CLOSE_INSTRUCTION

    def test_no_repetition_instruction_exists(self):
        assert "NO REPETIR" in NO_REPETITION_INSTRUCTION
        assert "HISTORIAL" in NO_REPETITION_INSTRUCTION

    def test_coherence_instruction_exists(self):
        assert "COHERENCIA" in COHERENCE_INSTRUCTION
        assert "CONSISTENCIA" in COHERENCE_INSTRUCTION

    def test_conversion_instruction_exists(self):
        assert "CONVERSIÓN" in CONVERSION_INSTRUCTION
        assert "acción" in CONVERSION_INSTRUCTION.lower()


# =============================================================================
# TEST SECTION BUILDERS
# =============================================================================


class TestBuildIdentitySection:
    """Tests for build_identity_section."""

    def test_includes_creator_name(self, sample_creator_data):
        section = build_identity_section(sample_creator_data)
        assert "Stefano" in section

    def test_includes_tone(self, sample_creator_data):
        section = build_identity_section(sample_creator_data)
        assert "energetic" in section or "tono" in section.lower()

    def test_includes_formality(self, sample_creator_data):
        section = build_identity_section(sample_creator_data)
        assert "formalidad" in section.lower() or "tutea" in section.lower()

    def test_includes_emoji_usage(self, sample_creator_data):
        section = build_identity_section(sample_creator_data)
        assert "emoji" in section.lower()

    def test_has_section_markers(self, sample_creator_data):
        section = build_identity_section(sample_creator_data)
        assert "=== IDENTIDAD ===" in section
        assert "=== FIN IDENTIDAD ===" in section


class TestBuildDataSection:
    """Tests for build_data_section."""

    def test_includes_products(self, sample_creator_data):
        section = build_data_section(sample_creator_data)
        assert "FitPack" in section
        assert "97" in section

    def test_includes_booking(self, sample_creator_data):
        section = build_data_section(sample_creator_data)
        assert "Discovery" in section or "RESERVA" in section

    def test_includes_payment_methods(self, sample_creator_data):
        section = build_data_section(sample_creator_data)
        assert "Bizum" in section or "666123456" in section

    def test_has_section_markers(self, sample_creator_data):
        section = build_data_section(sample_creator_data)
        assert "DATOS VERIFICADOS" in section

    def test_includes_rag_when_provided(self, sample_creator_data):
        rag_content = "This is RAG content about fitness tips."
        section = build_data_section(sample_creator_data, rag_content=rag_content)
        assert "fitness tips" in section

    def test_excludes_rag_when_disabled(self, sample_creator_data):
        rag_content = "This is RAG content."
        section = build_data_section(
            sample_creator_data, rag_content=rag_content, include_rag=False
        )
        assert "RAG content" not in section


class TestBuildUserSection:
    """Tests for build_user_section."""

    def test_includes_user_info(self, sample_user_context):
        section = build_user_section(sample_user_context)
        # Should include user context info
        assert section  # Non-empty


class TestBuildAlertsSection:
    """Tests for build_alerts_section."""

    def test_empty_when_no_alerts(self):
        ctx = DetectedContext()
        section = build_alerts_section(ctx)
        assert section == ""

    def test_includes_alerts_when_present(self):
        ctx = DetectedContext(interest_level="strong")
        ctx.build_alerts()
        section = build_alerts_section(ctx)
        assert "ALERTAS" in section or section == ""


class TestBuildRulesSection:
    """Tests for build_rules_section."""

    def test_includes_anti_hallucination(self):
        section = build_rules_section("Stefano")
        assert "ANTI-ALUCINACIÓN" in section

    def test_includes_creator_name_for_escalation(self):
        section = build_rules_section("Stefano")
        assert "Stefano" in section

    def test_includes_prohibitions(self):
        section = build_rules_section("Test")
        assert "NUNCA" in section
        assert "inventes" in section.lower()


class TestBuildActionsSection:
    """Tests for build_actions_section."""

    def test_includes_reservation_when_available(self, sample_creator_data):
        section = build_actions_section(sample_creator_data, "Stefano")
        assert "RESERVA" in section

    def test_includes_payment_when_products_available(self, sample_creator_data):
        section = build_actions_section(sample_creator_data, "Stefano")
        assert "PAGO" in section

    def test_includes_escalation(self, sample_creator_data):
        section = build_actions_section(sample_creator_data, "Stefano")
        assert "ESCALACIÓN" in section
        assert "Stefano" in section


class TestBuildB2BSection:
    """Tests for build_b2b_section."""

    def test_includes_b2b_context(self):
        section = build_b2b_section()
        assert "B2B" in section
        assert "profesional" in section.lower()


class TestBuildFrustrationSection:
    """Tests for build_frustration_section."""

    def test_severe_frustration(self):
        section = build_frustration_section("severe", "Usuario pidió 3 veces")
        assert "MUY FRUSTRADO" in section
        assert "empatía" in section.lower()

    def test_moderate_frustration(self):
        section = build_frustration_section("moderate", "No se siente escuchado")
        assert "FRUSTRADO" in section
        assert "directo" in section.lower()

    def test_mild_frustration(self):
        section = build_frustration_section("mild", "Impaciente")
        assert "impaciente" in section.lower() or "conciso" in section.lower()


# =============================================================================
# TEST MAIN PROMPT BUILDER
# =============================================================================


class TestBuildSystemPrompt:
    """Tests for build_system_prompt main function."""

    def test_includes_all_major_sections(
        self, sample_creator_data, sample_user_context, sample_detected_context
    ):
        prompt = build_system_prompt(
            creator_data=sample_creator_data,
            user_context=sample_user_context,
            detected_context=sample_detected_context,
        )

        # Check major sections
        assert "IDENTIDAD" in prompt
        assert "DATOS VERIFICADOS" in prompt
        assert "ANTI-ALUCINACIÓN" in prompt
        assert "CUÁNDO HACER QUÉ" in prompt

    def test_includes_creator_info(
        self, sample_creator_data, sample_user_context, sample_detected_context
    ):
        prompt = build_system_prompt(
            creator_data=sample_creator_data,
            user_context=sample_user_context,
            detected_context=sample_detected_context,
        )
        assert "Stefano" in prompt

    def test_includes_products(
        self, sample_creator_data, sample_user_context, sample_detected_context
    ):
        prompt = build_system_prompt(
            creator_data=sample_creator_data,
            user_context=sample_user_context,
            detected_context=sample_detected_context,
        )
        assert "FitPack" in prompt
        assert "97" in prompt

    def test_includes_conversion_instructions_by_default(
        self, sample_creator_data, sample_user_context, sample_detected_context
    ):
        prompt = build_system_prompt(
            creator_data=sample_creator_data,
            user_context=sample_user_context,
            detected_context=sample_detected_context,
        )
        assert "NO REPETIR" in prompt
        assert "COHERENCIA" in prompt
        assert "CONVERSIÓN" in prompt

    def test_excludes_conversion_when_disabled(
        self, sample_creator_data, sample_user_context, sample_detected_context
    ):
        prompt = build_system_prompt(
            creator_data=sample_creator_data,
            user_context=sample_user_context,
            detected_context=sample_detected_context,
            include_conversion_instructions=False,
        )
        assert "NO REPETIR" not in prompt
        assert "COHERENCIA" not in prompt

    def test_includes_proactive_close_for_strong_interest(
        self, sample_creator_data, sample_user_context
    ):
        ctx = DetectedContext(interest_level="strong")
        prompt = build_system_prompt(
            creator_data=sample_creator_data,
            user_context=sample_user_context,
            detected_context=ctx,
        )
        assert "CIERRE PROACTIVO" in prompt

    def test_excludes_proactive_close_for_low_interest(
        self, sample_creator_data, sample_user_context
    ):
        ctx = DetectedContext(interest_level="none")
        prompt = build_system_prompt(
            creator_data=sample_creator_data,
            user_context=sample_user_context,
            detected_context=ctx,
        )
        assert "CIERRE PROACTIVO" not in prompt

    def test_includes_b2b_section_when_b2b_detected(
        self, sample_creator_data, sample_user_context
    ):
        ctx = DetectedContext(is_b2b=True, company_context="TestCorp")
        prompt = build_system_prompt(
            creator_data=sample_creator_data,
            user_context=sample_user_context,
            detected_context=ctx,
        )
        assert "B2B" in prompt
        assert "profesional" in prompt.lower()

    def test_includes_frustration_handling_when_frustrated(
        self, sample_creator_data, sample_user_context
    ):
        ctx = DetectedContext(
            frustration_level="severe", frustration_reason="Usuario pidió 3 veces"
        )
        prompt = build_system_prompt(
            creator_data=sample_creator_data,
            user_context=sample_user_context,
            detected_context=ctx,
        )
        assert "FRUSTRADO" in prompt
        assert "empatía" in prompt.lower()


class TestSilviaB2BPrompt:
    """
    CRITICAL TEST: Silvia B2B case should generate appropriate prompt.

    The prompt should:
    1. Include B2B context section
    2. NOT include frustration handling
    3. Include professional collaboration language
    """

    def test_silvia_b2b_prompt(self, sample_creator_data, sample_user_context):
        """Test that Silvia's B2B message generates correct prompt."""
        # Simulate Silvia's detected context
        ctx = DetectedContext(
            sentiment="neutral",
            frustration_level="none",  # NOT frustrated
            is_b2b=True,
            company_context="Bamos - Grupos de estudiantes Erasmus",
            b2b_contact_name="Silvia",
            interest_level="soft",
            user_name="Silvia",
            is_first_message=True,
        )

        prompt = build_system_prompt(
            creator_data=sample_creator_data,
            user_context=sample_user_context,
            detected_context=ctx,
        )

        # Should have B2B section
        assert "B2B" in prompt
        assert "colaboración" in prompt.lower() or "profesional" in prompt.lower()

        # Should NOT have frustration handling
        assert "MUY FRUSTRADO" not in prompt

        # Should mention welcoming first message
        # (alerts section should include first message alert)


# =============================================================================
# TEST UTILITY FUNCTIONS
# =============================================================================


class TestGetPromptSummary:
    """Tests for get_prompt_summary function."""

    def test_detects_sections(
        self, sample_creator_data, sample_user_context, sample_detected_context
    ):
        prompt = build_system_prompt(
            creator_data=sample_creator_data,
            user_context=sample_user_context,
            detected_context=sample_detected_context,
        )
        summary = get_prompt_summary(prompt)

        assert summary["has_identity"] is True
        assert summary["has_data"] is True
        assert summary["has_rules"] is True
        assert summary["has_actions"] is True
        assert summary["total_length"] > 0


class TestValidatePrompt:
    """Tests for validate_prompt function."""

    def test_valid_prompt_no_warnings(
        self, sample_creator_data, sample_user_context, sample_detected_context
    ):
        prompt = build_system_prompt(
            creator_data=sample_creator_data,
            user_context=sample_user_context,
            detected_context=sample_detected_context,
        )
        warnings = validate_prompt(prompt)
        assert len(warnings) == 0

    def test_warns_on_missing_sections(self):
        # Minimal prompt missing sections
        prompt = "Hello, I am an assistant."
        warnings = validate_prompt(prompt)
        assert len(warnings) > 0
        assert any("IDENTITY" in w for w in warnings)

    def test_warns_on_very_long_prompt(
        self, sample_creator_data, sample_user_context, sample_detected_context
    ):
        # Add very long RAG content
        long_rag = "x" * 20000
        prompt = build_system_prompt(
            creator_data=sample_creator_data,
            user_context=sample_user_context,
            detected_context=sample_detected_context,
            rag_content=long_rag,
        )
        warnings = validate_prompt(prompt)
        assert any("long" in w.lower() for w in warnings)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestIntegration:
    """Integration tests for the complete prompt building flow."""

    def test_full_flow_product_inquiry(
        self, sample_creator_data, sample_user_context
    ):
        """Test complete flow for a product inquiry."""
        ctx = DetectedContext(
            intent=Intent.QUESTION_PRODUCT,
            interest_level="soft",
            is_first_message=False,
        )

        prompt = build_system_prompt(
            creator_data=sample_creator_data,
            user_context=sample_user_context,
            detected_context=ctx,
        )

        # Should have product info
        assert "FitPack" in prompt
        assert "97" in prompt

        # Should have soft interest handling (conversion instructions)
        assert "CONVERSIÓN" in prompt

    def test_full_flow_high_intent_purchase(
        self, sample_creator_data, sample_user_context
    ):
        """Test complete flow for high purchase intent."""
        ctx = DetectedContext(
            intent=Intent.INTEREST_STRONG,
            interest_level="strong",
            is_first_message=False,
        )

        prompt = build_system_prompt(
            creator_data=sample_creator_data,
            user_context=sample_user_context,
            detected_context=ctx,
        )

        # Should have proactive close
        assert "CIERRE PROACTIVO" in prompt

        # Should have payment links
        assert "pay.example.com" in prompt

    def test_full_flow_frustrated_user(
        self, sample_creator_data, sample_user_context
    ):
        """Test complete flow for frustrated user."""
        ctx = DetectedContext(
            frustration_level="moderate",
            frustration_reason="User repeated question",
            sentiment="frustrated",
        )

        prompt = build_system_prompt(
            creator_data=sample_creator_data,
            user_context=sample_user_context,
            detected_context=ctx,
        )

        # Should have frustration handling
        assert "FRUSTRADO" in prompt

    def test_empty_creator_data(self, sample_user_context, sample_detected_context):
        """Test with minimal creator data."""
        empty_data = CreatorData(creator_id="empty")

        # Should not raise
        prompt = build_system_prompt(
            creator_data=empty_data,
            user_context=sample_user_context,
            detected_context=sample_detected_context,
        )

        # Should still have basic structure
        assert "IDENTIDAD" in prompt
        assert "ANTI-ALUCINACIÓN" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
