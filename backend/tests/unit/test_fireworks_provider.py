"""Tests for Fireworks AI provider."""

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.providers.fireworks_provider import (
    call_fireworks,
    _record_failure,
    _record_success,
    _circuit_is_open,
    FIREWORKS_BASE_URL,
)


class TestCallFireworks:
    """Test call_fireworks function."""

    def setup_method(self):
        import core.providers.fireworks_provider as fp
        fp._fw_consecutive_failures = 0
        fp._fw_circuit_open_until = 0.0

    @pytest.mark.asyncio
    async def test_returns_none_without_api_key(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FIREWORKS_API_KEY", None)
            result = await call_fireworks(
                [{"role": "user", "content": "Hola"}],
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_successful_call(self):
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 5

        mock_choice = MagicMock()
        mock_choice.message.content = "Hola! 🩷"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_create = AsyncMock(return_value=mock_response)

        with patch.dict(os.environ, {"FIREWORKS_API_KEY": "test-key"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance

                result = await call_fireworks(
                    [{"role": "user", "content": "Hola"}],
                    max_tokens=60,
                    temperature=0.8,
                )

                assert result is not None
                assert result["content"] == "Hola! 🩷"
                assert result["provider"] == "fireworks"
                assert result["tokens_in"] == 10
                assert result["tokens_out"] == 5
                assert "latency_ms" in result

                MockClient.assert_called_once_with(
                    api_key="test-key",
                    base_url=FIREWORKS_BASE_URL,
                )

    @pytest.mark.asyncio
    async def test_empty_content_returns_none(self):
        mock_choice = MagicMock()
        mock_choice.message.content = ""
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=0)

        with patch.dict(os.environ, {"FIREWORKS_API_KEY": "test-key"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = AsyncMock(return_value=mock_response)
                MockClient.return_value = instance

                result = await call_fireworks(
                    [{"role": "user", "content": "Hola"}],
                )
                assert result is None

    @pytest.mark.asyncio
    async def test_timeout_returns_none(self):
        async def slow_call(*a, **kw):
            await asyncio.sleep(100)

        with patch.dict(os.environ, {"FIREWORKS_API_KEY": "test-key", "FIREWORKS_TIMEOUT": "0.01"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = slow_call
                MockClient.return_value = instance

                result = await call_fireworks(
                    [{"role": "user", "content": "Hola"}],
                )
                assert result is None

    @pytest.mark.asyncio
    async def test_api_error_returns_none(self):
        with patch.dict(os.environ, {"FIREWORKS_API_KEY": "test-key"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = AsyncMock(
                    side_effect=Exception("rate limited")
                )
                MockClient.return_value = instance

                result = await call_fireworks(
                    [{"role": "user", "content": "Hola"}],
                )
                assert result is None

    @pytest.mark.asyncio
    async def test_model_override(self):
        mock_choice = MagicMock()
        mock_choice.message.content = "Response"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=3)

        mock_create = AsyncMock(return_value=mock_response)

        with patch.dict(os.environ, {"FIREWORKS_API_KEY": "test-key"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance

                result = await call_fireworks(
                    [{"role": "user", "content": "Hi"}],
                    model="accounts/my-org/models/iris-lora-v1",
                )
                assert result is not None
                assert result["model"] == "accounts/my-org/models/iris-lora-v1"
                mock_create.assert_called_once()
                call_kwargs = mock_create.call_args[1]
                assert call_kwargs["model"] == "accounts/my-org/models/iris-lora-v1"


class TestCallFireworksConfigDriven:
    """Config-driven path: model_id loads sampling/runtime/provider from JSON."""

    def setup_method(self):
        import core.providers.fireworks_provider as fp
        fp._fw_consecutive_failures = 0
        fp._fw_circuit_open_until = 0.0
        from core.providers import model_config as _mc
        _mc.clear_cache()

    @pytest.mark.asyncio
    async def test_legacy_path_unchanged(self):
        """model_id=None → existing behavior preserved."""
        mock_choice = MagicMock()
        mock_choice.message.content = "Hi"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=2)
        mock_create = AsyncMock(return_value=mock_response)
        with patch.dict(os.environ, {"FIREWORKS_API_KEY": "test-key"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance

                result = await call_fireworks(
                    [{"role": "user", "content": "Hi"}],
                    max_tokens=60,
                    temperature=0.7,
                )
                assert result is not None
                kwargs = mock_create.call_args.kwargs
                assert kwargs["max_tokens"] == 60
                assert kwargs["temperature"] == 0.7
                assert "frequency_penalty" not in kwargs
                assert "presence_penalty" not in kwargs

    @pytest.mark.asyncio
    async def test_loads_config_values(self):
        mock_choice = MagicMock()
        mock_choice.message.content = "Hi"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=2)
        mock_create = AsyncMock(return_value=mock_response)
        with patch.dict(os.environ, {"FIREWORKS_API_KEY": "test-key"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance

                result = await call_fireworks(
                    [{"role": "user", "content": "Hi"}],
                    model_id="fireworks_default",
                )
                assert result is not None
                kwargs = mock_create.call_args.kwargs
                assert kwargs["model"] == "accounts/fireworks/models/qwen3-8b"
                assert kwargs["max_tokens"] == 60
                assert kwargs["temperature"] == 0.7

    @pytest.mark.asyncio
    async def test_caller_override_wins_over_config(self):
        mock_choice = MagicMock()
        mock_choice.message.content = "Hi"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=2)
        mock_create = AsyncMock(return_value=mock_response)
        with patch.dict(os.environ, {"FIREWORKS_API_KEY": "test-key"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance

                await call_fireworks(
                    [{"role": "user", "content": "Hi"}],
                    temperature=0.3,
                    max_tokens=42,
                    model_id="fireworks_default",
                )
                kwargs = mock_create.call_args.kwargs
                assert kwargs["temperature"] == 0.3
                assert kwargs["max_tokens"] == 42

    @pytest.mark.asyncio
    async def test_unknown_model_id_falls_back_to_default(self):
        mock_choice = MagicMock()
        mock_choice.message.content = "Hi"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock(prompt_tokens=5, completion_tokens=2)
        mock_create = AsyncMock(return_value=mock_response)
        with patch.dict(os.environ, {"FIREWORKS_API_KEY": "test-key"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance

                result = await call_fireworks(
                    [{"role": "user", "content": "Hi"}],
                    model_id="nonexistent_xyz",
                )
                assert result is not None
                kwargs = mock_create.call_args.kwargs
                assert kwargs["temperature"] == 0.5
                assert kwargs["max_tokens"] == 120

    @pytest.mark.asyncio
    async def test_missing_api_key_with_config(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FIREWORKS_API_KEY", None)
            result = await call_fireworks(
                [{"role": "user", "content": "Hi"}],
                model_id="fireworks_default",
            )
            assert result is None


class TestCircuitBreaker:
    def setup_method(self):
        import core.providers.fireworks_provider as fp
        fp._fw_consecutive_failures = 0
        fp._fw_circuit_open_until = 0.0

    def test_circuit_starts_closed(self):
        assert not _circuit_is_open()

    def test_circuit_opens_after_threshold(self):
        import core.providers.fireworks_provider as fp
        for _ in range(fp._FW_CB_THRESHOLD):
            _record_failure()
        assert _circuit_is_open()

    def test_success_resets_circuit(self):
        import core.providers.fireworks_provider as fp
        for _ in range(fp._FW_CB_THRESHOLD):
            _record_failure()
        assert _circuit_is_open()
        _record_success()
        assert not _circuit_is_open()

    @pytest.mark.asyncio
    async def test_open_circuit_skips_call(self):
        import core.providers.fireworks_provider as fp
        for _ in range(fp._FW_CB_THRESHOLD):
            _record_failure()

        with patch.dict(os.environ, {"FIREWORKS_API_KEY": "test-key"}):
            result = await call_fireworks(
                [{"role": "user", "content": "Hola"}],
            )
            assert result is None


class TestLiveIntegration:
    @pytest.mark.skipif(
        not os.getenv("FIREWORKS_API_KEY"),
        reason="FIREWORKS_API_KEY not set",
    )
    @pytest.mark.asyncio
    async def test_live_ping(self):
        result = await call_fireworks(
            [
                {"role": "system", "content": "Respond in one short sentence."},
                {"role": "user", "content": "Hola"},
            ],
            max_tokens=30,
            temperature=0.5,
        )
        assert result is not None
        assert len(result["content"]) > 0
        assert result["provider"] == "fireworks"
        print(f"\nLive Fireworks response: {result['content']}")
        print(f"  Model: {result['model']}, Latency: {result['latency_ms']}ms")
