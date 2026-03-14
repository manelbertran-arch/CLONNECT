"""
LLM client for personality extraction pipeline.

Uses Gemini 2.5 Flash (large context, high quality) as primary,
with GPT-4o fallback for analysis tasks requiring deep reasoning.
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _fix_double_encoding(text: str) -> str:
    """Fix double-encoded UTF-8 (UTF-8 bytes interpreted as Latin-1 then re-encoded)."""
    if "\u00c3" not in text:  # Ã — signature of double-encoding
        return text
    try:
        fixed = text.encode("latin-1").decode("utf-8")
        logger.info("Fixed double-encoded UTF-8 in LLM response (%d chars)", len(text))
        return fixed
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def _strip_code_blocks(text: str) -> str:
    """Strip markdown code blocks from LLM response."""
    text = text.strip()
    if text.startswith("```"):
        # Remove first line if it's just ``` or ```markdown etc.
        first_nl = text.find("\n")
        if first_nl > 0:
            text = text[first_nl + 1:]
    if text.endswith("```"):
        text = text[:-3].rstrip()
    return text

# Use Flash-Lite for extraction — 6x cheaper than Flash with acceptable quality
DEFAULT_EXTRACTION_MODEL = "gemini-2.0-flash-lite"


async def call_gemini_extraction(
    system_prompt: str,
    user_message: str,
    max_tokens: int = 8192,
    temperature: float = 0.3,
    model: Optional[str] = None,
) -> Optional[str]:
    """
    Call Gemini for personality extraction analysis.

    Uses higher max_tokens and lower temperature than DM generation.
    Longer timeout for processing large conversation datasets.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.error("GOOGLE_API_KEY not set")
        return None

    model = model or os.getenv("EXTRACTION_MODEL", DEFAULT_EXTRACTION_MODEL)
    url = f"{GEMINI_API_URL}/{model}:generateContent?key={api_key}"

    payload = {
        "contents": [{"parts": [{"text": user_message}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }

    max_retries = 3
    for attempt in range(max_retries):
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(url, json=payload)
                latency_ms = int((time.monotonic() - start) * 1000)

                if resp.status_code == 429:
                    wait = 2 ** attempt + 2
                    logger.warning(
                        "Gemini rate limited, waiting %ds (attempt %d/%d)",
                        wait, attempt + 1, max_retries,
                    )
                    await asyncio.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()

                candidates = data.get("candidates", [])
                if not candidates:
                    logger.error("Gemini: no candidates in response")
                    return None

                content = candidates[0]["content"]["parts"][0]["text"].strip()
                content = _fix_double_encoding(content)
                usage = data.get("usageMetadata", {})
                finish_reason = candidates[0].get("finishReason", "UNKNOWN")

                logger.info(
                    "Extraction LLM OK: model=%s latency=%dms tokens_in=%d tokens_out=%d len=%d finish=%s",
                    model, latency_ms,
                    usage.get("promptTokenCount", 0),
                    usage.get("candidatesTokenCount", 0),
                    len(content),
                    finish_reason,
                )
                return content

        except httpx.TimeoutException:
            logger.warning(
                "Gemini timeout (attempt %d/%d, %dms)",
                attempt + 1, max_retries,
                int((time.monotonic() - start) * 1000),
            )
            await asyncio.sleep(2)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                wait = 2 ** attempt + 2
                await asyncio.sleep(wait)
                continue
            logger.error("Gemini HTTP error: %s — %s", e.response.status_code, e.response.text[:500])
            return None
        except Exception as e:
            logger.error("Gemini error: %s", e)
            return None

    return None


async def call_openai_extraction(
    system_prompt: str,
    user_message: str,
    max_tokens: int = 8192,
    temperature: float = 0.3,
    model: Optional[str] = None,
) -> Optional[str]:
    """Fallback: call OpenAI for extraction analysis."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set")
        return None

    model = model or "gpt-4o"
    start = time.monotonic()

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            ),
            timeout=120.0,
        )

        content = response.choices[0].message.content
        if content:
            content = _fix_double_encoding(content)
        latency_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "OpenAI extraction OK: model=%s latency=%dms tokens=%d/%d len=%d",
            model, latency_ms,
            response.usage.prompt_tokens if response.usage else 0,
            response.usage.completion_tokens if response.usage else 0,
            len(content) if content else 0,
        )
        return content

    except Exception as e:
        logger.error("OpenAI extraction error: %s", e)
        return None


async def extract_with_llm(
    system_prompt: str,
    user_message: str,
    max_tokens: int = 8192,
    temperature: float = 0.3,
) -> Optional[str]:
    """
    Call LLM for extraction with cascade: Gemini Flash → OpenAI GPT-4o.

    Returns the response text, or None if both fail.
    """
    # Primary: Gemini Flash
    result = await call_gemini_extraction(
        system_prompt=system_prompt,
        user_message=user_message,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if result:
        return result

    logger.warning("Gemini extraction failed, trying OpenAI fallback")

    # Fallback: OpenAI GPT-4o
    result = await call_openai_extraction(
        system_prompt=system_prompt,
        user_message=user_message,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return result


async def extract_json_with_llm(
    system_prompt: str,
    user_message: str,
    max_tokens: int = 8192,
    temperature: float = 0.2,
) -> Optional[dict]:
    """
    Call LLM and parse the response as JSON.

    The system prompt should instruct the LLM to return valid JSON.
    Handles markdown code blocks (```json ... ```) gracefully.
    """
    result = await extract_with_llm(
        system_prompt=system_prompt,
        user_message=user_message,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if not result:
        return None

    # Strip markdown code blocks
    text = result.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM JSON response: %s\nFirst 500 chars: %s", e, text[:500])
        return None
