"""DeepInfra provider for Scout model inference with Groq fallback."""

import asyncio
import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DEEPINFRA_API_URL = "https://api.deepinfra.com/v1/openai/chat/completions"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

SCOUT_MODEL_DEEPINFRA = "meta-llama/Llama-4-Scout-17B-16E-Instruct"
SCOUT_MODEL_GROQ = "meta-llama/llama-4-scout-17b-16e-instruct"

# Persistent HTTP clients — reuse TCP/TLS connections across requests
_deepinfra_client: Optional[httpx.AsyncClient] = None
_groq_client: Optional[httpx.AsyncClient] = None


def _get_client(provider: str) -> httpx.AsyncClient:
    """Get or create a persistent HTTP client for the given provider."""
    global _deepinfra_client, _groq_client
    _timeout = float(os.getenv("DEEPINFRA_TIMEOUT", "30"))
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)

    if provider == "deepinfra":
        if _deepinfra_client is None or _deepinfra_client.is_closed:
            _deepinfra_client = httpx.AsyncClient(
                timeout=_timeout, limits=limits,
            )
        return _deepinfra_client
    else:
        if _groq_client is None or _groq_client.is_closed:
            _groq_client = httpx.AsyncClient(
                timeout=_timeout, limits=limits,
            )
        return _groq_client


async def _call_provider(
    url: str,
    api_key: str,
    model: str,
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    provider_name: str,
    max_retries: int = 3,
    lora_adapter: Optional[str] = None,
) -> Optional[str]:
    """Call an OpenAI-compatible provider with retry and exponential backoff."""
    for attempt in range(max_retries):
        start = time.monotonic()
        try:
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if lora_adapter:
                payload["lora_adapter"] = lora_adapter
            if os.getenv("DEEPINFRA_INCLUDE_REASONING", "").lower() == "false":
                payload["include_reasoning"] = False

            client = _get_client(provider_name.lower())
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            latency_ms = int((time.monotonic() - start) * 1000)

            if resp.status_code == 429:
                wait = 2 ** attempt + 1
                logger.warning(
                    "%s rate limited, waiting %ds (attempt %d/%d)",
                    provider_name, wait, attempt + 1, max_retries,
                )
                await asyncio.sleep(wait)
                continue

            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]
            content = (msg.get("content") or "").strip()
            # Reasoning models may put output in reasoning_content
            if not content and msg.get("reasoning_content"):
                content = msg["reasoning_content"].strip()

            usage = data.get("usage", {})
            lora_tag = f" lora={lora_adapter}" if lora_adapter else ""
            # Log with prompt cache info if available
            cached_tokens = usage.get("prompt_cache_hit_tokens", 0)
            cache_tag = f" cached={cached_tokens}" if cached_tokens else ""
            logger.info(
                "%s OK: model=%s%s latency=%dms tokens_in=%d tokens_out=%d%s len=%d",
                provider_name, model, lora_tag, latency_ms,
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
                cache_tag,
                len(content),
            )
            return content

        except httpx.TimeoutException:
            logger.warning(
                "%s timeout (attempt %d/%d)", provider_name, attempt + 1, max_retries,
            )
            await asyncio.sleep(2)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                wait = 2 ** attempt + 1
                await asyncio.sleep(wait)
                continue
            logger.error("%s HTTP error: %s", provider_name, e)
            return None
        except Exception as e:
            logger.error("%s error: %s", provider_name, e)
            return None

    return None


async def generate_response_deepinfra(
    messages: list[dict],
    max_tokens: int = 60,
    temperature: float = 0.7,
) -> Optional[str]:
    """Call Scout via DeepInfra, with optional LoRA adapter."""
    api_key = os.getenv("DEEPINFRA_API_KEY")
    if not api_key:
        logger.error("DEEPINFRA_API_KEY not set")
        return None

    model = os.getenv("SCOUT_MODEL", SCOUT_MODEL_DEEPINFRA)
    lora_adapter = (os.getenv("SCOUT_LORA_ADAPTER") or "").strip() or None
    if lora_adapter:
        logger.info("DeepInfra using LoRA adapter: %s", lora_adapter)
    return await _call_provider(
        DEEPINFRA_API_URL, api_key, model, messages, max_tokens, temperature,
        "DeepInfra", lora_adapter=lora_adapter,
    )


async def generate_response_groq(
    messages: list[dict],
    max_tokens: int = 60,
    temperature: float = 0.7,
) -> Optional[str]:
    """Call Scout via Groq (fallback)."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.error("GROQ_API_KEY not set")
        return None

    return await _call_provider(
        GROQ_API_URL, api_key, SCOUT_MODEL_GROQ, messages, max_tokens, temperature, "Groq",
    )


async def generate_scout_production(
    messages: list[dict],
    max_tokens: int = 60,
    temperature: float = 0.7,
) -> Optional[str]:
    """Production Scout inference with configurable provider.

    SCOUT_PROVIDER env var controls routing:
      - "gemini"   → Google Gemini (Flash-Lite), fallback to DeepInfra
      - "deepinfra" → DeepInfra (default), fallback to Groq
      - "groq"     → Groq primary, fallback to DeepInfra

    Returns response string or None if all providers fail.
    """
    provider = os.getenv("SCOUT_PROVIDER", "deepinfra")

    if provider == "gemini":
        from core.providers.gemini_provider import generate_response_gemini

        result = await generate_response_gemini(messages, max_tokens, temperature)
        if result:
            return result
        logger.warning("Gemini failed, falling back to DeepInfra")
        return await generate_response_deepinfra(messages, max_tokens, temperature)

    if provider == "groq":
        result = await generate_response_groq(messages, max_tokens, temperature)
        if result:
            return result
        logger.warning("Groq failed, falling back to DeepInfra")
        return await generate_response_deepinfra(messages, max_tokens, temperature)

    # Default: DeepInfra primary → Groq fallback
    result = await generate_response_deepinfra(messages, max_tokens, temperature)
    if result:
        return result

    if os.getenv("DEEPINFRA_NO_FALLBACK", "").lower() == "true":
        logger.warning("DeepInfra failed, fallback disabled (DEEPINFRA_NO_FALLBACK=true)")
        return None

    logger.warning("DeepInfra failed, falling back to Groq")
    return await generate_response_groq(messages, max_tokens, temperature)
