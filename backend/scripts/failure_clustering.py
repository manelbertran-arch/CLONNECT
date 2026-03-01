#!/usr/bin/env python3
"""
Failure clustering: identify WHERE and WHY the bot fails.

Groups failures by category, topic, turn position, message length, and dimension.
For each cluster, identifies patterns and suggests improvements.

Usage:
    python3.11 scripts/failure_clustering.py --input results/judge_results_XXX.json
    python3.11 scripts/failure_clustering.py --input results/judge_results_XXX.json --threshold 15
"""
import sys
import json
import argparse
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

logger = logging.getLogger(__name__)

DIMENSIONS = ["naturalidad", "relevancia", "estilo", "efectividad", "personalidad"]

# Gap threshold for "significant failure"
DEFAULT_GAP_THRESHOLD = 15  # Bot scores 15+ points below Stefano


def compute_pair_gap(evaluation: dict) -> float:
    """Compute the average gap between Stefano and bot scores."""
    ss = evaluation.get("stefano_scores", {})
    bs = evaluation.get("bot_scores", {})
    gaps = []
    for dim in DIMENSIONS:
        s_val = ss.get(dim, 50)
        b_val = bs.get(dim, 50)
        if isinstance(s_val, (int, float)) and isinstance(b_val, (int, float)):
            gaps.append(s_val - b_val)  # Positive = Stefano better
    return sum(gaps) / len(gaps) if gaps else 0


def classify_message_length(text: str) -> str:
    """Classify message length bucket."""
    n = len(text)
    if n < 20:
        return "muy_corto (<20)"
    elif n < 50:
        return "corto (20-49)"
    elif n < 100:
        return "medio (50-99)"
    elif n < 200:
        return "largo (100-199)"
    else:
        return "muy_largo (200+)"


def classify_turn_position(turn_index: int) -> str:
    """Classify turn position in conversation."""
    if turn_index == 0:
        return "primer_turno"
    elif turn_index <= 2:
        return "inicio (1-2)"
    elif turn_index <= 5:
        return "medio (3-5)"
    else:
        return "avanzado (6+)"


def extract_failure_patterns(failures: list[dict]) -> list[str]:
    """Extract common textual patterns from failures."""
    patterns = []

    # Check for common themes in bot responses
    bot_responses = [f.get("bot_response", "") for f in failures]
    stefano_responses = [f.get("stefano_real", "") for f in failures]

    # Length comparison
    bot_lengths = [len(r) for r in bot_responses if r]
    stef_lengths = [len(r) for r in stefano_responses if r]
    if bot_lengths and stef_lengths:
        avg_bot = sum(bot_lengths) / len(bot_lengths)
        avg_stef = sum(stef_lengths) / len(stef_lengths)
        if avg_bot > avg_stef * 1.5:
            patterns.append(f"Bot responses too long (avg {avg_bot:.0f} vs Stefano {avg_stef:.0f} chars)")
        elif avg_bot < avg_stef * 0.5:
            patterns.append(f"Bot responses too short (avg {avg_bot:.0f} vs Stefano {avg_stef:.0f} chars)")

    # Emoji comparison
    import re
    emoji_re = re.compile(
        "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF"
        "\U00002702-\U000027B0\U0000FE00-\U0000FE0F]+",
        flags=re.UNICODE,
    )
    bot_emoji_rate = sum(1 for r in bot_responses if emoji_re.search(r)) / max(len(bot_responses), 1)
    stef_emoji_rate = sum(1 for r in stefano_responses if emoji_re.search(r)) / max(len(stefano_responses), 1)
    if abs(bot_emoji_rate - stef_emoji_rate) > 0.2:
        patterns.append(f"Emoji usage mismatch (bot {bot_emoji_rate:.0%} vs Stefano {stef_emoji_rate:.0%})")

    # Question usage
    bot_q_rate = sum(1 for r in bot_responses if "?" in r) / max(len(bot_responses), 1)
    stef_q_rate = sum(1 for r in stefano_responses if "?" in r) / max(len(stefano_responses), 1)
    if abs(bot_q_rate - stef_q_rate) > 0.2:
        patterns.append(f"Question rate mismatch (bot {bot_q_rate:.0%} vs Stefano {stef_q_rate:.0%})")

    # Formality check (presence of periods, formal phrases)
    bot_formal = sum(1 for r in bot_responses if r.endswith(".") or "usted" in r.lower()) / max(len(bot_responses), 1)
    if bot_formal > 0.2:
        patterns.append(f"Bot too formal ({bot_formal:.0%} responses end with period or use 'usted')")

    # Generic/template detection
    generic_phrases = ["no dudes en", "con mucho gusto", "a tu disposicion", "no te preocupes"]
    bot_generic = sum(
        1 for r in bot_responses
        if any(p in r.lower() for p in generic_phrases)
    ) / max(len(bot_responses), 1)
    if bot_generic > 0.2:
        patterns.append(f"Bot uses generic phrases ({bot_generic:.0%} of failures)")

    return patterns


def cluster_failures(
    evaluations: list[dict],
    gap_threshold: float = DEFAULT_GAP_THRESHOLD,
) -> dict:
    """Cluster failures by multiple axes."""
    # Separate failures from successes
    failures = []
    successes = []

    for ev in evaluations:
        if "error" in ev:
            continue
        gap = compute_pair_gap(ev)
        ev["_avg_gap"] = gap
        if gap >= gap_threshold:
            failures.append(ev)
        else:
            successes.append(ev)

    clusters = {
        "summary": {
            "total_evaluated": len(evaluations),
            "total_failures": len(failures),
            "total_successes": len(successes),
            "failure_rate": round(len(failures) / max(len(evaluations), 1) * 100, 1),
            "gap_threshold": gap_threshold,
        },
        "by_category": {},
        "by_topic": {},
        "by_turn_position": {},
        "by_message_length": {},
        "by_dimension": {},
        "worst_cases": [],
        "patterns": [],
    }

    # By category
    cat_failures = defaultdict(list)
    cat_totals = Counter()
    for ev in evaluations:
        if "error" in ev:
            continue
        cat = ev.get("lead_category", "OTRO")
        cat_totals[cat] += 1
        if ev in failures:
            cat_failures[cat].append(ev)

    for cat in cat_totals:
        f_list = cat_failures[cat]
        clusters["by_category"][cat] = {
            "total": cat_totals[cat],
            "failures": len(f_list),
            "failure_rate": round(len(f_list) / max(cat_totals[cat], 1) * 100, 1),
            "avg_gap": round(sum(f["_avg_gap"] for f in f_list) / max(len(f_list), 1), 1) if f_list else 0,
        }

    # By topic
    topic_failures = defaultdict(list)
    topic_totals = Counter()
    for ev in evaluations:
        if "error" in ev:
            continue
        topic = ev.get("topic", "otro")
        topic_totals[topic] += 1
        if ev in failures:
            topic_failures[topic].append(ev)

    for topic in topic_totals:
        f_list = topic_failures[topic]
        clusters["by_topic"][topic] = {
            "total": topic_totals[topic],
            "failures": len(f_list),
            "failure_rate": round(len(f_list) / max(topic_totals[topic], 1) * 100, 1),
            "avg_gap": round(sum(f["_avg_gap"] for f in f_list) / max(len(f_list), 1), 1) if f_list else 0,
        }

    # By turn position
    pos_failures = defaultdict(list)
    pos_totals = Counter()
    for ev in evaluations:
        if "error" in ev:
            continue
        pos = classify_turn_position(ev.get("turn_index", 0))
        pos_totals[pos] += 1
        if ev in failures:
            pos_failures[pos].append(ev)

    for pos in pos_totals:
        f_list = pos_failures[pos]
        clusters["by_turn_position"][pos] = {
            "total": pos_totals[pos],
            "failures": len(f_list),
            "failure_rate": round(len(f_list) / max(pos_totals[pos], 1) * 100, 1),
        }

    # By message length (of Stefano's response)
    len_failures = defaultdict(list)
    len_totals = Counter()
    for ev in evaluations:
        if "error" in ev:
            continue
        bucket = classify_message_length(ev.get("stefano_real", ""))
        len_totals[bucket] += 1
        if ev in failures:
            len_failures[bucket].append(ev)

    for bucket in len_totals:
        f_list = len_failures[bucket]
        clusters["by_message_length"][bucket] = {
            "total": len_totals[bucket],
            "failures": len(f_list),
            "failure_rate": round(len(f_list) / max(len_totals[bucket], 1) * 100, 1),
        }

    # By dimension (which dimensions have the largest gaps)
    dim_gaps = defaultdict(list)
    for ev in failures:
        ss = ev.get("stefano_scores", {})
        bs = ev.get("bot_scores", {})
        for dim in DIMENSIONS:
            s_val = ss.get(dim, 50)
            b_val = bs.get(dim, 50)
            if isinstance(s_val, (int, float)) and isinstance(b_val, (int, float)):
                dim_gaps[dim].append(s_val - b_val)

    for dim in DIMENSIONS:
        gaps = dim_gaps[dim]
        if gaps:
            clusters["by_dimension"][dim] = {
                "avg_gap": round(sum(gaps) / len(gaps), 1),
                "max_gap": round(max(gaps), 1),
                "failures_with_gap_gt_20": sum(1 for g in gaps if g > 20),
            }

    # Worst cases (top 10 by gap)
    sorted_failures = sorted(failures, key=lambda f: f["_avg_gap"], reverse=True)
    for f in sorted_failures[:10]:
        clusters["worst_cases"].append({
            "conversation_id": f.get("conversation_id"),
            "avg_gap": round(f["_avg_gap"], 1),
            "lead_message": f.get("lead_message", "")[:200],
            "stefano_real": f.get("stefano_real", "")[:200],
            "bot_response": f.get("bot_response", "")[:200],
            "lead_category": f.get("lead_category"),
            "topic": f.get("topic"),
            "stefano_scores": f.get("stefano_scores"),
            "bot_scores": f.get("bot_scores"),
        })

    # Extract patterns
    clusters["patterns"] = extract_failure_patterns(failures)

    return clusters


def print_clustering_report(clusters: dict):
    """Print the failure clustering report."""
    s = clusters["summary"]

    print(f"\n{'='*60}")
    print(f"  Failure Clustering Report")
    print(f"{'='*60}")
    print(f"\n  Total evaluated: {s['total_evaluated']}")
    print(f"  Failures (gap >= {s['gap_threshold']}): {s['total_failures']} ({s['failure_rate']:.1f}%)")
    print(f"  Successes: {s['total_successes']}")

    print(f"\n  By Lead Category:")
    print(f"  {'Category':20s} {'Total':>6s} {'Fails':>6s} {'Rate':>6s} {'Gap':>6s}")
    print(f"  {'─'*44}")
    for cat, data in sorted(clusters["by_category"].items(), key=lambda x: -x[1]["failure_rate"]):
        print(f"  {cat:20s} {data['total']:>6d} {data['failures']:>6d} {data['failure_rate']:>5.1f}% {data['avg_gap']:>+5.1f}")

    print(f"\n  By Topic:")
    for topic, data in sorted(clusters["by_topic"].items(), key=lambda x: -x[1]["failure_rate"]):
        print(f"  {topic:20s} {data['total']:>6d} {data['failures']:>6d} {data['failure_rate']:>5.1f}%")

    print(f"\n  By Turn Position:")
    for pos, data in sorted(clusters["by_turn_position"].items()):
        print(f"  {pos:20s} {data['total']:>6d} {data['failures']:>6d} {data['failure_rate']:>5.1f}%")

    print(f"\n  By Message Length:")
    for bucket, data in sorted(clusters["by_message_length"].items()):
        print(f"  {bucket:20s} {data['total']:>6d} {data['failures']:>6d} {data['failure_rate']:>5.1f}%")

    print(f"\n  By Dimension (in failures):")
    print(f"  {'Dimension':20s} {'Avg Gap':>8s} {'Max Gap':>8s} {'Gap>20':>6s}")
    print(f"  {'─'*42}")
    for dim in DIMENSIONS:
        data = clusters["by_dimension"].get(dim, {})
        if data:
            print(f"  {dim:20s} {data['avg_gap']:>+7.1f} {data['max_gap']:>+7.1f} {data['failures_with_gap_gt_20']:>6d}")

    if clusters["patterns"]:
        print(f"\n  Detected Patterns:")
        for i, pattern in enumerate(clusters["patterns"], 1):
            print(f"    {i}. {pattern}")

    if clusters["worst_cases"]:
        print(f"\n  Worst Cases (top 3):")
        for i, wc in enumerate(clusters["worst_cases"][:3], 1):
            print(f"\n    #{i} (gap: {wc['avg_gap']:+.1f}, {wc['lead_category']}/{wc['topic']})")
            print(f"    Lead:    {wc['lead_message'][:80]}")
            print(f"    Stefano: {wc['stefano_real'][:80]}")
            print(f"    Bot:     {wc['bot_response'][:80]}")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Failure Clustering Analysis")
    parser.add_argument("--input", required=True, help="Path to judge results JSON")
    parser.add_argument("--threshold", type=float, default=DEFAULT_GAP_THRESHOLD, help="Gap threshold for failure")
    parser.add_argument("--judge", default=None, help="Filter to specific judge name")
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    evaluations = data.get("evaluations", [])
    if not evaluations:
        print("Error: No evaluations found in input file")
        sys.exit(1)

    # Filter by judge if specified
    if args.judge:
        evaluations = [e for e in evaluations if e.get("judge") == args.judge]

    print(f"  Loaded {len(evaluations)} evaluations from {input_path.name}")

    clusters = cluster_failures(evaluations, gap_threshold=args.threshold)
    print_clustering_report(clusters)

    # Save
    output_dir = Path(args.output) if args.output else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"failure_clusters_{timestamp}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "input_file": str(input_path),
            "threshold": args.threshold,
            "clusters": clusters,
        }, f, ensure_ascii=False, indent=2, default=str)

    print(f"  Saved to: {output_path}")
    print(f"\n  Next: Run auto-learner:")
    print(f"  python3.11 scripts/auto_learner.py --judge-input {input_path} --clusters-input {output_path}")


if __name__ == "__main__":
    main()
