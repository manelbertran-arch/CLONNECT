"""
Export clean training data for fine-tuning.

Uses contamination_filter v3 to ensure data quality.
Output: JSONL file compatible with Together.ai / Fireworks.ai / OpenAI fine-tuning.

Usage:
    cd backend && python -m scripts.export_training_data \
        --creator-id "5e5c2364-c99a-4484-b986-741bb84a11cf" \
        --output ~/Desktop/stefano_training_data.jsonl
"""

import argparse
import json
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.backtest.contamination_filter import (
    filter_turns,
)

CREATOR_ID_DEFAULT = "5e5c2364-c99a-4484-b986-741bb84a11cf"


def export_training_data(
    creator_id: str,
    output_path: str,
    creator_name: str = "Stefano Bonanno",
    min_response_length: int = 5,
) -> list:
    """Export clean conversation pairs for fine-tuning."""
    import sqlalchemy as sa

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    engine = sa.create_engine(database_url)

    # Load all conversations (include created_at for session boundary detection)
    query = sa.text("""
        SELECT
            m.lead_id, m.role, m.content, m.status, m.approved_by,
            m.created_at,
            l.username as lead_username
        FROM messages m
        JOIN leads l ON m.lead_id = l.id
        WHERE l.creator_id = :creator_id
        AND m.content IS NOT NULL AND m.content != ''
        ORDER BY m.lead_id, m.created_at ASC
    """)

    with engine.connect() as conn:
        rows = conn.execute(query, {"creator_id": creator_id}).fetchall()

    print(f"Loaded {len(rows)} messages")

    # Build conversation pairs — session-aware to avoid cross-conversation contamination.
    # Without session detection, a pair from Monday's "quiero barre" conversation
    # could get mixed with Thursday's "com esta la teva mare" → contaminated DPO pair.
    from core.conversation_boundary import segment_sessions

    convs_raw = defaultdict(list)
    lead_usernames = {}
    for row in rows:
        convs_raw[row.lead_id].append({
            "role": row.role,
            "content": row.content,
            "status": row.status or "",
            "approved_by": row.approved_by or "",
            "created_at": row.created_at,
        })
        if row.lead_username:
            lead_usernames[row.lead_id] = row.lead_username

    conversations = []
    all_turns = []
    cross_session_skipped = 0
    for lead_id, msgs in convs_raw.items():
        username = lead_usernames.get(lead_id, str(lead_id))

        # Segment into sessions so we only pair within the same conversation
        sessions = segment_sessions(msgs)

        turns = []
        for session in sessions:
            for i in range(1, len(session)):
                curr = session[i]
                prev = session[i - 1]
                if curr["role"] != "assistant" or curr["status"] != "sent":
                    continue
                if curr["approved_by"] not in ("", "creator", "creator_manual"):
                    continue
                if prev["role"] != "user":
                    continue

                turn = {
                    "user_message": prev["content"],
                    "real_response": curr["content"],
                    "real_length": len(curr["content"]),
                    "lead_username": username,
                }
                turns.append(turn)
                all_turns.append(turn)

        if turns:
            conversations.append({"lead_username": username, "turns": turns})

    print(f"Built {len(conversations)} conversations, {len(all_turns)} turns")

    # Filter contamination
    clean_turns, excluded, stats = filter_turns(conversations, all_turns)
    print(f"Clean: {len(clean_turns)}, Excluded: {len(excluded)}")

    # Format for fine-tuning (OpenAI chat format)
    system_msg = (
        f"Eres {creator_name}. Responde como el: breve, calido, "
        "con su tono personal. Mensajes cortos y naturales."
    )

    training_data = []
    for turn in clean_turns:
        if turn["real_length"] < min_response_length:
            continue
        training_data.append({
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": turn["user_message"]},
                {"role": "assistant", "content": turn["real_response"]},
            ]
        })

    # Write JSONL
    with open(output_path, "w", encoding="utf-8") as f:
        for item in training_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"\nExported {len(training_data)} training examples to {output_path}")

    # Stats
    lengths = [len(t["real_response"]) for t in clean_turns if t["real_length"] >= min_response_length]
    if lengths:
        print(f"Response length: median={statistics.median(lengths):.0f}, "
              f"mean={statistics.mean(lengths):.0f}, "
              f"p75={sorted(lengths)[int(len(lengths)*0.75)]}")
        print(f"<40c: {sum(1 for l in lengths if l<40)/len(lengths)*100:.0f}%")
        print(f"40-100c: {sum(1 for l in lengths if 40<=l<100)/len(lengths)*100:.0f}%")
        print(f">100c: {sum(1 for l in lengths if l>=100)/len(lengths)*100:.0f}%")

    return training_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export training data")
    parser.add_argument("--creator-id", default=CREATOR_ID_DEFAULT)
    parser.add_argument("--creator-name", default="Stefano Bonanno")
    parser.add_argument("--output", default="training_data.jsonl")
    args = parser.parse_args()

    export_training_data(args.creator_id, args.output, args.creator_name)
