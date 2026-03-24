"""DeepInfra provider for OpenAI-compatible model inference.

Supports any model hosted on DeepInfra (Qwen3-32B, Llama, Mistral, etc.)
via their OpenAI-compatible endpoint.

Env vars:
  DEEPINFRA_API_KEY  — API key for DeepInfra
  DEEPINFRA_MODEL    — model ID (e.g. "Qwen/Qwen3-32B", or fine-tuned endpoint)
"""

import asyncio
import logging
import os
import time
import time as _time
from typing import Optional

logger = logging.getLogger(__name__)

DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/openai"
DEEPINFRA_MODEL = os.getenv("DEEPINFRA_MODEL", "Qwen/Qwen3-32B")

# Circuit breaker — same pattern as Gemini
_deepinfra_consecutive_failures = 0
_deepinfra_circuit_open_until = 0.0
_DI_CB_THRESHOLD = int(os.getenv("DEEPINFRA_CB_THRESHOLD", "3"))
_DI_CB_COOLDOWN = int(os.getenv("DEEPINFRA_CB_COOLDOWN", "120"))


def _circuit_is_open() -> bool:
    if _deepinfra_consecutive_failures >= _DI_CB_THRESHOLD:
        if _time.time() < _deepinfra_circuit_open_until:
            return True
    return False


def _record_success():
    global _deepinfra_consecutive_failures, _deepinfra_circuit_open_until
    _deepinfra_consecutive_failures = 0
    _deepinfra_circuit_open_until = 0.0


def _record_failure():
    global _deepinfra_consecutive_failures, _deepinfra_circuit_open_until
    _deepinfra_consecutive_failures += 1
    if _deepinfra_consecutive_failures >= _DI_CB_THRESHOLD:
        _deepinfra_circuit_open_until = _time.time() + _DI_CB_COOLDOWN
        logger.warning(
            "DeepInfra circuit breaker OPEN: %d failures, cooldown %ds",
            _deepinfra_consecutive_failures, _DI_CB_COOLDOWN,
        )


async def call_deepinfra(
    messages: list[dict],
    max_tokens: int = 60,
    temperature: float = 0.7,
    model: Optional[str] = None,
) -> Optional[dict]:
    """Call DeepInfra via OpenAI-compatible API.

    Args:
        messages: OpenAI-format messages [{role, content}, ...]
        max_tokens: max output tokens
        temperature: sampling temperature
        model: override model (defaults to DEEPINFRA_MODEL env var)

    Returns:
        dict with {content, model, provider, latency_ms, tokens_in, tokens_out}
        or None on failure.
    """
    api_key = os.getenv("DEEPINFRA_API_KEY")
    if not api_key:
        logger.debug("DEEPINFRA_API_KEY not set, DeepInfra unavailable")
        return None

    if _circuit_is_open():
        logger.info("DeepInfra circuit breaker open, skipping")
        return None

    model = model or DEEPINFRA_MODEL
    timeout = float(os.getenv("DEEPINFRA_TIMEOUT", "8"))
    start = time.monotonic()

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=DEEPINFRA_BASE_URL,
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
            logger.warning("DeepInfra returned empty content")
            _record_failure()
            return None

        logger.info(
            "DeepInfra OK: model=%s latency=%dms tokens_in=%d tokens_out=%d len=%d",
            model, latency_ms, tokens_in, tokens_out, len(content),
        )
        _record_success()
        return {
            "content": content,
            "model": model,
            "provider": "deepinfra",
            "latency_ms": latency_ms,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }

    except asyncio.TimeoutError:
        logger.warning("DeepInfra timeout after %.0fs", timeout)
        _record_failure()
        return None
    except Exception as e:
        logger.error("DeepInfra error: %s", e)
        _record_failure()
        return None
