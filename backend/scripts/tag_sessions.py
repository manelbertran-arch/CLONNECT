"""
Retroactive session tagging for all messages.

Runs ConversationBoundaryDetector on all messages per lead and outputs
session statistics + sample sessions for manual verification.

Usage:
    railway run python3 scripts/tag_sessions.py --creator iris_bertran
    railway run python3 scripts/tag_sessions.py --creator iris_bertran --sample 20
"""

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")

from core.conversation_boundary import ConversationBoundaryDetector

DATABASE_URL = os.getenv("DATABASE_URL", "")


def _get_conn():
    return psycopg2.connect(DATABASE_URL)


def _resolve_creator_uuid(creator_name: str) -> str:
    conn = _get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name FROM creators WHERE name = %s", (creator_name,))
            row = cur.fetchone()
            if not row:
                print(f"ERROR: Creator '{creator_name}' not found")
                sys.exit(1)
            print(f"Creator: {row[1]} (id={row[0]})")
            return str(row[0])
    finally:
        conn.close()


def tag_all_messages(creator_name: str, sample_n: int = 20) -> dict:
    """Tag all messages with session boundaries and report statistics."""
    creator_uuid = _resolve_creator_uuid(creator_name)
    conn = _get_conn()
    detector = ConversationBoundaryDetector()

    try:
        # Get all leads for this creator
        with conn.cursor() as cur:
            cur.execute("""
                SELECT l.id, l.username, l.platform,
                       COUNT(m.id) AS msg_count
                FROM leads l
                JOIN messages m ON m.lead_id = l.id
                WHERE l.creator_id = %s
                  AND m.deleted_at IS NULL
                  AND m.content IS NOT NULL AND m.content != ''
                GROUP BY l.id, l.username, l.platform
                ORDER BY msg_count DESC
            """, (creator_uuid,))
            leads = cur.fetchall()

        print(f"\nProcessing {len(leads)} leads...")

        total_messages = 0
        total_sessions = 0
        session_sizes = []
        sample_sessions = []

        for lead_id, username, platform, msg_count in leads:
            # Get all messages for this lead
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, role, content, created_at
                    FROM messages
                    WHERE lead_id = %s
                      AND deleted_at IS NULL
                      AND content IS NOT NULL AND content != ''
                    ORDER BY created_at ASC
                """, (lead_id,))
                msg_rows = cur.fetchall()

            if not msg_rows:
                continue

            messages = [
                {
                    "id": str(row[0]),
                    "role": row[1],
                    "content": row[2],
                    "created_at": row[3],
                }
                for row in msg_rows
            ]

            sessions = detector.segment(messages)
            total_messages += len(messages)
            total_sessions += len(sessions)

            for session in sessions:
                session_sizes.append(len(session))

            # Collect samples
            if len(sample_sessions) < sample_n and len(sessions) >= 2:
                for si, session in enumerate(sessions[:3]):
                    if len(sample_sessions) >= sample_n:
                        break
                    sample_sessions.append({
                        "lead": username or str(lead_id)[:8],
                        "session_index": si,
                        "total_sessions_for_lead": len(sessions),
                        "messages": [
                            {
                                "role": m["role"],
                                "content": m["content"][:100],
                                "time": m["created_at"].isoformat() if m.get("created_at") else None,
                            }
                            for m in session[:5]  # first 5 messages of session
                        ],
                    })

        # Statistics
        avg_sessions_per_lead = total_sessions / len(leads) if leads else 0
        avg_session_size = sum(session_sizes) / len(session_sizes) if session_sizes else 0
        size_dist = Counter()
        for s in session_sizes:
            if s == 1:
                size_dist["1 msg"] += 1
            elif s <= 3:
                size_dist["2-3 msgs"] += 1
            elif s <= 10:
                size_dist["4-10 msgs"] += 1
            elif s <= 30:
                size_dist["11-30 msgs"] += 1
            else:
                size_dist["31+ msgs"] += 1

        stats = {
            "creator": creator_name,
            "total_leads": len(leads),
            "total_messages": total_messages,
            "total_sessions": total_sessions,
            "avg_sessions_per_lead": round(avg_sessions_per_lead, 1),
            "avg_session_size": round(avg_session_size, 1),
            "session_size_distribution": dict(size_dist),
            "tagged_at": datetime.now(timezone.utc).isoformat(),
        }

        print(f"\n{'='*60}")
        print(f"SESSION TAGGING RESULTS — {creator_name}")
        print(f"{'='*60}")
        print(f"Total leads:            {stats['total_leads']}")
        print(f"Total messages:         {stats['total_messages']}")
        print(f"Total sessions:         {stats['total_sessions']}")
        print(f"Avg sessions/lead:      {stats['avg_sessions_per_lead']}")
        print(f"Avg session size:       {stats['avg_session_size']} msgs")
        print(f"\nSession size distribution:")
        for bucket, count in sorted(size_dist.items()):
            print(f"  {bucket:<12} {count:>5}  ({count/total_sessions*100:.1f}%)")

        print(f"\n{'='*60}")
        print(f"SAMPLE SESSIONS (verify manually):")
        print(f"{'='*60}")
        for sample in sample_sessions[:sample_n]:
            print(f"\n--- Lead: {sample['lead']} | Session {sample['session_index']+1}/{sample['total_sessions_for_lead']} ---")
            for m in sample["messages"]:
                role_icon = "👤" if m["role"] == "user" else "🤖"
                time_str = m["time"][:16] if m.get("time") else "?"
                print(f"  {time_str} {role_icon} {m['content']}")

        # Save results
        out_dir = REPO_ROOT / "docs" / "research"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"session_tagging_{creator_name}.json"
        out_path.write_text(json.dumps({
            "stats": stats,
            "samples": sample_sessions,
        }, indent=2, ensure_ascii=False, default=str))
        print(f"\nSaved to {out_path}")

        return stats

    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tag messages with session boundaries")
    parser.add_argument("--creator", default="iris_bertran")
    parser.add_argument("--sample", type=int, default=20, help="Number of sample sessions to show")
    args = parser.parse_args()
    tag_all_messages(args.creator, args.sample)
