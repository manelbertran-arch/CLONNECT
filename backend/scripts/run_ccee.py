#!/usr/bin/env python3
"""
CCEE Script 7: Run CCEE Evaluation

CLI for running the full CCEE evaluation pipeline:
  1. Load evaluator profile
  2. Auto-generate or load test set
  3. Run bot pipeline N times
  4. Compute S1-S4 scores
  5. Compare to baseline (Wilcoxon + Cliff's delta)
  6. Output results + 5 human eval cases

Usage:
    railway run python3 scripts/run_ccee.py --creator iris_bertran --runs 3
    railway run python3 scripts/run_ccee.py --creator iris_bertran --runs 1 --compare baseline.json
    railway run python3 scripts/run_ccee.py --creator iris_bertran --override temperature=0.7
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import psycopg2
from dotenv import load_dotenv

load_dotenv()

from core.evaluation.ccee_scorer import (
    CCEEScorer,
    DEFAULT_WEIGHTS,
    score_s1_per_case,
    score_s4_per_case,
)
from core.evaluation.calibrator import CCEECalibrator
from core.evaluation.style_profile_builder import _get_conn, _resolve_creator_uuid


# ---------------------------------------------------------------------------
# Test set auto-generation
# ---------------------------------------------------------------------------

def auto_generate_test_set(
    creator_id: str, n_cases: int = 50
) -> List[Dict[str, Any]]:
    """Generate stratified test set from real conversations.

    Selects cases with ground truth, diverse input types, and trust levels.
    """
    from core.evaluation.style_profile_builder import classify_context

    conn = _get_conn()
    try:
        creator_uuid = _resolve_creator_uuid(conn, creator_id)
        if not creator_uuid:
            raise ValueError(f"Creator '{creator_id}' not found")

        cases = []
        with conn.cursor() as cur:
            # Fetch real user→assistant pairs with context
            cur.execute("""
                SELECT
                    m_user.content AS user_input,
                    m_bot.content AS ground_truth,
                    COALESCE(rd.trust_score, 0.0) AS trust_score,
                    l.username,
                    m_user.created_at
                FROM messages m_user
                JOIN messages m_bot ON m_bot.lead_id = m_user.lead_id
                    AND m_bot.role = 'assistant'
                    AND m_bot.created_at > m_user.created_at
                    AND m_bot.deleted_at IS NULL
                    AND COALESCE(m_bot.approved_by, 'human')
                        NOT IN ('auto', 'autopilot')
                JOIN leads l ON l.id = m_user.lead_id
                LEFT JOIN relationship_dna rd
                    ON rd.creator_id = %s
                    AND rd.follower_id = l.platform_user_id
                WHERE l.creator_id = CAST(%s AS uuid)
                    AND m_user.role = 'user'
                    AND m_user.content IS NOT NULL
                    AND LENGTH(m_user.content) > 2
                    AND m_user.deleted_at IS NULL
                ORDER BY RANDOM()
                LIMIT %s
            """, (creator_id, creator_uuid, n_cases * 3))

            rows = cur.fetchall()

        # Stratify by input type
        by_type: Dict[str, List] = {}
        for user_input, ground_truth, trust, username, created_at in rows:
            ctx = classify_context(user_input)
            if ctx not in by_type:
                by_type[ctx] = []
            by_type[ctx].append({
                "user_input": user_input,
                "ground_truth": ground_truth,
                "trust_score": float(trust),
                "username": username,
                "input_type": ctx,
                "created_at": str(created_at) if created_at else None,
            })

        # Sample proportionally from each type
        for ctx, type_cases in by_type.items():
            proportion = max(1, int(n_cases * len(type_cases) / len(rows)))
            cases.extend(type_cases[:proportion])

        # Fill remaining from pool
        all_remaining = [c for tc in by_type.values() for c in tc if c not in cases]
        while len(cases) < n_cases and all_remaining:
            cases.append(all_remaining.pop(0))

        return cases[:n_cases]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Bot pipeline runner
# ---------------------------------------------------------------------------

def run_bot_pipeline(
    creator_id: str,
    test_cases: List[Dict],
    overrides: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Run the production DM pipeline for each test case.

    Uses DMResponderAgentV2.process_dm() — the actual production pipeline.
    Overrides are passed as environment variables (e.g. temperature=0.7).
    """
    import asyncio

    try:
        from core.dm.agent import get_dm_agent
    except ImportError:
        raise RuntimeError(
            "Pipeline module not found (core.dm.agent). "
            "Use --skip-pipeline for scorer-only mode."
        )

    agent = get_dm_agent(creator_id)
    responses = []

    for tc in test_cases:
        old_env = {}
        try:
            if overrides:
                for k, v in overrides.items():
                    old_env[k] = os.environ.get(k)
                    os.environ[k] = v

            dm_response = asyncio.run(agent.process_dm(
                message=tc["user_input"],
                sender_id=tc.get("username", "test_user"),
                metadata={"platform": "instagram"},
            ))
            responses.append(
                dm_response.content
                if hasattr(dm_response, "content")
                else str(dm_response)
            )

        except Exception as e:
            responses.append(f"[ERROR: {e}]")
        finally:
            if overrides:
                for k, v in old_env.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

    return responses


# ---------------------------------------------------------------------------
# Results formatting
# ---------------------------------------------------------------------------

def _format_table(results: Dict) -> str:
    """Format results as a readable table."""
    lines = []
    lines.append(f"{'Metric':<25} {'Score':>8} {'Detail':>40}")
    lines.append("-" * 75)

    s1 = results["S1_style_fidelity"]
    lines.append(f"{'S1 Style Fidelity':<25} {s1['score']:>8.2f}")

    s2 = results["S2_response_quality"]
    lines.append(f"{'S2 Response Quality':<25} {s2['score']:>8.2f}")
    if isinstance(s2.get("detail"), dict):
        d = s2["detail"]
        lines.append(f"  {'BERTScore':<23} {d.get('bertscore_mean', 0):>8.4f}")
        lines.append(f"  {'chrF++':<23} {d.get('chrf_mean', 0):>8.4f}")
        lines.append(f"  {'G1 hallucinations':<23} {d.get('g1_hallucination_count', 0):>8d}")
        lines.append(f"  {'G2 bot reveals':<23} {d.get('g2_bot_reveal_count', 0):>8d}")

    s3 = results["S3_strategic_alignment"]
    lines.append(f"{'S3 Strategic Alignment':<25} {s3['score']:>8.2f}")

    s4 = results["S4_adaptation"]
    lines.append(f"{'S4 Adaptation':<25} {s4['score']:>8.2f}")

    lines.append("-" * 75)
    lines.append(f"{'COMPOSITE':<25} {results['composite']:>8.2f}")

    return "\n".join(lines)


def _select_human_eval_cases(
    test_cases: List[Dict],
    bot_responses: List[str],
    results: Dict,
    n: int = 5,
) -> List[Dict]:
    """Select N cases for human evaluation.

    Strategy: 1 per trust segment (UNKNOWN/KNOWN/CLOSE/INTIMATE) + 1 worst S3
    case (edge case). If fewer than 4 segments are present, fills remaining
    slots with additional cases not yet selected.
    """
    selected = []
    selected_idxs = set()
    seen_segments = set()

    # First pass: one per trust segment
    for i, tc in enumerate(test_cases):
        trust = tc.get("trust_score", 0.0)
        if trust < 0.3:
            seg = "UNKNOWN"
        elif trust < 0.7:
            seg = "KNOWN"
        elif trust < 0.9:
            seg = "CLOSE"
        else:
            seg = "INTIMATE"

        if seg not in seen_segments and len(selected) < n - 1:
            seen_segments.add(seg)
            selected_idxs.add(i)
            selected.append({
                "case_idx": i,
                "trust_segment": seg,
                "user_message": tc["user_input"],
                "iris_real_response": tc["ground_truth"],
                "bot_response": bot_responses[i],
                "input_type": tc.get("input_type", ""),
            })

    # Fill remaining segment slots with any unseen cases
    if len(selected) < n - 1:
        for i, tc in enumerate(test_cases):
            if i not in selected_idxs and len(selected) < n - 1:
                selected_idxs.add(i)
                selected.append({
                    "case_idx": i,
                    "trust_segment": "EXTRA",
                    "user_message": tc["user_input"],
                    "iris_real_response": tc["ground_truth"],
                    "bot_response": bot_responses[i],
                    "input_type": tc.get("input_type", ""),
                })

    # Last slot: worst scoring case (edge case)
    s3_detail = results.get("S3_strategic_alignment", {}).get("detail", {})
    per_case = s3_detail.get("per_case", [])
    if per_case:
        worst_idx = int(np.argmin(per_case))
        if worst_idx < len(test_cases):
            selected.append({
                "case_idx": worst_idx,
                "trust_segment": "EDGE_CASE",
                "user_message": test_cases[worst_idx]["user_input"],
                "iris_real_response": test_cases[worst_idx]["ground_truth"],
                "bot_response": bot_responses[worst_idx],
                "input_type": test_cases[worst_idx].get("input_type", ""),
                "s3_score": per_case[worst_idx],
            })

    return selected[:n]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run CCEE evaluation")
    parser.add_argument("--creator", required=True, help="Creator slug")
    parser.add_argument("--runs", type=int, default=1, help="Number of runs")
    parser.add_argument("--cases", type=int, default=50, help="Number of test cases")
    parser.add_argument("--test-set", help="Path to test set JSON (auto-generates if omitted)")
    parser.add_argument("--compare", help="Path to baseline results JSON for Wilcoxon comparison")
    parser.add_argument(
        "--override", action="append", default=[],
        help="Override config: KEY=VALUE (repeatable, e.g. --override temperature=0.7)"
    )
    parser.add_argument(
        "--profile-dir", default="evaluation_profiles",
        help="Directory with evaluator profiles"
    )
    parser.add_argument(
        "--output-dir", default="tests/ccee_results",
        help="Output directory for results"
    )
    parser.add_argument(
        "--skip-pipeline", action="store_true",
        help="Skip bot pipeline, use ground truth as bot response (for testing scorer)"
    )
    parser.add_argument(
        "--save-as", default=None,
        help="Custom name for results file (e.g. baseline_0, ablation_temp07)"
    )
    args = parser.parse_args()

    creator = args.creator
    profile_dir = os.path.join(args.profile_dir, creator)

    print(f"{'='*60}")
    print(f" CCEE Evaluation — {creator}")
    print(f" Runs: {args.runs} | Cases: {args.cases}")
    print(f"{'='*60}\n")

    # Load profiles
    print("[1] Loading evaluator profiles...")
    try:
        with open(os.path.join(profile_dir, "style_profile.json")) as f:
            style_profile = json.load(f)
        with open(os.path.join(profile_dir, "strategy_map.json")) as f:
            strategy_map = json.load(f)
        with open(os.path.join(profile_dir, "adaptation_profile.json")) as f:
            adaptation_profile = json.load(f)
    except FileNotFoundError as e:
        print(f"ERROR: Profile not found: {e}")
        print(f"Run 'scripts/build_evaluator.py --creator {creator}' first.")
        sys.exit(1)

    # Load calibrated weights if available
    weights_path = os.path.join(profile_dir, "weights.json")
    weights = None
    if os.path.exists(weights_path):
        with open(weights_path) as f:
            data = json.load(f)
        weights = data.get("calibrated_weights")
        print(f"  Using calibrated weights: {weights}")
    else:
        print(f"  Using default weights: {DEFAULT_WEIGHTS}")

    # Load or generate test set
    print("\n[2] Preparing test set...")
    if args.test_set:
        with open(args.test_set) as f:
            test_cases = json.load(f)
        print(f"  Loaded {len(test_cases)} cases from {args.test_set}")
    else:
        test_cases = auto_generate_test_set(creator, args.cases)
        print(f"  Auto-generated {len(test_cases)} stratified cases")

    # Parse overrides
    overrides = {}
    for ov in args.override:
        if "=" in ov:
            k, v = ov.split("=", 1)
            overrides[k.strip()] = v.strip()
    if overrides:
        print(f"  Overrides: {overrides}")

    # Run evaluation
    scorer = CCEEScorer(style_profile, strategy_map, adaptation_profile, weights)
    all_run_results = []
    all_composites = []

    for run_idx in range(args.runs):
        print(f"\n[3.{run_idx+1}] Run {run_idx+1}/{args.runs}...")

        if args.skip_pipeline:
            bot_responses = [tc["ground_truth"] for tc in test_cases]
            print("  (using ground truth as bot response — testing scorer only)")
        else:
            t0 = time.time()
            bot_responses = run_bot_pipeline(creator, test_cases, overrides or None)
            t1 = time.time()
            print(f"  Pipeline: {t1-t0:.1f}s for {len(test_cases)} cases")

        results = scorer.score(test_cases, bot_responses)
        all_run_results.append(results)
        all_composites.append(results["composite"])

        print(f"\n{_format_table(results)}")

    # Aggregate across runs
    if args.runs > 1:
        print(f"\n{'='*60}")
        print(f" Aggregated ({args.runs} runs)")
        print(f"{'='*60}")
        agg_composites = [r["composite"] for r in all_run_results]
        print(f"  Mean composite: {np.mean(agg_composites):.2f}")
        print(f"  Std:  {np.std(agg_composites):.2f}")
        for key in ["S1_style_fidelity", "S2_response_quality",
                     "S3_strategic_alignment", "S4_adaptation"]:
            scores = [r[key]["score"] for r in all_run_results]
            print(f"  {key}: {np.mean(scores):.2f} +/- {np.std(scores):.2f}")

    # Compare to baseline
    if args.compare:
        print(f"\n[4] Comparing to baseline: {args.compare}")
        with open(args.compare) as f:
            baseline_data = json.load(f)
        baseline_scores = baseline_data.get("composites", [])
        if baseline_scores:
            comparison = scorer.compare_to_baseline(all_composites, baseline_scores)
            print(f"  Verdict: {comparison['verdict']}")
            print(f"  p-value: {comparison['p_value']}")
            print(f"  Cliff's delta: {comparison['cliffs_delta']} ({comparison['effect_size']})")
            print(f"  Current: {comparison['current_mean']:.2f} vs Baseline: {comparison['baseline_mean']:.2f}")

    # Human eval cases
    print(f"\n[5] Cases for human evaluation:")
    human_cases = _select_human_eval_cases(
        test_cases, bot_responses, all_run_results[-1]
    )
    for i, hc in enumerate(human_cases, 1):
        print(f"\n  Case {i} [{hc['trust_segment']}] ({hc.get('input_type', '?')}):")
        print(f"    User: {hc['user_message'][:80]}")
        print(f"    Real: {hc['iris_real_response'][:80]}")
        print(f"    Bot:  {hc['bot_response'][:80]}")

    # Save results
    out_dir = os.path.join(args.output_dir, creator)
    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.save_as:
        out_path = os.path.join(out_dir, f"{args.save_as}.json")
    else:
        out_path = os.path.join(out_dir, f"ccee_run_{timestamp}.json")

    # Build per-case records using last run's scores
    last_run = all_run_results[-1]
    last_s2_per_case = (
        last_run.get("S2_response_quality", {})
        .get("detail", {})
        .get("per_case", [])
    )
    last_s3_per_case = (
        last_run.get("S3_strategic_alignment", {})
        .get("detail", {})
        .get("per_case", [])
    )
    per_case_records = []
    for i, tc in enumerate(test_cases):
        resp = bot_responses[i] if i < len(bot_responses) else ""
        trust = tc.get("trust_score", 0.0)
        per_case_records.append({
            "idx": i,
            "input_type": tc.get("input_type", "OTHER"),
            "trust_score": trust,
            "user_message": tc.get("user_input", ""),
            "iris_real_response": tc.get("ground_truth", ""),
            "bot_response": resp,
            "s1_score": score_s1_per_case(resp, style_profile, tc.get("user_input")),
            "s2_score": last_s2_per_case[i] if i < len(last_s2_per_case) else None,
            "s3_score": last_s3_per_case[i] if i < len(last_s3_per_case) else None,
            "s4_score": score_s4_per_case(resp, trust, adaptation_profile),
        })

    output = {
        "creator_id": creator,
        "timestamp": timestamp,
        "n_runs": args.runs,
        "n_cases": len(test_cases),
        "overrides": overrides,
        "runs": all_run_results,
        "composites": all_composites,
        "human_eval_cases": human_cases,
        "weights_used": weights or DEFAULT_WEIGHTS,
        "per_case_records": per_case_records,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n  Results saved to {out_path}")


if __name__ == "__main__":
    main()
