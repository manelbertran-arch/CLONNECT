#!/usr/bin/env python3
"""Mine per-intent length profile from real creator messages.

Queries the last 500 bot→user message pairs, classifies the user message
via classify_lead_context(), and computes per-context length statistics.

Output: tests/cpe_data/{creator}/length_by_intent.json

Usage:
    railway run python3 scripts/cpe_generate_length_profile.py --creator iris_bertran
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
from sqlalchemy import create_engine, text

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.length_controller import classify_lead_context


def main():
    parser = argparse.ArgumentParser(description="Generate per-intent length profile")
    parser.add_argument("--creator", required=True, help="Creator slug (e.g. iris_bertran)")
    parser.add_argument("--limit", type=int, default=500, help="Max message pairs to query")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(db_url)

    query = text("""
        SELECT m_user.content AS user_msg, m_bot.content AS bot_msg,
               LENGTH(m_bot.content) AS bot_len
        FROM messages m_bot
        JOIN LATERAL (
            SELECT content, lead_id, created_at
            FROM messages
            WHERE lead_id = m_bot.lead_id
              AND role = 'user'
              AND created_at < m_bot.created_at
            ORDER BY created_at DESC
            LIMIT 1
        ) m_user ON TRUE
        JOIN leads l ON l.id = m_bot.lead_id
        JOIN creators c ON c.id = l.creator_id
        WHERE c.name = :creator_id
          AND m_bot.role = 'assistant'
          AND m_bot.content IS NOT NULL
          AND LENGTH(m_bot.content) > 0
        ORDER BY m_bot.created_at DESC
        LIMIT :lim
    """)

    with engine.connect() as conn:
        rows = conn.execute(query, {"creator_id": args.creator, "lim": args.limit}).fetchall()

    if not rows:
        print(f"No messages found for creator '{args.creator}'", file=sys.stderr)
        sys.exit(1)

    print(f"Fetched {len(rows)} message pairs for '{args.creator}'")

    # Group by context
    groups: dict[str, list[int]] = {}
    all_lengths: list[int] = []
    for row in rows:
        user_msg = row.user_msg or ""
        bot_len = row.bot_len or 0
        context = classify_lead_context(user_msg)
        groups.setdefault(context, []).append(bot_len)
        all_lengths.append(bot_len)

    def compute_stats(lengths: list[int]) -> dict:
        arr = np.array(lengths)
        return {
            "p25": int(np.percentile(arr, 25)),
            "median": int(np.median(arr)),
            "p75": int(np.percentile(arr, 75)),
            "p90": int(np.percentile(arr, 90)),
            "count": len(lengths),
        }

    profile = {}
    for ctx, lengths in sorted(groups.items(), key=lambda x: -len(x[1])):
        profile[ctx] = compute_stats(lengths)
        print(f"  {ctx:25s}  n={len(lengths):3d}  median={profile[ctx]['median']}c")

    # Add default from all messages
    profile["default"] = compute_stats(all_lengths)
    print(f"  {'default':25s}  n={len(all_lengths):3d}  median={profile['default']['median']}c")

    # Save
    out_dir = Path(__file__).resolve().parent.parent / "tests" / "cpe_data" / args.creator
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "length_by_intent.json"
    with open(out_path, "w") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)

    print(f"\nSaved → {out_path}")


if __name__ == "__main__":
    main()
