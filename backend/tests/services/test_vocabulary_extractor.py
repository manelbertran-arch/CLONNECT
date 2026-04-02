"""Tests for vocabulary_extractor service (data-mined, TF-IDF).

Updated to test the new module-level functions after rewrite.
"""


class TestVocabularyExtractorService:
    """Test suite for vocabulary_extractor module functions."""

    def test_extract_common_words(self):
        """Should extract commonly used words from messages."""
        from services.vocabulary_extractor import extract_lead_vocabulary

        messages = [
            "Hola cuca, que tal?",
            "Cuca bon dia!",
            "Adeu cuca, un petó!",
        ]

        result = extract_lead_vocabulary(messages, min_freq=2)

        assert "cuca" in result
        assert result["cuca"] >= 2

    def test_empty_history_returns_empty(self):
        """Should return empty dict for empty message history."""
        from services.vocabulary_extractor import extract_lead_vocabulary

        result = extract_lead_vocabulary([])
        assert result == {}

    def test_short_history_returns_partial(self):
        """Should return partial results for short history."""
        from services.vocabulary_extractor import extract_lead_vocabulary

        messages = ["Hola", "Hey"]
        result = extract_lead_vocabulary(messages, min_freq=2)
        assert isinstance(result, dict)

    def test_long_history_extracts_patterns(self):
        """Should extract patterns from long conversation history."""
        from services.vocabulary_extractor import extract_lead_vocabulary

        messages = [f"Mensaje con palabra crack repetida" for _ in range(50)]
        result = extract_lead_vocabulary(messages, min_freq=2)
        assert "crack" in result

    def test_stopwords_filtered(self):
        """Stopwords should be excluded from results."""
        from services.vocabulary_extractor import extract_lead_vocabulary

        messages = ["que bueno que estás bien"] * 5
        result = extract_lead_vocabulary(messages, min_freq=2)
        for sw in ["que", "bueno", "bien"]:
            assert sw not in result

    def test_word_boundary_no_substring_match(self):
        """Should not match 'compa' inside 'acompanyar'."""
        from services.vocabulary_extractor import tokenize

        tokens = tokenize("Voy a acompanyarte al retiro")
        assert "compa" not in tokens

    def test_get_top_distinctive_words(self):
        """Should return top distinctive words."""
        from services.vocabulary_extractor import get_top_distinctive_words

        messages = ["Hola flower"] * 5 + ["Bon dia reina"] * 3
        result = get_top_distinctive_words(messages, top_n=3)
        assert len(result) <= 3
        assert isinstance(result, list)

    def test_tokenize_media_placeholder(self):
        """Media placeholders should produce no tokens."""
        from services.vocabulary_extractor import tokenize

        assert tokenize("[🎤 Audio]: algo") == []
        assert tokenize("[media/attachment]") == []
