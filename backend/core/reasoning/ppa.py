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

logger = logging.getLogger(__name__)

ENABLE_PPA = os.getenv("ENABLE_PPA", "false").lower() == "true"
ENABLE_SCORE_BEFORE_SPEAK = os.getenv("ENABLE_SCORE_BEFORE_SPEAK", "false").lower() == "true"

# Alignment threshold — responses below this get refined/retried
ALIGNMENT_THRESHOLD = float(os.getenv("PPA_ALIGNMENT_THRESHOLD", "0.7"))

# Phrases that should never appear in Iris's responses (Doc D patterns)
FORBIDDEN_PHRASES = [
    r"en qu[eé] puedo ayudarte",
    r"c[oó]mo puedo ayudarte",
    r"no dudes en",
    r"estoy aqu[ií] para",
    r"con mucho gusto",
    r"ser[aá] un placer",
    r"quedo a tu disposici[oó]n",
    r"espero que est[eé]s bien",
    r"cualquier consulta",
    r"no dud[eé]is en",
    r"si necesitas algo",
    r"estaré encantad[oa] de",
]

_FORBIDDEN_COMPILED = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN_PHRASES]


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
) -> tuple[float, Dict[str, float]]:
    """Score how well a response matches the creator's persona.

    Returns (overall_score, {dimension: score}).
    """
    baseline = calibration.get("baseline", {})
    target_median = baseline.get("median_length", 35)
    target_soft_max = baseline.get("soft_max", 60)

    scores = {}

    # 1. Length alignment (target: 10-60 chars for Iris)
    resp_len = len(response)
    if 10 <= resp_len <= target_soft_max:
        scores["length"] = 1.0
    elif resp_len <= target_soft_max * 1.5:
        # Mild penalty up to 1.5x soft max
        scores["length"] = max(0.3, 1.0 - (resp_len - target_soft_max) / (target_soft_max * 1.5))
    elif resp_len < 10:
        scores["length"] = 0.5  # Too short but not terrible
    else:
        scores["length"] = 0.2  # Way too long

    # 2. Emoji presence (Iris uses emojis ~18% of messages)
    emoji_pct_target = baseline.get("emoji_pct", 18.0)
    has_emoji = bool(re.search(r'[\U0001F300-\U0001FAFF\u2600-\u27BF]', response))
    # For individual messages, we just check presence when expected
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

    # Iris code-switches freely — both ca and es are fine
    if ca_count > 0 or es_count > 0:
        scores["language"] = 1.0
    else:
        # Very short messages may not have markers — that's OK
        scores["language"] = 0.8 if resp_len < 30 else 0.6

    # 4. Forbidden phrases (Doc D)
    has_forbidden = any(p.search(response) for p in _FORBIDDEN_COMPILED)
    scores["forbidden"] = 0.0 if has_forbidden else 1.0

    # 5. Formality check — Iris never uses formal register
    formal_markers = [r'\bEstimad[oa]\b', r'\bAtentamente\b', r'\bCordialmente\b',
                      r'\busted\b', r'\bLe informo\b']
    has_formal = any(re.search(p, response) for p in formal_markers)
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
) -> str:
    """Build the PPA refinement prompt with similar examples."""
    examples_text = ""
    for i, ex in enumerate(examples, 1):
        examples_text += (
            f"  {i}. Lead: \"{ex.get('user_message', '')}\"\n"
            f"     Iris: \"{ex.get('response', '')}\"\n"
        )

    lead_ref = f" para {lead_name}" if lead_name else ""

    return (
        f"La siguiente respuesta fue generada{lead_ref} pero no suena "
        f"suficientemente como Iris. Reescríbela manteniendo el mismo "
        f"contenido pero con el estilo de Iris (breve, emojis, "
        f"code-switching ca/es, directa):\n\n"
        f"Respuesta original: {response}\n\n"
        f"Ejemplos del estilo de Iris:\n{examples_text}\n"
        f"Respuesta refinada:"
    )


async def apply_ppa(
    response: str,
    calibration: Dict,
    lead_name: str = "",
    detected_language: str = "ca",
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
        response, calibration, detected_language,
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

    prompt = build_refinement_prompt(response, examples, lead_name)
    example_texts = [ex.get("response", "") for ex in examples]

    logger.info("[PPA] Refining response (score=%.2f < %.2f)", score, ALIGNMENT_THRESHOLD)

    try:
        from core.providers.gemini_provider import generate_dm_response

        result = await generate_dm_response(
            [
                {"role": "system", "content": (
                    "Eres Iris Bertran. Reescribe la respuesta con su estilo: "
                    "breve (10-60 chars), emojis, code-switching catalán/español, "
                    "tono directo e informal. NO inventes información nueva."
                )},
                {"role": "user", "content": prompt},
            ],
            max_tokens=80,
            temperature=0.5,
        )

        refined = (result or {}).get("content", "").strip()

        # Validate refinement: must not be empty, not too long, no forbidden phrases
        if (
            refined
            and 5 <= len(refined) <= 200
            and not any(p.search(refined) for p in _FORBIDDEN_COMPILED)
        ):
            # Re-score the refined version
            new_score, new_dim_scores = compute_alignment_score(
                refined, calibration, detected_language,
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
) -> SBSResult:
    """Score Before You Speak — evaluate quality before sending.

    Flow:
      1. Score initial response → if aligned: done (0 extra calls)
      2. PPA refine → if aligned: done (1 extra call)
      3. Retry at different temperature → pick best (2 extra calls max)

    Args:
        response: The initial LLM-generated response
        calibration: Creator calibration data (baseline, few-shot examples)
        system_prompt: System prompt used for generation (for retry)
        user_prompt: User prompt used for generation (for retry)
        lead_name: Lead display name (for refinement prompt)
        detected_language: Detected conversation language
    """
    if not calibration:
        return SBSResult(
            response=response, alignment_score=1.0, total_llm_calls=0, path="pass",
        )

    llm_calls = 0

    # Step 1: Score initial response
    score, dim_scores = compute_alignment_score(response, calibration, detected_language)

    candidates = [{"response": response, "score": score, "source": "initial"}]

    logger.info("[SBS] Initial score=%.2f (threshold=%.2f)", score, ALIGNMENT_THRESHOLD)

    if score >= ALIGNMENT_THRESHOLD:
        return SBSResult(
            response=response, alignment_score=score, scores=dim_scores,
            total_llm_calls=0, path="pass", candidates=candidates,
        )

    # Step 2: PPA refinement (1 extra call)
    ppa_result = await apply_ppa(
        response=response,
        calibration=calibration,
        lead_name=lead_name,
        detected_language=detected_language,
    )
    llm_calls += 1 if ppa_result.was_refined else 0

    if ppa_result.was_refined:
        candidates.append({
            "response": ppa_result.response,
            "score": ppa_result.alignment_score,
            "source": "ppa_refined",
        })

    if ppa_result.alignment_score >= ALIGNMENT_THRESHOLD:
        logger.info("[SBS] PPA refinement sufficient (%.2f)", ppa_result.alignment_score)
        return SBSResult(
            response=ppa_result.response, alignment_score=ppa_result.alignment_score,
            scores=ppa_result.scores, total_llm_calls=llm_calls,
            path="refined", candidates=candidates,
        )

    # Step 3: Retry generation with different temperature (1 more call)
    logger.info("[SBS] PPA insufficient (%.2f), retrying generation", ppa_result.alignment_score)

    try:
        from core.providers.gemini_provider import generate_dm_response

        retry_result = await generate_dm_response(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=80,
            temperature=0.5,  # Lower temperature for more focused retry
        )
        llm_calls += 1

        retry_text = (retry_result or {}).get("content", "").strip()

        if retry_text and 5 <= len(retry_text) <= 200:
            retry_score, retry_dim_scores = compute_alignment_score(
                retry_text, calibration, detected_language,
            )
            candidates.append({
                "response": retry_text,
                "score": retry_score,
                "source": "retry_t05",
            })

            # Pick the best candidate across all attempts
            best = max(candidates, key=lambda c: c["score"])
            logger.info(
                "[SBS] Retry done. Best='%s' score=%.2f (from %s)",
                best["response"][:40], best["score"], best["source"],
            )

            best_scores = dim_scores  # default
            if best["source"] == "retry_t05":
                best_scores = retry_dim_scores
            elif best["source"] == "ppa_refined":
                best_scores = ppa_result.scores

            return SBSResult(
                response=best["response"], alignment_score=best["score"],
                scores=best_scores, total_llm_calls=llm_calls,
                path="retried", candidates=candidates,
            )

    except Exception as e:
        logger.warning("[SBS] Retry generation failed: %s", e)

    # Fallback: return best of what we have
    best = max(candidates, key=lambda c: c["score"])
    return SBSResult(
        response=best["response"], alignment_score=best["score"],
        scores=dim_scores if best["source"] == "initial" else ppa_result.scores,
        total_llm_calls=llm_calls, path="retried", candidates=candidates,
    )
