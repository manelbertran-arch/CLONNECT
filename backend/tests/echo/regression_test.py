"""
ECHO Engine Regression Test.

Run before each deploy to ensure CloneScore doesn't regress.
Compares current score against a saved baseline.

Usage:
    python -m tests.echo.regression_test --creator stefano
    python -m tests.echo.regression_test --creator stefano --update-baseline

Criteria:
    - FAIL if score drops more than 5 points from baseline
    - WARN if any dimension drops more than 8 points
    - PASS otherwise
"""
import json
import logging
import argparse
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from tests.echo.evaluator import EchoEvaluator, aggregate_clone_score, DIMENSION_WEIGHTS
from tests.echo.generate_test_set import load_test_set

logger = logging.getLogger(__name__)

BASELINES_DIR = Path(__file__).parent / "baselines"
TEST_SETS_DIR = Path(__file__).parent / "test_sets"

REGRESSION_TOLERANCE = 5.0       # Max allowed overall score drop
DIMENSION_TOLERANCE = 8.0        # Max allowed per-dimension drop
REGRESSION_SUBSET_SIZE = 20      # Number of test cases for quick regression


def load_baseline(creator: str) -> dict | None:
    """Load the saved baseline for a creator."""
    path = BASELINES_DIR / f"{creator}_baseline.json"
    if not path.exists():
        logger.warning(f"No baseline found at {path}")
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_baseline(creator: str, baseline: dict) -> Path:
    """Save a new baseline for a creator."""
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    path = BASELINES_DIR / f"{creator}_baseline.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(baseline, f, ensure_ascii=False, indent=2)
    logger.info(f"Baseline saved to {path}")
    return path


def select_regression_subset(test_cases: list[dict], count: int = REGRESSION_SUBSET_SIZE) -> list[dict]:
    """
    Select the most representative test cases for regression.

    Strategy: pick evenly across lead categories and topics.
    """
    from collections import defaultdict

    by_category: dict[str, list] = defaultdict(list)
    for tc in test_cases:
        by_category[tc.get("lead_category", "other")].append(tc)

    selected = []
    per_category = max(1, count // max(len(by_category), 1))

    for category, cases in sorted(by_category.items()):
        # Further diversify by topic within category
        by_topic: dict[str, list] = defaultdict(list)
        for tc in cases:
            topic = tc.get("metadata", {}).get("topic", "other")
            by_topic[topic].append(tc)

        cat_selected = []
        per_topic = max(1, per_category // max(len(by_topic), 1))
        for topic_cases in by_topic.values():
            cat_selected.extend(topic_cases[:per_topic])

        # Fill if needed
        remaining = [c for c in cases if c not in cat_selected]
        while len(cat_selected) < per_category and remaining:
            cat_selected.append(remaining.pop(0))

        selected.extend(cat_selected[:per_category])

    # Fill to target
    selected_ids = {tc.get("id") for tc in selected}
    remaining = [tc for tc in test_cases if tc.get("id") not in selected_ids]
    while len(selected) < count and remaining:
        selected.append(remaining.pop(0))

    return selected[:count]


async def run_regression(
    creator: str,
    creator_profile: dict,
    llm_provider=None,
    pipeline=None,
    test_set_path: str | Path | None = None,
    use_llm_judge: bool = True,
) -> dict:
    """
    Run regression test against baseline.

    Returns dict with status (PASS/FAIL/WARN), current scores, diff from baseline.
    """
    # Load test set
    if test_set_path:
        test_cases, metadata = load_test_set(test_set_path)
    else:
        default_path = TEST_SETS_DIR / f"{creator}_v1.json"
        if default_path.exists():
            test_cases, metadata = load_test_set(default_path)
        else:
            logger.warning("No test set found, using sample test cases")
            from tests.echo.generate_test_set import generate_synthetic_test_set
            test_cases = generate_synthetic_test_set(count=30)
            metadata = {}

    # Select regression subset
    subset = select_regression_subset(test_cases, REGRESSION_SUBSET_SIZE)
    logger.info(f"Regression: running {len(subset)} test cases")

    # Run evaluation
    evaluator = EchoEvaluator(
        creator_profile=creator_profile,
        llm_provider=llm_provider,
        use_llm_judge=use_llm_judge,
    )
    batch_result = await evaluator.evaluate_batch(subset, pipeline=pipeline)

    current_score = batch_result["overall_score"]
    current_dims = batch_result["dimension_averages"]

    # Load baseline
    baseline = load_baseline(creator)

    if baseline is None:
        return {
            "status": "NO_BASELINE",
            "message": f"No baseline found for '{creator}'. Run with --update-baseline to create one.",
            "current_score": current_score,
            "current_dimensions": current_dims,
            "baseline_score": None,
            "diff": None,
            "dimension_diffs": {},
            "details": batch_result,
        }

    baseline_score = baseline.get("overall_score", 0)
    baseline_dims = baseline.get("dimension_scores", {})

    # Compute diffs
    overall_diff = current_score - baseline_score
    dimension_diffs = {}
    warnings = []

    for dim in DIMENSION_WEIGHTS:
        current_dim = current_dims.get(dim, 50.0)
        baseline_dim = baseline_dims.get(dim, 50.0)
        diff = current_dim - baseline_dim
        dimension_diffs[dim] = {
            "current": current_dim,
            "baseline": baseline_dim,
            "diff": round(diff, 1),
        }
        if diff < -DIMENSION_TOLERANCE:
            warnings.append(
                f"{dim}: dropped {abs(diff):.1f} points "
                f"({baseline_dim:.1f} → {current_dim:.1f})"
            )

    # Determine status
    if overall_diff < -REGRESSION_TOLERANCE:
        status = "FAIL"
        message = (
            f"CloneScore REGRESSED by {abs(overall_diff):.1f} points "
            f"(baseline: {baseline_score:.1f} → current: {current_score:.1f})"
        )
    elif warnings:
        status = "WARN"
        message = (
            f"Overall OK (diff: {overall_diff:+.1f}) but "
            f"{len(warnings)} dimension(s) regressed: {', '.join(w.split(':')[0] for w in warnings)}"
        )
    else:
        status = "PASS"
        message = (
            f"No regression detected (baseline: {baseline_score:.1f} → "
            f"current: {current_score:.1f}, diff: {overall_diff:+.1f})"
        )

    return {
        "status": status,
        "message": message,
        "current_score": current_score,
        "baseline_score": baseline_score,
        "diff": round(overall_diff, 1),
        "current_dimensions": current_dims,
        "baseline_dimensions": baseline_dims,
        "dimension_diffs": dimension_diffs,
        "warnings": warnings,
        "test_count": len(subset),
        "details": batch_result,
    }


def print_regression_report(result: dict) -> None:
    """Print regression test report."""
    status_icon = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠", "NO_BASELINE": "?"}.get(
        result["status"], "?"
    )

    print(f"\n{'='*60}")
    print(f"  Regression Test: {result['status']} {status_icon}")
    print(f"{'='*60}")
    print(f"  {result['message']}")
    print(f"\n  Scores:")
    print(f"    Baseline:  {result.get('baseline_score', 'N/A')}")
    print(f"    Current:   {result['current_score']}")
    if result.get("diff") is not None:
        print(f"    Diff:      {result['diff']:+.1f}")

    if result.get("dimension_diffs"):
        print(f"\n  Dimensions:")
        for dim, data in result["dimension_diffs"].items():
            arrow = "↑" if data["diff"] > 0 else "↓" if data["diff"] < 0 else "→"
            print(
                f"    {dim:25s}: {data['baseline']:.1f} → {data['current']:.1f} "
                f"({data['diff']:+.1f}) {arrow}"
            )

    if result.get("warnings"):
        print(f"\n  Warnings:")
        for w in result["warnings"]:
            print(f"    ⚠ {w}")

    print(f"\n  Test cases: {result.get('test_count', 0)}")
    print(f"  Tolerance: ±{REGRESSION_TOLERANCE} overall, ±{DIMENSION_TOLERANCE} per dimension")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ECHO Engine regression test")
    parser.add_argument("--creator", default="stefano", help="Creator name")
    parser.add_argument("--test-set", default=None, help="Test set JSON path")
    parser.add_argument(
        "--update-baseline", action="store_true",
        help="Update the baseline with current results",
    )
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM judge")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    # Placeholder profile (in production, load from DB)
    from tests.echo.conftest import TestCase
    creator_profile = {
        "name": "Stefano Bonanno",
        "doc_d_summary": "Stefano es un coach de nutricion cercano, motivador, usa emojis, tutea.",
        "avg_message_length": 55,
        "avg_emoji_rate": 0.15,
        "avg_question_rate": 0.6,
        "informal_markers": ["jaja", "bro", "crack", "tio"],
        "top_vocabulary": ["curso", "nutricion", "plan", "personalizado"],
        "products": [
            {"name": "Curso Nutricion Consciente", "price": 197, "currency": "EUR"},
            {"name": "Plan Personalizado 3 meses", "price": 297, "currency": "EUR"},
        ],
    }

    result = asyncio.run(
        run_regression(
            creator=args.creator,
            creator_profile=creator_profile,
            test_set_path=args.test_set,
            use_llm_judge=not args.no_llm,
        )
    )

    print_regression_report(result)

    if args.update_baseline:
        new_baseline = {
            "version": "v1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "creator": args.creator,
            "overall_score": result["current_score"],
            "dimension_scores": result["current_dimensions"],
            "sample_size": result.get("test_count", 0),
            "test_set_version": f"{args.creator}_v1",
        }
        save_baseline(args.creator, new_baseline)
        print(f"Baseline updated to {result['current_score']}")

    # Exit code for CI/CD
    if result["status"] == "FAIL":
        exit(1)
    elif result["status"] == "WARN":
        exit(0)  # Warnings don't block deploy
    else:
        exit(0)


if __name__ == "__main__":
    main()
