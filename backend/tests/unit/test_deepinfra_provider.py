"""Tests for DeepInfra provider, including config-driven mode and /no_think injection."""

import os
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.providers.deepinfra_provider import (
    call_deepinfra,
    strip_thinking_artifacts,
    DEEPINFRA_BASE_URL,
)
from core.providers import model_config as _mc


def _mock_response(content="Hola"):
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
    return mock_response


class TestCallDeepInfraLegacy:
    """Legacy path: model_id=None — current prod behavior must be preserved."""

    def setup_method(self):
        import core.providers.deepinfra_provider as dp
        dp._deepinfra_consecutive_failures = 0
        dp._deepinfra_circuit_open_until = 0.0
        _mc.clear_cache()

    @pytest.mark.asyncio
    async def test_no_api_key_returns_none(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DEEPINFRA_API_KEY", None)
            result = await call_deepinfra([{"role": "user", "content": "Hi"}])
            assert result is None

    @pytest.mark.asyncio
    async def test_legacy_qwen3_substring_injects_no_think(self):
        """Legacy path: /no_think appended to last user msg when 'Qwen3' in model."""
        mock_create = AsyncMock(return_value=_mock_response())
        env = {
            "DEEPINFRA_API_KEY": "test-key",
            "DEEPINFRA_MODEL": "Qwen/Qwen3-14B",
        }
        with patch.dict(os.environ, env):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance

                # We need to also patch DEEPINFRA_MODEL module-level constant
                import core.providers.deepinfra_provider as dp
                with patch.object(dp, "DEEPINFRA_MODEL", "Qwen/Qwen3-14B"):
                    result = await call_deepinfra(
                        [{"role": "user", "content": "hola"}],
                        max_tokens=50,
                        temperature=0.7,
                    )
                assert result is not None
                kwargs = mock_create.call_args.kwargs
                assert kwargs["model"] == "Qwen/Qwen3-14B"
                assert kwargs["max_tokens"] == 50
                assert kwargs["temperature"] == 0.7
                # /no_think should be appended to last user message
                assert kwargs["messages"][-1]["content"].endswith("/no_think")
                # No frequency_penalty by default in legacy
                assert "frequency_penalty" not in kwargs


class TestCallDeepInfraConfigDriven:

    def setup_method(self):
        import core.providers.deepinfra_provider as dp
        dp._deepinfra_consecutive_failures = 0
        dp._deepinfra_circuit_open_until = 0.0
        _mc.clear_cache()

    @pytest.mark.asyncio
    async def test_qwen3_14b_config_uses_config_values(self):
        mock_create = AsyncMock(return_value=_mock_response())
        with patch.dict(os.environ, {"DEEPINFRA_API_KEY": "test-key"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance

                result = await call_deepinfra(
                    [{"role": "user", "content": "hola"}],
                    model_id="qwen3_14b",
                )
                assert result is not None
                kwargs = mock_create.call_args.kwargs
                # From config/models/qwen3_14b.json
                assert kwargs["model"] == "Qwen/Qwen3-14B"
                assert kwargs["temperature"] == 0.7
                assert kwargs["max_tokens"] == 400
                # /no_think suffix from config
                assert kwargs["messages"][-1]["content"].endswith("/no_think")

    @pytest.mark.asyncio
    async def test_empty_no_think_suffix_skips_injection(self, tmp_path, monkeypatch):
        """A config with empty no_think_suffix must not inject /no_think."""
        # Write a temporary config without no_think_suffix
        cfg_dir = tmp_path / "config" / "models"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "test_no_inject.json").write_text("""{
            "model_id": "test_no_inject",
            "provider": {
                "name": "deepinfra",
                "api_key_env": "DEEPINFRA_API_KEY",
                "model_string": "Qwen/Qwen3-14B"
            },
            "sampling": {"temperature": 0.7, "max_tokens": 100},
            "thinking": {"enabled": false, "no_think_suffix": ""},
            "chat_template": {"strip_thinking_artifacts": false}
        }""")

        # Monkeypatch the loader's search dirs
        monkeypatch.setattr(_mc, "_MODEL_CONFIG_DIRS", [cfg_dir])
        _mc.clear_cache()

        mock_create = AsyncMock(return_value=_mock_response())
        with patch.dict(os.environ, {"DEEPINFRA_API_KEY": "test-key"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance

                await call_deepinfra(
                    [{"role": "user", "content": "hola"}],
                    model_id="test_no_inject",
                )
                kwargs = mock_create.call_args.kwargs
                # /no_think must NOT have been injected
                assert kwargs["messages"][-1]["content"] == "hola"

    @pytest.mark.asyncio
    async def test_caller_override_wins_over_config(self):
        mock_create = AsyncMock(return_value=_mock_response())
        with patch.dict(os.environ, {"DEEPINFRA_API_KEY": "test-key"}):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance

                await call_deepinfra(
                    [{"role": "user", "content": "hola"}],
                    temperature=0.3,
                    max_tokens=42,
                    model_id="qwen3_14b",
                )
                kwargs = mock_create.call_args.kwargs
                assert kwargs["temperature"] == 0.3
                assert kwargs["max_tokens"] == 42

    @pytest.mark.asyncio
    async def test_missing_api_key_with_config(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DEEPINFRA_API_KEY", None)
            result = await call_deepinfra(
                [{"role": "user", "content": "hola"}],
                model_id="qwen3_14b",
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_config_model_string_overrides_env_var(self):
        """When config provides model_string, the env var DEEPINFRA_MODEL is ignored."""
        mock_create = AsyncMock(return_value=_mock_response())
        env = {
            "DEEPINFRA_API_KEY": "test-key",
            "DEEPINFRA_MODEL": "should-be-ignored",
        }
        with patch.dict(os.environ, env):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance

                await call_deepinfra(
                    [{"role": "user", "content": "hi"}],
                    model_id="qwen3_14b",
                )
                kwargs = mock_create.call_args.kwargs
                assert kwargs["model"] == "Qwen/Qwen3-14B"


class TestDeepInfraFallback:
    """Transparent fallback to OpenRouter when DeepInfra fails."""

    def setup_method(self):
        import core.providers.deepinfra_provider as dp
        dp._deepinfra_consecutive_failures = 0
        dp._deepinfra_circuit_open_until = 0.0
        _mc.clear_cache()

    _OR_RESULT = {
        "content": "Hola desde OpenRouter",
        "model": "google/gemma-4-31b-it",
        "provider": "openrouter",
        "latency_ms": 500,
        "tokens_in": 10,
        "tokens_out": 5,
        "finish_reason": "stop",
    }

    @pytest.mark.asyncio
    async def test_fallback_on_empty_content(self):
        """Empty DeepInfra response triggers OpenRouter fallback when configured."""
        mock_create = AsyncMock(return_value=_mock_response(""))
        env = {
            "DEEPINFRA_API_KEY": "test-key",
            "DEEPINFRA_FALLBACK_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "or-test-key",
        }
        with patch.dict(os.environ, env):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance
                with patch(
                    "core.providers.openrouter_provider.call_openrouter",
                    new_callable=AsyncMock,
                    return_value=self._OR_RESULT,
                ):
                    result = await call_deepinfra(
                        [{"role": "user", "content": "hola"}],
                        max_tokens=100,
                        temperature=0.7,
                        model="google/gemma-4-31b-it",
                    )
        assert result is not None
        assert result["provider"] == "openrouter-fallback"
        assert result["content"] == "Hola desde OpenRouter"

    @pytest.mark.asyncio
    async def test_no_fallback_when_env_not_set(self):
        """Without DEEPINFRA_FALLBACK_PROVIDER, empty content still returns None."""
        mock_create = AsyncMock(return_value=_mock_response(""))
        env = {"DEEPINFRA_API_KEY": "test-key"}
        with patch.dict(os.environ, env):
            os.environ.pop("DEEPINFRA_FALLBACK_PROVIDER", None)
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance
                result = await call_deepinfra(
                    [{"role": "user", "content": "hola"}],
                    max_tokens=100,
                    temperature=0.7,
                    model="google/gemma-4-31b-it",
                )
        assert result is None

    @pytest.mark.asyncio
    async def test_fallback_when_circuit_open(self):
        """Open circuit breaker triggers OpenRouter fallback when configured."""
        import core.providers.deepinfra_provider as dp
        dp._deepinfra_consecutive_failures = 5
        dp._deepinfra_circuit_open_until = time.time() + 60

        env = {
            "DEEPINFRA_API_KEY": "test-key",
            "DEEPINFRA_FALLBACK_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "or-test-key",
        }
        with patch.dict(os.environ, env):
            with patch(
                "core.providers.openrouter_provider.call_openrouter",
                new_callable=AsyncMock,
                return_value=self._OR_RESULT,
            ):
                result = await call_deepinfra(
                    [{"role": "user", "content": "hola"}],
                    max_tokens=100,
                    temperature=0.7,
                    model="google/gemma-4-31b-it",
                )
        assert result is not None
        assert result["provider"] == "openrouter-fallback"

    @pytest.mark.asyncio
    async def test_no_fallback_when_circuit_open_and_env_not_set(self):
        """Open circuit with no fallback env var returns None."""
        import core.providers.deepinfra_provider as dp
        dp._deepinfra_consecutive_failures = 5
        dp._deepinfra_circuit_open_until = time.time() + 60

        env = {"DEEPINFRA_API_KEY": "test-key"}
        with patch.dict(os.environ, env):
            os.environ.pop("DEEPINFRA_FALLBACK_PROVIDER", None)
            result = await call_deepinfra(
                [{"role": "user", "content": "hola"}],
                max_tokens=100,
                temperature=0.7,
                model="google/gemma-4-31b-it",
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_no_fallback_when_openrouter_key_missing(self):
        """Fallback configured but OPENROUTER_API_KEY absent returns None with warning."""
        mock_create = AsyncMock(return_value=_mock_response(""))
        env = {"DEEPINFRA_API_KEY": "test-key", "DEEPINFRA_FALLBACK_PROVIDER": "openrouter"}
        with patch.dict(os.environ, env):
            os.environ.pop("OPENROUTER_API_KEY", None)
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance
                result = await call_deepinfra(
                    [{"role": "user", "content": "hola"}],
                    max_tokens=100,
                    temperature=0.7,
                    model="google/gemma-4-31b-it",
                )
        assert result is None

    @pytest.mark.asyncio
    async def test_fallback_model_override(self):
        """DEEPINFRA_FALLBACK_MODEL overrides the model slug sent to OpenRouter."""
        import core.providers.deepinfra_provider as dp
        dp._deepinfra_consecutive_failures = 5
        dp._deepinfra_circuit_open_until = time.time() + 60

        captured = {}

        async def fake_openrouter(messages, max_tokens=None, temperature=None, model=None):
            captured["model"] = model
            return self._OR_RESULT

        env = {
            "DEEPINFRA_API_KEY": "test-key",
            "OPENROUTER_API_KEY": "or-test-key",
            "DEEPINFRA_FALLBACK_PROVIDER": "openrouter",
            "DEEPINFRA_FALLBACK_MODEL": "qwen/qwen3-32b",  # OpenRouter slug
        }
        with patch.dict(os.environ, env):
            with patch(
                "core.providers.openrouter_provider.call_openrouter",
                side_effect=fake_openrouter,
            ):
                await call_deepinfra(
                    [{"role": "user", "content": "hola"}],
                    model="Qwen/Qwen3-32B",  # DeepInfra slug
                )
        assert captured["model"] == "qwen/qwen3-32b"

    @pytest.mark.asyncio
    async def test_fallback_params_passed_correctly(self):
        """Resolved max_tokens and temperature are forwarded to OpenRouter."""
        mock_create = AsyncMock(return_value=_mock_response(""))
        captured_kwargs = {}

        async def fake_openrouter(messages, max_tokens=None, temperature=None, model=None):
            captured_kwargs.update(
                max_tokens=max_tokens, temperature=temperature, model=model
            )
            return self._OR_RESULT

        env = {
            "DEEPINFRA_API_KEY": "test-key",
            "DEEPINFRA_FALLBACK_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "or-test-key",
        }
        with patch.dict(os.environ, env):
            with patch("openai.AsyncOpenAI") as MockClient:
                instance = MagicMock()
                instance.chat.completions.create = mock_create
                MockClient.return_value = instance
                with patch(
                    "core.providers.openrouter_provider.call_openrouter",
                    side_effect=fake_openrouter,
                ):
                    await call_deepinfra(
                        [{"role": "user", "content": "hola"}],
                        max_tokens=512,
                        temperature=0.1,
                        model="google/gemma-4-31b-it",
                    )
        assert captured_kwargs["max_tokens"] == 512
        assert captured_kwargs["temperature"] == 0.1
        assert captured_kwargs["model"] == "google/gemma-4-31b-it"


class TestStripThinkingArtifacts:
    """Pure function tests — kept after refactor for regression safety."""

    def test_strips_full_think_block(self):
        assert strip_thinking_artifacts("<think>foo</think>hola") == "hola"

    def test_strips_orphan_close(self):
        assert strip_thinking_artifacts("</think>hola") == "hola"

    def test_strips_trailing_no_think(self):
        assert strip_thinking_artifacts("hola /no_think") == "hola"
