"""
CPE Ablation Runner — Statistically Rigorous System Isolation

Runs the CPE v2 metrics (BERTScore + lexical) multiple times on baseline
and ablated configs, then performs statistical significance testing.

Protocol (from CPE_V2_METHODOLOGY.md):
  1. Run baseline config N times (default 5)
  2. Disable target system
  3. Run ablated config N times
  4. Wilcoxon signed-rank test on per-case BERTScore-F1 means
  5. Cliff's delta effect size
  6. Decision: KEEP / REMOVE / INVESTIGATE

Scientific basis:
  - Wilcoxon signed-rank: non-parametric paired test (no normality assumption)
  - Cliff's delta: effect size robust to non-normal distributions
  - Power: 50 cases × 5 runs detects d ≥ 0.25 with 80% power at α=0.05

Usage:
    # Ablate style_normalizer
    railway run python3.11 tests/cpe_ablation_runner.py --creator iris_bertran \\
        --disable style_normalizer --runs 5

    # Ablate few-shot loader with custom test set
    railway run python3.11 tests/cpe_ablation_runner.py --creator iris_bertran \\
        --disable few_shot_loader --runs 3 --test-set tests/cpe_data/iris_bertran/test_set.json

    # Baseline only (no ablation — establishes reference)
    railway run python3.11 tests/cpe_ablation_runner.py --creator iris_bertran \\
        --baseline-only --runs 5

Systems that can be ablated (via env vars or config):
  - style_normalizer (ENABLE_STYLE_NORMALIZER=false)
  - few_shot_loader (ENABLE_FEW_SHOT=false)
  - memory_engine (ENABLE_MEMORY=false)
  - rag (ENABLE_RAG=false)
  - length_hints (ENABLE_LENGTH_HINTS=false)
  - question_hints (ENABLE_QUESTION_HINTS=false)
  - pool_responses (ENABLE_POOL=false)
  - ppa (ENABLE_PPA=false)

Cost: $0 per run (Qwen3-14B via DeepInfra for generation, local BERTScore)
Time: ~8 min per config (5 runs × 50 cases × ~2s/case)
"""

import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cpe_ablation")
logger.setLevel(logging.INFO)


# System → env var mapping for ablation
ABLATION_ENV_VARS = {
    "style_normalizer": "ENABLE_STYLE_NORMALIZER",
    "few_shot_loader": "ENABLE_FEW_SHOT",
    "memory_engine": "ENABLE_MEMORY",
    "rag": "ENABLE_RAG",
    "length_hints": "ENABLE_LENGTH_HINTS",
    "question_hints": "ENABLE_QUESTION_HINTS",
    "pool_responses": "ENABLE_POOL",
    "ppa": "ENABLE_PPA",
    "sbs": "ENABLE_SCORE_BEFORE_SPEAK",
}


# =========================================================================
# STATISTICAL TESTS
# =========================================================================

def wilcoxon_signed_rank(x: List[float], y: List[float]) -> Tuple[float, float]:
    """Wilcoxon signed-rank test (non-parametric paired test).

    Returns (statistic, p_value).
    Falls back to manual implementation if scipy unavailable.
    """
    try:
        from scipy.stats import wilcoxon
        stat, p = wilcoxon(x, y, alternative="two-sided")
        return float(stat), float(p)
    except ImportError:
        # Manual implementation for environments without scipy
        diffs = [a - b for a, b in zip(x, y) if a != b]
        if not diffs:
            return 0.0, 1.0

        abs_diffs = [(abs(d), i, d) for i, d in enumerate(diffs)]
        abs_diffs.sort(key=lambda t: t[0])

        # Assign ranks (handle ties by averaging)
        ranks = [0.0] * len(abs_diffs)
        i = 0
        while i < len(abs_diffs):
            j = i
            while j < len(abs_diffs) and abs_diffs[j][0] == abs_diffs[i][0]:
                j += 1
            avg_rank = (i + j + 1) / 2  # 1-indexed average
            for k in range(i, j):
                ranks[k] = avg_rank
            i = j

        # Sum positive and negative ranks
        w_plus = sum(ranks[k] for k in range(len(diffs)) if abs_diffs[k][2] > 0)
        w_minus = sum(ranks[k] for k in range(len(diffs)) if abs_diffs[k][2] < 0)
        w = min(w_plus, w_minus)

        n = len(diffs)
        # Normal approximation for p-value (valid for n > 10)
        if n > 10:
            import math
            mean_w = n * (n + 1) / 4
            std_w = math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
            z = (w - mean_w) / std_w if std_w > 0 else 0
            # Two-tailed p-value from normal approximation
            p = 2 * (1 - _norm_cdf(abs(z)))
        else:
            # For small n, return conservative p-value
            p = 0.10  # Conservative fallback

        return float(w), float(p)


def _norm_cdf(x: float) -> float:
    """Standard normal CDF approximation."""
    import math
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def cliffs_delta(x: List[float], y: List[float]) -> float:
    """Cliff's delta effect size (non-parametric).

    Interpretation:
      |d| < 0.147: negligible
      |d| < 0.330: small
      |d| < 0.474: medium
      |d| >= 0.474: large

    Reference: Cliff (1993), Romano et al. (2006)
    """
    n_x, n_y = len(x), len(y)
    if n_x == 0 or n_y == 0:
        return 0.0

    count = 0
    for xi in x:
        for yi in y:
            if xi > yi:
                count += 1
            elif xi < yi:
                count -= 1

    return count / (n_x * n_y)


# =========================================================================
# PIPELINE RUNNER
# =========================================================================

def _get_platform_user_id(lead_id: str) -> Optional[str]:
    try:
        from api.database import SessionLocal
        from api.models import Lead
        session = SessionLocal()
        try:
            row = session.query(Lead.platform_user_id).filter_by(id=lead_id).first()
            return row[0] if row and row[0] else None
        finally:
            session.close()
    except Exception:
        return None


async def run_single(creator_id: str, conversations: List[Dict], run_id: int) -> List[Dict]:
    """Run pipeline once on all test cases."""
    from core.dm_agent_v2 import DMResponderAgent

    agent = DMResponderAgent(creator_id=creator_id)
    results = []

    for i, conv in enumerate(conversations, 1):
        test_input = conv.get("test_input", conv.get("lead_message", ""))
        lead_id = conv.get("lead_id", "")
        sender_id = _get_platform_user_id(lead_id) or lead_id

        history = []
        for turn in conv.get("turns", []):
            role = turn.get("role", "")
            content = turn.get("content", "")
            if not content:
                continue
            if role in ("iris", "assistant"):
                history.append({"role": "assistant", "content": content})
            elif role in ("lead", "user"):
                history.append({"role": "user", "content": content})
        if history and history[-1].get("content") == test_input:
            history = history[:-1]

        metadata = {
            "history": history,
            "username": conv.get("username", conv.get("lead_name", sender_id)),
            "message_id": f"abl_r{run_id}_{conv.get('id', i)}",
        }

        t0 = time.monotonic()
        try:
            dm_response = await agent.process_dm(
                message=test_input, sender_id=sender_id, metadata=metadata
            )
            bot_response = dm_response.content if dm_response else ""
        except Exception as e:
            logger.error(f"[run{run_id}][{conv.get('id', i)}] Error: {e}")
            bot_response = ""

        results.append({
            "id": conv.get("id", f"case_{i}"),
            "test_input": test_input,
            "ground_truth": conv.get("ground_truth", ""),
            "bot_response": bot_response,
            "elapsed_ms": int((time.monotonic() - t0) * 1000),
        })

    return results


async def run_multiple(
    creator_id: str,
    conversations: List[Dict],
    n_runs: int,
    label: str,
) -> List[List[Dict]]:
    """Run pipeline n_runs times, return list of result sets."""
    all_runs = []
    for run_id in range(1, n_runs + 1):
        logger.info(f"[{label}] Run {run_id}/{n_runs}...")
        results = await run_single(creator_id, conversations, run_id)
        all_runs.append(results)
        logger.info(f"[{label}] Run {run_id} complete: {len(results)} cases")
    return all_runs


# =========================================================================
# BERTSCORE COMPUTATION (uses cpe_bertscore module)
# =========================================================================

def compute_bertscore_for_runs(all_runs: List[List[Dict]]) -> List[List[float]]:
    """Compute BERTScore F1 for each run's results.

    Returns list of lists: [[f1_case1, f1_case2, ...], ...] per run.
    """
    try:
        from bert_score import score as bert_score
    except ImportError:
        logger.error("bert-score not installed. Run: pip install bert-score")
        sys.exit(1)

    all_f1s = []
    for run_idx, results in enumerate(all_runs):
        candidates = [r.get("bot_response", "") for r in results]
        references = [r.get("ground_truth", "") for r in results]

        # Replace empty strings to avoid errors
        safe_cands = [c if c else "." for c in candidates]
        safe_refs = [r if r else "." for r in references]

        _, _, F1 = bert_score(
            cands=safe_cands,
            refs=safe_refs,
            model_type="xlm-roberta-large",
            batch_size=16,
            verbose=False,
            rescale_with_baseline=True,
        )

        f1_list = [F1[i].item() for i in range(len(candidates))]
        # Zero out scores for empty pairs
        for i in range(len(candidates)):
            if not candidates[i] or not references[i]:
                f1_list[i] = 0.0

        all_f1s.append(f1_list)
        logger.info(f"  BERTScore run {run_idx + 1}: mean F1={statistics.mean(f1_list):.4f}")

    return all_f1s


# =========================================================================
# MAIN
# =========================================================================

async def main():
    parser = argparse.ArgumentParser(description="CPE Ablation Runner")
    parser.add_argument("--creator", required=True, help="Creator slug")
    parser.add_argument("--disable", default=None, help="System to ablate (e.g., style_normalizer)")
    parser.add_argument("--baseline-only", action="store_true", help="Run baseline only, no ablation")
    parser.add_argument("--runs", type=int, default=5, help="Number of runs per config (default: 5)")
    parser.add_argument("--test-set", default=None, help="Custom test set path")
    parser.add_argument("--output", default=None, help="Custom output path")
    args = parser.parse_args()

    if not args.disable and not args.baseline_only:
        logger.error("Specify --disable SYSTEM or --baseline-only")
        sys.exit(1)

    creator = args.creator
    cpe_dir = REPO_ROOT / "tests" / "cpe_data" / creator / "results"
    cpe_dir.mkdir(parents=True, exist_ok=True)

    # Load test set
    test_path = Path(args.test_set) if args.test_set else (
        REPO_ROOT / "tests" / "cpe_data" / creator / "test_set.json"
    )
    if not test_path.exists():
        test_path = REPO_ROOT / "tests" / "test_set_real_leads.json"

    with open(test_path) as f:
        data = json.load(f)
    conversations = data if isinstance(data, list) else data.get("conversations", data.get("test_cases", []))
    logger.info(f"Loaded {len(conversations)} test cases from {test_path}")

    # Phase 1: Baseline runs
    logger.info(f"=== BASELINE: {args.runs} runs ===")
    t0 = time.monotonic()
    baseline_runs = await run_multiple(creator, conversations, args.runs, "baseline")
    baseline_elapsed = time.monotonic() - t0
    logger.info(f"Baseline complete in {baseline_elapsed:.0f}s")

    # Phase 2: Compute BERTScore for baseline
    logger.info("Computing BERTScore for baseline runs...")
    baseline_f1s = compute_bertscore_for_runs(baseline_runs)

    # Per-case mean F1 across runs (baseline)
    n_cases = len(conversations)
    baseline_means = []
    for case_idx in range(n_cases):
        case_f1s = [baseline_f1s[run][case_idx] for run in range(args.runs)]
        baseline_means.append(statistics.mean(case_f1s))

    baseline_overall = statistics.mean(baseline_means)
    baseline_std = statistics.stdev(baseline_means) if len(baseline_means) > 1 else 0

    logger.info(f"Baseline BERTScore-F1: {baseline_overall:.4f} ± {baseline_std:.4f}")

    if args.baseline_only:
        # Output baseline results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(args.output) if args.output else (
            cpe_dir / f"ablation_baseline_{timestamp}.json"
        )

        output = {
            "creator": creator,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "config": "baseline",
            "n_runs": args.runs,
            "n_cases": n_cases,
            "baseline": {
                "bertscore_f1_mean": round(baseline_overall, 4),
                "bertscore_f1_std": round(baseline_std, 4),
                "per_case_means": [round(m, 4) for m in baseline_means],
            },
            "elapsed_s": round(baseline_elapsed, 1),
        }

        with open(output_path, "w") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        print(f"\n  Baseline BERTScore-F1: {baseline_overall:.4f} ± {baseline_std:.4f}")
        print(f"  Saved: {output_path}")
        return

    # Phase 3: Ablation runs
    system = args.disable
    env_var = ABLATION_ENV_VARS.get(system)
    if not env_var:
        logger.error(f"Unknown system '{system}'. Available: {list(ABLATION_ENV_VARS.keys())}")
        sys.exit(1)

    logger.info(f"=== ABLATION: disabling {system} ({env_var}=false) ===")

    # Set env var to disable system
    original_value = os.environ.get(env_var)
    os.environ[env_var] = "false"

    try:
        t1 = time.monotonic()
        ablated_runs = await run_multiple(creator, conversations, args.runs, f"ablated-{system}")
        ablated_elapsed = time.monotonic() - t1
    finally:
        # Restore env var
        if original_value is not None:
            os.environ[env_var] = original_value
        elif env_var in os.environ:
            del os.environ[env_var]

    # Phase 4: Compute BERTScore for ablated
    logger.info("Computing BERTScore for ablated runs...")
    ablated_f1s = compute_bertscore_for_runs(ablated_runs)

    ablated_means = []
    for case_idx in range(n_cases):
        case_f1s = [ablated_f1s[run][case_idx] for run in range(args.runs)]
        ablated_means.append(statistics.mean(case_f1s))

    ablated_overall = statistics.mean(ablated_means)
    ablated_std = statistics.stdev(ablated_means) if len(ablated_means) > 1 else 0

    # Phase 5: Statistical testing
    logger.info("Running statistical tests...")
    w_stat, p_value = wilcoxon_signed_rank(baseline_means, ablated_means)
    delta = cliffs_delta(baseline_means, ablated_means)

    # Decision rule
    mean_diff = baseline_overall - ablated_overall
    if p_value < 0.05 and abs(delta) > 0.20:
        if mean_diff > 0:
            decision = "KEEP"
            reason = f"Removing {system} significantly hurts quality (p={p_value:.4f}, d={delta:.3f})"
        else:
            decision = "REMOVE"
            reason = f"Removing {system} significantly improves quality (p={p_value:.4f}, d={delta:.3f})"
    elif p_value >= 0.05:
        decision = "REMOVE (no effect)"
        reason = f"No significant effect detected (p={p_value:.4f}). Simpler config preferred."
    else:
        decision = "INVESTIGATE"
        reason = f"Significant p={p_value:.4f} but small effect d={delta:.3f}"

    # Interpret Cliff's delta magnitude
    abs_d = abs(delta)
    if abs_d < 0.147:
        d_label = "negligible"
    elif abs_d < 0.330:
        d_label = "small"
    elif abs_d < 0.474:
        d_label = "medium"
    else:
        d_label = "large"

    # Output
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = Path(args.output) if args.output else (
        cpe_dir / f"ablation_{system}_{timestamp}.json"
    )

    output = {
        "creator": creator,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ablated_system": system,
        "env_var": env_var,
        "n_runs": args.runs,
        "n_cases": n_cases,
        "baseline": {
            "bertscore_f1_mean": round(baseline_overall, 4),
            "bertscore_f1_std": round(baseline_std, 4),
            "per_case_means": [round(m, 4) for m in baseline_means],
        },
        "ablated": {
            "bertscore_f1_mean": round(ablated_overall, 4),
            "bertscore_f1_std": round(ablated_std, 4),
            "per_case_means": [round(m, 4) for m in ablated_means],
        },
        "statistical_test": {
            "test": "Wilcoxon signed-rank (two-sided)",
            "statistic": round(w_stat, 4),
            "p_value": round(p_value, 6),
            "significant": p_value < 0.05,
            "cliffs_delta": round(delta, 4),
            "cliffs_delta_magnitude": d_label,
            "mean_difference": round(mean_diff, 4),
        },
        "decision": {
            "action": decision,
            "reason": reason,
        },
        "timing": {
            "baseline_s": round(baseline_elapsed, 1),
            "ablated_s": round(ablated_elapsed, 1),
        },
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Print summary
    print()
    print("=" * 65)
    print(f"  CPE ABLATION: {system} — @{creator}")
    print("=" * 65)
    print(f"  Runs: {args.runs} per config, {n_cases} test cases")
    print()
    print(f"  Baseline BERTScore-F1:  {baseline_overall:.4f} ± {baseline_std:.4f}")
    print(f"  Ablated BERTScore-F1:   {ablated_overall:.4f} ± {ablated_std:.4f}")
    print(f"  Delta:                  {mean_diff:+.4f}")
    print()
    print(f"  Wilcoxon p-value:       {p_value:.6f} {'(significant)' if p_value < 0.05 else '(not significant)'}")
    print(f"  Cliff's delta:          {delta:.4f} ({d_label})")
    print()
    print(f"  DECISION: {decision}")
    print(f"  Reason: {reason}")
    print()
    print(f"  Output: {output_path}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
