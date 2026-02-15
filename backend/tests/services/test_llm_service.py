"""
LLM Service tests - Written BEFORE implementation (TDD).
Run these tests FIRST - they should FAIL until service is created.
"""


class TestLLMServiceImport:
    """Test LLM service can be imported."""

    def test_llm_service_module_exists(self):
        """LLM service module should exist."""
        import services.llm_service
        assert services.llm_service is not None

    def test_llm_service_class_exists(self):
        """LLMService class should exist."""
        from services.llm_service import LLMService
        assert LLMService is not None

    def test_llm_provider_enum_exists(self):
        """LLMProvider enum should exist."""
        from services.llm_service import LLMProvider
        assert LLMProvider is not None

    def test_llm_response_class_exists(self):
        """LLMResponse class should exist."""
        from services.llm_service import LLMResponse
        assert LLMResponse is not None

    def test_llm_service_has_generate(self):
        """LLMService should have generate method."""
        from services.llm_service import LLMService
        assert hasattr(LLMService, 'generate')

    def test_llm_service_has_chat(self):
        """LLMService should have chat method."""
        from services.llm_service import LLMService
        assert hasattr(LLMService, 'chat')


class TestLLMServiceInstantiation:
    """Test LLMService instantiation."""

    def test_llm_service_instantiation_default(self):
        """LLMService should be instantiable with defaults."""
        from services.llm_service import LLMService
        service = LLMService()
        assert service is not None

    def test_llm_service_with_provider(self):
        """LLMService should accept provider config."""
        from services.llm_service import LLMService, LLMProvider
        service = LLMService(provider=LLMProvider.GROQ)
        assert service.provider == LLMProvider.GROQ

    def test_llm_service_with_model(self):
        """LLMService should accept model config."""
        from services.llm_service import LLMService
        service = LLMService(model="llama-3.3-70b-versatile")
        assert service.model == "llama-3.3-70b-versatile"

    def test_llm_service_with_temperature(self):
        """LLMService should accept temperature config."""
        from services.llm_service import LLMService
        service = LLMService(temperature=0.5)
        assert service.temperature == 0.5

    def test_llm_service_with_max_tokens(self):
        """LLMService should accept max_tokens config."""
        from services.llm_service import LLMService
        service = LLMService(max_tokens=2000)
        assert service.max_tokens == 2000


class TestLLMProvider:
    """Test LLMProvider enum."""

    def test_groq_provider(self):
        """Should have GROQ provider."""
        from services.llm_service import LLMProvider
        assert LLMProvider.GROQ.value == "groq"

    def test_openai_provider(self):
        """Should have OPENAI provider."""
        from services.llm_service import LLMProvider
        assert LLMProvider.OPENAI.value == "openai"

    def test_anthropic_provider(self):
        """Should have ANTHROPIC provider."""
        from services.llm_service import LLMProvider
        assert LLMProvider.ANTHROPIC.value == "anthropic"


class TestLLMResponse:
    """Test LLMResponse dataclass."""

    def test_llm_response_creation(self):
        """Should create LLMResponse object."""
        from services.llm_service import LLMResponse
        response = LLMResponse(
            content="Hello!",
            model="test-model",
            tokens_used=10
        )
        assert response.content == "Hello!"
        assert response.model == "test-model"
        assert response.tokens_used == 10

    def test_llm_response_with_metadata(self):
        """Should store metadata."""
        from services.llm_service import LLMResponse
        response = LLMResponse(
            content="Test",
            model="test-model",
            tokens_used=5,
            metadata={"finish_reason": "stop"}
        )
        assert response.metadata["finish_reason"] == "stop"

    def test_llm_response_is_empty(self):
        """Should detect empty responses."""
        from services.llm_service import LLMResponse
        empty = LLMResponse(content="", model="test", tokens_used=0)
        not_empty = LLMResponse(content="Hello", model="test", tokens_used=5)
        assert empty.is_empty is True
        assert not_empty.is_empty is False


class TestLLMServiceConfig:
    """Test LLM service configuration."""

    def test_get_available_models(self):
        """Should list available models."""
        from services.llm_service import LLMService
        service = LLMService()
        models = service.get_available_models()
        assert isinstance(models, list)
        assert len(models) > 0

    def test_get_stats(self):
        """Should return service statistics."""
        from services.llm_service import LLMService
        service = LLMService()
        stats = service.get_stats()
        assert isinstance(stats, dict)
        assert "provider" in stats
        assert "model" in stats


class TestLLMServiceGenerate:
    """Test LLM generation methods."""

    def test_generate_builds_messages(self):
        """generate should build proper messages."""
        from services.llm_service import LLMService
        service = LLMService()
        messages = service._build_messages(
            prompt="Hello",
            system_prompt="You are helpful."
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_generate_without_system_prompt(self):
        """generate should work without system prompt."""
        from services.llm_service import LLMService
        service = LLMService()
        messages = service._build_messages(
            prompt="Hello",
            system_prompt=None
        )
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_chat_builds_from_history(self):
        """chat should accept message history."""
        from services.llm_service import LLMService
        service = LLMService()
        history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]
        messages = service._build_chat_messages(
            history=history,
            new_message="How are you?",
            system_prompt="Be friendly."
        )
        assert len(messages) == 4  # system + 2 history + new
        assert messages[0]["role"] == "system"
        assert messages[-1]["content"] == "How are you?"
