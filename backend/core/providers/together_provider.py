"""Together.ai provider for fine-tuned model inference."""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

TOGETHER_API_URL = "https://api.together.xyz/v1/chat/completions"


async def generate_finetuned_response(
    messages: list[dict],
    max_tokens: int = 300,
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
