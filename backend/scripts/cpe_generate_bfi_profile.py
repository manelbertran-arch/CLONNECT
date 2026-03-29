#!/usr/bin/env python3
"""
CPE BFI Profile Generator — Big Five personality profile from creator messages.

Analyzes a sample of creator messages using GPT-4o to infer Big Five
Inventory (BFI) personality dimensions. Universal — works for any creator.

Usage:
    python scripts/cpe_generate_bfi_profile.py --creator iris_bertran
    python scripts/cpe_generate_bfi_profile.py --creator stefano_bonanno

Output:
    tests/cpe_data/{creator}/bfi_profile.json

BFI Dimensions:
    O - Openness to Experience (creative, curious vs conventional)
    C - Conscientiousness (organized, disciplined vs careless)
    E - Extraversion (outgoing, energetic vs solitary, reserved)
    A - Agreeableness (friendly, compassionate vs competitive)
    N - Neuroticism (sensitive, emotional vs secure, confident)

Cost: ~$0.30-0.50 per creator (10 batches × 20 messages via GPT-4o-mini)
"""

import argparse
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from dotenv import load_dotenv

load_dotenv()

BATCH_SIZE = 20
MAX_BATCHES = 10
MODEL = "gpt-4o-mini"

BFI_SYSTEM = """You are a psycholinguistic researcher analyzing communication patterns.
Given real messages from a person, estimate their Big Five Inventory (BFI) scores.

Score each dimension 1.0-5.0:
- O (Openness): creative, curious, variety-seeking vs conventional, routine
- C (Conscientiousness): organized, disciplined, detail-oriented vs careless, flexible
- E (Extraversion): outgoing, energetic, talkative vs reserved, solitary, quiet
- A (Agreeableness): friendly, compassionate, cooperative vs competitive, challenging
- N (Neuroticism): sensitive, nervous, moody vs secure, confident, calm

Base scores ONLY on communication style evidence:
- Word choice, emoji usage, message length, punctuation
- Tone (warm/cold, formal/casual, enthusiastic/reserved)
- Topics discussed and how they discuss them
- NOT on message content about third parties

Respond with ONLY valid JSON, no explanation."""

BFI_USER = """Analyze these {n} real messages from the same person:

{messages}

Score their Big Five personality (1.0-5.0 each).
Respond ONLY JSON: {{"O": X.X, "C": X.X, "E": X.X, "A": X.X, "N": X.X, "evidence": {{"O": "why", "C": "why", "E": "why", "A": "why", "N": "why"}}}}"""


def get_creator_messages(creator_slug: str, limit: int = 200):
    """Fetch real creator messages from DB."""
    from sqlalchemy import create_engine, text

    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if "sslmode" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    engine = create_engine(url, pool_size=2)

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM creators WHERE name = :name"), {"name": creator_slug}
        ).fetchone()
        if not row:
            print(f"Creator '{creator_slug}' not found")
            sys.exit(1)
        cid = str(row[0])

        msgs = conn.execute(
            text("""
                SELECT m.content
                FROM messages m
                JOIN leads l ON l.id = m.lead_id
                WHERE l.creator_id = :cid
                  AND m.role = 'assistant'
                  AND m.status IN ('sent', 'resolved_externally')
                  AND m.content IS NOT NULL
                  AND length(m.content) BETWEEN 10 AND 300
                  AND m.content NOT LIKE '[%%Audio]%%'
                  AND m.content NOT LIKE '[%%Photo]%%'
                  AND m.content NOT LIKE 'Sent%%'
                  AND m.content NOT LIKE 'http%%'
                ORDER BY m.created_at DESC
                LIMIT :lim
            """),
            {"cid": cid, "lim": limit},
        ).fetchall()

    return [m[0] for m in msgs]


def analyze_batch(client, messages: list, batch_num: int) -> dict:
    """Analyze a batch of messages for BFI scores."""
    formatted = "\n".join(f"  [{i+1}] {m[:150]}" for i, m in enumerate(messages))
    prompt = BFI_USER.format(n=len(messages), messages=formatted)

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": BFI_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=400,
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        data = json.loads(raw)
        print(f"  Batch {batch_num}: O={data.get('O', 0):.1f} C={data.get('C', 0):.1f} "
              f"E={data.get('E', 0):.1f} A={data.get('A', 0):.1f} N={data.get('N', 0):.1f}")
        return data
    except Exception as e:
        print(f"  Batch {batch_num}: ERROR — {e}")
        return {}


def aggregate_scores(batch_results: list) -> dict:
    """Aggregate BFI scores across batches with mean + std."""
    dims = ["O", "C", "E", "A", "N"]
    aggregated = {}

    for dim in dims:
        values = [b.get(dim, 0) for b in batch_results if b.get(dim, 0) > 0]
        if values:
            aggregated[dim] = {
                "mean": round(statistics.mean(values), 2),
                "std": round(statistics.stdev(values), 2) if len(values) > 1 else 0,
                "min": round(min(values), 1),
                "max": round(max(values), 1),
                "n_batches": len(values),
            }
        else:
            aggregated[dim] = {"mean": 3.0, "std": 0, "min": 3.0, "max": 3.0, "n_batches": 0}

    # Collect evidence from last batch (most complete)
    evidence = {}
    for b in reversed(batch_results):
        if b.get("evidence"):
            evidence = b["evidence"]
            break

    return aggregated, evidence


def main():
    parser = argparse.ArgumentParser(description="CPE BFI Profile Generator")
    parser.add_argument("--creator", required=True, help="Creator slug")
    parser.add_argument("--limit", type=int, default=200, help="Max messages to sample")
    parser.add_argument("--output", default=None, help="Output directory")
    args = parser.parse_args()

    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    print(f"Fetching messages for {args.creator}...")
    messages = get_creator_messages(args.creator, args.limit)
    print(f"Fetched {len(messages)} messages")

    if len(messages) < BATCH_SIZE:
        print(f"Need at least {BATCH_SIZE} messages, got {len(messages)}")
        sys.exit(1)

    # Shuffle for diversity within batches
    random.seed(42)
    random.shuffle(messages)

    # Split into batches
    n_batches = min(MAX_BATCHES, len(messages) // BATCH_SIZE)
    batches = [messages[i * BATCH_SIZE:(i + 1) * BATCH_SIZE] for i in range(n_batches)]

    print(f"Analyzing {n_batches} batches of {BATCH_SIZE} messages each...")
    batch_results = []
    for i, batch in enumerate(batches):
        result = analyze_batch(client, batch, i + 1)
        batch_results.append(result)
        time.sleep(0.5)

    # Aggregate
    scores, evidence = aggregate_scores(batch_results)

    # Output
    out_dir = Path(args.output) if args.output else Path("tests/cpe_data") / args.creator
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "bfi_profile.json"

    dim_labels = {
        "O": "Openness to Experience",
        "C": "Conscientiousness",
        "E": "Extraversion",
        "A": "Agreeableness",
        "N": "Neuroticism",
    }

    output = {
        "creator": args.creator,
        "model": MODEL,
        "messages_analyzed": len(messages),
        "n_batches": n_batches,
        "batch_size": BATCH_SIZE,
        "scores": {dim: scores[dim]["mean"] for dim in "OCEAN"},
        "scores_detailed": scores,
        "evidence": evidence,
        "dimension_labels": dim_labels,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to {out_path}")

    # Also save to DB for production access
    try:
        from services.creator_profile_service import save_profile
        if save_profile(args.creator, "bfi_profile", output):
            print(f"✅ Saved to DB: {args.creator}/bfi_profile")
        else:
            print(f"⚠️ DB save failed (creator not found?)")
    except Exception as e:
        print(f"⚠️ DB save skipped: {e}")

    # Summary
    print(f"\n{'='*50}")
    print(f"BFI PROFILE: {args.creator}")
    print(f"{'='*50}")
    for dim in "OCEAN":
        s = scores[dim]
        bar = "#" * int(s["mean"]) + "." * (5 - int(s["mean"]))
        label = dim_labels[dim]
        print(f"  {dim} ({label:28s}) {s['mean']:>4.1f}/5  [{bar}]  (std={s['std']:.2f})")
        if dim in evidence:
            print(f"    Evidence: {evidence[dim][:80]}")

    # Interpretation
    print(f"\n  Profile interpretation:")
    high = [dim for dim in "OCEAN" if scores[dim]["mean"] >= 3.8]
    low = [dim for dim in "OCEAN" if scores[dim]["mean"] <= 2.5]
    mid = [dim for dim in "OCEAN" if 2.5 < scores[dim]["mean"] < 3.8]
    if high:
        print(f"    High: {', '.join(f'{d} ({dim_labels[d]})' for d in high)}")
    if low:
        print(f"    Low:  {', '.join(f'{d} ({dim_labels[d]})' for d in low)}")
    if mid:
        print(f"    Mid:  {', '.join(f'{d} ({dim_labels[d]})' for d in mid)}")


if __name__ == "__main__":
    main()
