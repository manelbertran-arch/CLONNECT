"""
CPE Level 3 (v2): Shadow Mode Comparison — Lexical Metrics + Shadow Audit

Computes lexical overlap metrics between bot and creator responses:
  - BLEU-4 (n-gram precision with brevity penalty)
  - ROUGE-L (longest common subsequence)
  - chrF++ (character n-gram F1)
  - Vocabulary overlap (Jaccard)
  - Length ratio

Also audits shadow mode data from DB to quantify available preference pairs.

Scientific basis:
  - BLEU: Papineni et al. (ACL 2002) — standard MT metric, ρ=0.25 with humans
  - ROUGE-L: Lin (ACL 2004) — ρ=0.35 with humans for summarization
  - chrF++: Popović (WMT 2015) — ρ=0.52 for morphologically rich languages
  - All deterministic, $0, complementary to BERTScore

Usage:
    railway run python3.11 tests/cpe_shadow_comparison.py --creator iris_bertran
    railway run python3.11 tests/cpe_shadow_comparison.py --creator iris_bertran --audit-only
    railway run python3.11 tests/cpe_shadow_comparison.py --creator iris_bertran --responses FILE.json

Cost: $0 (pure computation)
"""

import argparse
import asyncio
import collections
import json
import logging
import math
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cpe_shadow")
logger.setLevel(logging.INFO)


# =========================================================================
# LEXICAL METRICS
# =========================================================================

def _tokenize(text: str) -> List[str]:
    """Simple whitespace + punctuation tokenizer for ES/CA."""
    return re.findall(r"\b\w+\b", text.lower())


def compute_bleu4(candidate: str, reference: str) -> float:
    """BLEU-4 score (Papineni et al., ACL 2002).

    Modified n-gram precision with brevity penalty.
    Uses smoothing method 1 (add 1 to numerator for zero counts).
    """
    cand_tokens = _tokenize(candidate)
    ref_tokens = _tokenize(reference)

    if not cand_tokens or not ref_tokens:
        return 0.0

    # Brevity penalty
    bp = 1.0 if len(cand_tokens) >= len(ref_tokens) else math.exp(1 - len(ref_tokens) / len(cand_tokens))

    # N-gram precisions (1-4)
    precisions = []
    for n in range(1, 5):
        cand_ngrams = collections.Counter(
            tuple(cand_tokens[i:i + n]) for i in range(len(cand_tokens) - n + 1)
        )
        ref_ngrams = collections.Counter(
            tuple(ref_tokens[i:i + n]) for i in range(len(ref_tokens) - n + 1)
        )

        clipped = sum(min(count, ref_ngrams[ng]) for ng, count in cand_ngrams.items())
        total = max(1, sum(cand_ngrams.values()))

        # Smoothing: add 1 for zero counts (method 1)
        if clipped == 0:
            clipped = 1
            total = total + 1

        precisions.append(clipped / total)

    # Geometric mean of precisions
    log_avg = sum(math.log(p) for p in precisions) / 4
    return round(bp * math.exp(log_avg), 4)


def compute_rouge_l(candidate: str, reference: str) -> float:
    """ROUGE-L score (Lin, ACL 2004).

    F1 based on longest common subsequence.
    """
    cand_tokens = _tokenize(candidate)
    ref_tokens = _tokenize(reference)

    if not cand_tokens or not ref_tokens:
        return 0.0

    # LCS via dynamic programming
    m, n = len(ref_tokens), len(cand_tokens)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_tokens[i - 1] == cand_tokens[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    lcs_len = dp[m][n]
    precision = lcs_len / n if n > 0 else 0
    recall = lcs_len / m if m > 0 else 0

    if precision + recall == 0:
        return 0.0
    f1 = 2 * precision * recall / (precision + recall)
    return round(f1, 4)


def compute_chrf(candidate: str, reference: str, n: int = 6) -> float:
    """chrF++ score (Popović, WMT 2015).

    Character n-gram F1 (good for morphologically rich languages like ES/CA).
    """
    if not candidate or not reference:
        return 0.0

    cand = candidate.lower()
    ref = reference.lower()

    total_precision = 0
    total_recall = 0
    count = 0

    for order in range(1, n + 1):
        cand_ngrams = collections.Counter(cand[i:i + order] for i in range(len(cand) - order + 1))
        ref_ngrams = collections.Counter(ref[i:i + order] for i in range(len(ref) - order + 1))

        matched = sum(min(cand_ngrams[ng], ref_ngrams[ng]) for ng in cand_ngrams if ng in ref_ngrams)
        cand_total = max(1, sum(cand_ngrams.values()))
        ref_total = max(1, sum(ref_ngrams.values()))

        total_precision += matched / cand_total
        total_recall += matched / ref_total
        count += 1

    avg_p = total_precision / count
    avg_r = total_recall / count

    if avg_p + avg_r == 0:
        return 0.0
    f1 = 2 * avg_p * avg_r / (avg_p + avg_r)
    return round(f1, 4)


def compute_vocab_overlap(candidate: str, reference: str) -> float:
    """Jaccard similarity of word sets."""
    cand_words = set(_tokenize(candidate))
    ref_words = set(_tokenize(reference))
    if not cand_words or not ref_words:
        return 0.0
    intersection = cand_words & ref_words
    union = cand_words | ref_words
    return round(len(intersection) / len(union), 4) if union else 0.0


def compute_length_ratio(candidate: str, reference: str) -> float:
    """Length ratio (candidate / reference)."""
    if not reference:
        return 0.0
    return round(len(candidate) / max(1, len(reference)), 4)


def compute_all_lexical(candidate: str, reference: str) -> Dict:
    """Compute all lexical metrics for a single pair."""
    return {
        "bleu4": compute_bleu4(candidate, reference),
        "rouge_l": compute_rouge_l(candidate, reference),
        "chrf": compute_chrf(candidate, reference),
        "vocab_overlap": compute_vocab_overlap(candidate, reference),
        "length_ratio": compute_length_ratio(candidate, reference),
    }


# =========================================================================
# SHADOW MODE AUDIT
# =========================================================================

def audit_shadow_data(creator_name: str) -> Dict:
    """Audit shadow/copilot data in DB for available preference pairs.

    Queries messages table for copilot_action records and preference_pairs table.
    """
    try:
        import psycopg2
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
    except Exception as e:
        logger.warning(f"Cannot connect to DB: {e}")
        return {"error": str(e), "available": False}

    try:
        # Get creator UUID
        cur.execute("SELECT id FROM creators WHERE name = %s", (creator_name,))
        row = cur.fetchone()
        if not row:
            return {"error": f"Creator '{creator_name}' not found", "available": False}
        creator_uuid = row[0]

        # 1. Count shadow pairs by action type
        cur.execute("""
            SELECT
                copilot_action,
                COUNT(*) as count,
                ROUND(AVG(confidence_score)::numeric, 3) as avg_confidence,
                MIN(created_at) as earliest,
                MAX(created_at) as latest
            FROM messages m
            JOIN leads l ON m.lead_id = l.id
            WHERE l.creator_id = %s
              AND m.role = 'assistant'
              AND m.suggested_response IS NOT NULL
              AND m.copilot_action IS NOT NULL
            GROUP BY copilot_action
            ORDER BY count DESC
        """, (str(creator_uuid),))
        shadow_actions = []
        for action_row in cur.fetchall():
            shadow_actions.append({
                "action": action_row[0],
                "count": action_row[1],
                "avg_confidence": float(action_row[2]) if action_row[2] else None,
                "earliest": action_row[3].isoformat() if action_row[3] else None,
                "latest": action_row[4].isoformat() if action_row[4] else None,
            })

        # 2. Count preference pairs
        cur.execute("""
            SELECT
                action_type,
                COUNT(*) as count,
                SUM(CASE WHEN is_active THEN 1 ELSE 0 END) as active_count
            FROM preference_pairs
            WHERE creator_id = %s
            GROUP BY action_type
            ORDER BY count DESC
        """, (str(creator_uuid),))
        pref_pairs = []
        for pp_row in cur.fetchall():
            pref_pairs.append({
                "action_type": pp_row[0],
                "total": pp_row[1],
                "active": pp_row[2],
            })

        # 3. Usable DPO pairs (both chosen and rejected non-empty)
        cur.execute("""
            SELECT COUNT(*)
            FROM preference_pairs
            WHERE creator_id = %s
              AND is_active = true
              AND chosen IS NOT NULL AND chosen != ''
              AND rejected IS NOT NULL AND rejected != ''
        """, (str(creator_uuid),))
        dpo_ready = cur.fetchone()[0]

        # 4. Sample shadow pairs for quality check
        cur.execute("""
            SELECT
                m.suggested_response,
                m.content,
                m.copilot_action,
                m.confidence_score
            FROM messages m
            JOIN leads l ON m.lead_id = l.id
            WHERE l.creator_id = %s
              AND m.role = 'assistant'
              AND m.suggested_response IS NOT NULL
              AND m.copilot_action IN ('edited', 'resolved_externally')
              AND m.content IS NOT NULL
              AND m.content != m.suggested_response
            ORDER BY m.created_at DESC
            LIMIT 10
        """, (str(creator_uuid),))
        samples = []
        for sample_row in cur.fetchall():
            samples.append({
                "bot_suggestion": sample_row[0][:200] if sample_row[0] else "",
                "creator_response": sample_row[1][:200] if sample_row[1] else "",
                "action": sample_row[2],
                "confidence": float(sample_row[3]) if sample_row[3] else None,
            })

        conn.close()

        total_shadow = sum(a["count"] for a in shadow_actions)
        total_pref = sum(p["total"] for p in pref_pairs)

        return {
            "available": True,
            "creator": creator_name,
            "shadow_messages": {
                "total": total_shadow,
                "by_action": shadow_actions,
            },
            "preference_pairs": {
                "total": total_pref,
                "dpo_ready": dpo_ready,
                "by_type": pref_pairs,
            },
            "dpo_readiness": {
                "pairs_available": dpo_ready,
                "sufficient_for_dpo": dpo_ready >= 200,
                "recommendation": (
                    f"Ready for DPO ({dpo_ready} pairs)" if dpo_ready >= 200
                    else f"Need more data ({dpo_ready}/200 minimum pairs)"
                ),
            },
            "samples": samples,
        }

    except Exception as e:
        conn.close()
        return {"error": str(e), "available": False}


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
            "message_id": f"shadow_{conv.get('id', i)}",
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
    parser = argparse.ArgumentParser(description="CPE Level 3 (v2): Shadow Mode Comparison")
    parser.add_argument("--creator", required=True, help="Creator slug")
    parser.add_argument("--test-set", default=None, help="Custom test set path")
    parser.add_argument("--responses", default=None, help="Reuse responses from file")
    parser.add_argument("--skip-pipeline", action="store_true", help="Reuse latest responses")
    parser.add_argument("--audit-only", action="store_true", help="Only audit shadow data in DB")
    parser.add_argument("--output", default=None, help="Custom output path")
    args = parser.parse_args()

    creator = args.creator
    cpe_dir = REPO_ROOT / "tests" / "cpe_data" / creator / "results"
    cpe_dir.mkdir(parents=True, exist_ok=True)

    # Shadow audit (always run)
    logger.info("Auditing shadow mode data...")
    shadow_audit = audit_shadow_data(creator)

    if args.audit_only:
        print()
        print("=" * 65)
        print(f"  SHADOW MODE AUDIT: @{creator}")
        print("=" * 65)

        if shadow_audit.get("available"):
            sm = shadow_audit["shadow_messages"]
            pp = shadow_audit["preference_pairs"]
            dpo = shadow_audit["dpo_readiness"]

            print(f"\n  Shadow messages total: {sm['total']}")
            for a in sm["by_action"]:
                print(f"    {a['action']:>25s}: {a['count']:>5d}  (avg conf: {a['avg_confidence'] or '?'})")

            print(f"\n  Preference pairs total: {pp['total']}")
            print(f"  DPO-ready pairs: {pp['dpo_ready']}")
            for p in pp["by_type"]:
                print(f"    {p['action_type']:>25s}: {p['total']:>5d} ({p['active']} active)")

            print(f"\n  DPO readiness: {dpo['recommendation']}")

            if shadow_audit.get("samples"):
                print(f"\n  Sample divergence pairs:")
                for s in shadow_audit["samples"][:3]:
                    print(f"    Bot: '{s['bot_suggestion'][:80]}...'")
                    print(f"    Iris: '{s['creator_response'][:80]}...'")
                    print(f"    Action: {s['action']}, Confidence: {s['confidence']}")
                    print()
        else:
            print(f"\n  Error: {shadow_audit.get('error', 'Unknown')}")

        print("=" * 65)

        # Save audit
        audit_path = cpe_dir / f"shadow_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(audit_path, "w") as f:
            json.dump(shadow_audit, f, indent=2, ensure_ascii=False, default=str)
        print(f"  Saved: {audit_path}")
        return

    # Load conversations
    if args.responses:
        with open(args.responses) as f:
            prev = json.load(f)
        conversations = prev if isinstance(prev, list) else prev.get("conversations", [])
        for c in conversations:
            if "input" in c and "test_input" not in c:
                c["test_input"] = c["input"]
            if "creator_real_response" in c and "ground_truth" not in c:
                c["ground_truth"] = c["creator_real_response"]
        logger.info(f"Loaded {len(conversations)} responses")
    elif args.skip_pipeline:
        existing = sorted(cpe_dir.glob("level1_*.json"), reverse=True)
        if not existing:
            logger.error("No existing results. Run Level 1 first.")
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

    # Compute lexical metrics for each pair
    logger.info(f"Computing lexical metrics for {len(conversations)} pairs...")
    per_case = []
    all_metrics = {k: [] for k in ["bleu4", "rouge_l", "chrf", "vocab_overlap", "length_ratio"]}

    for i, conv in enumerate(conversations):
        bot = conv.get("bot_response", "")
        gt = conv.get("ground_truth", "")

        if bot and gt:
            metrics = compute_all_lexical(bot, gt)
            for k, v in metrics.items():
                all_metrics[k].append(v)
        else:
            metrics = {"bleu4": 0, "rouge_l": 0, "chrf": 0, "vocab_overlap": 0, "length_ratio": 0}

        per_case.append({
            "id": conv.get("id", f"case_{i}"),
            "test_input": conv.get("test_input", ""),
            "ground_truth": gt,
            "bot_response": bot,
            "metrics": metrics,
        })

    # Aggregate
    aggregate = {}
    for k, vals in all_metrics.items():
        if vals:
            aggregate[k] = {
                "mean": round(statistics.mean(vals), 4),
                "median": round(statistics.median(vals), 4),
                "std": round(statistics.stdev(vals), 4) if len(vals) > 1 else 0,
                "min": round(min(vals), 4),
                "max": round(max(vals), 4),
            }
        else:
            aggregate[k] = {"mean": 0, "median": 0, "std": 0, "min": 0, "max": 0}

    # Normalized L3 score (per CPE v2 methodology)
    bleu_norm = min(1.0, aggregate["bleu4"]["mean"] / 0.30)
    rouge_norm = min(1.0, aggregate["rouge_l"]["mean"] / 0.50)
    chrf_norm = min(1.0, aggregate["chrf"]["mean"] / 0.60)
    l3_score = round((bleu_norm + rouge_norm + chrf_norm) / 3, 4)

    # Sort by composite worst
    per_case_sorted = sorted(
        per_case,
        key=lambda x: x["metrics"].get("rouge_l", 0) + x["metrics"].get("chrf", 0)
    )

    # Output
    timestamp = datetime.now(timezone.utc).isoformat()
    output_path = Path(args.output) if args.output else (
        cpe_dir / f"shadow_lexical_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )

    output = {
        "creator": creator,
        "timestamp": timestamp,
        "n_test_cases": len(conversations),
        "n_valid_pairs": sum(1 for v in all_metrics["bleu4"] if True),
        "aggregate": aggregate,
        "l3_normalized_score": l3_score,
        "shadow_audit": shadow_audit,
        "per_case": per_case_sorted,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)

    # Print summary
    print()
    print("=" * 65)
    print(f"  CPE LEVEL 3 (v2) — Shadow Lexical Metrics: @{creator}")
    print("=" * 65)
    print(f"  Valid pairs: {len(all_metrics['bleu4'])}/{len(conversations)}")
    print()
    print(f"  {'Metric':<20s} {'Mean':>8s} {'Median':>8s} {'Std':>8s} {'Target':>8s} {'Status':>8s}")
    print(f"  {'-'*60}")

    targets = {"bleu4": 0.10, "rouge_l": 0.25, "chrf": 0.30, "vocab_overlap": 0.15, "length_ratio": 1.0}
    for k in ["bleu4", "rouge_l", "chrf", "vocab_overlap", "length_ratio"]:
        a = aggregate[k]
        target = targets[k]
        if k == "length_ratio":
            ok = 0.7 <= a["mean"] <= 1.3
        else:
            ok = a["mean"] >= target
        status = "OK" if ok else "FLAG"
        print(f"  {k:<20s} {a['mean']:>8.4f} {a['median']:>8.4f} {a['std']:>8.4f} {target:>8.2f} {'  ' + status:>8s}")

    print(f"\n  L3 Normalized Score: {l3_score:.4f}")
    print()

    # Shadow audit summary
    if shadow_audit.get("available"):
        dpo = shadow_audit["dpo_readiness"]
        print(f"  Shadow data: {shadow_audit['shadow_messages']['total']} messages, "
              f"{dpo['pairs_available']} DPO-ready pairs")
        print(f"  DPO: {dpo['recommendation']}")
    else:
        print(f"  Shadow audit: {shadow_audit.get('error', 'unavailable')}")

    print()
    print(f"  Output: {output_path}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
