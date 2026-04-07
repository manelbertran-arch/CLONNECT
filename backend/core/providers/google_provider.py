"""Google AI Studio provider for Gemma 4 and other Google-hosted models.

Uses the google-generativeai SDK. Sampling params, thinking mode, and thought-block
filtering are all driven by the model config JSON — nothing is hardcoded here.

Env vars:
  GOOGLE_API_KEY              — API key for Google AI Studio (required)
  GOOGLE_AI_STUDIO_MODEL      — override the API model string from config
  GOOGLE_AI_STUDIO_MODEL_ID   — config file ID (default: gemma4_26b_a4b)
  GOOGLE_AI_CB_THRESHOLD      — circuit breaker failure threshold (default: 3)
  GOOGLE_AI_CB_COOLDOWN       — circuit breaker cooldown in seconds (default: 120)
  GOOGLE_AI_MAX_RETRIES       — max retries for rate limits (default: 3)
  GOOGLE_AI_TIMEOUT           — per-request timeout in seconds (default: 15)
"""

import asyncio
import logging
import os
import pathlib
import re
import time
from typing import Optional

from core.providers.model_config import load_model_config as _load_model_config

logger = logging.getLogger(__name__)

_BACKEND_ROOT = pathlib.Path(__file__).parent.parent.parent

# ---------------------------------------------------------------------------
# Circuit breaker — same pattern as deepinfra_provider
# ---------------------------------------------------------------------------
_google_consecutive_failures = 0
_google_circuit_open_until = 0.0
_GOOGLE_CB_THRESHOLD = int(os.getenv("GOOGLE_AI_CB_THRESHOLD", "3"))
_GOOGLE_CB_COOLDOWN = int(os.getenv("GOOGLE_AI_CB_COOLDOWN", "120"))


def _circuit_is_open() -> bool:
    if _google_consecutive_failures >= _GOOGLE_CB_THRESHOLD:
        if time.time() < _google_circuit_open_until:
            return True
    return False


def _record_success() -> None:
    global _google_consecutive_failures, _google_circuit_open_until
    _google_consecutive_failures = 0
    _google_circuit_open_until = 0.0


def _record_failure() -> None:
    global _google_consecutive_failures, _google_circuit_open_until
    _google_consecutive_failures += 1
    if _google_consecutive_failures >= _GOOGLE_CB_THRESHOLD:
        _google_circuit_open_until = time.time() + _GOOGLE_CB_COOLDOWN
        logger.warning(
            "GoogleProvider circuit breaker OPEN: %d failures, cooldown %ds",
            _google_consecutive_failures,
            _GOOGLE_CB_COOLDOWN,
        )


# ---------------------------------------------------------------------------
# Config loading — delegated to core.providers.model_config (shared loader)
# ---------------------------------------------------------------------------


def validate_template_file(model_id: str) -> None:
    """Raise FileNotFoundError if the model's template_file does not exist.

    Call this at startup / before first request. Fatal — no recovery.
    """
    cfg = _load_model_config(model_id)
    template_rel = cfg.get("system_prompt", {}).get("template_file")
    if not template_rel:
        return
    template_path = _BACKEND_ROOT / template_rel
    if not template_path.exists():
        raise FileNotFoundError(
            f"[GoogleProvider] FATAL: template_file '{template_rel}' not found "
            f"for model '{model_id}'. Expected at: {template_path}"
        )


# ---------------------------------------------------------------------------
# Thought-block filtering — Gemma 4 specific
# ---------------------------------------------------------------------------

def _strip_gemma_thought_blocks(text: str) -> str:
    """Strip Gemma 4 thought blocks and reasoning bullets.

    Handles:
      <|channel>thought ... <channel|>      — channel thinking blocks
      <|think|> ... <|/think|>              — think blocks
      Orphan <|think|> tokens
      Bullet-point reasoning (31B specific) — lines starting with * or known prefixes
    """
    # Full channel blocks
    text = re.sub(r"<\|channel>thought.*?<channel\|>", "", text, flags=re.DOTALL)
    # Full think blocks
    text = re.sub(r"<\|think\|>.*?<\|/think\|>", "", text, flags=re.DOTALL)
    # Orphan opening token
    text = re.sub(r"<\|think\|>", "", text)
    text = text.strip()

    # Bullet-point reasoning — 31B emits structured reasoning as *-prefixed lines
    # even with thinking=false. Strip any line that is clearly reasoning, not response.
    _REASONING_PREFIXES = (
        "* ", "*\t",
        "User's instruction", "User Input", "User says", "User (", "Lead (",
        "Analysis:", "Instructions:", "Constraint:", "Role:", "Context:",
        "Current date", "Note:", "Task:", "Goal:", "Step ", "Summary:",
        "---",
    )
    lines = text.split("\n")
    filtered = [l for l in lines
                if not any(l.strip().startswith(p) for p in _REASONING_PREFIXES)]
    result = "\n".join(filtered).strip()

    # If still verbose after bullet removal, take the last short standalone line —
    # that is the actual response the model settled on.
    if len(result) > 150:
        candidates = [
            l.strip() for l in result.split("\n")
            if l.strip() and not l.startswith((" ", "\t"))
        ]
        if candidates:
            result = candidates[-1]

    return result.strip()


# ---------------------------------------------------------------------------
# Main provider function
# ---------------------------------------------------------------------------

async def call_google_ai(
    messages: list[dict],
    model_id: str = "gemma4_26b_a4b",
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> Optional[dict]:
    """Call Google AI Studio via google-generativeai SDK.

    Sampling params come from the model config JSON unless explicitly overridden.
    Thinking mode is controlled by config.thinking.enabled.
    Thought blocks are filtered if config.chat_template.filter_thought_blocks=true.

    Args:
        messages:    OpenAI-format messages [{role, content}, ...]
        model_id:    Config file ID (resolves config/models/{model_id}.json)
        max_tokens:  Override config sampling.max_tokens
        temperature: Override config sampling.temperature

    Returns:
        dict {content, model, provider, latency_ms, tokens_in, tokens_out}
        or None on failure.
    """
    if _circuit_is_open():
        logger.info("GoogleProvider circuit breaker open, skipping")
        return None

    # Load config (cached)
    try:
        cfg = _load_model_config(model_id)
    except FileNotFoundError as e:
        logger.error("%s", e)
        return None

    # Provider info
    raw_provider = cfg.get("provider", {})
    if isinstance(raw_provider, dict):
        api_key_env = raw_provider.get("api_key_env", "GOOGLE_API_KEY")
        cfg_model_string = raw_provider.get("model_string", model_id)
    else:
        api_key_env = "GOOGLE_API_KEY"
        cfg_model_string = cfg.get("model_name", model_id)

    api_key = os.getenv(api_key_env)
    if not api_key:
        logger.error("GoogleProvider: %s not set", api_key_env)
        return None

    # Model string: env override > config
    model_string = os.getenv("GOOGLE_AI_STUDIO_MODEL") or cfg_model_string

    # Sampling — config values, optionally overridden by caller
    sampling = cfg.get("sampling", {})
    _max_tokens = max_tokens if max_tokens is not None else sampling.get("max_tokens", 300)
    _temperature = temperature if temperature is not None else sampling.get("temperature", 1.0)

    # Doc D metadata header: "#!max_tokens=N\n" prepended by build_from_template().
    # Parse it here (before building messages) and strip it so the model never sees it.
    # Only applies when caller did not explicitly pass max_tokens.
    import re as _re
    _doc_d_max_tokens: int | None = None
    _top_p = sampling.get("top_p", 0.95)
    _top_k = sampling.get("top_k", 64)
    _stop_seqs = sampling.get("stop_sequences") or []

    # Thinking mode — per model config, never global
    thinking_cfg = cfg.get("thinking", {})
    thinking_enabled = thinking_cfg.get("enabled", False)

    # Thought-block filtering
    filter_thought_blocks = cfg.get("chat_template", {}).get("filter_thought_blocks", False)

    # Check SDK availability early
    try:
        import google.generativeai as genai
    except ImportError:
        logger.error(
            "GoogleProvider: google-generativeai not installed. "
            "Run: pip install google-generativeai"
        )
        return None

    # Build system prompt and history from OpenAI-format messages
    system_prompt = ""
    history: list[dict] = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            system_prompt = content
        elif role == "user":
            history.append({"role": "user", "parts": [content]})
        elif role == "assistant":
            history.append({"role": "model", "parts": [content]})

    # Parse and strip Doc D metadata header "#!max_tokens=N" from system_prompt.
    # build_from_template() embeds this so the provider can apply creator-derived
    # max_output_tokens without a separate API call. Strip before sending to model.
    if system_prompt:
        _meta = _re.match(r'^#!max_tokens=(\d+)\n', system_prompt)
        if _meta:
            _doc_d_max_tokens = int(_meta.group(1))
            system_prompt = system_prompt[_meta.end():]
            # Only apply if caller did not already pass an explicit override
            if max_tokens is None:
                _max_tokens = _doc_d_max_tokens
                logger.debug(
                    "GoogleProvider: using Doc D suggested_max_tokens=%d for %s",
                    _max_tokens, model_id,
                )

    if not history:
        logger.error("GoogleProvider: no user message in messages")
        return None

    # system_prompt_mode — controls how Doc D is passed to the model.
    # "system_instruction" (default): passed as GenerativeModel(system_instruction=...)
    # "user_message": prepended to first user turn; system_instruction left empty.
    #   Use for models that echo system_instruction back (e.g. gemma-4-31b-it dense).
    _sp_mode = cfg.get("system_prompt", {}).get("system_prompt_mode", "system_instruction")
    if _sp_mode == "user_message" and system_prompt:
        first_user_text = history[0]["parts"][0]
        history[0] = {"role": "user", "parts": [f"{system_prompt}\n\n---\n{first_user_text}"]}
        logger.debug("GoogleProvider: system_prompt_mode=user_message — prepended to first user turn")
        system_prompt = ""

    # Thinking mode: prepend think token to system prompt only if enabled
    if thinking_enabled:
        think_token = thinking_cfg.get("token", "<|think|>")
        system_prompt = f"{think_token}\n{system_prompt}" if system_prompt else think_token

    generation_config: dict = {
        "temperature": _temperature,
        "top_p": _top_p,
        "top_k": _top_k,
        "max_output_tokens": _max_tokens,
    }
    if _stop_seqs:
        generation_config["stop_sequences"] = _stop_seqs

    max_retries = int(os.getenv("GOOGLE_AI_MAX_RETRIES", "3"))

    for attempt in range(max_retries):
        start = time.monotonic()
        try:
            genai.configure(api_key=api_key)

            gen_model = genai.GenerativeModel(
                model_name=model_string,
                system_instruction=system_prompt if system_prompt else None,
            )

            if len(history) > 1:
                # Multi-turn: start chat with all but the last message, then send last
                chat = gen_model.start_chat(history=history[:-1])
                last_content = history[-1]["parts"][0]
                response = await asyncio.to_thread(
                    chat.send_message,
                    last_content,
                    generation_config=generation_config,
                )
            else:
                user_text = history[0]["parts"][0]
                response = await asyncio.to_thread(
                    gen_model.generate_content,
                    user_text,
                    generation_config=generation_config,
                )

            latency_ms = int((time.monotonic() - start) * 1000)

            if not response.text:
                logger.warning(
                    "GoogleProvider: empty response (attempt %d/%d)", attempt + 1, max_retries
                )
                await asyncio.sleep(1)
                continue

            content = response.text.strip()

            if filter_thought_blocks:
                content = _strip_gemma_thought_blocks(content)

            if not content:
                logger.warning(
                    "GoogleProvider: content empty after filtering (attempt %d/%d)",
                    attempt + 1,
                    max_retries,
                )
                await asyncio.sleep(1)
                continue

            tokens_in = 0
            tokens_out = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                tokens_in = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                tokens_out = (
                    getattr(response.usage_metadata, "candidates_token_count", 0) or 0
                )

            logger.info(
                "GoogleProvider OK: model=%s latency=%dms tokens_in=%d tokens_out=%d len=%d",
                model_string, latency_ms, tokens_in, tokens_out, len(content),
            )
            _record_success()
            return {
                "content": content,
                "model": model_string,
                "provider": "google_ai_studio",
                "latency_ms": latency_ms,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
            }

        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            err_str = str(e)

            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                wait = min(2 ** (attempt + 1), 30)
                logger.warning(
                    "GoogleProvider rate limited (429), backing off %ds (attempt %d/%d)",
                    wait, attempt + 1, max_retries,
                )
                await asyncio.sleep(wait)
                continue

            if "401" in err_str or "API_KEY_INVALID" in err_str or "UNAUTHENTICATED" in err_str:
                logger.error(
                    "GoogleProvider: authentication failed — check %s (401)", api_key_env
                )
                _record_failure()
                return None  # Fatal: retrying won't help

            if "404" in err_str or "NOT_FOUND" in err_str:
                logger.error(
                    "GoogleProvider: model not found (404) — model_string='%s' may be wrong",
                    model_string,
                )
                _record_failure()
                return None  # Fatal: retrying won't help

            logger.error(
                "GoogleProvider error (attempt %d/%d): %s", attempt + 1, max_retries, e
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(1)

    _record_failure()
    return None
