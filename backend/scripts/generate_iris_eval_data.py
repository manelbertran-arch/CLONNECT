#!/usr/bin/env python3
"""Generate 30 bot responses for Iris human evaluation (CPE Level 5).

Runs the production DM pipeline on 30 representative test cases and saves
results for the evaluation form.
"""
import asyncio
import json
import sys
import time
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def main():
    from core.dm_agent_v2 import DMResponderAgent

    with open("tests/cpe_data/iris_bertran/test_set.json") as f:
        data = json.load(f)

    conversations = data["conversations"]

    # Select 30: prioritize diversity across categories
    # Take all non-casual first, then fill with casual
    non_casual = [c for c in conversations if c.get("category") != "casual"]
    casual = [c for c in conversations if c.get("category") == "casual"]
    selected = non_casual[:20] + casual[: 30 - len(non_casual[:20])]
    selected = selected[:30]

    print(f"Selected {len(selected)} cases:")
    cats = {}
    for c in selected:
        cat = c.get("category", "unknown")
        cats[cat] = cats.get(cat, 0) + 1
    for cat, n in sorted(cats.items()):
        print(f"  {cat}: {n}")

    agent = DMResponderAgent(creator_id="iris_bertran")
    results = []

    for i, conv in enumerate(selected, 1):
        test_input = conv.get("test_input", "")
        sender_id = conv.get("lead_username", f"eval_{i:03d}")

        # Build history from turns
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
            "username": conv.get("lead_username", sender_id),
            "message_id": f"eval_{conv.get('id', i)}",
        }

        t0 = time.monotonic()
        try:
            dm_response = await agent.process_dm(
                message=test_input, sender_id=sender_id, metadata=metadata
            )
            bot_response = dm_response.content if dm_response else ""
        except Exception as e:
            print(f"  [{i}/30] ERROR: {e}")
            bot_response = f"[ERROR: {e}]"
        elapsed = int((time.monotonic() - t0) * 1000)

        results.append(
            {
                "id": conv.get("id", f"eval_{i:03d}"),
                "lead_message": test_input,
                "bot_response": bot_response,
                "ground_truth": conv.get("ground_truth", ""),
                "category": conv.get("category", "unknown"),
                "language": conv.get("language", "unknown"),
                "history_summary": (
                    f"{len(history)} turns"
                    if history
                    else "no history"
                ),
            }
        )
        print(f"  [{i}/30] {elapsed}ms | {bot_response[:60]}...")

    out_path = "tests/cpe_data/iris_bertran/iris_human_eval_data.json"
    with open(out_path, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(results)} cases to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
