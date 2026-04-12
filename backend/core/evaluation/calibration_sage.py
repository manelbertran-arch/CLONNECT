"""
SAGE Self-Consistency Test for CCEE judge.

Based on "Are We on the Right Way to Assessing LLM-as-a-Judge?" (Dec 2025).

Measures two properties WITHOUT human annotation:
  IPI  — Intra-Pair Instability: does the judge flip when we swap response order?
  TOV  — Transitivity: if A>B and B>C, does the judge confirm A>C?

Quality gradient (Q5→Q1) is built DYNAMICALLY per creator:
  Q5 = real creator message from DB (long, personality-rich)
  Q4 = real creator message from DB (shorter, simpler)
  Q3 = LLM-generated generic/neutral response
  Q2 = LLM-generated formal/opposite-register response
  Q1 = LLM-generated wrong-language response

No hardcoded responses — works for any creator_id.
Uses the same judge (Qwen3-30B-A3B via DeepInfra) as the CCEE measurement.
"""

import json
import logging
import os
import re
import time
from typing import Dict, List, Optional, Tuple

import psycopg2

from core.evaluation.m_prometheus_judge import (
    _build_direct_prompt,
    _build_rubric_b2,
    _call_judge,
    _parse_pairwise_result,
    _parse_result_score,
)

logger = logging.getLogger(__name__)

# Thresholds from the SAGE paper
SAGE_IPI_THRESHOLD = 0.25   # <25% flip rate → reliable judge
SAGE_TOV_THRESHOLD = 0.15   # <15% transitivity violations → reliable judge


# ---------------------------------------------------------------------------
# Language detection — fully derived from style_profile A6 / A8
# ---------------------------------------------------------------------------

_LANG_NAMES: Dict[str, str] = {
    "ca": "Catalan", "es": "Spanish", "en": "English", "fr": "French",
    "it": "Italian", "pt": "Portuguese", "de": "German", "nl": "Dutch",
    "pl": "Polish", "ru": "Russian", "zh": "Chinese", "ja": "Japanese",
    "ar": "Arabic", "ko": "Korean", "tr": "Turkish", "sv": "Swedish",
    "no": "Norwegian", "da": "Danish", "fi": "Finnish", "ro": "Romanian",
}

# Candidate opposite languages (ordered by preference)
_OPPOSITE_LANG_CANDIDATES: List[Tuple[str, str]] = [
    ("de", "German (Deutsch)"),
    ("ja", "Japanese"),
    ("ar", "Arabic"),
    ("zh", "Mandarin Chinese"),
    ("ko", "Korean"),
    ("ru", "Russian"),
]


def _detect_creator_language(style_profile: Dict) -> Dict:
    """Extract primary language(s) and select an opposite language from style_profile.

    Uses A6_language_ratio for primary language detection.
    Uses A8_formality for register description.

    Returns dict with keys:
        primary       — human-readable e.g. "Catalan and Spanish"
        primary_codes — list of ISO codes e.g. ["ca", "es"]
        opposite      — language the creator does NOT use, e.g. "German (Deutsch)"
        formality     — e.g. "very informal"
    """
    lang_ratios = style_profile.get("A6_language_ratio", {}).get("ratios", {})

    # Top single-language codes (≥5%, no mixed codes like "ca-es")
    top_langs = sorted(
        [(l, r) for l, r in lang_ratios.items()
         if l != "unknown" and r >= 0.05 and "-" not in l],
        key=lambda x: -x[1],
    )[:3]
    primary_codes = [l for l, _ in top_langs]
    primary_names = [_LANG_NAMES.get(c, c) for c in primary_codes]
    primary_str = " and ".join(primary_names) if primary_names else "unknown"

    # Choose the first opposite language NOT present in creator's repertoire
    all_creator_langs = set(lang_ratios.keys())
    opposite = "German (Deutsch)"  # default fallback
    for code, display in _OPPOSITE_LANG_CANDIDATES:
        if code not in all_creator_langs or lang_ratios.get(code, 0) < 0.01:
            opposite = display
            break

    # Formality description
    formality_score = style_profile.get("A8_formality", {}).get("formality_score", 0)
    abbrev_rate = style_profile.get("A8_formality", {}).get("abbreviation_rate", 0)
    # Thresholds match the new continuous formality_score: (1 + formal_rate - informal_rate) / 2
    # 0.0 = fully informal, 0.5 = neutral/no markers, 1.0 = fully formal
    if formality_score < 0.3:
        formality = "very informal"
    elif formality_score < 0.45:
        formality = "informal"
    else:
        formality = "semi-formal"
    if abbrev_rate > 0.03:
        formality += ", abbreviation-heavy"

    return {
        "primary": primary_str,
        "primary_codes": primary_codes,
        "opposite": opposite,
        "formality": formality,
    }


# ---------------------------------------------------------------------------
# DB: real message fetching for Q5 / Q4
# ---------------------------------------------------------------------------

def _fetch_real_messages_for_sage(creator_id: str, limit: int = 80) -> List[Dict]:
    """Fetch real creator messages from DB for building Q5/Q4 quality levels.

    Returns list of dicts: {user_msg, creator_msg, char_count}
    Sorted descending by char_count (longest first → Q5 candidate at index 0).
    """
    from dotenv import load_dotenv
    load_dotenv()

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.warning("SAGE: DATABASE_URL not set — skipping DB fetch")
        return []

    try:
        conn = psycopg2.connect(db_url)
    except Exception as e:
        logger.warning(f"SAGE: DB connection failed: {e}")
        return []

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM creators WHERE name = %s", (creator_id,))
            row = cur.fetchone()
            if not row:
                logger.warning(f"SAGE: Creator '{creator_id}' not found in DB")
                return []
            creator_uuid = str(row[0])

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    m_user.content  AS user_msg,
                    m_bot.content   AS creator_msg,
                    LENGTH(m_bot.content) AS char_count
                FROM messages m_user
                JOIN messages m_bot
                    ON  m_bot.lead_id    = m_user.lead_id
                    AND m_bot.role       = 'assistant'
                    AND m_bot.created_at > m_user.created_at
                    AND m_bot.deleted_at IS NULL
                JOIN leads l ON l.id = m_user.lead_id
                WHERE l.creator_id      = CAST(%s AS uuid)
                    AND m_user.role     = 'user'
                    AND m_user.content  IS NOT NULL
                    AND LENGTH(m_user.content) > 10
                    AND m_user.deleted_at IS NULL
                    AND m_bot.content   IS NOT NULL
                    AND LENGTH(m_bot.content) > 10
                    AND m_bot.content   NOT LIKE '%%http%%'
                    AND m_bot.content   NOT LIKE '%%www.%%'
                    AND m_bot.content   NOT LIKE '[🎤%%'
                    AND m_bot.content   NOT LIKE '[%%Audio%%'
                    AND m_user.content  NOT LIKE 'http%%'
                    AND m_user.content  NOT LIKE '%%we.tl%%'
                    AND m_user.content  NOT LIKE '%%youtu%%'
                    AND m_user.content  NOT LIKE '%%tiktok%%'
                    AND m_user.content  NOT LIKE '[%%'
                ORDER BY RANDOM()
                LIMIT %s
                """,
                (creator_uuid, limit),
            )
            rows = cur.fetchall()

        pairs = [
            {"user_msg": r[0], "creator_msg": r[1], "char_count": r[2]}
            for r in rows
        ]
        pairs.sort(key=lambda x: x["char_count"], reverse=True)
        return pairs

    except Exception as e:
        logger.warning(f"SAGE: DB query failed: {e}")
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# LLM-based Q3 / Q2 / Q1 generation (all via _call_judge / Qwen3)
# ---------------------------------------------------------------------------

def _clean_generated(raw: str) -> str:
    """Strip judge format artifacts ([RESULT], [SCORE], ratings) from generated text."""
    import re as _re
    # Remove trailing [RESULT] N lines that leak from judge format
    raw = _re.sub(r"\s*\[RESULT\]\s*\d+\s*$", "", raw, flags=_re.IGNORECASE | _re.MULTILINE)
    raw = _re.sub(r"\s*\[SCORE\]\s*\d+\s*$", "", raw, flags=_re.IGNORECASE | _re.MULTILINE)
    return raw.strip().strip('"')


def _generate_q3_generic(user_msg: str, lang_info: Dict) -> str:
    """Q3: Generic, persona-free helpful response in the creator's primary language."""
    primary = lang_info["primary"]
    prompt = (
        f"Generate a brief, helpful response to the following message.\n"
        f"Rules: neutral tone, no personality, no slang, no emojis, no distinctive style.\n"
        f"Sound like a generic chatbot with zero persona.\n"
        f"YOU MUST respond in {primary} — do NOT use English or any other language.\n"
        f"Keep it to 1-2 sentences.\n\n"
        f'User message: "{user_msg}"\n\n'
        f"Generic response in {primary}:"
    )
    raw = _call_judge(prompt, max_tokens=150)
    if raw:
        return _clean_generated(raw)
    return "Entendido. Avísame si necesitas ayuda con algo."


def _generate_q2_formal(user_msg: str, creator_summary: str, lang_info: Dict) -> str:
    """Q2: Extremely formal / opposite-register response."""
    primary = lang_info["primary"]
    prompt = (
        f"Generate an extremely formal, corporate, robotic response to the following message.\n"
        f"The creator's normal style is: {creator_summary}\n"
        f"You MUST use the OPPOSITE register: ultra-formal, no slang, no abbreviations,\n"
        f"no warmth, bureaucratic language, full sentences with formal vocabulary.\n"
        f"Sound like a legal notice or corporate FAQ.\n"
        f"Respond in {primary}. 1-2 sentences.\n\n"
        f'User message: "{user_msg}"\n\n'
        f"Formal response in {primary}:"
    )
    raw = _call_judge(prompt, max_tokens=150)
    if raw:
        return _clean_generated(raw)
    return "Estimado usuario, su consulta ha sido recibida y será procesada en su debido momento."


def _generate_q1_wrong_language(user_msg: str, lang_info: Dict) -> str:
    """Q1: Response in the wrong language (opposite of creator's primary)."""
    opposite = lang_info["opposite"]
    primary = lang_info["primary"]
    prompt = (
        f"Respond to the following message ENTIRELY in {opposite}.\n"
        f"The user message is in {primary}, but you MUST respond in {opposite} only.\n"
        f"Do NOT use {primary} at all — the entire response must be {opposite}.\n"
        f"Use formal register. 1-2 sentences. Give a substantive reply.\n\n"
        f'User message: "{user_msg}"\n\n'
        f"Response in {opposite} only:"
    )
    raw = _call_judge(prompt, max_tokens=150)
    if raw:
        return _clean_generated(raw)
    return "Ich habe Ihre Nachricht erhalten und werde sie bearbeiten."


# ---------------------------------------------------------------------------
# Quality gradient builder
# ---------------------------------------------------------------------------

def _build_quality_gradient(
    creator_id: str,
    style_profile: Dict,
    creator_summary: str,
) -> Tuple[Optional[Dict[str, str]], str]:
    """Build the Q5→Q1 quality gradient dynamically.

    Returns:
        (gradient, user_input) where gradient = {Q5, Q4, Q3, Q2, Q1: response_str}
        Returns (None, "") if not enough real DB messages.
    """
    lang_info = _detect_creator_language(style_profile)

    # Fetch real messages for Q5 / Q4
    real_msgs = _fetch_real_messages_for_sage(creator_id)

    if len(real_msgs) < 2:
        logger.warning(
            f"SAGE: Need ≥2 real messages for gradient, got {len(real_msgs)} for {creator_id}"
        )
        return None, ""

    # Q5 = longest real message (most personality-rich)
    q5_entry = real_msgs[0]
    user_input = q5_entry["user_msg"]
    q5_response = q5_entry["creator_msg"]

    # Q4 = first ~35% of Q5 — same voice and topic, but shorter and less rich.
    # Using a truncated slice (at a word boundary) ensures topical relevance to
    # user_input while clearly being weaker than the full Q5 response.
    q5_len = len(q5_response)
    cutoff = max(40, int(q5_len * 0.35))
    # Snap back to last space within the first cutoff chars to avoid mid-word cut
    slice_text = q5_response[:cutoff]
    last_space = slice_text.rfind(" ")
    if last_space > 20:
        slice_text = slice_text[:last_space]
    q4_response = slice_text + "..."

    # Q3 / Q2 / Q1 = LLM-generated responses to the SAME user_input
    logger.info(f"SAGE: Generating Q3/Q2/Q1 for user_input: '{user_input[:60]}'")
    q3_response = _generate_q3_generic(user_input, lang_info)
    q2_response = _generate_q2_formal(user_input, creator_summary, lang_info)
    q1_response = _generate_q1_wrong_language(user_input, lang_info)

    gradient = {
        "Q5": q5_response,
        "Q4": q4_response,
        "Q3": q3_response,
        "Q2": q2_response,
        "Q1": q1_response,
    }

    for qid, resp in gradient.items():
        logger.info(f"SAGE gradient {qid} ({len(resp)}c): '{resp[:55]}'")

    return gradient, user_input


# ---------------------------------------------------------------------------
# IPI-specific pairwise prompt (B2 persona comparison, NOT H1 Turing test)
# ---------------------------------------------------------------------------

def _build_pairwise_prompt_ipi(
    user_input: str,
    response_a: str,
    response_b: str,
    creator_summary: str,
) -> str:
    """Pairwise prompt for IPI: asks which response better matches the creator's
    authentic voice and style, NOT which looks more like a 'real human'.
    Using B2 persona framing prevents H1 positional bias and is more appropriate
    for comparing quality levels in a persona-consistency gradient.
    """
    return (
        "###Task Description:\n"
        "An instruction and two responses are given. Compare and determine which response "
        "better matches the creator's authentic voice, communication style, and personality.\n"
        "Write brief feedback explaining your choice.\n"
        "The output format: \"Feedback: (feedback) [RESULT] A or B\"\n\n"
        "###Creator Profile:\n"
        f"{creator_summary}\n\n"
        "###Instruction:\n"
        f"User message: {user_input}\n\n"
        "###Response A:\n"
        f"{response_a}\n\n"
        "###Response B:\n"
        f"{response_b}\n\n"
        "###Feedback:"
    )


# ---------------------------------------------------------------------------
# IPI: Intra-Pair Instability test
# ---------------------------------------------------------------------------

def _run_ipi_test(
    gradient: Dict[str, str],
    user_input: str,
    creator_summary: str,
) -> Dict:
    """Intra-Pair Instability: swap response order and measure flip rate.

    For each pair (Q_high, Q_low):
      - Order 1: high as A, low as B  → judge should pick A
      - Order 2: low as A, high as B  → judge should pick B
      Flip = judge didn't prefer the higher-quality response in both orderings.

    IPI = flips / total_pairs  (threshold: <25%)
    """
    quality_order = ["Q5", "Q4", "Q3", "Q2", "Q1"]
    pairs = [
        (quality_order[i], quality_order[j])
        for i in range(len(quality_order))
        for j in range(i + 1, len(quality_order))
    ]

    flips = 0
    pair_details = []

    for q_high, q_low in pairs:
        resp_high = gradient[q_high]
        resp_low = gradient[q_low]

        # Order 1: high=A, low=B → expect "A"
        prompt1 = _build_pairwise_prompt_ipi(user_input, resp_high, resp_low, creator_summary)
        result1 = None
        for _ in range(2):
            raw = _call_judge(prompt1, max_tokens=400)
            if raw:
                result1 = _parse_pairwise_result(raw)
                if result1:
                    break
            time.sleep(1)

        # Order 2: low=A, high=B → expect "B"
        prompt2 = _build_pairwise_prompt_ipi(user_input, resp_low, resp_high, creator_summary)
        result2 = None
        for _ in range(2):
            raw = _call_judge(prompt2, max_tokens=400)
            if raw:
                result2 = _parse_pairwise_result(raw)
                if result2:
                    break
            time.sleep(1)

        consistent = result1 == "A" and result2 == "B"
        if not consistent:
            flips += 1

        pair_details.append({
            "pair": f"{q_high}>{q_low}",
            "order1_result": result1,
            "order2_result": result2,
            "consistent": consistent,
        })
        logger.info(
            f"IPI {q_high}>{q_low}: order1={result1} order2={result2} "
            f"{'OK' if consistent else 'FLIP'}"
        )

    total = len(pairs)
    ipi_rate = flips / total if total > 0 else 0.0
    return {
        "score": ipi_rate,
        "flips": flips,
        "total_pairs": total,
        "status": "PASS" if ipi_rate < SAGE_IPI_THRESHOLD else "FAIL",
        "pair_details": pair_details,
    }


# ---------------------------------------------------------------------------
# TOV: Transitivity test
# ---------------------------------------------------------------------------

def _score_single_response(
    response: str,
    user_input: str,
    reference: str,
    creator_summary: str,
) -> float:
    """Score a single response using the B2 rubric. Returns 1.0–5.0."""
    instruction = (
        f"Evalúa si la respuesta es consistente con el perfil del creator.\n"
        f"Mensaje del usuario: {user_input}"
    )
    rubric = _build_rubric_b2(creator_summary)
    prompt = _build_direct_prompt(instruction, response, reference, rubric)

    for _ in range(2):
        raw = _call_judge(prompt, max_tokens=500)
        if raw:
            score = _parse_result_score(raw)
            if score is not None:
                return float(score)
        time.sleep(1)
    return 3.0  # Middle default on parse failure


def _run_tov_test(
    gradient: Dict[str, str],
    user_input: str,
    creator_summary: str,
) -> Dict:
    """Transitivity test: individual scores should follow Q5>Q4>Q3>Q2>Q1.

    Each response scored 3 times for stability.
    Counts all pairwise ordering violations.

    TOV = violations / total_pairs  (threshold: <15%)
    """
    quality_order = ["Q5", "Q4", "Q3", "Q2", "Q1"]
    reference = gradient["Q5"]  # Gold standard

    # Score each response (3 repetitions)
    scores: Dict[str, float] = {}
    for qid in quality_order:
        reps = []
        for rep in range(3):
            s = _score_single_response(gradient[qid], user_input, reference, creator_summary)
            reps.append(s)
            logger.info(f"TOV {qid} rep{rep+1}: {s}")
            time.sleep(0.5)
        scores[qid] = sum(reps) / len(reps)
        logger.info(f"TOV {qid} mean: {scores[qid]:.2f}")

    # Check all pairwise orderings
    violations = 0
    total_checks = 0
    violation_details = []

    for i in range(len(quality_order)):
        for j in range(i + 1, len(quality_order)):
            q_high = quality_order[i]
            q_low = quality_order[j]
            total_checks += 1
            if scores[q_high] <= scores[q_low]:
                violations += 1
                violation_details.append({
                    "expected": f"{q_high}>{q_low}",
                    "actual": f"{q_high}={scores[q_high]:.2f} <= {q_low}={scores[q_low]:.2f}",
                })

    tov_rate = violations / total_checks if total_checks > 0 else 0.0
    return {
        "score": tov_rate,
        "violations": violations,
        "checks": total_checks,
        "status": "PASS" if tov_rate < SAGE_TOV_THRESHOLD else "FAIL",
        "scores": {qid: round(s, 2) for qid, s in scores.items()},
        "violation_details": violation_details,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_sage_consistency(
    creator_id: str,
    doc_d_text: str,
) -> Dict:
    """Run the full SAGE self-consistency test for the CCEE judge.

    Builds a quality gradient dynamically from the creator's DB messages and
    style profile. No hardcoded responses — universal for any creator_id.

    Args:
        creator_id  — Creator slug e.g. "iris_bertran"
        doc_d_text  — Creator summary text (from _build_creator_summary or similar)

    Returns dict with keys:
        status       — "PASS" | "FAIL" | "SKIPPED"
        ipi          — IPI result dict (score, flips, total_pairs, status, pair_details)
        transitivity — TOV result dict (score, violations, checks, status, scores)
        score_ordering — {Q5, Q4, Q3, Q2, Q1} → mean score (1–5)
        gradient_summary — preview of each gradient level
        user_input   — the user message used for all comparisons
        lang_info    — detected language info
        metadata     — judge model, thresholds
    """
    # Load style profile for language + formality detection
    sp_path = os.path.join("evaluation_profiles", creator_id, "style_profile.json")
    try:
        with open(sp_path) as f:
            style_profile = json.load(f)
    except Exception as e:
        logger.warning(f"SAGE: Could not load style profile for {creator_id}: {e}")
        style_profile = {}

    creator_summary = doc_d_text.strip() if doc_d_text and doc_d_text.strip() else f"Creator: {creator_id}"
    lang_info = _detect_creator_language(style_profile)

    logger.info(f"SAGE: Starting for {creator_id}")
    logger.info(f"SAGE: Language={lang_info['primary']}, opposite={lang_info['opposite']}, formality={lang_info['formality']}")

    # Build quality gradient
    gradient, user_input = _build_quality_gradient(creator_id, style_profile, creator_summary)
    if gradient is None:
        return {
            "status": "SKIPPED",
            "reason": "insufficient_real_messages_in_db",
            "creator_id": creator_id,
        }

    # IPI test: 10 pairs × 2 orderings = 20 judge calls
    logger.info("SAGE: IPI test — 10 pairs × 2 orderings (20 judge calls)")
    ipi_result = _run_ipi_test(gradient, user_input, creator_summary)

    # TOV test: 5 responses × 3 reps = 15 judge calls
    logger.info("SAGE: TOV test — 5 responses × 3 reps (15 judge calls)")
    tov_result = _run_tov_test(gradient, user_input, creator_summary)

    overall = "PASS" if ipi_result["status"] == "PASS" and tov_result["status"] == "PASS" else "FAIL"

    return {
        "status": overall,
        "creator_id": creator_id,
        "ipi": ipi_result,
        "transitivity": tov_result,
        "score_ordering": tov_result["scores"],
        "gradient_summary": {
            qid: {"chars": len(resp), "preview": resp[:60]}
            for qid, resp in gradient.items()
        },
        "user_input": user_input,
        "lang_info": lang_info,
        "metadata": {
            "creator_id": creator_id,
            "judge_model": "Qwen/Qwen3-30B-A3B",
            "judge_provider": "deepinfra",
            "ipi_threshold": SAGE_IPI_THRESHOLD,
            "tov_threshold": SAGE_TOV_THRESHOLD,
        },
    }
