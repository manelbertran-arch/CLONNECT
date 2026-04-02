"""
CPE Ablation — System #1: Sensitive Content Detection.

Adds ONLY sensitive_detector.py on top of the naked baseline.
Everything else stays OFF: no Doc D, no memory, no RAG, no style normalizer,
no few-shot, no guardrails, no post-processing.

Logic:
  - detect_sensitive_content(lead_message)
    → if sensitive  : return CANNED_RESPONSES[type]  (no LLM call)
    → if not sensitive: call DeepInfra exactly as naked baseline
      system_prompt = "Eres {creator_name}. Responde a los mensajes."
      max_tokens=150, temperature=0.7, model=Qwen3-14B

Methodology:
  - PersonaGym (EMNLP 2025) + AbGen (ACL 2025)
  - 3 runs × 50 cases
  - Wilcoxon signed-rank (paired, 150 obs) + Cliff's delta per metric
  - Compare vs naked_baseline_definitive.json

Usage:
    python3 tests/cpe_ablation_system01.py --creator iris_bertran
    python3 tests/cpe_ablation_system01.py --creator iris_bertran --evaluate-only

Output:
    tests/cpe_data/{creator}/sweep/sys01_run{N}_{ts}.json   — raw per run
    tests/cpe_data/{creator}/sweep/system01_sensitive_detection.json — final report
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
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DEEPINFRA_TIMEOUT", "30")
os.environ.setdefault("DEEPINFRA_CB_THRESHOLD", "999")

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cpe_sys01")
logger.setLevel(logging.INFO)

DEFAULT_MODEL  = "Qwen/Qwen3-14B"
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
# CANNED RESPONSES — used when sensitive content is detected
# =============================================================================

from core.sensitive_detector import (
    SensitiveType,
    detect_sensitive_content,
    get_crisis_resources,
)

CANNED_RESPONSES: Dict[str, str] = {
    SensitiveType.SELF_HARM.value: (
        "Hola, lo que me cuentas me preocupa. Por favor, habla con alguien de confianza "
        "o llama al 024 (gratuito, 24h). Estoy aquí si necesitas algo más. 💙"
    ),
    SensitiveType.EATING_DISORDER.value: (
        "Entiendo que puede ser un tema difícil. Te animo a que hables con un profesional "
        "de la salud que pueda acompañarte. Cuídate mucho. 🌿"
    ),
    SensitiveType.MINOR.value: (
        "Hola! Para poder ayudarte necesitaría que un adulto de tu familia estuviera "
        "presente. ¡Muchas gracias por escribir! 😊"
    ),
    SensitiveType.PHISHING.value: (
        "Lo siento, no puedo proporcionar esa información."
    ),
    SensitiveType.SPAM.value: (
        ""  # no response to spam
    ),
    SensitiveType.THREAT.value: (
        "Por favor, mantengamos una conversación respetuosa. 🙏"
    ),
    SensitiveType.ECONOMIC_DISTRESS.value: (
        "Entiendo que las cosas están difíciles. Estoy aquí para ayudarte en lo que pueda. 💪"
    ),
}


# =============================================================================
# METRICS — identical to cpe_baseline_naked.py
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


# ── chrF++ (CPE-native, word-padded) ─────────────────────────────────────────
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
# L2 — 5 metrics (per-case lists + aggregate)
# =============================================================================

def compute_l2(results: List[Dict]) -> dict:
    pairs = [(r["bot_response"], r["ground_truth"]) for r in results
             if r.get("bot_response") and r.get("ground_truth")]
    chrf_s   = [_chrf(b, g)   for b, g in pairs]
    bleu4_s  = [_bleu4(b, g)  for b, g in pairs]
    rouge_s  = [_rouge_l(b, g) for b, g in pairs]
    meteor_s = [_meteor(b, g)  for b, g in pairs]
    lenrat_s = [len(b) / len(g) if len(g) > 0 else 0.0 for b, g in pairs]
    n = len(pairs)
    return {
        "n_pairs":      n,
        "chrf":         round(statistics.mean(chrf_s),   4),
        "bleu4":        round(statistics.mean(bleu4_s),  4),
        "rouge_l":      round(statistics.mean(rouge_s),  4),
        "meteor":       round(statistics.mean(meteor_s), 4),
        "len_ratio":    round(statistics.mean(lenrat_s), 4),
        # per-case for Wilcoxon
        "_chrf_scores":    chrf_s,
        "_bleu4_scores":   bleu4_s,
        "_rougel_scores":  rouge_s,
        "_meteor_scores":  meteor_s,
        "_lenrat_scores":  lenrat_s,
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
# GENERATION — system 01
# =============================================================================

async def generate_sys01_run(
    test_cases: List[Dict],
    creator_name: str,
    model: str,
    run_idx: int,
    delay: float = RATE_LIMIT_DELAY,
) -> List[Dict]:
    """One run with ONLY sensitive detection active."""
    from core.providers.deepinfra_provider import call_deepinfra

    system_prompt = f"Eres {creator_name}. Responde a los mensajes."
    logger.info(f"[Run {run_idx}] sys01 | model={model} | cases={len(test_cases)}")

    results = []
    n_sensitive = 0

    for i, tc in enumerate(test_cases, 1):
        lead = tc["test_input"]
        t0   = time.monotonic()

        # ── Sensitive detection ───────────────────────────────────────────────
        sensitive = detect_sensitive_content(lead)

        if sensitive:
            canned       = CANNED_RESPONSES.get(sensitive.type.value, "")
            bot_response = canned
            elapsed_ms   = int((time.monotonic() - t0) * 1000)
            tokens_in = tokens_out = 0
            n_sensitive += 1
            source = f"canned:{sensitive.type.value}"
        else:
            # ── DeepInfra — identical to naked baseline ───────────────────────
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
                logger.warning(f"[Run {run_idx}] case {i} error: {e}")

            bot_response = resp["content"].strip() if resp else ""
            elapsed_ms   = int((time.monotonic() - t0) * 1000)
            tokens_in    = resp.get("tokens_in",  0) if resp else 0
            tokens_out   = resp.get("tokens_out", 0) if resp else 0
            source       = "llm"

        results.append({
            "id":             tc["id"],
            "test_input":     lead,
            "ground_truth":   tc.get("ground_truth", ""),
            "bot_response":   bot_response,
            "category":       tc.get("category", ""),
            "language":       tc.get("language", ""),
            "elapsed_ms":     elapsed_ms,
            "tokens_in":      tokens_in,
            "tokens_out":     tokens_out,
            "run":            run_idx,
            "source":         source,          # "llm" or "canned:SENSITIVE_TYPE"
            "sensitive_type": sensitive.type.value,
        })

        if i % 10 == 0 or source.startswith("canned"):
            tag = source if source != "llm" else "OK"
            print(f"  [{tag}] [{i:02d}/{len(test_cases)}] {tc['id']}: {bot_response[:60]!r}")

        if source == "llm":
            await asyncio.sleep(delay)

    n_ok = sum(1 for r in results if r["bot_response"])
    print(f"  Run {run_idx}: {n_ok}/{len(results)} responses, {n_sensitive} sensitive intercepted")
    return results


# =============================================================================
# STATISTICAL TESTS — Wilcoxon + Cliff's delta (paired)
# =============================================================================

def wilcoxon_signed_rank(x: List[float], y: List[float]) -> Tuple[float, float]:
    """
    Two-sided Wilcoxon signed-rank test.
    Returns (W_statistic, p_value).
    Uses normal approximation (valid for n >= 10).
    """
    diffs = [xi - yi for xi, yi in zip(x, y)]
    diffs = [d for d in diffs if d != 0]
    n = len(diffs)
    if n < 2:
        return 0.0, 1.0

    abs_diffs = sorted(enumerate(abs(d) for d in diffs), key=lambda t: t[1])
    # Assign ranks (handling ties with average rank)
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

    # Normal approximation
    mean_w  = n * (n + 1) / 4
    var_w   = n * (n + 1) * (2 * n + 1) / 24
    if var_w == 0:
        return w_stat, 1.0
    z = abs((w_stat - mean_w) / math.sqrt(var_w))
    # Two-sided p from standard normal CDF approximation (Hart 1968)
    p = 2 * _norm_sf(z)
    return round(w_stat, 2), round(p, 4)


def _norm_sf(z: float) -> float:
    """Survival function of standard normal (1 - CDF)."""
    # Abramowitz & Stegun 26.2.17
    t = 1.0 / (1.0 + 0.2316419 * z)
    poly = t * (0.319381530
              + t * (-0.356563782
              + t * (1.781477937
              + t * (-1.821255978
              + t * 1.330274429))))
    pdf  = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
    return pdf * poly


def cliffs_delta(x: List[float], y: List[float]) -> float:
    """
    Cliff's delta (paired version): (# x>y - # x<y) / n.
    Returns value in [-1, 1].
    """
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
    """
    Load per-case metric arrays from naked run files.
    Returns dict: metric_key → flat list (all runs concatenated, 150 entries).
    """
    run_files = sorted(sweep_dir.glob("naked_zero_run*_20260331_193231.json"))
    if not run_files:
        # fallback: any naked_zero run files
        run_files = sorted(sweep_dir.glob("naked_zero_run*.json"))

    per_case: Dict[str, List[float]] = {
        "has_emoji": [], "has_excl": [], "q_rate": [], "char_len": [],
        "is_ca": [], "sentence_count": [], "chrf": [], "bleu4": [],
        "rouge_l": [], "meteor": [], "len_ratio": [], "rep_rate": [],
    }

    for rf in run_files:
        data = json.loads(rf.read_text())
        results = data["results"]
        for r in results:
            bot  = r.get("bot_response", "")
            gt   = r.get("ground_truth", "")
            m    = _text_metrics(bot)
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


def extract_per_case(run_results_list: List[List[Dict]]) -> Dict[str, List[float]]:
    """Extract per-case metric arrays from system01 run results."""
    per_case: Dict[str, List[float]] = {
        "has_emoji": [], "has_excl": [], "q_rate": [], "char_len": [],
        "is_ca": [], "sentence_count": [], "chrf": [], "bleu4": [],
        "rouge_l": [], "meteor": [], "len_ratio": [], "rep_rate": [],
    }
    for results in run_results_list:
        for r in results:
            bot  = r.get("bot_response", "")
            gt   = r.get("ground_truth", "")
            m    = _text_metrics(bot)
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
# MAIN
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="CPE Ablation — System 01: Sensitive Detection")
    parser.add_argument("--creator",       default="iris_bertran")
    parser.add_argument("--runs",    type=int, default=3)
    parser.add_argument("--model",         default=DEFAULT_MODEL)
    parser.add_argument("--delay",   type=float, default=RATE_LIMIT_DELAY)
    parser.add_argument("--evaluate-only", action="store_true")
    args = parser.parse_args()

    creator_id   = args.creator
    n_runs       = max(1, args.runs)
    model        = args.model
    creator_name = creator_id.replace("_", " ").title()

    data_dir  = Path(f"tests/cpe_data/{creator_id}")
    sweep_dir = data_dir / "sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)

    # ── Load test cases ───────────────────────────────────────────────────────
    with open(data_dir / "test_set.json", encoding="utf-8") as f:
        test_set = json.load(f)
    conversations = test_set.get("conversations", [])
    print(f"Loaded {len(conversations)} test cases for '{creator_id}'")

    # ── Load baseline metrics (for L1 iris reference) ─────────────────────────
    bm_path = data_dir / "baseline_metrics.json"
    baseline_metrics = json.loads(bm_path.read_text()) if bm_path.exists() else {}
    print(f"Baseline metrics: {'loaded' if baseline_metrics else 'NOT FOUND — L1 will use defaults'}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # ── GENERATION ────────────────────────────────────────────────────────────
    run_files: List[Path] = []

    if args.evaluate_only:
        run_files = sorted(sweep_dir.glob("sys01_run*.json"))[:n_runs]
        if not run_files:
            print("ERROR: --evaluate-only but no sys01 run files found.")
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

            run_results = await generate_sys01_run(
                conversations, creator_name, model, run_idx, args.delay
            )
            rf = sweep_dir / f"sys01_run{run_idx}_{ts}.json"
            payload = {
                "ablation":      "system01_sensitive_detection",
                "creator":       creator_id,
                "creator_name":  creator_name,
                "model":         model,
                "system_prompt": f"Eres {creator_name}. Responde a los mensajes.",
                "systems_active": ["sensitive_detection"],
                "run":           run_idx,
                "n_cases":       len(run_results),
                "timestamp":     datetime.now(timezone.utc).isoformat(),
                "results":       run_results,
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

        sensitive_count = sum(1 for r in results if r.get("source", "llm") != "llm")
        print(f"  Run {data['run']}: L1={l1['score']}  "
              f"chrF={l2['chrf']:.4f}  rep={l3['rep_rate_pct']}%  "
              f"sensitive_intercepted={sensitive_count}")

    # ── BERTScore ─────────────────────────────────────────────────────────────
    print("\nComputing BERTScore...")
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
    sys01_pc  = extract_per_case(all_run_results)

    # BERTScore for naked (from naked_baseline_definitive.json)
    naked_bert_per_case: List[float] = []
    naked_def_path = data_dir / "naked_baseline_definitive.json"
    if naked_def_path.exists():
        _naked_bert_runs = json.loads(naked_def_path.read_text())["l3"]["metrics"]["coherence_bert_f1"]["runs"]
        # Approximate per-case as constant (we don't have per-case naked bert)
        # We'll skip Wilcoxon for BERTScore and just report delta of means
        naked_bert_mean = statistics.mean(_naked_bert_runs)
    else:
        naked_bert_mean = 0.828  # known value

    METRIC_MAP = {
        #  key              sys01_key    naked_key      direction (positive = improvement)
        "has_emoji":    ("has_emoji",   "has_emoji",   "lower_is_better"),
        "has_excl":     ("has_excl",    "has_excl",    "lower_is_better"),
        "q_rate":       ("q_rate",      "q_rate",      "lower_is_better"),
        "len_mean":     ("char_len",    "char_len",    "lower_is_better"),
        "sentence_cnt": ("sentence_count", "sentence_count", "lower_is_better"),
        "ca_rate":      ("is_ca",       "is_ca",       "higher_is_better"),
        "chrf":         ("chrf",        "chrf",        "higher_is_better"),
        "bleu4":        ("bleu4",       "bleu4",       "higher_is_better"),
        "rouge_l":      ("rouge_l",     "rouge_l",     "higher_is_better"),
        "meteor":       ("meteor",      "meteor",      "higher_is_better"),
        "len_ratio":    ("len_ratio",   "len_ratio",   "lower_is_better"),
        "rep_rate":     ("rep_rate",    "rep_rate",    "lower_is_better"),
    }

    stat_results: Dict[str, dict] = {}
    for label, (s_key, n_key, direction) in METRIC_MAP.items():
        s_vals = sys01_pc.get(s_key, [])
        n_vals = naked_pc.get(n_key, [])
        if not s_vals or not n_vals or len(s_vals) != len(n_vals):
            continue
        w_stat, p_val = wilcoxon_signed_rank(s_vals, n_vals)
        d = cliffs_delta(s_vals, n_vals)
        sig = p_val < 0.05
        stat_results[label] = {
            "naked_mean":  round(statistics.mean(n_vals), 4),
            "sys01_mean":  round(statistics.mean(s_vals), 4),
            "delta":       round(statistics.mean(s_vals) - statistics.mean(n_vals), 4),
            "wilcoxon_W":  w_stat,
            "p_value":     p_val,
            "cliffs_d":    d,
            "magnitude":   cliffs_magnitude(d),
            "significant": sig,
            "direction":   direction,
        }

    # ── AGGREGATE ─────────────────────────────────────────────────────────────
    def _agg(vals: List[float]) -> dict:
        return {"mean": round(statistics.mean(vals), 4),
                "std":  round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0,
                "runs": [round(v, 4) for v in vals]}

    l1_agg_metrics: Dict[str, dict] = {}
    for mk in ["has_emoji_pct","has_excl_pct","q_rate_pct","len_mean_chars",
               "len_median_chars","ca_rate_pct","vocab_jac_pct","sentence_count","distinct_2"]:
        vals = [r["metrics"][mk]["bot"] for r in run_l1 if mk in r.get("metrics", {})]
        if vals:
            l1_agg_metrics[mk] = _agg(vals)

    sensitive_counts = [
        sum(1 for r in rr if r.get("source","llm") != "llm")
        for rr in all_run_results
    ]

    # ── FINAL JSON ────────────────────────────────────────────────────────────
    import random
    random.seed(42)
    r1_results = all_run_results[0]
    # Filter to text-only ground_truth candidates
    text_indices = [i for i, r in enumerate(r1_results) if _is_text_ground_truth(r.get("ground_truth", ""))]
    sample_idx = random.sample(text_indices, min(5, len(text_indices)))
    sample_cases = []
    for idx in sample_idx:
        r = r1_results[idx]
        sample_cases.append({
            "case_idx":      idx + 1,
            "id":            r["id"],
            "category":      r["category"],
            "language":      r["language"],
            "lead":          r["test_input"],
            "bot_response":  r["bot_response"],
            "ground_truth":  r["ground_truth"],
            "source":        r.get("source", "llm"),
            "sensitive_type":r.get("sensitive_type", "none"),
            "conversation_context": _get_conversation_context(r["id"], conversations),
        })

    final = {
        "ablation":          "system01_sensitive_detection",
        "version":           "v1",
        "creator":           creator_id,
        "model":             model,
        "system_prompt":     f"Eres {creator_name}. Responde a los mensajes.",
        "systems_active":    ["sensitive_detection"],
        "n_runs":            len(all_run_results),
        "n_cases":           50,
        "computed":          datetime.now(timezone.utc).isoformat(),

        "sensitive_intercepts": {
            "per_run": sensitive_counts,
            "mean":    round(statistics.mean(sensitive_counts), 2),
            "note":    "cases where canned response used instead of LLM",
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
                "coherence_bert_f1":     _agg(bert_f1s),
                "repetition_rate_pct":   _agg([r["rep_rate_pct"]   for r in run_l3]),
                "hallucination_rate_pct":_agg([r["hallu_rate_pct"] for r in run_l3]),
            },
        },

        "statistical_comparison_vs_naked": stat_results,

        "sample_cases": sample_cases,
    }

    out_path = sweep_dir / "system01_sensitive_detection.json"
    out_path.write_text(json.dumps(final, indent=2, ensure_ascii=False))
    print(f"\nSaved → {out_path}")

    # ── REPORT ────────────────────────────────────────────────────────────────
    _print_report(final, naked_bert_mean)


def _print_report(data: dict, naked_bert_mean: float) -> None:
    print(f"\n{'='*72}")
    print(f"ABLATION REPORT — System 01: Sensitive Content Detection")
    print(f"Creator: {data['creator']} | Model: {data['model']}")
    print(f"Runs: {data['n_runs']} × {data['n_cases']} cases = "
          f"{data['n_runs']*data['n_cases']} total responses")
    print(f"{'='*72}")

    print(f"\n  Sensitive intercepts: {data['sensitive_intercepts']['mean']:.1f} / 50 "
          f"per run  ({data['sensitive_intercepts']['per_run']})")

    print(f"\n{'─'*72}")
    print(f"  {'METRIC':<22} {'NAKED':>8} {'SYS01':>8} {'DELTA':>8} "
          f"{'p-val':>7} {'Cliff d':>8} {'Sig?':>6}")
    print(f"{'─'*72}")

    sc = data["statistical_comparison_vs_naked"]

    DISPLAY = [
        ("has_emoji (%)",   "has_emoji"),
        ("has_excl (%)",    "has_excl"),
        ("q_rate (%)",      "q_rate"),
        ("len_mean (chars)","len_mean"),
        ("sentence_count",  "sentence_cnt"),
        ("ca_rate (%)",     "ca_rate"),
        ("chrF++",          "chrf"),
        ("BLEU-4",          "bleu4"),
        ("ROUGE-L",         "rouge_l"),
        ("METEOR",          "meteor"),
        ("len_ratio",       "len_ratio"),
        ("rep_rate (%)",    "rep_rate"),
    ]

    for label, key in DISPLAY:
        if key not in sc:
            continue
        m = sc[key]
        sig_mark = "✓" if m["significant"] else "·"
        print(f"  {label:<22} {m['naked_mean']:>8.4f} {m['sys01_mean']:>8.4f} "
              f"{m['delta']:>+8.4f} {m['p_value']:>7.4f} {m['cliffs_d']:>+8.4f} "
              f"  {sig_mark} ({m['magnitude']})")

    # BERTScore (no Wilcoxon — only aggregate available for naked)
    bert_sys01 = data["l3"]["agg"]["coherence_bert_f1"]["mean"]
    print(f"  {'BERTScore (lead→bot)':<22} {naked_bert_mean:>8.4f} {bert_sys01:>8.4f} "
          f"{bert_sys01 - naked_bert_mean:>+8.4f} {'n/a':>7} {'n/a':>8}")

    print(f"\n  L1 scores: {data['l1']['score_per_run']}")

    print(f"\n{'─'*72}")
    print("  5 RANDOM CASES (Run 1)")
    print(f"{'─'*72}")
    for c in data["sample_cases"]:
        src = f"[{c['source']}]" if c["source"] != "llm" else ""
        print(f"\n  Case {c['case_idx']} [{c['category']}/{c['language']}] {src}")
        ctx = c.get("conversation_context", [])
        if ctx:
            print(f"  Context (last {len(ctx)} turns):")
            for t in ctx:
                role_tag = "👤" if t["role"] == "user" else "🤖"
                print(f"    {role_tag} {t['content'][:120]}")
        print(f"  Lead: {c['lead'][:100]!r}")
        print(f"  Bot:  {c['bot_response'][:150]!r}")
        print(f"  GT:   {c['ground_truth'][:80]!r}")

    print(f"\n{'='*72}")
    print("CRITERION: improvement = p<0.05 AND |Cliff's d| ≥ 0.147 (small)")
    print(f"{'='*72}\n")


if __name__ == "__main__":
    asyncio.run(main())
