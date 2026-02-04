"""Tests for length controller."""

import pytest
from services.length_controller import (
    STEFAN_LENGTH_CONFIG,
    detect_message_type,
    enforce_length,
    get_max_length,
    truncate_response,
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


class TestGetMaxLength:
    def test_greeting_short(self):
        assert get_max_length("greeting") == 12

    def test_confirmation_short(self):
        assert get_max_length("confirmation") == 15

    def test_emotional_longer(self):
        assert get_max_length("emotional") == 50

    def test_normal_default(self):
        assert get_max_length("normal") == 28


class TestTruncateResponse:
    def test_no_truncation_needed(self):
        assert truncate_response("Hola!", 20) == "Hola!"

    def test_truncates_at_space(self):
        result = truncate_response("Esto es una respuesta muy larga", 20)
        assert len(result) <= 20
        assert " " not in result[-3:]

    def test_preserves_emoji(self):
        result = truncate_response("Genial hermano que bueno! 😊", 15)
        assert len(result) <= 15

    def test_adds_punctuation(self):
        result = truncate_response("Esto es algo que debería cortarse aquí", 15)
        assert result[-1] in "!.😊💙" or not result[-1].isalnum()


class TestEnforceLength:
    def test_greeting_enforces_short(self):
        response = enforce_length("¡Hola! ¿Cómo estás? Espero que todo bien 😊", "Hola")
        assert len(response) <= 12

    def test_confirmation_enforces_short(self):
        response = enforce_length("¡Perfecto! Me alegra mucho escuchar eso 💪", "Ok")
        assert len(response) <= 15

    def test_question_allows_longer(self):
        response = enforce_length("El precio es de 50 euros por sesión", "¿Cuánto cuesta?")
        assert len(response) <= 38

    def test_emotional_allows_empathy(self):
        response = enforce_length(
            "Entiendo hermano, a veces es difícil pero vas a salir adelante 💪",
            "Estoy pasando por un momento muy difícil",
        )
        assert len(response) <= 50


class TestIntegration:
    def test_stefan_style_lengths(self):
        """Verify responses match Stefan's style."""
        test_cases = [
            ("Hola!", "Ey! 😊"),
            ("Ok", "Dale!"),
            ("Jajaja", "Jaja"),
            ("Gracias!", "A ti!"),
        ]

        for lead_msg, expected_style in test_cases:
            msg_type = detect_message_type(lead_msg)
            max_len = get_max_length(msg_type)
            assert len(expected_style) <= max_len, f"'{expected_style}' exceeds max for {msg_type}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
