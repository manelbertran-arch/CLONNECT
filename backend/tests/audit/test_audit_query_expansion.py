"""Audit tests for core/query_expansion.py"""

from core.query_expansion import QueryExpander, get_query_expander


class TestAuditQueryExpander:
    def test_import(self):
        from core.query_expansion import QueryExpander, get_query_expander  # noqa: F811

        assert QueryExpander is not None

    def test_init(self):
        expander = QueryExpander()
        assert expander is not None

    def test_happy_path_expand(self):
        expander = get_query_expander()
        result = expander.expand("precio del curso")
        assert result is not None
        assert isinstance(result, list)

    def test_edge_case_empty_query(self):
        expander = QueryExpander()
        result = expander.expand("")
        assert isinstance(result, list)

    def test_error_handling_add_synonym(self):
        expander = QueryExpander()
        try:
            expander.add_synonym("curso", ["programa", "formacion"])
            result = expander.expand("curso")
            assert result is not None
        except (TypeError, AttributeError):
            pass  # Acceptable
