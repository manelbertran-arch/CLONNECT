"""Google Gemini provider for Flash-Lite model inference.

Production DM pipeline:
  PRIMARY:  Gemini Flash-Lite (model from core.config.llm_models.GEMINI_PRIMARY_MODEL)
  FALLBACK: GPT-4o-mini (via OpenAI API)
  Nothing else in the active path.

Entry point: generate_dm_response() — called from dm_agent_v2.py
"""

import asyncio
import logging
import os
import time
import time as _time
from typing import Optional

import httpx

from core.config.llm_models import GEMINI_PRIMARY_MODEL, LLM_PRIMARY_PROVIDER, safe_model

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_GEMINI_MODEL = GEMINI_PRIMARY_MODEL  # kept for backward compat references

# Circuit breaker: skip Gemini for CIRCUIT_BREAKER_COOLDOWN seconds after
# CIRCUIT_BREAKER_THRESHOLD consecutive failures.
_gemini_consecutive_failures = 0
_gemini_circuit_open_until = 0.0
CIRCUIT_BREAKER_THRESHOLD = int(os.getenv("GEMINI_CB_THRESHOLD", "2"))
CIRCUIT_BREAKER_COOLDOWN = int(os.getenv("GEMINI_CB_COOLDOWN", "120"))  # 2 minutes


def _gemini_circuit_is_open() -> bool:
    """Check if circuit breaker is open (Gemini should be skipped)."""
    if _gemini_consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
        if _time.time() < _gemini_circuit_open_until:
            return True
        # Cooldown expired — allow one probe request
    return False


def _gemini_record_success():
    """Record a successful Gemini call — reset circuit breaker."""
    global _gemini_consecutive_failures, _gemini_circuit_open_until
    _gemini_consecutive_failures = 0
    _gemini_circuit_open_until = 0.0


def _gemini_record_failure():
    """Record a Gemini failure — potentially open circuit."""
    global _gemini_consecutive_failures, _gemini_circuit_open_until
    _gemini_consecutive_failures += 1
    if _gemini_consecutive_failures >= CIRCUIT_BREAKER_THRESHOLD:
        _gemini_circuit_open_until = _time.time() + CIRCUIT_BREAKER_COOLDOWN
        logger.warning(
            "Circuit breaker OPEN: Gemini failed %d times, routing to GPT-4o-mini for %ds",
            _gemini_consecutive_failures, CIRCUIT_BREAKER_COOLDOWN
        )


def _log_llm_usage(
    provider: str,
    model: str,
    call_type: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
) -> None:
    """Fire-and-forget: persist one LLM call to llm_usage_log. Never raises."""
    try:
        from api.database import SessionLocal
        from api.models.learning import LLMUsageLog

        s = SessionLocal()
        try:
            s.add(LLMUsageLog(
                provider=provider,
                model=model,
                call_type=call_type,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
            ))
            s.commit()
        except Exception:
            s.rollback()
        finally:
            s.close()
    except Exception:
        pass  # Never block generation for logging


async def _async_log_usage(result: dict, call_type: str) -> None:
    """Async wrapper around _log_llm_usage for use with asyncio.create_task."""
    try:
        await asyncio.to_thread(
            _log_llm_usage,
            result.get("provider", "unknown"),
            result.get("model", "unknown"),
            call_type,
            result.get("tokens_in", 0),
            result.get("tokens_out", 0),
            result.get("latency_ms", 0),
        )
    except Exception:
        pass


async def _call_gemini(
    model: str,
    api_key: str,
    system_prompt: str,
    user_message: str,
    max_tokens: int,
    temperature: float,
    max_retries: int = 2,
    contents: Optional[list] = None,
    model_id: Optional[str] = None,
) -> Optional[str]:
    """Call Google Gemini API with fast retry (fail fast for interactive use).

    If `contents` is provided (multi-turn format), it takes priority over `user_message`.
    `contents` should be a list of {"role": "user"|"model", "parts": [{"text": "..."}]}.

    When `model_id` is provided, frequency_penalty / presence_penalty / safety
    settings are loaded from config/models/{model_id}.json. Otherwise, the
    legacy GEMINI_*_PENALTY env vars and BLOCK_ONLY_HIGH safety defaults apply.
    """
    url = f"{GEMINI_API_URL}/{model}:generateContent?key={api_key}"

    # ── Optional config-driven sampling/safety ──
    cfg_sampling: dict = {}
    cfg_safety: dict = {}
    if model_id is not None:
        try:
            from core.providers.model_config import (
                load_model_config,
                get_sampling,
                get_safety,
            )
            cfg = load_model_config(model_id)
            cfg_sampling = get_sampling(cfg)
            cfg_safety = get_safety(cfg)
        except FileNotFoundError as e:
            logger.error("[Gemini] config load failed for %s: %s", model_id, e)
            # Fall through to legacy defaults below

    if cfg_sampling:
        _presence_penalty = float(cfg_sampling.get("presence_penalty", 0.0) or 0.0)
        _frequency_penalty = float(cfg_sampling.get("frequency_penalty", 0.0) or 0.0)
    else:
        _presence_penalty = float(os.getenv("GEMINI_PRESENCE_PENALTY", "0.0"))
        _frequency_penalty = float(os.getenv("GEMINI_FREQUENCY_PENALTY", "0.0"))

    if cfg_safety:
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": cfg_safety["harassment"]},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": cfg_safety["hate_speech"]},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": cfg_safety["sexually_explicit"]},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": cfg_safety["dangerous_content"]},
        ]
    else:
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
        ]

    payload = {
        "contents": contents if contents is not None else [{"parts": [{"text": user_message}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
            # Anti-loop penalties: disabled by default (0.0) because presence_penalty
            # penalizes legitimate repetition in Iris's style ("ja ja ja", "amor amor").
            # Enable carefully via env vars only after style-specific calibration.
            "presencePenalty": _presence_penalty,
            "frequencyPenalty": _frequency_penalty,
        },
        # Relax safety filters: fitness/dance coaching uses emotional/physical language
        # that can trigger Gemini's default thresholds. BLOCK_ONLY_HIGH still prevents
        # genuinely harmful content while allowing "amor", "cariño", exercise terminology.
        "safetySettings": safety_settings,
    }

    for attempt in range(max_retries):
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload)
                latency_ms = int((time.monotonic() - start) * 1000)

                if resp.status_code == 429:
                    wait = 2 ** attempt + 1
                    logger.warning(
                        "Gemini rate limited, waiting %ds (attempt %d/%d)",
                        wait, attempt + 1, max_retries,
                    )
                    await asyncio.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()

                # Safety filter / empty candidates: Gemini returns 200 but
                # candidates is empty or candidate has no content.
                candidates = data.get("candidates", [])
                if not candidates:
                    reason = data.get("promptFeedback", {}).get("blockReason", "unknown")
                    logger.warning(
                        "Gemini no candidates (blockReason=%s), attempt %d/%d",
                        reason, attempt + 1, max_retries,
                    )
                    await asyncio.sleep(1)
                    continue

                candidate = candidates[0]
                finish_reason = candidate.get("finishReason", "")
                if finish_reason == "SAFETY" or "content" not in candidate:
                    safety_ratings = candidate.get("safetyRatings", [])
                    logger.warning(
                        "Gemini safety filter (finishReason=%s, ratings=%s), attempt %d/%d",
                        finish_reason, safety_ratings, attempt + 1, max_retries,
                    )
                    await asyncio.sleep(1)
                    continue

                content = candidate["content"]["parts"][0]["text"].strip()
                usage = data.get("usageMetadata", {})
                tokens_in = usage.get("promptTokenCount", 0)
                tokens_out = usage.get("candidatesTokenCount", 0)

                logger.info(
                    "Gemini OK: model=%s latency=%dms tokens_in=%d tokens_out=%d len=%d",
                    model, latency_ms, tokens_in, tokens_out, len(content),
                )
                return {
                    "content": content,
                    "model": model,
                    "provider": "gemini",
                    "latency_ms": latency_ms,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                }

        except httpx.TimeoutException:
            logger.warning(
                "Gemini timeout (attempt %d/%d)", attempt + 1, max_retries,
            )
            await asyncio.sleep(1)
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429:
                wait = min(2, 2 ** attempt + 1)  # Cap at 2s for interactive use
                await asyncio.sleep(wait)
                continue
            if status == 503:
                logger.warning(
                    "Gemini 503 Service Unavailable, retrying in 1s (attempt %d/%d)",
                    attempt + 1, max_retries,
                )
                await asyncio.sleep(1)  # Fixed 1s — don't escalate for interactive copilot
                continue
            logger.error("Gemini HTTP error: %s", e)
            return None
        except Exception as e:
            logger.error("Gemini error: %s", e)
            return None

    return None


async def generate_response_gemini(
    messages: list[dict],
    max_tokens: int = 60,
    temperature: float = 0.7,
    model_id: Optional[str] = None,
) -> Optional[str]:
    """Call Gemini Flash-Lite. Accepts OpenAI-format messages for compatibility.

    Converts OpenAI-format multi-turn messages to Gemini's contents format,
    supporting full conversation history for better context utilization.

    When `model_id` is provided, the per-model JSON config drives provider
    selection (api_key_env, model_string) and Gemini sampling/safety.
    """
    # ── Optional config-driven provider info ──
    cfg_api_key_env = "GOOGLE_API_KEY"
    cfg_model_string: Optional[str] = None
    if model_id is not None:
        try:
            from core.providers.model_config import load_model_config, get_provider_info
            cfg = load_model_config(model_id)
            prov = get_provider_info(cfg)
            cfg_api_key_env = prov.get("api_key_env") or "GOOGLE_API_KEY"
            cfg_model_string = prov.get("model_string") or None
        except FileNotFoundError as e:
            logger.error("[Gemini] config load failed for %s: %s", model_id, e)

    api_key = os.getenv(cfg_api_key_env)
    if not api_key:
        logger.error("%s not set", cfg_api_key_env)
        return None

    if cfg_model_string:
        model = safe_model(cfg_model_string)
    else:
        model = safe_model(os.getenv("GEMINI_MODEL", GEMINI_PRIMARY_MODEL))

    # Build system prompt and multi-turn contents from OpenAI-format messages.
    # Gemini uses "model" for assistant role; content must alternate user/model.
    system_prompt = ""
    contents = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "system":
            system_prompt = content
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": content}]})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": content}]})

    if not contents:
        logger.error("Gemini: no user message found in messages")
        return None

    result = await _call_gemini(
        model, api_key, system_prompt, "",
        max_tokens, temperature, contents=contents,
        model_id=model_id,
    )
    return result  # dict or None


async def generate_simple(
    prompt: str,
    system_prompt: str = "",
    max_tokens: int = 1024,
    temperature: float = 0.2,
) -> Optional[str]:
    """Simple text generation for non-DM uses (audio processing, tools).

    Returns raw text string or None. Gemini primary → GPT-4o-mini fallback.
    """
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    # 1. Try alternative provider if configured as primary
    if LLM_PRIMARY_PROVIDER == "google_ai_studio":
        result = await _try_google_ai(messages, "background")
        if result and result.get("content"):
            return result["content"]
    elif LLM_PRIMARY_PROVIDER == "together":
        result = await _try_together(messages, max_tokens, temperature, "background")
        if result and result.get("content"):
            return result["content"]
    elif LLM_PRIMARY_PROVIDER == "deepinfra":
        result = await _try_deepinfra(messages, max_tokens, temperature, "background")
        if result and result.get("content"):
            return result["content"]
    elif LLM_PRIMARY_PROVIDER == "openrouter":
        result = await _try_openrouter(messages, max_tokens, temperature, "background")
        if result and result.get("content"):
            return result["content"]

    # 2. Try Gemini (skip if circuit is open)
    if _gemini_circuit_is_open():
        logger.info("generate_simple: circuit breaker open, skipping Gemini")
    else:
        api_key = os.getenv("GOOGLE_API_KEY")
        if api_key:
            model = safe_model(os.getenv("GEMINI_MODEL", GEMINI_PRIMARY_MODEL))
            try:
                result = await asyncio.wait_for(
                    _call_gemini(model, api_key, system_prompt, prompt, max_tokens, temperature),
                    timeout=float(os.getenv("LLM_PRIMARY_TIMEOUT", "5")),
                )
                if result and result.get("content"):
                    _gemini_record_success()
                    asyncio.create_task(_async_log_usage(result, "background"))
                    return result["content"]
                logger.warning("generate_simple: Gemini returned empty, falling back")
                _gemini_record_failure()
            except asyncio.TimeoutError:
                logger.warning("generate_simple: Gemini timeout, falling back")
                _gemini_record_failure()
            except Exception as e:
                logger.warning("generate_simple: Gemini failed: %s, falling back", e)
                _gemini_record_failure()

    # 2. Fallback: GPT-4o-mini — same prompt, no extra guard
    logger.warning("[LLM-FALLBACK] Gemini failed (generate_simple), using OpenAI GPT-4o-mini")
    try:
        result = await _call_openai_mini(messages, max_tokens, temperature)
        if result and result.get("content"):
            asyncio.create_task(_async_log_usage(result, "background"))
            return result["content"]
    except Exception as e:
        logger.error("generate_simple: OpenAI fallback failed: %s", e)

    logger.critical("[LLM-ALL-DOWN] No LLM provider available (generate_simple)")
    return None


# =============================================================================
# GPT-4o-mini fallback (used only when Gemini fails)
# =============================================================================

async def _call_openai_mini(
    messages: list[dict],
    max_tokens: int = 60,
    temperature: float = 0.7,
) -> Optional[str]:
    """Call GPT-4o-mini via OpenAI as fallback."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set, GPT-4o-mini fallback unavailable")
        return None

    model = os.getenv("LLM_FALLBACK_MODEL", "gpt-4o-mini")
    timeout = float(os.getenv("LLM_FALLBACK_TIMEOUT", "10"))
    start = time.monotonic()

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
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
        logger.info(
            "OpenAI fallback OK: model=%s latency=%dms tokens_in=%d tokens_out=%d len=%d",
            model, latency_ms, tokens_in, tokens_out, len(content),
        )
        if not content:
            return None
        return {
            "content": content,
            "model": model,
            "provider": "openai",
            "latency_ms": latency_ms,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }
    except asyncio.TimeoutError:
        logger.error("OpenAI fallback timeout after %.0fs", timeout)
        return None
    except Exception as e:
        logger.error("OpenAI fallback error: %s", e)
        return None


_FALLBACK_GUARD = (
    "\n\nIMPORTANTE: No inventes información. Si no tienes contexto suficiente, "
    "responde brevemente con una reacción genérica amable."
)


def _add_fallback_guard(messages: list[dict]) -> list[dict]:
    """Append anti-hallucination instruction to system prompt for GPT-4o-mini fallback."""
    guarded = []
    system_found = False
    for msg in messages:
        if msg["role"] == "system" and not system_found:
            guarded.append({**msg, "content": msg["content"] + _FALLBACK_GUARD})
            system_found = True
        else:
            guarded.append(msg)
    if not system_found:
        guarded.insert(0, {"role": "system", "content": _FALLBACK_GUARD.strip()})
    return guarded


# =============================================================================
# Alternative primary providers (when LLM_PRIMARY_PROVIDER != gemini)
# =============================================================================

async def _try_google_ai(
    messages: list[dict],
    call_type: str,
) -> Optional[dict]:
    """Try Google AI Studio (Gemma 4) as primary provider.

    Sampling params are driven by the model config JSON — not by caller params.
    This is intentional: Gemma 4 optimal sampling (temp=1.0, top_k=64) differs
    from the Gemini Flash-Lite defaults.
    """
    try:
        from core.config.llm_models import GOOGLE_AI_STUDIO_MODEL_ID
        from core.providers.google_provider import call_google_ai

        model_id = GOOGLE_AI_STUDIO_MODEL_ID
        timeout = float(os.getenv("GOOGLE_AI_TIMEOUT", "15"))
        result = await asyncio.wait_for(
            call_google_ai(messages, model_id=model_id),
            timeout=timeout,
        )
        if result:
            asyncio.create_task(_async_log_usage(result, call_type))
            return result
        logger.warning("GoogleAI returned empty, falling back to Gemini")
    except asyncio.TimeoutError:
        logger.warning("GoogleAI timeout, falling back to Gemini")
    except Exception as e:
        logger.warning("GoogleAI failed: %s, falling back to Gemini", e)
    return None


async def _try_deepinfra(
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    call_type: str,
    model_id: Optional[str] = None,
) -> Optional[dict]:
    """Try DeepInfra as primary provider. Returns result dict or None."""
    try:
        from core.providers.deepinfra_provider import call_deepinfra

        timeout = float(os.getenv("DEEPINFRA_TIMEOUT", "8"))
        result = await asyncio.wait_for(
            call_deepinfra(messages, max_tokens, temperature, model_id=model_id),
            timeout=timeout,
        )
        if result:
            asyncio.create_task(_async_log_usage(result, call_type))
            return result
        logger.warning("DeepInfra returned empty, falling back to Gemini")
    except asyncio.TimeoutError:
        logger.warning("DeepInfra timeout, falling back to Gemini")
    except Exception as e:
        logger.warning("DeepInfra failed: %s, falling back to Gemini", e)
    return None


async def _try_together(
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    call_type: str,
    model_id: Optional[str] = None,
) -> Optional[dict]:
    """Try Together AI as primary provider. Returns result dict or None."""
    try:
        from core.providers.together_provider import call_together

        timeout = float(os.getenv("TOGETHER_TIMEOUT", "15"))
        result = await asyncio.wait_for(
            call_together(messages, max_tokens, temperature, model_id=model_id),
            timeout=timeout,
        )
        if result:
            asyncio.create_task(_async_log_usage(result, call_type))
            return result
        logger.warning("Together returned empty, falling back to Gemini")
    except asyncio.TimeoutError:
        logger.warning("Together timeout, falling back to Gemini")
    except Exception as e:
        logger.warning("Together failed: %s, falling back to Gemini", e)
    return None


async def _try_openrouter(
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    call_type: str,
    model_id: Optional[str] = None,
) -> Optional[dict]:
    """Try OpenRouter as primary provider. Returns result dict or None."""
    try:
        from core.providers.openrouter_provider import call_openrouter

        timeout = float(os.getenv("OPENROUTER_TIMEOUT", "120"))
        result = await asyncio.wait_for(
            call_openrouter(messages, max_tokens, temperature, model_id=model_id),
            timeout=timeout,
        )
        if result:
            asyncio.create_task(_async_log_usage(result, call_type))
            return result
        logger.warning("OpenRouter returned empty, falling back to Gemini")
    except asyncio.TimeoutError:
        logger.warning("OpenRouter timeout, falling back to Gemini")
    except Exception as e:
        logger.warning("OpenRouter failed: %s, falling back to Gemini", e)
    return None


# =============================================================================
# Production DM response: [Together/DeepInfra →] Gemini → GPT-4o-mini → None
# =============================================================================

async def generate_dm_response(
    messages: list[dict],
    max_tokens: int = 60,
    temperature: float = 0.7,
) -> Optional[dict]:
    """Generate DM response with two-provider cascade + circuit breaker.

    Pipeline:
      1. Gemini Flash-Lite (primary) — skipped if circuit breaker is open
      2. GPT-4o-mini (fallback) — timeout via LLM_FALLBACK_TIMEOUT env (default 10s)
      3. None if both fail

    Returns:
        dict with {content, model, provider, latency_ms} or None if all fail.

    Called from dm_agent_v2.py for all DM responses.
    """
    # 0. LLM_MODEL_NAME dispatch (preferred path).
    # When set, the active model config picks the provider; the legacy
    # LLM_PRIMARY_PROVIDER cascade is bypassed for the primary attempt.
    # Falls through to Gemini→GPT-4o-mini fallback if the active provider fails.
    from core.config.llm_models import get_active_model_config
    _active_cfg = get_active_model_config()
    if _active_cfg:
        from core.config.llm_models import LLM_MODEL_NAME as _LMN_static
        _model_id = os.getenv("LLM_MODEL_NAME") or _LMN_static
        _prov_name = (_active_cfg.get("provider", {}) or {}).get("name", "")
        if _prov_name == "deepinfra":
            result = await _try_deepinfra(messages, max_tokens, temperature, "dm_response", model_id=_model_id)
            if result:
                return result
        elif _prov_name == "together":
            result = await _try_together(messages, max_tokens, temperature, "dm_response", model_id=_model_id)
            if result:
                return result
        elif _prov_name == "openrouter":
            result = await _try_openrouter(messages, max_tokens, temperature, "dm_response", model_id=_model_id)
            if result:
                return result
            if os.getenv("CCEE_NO_FALLBACK"):
                logger.info("[CCEE] Fallback disabled — OpenRouter failed, returning None")
                return None
        elif _prov_name in ("gemini", "google"):
            if not _gemini_circuit_is_open():
                try:
                    primary_timeout = float(os.getenv("LLM_PRIMARY_TIMEOUT", "5"))
                    result = await asyncio.wait_for(
                        generate_response_gemini(messages, max_tokens, temperature, model_id=_model_id),
                        timeout=primary_timeout,
                    )
                    if result:
                        _gemini_record_success()
                        asyncio.create_task(_async_log_usage(result, "dm_response"))
                        return result
                    _gemini_record_failure()
                except asyncio.TimeoutError:
                    _gemini_record_failure()
                except Exception as e:
                    logger.warning("Gemini (config-driven) failed: %s", e)
                    _gemini_record_failure()
        elif _prov_name == "google_ai_studio":
            result = await _try_google_ai(messages, "dm_response")
            if result:
                return result
            if os.getenv("CCEE_NO_FALLBACK"):
                logger.info("[CCEE] Fallback disabled — primary provider failed, returning None")
                return None
        else:
            logger.warning("[LLM CONFIG] Unknown provider '%s' in active config — falling through to legacy cascade", _prov_name)
        # Active provider failed → fall through to GPT-4o-mini fallback below
        # (skip the legacy LLM_PRIMARY_PROVIDER cascade and the bare Gemini retry)
        logger.warning("[LLM-FALLBACK] Active model %s failed, using OpenAI GPT-4o-mini", _model_id)
        try:
            result = await _call_openai_mini(messages, max_tokens, temperature)
            if result:
                if isinstance(result, dict):
                    result["provider"] = "openai-fallback"
                asyncio.create_task(_async_log_usage(result, "dm_response"))
                return result
        except Exception as e:
            logger.error("GPT-4o-mini fallback failed: %s", e)
        logger.critical("[LLM-ALL-DOWN] No LLM provider available — active model and GPT-4o-mini both failed")
        return None

    # 1. PRIMARY: route based on LLM_PRIMARY_PROVIDER
    if LLM_PRIMARY_PROVIDER == "google_ai_studio":
        result = await _try_google_ai(messages, "dm_response")
        if result:
            return result
        # CCEE_NO_FALLBACK: evaluation mode — return None instead of mixing models.
        # Set this when running CCEE benchmarks to ensure response purity.
        if os.getenv("CCEE_NO_FALLBACK"):
            logger.info("[CCEE] Fallback disabled — primary provider failed, returning None")
            return None
    elif LLM_PRIMARY_PROVIDER == "together":
        result = await _try_together(messages, max_tokens, temperature, "dm_response")
        if result:
            return result
    elif LLM_PRIMARY_PROVIDER == "deepinfra":
        result = await _try_deepinfra(messages, max_tokens, temperature, "dm_response")
        if result:
            return result
    elif LLM_PRIMARY_PROVIDER == "openrouter":
        result = await _try_openrouter(messages, max_tokens, temperature, "dm_response")
        if result:
            return result
        if os.getenv("CCEE_NO_FALLBACK"):
            logger.info("[CCEE] Fallback disabled — OpenRouter failed, returning None")
            return None

    # 2. GEMINI: primary (default) or secondary (when alt provider is primary)
    if _gemini_circuit_is_open():
        logger.info("Circuit breaker open — skipping Gemini")
    else:
        try:
            primary_timeout = float(os.getenv("LLM_PRIMARY_TIMEOUT", "5"))
            result = await asyncio.wait_for(
                generate_response_gemini(messages, max_tokens, temperature),
                timeout=primary_timeout,
            )
            if result:
                _gemini_record_success()
                asyncio.create_task(_async_log_usage(result, "dm_response"))
                return result
            logger.warning("Flash-Lite returned empty, falling back")
            _gemini_record_failure()
        except asyncio.TimeoutError:
            logger.warning("Flash-Lite timeout after %.0fs, falling back",
                            float(os.getenv("LLM_PRIMARY_TIMEOUT", "5")))
            _gemini_record_failure()
        except Exception as e:
            logger.warning("Flash-Lite failed: %s, falling back", e)
            _gemini_record_failure()

    # 3. FALLBACK: GPT-4o-mini — same prompt, no extra anti-hallucination guard.
    # The system prompt already contains all identity/style rules for every provider.
    # Adding an extra "don't hallucinate" instruction was causing GPT-4o-mini to
    # generate overly cautious, generic responses (conv_015: "perrito" hallucination).
    logger.warning("[LLM-FALLBACK] Primary providers failed, using OpenAI GPT-4o-mini")
    try:
        result = await _call_openai_mini(messages, max_tokens, temperature)
        if result:
            if isinstance(result, dict):
                result["provider"] = "openai-fallback"
            asyncio.create_task(_async_log_usage(result, "dm_response"))
            return result
        logger.error("GPT-4o-mini returned empty")
    except Exception as e:
        logger.error("GPT-4o-mini fallback failed: %s", e)

    # 3. Both failed
    logger.critical("[LLM-ALL-DOWN] No LLM provider available — Gemini and GPT-4o-mini both failed")
    return None
