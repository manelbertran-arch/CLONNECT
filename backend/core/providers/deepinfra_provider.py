"""DeepInfra provider for OpenAI-compatible model inference.

Supports any model hosted on DeepInfra (Qwen3-32B, Llama, Mistral, etc.)
via their OpenAI-compatible endpoint.

Env vars:
  DEEPINFRA_API_KEY             — API key for DeepInfra
  DEEPINFRA_MODEL               — model ID (e.g. "Qwen/Qwen3-32B", or fine-tuned endpoint)
  DEEPINFRA_CB_COOLDOWN         — circuit breaker cooldown in seconds (default: 30)
  DEEPINFRA_CB_THRESHOLD        — consecutive failures before opening (default: 3)
  DEEPINFRA_FALLBACK_PROVIDER   — provider to use when DeepInfra fails (e.g. "openrouter")
"""

import asyncio
import logging
import os
import re
import time
import time as _time
from typing import Optional

logger = logging.getLogger(__name__)


def strip_thinking_artifacts(text: str) -> str:
    """Strip LLM reasoning tokens/artifacts from any provider output.

    Handles all known patterns produced by thinking models:
      - Full <think>…</think> blocks (Qwen3 extended-thinking mode)
      - Empty <think></think> blocks (Qwen3 /no_think residue)
      - Orphan </think> closing tags (model leaked closing tag without thinking)
      - Orphan <think> opening tags
      - Trailing /no_think instruction leaked into the response text

    Designed to be universal: safe to call on output from Gemini, GPT-4o,
    Qwen3, or any future model that may emit thinking tokens.
    """
    # 1. Full blocks with content (re.DOTALL so '.' matches newlines)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # 2. Orphan </think> anywhere in the string
    text = re.sub(r"</think>", "", text)
    # 3. Orphan <think> (no matching close tag)
    text = re.sub(r"<think>", "", text)
    # 4. Trailing /no_think instruction leaked to output (with optional whitespace)
    text = re.sub(r"\s*/no_think\s*$", "", text)
    return text.strip()


DEEPINFRA_BASE_URL = os.getenv("DEEPINFRA_BASE_URL", "https://api.deepinfra.com/v1/openai")
DEEPINFRA_MODEL = os.getenv("DEEPINFRA_MODEL", "Qwen/Qwen3-32B")

# Circuit breaker — same pattern as Gemini
_deepinfra_consecutive_failures = 0
_deepinfra_circuit_open_until = 0.0
_DI_CB_THRESHOLD = int(os.getenv("DEEPINFRA_CB_THRESHOLD", "3"))
_DI_CB_COOLDOWN = int(os.getenv("DEEPINFRA_CB_COOLDOWN", "30"))  # reduced from 120 — fallback covers the gap


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


async def _try_openrouter_fallback(
    messages: list,
    max_tokens: Optional[int],
    temperature: Optional[float],
    model: Optional[str],
) -> Optional[dict]:
    """Call OpenRouter as transparent fallback when DeepInfra is unavailable.

    Activated only when DEEPINFRA_FALLBACK_PROVIDER=openrouter AND OPENROUTER_API_KEY is set.
    Set DEEPINFRA_FALLBACK_MODEL to override the model slug when the DeepInfra slug is not
    valid on OpenRouter (e.g. "Qwen/Qwen3-32B" differs from OpenRouter's "qwen/qwen3-32b").
    Returns None if conditions are unmet or if the fallback also fails.
    """
    _fallback_provider = os.getenv("DEEPINFRA_FALLBACK_PROVIDER", "").lower()
    if _fallback_provider != "openrouter":
        return None
    if not os.getenv("OPENROUTER_API_KEY"):
        logger.warning("[DI-FALLBACK] OPENROUTER_API_KEY not set — fallback inactive")
        return None
    # Allow model slug override when DeepInfra and OpenRouter use different formats
    _fallback_model = os.getenv("DEEPINFRA_FALLBACK_MODEL") or model
    try:
        from core.providers.openrouter_provider import call_openrouter
        logger.warning(
            "[DI-FALLBACK] DeepInfra unavailable — falling back to OpenRouter model=%s",
            _fallback_model,
        )
        result = await call_openrouter(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            model=_fallback_model,
        )
        if result is None:
            logger.warning(
                "[DI-FALLBACK] OpenRouter also returned None — both providers unavailable"
            )
            return None
        return {**result, "provider": "openrouter-fallback"}
    except Exception as e:
        logger.error("[DI-FALLBACK] OpenRouter fallback also failed: %s", e)
        return None


async def call_deepinfra(
    messages: list[dict],
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
    model: Optional[str] = None,
    frequency_penalty: Optional[float] = None,
    model_id: Optional[str] = None,
) -> Optional[dict]:
    """Call DeepInfra via OpenAI-compatible API.

    Args:
        messages: OpenAI-format messages [{role, content}, ...]
        max_tokens: max output tokens (None → config or 400 legacy default)
        temperature: sampling temperature (None → config or 0.7 legacy default)
        model: override model string (defaults to DEEPINFRA_MODEL env var)
        frequency_penalty: penalize repeated tokens (None → config or env var)
        model_id: optional config file name (e.g. "qwen3_14b") to load
                  sampling/runtime/provider/thinking from
                  config/models/{model_id}.json. Caller-supplied
                  temperature/max_tokens/frequency_penalty still win.

    Returns:
        dict with {content, model, provider, latency_ms, tokens_in, tokens_out}
        or None on failure. When DEEPINFRA_FALLBACK_PROVIDER=openrouter, failed
        requests are transparently retried via OpenRouter before returning None.
    """
    # ── Config-driven path ──
    cfg_sampling: dict = {}
    cfg_runtime: dict = {}
    cfg_provider: dict = {}
    cfg_thinking: dict = {}
    cfg_chat_template: dict = {}
    cfg_loaded = False
    if model_id is not None:
        try:
            from core.providers.model_config import (
                load_model_config,
                get_provider_info,
                get_sampling,
                get_runtime,
                get_thinking,
                get_chat_template,
            )
            cfg = load_model_config(model_id)
            cfg_provider = get_provider_info(cfg)
            cfg_sampling = get_sampling(cfg)
            cfg_runtime = get_runtime(cfg)
            cfg_thinking = get_thinking(cfg)
            cfg_chat_template = get_chat_template(cfg)
            cfg_loaded = True
            logger.info(
                "[DeepInfra] using config: %s, model_string=%s, temp=%s, max_tokens=%s, no_think_suffix=%r",
                model_id,
                cfg_provider.get("model_string"),
                cfg_sampling.get("temperature"),
                cfg_sampling.get("max_tokens"),
                cfg_thinking.get("no_think_suffix", ""),
            )
        except FileNotFoundError as e:
            logger.error("[DeepInfra] config load failed for %s: %s", model_id, e)
            return None

    api_key_env = cfg_provider.get("api_key_env") or "DEEPINFRA_API_KEY"
    api_key = os.getenv(api_key_env)
    if not api_key:
        logger.debug("%s not set, DeepInfra unavailable", api_key_env)
        return None

    # Resolve model and sampling params BEFORE the circuit check so the
    # fallback path has fully-resolved values to pass to OpenRouter.
    if model is None:
        if cfg_provider.get("model_string"):
            model = cfg_provider["model_string"]
        else:
            model = DEEPINFRA_MODEL

    _temperature = temperature
    if _temperature is None:
        _temperature = cfg_sampling.get("temperature", 0.7) if cfg_sampling else 0.7
    _max_tokens = max_tokens
    if _max_tokens is None:
        _max_tokens = cfg_sampling.get("max_tokens", 400) if cfg_sampling else 400

    if cfg_runtime:
        timeout = float(cfg_runtime.get("timeout_seconds", 8))
    else:
        timeout = float(os.getenv("DEEPINFRA_TIMEOUT", "30"))  # 30s default — Gemma-4-31B needs 30-40s

    base_url = cfg_provider.get("base_url") or DEEPINFRA_BASE_URL

    if _circuit_is_open():
        logger.info("DeepInfra circuit breaker open, skipping")
        return await _try_openrouter_fallback(messages, _max_tokens, _temperature, model)

    start = time.monotonic()

    # /no_think suffix injection.
    # Config-driven path: use cfg_thinking.no_think_suffix (empty string → no injection).
    # Legacy path: keep hardcoded Qwen3 substring detection for backward compat.
    if cfg_loaded:
        no_think_suffix = cfg_thinking.get("no_think_suffix", "") or ""
        if no_think_suffix:
            send_messages = []
            for i, msg in enumerate(messages):
                if i == len(messages) - 1 and msg.get("role") == "user":
                    content = msg["content"].rstrip()
                    if not content.endswith(no_think_suffix):
                        msg = {**msg, "content": content + " " + no_think_suffix}
                send_messages.append(msg)
        else:
            send_messages = messages
    else:
        send_messages = messages
        if "Qwen3" in model or "qwen3" in model.lower():
            send_messages = []
            for i, msg in enumerate(messages):
                if i == len(messages) - 1 and msg.get("role") == "user":
                    content = msg["content"].rstrip()
                    if not content.endswith("/no_think"):
                        msg = {**msg, "content": content + " /no_think"}
                send_messages.append(msg)

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

        # frequency_penalty: caller arg > config > env var > 0.0
        _freq_pen = frequency_penalty
        if _freq_pen is None:
            if cfg_sampling:
                _freq_pen = float(cfg_sampling.get("frequency_penalty", 0.0) or 0.0)
            else:
                _freq_pen = float(os.getenv("DEEPINFRA_FREQUENCY_PENALTY", "0.0"))

        create_kwargs = dict(
            model=model,
            messages=send_messages,
            max_tokens=_max_tokens,
            temperature=_temperature,
        )
        if _freq_pen > 0:
            create_kwargs["frequency_penalty"] = _freq_pen
        # presence_penalty from config (only when > 0)
        if cfg_sampling:
            pp = float(cfg_sampling.get("presence_penalty", 0.0) or 0.0)
            if pp > 0:
                create_kwargs["presence_penalty"] = pp

        response = await asyncio.wait_for(
            client.chat.completions.create(**create_kwargs),
            timeout=timeout,
        )

        content = (response.choices[0].message.content or "").strip()
        # strip_thinking_artifacts is config-controlled. Legacy path always strips
        # (preserves current prod behavior). Config path follows
        # chat_template.strip_thinking_artifacts (default true via qwen3_14b.json).
        if cfg_loaded:
            if cfg_chat_template.get("strip_thinking_artifacts", True):
                content = strip_thinking_artifacts(content)
        else:
            content = strip_thinking_artifacts(content)
        finish_reason = (response.choices[0].finish_reason or "").lower()
        latency_ms = int((time.monotonic() - start) * 1000)
        usage = response.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0

        if not content:
            logger.warning("DeepInfra returned empty content")
            _record_failure()
            return await _try_openrouter_fallback(messages, _max_tokens, _temperature, model)

        logger.info(
            "DeepInfra OK: model=%s latency=%dms tokens_in=%d tokens_out=%d len=%d finish_reason=%s",
            model, latency_ms, tokens_in, tokens_out, len(content), finish_reason,
        )
        _record_success()
        return {
            "content": content,
            "model": model,
            "provider": "deepinfra",
            "latency_ms": latency_ms,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "finish_reason": finish_reason,
        }

    except asyncio.TimeoutError:
        logger.warning("DeepInfra timeout after %.0fs", timeout)
        _record_failure()
        return await _try_openrouter_fallback(messages, _max_tokens, _temperature, model)
    except Exception as e:
        logger.error("DeepInfra error: %s", e)
        _record_failure()
        return await _try_openrouter_fallback(messages, _max_tokens, _temperature, model)
