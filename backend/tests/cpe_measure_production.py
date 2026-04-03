"""
CPE — Production Baseline Measurement (Post-Deploy).

Measures the CURRENT production pipeline state after deploying 80+ bug fixes
and 14 system optimizations. Uses the REAL production agent (Gemini Flash-Lite
primary, GPT-4o-mini fallback) — not the ablation DeepInfra/Qwen pipeline.

Active production config:
  USE_COMPRESSED_DOC_D=true
  ENABLE_STYLE_NORMALIZER=true
  ENABLE_MEMORY_ENGINE=true
  ENABLE_DNA_AUTO_CREATE=false / ENABLE_DNA_TRIGGERS=false / ENABLE_DNA_AUTO_ANALYZE=false
  ENABLE_QUESTION_REMOVAL=false / ENABLE_EVALUATOR_FEEDBACK=false / ENABLE_RERANKING=false

Protocol:
  - 50 test cases × 3 runs = 150 observations
  - Text-only ground truth (audio/sticker excluded)
  - Conversation context from test case turns ONLY (no full DB history, prevents session bleed)
  - L1 (9 style metrics) + L2 (chrF++, BLEU-4, ROUGE-L, METEOR, len_ratio, SemSim)
  - L3 (BERTScore F1, repetition_rate, hallucination_rate)
  - Wilcoxon signed-rank + Cliff's delta vs locked Layer 2 baseline
  - 5 diverse cases for human evaluation with full context budget breakdown

Usage:
    railway run python3.11 tests/cpe_measure_production.py --creator iris_bertran
    railway run python3.11 tests/cpe_measure_production.py --creator iris_bertran --runs 1
    railway run python3.11 tests/cpe_measure_production.py --creator iris_bertran --evaluate-only

Output:
    tests/cpe_data/{creator}/sweep/production_baseline_postdeploy.json
"""

import argparse
import asyncio
import json
import logging
import math
import os
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Suppress verbose pipeline noise
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cpe_prod")
logger.setLevel(logging.INFO)

# Rate limit delay between LLM calls (Gemini Flash-Lite limits)
RATE_LIMIT_DELAY = 2.0

# Hallucination pattern (same as ablation scripts)
_HALLU_RE = re.compile(
    r"\b(disponible en|puedes encontrar|te recomiendo|en nuestra|"
    r"visita (nuestra|la) (web|página|tienda)|www\.|https?://|"
    r"precio es de|cuesta \d|€\d|\d+€)\b",
    re.IGNORECASE,
)

_MEDIA_PLACEHOLDERS = {
    "[audio]", "[sticker]", "[photo]", "[foto]", "[video]",
    "[reel]", "[story]", "[historia]", "[archivo]", "[attachment]",
    "audio", "sticker", "photo", "foto", "video",
    "👍", "❤️", "😂", "🔥", "😮", "😢", "😡", "🎉",
    "ha enviado un audio", "ha enviado una foto", "ha enviado un video",
    "sent an audio", "sent a photo", "sent a video",
    "sent an attachment", "ha enviado un sticker",
}


# =============================================================================
# TEXT METRICS — reused from ablation scripts
# =============================================================================

def _count_sentences(text: str) -> int:
    if not text:
        return 0
    return len(re.findall(r"[.!?]+", text)) or 1


def _text_metrics(text: str) -> Dict[str, float]:
    if not text:
        return {
            "char_len": 0, "has_emoji": 0, "has_excl": 0,
            "q_rate": 0, "sentence_count": 0,
        }
    emoji_pat = re.compile(
        "[\U00010000-\U0010FFFF"
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\u2600-\u26FF\u2700-\u27BF]",
        re.UNICODE,
    )
    has_emoji = 1 if emoji_pat.search(text) else 0
    has_excl = 1 if "!" in text else 0
    q_rate = 1 if "?" in text else 0
    return {
        "char_len": len(text),
        "has_emoji": has_emoji,
        "has_excl": has_excl,
        "q_rate": q_rate,
        "sentence_count": _count_sentences(text),
    }


def _chrf(hyp: str, ref: str) -> float:
    if not hyp or not ref:
        return 0.0
    h_chars = set(hyp)
    r_chars = set(ref)
    inter = h_chars & r_chars
    if not inter:
        return 0.0
    prec = len(inter) / len(h_chars)
    rec = len(inter) / len(r_chars)
    if prec + rec == 0:
        return 0.0
    return 2 * prec * rec / (prec + rec)


def _bleu4(hyp: str, ref: str) -> float:
    if not hyp or not ref:
        return 0.0
    h_toks = hyp.lower().split()
    r_toks = ref.lower().split()
    if not h_toks or not r_toks:
        return 0.0
    scores = []
    for n in range(1, 5):
        h_ng = [tuple(h_toks[i:i + n]) for i in range(len(h_toks) - n + 1)]
        r_ng = [tuple(r_toks[i:i + n]) for i in range(len(r_toks) - n + 1)]
        if not h_ng:
            return 0.0
        r_count = defaultdict(int)
        for g in r_ng:
            r_count[g] += 1
        clip = 0
        for g in h_ng:
            if r_count[g] > 0:
                clip += 1
                r_count[g] -= 1
        scores.append(clip / len(h_ng))
    if any(s == 0 for s in scores):
        return 0.0
    log_avg = sum(math.log(s) for s in scores) / 4
    bp = min(1.0, len(h_toks) / len(r_toks)) if r_toks else 0.0
    return round(bp * math.exp(log_avg), 4)


def _lcs_len(a: list, b: list) -> int:
    la, lb = len(a), len(b)
    dp = [0] * (lb + 1)
    for i in range(la):
        prev = 0
        for j in range(lb):
            tmp = dp[j + 1]
            dp[j + 1] = prev + 1 if a[i] == b[j] else max(dp[j + 1], dp[j])
            prev = tmp
    return dp[lb]


def _rouge_l(hyp: str, ref: str) -> float:
    if not hyp or not ref:
        return 0.0
    h_toks = hyp.lower().split()
    r_toks = ref.lower().split()
    if not h_toks or not r_toks:
        return 0.0
    lcs = _lcs_len(h_toks, r_toks)
    prec = lcs / len(h_toks)
    rec = lcs / len(r_toks)
    if prec + rec == 0:
        return 0.0
    return round(2 * prec * rec / (prec + rec), 4)


def _meteor(hyp: str, ref: str) -> float:
    if not hyp or not ref:
        return 0.0
    h_toks = set(hyp.lower().split())
    r_toks = set(ref.lower().split())
    matches = h_toks & r_toks
    if not matches:
        return 0.0
    prec = len(matches) / len(hyp.split())
    rec = len(matches) / len(ref.split())
    if prec + rec == 0:
        return 0.0
    f = 10 * prec * rec / (9 * prec + rec)
    return round(f, 4)


def _repetition_rate(text: str) -> bool:
    if not text or len(text) < 15:
        return False
    words = text.lower().split()
    if len(words) < 4:
        return False
    pairs = [f"{words[i]}_{words[i+1]}" for i in range(len(words) - 1)]
    unique = set(pairs)
    return len(unique) < len(pairs) * 0.5


def _is_text_ground_truth(gt: str) -> bool:
    if not gt or not gt.strip():
        return False
    gt_lower = gt.strip().lower()
    if gt_lower in _MEDIA_PLACEHOLDERS:
        return False
    if gt_lower.startswith("[") and gt_lower.endswith("]") and len(gt_lower) < 40:
        inner = gt_lower[1:-1].strip()
        media_words = {"audio", "sticker", "photo", "foto", "video", "image",
                       "reel", "story", "historia", "archivo", "attachment"}
        if any(w in inner for w in media_words):
            return False
    return True


def _get_conversation_context(case_id: str, conversations: list) -> list:
    for tc in conversations:
        if tc.get("id") == case_id:
            turns = tc.get("turns", [])
            return turns[-5:] if turns else []
    return []


# =============================================================================
# L1 — 9 style metrics
# =============================================================================

def compute_l1(responses: List[str], baseline_metrics: dict) -> dict:
    if not responses:
        return {"score": "0/9", "passed": 0, "metrics": {}}
    valid = [r for r in responses if r]
    if not valid:
        return {"score": "0/9", "passed": 0, "metrics": {}}

    bot_metrics = {
        "char_len": statistics.mean([len(r) for r in valid]),
        "has_emoji_pct": sum(1 for r in valid if re.search(
            r"[\U00010000-\U0010FFFF\U0001F600-\U0001F64F"
            r"\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
            r"\U0001F1E0-\U0001F1FF\u2600-\u26FF\u2700-\u27BF]",
            r, re.UNICODE,
        )) / len(valid) * 100,
        "has_excl_pct": sum(1 for r in valid if "!" in r) / len(valid) * 100,
        "q_rate_pct": sum(1 for r in valid if "?" in r) / len(valid) * 100,
        "sentence_count": statistics.mean([_count_sentences(r) for r in valid]),
        "multi_line_pct": sum(1 for r in valid if "\n" in r) / len(valid) * 100,
        "caps_pct": sum(1 for r in valid if any(c.isupper() for c in r)) / len(valid) * 100,
        "avg_word_count": statistics.mean([len(r.split()) for r in valid]),
        "empty_rate_pct": (len(responses) - len(valid)) / len(responses) * 100,
    }

    # Reference targets from real Iris data (fallback if no baseline_metrics)
    iris_targets = {
        "char_len":        (13, 120),    # 13-120 chars typical range
        "has_emoji_pct":   (5, 40),      # 23% real median; 5-40% acceptable
        "has_excl_pct":    (0, 15),      # 2% real; under 15% OK
        "q_rate_pct":      (5, 30),      # 14% real
        "sentence_count":  (1, 3),       # 1-2 sentences typical
        "multi_line_pct":  (0, 30),
        "caps_pct":        (0, 20),
        "avg_word_count":  (2, 20),
        "empty_rate_pct":  (0, 10),
    }

    passed = 0
    metrics_detail = {}
    for m, bot_val in bot_metrics.items():
        lo, hi = iris_targets.get(m, (0, 9999))
        ok = lo <= bot_val <= hi
        if ok:
            passed += 1
        metrics_detail[m] = {"bot": round(bot_val, 2), "in_range": ok}

    return {
        "score": f"{passed}/9",
        "passed": passed,
        "metrics": metrics_detail,
    }


# =============================================================================
# L2 — 6 metrics
# =============================================================================

def compute_l2(results: List[Dict]) -> dict:
    pairs = [
        (r["bot_response"], r["ground_truth"])
        for r in results
        if r.get("bot_response") and r.get("ground_truth") and _is_text_ground_truth(r["ground_truth"])
    ]
    if not pairs:
        return {"n_pairs": 0, "chrf": 0, "bleu4": 0, "rouge_l": 0, "meteor": 0, "len_ratio": 0, "semsim": 0}
    chrf_s   = [_chrf(b, g)    for b, g in pairs]
    bleu4_s  = [_bleu4(b, g)   for b, g in pairs]
    rouge_s  = [_rouge_l(b, g) for b, g in pairs]
    meteor_s = [_meteor(b, g)  for b, g in pairs]
    lenrat_s = [len(b) / len(g) if len(g) > 0 else 0.0 for b, g in pairs]
    return {
        "n_pairs":     len(pairs),
        "chrf":        round(statistics.mean(chrf_s),   4),
        "bleu4":       round(statistics.mean(bleu4_s),  4),
        "rouge_l":     round(statistics.mean(rouge_s),  4),
        "meteor":      round(statistics.mean(meteor_s), 4),
        "len_ratio":   round(statistics.mean(lenrat_s), 4),
        "_chrf_scores":    chrf_s,
        "_bleu4_scores":   bleu4_s,
        "_rougel_scores":  rouge_s,
        "_meteor_scores":  meteor_s,
        "_lenrat_scores":  lenrat_s,
    }


def compute_semsim(results: List[Dict]) -> float:
    try:
        from sentence_transformers import SentenceTransformer, util
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        pairs = [
            (r["bot_response"], r["ground_truth"])
            for r in results
            if r.get("bot_response") and r.get("ground_truth") and _is_text_ground_truth(r["ground_truth"])
        ]
        if not pairs:
            return 0.0
        bots = [b or "." for b, _ in pairs]
        gts  = [g or "." for _, g in pairs]
        emb_b = model.encode(bots, convert_to_tensor=True)
        emb_g = model.encode(gts,  convert_to_tensor=True)
        sims = [util.cos_sim(emb_b[i], emb_g[i]).item() for i in range(len(bots))]
        return round(statistics.mean(sims), 4)
    except ImportError:
        return 0.0


# =============================================================================
# L3 — BERTScore + repetition + hallucination
# =============================================================================

def compute_l3_quick(results: List[Dict]) -> dict:
    bots        = [r["bot_response"] for r in results]
    rep_flags   = [_repetition_rate(b) for b in bots]
    hallu_flags = [bool(_HALLU_RE.search(b)) for b in bots]
    return {
        "rep_rate_pct":   round(sum(rep_flags)   / len(rep_flags)   * 100, 2) if rep_flags else 0,
        "hallu_rate_pct": round(sum(hallu_flags) / len(hallu_flags) * 100, 2) if hallu_flags else 0,
        "_rep_flags":     [int(f) for f in rep_flags],
        "_hallu_flags":   [int(f) for f in hallu_flags],
    }


def compute_l3_bertscore(results: List[Dict]) -> dict:
    pairs = [
        (r["bot_response"], r["ground_truth"])
        for r in results
        if r.get("bot_response") and r.get("ground_truth") and _is_text_ground_truth(r["ground_truth"])
    ]
    if not pairs:
        return {"coherence_bert_f1": 0.0, "_bert_f1_scores": []}
    bots = [b if b else "." for b, _ in pairs]
    gts  = [g if g else "." for _, g in pairs]
    try:
        from bert_score import score as bert_score
        _, _, F1 = bert_score(
            cands=bots, refs=gts,
            model_type="xlm-roberta-large", lang="es",
            batch_size=16, verbose=False, rescale_with_baseline=True,
        )
        f1_scores = [F1[i].item() for i in range(len(bots))]
        return {
            "coherence_bert_f1": round(statistics.mean(f1_scores), 4),
            "_bert_f1_scores": f1_scores,
        }
    except ImportError:
        logger.warning("bert-score not installed, skipping BERTScore")
        return {"coherence_bert_f1": 0.0, "_bert_f1_scores": []}


# =============================================================================
# STATISTICAL TESTS
# =============================================================================

def _norm_sf(z: float) -> float:
    t    = 1.0 / (1.0 + 0.2316419 * z)
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
    return math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi) * poly


def wilcoxon_signed_rank(x: List[float], y: List[float]) -> Tuple[float, float]:
    diffs = [xi - yi for xi, yi in zip(x, y)]
    diffs = [d for d in diffs if d != 0]
    n = len(diffs)
    if n < 2:
        return 0.0, 1.0
    abs_diffs = sorted(enumerate(abs(d) for d in diffs), key=lambda t: t[1])
    ranked = [0.0] * len(abs_diffs)
    i = 0
    while i < len(abs_diffs):
        j = i
        while j < len(abs_diffs) - 1 and abs_diffs[j + 1][1] == abs_diffs[i][1]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranked[abs_diffs[k][0]] = avg_rank
        i = j + 1
    w_plus  = sum(r for d, r in zip(diffs, ranked) if d > 0)
    w_minus = sum(r for d, r in zip(diffs, ranked) if d < 0)
    w_stat  = min(w_plus, w_minus)
    mean_w  = n * (n + 1) / 4
    var_w   = n * (n + 1) * (2 * n + 1) / 24
    if var_w == 0:
        return w_stat, 1.0
    z = abs((w_stat - mean_w) / math.sqrt(var_w))
    p = 2 * _norm_sf(z)
    return round(w_stat, 2), round(p, 4)


def cliffs_delta(x: List[float], y: List[float]) -> float:
    n = 0
    for xi in x:
        for yi in y:
            n += (1 if xi > yi else -1 if xi < yi else 0)
    return round(n / (len(x) * len(y)), 4) if x and y else 0.0


def cliffs_magnitude(d: float) -> str:
    ad = abs(d)
    if ad < 0.147:
        return "negligible"
    if ad < 0.33:
        return "small"
    if ad < 0.474:
        return "medium"
    return "large"


def extract_per_case_from_results(all_run_results: List[List[Dict]]) -> Dict[str, List[float]]:
    """Compute per-case metric vectors averaged across runs."""
    per_case: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for run_results in all_run_results:
        for r in run_results:
            cid = r["id"]
            bot = r.get("bot_response", "")
            gt  = r.get("ground_truth", "")
            tm  = _text_metrics(bot)
            per_case[cid]["char_len"].append(tm["char_len"])
            per_case[cid]["has_emoji"].append(tm["has_emoji"])
            per_case[cid]["has_excl"].append(tm["has_excl"])
            per_case[cid]["q_rate"].append(tm["q_rate"])
            per_case[cid]["sentence_count"].append(tm["sentence_count"])
            if bot and gt:
                per_case[cid]["chrf"].append(_chrf(bot, gt))
                per_case[cid]["bleu4"].append(_bleu4(bot, gt))
                per_case[cid]["rouge_l"].append(_rouge_l(bot, gt))
                per_case[cid]["meteor"].append(_meteor(bot, gt))
                per_case[cid]["len_ratio"].append(len(bot) / len(gt) if gt else 0)

    aggregated: Dict[str, List[float]] = defaultdict(list)
    for cid, metrics in per_case.items():
        for m, vals in metrics.items():
            aggregated[m].append(statistics.mean(vals))
    return dict(aggregated)


def _load_baseline_per_case(baseline_path: Path) -> Dict[str, List[float]]:
    """Load per-case metric vectors from a locked baseline JSON file."""
    if not baseline_path.exists():
        return {}
    try:
        d = json.loads(baseline_path.read_text())
        # Try to reconstruct from run files referenced in the baseline
        # The locked baseline stores run files alongside the summary
        run_results_list = []
        for run_data in d.get("_run_results", []):
            run_results_list.append(run_data)
        if run_results_list:
            return extract_per_case_from_results(run_results_list)

        # Fallback: build from l2 per-run scores (less precise, no per-case)
        # Return empty so comparison gracefully skips
        logger.warning("Locked baseline has no _run_results — per-case comparison unavailable")
        return {}
    except Exception as e:
        logger.warning("Failed to load baseline: %s", e)
        return {}


def compare_vs_baseline(
    test_pc: Dict[str, List[float]],
    base_pc: Dict[str, List[float]],
) -> Dict[str, Dict]:
    metrics = ["chrf", "bleu4", "rouge_l", "meteor", "len_ratio",
               "char_len", "has_emoji", "has_excl", "q_rate", "sentence_count"]
    comparison = {}
    for m in metrics:
        if m not in test_pc or m not in base_pc:
            continue
        x, y = test_pc[m], base_pc[m]
        n = min(len(x), len(y))
        if n < 3:
            continue
        x, y = x[:n], y[:n]
        w, p = wilcoxon_signed_rank(x, y)
        d = cliffs_delta(x, y)
        comparison[m] = {
            "w": w, "p": p,
            "cliff_d": d,
            "magnitude": cliffs_magnitude(d),
            "mean_prod": round(statistics.mean(x), 4),
            "mean_base": round(statistics.mean(y), 4),
            "delta": round(statistics.mean(x) - statistics.mean(y), 4),
        }
    return comparison


# =============================================================================
# LEAD RESOLUTION — resolve test case username → platform_user_id for agent
# =============================================================================

def _resolve_platform_user_id(lead_username: str, creator_id: str) -> str:
    """Resolve test case lead_username to platform_user_id."""
    if not lead_username:
        return "unknown"
    # WhatsApp leads: username IS the platform_user_id
    if lead_username.startswith("wa_"):
        return lead_username
    # IG: try to resolve via DB
    try:
        from api.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            row = session.execute(
                text("""
                    SELECT l.platform_user_id FROM leads l
                    JOIN creators c ON l.creator_id = c.id
                    WHERE c.name = :cname
                      AND (l.username = :uname OR l.platform_user_id = :uname)
                    LIMIT 1
                """),
                {"cname": creator_id, "uname": lead_username},
            ).fetchone()
            if row and row[0]:
                return row[0]
        finally:
            session.close()
    except Exception as e:
        logger.debug("DB resolve failed for %s: %s", lead_username, e)
    return lead_username  # fallback


def _build_history_metadata(turns: List[Dict], test_input: str) -> List[Dict]:
    """Convert test case turns to history format for the agent.

    Maps 'iris'/'assistant' → 'assistant', 'lead'/'user' → 'user'.
    Excludes the test_input itself (the current message being tested).
    Returns CURRENT SESSION turns only — no DB history loaded.
    """
    history = []
    for turn in turns:
        role = turn.get("role", "")
        content = turn.get("content", "")
        if not content:
            continue
        if role in ("iris", "assistant"):
            history.append({"role": "assistant", "content": content})
        elif role in ("lead", "user"):
            history.append({"role": "user", "content": content})
    # Remove last user message if it matches test_input (agent will get it as message=)
    if history and history[-1].get("role") == "user" and history[-1].get("content") == test_input:
        history = history[:-1]
    # Keep last 10 turns (5 exchanges)
    return history[-10:]


# =============================================================================
# PRODUCTION RUN — phases 1-4, skip post-processing (no DB writes)
# =============================================================================

async def run_production_single(
    test_cases: List[Dict],
    agent,
    creator_id: str,
    run_idx: int,
    delay: float = RATE_LIMIT_DELAY,
) -> Tuple[List[Dict], Dict[str, int]]:
    """One run of the production pipeline across all test cases.

    Calls phases 1-4 of DMResponderAgentV2:
      1. _phase_detection  (input guards, sensitive, pool, frustration, context)
      2. _phase_memory_and_context  (DNA, memory, RAG, episodic, few-shot)
      3. _phase_llm_generation  (Gemini Flash-Lite → GPT-4o-mini fallback)
    Skips phase 5 (_phase_postprocessing) to avoid DB side effects.
    """
    counts: Dict[str, int] = defaultdict(int)
    results = []

    logger.info("[Run %d] production pipeline | cases=%d", run_idx, len(test_cases))

    for i, tc in enumerate(test_cases, 1):
        message = tc["test_input"]
        ground_truth = tc.get("ground_truth", "")
        lead_username = tc.get("lead_username", "")
        t0 = time.monotonic()

        bot_response = ""
        source = "llm"
        pool_category = None
        pool_conf = 0.0
        dna_injected = False
        memory_recalled = False
        rag_fired = False
        doc_d_chars = 0
        dna_chars = 0
        memory_chars = 0
        rag_chars = 0
        episodic_chars = 0
        conv_history_chars = 0
        total_context_chars = 0
        max_context_chars = int(os.getenv("MAX_CONTEXT_CHARS", "8000"))
        system_prompt_chars = 0
        tokens_in = 0
        tokens_out = 0
        model_used = ""

        # Resolve sender_id from lead_username
        sender_id = await asyncio.to_thread(_resolve_platform_user_id, lead_username, creator_id)

        # Build metadata: pass history from test case ONLY (current session context)
        turns = tc.get("turns", [])
        history = _build_history_metadata(turns, message)
        metadata = {
            "history": history,
            # Disable DB history fetch: we use test case turns exclusively
            "_cpe_test_mode": True,
        }
        cognitive_metadata: Dict[str, Any] = {}

        try:
            # Phase 1: detection (input guards, sensitive, pool, frustration, context)
            detection = await agent._phase_detection(message, sender_id, metadata, cognitive_metadata)

            if detection.pool_response:
                # Pool fast-path: use the pool response directly
                bot_response = detection.pool_response.content.strip()
                source = "pool"
                counts["pool_matched"] += 1
                if hasattr(detection.pool_response, "metadata"):
                    pool_category = detection.pool_response.metadata.get("category", "pool")
                    pool_conf = detection.pool_response.metadata.get("confidence", 0.0)
            else:
                # Phase 2-3: memory + context + RAG
                context = await agent._phase_memory_and_context(
                    message, sender_id, metadata, cognitive_metadata, detection
                )

                # Extract context budget metrics from ContextBundle
                doc_d_chars = len(getattr(agent, "style_prompt", "") or "")
                dna_chars = len(context.dna_context or "")
                memory_chars = len(context.memory_context or "")
                rag_chars = len(context.rag_context or "")
                conv_history_chars = sum(len(m.get("content", "")) for m in (context.history or []))
                system_prompt_chars = len(context.system_prompt or "")
                total_context_chars = cognitive_metadata.get("context_total_chars", system_prompt_chars)
                episodic_chars = cognitive_metadata.get("episodic_chars", 0)

                dna_injected = bool(context.dna_context)
                memory_recalled = cognitive_metadata.get("memory_recalled", False)
                rag_fired = bool(context.rag_results)

                if dna_injected:
                    counts["dna_injected"] += 1
                if memory_recalled:
                    counts["memory_recalled"] += 1
                if rag_fired:
                    counts["rag_fired"] += 1

                # Phase 4: LLM generation (Gemini → GPT-4o-mini fallback)
                counts["llm_calls"] += 1
                llm_response = await agent._phase_llm_generation(
                    message, "", context.system_prompt, context, cognitive_metadata, detection
                )

                if llm_response and not llm_response.is_empty:
                    bot_response = llm_response.content.strip()
                    model_used = getattr(llm_response, "model", "")
                    tokens_in = getattr(llm_response, "tokens_used", 0)
                    source = "llm"
                    counts["llm_ok"] += 1
                else:
                    source = "llm_empty"
                    counts["llm_empty"] += 1

        except Exception as e:
            logger.warning("[Run %d] Error case %d (%s): %s", run_idx, i, tc["id"], e)
            source = "error"
            counts["errors"] += 1

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        results.append({
            "id":                  tc["id"],
            "test_input":          message,
            "ground_truth":        ground_truth,
            "bot_response":        bot_response,
            "category":            tc.get("category", ""),
            "language":            tc.get("language", ""),
            "lead_username":       lead_username,
            "run":                 run_idx,
            "source":              source,
            "elapsed_ms":          elapsed_ms,
            "tokens_in":           tokens_in,
            "tokens_out":          tokens_out,
            "model_used":          model_used,
            "dna_injected":        dna_injected,
            "memory_recalled":     memory_recalled,
            "rag_fired":           rag_fired,
            "pool_category":       pool_category,
            "pool_conf":           pool_conf,
            # Context budget breakdown
            "context": {
                "doc_d_chars":        doc_d_chars,
                "dna_chars":          dna_chars,
                "memory_chars":       memory_chars,
                "rag_chars":          rag_chars,
                "episodic_chars":     episodic_chars,
                "conv_history_chars": conv_history_chars,
                "total_context_chars": total_context_chars,
                "system_prompt_chars": system_prompt_chars,
                "max_context_chars":   max_context_chars,
                "utilization_pct":     round(total_context_chars / max_context_chars * 100, 1)
                                       if max_context_chars else 0,
            },
            "cognitive_metadata": {
                k: v for k, v in cognitive_metadata.items()
                if not k.startswith("_")
            },
        })

        # Progress log
        if i % 10 == 0 or source in ("error", "llm_empty"):
            ctx_tag = f"DNA={'Y' if dna_injected else 'N'} MEM={'Y' if memory_recalled else 'N'} RAG={'Y' if rag_fired else 'N'}"
            print(f"  [{source:6}] [{i:02d}/{len(test_cases)}] {tc['id']}: {bot_response[:50]!r} [{ctx_tag}]")

        # Rate limit only for LLM calls (pool responses are instant)
        if source == "llm":
            await asyncio.sleep(delay)

    n_ok = sum(1 for r in results if r["bot_response"])
    ok_ms = [r["elapsed_ms"] for r in results if r["bot_response"] and r["elapsed_ms"] > 0]
    avg_ms = statistics.mean(ok_ms) if ok_ms else 0
    print(
        f"  Run {run_idx}: {n_ok}/{len(results)} OK | "
        f"llm={counts['llm_calls']} pool={counts['pool_matched']} "
        f"dna={counts['dna_injected']} mem={counts['memory_recalled']} "
        f"rag={counts['rag_fired']} | avg {avg_ms:.0f}ms"
    )
    return results, dict(counts)


# =============================================================================
# 5 DIVERSE CASES FOR HUMAN EVAL
# =============================================================================

def _pick_diverse_cases(all_results: List[List[Dict]], test_cases: List[Dict]) -> List[Dict]:
    """Pick 5 diverse cases for human evaluation.

    Selection criteria:
    1. Close relationship (relationship_score > 0.6 or trust in DNA)
    2. New lead (low message count or low relationship_score)
    3. Question about services/prices (category=product_inquiry/question/booking)
    4. Emotional message (category=long_personal or emotional keyword in message)
    5. Casual/short exchange (category=casual/short_response/greeting)
    """
    r1 = all_results[0] if all_results else []
    text_only = [r for r in r1 if _is_text_ground_truth(r.get("ground_truth", "")) and r.get("bot_response")]
    if not text_only:
        return []

    def _case_detail(r: Dict) -> Dict:
        tc = next((t for t in test_cases if t["id"] == r["id"]), {})
        turns = tc.get("turns", [])
        ctx = turns[-5:] if turns else []
        return {
            "id": r["id"],
            "category": r["category"],
            "language": r["language"],
            "lead_username": r["lead_username"],
            "test_input": r["test_input"],
            "ground_truth": r["ground_truth"],
            "bot_response": r["bot_response"],
            "source": r["source"],
            "dna_injected": r["dna_injected"],
            "memory_recalled": r["memory_recalled"],
            "rag_fired": r["rag_fired"],
            "context_budget": r["context"],
            "conversation_context": [
                {"role": t.get("role", ""), "content": t.get("content", "")}
                for t in ctx
            ],
        }

    cases = []
    used_ids = set()

    # 1. Close relationship (relationship_score > 0.6 OR dna_injected with trust in meta)
    for r in text_only:
        if r["id"] in used_ids:
            continue
        rel_score = r["cognitive_metadata"].get("relationship_score", 0)
        if rel_score > 0.6 or (r["dna_injected"] and rel_score > 0.5):
            cases.append({**_case_detail(r), "_selection": "close_relationship"})
            used_ids.add(r["id"])
            break

    # 2. New lead (relationship_score < 0.3 or not dna_injected)
    for r in text_only:
        if r["id"] in used_ids:
            continue
        rel_score = r["cognitive_metadata"].get("relationship_score", 999)
        if rel_score < 0.3 or not r["dna_injected"]:
            cases.append({**_case_detail(r), "_selection": "new_lead"})
            used_ids.add(r["id"])
            break

    # 3. Question about services/prices
    SERVICE_CATS = {"product_inquiry", "question", "booking", "objection"}
    SERVICE_KEYWORDS = {
        "precio", "cost", "cuánto", "cuanto", "clase", "sesion",
        "reservar", "apuntar", "horario", "plaza", "disponible",
        "servicio", "how much", "price", "book",
    }
    for r in text_only:
        if r["id"] in used_ids:
            continue
        msg_lower = r["test_input"].lower()
        if r["category"] in SERVICE_CATS or any(kw in msg_lower for kw in SERVICE_KEYWORDS):
            cases.append({**_case_detail(r), "_selection": "service_price_question"})
            used_ids.add(r["id"])
            break

    # 4. Emotional message (long_personal, or emotional keywords)
    EMOTIONAL_CATS = {"long_personal", "humor"}
    EMOTIONAL_KW = {
        "triste", "mal", "bien", "amor", "quiero", "echo de menos",
        "greu", "pena", "genial", "mola", "guay", "flipé", "increíble",
        "emocionado", "nervous", "excited", "happy", "sad", "love",
    }
    for r in text_only:
        if r["id"] in used_ids:
            continue
        msg_lower = r["test_input"].lower()
        if r["category"] in EMOTIONAL_CATS or any(kw in msg_lower for kw in EMOTIONAL_KW):
            cases.append({**_case_detail(r), "_selection": "emotional_message"})
            used_ids.add(r["id"])
            break

    # 5. Casual/short exchange
    CASUAL_CATS = {"casual", "short_response", "greeting", "thanks", "emoji_reaction"}
    for r in text_only:
        if r["id"] in used_ids:
            continue
        if r["category"] in CASUAL_CATS or len(r["test_input"]) < 30:
            cases.append({**_case_detail(r), "_selection": "casual_short"})
            used_ids.add(r["id"])
            break

    # Fill remaining slots with diverse categories not yet represented
    if len(cases) < 5:
        seen_cats = {c["category"] for c in cases}
        for r in text_only:
            if r["id"] in used_ids:
                continue
            if r["category"] not in seen_cats:
                cases.append({**_case_detail(r), "_selection": "diverse_fill"})
                used_ids.add(r["id"])
                seen_cats.add(r["category"])
            if len(cases) >= 5:
                break

    return cases[:5]


# =============================================================================
# MAIN
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="CPE Production Baseline (Post-Deploy)")
    parser.add_argument("--creator",      default="iris_bertran")
    parser.add_argument("--runs",         type=int, default=3)
    parser.add_argument("--delay",        type=float, default=RATE_LIMIT_DELAY)
    parser.add_argument("--cases",        type=int, default=50)
    parser.add_argument("--evaluate-only", action="store_true",
                        help="Skip generation; re-evaluate existing run files")
    args = parser.parse_args()

    creator_id = args.creator
    n_runs = max(1, args.runs)

    data_dir  = Path(f"tests/cpe_data/{creator_id}")
    sweep_dir = data_dir / "sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 74)
    print("CPE PRODUCTION BASELINE — POST-DEPLOY MEASUREMENT")
    print("=" * 74)
    print(f"Creator: {creator_id} | Runs: {n_runs} | Cases: {args.cases}")

    # ── Load test set ─────────────────────────────────────────────────────────
    test_set_v2 = data_dir / "test_set_v2_stratified.json"
    test_set_v1 = data_dir / "test_set.json"
    test_set_path = test_set_v2 if test_set_v2.exists() else test_set_v1
    with open(test_set_path, encoding="utf-8") as f:
        test_set = json.load(f)
    conversations = test_set.get("conversations", [])[:args.cases]
    version = test_set.get("metadata", {}).get("version", "v1")
    n_mt = sum(1 for c in conversations if c.get("is_multi_turn"))
    print(f"Test set: {len(conversations)} cases (version={version}, multi-turn={n_mt})")

    # ── Load locked baseline for comparison ───────────────────────────────────
    baseline_path = sweep_dir / "layer2_v2_baseline_locked.json"
    if not baseline_path.exists():
        print(f"WARNING: Locked baseline not found at {baseline_path}")
        print("         Comparison vs baseline will be skipped.")
    else:
        print(f"Locked baseline: {baseline_path.name}")

    # ── Load baseline metrics for L1 comparison ───────────────────────────────
    bm_path = data_dir / "baseline_metrics.json"
    baseline_metrics = json.loads(bm_path.read_text()) if bm_path.exists() else {}

    # ── Active production flags ───────────────────────────────────────────────
    prod_flags = {
        "USE_COMPRESSED_DOC_D":      os.getenv("USE_COMPRESSED_DOC_D",      "true"),
        "ENABLE_STYLE_NORMALIZER":   os.getenv("ENABLE_STYLE_NORMALIZER",    "true"),
        "ENABLE_MEMORY_ENGINE":      os.getenv("ENABLE_MEMORY_ENGINE",       "true"),
        "ENABLE_DNA_AUTO_CREATE":    os.getenv("ENABLE_DNA_AUTO_CREATE",      "false"),
        "ENABLE_DNA_TRIGGERS":       os.getenv("ENABLE_DNA_TRIGGERS",         "false"),
        "ENABLE_DNA_AUTO_ANALYZE":   os.getenv("ENABLE_DNA_AUTO_ANALYZE",     "false"),
        "ENABLE_QUESTION_REMOVAL":   os.getenv("ENABLE_QUESTION_REMOVAL",     "false"),
        "ENABLE_EVALUATOR_FEEDBACK": os.getenv("ENABLE_EVALUATOR_FEEDBACK",   "false"),
        "ENABLE_RERANKING":          os.getenv("ENABLE_RERANKING",            "false"),
        "MAX_CONTEXT_CHARS":         os.getenv("MAX_CONTEXT_CHARS",           "8000"),
        "LLM_PRIMARY_PROVIDER":      os.getenv("LLM_PRIMARY_PROVIDER",        "gemini"),
    }
    print(f"\nProduction flags: {json.dumps(prod_flags, indent=2)}")

    # ── Initialize production agent ───────────────────────────────────────────
    print(f"\nInitializing production agent for {creator_id}...")
    t_init = time.monotonic()
    try:
        from core.dm_agent_v2 import get_dm_agent
        agent = get_dm_agent(creator_id)
        print(f"Agent initialized in {int((time.monotonic() - t_init) * 1000)}ms")
        print(f"Doc D (style_prompt): {len(getattr(agent, 'style_prompt', '') or '')} chars")
    except Exception as e:
        logger.error("Failed to initialize agent: %s", e, exc_info=True)
        sys.exit(1)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = sweep_dir / "production_baseline_postdeploy.json"

    # ── GENERATION ────────────────────────────────────────────────────────────
    run_files: List[Path] = []
    all_results: List[List[Dict]] = []
    all_counts: List[dict] = []

    if args.evaluate_only:
        pattern = "prod_baseline_run*_*.json"
        for run_idx in range(1, n_runs + 1):
            files = sorted(sweep_dir.glob(f"prod_baseline_run{run_idx}_*.json"))
            if files:
                run_files.append(files[-1])
        if not run_files:
            print("ERROR: --evaluate-only but no prod_baseline_run*.json files found.")
            sys.exit(1)
        for rf in run_files:
            d = json.loads(rf.read_text())
            all_results.append(d["results"])
            all_counts.append(d.get("intercept_counts", {}))
        print(f"Evaluate-only: loaded {len(run_files)} run files")
    else:
        # Verify Gemini API key is set
        if not os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
            print("WARNING: GEMINI_API_KEY not found — Gemini calls may fail (GPT-4o-mini fallback active)")

        for run_idx in range(1, n_runs + 1):
            print(f"\n{'─' * 74}")
            print(f"RUN {run_idx}/{n_runs}")
            print(f"{'─' * 74}")

            run_results, counts = await run_production_single(
                conversations, agent, creator_id, run_idx, args.delay,
            )
            all_results.append(run_results)
            all_counts.append(counts)

            rf = sweep_dir / f"prod_baseline_run{run_idx}_{ts}.json"
            payload = {
                "ablation":       "production_baseline_postdeploy",
                "creator":        creator_id,
                "model":          "gemini-flash-lite+gpt4o-mini-fallback",
                "prod_flags":     prod_flags,
                "run":            run_idx,
                "n_cases":        len(run_results),
                "timestamp":      datetime.now(timezone.utc).isoformat(),
                "intercept_counts": counts,
                "results":        run_results,
            }
            rf.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
            run_files.append(rf)
            print(f"  Saved: {rf.name}")

    # ── EVALUATION ────────────────────────────────────────────────────────────
    print("\n" + "=" * 74)
    print("EVALUATION")
    print("=" * 74)

    # L1 per run
    l1_per_run = []
    for run_results in all_results:
        responses = [r["bot_response"] for r in run_results]
        l1 = compute_l1(responses, baseline_metrics)
        l1_per_run.append(l1)

    # L2 per run
    l2_per_run = []
    for run_results in all_results:
        l2 = compute_l2(run_results)
        l2_per_run.append(l2)

    # L3 quick per run
    l3q_per_run = []
    for run_results in all_results:
        l3q = compute_l3_quick(run_results)
        l3q_per_run.append(l3q)

    # L3 BERTScore (expensive — runs once on all concatenated results)
    print("Computing BERTScore (this takes ~2 min)...")
    l3_bert_per_run = []
    for run_results in all_results:
        l3b = compute_l3_bertscore(run_results)
        l3_bert_per_run.append(l3b)

    # Semantic similarity
    print("Computing semantic similarity...")
    semsim_per_run = [compute_semsim(rr) for rr in all_results]

    # L2 semsim extension
    for i, l2 in enumerate(l2_per_run):
        l2["semsim"] = semsim_per_run[i]

    # ── Aggregate L1 ─────────────────────────────────────────────────────────
    l1_agg = {}
    if l1_per_run and l1_per_run[0]:
        for metric_name in l1_per_run[0].get("metrics", {}):
            vals = [lr["metrics"][metric_name]["bot"] for lr in l1_per_run if "metrics" in lr]
            if vals:
                l1_agg[metric_name] = {
                    "mean": round(statistics.mean(vals), 4),
                    "std":  round(statistics.stdev(vals), 4) if len(vals) > 1 else 0,
                    "runs": vals,
                }
    l1_score_runs = [lr.get("passed", 0) for lr in l1_per_run]
    l1_score_mean = round(statistics.mean(l1_score_runs), 1) if l1_score_runs else 0

    # ── Aggregate L2 ─────────────────────────────────────────────────────────
    l2_agg = {}
    for metric_name in ["chrf", "bleu4", "rouge_l", "meteor", "len_ratio", "semsim"]:
        vals = [lr[metric_name] for lr in l2_per_run if metric_name in lr]
        if vals:
            l2_agg[metric_name] = {
                "mean": round(statistics.mean(vals), 4),
                "std":  round(statistics.stdev(vals), 4) if len(vals) > 1 else 0,
                "runs": vals,
            }

    # ── Aggregate L3 ─────────────────────────────────────────────────────────
    bert_vals = [lr["coherence_bert_f1"] for lr in l3_bert_per_run]
    rep_vals  = [lr["rep_rate_pct"]       for lr in l3q_per_run]
    hallu_vals = [lr["hallu_rate_pct"]    for lr in l3q_per_run]

    l3_agg = {
        "coherence_bert_f1": {
            "mean": round(statistics.mean(bert_vals), 4),
            "std":  round(statistics.stdev(bert_vals), 4) if len(bert_vals) > 1 else 0,
            "runs": bert_vals,
        },
        "repetition_rate_pct": {
            "mean": round(statistics.mean(rep_vals), 2),
            "std":  round(statistics.stdev(rep_vals), 2) if len(rep_vals) > 1 else 0,
            "runs": rep_vals,
        },
        "hallucination_rate_pct": {
            "mean": round(statistics.mean(hallu_vals), 2),
            "std":  round(statistics.stdev(hallu_vals), 2) if len(hallu_vals) > 1 else 0,
            "runs": hallu_vals,
        },
    }

    # ── Context injection stats ───────────────────────────────────────────────
    ctx_stats = {}
    for metric_name in ["doc_d_chars", "dna_chars", "memory_chars", "rag_chars",
                         "episodic_chars", "conv_history_chars", "total_context_chars",
                         "utilization_pct"]:
        vals = [
            r["context"][metric_name]
            for run_results in all_results
            for r in run_results
            if r.get("context") and metric_name in r["context"]
        ]
        if vals:
            ctx_stats[metric_name] = {
                "mean": round(statistics.mean(vals), 1),
                "max":  max(vals),
                "min":  min(vals),
                "nonzero_pct": round(sum(1 for v in vals if v > 0) / len(vals) * 100, 1),
            }

    # ── Intercept counts ──────────────────────────────────────────────────────
    ic_avg = {}
    if all_counts:
        all_keys = set()
        for c in all_counts:
            all_keys.update(c.keys())
        for k in sorted(all_keys):
            vals = [c.get(k, 0) for c in all_counts]
            ic_avg[k] = round(statistics.mean(vals), 1)

    # ── Statistical comparison vs locked baseline ─────────────────────────────
    print("\nStatistical comparison vs locked baseline...")
    test_pc = extract_per_case_from_results(all_results)
    base_pc = _load_baseline_per_case(baseline_path)
    stat_comparison = {}
    if base_pc:
        stat_comparison = compare_vs_baseline(test_pc, base_pc)
    else:
        print("  (Skipped — locked baseline has no per-case data for paired tests)")

    # ── 5 Diverse cases for human eval ───────────────────────────────────────
    sample_cases = _pick_diverse_cases(all_results, conversations)

    # ── Build report ─────────────────────────────────────────────────────────
    report = {
        "measurement": "production_baseline_postdeploy",
        "description": "Current production config after 80+ bug fixes and 14 system optimizations",
        "creator": creator_id,
        "model": "gemini-flash-lite+gpt4o-mini-fallback",
        "prod_flags": prod_flags,
        "n_runs": n_runs,
        "n_cases": len(conversations),
        "computed": datetime.now(timezone.utc).isoformat(),
        "baseline_reference": str(baseline_path) if baseline_path.exists() else "NOT FOUND",
        "intercept_counts_per_run": all_counts,
        "intercept_counts_avg": ic_avg,
        "context_injection_stats": ctx_stats,
        "l1": {
            "score_per_run": [lr.get("score", "?/9") for lr in l1_per_run],
            "score_mean": l1_score_mean,
            "agg_metrics": l1_agg,
            "per_run": [lr.get("metrics", {}) for lr in l1_per_run],
        },
        "l2": {
            "agg": l2_agg,
            "per_run": [{k: v for k, v in lr.items() if not k.startswith("_")} for lr in l2_per_run],
        },
        "l3": {"agg": l3_agg},
        "statistical_comparison_vs_baseline": stat_comparison,
        "sample_cases": sample_cases,
        # Store run results for future per-case paired tests
        "_run_results": [run_results for run_results in all_results],
    }

    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nSaved: {output_path}")

    # ── Print summary ─────────────────────────────────────────────────────────
    print("\n" + "=" * 74)
    print(f"  PRODUCTION BASELINE — @{creator_id} — {n_runs} runs × {len(conversations)} cases")
    print("=" * 74)

    print(f"\n  L1 Score: {l1_score_mean}/9 avg | per-run: {l1_score_runs}")
    print(f"\n  L1 Metrics (mean ± std):")
    for m, v in l1_agg.items():
        print(f"    {m:<25} {v['mean']:>8.2f} ± {v['std']:.2f}")

    print(f"\n  L2 Metrics:")
    for m, v in l2_agg.items():
        print(f"    {m:<25} {v['mean']:>8.4f} ± {v['std']:.4f}")

    print(f"\n  L3 Metrics:")
    for m, v in l3_agg.items():
        print(f"    {m:<30} {v['mean']:>8.4f} ± {v['std']:.4f}")

    print(f"\n  Context injection (avg per response):")
    for m, v in ctx_stats.items():
        print(f"    {m:<30} mean={v['mean']:>7.0f}  nonzero={v['nonzero_pct']:.0f}%")

    print(f"\n  Intercept counts (avg per run):")
    for k, v in ic_avg.items():
        print(f"    {k:<30} {v:.1f}")

    if stat_comparison:
        print(f"\n  Statistical comparison vs Layer 2 locked baseline:")
        print(f"  {'Metric':<20} {'Δ':>9} {'p':>8} {'Cliff d':>9} {'Magnitude':<12}")
        print(f"  {'-'*20} {'-'*9} {'-'*8} {'-'*9} {'-'*12}")
        for m, v in stat_comparison.items():
            sig = "* " if v["p"] < 0.05 else "  "
            print(
                f"  {m:<20} {v['delta']:>+9.4f} {v['p']:>8.4f}{sig}"
                f" {v['cliff_d']:>+9.4f} {v['magnitude']:<12}"
            )

    print(f"\n  5 Sample Cases for Human Evaluation:")
    print(f"  {'─' * 70}")
    for sc in sample_cases:
        sel_tag = sc.get("_selection", "?")
        dna_tag = " [DNA]" if sc.get("dna_injected") else ""
        mem_tag = " [MEM]" if sc.get("memory_recalled") else ""
        rag_tag = " [RAG]" if sc.get("rag_fired") else ""
        print(f"\n  [{sc['category']}] [{sel_tag}]{dna_tag}{mem_tag}{rag_tag}")
        print(f"  Lead: @{sc['lead_username']} | {sc['id']}")

        ctx = sc.get("conversation_context", [])
        if ctx:
            print(f"  Context (last {len(ctx)} turns from current session):")
            for t in ctx:
                role_tag = "👤" if t["role"] in ("user", "lead") else "🤖"
                print(f"    {role_tag} {t['content'][:100]}")

        budget = sc.get("context_budget", {})
        print(f"  Message: {sc['test_input'][:80]}")
        print(f"  Bot:     {sc['bot_response'][:80]}")
        print(f"  GT:      {sc['ground_truth'][:80]}")
        print(f"  Context: DocD={budget.get('doc_d_chars',0)} DNA={budget.get('dna_chars',0)} "
              f"Mem={budget.get('memory_chars',0)} RAG={budget.get('rag_chars',0)} "
              f"Episodic={budget.get('episodic_chars',0)} History={budget.get('conv_history_chars',0)}")
        print(f"           Total={budget.get('total_context_chars',0)} / "
              f"MAX={budget.get('max_context_chars',8000)} "
              f"({budget.get('utilization_pct',0):.0f}% utilized)")

    print("\n" + "=" * 74)
    print(f"  Output: {output_path}")
    print("=" * 74)


if __name__ == "__main__":
    asyncio.run(main())
