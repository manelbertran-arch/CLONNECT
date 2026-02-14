"""Google Gemini provider for Flash-Lite model inference."""

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
                return content

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

    return await _call_gemini(
        model, api_key, system_prompt, user_message,
        max_tokens, temperature,
    )
