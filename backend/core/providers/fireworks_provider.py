"""Fireworks AI provider for OpenAI-compatible model inference.

Supports LoRA serverless on Qwen3-8B at base model pricing.
Uses OpenAI-compatible API format.

Env vars:
  FIREWORKS_API_KEY  — API key for Fireworks AI
  FIREWORKS_MODEL    — model ID (e.g. "accounts/your-account/models/your-lora")
  FIREWORKS_TIMEOUT  — request timeout in seconds (default: 15)
"""

import asyncio
import logging
import os
import time
import time as _time
from typing import Optional

logger = logging.getLogger(__name__)

FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"
FIREWORKS_MODEL = os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/qwen3-8b")

# Circuit breaker
_fw_consecutive_failures = 0
_fw_circuit_open_until = 0.0
_FW_CB_THRESHOLD = int(os.getenv("FIREWORKS_CB_THRESHOLD", "3"))
_FW_CB_COOLDOWN = int(os.getenv("FIREWORKS_CB_COOLDOWN", "120"))


def _circuit_is_open() -> bool:
    if _fw_consecutive_failures >= _FW_CB_THRESHOLD:
        if _time.time() < _fw_circuit_open_until:
            return True
    return False


def _record_success():
    global _fw_consecutive_failures, _fw_circuit_open_until
    _fw_consecutive_failures = 0
    _fw_circuit_open_until = 0.0


def _record_failure():
    global _fw_consecutive_failures, _fw_circuit_open_until
    _fw_consecutive_failures += 1
    if _fw_consecutive_failures >= _FW_CB_THRESHOLD:
        _fw_circuit_open_until = _time.time() + _FW_CB_COOLDOWN
        logger.warning(
            "Fireworks circuit breaker OPEN: %d failures, cooldown %ds",
            _fw_consecutive_failures, _FW_CB_COOLDOWN,
        )


async def call_fireworks(
    messages: list[dict],
    max_tokens: int = 60,
    temperature: float = 0.7,
    model: Optional[str] = None,
) -> Optional[dict]:
    """Call Fireworks AI via OpenAI-compatible API.

    Args:
        messages: OpenAI-format messages [{role, content}, ...]
        max_tokens: max output tokens
        temperature: sampling temperature
        model: override model (defaults to FIREWORKS_MODEL env var)

    Returns:
        dict with {content, model, provider, latency_ms, tokens_in, tokens_out}
        or None on failure.
    """
    api_key = os.getenv("FIREWORKS_API_KEY")
    if not api_key:
        logger.debug("FIREWORKS_API_KEY not set, Fireworks AI unavailable")
        return None

    if _circuit_is_open():
        logger.info("Fireworks circuit breaker open, skipping")
        return None

    model = model or FIREWORKS_MODEL
    timeout = float(os.getenv("FIREWORKS_TIMEOUT", "15"))
    start = time.monotonic()

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=FIREWORKS_BASE_URL,
        )

        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            ),
            timeout=timeout,
        )

        content = (response.choices[0].message.content or "").strip()
        latency_ms = int((time.monotonic() - start) * 1000)
        usage = response.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0

        if not content:
            logger.warning("Fireworks returned empty content")
            _record_failure()
            return None

        logger.info(
            "Fireworks OK: model=%s latency=%dms tokens_in=%d tokens_out=%d len=%d",
            model, latency_ms, tokens_in, tokens_out, len(content),
        )
        _record_success()
        return {
            "content": content,
            "model": model,
            "provider": "fireworks",
            "latency_ms": latency_ms,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }

    except asyncio.TimeoutError:
        logger.warning("Fireworks timeout after %.0fs", timeout)
        _record_failure()
        return None
    except Exception as e:
        logger.error("Fireworks error: %s", e)
        _record_failure()
        return None
