"""Test vocabulary_extractor flag in dm_agent_v2 (Step 20)."""


class TestVocabularyExtractorIntegration:
    def test_flag_exists(self):
        from core.dm_agent_v2 import ENABLE_VOCABULARY_EXTRACTION

        assert isinstance(ENABLE_VOCABULARY_EXTRACTION, bool)

    def test_import_works(self):
        from services.vocabulary_extractor import VocabularyExtractor

        assert VocabularyExtractor is not None

    def test_extractor_instantiates(self):
        from services.vocabulary_extractor import VocabularyExtractor

        extractor = VocabularyExtractor()
        assert extractor is not None
