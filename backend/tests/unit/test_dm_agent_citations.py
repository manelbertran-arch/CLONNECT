"""Test citation_service integration in dm_agent_v2 (Step 17)."""


class TestCitationIntegration:
    def test_flag_exists(self):
        from core.dm_agent_v2 import ENABLE_CITATIONS

        assert isinstance(ENABLE_CITATIONS, bool)

    def test_import_works(self):
        from core.citation_service import get_citation_prompt_section

        assert callable(get_citation_prompt_section)

    def test_returns_string(self):
        """Citation service should return a string (empty if no index)."""
        from core.citation_service import get_citation_prompt_section

        result = get_citation_prompt_section("nonexistent_creator", "test query")
        assert isinstance(result, str)
