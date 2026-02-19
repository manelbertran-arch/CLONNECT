"""Google Gemini provider for Flash-Lite model inference.

Production DM pipeline:
  PRIMARY:  Gemini 2.0 Flash-Lite (via Google AI API)
  FALLBACK: GPT-4o-mini (via OpenAI API)
  Nothing else in the active path.

Entry point: generate_dm_response() — called from dm_agent_v2.py
"""

import asyncio
import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"


async def _call_gemini(
    model: str,
    api_key: str,
    system_prompt: str,
    user_message: str,
    max_tokens: int,
    temperature: float,
    max_retries: int = 3,
) -> Optional[str]:
    """Call Google Gemini API with retry and exponential backoff."""
    url = f"{GEMINI_API_URL}/{model}:generateContent?key={api_key}"

    payload = {
        "contents": [{"parts": [{"text": user_message}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }

    for attempt in range(max_retries):
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
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

                content = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                usage = data.get("usageMetadata", {})

                logger.info(
                    "Gemini OK: model=%s latency=%dms tokens_in=%d tokens_out=%d len=%d",
                    model, latency_ms,
                    usage.get("promptTokenCount", 0),
                    usage.get("candidatesTokenCount", 0),
                    len(content),
                )
                return {
                    "content": content,
                    "model": model,
                    "provider": "gemini",
                    "latency_ms": latency_ms,
                }

        except httpx.TimeoutException:
            logger.warning(
                "Gemini timeout (attempt %d/%d)", attempt + 1, max_retries,
            )
            await asyncio.sleep(2)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                wait = 2 ** attempt + 1
                await asyncio.sleep(wait)
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
) -> Optional[str]:
    """Call Gemini Flash-Lite. Accepts OpenAI-format messages for compatibility.

    Extracts system prompt and user message from the messages list,
    then calls the Gemini generateContent API.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY not set")
        return None

    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

    # Extract system prompt and user message from OpenAI-format messages
    system_prompt = ""
    user_message = ""
    for msg in messages:
        if msg["role"] == "system":
            system_prompt = msg["content"]
        elif msg["role"] == "user":
            user_message = msg["content"]

    if not user_message:
        logger.error("Gemini: no user message found in messages")
        return None

    result = await _call_gemini(
        model, api_key, system_prompt, user_message,
        max_tokens, temperature,
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

    # 1. Try Gemini
    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        try:
            result = await asyncio.wait_for(
                _call_gemini(model, api_key, system_prompt, prompt, max_tokens, temperature),
                timeout=float(os.getenv("LLM_PRIMARY_TIMEOUT", "8")),
            )
            if result and result.get("content"):
                return result["content"]
            logger.warning("generate_simple: Gemini returned empty, falling back")
        except asyncio.TimeoutError:
            logger.warning("generate_simple: Gemini timeout, falling back")
        except Exception as e:
            logger.warning("generate_simple: Gemini failed: %s, falling back", e)

    # 2. Fallback: GPT-4o-mini
    try:
        result = await _call_openai_mini(messages, max_tokens, temperature)
        if result and result.get("content"):
            return result["content"]
    except Exception as e:
        logger.error("generate_simple: OpenAI fallback failed: %s", e)

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
        logger.info(
            "OpenAI fallback OK: model=%s latency=%dms tokens_in=%d tokens_out=%d len=%d",
            model, latency_ms,
            usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0,
            len(content),
        )
        if not content:
            return None
        return {
            "content": content,
            "model": model,
            "provider": "openai",
            "latency_ms": latency_ms,
        }
    except asyncio.TimeoutError:
        logger.error("OpenAI fallback timeout after %.0fs", timeout)
        return None
    except Exception as e:
        logger.error("OpenAI fallback error: %s", e)
        return None


# =============================================================================
# Production DM response: Flash-Lite → GPT-4o-mini → None
# =============================================================================

async def generate_dm_response(
    messages: list[dict],
    max_tokens: int = 60,
    temperature: float = 0.7,
) -> Optional[dict]:
    """Generate DM response with two-provider cascade.

    Pipeline:
      1. Gemini Flash-Lite (primary) — timeout via LLM_PRIMARY_TIMEOUT env (default 8s)
      2. GPT-4o-mini (fallback) — timeout via LLM_FALLBACK_TIMEOUT env (default 10s)
      3. None if both fail

    Returns:
        dict with {content, model, provider, latency_ms} or None if all fail.

    Called from dm_agent_v2.py for all DM responses.
    """
    # 1. PRIMARY: Gemini Flash-Lite
    try:
        primary_timeout = float(os.getenv("LLM_PRIMARY_TIMEOUT", "8"))
        result = await asyncio.wait_for(
            generate_response_gemini(messages, max_tokens, temperature),
            timeout=primary_timeout,
        )
        if result:
            return result
        logger.warning("Flash-Lite returned empty, falling back to GPT-4o-mini")
    except asyncio.TimeoutError:
        logger.warning("Flash-Lite timeout after %.0fs, falling back to GPT-4o-mini",
                        float(os.getenv("LLM_PRIMARY_TIMEOUT", "8")))
    except Exception as e:
        logger.warning("Flash-Lite failed: %s, falling back to GPT-4o-mini", e)

    # 2. FALLBACK: GPT-4o-mini
    try:
        result = await _call_openai_mini(messages, max_tokens, temperature)
        if result:
            return result
        logger.error("GPT-4o-mini returned empty")
    except Exception as e:
        logger.error("GPT-4o-mini fallback failed: %s", e)

    # 3. Both failed
    logger.error("All LLM providers failed (Flash-Lite + GPT-4o-mini)")
    return None
