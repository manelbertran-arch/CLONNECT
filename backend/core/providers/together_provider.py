"""Together.ai provider for fine-tuned and Scout model inference."""

import asyncio
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"
DEEPINFRA_API_URL = "https://api.deepinfra.com/v1/openai/chat/completions"

SCOUT_MODEL = "meta-llama/Llama-4-Scout-17B-16E-Instruct"


async def generate_scout_response(
    messages: list[dict],
    max_tokens: int = 60,
    temperature: float = 0.7,
) -> Optional[str]:
    """Call Llama 4 Scout via DeepInfra with retry on rate limit."""
    api_key = os.getenv("DEEPINFRA_API_KEY")

    if not api_key:
        logger.error("DEEPINFRA_API_KEY not set for Scout")
        return None

    for attempt in range(5):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    DEEPINFRA_API_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": SCOUT_MODEL,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                )
                if resp.status_code == 429:
                    wait = 2 ** attempt + 1
                    logger.warning("DeepInfra rate limited, waiting %ds (attempt %d)", wait, attempt + 1)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
        except httpx.TimeoutException:
            logger.error("DeepInfra Scout timeout (attempt %d)", attempt + 1)
            await asyncio.sleep(2)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                wait = 2 ** attempt + 1
                await asyncio.sleep(wait)
                continue
            logger.error("DeepInfra Scout error: %s", e)
            return None
        except Exception as e:
            logger.error("DeepInfra Scout error: %s", e)
            return None

    return None


async def generate_finetuned_response(
    messages: list[dict],
    max_tokens: int = 60,
    temperature: float = 0.7,
    api_key: Optional[str] = None,
    model_id: Optional[str] = None,
) -> Optional[str]:
    """Call Together.ai fine-tuned model. Returns response string or None on failure."""
    api_key = api_key or os.getenv("TOGETHER_API_KEY")
    model_id = model_id or os.getenv("TOGETHER_MODEL_ID")

    if not api_key or not model_id:
        return None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                TOGETHER_API_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model_id,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stop": ["<|eot_id|>"],
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except httpx.TimeoutException:
        logger.error("Together.ai timeout")
        return None
    except Exception as e:
        logger.error("Together.ai error: %s", e)
        return None
