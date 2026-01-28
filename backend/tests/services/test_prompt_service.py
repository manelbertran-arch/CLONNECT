"""
Prompt Service tests - Written BEFORE implementation (TDD).
Run these tests FIRST - they should FAIL until service is created.
"""
import pytest


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
