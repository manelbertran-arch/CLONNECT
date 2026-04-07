"""OpenRouter provider for OpenAI-compatible model inference.

Supports any model hosted on OpenRouter (Gemma 4 31B, etc.)
via their OpenAI-compatible endpoint.

Env vars:
  OPENROUTER_API_KEY  — API key for OpenRouter (required)
  OPENROUTER_MODEL    — model ID (e.g. "google/gemma-4-31b-it")
  OPENROUTER_TIMEOUT  — request timeout in seconds (default: 120)

Config-driven mode:
  When called with model_id="<config_name>", sampling/runtime/provider info
  are loaded from config/models/<config_name>.json. Caller-passed
  temperature/max_tokens still override config values when not None.
"""

import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-31b-it")

# Circuit breaker — same pattern as together_provider
_openrouter_consecutive_failures = 0
_openrouter_circuit_open_until = 0.0
_OR_CB_THRESHOLD = int(os.getenv("OPENROUTER_CB_THRESHOLD", "3"))
_OR_CB_COOLDOWN = int(os.getenv("OPENROUTER_CB_COOLDOWN", "120"))


def _circuit_is_open() -> bool:
    if _openrouter_consecutive_failures >= _OR_CB_THRESHOLD:
        if time.time() < _openrouter_circuit_open_until:
            return True
    return False


def _record_success():
    global _openrouter_consecutive_failures, _openrouter_circuit_open_until
    _openrouter_consecutive_failures = 0
    _openrouter_circuit_open_until = 0.0


def _record_failure():
    global _openrouter_consecutive_failures, _openrouter_circuit_open_until
    _openrouter_consecutive_failures += 1
    if _openrouter_consecutive_failures >= _OR_CB_THRESHOLD:
        _openrouter_circuit_open_until = time.time() + _OR_CB_COOLDOWN
        logger.warning(
            "OpenRouter circuit breaker OPEN: %d failures, cooldown %ds",
            _openrouter_consecutive_failures, _OR_CB_COOLDOWN,
        )


async def call_openrouter(
    messages: list[dict],
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    model: Optional[str] = None,
    model_id: Optional[str] = None,
) -> Optional[dict]:
    """Call OpenRouter via OpenAI-compatible API.

    Args:
        messages: OpenAI-format messages [{role, content}, ...]
        max_tokens: max output tokens (None → config or 78 legacy default)
        temperature: sampling temperature (None → config or 0.7 legacy default)
        model: override model string (defaults to OPENROUTER_MODEL env var)
        model_id: optional config file name (e.g. "openrouter_default") to
                  load sampling/runtime/provider from config/models/{model_id}.json.
                  Caller-supplied temperature/max_tokens still win.

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
                "[OpenRouter] using config: %s, model_string=%s, temp=%s, max_tokens=%s",
                model_id,
                cfg_provider.get("model_string"),
                cfg_sampling.get("temperature"),
                cfg_sampling.get("max_tokens"),
            )
        except FileNotFoundError as e:
            logger.error("[OpenRouter] config load failed for %s: %s", model_id, e)
            return None

    # API key: from config-specified env var if set, else legacy OPENROUTER_API_KEY
    api_key_env = cfg_provider.get("api_key_env") or "OPENROUTER_API_KEY"
    api_key = os.getenv(api_key_env)
    if not api_key:
        logger.debug("%s not set, OpenRouter unavailable", api_key_env)
        return None

    if _circuit_is_open():
        logger.info("OpenRouter circuit breaker open, skipping")
        return None

    # Model string: explicit `model` arg > config > env var > module default
    if model is None:
        if cfg_provider.get("model_string"):
            model = cfg_provider["model_string"]
        else:
            model = os.getenv("OPENROUTER_MODEL", OPENROUTER_MODEL)

    # Sampling: caller arg > config > legacy default
    _temperature = temperature
    if _temperature is None:
        _temperature = cfg_sampling.get("temperature", 0.7) if cfg_sampling else 0.7
    _max_tokens = max_tokens
    if _max_tokens is None:
        _max_tokens = cfg_sampling.get("max_tokens", 78) if cfg_sampling else 78

    # Timeout: config > env > default
    if cfg_runtime:
        timeout = float(cfg_runtime.get("timeout_seconds", 120))
    else:
        timeout = float(os.getenv("OPENROUTER_TIMEOUT", "120"))

    # Base URL: config > module default
    base_url = cfg_provider.get("base_url") or OPENROUTER_BASE_URL

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
        # Optional penalties from config — only include when > 0
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
        latency_ms = int((time.monotonic() - start) * 1000)
        usage = response.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0

        if not content:
            logger.warning("OpenRouter returned empty content")
            _record_failure()
            return None

        logger.info(
            "OpenRouter OK: model=%s latency=%dms tokens_in=%d tokens_out=%d len=%d",
            model, latency_ms, tokens_in, tokens_out, len(content),
        )
        _record_success()
        return {
            "content": content,
            "model": model,
            "provider": "openrouter",
            "latency_ms": latency_ms,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }

    except asyncio.TimeoutError:
        logger.warning("OpenRouter timeout after %.0fs", timeout)
        _record_failure()
        return None
    except Exception as e:
        logger.error("OpenRouter error: %s", e)
        _record_failure()
        return None
