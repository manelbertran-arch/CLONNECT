"""Test query_expansion integration in dm_agent_v2 (Step 6)."""


class TestQueryExpansionIntegration:
    def test_module_importable(self):
        from core.query_expansion import get_query_expander

        expander = get_query_expander()
        assert expander is not None

    def test_flag_exists(self):
        from core.dm_agent_v2 import ENABLE_QUERY_EXPANSION

        assert isinstance(ENABLE_QUERY_EXPANSION, bool)

    def test_expand_precio(self):
        from core.query_expansion import get_query_expander

        expander = get_query_expander()
        results = expander.expand("precio del curso")
        assert len(results) >= 2
        assert "precio del curso" in results

    def test_expand_empty_query(self):
        from core.query_expansion import get_query_expander

        expander = get_query_expander()
        results = expander.expand("")
        assert results == [""]

    def test_expand_tokens(self):
        from core.query_expansion import get_query_expander

        expander = get_query_expander()
        tokens = expander.expand_tokens("mentoría")
        assert "mentoría" in tokens or "mentoring" in tokens
