"""
Post Persona Alignment (PPA) — refine LLM responses to match creator voice.

Based on PPA (Chen et al., 2025): generate → retrieve similar persona examples
→ refine if misaligned. Reuses the reflexion engine slot in postprocessing.

Score Before You Speak (Saggar et al., ECAI 2025) extension:
  1. Score alignment → if >= 0.7 → done (0 extra calls)
  2. If < 0.7 → PPA refine (1 extra call) → re-score
  3. If still < 0.7 → retry generation at different temperature, pick best (2 extra calls max)

Feature flags:
  - ENABLE_PPA (default: false) — basic PPA refinement
  - ENABLE_SCORE_BEFORE_SPEAK (default: false) — full score-before-speak with retry
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core.observability.metrics import emit_metric

logger = logging.getLogger(__name__)

ENABLE_PPA = os.getenv("ENABLE_PPA", "false").lower() == "true"
ENABLE_SCORE_BEFORE_SPEAK = os.getenv("ENABLE_SCORE_BEFORE_SPEAK", "false").lower() == "true"

# Alignment threshold — responses below this get refined/retried
ALIGNMENT_THRESHOLD = float(os.getenv("PPA_ALIGNMENT_THRESHOLD", "0.7"))

# Default values when no calibration exists (new creator without data)
_DEFAULTS = {
    "median_length": 40,
    "soft_max": 80,
    "emoji_pct": 15.0,
}

# Universal formal markers — language-independent, not creator-specific
_FORMAL_MARKERS = [
    r'\bEstimad[oa]\b', r'\bAtentamente\b', r'\bCordialmente\b',
    r'\busted\b', r'\bLe informo\b', r'\bSaludos cordiales\b',
]
_FORMAL_COMPILED = [re.compile(p, re.IGNORECASE) for p in _FORMAL_MARKERS]

# Fallback forbidden phrases — used only when no creator blacklist available
_DEFAULT_FORBIDDEN = [
    r"en qu[eé] puedo ayudarte",
    r"c[oó]mo puedo ayudarte",
    r"no dudes en",
    r"estoy aqu[ií] para",
    r"con mucho gusto",
    r"ser[aá] un placer",
    r"quedo a tu disposici[oó]n",
    r"espero que est[eé]s bien",
    r"cualquier consulta",
    r"si necesitas algo",
    r"estaré encantad[oa] de",
]
_DEFAULT_FORBIDDEN_COMPILED = [re.compile(p, re.IGNORECASE) for p in _DEFAULT_FORBIDDEN]

# Cache compiled blacklists per creator to avoid re-parsing on every call
_blacklist_cache: Dict[str, List[re.Pattern]] = {}


def _get_forbidden_patterns(creator_id: str = "") -> List[re.Pattern]:
    """Get forbidden phrase patterns from creator's Doc D blacklist.

    Falls back to default hardcoded list if no creator extraction exists.
    """
    if not creator_id:
        return _DEFAULT_FORBIDDEN_COMPILED

    if creator_id in _blacklist_cache:
        return _blacklist_cache[creator_id]

    try:
        from core.personality_loader import load_extraction

        extraction = load_extraction(creator_id)
        if extraction and extraction.blacklist_phrases:
            patterns = []
            for phrase_group in extraction.blacklist_phrases:
                # Doc D blacklist uses "/" to separate alternatives:
                # 'no dudes en" / "no dudes en contactarme'
                for sub in phrase_group.split("/"):
                    sub = sub.strip().strip('"').strip()
                    if len(sub) >= 4:  # Skip very short fragments
                        patterns.append(re.compile(re.escape(sub), re.IGNORECASE))

            if patterns:
                _blacklist_cache[creator_id] = patterns
                return patterns
    except Exception as e:
        logger.debug("Could not load blacklist for %s: %s", creator_id, e)

    return _DEFAULT_FORBIDDEN_COMPILED


@dataclass
class PPAResult:
    """Result of Post Persona Alignment."""
    response: str
    alignment_score: float
    was_refined: bool
    scores: Dict[str, float] = field(default_factory=dict)
    matched_examples: List[str] = field(default_factory=list)


def compute_alignment_score(
    response: str,
    calibration: Dict,
    detected_language: str = "ca",
    creator_id: str = "",
) -> tuple[float, Dict[str, float]]:
    """Score how well a response matches the creator's persona.

    All thresholds are read from calibration["baseline"]. If missing,
    defaults are used so PPA works for any creator without code changes.

    Returns (overall_score, {dimension: score}).
    """
    baseline = calibration.get("baseline", {})
    target_median = baseline.get("median_length", _DEFAULTS["median_length"])
    target_soft_max = baseline.get("soft_max", _DEFAULTS["soft_max"])
    emoji_pct_target = baseline.get("emoji_pct", _DEFAULTS["emoji_pct"])

    scores = {}

    # 1. Length alignment — range derived from calibration
    resp_len = len(response)
    # Acceptable range: median/3 to soft_max
    min_acceptable = max(5, target_median // 3)
    if min_acceptable <= resp_len <= target_soft_max:
        scores["length"] = 1.0
    elif resp_len < min_acceptable:
        scores["length"] = 0.5  # Too short but not fatal
    elif resp_len <= target_soft_max * 1.5:
        overshoot = resp_len - target_soft_max
        scores["length"] = max(0.3, 1.0 - overshoot / (target_soft_max * 0.5))
    else:
        scores["length"] = 0.2  # Way too long

    # 2. Emoji presence — threshold from calibration
    has_emoji = bool(re.search(r'[\U0001F300-\U0001FAFF\u2600-\u27BF]', response))
    if emoji_pct_target > 10:
        scores["emoji"] = 1.0 if has_emoji else 0.4
    else:
        scores["emoji"] = 1.0  # Creator doesn't use emojis much

    # 3. Language alignment
    ca_markers = [r'\bperò\b', r'\bamb\b', r'\bdoncs\b', r'\btambé\b', r'\bperquè\b',
                  r'\bfem\b', r'\bquè\b', r'\bés\b', r'\bpuc\b', r'\bpots\b']
    es_markers = [r'\bpero\b', r'\bgracias\b', r'\bpuedes\b', r'\btienes\b',
                  r'\bbueno\b', r'\bvale\b', r'\bclaro\b']
    resp_lower = response.lower()
    ca_count = sum(1 for p in ca_markers if re.search(p, resp_lower))
    es_count = sum(1 for p in es_markers if re.search(p, resp_lower))

    if ca_count > 0 or es_count > 0:
        scores["language"] = 1.0
    else:
        scores["language"] = 0.8 if resp_len < 30 else 0.6

    # 4. Forbidden phrases — from creator's Doc D blacklist
    forbidden = _get_forbidden_patterns(creator_id)
    has_forbidden = any(p.search(response) for p in forbidden)
    scores["forbidden"] = 0.0 if has_forbidden else 1.0

    # 5. Formality check — universal markers
    has_formal = any(p.search(response) for p in _FORMAL_COMPILED)
    scores["formality"] = 0.0 if has_formal else 1.0

    # Weighted average
    weights = {"length": 0.25, "emoji": 0.15, "language": 0.15,
               "forbidden": 0.25, "formality": 0.20}
    overall = sum(scores[k] * weights[k] for k in weights)

    return overall, scores


def find_similar_examples(
    response: str,
    calibration: Dict,
    n: int = 3,
) -> List[Dict]:
    """Find the n most similar few-shot examples by simple keyword overlap.

    No embeddings needed — lightweight text matching is sufficient
    for the calibration file's 20-30 examples.
    """
    examples = calibration.get("few_shot_examples", [])
    if not examples:
        return []

    resp_words = set(re.findall(r'\b\w{3,}\b', response.lower()))

    scored = []
    for ex in examples:
        ex_text = f"{ex.get('user_message', '')} {ex.get('response', '')}".lower()
        ex_words = set(re.findall(r'\b\w{3,}\b', ex_text))
        if not ex_words:
            continue
        overlap = len(resp_words & ex_words)
        scored.append((overlap, ex))

    scored.sort(key=lambda x: -x[0])
    return [ex for _, ex in scored[:n]]


def build_refinement_prompt(
    response: str,
    examples: List[Dict],
    lead_name: str = "",
    creator_name: str = "",
) -> str:
    """Build the PPA refinement prompt with similar examples."""
    examples_text = ""
    name = creator_name or "the creator"
    for i, ex in enumerate(examples, 1):
        examples_text += (
            f"  {i}. Lead: \"{ex.get('user_message', '')}\"\n"
            f"     {name}: \"{ex.get('response', '')}\"\n"
        )

    lead_ref = f" para {lead_name}" if lead_name else ""

    return (
        f"La siguiente respuesta fue generada{lead_ref} pero no suena "
        f"suficientemente como {name}. Reescríbela manteniendo el mismo "
        f"contenido pero con el estilo de {name} (breve, directa, natural):\n\n"
        f"Respuesta original: {response}\n\n"
        f"Ejemplos del estilo de {name}:\n{examples_text}\n"
        f"Respuesta refinada:"
    )


def _build_refinement_system_prompt(calibration: Dict, creator_name: str = "") -> str:
    """Build system prompt for refinement call from calibration data."""
    baseline = calibration.get("baseline", {})
    soft_max = baseline.get("soft_max", _DEFAULTS["soft_max"])
    median = baseline.get("median_length", _DEFAULTS["median_length"])
    emoji_pct = baseline.get("emoji_pct", _DEFAULTS["emoji_pct"])
    name = creator_name or "the creator"

    parts = [f"Eres {name}. Reescribe la respuesta con su estilo:"]
    parts.append(f"breve ({median}-{soft_max} chars)")
    if emoji_pct > 10:
        parts.append("emojis")
    parts.append("tono directo e informal. NO inventes información nueva.")

    return " ".join(parts)


async def apply_ppa(
    response: str,
    calibration: Dict,
    lead_name: str = "",
    detected_language: str = "ca",
    creator_id: str = "",
    creator_name: str = "",
) -> PPAResult:
    """Apply Post Persona Alignment to a response.

    Returns the (possibly refined) response with alignment metadata.
    """
    if not calibration:
        return PPAResult(
            response=response, alignment_score=1.0,
            was_refined=False, scores={},
        )

    # Step 1: Score alignment
    score, dim_scores = compute_alignment_score(
        response, calibration, detected_language, creator_id,
    )

    logger.info(
        "[PPA] alignment_score=%.2f scores=%s len=%d",
        score, dim_scores, len(response),
    )

    # Step 2: If aligned enough, pass through
    if score >= ALIGNMENT_THRESHOLD:
        return PPAResult(
            response=response, alignment_score=score,
            was_refined=False, scores=dim_scores,
        )

    # Step 3: Find similar examples and refine
    examples = find_similar_examples(response, calibration, n=3)
    if not examples:
        logger.warning("[PPA] No calibration examples found, skipping refinement")
        return PPAResult(
            response=response, alignment_score=score,
            was_refined=False, scores=dim_scores,
        )

    prompt = build_refinement_prompt(response, examples, lead_name, creator_name)
    example_texts = [ex.get("response", "") for ex in examples]
    system_prompt = _build_refinement_system_prompt(calibration, creator_name)

    logger.info("[PPA] Refining response (score=%.2f < %.2f)", score, ALIGNMENT_THRESHOLD)

    try:
        from core.providers.gemini_provider import generate_dm_response

        baseline = calibration.get("baseline", {})
        soft_max = baseline.get("soft_max", _DEFAULTS["soft_max"])

        result = await generate_dm_response(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max(80, soft_max + 20),
            temperature=0.5,
        )

        refined = (result or {}).get("content", "").strip()

        # Validate refinement using creator's own blacklist
        forbidden = _get_forbidden_patterns(creator_id)
        if (
            refined
            and 5 <= len(refined) <= soft_max * 3
            and not any(p.search(refined) for p in forbidden)
        ):
            # Re-score the refined version
            new_score, new_dim_scores = compute_alignment_score(
                refined, calibration, detected_language, creator_id,
            )
            logger.info(
                "[PPA] Refined: %.2f→%.2f '%s' → '%s'",
                score, new_score, response[:50], refined[:50],
            )
            return PPAResult(
                response=refined, alignment_score=new_score,
                was_refined=True, scores=new_dim_scores,
                matched_examples=example_texts,
            )
        else:
            logger.warning("[PPA] Refinement rejected (empty/too_long/forbidden)")

    except Exception as e:
        logger.warning("[PPA] Refinement LLM call failed: %s", e)

    # Fallback: return original
    return PPAResult(
        response=response, alignment_score=score,
        was_refined=False, scores=dim_scores,
        matched_examples=example_texts,
    )


# ═══════════════════════════════════════════════════════════════════════
# SCORE BEFORE YOU SPEAK (Saggar et al., ECAI 2025)
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class SBSResult:
    """Result of Score Before You Speak evaluation."""
    response: str
    alignment_score: float
    scores: Dict[str, float] = field(default_factory=dict)
    total_llm_calls: int = 0
    path: str = ""  # "pass" | "refined" | "retried"
    candidates: List[Dict] = field(default_factory=list)


async def score_before_speak(
    response: str,
    calibration: Dict,
    system_prompt: str,
    user_prompt: str,
    lead_name: str = "",
    detected_language: str = "ca",
    creator_id: str = "",
    creator_name: str = "",
) -> SBSResult:
    """Score Before You Speak — evaluate quality before sending.

    Flow:
      1. Score initial response → if aligned (>= 0.7): done (0 extra calls)
      2. If score < 0.7 AND user_prompt available:
         Retry generation with the SAME primary model at temperature=0.5.
         This avoids cross-model rewrites (Gemini rewriting Qwen output) which
         introduced semantic drift. Lower temperature = more conservative output.
      3. Always pick max(initial, retry) — never output a retry with lower score.
         If no user_prompt or retry fails: return original unchanged.

    Note: PPA refinement (Gemini rewrite with few-shot examples) was removed
    because it degraded quality ~0.7 pts in A/B eval (cross-model semantic drift).
    """
    if not calibration:
        return SBSResult(
            response=response, alignment_score=1.0, total_llm_calls=0, path="pass",
        )

    # Step 1: Score initial response
    score, dim_scores = compute_alignment_score(
        response, calibration, detected_language, creator_id,
    )

    candidates = [{"response": response, "score": score, "scores": dim_scores, "source": "initial"}]

    logger.info("[SBS] Initial score=%.2f (threshold=%.2f)", score, ALIGNMENT_THRESHOLD)
    emit_metric("sbs_score_initial", score, creator_id=creator_id)

    if score >= ALIGNMENT_THRESHOLD:
        emit_metric("sbs_path_total", creator_id=creator_id, path="pass")
        return SBSResult(
            response=response, alignment_score=score, scores=dim_scores,
            total_llm_calls=0, path="pass", candidates=candidates,
        )

    # Step 2: Retry with same primary model at temperature=0.5 (more conservative)
    # Guard: skip retry if user_prompt is empty (full_prompt not set by generation phase)
    if not user_prompt:
        logger.debug("[SBS] No user_prompt available, skipping retry (returning original)")
        emit_metric("sbs_path_total", creator_id=creator_id, path="pass")
        return SBSResult(
            response=response, alignment_score=score, scores=dim_scores,
            total_llm_calls=0, path="pass", candidates=candidates,
        )

    logger.info("[SBS] score=%.2f < %.2f, retrying with primary model at temp=0.5", score, ALIGNMENT_THRESHOLD)

    try:
        from core.providers.gemini_provider import generate_dm_response

        baseline = calibration.get("baseline", {})
        soft_max = baseline.get("soft_max", _DEFAULTS["soft_max"])

        retry_result = await generate_dm_response(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max(80, soft_max + 20),
            temperature=0.5,
        )

        retry_text = (retry_result or {}).get("content", "").strip()

        if retry_text and 5 <= len(retry_text) <= soft_max * 3:
            retry_score, retry_dim_scores = compute_alignment_score(
                retry_text, calibration, detected_language, creator_id,
            )
            candidates.append({
                "response": retry_text,
                "score": retry_score,
                "scores": retry_dim_scores,
                "source": "retry_t05",
            })

            # Always pick the BEST candidate — never downgrade to a worse retry
            best = max(candidates, key=lambda c: c["score"])
            logger.info(
                "[SBS] Retry score=%.2f. Best='%s' score=%.2f (from %s)",
                retry_score, best["response"][:40], best["score"], best["source"],
            )
            emit_metric("sbs_score_retry", retry_score, creator_id=creator_id)
            emit_metric("sbs_path_total", creator_id=creator_id, path="retried")

            return SBSResult(
                response=best["response"],
                alignment_score=best["score"],
                scores=best.get("scores", dim_scores),
                total_llm_calls=1,
                path="retried",
                candidates=candidates,
            )

    except Exception as e:
        logger.warning("[SBS] Retry generation failed: %s", e)

    # Retry failed or produced invalid output — return original unchanged
    emit_metric("sbs_path_total", creator_id=creator_id, path="fail_retry_fallback")
    return SBSResult(
        response=response, alignment_score=score, scores=dim_scores,
        total_llm_calls=0, path="fail_retry_fallback", candidates=candidates,
    )
