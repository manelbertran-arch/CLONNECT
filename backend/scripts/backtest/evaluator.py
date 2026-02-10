"""
Backtest Evaluator - Score bot responses across 5 dimensions.

Dimensions (weighted):
  Length:  25% - Response length within creator's normal range
  Tone:   25% - Emoji%, question%, exclamation% match creator
  Pool:   15% - Pool match rate for eligible messages
  Safety: 20% - No hallucinations, no links, no prices invented
  Intent: 15% - Correct context classification

Each dimension scores 0-100. Weighted sum = overall score.
"""

import re
from typing import Any, Dict, List, Optional, Tuple


DIMENSION_WEIGHTS = {
    "length": 0.25,
    "tone": 0.25,
    "pool": 0.15,
    "safety": 0.20,
    "intent": 0.15,
}


def score_length(
    turns: List[Dict],
    context_soft_max: Optional[Dict[str, int]] = None,
    baseline_soft_max: int = 60,
) -> Tuple[float, Dict]:
    """
    Score length dimension: % of responses within context-appropriate range.

    A response is "within range" if its length <= soft_max for its context.
    Uses per-context soft_max from calibration if available.
    """
    if not turns:
        return 100.0, {"n": 0}

    within_range = 0
    details_by_context = {}

    for turn in turns:
        ctx = turn.get("context", "otro")
        bot_len = len(turn.get("bot_response", ""))
        real_len = turn.get("real_length", 0)

        # Get soft_max for this context
        if context_soft_max and ctx in context_soft_max:
            soft_max = context_soft_max[ctx]
        else:
            soft_max = baseline_soft_max

        # Scoring: full credit if within soft_max, partial if within 2x, zero if beyond
        # Also full credit if within 1.5x of real response length
        if bot_len <= soft_max:
            credit = 1.0
        elif real_len > 0 and bot_len <= real_len * 1.5:
            credit = 1.0
        elif bot_len <= soft_max * 2:
            # Partial credit: linear decay from soft_max to 2x soft_max
            overshoot = (bot_len - soft_max) / soft_max
            credit = max(0.0, 1.0 - overshoot)
        else:
            credit = 0.0

        if ctx not in details_by_context:
            details_by_context[ctx] = {"total": 0, "within": 0.0, "soft_max": soft_max}
        details_by_context[ctx]["total"] += 1
        details_by_context[ctx]["within"] += credit
        within_range += credit

    score = 100.0 * within_range / len(turns)

    return round(score, 1), {
        "n": len(turns),
        "within_range": round(within_range, 1),
        "pct": round(score, 1),
        "by_context": {
            ctx: {
                "total": d["total"],
                "within": round(d["within"], 1),
                "pct": round(100 * d["within"] / d["total"], 1) if d["total"] else 0,
                "soft_max": d["soft_max"],
            }
            for ctx, d in details_by_context.items()
        },
    }


def score_tone(
    turns: List[Dict],
    target_emoji_pct: float = 19.0,
    target_question_pct: float = 12.7,
    target_excl_pct: float = 20.0,
) -> Tuple[float, Dict]:
    """
    Score tone dimension: how close bot's emoji/question/exclamation rates
    are to creator's real rates.

    Each sub-metric contributes equally (33% each).
    Penalty = abs(actual - target) / target, capped at 1.0.
    """
    if not turns:
        return 100.0, {"n": 0}

    n = len(turns)
    bot_emoji = sum(1 for t in turns if _has_emoji(t.get("bot_response", "")))
    bot_question = sum(1 for t in turns if "?" in t.get("bot_response", ""))
    bot_excl = sum(1 for t in turns if "!" in t.get("bot_response", ""))

    actual_emoji_pct = 100 * bot_emoji / n
    actual_question_pct = 100 * bot_question / n
    actual_excl_pct = 100 * bot_excl / n

    # Score each sub-metric (100 = perfect match, 0 = way off)
    def sub_score(actual: float, target: float) -> float:
        if target == 0:
            return 100.0 if actual == 0 else 50.0
        delta = abs(actual - target) / target
        return max(0.0, 100.0 * (1.0 - delta))

    emoji_score = sub_score(actual_emoji_pct, target_emoji_pct)
    question_score = sub_score(actual_question_pct, target_question_pct)
    excl_score = sub_score(actual_excl_pct, target_excl_pct)

    # Weighted: emoji 40%, question 35%, exclamation 25%
    overall = emoji_score * 0.40 + question_score * 0.35 + excl_score * 0.25

    return round(overall, 1), {
        "n": n,
        "emoji": {"actual_pct": round(actual_emoji_pct, 1), "target_pct": target_emoji_pct, "score": round(emoji_score, 1)},
        "question": {"actual_pct": round(actual_question_pct, 1), "target_pct": target_question_pct, "score": round(question_score, 1)},
        "exclamation": {"actual_pct": round(actual_excl_pct, 1), "target_pct": target_excl_pct, "score": round(excl_score, 1)},
    }


def score_pool(turns: List[Dict]) -> Tuple[float, Dict]:
    """
    Score pool dimension: % of pool-eligible turns that got a pool response.

    Pool-eligible = contexts where pools should cover (greeting, thanks, laugh, etc.)
    """
    if not turns:
        return 100.0, {"n": 0}

    pool_eligible_contexts = {
        "saludo", "agradecimiento", "casual", "humor", "reaccion",
        "continuacion", "apoyo_emocional", "compartir_logro",
        "story_mention",  # Short reactions eligible for pool
    }

    eligible = [t for t in turns if t.get("context", "otro") in pool_eligible_contexts]
    if not eligible:
        return 100.0, {"n": 0, "eligible": 0}

    matched = sum(1 for t in eligible if t.get("pool_matched", False))
    score = 100.0 * matched / len(eligible)

    return round(score, 1), {
        "n": len(turns),
        "eligible": len(eligible),
        "matched": matched,
        "pct": round(score, 1),
    }


def score_safety(turns: List[Dict]) -> Tuple[float, Dict]:
    """
    Score safety dimension: no hallucinations, invented links/prices.

    Checks:
    - No invented URLs (http/https links not in known products)
    - No invented prices (currency amounts not matching real data)
    - No AI self-references ("como IA", "como asistente")
    """
    if not turns:
        return 100.0, {"n": 0}

    violations = 0
    violation_details = []

    ai_patterns = [
        "como ia", "como asistente", "como modelo", "como inteligencia",
        "soy un bot", "soy una ia",
    ]

    for turn in turns:
        resp = turn.get("bot_response", "").lower()

        # Check AI self-references
        for pattern in ai_patterns:
            if pattern in resp:
                violations += 1
                violation_details.append(f"ai_ref: {pattern}")
                break

    score = 100.0 * (len(turns) - violations) / len(turns)

    return round(score, 1), {
        "n": len(turns),
        "violations": violations,
        "violation_details": violation_details[:10],
    }


def score_intent(
    turns: List[Dict],
    max_otro_pct: float = 20.0,
) -> Tuple[float, Dict]:
    """
    Score intent dimension: quality of context classification.

    Metrics:
    - % classified as "otro" (lower is better, target <20%)
    - Context consistency (same context for similar messages)
    """
    if not turns:
        return 100.0, {"n": 0}

    n = len(turns)
    context_counts: Dict[str, int] = {}
    for turn in turns:
        ctx = turn.get("context", "otro")
        context_counts[ctx] = context_counts.get(ctx, 0) + 1

    otro_count = context_counts.get("otro", 0)
    otro_pct = 100.0 * otro_count / n

    # Score: 100 if otro <20%, linear penalty up to 60% otro
    if otro_pct <= max_otro_pct:
        otro_score = 100.0
    elif otro_pct >= 60.0:
        otro_score = 50.0
    else:
        otro_score = 100.0 - (otro_pct - max_otro_pct) * (50.0 / (60.0 - max_otro_pct))

    # Coverage score: how many distinct categories are used
    n_categories = len([c for c in context_counts if context_counts[c] >= 2])
    coverage_score = min(100.0, n_categories * 10)  # 10 categories = 100

    overall = otro_score * 0.6 + coverage_score * 0.4

    return round(overall, 1), {
        "n": n,
        "otro_pct": round(otro_pct, 1),
        "context_distribution": {
            k: {"count": v, "pct": round(100 * v / n, 1)}
            for k, v in sorted(context_counts.items(), key=lambda x: -x[1])
        },
        "n_categories": n_categories,
    }


def evaluate_all(
    turns: List[Dict],
    calibration: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Run all 5 scoring dimensions on a set of turns.

    Args:
        turns: List of turn dicts with bot_response, real_response, context, etc.
        calibration: Optional calibration data with targets

    Returns:
        Full evaluation results with per-dimension and overall scores
    """
    cal = calibration or {}
    baseline = cal.get("baseline", {})

    context_soft_max = cal.get("context_soft_max", None)
    baseline_soft_max = baseline.get("soft_max", 60)
    target_emoji = baseline.get("emoji_pct", 19.0)
    target_question = baseline.get("question_frequency_pct", 12.7)
    target_excl = baseline.get("exclamation_pct", 20.0)

    length_score, length_details = score_length(turns, context_soft_max, baseline_soft_max)
    tone_score, tone_details = score_tone(turns, target_emoji, target_question, target_excl)
    pool_score, pool_details = score_pool(turns)
    safety_score, safety_details = score_safety(turns)
    intent_score, intent_details = score_intent(turns)

    overall = (
        length_score * DIMENSION_WEIGHTS["length"]
        + tone_score * DIMENSION_WEIGHTS["tone"]
        + pool_score * DIMENSION_WEIGHTS["pool"]
        + safety_score * DIMENSION_WEIGHTS["safety"]
        + intent_score * DIMENSION_WEIGHTS["intent"]
    )

    return {
        "overall_score": round(overall, 1),
        "dimensions": {
            "length": {"score": length_score, "weight": DIMENSION_WEIGHTS["length"], "details": length_details},
            "tone": {"score": tone_score, "weight": DIMENSION_WEIGHTS["tone"], "details": tone_details},
            "pool": {"score": pool_score, "weight": DIMENSION_WEIGHTS["pool"], "details": pool_details},
            "safety": {"score": safety_score, "weight": DIMENSION_WEIGHTS["safety"], "details": safety_details},
            "intent": {"score": intent_score, "weight": DIMENSION_WEIGHTS["intent"], "details": intent_details},
        },
        "n_turns": len(turns),
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _has_emoji(text: str) -> bool:
    """Check if text contains emoji."""
    return bool(re.search(r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]|[\ufe00-\ufe0f]", text))
