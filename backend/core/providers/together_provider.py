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
    max_tokens: int = 60,
    temperature: float = 0.7,
    model: Optional[str] = None,
) -> Optional[dict]:
    """Call Together AI via OpenAI-compatible API.

    Args:
        messages: OpenAI-format messages [{role, content}, ...]
        max_tokens: max output tokens
        temperature: sampling temperature
        model: override model (defaults to TOGETHER_MODEL env var)

    Returns:
        dict with {content, model, provider, latency_ms, tokens_in, tokens_out}
        or None on failure.
    """
    api_key = os.getenv("TOGETHER_API_KEY")
    if not api_key:
        logger.debug("TOGETHER_API_KEY not set, Together AI unavailable")
        return None

    if _circuit_is_open():
        logger.info("Together circuit breaker open, skipping")
        return None

    model = model or TOGETHER_MODEL
    timeout = float(os.getenv("TOGETHER_TIMEOUT", "15"))
    start = time.monotonic()

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=TOGETHER_BASE_URL,
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
            logger.warning("Together returned empty content")
            _record_failure()
            return None

        logger.info(
            "Together OK: model=%s latency=%dms tokens_in=%d tokens_out=%d len=%d",
            model, latency_ms, tokens_in, tokens_out, len(content),
        )
        _record_success()
        return {
            "content": content,
            "model": model,
            "provider": "together",
            "latency_ms": latency_ms,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }

    except asyncio.TimeoutError:
        logger.warning("Together timeout after %.0fs", timeout)
        _record_failure()
        return None
    except Exception as e:
        logger.error("Together error: %s", e)
        _record_failure()
        return None
