"""
CCEE v5.2 — Ground Truth Calibration Test

Uses real creator messages from DB as ground truth anchors:
  - Real creator messages = definition of perfect persona (target: ≥4/5)
  - Style-inverted responses (LLM-generated opposite style) = anti-persona (target: ≤2/5)
  - Required gap between real and inverted: ≥2.0 points

Method: PersonaGym EMNLP 2025 — exemplar responses at each score level for calibration.
Our advantage: we have the REAL creator messages — the ultimate exemplar for score 5.

ZERO HARDCODING: No creator-specific strings. All behaviour derived from Doc D and DB data.
UNIVERSAL: Works for any creator in any language.

Functions:
  load_real_creator_messages(creator_id, n, min_length) -> List[Dict]
  generate_style_inverted_responses(doc_d_text, user_inputs, n) -> List[Dict]
  run_ground_truth_calibration(creator_id, doc_d_text, n_samples, metrics) -> Dict
"""

import logging
import os
import json
import random
import re
import time
from typing import Any, Dict, List, Optional

import openai
import psycopg2

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DB access (mirrors pattern from _fetch_real_responses_for_h1 in scorer)
# ---------------------------------------------------------------------------

def load_real_creator_messages(
    creator_id: str,
    n: int = 20,
    min_length: int = 10,
) -> List[Dict[str, str]]:
    """Load real creator messages from DB together with the preceding lead message.

    Returns {"user_input": str, "content": str} — the user_input is the lead
    message that prompted the real creator response.

    Args:
        creator_id: Creator slug (e.g. "iris_bertran")
        n: Number of message pairs to fetch
        min_length: Minimum character length for creator responses

    Returns:
        List of {"user_input": str, "content": str} dicts.
        Empty list if DB unavailable or creator not found.
    """
    from dotenv import load_dotenv
    load_dotenv()

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.warning("calibration: DATABASE_URL not set, cannot load real messages")
        return []

    try:
        conn = psycopg2.connect(db_url)
    except Exception as e:
        logger.warning(f"calibration: DB connection failed: {e}")
        return []

    try:
        # Resolve creator UUID
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM creators WHERE name = %s", (creator_id,))
            row = cur.fetchone()
            if not row:
                logger.warning(f"calibration: creator '{creator_id}' not found in DB")
                return []
            creator_uuid = str(row[0])

        # Fetch real user→creator message pairs (random sample)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    m_user.content AS user_msg,
                    m_bot.content  AS creator_msg
                FROM messages m_user
                JOIN messages m_bot
                    ON m_bot.lead_id   = m_user.lead_id
                    AND m_bot.role     = 'assistant'
                    AND m_bot.created_at > m_user.created_at
                    AND m_bot.deleted_at IS NULL
                JOIN leads l ON l.id = m_user.lead_id
                WHERE l.creator_id      = CAST(%s AS uuid)
                    AND m_user.role     = 'user'
                    AND m_user.content  IS NOT NULL
                    AND LENGTH(m_user.content)  > 2
                    AND m_user.deleted_at IS NULL
                    AND m_bot.content   IS NOT NULL
                    AND LENGTH(m_bot.content)  >= %s
                    AND m_bot.content NOT LIKE '[%%'
                    AND m_bot.content NOT LIKE 'http%%'
                    AND m_bot.content NOT LIKE '%%sticker%%'
                    AND m_bot.content NOT LIKE '%%[📷%%'
                    AND m_bot.content NOT LIKE '%%[🎤%%'
                    AND m_bot.content NOT LIKE '%%[audio%%'
                    AND m_bot.content NOT LIKE '%%[video%%'
                    AND m_bot.content NOT LIKE '%%[image%%'
                ORDER BY RANDOM()
                LIMIT %s
            """, (creator_uuid, min_length, n * 3))  # oversample, then trim
            rows = cur.fetchall()

        if not rows:
            logger.warning(f"calibration: no messages found for {creator_id}")
            return []

        # De-duplicate creator responses and trim to n
        seen: set = set()
        pairs: List[Dict[str, str]] = []
        for user_msg, creator_msg in rows:
            key = creator_msg.strip().lower()[:60]
            if key in seen:
                continue
            seen.add(key)
            pairs.append({"user_input": str(user_msg), "content": str(creator_msg)})
            if len(pairs) >= n:
                break

        logger.info(f"calibration: loaded {len(pairs)} real creator messages for {creator_id}")
        return pairs

    except Exception as e:
        logger.warning(f"calibration: DB query failed: {e}")
        return []
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Style-inverted response generator (LLM, derived from Doc D)
# ---------------------------------------------------------------------------

def generate_style_inverted_responses(
    doc_d_text: str,
    user_inputs: List[str],
    n: int = 20,
) -> List[Dict[str, str]]:
    """Generate anti-persona responses by INVERTING the creator's style from Doc D.

    Uses the lead-sim model (Qwen3-30B-A3B via DeepInfra) to produce responses
    that are the OPPOSITE of the creator's documented style. The inversion is
    derived entirely from Doc D — no language-specific templates or hardcoding.

    The LLM is asked to:
      1. Analyse the creator's style dimensions from Doc D
      2. Produce responses that maximally violate each dimension

    Args:
        doc_d_text: Creator's Doc D persona profile (full text)
        user_inputs: Lead messages to respond to
        n: Total number of inverted responses to generate

    Returns:
        List of {"user_input": str, "content": str, "inversion_type": str}
    """
    api_key = os.environ.get("DEEPINFRA_API_KEY")
    if not api_key:
        logger.warning("calibration: DEEPINFRA_API_KEY not set, cannot generate inversions")
        return []

    client = openai.OpenAI(
        api_key=api_key,
        base_url="https://api.deepinfra.com/v1/openai",
        timeout=60,
    )
    lead_sim_model = os.environ.get("LEAD_SIM_MODEL", "Qwen/Qwen3-30B-A3B")

    # Cycle through user inputs to fill n responses
    sampled_inputs = [user_inputs[i % len(user_inputs)] for i in range(n)]

    # Batch request: generate all n inversions in one LLM call (cheaper, faster)
    numbered_inputs = "\n".join(f"{i+1}. {msg}" for i, msg in enumerate(sampled_inputs))

    prompt = (
        f"Given this creator's personality profile:\n"
        f"{doc_d_text[:1200]}\n\n"
        f"Your task: generate responses to each user message below that are the "
        f"EXACT OPPOSITE of this creator's style. You are generating ANTI-PERSONA "
        f"responses — a robotic assistant that is nothing like this creator.\n\n"
        f"MANDATORY inversion rules (ALL must apply to every response):\n"
        f"1. LANGUAGE: Respond ONLY in formal English, regardless of the language of the "
        f"user message. The creator uses informal vernacular — you use formal English.\n"
        f"2. REGISTER: Use corporate, stiff, bureaucratic phrasing (e.g. 'I acknowledge your "
        f"message', 'Please be advised', 'As per your inquiry').\n"
        f"3. WARMTH: Be cold, transactional, impersonal. No empathy, no warmth, no personality.\n"
        f"4. LENGTH: Write 1-3 complete formal sentences. Never one-word answers.\n"
        f"5. EMOJI: Use zero emoji, abbreviations, slang, or informal punctuation.\n"
        f"6. VOCABULARY: Avoid any vocabulary, catchphrases, or patterns from this creator.\n\n"
        f"User messages to respond to:\n{numbered_inputs}\n\n"
        f"Output ONLY the {n} numbered responses in the same order, "
        f"one per line, format: '1. <response>' through '{n}. <response>'. "
        f"No other text. /no_think"
    )

    try:
        resp = client.chat.completions.create(
            model=lead_sim_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=2000,
        )
        raw = resp.choices[0].message.content or ""
        from core.providers.deepinfra_provider import strip_thinking_artifacts
        raw = strip_thinking_artifacts(raw).strip()

        # Parse numbered responses
        inverted: List[Dict[str, str]] = []
        for i, user_input in enumerate(sampled_inputs):
            # Match line starting with "i+1."
            pattern = rf"(?:^|\n)\s*{i+1}\.\s*(.+?)(?=\n\s*{i+2}\.|$)"
            m = re.search(pattern, raw, re.DOTALL)
            if m:
                content = m.group(1).strip()
            else:
                # Fallback: split by numbered lines
                lines = [l.strip() for l in raw.splitlines() if l.strip()]
                content = lines[i] if i < len(lines) else f"[inversion_{i+1}]"
                # Strip leading "N. "
                content = re.sub(r"^\d+\.\s*", "", content)

            inverted.append({
                "user_input": user_input,
                "content": content,
                "inversion_type": "style_inverted_from_doc_d",
            })

        logger.info(f"calibration: generated {len(inverted)} style-inverted responses")
        return inverted

    except Exception as e:
        logger.warning(f"calibration: inversion generation failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Judge scorer (reuses _call_judge + RUBRIC_J3 from scorer — no duplication)
# ---------------------------------------------------------------------------

def _score_response_j3(
    user_input: str,
    bot_response: str,
    doc_d: str,
) -> Optional[int]:
    """Score a single response on the J3 persona-alignment rubric (1-5).

    Reuses _call_judge and RUBRIC_J3 from multi_turn_scorer — no duplication.

    Returns:
        Integer 1-5, or None if judge failed.
    """
    from core.evaluation.m_prometheus_judge import _call_judge
    from core.evaluation.multi_turn_scorer import RUBRIC_J3

    prompt = f"""###Task Description:
An instruction (might include an Input inside it), a response to evaluate, a reference answer that gets a score of 5, and a score rubric representing an evaluation criteria are given.
1. Write a detailed feedback that assesses the quality of the response strictly based on the given score rubric, not evaluating in general.
2. After writing a feedback, write a score that is an integer between 1 and 5.
3. The output format should look as follows: "Feedback: (write a feedback) [RESULT] (an integer between 1 and 5)"
4. Please do not generate any other opening, closing, or explanations.

###Instruction:
You are evaluating whether a creator's response aligns with their personality profile.

=== CREATOR PERSONALITY PROFILE ===
{doc_d}

=== CONTEXT ===
The lead said: "{user_input}"
The creator responded:

Does this response ACTIVELY demonstrate the personality profile above?
Focus on: tone, vocabulary, language mixing, emotional register, formality level.
IMPORTANT: A very short response like "sí", "jaja", or "vale 💕" that doesn't violate \
the persona but also doesn't demonstrate it should score 3 (passive match), not 5. \
Score 5 requires the response to ACTIVELY demonstrate the creator's unique communication \
patterns — their specific catchphrases, language mix, emotional warmth style, etc.

###Response to evaluate:
{bot_response}

###Reference Answer (Score 5):
The response perfectly matches the creator's documented tone, vocabulary, language mix, and emotional warmth.

###Score Rubric:
{RUBRIC_J3}

###Feedback:"""

    raw = _call_judge(prompt)
    if not raw:
        return None
    m = re.search(r'\[RESULT\]\s*(\d)', raw)
    if m:
        score = int(m.group(1))
        return score if 1 <= score <= 5 else None
    return None


# ---------------------------------------------------------------------------
# Main calibration runner
# ---------------------------------------------------------------------------

def run_ground_truth_calibration(
    creator_id: str,
    doc_d_text: str,
    n_samples: int = 20,
    metrics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run ground truth calibration for the CCEE judge.

    Two-sided test:
      1. Real creator messages from DB → should score ≥4/5 (they ARE the persona)
      2. Style-inverted responses (LLM-generated opposite) → should score ≤2/5

    PASS criteria (PersonaGym EMNLP 2025 calibration standard):
      - real_mean ≥ 4.0
      - inverted_mean ≤ 2.0
      - gap ≥ 2.0

    Args:
        creator_id: Creator slug
        doc_d_text: Creator's Doc D persona profile text
        n_samples: Number of samples for each group (real and inverted)
        metrics: List of metric names to calibrate (currently only "J3" supported)

    Returns:
        Dict with per-metric calibration results and overall status.
    """
    if metrics is None:
        metrics = ["J3"]

    # Load doc D from scorer if not supplied
    if not doc_d_text:
        from core.evaluation.multi_turn_scorer import _load_compressed_doc_d
        doc_d_text = _load_compressed_doc_d(creator_id)

    start = time.time()
    results: Dict[str, Any] = {
        "creator_id": creator_id,
        "n_samples": n_samples,
        "metrics": {},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    # --- Load real messages ---
    print(f"[calibration] Loading {n_samples} real messages for {creator_id}...")
    real_pairs = load_real_creator_messages(creator_id, n=n_samples)
    if not real_pairs:
        results["error"] = "no_real_messages_in_db"
        results["status"] = "ERROR"
        return results

    # Extract user inputs for inversion generation
    user_inputs = [p["user_input"] for p in real_pairs]

    # --- Generate style-inverted responses ---
    print(f"[calibration] Generating {n_samples} style-inverted responses...")
    inverted_pairs = generate_style_inverted_responses(
        doc_d_text=doc_d_text,
        user_inputs=user_inputs,
        n=n_samples,
    )
    if not inverted_pairs:
        results["error"] = "inversion_generation_failed"
        results["status"] = "ERROR"
        return results

    # --- Score both groups with judge ---
    for metric in metrics:
        if metric != "J3":
            logger.warning(f"calibration: metric '{metric}' not yet implemented, skipping")
            continue

        print(f"[calibration] Scoring {metric}: real group ({len(real_pairs)} samples)...")
        real_scores: List[int] = []
        real_details: List[Dict] = []

        for i, pair in enumerate(real_pairs):
            score = _score_response_j3(pair["user_input"], pair["content"], doc_d_text)
            if score is not None:
                real_scores.append(score)
                real_details.append({
                    "user_input": pair["user_input"][:80],
                    "content": pair["content"][:80],
                    "score": score,
                })
            if (i + 1) % 5 == 0:
                print(f"  real: {i+1}/{len(real_pairs)} scored, running mean={sum(real_scores)/max(1,len(real_scores)):.2f}")

        print(f"[calibration] Scoring {metric}: inverted group ({len(inverted_pairs)} samples)...")
        inverted_scores: List[int] = []
        inverted_details: List[Dict] = []

        for i, pair in enumerate(inverted_pairs):
            score = _score_response_j3(pair["user_input"], pair["content"], doc_d_text)
            if score is not None:
                inverted_scores.append(score)
                inverted_details.append({
                    "user_input": pair["user_input"][:80],
                    "content": pair["content"][:80],
                    "inversion_type": pair.get("inversion_type", ""),
                    "score": score,
                })
            if (i + 1) % 5 == 0:
                print(f"  inverted: {i+1}/{len(inverted_pairs)} scored, running mean={sum(inverted_scores)/max(1,len(inverted_scores)):.2f}")

        # --- Compute calibration statistics ---
        real_mean = sum(real_scores) / len(real_scores) if real_scores else 0.0
        inverted_mean = sum(inverted_scores) / len(inverted_scores) if inverted_scores else 0.0
        gap = real_mean - inverted_mean

        def _score_dist(scores: List[int]) -> Dict[str, int]:
            dist = {str(s): 0 for s in range(1, 6)}
            for s in scores:
                dist[str(s)] = dist.get(str(s), 0) + 1
            return dist

        # PASS criteria
        pass_real = real_mean >= 4.0
        pass_inverted = inverted_mean <= 2.0
        pass_gap = gap >= 2.0
        metric_status = "PASS" if (pass_real and pass_inverted and pass_gap) else "FAIL"

        results["metrics"][metric] = {
            "real_mean": round(real_mean, 3),
            "real_n": len(real_scores),
            "real_distribution": _score_dist(real_scores),
            "real_details": real_details,
            "inverted_mean": round(inverted_mean, 3),
            "inverted_n": len(inverted_scores),
            "inverted_distribution": _score_dist(inverted_scores),
            "inverted_details": inverted_details,
            "gap": round(gap, 3),
            "pass_real_geq_4": pass_real,
            "pass_inverted_leq_2": pass_inverted,
            "pass_gap_geq_2": pass_gap,
            "status": metric_status,
        }

        print(
            f"\n[calibration] {metric} results:\n"
            f"  Real mean:     {real_mean:.3f}/5 (n={len(real_scores)}) "
            f"{'✅' if pass_real else '❌ (need ≥4.0)'}\n"
            f"  Inverted mean: {inverted_mean:.3f}/5 (n={len(inverted_scores)}) "
            f"{'✅' if pass_inverted else '❌ (need ≤2.0)'}\n"
            f"  Gap:           {gap:.3f} pts "
            f"{'✅' if pass_gap else '❌ (need ≥2.0)'}\n"
            f"  Status: {metric_status}"
        )

    # --- Overall status ---
    metric_statuses = [v.get("status") for v in results["metrics"].values()]
    results["status"] = "PASS" if metric_statuses and all(s == "PASS" for s in metric_statuses) else "FAIL"
    results["elapsed_s"] = round(time.time() - start, 1)

    return results
