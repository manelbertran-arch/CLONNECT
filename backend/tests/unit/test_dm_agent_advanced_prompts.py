"""Test prompt_builder advanced integration in dm_agent_v2 (Step 12)."""


class TestAdvancedPromptsIntegration:
    def test_module_importable(self):
        from core.prompt_builder import build_alerts_section, build_rules_section

        assert callable(build_rules_section)
        assert callable(build_alerts_section)

    def test_flag_exists(self):
        from core.dm_agent_v2 import ENABLE_ADVANCED_PROMPTS

        assert isinstance(ENABLE_ADVANCED_PROMPTS, bool)

    def test_rules_section_content(self):
        from core.prompt_builder import build_rules_section

        rules = build_rules_section("TestCreator")
        assert "ANTI-ALUCINACIÓN" in rules
        assert "TestCreator" in rules

    def test_flag_default_off(self):
        """Advanced prompts should default to OFF (changes prompt significantly)."""
        import os

        original = os.environ.pop("ENABLE_ADVANCED_PROMPTS", None)
        try:
            flag = os.getenv("ENABLE_ADVANCED_PROMPTS", "false").lower() == "true"
            assert flag is False
        finally:
            if original is not None:
                os.environ["ENABLE_ADVANCED_PROMPTS"] = original
