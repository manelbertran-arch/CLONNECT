"""
CPE Baseline Naked — Punto Cero del ablation study.

Llama a Qwen3-14B via DeepInfra con SOLO un system prompt mínimo.
Sin Doc D, sin memory, sin RAG, sin history, sin nada.

Metodología:
  - PersonaGym (EMNLP 2025): baseline completo antes de ablaciones
  - AbGen (ACL 2025): 3 runs mínimo, Wilcoxon signed-rank p<0.05
  - Cada sistema se comparará contra este punto cero

Usage:
    python3 tests/cpe_baseline_naked.py --creator iris_bertran
    python3 tests/cpe_baseline_naked.py --creator iris_bertran --runs 3
    python3 tests/cpe_baseline_naked.py --creator iris_bertran --evaluate-only
    python3 tests/cpe_baseline_naked.py --creator iris_bertran --model Qwen/Qwen3-14B

Output:
    tests/cpe_data/{creator}/sweep/naked_zero_run{N}_{ts}.json  — un fichero por run
    tests/cpe_data/{creator}/sweep/naked_zero_summary_{ts}.json — agregado
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

# Set timeout BEFORE importing the provider (it reads env at import time via module-level call_deepinfra)
os.environ.setdefault("DEEPINFRA_TIMEOUT", "30")
# Disable circuit breaker for eval scripts (we handle retries manually)
os.environ.setdefault("DEEPINFRA_CB_THRESHOLD", "999")

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cpe_naked")
logger.setLevel(logging.INFO)

DEFAULT_MODEL = "Qwen/Qwen3-14B"
RATE_LIMIT_DELAY = 1.2  # seconds between API calls


# =========================================================================
# METRICS — LEVEL 1 (quantitative style)
# =========================================================================

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


def _compute_text_metrics(text: str) -> dict:
    if not text:
        return {"length": 0, "emoji_count": 0, "has_emoji": False,
                "has_question": False, "has_exclamation": False,
                "language": "unknown", "words": set()}
    words = set(re.findall(r"\b\w+\b", text.lower()))
    emojis = _EMOJI_RE.findall(text)
    ca_hits = len(_CA_MARKERS.findall(text))
    es_hits = len(_ES_MARKERS.findall(text))
    if ca_hits and es_hits:
        lang = "ca-es"
    elif ca_hits > es_hits:
        lang = "ca"
    else:
        lang = "es"
    return {
        "length": len(text),
        "emoji_count": len(emojis),
        "has_emoji": len(emojis) > 0,
        "has_question": "?" in text,
        "has_exclamation": "!" in text,
        "language": lang,
        "words": words,
    }


def compute_l1(responses: List[str], baseline_metrics: dict) -> dict:
    """Level 1: quantitative style alignment vs creator baseline."""
    bm = baseline_metrics.get("metrics", {})
    emoji_b   = bm.get("emoji", {})
    punct_b   = bm.get("punctuation", {})
    length_b  = bm.get("length", {})
    vocab_b   = bm.get("vocabulary", {})
    lang_b    = bm.get("languages", {})

    iris_emoji_rate  = emoji_b.get("emoji_rate_pct", 22)
    iris_excl_rate   = punct_b.get("exclamation_rate_pct", 2)
    iris_q_rate      = punct_b.get("question_rate_pct", 14)
    iris_len_median  = length_b.get("char_median", 26)
    iris_len_mean    = length_b.get("char_mean", 95)
    iris_ca_pct      = next((d["pct"] for d in lang_b.get("detected", []) if d["lang"] == "ca"), 0)
    iris_top_words   = set(w[0] for w in vocab_b.get("top_50", [])[:50])

    n = len(responses)
    if not n:
        return {"overall": 0.0, "n": 0}

    all_m, all_bot_words = [], set()
    for text in responses:
        m = _compute_text_metrics(text)
        all_bot_words |= m.pop("words", set())
        all_m.append(m)

    bot_emoji_rate = sum(1 for m in all_m if m["has_emoji"]) / n * 100
    bot_excl_rate  = sum(1 for m in all_m if m["has_exclamation"]) / n * 100
    bot_q_rate     = sum(1 for m in all_m if m["has_question"]) / n * 100
    bot_len_mean   = statistics.mean(m["length"] for m in all_m)
    bot_len_median = statistics.median(m["length"] for m in all_m)
    bot_ca_rate    = sum(1 for m in all_m if m.get("language") in ("ca", "ca-es")) / n * 100
    vocab_jaccard  = len(iris_top_words & all_bot_words) / len(iris_top_words | all_bot_words) if (iris_top_words | all_bot_words) else 0

    flags = []

    def check_pct(name, bot_val, iris_val, tol_pp=20):
        div = abs(bot_val - iris_val)
        ok = div <= tol_pp
        flags.append((name, bot_val, iris_val, div, ok))

    def check_num(name, bot_val, iris_val, tol_pct=30):
        div = abs(bot_val - iris_val) / iris_val * 100 if iris_val else 0
        ok = div <= tol_pct
        flags.append((name, bot_val, iris_val, div, ok))

    check_pct("emoji_rate",  bot_emoji_rate, iris_emoji_rate)
    check_pct("excl_rate",   bot_excl_rate,  iris_excl_rate, tol_pp=10)
    check_pct("q_rate",      bot_q_rate,     iris_q_rate)
    check_num("len_mean",    bot_len_mean,   iris_len_mean)
    check_num("len_median",  bot_len_median, iris_len_median)
    check_pct("ca_rate",     bot_ca_rate,    iris_ca_pct)
    check_pct("vocab_jac",   vocab_jaccard * 100, 5.0, tol_pp=10)

    passed = sum(1 for *_, ok in flags if ok)
    return {
        "overall":        round(passed / len(flags), 3),
        "passed":         passed,
        "total":          len(flags),
        "n_responses":    n,
        "bot_emoji_rate": round(bot_emoji_rate, 1),
        "bot_excl_rate":  round(bot_excl_rate, 1),
        "bot_q_rate":     round(bot_q_rate, 1),
        "bot_len_mean":   round(bot_len_mean, 1),
        "bot_len_median": round(bot_len_median, 1),
        "bot_ca_rate":    round(bot_ca_rate, 1),
        "vocab_jaccard":  round(vocab_jaccard, 4),
        "details":        {name: {"bot": round(b, 2), "iris": round(i, 2), "div": round(d, 2), "ok": ok}
                           for name, b, i, d, ok in flags},
    }


# =========================================================================
# METRICS — LEVEL 3 (lexical similarity vs ground truth)
# =========================================================================

def _tokenize(text: str) -> List[str]:
    return re.findall(r"\b\w+\b", text.lower())


def _bleu4(candidate: str, reference: str) -> float:
    """BLEU-4 (sentence-level)."""
    cand_tokens = _tokenize(candidate)
    ref_tokens  = _tokenize(reference)
    if not cand_tokens or not ref_tokens:
        return 0.0
    precisions = []
    for n in range(1, 5):
        def _ngrams(tokens, n):
            return Counter(tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1))
        cand_ng = _ngrams(cand_tokens, n)
        ref_ng  = _ngrams(ref_tokens, n)
        matches = sum(min(cnt, ref_ng[ng]) for ng, cnt in cand_ng.items())
        total   = sum(cand_ng.values())
        if total == 0:
            return 0.0
        precisions.append(matches / total)
    if any(p == 0 for p in precisions):
        return 0.0
    log_avg = sum(math.log(p) for p in precisions) / 4
    bp = min(1.0, len(cand_tokens) / len(ref_tokens)) if ref_tokens else 1.0
    return round(bp * math.exp(log_avg), 4)


def _rouge_l(candidate: str, reference: str) -> float:
    cand_tokens = _tokenize(candidate)
    ref_tokens  = _tokenize(reference)
    if not cand_tokens or not ref_tokens:
        return 0.0
    m, n = len(ref_tokens), len(cand_tokens)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_tokens[i-1] == cand_tokens[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    lcs = dp[m][n]
    if lcs == 0:
        return 0.0
    p = lcs / n
    r = lcs / m
    return round(2 * p * r / (p + r), 4)


def _chrf(candidate: str, reference: str, n: int = 6, beta: float = 2.0) -> float:
    """chrF++ score."""
    if not candidate or not reference:
        return 0.0

    def _char_ngrams(text: str, order: int) -> Counter:
        ngrams: Counter = Counter()
        for w in text.split():
            w = " " + w + " "
            for i in range(len(w) - order + 1):
                ngrams[w[i:i + order]] += 1
        return ngrams

    precisions, recalls = [], []
    for order in range(1, n + 1):
        ref_ng  = _char_ngrams(reference, order)
        cand_ng = _char_ngrams(candidate, order)
        total_cand = sum(cand_ng.values())
        total_ref  = sum(ref_ng.values())
        if total_cand == 0 or total_ref == 0:
            precisions.append(0.0)
            recalls.append(0.0)
            continue
        matches = sum(min(cnt, ref_ng[ng]) for ng, cnt in cand_ng.items())
        precisions.append(matches / total_cand)
        recalls.append(matches / total_ref)

    p_avg = statistics.mean(precisions) if precisions else 0.0
    r_avg = statistics.mean(recalls)    if recalls    else 0.0
    if p_avg + r_avg == 0:
        return 0.0
    return round((1 + beta**2) * p_avg * r_avg / (beta**2 * p_avg + r_avg), 4)


def _vocab_overlap(candidate: str, reference: str) -> float:
    cand_words = set(_tokenize(candidate))
    ref_words  = set(_tokenize(reference))
    if not cand_words or not ref_words:
        return 0.0
    return round(len(cand_words & ref_words) / len(cand_words | ref_words), 4)


def compute_l3(results: List[Dict]) -> dict:
    """Level 3: lexical similarity of bot responses vs ground truth."""
    pairs = [(r.get("bot_response", ""), r.get("ground_truth", "")) for r in results
             if r.get("bot_response") and r.get("ground_truth")]
    if not pairs:
        return {"bleu4": 0.0, "rouge_l": 0.0, "chrf": 0.0, "vocab_overlap": 0.0}

    bleu4_scores  = [_bleu4(b, g)        for b, g in pairs]
    rougel_scores = [_rouge_l(b, g)      for b, g in pairs]
    chrf_scores   = [_chrf(b, g)         for b, g in pairs]
    vocab_scores  = [_vocab_overlap(b, g) for b, g in pairs]

    return {
        "bleu4":        round(statistics.mean(bleu4_scores), 4),
        "rouge_l":      round(statistics.mean(rougel_scores), 4),
        "chrf":         round(statistics.mean(chrf_scores), 4),
        "vocab_overlap": round(statistics.mean(vocab_scores), 4),
        "n_pairs":      len(pairs),
        # Per-case scores for Wilcoxon comparisons
        "_bleu4_scores":  bleu4_scores,
        "_rougel_scores": rougel_scores,
        "_chrf_scores":   chrf_scores,
    }


# =========================================================================
# GENERATION — DeepInfra direct call
# =========================================================================

async def generate_naked_run(
    test_cases: List[Dict],
    creator_name: str,
    model: str,
    run_idx: int,
    delay: float = RATE_LIMIT_DELAY,
) -> List[Dict]:
    """Generate one run of naked baseline responses via DeepInfra."""
    from core.providers.deepinfra_provider import call_deepinfra

    # NAKED system prompt: only name + role, nothing else
    system_prompt = f"Eres {creator_name}. Responde a los mensajes."
    logger.info(f"[Run {run_idx}] system_prompt: '{system_prompt}'")
    logger.info(f"[Run {run_idx}] model: {model}")
    logger.info(f"[Run {run_idx}] {len(test_cases)} test cases, delay={delay}s")

    results = []
    for i, tc in enumerate(test_cases, 1):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": tc["test_input"]},
        ]
        t0 = time.monotonic()
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
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        tokens_in  = resp.get("tokens_in", 0)  if resp else 0
        tokens_out = resp.get("tokens_out", 0) if resp else 0

        results.append({
            "id":            tc["id"],
            "test_input":    tc["test_input"],
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
            status = "ERR" if not bot_response else "OK"
            print(f"  [{status}] [{i:02d}/{len(test_cases)}] {tc['id']}: {bot_response[:60]!r}")

        await asyncio.sleep(delay)

    n_ok = sum(1 for r in results if r["bot_response"])
    ok_ms = [r["elapsed_ms"] for r in results if r["bot_response"] and r["elapsed_ms"] > 0]
    avg_ms = statistics.mean(ok_ms) if ok_ms else 0
    print(f"  Run {run_idx} done: {n_ok}/{len(results)} OK, avg {avg_ms:.0f}ms")
    return results


# =========================================================================
# STATISTICAL AGGREGATION
# =========================================================================

def _mean_std(values: List[float]) -> Tuple[float, float]:
    if len(values) == 1:
        return values[0], 0.0
    return round(statistics.mean(values), 4), round(statistics.stdev(values), 4)


def aggregate_runs(run_l1: List[dict], run_l3: List[dict]) -> dict:
    """Compute mean ± std dev across runs for all key metrics."""
    def _collect(run_dicts: List[dict], key: str) -> List[float]:
        return [d[key] for d in run_dicts if key in d]

    l1_keys = ["overall", "bot_emoji_rate", "bot_excl_rate", "bot_q_rate",
               "bot_len_mean", "bot_len_median", "bot_ca_rate", "vocab_jaccard"]
    l3_keys = ["bleu4", "rouge_l", "chrf", "vocab_overlap"]

    agg = {}
    for key in l1_keys:
        vals = _collect(run_l1, key)
        if vals:
            mean, std = _mean_std(vals)
            agg[f"l1_{key}"] = {"mean": mean, "std": std, "runs": vals}

    for key in l3_keys:
        vals = _collect(run_l3, key)
        if vals:
            mean, std = _mean_std(vals)
            agg[f"l3_{key}"] = {"mean": mean, "std": std, "runs": vals}

    return agg


# =========================================================================
# REPORT PRINTER
# =========================================================================

def print_report(creator: str, model: str, n_runs: int, agg: dict) -> None:
    print(f"\n{'='*60}")
    print(f"NAKED BASELINE — {creator} ({model})")
    print(f"Runs: {n_runs} | Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")
    print(f"\n{'METRIC':<22} {'MEAN':>8} {'± STD':>8} {'RUNS'}")
    print(f"{'-'*60}")

    metric_labels = {
        "l1_overall":        "L1 overall score",
        "l1_bot_emoji_rate": "L1 emoji_rate %",
        "l1_bot_excl_rate":  "L1 excl_rate %",
        "l1_bot_q_rate":     "L1 q_rate %",
        "l1_bot_len_mean":   "L1 len_mean chars",
        "l1_bot_len_median": "L1 len_median chars",
        "l1_bot_ca_rate":    "L1 ca_rate %",
        "l1_vocab_jaccard":  "L1 vocab Jaccard",
        "l3_bleu4":          "L3 BLEU-4",
        "l3_rouge_l":        "L3 ROUGE-L",
        "l3_chrf":           "L3 chrF++",
        "l3_vocab_overlap":  "L3 vocab_overlap",
    }

    for key, label in metric_labels.items():
        if key not in agg:
            continue
        d = agg[key]
        runs_str = " | ".join(f"{v:.3f}" for v in d["runs"])
        print(f"  {label:<20} {d['mean']:>8.3f} {d['std']:>8.3f}   [{runs_str}]")

    print(f"\n{'='*60}")
    print("ESTE ES EL PUNTO CERO. Cada sistema se compara contra esto.")
    print("Criterio de mejora: Wilcoxon p<0.05 + Cliff's delta >small")
    print(f"{'='*60}\n")


# =========================================================================
# MAIN
# =========================================================================

async def main():
    parser = argparse.ArgumentParser(description="CPE Naked Baseline — Zero-system reference")
    parser.add_argument("--creator",        default="iris_bertran", help="Creator ID (slug)")
    parser.add_argument("--runs",     type=int, default=3,          help="Number of runs (min 3)")
    parser.add_argument("--model",          default=DEFAULT_MODEL,  help="DeepInfra model ID")
    parser.add_argument("--delay",   type=float, default=RATE_LIMIT_DELAY, help="Delay between API calls (s)")
    parser.add_argument("--evaluate-only", action="store_true",    help="Skip generation, recompute metrics from existing files")
    args = parser.parse_args()

    creator_id   = args.creator
    n_runs       = max(1, args.runs)
    model        = args.model
    delay        = args.delay

    data_dir  = Path(f"tests/cpe_data/{creator_id}")
    sweep_dir = data_dir / "sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)

    # Load test cases (prefer v2 stratified if available)
    test_set_v2 = data_dir / "test_set_v2_stratified.json"
    test_set_v1 = data_dir / "test_set.json"
    test_set_path = test_set_v2 if test_set_v2.exists() else test_set_v1
    if not test_set_path.exists():
        print(f"ERROR: test set not found at {test_set_path}")
        sys.exit(1)

    with open(test_set_path) as f:
        test_set = json.load(f)
    conversations = test_set.get("conversations", [])
    version = test_set.get("metadata", {}).get("version", "v1")
    n_mt = sum(1 for c in conversations if c.get("is_multi_turn"))
    print(f"Loaded {len(conversations)} test cases for '{creator_id}' "
          f"(version={version}, multi-turn={n_mt}) from {test_set_path.name}")

    # Load baseline metrics (for L1 computation)
    baseline_path = data_dir / "baseline_metrics.json"
    baseline_metrics: dict = {}
    if baseline_path.exists():
        with open(baseline_path) as f:
            baseline_metrics = json.load(f)
        print(f"Loaded baseline metrics from {baseline_path}")
    else:
        print(f"WARNING: baseline_metrics.json not found at {baseline_path}, L1 will be empty")

    # Creator display name
    creator_name = creator_id.replace("_", " ").title()

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # -----------------------------------------------------------------------
    # GENERATION (or load existing)
    # -----------------------------------------------------------------------
    run_files: List[Path] = []

    if args.evaluate_only:
        # Find existing naked_zero run files sorted by creation time
        existing = sorted(sweep_dir.glob(f"naked_zero_run*_{creator_id}*.json"))
        if not existing:
            # Fallback: any naked_zero file
            existing = sorted(sweep_dir.glob("naked_zero_run*.json"))
        run_files = existing[:n_runs]
        if not run_files:
            print("ERROR: --evaluate-only but no existing naked_zero run files found.")
            sys.exit(1)
        print(f"Evaluate-only mode: loading {len(run_files)} existing run files")
    else:
        api_key = os.getenv("DEEPINFRA_API_KEY")
        if not api_key:
            print("ERROR: DEEPINFRA_API_KEY not set. Cannot generate responses.")
            sys.exit(1)

        for run_idx in range(1, n_runs + 1):
            print(f"\n--- RUN {run_idx}/{n_runs} ---")
            # Reset circuit breaker state between runs
            try:
                import core.providers.deepinfra_provider as _di
                _di._deepinfra_consecutive_failures = 0
                _di._deepinfra_circuit_open_until = 0.0
            except Exception:
                pass
            run_results = await generate_naked_run(
                conversations, creator_name, model, run_idx, delay
            )

            run_file = sweep_dir / f"naked_zero_run{run_idx}_{ts}.json"
            payload = {
                "creator":       creator_id,
                "creator_name":  creator_name,
                "model":         model,
                "system_prompt": f"Eres {creator_name}. Responde a los mensajes.",
                "run":           run_idx,
                "n_cases":       len(run_results),
                "timestamp":     datetime.now(timezone.utc).isoformat(),
                "results":       run_results,
            }
            with open(run_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            print(f"Saved: {run_file}")
            run_files.append(run_file)

    # -----------------------------------------------------------------------
    # EVALUATION — L1 + L3 per run
    # -----------------------------------------------------------------------
    print("\n--- EVALUATING METRICS ---")
    run_l1: List[dict] = []
    run_l3: List[dict] = []

    for run_file in run_files:
        with open(run_file, encoding="utf-8") as f:
            payload = json.load(f)

        results = payload.get("results", payload) if isinstance(payload, dict) else payload
        responses = [r.get("bot_response", "") for r in results]

        l1 = compute_l1(responses, baseline_metrics)
        l3 = compute_l3(results)
        run_l1.append(l1)
        run_l3.append(l3)

        run_label = payload.get("run", run_files.index(run_file) + 1) if isinstance(payload, dict) else "?"
        print(f"  Run {run_label}: L1={l1['overall']:.3f} ({l1['passed']}/{l1['total']}) | "
              f"chrF={l3['chrf']:.4f} | ROUGE-L={l3['rouge_l']:.4f} | BLEU-4={l3['bleu4']:.4f}")

    # -----------------------------------------------------------------------
    # AGGREGATE + SUMMARY
    # -----------------------------------------------------------------------
    agg = aggregate_runs(run_l1, run_l3)

    summary = {
        "creator":        creator_id,
        "model":          model,
        "system_prompt":  f"Eres {creator_name}. Responde a los mensajes.",
        "n_runs":         len(run_files),
        "n_cases":        len(conversations),
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "methodology":    "naked_zero — no Doc D, no memory, no RAG, no history, no guardrails",
        "papers":         ["PersonaGym (EMNLP 2025)", "AbGen (ACL 2025)"],
        "run_l1":         run_l1,
        "run_l3":         [{k: v for k, v in r.items() if not k.startswith("_")} for r in run_l3],
        "aggregate":      agg,
    }

    summary_file = sweep_dir / f"naked_zero_summary_{ts}.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\nSaved summary: {summary_file}")

    print_report(creator_id, model, len(run_files), agg)

    return summary


if __name__ == "__main__":
    asyncio.run(main())
