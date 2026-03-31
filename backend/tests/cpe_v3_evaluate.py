"""
CPE v3 Evaluate — Unified evaluation script for AI clone quality (CPE v3).

Generates responses via DeepInfra (or loads pre-generated files) and evaluates
across 4 dimensions: Linguistic Style, Semantic Similarity, Persona Consistency,
Conversational Quality.

python3.11 shebang equivalent — run with:
    python3.11 tests/cpe_v3_evaluate.py --creator iris_bertran
    python3.11 tests/cpe_v3_evaluate.py --creator iris_bertran --runs 3
    python3.11 tests/cpe_v3_evaluate.py --creator iris_bertran --evaluate-only
    python3.11 tests/cpe_v3_evaluate.py --creator iris_bertran --responses path/to/run.json
    python3.11 tests/cpe_v3_evaluate.py --creator iris_bertran --compare path/to/baseline_summary.json
    python3.11 tests/cpe_v3_evaluate.py --creator iris_bertran --skip-bertscore
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── repo root on sys.path so we can import core.* ───────────────────────────
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Set env BEFORE importing the provider (it reads at import time)
os.environ.setdefault("DEEPINFRA_TIMEOUT", "30")
os.environ.setdefault("DEEPINFRA_CB_THRESHOLD", "999")

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cpe_v3_evaluate")
logger.setLevel(logging.INFO)

DEFAULT_MODEL = "Qwen/Qwen3-14B"
DEFAULT_DELAY = 1.2  # seconds between API calls


# ── helpers ─────────────────────────────────────────────────────────────────

def _load_json(path: Path, label: str) -> Any:
    if not path.exists():
        print(f"ERROR: {label} not found at {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _load_json_optional(path: Path) -> Any:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _results_from_file(path: Path) -> List[Dict]:
    """Accept either a JSON list or {"results": [...]} wrapper."""
    data = _load_json(path, f"responses file {path}")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("results", [])
    print(f"ERROR: unexpected format in {path}")
    sys.exit(1)


# ── generation ───────────────────────────────────────────────────────────────

async def _generate_run(
    test_cases: List[Dict],
    system_prompt: str,
    model: str,
    run_idx: int,
    delay: float,
) -> List[Dict]:
    """Call DeepInfra for one run over all test cases."""
    from core.providers.deepinfra_provider import call_deepinfra  # noqa: PLC0415

    logger.info("[Run %d] model=%s  system_prompt=%r  cases=%d  delay=%.1fs",
                run_idx, model, system_prompt[:60], len(test_cases), delay)

    results: List[Dict] = []
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
        except Exception as exc:
            logger.warning("[Run %d] case %d error: %s", run_idx, i, exc)

        bot_response = resp["content"].strip() if resp else ""
        elapsed_ms   = int((time.monotonic() - t0) * 1000)
        tokens_in    = resp.get("tokens_in", 0)  if resp else 0
        tokens_out   = resp.get("tokens_out", 0) if resp else 0

        results.append({
            "id":           tc["id"],
            "test_input":   tc["test_input"],
            "ground_truth": tc.get("ground_truth", ""),
            "bot_response": bot_response,
            "category":     tc.get("category", ""),
            "language":     tc.get("language", ""),
            "elapsed_ms":   elapsed_ms,
            "tokens_in":    tokens_in,
            "tokens_out":   tokens_out,
            "run":          run_idx,
        })

        if i % 10 == 0 or not bot_response:
            status = "ERR" if not bot_response else "OK"
            print(f"  [{status}] [{i:02d}/{len(test_cases)}] {tc['id']}: {bot_response[:60]!r}")

        await asyncio.sleep(delay)

    n_ok = sum(1 for r in results if r["bot_response"])
    print(f"  Run {run_idx} done: {n_ok}/{len(results)} OK")
    return results


# ── report ───────────────────────────────────────────────────────────────────

def _tick(ok: bool) -> str:
    return "✓" if ok else "✗"


def _fmt_opt(val: Optional[float], fmt: str = ".3f") -> str:
    if val is None:
        return "N/A"
    return format(val, fmt)


def _fmt_std(mean: Optional[float], std: Optional[float]) -> str:
    if mean is None:
        return "N/A"
    if std is None or std == 0.0:
        return format(mean, ".3f")
    return f"{mean:.3f} ± {std:.3f}"


def _print_report(
    creator: str,
    model: str,
    n_runs: int,
    n_cases: int,
    d1: dict,
    d2: dict,
    d3: dict,
    d4: dict,
    cpe: dict,
    agg: Optional[dict] = None,
) -> None:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*60}")
    print(f"CPE v3 EVALUATION — {creator} ({model})")
    print(f"Runs: {n_runs} | Cases: {n_cases} | Date: {now_str}")
    print(f"{'='*60}")

    # D1
    det = d1.get("details", {})
    passed = d1.get("l1_passed", 0)
    total  = d1.get("l1_total", 7)
    print(f"\nDIMENSIÓN 1 — ESTILO LINGÜÍSTICO")
    print(f"  L1 overall score:    {d1.get('l1_score', 0.0):.3f}  ({passed}/{total} passed)")
    for key in ("emoji_rate", "excl_rate", "q_rate", "len_mean", "len_median", "ca_rate", "vocab_jaccard"):
        info = det.get(key)
        if info is None:
            continue
        ok_sym = _tick(info.get("pass", False))
        bot_val = info.get("bot", 0.0)
        cr_val  = info.get("creator")
        if cr_val is not None:
            print(f"  {key:<20} {bot_val*100 if 'rate' in key else bot_val:>7.1f}  "
                  f"(creator: {cr_val*100 if 'rate' in key else cr_val:.1f})  {ok_sym}")
        else:
            print(f"  {key:<20} {bot_val:>7.4f}  {ok_sym}")

    # D2
    def _d2_val(key: str) -> Tuple[Optional[float], Optional[float]]:
        """Return (mean, std) pulling from agg if multi-run."""
        val = d2.get(key)
        if agg and f"{key}" in agg:
            a = agg[f"{key}"]
            return a.get("mean"), a.get("std")
        return val, None

    print(f"\nDIMENSIÓN 2 — SIMILITUD SEMÁNTICA")
    bs_mean, bs_std = _d2_val("bertscore_f1")
    print(f"  BERTScore F1:        {_fmt_std(bs_mean, bs_std)}")
    chrf_mean, chrf_std = _d2_val("chrf")
    print(f"  chrF++:              {_fmt_std(chrf_mean, chrf_std)}")
    rl_mean, rl_std = _d2_val("rouge_l")
    print(f"  ROUGE-L:             {_fmt_std(rl_mean, rl_std)}")
    b4_mean, b4_std = _d2_val("bleu4")
    print(f"  BLEU-4:              {_fmt_std(b4_mean, b4_std)}")
    met_mean, met_std = _d2_val("meteor")
    if met_mean is None:
        print(f"  METEOR:              N/A (nltk not installed)")
    else:
        print(f"  METEOR:              {_fmt_std(met_mean, met_std)}")
    comp_mean, comp_std = _d2_val("composite")
    print(f"  Composite:           {_fmt_std(comp_mean, comp_std)}")

    # D3
    print(f"\nDIMENSIÓN 3 — CONSISTENCIA DE PERSONA")
    chr_rate = d3.get("catchphrase_hit_rate")
    print(f"  Catchphrase rate:    {_fmt_opt(chr_rate, '.1%') if chr_rate is not None else 'N/A (no vocab)'}")
    print(f"  Repetition rate:     {d3.get('repetition_rate', 0.0):.1%}")
    print(f"  Assistant language:  {d3.get('assistant_language_rate', 0.0):.1%}")
    print(f"  Persona score:       {d3.get('persona_score', 0.0):.3f}")

    # D4
    print(f"\nDIMENSIÓN 4 — CALIDAD CONVERSACIONAL")
    print(f"  Coherence proxy:     {d4.get('coherence_bertscore', 0.0):.3f}")
    print(f"  Hallucination rate:  {d4.get('hallucination_rate', 0.0):.1%}")
    lr = d4.get('length_ratio', 0.0)
    print(f"  Length ratio dev:    {1.0 + lr:.2f} (dev: {lr:.2f})")
    print(f"  Quality score:       {d4.get('quality_score', 0.0):.3f}")

    # Composite
    grade = cpe.get("grade", "?")
    overall = cpe.get("overall", 0.0)
    print(f"\nCPE v3 COMPOSITE SCORE:  {overall:.3f}  (Grade: {grade})")
    print(f"{'='*60}")


def _print_comparison(
    compare_data: dict,
    baseline_summary: dict,
    current_d2: dict,
) -> None:
    """Print Wilcoxon comparison table."""
    from tests.cpe_v3_evaluator import wilcoxon_signed_rank, cliffs_delta, cliff_magnitude  # noqa: PLC0415

    cur_chrf = current_d2.get("_per_case_chrf", [])
    cur_bs   = current_d2.get("_per_case_bertscore", [])
    cur_rl   = [r.get("rouge_l") for r in compare_data.get("_per_case_rouge_l", [])] if "_per_case_rouge_l" in compare_data else []

    base_chrf = baseline_summary.get("_per_case_chrf", [])
    base_bs   = baseline_summary.get("_per_case_bertscore", [])

    # Pull baseline per-case data from d2 block if available
    if not base_chrf:
        base_chrf = (baseline_summary.get("d2") or {}).get("_per_case_chrf", [])
    if not base_bs:
        base_bs = (baseline_summary.get("d2") or {}).get("_per_case_bertscore", [])

    print(f"\nCOMPARACIÓN vs BASELINE")
    header = f"  {'Métrica':<14} {'Baseline':>9} {'Actual':>9} {'Δ':>8}  {'p-val':>7}  {'Effect'}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    metrics_pairs = []
    if base_chrf and cur_chrf:
        base_m = sum(base_chrf) / len(base_chrf)
        cur_m  = sum(cur_chrf)  / len(cur_chrf)
        metrics_pairs.append(("chrF++", base_chrf, cur_chrf, base_m, cur_m))
    if base_bs and cur_bs:
        base_m = sum(base_bs) / len(base_bs)
        cur_m  = sum(cur_bs)  / len(cur_bs)
        metrics_pairs.append(("BERTScore", base_bs, cur_bs, base_m, cur_m))

    # Also pull scalar metrics from d2 summary blocks
    for metric_key, label in [("rouge_l", "ROUGE-L"), ("bleu4", "BLEU-4")]:
        base_val = (baseline_summary.get("d2") or {}).get(metric_key)
        cur_val  = current_d2.get(metric_key)
        if base_val is not None and cur_val is not None:
            metrics_pairs.append((label, [base_val], [cur_val], base_val, cur_val))

    all_significant = []
    for label, base_list, cur_list, base_m, cur_m in metrics_pairs:
        delta_val = cur_m - base_m
        sign = "+" if delta_val >= 0 else ""
        try:
            _, p = wilcoxon_signed_rank(cur_list, base_list)
            p_str = f"{p:.4f}" if p is not None else "N/A"
            significant = p is not None and p < 0.05
        except Exception:
            p_str = "N/A"
            significant = False
        cd = cliffs_delta(cur_list, base_list)
        mag = cliff_magnitude(cd)
        arrow = "↑" if cd > 0 else ("↓" if cd < 0 else "→")
        all_significant.append(significant and cd > 0)
        print(f"  {label:<14} {base_m:>9.3f} {cur_m:>9.3f} {sign}{delta_val:>7.3f}  {p_str:>7}  {mag} {arrow}")

    if metrics_pairs:
        if all(all_significant) and all_significant:
            decision = "IMPROVES (all key metrics significant at p<0.05)"
        elif any(all_significant):
            decision = "PARTIAL IMPROVEMENT (some metrics significant)"
        else:
            decision = "NO_EFFECT (no metric significant at p<0.05)"
        print(f"  Decision: {decision}")


# ── main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="CPE v3 Unified Evaluation — Generate + Evaluate AI clone responses"
    )
    parser.add_argument("--creator",       default="iris_bertran",   help="Creator slug")
    parser.add_argument("--runs",    type=int, default=1,            help="Number of generation runs (default 1)")
    parser.add_argument("--model",         default=DEFAULT_MODEL,    help="DeepInfra model ID")
    parser.add_argument("--system-prompt", default=None,             help="Override system prompt")
    parser.add_argument("--evaluate-only", action="store_true",      help="Skip generation; load existing naked_zero_run*.json files")
    parser.add_argument("--responses",     default=None,             help="Evaluate a specific pre-generated response file")
    parser.add_argument("--compare",       default=None,             help="Path to previous CPE v3 summary JSON to compare against")
    parser.add_argument("--skip-bertscore", action="store_true",     help="Skip BERTScore (faster)")
    parser.add_argument("--delay",   type=float, default=DEFAULT_DELAY, help="Delay between API calls in seconds")
    args = parser.parse_args()

    creator_id   = args.creator
    n_runs       = max(1, args.runs)
    model        = args.model
    delay        = args.delay

    data_dir  = REPO_ROOT / "tests" / "cpe_data" / creator_id
    sweep_dir = data_dir / "sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)

    # ── load test set ────────────────────────────────────────────────────────
    test_set     = _load_json(data_dir / "test_set.json", "test_set.json")
    conversations: List[Dict] = test_set.get("conversations", [])
    print(f"Loaded {len(conversations)} test cases for '{creator_id}'")

    # ── load baseline metrics ────────────────────────────────────────────────
    baseline_metrics: dict = _load_json_optional(data_dir / "baseline_metrics.json")
    if baseline_metrics:
        print(f"Loaded baseline_metrics from {data_dir / 'baseline_metrics.json'}")
    else:
        print(f"WARNING: baseline_metrics.json not found — D1 will be degraded")

    # ── load calibration ─────────────────────────────────────────────────────
    cal_path = REPO_ROOT / "calibrations" / f"{creator_id}.json"
    if not cal_path.exists():
        cal_path = REPO_ROOT / "calibrations" / "iris_bertran.json"
    calibration: dict = _load_json_optional(cal_path)
    if calibration:
        print(f"Loaded calibration from {cal_path}")
    else:
        print(f"WARNING: calibration not found — D3/D4 may be degraded")

    creator_name = creator_id.replace("_", " ").title()

    # ── system prompt ────────────────────────────────────────────────────────
    system_prompt = args.system_prompt or f"Eres {creator_name}. Responde a los mensajes."

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # ── decide source of results ─────────────────────────────────────────────
    run_files: List[Path] = []

    if args.responses:
        # Single file provided directly
        responses_path = Path(args.responses)
        if not responses_path.exists():
            print(f"ERROR: --responses file not found: {responses_path}")
            sys.exit(1)
        run_files = [responses_path]
        n_runs = 1
        print(f"Using provided responses file: {responses_path}")

    elif args.evaluate_only:
        existing = sorted(sweep_dir.glob("naked_zero_run*.json"))
        run_files = existing[:n_runs] if n_runs < len(existing) else existing
        if not run_files:
            print("ERROR: --evaluate-only but no naked_zero_run*.json files found in sweep dir.")
            sys.exit(1)
        n_runs = len(run_files)
        print(f"Evaluate-only mode: loading {n_runs} run file(s)")

    else:
        # Generate
        api_key = os.getenv("DEEPINFRA_API_KEY")
        if not api_key:
            print("ERROR: DEEPINFRA_API_KEY not set. Cannot generate responses.")
            sys.exit(1)

        for run_idx in range(1, n_runs + 1):
            print(f"\n--- GENERATION RUN {run_idx}/{n_runs} ---")
            # Reset circuit breaker state
            try:
                import core.providers.deepinfra_provider as _di  # noqa: PLC0415
                _di._deepinfra_consecutive_failures = 0
                _di._deepinfra_circuit_open_until = 0.0
            except Exception:
                pass

            run_results = await _generate_run(
                conversations, system_prompt, model, run_idx, delay
            )

            run_file = sweep_dir / f"cpe_v3_run{run_idx}_{ts}.json"
            payload = {
                "creator":       creator_id,
                "creator_name":  creator_name,
                "model":         model,
                "system_prompt": system_prompt,
                "run":           run_idx,
                "n_cases":       len(run_results),
                "timestamp":     datetime.now(timezone.utc).isoformat(),
                "results":       run_results,
            }
            with open(run_file, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
            print(f"Saved: {run_file}")
            run_files.append(run_file)

    # ── evaluate each run ────────────────────────────────────────────────────
    from tests.cpe_v3_evaluator import (  # noqa: PLC0415
        dim1_linguistic_style,
        dim2_semantic_similarity,
        dim3_persona_consistency,
        dim4_conversational_quality,
        cpe_v3_score,
        aggregate_runs,
    )

    print("\n--- EVALUATING METRICS ---")
    run_d1: List[dict] = []
    run_d2: List[dict] = []
    run_d3: List[dict] = []
    run_d4: List[dict] = []
    run_cpe: List[dict] = []

    for run_file in run_files:
        results = _results_from_file(run_file)
        responses = [r.get("bot_response", "") for r in results]

        d1 = dim1_linguistic_style(responses, baseline_metrics, calibration)
        d2 = dim2_semantic_similarity(
            results,
            skip_bertscore=args.skip_bertscore,
        )
        d3 = dim3_persona_consistency(results, calibration)
        d4 = dim4_conversational_quality(results, calibration)
        cpe = cpe_v3_score(d1, d2, d3, d4)

        run_d1.append(d1)
        run_d2.append(d2)
        run_d3.append(d3)
        run_d4.append(d4)
        run_cpe.append(cpe)

        run_label = getattr(run_file, "stem", str(run_file))
        print(f"  {run_label}: "
              f"D1={d1.get('l1_score', 0.0):.3f} "
              f"D2-chrF={d2.get('chrf', 0.0):.4f} "
              f"D3={d3.get('persona_score', 0.0):.3f} "
              f"D4={d4.get('quality_score', 0.0):.3f} "
              f"CPE={cpe.get('overall', 0.0):.3f}")

    # ── aggregate across runs ─────────────────────────────────────────────────
    # Build flat dicts for aggregate_runs (numeric leaves only from each dim)
    def _flatten_dim(d: dict, prefix: str) -> dict:
        out = {}
        for k, v in d.items():
            if k.startswith("_") or k == "details" or k == "code_switching":
                continue
            if isinstance(v, (int, float)) and v is not None:
                out[f"{prefix}_{k}"] = v
        return out

    flat_runs = []
    for d1, d2, d3, d4, cpe in zip(run_d1, run_d2, run_d3, run_d4, run_cpe):
        flat = {}
        flat.update(_flatten_dim(d1, "d1"))
        flat.update(_flatten_dim(d2, "d2"))
        flat.update(_flatten_dim(d3, "d3"))
        flat.update(_flatten_dim(d4, "d4"))
        flat["cpe_overall"] = cpe.get("overall", 0.0)
        flat_runs.append(flat)

    agg = aggregate_runs(flat_runs) if len(flat_runs) > 1 else {}

    # Use last run's d2 for per-case arrays (or first if single run)
    final_d2 = run_d2[-1]
    final_d1 = run_d1[-1]
    final_d3 = run_d3[-1]
    final_d4 = run_d4[-1]
    final_cpe = run_cpe[-1]

    # ── report ────────────────────────────────────────────────────────────────
    _print_report(
        creator_id, model, len(run_files), len(conversations),
        final_d1, final_d2, final_d3, final_d4, final_cpe,
        agg=agg,
    )

    # ── comparison ───────────────────────────────────────────────────────────
    if args.compare:
        compare_path = Path(args.compare)
        if not compare_path.exists():
            print(f"WARNING: --compare file not found: {compare_path}. Skipping comparison.")
        else:
            baseline_summary = _load_json(compare_path, "--compare file")
            _print_comparison({"_per_case_rouge_l": []}, baseline_summary, final_d2)

    # ── save summary ─────────────────────────────────────────────────────────
    summary = {
        "creator":       creator_id,
        "model":         model,
        "system_prompt": system_prompt,
        "n_runs":        len(run_files),
        "n_cases":       len(conversations),
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "d1":            {k: v for k, v in final_d1.items() if not k.startswith("_")},
        "d2":            {k: v for k, v in final_d2.items() if not k.startswith("_")},
        "d3":            final_d3,
        "d4":            final_d4,
        "cpe_v3":        final_cpe,
        "aggregate":     agg,
        "_per_case_chrf":      final_d2.get("_per_case_chrf", []),
        "_per_case_bertscore": final_d2.get("_per_case_bertscore", []),
    }

    summary_file = sweep_dir / f"cpe_v3_summary_{ts}.json"
    with open(summary_file, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
    print(f"\nSaved summary: {summary_file}")


if __name__ == "__main__":
    asyncio.run(main())
