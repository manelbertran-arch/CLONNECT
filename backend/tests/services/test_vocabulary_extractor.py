"""Tests for VocabularyExtractor service.

TDD: Tests written FIRST before implementation.
Part of RELATIONSHIP-DNA feature.
"""

from models.relationship_dna import RelationshipType


class TestVocabularyExtractor:
    """Test suite for VocabularyExtractor service."""

    def test_extract_common_words(self):
        """Should extract commonly used words from messages."""
        from services.vocabulary_extractor import VocabularyExtractor

        extractor = VocabularyExtractor()
        messages = [
            "Hola hermano, que tal?",
            "Muy bien hermano! Y vos?",
            "Todo genial hermano, gracias por preguntar",
        ]

        result = extractor.extract_common_words(messages)

        assert "hermano" in result
        assert len(result) <= 10  # Should limit results

    def test_extract_emojis(self):
        """Should extract emojis from messages."""
        from services.vocabulary_extractor import VocabularyExtractor

        extractor = VocabularyExtractor()
        messages = [
            "Genial! 🙏🏽",
            "Gracias hermano 💪🏽 🔥",
            "Un abrazo 🙏🏽",
        ]

        result = extractor.extract_emojis(messages)

        assert "🙏🏽" in result
        assert any("💪" in e or "🔥" in e for e in result)

    def test_detect_forbidden_words(self):
        """Should detect words that should be avoided based on relationship."""
        from services.vocabulary_extractor import VocabularyExtractor

        extractor = VocabularyExtractor()

        # For INTIMA relationship, should avoid "hermano"
        forbidden = extractor.get_forbidden_words(RelationshipType.INTIMA.value)

        assert "hermano" in forbidden
        assert "bro" in forbidden

    def test_extract_muletillas(self):
        """Should extract filler words (muletillas) from messages."""
        from services.vocabulary_extractor import VocabularyExtractor

        extractor = VocabularyExtractor()
        messages = [
            "Bueno, pues nada, que te cuento",
            "Pues mira, la verdad es que...",
            "Bueno pues eso, que genial",
        ]

        result = extractor.extract_muletillas(messages)

        assert "bueno" in result or "pues" in result

    def test_empty_history_returns_empty(self):
        """Should return empty list for empty message history."""
        from services.vocabulary_extractor import VocabularyExtractor

        extractor = VocabularyExtractor()

        result = extractor.extract_common_words([])

        assert result == []

    def test_short_history_returns_partial(self):
        """Should return partial results for short history."""
        from services.vocabulary_extractor import VocabularyExtractor

        extractor = VocabularyExtractor()
        messages = ["Hola", "Hey"]

        result = extractor.extract_common_words(messages)

        assert isinstance(result, list)
        # May be empty or have few results for short history

    def test_long_history_extracts_patterns(self):
        """Should extract patterns from long conversation history."""
        from services.vocabulary_extractor import VocabularyExtractor

        extractor = VocabularyExtractor()
        messages = []
        for i in range(50):
            messages.append(f"Mensaje {i} con palabra crack repetida")

        result = extractor.extract_common_words(messages)

        assert "crack" in result  # Should find repeated word

    def test_extract_from_stefan_style_data(self):
        """Should extract Stefan's specific vocabulary patterns."""
        from services.vocabulary_extractor import VocabularyExtractor

        extractor = VocabularyExtractor()
        # Stefan's typical messages
        messages = [
            "Hermano que bueno verte por aqui! 🙏🏽",
            "Bro, como vas con todo?",
            "Increible! Me alegro mucho por ti hermano 💪🏽",
            "El proximo circulo va a estar brutal",
            "Te mando un abrazo grande hermano 🫂",
        ]

        common = extractor.extract_common_words(messages)
        emojis = extractor.extract_emojis(messages)

        # Should detect Stefan's vocabulary
        assert "hermano" in common or "bro" in common
        assert "🙏🏽" in emojis or "💪🏽" in emojis
