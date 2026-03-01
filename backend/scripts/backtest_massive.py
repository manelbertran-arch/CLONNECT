#!/usr/bin/env python3
"""
Massive backtest: reproduce real conversations with the bot.

For each turn where Stefano responded, generates the bot alternative.
Uses REAL Stefano history (not bot responses) to prevent contamination.

Usage:
    # Full backtest (all conversations)
    railway run python3.11 scripts/backtest_massive.py --input results/real_conversations_XXX.json

    # Sample 200 pairs (economical)
    railway run python3.11 scripts/backtest_massive.py --input results/real_conversations_XXX.json --sample 200

    # Re-eval mode (after auto-learning, smaller sample)
    railway run python3.11 scripts/backtest_massive.py --input results/real_conversations_XXX.json --mode re-eval --sample 100

Cost estimate:
    - Bot generation: ~$0.01/turn (Gemini Flash-Lite)
    - 2000 turns → ~$20
    - Sample 200 → ~$2
"""
import os
import sys
import json
import time
import asyncio
import argparse
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

logger = logging.getLogger(__name__)

STEFANO_CREATOR_ID = "5e5c2364-c99a-4484-b986-741bb84a11cf"


def disable_side_effects():
    """Disable side-effect features for safe backtest execution."""
    os.environ["ENABLE_DNA_TRIGGERS"] = "false"
    os.environ["ENABLE_MESSAGE_SPLITTING"] = "false"
    os.environ["ENABLE_NURTURING_AUTO_SCHEDULE"] = "false"
    os.environ["ENABLE_LEAD_SCORING_REALTIME"] = "false"
    os.environ["ENABLE_AUTOLEARNING"] = "false"
    # Keep clone score and other read-only features enabled
    os.environ.setdefault("ENABLE_CLONE_SCORE", "false")


def init_agent(creator_id: str):
    """Initialize the DM pipeline agent."""
    from core.dm_agent_v2 import DMResponderAgentV2, AgentConfig

    agent = DMResponderAgentV2(
        creator_id=creator_id,
        config=AgentConfig(
            temperature=0.7,
            max_tokens=200,
        ),
    )
    logger.info(f"Initialized DMResponderAgentV2 for {creator_id}")
    return agent


async def reproduce_conversation(
    conversation: dict,
    agent,
    max_turns: int | None = None,
) -> list[dict]:
    """Reproduce a conversation, generating bot responses for each Stefano turn.

    Uses REAL Stefano responses for history (not bot alternatives) to prevent
    error accumulation across turns.
    """
    results = []
    history = []  # Accumulates real history for context

    turns = conversation["turns"]
    stefano_turn_count = 0

    for i, turn in enumerate(turns):
        # Lead messages → add to history for context
        if turn["role"] == "lead":
            history.append({
                "role": "user",
                "content": turn["content"],
            })
            continue

        # Bot messages (approved as-is) → add to history but skip evaluation
        if turn["role"] == "bot":
            history.append({
                "role": "assistant",
                "content": turn["content"],
            })
            continue

        # Stefano's real message → generate bot alternative
        if turn["role"] == "stefano_real":
            if max_turns and stefano_turn_count >= max_turns:
                break

            # Get the last lead message (what Stefano was responding to)
            last_lead_msg = ""
            for h in reversed(history):
                if h["role"] == "user":
                    last_lead_msg = h["content"]
                    break

            if not last_lead_msg:
                # First turn without lead message — skip
                history.append({
                    "role": "assistant",
                    "content": turn["content"],
                })
                continue

            # Generate bot response
            try:
                start_ms = time.monotonic()
                dm_response = await agent.process_dm(
                    message=last_lead_msg,
                    sender_id=conversation.get("lead_id", "backtest_user"),
                    metadata={
                        "history": history[:-1] if len(history) > 1 else [],  # Exclude last lead msg (it's the current input)
                        "lead_stage": conversation.get("lead_category", "nuevo").lower(),
                        "turn_index": stefano_turn_count,
                        "conversation_id": conversation["id"],
                        "username": conversation.get("lead_username", "backtest_user"),
                    },
                )
                elapsed_ms = int((time.monotonic() - start_ms) * 1000)

                bot_response = dm_response.content if dm_response else ""
                bot_confidence = dm_response.confidence if dm_response else 0.0
                bot_tokens = dm_response.tokens_used if dm_response else 0
                bot_metadata = dm_response.metadata if dm_response else {}

            except Exception as e:
                logger.warning(f"Bot generation failed for {conversation['id']} turn {i}: {e}")
                bot_response = f"[ERROR: {str(e)[:100]}]"
                bot_confidence = 0.0
                bot_tokens = 0
                bot_metadata = {"error": str(e)}
                elapsed_ms = 0

            results.append({
                "conversation_id": conversation["id"],
                "turn_index": i,
                "stefano_turn_index": stefano_turn_count,
                "lead_message": last_lead_msg,
                "conversation_context": history[:-1][-10:],  # Last 10 messages for context
                "stefano_real": turn["content"],
                "bot_response": bot_response,
                "lead_category": conversation["lead_category"],
                "topic": conversation["topic"],
                "bot_confidence": bot_confidence,
                "bot_tokens": bot_tokens,
                "bot_latency_ms": elapsed_ms,
                "bot_used_pool": bot_metadata.get("used_pool", False) if isinstance(bot_metadata, dict) else False,
            })

            stefano_turn_count += 1

            # Add REAL Stefano response to history (not bot) to prevent contamination
            history.append({
                "role": "assistant",
                "content": turn["content"],
            })

    return results


async def run_backtest(
    conversations: list[dict],
    agent,
    sample_size: int | None = None,
    max_concurrent: int = 5,
) -> dict:
    """Run the massive backtest across all conversations."""
    # Optionally sample
    if sample_size and sample_size < len(conversations):
        # Stratified sample by category
        by_category = {}
        for conv in conversations:
            cat = conv["lead_category"]
            by_category.setdefault(cat, []).append(conv)

        sampled = []
        per_cat = max(1, sample_size // len(by_category))
        for cat, convs in by_category.items():
            sampled.extend(random.sample(convs, min(per_cat, len(convs))))

        # Fill remaining from all
        remaining = sample_size - len(sampled)
        if remaining > 0:
            pool = [c for c in conversations if c not in sampled]
            sampled.extend(random.sample(pool, min(remaining, len(pool))))

        conversations = sampled[:sample_size]
        logger.info(f"Sampled {len(conversations)} conversations (stratified)")

    all_pairs = []
    total_start = time.monotonic()
    errors = 0

    # Process in batches to control concurrency
    semaphore = asyncio.Semaphore(max_concurrent)

    async def process_one(conv):
        nonlocal errors
        async with semaphore:
            try:
                pairs = await reproduce_conversation(conv, agent)
                return pairs
            except Exception as e:
                logger.error(f"Failed {conv['id']}: {e}")
                errors += 1
                return []

    print(f"\n  Processing {len(conversations)} conversations...")

    tasks = [process_one(conv) for conv in conversations]
    results = await asyncio.gather(*tasks)

    for pair_list in results:
        all_pairs.extend(pair_list)

    total_elapsed = time.monotonic() - total_start

    # Compute stats
    total_tokens = sum(p.get("bot_tokens", 0) for p in all_pairs)
    latencies = [p["bot_latency_ms"] for p in all_pairs if p["bot_latency_ms"] > 0]
    pool_count = sum(1 for p in all_pairs if p.get("bot_used_pool"))

    stats = {
        "total_conversations": len(conversations),
        "total_pairs": len(all_pairs),
        "errors": errors,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(total_tokens * 0.00001, 4),  # Rough estimate
        "elapsed_seconds": round(total_elapsed, 1),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
        "p95_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0, 1),
        "pool_match_rate": round(pool_count / len(all_pairs) * 100, 1) if all_pairs else 0,
        "by_category": dict(Counter(p["lead_category"] for p in all_pairs)),
        "by_topic": dict(Counter(p["topic"] for p in all_pairs)),
    }

    return {"pairs": all_pairs, "stats": stats}


def print_backtest_report(stats: dict):
    """Print backtest summary."""
    print(f"\n{'='*60}")
    print(f"  Massive Backtest Report")
    print(f"{'='*60}")
    print(f"\n  Conversations: {stats['total_conversations']}")
    print(f"  Response pairs: {stats['total_pairs']}")
    print(f"  Errors: {stats['errors']}")
    print(f"  Elapsed: {stats['elapsed_seconds']:.1f}s")
    print(f"  Pool match rate: {stats['pool_match_rate']:.1f}%")

    print(f"\n  Latency:")
    print(f"    Avg: {stats['avg_latency_ms']:.0f}ms")
    print(f"    P95: {stats['p95_latency_ms']:.0f}ms")

    print(f"\n  Tokens: {stats['total_tokens']:,}")
    print(f"  Est. cost: ${stats['estimated_cost_usd']:.2f}")

    print(f"\n  By category:")
    for cat, count in sorted(stats.get("by_category", {}).items(), key=lambda x: -x[1]):
        print(f"    {cat:20s} {count}")

    print(f"\n  By topic:")
    for topic, count in sorted(stats.get("by_topic", {}).items(), key=lambda x: -x[1]):
        print(f"    {topic:20s} {count}")

    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Massive Backtest with Real Conversations")
    parser.add_argument("--input", required=True, help="Path to extracted conversations JSON")
    parser.add_argument("--sample", type=int, default=None, help="Sample N conversations (stratified)")
    parser.add_argument("--max-concurrent", type=int, default=5, help="Max concurrent bot calls")
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--mode", choices=["full", "re-eval"], default="full", help="Backtest mode")
    parser.add_argument("--creator-id", default=STEFANO_CREATOR_ID, help="Creator UUID")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Load extracted conversations
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conversations = data.get("conversations", [])
    if not conversations:
        print("Error: No conversations found in input file")
        sys.exit(1)

    print(f"  Loaded {len(conversations)} conversations from {input_path.name}")

    # Disable side effects and init agent
    disable_side_effects()
    agent = init_agent(args.creator_id)

    # Run backtest
    result = asyncio.run(run_backtest(
        conversations,
        agent,
        sample_size=args.sample,
        max_concurrent=args.max_concurrent,
    ))

    print_backtest_report(result["stats"])

    # Save results
    output_dir = Path(args.output) if args.output else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    mode_tag = args.mode
    output_path = output_dir / f"backtest_{mode_tag}_{timestamp}.json"

    output = {
        "backtest_at": datetime.now(timezone.utc).isoformat(),
        "mode": args.mode,
        "input_file": str(input_path),
        "creator_id": args.creator_id,
        "stats": result["stats"],
        "pairs": result["pairs"],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    print(f"  Saved to: {output_path}")
    print(f"  File size: {output_path.stat().st_size / 1024:.1f} KB")
    print(f"\n  Next: Run blind judge evaluation:")
    print(f"  railway run python3.11 scripts/blind_judge.py --input {output_path}")


# Needed for Counter import
from collections import Counter

if __name__ == "__main__":
    main()
