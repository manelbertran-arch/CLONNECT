#!/usr/bin/env python3
"""
Compare before/after backtest results.

Shows deltas per dimension, cluster resolution, and overall improvement.

Usage:
    python3.11 scripts/compare_backtests.py --before results/judge_results_v1.json --after results/judge_results_v2.json
"""
import sys
import json
import argparse
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

logger = logging.getLogger(__name__)

DIMENSIONS = ["naturalidad", "relevancia", "estilo", "efectividad", "personalidad"]


def extract_metrics_from_judge_results(data: dict) -> dict:
    """Extract comparable metrics from judge results."""
    evaluations = data.get("evaluations", [])
    valid = [e for e in evaluations if "error" not in e]

    if not valid:
        return {"error": "No valid evaluations"}

    # Indistinguishability
    correct = sum(1 for e in valid if e.get("judge_guessed_correctly"))
    indistinguishable = (1.0 - correct / len(valid)) * 100

    # Per-dimension scores
    dim_stefano = defaultdict(list)
    dim_bot = defaultdict(list)
    for e in valid:
        ss = e.get("stefano_scores", {})
        bs = e.get("bot_scores", {})
        for dim in DIMENSIONS:
            s = ss.get(dim, 50)
            b = bs.get(dim, 50)
            if isinstance(s, (int, float)) and isinstance(b, (int, float)):
                dim_stefano[dim].append(s)
                dim_bot[dim].append(b)

    avg_stefano = {dim: sum(v) / len(v) for dim, v in dim_stefano.items() if v}
    avg_bot = {dim: sum(v) / len(v) for dim, v in dim_bot.items() if v}
    avg_gap = {dim: avg_stefano.get(dim, 50) - avg_bot.get(dim, 50) for dim in DIMENSIONS}

    # Win rates
    win_rates = {}
    for dim in DIMENSIONS:
        s_scores = dim_stefano.get(dim, [])
        b_scores = dim_bot.get(dim, [])
        if s_scores and b_scores:
            wins = sum(1 for s, b in zip(s_scores, b_scores) if b >= s)
            win_rates[dim] = wins / len(s_scores) * 100

    # By category
    cat_metrics = defaultdict(lambda: {"correct": 0, "total": 0, "gaps": []})
    for e in valid:
        cat = e.get("lead_category", "OTRO")
        cat_metrics[cat]["total"] += 1
        if e.get("judge_guessed_correctly"):
            cat_metrics[cat]["correct"] += 1
        # Compute avg gap
        ss = e.get("stefano_scores", {})
        bs = e.get("bot_scores", {})
        gaps = []
        for dim in DIMENSIONS:
            s = ss.get(dim, 50)
            b = bs.get(dim, 50)
            if isinstance(s, (int, float)) and isinstance(b, (int, float)):
                gaps.append(s - b)
        if gaps:
            cat_metrics[cat]["gaps"].append(sum(gaps) / len(gaps))

    by_category = {}
    for cat, m in cat_metrics.items():
        by_category[cat] = {
            "indistinguishable": round((1.0 - m["correct"] / max(m["total"], 1)) * 100, 1),
            "avg_gap": round(sum(m["gaps"]) / len(m["gaps"]), 1) if m["gaps"] else 0,
            "total": m["total"],
        }

    # Failure rate (gap > 15)
    failure_threshold = 15
    failures = 0
    for e in valid:
        ss = e.get("stefano_scores", {})
        bs = e.get("bot_scores", {})
        gaps = []
        for dim in DIMENSIONS:
            s = ss.get(dim, 50)
            b = bs.get(dim, 50)
            if isinstance(s, (int, float)) and isinstance(b, (int, float)):
                gaps.append(s - b)
        avg = sum(gaps) / len(gaps) if gaps else 0
        if avg >= failure_threshold:
            failures += 1

    return {
        "total_pairs": len(valid),
        "indistinguishable_pct": round(indistinguishable, 1),
        "avg_stefano": {dim: round(v, 1) for dim, v in avg_stefano.items()},
        "avg_bot": {dim: round(v, 1) for dim, v in avg_bot.items()},
        "avg_gap": {dim: round(v, 1) for dim, v in avg_gap.items()},
        "win_rates": {dim: round(v, 1) for dim, v in win_rates.items()},
        "by_category": by_category,
        "failure_rate": round(failures / max(len(valid), 1) * 100, 1),
        "failures": failures,
    }


def print_comparison(before: dict, after: dict, before_name: str, after_name: str):
    """Print before/after comparison."""
    print(f"\n{'='*70}")
    print(f"  BACKTEST COMPARISON")
    print(f"{'='*70}")
    print(f"\n  Before: {before_name} ({before['total_pairs']} pairs)")
    print(f"  After:  {after_name} ({after['total_pairs']} pairs)")

    # Overall metrics
    ind_before = before["indistinguishable_pct"]
    ind_after = after["indistinguishable_pct"]
    ind_delta = ind_after - ind_before

    fr_before = before["failure_rate"]
    fr_after = after["failure_rate"]
    fr_delta = fr_after - fr_before

    print(f"\n  {'Metric':25s} {'Before':>8s} {'After':>8s} {'Delta':>8s}")
    print(f"  {'─'*51}")
    print(f"  {'Indistinguishable %':25s} {ind_before:>7.1f}% {ind_after:>7.1f}% {ind_delta:>+7.1f}%")
    print(f"  {'Failure rate':25s} {fr_before:>7.1f}% {fr_after:>7.1f}% {fr_delta:>+7.1f}%")

    # Per-dimension gaps
    print(f"\n  Score gaps (Stefano - Bot, lower is better):")
    print(f"  {'Dimension':20s} {'Before':>8s} {'After':>8s} {'Delta':>8s} {'Win% Δ':>8s}")
    print(f"  {'─'*52}")
    for dim in DIMENSIONS:
        g_before = before["avg_gap"].get(dim, 0)
        g_after = after["avg_gap"].get(dim, 0)
        g_delta = g_after - g_before

        w_before = before["win_rates"].get(dim, 0)
        w_after = after["win_rates"].get(dim, 0)
        w_delta = w_after - w_before

        marker = ""
        if g_delta < -3:
            marker = " IMPROVED"
        elif g_delta > 3:
            marker = " REGRESSED"

        print(f"  {dim:20s} {g_before:>+7.1f} {g_after:>+7.1f} {g_delta:>+7.1f} {w_delta:>+7.1f}%{marker}")

    # Per-category comparison
    all_cats = set(list(before.get("by_category", {}).keys()) + list(after.get("by_category", {}).keys()))
    if all_cats:
        print(f"\n  By category (indistinguishable %):")
        print(f"  {'Category':20s} {'Before':>8s} {'After':>8s} {'Delta':>8s}")
        print(f"  {'─'*44}")
        for cat in sorted(all_cats):
            b_cat = before.get("by_category", {}).get(cat, {})
            a_cat = after.get("by_category", {}).get(cat, {})
            b_val = b_cat.get("indistinguishable", 0)
            a_val = a_cat.get("indistinguishable", 0)
            delta = a_val - b_val
            print(f"  {cat:20s} {b_val:>7.1f}% {a_val:>7.1f}% {delta:>+7.1f}%")

    # Verdict
    print(f"\n  {'─'*51}")
    improvements = 0
    regressions = 0
    for dim in DIMENSIONS:
        g_delta = after["avg_gap"].get(dim, 0) - before["avg_gap"].get(dim, 0)
        if g_delta < -2:
            improvements += 1
        elif g_delta > 2:
            regressions += 1

    if ind_delta > 5 and improvements > regressions:
        verdict = "SIGNIFICANT IMPROVEMENT"
    elif ind_delta > 0 and improvements >= regressions:
        verdict = "IMPROVEMENT"
    elif ind_delta < -5:
        verdict = "REGRESSION"
    else:
        verdict = "NO SIGNIFICANT CHANGE"

    print(f"  VERDICT: {verdict}")
    print(f"  Dimensions improved: {improvements}/{len(DIMENSIONS)}")
    print(f"  Dimensions regressed: {regressions}/{len(DIMENSIONS)}")
    print(f"{'='*70}\n")


def main():
    parser = argparse.ArgumentParser(description="Compare Backtest Results")
    parser.add_argument("--before", required=True, help="Path to before judge results JSON")
    parser.add_argument("--after", required=True, help="Path to after judge results JSON")
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    before_path = Path(args.before)
    after_path = Path(args.after)

    for p in [before_path, after_path]:
        if not p.exists():
            print(f"Error: File not found: {p}")
            sys.exit(1)

    with open(before_path, "r", encoding="utf-8") as f:
        before_data = json.load(f)
    with open(after_path, "r", encoding="utf-8") as f:
        after_data = json.load(f)

    before_metrics = extract_metrics_from_judge_results(before_data)
    after_metrics = extract_metrics_from_judge_results(after_data)

    print_comparison(before_metrics, after_metrics, before_path.name, after_path.name)

    # Save comparison
    if args.output:
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"comparison_{timestamp}.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({
                "compared_at": datetime.now(timezone.utc).isoformat(),
                "before_file": str(before_path),
                "after_file": str(after_path),
                "before_metrics": before_metrics,
                "after_metrics": after_metrics,
            }, f, ensure_ascii=False, indent=2)
        print(f"  Saved to: {output_path}")


if __name__ == "__main__":
    main()
