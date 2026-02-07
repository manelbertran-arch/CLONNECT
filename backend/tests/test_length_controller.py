"""Tests for length controller."""

import pytest
from services.length_controller import (
    STEFAN_LENGTH_CONFIG,
    detect_message_type,
    enforce_length,
    get_soft_max,
)


class TestDetectMessageType:
    def test_greeting_simple(self):
        assert detect_message_type("Hola") == "greeting"
        assert detect_message_type("Hey!") == "greeting"
        assert detect_message_type("Buenas") == "greeting"

    def test_confirmation(self):
        assert detect_message_type("Ok") == "confirmation"
        assert detect_message_type("Dale!") == "confirmation"
        assert detect_message_type("Perfecto") == "confirmation"

    def test_emoji_only(self):
        assert detect_message_type("😊") == "emoji_only"
        assert detect_message_type("🔥💪") == "emoji_only"

    def test_laugh(self):
        assert detect_message_type("Jajaja") == "laugh"
        assert detect_message_type("jajaj") == "laugh"

    def test_thanks(self):
        assert detect_message_type("Gracias!") == "thanks"
        assert detect_message_type("Muchas gracias hermano") == "thanks"

    def test_question(self):
        assert detect_message_type("¿Cómo estás?") == "question"
        assert detect_message_type("Qué precio tiene?") == "question"

    def test_normal(self):
        assert detect_message_type("Me mudé a Barcelona") == "normal"


class TestGetSoftMax:
    def test_greeting_allows_reasonable_length(self):
        assert get_soft_max("greeting") == 30

    def test_confirmation_allows_reasonable_length(self):
        assert get_soft_max("confirmation") == 25

    def test_emotional_allows_long(self):
        assert get_soft_max("emotional") == 200

    def test_normal_allows_long(self):
        assert get_soft_max("normal") == 150


class TestEnforceLength:
    def test_never_truncates_short_responses(self):
        """Responses under 200 chars should NEVER be truncated."""
        response = "Hola! Me alegra que te interese el programa! Es perfecto para ti 😊"
        result = enforce_length(response, "Hola")
        assert result == response

    def test_never_truncates_mid_sentence(self):
        """Should never cut a response mid-sentence."""
        response = "Entiendo hermano, a veces es difícil pero vas a salir adelante 💪"
        result = enforce_length(response, "Estoy mal")
        assert result == response

    def test_preserves_price_response(self):
        """Price responses should be complete even if long."""
        response = "El programa cuesta 97€ y incluye 12 sesiones de coaching grupal 💪"
        result = enforce_length(response, "Cuánto cuesta?")
        assert result == response

    def test_preserves_complete_sentences(self):
        """Medium responses should stay intact."""
        response = "Genial crack! El Círculo de Hombres es un espacio de desarrollo personal."
        result = enforce_length(response, "Qué es el círculo?")
        assert result == response


class TestIntegration:
    def test_stefan_config_exists(self):
        """Verify Stefan's config is loaded."""
        assert STEFAN_LENGTH_CONFIG.target_length == 38
        assert STEFAN_LENGTH_CONFIG.soft_max == 150

    def test_stefan_style_examples(self):
        """Verify Stefan's short responses fit within soft limits."""
        short_responses = ["Ey! 😊", "Dale!", "Jaja", "A ti!", "Genial! 😊"]
        for resp in short_responses:
            assert len(resp) <= get_soft_max("greeting")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
