#!/usr/bin/env python3
"""
ECHO Baseline Measurement CLI.

Runs CloneScore evaluation against real production data for a creator.
Requires DB connection and LLM API keys.

Usage:
    python scripts/echo_baseline.py --creator-id stefano_auto
    python scripts/echo_baseline.py --creator-id stefano_auto --sample-size 100
    python scripts/echo_baseline.py --creator-id stefano_auto --output-dir results/
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

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("echo_baseline")


DIMENSION_LABELS = {
    "style_fidelity": "Style Fidelity",
    "knowledge_accuracy": "Knowledge Accuracy",
    "persona_consistency": "Persona Consistency",
    "tone_appropriateness": "Tone Appropriateness",
    "sales_effectiveness": "Sales Effectiveness",
    "safety_score": "Safety Score",
}

THRESHOLDS = {
    "excellent": 90,
    "good": 75,
    "acceptable": 60,
    "needs_improvement": 40,
    "critical": 0,
}


def classify_score(score: float) -> str:
    for label, threshold in THRESHOLDS.items():
        if score >= threshold:
            return label
    return "critical"


def print_results(result: dict, creator_id: str):
    """Print formatted results table."""
    print("\n" + "=" * 60)
    print(f"  ECHO Baseline — {creator_id}")
    print(f"  Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    dims = result.get("dimension_scores", {})
    overall = result.get("overall_score", 0)

    print(f"\n{'Dimension':<25} {'Score':>8} {'Rating':>20}")
    print("-" * 55)
    for dim_key, label in DIMENSION_LABELS.items():
        score = dims.get(dim_key, 0)
        rating = classify_score(score)
        bar = "█" * int(score / 5) + "░" * (20 - int(score / 5))
        print(f"  {label:<23} {score:>6.1f}   {bar} {rating}")

    print("-" * 55)
    overall_rating = classify_score(overall)
    print(f"  {'OVERALL':<23} {overall:>6.1f}   {'█' * int(overall / 5)}{'░' * (20 - int(overall / 5))} {overall_rating}")

    print(f"\n  Samples evaluated: {result.get('sample_size', 0)}")
    print(f"  LLM evaluations:  {result.get('llm_samples', 0)}")
    print(f"  Elapsed:          {result.get('elapsed_ms', 0)}ms")

    if result.get("skipped"):
        print(f"\n  SKIPPED: {result.get('reason', 'unknown')}")

    print("=" * 60 + "\n")


def save_results(result: dict, creator_id: str, output_dir: str):
    """Save results to JSON file."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    filename = f"echo_results_{creator_id}_{date_str}.json"
    filepath = output_path / filename

    output = {
        "version": "1.0",
        "creator_id": creator_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": result,
        "thresholds": THRESHOLDS,
        "classifications": {},
    }

    dims = result.get("dimension_scores", {})
    for dim, score in dims.items():
        output["classifications"][dim] = classify_score(score)
    output["classifications"]["overall"] = classify_score(result.get("overall_score", 0))

    with open(filepath, "w") as f:
        json.dump(output, f, indent=2, default=str)

    logger.info(f"Results saved to {filepath}")
    return filepath


async def run_baseline(creator_id: str, sample_size: int) -> dict:
    """Run baseline evaluation for a creator."""
    from api.database import SessionLocal
    from api.models import Creator
    from services.clone_score_engine import get_clone_score_engine

    session = SessionLocal()
    try:
        creator = (
            session.query(Creator.id, Creator.name)
            .filter(Creator.name == creator_id)
            .first()
        )
        if not creator:
            logger.error(f"Creator '{creator_id}' not found in database")
            return {"error": f"Creator not found: {creator_id}"}

        creator_db_id, creator_name = creator
        logger.info(f"Running baseline for {creator_name} (id={creator_db_id})")
    finally:
        session.close()

    engine = get_clone_score_engine()
    result = await engine.evaluate_batch(
        creator_id=creator_name,
        creator_db_id=creator_db_id,
        sample_size=sample_size,
    )

    return result


def main():
    parser = argparse.ArgumentParser(
        description="ECHO Baseline Measurement CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/echo_baseline.py --creator-id stefano_auto
    python scripts/echo_baseline.py --creator-id stefano_auto --sample-size 100
    python scripts/echo_baseline.py --creator-id stefano_auto --output-dir results/
        """,
    )
    parser.add_argument(
        "--creator-id",
        required=True,
        help="Creator name (e.g., stefano_auto)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=50,
        help="Number of messages to evaluate (default: 50)",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to save results JSON (default: current dir)",
    )

    args = parser.parse_args()

    # Verify environment
    if not os.getenv("DATABASE_URL"):
        logger.error("DATABASE_URL not set. This script requires a real database connection.")
        sys.exit(1)

    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("OPENAI_API_KEY not set. LLM judge dimensions will use fallback scores.")

    logger.info(f"Starting baseline: creator={args.creator_id}, samples={args.sample_size}")
    start = time.monotonic()

    result = asyncio.run(run_baseline(args.creator_id, args.sample_size))

    elapsed = int((time.monotonic() - start) * 1000)
    logger.info(f"Baseline completed in {elapsed}ms")

    print_results(result, args.creator_id)

    if "error" not in result:
        filepath = save_results(result, args.creator_id, args.output_dir)
        print(f"Results saved to: {filepath}")
    else:
        logger.error(f"Baseline failed: {result['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
