#!/usr/bin/env python3
"""
Sprint 7 — Multi-turn extraction desde DB messages.

- Source: tabla messages (57,957 msgs, 1,738 leads, role values verificados)
- Threshold gap: 60 min
- Burst merge: <5 min mismo rol
- Min/Max turns: 4-12
- Target output: 1,600-2,400 conversations
- Output: data/dpo/trl/sprint7/sft_mt.jsonl (ChatML + Doc D system)
"""

import json
from pathlib import Path
from sqlalchemy import create_engine, text
from os import environ
from dotenv import load_dotenv
from collections import Counter

load_dotenv()

# Config
GAP_THRESHOLD_MIN = 60
BURST_MERGE_MIN = 5
MIN_TURNS = 4
MAX_TURNS = 12

DOC_D_PATH = Path("data/personality_extractions/iris_bertran/doc_d_bot_configuration.md")


def load_doc_d():
    return DOC_D_PATH.read_text()


def fetch_messages(engine):
    query = text("""
        SELECT m.lead_id, m.role, m.content, m.created_at
        FROM messages m
        JOIN leads l ON m.lead_id = l.id
        JOIN creators c ON l.creator_id = c.id
        WHERE c.name = 'iris_bertran'
          AND m.deleted_at IS NULL
          AND m.content IS NOT NULL
          AND m.content != ''
          AND m.status IN ('sent', 'resolved_externally')
        ORDER BY m.lead_id, m.created_at
    """)
    with engine.connect() as conn:
        return list(conn.execute(query))


def group_by_conversations(messages):
    conversations = []
    current = []
    last_lead = None
    last_time = None

    for row in messages:
        lead_id, role, content, created_at = row

        if lead_id != last_lead:
            if current:
                conversations.append(current)
            current = [(role, content, created_at)]
            last_lead = lead_id
            last_time = created_at
            continue

        gap = (created_at - last_time).total_seconds() / 60
        if gap > GAP_THRESHOLD_MIN:
            if current:
                conversations.append(current)
            current = [(role, content, created_at)]
        else:
            current.append((role, content, created_at))

        last_time = created_at

    if current:
        conversations.append(current)

    return conversations


def merge_bursts(conv):
    if not conv:
        return conv

    merged = [conv[0]]
    for role, content, ts in conv[1:]:
        last_role, last_content, last_ts = merged[-1]
        gap = (ts - last_ts).total_seconds() / 60

        if role == last_role and gap < BURST_MERGE_MIN:
            merged[-1] = (role, last_content + "\n" + content, ts)
        else:
            merged.append((role, content, ts))

    return merged


def to_chatml(conv, system_prompt):
    messages = [{"role": "system", "content": system_prompt}]
    for role, content, _ in conv:
        messages.append({"role": role, "content": content})
    return {"source": "multi_turn_db", "messages": messages}


def filter_valid(conv):
    if len(conv) < MIN_TURNS or len(conv) > MAX_TURNS:
        return False
    roles = set(r for r, _, _ in conv)
    if 'user' not in roles or 'assistant' not in roles:
        return False
    return True


def main():
    print("Loading Doc D...")
    doc_d = load_doc_d()
    print(f"Doc D length: {len(doc_d)} chars")

    print("Connecting to DB...")
    engine = create_engine(environ['DATABASE_URL'])

    print("Fetching messages...")
    messages = fetch_messages(engine)
    print(f"Total messages: {len(messages):,}")

    print("Grouping by conversations (gap 60min)...")
    convs = group_by_conversations(messages)
    print(f"Conversations after gap split: {len(convs):,}")

    print("Merging bursts (<5min)...")
    convs = [merge_bursts(c) for c in convs]

    pre_filter = len(convs)
    convs = [c for c in convs if filter_valid(c)]
    print(f"Valid multi-turn ({MIN_TURNS}-{MAX_TURNS} turns): {len(convs):,} (filtered {pre_filter - len(convs):,})")

    print("Converting to ChatML...")
    output = [to_chatml(c, doc_d) for c in convs]

    out_path = Path("data/dpo/trl/sprint7/sft_mt.jsonl")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open('w') as f:
        for entry in output:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(output):,} conversations to {out_path}")

    # Stats
    turn_counts = [len(e['messages']) - 1 for e in output]
    if turn_counts:
        print(f"\nTurn distribution:")
        print(f"  Avg: {sum(turn_counts)/len(turn_counts):.1f}")
        print(f"  Min: {min(turn_counts)}")
        print(f"  Max: {max(turn_counts)}")
        print(f"  Median: {sorted(turn_counts)[len(turn_counts)//2]}")

        dist = Counter(turn_counts)
        print(f"\nDistribution:")
        for k in sorted(dist.keys()):
            bar = "█" * (dist[k] // 20)
            print(f"  {k:2d} turns: {dist[k]:4d} {bar}")

        # Token estimate
        total_chars = sum(len(m['content']) for c in output for m in c['messages'])
        print(f"\nTotal chars: {total_chars:,}")
        print(f"Approx tokens (chars/3): {total_chars // 3:,}")


if __name__ == "__main__":
    main()
