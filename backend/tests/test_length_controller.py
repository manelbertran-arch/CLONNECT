"""Tests for adaptive length controller based on 2,967 real Stefan messages."""

import pytest
from services.length_controller import (
    CONTEXT_LENGTH_RULES,
    ContextLengthRule,
    STEFAN_LENGTH_CONFIG,
    classify_lead_context,
    detect_message_type,
    enforce_length,
    get_context_rule,
    get_length_guidance_prompt,
    get_soft_max,
)


class TestClassifyLeadContext:
    """Test context classification matches real conversation categories."""

    def test_saludo(self):
        assert classify_lead_context("Hola") == "saludo"
        assert classify_lead_context("Hey!") == "saludo"
        assert classify_lead_context("Buenas tardes") == "saludo"
        assert classify_lead_context("Qué tal") == "saludo"

    def test_pregunta_precio(self):
        assert classify_lead_context("Cuánto cuesta?") == "pregunta_precio"
        assert classify_lead_context("Qué precio tiene?") == "pregunta_precio"
        assert classify_lead_context("Cuanto vale el programa?") == "pregunta_precio"

    def test_pregunta_producto(self):
        assert classify_lead_context("Qué incluye el programa?") == "pregunta_producto"
        assert classify_lead_context("Cómo funciona tu programa?") == "pregunta_producto"
        assert classify_lead_context("Dame detalles del curso") == "pregunta_producto"

    def test_objecion(self):
        assert classify_lead_context("Es un poco caro para mí") == "objecion"
        assert classify_lead_context("No sé si me lo puedo permitir") == "objecion"

    def test_interes(self):
        assert classify_lead_context("Me interesa el programa") == "interes"
        assert classify_lead_context("Quiero saber más") == "interes"
        assert classify_lead_context("Cómo puedo apuntarme?") == "interes"

    def test_agradecimiento(self):
        assert classify_lead_context("Gracias!") == "agradecimiento"
        assert classify_lead_context("Muchas gracias hermano") == "agradecimiento"

    def test_casual(self):
        assert classify_lead_context("Jajaja") == "casual"
        assert classify_lead_context("😂🤣") == "casual"

    def test_story_mention(self):
        assert classify_lead_context("Mentioned you in their story") == "story_mention"

    def test_pregunta_general(self):
        assert classify_lead_context("Cómo te fue en el viaje?") == "pregunta_general"

    def test_otro(self):
        assert classify_lead_context("Me mudé a Barcelona") == "otro"

    def test_inicio_conversacion(self):
        assert classify_lead_context("") == "inicio_conversacion"
        assert classify_lead_context(None) == "inicio_conversacion"


class TestDetectMessageType:
    """detect_message_type is now an alias for classify_lead_context."""

    def test_returns_same_as_classify(self):
        messages = ["Hola", "Cuánto cuesta?", "Jajaja", "Me mudé"]
        for msg in messages:
            assert detect_message_type(msg) == classify_lead_context(msg)


class TestContextRules:
    """Test that context rules reflect real 2,967-message PostgreSQL data."""

    def test_all_contexts_have_rules(self):
        expected = [
            "saludo", "pregunta_precio", "pregunta_producto", "pregunta_general",
            "objecion", "interes", "agradecimiento", "casual",
            "story_mention", "inicio_conversacion", "otro",
        ]
        for ctx in expected:
            assert ctx in CONTEXT_LENGTH_RULES, f"Missing rule for {ctx}"

    def test_objecion_is_longest_median(self):
        """Objections have the longest median (53 chars) - needs persuasion."""
        rule = get_context_rule("objecion")
        assert rule.target == 53
        assert rule.hard_max == 277

    def test_interes_is_shortest_median(self):
        """Interest signals have shortest median (10 chars) - just acknowledge."""
        rule = get_context_rule("interes")
        assert rule.target == 10

    def test_saludo_is_short(self):
        rule = get_context_rule("saludo")
        assert rule.target == 17
        assert rule.hard_max == 44

    def test_pregunta_precio_allows_explanation(self):
        rule = get_context_rule("pregunta_precio")
        assert rule.hard_max == 162

    def test_otro_is_baseline(self):
        """'otro' has the most samples (2386) and represents baseline behavior."""
        rule = get_context_rule("otro")
        assert rule.target == 23
        assert rule.n_samples == 2386

    def test_5x_difference_between_extremes(self):
        """Median varies 5x+ from shortest (interes=10) to longest (objecion=53)."""
        interes = get_context_rule("interes")
        objecion = get_context_rule("objecion")
        ratio = objecion.target / interes.target
        assert ratio >= 5.0

    def test_unknown_context_uses_default(self):
        rule = get_context_rule("nonexistent_type")
        assert rule.target == 23
        assert rule.soft_max == 60


class TestGetSoftMax:
    def test_returns_p90_for_context(self):
        assert get_soft_max("saludo") == 31
        assert get_soft_max("objecion") == 277
        assert get_soft_max("casual") == 42
        assert get_soft_max("interes") == 34


class TestEnforceLength:
    def test_short_response_never_truncated(self):
        response = "Hola! Me alegra que te interese 😊"
        result = enforce_length(response, "Hola")
        assert result == response

    def test_within_hard_max_never_truncated(self):
        """A 200-char response to an objection (hard_max=277) stays intact."""
        response = "Entiendo hermano, " + "a" * 180
        result = enforce_length(response, "Es un poco caro para mí")
        assert result == response

    def test_preserves_price_response(self):
        """Price responses up to 162 chars stay intact."""
        response = "El programa cuesta 97 euros e incluye 12 sesiones de coaching grupal, acceso a la comunidad y soporte por WhatsApp"
        result = enforce_length(response, "Cuánto cuesta?")
        assert result == response

    def test_preserves_objection_handling(self):
        """Objection responses up to 277 chars stay intact."""
        response = "Entiendo tu preocupación. " + "a" * 200
        result = enforce_length(response, "No sé si me lo puedo permitir ahora")
        assert result == response

    def test_never_cuts_mid_sentence(self):
        """Even excessively long responses never get cut mid-word."""
        # With sentence boundaries, it trims at the last one
        response = "Primera frase completa. " + "Otra frase. " * 50 + "Final sin punto"
        result = enforce_length(response, "Hola")
        # Should either return as-is or cut at a ". " boundary
        assert result.endswith(".") or result == response

    def test_context_override(self):
        """Explicit context parameter overrides auto-detection."""
        response = "A" * 100
        # "otro" hard_max=569, so 100 chars should pass
        result = enforce_length(response, "anything", context="otro")
        assert result == response


class TestGetLengthGuidancePrompt:
    def test_includes_target(self):
        hint = get_length_guidance_prompt("Jajaja")
        assert "18" in hint  # casual target

    def test_includes_context_description(self):
        hint = get_length_guidance_prompt("Cuánto cuesta?")
        assert "price" in hint.lower() or "precio" in hint.lower()

    def test_includes_range(self):
        hint = get_length_guidance_prompt("Hola")
        assert "range" in hint.lower() or "rango" in hint.lower()


class TestBackwardCompatibility:
    def test_stefan_config_exists(self):
        """Legacy STEFAN_LENGTH_CONFIG still available."""
        assert STEFAN_LENGTH_CONFIG.target_length == 23
        assert STEFAN_LENGTH_CONFIG.soft_max == 150

    def test_enforce_length_accepts_config(self):
        """Legacy config parameter accepted but ignored gracefully."""
        response = "Hola!"
        result = enforce_length(response, "Hola", config=STEFAN_LENGTH_CONFIG)
        assert result == response


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
