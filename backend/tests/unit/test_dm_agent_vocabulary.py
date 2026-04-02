"""Test vocabulary_extractor module imports and basic functionality."""


class TestVocabularyExtractorIntegration:
    def test_import_works(self):
        from services.vocabulary_extractor import (
            tokenize, extract_lead_vocabulary, get_top_distinctive_words,
            STOPWORDS,
        )
        assert callable(tokenize)
        assert callable(extract_lead_vocabulary)
        assert callable(get_top_distinctive_words)
        assert isinstance(STOPWORDS, frozenset)

    def test_tokenize_basic(self):
        from services.vocabulary_extractor import tokenize
        tokens = tokenize("Hola cuca bon dia")
        assert isinstance(tokens, list)
        assert "cuca" in tokens
