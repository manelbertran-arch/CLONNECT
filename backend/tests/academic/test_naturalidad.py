"""
Category 2: CALIDAD DE RESPUESTA - Test Naturalidad
Tests that verify the DM bot's responses sound natural and human-like.

Validates that:
- Robotic patterns are cleaned from responses
- Emoji usage is configured in the prompt
- Length controller sets human-like lengths
- Generic phrases are not left in responses
- Creator personality is injected into prompts
"""

import pytest
from core.creator_data_loader import CreatorData, CreatorProfile, ToneProfileInfo
from core.guardrails import ResponseGuardrail
from core.prompt_builder import build_identity_section
from core.response_fixes import (
    apply_all_response_fixes,
    clean_raw_ctas,
    fix_identity_claim,
    hide_technical_errors,
)
from services.length_controller import get_context_rule

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def creator_data_stefan() -> CreatorData:
    """Creator data mimicking a real personality (Stefan-like) for naturalness tests."""
    data = CreatorData(creator_id="stefano")
    data.profile = CreatorProfile(
        id="uuid-stefan",
        name="stefano",
        clone_name="stefano bonanno",
        clone_tone="friendly",
        clone_vocabulary="cercano, directo, motivador",
    )
    data.tone_profile = ToneProfileInfo(
        dialect="neutral",
        formality="informal",
        energy="high",
        humor=True,
        emojis="moderate",
        signature_phrases=["vamos!", "dale!", "a por ello!"],
        vocabulary=["genial", "brutal", "increible"],
    )
    return data


@pytest.fixture
def guardrail() -> ResponseGuardrail:
    return ResponseGuardrail()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNaturalidad:
    """Test that responses sound natural and human-like."""

    def test_no_suena_robot(self):
        """Response fixes removes robotic patterns like error prefixes and raw CTAs."""
        # A response with error prefix (robotic)
        response_with_error = "ERROR: Connection timeout. Hola! Te cuento sobre el coaching."
        fixed = hide_technical_errors(response_with_error)
        assert "ERROR" not in fixed
        assert "timeout" not in fixed.lower()

        # A response with raw CTAs (robotic / copy-paste from marketing)
        response_with_cta = "El coaching es genial! COMPRA AHORA y no te lo pierdas!"
        fixed_cta = clean_raw_ctas(response_with_cta)
        assert "COMPRA AHORA" not in fixed_cta
        # The natural part should remain
        assert "coaching" in fixed_cta.lower()

    def test_usa_emojis_apropiados(self, creator_data_stefan: CreatorData):
        """Prompt builder configures emoji usage based on creator's tone profile."""
        identity_section = build_identity_section(creator_data_stefan)

        # Stefan has "moderate" emoji setting
        assert "emoji" in identity_section.lower()
        assert "Moderado" in identity_section or "1-2" in identity_section

    def test_longitud_natural(self):
        """Length controller sets human-like lengths based on real message data."""
        # Greeting should be short (real data: median 17 chars)
        saludo_rule = get_context_rule("saludo")
        assert saludo_rule.target <= 30  # Greetings should be concise
        assert saludo_rule.soft_max <= 50  # Even P90 should not be super long

        # Interest signals should be very short (real data: median 10 chars)
        interes_rule = get_context_rule("interes")
        assert interes_rule.target <= 15  # Just acknowledge, don't oversell

        # Objections need longer responses (real data: median 53 chars)
        objecion_rule = get_context_rule("objecion")
        assert objecion_rule.target > saludo_rule.target  # Must be longer than greetings
        assert objecion_rule.hard_max >= 200  # Must allow detailed persuasion

    def test_no_frases_genericas(self):
        """Response fixes removes generic / robotic content from responses."""
        # Identity claim is a generic pattern ("Soy Stefano" should become assistant)
        response_identity = "Hola! Soy Stefano y te voy a ayudar."
        fixed = fix_identity_claim(response_identity, creator_name="Stefano")
        assert "asistente" in fixed.lower()

        # All fixes together should clean up robotic content
        robotic_response = (
            "ERROR: null. Soy Stefano. COMPRA AHORA el coaching. "
            "Visita ://www.example.com para mas info."
        )
        fixed_all = apply_all_response_fixes(robotic_response, creator_name="Stefano")
        assert "ERROR" not in fixed_all
        assert "COMPRA AHORA" not in fixed_all
        assert "asistente" in fixed_all.lower()
        # Broken link should be fixed
        assert "https://www.example.com" in fixed_all

    def test_personalidad_stefan(self, creator_data_stefan: CreatorData):
        """Prompt builder includes creator personality traits in the identity section."""
        identity = build_identity_section(creator_data_stefan)

        # Creator name must appear
        assert "stefano bonanno" in identity.lower()
        # Tone must be described
        assert "amigable" in identity.lower() or "friendly" in identity.lower()
        # Signature phrases or vocabulary must be included
        assert "vamos!" in identity.lower() or "genial" in identity.lower()
        # Formality level must be set
        assert "formalidad" in identity.lower() or "Tutea" in identity
        # Emoji usage must be set
        assert "emoji" in identity.lower()
