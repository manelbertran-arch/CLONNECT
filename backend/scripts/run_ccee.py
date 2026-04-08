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
                    m_user.created_at,
                    l.id AS lead_uuid
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
        for user_input, ground_truth, trust, username, created_at, lead_uuid in rows:
            ctx = classify_context(user_input)
            if ctx not in by_type:
                by_type[ctx] = []
            by_type[ctx].append({
                "user_input": user_input,
                "ground_truth": ground_truth,
                "trust_score": float(trust),
                "username": username,
                # lead_uuid: real DB UUID for this lead. Passed as sender_id so
                # MemoryEngine can resolve memories without UUID CAST errors.
                # l.username may be a phone number (WhatsApp) which fails CAST.
                "lead_uuid": str(lead_uuid) if lead_uuid else None,
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
    inter_case_delay = float(os.environ.get("CCEE_INTER_CASE_DELAY", "0"))

    for i, tc in enumerate(test_cases):
        old_env = {}
        try:
            if overrides:
                for k, v in overrides.items():
                    old_env[k] = os.environ.get(k)
                    os.environ[k] = v

            # Prefer real lead UUID so MemoryEngine can resolve DB lookups.
            # l.username may be a phone number (WhatsApp leads) which fails
            # CAST to UUID in _resolve_lead_uuid → empty memories → J1=0.
            sender_id = tc.get("lead_uuid") or tc.get("username") or "test_user"
            dm_response = asyncio.run(agent.process_dm(
                message=tc["user_input"],
                sender_id=sender_id,
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

        if inter_case_delay > 0 and i < len(test_cases) - 1:
            import time as _time
            _time.sleep(inter_case_delay)

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
    if isinstance(s3.get("detail"), dict):
        d = s3["detail"]
        lines.append(f"  {'E1 per-case':<23} {d.get('e1_per_case_mean', 0):>8.2f}")
        lines.append(f"  {'E2 distribution':<23} {d.get('e2_distribution_match', 0):>8.2f}")

    s4 = results["S4_adaptation"]
    lines.append(f"{'S4 Adaptation':<25} {s4['score']:>8.2f}")

    # B: Persona Fidelity
    b = results.get("B_persona_fidelity", {})
    if b:
        lines.append(f"{'B  Persona Fidelity':<25} {b.get('score', 50):>8.2f}")
        if isinstance(b.get("B1"), dict):
            lines.append(f"  {'B1 OCEAN alignment':<23} {b['B1'].get('score', 50):>8.2f}")
        if isinstance(b.get("B4"), dict):
            lines.append(f"  {'B4 knowledge bounds':<23} {b['B4'].get('score', 50):>8.2f}")

    # G: Safety
    g = results.get("G_safety", {})
    if g:
        lines.append(f"{'G  Safety':<25} {g.get('score', 50):>8.2f}")
        lines.append(f"  {'G1 hallucination':<23} {g.get('G1_score', 50):>8.2f}")
        if isinstance(g.get("G3"), dict) and g["G3"].get("detail") != "no jailbreak tests run":
            lines.append(f"  {'G3 jailbreak resist.':<23} {g['G3'].get('score', 50):>8.2f}")

    # H: Indistinguishability
    h = results.get("H_indistinguishability", {})
    if h:
        lines.append(f"{'H  Indistinguishability':<25} {h.get('score', 50):>8.2f}")
        if isinstance(h.get("H2"), dict):
            lines.append(f"  {'H2 style fingerprint':<23} {h['H2'].get('score', 50):>8.2f}")

    # I: Business Impact
    i_biz = results.get("I_business_impact", {})
    if i_biz:
        lines.append(f"{'I  Business Impact':<25} {i_biz.get('score', 50):>8.2f}")
        for key in ["I1_lead_response_rate", "I2_conversation_continuation",
                     "I3_escalation_rate", "I4_funnel_progression"]:
            if key in i_biz:
                label = key.replace("_", " ").replace("I1 ", "  I1 ").replace("I2 ", "  I2 ").replace("I3 ", "  I3 ").replace("I4 ", "  I4 ")
                lines.append(f"  {key[3:]:<23} {i_biz[key].get('score', 50):>8.2f}")

    # J: Cognitive Fidelity
    j1 = results.get("J1_memory_recall", {})
    if j1:
        lines.append(f"{'J1 Memory Recall':<25} {j1.get('score', 50):>8.2f}")
    j2 = results.get("J2_multiturn_consistency", {})
    if j2:
        lines.append(f"{'J2 Multi-turn Consist.':<25} {j2.get('score', 50):>8.2f}")
    j_cog = results.get("J_cognitive_fidelity")
    if j_cog is not None:
        lines.append(f"{'J  Cognitive Fidelity':<25} {j_cog:>8.2f}")

    # LLM Judge
    llm = results.get("LLM_judge", {})
    if llm:
        lines.append(f"{'--- LLM Judge ---':<25}")
        for key in ["B2_persona_consistency", "B5_emotional_signature",
                     "C2_naturalness", "C3_contextual_appropriateness"]:
            if key in llm:
                lines.append(f"  {key[3:]:<23} {llm[key].get('score', 50):>8.2f}")
        lines.append(f"  {'cost USD':<23} {llm.get('estimated_cost_usd', 0):>8.4f}")

    # Human eval
    human = results.get("human_eval", {})
    if human:
        lines.append(f"{'--- Human Eval ---':<25}")
        for key in ["B3_persona_identification", "H1_turing_test", "H3_would_send"]:
            if key in human:
                lines.append(f"  {key[3:]:<23} {human[key].get('score', 50):>8.2f}")

    lines.append("-" * 75)
    pa = results.get("params_active", "?")
    pt = results.get("params_total", 44)
    lines.append(f"{'COMPOSITE':<25} {results['composite']:>8.2f}  ({pa}/{pt} params)")

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


def _run_prometheus_on_responses(
    test_cases: List[Dict],
    bot_responses: List[str],
) -> Dict:
    """Run M-Prometheus/LLM judge on one set of bot responses and return raw scores."""
    from core.evaluation.m_prometheus_judge import evaluate_all_params

    prom_cases = [
        {
            "bot_response": bot_responses[i],
            "ground_truth": tc["ground_truth"],
            "user_input": tc["user_input"],
        }
        for i, tc in enumerate(test_cases)
    ]
    raw = evaluate_all_params(prom_cases, max_cases=len(prom_cases))

    def _per_case_list(key, per_case_data):
        return [c.get(key, 50.0) for c in per_case_data]

    return {
        "B2_persona_consistency": {
            "score": raw["B2_persona_consistency"],
            "per_case": _per_case_list("B2", raw.get("per_case", [])),
        },
        "B5_emotional_signature": {
            "score": raw["B5_emotional_signature"],
            "per_case": _per_case_list("B5", raw.get("per_case", [])),
        },
        "C2_naturalness": {
            "score": raw["C2_naturalness"],
            "per_case": _per_case_list("C2", raw.get("per_case", [])),
        },
        "C3_contextual_appropriateness": {
            "score": raw["C3_contextual_appropriateness"],
            "per_case": _per_case_list("C3", raw.get("per_case", [])),
        },
        "H1_turing_test_rate": raw.get("H1_turing_test_rate", 0.0),
        "model": raw.get("model", "m-prometheus-14b"),
        "n_cases": raw.get("n_cases", 0),
        "total_time_seconds": raw.get("total_time_seconds", 0.0),
    }


def _score_all_runs(
    data: Dict,
    per_run_records: List[List[Dict]],
    args,
    creator: str,
    profile_dir: str,
    style_profile: Dict,
    strategy_map: Dict,
    adaptation_profile: Dict,
    weights: Optional[Dict],
) -> None:
    """Judge each run independently and report per-run composites + mean ± std."""
    import json as _json

    n_runs = len(per_run_records)
    print(f"  [score-all-runs] {n_runs} runs × {len(per_run_records[0])} cases")

    scorer = CCEEScorer(style_profile, strategy_map, adaptation_profile, weights)

    # Build test_cases from run 0 records (same across all runs)
    test_cases = [
        {
            "user_input": r.get("user_message", ""),
            "ground_truth": r.get("iris_real_response", ""),
            "trust_score": r.get("trust_score", 0.5),
            "input_type": r.get("input_type", "OTHER"),
            "trust_segment": r.get("trust_segment", "UNKNOWN"),
            "username": r.get("username", ""),
            "lead_uuid": r.get("lead_uuid"),
        }
        for r in per_run_records[0]
    ]

    business_scores = None
    try:
        from core.evaluation.business_metrics import score_business_metrics
        business_scores = score_business_metrics(creator)
        print(f"  Business metrics: I-score={business_scores.get('score', '?')}")
    except Exception as e:
        print(f"  Business metrics unavailable: {e}")

    all_results = []
    all_composites = []
    all_run_prometheus = []

    for run_i, run_records in enumerate(per_run_records):
        run_bots = [r.get("bot_response", "") for r in run_records]
        print(f"\n  --- Run {run_i + 1}/{n_runs} ---")

        prom = _run_prometheus_on_responses(test_cases, run_bots)
        all_run_prometheus.append(prom)
        print(
            f"  Prometheus: B2={prom['B2_persona_consistency']['score']:.1f} "
            f"B5={prom['B5_emotional_signature']['score']:.1f} "
            f"C2={prom['C2_naturalness']['score']:.1f} "
            f"C3={prom['C3_contextual_appropriateness']['score']:.1f} "
            f"H1={prom['H1_turing_test_rate']:.1f}% "
            f"({prom.get('total_time_seconds', 0):.0f}s)"
        )

        result = scorer.score(
            test_cases, run_bots,
            llm_scores=prom,
            business_scores=business_scores,
        )
        all_results.append(result)
        all_composites.append(result["composite"])
        print(f"{_format_table(result)}")

    # Summary table
    print(f"\n{'='*60}")
    print(f" All-runs summary ({n_runs} runs, GPT-4o judge per run)")
    print(f"{'='*60}")
    print(f"  Composites: {[f'{c:.2f}' for c in all_composites]}")
    print(f"  Mean: {np.mean(all_composites):.2f}  Std: {np.std(all_composites):.2f}")
    for key in ["S1_style_fidelity", "S2_response_quality",
                "S3_strategic_alignment", "S4_adaptation",
                "B_persona_fidelity", "G_safety", "H_indistinguishability",
                "J1_memory_recall", "J2_multiturn_consistency"]:
        scores = [r[key]["score"] for r in all_results if key in r]
        if scores:
            print(f"  {key}: {np.mean(scores):.2f} ± {np.std(scores):.2f}")

    # Save
    out_dir = os.path.join(args.output_dir, creator)
    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = args.save_as if args.save_as else f"alljudged_{timestamp}"
    out_path = os.path.join(out_dir, f"{out_name}.json")

    output = {
        "creator_id": creator,
        "timestamp": timestamp,
        "n_runs": n_runs,
        "n_cases": len(test_cases),
        "overrides": data.get("overrides", {}),
        "runs": all_results,
        "composites": all_composites,
        "composite_mean": float(np.mean(all_composites)),
        "composite_std": float(np.std(all_composites)),
        "weights_used": weights or DEFAULT_WEIGHTS,
        "per_case_records": data.get("per_case_records", []),
        "per_run_records": per_run_records,
        "per_run_prometheus": all_run_prometheus,
        "source_genonly": args.score_prometheus,
        "score_all_runs": True,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        _json.dump(output, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Results saved to {out_path}")


def _run_score_prometheus(args) -> None:
    """--score-prometheus flow: read existing generate-only JSON, run Prometheus, save final."""
    import json as _json

    src_path = args.score_prometheus
    print(f"[score-prometheus] Loading responses from {src_path}...")
    with open(src_path, encoding="utf-8") as f:
        data = _json.load(f)

    creator = data.get("creator_id") or args.creator
    profile_dir = os.path.join(args.profile_dir, creator)

    with open(os.path.join(profile_dir, "style_profile.json")) as f:
        style_profile = _json.load(f)
    with open(os.path.join(profile_dir, "strategy_map.json")) as f:
        strategy_map = _json.load(f)
    with open(os.path.join(profile_dir, "adaptation_profile.json")) as f:
        adaptation_profile = _json.load(f)

    weights_path = os.path.join(profile_dir, "weights.json")
    weights = None
    if os.path.exists(weights_path):
        with open(weights_path) as f:
            weights = _json.load(f).get("calibrated_weights")

    # --score-all-runs: judge each run independently from per_run_records
    if getattr(args, "score_all_runs", False):
        per_run_records = data.get("per_run_records")
        if not per_run_records:
            print("  WARNING: per_run_records not found in JSON — falling back to single-run scoring")
        else:
            _score_all_runs(
                data, per_run_records, args,
                creator, profile_dir, style_profile, strategy_map,
                adaptation_profile, weights,
            )
            return

    records = data["per_case_records"]
    test_cases = [
        {
            "user_input": r.get("user_message", ""),
            "ground_truth": r.get("iris_real_response", ""),
            "trust_score": r.get("trust_score", 0.5),
            "input_type": r.get("input_type", "OTHER"),
            "trust_segment": r.get("trust_segment", "UNKNOWN"),
            "username": r.get("username", ""),
            # Persist lead_uuid so sender_id resolution and J1 grouping use the real DB UUID
            "lead_uuid": r.get("lead_uuid"),
        }
        for r in records
    ]
    bot_responses = [r.get("bot_response", "") for r in records]

    print(f"  {len(test_cases)} cases loaded | creator: {creator}")

    # Run Prometheus
    print("  Running M-Prometheus 14B judge (B2, B5, C2, C3, H1) via Ollama...")
    from core.evaluation.m_prometheus_judge import evaluate_all_params
    prom_cases = [
        {
            "bot_response": bot_responses[i],
            "ground_truth": tc["ground_truth"],
            "user_input": tc["user_input"],
        }
        for i, tc in enumerate(test_cases)
    ]
    raw = evaluate_all_params(prom_cases, max_cases=len(prom_cases))

    def _per_case_list(key, per_case_data):
        return [c.get(key, 50.0) for c in per_case_data]

    prometheus_scores = {
        "B2_persona_consistency": {
            "score": raw["B2_persona_consistency"],
            "per_case": _per_case_list("B2", raw.get("per_case", [])),
        },
        "B5_emotional_signature": {
            "score": raw["B5_emotional_signature"],
            "per_case": _per_case_list("B5", raw.get("per_case", [])),
        },
        "C2_naturalness": {
            "score": raw["C2_naturalness"],
            "per_case": _per_case_list("C2", raw.get("per_case", [])),
        },
        "C3_contextual_appropriateness": {
            "score": raw["C3_contextual_appropriateness"],
            "per_case": _per_case_list("C3", raw.get("per_case", [])),
        },
        "H1_turing_test_rate": raw.get("H1_turing_test_rate", 0.0),
        "model": raw.get("model", "m-prometheus-14b"),
        "n_cases": raw.get("n_cases", 0),
        "total_time_seconds": raw.get("total_time_seconds", 0.0),
    }
    print(
        f"  Prometheus: B2={prometheus_scores['B2_persona_consistency']['score']:.1f} "
        f"B5={prometheus_scores['B5_emotional_signature']['score']:.1f} "
        f"C2={prometheus_scores['C2_naturalness']['score']:.1f} "
        f"C3={prometheus_scores['C3_contextual_appropriateness']['score']:.1f} "
        f"H1={prometheus_scores['H1_turing_test_rate']:.1f}% "
        f"({raw.get('total_time_seconds', 0):.0f}s)"
    )

    # Business metrics
    business_scores = None
    try:
        from core.evaluation.business_metrics import score_business_metrics
        business_scores = score_business_metrics(creator)
        print(f"  Business metrics: I-score={business_scores.get('score', '?')}")
    except Exception as e:
        print(f"  Business metrics unavailable: {e}")

    # Re-score
    scorer = CCEEScorer(style_profile, strategy_map, adaptation_profile, weights)
    result = scorer.score(
        test_cases, bot_responses,
        llm_scores=prometheus_scores,
        business_scores=business_scores,
    )
    print(f"\n{_format_table(result)}")

    # Save
    out_dir = os.path.join(args.output_dir, creator)
    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_name = args.save_as if args.save_as else f"prometheus_{timestamp}"
    out_path = os.path.join(out_dir, f"{out_name}.json")

    human_cases = _select_human_eval_cases(test_cases, bot_responses, result)
    for i, hc in enumerate(human_cases, 1):
        print(f"\n  Case {i} [{hc['trust_segment']}] ({hc.get('input_type', '?')}):")
        print(f"    User: {hc['user_message'][:80]}")
        print(f"    Real: {hc['iris_real_response'][:80]}")
        print(f"    Bot:  {hc['bot_response'][:80]}")

    output = {
        "creator_id": creator,
        "timestamp": timestamp,
        "n_runs": 1,
        "n_cases": len(test_cases),
        "overrides": data.get("overrides", {}),
        "runs": [result],
        "composites": [result["composite"]],
        "human_eval_cases": human_cases,
        "weights_used": weights or DEFAULT_WEIGHTS,
        "per_case_records": records,
        "source_genonly": src_path,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        _json.dump(output, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Results saved to {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Run CCEE evaluation")
    parser.add_argument("--creator", required=False, default=None, help="Creator slug (required unless --score-prometheus)")
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
    parser.add_argument(
        "--with-llm-judge", action="store_true",
        help="Run LLM judge metrics (B2, B5, C2, C3) — costs ~$0.01 per run"
    )
    parser.add_argument(
        "--with-prometheus-judge", action="store_true",
        help="Run M-Prometheus 14B judge (B2, B5, C2, C3, H1) via Ollama local — free"
    )
    parser.add_argument(
        "--with-business-metrics", action="store_true",
        help="Include business metrics from DB (I1-I4)"
    )
    parser.add_argument(
        "--generate-only", action="store_true",
        help="Generate bot responses + deterministic scores only. Skip Prometheus/LLM judge."
    )
    parser.add_argument(
        "--score-prometheus", default=None, metavar="JSON_FILE",
        help="Re-score an existing generate-only JSON with M-Prometheus 14B via Ollama."
    )
    parser.add_argument(
        "--score-all-runs", action="store_true",
        help="With --score-prometheus: judge each run separately from per_run_records and report mean ± std."
    )
    parser.add_argument(
        "--with-human-ratings", default=None,
        help="Path to human ratings JSON for B3, H1, H3"
    )
    parser.add_argument(
        "--with-jailbreak-test", action="store_true",
        help="Run jailbreak resistance test (G3)"
    )
    args = parser.parse_args()

    # --score-prometheus: separate flow — reads existing JSON, runs Prometheus, saves final
    if args.score_prometheus:
        _run_score_prometheus(args)
        return

    if not args.creator:
        print("ERROR: --creator is required")
        sys.exit(1)
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

    # Load optional data sources
    business_scores = None
    if args.with_business_metrics:
        print("\n[BIZ] Computing business metrics...")
        try:
            from core.evaluation.business_metrics import score_business_metrics
            business_scores = score_business_metrics(creator)
            print(f"  I-score: {business_scores.get('score', '?')}")
        except Exception as e:
            print(f"  WARNING: Business metrics failed: {e}")

    human_scores = None
    if args.with_human_ratings:
        print(f"\n[HUMAN] Loading human ratings from {args.with_human_ratings}...")
        try:
            with open(args.with_human_ratings) as f:
                human_data = json.load(f)
            human_scores = human_data.get("scores", {})
            print(f"  Loaded: {list(human_scores.keys())}")
        except Exception as e:
            print(f"  WARNING: Human ratings failed: {e}")

    jailbreak_prompts_data = None
    if args.with_jailbreak_test:
        jp_path = os.path.join("evaluation_profiles", "jailbreak_prompts.json")
        if os.path.exists(jp_path):
            with open(jp_path) as f:
                jailbreak_prompts_data = json.load(f).get("prompts", [])
            print(f"\n[G3] Loaded {len(jailbreak_prompts_data)} jailbreak prompts")
        else:
            print(f"\n[G3] WARNING: {jp_path} not found")

    # Run evaluation
    scorer = CCEEScorer(style_profile, strategy_map, adaptation_profile, weights)
    all_run_results = []
    all_composites = []
    all_bot_responses_per_run: List[List[str]] = []  # one list per run, for per_run_records

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
        all_bot_responses_per_run.append(list(bot_responses))

        # Optional: run jailbreak test
        jailbreak_responses = None
        if jailbreak_prompts_data and not args.skip_pipeline:
            print("  Running jailbreak resistance test...")
            jb_cases = [{"user_input": p["prompt"]} for p in jailbreak_prompts_data]
            jailbreak_responses = run_bot_pipeline(creator, jb_cases, overrides or None)

        # --generate-only: score deterministically, accumulate across runs (save after loop)
        if args.generate_only:
            results = scorer.score(
                test_cases, bot_responses,
                llm_scores=None, human_scores=None,
                business_scores=None, jailbreak_responses=None,
            )
            print(f"\n{_format_table(results)}")
            all_run_results.append(results)
            all_composites.append(results["composite"])
            continue

        # Optional: run Prometheus judge (local Ollama, free)
        prometheus_scores = None
        if args.with_prometheus_judge:
            print("  Running M-Prometheus 14B judge (B2, B5, C2, C3, H1) via Ollama...")
            try:
                from core.evaluation.m_prometheus_judge import evaluate_all_params
                prom_cases = [
                    {
                        "bot_response": bot_responses[i],
                        "ground_truth": tc.get("ground_truth", ""),
                        "user_input": tc.get("user_input", ""),
                    }
                    for i, tc in enumerate(test_cases)
                    if i < len(bot_responses)
                ]
                raw = evaluate_all_params(prom_cases, max_cases=len(prom_cases))
                # Transform to llm_scores-compatible format for CCEEScorer
                def _per_case_list(key, per_case_data):
                    return [c.get(key, 50.0) for c in per_case_data]

                prometheus_scores = {
                    "B2_persona_consistency": {
                        "score": raw["B2_persona_consistency"],
                        "per_case": _per_case_list("B2", raw.get("per_case", [])),
                    },
                    "B5_emotional_signature": {
                        "score": raw["B5_emotional_signature"],
                        "per_case": _per_case_list("B5", raw.get("per_case", [])),
                    },
                    "C2_naturalness": {
                        "score": raw["C2_naturalness"],
                        "per_case": _per_case_list("C2", raw.get("per_case", [])),
                    },
                    "C3_contextual_appropriateness": {
                        "score": raw["C3_contextual_appropriateness"],
                        "per_case": _per_case_list("C3", raw.get("per_case", [])),
                    },
                    "H1_turing_test_rate": raw.get("H1_turing_test_rate", 0.0),
                    "model": raw.get("model", "m-prometheus-14b"),
                    "n_cases": raw.get("n_cases", 0),
                    "total_time_seconds": raw.get("total_time_seconds", 0.0),
                }
                print(
                    f"  Prometheus: B2={prometheus_scores['B2_persona_consistency']['score']:.1f} "
                    f"B5={prometheus_scores['B5_emotional_signature']['score']:.1f} "
                    f"C2={prometheus_scores['C2_naturalness']['score']:.1f} "
                    f"C3={prometheus_scores['C3_contextual_appropriateness']['score']:.1f} "
                    f"H1={prometheus_scores['H1_turing_test_rate']:.1f}% "
                    f"({raw.get('total_time_seconds', 0):.0f}s)"
                )
            except Exception as e:
                print(f"  ERROR: Prometheus judge failed: {e}")
                raise

        # Optional: run LLM judge
        llm_scores = None
        if args.with_llm_judge:
            import asyncio as _asyncio
            print("  Running LLM judge (B2, B5, C2, C3)...")
            try:
                from core.evaluation.llm_judge import score_llm_judge_batch
                # Build creator description from profile
                creator_desc = (
                    f"Content creator. Language: {list(style_profile.get('A6_language_ratio', {}).get('ratios', {}).keys())}. "
                    f"Style: emoji rate {style_profile.get('A2_emoji', {}).get('global_rate', '?')}, "
                    f"formality {style_profile.get('A8_formality', {}).get('formality_score', '?')}. "
                    f"Catchphrases: {[cp['phrase'] for cp in style_profile.get('A9_catchphrases', {}).get('catchphrases', [])[:5]]}"
                )
                llm_scores = _asyncio.run(
                    score_llm_judge_batch(test_cases, bot_responses, creator_desc)
                )
                print(f"  LLM judge cost: ${llm_scores.get('estimated_cost_usd', 0):.4f}")
            except Exception as e:
                print(f"  WARNING: LLM judge failed: {e}")

        # Merge prometheus into llm_scores slot if no API judge ran
        if prometheus_scores is not None and llm_scores is None:
            llm_scores = prometheus_scores

        results = scorer.score(
            test_cases, bot_responses,
            llm_scores=llm_scores,
            human_scores=human_scores,
            business_scores=business_scores,
            jailbreak_responses=jailbreak_responses,
        )
        all_run_results.append(results)
        all_composites.append(results["composite"])

        print(f"\n{_format_table(results)}")

    # --generate-only: save all accumulated runs after loop completes
    if args.generate_only:
        out_dir = os.path.join(args.output_dir, creator)
        os.makedirs(out_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_name = args.save_as if args.save_as else f"genonly_{timestamp}"
        out_path = os.path.join(out_dir, f"{out_name}.json")
        # Build per_run_records — one list per run, compatible with --score-all-runs
        per_run_records: List[List[Dict]] = []
        for run_i, run_bots in enumerate(all_bot_responses_per_run):
            run_result = all_run_results[run_i]
            run_s2 = run_result.get("S2_response_quality", {}).get("detail", {}).get("per_case", [])
            run_s3 = run_result.get("S3_strategic_alignment", {}).get("detail", {}).get("per_case", [])
            run_records: List[Dict] = []
            for i, tc in enumerate(test_cases):
                resp = run_bots[i] if i < len(run_bots) else ""
                trust = tc.get("trust_score", 0.0)
                run_records.append({
                    "idx": i,
                    "run": run_i,
                    "input_type": tc.get("input_type", "OTHER"),
                    "trust_score": trust,
                    "trust_segment": tc.get("trust_segment", "UNKNOWN"),
                    "username": tc.get("username", ""),
                    "lead_uuid": tc.get("lead_uuid"),
                    "user_message": tc.get("user_input", ""),
                    "iris_real_response": tc.get("ground_truth", ""),
                    "bot_response": resp,
                    "s1_score": score_s1_per_case(resp, style_profile, tc.get("user_input")),
                    "s2_score": run_s2[i] if i < len(run_s2) else None,
                    "s3_score": run_s3[i] if i < len(run_s3) else None,
                    "s4_score": score_s4_per_case(resp, trust, adaptation_profile),
                })
            per_run_records.append(run_records)
        # per_case_records: last run's records (single-run --score-prometheus compat)
        per_case_records = per_run_records[-1] if per_run_records else []
        genonly_output = {
            "creator_id": creator,
            "timestamp": timestamp,
            "n_runs": args.runs,
            "n_cases": len(test_cases),
            "overrides": overrides,
            "runs": all_run_results,
            "composites": all_composites,
            "human_eval_cases": [],
            "weights_used": weights or DEFAULT_WEIGHTS,
            "per_case_records": per_case_records,
            "per_run_records": per_run_records,
            "generate_only": True,
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(genonly_output, f, indent=2, ensure_ascii=False, default=str)
        print(f"\n  Responses saved to {out_path}")
        print(f"  Run --score-prometheus {out_path} --score-all-runs --save-as <name> to score all {args.runs} runs.")
        return

    # Aggregate across runs
    if args.runs > 1:
        print(f"\n{'='*60}")
        print(f" Aggregated ({args.runs} runs)")
        print(f"{'='*60}")
        agg_composites = [r["composite"] for r in all_run_results]
        print(f"  Mean composite: {np.mean(agg_composites):.2f}")
        print(f"  Std:  {np.std(agg_composites):.2f}")
        for key in ["S1_style_fidelity", "S2_response_quality",
                     "S3_strategic_alignment", "S4_adaptation",
                     "B_persona_fidelity", "G_safety", "H_indistinguishability",
                     "J1_memory_recall", "J2_multiturn_consistency"]:
            scores = [r[key]["score"] for r in all_run_results if key in r]
            if scores:
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
            "username": tc.get("username", ""),
            # lead_uuid: real DB UUID (l.id). Persisted so --score-prometheus
            # can resolve sender_id without falling back to username.
            "lead_uuid": tc.get("lead_uuid"),
            "user_message": tc.get("user_input", ""),
            "iris_real_response": tc.get("ground_truth", ""),
            "bot_response": resp,
            "s1_score": score_s1_per_case(resp, style_profile, tc.get("user_input")),
            "s2_score": last_s2_per_case[i] if i < len(last_s2_per_case) else None,
            "s3_score": last_s3_per_case[i] if i < len(last_s3_per_case) else None,
            "s4_score": score_s4_per_case(resp, trust, adaptation_profile),
        })

    # Build per_run_records: one list per run, each case has its own bot_response for that run.
    # Used by --score-all-runs so the judge can evaluate each run independently.
    per_run_records: List[List[Dict]] = []
    for run_i, run_bots in enumerate(all_bot_responses_per_run):
        run_result = all_run_results[run_i]
        run_s2 = run_result.get("S2_response_quality", {}).get("detail", {}).get("per_case", [])
        run_s3 = run_result.get("S3_strategic_alignment", {}).get("detail", {}).get("per_case", [])
        run_records: List[Dict] = []
        for i, tc in enumerate(test_cases):
            resp = run_bots[i] if i < len(run_bots) else ""
            trust = tc.get("trust_score", 0.0)
            run_records.append({
                "idx": i,
                "run": run_i,
                "input_type": tc.get("input_type", "OTHER"),
                "trust_score": trust,
                "trust_segment": tc.get("trust_segment", "UNKNOWN"),
                "username": tc.get("username", ""),
                "lead_uuid": tc.get("lead_uuid"),
                "user_message": tc.get("user_input", ""),
                "iris_real_response": tc.get("ground_truth", ""),
                "bot_response": resp,
                "s1_score": score_s1_per_case(resp, style_profile, tc.get("user_input")),
                "s2_score": run_s2[i] if i < len(run_s2) else None,
                "s3_score": run_s3[i] if i < len(run_s3) else None,
                "s4_score": score_s4_per_case(resp, trust, adaptation_profile),
            })
        per_run_records.append(run_records)

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
        "per_run_records": per_run_records,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n  Results saved to {out_path}")


if __name__ == "__main__":
    main()
