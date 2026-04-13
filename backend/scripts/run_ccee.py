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

    # Seed for reproducible test case selection across runs
    # Set via CCEE_SEED env var (default: 42 for reproducibility)
    ccee_seed = float(os.environ.get("CCEE_SEED", "42")) / 1000.0  # PG setseed range: -1 to 1
    ccee_seed = max(-1.0, min(1.0, ccee_seed))  # clamp

    conn = _get_conn()
    try:
        creator_uuid = _resolve_creator_uuid(conn, creator_id)
        if not creator_uuid:
            raise ValueError(f"Creator '{creator_id}' not found")

        cases = []
        with conn.cursor() as cur:
            # Seed PostgreSQL random for reproducible test case selection
            cur.execute("SELECT setseed(%s)", (ccee_seed,))

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

def _fs(val, width=8, decimals=2) -> str:
    """Format a score that may be None."""
    if val is None:
        return f"{'N/A':>{width}}"
    return f"{val:>{width}.{decimals}f}"


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
            lines.append(f"  {'B1 OCEAN alignment':<23} {_fs(b['B1'].get('score'))}")
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
# Helpers
# ---------------------------------------------------------------------------


def _resolve_doc_d(style_profile: Dict, creator_id: str = "") -> str:
    """Resolve Doc D text from style_profile or DB fallback."""
    # Try style_profile first
    dd = style_profile.get("compressed_doc_d", {})
    dd_text = dd.get("text", dd) if isinstance(dd, dict) else str(dd or "")
    if dd_text:
        return dd_text
    # Fallback to DB-based loader
    try:
        from core.evaluation.multi_turn_scorer import _load_compressed_doc_d
        cid = creator_id or style_profile.get("creator_id", "")
        if cid:
            return _load_compressed_doc_d(cid)
    except Exception:
        pass
    return ""


def _build_creator_summary(style_profile: Dict) -> str:
    """Build a natural-language creator summary from style_profile for B2 judge rubric."""
    creator_id = style_profile.get("creator_id", "unknown")

    # Language(s)
    lang_ratios = style_profile.get("A6_language_ratio", {}).get("ratios", {})
    top_langs = sorted(lang_ratios.items(), key=lambda x: -x[1])
    top_langs = [(l, r) for l, r in top_langs if l != "unknown" and r >= 0.05][:3]
    lang_str = ", ".join(f"{l} ({r*100:.0f}%)" for l, r in top_langs) if top_langs else "unknown"

    # Formality
    formality_score = style_profile.get("A8_formality", {}).get("formality_score", 0)
    abbrev_rate = style_profile.get("A8_formality", {}).get("abbreviation_rate", 0)
    if formality_score < 0.02:
        formality_str = "very informal"
    elif formality_score < 0.1:
        formality_str = "informal"
    else:
        formality_str = "semi-formal"
    if abbrev_rate > 0.03:
        formality_str += ", uses abbreviations frequently"

    # Emoji usage
    emoji_rate = style_profile.get("A2_emoji", {}).get("global_rate", 0)
    if emoji_rate > 0.5:
        emoji_str = "uses emojis heavily"
    elif emoji_rate > 0.2:
        emoji_str = "uses emojis regularly"
    elif emoji_rate > 0.05:
        emoji_str = "uses emojis occasionally"
    else:
        emoji_str = "rarely uses emojis"

    # Catchphrases
    catchphrases = style_profile.get("A9_catchphrases", {}).get("catchphrases", [])
    real_phrases = [
        cp["phrase"] for cp in catchphrases
        if cp["phrase"] not in ("media attachment", "mentioned their")
    ][:5]
    phrases_str = ", ".join(f'"{p}"' for p in real_phrases) if real_phrases else "none documented"

    # Message length
    a1 = style_profile.get("A1_length", {})
    mean_len = a1.get("mean", 0)
    if mean_len < 30:
        len_str = "very short messages"
    elif mean_len < 80:
        len_str = "short to medium messages"
    else:
        len_str = "medium to long messages"

    return (
        f"Creator: {creator_id}\n"
        f"Languages used: {lang_str}\n"
        f"Tone/Register: {formality_str}\n"
        f"Emoji style: {emoji_str}\n"
        f"Message length: {len_str} (avg {mean_len:.0f} chars)\n"
        f"Signature phrases: {phrases_str}\n"
        f"\nExpected behavior: responses should match this creator's language mix, "
        f"informal register, and communication style. A response in a foreign language "
        f"or overly formal tone does NOT match this creator."
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _run_prometheus_on_responses(
    test_cases: List[Dict],
    bot_responses: List[str],
    creator_summary: str = "",
    doc_d_text: str = "",
    creator_id: str = "",
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
    raw = evaluate_all_params(
        prom_cases, max_cases=len(prom_cases), creator_summary=creator_summary,
        doc_d_text=doc_d_text, creator_id=creator_id,
    )

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

        prom = _run_prometheus_on_responses(
            test_cases, run_bots,
            doc_d_text=_resolve_doc_d(style_profile, creator), creator_id=creator,
        )
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
    print(f" All-runs summary ({n_runs} runs, Qwen3-30B judge per run)")
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
    print("  Running Qwen3-30B-A3B judge (B2, B5, C2, C3, H1) via DeepInfra...")
    from core.evaluation.m_prometheus_judge import evaluate_all_params
    prom_cases = [
        {
            "bot_response": bot_responses[i],
            "ground_truth": tc["ground_truth"],
            "user_input": tc["user_input"],
        }
        for i, tc in enumerate(test_cases)
    ]
    raw = evaluate_all_params(
        prom_cases, max_cases=len(prom_cases),
        doc_d_text=_resolve_doc_d(style_profile, creator), creator_id=creator,
    )

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


def _build_metadata(args) -> Dict[str, Any]:
    """Build metadata block for JSON output — records model, provider, and run config."""
    from core.evaluation.m_prometheus_judge import MODEL_NAME as JUDGE_MODEL

    return {
        "ccee_version": "v5" if getattr(args, "v5", False) else (
            "v4.1" if getattr(args, "v41_metrics", False) else "v4"
        ),
        "timestamp": datetime.now().isoformat(),
        "model": os.environ.get("DEEPINFRA_MODEL", os.environ.get("LLM_MODEL_NAME", "unknown")),
        "provider": os.environ.get("LLM_PRIMARY_PROVIDER", "unknown"),
        "judge_model": JUDGE_MODEL,
        "lead_sim_model": os.environ.get("LEAD_SIM_MODEL", "Qwen/Qwen3-30B-A3B"),
        "cases": args.cases,
        "runs": args.runs,
        "mt_conversations": getattr(args, "mt_conversations", None),
        "mt_turns": getattr(args, "mt_turns", None),
        "flags": {
            "generate_only": getattr(args, "generate_only", False),
            "multi_turn": getattr(args, "multi_turn", False),
            "v4_composite": getattr(args, "v4_composite", False),
            "v41_metrics": getattr(args, "v41_metrics", False),
            "v5": getattr(args, "v5", False),
        },
    }


def _compute_v4_composite(
    st_results: Dict[str, Any],
    mt_results: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute full v4 composite: weighted integration of ST + MT dimensions.

    Formula: 0.20*S1 + 0.15*S2 + 0.20*S3 + 0.12*S4 + 0.05*J_old + 0.13*J_new + 0.08*K + 0.07*G5
    where:
      S1-S4, J_old from single-turn run
      J_new = 0.4*J3 + 0.3*J4 + 0.3*J5 (from multi_turn)
      K = 0.6*K1 + 0.4*K2 (from multi_turn)
      G5 from multi_turn

    NULL handling: excludes None dimensions and redistributes weight proportionally.
    """
    # Extract ST scores
    s1 = st_results.get("S1_style_fidelity", {}).get("score")
    s2 = st_results.get("S2_response_quality", {}).get("score")
    s3 = st_results.get("S3_strategic_alignment", {}).get("score")
    s4 = st_results.get("S4_adaptation", {}).get("score")

    # J_old: average of J1 and J2 from single-turn (cognitive fidelity)
    j1 = st_results.get("J1_memory_recall", {}).get("score")
    j2 = st_results.get("J2_multiturn_consistency", {}).get("score")
    j_old_vals = [v for v in [j1, j2] if v is not None]
    j_old = float(np.mean(j_old_vals)) if j_old_vals else None

    # J_new: weighted from multi-turn
    j3 = mt_results.get("J3_prompt_to_line_mean")
    j4 = mt_results.get("J4_line_to_line_mean")
    j5 = mt_results.get("J5_belief_drift_mean")
    j_new_parts = {"J3": (j3, 0.4), "J4": (j4, 0.3), "J5": (j5, 0.3)}
    j_new_active = {k: (v, w) for k, (v, w) in j_new_parts.items() if v is not None}
    if j_new_active:
        total_jw = sum(w for _, w in j_new_active.values())
        j_new = sum((w / total_jw) * v for v, w in j_new_active.values())
    else:
        j_new = None

    # K: weighted from multi-turn
    k1 = mt_results.get("K1_context_retention_mean")
    k2 = mt_results.get("K2_style_retention_mean")
    k_parts = {"K1": (k1, 0.6), "K2": (k2, 0.4)}
    k_active = {k: (v, w) for k, (v, w) in k_parts.items() if v is not None}
    if k_active:
        total_kw = sum(w for _, w in k_active.values())
        k_score = sum((w / total_kw) * v for v, w in k_active.values())
    else:
        k_score = None

    # G5 from multi-turn
    g5 = mt_results.get("G5_persona_robustness_mean")

    # Full v4 weighted composite
    dimensions = {
        "S1": (s1, 0.20),
        "S2": (s2, 0.15),
        "S3": (s3, 0.20),
        "S4": (s4, 0.12),
        "J_old": (j_old, 0.05),
        "J_new": (j_new, 0.13),
        "K": (k_score, 0.08),
        "G5": (g5, 0.07),
    }

    active = {k: (v, w) for k, (v, w) in dimensions.items() if v is not None}
    excluded = [k for k in dimensions if k not in active]

    if not active:
        return {"score": None, "reason": "no_active_dimensions"}

    total_w = sum(w for _, w in active.values())
    composite = sum((w / total_w) * v for v, w in active.values())

    return {
        "score": round(composite, 1),
        "active_dimensions": list(active.keys()),
        "excluded_dimensions": excluded,
        "dimension_scores": {k: round(v, 1) for k, (v, _) in active.items()},
        "dimension_weights": {k: round(w, 2) for k, (_, w) in dimensions.items()},
    }


def _compute_v41_composite(
    st_results: Dict[str, Any],
    mt_results: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute v4.1 composite: v4 weights redistributed + new J6 and L dimensions.

    v4.1 = 0.18*S1 + 0.13*S2 + 0.18*S3 + 0.10*S4 + 0.04*J_old + 0.10*J_new
           + 0.04*J6 + 0.07*K + 0.06*G5 + 0.10*L

    where:
      L = 0.40*L1 + 0.30*L2 + 0.30*L3 (new dimension)
      J6 = Q&A Consistency (standalone)
      All others unchanged from v4.

    NULL handling: excludes None dimensions and redistributes weight proportionally.
    """
    # Extract ST scores
    s1 = st_results.get("S1_style_fidelity", {}).get("score")
    s2 = st_results.get("S2_response_quality", {}).get("score")
    s3 = st_results.get("S3_strategic_alignment", {}).get("score")
    s4 = st_results.get("S4_adaptation", {}).get("score")

    # J_old
    j1 = st_results.get("J1_memory_recall", {}).get("score")
    j2 = st_results.get("J2_multiturn_consistency", {}).get("score")
    j_old_vals = [v for v in [j1, j2] if v is not None]
    j_old = float(np.mean(j_old_vals)) if j_old_vals else None

    # J_new = 0.4*J3 + 0.3*J4 + 0.3*J5
    j3 = mt_results.get("J3_prompt_to_line_mean")
    j4 = mt_results.get("J4_line_to_line_mean")
    j5 = mt_results.get("J5_belief_drift_mean")
    j_new_parts = {"J3": (j3, 0.4), "J4": (j4, 0.3), "J5": (j5, 0.3)}
    j_new_active = {k: (v, w) for k, (v, w) in j_new_parts.items() if v is not None}
    if j_new_active:
        total_jw = sum(w for _, w in j_new_active.values())
        j_new = sum((w / total_jw) * v for v, w in j_new_active.values())
    else:
        j_new = None

    # J6 = Q&A Consistency
    j6 = mt_results.get("J6_qa_consistency_mean")

    # K = 0.6*K1 + 0.4*K2
    k1 = mt_results.get("K1_context_retention_mean")
    k2 = mt_results.get("K2_style_retention_mean")
    k_parts = {"K1": (k1, 0.6), "K2": (k2, 0.4)}
    k_active = {k: (v, w) for k, (v, w) in k_parts.items() if v is not None}
    if k_active:
        total_kw = sum(w for _, w in k_active.values())
        k_score = sum((w / total_kw) * v for v, w in k_active.values())
    else:
        k_score = None

    # G5 from multi-turn
    g5 = mt_results.get("G5_persona_robustness_mean")

    # L = 0.40*L1 + 0.30*L2 + 0.30*L3 (new dimension)
    l1 = mt_results.get("L1_persona_tone_mean")
    l2 = mt_results.get("L2_logical_reasoning_mean")
    l3 = mt_results.get("L3_action_justification_mean")
    l_parts = {"L1": (l1, 0.40), "L2": (l2, 0.30), "L3": (l3, 0.30)}
    l_active = {k: (v, w) for k, (v, w) in l_parts.items() if v is not None}
    if l_active:
        total_lw = sum(w for _, w in l_active.values())
        l_score = sum((w / total_lw) * v for v, w in l_active.values())
    else:
        l_score = None

    # Full v4.1 weighted composite
    dimensions = {
        "S1": (s1, 0.18),
        "S2": (s2, 0.13),
        "S3": (s3, 0.18),
        "S4": (s4, 0.10),
        "J_old": (j_old, 0.04),
        "J_new": (j_new, 0.10),
        "J6": (j6, 0.04),
        "K": (k_score, 0.07),
        "G5": (g5, 0.06),
        "L": (l_score, 0.10),
    }

    active = {k: (v, w) for k, (v, w) in dimensions.items() if v is not None}
    excluded = [k for k in dimensions if k not in active]

    if not active:
        return {"score": None, "reason": "no_active_dimensions"}

    total_w = sum(w for _, w in active.values())
    composite = sum((w / total_w) * v for v, w in active.values())

    return {
        "score": round(composite, 1),
        "version": "v4.1",
        "active_dimensions": list(active.keys()),
        "excluded_dimensions": excluded,
        "dimension_scores": {k: round(v, 1) for k, (v, _) in active.items()},
        "dimension_weights": {k: round(w, 2) for k, (_, w) in dimensions.items()},
        "sub_dimensions": {
            "J_new": {"J3": j3, "J4": j4, "J5": j5},
            "K": {"K1": k1, "K2": k2},
            "L": {"L1": l1, "L2": l2, "L3": l3},
        },
    }


def _compute_v5_composite(
    st_results: Dict[str, Any],
    mt_results: Dict[str, Any],
    prometheus_scores: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute v5 composite: v4.1 + H1 Turing test + B (B2+B5 from judge).

    v5 = 0.16*S1 + 0.12*S2 + 0.16*S3 + 0.09*S4 + 0.03*J_old + 0.09*J_new
         + 0.03*J6 + 0.06*K + 0.05*G5 + 0.09*L + 0.07*H + 0.05*B

    H = H1 (MT Turing test) if available, else H2 (style fingerprint from ST)
    B = mean of available B sub-params (B1 from ST, B2/B5 from judge)
    """
    # Extract ST scores
    s1 = st_results.get("S1_style_fidelity", {}).get("score")
    s2 = st_results.get("S2_response_quality", {}).get("score")
    s3 = st_results.get("S3_strategic_alignment", {}).get("score")
    s4 = st_results.get("S4_adaptation", {}).get("score")

    # J_old
    j1 = st_results.get("J1_memory_recall", {}).get("score")
    j2 = st_results.get("J2_multiturn_consistency", {}).get("score")
    j_old_vals = [v for v in [j1, j2] if v is not None]
    j_old = float(np.mean(j_old_vals)) if j_old_vals else None

    # J_new = 0.4*J3 + 0.3*J4 + 0.3*J5
    j3 = mt_results.get("J3_prompt_to_line_mean")
    j4 = mt_results.get("J4_line_to_line_mean")
    j5 = mt_results.get("J5_belief_drift_mean")
    j_new_parts = {"J3": (j3, 0.4), "J4": (j4, 0.3), "J5": (j5, 0.3)}
    j_new_active = {k: (v, w) for k, (v, w) in j_new_parts.items() if v is not None}
    if j_new_active:
        total_jw = sum(w for _, w in j_new_active.values())
        j_new = sum((w / total_jw) * v for v, w in j_new_active.values())
    else:
        j_new = None

    # J6 = Q&A Consistency
    j6 = mt_results.get("J6_qa_consistency_mean")

    # K = 0.6*K1 + 0.4*K2
    k1 = mt_results.get("K1_context_retention_mean")
    k2 = mt_results.get("K2_style_retention_mean")
    k_parts = {"K1": (k1, 0.6), "K2": (k2, 0.4)}
    k_active = {k: (v, w) for k, (v, w) in k_parts.items() if v is not None}
    if k_active:
        total_kw = sum(w for _, w in k_active.values())
        k_score = sum((w / total_kw) * v for v, w in k_active.values())
    else:
        k_score = None

    # G5
    g5 = mt_results.get("G5_persona_robustness_mean")

    # L = 0.40*L1 + 0.30*L2 + 0.30*L3
    l1 = mt_results.get("L1_persona_tone_mean")
    l2 = mt_results.get("L2_logical_reasoning_mean")
    l3 = mt_results.get("L3_action_justification_mean")
    l_parts = {"L1": (l1, 0.40), "L2": (l2, 0.30), "L3": (l3, 0.30)}
    l_active_parts = {k: (v, w) for k, (v, w) in l_parts.items() if v is not None}
    if l_active_parts:
        total_lw = sum(w for _, w in l_active_parts.values())
        l_score = sum((w / total_lw) * v for v, w in l_active_parts.values())
    else:
        l_score = None

    # H: prefer H1 (MT Turing test) over H2 (style fingerprint)
    h1_data = mt_results.get("H1_turing_test", {})
    h1 = h1_data.get("score") if isinstance(h1_data, dict) else None
    h2 = st_results.get("H_indistinguishability", {}).get("H2", {}).get("score") if h1 is None else None
    h_score = h1 if h1 is not None else h2

    # B: mean of available B sub-params
    b_components = []
    # B1 from ST
    b1 = st_results.get("B_persona_fidelity", {}).get("B1", {}).get("score")
    if b1 is not None:
        b_components.append(b1)
    # B4 from ST
    b4 = st_results.get("B_persona_fidelity", {}).get("B4", {}).get("score")
    if b4 is not None:
        b_components.append(b4)
    # B2, B5 from prometheus judge
    if prometheus_scores:
        b2 = prometheus_scores.get("B2_persona_consistency", {}).get("score")
        b5 = prometheus_scores.get("B5_emotional_signature", {}).get("score")
        if b2 is not None:
            b_components.append(b2)
        if b5 is not None:
            b_components.append(b5)
    b_score = float(np.mean(b_components)) if b_components else None

    # Full v5 weighted composite
    dimensions = {
        "S1": (s1, 0.16),
        "S2": (s2, 0.12),
        "S3": (s3, 0.16),
        "S4": (s4, 0.09),
        "J_old": (j_old, 0.03),
        "J_new": (j_new, 0.09),
        "J6": (j6, 0.03),
        "K": (k_score, 0.06),
        "G5": (g5, 0.05),
        "L": (l_score, 0.09),
        "H": (h_score, 0.07),
        "B": (b_score, 0.05),
    }

    active = {k: (v, w) for k, (v, w) in dimensions.items() if v is not None}
    excluded = [k for k in dimensions if k not in active]

    if not active:
        return {"score": None, "reason": "no_active_dimensions"}

    total_w = sum(w for _, w in active.values())
    composite = sum((w / total_w) * v for v, w in active.values())

    return {
        "score": round(composite, 1),
        "version": "v5",
        "active_dimensions": list(active.keys()),
        "excluded_dimensions": excluded,
        "dimension_scores": {k: round(v, 1) for k, (v, _) in active.items()},
        "dimension_weights": {k: round(w, 2) for k, (_, w) in dimensions.items()},
        "sub_dimensions": {
            "J_new": {"J3": j3, "J4": j4, "J5": j5},
            "K": {"K1": k1, "K2": k2},
            "L": {"L1": l1, "L2": l2, "L3": l3},
            "H": {"H1": h1, "H2": h2},
            "B": {"B1": b1, "B4": b4,
                  "B2": prometheus_scores.get("B2_persona_consistency", {}).get("score") if prometheus_scores else None,
                  "B5": prometheus_scores.get("B5_emotional_signature", {}).get("score") if prometheus_scores else None},
        },
    }


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
        help="Run Qwen3-30B-A3B judge (B2, B5, C2, C3, H1) via DeepInfra"
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
        help="Re-score an existing generate-only JSON with Qwen3-30B-A3B via DeepInfra."
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
    # --- v4 multi-turn flags ---
    parser.add_argument(
        "--multi-turn", action="store_true",
        help="Run v4 multi-turn evaluation (J3, J4, J5, K1, K2, G5)"
    )
    parser.add_argument(
        "--mt-conversations", type=int, default=8,
        help="Number of multi-turn conversations to generate (default: 8)"
    )
    parser.add_argument(
        "--mt-turns", type=int, default=10,
        help="Number of turns per conversation (default: 10)"
    )
    parser.add_argument(
        "--v4-composite", action="store_true",
        help="Include v4 multi-turn scores in composite calculation"
    )
    parser.add_argument(
        "--v41-metrics", action="store_true",
        help="Enable v4.1 new metrics (J6, L1, L2, L3) — requires --multi-turn"
    )
    parser.add_argument(
        "--v5", action="store_true",
        help="Enable v5 metrics (H1 Turing test + auto B2/B5 judge) — requires --multi-turn"
    )
    parser.add_argument(
        "--v52-fixes", action="store_true",
        help="Enable v5.2 calibration fixes: multi-adversarial, Q&A probes, dynamic B2 rubric — requires --v5"
    )
    args = parser.parse_args()

    # --v5 implies --v41-metrics and --v4-composite
    if args.v5:
        args.v41_metrics = True
        args.v4_composite = True

    if args.v41_metrics and not args.multi_turn:
        parser.error("--v41-metrics requires --multi-turn")

    if args.v52_fixes and not args.v5:
        parser.error("--v52-fixes requires --v5")

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

        # Optional: run Prometheus judge (Qwen3-30B-A3B via DeepInfra)
        prometheus_scores = None
        if args.with_prometheus_judge:
            print("  Running Qwen3-30B-A3B judge (B2, B5, C2, C3, H1) via DeepInfra...")
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
                # Load Doc D for exemplar calibration
                raw = evaluate_all_params(
                    prom_cases, max_cases=len(prom_cases),
                    doc_d_text=_resolve_doc_d(style_profile, creator), creator_id=creator,
                )
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
                # PersonaGym exemplar calibration for B2
                _b2_exemplar_rubric = ""
                try:
                    from core.evaluation.exemplar_generator import get_exemplar_rubric_block
                    _doc_d_text = _resolve_doc_d(style_profile, creator)
                    if _doc_d_text:
                        _b2_exemplar_rubric = get_exemplar_rubric_block(
                            _doc_d_text, creator_id=creator
                        )
                        if _b2_exemplar_rubric:
                            print("  B2 using exemplar-calibrated rubric (PersonaGym)")
                except Exception as _ex:
                    print(f"  WARNING: Exemplar generation for B2 failed: {_ex}")
                llm_scores = _asyncio.run(
                    score_llm_judge_batch(
                        test_cases, bot_responses, creator_desc,
                        exemplar_rubric=_b2_exemplar_rubric,
                    )
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
        # --- v4 multi-turn in generate-only mode ---
        v4_genonly = None
        if args.multi_turn:
            print(f"\n[MT] Running v4 multi-turn evaluation...")
            print(f"  {args.mt_conversations} conversations × {args.mt_turns} turns")
            from core.evaluation.multi_turn_generator import generate_multi_turn_batch
            from core.evaluation.multi_turn_scorer import score_multi_turn_batch

            mt_gen_kwargs = dict(
                creator_id=creator,
                test_cases=test_cases,
                n_turns=args.mt_turns,
                n_conversations=args.mt_conversations,
                include_belief_shift=True,
                include_adversarial=True,
            )
            if getattr(args, "v52_fixes", False):
                mt_gen_kwargs["inject_qa_probes"] = True
                mt_gen_kwargs["doc_d_text"] = _build_creator_summary(style_profile)
            mt_conversations = generate_multi_turn_batch(**mt_gen_kwargs)
            print(f"\n  Scoring {len(mt_conversations)} multi-turn conversations...")
            v4_genonly = score_multi_turn_batch(
                mt_conversations, creator, style_profile,
                enable_v41=args.v41_metrics,
                enable_v5=args.v5,
            )

            print(f"\n{'='*60}")
            print(f" v4 Multi-Turn Results")
            print(f"{'='*60}")
            def _fmt(v): return f"{v:.1f}" if v is not None else "null"
            print(f"  J3 Prompt-to-Line:    {_fmt(v4_genonly['J3_prompt_to_line_mean'])}")
            print(f"  J4 Line-to-Line:      {_fmt(v4_genonly['J4_line_to_line_mean'])}")
            print(f"  J5 Belief Drift:      {_fmt(v4_genonly['J5_belief_drift_mean'])}")
            print(f"  K1 Context Retention: {_fmt(v4_genonly['K1_context_retention_mean'])}")
            print(f"  K2 Style Retention:   {_fmt(v4_genonly['K2_style_retention_mean'])}")
            print(f"  G5 Persona Robust.:   {_fmt(v4_genonly['G5_persona_robustness_mean'])}")
            print(f"  MT Composite:         {_fmt(v4_genonly['mt_composite_mean'])}")
            if args.v41_metrics:
                print(f"  --- v4.1 metrics ---")
                print(f"  J6 Q&A Consistency:   {_fmt(v4_genonly.get('J6_qa_consistency_mean'))}")
                print(f"  L1 Persona Tone:      {_fmt(v4_genonly.get('L1_persona_tone_mean'))}")
                print(f"  L2 Logical Reasoning: {_fmt(v4_genonly.get('L2_logical_reasoning_mean'))}")
                print(f"  L3 Action Justif.:    {_fmt(v4_genonly.get('L3_action_justification_mean'))}")
            if args.v5:
                h1_data = v4_genonly.get("H1_turing_test", {})
                print(f"  --- v5 metrics ---")
                print(f"  H1 Turing Test:       {_fmt(h1_data.get('score'))}")

            # Print conversation details
            feedback_keys = ["J3_prompt_to_line", "J4_line_to_line", "J5_belief_drift",
                            "K1_context_retention", "G5_persona_robustness"]
            if args.v41_metrics:
                feedback_keys.extend(["J6_qa_consistency", "L3_action_justification"])
            for conv_data in v4_genonly.get("per_conversation_full", []):
                for sub_key in feedback_keys:
                    detail = conv_data.get(sub_key, {})
                    if detail.get("feedback"):
                        print(f"\n  {sub_key} feedback: {detail['feedback'][:200]}")

        # v5: auto-run Prometheus judge on ST test cases (B2, B5, C2, C3, H1)
        genonly_prometheus = None
        if args.v5 and all_bot_responses_per_run:
            print(f"\n[v5] Auto-running judge on ST cases (B2, B5, C2, C3)...")
            _creator_summary = _build_creator_summary(style_profile) if getattr(args, "v52_fixes", False) else ""
            if _creator_summary:
                print(f"  [v5.2] Dynamic B2 rubric active for: {creator}")
            try:
                genonly_prometheus = _run_prometheus_on_responses(
                    test_cases, all_bot_responses_per_run[-1],
                    creator_summary=_creator_summary,
                    doc_d_text=_resolve_doc_d(style_profile, creator), creator_id=creator,
                )
                print(
                    f"  B2={genonly_prometheus['B2_persona_consistency']['score']:.1f} "
                    f"B5={genonly_prometheus['B5_emotional_signature']['score']:.1f} "
                    f"C2={genonly_prometheus['C2_naturalness']['score']:.1f} "
                    f"C3={genonly_prometheus['C3_contextual_appropriateness']['score']:.1f}"
                )
            except Exception as e:
                print(f"  WARNING: Auto-judge failed: {e}")

        # Compute composites: v4, v4.1, v5
        v4_composite_data = None
        v41_composite_data = None
        v5_composite_data = None
        if v4_genonly is not None and all_run_results:
            v4_composite_data = _compute_v4_composite(all_run_results[-1], v4_genonly)
            if v4_composite_data.get("score") is not None:
                print(f"\n  v4 COMPOSITE (weighted ST+MT): {v4_composite_data['score']:.1f}")
            if args.v41_metrics:
                v41_composite_data = _compute_v41_composite(all_run_results[-1], v4_genonly)
                if v41_composite_data.get("score") is not None:
                    print(f"  v4.1 COMPOSITE (with J6+L):   {v41_composite_data['score']:.1f}")
            if args.v5:
                v5_composite_data = _compute_v5_composite(
                    all_run_results[-1], v4_genonly, genonly_prometheus
                )
                if v5_composite_data.get("score") is not None:
                    print(f"  v5 COMPOSITE (with H1+B):     {v5_composite_data['score']:.1f}")
                    if v5_composite_data.get("excluded_dimensions"):
                        print(f"    Excluded: {v5_composite_data['excluded_dimensions']}")

        genonly_output = {
            "metadata": _build_metadata(args),
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
        if v4_genonly is not None:
            genonly_output["v4_multi_turn"] = v4_genonly
        if v4_composite_data is not None:
            genonly_output["v4_composite"] = v4_composite_data
        if v41_composite_data is not None:
            genonly_output["v41_composite"] = v41_composite_data
        if v5_composite_data is not None:
            genonly_output["v5_composite"] = v5_composite_data
        if genonly_prometheus is not None:
            genonly_output["prometheus_scores"] = genonly_prometheus
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

    # --- v4 multi-turn evaluation ---
    v4_results = None
    normal_prometheus = None
    if args.multi_turn:
        print(f"\n[MT] Running v4 multi-turn evaluation...")
        print(f"  {args.mt_conversations} conversations × {args.mt_turns} turns")
        from core.evaluation.multi_turn_generator import generate_multi_turn_batch
        from core.evaluation.multi_turn_scorer import score_multi_turn_batch

        mt_gen_kwargs2 = dict(
            creator_id=creator,
            test_cases=test_cases,
            n_turns=args.mt_turns,
            n_conversations=args.mt_conversations,
            include_belief_shift=True,
            include_adversarial=True,
        )
        if getattr(args, "v52_fixes", False):
            mt_gen_kwargs2["inject_qa_probes"] = True
            mt_gen_kwargs2["doc_d_text"] = _build_creator_summary(style_profile)
        mt_conversations = generate_multi_turn_batch(**mt_gen_kwargs2)
        print(f"\n  Scoring {len(mt_conversations)} multi-turn conversations...")
        v4_results = score_multi_turn_batch(
            mt_conversations, creator, style_profile,
            enable_v41=args.v41_metrics,
            enable_v5=args.v5,
        )

        print(f"\n{'='*60}")
        print(f" v4 Multi-Turn Results")
        print(f"{'='*60}")
        def _fmtv(v): return f"{v:.1f}" if v is not None else "null"
        print(f"  J3 Prompt-to-Line:    {_fmtv(v4_results['J3_prompt_to_line_mean'])}")
        print(f"  J4 Line-to-Line:      {_fmtv(v4_results['J4_line_to_line_mean'])}")
        print(f"  J5 Belief Drift:      {_fmtv(v4_results['J5_belief_drift_mean'])}")
        print(f"  K1 Context Retention: {_fmtv(v4_results['K1_context_retention_mean'])}")
        print(f"  K2 Style Retention:   {_fmtv(v4_results['K2_style_retention_mean'])}")
        print(f"  G5 Persona Robust.:   {_fmtv(v4_results['G5_persona_robustness_mean'])}")
        print(f"  MT Composite:         {_fmtv(v4_results['mt_composite_mean'])}")
        if args.v41_metrics:
            print(f"  --- v4.1 metrics ---")
            print(f"  J6 Q&A Consistency:   {_fmtv(v4_results.get('J6_qa_consistency_mean'))}")
            print(f"  L1 Persona Tone:      {_fmtv(v4_results.get('L1_persona_tone_mean'))}")
            print(f"  L2 Logical Reasoning: {_fmtv(v4_results.get('L2_logical_reasoning_mean'))}")
            print(f"  L3 Action Justif.:    {_fmtv(v4_results.get('L3_action_justification_mean'))}")
        if args.v5:
            h1_data = v4_results.get("H1_turing_test", {})
            print(f"  --- v5 metrics ---")
            print(f"  H1 Turing Test:       {_fmtv(h1_data.get('score'))}")

        # v5: auto-run Prometheus judge on ST test cases
        normal_prometheus = None
        if args.v5 and all_run_results:
            print(f"\n[v5] Auto-running judge on ST cases (B2, B5, C2, C3)...")
            _norm_summary = _build_creator_summary(style_profile) if getattr(args, "v52_fixes", False) else ""
            if _norm_summary:
                print(f"  [v5.2] Dynamic B2 rubric active for: {creator}")
            try:
                normal_prometheus = _run_prometheus_on_responses(
                    test_cases, bot_responses,
                    creator_summary=_norm_summary,
                    doc_d_text=_resolve_doc_d(style_profile, creator), creator_id=creator,
                )
                print(
                    f"  B2={normal_prometheus['B2_persona_consistency']['score']:.1f} "
                    f"B5={normal_prometheus['B5_emotional_signature']['score']:.1f} "
                    f"C2={normal_prometheus['C2_naturalness']['score']:.1f} "
                    f"C3={normal_prometheus['C3_contextual_appropriateness']['score']:.1f}"
                )
            except Exception as e:
                print(f"  WARNING: Auto-judge failed: {e}")

        if args.v4_composite and all_run_results:
            v4_composite_data = _compute_v4_composite(all_run_results[-1], v4_results)
            if v4_composite_data.get("score") is not None:
                print(f"\n  v4 COMPOSITE (weighted ST+MT): {v4_composite_data['score']:.1f}")
                print(f"    Active: {v4_composite_data.get('active_dimensions', [])}")
                if v4_composite_data.get("excluded_dimensions"):
                    print(f"    Excluded: {v4_composite_data['excluded_dimensions']}")
            else:
                print(f"\n  v4 Composite: N/A (insufficient data)")
            if args.v41_metrics:
                v41_data = _compute_v41_composite(all_run_results[-1], v4_results)
                if v41_data.get("score") is not None:
                    print(f"  v4.1 COMPOSITE (with J6+L):   {v41_data['score']:.1f}")
            if args.v5:
                v5_data = _compute_v5_composite(
                    all_run_results[-1], v4_results, normal_prometheus
                )
                if v5_data.get("score") is not None:
                    print(f"  v5 COMPOSITE (with H1+B):     {v5_data['score']:.1f}")

    # Compare to baseline
    if args.compare:
        print(f"\n[4] Comparing to baseline: {args.compare}")
        with open(args.compare) as f:
            baseline_data = json.load(f)
        baseline_scores = baseline_data.get("composites", [])
        if baseline_scores:
            comparison = scorer.compare_to_baseline(all_composites, baseline_scores)
            if "verdict" not in comparison:
                print(f"  Status: {comparison.get('status', 'unknown')} (current={len(all_composites)}, baseline={len(baseline_scores)} scores)")
            else:
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
        "metadata": _build_metadata(args),
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
    if v4_results is not None:
        output["v4_multi_turn"] = v4_results
    if args.v4_composite and v4_results is not None and all_run_results:
        output["v4_composite"] = _compute_v4_composite(all_run_results[-1], v4_results)
    if args.v41_metrics and v4_results is not None and all_run_results:
        output["v41_composite"] = _compute_v41_composite(all_run_results[-1], v4_results)
    if args.v5 and v4_results is not None and all_run_results:
        output["v5_composite"] = _compute_v5_composite(
            all_run_results[-1], v4_results, normal_prometheus
        )
        if normal_prometheus is not None:
            output["prometheus_scores"] = normal_prometheus
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n  Results saved to {out_path}")


if __name__ == "__main__":
    main()
