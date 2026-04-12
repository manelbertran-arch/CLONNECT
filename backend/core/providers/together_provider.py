"""Together AI provider for OpenAI-compatible model inference.

Supports any model hosted on Together AI (Qwen3-32B, Llama, fine-tuned, etc.)
via their OpenAI-compatible endpoint.

Env vars:
  TOGETHER_API_KEY  — API key for Together AI
  TOGETHER_MODEL    — model ID (e.g. "Qwen/Qwen3-32B", or fine-tuned endpoint)
  TOGETHER_TIMEOUT  — request timeout in seconds (default: 15)
"""

import asyncio
import logging
import os
import time
import time as _time
from typing import Optional

logger = logging.getLogger(__name__)

TOGETHER_BASE_URL = "https://api.together.xyz/v1"
TOGETHER_MODEL = os.getenv("TOGETHER_MODEL", "Qwen/Qwen3-32B")

# Circuit breaker — same pattern as Gemini/DeepInfra
_together_consecutive_failures = 0
_together_circuit_open_until = 0.0
_TG_CB_THRESHOLD = int(os.getenv("TOGETHER_CB_THRESHOLD", "3"))
_TG_CB_COOLDOWN = int(os.getenv("TOGETHER_CB_COOLDOWN", "120"))


def _circuit_is_open() -> bool:
    if _together_consecutive_failures >= _TG_CB_THRESHOLD:
        if _time.time() < _together_circuit_open_until:
            return True
    return False


def _record_success():
    global _together_consecutive_failures, _together_circuit_open_until
    _together_consecutive_failures = 0
    _together_circuit_open_until = 0.0


def _record_failure():
    global _together_consecutive_failures, _together_circuit_open_until
    _together_consecutive_failures += 1
    if _together_consecutive_failures >= _TG_CB_THRESHOLD:
        _together_circuit_open_until = _time.time() + _TG_CB_COOLDOWN
        logger.warning(
            "Together circuit breaker OPEN: %d failures, cooldown %ds",
            _together_consecutive_failures, _TG_CB_COOLDOWN,
        )


async def call_together(
    messages: list[dict],
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    model: Optional[str] = None,
    model_id: Optional[str] = None,
) -> Optional[dict]:
    """Call Together AI via OpenAI-compatible API.

    Args:
        messages: OpenAI-format messages [{role, content}, ...]
        max_tokens: max output tokens (None → config or 60 legacy default)
        temperature: sampling temperature (None → config or 0.7 legacy default)
        model: override model (defaults to TOGETHER_MODEL env var)
        model_id: optional config file name to load sampling/runtime/provider
                  from config/models/{model_id}.json. Caller-supplied
                  temperature/max_tokens still win.

    Returns:
        dict with {content, model, provider, latency_ms, tokens_in, tokens_out}
        or None on failure.
    """
    # ── Config-driven path ──
    cfg_sampling: dict = {}
    cfg_runtime: dict = {}
    cfg_provider: dict = {}
    if model_id is not None:
        try:
            from core.providers.model_config import (
                load_model_config,
                get_provider_info,
                get_sampling,
                get_runtime,
            )
            cfg = load_model_config(model_id)
            cfg_provider = get_provider_info(cfg)
            cfg_sampling = get_sampling(cfg)
            cfg_runtime = get_runtime(cfg)
            logger.info(
                "[Together] using config: %s, model_string=%s, temp=%s, max_tokens=%s",
                model_id,
                cfg_provider.get("model_string"),
                cfg_sampling.get("temperature"),
                cfg_sampling.get("max_tokens"),
            )
        except FileNotFoundError as e:
            logger.error("[Together] config load failed for %s: %s", model_id, e)
            return None

    api_key_env = cfg_provider.get("api_key_env") or "TOGETHER_API_KEY"
    api_key = os.getenv(api_key_env)
    if not api_key:
        logger.debug("%s not set, Together AI unavailable", api_key_env)
        return None

    if _circuit_is_open():
        logger.info("Together circuit breaker open, skipping")
        return None

    if model is None:
        if cfg_provider.get("model_string"):
            model = cfg_provider["model_string"]
        else:
            model = TOGETHER_MODEL

    _temperature = temperature
    if _temperature is None:
        _temperature = cfg_sampling.get("temperature", 0.7) if cfg_sampling else 0.7
    _max_tokens = max_tokens
    if _max_tokens is None:
        _max_tokens = cfg_sampling.get("max_tokens", 60) if cfg_sampling else 60

    if cfg_runtime:
        timeout = float(cfg_runtime.get("timeout_seconds", 15))
    else:
        timeout = float(os.getenv("TOGETHER_TIMEOUT", "15"))

    base_url = cfg_provider.get("base_url") or TOGETHER_BASE_URL

    start = time.monotonic()

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

        create_kwargs: dict = dict(
            model=model,
            messages=messages,
            max_tokens=_max_tokens,
            temperature=_temperature,
        )
        if cfg_sampling:
            fp = float(cfg_sampling.get("frequency_penalty", 0.0) or 0.0)
            pp = float(cfg_sampling.get("presence_penalty", 0.0) or 0.0)
            if fp > 0:
                create_kwargs["frequency_penalty"] = fp
            if pp > 0:
                create_kwargs["presence_penalty"] = pp

        response = await asyncio.wait_for(
            client.chat.completions.create(**create_kwargs),
            timeout=timeout,
        )

        content = (response.choices[0].message.content or "").strip()
        finish_reason = (response.choices[0].finish_reason or "").lower()
        latency_ms = int((time.monotonic() - start) * 1000)
        usage = response.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0

        if not content:
            logger.warning("Together returned empty content")
            _record_failure()
            return None

        logger.info(
            "Together OK: model=%s latency=%dms tokens_in=%d tokens_out=%d len=%d finish_reason=%s",
            model, latency_ms, tokens_in, tokens_out, len(content), finish_reason,
        )
        _record_success()
        return {
            "content": content,
            "model": model,
            "provider": "together",
            "latency_ms": latency_ms,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "finish_reason": finish_reason,
        }

    except asyncio.TimeoutError:
        logger.warning("Together timeout after %.0fs", timeout)
        _record_failure()
        return None
    except Exception as e:
        logger.error("Together error: %s", e)
        _record_failure()
        return None
