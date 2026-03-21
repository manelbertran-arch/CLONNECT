"""
Compress lead memories for the 20 test set leads.

Usage: cd backend && python3 scripts/compress_test_leads.py
Requires: GOOGLE_API_KEY in .env, DB access
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from services.memory_engine import get_memory_engine


async def main():
    engine = get_memory_engine()

    with open(Path(__file__).resolve().parent.parent / "tests" / "test_set_v1.json") as f:
        test_set = json.load(f)

    leads = [(c["lead_id"], c.get("lead_name", "?"), c["id"]) for c in test_set["conversations"]]
    # Deduplicate by lead_id
    seen = set()
    unique_leads = []
    for lid, name, cid in leads:
        if lid not in seen:
            seen.add(lid)
            unique_leads.append((lid, name, cid))

    creator_id = "iris_bertran"
    print(f"Compressing memories for {len(unique_leads)} unique leads...\n")

    results = []
    for i, (lead_id, lead_name, conv_id) in enumerate(unique_leads):
        print(f"[{i+1}/{len(unique_leads)}] {lead_name:25s} ({lead_id[:8]}...) ", end="", flush=True)

        memo = await engine.compress_lead_memory(creator_id, lead_id)

        if memo:
            print(f"OK ({len(memo)} chars)")
            results.append({
                "lead_id": lead_id,
                "lead_name": lead_name,
                "memo": memo,
                "chars": len(memo),
            })
        else:
            print("SKIP (not enough facts)")

        # Rate limit
        if i < len(unique_leads) - 1:
            await asyncio.sleep(1.0)

    print(f"\nCompressed {len(results)}/{len(unique_leads)} leads")

    # Print first 3 examples
    print("\n" + "=" * 60)
    print("EXAMPLE MEMOS:")
    print("=" * 60)
    for r in results[:3]:
        print(f"\n--- {r['lead_name']} ({r['lead_id'][:8]}...) ---")
        print(r["memo"])

    # Save results
    out_path = Path(__file__).resolve().parent.parent / "tests" / "compressed_memos_v1.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
