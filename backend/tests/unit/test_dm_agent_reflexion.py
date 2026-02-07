"""Test reflexion_engine integration in dm_agent_v2 (Step 7)."""


class TestReflexionEngineIntegration:
    def test_module_importable(self):
        from core.reflexion_engine import get_reflexion_engine

        engine = get_reflexion_engine()
        assert engine is not None

    def test_flag_exists(self):
        from core.dm_agent_v2 import ENABLE_REFLEXION

        assert isinstance(ENABLE_REFLEXION, bool)

    def test_good_response_passes(self):
        from core.reflexion_engine import get_reflexion_engine

        engine = get_reflexion_engine()
        result = engine.analyze_response(
            response="El curso cuesta 97€ y puedes apuntarte aquí.",
            user_message="¿Cuánto cuesta?",
        )
        assert not result.needs_revision or result.severity == "low"

    def test_short_response_flagged(self):
        from core.reflexion_engine import get_reflexion_engine

        engine = get_reflexion_engine()
        result = engine.analyze_response(
            response="Ok",
            user_message="¿Qué incluye el curso?",
        )
        assert result.needs_revision

    def test_repetition_detected(self):
        from core.reflexion_engine import get_reflexion_engine

        engine = get_reflexion_engine()
        prev = ["El curso incluye 10 módulos de formación completa con soporte"]
        result = engine.analyze_response(
            response="El curso incluye 10 módulos de formación completa con soporte personalizado",
            user_message="¿Qué incluye?",
            previous_bot_responses=prev,
        )
        assert result.needs_revision
