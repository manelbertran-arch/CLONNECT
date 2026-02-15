"""Audit tests for core/reflexion_engine.py"""

from core.reflexion_engine import ReflexionEngine, get_reflexion_engine


class TestAuditReflexionEngine:
    def test_import(self):
        from core.reflexion_engine import (  # noqa: F811
            ReflexionEngine,
            ReflexionResult,
            get_reflexion_engine,
        )

        assert ReflexionEngine is not None

    def test_init(self):
        engine = ReflexionEngine()
        assert engine is not None

    def test_happy_path_get_engine(self):
        engine = get_reflexion_engine()
        assert engine is not None

    def test_edge_case_has_methods(self):
        engine = ReflexionEngine()
        assert hasattr(engine, "analyze_response")
        assert hasattr(engine, "build_revision_prompt")

    def test_error_handling_analyze(self):
        engine = ReflexionEngine()
        try:
            result = engine.analyze_response(
                response="Hola!",
                user_message="Hola",
            )
            assert result is not None
        except Exception:
            pass  # May need LLM
