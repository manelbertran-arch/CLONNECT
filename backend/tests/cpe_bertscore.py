"""
CPE Level 2 (v2): BERTScore — Multilingual Semantic Similarity

Computes BERTScore between bot responses and creator real responses
using XLM-RoBERTa-large (cross-lingual, supports ES/CA natively).

Scientific basis:
  - Zhang et al. (ICLR 2020): BERTScore F1 correlates ρ=0.59-0.72 with humans
  - Cross-lingual embeddings work for ES/CA without language-specific tuning
  - Deterministic: same inputs → same outputs (no judge stochasticity)

Usage:
    railway run python3.11 tests/cpe_bertscore.py --creator iris_bertran
    railway run python3.11 tests/cpe_bertscore.py --creator iris_bertran --skip-pipeline
    python3.11 tests/cpe_bertscore.py --creator iris_bertran --responses tests/cpe_data/iris_bertran/results/level1_*.json

Cost: $0 (local model inference, ~2s for 50 test cases on M-series Mac)
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
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cpe_bertscore")
logger.setLevel(logging.INFO)

# BERTScore model — XLM-RoBERTa-large for multilingual (ES/CA/EN)
# Papers: Conneau et al. (ACL 2020), Zhang et al. (ICLR 2020)
DEFAULT_MODEL = "xlm-roberta-large"


# =========================================================================
# BERTSCORE COMPUTATION
# =========================================================================

def compute_bertscore_batch(
    candidates: List[str],
    references: List[str],
    model_type: str = DEFAULT_MODEL,
    batch_size: int = 16,
) -> Dict:
    """Compute BERTScore for a batch of (candidate, reference) pairs.

    Returns per-pair and aggregate P/R/F1 scores.
    """
    try:
        from bert_score import score as bert_score
    except ImportError:
        logger.error("bert-score not installed. Run: pip install bert-score")
        sys.exit(1)

    # Filter empty pairs
    valid_indices = []
    valid_cands = []
    valid_refs = []
    for i, (c, r) in enumerate(zip(candidates, references)):
        if c and r:
            valid_indices.append(i)
            valid_cands.append(c)
            valid_refs.append(r)

    if not valid_cands:
        return {
            "per_pair": [],
            "aggregate": {"precision": 0.0, "recall": 0.0, "f1": 0.0},
            "n_valid": 0,
            "n_total": len(candidates),
        }

    logger.info(f"Computing BERTScore for {len(valid_cands)} pairs with {model_type}...")
    t0 = time.monotonic()

    # rescale_with_baseline requires lang; disable it when using model_type directly
    P, R, F1 = bert_score(
        cands=valid_cands,
        refs=valid_refs,
        model_type=model_type,
        batch_size=batch_size,
        verbose=False,
        rescale_with_baseline=False,
    )

    elapsed = time.monotonic() - t0
    logger.info(f"BERTScore computed in {elapsed:.1f}s")

    # Build per-pair results (including empty pairs as score=0)
    per_pair = [{"precision": 0.0, "recall": 0.0, "f1": 0.0, "valid": False}] * len(candidates)
    for idx, vi in enumerate(valid_indices):
        per_pair[vi] = {
            "precision": round(P[idx].item(), 4),
            "recall": round(R[idx].item(), 4),
            "f1": round(F1[idx].item(), 4),
            "valid": True,
        }

    # Aggregate (only valid pairs)
    f1_vals = [F1[i].item() for i in range(len(valid_cands))]
    p_vals = [P[i].item() for i in range(len(valid_cands))]
    r_vals = [R[i].item() for i in range(len(valid_cands))]

    aggregate = {
        "precision": round(statistics.mean(p_vals), 4),
        "recall": round(statistics.mean(r_vals), 4),
        "f1": round(statistics.mean(f1_vals), 4),
        "f1_std": round(statistics.stdev(f1_vals), 4) if len(f1_vals) > 1 else 0.0,
        "f1_median": round(statistics.median(f1_vals), 4),
        "f1_min": round(min(f1_vals), 4),
        "f1_max": round(max(f1_vals), 4),
    }

    return {
        "per_pair": per_pair,
        "aggregate": aggregate,
        "n_valid": len(valid_cands),
        "n_total": len(candidates),
        "model": model_type,
        "elapsed_s": round(elapsed, 1),
    }


def bootstrap_ci(scores: List[float], n_bootstrap: int = 1000, ci: float = 0.95) -> Dict:
    """Bootstrap confidence interval for BERTScore F1.

    Used for significance testing in ablations.
    Returns mean, lower, upper bounds.
    """
    import random
    random.seed(42)  # Reproducible CI

    n = len(scores)
    if n < 2:
        return {"mean": scores[0] if scores else 0.0, "lower": 0.0, "upper": 0.0, "ci": ci}

    bootstrap_means = []
    for _ in range(n_bootstrap):
        sample = random.choices(scores, k=n)
        bootstrap_means.append(statistics.mean(sample))

    bootstrap_means.sort()
    alpha = (1 - ci) / 2
    lower_idx = int(alpha * n_bootstrap)
    upper_idx = int((1 - alpha) * n_bootstrap) - 1

    return {
        "mean": round(statistics.mean(scores), 4),
        "lower": round(bootstrap_means[lower_idx], 4),
        "upper": round(bootstrap_means[upper_idx], 4),
        "ci": ci,
        "n_bootstrap": n_bootstrap,
    }


# =========================================================================
# PIPELINE RUNNER (reuse pattern from level 1)
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


async def run_pipeline(creator_id: str, conversations: List[Dict]) -> List[Dict]:
    """Run production DM pipeline on test conversations."""
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
            "message_id": f"bert_{conv.get('id', i)}",
        }

        t0 = time.monotonic()
        try:
            dm_response = await agent.process_dm(
                message=test_input, sender_id=sender_id, metadata=metadata
            )
            bot_response = dm_response.content if dm_response else ""
        except Exception as e:
            logger.error(f"[{conv.get('id', i)}] Pipeline error: {e}")
            bot_response = ""

        results.append({
            **conv,
            "bot_response": bot_response,
            "elapsed_ms": int((time.monotonic() - t0) * 1000),
        })
        logger.info(f"[{i}/{len(conversations)}] '{bot_response[:40]}...'")

    return results


# =========================================================================
# MAIN
# =========================================================================

async def main():
    parser = argparse.ArgumentParser(description="CPE Level 2 (v2): BERTScore Multilingual")
    parser.add_argument("--creator", required=True, help="Creator slug (e.g., iris_bertran)")
    parser.add_argument("--test-set", default=None, help="Custom test set path")
    parser.add_argument("--responses", default=None, help="Reuse responses from existing file")
    parser.add_argument("--skip-pipeline", action="store_true", help="Reuse latest responses")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="BERTScore model")
    parser.add_argument("--output", default=None, help="Custom output path")
    args = parser.parse_args()

    creator = args.creator
    cpe_dir = REPO_ROOT / "tests" / "cpe_data" / creator / "results"
    cpe_dir.mkdir(parents=True, exist_ok=True)

    # Load test set / responses
    if args.responses:
        with open(args.responses) as f:
            prev = json.load(f)
        conversations = prev if isinstance(prev, list) else prev.get("conversations", [])
        # Normalize fields
        for c in conversations:
            if "input" in c and "test_input" not in c:
                c["test_input"] = c["input"]
            if "creator_real_response" in c and "ground_truth" not in c:
                c["ground_truth"] = c["creator_real_response"]
        logger.info(f"Loaded {len(conversations)} responses from {args.responses}")
    elif args.skip_pipeline:
        existing = sorted(cpe_dir.glob("level1_*.json"), reverse=True)
        if not existing:
            logger.error("No existing results. Run Level 1 first or use --responses.")
            sys.exit(1)
        with open(existing[0]) as f:
            prev = json.load(f)
        conversations = prev.get("conversations", [])
        logger.info(f"Reusing {len(conversations)} responses from {existing[0].name}")
    else:
        test_path = Path(args.test_set) if args.test_set else (
            REPO_ROOT / "tests" / "cpe_data" / creator / "test_set.json"
        )
        if not test_path.exists():
            test_path = REPO_ROOT / "tests" / "test_set_real_leads.json"
        with open(test_path) as f:
            data = json.load(f)
        conversations = data if isinstance(data, list) else data.get("conversations", data.get("test_cases", []))
        conversations = await run_pipeline(creator, conversations)

    # Extract candidate/reference pairs
    candidates = [c.get("bot_response", "") for c in conversations]
    references = [c.get("ground_truth", "") for c in conversations]

    # Compute BERTScore
    result = compute_bertscore_batch(candidates, references, model_type=args.model)

    # Bootstrap CI for F1
    valid_f1s = [p["f1"] for p in result["per_pair"] if p["valid"]]
    ci = bootstrap_ci(valid_f1s)

    # Per-case details
    per_case = []
    for i, conv in enumerate(conversations):
        per_case.append({
            "id": conv.get("id", f"case_{i}"),
            "test_input": conv.get("test_input", ""),
            "ground_truth": conv.get("ground_truth", ""),
            "bot_response": conv.get("bot_response", ""),
            "bertscore": result["per_pair"][i],
        })

    # Sort by F1 to show worst cases
    per_case_sorted = sorted(per_case, key=lambda x: x["bertscore"]["f1"])

    # Output
    timestamp = datetime.now(timezone.utc).isoformat()
    output_path = Path(args.output) if args.output else (
        cpe_dir / f"bertscore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    output = {
        "creator": creator,
        "timestamp": timestamp,
        "model": args.model,
        "n_test_cases": len(conversations),
        "n_valid_pairs": result["n_valid"],
        "aggregate": result["aggregate"],
        "bootstrap_ci_95": ci,
        "elapsed_s": result["elapsed_s"],
        "per_case": per_case_sorted,
        "worst_5": per_case_sorted[:5],
        "best_5": per_case_sorted[-5:],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Print summary
    agg = result["aggregate"]
    print()
    print("=" * 65)
    print(f"  CPE LEVEL 2 (v2) — BERTScore: @{creator}")
    print("=" * 65)
    print(f"  Model: {args.model}")
    print(f"  Valid pairs: {result['n_valid']}/{len(conversations)}")
    print(f"  Elapsed: {result['elapsed_s']}s")
    print()
    print(f"  BERTScore F1:  {agg['f1']:.4f}  (std={agg['f1_std']:.4f})")
    print(f"  BERTScore P:   {agg['precision']:.4f}")
    print(f"  BERTScore R:   {agg['recall']:.4f}")
    print(f"  95% CI:        [{ci['lower']:.4f}, {ci['upper']:.4f}]")
    print(f"  Range:         [{agg['f1_min']:.4f}, {agg['f1_max']:.4f}]")
    print()

    # Interpretation
    f1 = agg["f1"]
    if f1 >= 0.70:
        quality = "STRONG semantic match"
    elif f1 >= 0.55:
        quality = "ACCEPTABLE — correct intent, different phrasing"
    else:
        quality = "POOR — different meaning or missing content"
    print(f"  Assessment: {quality}")
    print()

    # Worst cases
    print("  Worst 5 cases (lowest BERTScore F1):")
    for case in per_case_sorted[:5]:
        bs = case["bertscore"]
        print(f"    [{case['id']}] F1={bs['f1']:.3f}")
        print(f"      Input: {case['test_input'][:60]}...")
        print(f"      GT:    {case['ground_truth'][:60]}...")
        print(f"      Bot:   {case['bot_response'][:60]}...")
        print()

    print(f"  Output: {output_path}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
