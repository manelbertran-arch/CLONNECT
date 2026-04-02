"""
CPE Full-Sweep Additive Ablation — Systematic System Evaluation

Protocol:
  1. Disable ALL ablatable systems → run naked baseline (N runs)
  2. Enable ONE system at a time → run (N runs)
  3. Compare each system vs naked using Wilcoxon + Cliff's delta
  4. Report decision table

Instruments (CPE v2):
  - L1: Quantitative text metrics (length, emoji, questions, vocab)
  - L2: BERTScore F1 with XLM-RoBERTa-large
  - L3: BLEU-4, ROUGE-L, chrF++, vocab overlap, length ratio

Usage:
    railway run python3.11 tests/cpe_full_sweep.py --creator iris_bertran --runs 3
    railway run python3.11 tests/cpe_full_sweep.py --creator iris_bertran --runs 3 --phase 3
    railway run python3.11 tests/cpe_full_sweep.py --creator iris_bertran --evaluate-only

Cost: $0 per evaluation (Qwen3-14B via DeepInfra for generation, local metrics)
"""

import argparse
import asyncio
import json
import logging
import math
import os
import re
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cpe_sweep")
logger.setLevel(logging.INFO)


# =========================================================================
# SYSTEM DEFINITIONS — env var mapping + phases
# =========================================================================

# Each system: (env_var, value_to_disable, value_to_enable, default_prod)
SYSTEMS = {
    # Phase 3: Prompt Assembly
    "compressed_doc_d":  ("USE_COMPRESSED_DOC_D",        "false", "true",  "true"),
    "few_shot":          ("ENABLE_FEW_SHOT",             "false", "true",  "true"),   # needs flag guard
    "echo":              ("ENABLE_STYLE_ANALYZER",       "false", "true",  "true"),
    "style_normalizer":  ("ENABLE_STYLE_NORMALIZER",     "false", "true",  "true"),
    "length_hints":      ("ENABLE_LENGTH_HINTS",         "false", "true",  "true"),   # needs flag guard
    "question_hints":    ("ENABLE_QUESTION_HINTS",       "false", "true",  "true"),   # needs flag guard
    "sbs":               ("ENABLE_SCORE_BEFORE_SPEAK",   "false", "true",  "true"),

    # Phase 2: Context Loading
    "memory_engine":     ("ENABLE_MEMORY_ENGINE",        "false", "true",  "true"),
    "episodic_memory":   ("ENABLE_EPISODIC_MEMORY",      "false", "true",  "true"),
    "rag":               ("ENABLE_RAG",                  "false", "true",  "true"),
    "reranker":          ("ENABLE_RERANKING",            "false", "true",  "true"),
    "pool_matching":     ("POOL_CONFIDENCE",             "999",   "0.8",   "0.8"),

    # Phase 5: Post-processing
    "guardrails":        ("ENABLE_GUARDRAILS",           "false", "true",  "true"),
    "output_validation": ("ENABLE_OUTPUT_VALIDATION",    "false", "true",  "false"),
    "response_fixes":    ("ENABLE_RESPONSE_FIXES",       "false", "true",  "true"),
}

PHASE_MAP = {
    3: ["compressed_doc_d", "few_shot", "echo", "style_normalizer",
        "length_hints", "question_hints", "sbs"],
    2: ["memory_engine", "episodic_memory", "rag", "reranker", "pool_matching"],
    5: ["guardrails", "output_validation", "response_fixes"],
}

# Systems that lack env var guards in codebase (will be skipped with note)
# few_shot: ENABLE_FEW_SHOT added in context.py
# length_hints: ENABLE_LENGTH_HINTS added in generation.py
# question_hints: ENABLE_QUESTION_HINTS added in generation.py
NEEDS_FLAG: set = set()  # All flags now exist


# =========================================================================
# STATISTICAL TESTS (from cpe_ablation_runner.py)
# =========================================================================

def wilcoxon_signed_rank(x: List[float], y: List[float]) -> Tuple[float, float]:
    """Wilcoxon signed-rank test (non-parametric paired test)."""
    try:
        from scipy.stats import wilcoxon
        stat, p = wilcoxon(x, y, alternative="two-sided")
        return float(stat), float(p)
    except ImportError:
        diffs = [a - b for a, b in zip(x, y) if a != b]
        if not diffs:
            return 0.0, 1.0
        abs_diffs = [(abs(d), i, d) for i, d in enumerate(diffs)]
        abs_diffs.sort(key=lambda t: t[0])
        ranks = [0.0] * len(abs_diffs)
        i = 0
        while i < len(abs_diffs):
            j = i
            while j < len(abs_diffs) and abs_diffs[j][0] == abs_diffs[i][0]:
                j += 1
            avg_rank = (i + j + 1) / 2
            for k in range(i, j):
                ranks[k] = avg_rank
            i = j
        w_plus = sum(ranks[k] for k in range(len(diffs)) if abs_diffs[k][2] > 0)
        w_minus = sum(ranks[k] for k in range(len(diffs)) if abs_diffs[k][2] < 0)
        w = min(w_plus, w_minus)
        n = len(diffs)
        if n > 10:
            mean_w = n * (n + 1) / 4
            std_w = math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
            z = (w - mean_w) / std_w if std_w > 0 else 0
            p = 2 * (1 - _norm_cdf(abs(z)))
        else:
            p = 0.10
        return float(w), float(p)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def cliffs_delta(x: List[float], y: List[float]) -> float:
    """Cliff's delta effect size."""
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


def cliff_magnitude(d: float) -> str:
    ad = abs(d)
    if ad < 0.147:
        return "negligible"
    elif ad < 0.330:
        return "small"
    elif ad < 0.474:
        return "medium"
    return "large"


# =========================================================================
# LEXICAL METRICS (from cpe_shadow_comparison.py)
# =========================================================================

def _tokenize(text: str) -> List[str]:
    return re.findall(r"\b\w+\b", text.lower())


def compute_chrf(candidate: str, reference: str, n: int = 6, beta: float = 2.0) -> float:
    """chrF++ score."""
    if not candidate or not reference:
        return 0.0

    def _char_ngrams(text, order):
        ngrams = Counter()
        for w in text.split():
            w = " " + w + " "
            for i in range(len(w) - order + 1):
                ngrams[w[i:i+order]] += 1
        return ngrams

    precisions, recalls = [], []
    for order in range(1, n + 1):
        cand_ng = _char_ngrams(candidate, order)
        ref_ng = _char_ngrams(reference, order)
        common = sum((cand_ng & ref_ng).values())
        p = common / max(sum(cand_ng.values()), 1)
        r = common / max(sum(ref_ng.values()), 1)
        precisions.append(p)
        recalls.append(r)

    avg_p = statistics.mean(precisions) if precisions else 0
    avg_r = statistics.mean(recalls) if recalls else 0
    if avg_p + avg_r == 0:
        return 0.0
    return (1 + beta**2) * avg_p * avg_r / (beta**2 * avg_p + avg_r)


def compute_rouge_l(candidate: str, reference: str) -> float:
    """ROUGE-L F1."""
    cand_tokens = _tokenize(candidate)
    ref_tokens = _tokenize(reference)
    if not cand_tokens or not ref_tokens:
        return 0.0
    m, n = len(ref_tokens), len(cand_tokens)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_tokens[i-1] == cand_tokens[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    lcs = dp[m][n]
    if lcs == 0:
        return 0.0
    p = lcs / n
    r = lcs / m
    return 2 * p * r / (p + r)


def compute_vocab_overlap(candidate: str, reference: str) -> float:
    """Jaccard vocabulary overlap."""
    cand_words = set(_tokenize(candidate))
    ref_words = set(_tokenize(reference))
    if not cand_words or not ref_words:
        return 0.0
    return len(cand_words & ref_words) / len(cand_words | ref_words)


# =========================================================================
# EMOJI REGEX
# =========================================================================

_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\u2600-\u27BF\U0001F900-\U0001F9FF]"
    r"[\U0001F3FB-\U0001F3FF\uFE0F]?"
)


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


async def generate_responses(
    creator_id: str,
    conversations: List[Dict],
    run_id: int,
    label: str,
) -> List[Dict]:
    """Run pipeline once on all test cases, return results with bot_response."""
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
            "message_id": f"sweep_{label}_r{run_id}_{conv.get('id', i)}",
        }

        t0 = time.monotonic()
        try:
            dm_response = await agent.process_dm(
                message=test_input, sender_id=sender_id, metadata=metadata
            )
            bot_response = dm_response.content if dm_response else ""
        except Exception as e:
            logger.error(f"[{label}][run{run_id}][{conv.get('id', i)}] Error: {e}")
            bot_response = ""

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        results.append({
            "id": conv.get("id", f"case_{i}"),
            "test_input": test_input,
            "ground_truth": conv.get("ground_truth", ""),
            "bot_response": bot_response,
            "elapsed_ms": elapsed_ms,
        })

        # Rate limit: 1-2s between calls
        if i < len(conversations):
            await asyncio.sleep(1.5)

    return results


# =========================================================================
# EVALUATION — L1 + L2 + L3 metrics per response
# =========================================================================

def evaluate_l1(bot: str, gt: str) -> Dict[str, float]:
    """L1: Quantitative text metrics."""
    bot_len = len(bot)
    gt_len = len(gt) if gt else 1
    bot_words = len(re.findall(r"\b\w+\b", bot))
    gt_words = len(re.findall(r"\b\w+\b", gt)) if gt else 1
    bot_emoji = len(_EMOJI_RE.findall(bot))
    gt_emoji = len(_EMOJI_RE.findall(gt)) if gt else 0
    bot_q = bot.count("?")
    gt_q = gt.count("?") if gt else 0

    return {
        "length_ratio": bot_len / max(gt_len, 1),
        "word_ratio": bot_words / max(gt_words, 1),
        "emoji_diff": bot_emoji - gt_emoji,
        "question_diff": bot_q - gt_q,
    }


def evaluate_l2_batch(bots: List[str], gts: List[str]) -> List[float]:
    """L2: BERTScore F1 for a batch."""
    try:
        from bert_score import score as bert_score
    except ImportError:
        logger.error("bert-score not installed. pip install bert-score")
        return [0.0] * len(bots)

    safe_bots = [b if b else "." for b in bots]
    safe_gts = [g if g else "." for g in gts]

    _, _, F1 = bert_score(
        cands=safe_bots,
        refs=safe_gts,
        model_type="xlm-roberta-large",
        lang="es",
        batch_size=16,
        verbose=False,
        rescale_with_baseline=True,
    )

    f1s = [F1[i].item() for i in range(len(bots))]
    for i in range(len(bots)):
        if not bots[i] or not gts[i]:
            f1s[i] = 0.0
    return f1s


def evaluate_l3(bot: str, gt: str) -> Dict[str, float]:
    """L3: Lexical metrics."""
    return {
        "chrf": compute_chrf(bot, gt),
        "rouge_l": compute_rouge_l(bot, gt),
        "vocab_overlap": compute_vocab_overlap(bot, gt),
    }


# =========================================================================
# ENV VAR MANAGEMENT
# =========================================================================

def set_all_off() -> Dict[str, Optional[str]]:
    """Disable all ablatable systems. Returns original values for restore."""
    originals = {}
    for sys_name, (env_var, off_val, on_val, _) in SYSTEMS.items():
        originals[env_var] = os.environ.get(env_var)
        os.environ[env_var] = off_val
    return originals


def set_one_on(system_name: str):
    """Enable a single system (assumes all are already OFF)."""
    env_var, _, on_val, _ = SYSTEMS[system_name]
    os.environ[env_var] = on_val


def restore_env(originals: Dict[str, Optional[str]]):
    """Restore original env vars."""
    for env_var, val in originals.items():
        if val is not None:
            os.environ[env_var] = val
        elif env_var in os.environ:
            del os.environ[env_var]


# =========================================================================
# MAIN
# =========================================================================

async def main():
    parser = argparse.ArgumentParser(description="CPE Full-Sweep Additive Ablation")
    parser.add_argument("--creator", required=True, help="Creator slug")
    parser.add_argument("--runs", type=int, default=3, help="Runs per config (default: 3)")
    parser.add_argument("--phase", type=int, default=None, help="Only run specific phase (2, 3, or 5)")
    parser.add_argument("--system", default=None, help="Only run specific system")
    parser.add_argument("--evaluate-only", action="store_true", help="Evaluate existing responses")
    parser.add_argument("--skip-naked", action="store_true", help="Skip naked baseline (reuse existing)")
    parser.add_argument("--test-set", default=None, help="Custom test set path")
    args = parser.parse_args()

    creator = args.creator
    sweep_dir = REPO_ROOT / "tests" / "cpe_data" / creator / "sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)

    # Load test set
    test_path = Path(args.test_set) if args.test_set else (
        REPO_ROOT / "tests" / "cpe_data" / creator / "test_set.json"
    )
    with open(test_path) as f:
        data = json.load(f)
    conversations = data if isinstance(data, list) else data.get("conversations", data.get("test_cases", []))
    n_cases = len(conversations)
    logger.info(f"Loaded {n_cases} test cases from {test_path}")

    # Determine which systems to ablate
    if args.system:
        systems_to_test = [args.system]
    elif args.phase:
        systems_to_test = PHASE_MAP.get(args.phase, [])
    else:
        systems_to_test = []
        for phase in [3, 5, 2]:
            systems_to_test.extend(PHASE_MAP[phase])

    # Check which systems have flags
    skipped = []
    active_systems = []
    for s in systems_to_test:
        if s in NEEDS_FLAG:
            skipped.append(s)
            logger.warning(f"SKIP {s}: needs ENABLE flag in codebase")
        else:
            active_systems.append(s)

    logger.info(f"Systems to test: {active_systems}")
    if skipped:
        logger.info(f"Skipped (needs flag): {skipped}")

    n_runs = args.runs

    # =====================================================================
    # PHASE A: Generate responses
    # =====================================================================

    if not args.evaluate_only:
        originals = set_all_off()

        try:
            # A1: Naked baseline
            naked_file = sweep_dir / "naked_responses.json"
            if args.skip_naked and naked_file.exists():
                logger.info("Reusing existing naked baseline responses")
            else:
                logger.info(f"=== NAKED BASELINE: {n_runs} runs x {n_cases} cases ===")
                naked_runs = []
                for run_id in range(1, n_runs + 1):
                    logger.info(f"[naked] Run {run_id}/{n_runs}...")
                    results = await generate_responses(creator, conversations, run_id, "naked")
                    naked_runs.append(results)
                    logger.info(f"[naked] Run {run_id} done: {len(results)} responses")

                with open(naked_file, "w") as f:
                    json.dump({
                        "config": "naked",
                        "n_runs": n_runs,
                        "runs": naked_runs,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }, f, indent=2, ensure_ascii=False)
                logger.info(f"Saved naked responses: {naked_file}")

            # A2: Per-system responses
            for sys_name in active_systems:
                sys_file = sweep_dir / f"{sys_name}_responses.json"
                if sys_file.exists():
                    logger.info(f"[{sys_name}] Responses already exist, skipping generation")
                    continue

                # Reset all OFF, then enable just this system
                set_all_off()
                set_one_on(sys_name)
                env_var = SYSTEMS[sys_name][0]
                logger.info(f"=== {sys_name.upper()} ({env_var}={os.environ[env_var]}) ===")

                sys_runs = []
                for run_id in range(1, n_runs + 1):
                    logger.info(f"[{sys_name}] Run {run_id}/{n_runs}...")
                    results = await generate_responses(creator, conversations, run_id, sys_name)
                    sys_runs.append(results)
                    logger.info(f"[{sys_name}] Run {run_id} done")

                with open(sys_file, "w") as f:
                    json.dump({
                        "config": sys_name,
                        "env_var": env_var,
                        "n_runs": n_runs,
                        "runs": sys_runs,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }, f, indent=2, ensure_ascii=False)
                logger.info(f"Saved {sys_name} responses: {sys_file}")

        finally:
            restore_env(originals)

    # =====================================================================
    # PHASE B: Evaluate all responses
    # =====================================================================

    logger.info("=== EVALUATION PHASE ===")

    # Load naked baseline
    naked_file = sweep_dir / "naked_responses.json"
    if not naked_file.exists():
        logger.error("No naked baseline found. Run generation first.")
        sys.exit(1)
    with open(naked_file) as f:
        naked_data = json.load(f)
    naked_runs = naked_data["runs"]

    # Compute naked metrics
    logger.info("Computing naked baseline metrics...")
    naked_l2_per_run = []
    naked_l3_per_run = []
    for run_results in naked_runs:
        bots = [r["bot_response"] for r in run_results]
        gts = [r["ground_truth"] for r in run_results]

        l2_f1s = evaluate_l2_batch(bots, gts)
        naked_l2_per_run.append(l2_f1s)

        l3_chrfs = [evaluate_l3(b, g)["chrf"] for b, g in zip(bots, gts)]
        naked_l3_per_run.append(l3_chrfs)

    # Per-case means across runs (naked)
    naked_l2_means = []
    naked_l3_means = []
    for case_idx in range(n_cases):
        l2_vals = [naked_l2_per_run[r][case_idx] for r in range(len(naked_runs))]
        l3_vals = [naked_l3_per_run[r][case_idx] for r in range(len(naked_runs))]
        naked_l2_means.append(statistics.mean(l2_vals))
        naked_l3_means.append(statistics.mean(l3_vals))

    naked_l2_overall = statistics.mean(naked_l2_means)
    naked_l3_overall = statistics.mean(naked_l3_means)
    logger.info(f"Naked baseline: BERTScore={naked_l2_overall:.4f}, chrF={naked_l3_overall:.4f}")

    # Evaluate each system
    results_table = []

    for sys_name in active_systems:
        sys_file = sweep_dir / f"{sys_name}_responses.json"
        if not sys_file.exists():
            logger.warning(f"No responses for {sys_name}, skipping evaluation")
            results_table.append({
                "system": sys_name,
                "status": "NO DATA",
            })
            continue

        with open(sys_file) as f:
            sys_data = json.load(f)
        sys_runs = sys_data["runs"]

        logger.info(f"Evaluating {sys_name}...")

        sys_l2_per_run = []
        sys_l3_per_run = []
        for run_results in sys_runs:
            bots = [r["bot_response"] for r in run_results]
            gts = [r["ground_truth"] for r in run_results]

            l2_f1s = evaluate_l2_batch(bots, gts)
            sys_l2_per_run.append(l2_f1s)

            l3_chrfs = [evaluate_l3(b, g)["chrf"] for b, g in zip(bots, gts)]
            sys_l3_per_run.append(l3_chrfs)

        # Per-case means
        sys_l2_means = []
        sys_l3_means = []
        for case_idx in range(n_cases):
            l2_vals = [sys_l2_per_run[r][case_idx] for r in range(len(sys_runs))]
            l3_vals = [sys_l3_per_run[r][case_idx] for r in range(len(sys_runs))]
            sys_l2_means.append(statistics.mean(l2_vals))
            sys_l3_means.append(statistics.mean(l3_vals))

        sys_l2_overall = statistics.mean(sys_l2_means)
        sys_l3_overall = statistics.mean(sys_l3_means)

        # Statistical tests: system vs naked
        # Positive delta = system IMPROVES over naked
        l2_delta = sys_l2_overall - naked_l2_overall
        l3_delta = sys_l3_overall - naked_l3_overall

        w_l2, p_l2 = wilcoxon_signed_rank(sys_l2_means, naked_l2_means)
        d_l2 = cliffs_delta(sys_l2_means, naked_l2_means)

        w_l3, p_l3 = wilcoxon_signed_rank(sys_l3_means, naked_l3_means)
        d_l3 = cliffs_delta(sys_l3_means, naked_l3_means)

        # Decision: based on BERTScore (primary) + chrF (secondary)
        if p_l2 < 0.05 and abs(d_l2) >= 0.147:
            if d_l2 > 0:
                decision = "KEEP"
            else:
                decision = "HURTS"
        elif p_l2 >= 0.05:
            decision = "NO EFFECT"
        else:
            decision = "INVESTIGATE"

        results_table.append({
            "system": sys_name,
            "env_var": SYSTEMS[sys_name][0],
            "status": "TESTED",
            "l2_bertscore": round(sys_l2_overall, 4),
            "l2_delta": round(l2_delta, 4),
            "l2_p": round(p_l2, 6),
            "l2_cliff": round(d_l2, 4),
            "l2_cliff_mag": cliff_magnitude(d_l2),
            "l3_chrf": round(sys_l3_overall, 4),
            "l3_delta": round(l3_delta, 4),
            "l3_p": round(p_l3, 6),
            "l3_cliff": round(d_l3, 4),
            "decision": decision,
        })

        logger.info(
            f"  {sys_name}: BERTScore={sys_l2_overall:.4f} (Δ{l2_delta:+.4f}, p={p_l2:.4f}), "
            f"chrF={sys_l3_overall:.4f} (Δ{l3_delta:+.4f}), decision={decision}"
        )

    # Add skipped systems
    for s in skipped:
        results_table.append({
            "system": s,
            "env_var": SYSTEMS[s][0],
            "status": "SKIP (needs flag)",
            "decision": "NEEDS FLAG",
        })

    # =====================================================================
    # PHASE C: Report
    # =====================================================================

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "creator": creator,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "protocol": "additive_ablation",
        "n_runs": n_runs,
        "n_cases": n_cases,
        "naked_baseline": {
            "bertscore_f1": round(naked_l2_overall, 4),
            "chrf": round(naked_l3_overall, 4),
        },
        "systems": results_table,
    }

    report_path = sweep_dir / f"sweep_report_{timestamp}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Print summary table
    print()
    print("=" * 95)
    print(f"  CPE FULL-SWEEP ABLATION — @{creator} — {n_runs} runs × {n_cases} cases")
    print("=" * 95)
    print(f"  Naked baseline: BERTScore={naked_l2_overall:.4f}, chrF={naked_l3_overall:.4f}")
    print()
    print(f"  {'System':<20} {'BERTScore':>9} {'Δ':>7} {'p-val':>8} {'Cliff':>7} {'chrF':>7} {'Δ':>7} {'Decision':<12}")
    print(f"  {'-'*18:<20} {'-'*9:>9} {'-'*7:>7} {'-'*8:>8} {'-'*7:>7} {'-'*7:>7} {'-'*7:>7} {'-'*12:<12}")

    for row in results_table:
        if row["status"] == "TESTED":
            print(
                f"  {row['system']:<20} {row['l2_bertscore']:>9.4f} "
                f"{row['l2_delta']:>+7.4f} {row['l2_p']:>8.4f} "
                f"{row['l2_cliff']:>+7.3f} {row['l3_chrf']:>7.4f} "
                f"{row['l3_delta']:>+7.4f} {row['decision']:<12}"
            )
        elif row["status"] == "SKIP (needs flag)":
            print(f"  {row['system']:<20} {'---':>9} {'---':>7} {'---':>8} {'---':>7} {'---':>7} {'---':>7} {'NEEDS FLAG':<12}")
        else:
            print(f"  {row['system']:<20} {'---':>9} {'---':>7} {'---':>8} {'---':>7} {'---':>7} {'---':>7} {'NO DATA':<12}")

    print()
    print(f"  Report: {report_path}")
    print("=" * 95)


if __name__ == "__main__":
    asyncio.run(main())
