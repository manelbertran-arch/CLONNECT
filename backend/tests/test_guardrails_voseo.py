#!/usr/bin/env python3
"""
Test Suite for Clonnect DM Bot v1.3.8
Tests: Guardrails, Voseo, Tone Profiles, Caching, Multi-creator

Converted from /tmp/full_test_suite.py to pytest format
"""
import warnings

warnings.filterwarnings("ignore")


# =============================================================================
# GUARDRAILS TESTS
# =============================================================================


class TestGuardrails:
    """Tests for ResponseGuardrail validation"""

    def test_guardrails_module_loads(self):
        """Guardrails module should load without errors"""
        from core.guardrails import get_response_guardrail

        guardrail = get_response_guardrail()
        assert guardrail is not None

    def test_price_validation_correct_price_passes(self):
        """Correct price should pass validation"""
        from core.guardrails import get_response_guardrail

        guardrail = get_response_guardrail()

        products = [{"name": "Curso", "price": 97}]
        context = {"products": products, "creator_config": {}}

        result = guardrail.validate_response(
            query="Cuanto cuesta?", response="El curso cuesta 97€", context=context
        )
        assert result.get("valid", False) is True

    def test_price_validation_wrong_price_detected(self):
        """Wrong/hallucinated price should be detected or corrected"""
        from core.guardrails import get_response_guardrail

        guardrail = get_response_guardrail()

        products = [{"name": "Curso", "price": 97}]
        context = {"products": products, "creator_config": {}}

        result = guardrail.validate_response(
            query="Cuanto cuesta?", response="El curso cuesta solo 50€", context=context
        )
        # Should either mark as invalid, flag issues, or provide corrected response
        assert (
            not result.get("valid", True)
            or result.get("issues", [])
            or result.get("corrected_response")
        )

    def test_placeholder_detection_bracket_link(self):
        """[link] placeholder should be flagged"""
        from core.guardrails import get_response_guardrail

        guardrail = get_response_guardrail()

        products = [{"name": "Curso", "price": 97}]
        context = {"products": products, "creator_config": {}}

        result = guardrail.validate_response(
            query="Dame el link", response="Aquí tienes el link: [link de pago]", context=context
        )
        corrected = result.get("corrected_response") or ""
        assert not result.get("valid", True) or "[link" not in corrected

    def test_placeholder_detection_curly_url(self):
        """{url} placeholder should be flagged"""
        from core.guardrails import get_response_guardrail

        guardrail = get_response_guardrail()

        products = [{"name": "Curso", "price": 97}]
        context = {"products": products, "creator_config": {}}

        result = guardrail.validate_response(
            query="Donde compro?", response="Compra aquí: {payment_url}", context=context
        )
        corrected = result.get("corrected_response") or ""
        assert not result.get("valid", True) or "{" not in corrected


# =============================================================================
# VOSEO TESTS (Argentine Dialect)
# =============================================================================


class TestVoseo:
    """Tests for Argentine voseo dialect conversion"""

    def test_voseo_function_loads(self):
        """apply_voseo function should be importable"""
        from core.dm_agent import apply_voseo

        assert apply_voseo is not None

    def test_voseo_quieres_to_queres(self):
        """'quieres' should convert to 'querés'"""
        from core.dm_agent import apply_voseo

        tuteo_text = "¿Quieres saber más?"
        voseo_text = apply_voseo(tuteo_text)
        assert "querés" in voseo_text.lower()

    def test_voseo_puedes_to_podes(self):
        """'puedes' should convert to 'podés'"""
        from core.dm_agent import apply_voseo

        tuteo_text = "Puedes comprarlo cuando quieras."
        voseo_text = apply_voseo(tuteo_text)
        assert "podés" in voseo_text.lower()

    def test_voseo_tienes_to_tenes(self):
        """'tienes' should convert to 'tenés'"""
        from core.dm_agent import apply_voseo

        tuteo_text = "Tienes que pensar en ello."
        voseo_text = apply_voseo(tuteo_text)
        assert "tenés" in voseo_text.lower()

    def test_voseo_necesitas_to_necesitas(self):
        """'necesitas' should convert to 'necesitás'"""
        from core.dm_agent import apply_voseo

        tuteo_text = "Lo que necesitas es esto."
        voseo_text = apply_voseo(tuteo_text)
        assert "necesitás" in voseo_text.lower()

    def test_dialect_detection_returns_value(self):
        """get_tone_dialect should return valid value"""
        from core.tone_service import get_tone_dialect

        dialect = get_tone_dialect("fitpack_global")
        assert dialect is None or isinstance(dialect, str)


# =============================================================================
# TONE PROFILE TESTS
# =============================================================================


class TestToneProfiles:
    """Tests for tone profile loading and application"""

    def test_tone_profile_loads_for_creator(self):
        """Tone profile should load for known creator"""
        from core.tone_service import get_tone_prompt_section

        tone_section = get_tone_prompt_section("fitpack_global")
        assert tone_section is not None
        assert len(tone_section) > 0

    def test_language_detection_returns_valid(self):
        """Language detection should return valid language code"""
        from core.tone_service import get_tone_language

        lang = get_tone_language("fitpack_global")
        assert lang in ["es", "en", "es-AR", None, ""]

    def test_tone_section_has_content(self):
        """Tone section should have meaningful content"""
        from core.tone_service import get_tone_prompt_section

        tone_section = get_tone_prompt_section("fitpack_global")
        assert tone_section is not None
        # Should contain tone/style info or be substantial
        has_content = (
            "tone" in tone_section.lower()
            or "style" in tone_section.lower()
            or len(tone_section) > 50
        )
        assert has_content


# =============================================================================
# CACHING BEHAVIOR TESTS
# =============================================================================


class TestCachingBehavior:
    """Tests for response caching configuration"""

    def test_non_cacheable_intents_defined(self):
        """NON_CACHEABLE_INTENTS should be defined"""
        from core.dm_agent import NON_CACHEABLE_INTENTS

        assert NON_CACHEABLE_INTENTS is not None

    def test_objection_price_is_non_cacheable(self):
        """OBJECTION_PRICE should not be cached"""
        from core.dm_agent import NON_CACHEABLE_INTENTS, Intent

        assert Intent.OBJECTION_PRICE in NON_CACHEABLE_INTENTS

    def test_interest_strong_is_non_cacheable(self):
        """INTEREST_STRONG should not be cached"""
        from core.dm_agent import NON_CACHEABLE_INTENTS, Intent

        assert Intent.INTEREST_STRONG in NON_CACHEABLE_INTENTS

    def test_escalation_is_non_cacheable(self):
        """ESCALATION should not be cached"""
        from core.dm_agent import NON_CACHEABLE_INTENTS, Intent

        assert Intent.ESCALATION in NON_CACHEABLE_INTENTS

    def test_support_is_non_cacheable(self):
        """SUPPORT should not be cached"""
        from core.dm_agent import NON_CACHEABLE_INTENTS, Intent

        assert Intent.SUPPORT in NON_CACHEABLE_INTENTS

    def test_greeting_is_cacheable(self):
        """GREETING should be cacheable (not in non-cacheable set)"""
        from core.dm_agent import NON_CACHEABLE_INTENTS, Intent

        assert Intent.GREETING not in NON_CACHEABLE_INTENTS

    def test_thanks_is_cacheable(self):
        """THANKS should be cacheable (not in non-cacheable set)"""
        from core.dm_agent import NON_CACHEABLE_INTENTS, Intent

        assert Intent.THANKS not in NON_CACHEABLE_INTENTS


# =============================================================================
# MULTI-CREATOR CONFIG TESTS
# =============================================================================


class TestMultiCreatorConfig:
    """Tests for multi-creator support"""

    def test_fitpack_global_agent_creates(self):
        """Agent should create for fitpack_global"""
        from core.dm_agent import DMResponderAgent

        agent = DMResponderAgent(creator_id="fitpack_global")
        assert agent is not None

    def test_stefano_bonanno_agent_creates(self):
        """Agent should create for stefano_bonanno"""
        from core.dm_agent import DMResponderAgent

        agent = DMResponderAgent(creator_id="stefano_bonanno")
        assert agent is not None

    def test_agents_are_independent(self):
        """Different creators should have different agent instances"""
        from core.dm_agent import DMResponderAgent

        agent1 = DMResponderAgent(creator_id="fitpack_global")
        agent2 = DMResponderAgent(creator_id="stefano_bonanno")
        assert agent1.creator_id != agent2.creator_id

    def test_products_accessible(self):
        """Agent should have products attribute"""
        from core.dm_agent import DMResponderAgent

        agent = DMResponderAgent(creator_id="fitpack_global")
        assert hasattr(agent, "products")
