"""Tests for BotInstructionsGenerator service.

TDD: Tests written FIRST before implementation.
Part of RELATIONSHIP-DNA feature.
"""

from models.relationship_dna import RelationshipType


class TestBotInstructionsGenerator:
    """Test suite for BotInstructionsGenerator service."""

    def test_generate_for_intima(self):
        """Should generate appropriate instructions for INTIMA relationship."""
        from services.bot_instructions_generator import BotInstructionsGenerator

        generator = BotInstructionsGenerator()
        dna_data = {
            "relationship_type": RelationshipType.INTIMA.value,
            "vocabulary_uses": ["amor", "cariño"],
            "vocabulary_avoids": ["hermano", "bro"],
            "emojis": ["💙", "❤️"],
            "recurring_topics": [],
        }

        result = generator.generate(dna_data)

        assert result is not None
        assert len(result) > 0
        assert "íntim" in result.lower() or "cariño" in result.lower()
        # Should mention vocabulary to use
        assert "amor" in result.lower() or "usa" in result.lower()

    def test_generate_for_amistad(self):
        """Should generate appropriate instructions for AMISTAD_CERCANA."""
        from services.bot_instructions_generator import BotInstructionsGenerator

        generator = BotInstructionsGenerator()
        dna_data = {
            "relationship_type": RelationshipType.AMISTAD_CERCANA.value,
            "vocabulary_uses": ["hermano", "bro"],
            "vocabulary_avoids": ["amor", "cariño"],
            "emojis": ["🙏🏽", "💪🏽"],
            "recurring_topics": ["circulos", "meditacion"],
        }

        result = generator.generate(dna_data)

        assert result is not None
        # Should mention fraternal/close friend tone
        assert "fraternal" in result.lower() or "cercana" in result.lower() or "hermano" in result.lower()

    def test_generate_for_cliente(self):
        """Should generate appropriate instructions for CLIENTE."""
        from services.bot_instructions_generator import BotInstructionsGenerator

        generator = BotInstructionsGenerator()
        dna_data = {
            "relationship_type": RelationshipType.CLIENTE.value,
            "vocabulary_uses": [],
            "vocabulary_avoids": ["hermano", "bro"],
            "emojis": [],
            "recurring_topics": [],
        }

        result = generator.generate(dna_data)

        assert result is not None
        # Should mention professional tone
        assert "profesional" in result.lower() or "cliente" in result.lower()

    def test_include_vocabulary(self):
        """Should include vocabulary instructions when provided."""
        from services.bot_instructions_generator import BotInstructionsGenerator

        generator = BotInstructionsGenerator()
        dna_data = {
            "relationship_type": RelationshipType.AMISTAD_CERCANA.value,
            "vocabulary_uses": ["hermano", "bro", "crack"],
            "vocabulary_avoids": ["amigo", "colega"],
            "emojis": ["🙏🏽"],
            "recurring_topics": [],
        }

        result = generator.generate(dna_data)

        # Should include vocabulary instructions
        assert "hermano" in result.lower() or "bro" in result.lower()
        # Should mention what to avoid
        assert "evita" in result.lower() or "avoid" in result.lower() or "no uses" in result.lower()

    def test_include_golden_examples(self):
        """Should include golden examples in instructions."""
        from services.bot_instructions_generator import BotInstructionsGenerator

        generator = BotInstructionsGenerator()
        dna_data = {
            "relationship_type": RelationshipType.AMISTAD_CERCANA.value,
            "vocabulary_uses": ["hermano"],
            "vocabulary_avoids": [],
            "emojis": ["🙏🏽"],
            "recurring_topics": [],
            "golden_examples": [
                {"lead": "Que tal?", "creator": "Todo bien hermano! Y vos?"},
                {"lead": "Gracias!", "creator": "Un placer bro 🙏🏽"},
            ],
        }

        result = generator.generate(dna_data)

        # Should include example section
        assert "ejemplo" in result.lower() or "example" in result.lower() or "así" in result.lower()
