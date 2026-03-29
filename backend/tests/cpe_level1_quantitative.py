"""
CPE Level 1: Quantitative Style Comparison — Bot vs Creator

Compares measurable text properties of bot responses against a creator's
real response baseline. Zero LLM calls, zero cost, pure computation.

For each test case:
  1. Run the production DM pipeline to get a bot response
  2. Compute text metrics on both bot and creator responses
  3. Report divergence per metric

Usage:
    railway run python3 tests/cpe_level1_quantitative.py --creator iris_bertran
    railway run python3 tests/cpe_level1_quantitative.py --creator iris_bertran --skip-pipeline
    railway run python3 tests/cpe_level1_quantitative.py --creator stefano_bonanno

The --skip-pipeline flag reuses bot responses from the latest results file
instead of re-running the pipeline (useful for metric iteration).
"""

import argparse
import asyncio
import json
import logging
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cpe_level1")
logger.setLevel(logging.INFO)

# Emoji regex (Unicode emoji ranges)
_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\u2600-\u27BF\U0001F900-\U0001F9FF]"
    r"[\U0001F3FB-\U0001F3FF\uFE0F]?"
)

# Catalan-only markers (for code-switching detection)
_CA_MARKERS = re.compile(
    r"\b(tinc|estic|però|molt|doncs|també|perquè|això|vull|puc|"
    r"gràcies|gracies|bon dia|bona tarda|bona nit|setmana|"
    r"dimarts|dijous|dissabte|diumenge|nosaltres|puguis|vulguis)\b",
    re.IGNORECASE,
)
_ES_MARKERS = re.compile(
    r"\b(tengo|estoy|pero|mucho|entonces|también|porque|quiero|"
    r"puedo|necesito|bueno|gracias|vale|claro|genial|"
    r"miércoles|jueves|sábado|domingo|nosotros)\b",
    re.IGNORECASE,
)


# =========================================================================
# TEXT METRICS (universal — works for any language/creator)
# =========================================================================

def compute_metrics(text: str) -> Dict[str, Any]:
    """Compute quantitative text metrics on a single response."""
    if not text:
        return {
            "length": 0, "word_count": 0, "emoji_count": 0, "has_emoji": False,
            "question_count": 0, "has_question": False, "exclamation_count": 0,
            "has_exclamation": False, "language": "unknown", "uppercase_ratio": 0,
            "sentence_count": 1, "avg_word_length": 0, "words": set(),
        }

    words = re.findall(r"\b\w+\b", text.lower())
    emojis = _EMOJI_RE.findall(text)
    questions = text.count("?")
    exclamations = text.count("!")
    sentences = max(1, len(re.split(r"[.!?]+", text.strip())))
    alpha_chars = [c for c in text if c.isalpha()]
    upper_count = sum(1 for c in alpha_chars if c.isupper())
    upper_ratio = upper_count / len(alpha_chars) if alpha_chars else 0

    # Language detection (fast, no external deps)
    ca_hits = len(_CA_MARKERS.findall(text))
    es_hits = len(_ES_MARKERS.findall(text))
    if ca_hits and es_hits:
        lang = "ca-es"
    elif ca_hits > es_hits:
        lang = "ca"
    elif es_hits > 0:
        lang = "es"
    else:
        lang = "es"  # default

    return {
        "length": len(text),
        "word_count": len(words),
        "emoji_count": len(emojis),
        "has_emoji": len(emojis) > 0,
        "question_count": questions,
        "has_question": questions > 0,
        "exclamation_count": exclamations,
        "has_exclamation": exclamations > 0,
        "language": lang,
        "uppercase_ratio": round(upper_ratio, 3),
        "sentence_count": sentences,
        "avg_word_length": round(sum(len(w) for w in words) / len(words), 1) if words else 0,
        "words": set(words),
    }


def compute_vocabulary_overlap(creator_words: set, bot_words: set) -> float:
    """Jaccard similarity between creator and bot vocabulary."""
    if not creator_words or not bot_words:
        return 0.0
    intersection = creator_words & bot_words
    union = creator_words | bot_words
    return round(len(intersection) / len(union), 3) if union else 0.0


# =========================================================================
# BASELINE COMPUTATION (from ground truth responses)
# =========================================================================

def compute_baseline(conversations: List[Dict]) -> Dict[str, Any]:
    """Compute creator baseline metrics from ground_truth responses."""
    all_metrics = []
    all_words = set()

    for conv in conversations:
        gt = conv.get("ground_truth", "")
        if not gt:
            continue
        m = compute_metrics(gt)
        all_words |= m.pop("words", set())
        all_metrics.append(m)

    if not all_metrics:
        return {}

    baseline = {"n": len(all_metrics), "vocabulary": all_words}
    numeric_keys = ["length", "word_count", "emoji_count", "question_count",
                    "exclamation_count", "uppercase_ratio", "sentence_count", "avg_word_length"]
    bool_keys = ["has_emoji", "has_question", "has_exclamation"]

    for key in numeric_keys:
        vals = [m[key] for m in all_metrics]
        baseline[key] = {
            "mean": round(statistics.mean(vals), 1),
            "median": round(statistics.median(vals), 1),
            "std": round(statistics.stdev(vals), 1) if len(vals) > 1 else 0,
        }

    for key in bool_keys:
        pct = sum(1 for m in all_metrics if m[key]) / len(all_metrics) * 100
        baseline[key] = {"pct": round(pct, 1)}

    # Language distribution
    langs = [m["language"] for m in all_metrics]
    from collections import Counter
    lang_dist = Counter(langs)
    baseline["language_distribution"] = {k: round(v / len(langs) * 100, 1) for k, v in lang_dist.items()}

    return baseline


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

    logger.info(f"Initializing DMResponderAgent for '{creator_id}'...")
    agent = DMResponderAgent(creator_id=creator_id)
    logger.info("Agent initialized")

    results = []
    for i, conv in enumerate(conversations, 1):
        test_input = conv.get("test_input", conv.get("lead_message", conv.get("message", "")))
        lead_id = conv.get("lead_id", "")
        sender_id = _get_platform_user_id(lead_id) or lead_id

        # Build history
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
            "message_id": f"cpe_{conv.get('id', i)}",
        }

        t0 = time.monotonic()
        try:
            dm_response = await agent.process_dm(message=test_input, sender_id=sender_id, metadata=metadata)
            bot_response = dm_response.content if dm_response else ""
        except Exception as e:
            logger.error(f"[{conv.get('id', i)}] Pipeline error: {e}")
            bot_response = ""
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        results.append({
            **conv,
            "bot_response": bot_response,
            "elapsed_ms": elapsed_ms,
        })
        logger.info(f"[{i}/{len(conversations)}] {conv.get('id', '?')}: {elapsed_ms}ms | '{bot_response[:40]}...'")

    return results


# =========================================================================
# COMPARISON + SCORING
# =========================================================================

def compare_metrics(baseline: Dict, bot_metrics: List[Dict], bot_words: set) -> Dict:
    """Compare bot aggregate metrics against creator baseline."""
    comparison = {}
    numeric_keys = ["length", "word_count", "emoji_count", "question_count",
                    "exclamation_count", "uppercase_ratio", "sentence_count", "avg_word_length"]
    bool_keys = ["has_emoji", "has_question", "has_exclamation"]

    flags = 0

    for key in numeric_keys:
        creator = baseline.get(key, {})
        c_mean = creator.get("mean", 0)
        vals = [m[key] for m in bot_metrics]
        b_mean = round(statistics.mean(vals), 1) if vals else 0
        b_median = round(statistics.median(vals), 1) if vals else 0

        divergence = abs(b_mean - c_mean) / c_mean * 100 if c_mean else 0
        flagged = divergence > 30

        if flagged:
            flags += 1
            direction = "higher" if b_mean > c_mean else "lower"
            interpretation = f"Bot {key} is {divergence:.0f}% {direction} than creator"
        else:
            interpretation = f"Within 30% tolerance"

        comparison[key] = {
            "creator_mean": c_mean,
            "creator_median": creator.get("median", c_mean),
            "bot_mean": b_mean,
            "bot_median": b_median,
            "divergence_pct": round(divergence, 1),
            "flag": flagged,
            "interpretation": interpretation,
        }

    for key in bool_keys:
        creator_pct = baseline.get(key, {}).get("pct", 0)
        bot_pct = round(sum(1 for m in bot_metrics if m[key]) / len(bot_metrics) * 100, 1) if bot_metrics else 0
        divergence = abs(bot_pct - creator_pct)
        flagged = divergence > 20  # 20pp tolerance for booleans

        if flagged:
            flags += 1

        comparison[key] = {
            "creator_pct": creator_pct,
            "bot_pct": bot_pct,
            "divergence_pp": round(divergence, 1),
            "flag": flagged,
        }

    # Language distribution
    from collections import Counter
    bot_langs = Counter(m["language"] for m in bot_metrics)
    bot_lang_dist = {k: round(v / len(bot_metrics) * 100, 1) for k, v in bot_langs.items()}
    comparison["language_distribution"] = {
        "creator": baseline.get("language_distribution", {}),
        "bot": bot_lang_dist,
    }

    # Vocabulary overlap
    creator_vocab = baseline.get("vocabulary", set())
    vocab_overlap = compute_vocabulary_overlap(creator_vocab, bot_words)
    comparison["vocabulary_overlap"] = {
        "jaccard": vocab_overlap,
        "creator_vocab_size": len(creator_vocab),
        "bot_vocab_size": len(bot_words),
        "flag": vocab_overlap < 0.05,
    }
    if vocab_overlap < 0.05:
        flags += 1

    # Overall score: 1.0 = perfect match, 0.0 = completely different
    total_metrics = len(numeric_keys) + len(bool_keys) + 1  # +1 for vocab
    non_flagged = total_metrics - flags
    overall = round(non_flagged / total_metrics, 2)

    return {
        "metrics": comparison,
        "flags_count": flags,
        "total_metrics": total_metrics,
        "overall_quantitative_match": overall,
    }


# =========================================================================
# MAIN
# =========================================================================

async def main():
    parser = argparse.ArgumentParser(description="CPE Level 1: Quantitative Style Comparison")
    parser.add_argument("--creator", required=True, help="Creator slug (e.g., iris_bertran)")
    parser.add_argument("--test-set", default=None, help="Custom test set path")
    parser.add_argument("--skip-pipeline", action="store_true", help="Reuse latest bot responses")
    parser.add_argument("--output", default=None, help="Custom output path")
    args = parser.parse_args()

    creator = args.creator
    cpe_dir = REPO_ROOT / "tests" / "cpe_data" / creator / "results"
    cpe_dir.mkdir(parents=True, exist_ok=True)

    # Load test set
    if args.test_set:
        test_path = Path(args.test_set)
    else:
        # Try creator-specific, fall back to real_leads
        test_path = REPO_ROOT / "tests" / "cpe_data" / creator / "test_set.json"
        if not test_path.exists():
            test_path = REPO_ROOT / "tests" / "test_set_real_leads.json"

    logger.info(f"Loading test set: {test_path}")
    with open(test_path) as f:
        data = json.load(f)
    conversations = data if isinstance(data, list) else data.get("conversations", data.get("test_cases", []))
    logger.info(f"Loaded {len(conversations)} test cases")

    # Run pipeline or reuse
    if args.skip_pipeline:
        # Find latest results
        existing = sorted(cpe_dir.glob("level1_*.json"), reverse=True)
        if not existing:
            logger.error("No existing results to reuse. Run without --skip-pipeline first.")
            sys.exit(1)
        with open(existing[0]) as f:
            prev = json.load(f)
        results = prev.get("conversations", [])
        logger.info(f"Reusing {len(results)} bot responses from {existing[0].name}")
    else:
        results = await run_pipeline(creator, conversations)

    # Compute creator baseline from ground_truth
    logger.info("Computing creator baseline from ground_truth...")
    baseline = compute_baseline(conversations)
    logger.info(f"Baseline: n={baseline.get('n', 0)} responses")

    # Compute bot metrics
    logger.info("Computing bot metrics...")
    bot_metrics_list = []
    bot_words = set()
    for r in results:
        bot_text = r.get("bot_response", "")
        m = compute_metrics(bot_text)
        bot_words |= m.pop("words", set())
        bot_metrics_list.append(m)

    # Compare
    comparison = compare_metrics(baseline, bot_metrics_list, bot_words)

    # Build output
    timestamp = datetime.now(timezone.utc).isoformat()
    output_path = Path(args.output) if args.output else cpe_dir / f"level1_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    # Serialize baseline (remove set for JSON)
    baseline_serializable = {k: v for k, v in baseline.items() if k != "vocabulary"}
    baseline_serializable["vocabulary_size"] = len(baseline.get("vocabulary", set()))

    output = {
        "creator": creator,
        "timestamp": timestamp,
        "test_set": str(test_path),
        "n_test_cases": len(results),
        "creator_baseline": baseline_serializable,
        **comparison,
        "conversations": [
            {
                "id": r.get("id", "?"),
                "test_input": r.get("test_input", r.get("lead_message", "")),
                "ground_truth": r.get("ground_truth", ""),
                "bot_response": r.get("bot_response", ""),
                "elapsed_ms": r.get("elapsed_ms", 0),
            }
            for r in results
        ],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Print summary
    print()
    print("=" * 65)
    print(f"  CPE LEVEL 1 — Quantitative Style Match: @{creator}")
    print("=" * 65)
    print(f"  Test cases: {len(results)}")
    print(f"  Overall match: {comparison['overall_quantitative_match']}")
    print(f"  Flags (>30% divergence): {comparison['flags_count']}/{comparison['total_metrics']}")
    print()

    metrics = comparison["metrics"]
    print(f"  {'Metric':<22s} {'Creator':>8s} {'Bot':>8s} {'Div%':>6s} {'Flag':>5s}")
    print(f"  {'-'*52}")
    for key in ["length", "word_count", "emoji_count", "question_count",
                "exclamation_count", "uppercase_ratio"]:
        m = metrics.get(key, {})
        c = m.get("creator_mean", m.get("creator_pct", 0))
        b = m.get("bot_mean", m.get("bot_pct", 0))
        d = m.get("divergence_pct", m.get("divergence_pp", 0))
        f_str = ">>>" if m.get("flag") else ""
        print(f"  {key:<22s} {c:>8.1f} {b:>8.1f} {d:>5.1f}% {f_str:>5s}")

    for key in ["has_emoji", "has_question", "has_exclamation"]:
        m = metrics.get(key, {})
        c = m.get("creator_pct", 0)
        b = m.get("bot_pct", 0)
        d = m.get("divergence_pp", 0)
        f_str = ">>>" if m.get("flag") else ""
        print(f"  {key:<22s} {c:>7.1f}% {b:>7.1f}% {d:>5.1f}pp {f_str:>5s}")

    v = metrics.get("vocabulary_overlap", {})
    print(f"  {'vocab_overlap':<22s} {'jaccard':>8s} {v.get('jaccard', 0):>8.3f}")

    lang = metrics.get("language_distribution", {})
    print(f"\n  Language: creator={lang.get('creator', {})}  bot={lang.get('bot', {})}")

    print()
    print(f"  Output: {output_path}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
