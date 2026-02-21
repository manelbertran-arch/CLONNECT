#!/usr/bin/env python3
"""
ECHO Engine Master Validation Script.

Orchestrates all test modules and generates a unified report.

Usage:
    python tests/echo/run_validation.py --mode full       # Everything
    python tests/echo/run_validation.py --mode quick      # Regression only (20 cases)
    python tests/echo/run_validation.py --mode stress     # Stress test only
    python tests/echo/run_validation.py --mode ab         # A/B comparison only
    python tests/echo/run_validation.py --mode eval       # Full evaluation only
    python tests/echo/run_validation.py --mode validation # Generate HTML for Stefano

Options:
    --creator NAME      Creator name (default: stefano)
    --test-set PATH     Path to test set JSON
    --no-llm            Skip LLM-judge evaluations (free but less accurate)
    --synthetic         Use synthetic test data (no DB required)
    --concurrent N      Concurrent workers for stress test (default: 10)
    --output PATH       Output directory for reports

Cost estimate (full mode, 100 test cases):
    - Evaluation (6 dims x 3 LLM calls): ~$6.00
    - A/B comparison (100 calls): ~$2.00
    - Total: ~$8.00
"""
import os
import sys
import json
import time
import asyncio
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from tests.echo.evaluator import EchoEvaluator, score_label, DIMENSION_WEIGHTS
from tests.echo.ab_comparison import ABComparisonRunner, print_ab_report
from tests.echo.regression_test import run_regression, print_regression_report, save_baseline
from tests.echo.stress_test import StressTestRunner, print_stress_report
from tests.echo.stefano_validation import generate_validation_html
from tests.echo.dashboard_data import (
    generate_dashboard_from_test_cases,
    save_dashboard,
    print_dashboard_summary,
)
from tests.echo.generate_test_set import (
    load_test_set,
    generate_synthetic_test_set,
    save_test_set,
    print_stats,
    compute_stats,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default creator profile (loaded from DB in production)
# ---------------------------------------------------------------------------

DEFAULT_CREATOR_PROFILE = {
    "name": "Stefano Bonanno",
    "doc_d_summary": (
        "Stefano es un coach de nutricion y bienestar italiano radicado en Espana. "
        "Es cercano, motivador, usa emojis frecuentemente (especialmente 💪🔥😊), "
        "tutea a todos, usa voseo informal. Habla en espanol con toques de italiano. "
        "Vende cursos de nutricion y planes personalizados. "
        "Es directo pero nunca agresivo. Usa 'jaja', 'bro', 'crack'. "
        "Respuestas cortas (30-80 palabras). Siempre cierra con pregunta o CTA."
    ),
    "avg_message_length": 85,  # avg chars per message
    "avg_emoji_rate": 0.15,
    "avg_question_rate": 0.6,
    "informal_markers": ["jaja", "bro", "crack", "tio", "vamos", "dale"],
    "top_vocabulary": [
        "curso", "nutricion", "plan", "personalizado", "energia",
        "resultados", "salud", "entrenamiento", "comida", "cambio",
        "habito", "objetivo", "progreso", "motivacion", "bienestar",
    ],
    "products": [
        {"name": "Curso Nutricion Consciente", "price": 197, "currency": "EUR"},
        {"name": "Plan Personalizado 3 meses", "price": 297, "currency": "EUR"},
        {"name": "Masterclass Energia", "price": 47, "currency": "EUR"},
        {"name": "Ebook Recetas Fit", "price": 19, "currency": "EUR"},
    ],
}


# ---------------------------------------------------------------------------
# Pipeline loader
# ---------------------------------------------------------------------------

def load_pipeline():
    """Try to load the real DM pipeline, return None if unavailable."""
    try:
        from core.dm_agent_v2 import DMResponderAgentV2
        pipeline = DMResponderAgentV2()
        logger.info("Loaded real DM pipeline")
        return pipeline
    except Exception as e:
        logger.info(f"Real pipeline not available ({e}), using mock")
        return None


def load_llm_provider():
    """Try to load the real Gemini provider, return None if unavailable."""
    try:
        from core.providers.gemini_provider import _call_gemini
        logger.info("Loaded Gemini LLM provider")
        return _call_gemini
    except Exception as e:
        logger.info(f"Gemini provider not available ({e}), using mock")
        return None


def load_creator_profile(creator: str):
    """Try to load creator profile from DB, fallback to default."""
    try:
        from tests.echo.generate_test_set import get_db_session, resolve_creator_id
        session = get_db_session()
        creator_id = resolve_creator_id(session, creator)

        # Load tone profile
        from api.models import ToneProfile, Product, Creator
        creator_row = session.query(Creator).filter(Creator.id == creator_id).first()
        tone = session.query(ToneProfile).filter(ToneProfile.creator_id == creator_id).first()
        products = session.query(Product).filter(Product.creator_id == creator_id).all()

        profile = dict(DEFAULT_CREATOR_PROFILE)
        profile["name"] = creator_row.name if creator_row else creator.title()

        if tone and tone.profile_data:
            pd = tone.profile_data
            profile["avg_emoji_rate"] = pd.get("emoji_frequency_score", 0.15)
            profile["informal_markers"] = pd.get("muletillas", profile["informal_markers"])

        if products:
            profile["products"] = [
                {"name": p.name, "price": float(p.price) if p.price else 0, "currency": "EUR"}
                for p in products
            ]

        session.close()
        logger.info(f"Loaded profile for {profile['name']} from DB")
        return profile

    except Exception as e:
        logger.info(f"Could not load profile from DB ({e}), using default")
        return DEFAULT_CREATOR_PROFILE


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

async def run_full(args, test_cases, profile, pipeline, llm_provider):
    """Run full validation suite."""
    print("\n" + "=" * 60)
    print("  ECHO Engine — Full Validation Suite")
    print("=" * 60)

    all_results = {}
    total_start = time.perf_counter()

    # 1. Evaluation
    print("\n[1/5] Running CloneScore evaluation...")
    evaluator = EchoEvaluator(
        creator_profile=profile,
        llm_provider=llm_provider,
        use_llm_judge=not args.no_llm,
    )
    eval_results = await evaluator.evaluate_batch(test_cases, pipeline=pipeline)
    all_results["evaluation"] = eval_results
    print(f"  CloneScore: {eval_results['overall_score']:.1f}/100 ({score_label(eval_results['overall_score'])})")

    # 2. A/B Comparison
    print("\n[2/5] Running A/B blind comparison...")
    ab_runner = ABComparisonRunner(
        creator_profile=profile,
        llm_provider=llm_provider,
    )
    ab_results = await ab_runner.run(test_cases, pipeline=pipeline)
    all_results["ab_comparison"] = ab_results
    print(f"  Indistinguishable: {ab_results['indistinguishable_rate']*100:.1f}%")

    # 3. Regression
    print("\n[3/5] Running regression test...")
    regression_results = await run_regression(
        creator=args.creator,
        creator_profile=profile,
        llm_provider=llm_provider,
        pipeline=pipeline,
        use_llm_judge=not args.no_llm,
    )
    all_results["regression"] = regression_results
    print(f"  Status: {regression_results['status']}")

    # 4. Stress test
    print("\n[4/5] Running stress test...")
    stress_runner = StressTestRunner(
        pipeline=pipeline,
        concurrent=args.concurrent,
        duration_secs=15,  # Shorter for full suite
    )
    stress_results = await stress_runner.run()
    all_results["stress"] = stress_results
    print(f"  p95: {stress_results.get('latency', {}).get('p95_ms', 0):.0f}ms")

    # 5. Dashboard data
    print("\n[5/5] Generating dashboard data...")
    dashboard = generate_dashboard_from_test_cases(
        test_cases, eval_results, creator_name=profile.get("name", args.creator)
    )
    all_results["dashboard"] = dashboard

    total_time = time.perf_counter() - total_start

    # Print unified report
    _print_unified_report(all_results, profile, len(test_cases), total_time)

    return all_results


async def run_quick(args, test_cases, profile, pipeline, llm_provider):
    """Run quick regression only (20 cases)."""
    print("\n" + "=" * 60)
    print("  ECHO Engine — Quick Regression")
    print("=" * 60)

    result = await run_regression(
        creator=args.creator,
        creator_profile=profile,
        llm_provider=llm_provider,
        pipeline=pipeline,
        use_llm_judge=not args.no_llm,
    )
    print_regression_report(result)
    return {"regression": result}


async def run_stress_mode(args, profile, pipeline):
    """Run stress test only."""
    print("\n" + "=" * 60)
    print("  ECHO Engine — Stress Test")
    print("=" * 60)

    runner = StressTestRunner(
        pipeline=pipeline,
        concurrent=args.concurrent,
        duration_secs=args.duration or 30,
    )
    result = await runner.run()
    print_stress_report(result)
    return {"stress": result}


async def run_ab_mode(args, test_cases, profile, pipeline, llm_provider):
    """Run A/B comparison only."""
    print("\n" + "=" * 60)
    print("  ECHO Engine — A/B Blind Comparison")
    print("=" * 60)

    runner = ABComparisonRunner(
        creator_profile=profile,
        llm_provider=llm_provider,
    )
    result = await runner.run(test_cases, pipeline=pipeline)
    print_ab_report(result)
    return {"ab_comparison": result}


async def run_eval_mode(args, test_cases, profile, pipeline, llm_provider):
    """Run full evaluation only."""
    print("\n" + "=" * 60)
    print("  ECHO Engine — Full Evaluation")
    print("=" * 60)

    evaluator = EchoEvaluator(
        creator_profile=profile,
        llm_provider=llm_provider,
        use_llm_judge=not args.no_llm,
    )
    result = await evaluator.evaluate_batch(test_cases, pipeline=pipeline)

    dashboard = generate_dashboard_from_test_cases(
        test_cases, result, creator_name=profile.get("name", args.creator)
    )
    print_dashboard_summary(dashboard)
    return {"evaluation": result, "dashboard": dashboard}


async def run_validation_mode(args, test_cases, profile, pipeline):
    """Generate HTML for Stefano validation."""
    print("\n" + "=" * 60)
    print("  ECHO Engine — Creator Validation HTML")
    print("=" * 60)

    output = args.output or str(Path(__file__).parent / f"validation_{args.creator}.html")
    path = await generate_validation_html(
        creator_name=profile.get("name", args.creator.title()),
        test_cases=test_cases,
        pipeline=pipeline,
        count=20,
        output_path=output,
    )
    print(f"\nHTML generated: {path}")
    print(f"Open in browser: file://{path.resolve()}")
    return {"validation_html": str(path)}


# ---------------------------------------------------------------------------
# Unified report
# ---------------------------------------------------------------------------

def _print_unified_report(results: dict, profile: dict, test_set_size: int, total_time: float):
    """Print the final unified validation report."""
    eval_r = results.get("evaluation", {})
    ab_r = results.get("ab_comparison", {})
    reg_r = results.get("regression", {})
    stress_r = results.get("stress", {})

    overall = eval_r.get("overall_score", 0)
    dims = eval_r.get("dimension_averages", {})
    latency = eval_r.get("latency", {})

    print(f"\n{'='*60}")
    print(f"  ECHO Engine Validation Report")
    print(f"{'='*60}")
    print(f"  Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Creator: {profile.get('name', 'Unknown')}")
    print(f"  Duration: {total_time:.1f}s")

    print(f"\n  Test Set: {test_set_size} cases")
    print(f"  CloneScore: {overall:.1f}/100")
    for dim, weight in DIMENSION_WEIGHTS.items():
        score = dims.get(dim, 0)
        bar_len = int(score / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        print(f"    - {dim:25s} {bar} {score:.1f}")

    ab_rate = ab_r.get("indistinguishable_rate", 0) * 100
    print(f"\n  A/B Blind Test: {ab_rate:.0f}% indistinguishable")

    reg_status = reg_r.get("status", "N/A")
    reg_base = reg_r.get("baseline_score")
    reg_current = reg_r.get("current_score", 0)
    if reg_base is not None:
        print(f"  Regression: {reg_status} (baseline: {reg_base:.1f} → current: {reg_current:.1f})")
    else:
        print(f"  Regression: {reg_status}")

    stress_lat = stress_r.get("latency", {})
    stress_err = stress_r.get("errors", 0)
    stress_total = stress_r.get("total_requests", 0)
    print(f"  Stress: p95={stress_lat.get('p95_ms', 0):.1f}ms, errors={stress_err}/{stress_total}")

    print(f"  Latency: avg {latency.get('avg_ms', 0):.1f}ms, p95 {latency.get('p95_ms', 0):.1f}ms")

    # Issues
    dashboard = results.get("dashboard", {})
    issues = dashboard.get("issues", [])
    if issues:
        print(f"\n  Top issues:")
        for i, issue in enumerate(issues[:5], 1):
            print(f"    {i}. {issue['message']}")

    # Verdict
    print(f"\n  {'─'*56}")
    if overall >= 80:
        verdict = "READY FOR AUTOPILOT (score >= 80)"
    elif overall >= 75:
        verdict = "READY FOR COPILOT (score >= 75)"
    elif overall >= 60:
        verdict = "NEEDS IMPROVEMENT (score 60-74)"
    else:
        verdict = "NOT READY (score < 60)"
    print(f"  VERDICT: {verdict}")

    # Cost
    stats = eval_r.get("stats", {})
    total_cost = stats.get("total_cost_usd", 0) + ab_r.get("cost_usd", 0)
    print(f"  Total cost: ${total_cost:.2f}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ECHO Engine Master Validation Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  full       - Run all tests (eval + A/B + regression + stress + dashboard)
  quick      - Regression only (20 test cases, ~$1.20)
  stress     - Stress test only (no LLM cost)
  ab         - A/B blind comparison only (~$2.00)
  eval       - Full evaluation only (~$6.00)
  validation - Generate HTML for creator review

Examples:
  python tests/echo/run_validation.py --mode quick
  python tests/echo/run_validation.py --mode full --synthetic
  python tests/echo/run_validation.py --mode stress --concurrent 20
  python tests/echo/run_validation.py --mode validation --output /tmp/exam.html
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["full", "quick", "stress", "ab", "eval", "validation"],
        default="quick",
        help="Validation mode (default: quick)",
    )
    parser.add_argument("--creator", default="stefano", help="Creator name")
    parser.add_argument("--test-set", default=None, help="Test set JSON path")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM judge ($0 cost)")
    parser.add_argument("--synthetic", action="store_true", help="Use synthetic data (no DB)")
    parser.add_argument("--concurrent", type=int, default=10, help="Stress test concurrent workers")
    parser.add_argument("--duration", type=int, default=None, help="Stress test duration (seconds)")
    parser.add_argument("--output", default=None, help="Output path for reports/HTML")
    parser.add_argument("--save-results", action="store_true", help="Save results to JSON")
    parser.add_argument("--update-baseline", action="store_true", help="Update regression baseline")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Load test set
    test_cases = []
    if args.test_set:
        test_cases, _ = load_test_set(args.test_set)
        logger.info(f"Loaded {len(test_cases)} test cases from {args.test_set}")
    elif args.synthetic:
        test_cases = generate_synthetic_test_set(count=100)
        logger.info(f"Generated {len(test_cases)} synthetic test cases")
    else:
        default_path = Path(__file__).parent / "test_sets" / f"{args.creator}_v1.json"
        if default_path.exists():
            test_cases, _ = load_test_set(default_path)
            logger.info(f"Loaded {len(test_cases)} test cases from {default_path}")
        else:
            logger.info("No test set found, generating synthetic data")
            test_cases = generate_synthetic_test_set(count=100)
            # Save for future runs
            save_test_set(
                test_cases,
                default_path,
                args.creator,
                compute_stats(test_cases),
            )
            logger.info(f"Saved synthetic test set to {default_path}")

    # Load components
    profile = load_creator_profile(args.creator)
    pipeline = load_pipeline() if args.mode != "validation" else None
    llm_provider = load_llm_provider() if not args.no_llm else None

    # Run selected mode
    mode_map = {
        "full": lambda: run_full(args, test_cases, profile, pipeline, llm_provider),
        "quick": lambda: run_quick(args, test_cases, profile, pipeline, llm_provider),
        "stress": lambda: run_stress_mode(args, profile, pipeline),
        "ab": lambda: run_ab_mode(args, test_cases, profile, pipeline, llm_provider),
        "eval": lambda: run_eval_mode(args, test_cases, profile, pipeline, llm_provider),
        "validation": lambda: run_validation_mode(args, test_cases, profile, pipeline),
    }

    results = asyncio.run(mode_map[args.mode]())

    # Save results if requested
    if args.save_results:
        output_dir = Path(args.output) if args.output else Path(__file__).parent
        output_path = output_dir / f"results_{args.creator}_{args.mode}.json"

        # Make results JSON-serializable
        def _serialize(obj):
            if isinstance(obj, Path):
                return str(obj)
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, set):
                return list(obj)
            return str(obj)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=_serialize)
        print(f"Results saved to: {output_path}")

    # Update baseline if requested
    if args.update_baseline and "regression" in results:
        reg = results["regression"]
        save_baseline(args.creator, {
            "version": "v1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "creator": args.creator,
            "overall_score": reg.get("current_score", 0),
            "dimension_scores": reg.get("current_dimensions", {}),
            "sample_size": reg.get("test_count", 0),
        })

    # Exit code
    if args.mode == "quick" and results.get("regression", {}).get("status") == "FAIL":
        sys.exit(1)
    elif args.mode == "stress" and not results.get("stress", {}).get("pass", True):
        sys.exit(1)


if __name__ == "__main__":
    main()
