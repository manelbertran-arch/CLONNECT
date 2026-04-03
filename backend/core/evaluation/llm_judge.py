"""
CCEE LLM Judge (B2, B5, C2, C3)

Uses Gemini Flash Lite as evaluator for subjective quality metrics:
  B2 — Persona consistency: does the bot maintain personality?
  B5 — Emotional signature: does the bot react emotionally like the creator?
  C2 — Naturalness: does it sound like a real human DM?
  C3 — Contextual appropriateness: is the response fitting for the context?
"""

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Cost tracking (Gemini Flash Lite approximate pricing)
_COST_PER_1K_INPUT = 0.000075   # $0.075 per 1M input tokens
_COST_PER_1K_OUTPUT = 0.0003    # $0.30 per 1M output tokens
_total_input_tokens = 0
_total_output_tokens = 0


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // 4)


def _parse_rating(response: str) -> Optional[int]:
    """Extract 1-5 rating from LLM response."""
    if not response:
        return None
    # Try JSON parsing first
    try:
        data = json.loads(response)
        if isinstance(data, dict):
            for key in ("rating", "score", "puntuacion", "nota"):
                if key in data:
                    val = int(data[key])
                    if 1 <= val <= 5:
                        return val
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    # Fallback: regex for "rating": N or just a standalone digit
    m = re.search(r'["\']?(?:rating|score|nota)["\']?\s*[:=]\s*(\d)', response)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 5:
            return val
    # Last resort: first digit 1-5 on its own line
    for line in response.strip().split('\n'):
        line = line.strip()
        if re.match(r'^[1-5]$', line):
            return int(line)
    return None


def _rating_to_score(rating: Optional[int]) -> float:
    """Convert 1-5 rating to 0-100 score."""
    if rating is None:
        return 50.0  # neutral fallback
    return (rating - 1) * 25.0  # 1→0, 2→25, 3→50, 4→75, 5→100


async def _call_prometheus(prompt: str) -> Optional[str]:
    """Call Prometheus via HuggingFace Inference API."""
    import aiohttp
    hf_token = os.environ.get("HF_TOKEN")
    model = os.environ.get("PROMETHEUS_MODEL", "prometheus-eval/prometheus-7b-v2.0")
    if not hf_token:
        return None

    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {"Authorization": f"Bearer {hf_token}"}
    payload = {
        "inputs": prompt,
        "parameters": {"max_new_tokens": 150, "temperature": 0.1, "return_full_text": False},
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, list) and data:
                        return data[0].get("generated_text", "")
                elif resp.status == 503:
                    # Model loading — wait and retry handled by caller
                    logger.info(f"Prometheus model loading (503), will retry")
                else:
                    body = await resp.text()
                    logger.warning(f"Prometheus returned {resp.status}: {body[:200]}")
    except Exception as e:
        logger.warning(f"Prometheus call failed: {e}")
    return None


async def _call_judge(prompt: str, system_prompt: str = "") -> Optional[str]:
    """Call LLM judge: Prometheus (HF) → Gemini fallback."""
    global _total_input_tokens, _total_output_tokens

    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    _total_input_tokens += _estimate_tokens(full_prompt)

    for attempt in range(2):
        # Try Prometheus first
        result = await _call_prometheus(full_prompt)
        if result:
            _total_output_tokens += _estimate_tokens(result)
            return result

        # Fallback to Gemini
        try:
            from core.providers.gemini_provider import generate_simple
            result = await generate_simple(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=150,
                temperature=0.1,
            )
            if result:
                _total_output_tokens += _estimate_tokens(result)
                return result
        except Exception as e:
            logger.warning(f"LLM judge attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                await asyncio.sleep(1.0)
    return None


# ---------------------------------------------------------------------------
# Individual judge functions
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are an expert evaluator of AI-generated social media DMs. "
    "Rate ONLY with a JSON object: {\"rating\": N, \"reason\": \"...\"} where N is 1-5. "
    "Be strict. Real DMs are short, informal, and natural."
)


async def score_b2_persona_consistency(
    bot_response: str,
    creator_description: str,
    user_input: str,
) -> float:
    """B2: Does the bot maintain the creator's personality consistently?"""
    prompt = (
        f"Creator description: {creator_description}\n\n"
        f"User message: {user_input}\n"
        f"Bot response: {bot_response}\n\n"
        "Rate 1-5: Does this response sound like it comes from the creator described above? "
        "1=completely off-character, 3=somewhat consistent, 5=perfectly in character.\n"
        "Respond ONLY with JSON: {\"rating\": N, \"reason\": \"...\"}"
    )
    result = await _call_judge(prompt, _SYSTEM_PROMPT)
    return _rating_to_score(_parse_rating(result))


async def score_b5_emotional_signature(
    bot_response: str,
    creator_description: str,
    user_input: str,
) -> float:
    """B5: Does the bot's emotional tone match the creator's typical reaction?"""
    prompt = (
        f"Creator personality: {creator_description}\n\n"
        f"User message: {user_input}\n"
        f"Bot response: {bot_response}\n\n"
        "Rate 1-5: Does the emotional tone match how this creator typically reacts? "
        "Consider warmth, humor, empathy, enthusiasm. "
        "1=completely wrong tone, 3=acceptable, 5=perfect emotional match.\n"
        "Respond ONLY with JSON: {\"rating\": N, \"reason\": \"...\"}"
    )
    result = await _call_judge(prompt, _SYSTEM_PROMPT)
    return _rating_to_score(_parse_rating(result))


async def score_c2_naturalness(bot_response: str) -> float:
    """C2: Does the response sound like a real person typed it in a DM?"""
    prompt = (
        f"Message: {bot_response}\n\n"
        "Rate 1-5: Does this read like a real person typed it in Instagram DMs? "
        "Look for: natural abbreviations, casual tone, appropriate length, "
        "no overly formal language, no AI-like patterns (lists, bullet points, disclaimers). "
        "1=obviously AI, 3=could be either, 5=definitely human.\n"
        "Respond ONLY with JSON: {\"rating\": N, \"reason\": \"...\"}"
    )
    result = await _call_judge(prompt, _SYSTEM_PROMPT)
    return _rating_to_score(_parse_rating(result))


async def score_c3_contextual_appropriateness(
    bot_response: str,
    user_input: str,
    context_type: str = "",
) -> float:
    """C3: Is the response appropriate for the conversation context?"""
    ctx = f" (context type: {context_type})" if context_type else ""
    prompt = (
        f"User message{ctx}: {user_input}\n"
        f"Bot response: {bot_response}\n\n"
        "Rate 1-5: Is this response appropriate for the context? "
        "Consider: relevance, tone match to situation, helpful vs dismissive, "
        "respects emotional state if applicable. "
        "1=completely inappropriate, 3=adequate, 5=perfectly fitting.\n"
        "Respond ONLY with JSON: {\"rating\": N, \"reason\": \"...\"}"
    )
    result = await _call_judge(prompt, _SYSTEM_PROMPT)
    return _rating_to_score(_parse_rating(result))


# ---------------------------------------------------------------------------
# Batch scoring
# ---------------------------------------------------------------------------

async def score_llm_judge_batch(
    test_cases: List[Dict],
    bot_responses: List[str],
    creator_description: str,
    max_concurrent: int = 5,
) -> Dict[str, Any]:
    """Run all 4 LLM judge metrics over all test cases.

    Returns aggregate scores for B2, B5, C2, C3 plus timing and cost.
    """
    global _total_input_tokens, _total_output_tokens
    _total_input_tokens = 0
    _total_output_tokens = 0

    start_time = time.time()
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _bounded(coro):
        async with semaphore:
            return await coro

    # Build all tasks
    b2_tasks = []
    b5_tasks = []
    c2_tasks = []
    c3_tasks = []

    for tc, resp in zip(test_cases, bot_responses):
        user_input = tc.get("user_input", "")
        ctx_type = tc.get("input_type", "")

        b2_tasks.append(_bounded(score_b2_persona_consistency(resp, creator_description, user_input)))
        b5_tasks.append(_bounded(score_b5_emotional_signature(resp, creator_description, user_input)))
        c2_tasks.append(_bounded(score_c2_naturalness(resp)))
        c3_tasks.append(_bounded(score_c3_contextual_appropriateness(resp, user_input, ctx_type)))

    # Run all in parallel (bounded by semaphore)
    all_tasks = b2_tasks + b5_tasks + c2_tasks + c3_tasks
    all_results = await asyncio.gather(*all_tasks, return_exceptions=True)

    n = len(test_cases)
    b2_scores = []
    b5_scores = []
    c2_scores = []
    c3_scores = []

    for i, result in enumerate(all_results):
        score = result if isinstance(result, float) else 50.0
        if i < n:
            b2_scores.append(score)
        elif i < 2 * n:
            b5_scores.append(score)
        elif i < 3 * n:
            c2_scores.append(score)
        else:
            c3_scores.append(score)

    elapsed = time.time() - start_time
    est_cost = (
        _total_input_tokens / 1000 * _COST_PER_1K_INPUT
        + _total_output_tokens / 1000 * _COST_PER_1K_OUTPUT
    )

    def _mean(lst):
        return round(sum(lst) / max(len(lst), 1), 2)

    return {
        "B2_persona_consistency": {"score": _mean(b2_scores), "per_case": b2_scores},
        "B5_emotional_signature": {"score": _mean(b5_scores), "per_case": b5_scores},
        "C2_naturalness": {"score": _mean(c2_scores), "per_case": c2_scores},
        "C3_contextual_appropriateness": {"score": _mean(c3_scores), "per_case": c3_scores},
        "aggregate": round((_mean(b2_scores) + _mean(b5_scores) + _mean(c2_scores) + _mean(c3_scores)) / 4, 2),
        "timing_seconds": round(elapsed, 1),
        "estimated_cost_usd": round(est_cost, 4),
        "total_llm_calls": len(all_tasks),
    }
