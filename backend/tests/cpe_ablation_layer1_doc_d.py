"""
CPE Ablation Layer 1 — Naked + Compressed Doc D (~1.3K chars).

This is the FIRST system that changes the bot's personality.
Expected to be the biggest single jump in the ablation ladder.

Systems active:
  ✓ Compressed Doc D (system prompt = full personality description)
Systems OFF:
  ✗ Memory / RAG / few-shot / style normalizer / sensitive detection / post-processing

Methodology:
  - PersonaGym (EMNLP 2025) + AbGen (ACL 2025)
  - 3 runs × 50 cases = 150 observations
  - L1 (9 metrics) + L2 (5 metrics) + L3 (3: BERTScore + rep + hallucination)
  - Wilcoxon signed-rank + Cliff's delta vs naked baseline

Usage:
    railway run python3 tests/cpe_ablation_layer1_doc_d.py --creator iris_bertran
    railway run python3 tests/cpe_ablation_layer1_doc_d.py --creator iris_bertran --evaluate-only

Output:
    tests/cpe_data/{creator}/sweep/layer1_doc_d_run{N}_{ts}.json   — raw per run
    tests/cpe_data/{creator}/sweep/layer1_doc_d.json               — final report
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
logger = logging.getLogger("cpe_layer1_docd")
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
# LOAD SYSTEM PROMPT — compressed Doc D
# =============================================================================

def load_system_prompt(creator_id: str) -> str:
    """Load compressed Doc D.

    Priority:
      1. DB via creator_profile_service (cached, ~3K chars)
      2. build_compressed_doc_d() (regenerates from baseline + BFI + DB)

    Raises RuntimeError if neither source is available.
    """
    # 1. Try DB profile cache
    try:
        from services.creator_profile_service import get_profile
        data = get_profile(creator_id, "compressed_doc_d")
        if data and data.get("text"):
            logger.info("Loaded compressed_doc_d from DB profile cache")
            return data["text"]
    except Exception as e:
        logger.warning("DB profile lookup failed: %s", e)

    # 2. Build from scratch (reads baseline_metrics + BFI from DB/local files)
    try:
        from core.dm.compressed_doc_d import build_compressed_doc_d
        logger.info("DB profile not found — building compressed_doc_d from scratch")
        return build_compressed_doc_d(creator_id)
    except Exception as e:
        raise RuntimeError(f"Cannot load compressed Doc D for '{creator_id}': {e}") from e


# =============================================================================
# METRICS — identical to cpe_ablation_system01.py
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
    words   = set(re.findall(r"\b\w+\b", text.lower()))
    emojis  = _EMOJI_RE.findall(text)
    ca_hits = len(_CA_MARKERS.findall(text))
    es_hits = len(_ES_MARKERS.findall(text))
    lang    = "ca-es" if (ca_hits and es_hits) else ("ca" if ca_hits > es_hits else "es")
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
# L1 — 9 metrics  (identical to cpe_ablation_system01.py)
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
# L2 — 5 metrics (per-case lists + aggregate)
# =============================================================================

def _semantic_similarity(candidates: List[str], references: List[str]) -> List[float]:
    """Compute SentenceBERT cosine similarity between candidate and reference pairs.

    Uses paraphrase-multilingual-MiniLM-L12-v2 (multilingual, fast).
    Returns list of cosine similarities [0, 1].
    """
    try:
        from sentence_transformers import SentenceTransformer, util
        model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        cand_embs = model.encode(candidates, convert_to_tensor=True, show_progress_bar=False)
        ref_embs = model.encode(references, convert_to_tensor=True, show_progress_bar=False)
        # Pairwise cosine similarity (diagonal only)
        sims = [float(util.cos_sim(cand_embs[i], ref_embs[i])) for i in range(len(candidates))]
        return sims
    except ImportError:
        logger.warning("sentence-transformers not installed — skipping semantic similarity")
        return [0.0] * len(candidates)


def compute_l2(results: List[Dict]) -> dict:
    pairs = [(r["bot_response"], r["ground_truth"]) for r in results
             if r.get("bot_response") and r.get("ground_truth")]
    chrf_s   = [_chrf(b, g)   for b, g in pairs]
    bleu4_s  = [_bleu4(b, g)  for b, g in pairs]
    rouge_s  = [_rouge_l(b, g) for b, g in pairs]
    meteor_s = [_meteor(b, g)  for b, g in pairs]
    lenrat_s = [len(b) / len(g) if len(g) > 0 else 0.0 for b, g in pairs]

    # FIX 2: Semantic similarity replaces chrF++ as primary decision metric
    candidates = [b for b, g in pairs]
    references = [g for b, g in pairs]
    semsim_s = _semantic_similarity(candidates, references)

    n = len(pairs)
    return {
        "n_pairs":      n,
        "chrf":         round(statistics.mean(chrf_s),   4),
        "bleu4":        round(statistics.mean(bleu4_s),  4),
        "rouge_l":      round(statistics.mean(rouge_s),  4),
        "meteor":       round(statistics.mean(meteor_s), 4),
        "len_ratio":    round(statistics.mean(lenrat_s), 4),
        "semsim":       round(statistics.mean(semsim_s), 4),
        "_chrf_scores":    chrf_s,
        "_bleu4_scores":   bleu4_s,
        "_rougel_scores":  rouge_s,
        "_meteor_scores":  meteor_s,
        "_lenrat_scores":  lenrat_s,
        "_semsim_scores":  semsim_s,
    }


# =============================================================================
# L3 — repetition + hallucination (BERTScore computed separately)
# =============================================================================

def compute_l3_quick(results: List[Dict]) -> dict:
    bots = [r["bot_response"] for r in results]
    rep_flags   = [_repetition_rate(b) for b in bots]
    hallu_flags = [bool(_HALLU_RE.search(b)) for b in bots]
    return {
        "rep_rate_pct":   round(sum(rep_flags)   / len(rep_flags)   * 100, 2),
        "hallu_rate_pct": round(sum(hallu_flags) / len(hallu_flags) * 100, 2),
        "_rep_flags":     [int(f) for f in rep_flags],
        "_hallu_flags":   [int(f) for f in hallu_flags],
    }


# =============================================================================
# GENERATION — Layer 1: Doc D as system prompt, everything else OFF
# =============================================================================

async def generate_layer1_run(
    test_cases: List[Dict],
    system_prompt: str,
    model: str,
    run_idx: int,
    delay: float = RATE_LIMIT_DELAY,
) -> List[Dict]:
    """One run with ONLY compressed Doc D as system prompt. No other systems."""
    from core.providers.deepinfra_provider import call_deepinfra

    logger.info(f"[Run {run_idx}] layer1_doc_d | model={model} | cases={len(test_cases)} | prompt_len={len(system_prompt)}")

    results = []
    for i, tc in enumerate(test_cases, 1):
        lead = tc["test_input"]
        t0   = time.monotonic()

        # Build messages: system + context turns (for multi-turn) + user
        messages = [{"role": "system", "content": system_prompt}]
        if tc.get("is_multi_turn") and tc.get("turns"):
            for turn in tc["turns"]:
                messages.append({
                    "role": turn["role"],
                    "content": turn["content"],
                })
        messages.append({"role": "user", "content": lead})
        resp = None
        try:
            resp = await call_deepinfra(
                messages,
                max_tokens=150,
                temperature=0.7,
                model=model,
            )
        except Exception as e:
            logger.warning(f"[Run {run_idx}] case {i} error: {e}")

        bot_response = resp["content"].strip() if resp else ""
        elapsed_ms   = int((time.monotonic() - t0) * 1000)
        tokens_in    = resp.get("tokens_in",  0) if resp else 0
        tokens_out   = resp.get("tokens_out", 0) if resp else 0

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
        })

        if i % 10 == 0 or not bot_response:
            tag = "ERR" if not bot_response else "OK"
            print(f"  [{tag}] [{i:02d}/{len(test_cases)}] {tc['id']}: {bot_response[:60]!r}")

        await asyncio.sleep(delay)

    n_ok = sum(1 for r in results if r["bot_response"])
    ok_ms = [r["elapsed_ms"] for r in results if r["bot_response"] and r["elapsed_ms"] > 0]
    avg_ms = statistics.mean(ok_ms) if ok_ms else 0
    print(f"  Run {run_idx}: {n_ok}/{len(results)} OK, avg {avg_ms:.0f}ms")
    return results


# =============================================================================
# STATISTICAL TESTS — Wilcoxon + Cliff's delta (copied from sys01)
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
    z  = abs((w_stat - mean_w) / math.sqrt(var_w))
    p  = 2 * _norm_sf(z)
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
# LOAD NAKED BASELINE PER-CASE SCORES (for Wilcoxon)
# =============================================================================

def load_naked_per_case(sweep_dir: Path) -> Dict[str, List[float]]:
    run_files = sorted(sweep_dir.glob("naked_zero_run*_20260331_193231.json"))
    if not run_files:
        run_files = sorted(sweep_dir.glob("naked_zero_run*.json"))

    per_case: Dict[str, List[float]] = {
        "has_emoji": [], "has_excl": [], "q_rate": [], "char_len": [],
        "is_ca": [], "sentence_count": [], "chrf": [], "bleu4": [],
        "rouge_l": [], "meteor": [], "len_ratio": [], "rep_rate": [],
        "semsim": [],
    }
    for rf in run_files:
        data    = json.loads(rf.read_text())
        results = data["results"]
        bots = [r.get("bot_response", "") for r in results]
        gts  = [r.get("ground_truth", "") for r in results]
        semsim_scores = _semantic_similarity(bots, gts) if bots else []
        for idx, r in enumerate(results):
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
            per_case["semsim"].append(semsim_scores[idx] if idx < len(semsim_scores) else 0.0)
    return per_case


def extract_per_case(run_results_list: List[List[Dict]]) -> Dict[str, List[float]]:
    per_case: Dict[str, List[float]] = {
        "has_emoji": [], "has_excl": [], "q_rate": [], "char_len": [],
        "is_ca": [], "sentence_count": [], "chrf": [], "bleu4": [],
        "rouge_l": [], "meteor": [], "len_ratio": [], "rep_rate": [],
        "semsim": [],
    }
    for results in run_results_list:
        bots = [r.get("bot_response", "") for r in results]
        gts  = [r.get("ground_truth", "") for r in results]
        semsim_scores = _semantic_similarity(bots, gts) if bots else []
        for idx, r in enumerate(results):
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
            per_case["semsim"].append(semsim_scores[idx] if idx < len(semsim_scores) else 0.0)
    return per_case


# =============================================================================
# MAIN
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="CPE Ablation Layer 1 — Compressed Doc D")
    parser.add_argument("--creator",       default="iris_bertran")
    parser.add_argument("--runs",    type=int, default=3)
    parser.add_argument("--model",         default=DEFAULT_MODEL)
    parser.add_argument("--delay",   type=float, default=RATE_LIMIT_DELAY)
    parser.add_argument("--evaluate-only", action="store_true")
    args = parser.parse_args()

    creator_id = args.creator
    n_runs     = max(1, args.runs)
    model      = args.model

    data_dir  = Path(f"tests/cpe_data/{creator_id}")
    sweep_dir = data_dir / "sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)

    # ── Load system prompt (Doc D) ────────────────────────────────────────────
    print("\n" + "="*72)
    print("LOADING COMPRESSED DOC D — THIS IS THE SYSTEM PROMPT SENT TO DeepInfra")
    print("="*72)
    system_prompt = load_system_prompt(creator_id)
    print(f"\n--- EXACT SYSTEM PROMPT ({len(system_prompt)} chars) ---")
    print(system_prompt)
    print(f"\n--- END SYSTEM PROMPT ---\n")

    # ── Load test cases (prefer v2 stratified if available) ─────────────────
    test_set_v2 = data_dir / "test_set_v2_stratified.json"
    test_set_v1 = data_dir / "test_set.json"
    test_set_path = test_set_v2 if test_set_v2.exists() else test_set_v1
    with open(test_set_path, encoding="utf-8") as f:
        test_set = json.load(f)
    conversations = test_set.get("conversations", [])
    version = test_set.get("metadata", {}).get("version", "v1")
    n_mt = sum(1 for c in conversations if c.get("is_multi_turn"))
    print(f"Loaded {len(conversations)} test cases for '{creator_id}' "
          f"(version={version}, multi-turn={n_mt}) from {test_set_path.name}")

    # ── Load baseline metrics (for L1 iris reference) ─────────────────────────
    bm_path = data_dir / "baseline_metrics.json"
    baseline_metrics = json.loads(bm_path.read_text()) if bm_path.exists() else {}
    print(f"Baseline metrics: {'loaded' if baseline_metrics else 'NOT FOUND — L1 will use defaults'}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # ── GENERATION ────────────────────────────────────────────────────────────
    run_files: List[Path] = []

    if args.evaluate_only:
        run_files = sorted(sweep_dir.glob("layer1_doc_d_run*.json"))[:n_runs]
        if not run_files:
            print("ERROR: --evaluate-only but no layer1_doc_d_run*.json files found.")
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

            run_results = await generate_layer1_run(
                conversations, system_prompt, model, run_idx, args.delay
            )
            rf = sweep_dir / f"layer1_doc_d_run{run_idx}_{ts}.json"
            payload = {
                "ablation":       "layer1_compressed_doc_d",
                "creator":        creator_id,
                "model":          model,
                "system_prompt":  system_prompt,
                "systems_active": ["compressed_doc_d"],
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
              f"SemSim={l2['semsim']:.4f}  rep={l3['rep_rate_pct']}%")

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

    # ── STATISTICAL COMPARISON vs NAKED ──────────────────────────────────────
    print("\n--- WILCOXON + CLIFF'S DELTA vs NAKED BASELINE ---")
    naked_pc  = load_naked_per_case(sweep_dir)
    layer1_pc = extract_per_case(all_run_results)

    # Naked BERTScore mean (from known run or definitive file)
    naked_bert_mean = 0.828
    naked_def_path  = data_dir / "naked_baseline_definitive.json"
    if naked_def_path.exists():
        try:
            _nb = json.loads(naked_def_path.read_text())
            naked_bert_mean = statistics.mean(
                _nb["l3"]["metrics"]["coherence_bert_f1"]["runs"]
            )
        except Exception:
            pass

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
        "semsim":       ("semsim",         "semsim",         "higher_is_better"),
        "len_ratio":    ("len_ratio",      "len_ratio",      "lower_is_better"),
        "rep_rate":     ("rep_rate",       "rep_rate",       "lower_is_better"),
    }

    stat_results: Dict[str, dict] = {}
    for label, (l_key, n_key, direction) in METRIC_MAP.items():
        l_vals = layer1_pc.get(l_key, [])
        n_vals = naked_pc.get(n_key, [])
        if not l_vals or not n_vals or len(l_vals) != len(n_vals):
            continue
        w_stat, p_val = wilcoxon_signed_rank(l_vals, n_vals)
        d = cliffs_delta(l_vals, n_vals)
        stat_results[label] = {
            "naked_mean":  round(statistics.mean(n_vals), 4),
            "layer1_mean": round(statistics.mean(l_vals), 4),
            "delta":       round(statistics.mean(l_vals) - statistics.mean(n_vals), 4),
            "wilcoxon_W":  w_stat,
            "p_value":     p_val,
            "cliffs_d":    d,
            "magnitude":   cliffs_magnitude(d),
            "significant": p_val < 0.05,
            "direction":   direction,
        }

    # ── AGGREGATE ─────────────────────────────────────────────────────────────
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

    # ── HUMAN EVALUATION PROTOCOL (FIX 3) ───────────────────────────────────
    # 15 cases: 5 random + 5 worst BERTScore + 5 best BERTScore
    import random
    random.seed(42)
    r1_results = all_run_results[0]
    n_cases = len(r1_results)

    # Get per-case BERTScore from run 1
    r1_bert = bert_per_case[:n_cases] if len(bert_per_case) >= n_cases else bert_per_case

    # Sort by BERTScore — only consider cases with text ground_truth
    text_ok = {i for i in range(n_cases)
               if _is_text_ground_truth(r1_results[i].get("ground_truth", ""))}
    indexed_bert = [(i, r1_bert[i]) for i in range(len(r1_bert)) if i in text_ok]
    sorted_by_bert = sorted(indexed_bert, key=lambda x: x[1])

    # 5 worst BERTScore
    worst_5_idx = [idx for idx, _ in sorted_by_bert[:5]]
    # 5 best BERTScore
    best_5_idx = [idx for idx, _ in sorted_by_bert[-5:]]
    # 5 random (excluding worst/best already selected)
    used_idx = set(worst_5_idx + best_5_idx)
    remaining = [i for i in text_ok if i not in used_idx]
    random_5_idx = random.sample(remaining, min(5, len(remaining)))

    def _build_eval_case(idx: int, selection: str) -> dict:
        r = r1_results[idx]
        bert_val = r1_bert[idx] if idx < len(r1_bert) else 0.0
        return {
            "case_idx":     idx + 1,
            "id":           r["id"],
            "category":     r.get("category", ""),
            "language":     r.get("language", ""),
            "is_multi_turn": r.get("is_multi_turn", False),
            "selection":    selection,
            "bert_f1":      round(bert_val, 4),
            "lead":         r["test_input"],
            "bot_response": r["bot_response"],
            "ground_truth": r["ground_truth"],
            "conversation_context": _get_conversation_context(r["id"], conversations),
            # Human eval fields (to be filled by Manel)
            "coherencia":   None,  # 1-5
            "enviarias":    None,  # 1-5
        }

    sample_cases = (
        [_build_eval_case(i, "worst_bert") for i in worst_5_idx] +
        [_build_eval_case(i, "random") for i in random_5_idx] +
        [_build_eval_case(i, "best_bert") for i in best_5_idx]
    )

    # ── FINAL JSON ────────────────────────────────────────────────────────────
    final = {
        "ablation":       "layer1_compressed_doc_d",
        "version":        "v1",
        "creator":        creator_id,
        "model":          model,
        "system_prompt":  system_prompt,
        "system_prompt_chars": len(system_prompt),
        "systems_active": ["compressed_doc_d"],
        "n_runs":         len(all_run_results),
        "n_cases":        len(conversations),
        "computed":       datetime.now(timezone.utc).isoformat(),

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
                "semsim":    _agg([r["semsim"]    for r in run_l2]),
                "len_ratio": _agg([r["len_ratio"] for r in run_l2]),
            },
            "per_run": [{"run": i+1, "chrf": r["chrf"], "bleu4": r["bleu4"],
                         "rouge_l": r["rouge_l"], "meteor": r["meteor"],
                         "semsim": r["semsim"],
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

        "statistical_comparison_vs_naked": stat_results,
        "sample_cases": sample_cases,
    }

    out_path = sweep_dir / "layer1_doc_d.json"
    out_path.write_text(json.dumps(final, indent=2, ensure_ascii=False))
    print(f"\nSaved → {out_path}")

    _print_report(final, naked_bert_mean)


def _print_report(data: dict, naked_bert_mean: float) -> None:
    print(f"\n{'='*72}")
    print(f"ABLATION REPORT — Layer 1: Compressed Doc D ({data['system_prompt_chars']} chars)")
    print(f"Creator: {data['creator']} | Model: {data['model']}")
    print(f"Runs: {data['n_runs']} × {data['n_cases']} cases = "
          f"{data['n_runs']*data['n_cases']} total responses")
    print(f"{'='*72}")

    print(f"\n{'─'*72}")
    print(f"  {'METRIC':<22} {'NAKED':>8} {'LAYER1':>8} {'DELTA':>8} "
          f"{'p-val':>7} {'Cliff d':>8} {'Sig?':>6}")
    print(f"{'─'*72}")

    sc = data["statistical_comparison_vs_naked"]

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
        ("SemSim (cosine)",  "semsim"),
        ("len_ratio",        "len_ratio"),
        ("rep_rate (%)",     "rep_rate"),
    ]

    for label, key in DISPLAY:
        if key not in sc:
            continue
        m = sc[key]
        sig_mark = "✓" if m["significant"] else "·"
        print(f"  {label:<22} {m['naked_mean']:>8.4f} {m['layer1_mean']:>8.4f} "
              f"{m['delta']:>+8.4f} {m['p_value']:>7.4f} {m['cliffs_d']:>+8.4f} "
              f"  {sig_mark} ({m['magnitude']})")

    bert_layer1 = data["l3"]["agg"]["coherence_bert_f1"]["mean"]
    print(f"  {'BERTScore (lead→bot)':<22} {naked_bert_mean:>8.4f} {bert_layer1:>8.4f} "
          f"{bert_layer1 - naked_bert_mean:>+8.4f} {'n/a':>7} {'n/a':>8}")

    print(f"\n  L1 scores: {data['l1']['score_per_run']}")

    print(f"\n{'─'*72}")
    print("  HUMAN EVALUATION — 15 CASES (5 worst BERTScore + 5 random + 5 best)")
    print("  Score each: coherencia (1-5) + enviarías (1-5)")
    print(f"{'─'*72}")
    current_section = None
    for c in data["sample_cases"]:
        section = c.get("selection", "random")
        if section != current_section:
            current_section = section
            label = {"worst_bert": "WORST BERTScore", "random": "RANDOM",
                     "best_bert": "BEST BERTScore"}.get(section, section)
            print(f"\n  ── {label} ──")
        mt = " [MT]" if c.get("is_multi_turn") else ""
        print(f"\n  Case {c['case_idx']} [{c['category']}/{c['language']}]{mt} "
              f"BERTf1={c.get('bert_f1', '?')}")
        ctx = c.get("conversation_context", [])
        if ctx:
            print(f"  Context (last {len(ctx)} turns):")
            for t in ctx:
                role_tag = "👤" if t["role"] == "user" else "🤖"
                print(f"    {role_tag} {t['content'][:120]}")
        print(f"  Lead: {c['lead'][:120]!r}")
        print(f"  Bot:  {c['bot_response'][:200]!r}")
        print(f"  GT:   {c['ground_truth'][:100]!r}")
        print(f"  coherencia: ___/5  enviarías: ___/5")

    print(f"\n{'='*72}")
    print("CRITERION: improvement = p<0.05 AND |Cliff's d| ≥ 0.147 (small)")
    print(f"{'='*72}\n")


if __name__ == "__main__":
    asyncio.run(main())
