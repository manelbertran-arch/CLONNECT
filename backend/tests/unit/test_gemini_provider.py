"""Tests for Gemini provider routing + LLM_MODEL_NAME dispatch."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.providers import gemini_provider as gp
from core.providers import model_config as _mc


class TestGenerateDmResponseRouting:
    """Routing layer: generate_dm_response dispatches based on LLM_MODEL_NAME."""

    def setup_method(self):
        gp._gemini_consecutive_failures = 0
        gp._gemini_circuit_open_until = 0.0
        _mc.clear_cache()

    @pytest.mark.asyncio
    async def test_unset_llm_model_name_uses_legacy_cascade(self):
        """LLM_MODEL_NAME unset → existing LLM_PRIMARY_PROVIDER cascade."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LLM_MODEL_NAME", None)
            with patch.object(gp, "_try_deepinfra", new_callable=AsyncMock) as mock_di, \
                 patch.object(gp, "generate_response_gemini", new_callable=AsyncMock) as mock_gem, \
                 patch.object(gp, "_call_openai_mini", new_callable=AsyncMock) as mock_omi:
                mock_di.return_value = None
                mock_gem.return_value = {"content": "ok", "model": "g", "provider": "gemini", "latency_ms": 1}
                mock_omi.return_value = None

                # Force legacy cascade through LLM_PRIMARY_PROVIDER=gemini path
                with patch.object(gp, "LLM_PRIMARY_PROVIDER", "gemini"):
                    result = await gp.generate_dm_response(
                        [{"role": "user", "content": "hi"}],
                        max_tokens=50,
                        temperature=0.7,
                    )
                    assert result is not None
                    # Deepinfra not called via legacy cascade when LLM_PRIMARY_PROVIDER=gemini
                    mock_di.assert_not_called()
                    mock_gem.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_model_name_qwen3_14b_routes_to_deepinfra(self):
        with patch.dict(os.environ, {"LLM_MODEL_NAME": "qwen3_14b"}):
            with patch.object(gp, "_try_deepinfra", new_callable=AsyncMock) as mock_di, \
                 patch.object(gp, "generate_response_gemini", new_callable=AsyncMock) as mock_gem:
                mock_di.return_value = {"content": "ok", "model": "Qwen/Qwen3-14B", "provider": "deepinfra", "latency_ms": 5}
                result = await gp.generate_dm_response(
                    [{"role": "user", "content": "hi"}],
                    max_tokens=50,
                    temperature=0.7,
                )
                assert result is not None
                assert result["provider"] == "deepinfra"
                mock_di.assert_called_once()
                # Verify model_id was forwarded
                call_kwargs = mock_di.call_args.kwargs
                assert call_kwargs.get("model_id") == "qwen3_14b"
                mock_gem.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_model_name_gemini_flash_lite_routes_to_gemini(self):
        with patch.dict(os.environ, {"LLM_MODEL_NAME": "gemini_flash_lite", "GOOGLE_API_KEY": "k"}):
            with patch.object(gp, "_try_deepinfra", new_callable=AsyncMock) as mock_di, \
                 patch.object(gp, "generate_response_gemini", new_callable=AsyncMock) as mock_gem:
                mock_gem.return_value = {"content": "ok", "model": "gemini-2.5-flash-lite", "provider": "gemini", "latency_ms": 3}
                result = await gp.generate_dm_response(
                    [{"role": "user", "content": "hi"}],
                    max_tokens=50,
                    temperature=0.7,
                )
                assert result is not None
                assert result["provider"] == "gemini"
                mock_gem.assert_called_once()
                # model_id forwarded
                call_kwargs = mock_gem.call_args.kwargs
                assert call_kwargs.get("model_id") == "gemini_flash_lite"
                mock_di.assert_not_called()


class TestCallGeminiConfigDriven:
    """_call_gemini reads safety / penalties from config when model_id provided."""

    def setup_method(self):
        gp._gemini_consecutive_failures = 0
        gp._gemini_circuit_open_until = 0.0
        _mc.clear_cache()

    @pytest.mark.asyncio
    async def test_legacy_path_uses_env_var_penalties(self):
        """No model_id → reads GEMINI_*_PENALTY env vars (current prod behavior)."""
        captured = {}

        class FakeResp:
            status_code = 200
            def json(self):
                return {
                    "candidates": [{
                        "content": {"parts": [{"text": "hola"}]},
                        "finishReason": "STOP",
                    }],
                    "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 1},
                }
            def raise_for_status(self):
                return None

        async def fake_post(url, json=None):
            captured["payload"] = json
            return FakeResp()

        class FakeClient:
            def __init__(self, *a, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return None
            async def post(self, url, json=None):
                return await fake_post(url, json=json)

        with patch.dict(os.environ, {"GEMINI_PRESENCE_PENALTY": "0.5", "GEMINI_FREQUENCY_PENALTY": "0.3"}):
            with patch("httpx.AsyncClient", FakeClient):
                result = await gp._call_gemini(
                    "gemini-2.5-flash-lite", "test-key", "sys", "hi",
                    max_tokens=20, temperature=0.7, max_retries=1,
                )
                assert result is not None
                gen_cfg = captured["payload"]["generationConfig"]
                assert gen_cfg["presencePenalty"] == 0.5
                assert gen_cfg["frequencyPenalty"] == 0.3

    @pytest.mark.asyncio
    async def test_config_path_uses_config_penalties(self, tmp_path, monkeypatch):
        """When model_id provided, penalties come from config not env."""
        cfg_dir = tmp_path / "config" / "models"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "test_gemini_cfg.json").write_text("""{
            "model_id": "test_gemini_cfg",
            "provider": {
                "name": "gemini",
                "api_key_env": "GOOGLE_API_KEY",
                "model_string": "gemini-2.5-flash-lite"
            },
            "sampling": {
                "temperature": 0.7, "max_tokens": 60,
                "frequency_penalty": 0.9, "presence_penalty": 0.8
            },
            "safety": {
                "harassment": "BLOCK_NONE",
                "hate_speech": "BLOCK_NONE",
                "sexually_explicit": "BLOCK_NONE",
                "dangerous_content": "BLOCK_NONE"
            }
        }""")
        monkeypatch.setattr(_mc, "_MODEL_CONFIG_DIRS", [cfg_dir])
        _mc.clear_cache()

        captured = {}

        class FakeResp:
            status_code = 200
            def json(self):
                return {
                    "candidates": [{
                        "content": {"parts": [{"text": "ok"}]},
                        "finishReason": "STOP",
                    }],
                    "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 1},
                }
            def raise_for_status(self):
                return None

        class FakeClient:
            def __init__(self, *a, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return None
            async def post(self, url, json=None):
                captured["payload"] = json
                return FakeResp()

        # Make sure env vars set differently are NOT used
        with patch.dict(os.environ, {"GEMINI_PRESENCE_PENALTY": "0.0", "GEMINI_FREQUENCY_PENALTY": "0.0"}):
            with patch("httpx.AsyncClient", FakeClient):
                result = await gp._call_gemini(
                    "gemini-2.5-flash-lite", "test-key", "sys", "hi",
                    max_tokens=20, temperature=0.7, max_retries=1,
                    model_id="test_gemini_cfg",
                )
                assert result is not None
                gen_cfg = captured["payload"]["generationConfig"]
                assert gen_cfg["frequencyPenalty"] == 0.9
                assert gen_cfg["presencePenalty"] == 0.8
                # Safety from config
                cats = {s["category"]: s["threshold"] for s in captured["payload"]["safetySettings"]}
                assert cats["HARM_CATEGORY_HARASSMENT"] == "BLOCK_NONE"
