"""
DM Agent V2 tests - Written BEFORE implementation (TDD).
Tests the new slim orchestrator using modular services.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch


class TestDMAgentV2Import:
    """Test agent can be imported."""

    def test_agent_module_exists(self):
        """Agent module should exist."""
        import core.dm_agent_v2
        assert core.dm_agent_v2 is not None

    def test_agent_class_exists(self):
        """DMResponderAgentV2 class should exist."""
        from core.dm_agent_v2 import DMResponderAgentV2
        assert DMResponderAgentV2 is not None

    def test_dm_response_class_exists(self):
        """DMResponse dataclass should exist."""
        from core.dm_agent_v2 import DMResponse
        assert DMResponse is not None

    def test_agent_config_class_exists(self):
        """AgentConfig dataclass should exist."""
        from core.dm_agent_v2 import AgentConfig
        assert AgentConfig is not None


class TestDMAgentV2Instantiation:
    """Test agent instantiation."""

    def test_agent_instantiation(self):
        """Agent should be instantiable."""
        from core.dm_agent_v2 import DMResponderAgentV2
        agent = DMResponderAgentV2(creator_id="test_creator")
        assert agent is not None

    def test_agent_has_creator_id(self):
        """Agent should store creator_id."""
        from core.dm_agent_v2 import DMResponderAgentV2
        agent = DMResponderAgentV2(creator_id="test_creator")
        assert agent.creator_id == "test_creator"

    def test_agent_has_services(self):
        """Agent should initialize all services."""
        from core.dm_agent_v2 import DMResponderAgentV2
        agent = DMResponderAgentV2(creator_id="test_creator")
        assert hasattr(agent, 'intent_classifier')
        assert hasattr(agent, 'prompt_builder')
        assert hasattr(agent, 'memory_store')
        assert hasattr(agent, 'rag_service')
        assert hasattr(agent, 'llm_service')
        assert hasattr(agent, 'lead_service')
        assert hasattr(agent, 'instagram_service')

    def test_agent_with_custom_config(self):
        """Agent should accept custom config."""
        from core.dm_agent_v2 import DMResponderAgentV2, AgentConfig
        from services import LLMProvider

        config = AgentConfig(
            llm_provider=LLMProvider.GROQ,
            temperature=0.5,
            max_tokens=512
        )
        agent = DMResponderAgentV2(creator_id="test", config=config)
        assert agent.config.temperature == 0.5
        assert agent.config.max_tokens == 512


class TestDMAgentV2ProcessDM:
    """Test main process_dm method."""

    def test_process_dm_method_exists(self):
        """Should have process_dm method."""
        from core.dm_agent_v2 import DMResponderAgentV2
        agent = DMResponderAgentV2(creator_id="test")
        assert hasattr(agent, 'process_dm')
        assert callable(agent.process_dm)

    @pytest.mark.asyncio
    async def test_process_dm_returns_response(self):
        """process_dm should return a DMResponse."""
        from core.dm_agent_v2 import DMResponderAgentV2, DMResponse
        from services import LLMResponse

        agent = DMResponderAgentV2(creator_id="test")

        # Mock LLM to avoid API calls
        mock_response = LLMResponse(
            content="Hola! En que puedo ayudarte?",
            model="test-model",
            tokens_used=10,
        )
        agent.llm_service.generate = AsyncMock(return_value=mock_response)

        response = await agent.process_dm(
            message="Hola",
            sender_id="user_123",
        )

        assert response is not None
        assert isinstance(response, DMResponse)
        assert response.content is not None

    @pytest.mark.asyncio
    async def test_process_dm_classifies_intent(self):
        """process_dm should classify message intent."""
        from core.dm_agent_v2 import DMResponderAgentV2
        from services import LLMResponse

        agent = DMResponderAgentV2(creator_id="test")

        mock_response = LLMResponse(
            content="El curso cuesta 97 euros.",
            model="test-model",
            tokens_used=15,
        )
        agent.llm_service.generate = AsyncMock(return_value=mock_response)

        response = await agent.process_dm(
            message="Cuanto cuesta el curso?",
            sender_id="user_123",
        )

        # Should detect as PRODUCT_QUESTION
        assert response.intent in ["product_question", "PRODUCT_QUESTION", "question_product"]

    @pytest.mark.asyncio
    async def test_process_dm_handles_error(self):
        """process_dm should handle errors gracefully."""
        from core.dm_agent_v2 import DMResponderAgentV2

        agent = DMResponderAgentV2(creator_id="test")

        # Make LLM raise an exception
        agent.llm_service.generate = AsyncMock(side_effect=Exception("API Error"))

        response = await agent.process_dm(
            message="Hola",
            sender_id="user_123",
        )

        # Should return error response
        assert response is not None
        assert "error" in response.metadata or response.intent == "ERROR"


class TestDMAgentV2Knowledge:
    """Test knowledge/RAG management."""

    def test_add_knowledge_method_exists(self):
        """Should have add_knowledge method."""
        from core.dm_agent_v2 import DMResponderAgentV2
        agent = DMResponderAgentV2(creator_id="test")
        assert hasattr(agent, 'add_knowledge')

    def test_add_knowledge_returns_id(self):
        """add_knowledge should return document ID."""
        from core.dm_agent_v2 import DMResponderAgentV2
        agent = DMResponderAgentV2(creator_id="test")

        doc_id = agent.add_knowledge(
            content="Nuestro curso cuesta 97 euros",
            metadata={"type": "pricing"}
        )

        assert doc_id is not None
        assert isinstance(doc_id, str)

    def test_retrieve_knowledge(self):
        """Should retrieve relevant knowledge."""
        from core.dm_agent_v2 import DMResponderAgentV2
        agent = DMResponderAgentV2(creator_id="test")

        agent.add_knowledge("El curso de Python cuesta 97 euros", {"type": "pricing"})
        results = agent.rag_service.retrieve("precio curso", top_k=3)

        assert isinstance(results, list)


class TestDMAgentV2Stats:
    """Test statistics and monitoring."""

    def test_get_stats_method_exists(self):
        """Should have get_stats method."""
        from core.dm_agent_v2 import DMResponderAgentV2
        agent = DMResponderAgentV2(creator_id="test")
        assert hasattr(agent, 'get_stats')

    def test_get_stats_returns_dict(self):
        """get_stats should return a dictionary."""
        from core.dm_agent_v2 import DMResponderAgentV2
        agent = DMResponderAgentV2(creator_id="test")

        stats = agent.get_stats()

        assert isinstance(stats, dict)
        assert "creator_id" in stats
        assert "llm" in stats
        assert "rag" in stats

    def test_health_check_method_exists(self):
        """Should have health_check method."""
        from core.dm_agent_v2 import DMResponderAgentV2
        agent = DMResponderAgentV2(creator_id="test")
        assert hasattr(agent, 'health_check')

    def test_health_check_returns_all_healthy(self):
        """health_check should return all services as healthy."""
        from core.dm_agent_v2 import DMResponderAgentV2
        agent = DMResponderAgentV2(creator_id="test")

        health = agent.health_check()

        assert isinstance(health, dict)
        assert all(v is True for v in health.values())


class TestDMResponse:
    """Test DMResponse dataclass."""

    def test_dm_response_creation(self):
        """DMResponse should be creatable."""
        from core.dm_agent_v2 import DMResponse

        response = DMResponse(
            content="Test response",
            intent="greeting",
            lead_stage="NUEVO",
            confidence=0.9,
        )

        assert response.content == "Test response"
        assert response.intent == "greeting"
        assert response.lead_stage == "NUEVO"
        assert response.confidence == 0.9

    def test_dm_response_to_dict(self):
        """DMResponse should convert to dictionary."""
        from core.dm_agent_v2 import DMResponse

        response = DMResponse(
            content="Test",
            intent="greeting",
            lead_stage="NUEVO",
            confidence=0.9,
        )

        result = response.to_dict()

        assert isinstance(result, dict)
        assert result["content"] == "Test"
        assert result["intent"] == "greeting"


class TestAgentConfig:
    """Test AgentConfig dataclass."""

    def test_agent_config_defaults(self):
        """AgentConfig should have sensible defaults."""
        from core.dm_agent_v2 import AgentConfig
        from services import LLMProvider

        config = AgentConfig()

        assert config.llm_provider == LLMProvider.GROQ
        assert config.temperature == 0.7
        assert config.max_tokens == 1024

    def test_agent_config_custom_values(self):
        """AgentConfig should accept custom values."""
        from core.dm_agent_v2 import AgentConfig
        from services import LLMProvider

        config = AgentConfig(
            llm_provider=LLMProvider.OPENAI,
            temperature=0.3,
            max_tokens=2048,
            rag_top_k=5
        )

        assert config.llm_provider == LLMProvider.OPENAI
        assert config.temperature == 0.3
        assert config.max_tokens == 2048
        assert config.rag_top_k == 5
