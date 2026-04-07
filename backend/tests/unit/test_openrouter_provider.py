"""Tests for OpenRouter provider, including config-driven mode."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.providers.openrouter_provider import (
    call_openrouter,
    _record_failure,
    _record_success,
    _circuit_is_open,
    OPENROUTER_BASE_URL,
)
from core.providers import model_config as _mc


def _mock_response(content="Hola!", pin=10, pout=5):
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = MagicMock(prompt_tokens=pin, completion_tokens=pout)
    return mock_response


class TestCallOpenRouterLegacy:
    """Legacy path: model_id=None → existing behavior preserved."""

    def setup_method(self):
        import core.providers.openrouter_provider as op
        op._openrouter_consecutive_failures = 0
        op._openrouter_circuit_open_until = 0.0
        _mc.clear_cache()

    @pytest.mark.asyncio
    async def test_returns_none_without_api_key(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENROUTER_API_KEY", None)
            result = await call_openrouter([{"role": "user", "content": "Hi"}])
            assert result is None

    @pytest.mark.asyncio
    async def test_legacy_path_uses_env_and_arg_defaults(self):
        mock_create = AsyncMock(return_value=_mock_response())
        env = {
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_MODEL": "google/gemma-4-31b-it",
        }
        with patch.dict(os.environ, env):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance

                result = await call_openrouter(
                    [{"role": "user", "content": "Hi"}],
                    max_tokens=50,
                    temperature=0.6,
                )
                assert result is not None
                assert result["provider"] == "openrouter"
                MockClient.assert_called_once_with(
                    api_key="test-key",
                    base_url=OPENROUTER_BASE_URL,
                )
                kwargs = mock_create.call_args.kwargs
                assert kwargs["model"] == "google/gemma-4-31b-it"
                assert kwargs["max_tokens"] == 50
                assert kwargs["temperature"] == 0.6
                # No penalties in legacy path
                assert "frequency_penalty" not in kwargs
                assert "presence_penalty" not in kwargs


class TestCallOpenRouterConfigDriven:
    """Config-driven path: model_id loads sampling/runtime/provider from JSON."""

    def setup_method(self):
        import core.providers.openrouter_provider as op
        op._openrouter_consecutive_failures = 0
        op._openrouter_circuit_open_until = 0.0
        _mc.clear_cache()

    @pytest.mark.asyncio
    async def test_loads_config_values(self):
        mock_create = AsyncMock(return_value=_mock_response())
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance

                result = await call_openrouter(
                    [{"role": "user", "content": "Hi"}],
                    model_id="openrouter_default",
                )
                assert result is not None
                kwargs = mock_create.call_args.kwargs
                # From config/models/openrouter_default.json
                assert kwargs["model"] == "google/gemma-4-31b-it"
                assert kwargs["max_tokens"] == 78
                assert kwargs["temperature"] == 0.7

    @pytest.mark.asyncio
    async def test_caller_override_wins_over_config(self):
        mock_create = AsyncMock(return_value=_mock_response())
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance

                result = await call_openrouter(
                    [{"role": "user", "content": "Hi"}],
                    temperature=0.3,
                    max_tokens=42,
                    model_id="openrouter_default",
                )
                assert result is not None
                kwargs = mock_create.call_args.kwargs
                assert kwargs["temperature"] == 0.3
                assert kwargs["max_tokens"] == 42

    @pytest.mark.asyncio
    async def test_unknown_model_id_falls_back_to_default(self):
        mock_create = AsyncMock(return_value=_mock_response())
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance

                result = await call_openrouter(
                    [{"role": "user", "content": "Hi"}],
                    model_id="nonexistent_xyz",
                )
                # default_config.json has empty provider — but loader returns it,
                # so call should still happen with default sampling values
                assert result is not None
                kwargs = mock_create.call_args.kwargs
                # default_config.json max_tokens=120, temp=0.5
                assert kwargs["temperature"] == 0.5
                assert kwargs["max_tokens"] == 120

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_none_gracefully(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENROUTER_API_KEY", None)
            result = await call_openrouter(
                [{"role": "user", "content": "Hi"}],
                model_id="openrouter_default",
            )
            assert result is None


class TestCircuitBreaker:
    def setup_method(self):
        import core.providers.openrouter_provider as op
        op._openrouter_consecutive_failures = 0
        op._openrouter_circuit_open_until = 0.0

    def test_circuit_starts_closed(self):
        assert not _circuit_is_open()

    def test_circuit_opens_after_threshold(self):
        import core.providers.openrouter_provider as op
        for _ in range(op._OR_CB_THRESHOLD):
            _record_failure()
        assert _circuit_is_open()

    def test_success_resets_circuit(self):
        import core.providers.openrouter_provider as op
        for _ in range(op._OR_CB_THRESHOLD):
            _record_failure()
        _record_success()
        assert not _circuit_is_open()
