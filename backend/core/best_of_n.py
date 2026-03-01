"""
Best-of-N Candidate Generation for copilot mode.

Generates N candidates at different temperatures in parallel,
scores each with the confidence scorer, and returns the best one.
Only active when ENABLE_BEST_OF_N=true and copilot mode is on.

Feature flag: ENABLE_BEST_OF_N (default false)
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

BEST_OF_N_TEMPERATURES = [0.2, 0.7, 1.4]
BEST_OF_N_TIMEOUT = float(os.getenv("BEST_OF_N_TIMEOUT", "12"))

# Style hints injected into the system prompt for each temperature
# to force visibly different outputs even when the LLM is deterministic
BEST_OF_N_STYLE_HINTS = [
    "\n[ESTILO: responde de forma breve y directa, máximo 1-2 frases cortas]",
    "",  # balanced — no extra hint
    "\n[ESTILO: responde de forma más elaborada, cálida y expresiva, 3-4 frases con personalidad]",
]


@dataclass
class Candidate:
    content: str
    temperature: float
    confidence: float
    model: str = ""
    provider: str = ""
    latency_ms: int = 0
    rank: int = 0


@dataclass
class BestOfNResult:
    best: Candidate
    all_candidates: List[Candidate] = field(default_factory=list)
    total_latency_ms: int = 0
    fallback_used: bool = False


async def _generate_single(
    messages: list[dict],
    max_tokens: int,
    temperature: float,
    style_hint: str = "",
) -> Optional[dict]:
    """Generate a single candidate at the given temperature."""
    from core.providers.gemini_provider import generate_dm_response

    # Inject style hint into system prompt to force variation
    if style_hint and messages and messages[0].get("role") == "system":
        patched = list(messages)
        patched[0] = {**patched[0], "content": patched[0]["content"] + style_hint}
        return await generate_dm_response(patched, max_tokens, temperature)

    return await generate_dm_response(messages, max_tokens, temperature)


async def generate_best_of_n(
    messages: list[dict],
    max_tokens: int,
    intent: str,
    response_type: str,
    creator_id: str,
) -> Optional[BestOfNResult]:
    """Generate N candidates in parallel at different temperatures.

    Args:
        messages: LLM messages (system + user)
        max_tokens: Max tokens per candidate
        intent: Detected intent for confidence scoring
        response_type: Response type for confidence scoring
        creator_id: Creator name for confidence scoring

    Returns:
        BestOfNResult with best candidate and all candidates, or None if all fail.
    """
    from core.confidence_scorer import calculate_confidence

    t_start = time.monotonic()

    # Launch all candidates in parallel with style hints for diversity
    tasks = [
        _generate_single(messages, max_tokens, temp, hint)
        for temp, hint in zip(BEST_OF_N_TEMPERATURES, BEST_OF_N_STYLE_HINTS)
    ]

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=BEST_OF_N_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "[BestOfN] All candidates timed out after %.1fs", BEST_OF_N_TIMEOUT
        )
        return None

    # Score successful candidates
    candidates: List[Candidate] = []
    for i, result in enumerate(results):
        temp = BEST_OF_N_TEMPERATURES[i]
        if isinstance(result, Exception):
            logger.debug("[BestOfN] T=%.1f failed: %s", temp, result)
            continue
        if result is None or not result.get("content"):
            logger.debug("[BestOfN] T=%.1f returned empty", temp)
            continue

        content = result["content"]
        confidence = calculate_confidence(
            intent=intent,
            response_text=content,
            response_type=response_type,
            creator_id=creator_id,
        )
        candidates.append(Candidate(
            content=content,
            temperature=temp,
            confidence=confidence,
            model=result.get("model", ""),
            provider=result.get("provider", ""),
            latency_ms=result.get("latency_ms", 0),
        ))

    if not candidates:
        logger.warning("[BestOfN] All %d candidates failed", len(BEST_OF_N_TEMPERATURES))
        return None

    # Sort by confidence descending, assign ranks
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    for rank, cand in enumerate(candidates):
        cand.rank = rank + 1

    total_ms = int((time.monotonic() - t_start) * 1000)
    best = candidates[0]

    logger.info(
        "[BestOfN] %d/%d candidates, best=%.3f T=%.1f (%dms total)",
        len(candidates),
        len(BEST_OF_N_TEMPERATURES),
        best.confidence,
        best.temperature,
        total_ms,
    )

    return BestOfNResult(
        best=best,
        all_candidates=candidates,
        total_latency_ms=total_ms,
        fallback_used=len(candidates) < len(BEST_OF_N_TEMPERATURES),
    )


def serialize_candidates(result: BestOfNResult) -> dict:
    """Serialize BestOfNResult for storage in msg_metadata."""
    return {
        "candidates": [
            {
                "content": c.content,
                "temperature": c.temperature,
                "confidence": c.confidence,
                "model": c.model,
                "provider": c.provider,
                "latency_ms": c.latency_ms,
                "rank": c.rank,
            }
            for c in result.all_candidates
        ],
        "best_temperature": result.best.temperature,
        "best_confidence": result.best.confidence,
        "total_latency_ms": result.total_latency_ms,
        "fallback_used": result.fallback_used,
        "n_candidates": len(result.all_candidates),
    }



class BestOfNSelector:
    """Synchronous wrapper for Best-of-N selection with confidence scoring."""

    def calculate_confidence(
        self,
        intent: str,
        response_text: str,
        response_type: str = "generated",
        creator_id: str = "",
    ) -> float:
        """
        Calculate confidence score for a candidate response.

        Returns 0.0 for empty responses, higher scores for valid responses.
        """
        if not response_text or not response_text.strip():
            return 0.0

        score = 0.5  # base score

        # Pool responses get a confidence boost
        if response_type == "pool":
            score += 0.3

        # Penalize very short responses
        if len(response_text) < 10:
            score -= 0.2

        # Penalize very long responses
        if len(response_text) > 500:
            score -= 0.1

        return max(0.0, min(1.0, score))
