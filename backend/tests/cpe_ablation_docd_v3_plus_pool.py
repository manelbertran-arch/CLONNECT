"""
CPE Ablation — Doc D v3 + Pool Matching (#5).

Systems active:
  ✓ Compressed Doc D (personality system prompt)
  ✓ Pool Matching (try_pool_response for iris_bertran)
Systems OFF:
  ✗ Memory / RAG / few-shot / style normalizer / sensitive detection / post-processing

Routing:
  message → try_pool_response(iris_bertran)
    └── matched   → return pool response directly  (skip LLM)
    └── unmatched → DeepInfra(Qwen3-14B, Doc D v3 system prompt)

Methodology:
  - PersonaGym (EMNLP 2025) + AbGen (ACL 2025)
  - 3 runs × 50 cases = 150 observations
  - L1 (9 metrics) + L2 (5 metrics) + L3 (3: BERTScore + rep + hallucination)
  - Wilcoxon signed-rank + Cliff's delta vs NAKED and vs DOC D v3 ONLY

Usage:
    railway run python3 tests/cpe_ablation_docd_v3_plus_pool.py --creator iris_bertran
    railway run python3 tests/cpe_ablation_docd_v3_plus_pool.py --creator iris_bertran --evaluate-only

Output:
    tests/cpe_data/{creator}/sweep/docd_v3_plus_pool_run{N}_{ts}.json  — raw per run
    tests/cpe_data/{creator}/sweep/docd_v3_plus_pool.json              — final report
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
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DEEPINFRA_TIMEOUT", "30")
os.environ.setdefault("DEEPINFRA_CB_THRESHOLD", "999")

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cpe_docd_plus_pool")
logger.setLevel(logging.INFO)

DEFAULT_MODEL    = "Qwen/Qwen3-14B"
RATE_LIMIT_DELAY = 1.2

_MEDIA_PLACEHOLDERS = {
    "sent an attachment", "sent a photo", "sent a video",
    "shared a reel", "shared a story", "sent a voice message",
    "[image]", "[video]", "[sticker]", "[🏷️ sticker]",
    "[audio]", "[🎤 audio]", "[🎤 audio message]",
    "[📷 photo]", "[📷 foto]", "[📸 photo]", "[📸 foto]",
    "audio message", "mensaje de voz",
    "envió un archivo adjunto", "envió una foto", "envió un video",
    "compartió un reel", "compartió una historia",
}


def _is_text_ground_truth(gt: str) -> bool:
    """Return True if ground_truth is real text (not an audio/sticker/media placeholder)."""
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
    """Extract last 5 turns from the test case's conversation history."""
    for tc in conversations:
        if tc.get("id") == case_id:
            turns = tc.get("turns", [])
            return turns[-5:] if turns else []
    return []


# =============================================================================
# LOAD SYSTEM PROMPT — compressed Doc D  (identical to layer1 script)
# =============================================================================

def load_system_prompt(creator_id: str) -> str:
    try:
        from services.creator_profile_service import get_profile
        data = get_profile(creator_id, "compressed_doc_d")
        if data and data.get("text"):
            logger.info("Loaded compressed_doc_d from DB profile cache")
            return data["text"]
    except Exception as e:
        logger.warning("DB profile lookup failed: %s", e)

    try:
        from core.dm.compressed_doc_d import build_compressed_doc_d
        logger.info("DB profile not found — building compressed_doc_d from scratch")
        return build_compressed_doc_d(creator_id)
    except Exception as e:
        raise RuntimeError(f"Cannot load compressed Doc D for '{creator_id}': {e}") from e


# =============================================================================
# POOL MATCHING INIT
# =============================================================================

def load_pool_variator(creator_id: str):
    """Initialise ResponseVariatorV2 with creator-specific calibration pools.

    try_pool_response uses _extraction_pools[creator_id] when creator_id is passed.
    If personality_loader returns empty pools (all DRAFT / no extraction record),
    we inject the calibration response_pools directly so pool matching is functional
    for ablation purposes.
    """
    from services.response_variator_v2 import ResponseVariatorV2
    variator = ResponseVariatorV2()

    # Attempt personality_loader extraction first
    variator._load_extraction_pools(creator_id)

    # If extraction pools empty (iris_bertran has DRAFT pools only), inject calibration pools
    if not variator._extraction_pools.get(creator_id):
        cal_path = REPO_ROOT / "calibrations" / f"{creator_id}.json"
        if cal_path.exists():
            with open(cal_path, encoding="utf-8") as f:
                cal_data = json.load(f)
            cal_pools = cal_data.get("response_pools", {})
            if cal_pools:
                variator._extraction_pools[creator_id] = cal_pools
                # Mark as attempted so _load_extraction_pools doesn't overwrite
                variator._extraction_attempted.add(creator_id)
                total = sum(len(v) for v in cal_pools.values())
                logger.info(
                    "Injected calibration pools for '%s': %d categories, %d responses",
                    creator_id, len(cal_pools), total,
                )
                print(f"  Pool variator: {len(cal_pools)} categories, {total} responses from calibration")
    else:
        total = sum(len(v) for v in variator._extraction_pools[creator_id].values())
        logger.info("Pool extraction pools for '%s': %d responses", creator_id, total)
        print(f"  Pool variator: extraction pools loaded ({total} responses)")

    return variator


def load_calibration(creator_id: str) -> dict:
    """Load creator calibration JSON for pool context_soft_max + baseline."""
    cal_path = REPO_ROOT / "calibrations" / f"{creator_id}.json"
    if cal_path.exists():
        with open(cal_path, encoding="utf-8") as f:
            return json.load(f)
    logger.warning("Calibration not found at %s — using empty dict", cal_path)
    return {}


# =============================================================================
# METRICS  (copied verbatim from cpe_ablation_layer1_doc_d.py)
# =============================================================================

_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\u2600-\u27BF\U0001F900-\U0001F9FF][\U0001F3FB-\U0001F3FF\uFE0F]?"
)
_CA_MARKERS = re.compile(
    r"\b(tinc|estic|però|molt|doncs|també|perquè|això|vull|puc|"
    r"gràcies|gracies|bon dia|bona tarda|bona nit|setmana|"
    r"dimarts|dijous|dissabte|diumenge|nosaltres|puguis|vulguis)\b",
    re.IGNORECASE,
)
_ES_MARKERS = re.compile(
    r"\b(tengo|estoy|pero|mucho|entonces|también|porque|quiero|"
    r"puedo|necesito|bueno|gracias|vale|claro|genial|"
    r"miércoles|jueves|sábado|domingo|nosotros)\b",
    re.IGNORECASE,
)


def _text_metrics(text: str) -> dict:
    if not text:
        return {"length": 0, "has_emoji": False, "has_question": False,
                "has_exclamation": False, "language": "unknown", "words": set()}
    words  = set(re.findall(r"\b\w+\b", text.lower()))
    emojis = _EMOJI_RE.findall(text)
    ca_hits = len(_CA_MARKERS.findall(text))
    es_hits = len(_ES_MARKERS.findall(text))
    lang = "ca-es" if (ca_hits and es_hits) else ("ca" if ca_hits > es_hits else "es")
    return {
        "length":          len(text),
        "has_emoji":       len(emojis) > 0,
        "has_question":    "?" in text,
        "has_exclamation": "!" in text,
        "language":        lang,
        "words":           words,
    }


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\b\w+\b", text.lower())


def _count_sentences(text: str) -> int:
    text = text.strip()
    if not text:
        return 0
    parts = re.split(r"[.!?]+(?:\s|$)", text)
    return max(1, len([p for p in parts if p.strip()]))


def _distinct2(texts: List[str]) -> float:
    all_bgs: List[Tuple] = []
    unique_bgs: set = set()
    for t in texts:
        toks = _tokenize(t)
        bgs  = list(zip(toks, toks[1:]))
        all_bgs.extend(bgs)
        unique_bgs.update(bgs)
    return len(unique_bgs) / len(all_bgs) if all_bgs else 0.0


def _chrf(candidate: str, reference: str, n: int = 6, beta: float = 2.0) -> float:
    if not candidate or not reference:
        return 0.0
    def _char_ngrams(text: str, order: int) -> Counter:
        ctr: Counter = Counter()
        for w in text.split():
            w = " " + w + " "
            for i in range(len(w) - order + 1):
                ctr[w[i:i + order]] += 1
        return ctr
    precs, recs = [], []
    for order in range(1, n + 1):
        ref_ng  = _char_ngrams(reference, order)
        cand_ng = _char_ngrams(candidate, order)
        tc, tr  = sum(cand_ng.values()), sum(ref_ng.values())
        if tc == 0 or tr == 0:
            precs.append(0.0); recs.append(0.0); continue
        m = sum(min(cnt, ref_ng[ng]) for ng, cnt in cand_ng.items())
        precs.append(m / tc); recs.append(m / tr)
    p = statistics.mean(precs) if precs else 0.0
    r = statistics.mean(recs)  if recs  else 0.0
    if p + r == 0:
        return 0.0
    return round((1 + beta ** 2) * p * r / (beta ** 2 * p + r), 4)


def _bleu4(candidate: str, reference: str) -> float:
    cand_tok = _tokenize(candidate)
    ref_tok  = _tokenize(reference)
    if not cand_tok or not ref_tok:
        return 0.0
    precs = []
    for n in range(1, 5):
        c_ng = Counter(tuple(cand_tok[i:i+n]) for i in range(len(cand_tok)-n+1))
        r_ng = Counter(tuple(ref_tok[i:i+n])  for i in range(len(ref_tok)-n+1))
        matches = sum(min(cnt, r_ng[ng]) for ng, cnt in c_ng.items())
        total   = sum(c_ng.values())
        if total == 0:
            return 0.0
        precs.append(matches / total)
    if any(p == 0 for p in precs):
        return 0.0
    log_avg = sum(math.log(p) for p in precs) / 4
    bp = min(1.0, len(cand_tok) / len(ref_tok))
    return round(bp * math.exp(log_avg), 4)


def _rouge_l(candidate: str, reference: str) -> float:
    cand_tok = _tokenize(candidate)
    ref_tok  = _tokenize(reference)
    m, n     = len(ref_tok), len(cand_tok)
    if m == 0 or n == 0:
        return 0.0
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            dp[i][j] = (dp[i-1][j-1] + 1) if ref_tok[i-1] == cand_tok[j-1] \
                       else max(dp[i-1][j], dp[i][j-1])
    lcs = dp[m][n]
    if lcs == 0:
        return 0.0
    p = lcs / n; r = lcs / m
    return round(2 * p * r / (p + r), 4)


def _meteor(candidate: str, reference: str) -> float:
    from nltk.translate.meteor_score import single_meteor_score
    c, r = _tokenize(candidate), _tokenize(reference)
    if not c or not r:
        return 0.0
    return round(single_meteor_score(r, c), 4)


def _repetition_rate(text: str) -> bool:
    toks = _tokenize(text)
    if len(toks) < 8:
        return False
    ngs = list(zip(toks, toks[1:], toks[2:], toks[3:]))
    return len(ngs) != len(set(ngs))


_HALLU_RE = re.compile(
    r"https?://|www\.|\.com|\.es|\.org|amazon|instagram\.com|linktr\.ee|"
    r"shopify|booking|aliexpress|temu|zara|shein|nike|adidas", re.I
)


# =============================================================================
# L1 — 9 metrics
# =============================================================================

def compute_l1(responses: List[str], baseline_metrics: dict) -> dict:
    bm        = baseline_metrics.get("metrics", {})
    iris_emj  = bm.get("emoji",       {}).get("emoji_rate_pct",       22.0)
    iris_excl = bm.get("punctuation", {}).get("exclamation_rate_pct",  1.8)
    iris_q    = bm.get("punctuation", {}).get("question_rate_pct",    14.2)
    iris_lmed = bm.get("length",      {}).get("char_median",           26.0)
    iris_lmn  = bm.get("length",      {}).get("char_mean",             95.2)
    iris_ca   = next((d["pct"] for d in bm.get("languages", {}).get("detected", []) if d["lang"] == "ca"), 43.5)
    iris_top  = set(w[0] for w in bm.get("vocabulary", {}).get("top_50", [])[:50])
    iris_sc   = 1.81
    iris_d2   = 0.934

    n = len(responses)
    if not n:
        return {}

    all_m: List[dict] = []
    all_bot_words: set = set()
    for text in responses:
        m = _text_metrics(text)
        all_bot_words |= m.pop("words", set())
        all_m.append(m)

    bot_emj  = sum(1 for m in all_m if m["has_emoji"])       / n * 100
    bot_excl = sum(1 for m in all_m if m["has_exclamation"]) / n * 100
    bot_q    = sum(1 for m in all_m if m["has_question"])    / n * 100
    bot_lmn  = statistics.mean(m["length"] for m in all_m)
    bot_lmed = statistics.median(m["length"] for m in all_m)
    bot_ca   = sum(1 for m in all_m if m.get("language") in ("ca", "ca-es")) / n * 100
    voc_jac  = len(iris_top & all_bot_words) / len(iris_top | all_bot_words) if (iris_top | all_bot_words) else 0
    bot_sc   = statistics.mean(_count_sentences(r) for r in responses)
    bot_d2   = _distinct2(responses)

    def chk_pct(bot_v, iris_v, tol=20):  return abs(bot_v - iris_v) <= tol
    def chk_num(bot_v, iris_v, tol=30):  return abs(bot_v - iris_v) / iris_v * 100 <= tol if iris_v else False
    def chk_pct10(bot_v, iris_v):         return abs(bot_v - iris_v) <= 10

    results = {
        "has_emoji_pct":    {"bot": round(bot_emj,  2), "iris": iris_emj,  "pass": chk_pct(bot_emj,  iris_emj)},
        "has_excl_pct":     {"bot": round(bot_excl, 2), "iris": iris_excl, "pass": chk_pct10(bot_excl, iris_excl)},
        "q_rate_pct":       {"bot": round(bot_q,    2), "iris": iris_q,    "pass": chk_pct(bot_q,    iris_q)},
        "len_mean_chars":   {"bot": round(bot_lmn,  2), "iris": iris_lmn,  "pass": chk_num(bot_lmn,  iris_lmn)},
        "len_median_chars": {"bot": round(bot_lmed, 2), "iris": iris_lmed, "pass": chk_num(bot_lmed, iris_lmed)},
        "ca_rate_pct":      {"bot": round(bot_ca,   2), "iris": iris_ca,   "pass": chk_pct(bot_ca,   iris_ca)},
        "vocab_jac_pct":    {"bot": round(voc_jac * 100, 2), "iris": 5.0,  "pass": chk_pct10(voc_jac * 100, 5.0)},
        "sentence_count":   {"bot": round(bot_sc,   3), "iris": iris_sc,   "pass": chk_num(bot_sc,   iris_sc)},
        "distinct_2":       {"bot": round(bot_d2,   4), "iris": iris_d2,   "pass": chk_num(bot_d2,   iris_d2)},
    }
    passed = sum(1 for v in results.values() if v["pass"])
    return {"score": f"{passed}/9", "passed": passed, "metrics": results}


# =============================================================================
# L2 — 5 metrics
# =============================================================================

def compute_l2(results: List[Dict]) -> dict:
    pairs    = [(r["bot_response"], r["ground_truth"]) for r in results
                if r.get("bot_response") and r.get("ground_truth")]
    chrf_s   = [_chrf(b, g)    for b, g in pairs]
    bleu4_s  = [_bleu4(b, g)   for b, g in pairs]
    rouge_s  = [_rouge_l(b, g)  for b, g in pairs]
    meteor_s = [_meteor(b, g)   for b, g in pairs]
    lenrat_s = [len(b) / len(g) if len(g) > 0 else 0.0 for b, g in pairs]
    n = len(pairs)
    return {
        "n_pairs":         n,
        "chrf":            round(statistics.mean(chrf_s),   4),
        "bleu4":           round(statistics.mean(bleu4_s),  4),
        "rouge_l":         round(statistics.mean(rouge_s),  4),
        "meteor":          round(statistics.mean(meteor_s), 4),
        "len_ratio":       round(statistics.mean(lenrat_s), 4),
        "_chrf_scores":    chrf_s,
        "_bleu4_scores":   bleu4_s,
        "_rougel_scores":  rouge_s,
        "_meteor_scores":  meteor_s,
        "_lenrat_scores":  lenrat_s,
    }


# =============================================================================
# L3 — repetition + hallucination
# =============================================================================

def compute_l3_quick(results: List[Dict]) -> dict:
    bots        = [r["bot_response"] for r in results]
    rep_flags   = [_repetition_rate(b) for b in bots]
    hallu_flags = [bool(_HALLU_RE.search(b)) for b in bots]
    return {
        "rep_rate_pct":   round(sum(rep_flags)   / len(rep_flags)   * 100, 2),
        "hallu_rate_pct": round(sum(hallu_flags) / len(hallu_flags) * 100, 2),
        "_rep_flags":     [int(f) for f in rep_flags],
        "_hallu_flags":   [int(f) for f in hallu_flags],
    }


# =============================================================================
# STATISTICAL TESTS — Wilcoxon + Cliff's delta
# =============================================================================

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

    mean_w = n * (n + 1) / 4
    var_w  = n * (n + 1) * (2 * n + 1) / 24
    if var_w == 0:
        return w_stat, 1.0
    z = abs((w_stat - mean_w) / math.sqrt(var_w))
    p = 2 * _norm_sf(z)
    return round(w_stat, 2), round(p, 4)


def _norm_sf(z: float) -> float:
    t    = 1.0 / (1.0 + 0.2316419 * z)
    poly = t * (0.319381530
              + t * (-0.356563782
              + t * (1.781477937
              + t * (-1.821255978
              + t * 1.330274429))))
    pdf  = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
    return pdf * poly


def cliffs_delta(x: List[float], y: List[float]) -> float:
    n = len(x)
    if n == 0:
        return 0.0
    greater = sum(1 for xi, yi in zip(x, y) if xi > yi)
    less    = sum(1 for xi, yi in zip(x, y) if xi < yi)
    return round((greater - less) / n, 4)


def cliffs_magnitude(d: float) -> str:
    a = abs(d)
    if a < 0.147: return "negligible"
    if a < 0.330: return "small"
    if a < 0.474: return "medium"
    return "large"


# =============================================================================
# LOAD PER-CASE SCORES from existing run files (for Wilcoxon)
# =============================================================================

def _extract_per_case_from_files(run_files: List[Path]) -> Dict[str, List[float]]:
    per_case: Dict[str, List[float]] = {
        "has_emoji": [], "has_excl": [], "q_rate": [], "char_len": [],
        "is_ca": [], "sentence_count": [], "chrf": [], "bleu4": [],
        "rouge_l": [], "meteor": [], "len_ratio": [], "rep_rate": [],
    }
    for rf in run_files:
        data    = json.loads(rf.read_text())
        results = data["results"]
        for r in results:
            bot = r.get("bot_response", "")
            gt  = r.get("ground_truth", "")
            m   = _text_metrics(bot)
            per_case["has_emoji"].append(float(m["has_emoji"]))
            per_case["has_excl"].append(float(m["has_exclamation"]))
            per_case["q_rate"].append(float(m["has_question"]))
            per_case["char_len"].append(float(m["length"]))
            per_case["is_ca"].append(float(m["language"] in ("ca", "ca-es")))
            per_case["sentence_count"].append(float(_count_sentences(bot)))
            per_case["chrf"].append(_chrf(bot, gt))
            per_case["bleu4"].append(_bleu4(bot, gt))
            per_case["rouge_l"].append(_rouge_l(bot, gt))
            per_case["meteor"].append(_meteor(bot, gt))
            per_case["len_ratio"].append(len(bot) / len(gt) if len(gt) > 0 else 0.0)
            per_case["rep_rate"].append(float(_repetition_rate(bot)))
    return per_case


def load_naked_per_case(sweep_dir: Path) -> Dict[str, List[float]]:
    run_files = sorted(sweep_dir.glob("naked_zero_run*_20260331_193231.json"))
    if not run_files:
        run_files = sorted(sweep_dir.glob("naked_zero_run*.json"))
    return _extract_per_case_from_files(run_files)


def load_layer1_per_case(sweep_dir: Path) -> Dict[str, List[float]]:
    """Load Doc D v3 only (layer1) per-case scores — most recent 3-run set."""
    # Group by timestamp suffix, pick the latest complete set of 3
    from collections import defaultdict
    by_ts: Dict[str, List[Path]] = defaultdict(list)
    for f in sorted(sweep_dir.glob("layer1_doc_d_run*.json")):
        # filename: layer1_doc_d_run{N}_{ts}.json
        parts = f.stem.split("_")
        ts = "_".join(parts[-2:])   # e.g. 20260401_170808
        by_ts[ts].append(f)

    # Pick timestamp with exactly 3 run files (complete set), most recent first
    complete = sorted(
        [(ts, files) for ts, files in by_ts.items() if len(files) == 3],
        key=lambda t: t[0],
        reverse=True,
    )
    if not complete:
        logger.warning("No complete layer1_doc_d 3-run set found — stat comparison vs Doc D v3 will be skipped")
        return {}

    ts, run_files = complete[0]
    logger.info("Using layer1_doc_d runs from %s (%d files)", ts, len(run_files))
    return _extract_per_case_from_files(run_files)


def extract_per_case_from_results(run_results_list: List[List[Dict]]) -> Dict[str, List[float]]:
    per_case: Dict[str, List[float]] = {
        "has_emoji": [], "has_excl": [], "q_rate": [], "char_len": [],
        "is_ca": [], "sentence_count": [], "chrf": [], "bleu4": [],
        "rouge_l": [], "meteor": [], "len_ratio": [], "rep_rate": [],
    }
    for results in run_results_list:
        for r in results:
            bot = r.get("bot_response", "")
            gt  = r.get("ground_truth", "")
            m   = _text_metrics(bot)
            per_case["has_emoji"].append(float(m["has_emoji"]))
            per_case["has_excl"].append(float(m["has_exclamation"]))
            per_case["q_rate"].append(float(m["has_question"]))
            per_case["char_len"].append(float(m["length"]))
            per_case["is_ca"].append(float(m["language"] in ("ca", "ca-es")))
            per_case["sentence_count"].append(float(_count_sentences(bot)))
            per_case["chrf"].append(_chrf(bot, gt))
            per_case["bleu4"].append(_bleu4(bot, gt))
            per_case["rouge_l"].append(_rouge_l(bot, gt))
            per_case["meteor"].append(_meteor(bot, gt))
            per_case["len_ratio"].append(len(bot) / len(gt) if len(gt) > 0 else 0.0)
            per_case["rep_rate"].append(float(_repetition_rate(bot)))
    return per_case


# =============================================================================
# GENERATION — Doc D v3 + Pool Matching
# =============================================================================

async def generate_run(
    test_cases: List[Dict],
    system_prompt: str,
    variator,
    calibration: dict,
    creator_id: str,
    model: str,
    run_idx: int,
    delay: float = RATE_LIMIT_DELAY,
) -> List[Dict]:
    """
    One run. For each message:
      1. try_pool_response(iris_bertran) — if matched, return pool response (no LLM)
      2. if not matched — call DeepInfra with Doc D v3 system prompt
    """
    from core.providers.deepinfra_provider import call_deepinfra

    pool_hit = 0
    llm_hit  = 0

    logger.info(
        "[Run %d] docd_v3+pool | model=%s | cases=%d | prompt_len=%d",
        run_idx, model, len(test_cases), len(system_prompt),
    )

    results = []
    for i, tc in enumerate(test_cases, 1):
        lead = tc["test_input"]
        t0   = time.monotonic()
        bot_response = ""
        source       = "llm"
        pool_cat     = None
        pool_conf    = 0.0
        tokens_in    = 0
        tokens_out   = 0

        # ── 1. Pool matching ────────────────────────────────────────────────
        try:
            match = variator.try_pool_response(
                lead_message  = lead,
                min_confidence= 0.7,
                calibration   = calibration,
                turn_index    = i,
                conv_id       = f"ablation_run{run_idx}_{i}",
                creator_id    = creator_id,
            )
            if match.matched and match.response:
                bot_response = match.response.strip()
                source       = "pool"
                pool_cat     = match.category
                pool_conf    = round(match.confidence, 3)
                pool_hit    += 1
        except Exception as e:
            logger.warning("[Run %d] pool error case %d: %s", run_idx, i, e)

        # ── 2. LLM fallback ─────────────────────────────────────────────────
        if not bot_response:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": lead},
            ]
            resp = None
            try:
                resp = await call_deepinfra(
                    messages,
                    max_tokens=150,
                    temperature=0.7,
                    model=model,
                )
            except Exception as e:
                logger.warning("[Run %d] LLM error case %d: %s", run_idx, i, e)

            bot_response = resp["content"].strip() if resp else ""
            tokens_in    = resp.get("tokens_in",  0) if resp else 0
            tokens_out   = resp.get("tokens_out", 0) if resp else 0
            llm_hit     += 1

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        results.append({
            "id":            tc["id"],
            "test_input":    lead,
            "ground_truth":  tc.get("ground_truth", ""),
            "bot_response":  bot_response,
            "category":      tc.get("category", ""),
            "language":      tc.get("language", ""),
            "elapsed_ms":    elapsed_ms,
            "tokens_in":     tokens_in,
            "tokens_out":    tokens_out,
            "run":           run_idx,
            "source":        source,          # "pool" | "llm"
            "pool_category": pool_cat,
            "pool_conf":     pool_conf,
        })

        if i % 10 == 0 or not bot_response:
            tag = "POOL" if source == "pool" else ("ERR" if not bot_response else "LLM")
            print(f"  [{tag}] [{i:02d}/{len(test_cases)}] {tc['id']}: {bot_response[:60]!r}")

        if source == "llm":
            await asyncio.sleep(delay)  # rate-limit only LLM calls

    n_ok = sum(1 for r in results if r["bot_response"])
    ok_ms = [r["elapsed_ms"] for r in results if r["bot_response"] and r["elapsed_ms"] > 0]
    avg_ms = statistics.mean(ok_ms) if ok_ms else 0
    print(f"  Run {run_idx}: {n_ok}/{len(results)} OK | pool={pool_hit} llm={llm_hit} | avg {avg_ms:.0f}ms")
    return results


# =============================================================================
# MAIN
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="CPE Ablation — Doc D v3 + Pool Matching")
    parser.add_argument("--creator",        default="iris_bertran")
    parser.add_argument("--runs",    type=int, default=3)
    parser.add_argument("--model",          default=DEFAULT_MODEL)
    parser.add_argument("--delay",   type=float, default=RATE_LIMIT_DELAY)
    parser.add_argument("--evaluate-only",  action="store_true")
    args = parser.parse_args()

    creator_id = args.creator
    n_runs     = max(1, args.runs)
    model      = args.model

    data_dir  = Path(f"tests/cpe_data/{creator_id}")
    sweep_dir = data_dir / "sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)

    # ── Load system prompt ────────────────────────────────────────────────────
    print("\n" + "="*72)
    print("DOC D v3 + POOL MATCHING ABLATION")
    print("="*72)
    system_prompt = load_system_prompt(creator_id)
    print(f"\nSystem prompt: {len(system_prompt)} chars")

    # ── Load test data ────────────────────────────────────────────────────────
    with open(data_dir / "test_set.json", encoding="utf-8") as f:
        test_set = json.load(f)
    conversations = test_set.get("conversations", [])
    print(f"Test cases: {len(conversations)}")

    # ── Load baseline metrics ─────────────────────────────────────────────────
    bm_path = data_dir / "baseline_metrics.json"
    baseline_metrics = json.loads(bm_path.read_text()) if bm_path.exists() else {}
    print(f"Baseline metrics: {'loaded' if baseline_metrics else 'NOT FOUND'}")

    # ── Load pool variator + calibration ──────────────────────────────────────
    variator    = load_pool_variator(creator_id)
    calibration = load_calibration(creator_id)
    print(f"Calibration: {'loaded' if calibration else 'NOT FOUND'}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # ── GENERATION ────────────────────────────────────────────────────────────
    run_files: List[Path] = []

    if args.evaluate_only:
        run_files = sorted(sweep_dir.glob("docd_v3_plus_pool_run*.json"))[:n_runs]
        if not run_files:
            print("ERROR: --evaluate-only but no docd_v3_plus_pool_run*.json files found.")
            sys.exit(1)
        print(f"Evaluate-only: loading {len(run_files)} existing files")
    else:
        api_key = os.getenv("DEEPINFRA_API_KEY")
        if not api_key:
            print("ERROR: DEEPINFRA_API_KEY not set.")
            sys.exit(1)

        for run_idx in range(1, n_runs + 1):
            print(f"\n--- RUN {run_idx}/{n_runs} ---")
            try:
                import core.providers.deepinfra_provider as _di
                _di._deepinfra_consecutive_failures = 0
                _di._deepinfra_circuit_open_until   = 0.0
            except Exception:
                pass

            run_results = await generate_run(
                conversations, system_prompt, variator, calibration,
                creator_id, model, run_idx, args.delay,
            )
            rf = sweep_dir / f"docd_v3_plus_pool_run{run_idx}_{ts}.json"
            payload = {
                "ablation":       "docd_v3_plus_pool",
                "creator":        creator_id,
                "model":          model,
                "system_prompt":  system_prompt,
                "systems_active": ["compressed_doc_d", "pool_matching"],
                "run":            run_idx,
                "n_cases":        len(run_results),
                "timestamp":      datetime.now(timezone.utc).isoformat(),
                "results":        run_results,
            }
            rf.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
            print(f"Saved: {rf}")
            run_files.append(rf)

    # ── EVALUATION ────────────────────────────────────────────────────────────
    print("\n--- EVALUATING METRICS ---")
    all_run_results: List[List[Dict]] = []
    run_l1: List[dict] = []
    run_l2: List[dict] = []
    run_l3: List[dict] = []

    for rf in run_files:
        data    = json.loads(rf.read_text())
        results = data["results"]
        all_run_results.append(results)

        pool_n = sum(1 for r in results if r.get("source") == "pool")
        llm_n  = sum(1 for r in results if r.get("source") == "llm")

        responses = [r["bot_response"] for r in results]
        l1 = compute_l1(responses, baseline_metrics)
        l2 = compute_l2(results)
        l3 = compute_l3_quick(results)

        run_l1.append(l1)
        run_l2.append(l2)
        run_l3.append(l3)

        print(f"  Run {data['run']}: L1={l1['score']}  "
              f"chrF={l2['chrf']:.4f}  BLEU={l2['bleu4']:.4f}  "
              f"ROUGE={l2['rouge_l']:.4f}  METEOR={l2['meteor']:.4f}  "
              f"rep={l3['rep_rate_pct']}%  [pool={pool_n} llm={llm_n}]")

    # ── Pool match rate (aggregate across all runs) ───────────────────────────
    all_results_flat = [r for run in all_run_results for r in run]
    pool_total = sum(1 for r in all_results_flat if r.get("source") == "pool")
    llm_total  = sum(1 for r in all_results_flat if r.get("source") == "llm")
    pool_rate  = round(pool_total / len(all_results_flat) * 100, 1) if all_results_flat else 0.0
    print(f"\n  Pool hit rate: {pool_total}/{len(all_results_flat)} ({pool_rate}%)")

    # ── BERTScore ─────────────────────────────────────────────────────────────
    print("\nComputing BERTScore (L3, coherence)...")
    from bert_score import score as bert_score_fn

    bert_f1s: List[float] = []
    bert_per_case: List[float] = []
    for run_data in all_run_results:
        bots  = [r["bot_response"] for r in run_data]
        leads = [r["test_input"]   for r in run_data]
        _, _, F1 = bert_score_fn(bots, leads, lang="es", verbose=False,
                                  model_type="distilbert-base-multilingual-cased")
        bert_f1s.append(float(F1.mean()))
        bert_per_case.extend(F1.tolist())
        print(f"  BERTScore run: {F1.mean():.4f}")

    # ── STATISTICAL COMPARISONS ───────────────────────────────────────────────
    METRIC_MAP = {
        "has_emoji":    ("has_emoji",      "has_emoji",      "lower_is_better"),
        "has_excl":     ("has_excl",       "has_excl",       "lower_is_better"),
        "q_rate":       ("q_rate",         "q_rate",         "lower_is_better"),
        "len_mean":     ("char_len",       "char_len",       "lower_is_better"),
        "sentence_cnt": ("sentence_count", "sentence_count", "lower_is_better"),
        "ca_rate":      ("is_ca",          "is_ca",          "higher_is_better"),
        "chrf":         ("chrf",           "chrf",           "higher_is_better"),
        "bleu4":        ("bleu4",          "bleu4",          "higher_is_better"),
        "rouge_l":      ("rouge_l",        "rouge_l",        "higher_is_better"),
        "meteor":       ("meteor",         "meteor",         "higher_is_better"),
        "len_ratio":    ("len_ratio",      "len_ratio",      "lower_is_better"),
        "rep_rate":     ("rep_rate",       "rep_rate",       "lower_is_better"),
    }

    current_pc = extract_per_case_from_results(all_run_results)

    def _compute_stat(current: Dict, reference: Dict, label: str) -> dict:
        out: Dict[str, dict] = {}
        for key, (c_key, r_key, direction) in METRIC_MAP.items():
            c_vals = current.get(c_key, [])
            r_vals = reference.get(r_key, [])
            if not c_vals or not r_vals or len(c_vals) != len(r_vals):
                continue
            w_stat, p_val = wilcoxon_signed_rank(c_vals, r_vals)
            d = cliffs_delta(c_vals, r_vals)
            out[key] = {
                f"{label}_mean": round(statistics.mean(r_vals), 4),
                "current_mean":  round(statistics.mean(c_vals), 4),
                "delta":         round(statistics.mean(c_vals) - statistics.mean(r_vals), 4),
                "wilcoxon_W":    w_stat,
                "p_value":       p_val,
                "cliffs_d":      d,
                "magnitude":     cliffs_magnitude(d),
                "significant":   p_val < 0.05,
                "direction":     direction,
            }
        return out

    print("\n--- LOADING BASELINES FOR STATISTICAL COMPARISON ---")
    naked_pc   = load_naked_per_case(sweep_dir)
    layer1_pc  = load_layer1_per_case(sweep_dir)

    stat_vs_naked  = _compute_stat(current_pc, naked_pc,  "naked")   if naked_pc  else {}
    stat_vs_layer1 = _compute_stat(current_pc, layer1_pc, "layer1")  if layer1_pc else {}

    naked_bert_mean  = 0.828
    layer1_bert_mean = 0.828
    naked_def_path = data_dir / "naked_baseline_definitive.json"
    if naked_def_path.exists():
        try:
            _nb = json.loads(naked_def_path.read_text())
            naked_bert_mean = statistics.mean(
                _nb["l3"]["metrics"]["coherence_bert_f1"]["runs"]
            )
        except Exception:
            pass
    try:
        with open(sweep_dir / "layer1_doc_d.json") as f:
            _l1d = json.load(f)
        layer1_bert_mean = _l1d["l3"]["agg"]["coherence_bert_f1"]["mean"]
    except Exception:
        pass

    # ── AGGREGATE HELPER ──────────────────────────────────────────────────────
    def _agg(vals: List[float]) -> dict:
        return {"mean": round(statistics.mean(vals), 4),
                "std":  round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0,
                "runs": [round(v, 4) for v in vals]}

    l1_agg_metrics: Dict[str, dict] = {}
    for mk in ["has_emoji_pct", "has_excl_pct", "q_rate_pct", "len_mean_chars",
               "len_median_chars", "ca_rate_pct", "vocab_jac_pct", "sentence_count", "distinct_2"]:
        vals = [r["metrics"][mk]["bot"] for r in run_l1 if mk in r.get("metrics", {})]
        if vals:
            l1_agg_metrics[mk] = _agg(vals)

    # ── SAMPLE CASES (5 — at least 2 pool, 2 llm, text-only GT) ────────────
    r1_results = all_run_results[0]

    # Filter: only cases with real text ground_truth
    r1_text    = [r for r in r1_results if _is_text_ground_truth(r.get("ground_truth", ""))]
    pool_cases = [r for r in r1_text if r.get("source") == "pool"]
    llm_cases  = [r for r in r1_text if r.get("source") == "llm"]

    import random
    random.seed(42)

    n_pool_show = min(2, len(pool_cases))
    n_llm_show  = min(2, len(llm_cases))
    n_extra     = 5 - n_pool_show - n_llm_show

    sample_inputs = (
        random.sample(pool_cases, n_pool_show)
        + random.sample(llm_cases, n_llm_show)
        + random.sample(r1_text, n_extra)
    )
    # Deduplicate by id (extra cases might overlap)
    seen: set = set()
    sample_inputs_dedup = []
    for r in sample_inputs:
        if r["id"] not in seen:
            seen.add(r["id"])
            sample_inputs_dedup.append(r)
    sample_cases = []
    for idx, r in enumerate(sample_inputs_dedup[:5], 1):
        sample_cases.append({
            "case_idx":     idx,
            "id":           r["id"],
            "category":     r.get("category", ""),
            "language":     r.get("language", ""),
            "source":       r.get("source", ""),
            "pool_category":r.get("pool_category"),
            "pool_conf":    r.get("pool_conf", 0.0),
            "lead":         r["test_input"],
            "bot_response": r["bot_response"],
            "ground_truth": r["ground_truth"],
            "conversation_context": _get_conversation_context(r["id"], conversations),
        })

    # ── FINAL JSON ────────────────────────────────────────────────────────────
    final = {
        "ablation":          "docd_v3_plus_pool",
        "version":           "v1",
        "creator":           creator_id,
        "model":             model,
        "system_prompt":     system_prompt,
        "system_prompt_chars": len(system_prompt),
        "systems_active":    ["compressed_doc_d", "pool_matching"],
        "n_runs":            len(all_run_results),
        "n_cases":           len(conversations),
        "computed":          datetime.now(timezone.utc).isoformat(),

        "pool_stats": {
            "total_responses":    len(all_results_flat),
            "pool_hits":          pool_total,
            "llm_calls":          llm_total,
            "pool_hit_rate_pct":  pool_rate,
        },

        "l1": {
            "score_per_run": [r["score"] for r in run_l1],
            "agg_metrics":   l1_agg_metrics,
            "per_run":       [{"run": i+1, **r} for i, r in enumerate(run_l1)],
        },

        "l2": {
            "agg": {
                "chrf":      _agg([r["chrf"]      for r in run_l2]),
                "bleu4":     _agg([r["bleu4"]     for r in run_l2]),
                "rouge_l":   _agg([r["rouge_l"]   for r in run_l2]),
                "meteor":    _agg([r["meteor"]    for r in run_l2]),
                "len_ratio": _agg([r["len_ratio"] for r in run_l2]),
            },
            "per_run": [{"run": i+1, "chrf": r["chrf"], "bleu4": r["bleu4"],
                         "rouge_l": r["rouge_l"], "meteor": r["meteor"],
                         "len_ratio": r["len_ratio"], "n_pairs": r["n_pairs"]}
                        for i, r in enumerate(run_l2)],
        },

        "l3": {
            "agg": {
                "coherence_bert_f1":      _agg(bert_f1s),
                "repetition_rate_pct":    _agg([r["rep_rate_pct"]   for r in run_l3]),
                "hallucination_rate_pct": _agg([r["hallu_rate_pct"] for r in run_l3]),
            },
        },

        "statistical_comparison_vs_naked":  stat_vs_naked,
        "statistical_comparison_vs_layer1": stat_vs_layer1,
        "sample_cases": sample_cases,
    }

    out_path = sweep_dir / "docd_v3_plus_pool.json"
    out_path.write_text(json.dumps(final, indent=2, ensure_ascii=False))
    print(f"\nSaved → {out_path}")

    _print_report(final, naked_bert_mean, layer1_bert_mean)


def _print_report(data: dict, naked_bert: float, layer1_bert: float) -> None:
    n_total = data["n_runs"] * data["n_cases"]
    ps      = data["pool_stats"]
    print(f"\n{'='*76}")
    print(f"ABLATION REPORT — Doc D v3 + Pool Matching")
    print(f"Creator: {data['creator']} | Model: {data['model']}")
    print(f"Runs: {data['n_runs']} × {data['n_cases']} = {n_total} | "
          f"Pool: {ps['pool_hits']}/{ps['total_responses']} ({ps['pool_hit_rate_pct']}%) | "
          f"LLM: {ps['llm_calls']}")
    print(f"{'='*76}")

    def _row(label, sc_naked, sc_layer1, key):
        n = sc_naked.get(key, {})
        l = sc_layer1.get(key, {})
        n_mean   = n.get("naked_mean",   "—")
        l1_mean  = l.get("layer1_mean",  "—")
        cur      = n.get("current_mean", l.get("current_mean", "—"))
        np_val   = n.get("p_value",  "—")
        lp_val   = l.get("p_value",  "—")
        nd       = n.get("cliffs_d", "—")
        ld       = l.get("cliffs_d", "—")
        ns       = "✓" if n.get("significant") else "·"
        ls       = "✓" if l.get("significant") else "·"
        def _fmt(v): return f"{v:8.4f}" if isinstance(v, float) else f"{'—':>8}"
        print(f"  {label:<22} {_fmt(n_mean)} {_fmt(l1_mean)} {_fmt(cur)} "
              f"  vs-naked: {_fmt(nd)} p={_fmt(np_val)} {ns}"
              f"  vs-l1: {_fmt(ld)} p={_fmt(lp_val)} {ls}")

    sc_n  = data.get("statistical_comparison_vs_naked",  {})
    sc_l1 = data.get("statistical_comparison_vs_layer1", {})

    print(f"\n  {'METRIC':<22} {'NAKED':>8} {'DOCD-V3':>8} {'POOL+L1':>8}  "
          f"  {'vs-naked':>25}  {'vs-DocD-v3':>25}")
    print(f"{'─'*76}")

    DISPLAY = [
        ("has_emoji (%)",    "has_emoji"),
        ("has_excl (%)",     "has_excl"),
        ("q_rate (%)",       "q_rate"),
        ("len_mean (chars)", "len_mean"),
        ("sentence_count",   "sentence_cnt"),
        ("ca_rate (%)",      "ca_rate"),
        ("chrF++",           "chrf"),
        ("BLEU-4",           "bleu4"),
        ("ROUGE-L",          "rouge_l"),
        ("METEOR",           "meteor"),
        ("len_ratio",        "len_ratio"),
        ("rep_rate (%)",     "rep_rate"),
    ]
    for label, key in DISPLAY:
        _row(label, sc_n, sc_l1, key)

    bert_cur = data["l3"]["agg"]["coherence_bert_f1"]["mean"]
    print(f"  {'BERTScore':<22} {naked_bert:8.4f} {layer1_bert:8.4f} {bert_cur:8.4f}")

    print(f"\n  L1 scores: {data['l1']['score_per_run']}")

    print(f"\n{'─'*76}")
    print("  5 SAMPLE CASES — pool-matched cases labelled [POOL], LLM cases [LLM]")
    print(f"{'─'*76}")
    for c in data["sample_cases"]:
        src = c.get("source", "?").upper()
        pool_info = ""
        if src == "POOL":
            pool_info = f" cat={c.get('pool_category')} conf={c.get('pool_conf'):.2f}"
        print(f"\n  Case {c['case_idx']} [{src}] [{c['category']}/{c['language']}]{pool_info}")
        ctx = c.get("conversation_context", [])
        if ctx:
            print(f"  Context (last {len(ctx)} turns):")
            for t in ctx:
                role_tag = "👤" if t["role"] == "user" else "🤖"
                print(f"    {role_tag} {t['content'][:120]}")
        print(f"  Lead: {c['lead'][:120]!r}")
        print(f"  Bot:  {c['bot_response'][:200]!r}")
        print(f"  GT:   {c['ground_truth'][:100]!r}")

    print(f"\n{'='*76}")
    print("CRITERION: IMPROVES = p<0.05 AND Cliff's |d| ≥ 0.147 (small effect)")
    print(f"{'='*76}\n")


if __name__ == "__main__":
    asyncio.run(main())
