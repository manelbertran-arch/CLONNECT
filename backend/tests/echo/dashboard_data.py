"""
ECHO Dashboard Data Generator.

Produces JSON data for the CloneScore dashboard:
- CloneScore over time
- CloneScore by dimension
- CloneScore by lead category
- Top 5 worst responses (for improvement)
- Top 5 best responses (for few-shot examples)

Usage:
    python -m tests.echo.dashboard_data --creator stefano
    python -m tests.echo.dashboard_data --creator stefano --days 30 --output /tmp/dashboard.json
"""
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


def generate_dashboard_data(
    evaluation_results: dict,
    historical_scores: list[dict] | None = None,
    creator_name: str = "Unknown",
) -> dict:
    """
    Generate complete dashboard data from evaluation results.

    Args:
        evaluation_results: Output from EchoEvaluator.evaluate_batch()
        historical_scores: List of previous evaluation summaries for trend
        creator_name: Name of the creator

    Returns:
        Dashboard-ready JSON structure
    """
    results = evaluation_results.get("results", [])
    overall_score = evaluation_results.get("overall_score", 0)
    dim_averages = evaluation_results.get("dimension_averages", {})

    now = datetime.now(timezone.utc)

    # ---------------------------------------------------------------
    # 1. Score over time (historical trend)
    # ---------------------------------------------------------------
    score_timeline = []
    if historical_scores:
        for h in historical_scores:
            score_timeline.append({
                "date": h.get("date", ""),
                "overall_score": h.get("overall_score", 0),
                "dimensions": h.get("dimension_averages", {}),
            })

    # Add current
    score_timeline.append({
        "date": now.isoformat(),
        "overall_score": overall_score,
        "dimensions": dim_averages,
    })

    # ---------------------------------------------------------------
    # 2. Score by dimension (radar chart data)
    # ---------------------------------------------------------------
    dimension_chart = []
    dimension_labels = {
        "style_fidelity": "Estilo",
        "knowledge_accuracy": "Conocimiento",
        "persona_consistency": "Personalidad",
        "tone_appropriateness": "Tono",
        "sales_effectiveness": "Ventas",
        "safety_score": "Seguridad",
    }
    for dim, label in dimension_labels.items():
        dimension_chart.append({
            "dimension": dim,
            "label": label,
            "score": dim_averages.get(dim, 0),
            "weight": {
                "style_fidelity": 0.20,
                "knowledge_accuracy": 0.20,
                "persona_consistency": 0.20,
                "tone_appropriateness": 0.15,
                "sales_effectiveness": 0.15,
                "safety_score": 0.10,
            }.get(dim, 0),
        })

    # ---------------------------------------------------------------
    # 3. Score by lead category
    # ---------------------------------------------------------------
    by_category: dict[str, list[float]] = defaultdict(list)
    for r in results:
        # Find the original test case's category
        tc_id = r.get("test_case_id", "")
        category = "unknown"
        # Try to extract from results metadata
        for dim_name, details in r.get("dimension_details", {}).items():
            if isinstance(details, dict) and "lead_category" in details:
                category = details["lead_category"]
                break
        by_category[category].append(r.get("overall_score", 0))

    # If categories weren't found in details, try to infer from test_case_id patterns
    # This is a fallback; proper implementation should pass categories through
    category_scores = {}
    for cat, scores in by_category.items():
        if scores:
            import statistics
            category_scores[cat] = {
                "count": len(scores),
                "mean": round(statistics.mean(scores), 1),
                "min": round(min(scores), 1),
                "max": round(max(scores), 1),
            }

    # ---------------------------------------------------------------
    # 4. Top 5 worst responses
    # ---------------------------------------------------------------
    sorted_by_score = sorted(results, key=lambda r: r.get("overall_score", 0))
    worst_5 = []
    for r in sorted_by_score[:5]:
        worst_5.append({
            "test_case_id": r.get("test_case_id"),
            "overall_score": r.get("overall_score"),
            "bot_response": r.get("bot_response", "")[:200],
            "real_response": r.get("real_response", "")[:200],
            "weakest_dimension": _find_weakest_dimension(r.get("dimension_scores", {})),
            "dimension_scores": r.get("dimension_scores", {}),
        })

    # ---------------------------------------------------------------
    # 5. Top 5 best responses (candidates for few-shot examples)
    # ---------------------------------------------------------------
    best_5 = []
    for r in sorted_by_score[-5:]:
        best_5.append({
            "test_case_id": r.get("test_case_id"),
            "overall_score": r.get("overall_score"),
            "bot_response": r.get("bot_response", "")[:200],
            "real_response": r.get("real_response", "")[:200],
            "strongest_dimension": _find_strongest_dimension(r.get("dimension_scores", {})),
            "dimension_scores": r.get("dimension_scores", {}),
        })

    # ---------------------------------------------------------------
    # 6. Issue analysis
    # ---------------------------------------------------------------
    issues = _analyze_issues(results, dim_averages)

    # ---------------------------------------------------------------
    # 7. Cost summary
    # ---------------------------------------------------------------
    stats = evaluation_results.get("stats", {})
    cost_summary = {
        "total_cost_usd": stats.get("total_cost_usd", 0),
        "total_llm_calls": stats.get("total_llm_calls", 0),
        "total_tokens": stats.get("total_tokens", 0),
        "cost_per_eval": round(
            stats.get("total_cost_usd", 0) / max(stats.get("evaluated", 1), 1), 4
        ),
    }

    # ---------------------------------------------------------------
    # Assemble dashboard
    # ---------------------------------------------------------------
    return {
        "generated_at": now.isoformat(),
        "creator": creator_name,
        "summary": {
            "overall_score": overall_score,
            "label": _score_label(overall_score),
            "total_evaluated": stats.get("evaluated", len(results)),
            "total_errors": stats.get("errors", 0),
        },
        "score_timeline": score_timeline,
        "dimension_chart": dimension_chart,
        "dimension_averages": dim_averages,
        "by_category": category_scores,
        "worst_5": worst_5,
        "best_5": best_5,
        "issues": issues,
        "cost": cost_summary,
        "latency": evaluation_results.get("latency", {}),
    }


def generate_dashboard_from_test_cases(
    test_cases: list[dict],
    evaluation_results: dict,
    creator_name: str = "Unknown",
) -> dict:
    """
    Enhanced version that accepts test_cases for proper category mapping.
    """
    results = evaluation_results.get("results", [])

    # Build category lookup from test cases
    tc_lookup = {tc.get("id"): tc for tc in test_cases}

    # Enrich results with category info
    by_category: dict[str, list[float]] = defaultdict(list)
    for r in results:
        tc = tc_lookup.get(r.get("test_case_id"), {})
        category = tc.get("lead_category", "unknown")
        by_category[category].append(r.get("overall_score", 0))

    # Build base dashboard
    dashboard = generate_dashboard_data(evaluation_results, creator_name=creator_name)

    # Override category scores with proper data
    import statistics
    dashboard["by_category"] = {
        cat: {
            "count": len(scores),
            "mean": round(statistics.mean(scores), 1),
            "min": round(min(scores), 1),
            "max": round(max(scores), 1),
        }
        for cat, scores in by_category.items()
        if scores
    }

    # Also add by-topic breakdown
    by_topic: dict[str, list[float]] = defaultdict(list)
    for r in results:
        tc = tc_lookup.get(r.get("test_case_id"), {})
        topic = tc.get("metadata", {}).get("topic", "unknown")
        by_topic[topic].append(r.get("overall_score", 0))

    dashboard["by_topic"] = {
        topic: {
            "count": len(scores),
            "mean": round(statistics.mean(scores), 1),
        }
        for topic, scores in by_topic.items()
        if scores
    }

    return dashboard


def _find_weakest_dimension(scores: dict) -> str:
    """Find the dimension with the lowest score."""
    if not scores:
        return "unknown"
    return min(scores, key=scores.get)


def _find_strongest_dimension(scores: dict) -> str:
    """Find the dimension with the highest score."""
    if not scores:
        return "unknown"
    return max(scores, key=scores.get)


def _score_label(score: float) -> str:
    """Return label for score."""
    if score >= 90:
        return "Excelente"
    if score >= 75:
        return "Bueno"
    if score >= 60:
        return "Aceptable"
    if score >= 40:
        return "Mejorable"
    return "Critico"


def _analyze_issues(results: list[dict], dim_averages: dict) -> list[dict]:
    """Analyze common issues across results."""
    issues = []

    # Check for low-scoring dimensions
    for dim, avg in dim_averages.items():
        if avg < 60:
            issues.append({
                "severity": "high",
                "dimension": dim,
                "message": f"{dim} average score is {avg:.1f} (below 60)",
                "recommendation": _get_recommendation(dim),
            })
        elif avg < 75:
            issues.append({
                "severity": "medium",
                "dimension": dim,
                "message": f"{dim} average score is {avg:.1f} (below target 75)",
                "recommendation": _get_recommendation(dim),
            })

    # Check for high variance
    from collections import defaultdict
    dim_scores_list: dict[str, list[float]] = defaultdict(list)
    for r in results:
        for dim, score in r.get("dimension_scores", {}).items():
            dim_scores_list[dim].append(score)

    for dim, scores in dim_scores_list.items():
        if len(scores) > 5:
            import statistics
            stdev = statistics.stdev(scores)
            if stdev > 20:
                issues.append({
                    "severity": "medium",
                    "dimension": dim,
                    "message": f"{dim} has high variance (stdev={stdev:.1f}) — inconsistent quality",
                    "recommendation": "Investigate which test case types cause low scores",
                })

    # Sort by severity
    severity_order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda x: severity_order.get(x.get("severity", "low"), 2))

    return issues[:10]  # Top 10 issues


def _get_recommendation(dimension: str) -> str:
    """Get improvement recommendation for a dimension."""
    recommendations = {
        "style_fidelity": "Review tone_profiles and adjust style_prompt. Add more informal markers and emoji patterns.",
        "knowledge_accuracy": "Update knowledge_base and products. Check for outdated prices or missing product info.",
        "persona_consistency": "Review Doc D and ensure personality traits are clearly defined. Add more few-shot examples.",
        "tone_appropriateness": "Adjust response strategy by lead stage. Ensure new leads get warm, not salesy, tone.",
        "sales_effectiveness": "Review copilot approval patterns. Improve CTA placement and closing techniques.",
        "safety_score": "Check for hallucinated prices/contacts. Strengthen guardrails and output validation.",
    }
    return recommendations.get(dimension, "Review and improve this dimension.")


def save_dashboard(data: dict, output_path: str | Path) -> Path:
    """Save dashboard data to JSON."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info(f"Dashboard data saved to {path}")
    return path


def print_dashboard_summary(data: dict) -> None:
    """Print a terminal-friendly dashboard summary."""
    summary = data.get("summary", {})
    dims = data.get("dimension_averages", {})

    print(f"\n{'='*60}")
    print(f"  CloneScore Dashboard — {data.get('creator', '?')}")
    print(f"{'='*60}")
    print(f"  Overall: {summary.get('overall_score', 0):.1f}/100 ({summary.get('label', '?')})")
    print(f"  Evaluated: {summary.get('total_evaluated', 0)} | Errors: {summary.get('total_errors', 0)}")

    print(f"\n  Dimensions:")
    for dim_data in data.get("dimension_chart", []):
        bar_len = int(dim_data["score"] / 5)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        print(f"    {dim_data['label']:15s} {bar} {dim_data['score']:.1f}")

    if data.get("by_category"):
        print(f"\n  By Lead Category:")
        for cat, cat_data in sorted(data["by_category"].items()):
            print(f"    {cat:15s}: {cat_data['mean']:.1f} (n={cat_data['count']})")

    if data.get("issues"):
        print(f"\n  Top Issues:")
        for i, issue in enumerate(data["issues"][:5], 1):
            sev_icon = {"high": "!!", "medium": "!", "low": "~"}.get(issue["severity"], "?")
            print(f"    {i}. [{sev_icon}] {issue['message']}")

    cost = data.get("cost", {})
    if cost:
        print(f"\n  Cost: ${cost.get('total_cost_usd', 0):.4f} ({cost.get('total_llm_calls', 0)} LLM calls)")

    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate ECHO dashboard data")
    parser.add_argument("--creator", default="stefano", help="Creator name")
    parser.add_argument("--input", default=None, help="Evaluation results JSON path")
    parser.add_argument("--output", default=None, help="Output JSON path")
    parser.add_argument("--days", type=int, default=30, help="Days of history to include")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.input and Path(args.input).exists():
        with open(args.input, "r") as f:
            evaluation_results = json.load(f)
    else:
        # Generate mock data for testing
        logger.info("No input provided, generating mock dashboard data")
        evaluation_results = {
            "overall_score": 76.3,
            "dimension_averages": {
                "style_fidelity": 80.2,
                "knowledge_accuracy": 73.5,
                "persona_consistency": 78.1,
                "tone_appropriateness": 76.8,
                "sales_effectiveness": 65.3,
                "safety_score": 89.4,
            },
            "results": [],
            "stats": {
                "evaluated": 100,
                "errors": 2,
                "total_cost_usd": 6.12,
                "total_llm_calls": 298,
                "total_tokens": 45000,
            },
            "latency": {"avg_ms": 1800, "p95_ms": 2400},
        }

    dashboard = generate_dashboard_data(
        evaluation_results,
        creator_name=args.creator.title(),
    )

    print_dashboard_summary(dashboard)

    output_path = args.output or str(
        Path(__file__).parent / f"dashboard_{args.creator}.json"
    )
    save_dashboard(dashboard, output_path)
    print(f"Dashboard data saved to: {output_path}")


if __name__ == "__main__":
    main()
