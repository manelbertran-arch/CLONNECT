"""
Prompt Service tests - Written BEFORE implementation (TDD).
Run these tests FIRST - they should FAIL until service is created.
"""


class TestPromptServiceImport:
    """Test prompt service can be imported."""

    def test_prompt_service_module_exists(self):
        """Prompt service module should exist."""
        import services.prompt_service
        assert services.prompt_service is not None

    def test_prompt_builder_class_exists(self):
        """PromptBuilder class should exist."""
        from services.prompt_service import PromptBuilder
        assert PromptBuilder is not None

    def test_prompt_builder_has_build_system_prompt(self):
        """PromptBuilder should have build_system_prompt method."""
        from services.prompt_service import PromptBuilder
        assert hasattr(PromptBuilder, 'build_system_prompt')

    def test_prompt_builder_has_build_user_context(self):
        """PromptBuilder should have build_user_context method."""
        from services.prompt_service import PromptBuilder
        assert hasattr(PromptBuilder, 'build_user_context')


class TestPromptBuilderInstantiation:
    """Test PromptBuilder instantiation."""

    def test_prompt_builder_instantiation(self):
        """PromptBuilder should be instantiable."""
        from services.prompt_service import PromptBuilder
        builder = PromptBuilder()
        assert builder is not None

    def test_prompt_builder_with_personality(self):
        """PromptBuilder should accept personality config."""
        from services.prompt_service import PromptBuilder
        personality = {"tone": "friendly", "name": "TestBot"}
        builder = PromptBuilder(personality=personality)
        assert builder is not None


class TestBuildSystemPrompt:
    """Test system prompt building."""

    def test_build_system_prompt_returns_string(self):
        """build_system_prompt should return a string."""
        from services.prompt_service import PromptBuilder
        builder = PromptBuilder()
        prompt = builder.build_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_build_system_prompt_includes_role(self):
        """System prompt should include assistant role."""
        from services.prompt_service import PromptBuilder
        builder = PromptBuilder()
        prompt = builder.build_system_prompt()
        assert "asistente" in prompt.lower() or "assistant" in prompt.lower()

    def test_build_system_prompt_with_products(self):
        """System prompt should include product info when provided."""
        from services.prompt_service import PromptBuilder
        builder = PromptBuilder()
        products = [{"name": "Curso Pro", "price": 97}]
        prompt = builder.build_system_prompt(products=products)
        assert "Curso Pro" in prompt or "97" in prompt


class TestBuildUserContext:
    """Test user context building."""

    def test_build_user_context_returns_string(self):
        """build_user_context should return a string."""
        from services.prompt_service import PromptBuilder
        builder = PromptBuilder()
        context = builder.build_user_context(
            username="testuser",
            stage="NUEVO"
        )
        assert isinstance(context, str)

    def test_build_user_context_includes_username(self):
        """User context should include username."""
        from services.prompt_service import PromptBuilder
        builder = PromptBuilder()
        context = builder.build_user_context(
            username="johndoe",
            stage="INTERESADO"
        )
        assert "johndoe" in context

    def test_build_user_context_includes_history(self):
        """User context should include conversation history."""
        from services.prompt_service import PromptBuilder
        builder = PromptBuilder()
        history = [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "Hola! Como puedo ayudarte?"}
        ]
        context = builder.build_user_context(
            username="testuser",
            stage="NUEVO",
            history=history
        )
        assert "Hola" in context


class TestToneEmojiRule:
    """Test that _tone_config emoji_rule is injected into the system prompt."""

    def test_professional_tone_injects_no_emoji_rule(self):
        """Professional tone → 'NINGUNO' (no emojis) must appear in system prompt."""
        from services.prompt_service import PromptBuilder
        builder = PromptBuilder(personality={"tone": "professional", "name": "Bot"})
        prompt = builder.build_system_prompt()
        assert "NINGUNO" in prompt, "Professional tone emoji rule not injected"

    def test_casual_tone_injects_frecuente_rule(self):
        """Casual tone → 'frecuente' must appear in system prompt."""
        from services.prompt_service import PromptBuilder
        builder = PromptBuilder(personality={"tone": "casual", "name": "Bot"})
        prompt = builder.build_system_prompt()
        assert "frecuente" in prompt.lower(), "Casual tone emoji rule not injected"

    def test_friendly_tone_injects_moderado_rule(self):
        """Friendly tone → 'moderado' must appear in system prompt."""
        from services.prompt_service import PromptBuilder
        builder = PromptBuilder(personality={"tone": "friendly", "name": "Bot"})
        prompt = builder.build_system_prompt()
        assert "moderado" in prompt.lower(), "Friendly tone emoji rule not injected"

    def test_default_tone_injects_emoji_rule(self):
        """No tone specified → defaults to friendly → 'moderado' must appear."""
        from services.prompt_service import PromptBuilder
        builder = PromptBuilder(personality={"name": "Bot"})
        prompt = builder.build_system_prompt()
        assert "moderado" in prompt.lower(), "Default (friendly) tone emoji rule not injected"

    def test_unknown_tone_falls_back_to_friendly(self):
        """Unknown tone falls back to friendly → 'moderado' must appear."""
        from services.prompt_service import PromptBuilder
        builder = PromptBuilder(personality={"tone": "aggressive", "name": "Bot"})
        prompt = builder.build_system_prompt()
        assert "moderado" in prompt.lower(), "Fallback tone emoji rule not injected"

    def test_emoji_rule_appears_in_importante_section(self):
        """Emoji rule must be inside the IMPORTANTE block."""
        from services.prompt_service import PromptBuilder
        builder = PromptBuilder(personality={"tone": "professional", "name": "Bot"})
        prompt = builder.build_system_prompt()
        importante_pos = prompt.find("IMPORTANTE:")
        ninguno_pos = prompt.find("NINGUNO")
        assert importante_pos != -1, "IMPORTANTE section missing"
        assert ninguno_pos > importante_pos, "Emoji rule must appear after IMPORTANTE:"

    def test_skip_safety_omits_emoji_rule(self):
        """When skip_safety=True, no IMPORTANTE block → emoji rule also absent."""
        from services.prompt_service import PromptBuilder
        builder = PromptBuilder(personality={"tone": "professional", "name": "Bot"})
        prompt = builder.build_system_prompt(skip_safety=True)
        assert "NINGUNO" not in prompt, "Emoji rule must not appear when safety is skipped"
