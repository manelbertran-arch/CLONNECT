"""
Category 5: EXPERIENCIA USUARIO - Test Humanidad
Tests that verify the bot behaves in a human-like manner, avoiding
robotic repetition and maintaining a consistent personality.

Validates that:
- Response variator produces different outputs for the same input
- Variation service tracks used responses to avoid repetition
- Creator personality data stays constant across calls
- Tone profile humor setting affects prompt output
- Output validator detects robotic patterns (hallucinated links, etc.)
"""

import pytest
from core.creator_data_loader import CreatorData, CreatorProfile, ProductInfo, ToneProfileInfo
from core.output_validator import validate_links
from core.prompt_builder import build_identity_section
from core.response_variation import VariationEngine
from services.response_variator_v2 import ResponseVariatorV2

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def variation_engine() -> VariationEngine:
    """Fresh VariationEngine with no prior history."""
    return VariationEngine()


@pytest.fixture
def variator_v2() -> ResponseVariatorV2:
    """ResponseVariatorV2 with fallback pools (no file dependency)."""
    # Pass a non-existent path so it uses fallback pools only
    return ResponseVariatorV2(pools_path="/dev/null/nonexistent.json")


@pytest.fixture
def creator_data() -> CreatorData:
    """Creator data for personality and validation tests."""
    data = CreatorData(creator_id="test_humanidad")
    data.profile = CreatorProfile(
        id="uuid-hum",
        name="HumanCreator",
        clone_name="stefano bonanno",
        clone_tone="friendly",
        clone_vocabulary="bro, hermano, crack, dale",
    )
    data.products = [
        ProductInfo(
            id="prod-hum-1",
            name="Curso Fitness",
            description="12-week fitness transformation programme.",
            short_description="12-week fitness plan",
            price=297.0,
            currency="EUR",
            payment_link="https://pay.hotmart.com/fitness",
            category="product",
        ),
    ]
    data.tone_profile = ToneProfileInfo(
        dialect="rioplatense",
        formality="informal",
        energy="high",
        humor=True,
        emojis="moderate",
        signature_phrases=["dale!", "vamos!", "crack"],
        vocabulary=["bro", "hermano", "genial"],
        topics_to_avoid=["politica", "religion"],
    )
    return data


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHumanidad:
    """Bot must behave in a human-like, non-repetitive manner."""

    def test_varia_respuestas(self, variation_engine):
        """Response variator produces different outputs for same input.

        When the same greeting response is passed through the engine
        repeatedly for the SAME conversation, the engine should track
        usage and select different greeting variants over time.
        """
        original_response = "Hola! Como estas? Te cuento sobre el curso."
        conv_id = "test_varia"

        outputs = set()
        for _ in range(10):
            varied = variation_engine.vary_response(original_response, conv_id)
            outputs.add(varied)

        # Within the same conversation, the engine tracks usage and picks
        # the least-used greeting variant each time, producing variety
        assert len(outputs) >= 2, (
            f"VariationEngine should produce varied outputs within a "
            f"conversation, got {len(outputs)} unique output(s)"
        )

    def test_no_repetitivo(self, variation_engine):
        """Variation service tracks used responses to avoid repetition.

        When the same conversation ID is used repeatedly, the engine
        should track which greetings/closings were used and prefer
        less-used alternatives.
        """
        conv_id = "test_no_repeat"
        greeting_response = "Hola! Perfecto, te cuento."

        # Call multiple times with the same conv_id
        results = []
        for _ in range(6):
            varied = variation_engine.vary_response(greeting_response, conv_id)
            results.append(varied)

        # Check that usage is being tracked
        stats = variation_engine.get_usage_stats(conv_id)
        assert len(stats) > 0, "VariationEngine should track usage stats for the conversation"

        # At least one greeting category should have usage > 0
        greeting_stats = stats.get("greeting", {})
        if greeting_stats:
            total_uses = sum(greeting_stats.values())
            assert total_uses > 0, "Greeting usage should be tracked after multiple calls"

    def test_personalidad_consistente(self, creator_data):
        """Creator personality data stays constant across calls.

        The identity section built from creator_data must consistently
        contain the same personality elements.
        """
        section_1 = build_identity_section(creator_data)
        section_2 = build_identity_section(creator_data)

        # Deterministic: same input produces same output
        assert (
            section_1 == section_2
        ), "build_identity_section should be deterministic for same input"

        # Must contain core personality elements
        assert "stefano bonanno" in section_1.lower(), "Identity section must include clone_name"
        assert "rioplatense" in section_1.lower(), "Identity section must include dialect"
        assert (
            "informal" in section_1.lower() or "tú" in section_1.lower()
        ), "Identity section must reflect informal formality"

    def test_humor_apropiado(self, creator_data):
        """Tone profile humor setting affects prompt output.

        When humor=True in ToneProfileInfo, the identity section
        or prompt should reflect an energetic, humorous tone.
        When humor=False, the tone should be more restrained.
        """
        # With humor=True (current fixture)
        section_humor = build_identity_section(creator_data)

        # Create a version without humor
        no_humor_data = CreatorData(creator_id="test_no_humor")
        no_humor_data.profile = CreatorProfile(
            id="uuid-nohum",
            name="SeriousCreator",
            clone_name="dr. martinez",
            clone_tone="professional",
        )
        no_humor_data.tone_profile = ToneProfileInfo(
            dialect="neutral",
            formality="formal",
            energy="low",
            humor=False,
            emojis="none",
        )

        section_no_humor = build_identity_section(no_humor_data)

        # Humorous tone should differ from professional tone
        assert (
            section_humor != section_no_humor
        ), "Humorous vs professional identity sections should differ"

        # Professional should mention formal/usted
        assert (
            "formal" in section_no_humor.lower() or "usted" in section_no_humor.lower()
        ), "Professional tone should mention formal/usted"

        # Humorous/friendly should mention amigable/cercano and emoji usage
        assert (
            "amigable" in section_humor.lower() or "cercano" in section_humor.lower()
        ), "Friendly tone should mention amigable/cercano"

        # Emoji usage should differ
        assert (
            "NINGUNO" in section_no_humor or "ninguno" in section_no_humor.lower()
        ), "Professional tone should suppress emojis"

    def test_no_robotic(self, creator_data):
        """Output validator detects robotic patterns.

        Hallucinated links (unauthorized URLs) are a robotic/non-human
        pattern. The validator should catch and flag them.
        """
        # Response with a hallucinated (fake) URL
        robotic_response = (
            "Claro! Puedes comprar el curso aqui: "
            "https://fakeshop.xyz/buy-now-123 y te lo envio!"
        )

        known_links = creator_data.get_known_links()

        # Validate links
        issues, corrected = validate_links(robotic_response, known_links)

        # Should detect the hallucinated link
        assert len(issues) > 0, "Validator should detect hallucinated/unauthorized URLs"
        assert (
            issues[0].type == "hallucinated_link"
        ), f"Issue type should be 'hallucinated_link', got '{issues[0].type}'"

        # Corrected response should have removed the fake URL
        assert (
            "fakeshop.xyz" not in corrected
        ), "Corrected response should not contain the hallucinated URL"
        assert (
            "[enlace removido]" in corrected
        ), "Corrected response should contain the removal placeholder"

        # Verify a valid response passes cleanly
        clean_response = "El curso cuesta 297 euros. Te cuento mas?"
        clean_issues, clean_corrected = validate_links(clean_response, known_links)
        assert len(clean_issues) == 0, "Clean response without URLs should have no link issues"
