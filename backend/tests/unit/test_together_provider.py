"""Tests for Together AI provider."""

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.providers.together_provider import (
    call_together,
    _record_failure,
    _record_success,
    _circuit_is_open,
    TOGETHER_BASE_URL,
)


class TestCallTogether:
    """Test call_together function."""

    def setup_method(self):
        """Reset circuit breaker state before each test."""
        import core.providers.together_provider as tp
        tp._together_consecutive_failures = 0
        tp._together_circuit_open_until = 0.0

    @pytest.mark.asyncio
    async def test_returns_none_without_api_key(self):
        """No TOGETHER_API_KEY → returns None without calling API."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TOGETHER_API_KEY", None)
            result = await call_together(
                [{"role": "user", "content": "Hola"}],
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_successful_call(self):
        """Mocked successful Together API call."""
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 5

        mock_choice = MagicMock()
        mock_choice.message.content = "Hola! 🩷"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_create = AsyncMock(return_value=mock_response)

        with patch.dict(os.environ, {"TOGETHER_API_KEY": "test-key"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance

                result = await call_together(
                    [{"role": "user", "content": "Hola"}],
                    max_tokens=60,
                    temperature=0.8,
                )

                assert result is not None
                assert result["content"] == "Hola! 🩷"
                assert result["provider"] == "together"
                assert result["tokens_in"] == 10
                assert result["tokens_out"] == 5
                assert "latency_ms" in result

                MockClient.assert_called_once_with(
                    api_key="test-key",
                    base_url=TOGETHER_BASE_URL,
                )

    @pytest.mark.asyncio
    async def test_empty_content_returns_none(self):
        """Empty content from API → returns None and records failure."""
        mock_choice = MagicMock()
        mock_choice.message.content = ""
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=0)

        with patch.dict(os.environ, {"TOGETHER_API_KEY": "test-key"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = AsyncMock(return_value=mock_response)
                MockClient.return_value = instance

                result = await call_together(
                    [{"role": "user", "content": "Hola"}],
                )
                assert result is None

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self):
        """Timeout → returns None and records failure."""
        async def slow_call(*a, **kw):
            await asyncio.sleep(100)

        with patch.dict(os.environ, {"TOGETHER_API_KEY": "test-key", "TOGETHER_TIMEOUT": "0.01"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = slow_call
                MockClient.return_value = instance

                result = await call_together(
                    [{"role": "user", "content": "Hola"}],
                )
                assert result is None

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self):
        """API error → returns None and records failure."""
        with patch.dict(os.environ, {"TOGETHER_API_KEY": "test-key"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = AsyncMock(
                    side_effect=Exception("rate limited")
                )
                MockClient.return_value = instance

                result = await call_together(
                    [{"role": "user", "content": "Hola"}],
                )
                assert result is None

    @pytest.mark.asyncio
    async def test_model_override(self):
        """Custom model is passed to API."""
        mock_choice = MagicMock()
        mock_choice.message.content = "Response"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=3)

        mock_create = AsyncMock(return_value=mock_response)

        with patch.dict(os.environ, {"TOGETHER_API_KEY": "test-key"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance

                result = await call_together(
                    [{"role": "user", "content": "Hi"}],
                    model="Qwen/Qwen3-8B",
                )
                assert result is not None
                assert result["model"] == "Qwen/Qwen3-8B"
                mock_create.assert_called_once()
                call_kwargs = mock_create.call_args[1]
                assert call_kwargs["model"] == "Qwen/Qwen3-8B"


class TestCircuitBreaker:
    """Test circuit breaker behavior."""

    def setup_method(self):
        """Reset circuit breaker state before each test."""
        import core.providers.together_provider as tp
        tp._together_consecutive_failures = 0
        tp._together_circuit_open_until = 0.0

    def test_circuit_starts_closed(self):
        assert not _circuit_is_open()

    def test_circuit_opens_after_threshold(self):
        import core.providers.together_provider as tp
        for _ in range(tp._TG_CB_THRESHOLD):
            _record_failure()
        assert _circuit_is_open()

    def test_success_resets_circuit(self):
        import core.providers.together_provider as tp
        for _ in range(tp._TG_CB_THRESHOLD):
            _record_failure()
        assert _circuit_is_open()
        _record_success()
        assert not _circuit_is_open()

    @pytest.mark.asyncio
    async def test_open_circuit_skips_call(self):
        """When circuit is open, call_together returns None without API call."""
        import core.providers.together_provider as tp
        for _ in range(tp._TG_CB_THRESHOLD):
            _record_failure()

        with patch.dict(os.environ, {"TOGETHER_API_KEY": "test-key"}):
            result = await call_together(
                [{"role": "user", "content": "Hola"}],
            )
            assert result is None


class TestLiveIntegration:
    """Live integration test — only runs when TOGETHER_API_KEY is set."""

    @pytest.mark.skipif(
        not os.getenv("TOGETHER_API_KEY"),
        reason="TOGETHER_API_KEY not set",
    )
    @pytest.mark.asyncio
    async def test_live_ping(self):
        """Real API call with 'Hola' to verify connectivity."""
        result = await call_together(
            [
                {"role": "system", "content": "Respond in one short sentence."},
                {"role": "user", "content": "Hola"},
            ],
            max_tokens=30,
            temperature=0.5,
        )
        assert result is not None
        assert len(result["content"]) > 0
        assert result["provider"] == "together"
        print(f"\nLive Together response: {result['content']}")
        print(f"  Model: {result['model']}, Latency: {result['latency_ms']}ms")
