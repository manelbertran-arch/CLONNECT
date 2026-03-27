"""Integration tests for the BotOrchestrator."""

import pytest

from services.bot_orchestrator import BotOrchestrator, BotResponse


@pytest.fixture
def orchestrator():
    """Create a BotOrchestrator for testing."""
    return BotOrchestrator()


class TestBasicFlow:
    """Tests for basic message flow."""

    @pytest.mark.asyncio
    async def test_greeting_uses_pool(self, orchestrator):
        """Greetings should use pool, not LLM."""
        response = await orchestrator.process_message(
            message="Hola!",
            lead_id="test_lead",
            creator_id="test_creator",
        )

        assert response.used_pool
        assert len(response.messages) == 1
        assert response.delays[0] >= 2.0

    @pytest.mark.asyncio
    async def test_emoji_uses_pool(self, orchestrator):
        """Emojis should use pool."""
        response = await orchestrator.process_message(
            message="💪",
            lead_id="test_lead",
            creator_id="test_creator",
        )

        assert response.used_pool
        assert len(response.messages[0]) <= 5

    @pytest.mark.asyncio
    async def test_thanks_uses_pool(self, orchestrator):
        """Thanks should use pool."""
        response = await orchestrator.process_message(
            message="Gracias!",
            lead_id="test_lead",
            creator_id="test_creator",
        )

        assert response.used_pool
        assert response.has_response

    @pytest.mark.asyncio
    async def test_complex_needs_llm(self, orchestrator):
        """Complex questions need LLM."""

        async def mock_llm(**kwargs):
            return "El coaching individual cuesta 150€ la sesión 😊"

        response = await orchestrator.process_message(
            message="Cuánto cuesta el coaching?",
            lead_id="test_lead",
            creator_id="test_creator",
            generate_with_llm=mock_llm,
        )

        assert not response.used_pool
        assert "150" in response.single_message


class TestMultiMessage:
    """Tests for multi-message splitting."""

    @pytest.mark.asyncio
    async def test_long_response_splits(self, orchestrator):
        """Long responses should be split."""

        async def mock_llm(**kwargs):
            return (
                "El Círculo de Hombres es una comunidad increíble donde nos reunimos. "
                "Nos juntamos cada semana para trabajar temas de desarrollo personal. "
                "Incluye sesiones grupales, recursos exclusivos y eventos especiales. "
                "El precio es 97€ al mes y puedes cancelar cuando quieras."
            )

        response = await orchestrator.process_message(
            message="Cuéntame todo sobre el Círculo",
            lead_id="test_lead",
            creator_id="test_creator",
            generate_with_llm=mock_llm,
        )

        assert response.is_multi_message
        assert len(response.messages) >= 2
        assert len(response.delays) == len(response.messages)

    @pytest.mark.asyncio
    async def test_short_response_not_split(self, orchestrator):
        """Short responses should not be split."""

        async def mock_llm(**kwargs):
            return "El precio es 150€ 😊"

        response = await orchestrator.process_message(
            message="Precio?",
            lead_id="test_lead",
            creator_id="test_creator",
            generate_with_llm=mock_llm,
        )

        assert not response.is_multi_message
        assert len(response.messages) == 1


class TestTiming:
    """Tests for timing calculations."""

    @pytest.mark.asyncio
    async def test_has_minimum_delay(self, orchestrator):
        """Should have minimum delay."""
        response = await orchestrator.process_message(
            message="Hola!",
            lead_id="test_lead",
            creator_id="test_creator",
        )

        assert response.delays[0] >= 2.0

    @pytest.mark.asyncio
    async def test_multi_message_has_delays(self, orchestrator):
        """Multi-message should have delay for each part."""

        async def mock_llm(**kwargs):
            return (
                "Primera parte del mensaje con información importante. "
                "Segunda parte con más detalles relevantes para ti. "
                "Tercera parte final con el cierre del mensaje."
            )

        response = await orchestrator.process_message(
            message="Cuéntame todo",
            lead_id="test_lead",
            creator_id="test_creator",
            generate_with_llm=mock_llm,
        )

        if response.is_multi_message:
            assert len(response.delays) == len(response.messages)
            assert all(d > 0 for d in response.delays)


class TestMemory:
    """Tests for memory functionality."""

    @pytest.mark.asyncio
    async def test_memory_context_built(self, orchestrator):
        """Memory context should be passed to LLM."""
        received_context = {}

        async def mock_llm(**kwargs):
            received_context.update(kwargs)
            return "Respuesta de prueba"

        await orchestrator.process_message(
            message="Cuánto cuesta?",
            lead_id="memory_test_lead",
            creator_id="test_creator",
            generate_with_llm=mock_llm,
        )

        assert "memory_context" in received_context
        assert "references_past" in received_context


class TestBotResponseProperties:
    """Tests for BotResponse dataclass."""

    def test_single_message_property(self):
        """single_message should return first message."""
        response = BotResponse(messages=["First", "Second"])
        assert response.single_message == "First"

    def test_single_message_empty(self):
        """single_message should return empty string if no messages."""
        response = BotResponse(messages=[])
        assert response.single_message == ""

    def test_is_multi_message(self):
        """is_multi_message should detect multiple messages."""
        single = BotResponse(messages=["One"])
        multi = BotResponse(messages=["One", "Two"])

        assert not single.is_multi_message
        assert multi.is_multi_message

    def test_has_response(self):
        """has_response should detect if there are messages."""
        with_messages = BotResponse(messages=["Hello"])
        without_messages = BotResponse(messages=[])

        assert with_messages.has_response
        assert not without_messages.has_response


class TestFallback:
    """Tests for fallback behavior."""

    @pytest.mark.asyncio
    async def test_no_llm_fallback(self, orchestrator):
        """Should have fallback if no LLM provided."""
        response = await orchestrator.process_message(
            message="Pregunta compleja sin LLM?",
            lead_id="test_lead",
            creator_id="test_creator",
            generate_with_llm=None,
        )

        # Should have some response even without LLM
        assert response.has_response

    @pytest.mark.asyncio
    async def test_llm_error_fallback(self, orchestrator):
        """Should handle LLM errors gracefully."""

        async def failing_llm(**kwargs):
            raise Exception("LLM Error")

        response = await orchestrator.process_message(
            message="Pregunta que causa error?",
            lead_id="test_lead",
            creator_id="test_creator",
            generate_with_llm=failing_llm,
        )

        # Should still return something
        assert response.has_response


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
