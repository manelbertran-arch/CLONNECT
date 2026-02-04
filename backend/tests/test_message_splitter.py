"""Tests for the MessageSplitter service."""

import pytest
from services.message_splitter import MessageSplitter, SplitConfig


@pytest.fixture
def splitter():
    """Create a MessageSplitter with default config."""
    return MessageSplitter()


@pytest.fixture
def strict_splitter():
    """Create a MessageSplitter with strict config for testing."""
    config = SplitConfig(
        min_length_to_split=50,
        target_length=30,
        max_length=80,
    )
    return MessageSplitter(config=config)


class TestShouldSplit:
    """Tests for split detection."""

    def test_short_message_no_split(self, splitter):
        """Short messages should not be split."""
        assert not splitter.should_split("Hola! 😊")
        assert not splitter.should_split("Gracias por tu mensaje!")

    def test_long_message_with_sentences_splits(self, splitter):
        """Long messages with sentence breaks should split."""
        msg = (
            "El precio del coaching individual es 150€ por sesión. "
            "Incluye una sesión completa de 90 minutos con seguimiento personalizado."
        )
        assert splitter.should_split(msg)

    def test_long_message_no_breaks_no_split(self, splitter):
        """Long messages without breaks should not split."""
        msg = "El programa de coaching individual tiene un precio de ciento cincuenta euros"
        assert not splitter.should_split(msg)

    def test_paragraph_breaks_splits(self, splitter):
        """Messages with paragraph breaks should split."""
        msg = (
            "El programa de coaching incluye sesiones semanales personalizadas.\n\n"
            "También tendrás acceso al grupo privado de la comunidad."
        )
        assert splitter.should_split(msg)

    def test_exclamation_breaks_splits(self, splitter):
        """Messages with ! followed by text should split."""
        msg = (
            "Genial! Me alegro mucho de que te interese. "
            "El programa de coaching está diseñado para ayudarte a crecer."
        )
        assert splitter.should_split(msg)


class TestSplitting:
    """Tests for actual splitting."""

    def test_single_message_returns_one_part(self, splitter):
        """Short message returns single part."""
        parts = splitter.split("Hola! 😊")
        assert len(parts) == 1
        assert parts[0].text == "Hola! 😊"
        assert parts[0].is_first
        assert parts[0].is_last

    def test_paragraph_split(self, splitter):
        """Paragraph breaks create separate parts."""
        msg = (
            "El precio del coaching individual es 150€ por sesión de 90 minutos.\n\n"
            "Incluye coaching personalizado, seguimiento semanal y acceso al grupo privado."
        )
        parts = splitter.split(msg)
        assert len(parts) == 2
        assert "150€" in parts[0].text
        assert "coaching personalizado" in parts[1].text

    def test_sentence_split(self, splitter):
        """Sentence endings create separate parts."""
        msg = (
            "Perfecto! Me encanta mucho que te interese el programa de coaching. "
            "Te cuento los detalles y beneficios que incluye la membresía."
        )
        parts = splitter.split(msg)
        assert len(parts) >= 2

    def test_first_last_flags(self, splitter):
        """First and last flags are set correctly."""
        msg = "Primera parte. Segunda parte. Tercera parte."
        parts = splitter.split(msg)

        if len(parts) > 1:
            assert parts[0].is_first
            assert not parts[0].is_last
            assert not parts[-1].is_first
            assert parts[-1].is_last

    def test_max_parts_limit(self, splitter):
        """Should not exceed max_parts."""
        msg = "Uno. Dos. Tres. Cuatro. Cinco. Seis. Siete. Ocho."
        parts = splitter.split(msg)
        assert len(parts) <= splitter.config.max_parts


class TestDelays:
    """Tests for delay calculation."""

    def test_first_part_has_delay(self, splitter):
        """First part should have reading/thinking delay."""
        parts = splitter.split("Hola! Cómo estás?", "Buenas!")
        assert parts[0].delay_before >= 2.0  # Minimum delay

    def test_inter_message_delay_shorter(self, splitter):
        """Delays between parts should be shorter."""
        msg = "Primera parte del mensaje bastante largo.\n\nSegunda parte también larga."
        parts = splitter.split(msg, "Hola")

        if len(parts) > 1:
            # First delay (reading + thinking) should be longer
            first_delay = parts[0].delay_before
            # Second delay (just typing) should be shorter
            second_delay = parts[1].delay_before
            # First delay includes reading time, should be >= minimum
            assert first_delay >= 2.0
            # Second delay is inter-message (shorter)
            assert second_delay <= splitter.config.inter_message_delay_max

    def test_delay_within_range(self, splitter):
        """Inter-message delays should be within configured range."""
        msg = "Parte uno muy larga. Parte dos también. Parte tres aquí."
        parts = splitter.split(msg)

        for part in parts[1:]:  # Skip first
            assert part.delay_before >= splitter.config.inter_message_delay_min
            assert part.delay_before <= splitter.config.inter_message_delay_max


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_message(self, splitter):
        """Empty message should return single empty part."""
        parts = splitter.split("")
        assert len(parts) == 1
        assert parts[0].text == ""

    def test_only_emoji(self, splitter):
        """Emoji-only message should not split."""
        parts = splitter.split("💙")
        assert len(parts) == 1
        assert parts[0].text == "💙"

    def test_newline_only_message(self, splitter):
        """Message with only newlines should not create empty parts."""
        msg = "Hola!\n\n\n\nCómo estás?"
        parts = splitter.split(msg)
        for part in parts:
            assert part.text.strip() != ""

    def test_preserves_emoji_at_end(self, splitter):
        """Emoji at end of sentence should stay with text."""
        msg = "Gracias por tu mensaje! 😊 Me encanta poder ayudarte."
        parts = splitter.split(msg)
        # Check that emoji stays with its sentence
        for part in parts:
            if "😊" in part.text:
                assert "Gracias" in part.text or len(part.text) > 2


class TestRealWorldExamples:
    """Tests with real-world message examples."""

    def test_coaching_price_response(self, splitter):
        """Typical coaching price response."""
        msg = (
            "El precio del coaching individual es 150€ por sesión. "
            "Cada sesión dura 90 minutos. "
            "Te interesa que agendemos una primera sesión?"
        )
        parts = splitter.split(msg)
        assert 1 <= len(parts) <= 3

    def test_greeting_with_question(self, splitter):
        """Greeting followed by question."""
        msg = "Hola! Qué tal? Me alegra que me escribas. En qué te puedo ayudar?"
        parts = splitter.split(msg)
        assert len(parts) >= 1

    def test_list_response(self, splitter):
        """Response with implicit list."""
        msg = (
            "El programa incluye:\n"
            "- Sesiones semanales\n"
            "- Acceso al grupo privado\n"
            "- Material de trabajo"
        )
        parts = splitter.split(msg)
        # Lists are tricky, should handle gracefully
        assert len(parts) >= 1
        total_text = " ".join(p.text for p in parts)
        assert "semanales" in total_text
        assert "grupo" in total_text

    def test_short_confirmation(self, splitter):
        """Short confirmations should not split."""
        msg = "Perfecto! 😊"
        parts = splitter.split(msg)
        assert len(parts) == 1
        assert parts[0].text == "Perfecto! 😊"


class TestTotalDelay:
    """Tests for total delay calculation."""

    def test_total_delay_sum(self, splitter):
        """Total delay should be sum of all parts."""
        msg = "Primera parte. Segunda parte. Tercera parte."
        parts = splitter.split(msg)
        total = splitter.get_total_delay(parts)
        expected = sum(p.delay_before for p in parts)
        assert total == expected


class TestFormatDebug:
    """Tests for debug formatting."""

    def test_format_includes_part_count(self, splitter):
        """Debug format should include part count."""
        msg = "Primera parte larga. Segunda parte también."
        parts = splitter.split(msg)
        debug = splitter.format_for_debug(parts)
        assert f"Split into {len(parts)} parts" in debug

    def test_format_includes_delays(self, splitter):
        """Debug format should include delays."""
        msg = "Primera parte. Segunda parte."
        parts = splitter.split(msg)
        debug = splitter.format_for_debug(parts)
        assert "s)" in debug  # Seconds indicator


class TestCustomConfig:
    """Tests for custom configuration."""

    def test_custom_min_length(self):
        """Custom min_length_to_split should be respected."""
        config = SplitConfig(min_length_to_split=200)
        splitter = MessageSplitter(config=config)

        msg = "Este mensaje tiene más de 80 chars. Pero menos de 200. No debería dividirse."
        assert not splitter.should_split(msg)

    def test_custom_max_parts(self):
        """Custom max_parts should be respected."""
        config = SplitConfig(max_parts=2)
        splitter = MessageSplitter(config=config)

        msg = "Uno. Dos. Tres. Cuatro. Cinco."
        parts = splitter.split(msg)
        assert len(parts) <= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
