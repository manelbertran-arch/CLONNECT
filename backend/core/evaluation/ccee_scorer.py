"""
CCEE Script 4: CCEE Scorer (v2)

Scores bot responses across 5 dimensions:
  S1 — Style Fidelity (A1-A9 within [P10, P90] + contextual match)
  S2 — Response Quality (BERTScore, lexical metrics, C4 relevance, penalties G1/G2/G4)
  S3 — Strategic Alignment (E1 per-case + E2 distribution JSD)
  S4 — Adaptation (directional + proximity + F2 vocab + F3 length)
  J  — Cognitive Fidelity (J1 memory recall + J2 multi-turn consistency)

Composite = 0.25*S1 + 0.20*S2 + 0.25*S3 + 0.15*S4 + 0.15*J (default weights).
"""

import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.evaluation.style_profile_builder import (
    EMOJI_RE,
    classify_context,
)
from core.evaluation.strategy_map_builder import classify_strategy
from services.vocabulary_extractor import tokenize

# ---------------------------------------------------------------------------
# Metric imports from cpe_v3_evaluator
# ---------------------------------------------------------------------------
from tests.cpe_v3_evaluator import (
    _compute_bertscore_batch,
    _compute_bleu4,
    _compute_chrf,
    _compute_meteor,
    _compute_rouge_l,
    cliffs_delta,
    cliff_magnitude,
    wilcoxon_signed_rank,
)

# ---------------------------------------------------------------------------
# Default weights
# ---------------------------------------------------------------------------
DEFAULT_WEIGHTS = {"S1": 0.25, "S2": 0.20, "S3": 0.25, "S4": 0.15, "J": 0.15}

# ---------------------------------------------------------------------------
# Guard patterns for penalties
# ---------------------------------------------------------------------------
_BOT_REVEAL_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"soy (un |una )?(asistente|bot|ia|inteligencia artificial)",
        r"soc (un |una )?(assistent|bot|ia|intel·ligència artificial)",
        r"i('m| am) (a |an )?(assistant|bot|ai|language model)",
        r"como (asistente|ia|modelo)",
        r"com a (assistent|ia|model)",
        r"no (soy|soc) (una persona|humano|humana)",
    ]
]

_HALLUCINATION_INDICATORS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"según (mi|nuestra) (base de datos|información)",
        r"according to (my|our) (database|records)",
        r"he verificado|i've verified|i have confirmed",
    ]
]


# ---------------------------------------------------------------------------
# S1: Style Fidelity
# ---------------------------------------------------------------------------

def _within_range(value: float, lo: float, hi: float) -> float:
    """Score 0-100 based on how close value is to [lo, hi] range."""
    if lo <= value <= hi:
        return 100.0
    range_size = hi - lo if hi > lo else 1.0
    if value < lo:
        distance = lo - value
    else:
        distance = value - hi
    penalty = min(100.0, (distance / range_size) * 100)
    return max(0.0, 100.0 - penalty)


def score_s1_style_fidelity(
    bot_responses: List[str],
    style_profile: Dict,
    test_cases: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    """Score style fidelity of bot responses against creator profile.

    Returns per-metric scores and aggregate S1 score (0-100).
    """
    if not bot_responses:
        return {"score": 0.0, "detail": "no responses"}

    # A1: Length
    bot_lengths = [len(r) for r in bot_responses]
    a1_thresh = style_profile["A1_length"].get("threshold", [0, 10000])
    a1_scores = [_within_range(l, a1_thresh[0], a1_thresh[1]) for l in bot_lengths]

    # A2: Emoji rate (global)
    bot_emoji = [1.0 if EMOJI_RE.search(r) else 0.0 for r in bot_responses]
    bot_emoji_rate = sum(bot_emoji) / len(bot_emoji)
    creator_emoji_rate = style_profile["A2_emoji"]["global_rate"]
    # Score: closeness to creator rate (within ±0.2 = perfect)
    a2_score = max(0.0, 100.0 - abs(bot_emoji_rate - creator_emoji_rate) * 200)

    # A2 contextual: per-context emoji match
    a2_ctx_scores = []
    if test_cases:
        per_ctx = style_profile["A2_emoji"].get("per_context", {})
        for tc, resp in zip(test_cases, bot_responses):
            ctx = classify_context(tc.get("user_input", ""))
            if ctx in per_ctx and per_ctx[ctx]["count"] >= 5:
                creator_ctx_rate = per_ctx[ctx]["rate"]
                bot_has_emoji = 1.0 if EMOJI_RE.search(resp) else 0.0
                # Binary match: did bot match creator's tendency?
                if creator_ctx_rate > 0.5 and bot_has_emoji == 1.0:
                    a2_ctx_scores.append(100.0)
                elif creator_ctx_rate < 0.2 and bot_has_emoji == 0.0:
                    a2_ctx_scores.append(100.0)
                else:
                    a2_ctx_scores.append(
                        max(0.0, 100.0 - abs(bot_has_emoji - creator_ctx_rate) * 100)
                    )

    a2_ctx_bonus = np.mean(a2_ctx_scores) if a2_ctx_scores else 0.0

    # A3: Exclamation rate
    bot_excl = sum(1 for r in bot_responses if "!" in r) / len(bot_responses)
    creator_excl = style_profile["A3_exclamations"]["rate"]
    a3_score = max(0.0, 100.0 - abs(bot_excl - creator_excl) * 200)

    # A4: Question rate
    bot_q = sum(1 for r in bot_responses if "?" in r) / len(bot_responses)
    creator_q = style_profile["A4_questions"]["rate"]
    a4_score = max(0.0, 100.0 - abs(bot_q - creator_q) * 200)

    # A5: Vocabulary overlap with top distinctive words
    creator_vocab = set(
        item["word"] for item in style_profile["A5_vocabulary"].get("top_50", [])
    )
    if creator_vocab:
        bot_words = set()
        for r in bot_responses:
            bot_words.update(tokenize(r))
        overlap = len(bot_words & creator_vocab) / len(creator_vocab)
        a5_score = min(100.0, overlap * 200)  # 50% overlap = 100
    else:
        a5_score = 50.0

    # A6: Language ratio match
    creator_langs = style_profile["A6_language_ratio"]["ratios"]
    if creator_langs:
        from services.calibration_loader import detect_message_language
        bot_langs = {}
        for r in bot_responses:
            lang = detect_message_language(r) or "unknown"
            bot_langs[lang] = bot_langs.get(lang, 0) + 1
        bot_total = sum(bot_langs.values())
        bot_ratios = {k: v / bot_total for k, v in bot_langs.items()}
        # Compare dominant language
        creator_dominant = max(creator_langs, key=creator_langs.get)
        bot_dominant_ratio = bot_ratios.get(creator_dominant, 0.0)
        a6_score = min(100.0, bot_dominant_ratio * 100 / max(creator_langs[creator_dominant], 0.01))
    else:
        a6_score = 50.0

    # A7: Fragmentation (count newline-separated fragments vs profile)
    a7_data = style_profile.get("A7_fragmentation", {})
    a7_thresh = a7_data.get("threshold", [1.0, 4.0])
    bot_frags = []
    for r in bot_responses:
        chunks = [c.strip() for c in r.split('\n') if c.strip()]
        bot_frags.append(max(1, len(chunks)))
    a7_frag_scores = [_within_range(f, a7_thresh[0], a7_thresh[1]) for f in bot_frags]
    a7_score = float(np.mean(a7_frag_scores)) if a7_frag_scores else 50.0

    # A8: Formality match
    a8_profile = style_profile["A8_formality"]
    creator_formality = a8_profile["formality_score"]
    # Measure bot formality inline (avoid unbound method call)
    from core.evaluation.style_profile_builder import StyleProfileBuilder
    bot_formality = StyleProfileBuilder()._compute_a8(bot_responses)["formality_score"]
    a8_score = max(0.0, 100.0 - abs(bot_formality - creator_formality) * 200)

    # A9: Catchphrase usage
    catchphrases = set(
        item["phrase"]
        for item in style_profile["A9_catchphrases"].get("catchphrases", [])
    )
    if catchphrases:
        bot_text = " ".join(bot_responses).lower()
        used = sum(1 for cp in catchphrases if cp in bot_text)
        a9_score = min(100.0, (used / len(catchphrases)) * 200)  # 50% = 100
    else:
        a9_score = 50.0

    # Aggregate (equal weight for each metric + contextual bonus)
    metric_scores = [
        a1_scores and np.mean(a1_scores) or 0.0,
        a2_score, a3_score, a4_score, a5_score,
        a6_score, a7_score, a8_score, a9_score,
    ]
    base_score = float(np.mean(metric_scores))
    # Contextual bonus: up to 10 points
    final = min(100.0, base_score * 0.9 + a2_ctx_bonus * 0.1)

    return {
        "score": round(final, 2),
        "detail": {
            "A1_length": round(float(np.mean(a1_scores)) if a1_scores else 0.0, 2),
            "A2_emoji": round(a2_score, 2),
            "A2_contextual": round(a2_ctx_bonus, 2),
            "A3_exclamations": round(a3_score, 2),
            "A4_questions": round(a4_score, 2),
            "A5_vocabulary": round(a5_score, 2),
            "A6_language": round(a6_score, 2),
            "A7_fragmentation": round(a7_score, 2),
            "A8_formality": round(a8_score, 2),
            "A9_catchphrases": round(a9_score, 2),
        },
    }


def score_s1_per_case(
    bot_response: str,
    style_profile: Dict,
    user_input: Optional[str] = None,
) -> float:
    """Score style fidelity for a single response (0-100).

    Uses probabilistic per-case scoring for binary metrics (excl, question,
    emoji) and direct range-based scoring for length, vocabulary, and
    fragmentation (A7 via newline-fragment count).
    """
    # A1: length
    a1_thresh = style_profile["A1_length"].get("threshold", [0, 10000])
    a1 = _within_range(len(bot_response), a1_thresh[0], a1_thresh[1])

    # A2: emoji — probability-weighted per-case
    creator_emoji_rate = style_profile["A2_emoji"]["global_rate"]
    has_emoji = 1.0 if EMOJI_RE.search(bot_response) else 0.0
    a2 = max(0.0, 100.0 - abs(has_emoji - creator_emoji_rate) * 100.0)

    # A2 contextual
    a2_ctx = 0.0
    if user_input:
        per_ctx = style_profile["A2_emoji"].get("per_context", {})
        ctx = classify_context(user_input)
        if ctx in per_ctx and per_ctx[ctx]["count"] >= 5:
            ctx_rate = per_ctx[ctx]["rate"]
            a2_ctx = max(0.0, 100.0 - abs(has_emoji - ctx_rate) * 100.0)

    # A3: exclamation
    creator_excl = style_profile["A3_exclamations"]["rate"]
    has_excl = 1.0 if "!" in bot_response else 0.0
    a3 = max(0.0, 100.0 - abs(has_excl - creator_excl) * 100.0)

    # A4: question
    creator_q = style_profile["A4_questions"]["rate"]
    has_q = 1.0 if "?" in bot_response else 0.0
    a4 = max(0.0, 100.0 - abs(has_q - creator_q) * 100.0)

    # A5: vocabulary overlap — scale up since single response is short
    creator_vocab = set(
        item["word"] for item in style_profile["A5_vocabulary"].get("top_50", [])
    )
    if creator_vocab:
        words = set(tokenize(bot_response))
        overlap = len(words & creator_vocab) / len(creator_vocab)
        a5 = min(100.0, overlap * 300.0)  # 33% overlap = 100
    else:
        a5 = 50.0

    # A6: language match
    creator_langs = style_profile["A6_language_ratio"]["ratios"]
    if creator_langs:
        from services.calibration_loader import detect_message_language
        creator_dominant = max(creator_langs, key=creator_langs.get)
        bot_lang = detect_message_language(bot_response) or "unknown"
        a6 = 100.0 if bot_lang == creator_dominant else max(
            0.0, 100.0 - (1.0 - creator_langs.get(bot_lang, 0.0)) * 100.0
        )
    else:
        a6 = 50.0

    # A8: formality (single response — noisy but included)
    a8_profile = style_profile["A8_formality"]
    creator_formality = a8_profile["formality_score"]
    from core.evaluation.style_profile_builder import StyleProfileBuilder
    bot_formality = StyleProfileBuilder()._compute_a8([bot_response])["formality_score"]
    a8 = max(0.0, 100.0 - abs(bot_formality - creator_formality) * 200.0)

    # A9: catchphrase
    catchphrases = set(
        item["phrase"]
        for item in style_profile["A9_catchphrases"].get("catchphrases", [])
    )
    if catchphrases:
        text_lower = bot_response.lower()
        a9 = 100.0 if any(cp in text_lower for cp in catchphrases) else 0.0
    else:
        a9 = 50.0

    # A7: fragmentation (per-case)
    a7_data = style_profile.get("A7_fragmentation", {})
    a7_thresh = a7_data.get("threshold", [1.0, 4.0])
    chunks = [c.strip() for c in bot_response.split('\n') if c.strip()]
    a7 = _within_range(max(1, len(chunks)), a7_thresh[0], a7_thresh[1])

    metrics = [a1, a2, a3, a4, a5, a6, a7, a8, a9]
    base = float(np.mean(metrics))
    final = min(100.0, base * 0.9 + a2_ctx * 0.1) if user_input else base
    return round(final, 2)


# ---------------------------------------------------------------------------
# S2: Response Quality
# ---------------------------------------------------------------------------

def _echo_rate(user_input: str, bot_response: str) -> float:
    """How much the bot copies the user input (0=none, 1=verbatim)."""
    if not user_input or not bot_response:
        return 0.0
    user_words = set(user_input.lower().split())
    bot_words = set(bot_response.lower().split())
    if not user_words:
        return 0.0
    return len(user_words & bot_words) / len(user_words)


def _detect_bot_reveal(text: str) -> bool:
    return any(p.search(text) for p in _BOT_REVEAL_PATTERNS)


def _detect_hallucination(text: str) -> bool:
    return any(p.search(text) for p in _HALLUCINATION_INDICATORS)


def score_s2_response_quality(
    test_cases: List[Dict],
    bot_responses: List[str],
) -> Dict[str, Any]:
    """Score response quality using lexical metrics + penalties.

    test_cases must have 'user_input' and 'ground_truth' keys.
    """
    if not test_cases or not bot_responses:
        return {"score": 0.0, "detail": "no data"}

    ground_truths = [tc["ground_truth"] for tc in test_cases]
    user_inputs = [tc.get("user_input", "") for tc in test_cases]

    n = len(bot_responses)

    # D-metrics: against ground truth
    chrf_scores = [_compute_chrf(b, g) for b, g in zip(bot_responses, ground_truths)]
    bleu_scores = [_compute_bleu4(b, g) for b, g in zip(bot_responses, ground_truths)]
    rouge_scores = [_compute_rouge_l(b, g) for b, g in zip(bot_responses, ground_truths)]
    meteor_scores = []
    for b, g in zip(bot_responses, ground_truths):
        m = _compute_meteor(b, g)
        meteor_scores.append(m if m is not None else 0.0)

    # C1: BERTScore (coherence with context)
    bert_scores = _compute_bertscore_batch(bot_responses, ground_truths)
    if bert_scores is None:
        bert_scores = [0.5] * n

    # D6: Semantic similarity — reuse C1 BERTScore (bot vs ground truth)
    # Both C1 and D6 target ground truth; they share the same underlying signal.
    semsim_scores = bert_scores

    # C4: Contextual relevance (BERTScore against user input — distinct signal)
    c4_scores = _compute_bertscore_batch(bot_responses, user_inputs)
    if c4_scores is None:
        c4_scores = [0.5] * n

    # C5: Self-repetition (1 - self_bleu between responses)
    if n > 1:
        self_bleu = []
        for i in range(n):
            others = [bot_responses[j] for j in range(n) if j != i]
            avg_bleu = np.mean([_compute_bleu4(bot_responses[i], o) for o in others[:5]])
            self_bleu.append(avg_bleu)
        c5_scores = [1.0 - sb for sb in self_bleu]
    else:
        c5_scores = [1.0]

    # Length ratio
    length_ratios = []
    for b, g in zip(bot_responses, ground_truths):
        if len(g) > 0:
            ratio = len(b) / len(g)
            # Score: 1.0 when ratio=1, decreasing as ratio deviates
            lr_score = max(0.0, 1.0 - abs(1.0 - ratio) * 0.5)
        else:
            lr_score = 0.5
        length_ratios.append(lr_score)

    # G-penalties (per response)
    g1_penalties = [20.0 if _detect_hallucination(b) else 0.0 for b in bot_responses]
    g2_penalties = [30.0 if _detect_bot_reveal(b) else 0.0 for b in bot_responses]
    g4_penalties = [
        min(20.0, _echo_rate(u, b) * 40.0)
        for u, b in zip(user_inputs, bot_responses)
    ]

    # Aggregate per case
    case_scores = []
    for i in range(n):
        raw = (
            bert_scores[i] * 25
            + c4_scores[i] * 5
            + c5_scores[i] * 10
            + chrf_scores[i] * 15
            + bleu_scores[i] * 10
            + rouge_scores[i] * 10
            + meteor_scores[i] * 10
            + length_ratios[i] * 15
        )
        penalty = g1_penalties[i] + g2_penalties[i] + g4_penalties[i]
        case_scores.append(max(0.0, min(100.0, raw - penalty)))

    return {
        "score": round(float(np.mean(case_scores)), 2),
        "detail": {
            "bertscore_mean": round(float(np.mean(bert_scores)), 4),
            "chrf_mean": round(float(np.mean(chrf_scores)), 4),
            "bleu4_mean": round(float(np.mean(bleu_scores)), 4),
            "rouge_l_mean": round(float(np.mean(rouge_scores)), 4),
            "meteor_mean": round(float(np.mean(meteor_scores)), 4),
            "semsim_mean": round(float(np.mean(semsim_scores)), 4),
            "c4_relevance_mean": round(float(np.mean(c4_scores)), 4),
            "self_rep_mean": round(float(np.mean(c5_scores)), 4),
            "g1_hallucination_count": sum(1 for p in g1_penalties if p > 0),
            "g2_bot_reveal_count": sum(1 for p in g2_penalties if p > 0),
            "g4_echo_mean": round(float(np.mean(g4_penalties)), 2),
            "per_case": [round(s, 2) for s in case_scores],
        },
    }


# ---------------------------------------------------------------------------
# S3: Strategic Alignment
# ---------------------------------------------------------------------------

def _jsd(p: Dict[str, float], q: Dict[str, float]) -> float:
    """Jensen-Shannon Divergence (base-2, bounded [0, 1])."""
    all_keys = sorted(set(p) | set(q))
    p_arr = np.array([p.get(k, 0.0) for k in all_keys], dtype=float)
    q_arr = np.array([q.get(k, 0.0) for k in all_keys], dtype=float)
    p_sum = p_arr.sum()
    q_sum = q_arr.sum()
    if p_sum == 0 or q_sum == 0:
        return 1.0
    p_arr = p_arr / p_sum
    q_arr = q_arr / q_sum
    m = 0.5 * (p_arr + q_arr)
    eps = 1e-12
    kl_pm = float(np.sum(np.where(p_arr > 0, p_arr * np.log2((p_arr + eps) / (m + eps)), 0.0)))
    kl_qm = float(np.sum(np.where(q_arr > 0, q_arr * np.log2((q_arr + eps) / (m + eps)), 0.0)))
    return max(0.0, min(1.0, 0.5 * kl_pm + 0.5 * kl_qm))


def score_s3_strategic_alignment(
    test_cases: List[Dict],
    bot_responses: List[str],
    strategy_map: Dict,
) -> Dict[str, Any]:
    """Score how well bot strategies match creator's strategy map.

    E1: per-case strategy match (top-2 check)
    E2: aggregate strategy distribution match (JSD)
    S3 = 0.7 * E1 + 0.3 * E2
    """
    if not test_cases or not bot_responses:
        return {"score": 0.0, "detail": "no data"}

    sm = strategy_map.get("strategy_map", strategy_map)
    case_scores = []
    bot_strategies: List[str] = []

    for tc, resp in zip(test_cases, bot_responses):
        user_input = tc.get("user_input", "")
        input_type = classify_context(user_input)

        bot_strategy = classify_strategy(user_input, resp)
        bot_strategies.append(bot_strategy)

        # Look up creator's distribution for this input type
        type_data = sm.get(input_type, {})
        dist = type_data.get("distribution", {})

        if not dist:
            case_scores.append(50.0)  # no data = neutral
            continue

        # Score: is bot strategy in creator's top 2?
        sorted_strategies = sorted(dist.items(), key=lambda x: x[1], reverse=True)
        top2 = {s[0] for s in sorted_strategies[:2]}

        if bot_strategy in top2:
            case_scores.append(100.0)
        elif bot_strategy in dist:
            case_scores.append(dist[bot_strategy] * 100)
        else:
            case_scores.append(0.0)

    e1_score = float(np.mean(case_scores))

    # E2: aggregate distribution match (JSD)
    bot_counts = Counter(bot_strategies)
    bot_total = len(bot_strategies)
    bot_dist = {s: bot_counts.get(s, 0) / bot_total for s in bot_counts}
    creator_global = strategy_map.get("global_strategy_distribution", {})
    if creator_global:
        jsd = _jsd(bot_dist, creator_global)
        e2_score = (1.0 - jsd) * 100.0
    else:
        e2_score = 50.0

    final_score = 0.7 * e1_score + 0.3 * e2_score

    return {
        "score": round(final_score, 2),
        "detail": {
            "e1_per_case_mean": round(e1_score, 2),
            "e2_distribution_match": round(e2_score, 2),
            "bot_strategy_distribution": {k: round(v, 4) for k, v in bot_dist.items()},
            "per_case": [round(s, 1) for s in case_scores],
            "mean": round(final_score, 2),
        },
    }


# ---------------------------------------------------------------------------
# S4: Adaptation
# ---------------------------------------------------------------------------

def _trust_segment_for_case(tc: Dict) -> Optional[str]:
    """Extract trust segment from test case metadata."""
    from core.evaluation.adaptation_profiler import _trust_segment
    trust = tc.get("trust_score", tc.get("trust", None))
    if trust is None:
        return None
    return _trust_segment(float(trust))


def score_s4_adaptation(
    test_cases: List[Dict],
    bot_responses: List[str],
    adaptation_profile: Dict,
) -> Dict[str, Any]:
    """Score if bot adapts style to match creator per trust segment.

    Uses two signals:
    - Proximity: per-case style match against creator's segment profile (primary)
    - Directional: does the bot shift style in the same direction as creator (bonus)

    Blends 60% proximity + 40% directional when both available.
    """
    if not test_cases or not bot_responses:
        return {"score": 0.0, "detail": "no data"}

    # --- Proximity scores (per-case segment fit) ---
    has_segments = bool(adaptation_profile.get("segments"))
    proximity_scores = []
    for tc, resp in zip(test_cases, bot_responses):
        trust = tc.get("trust_score", tc.get("trust", None))
        if trust is not None and has_segments:
            proximity_scores.append(
                score_s4_per_case(resp, float(trust), adaptation_profile)
            )

    # --- Directional scores (cross-segment trend match) ---
    adapt = adaptation_profile.get("adaptation", {})
    directions = adapt.get("directions", {})
    direction_scores = []
    valid_segs = []

    if directions and adapt.get("status") != "insufficient_segments":
        by_segment: Dict[str, List[str]] = defaultdict(list)
        for tc, resp in zip(test_cases, bot_responses):
            seg = _trust_segment_for_case(tc)
            if seg:
                by_segment[seg].append(resp)

        ordered = ["UNKNOWN", "KNOWN", "CLOSE", "INTIMATE"]
        valid_segs = [s for s in ordered if s in by_segment and len(by_segment[s]) >= 3]

        if len(valid_segs) >= 2:
            bot_metrics = {}
            for seg in valid_segs:
                resps = by_segment[seg]
                bot_metrics[seg] = {
                    "length_mean": np.mean([len(r) for r in resps]),
                    "emoji_rate": sum(1 for r in resps if EMOJI_RE.search(r)) / len(resps),
                    "exclamation_rate": sum(1 for r in resps if "!" in r) / len(resps),
                    "question_rate": sum(1 for r in resps if "?" in r) / len(resps),
                }

            for metric_name in ["length_mean", "emoji_rate", "exclamation_rate", "question_rate"]:
                creator_dir = directions.get(metric_name, {}).get("direction", "neutral")
                if creator_dir == "neutral":
                    direction_scores.append(50.0)
                    continue

                bot_vals = [bot_metrics[s][metric_name] for s in valid_segs]
                if len(bot_vals) < 2:
                    direction_scores.append(50.0)
                    continue

                x = np.arange(len(bot_vals), dtype=float)
                slope = np.polyfit(x, np.array(bot_vals, dtype=float), 1)[0]

                if creator_dir == "increases_with_trust" and slope > 0:
                    direction_scores.append(100.0)
                elif creator_dir == "decreases_with_trust" and slope < 0:
                    direction_scores.append(100.0)
                elif abs(slope) < 0.01:
                    direction_scores.append(50.0)
                else:
                    direction_scores.append(0.0)

    # --- Blend scores ---
    has_proximity = len(proximity_scores) > 0
    has_directional = len(direction_scores) > 0

    if has_proximity and has_directional:
        prox_mean = float(np.mean(proximity_scores))
        dir_mean = float(np.mean(direction_scores))
        score = 0.6 * prox_mean + 0.4 * dir_mean
        mode = "blended"
    elif has_proximity:
        score = float(np.mean(proximity_scores))
        mode = "proximity_only"
    elif has_directional:
        score = float(np.mean(direction_scores))
        mode = "directional_only"
    else:
        return {"score": 50.0, "detail": "no adaptation data available"}

    score = max(0.0, min(100.0, score))

    detail: Dict[str, Any] = {"mode": mode}
    if has_proximity:
        detail["proximity_mean"] = round(float(np.mean(proximity_scores)), 2)
        detail["proximity_n"] = len(proximity_scores)
    if has_directional:
        detail["per_metric"] = {
            m: round(s, 1)
            for m, s in zip(
                ["length", "emoji", "exclamation", "question"],
                direction_scores,
            )
        }
        detail["segments_used"] = valid_segs

    return {"score": round(score, 2), "detail": detail}


def score_s4_per_case(
    bot_response: str,
    trust_score: float,
    adaptation_profile: Dict,
) -> float:
    """Score segment-fit for a single response (0-100).

    Unlike aggregate S4 (which measures directional adaptation across segments),
    per-case S4 measures proximity: does this response match the creator's style
    for the specific trust segment of this conversation?
    """
    from core.evaluation.adaptation_profiler import _trust_segment
    segment = _trust_segment(trust_score)
    if segment is None:
        return 50.0

    segments = adaptation_profile.get("segments", {})
    seg_data = segments.get(segment)
    if not seg_data or seg_data.get("message_count", 0) < 10:
        return 50.0  # insufficient data for this segment

    # Compute 4 bot metrics for this single response
    has_emoji = 1.0 if EMOJI_RE.search(bot_response) else 0.0
    has_excl = 1.0 if "!" in bot_response else 0.0
    has_q = 1.0 if "?" in bot_response else 0.0

    # A1: length vs segment P10/P90
    a1_len = seg_data.get("A1_length", {})
    a1 = _within_range(
        len(bot_response),
        a1_len.get("P10", 0),
        a1_len.get("P90", 10000),
    )

    # A2: emoji rate proximity
    seg_emoji_rate = seg_data.get("A2_emoji_rate", 0.5)
    a2 = max(0.0, 100.0 - abs(has_emoji - seg_emoji_rate) * 100.0)

    # A3: exclamation rate proximity
    seg_excl_rate = seg_data.get("A3_exclamation_rate", 0.5)
    a3 = max(0.0, 100.0 - abs(has_excl - seg_excl_rate) * 100.0)

    # A4: question rate proximity
    seg_q_rate = seg_data.get("A4_question_rate", 0.5)
    a4 = max(0.0, 100.0 - abs(has_q - seg_q_rate) * 100.0)

    # F2: vocabulary diversity proximity
    seg_vocab_div = seg_data.get("A5_vocab_diversity")
    if seg_vocab_div is not None:
        bot_tokens = tokenize(bot_response)
        bot_vocab_div = len(set(bot_tokens)) / max(len(bot_tokens), 1)
        a5 = max(0.0, 100.0 - abs(bot_vocab_div - seg_vocab_div) * 200.0)
    else:
        a5 = 50.0

    # F3: length adaptation (isolated)
    seg_length_mean = a1_len.get("mean", 50.0)
    f3 = max(0.0, 100.0 - min(100.0, abs(len(bot_response) - seg_length_mean) / max(seg_length_mean, 1.0) * 100.0))

    return round(float(np.mean([a1, a2, a3, a4, a5, f3])), 2)


# ---------------------------------------------------------------------------
# J: Cognitive Fidelity (J1 Memory Recall, J2 Multi-turn Consistency)
# ---------------------------------------------------------------------------

_FACT_RE = re.compile(
    r'\b\d{1,2}[:/h]\d{2}\b'          # times: 10:45, 16h30
    r'|\b\d+\s*[€$]\b'                 # prices: 97€
    r'|€\s*\d+'
    r'|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b',  # dates: 15/3, 15/03/2026
    re.UNICODE,
)
# Proper nouns: capitalized words 4+ chars after a space (not sentence-initial)
_NAME_RE = re.compile(r'(?<=\s)[A-Z][a-zà-ú]{3,}')
_COMMON_WORDS = frozenset({
    "hola", "como", "pero", "para", "este", "esta", "estos", "estas",
    "mira", "vale", "bueno", "pues", "bien", "claro", "clar", "molt",
    "tranqui", "gracias", "gràcies", "tota", "també", "quan", "perquè",
    "después", "antes", "ahora", "todo", "todas", "todos", "nada",
})


def score_j1_memory_recall(
    test_cases: List[Dict],
    bot_responses: List[str],
) -> Dict[str, Any]:
    """Score whether bot references facts from conversation history.

    For test cases that have conversation_history or prior user_inputs,
    extract key facts (numbers, names, dates) and check if bot response
    references them when contextually appropriate.
    """
    if not test_cases or not bot_responses:
        return {"score": 50.0, "detail": "no data"}

    # Group by username to detect multi-turn
    by_user: Dict[str, List[int]] = defaultdict(list)
    for i, tc in enumerate(test_cases):
        username = tc.get("username", f"anon_{i}")
        by_user[username].append(i)

    scored_cases = []
    for username, idxs in by_user.items():
        if len(idxs) < 2:
            continue
        # Accumulate facts from previous turns
        accumulated_facts: set = set()
        for pos, idx in enumerate(idxs):
            if pos == 0:
                # First turn: extract facts but don't score
                user_msg = test_cases[idx].get("user_input", "")
                facts = set(_FACT_RE.findall(user_msg))
                names = set(_NAME_RE.findall(user_msg))
                for f in facts:
                    if len(f) > 2:
                        accumulated_facts.add(f.lower())
                for n in names:
                    if n.lower() not in _COMMON_WORDS and len(n) > 3:
                        accumulated_facts.add(n.lower())
                continue
            if not accumulated_facts:
                continue
            # Check if bot response references any accumulated fact
            resp_lower = bot_responses[idx].lower() if idx < len(bot_responses) else ""
            matched = sum(1 for f in accumulated_facts if f in resp_lower)
            score = min(100.0, (matched / len(accumulated_facts)) * 100.0)
            scored_cases.append(score)
            # Add new facts from this turn
            user_msg = test_cases[idx].get("user_input", "")
            facts = set(_FACT_RE.findall(user_msg))
            names = set(_NAME_RE.findall(user_msg))
            for f in facts:
                if len(f) > 2:
                    accumulated_facts.add(f.lower())
            for n in names:
                if n.lower() not in _COMMON_WORDS and len(n) > 3:
                    accumulated_facts.add(n.lower())

    if not scored_cases:
        return {"score": 50.0, "detail": "no multi-turn data"}

    return {
        "score": round(float(np.mean(scored_cases)), 2),
        "detail": {
            "cases_scored": len(scored_cases),
            "mean": round(float(np.mean(scored_cases)), 2),
        },
    }


def score_j2_multiturn_consistency(
    bot_responses: List[str],
    style_profile: Dict,
) -> Dict[str, Any]:
    """Score style consistency across all bot responses in a run.

    Measures whether the bot maintains consistent persona by comparing
    the variance in its style metrics against the creator's own variance.
    Low divergence from creator's variance = high consistency.
    """
    if len(bot_responses) < 5:
        return {"score": 50.0, "detail": "insufficient responses (need >= 5)"}

    # Compute per-response style metrics
    lengths = [float(len(r)) for r in bot_responses]
    emoji_flags = [1.0 if EMOJI_RE.search(r) else 0.0 for r in bot_responses]
    q_flags = [1.0 if "?" in r else 0.0 for r in bot_responses]
    excl_flags = [1.0 if "!" in r else 0.0 for r in bot_responses]

    # Bot variance
    bot_length_std = float(np.std(lengths))
    bot_emoji_rate = float(np.mean(emoji_flags))
    bot_q_rate = float(np.mean(q_flags))

    # Creator variance from profile
    creator_length_std = style_profile.get("A1_length", {}).get("std", 50.0)
    creator_emoji_rate = style_profile.get("A2_emoji", {}).get("global_rate", 0.5)
    creator_q_rate = style_profile.get("A4_questions", {}).get("rate", 0.3)

    # Score: closeness of bot's variance/rates to creator's
    # Length std: closer to creator's std = better
    if creator_length_std > 0:
        length_score = max(0.0, 100.0 - abs(bot_length_std - creator_length_std) / creator_length_std * 50.0)
    else:
        length_score = 50.0

    # Rate proximity (bot's aggregate rate vs creator's)
    emoji_score = max(0.0, 100.0 - abs(bot_emoji_rate - creator_emoji_rate) * 200.0)
    q_score = max(0.0, 100.0 - abs(bot_q_rate - creator_q_rate) * 200.0)

    # Exclamation consistency
    bot_excl_rate = float(np.mean(excl_flags))
    creator_excl_rate = style_profile.get("A3_exclamations", {}).get("rate", 0.3)
    excl_score = max(0.0, 100.0 - abs(bot_excl_rate - creator_excl_rate) * 200.0)

    # Self-consistency: low coefficient of variation in length = more robotic.
    # But too high CV = chaotic. Score peaks when bot CV matches creator CV.
    bot_cv = bot_length_std / max(float(np.mean(lengths)), 1.0)
    creator_cv = creator_length_std / max(style_profile.get("A1_length", {}).get("mean", 50.0), 1.0)
    cv_score = max(0.0, 100.0 - abs(bot_cv - creator_cv) * 100.0)

    final = float(np.mean([length_score, emoji_score, q_score, excl_score, cv_score]))

    return {
        "score": round(max(0.0, min(100.0, final)), 2),
        "detail": {
            "length_consistency": round(length_score, 2),
            "emoji_consistency": round(emoji_score, 2),
            "question_consistency": round(q_score, 2),
            "exclamation_consistency": round(excl_score, 2),
            "cv_match": round(cv_score, 2),
            "bot_length_std": round(bot_length_std, 2),
            "creator_length_std": round(creator_length_std, 2),
        },
    }


# ---------------------------------------------------------------------------
# Composite Scorer
# ---------------------------------------------------------------------------

class CCEEScorer:
    """Main CCEE scoring engine."""

    def __init__(
        self,
        style_profile: Dict,
        strategy_map: Dict,
        adaptation_profile: Dict,
        weights: Optional[Dict[str, float]] = None,
    ):
        self.style_profile = style_profile
        self.strategy_map = strategy_map
        self.adaptation_profile = adaptation_profile
        self.weights = weights or DEFAULT_WEIGHTS

    def score(self, test_cases: List[Dict], bot_responses: List[str]) -> Dict[str, Any]:
        """Score bot responses across all dimensions.

        Args:
            test_cases: List of dicts with keys:
                - user_input: str
                - ground_truth: str
                - trust_score: float (optional, for S4)
            bot_responses: List of bot response strings

        Returns:
            Dict with S1-S4 + J1/J2 scores, composite, and details.
        """
        s1 = score_s1_style_fidelity(
            bot_responses, self.style_profile, test_cases
        )
        s2 = score_s2_response_quality(test_cases, bot_responses)
        s3 = score_s3_strategic_alignment(
            test_cases, bot_responses, self.strategy_map
        )
        s4 = score_s4_adaptation(
            test_cases, bot_responses, self.adaptation_profile
        )
        j1 = score_j1_memory_recall(test_cases, bot_responses)
        j2 = score_j2_multiturn_consistency(bot_responses, self.style_profile)
        j_score = 0.5 * j1["score"] + 0.5 * j2["score"]

        composite = (
            self.weights.get("S1", 0.25) * s1["score"]
            + self.weights.get("S2", 0.20) * s2["score"]
            + self.weights.get("S3", 0.25) * s3["score"]
            + self.weights.get("S4", 0.15) * s4["score"]
            + self.weights.get("J", 0.15) * j_score
        )

        return {
            "S1_style_fidelity": s1,
            "S2_response_quality": s2,
            "S3_strategic_alignment": s3,
            "S4_adaptation": s4,
            "J1_memory_recall": j1,
            "J2_multiturn_consistency": j2,
            "J_cognitive_fidelity": round(j_score, 2),
            "composite": round(composite, 2),
            "weights": self.weights,
        }

    def compare_to_baseline(
        self,
        current_scores: List[float],
        baseline_scores: List[float],
    ) -> Dict[str, Any]:
        """Compare current run to baseline using Wilcoxon + Cliff's delta."""
        if len(current_scores) < 5 or len(baseline_scores) < 5:
            return {"status": "insufficient_data"}

        stat, p_value = wilcoxon_signed_rank(current_scores, baseline_scores)
        d = cliffs_delta(current_scores, baseline_scores)
        mag = cliff_magnitude(d)

        if p_value < 0.05:
            if d > 0:
                verdict = "IMPROVES"
            else:
                verdict = "HURTS"
        else:
            verdict = "NO_EFFECT"

        return {
            "verdict": verdict,
            "wilcoxon_stat": round(stat, 4),
            "p_value": round(p_value, 6),
            "cliffs_delta": round(d, 4),
            "effect_size": mag,
            "current_mean": round(float(np.mean(current_scores)), 2),
            "baseline_mean": round(float(np.mean(baseline_scores)), 2),
        }
