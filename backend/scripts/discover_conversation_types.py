"""
Discover conversation types from creator's historical messages.
Universal — works for any creator, any language.
Run during onboarding or manually.

Usage:
    python scripts/discover_conversation_types.py --creator iris_bertran
"""
import argparse
import collections
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _classify_message_universal(content: str) -> str:
    """Classify a user message into a conversation type using structural signals."""
    if not content or len(content.strip()) < 2:
        return "empty"

    c = content.strip()
    cl = c.lower()

    if c.startswith("[audio") or c.startswith("[Audio") or c.startswith("[🎤"):
        return "audio_message"
    if re.match(r'^[\U0001f000-\U0001ffff\u2600-\u27bf\u2764\ufe0f\s]+$', c):
        return "emoji_reaction"
    if re.search(r'[€$£¥]|\d+\s*(eur|usd|gbp)', cl):
        return "product_inquiry"
    if re.match(r'^(hol[ae]|hey|hi|bon\s*dia|buen[ao]s|ey|ei|hello)', cl) and len(c) <= 20:
        return "greeting"
    if re.search(r'graci|merci|thanks|gràci', cl):
        return "thanks"
    if re.search(r'bye|adeu|nanit|adi[oó]s|bona\s*nit|see\s*you', cl):
        return "farewell"
    if re.search(r'[jh]a[jh]a|😂|🤣', cl) and len(c) < 40:
        return "casual_humor"
    if len(c) <= 12 and "?" not in c:
        return "short_response"
    if "?" in c and len(c) > 15:
        return "question"
    if re.search(r'https?://|www\.', cl):
        return "link_share"
    if len(c) > 80:
        return "long_personal"
    return "casual_chat"


def _analyze_creator_behavior(assistant_msgs: list) -> dict:
    """Analyze how the creator typically responds in this type."""
    if not assistant_msgs:
        return {"avg_length": 0, "emoji_rate": 0.0, "products_mentioned": False}

    lengths = [len(m) for m in assistant_msgs]
    emoji_pat = re.compile(r'[\U0001f000-\U0001ffff\u2600-\u27bf\u2764\ufe0f]')
    emoji_count = sum(1 for m in assistant_msgs if emoji_pat.search(m))
    product_pat = re.compile(
        r'[€$£¥]|\d+\s*(eur|usd|gbp)|reserv|book|class|clase|pack|link|pago|payment', re.I
    )
    product_count = sum(1 for m in assistant_msgs if product_pat.search(m))

    return {
        "avg_length": int(sum(lengths) / len(lengths)),
        "emoji_rate": round(emoji_count / len(assistant_msgs), 2),
        "products_mentioned": product_count / len(assistant_msgs) > 0.1,
    }


def discover(creator_id: str, db_url: str = None) -> dict:
    """Discover conversation types from creator's historical data."""
    from sqlalchemy import create_engine, text

    db_url = db_url or os.environ.get("DATABASE_URL", "")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    if "sslmode" not in db_url:
        db_url += ("&" if "?" in db_url else "?") + "sslmode=require"

    engine = create_engine(db_url, pool_pre_ping=True, connect_args={"connect_timeout": 30})

    with engine.connect() as conn:
        msgs = conn.execute(text("""
            SELECT l.username, m.role, m.content
            FROM messages m
            JOIN leads l ON l.id = m.lead_id
            WHERE l.creator_id = (
                SELECT id FROM creators WHERE name = :cid LIMIT 1
            )
            AND m.content IS NOT NULL AND length(m.content) > 1
            AND m.deleted_at IS NULL
            AND m.created_at > NOW() - INTERVAL '3 months'
            ORDER BY l.username, m.created_at
        """), {"cid": creator_id}).fetchall()

    # Group by lead
    by_lead = collections.defaultdict(list)
    for m in msgs:
        by_lead[m.username].append({"role": m.role, "content": m.content})

    # Classify user messages, collect paired assistant responses
    type_user_msgs = collections.defaultdict(list)
    type_assistant_msgs = collections.defaultdict(list)

    for lead, messages in by_lead.items():
        for i, msg in enumerate(messages):
            if msg["role"] == "user":
                conv_type = _classify_message_universal(msg["content"])
                type_user_msgs[conv_type].append(msg["content"])
                if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant":
                    type_assistant_msgs[conv_type].append(messages[i + 1]["content"])

    total_msgs = sum(len(v) for v in type_user_msgs.values())
    if total_msgs == 0:
        return {}

    conversation_types = {}
    for type_name, user_msgs in type_user_msgs.items():
        if len(user_msgs) < 5:
            continue

        frequency = len(user_msgs) / total_msgs
        behavior = _analyze_creator_behavior(type_assistant_msgs.get(type_name, []))

        conversation_types[type_name] = {
            "frequency": round(frequency, 3),
            "count": len(user_msgs),
            "creator_avg_length": behavior["avg_length"],
            "creator_emoji_rate": behavior["emoji_rate"],
            "products_relevant": behavior["products_mentioned"],
            "sample_user_msgs": [m[:80] for m in user_msgs[:3]],
        }

    return dict(sorted(conversation_types.items(), key=lambda x: x[1]["frequency"], reverse=True))


def main():
    parser = argparse.ArgumentParser(description="Discover conversation types")
    parser.add_argument("--creator", required=True)
    args = parser.parse_args()

    types = discover(args.creator)

    print(f"\nDiscovered {len(types)} conversation types for {args.creator}:")
    for name, data in types.items():
        tag = "🛒" if data["products_relevant"] else "💬"
        print(
            f"  {tag} {name:18s}: {data['frequency']*100:5.1f}% ({data['count']:4d} msgs) "
            f"avg_len={data['creator_avg_length']:3d}c emoji={data['creator_emoji_rate']:.0%}"
        )

    cal_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "calibrations", f"{args.creator}.json"
    )
    if os.path.exists(cal_path):
        with open(cal_path) as f:
            cal = json.load(f)
    else:
        cal = {}

    cal["conversation_types"] = types
    with open(cal_path, "w", encoding="utf-8") as f:
        json.dump(cal, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to {cal_path}")


if __name__ == "__main__":
    main()
