"""Tests for DeepInfra provider, including config-driven mode and /no_think injection."""

import os
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


class TestStripThinkingArtifacts:
    """Pure function tests — kept after refactor for regression safety."""

    def test_strips_full_think_block(self):
        assert strip_thinking_artifacts("<think>foo</think>hola") == "hola"

    def test_strips_orphan_close(self):
        assert strip_thinking_artifacts("</think>hola") == "hola"

    def test_strips_trailing_no_think(self):
        assert strip_thinking_artifacts("hola /no_think") == "hola"
