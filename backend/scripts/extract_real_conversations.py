#!/usr/bin/env python3
"""
Extract real conversations where Stefano responded personally (not the bot).

Identifies Stefano's authentic messages via:
- copilot_action IS NULL + suggested_response IS NULL (pre-bot era)
- copilot_action = 'edited' (Stefano edited the bot suggestion)
- copilot_action = 'manual_override' (Stefano wrote from scratch)
- copilot_action = 'resolved_externally' (replied from IG/WA directly)

Excludes:
- Bot-approved messages (copilot_action='approved', approved_by='auto')
- Conversations with < 3 exchanges
- Media-only messages without text
- Leads with no Stefano messages

Usage:
    # Extract from production DB (via railway run)
    railway run python3.11 scripts/extract_real_conversations.py

    # With options
    railway run python3.11 scripts/extract_real_conversations.py --min-turns 3 --limit 500 --output results/

    # Dry run (show stats only)
    railway run python3.11 scripts/extract_real_conversations.py --dry-run
"""
import os
import sys
import json
import argparse
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

logger = logging.getLogger(__name__)

# Stefano's creator ID
STEFANO_CREATOR_ID = "5e5c2364-c99a-4484-b986-741bb84a11cf"

# Copilot actions that indicate REAL Stefano messages
REAL_STEFANO_ACTIONS = {
    None,           # Pre-bot era (no copilot tracking)
    "edited",       # Stefano edited the bot suggestion → content IS Stefano's
    "manual_override",  # Stefano wrote from scratch
    "resolved_externally",  # Stefano replied from IG/WA directly
}

# Actions that indicate BOT messages (not Stefano)
BOT_ACTIONS = {
    "approved",     # Bot suggestion accepted as-is
}

# Intent → topic mapping
INTENT_TO_TOPIC = {
    "greeting": "casual",
    "thanks": "casual",
    "casual": "casual",
    "farewell": "casual",
    "product_inquiry": "ventas",
    "pricing": "ventas",
    "purchase": "ventas",
    "interest": "ventas",
    "objection": "ventas",
    "complaint": "soporte",
    "support": "soporte",
    "technical": "soporte",
    "booking": "reservas",
    "schedule": "reservas",
    "content": "contenido",
    "story_reply": "contenido",
    "collaboration": "contenido",
}


def get_db_session():
    """Get a DB session."""
    from api.database import SessionLocal
    return SessionLocal()


def classify_topic(messages: list[dict]) -> str:
    """Classify conversation topic from message intents."""
    intent_counts = Counter()
    for msg in messages:
        intent = msg.get("intent", "")
        topic = INTENT_TO_TOPIC.get(intent, "otro")
        intent_counts[topic] += 1

    if not intent_counts:
        return "casual"
    return intent_counts.most_common(1)[0][0]


def is_real_stefano_message(msg: dict) -> bool:
    """Determine if a message is genuinely from Stefano (not the bot)."""
    if msg["role"] != "assistant":
        return False

    action = msg.get("copilot_action")
    approved_by = msg.get("approved_by")
    suggested = msg.get("suggested_response")

    # Edited or manual override → definitely Stefano
    if action in ("edited", "manual_override", "resolved_externally"):
        return True

    # No copilot tracking AND no suggested_response → pre-bot era
    if action is None and suggested is None:
        # Additional heuristic: if approved_by is "auto", it's likely bot
        if approved_by == "auto":
            return False
        return True

    # Approved as-is → it's the bot's words (even if Stefano clicked "send")
    if action == "approved":
        return False

    return False


def extract_conversations(
    session,
    creator_id: str = STEFANO_CREATOR_ID,
    min_turns: int = 3,
    min_stefano_messages: int = 1,
    limit: int | None = None,
) -> tuple[list[dict], dict]:
    """Extract real conversations from the database.

    Returns (conversations, stats).
    """
    from sqlalchemy import func, text
    from api.models import Lead, Message

    # Step 1: Get all leads for this creator with sufficient messages
    logger.info(f"Querying leads for creator {creator_id}...")
    leads = (
        session.query(Lead)
        .filter(Lead.creator_id == creator_id)
        .order_by(Lead.last_contact_at.desc())
        .all()
    )
    logger.info(f"Found {len(leads)} leads")

    conversations = []
    stats = {
        "total_leads_scanned": len(leads),
        "total_conversations": 0,
        "total_stefano_messages": 0,
        "total_lead_messages": 0,
        "total_bot_messages_excluded": 0,
        "skipped_too_few_turns": 0,
        "skipped_no_stefano": 0,
        "skipped_no_text": 0,
        "by_category": Counter(),
        "by_topic": Counter(),
        "by_has_media": Counter(),
    }

    for lead in leads:
        # Get all messages for this lead, ordered chronologically
        messages = (
            session.query(
                Message.id,
                Message.role,
                Message.content,
                Message.intent,
                Message.copilot_action,
                Message.suggested_response,
                Message.approved_by,
                Message.status,
                Message.msg_metadata,
                Message.created_at,
            )
            .filter(
                Message.lead_id == lead.id,
                Message.content.isnot(None),
                Message.content != "",
            )
            .order_by(Message.created_at.asc())
            .all()
        )

        if len(messages) < min_turns:
            stats["skipped_too_few_turns"] += 1
            continue

        # Build conversation turns
        turns = []
        stefano_count = 0
        lead_count = 0
        bot_excluded = 0
        has_media = False

        for msg in messages:
            msg_dict = {
                "role": msg.role,
                "content": msg.content,
                "intent": msg.intent,
                "copilot_action": msg.copilot_action,
                "suggested_response": msg.suggested_response,
                "approved_by": msg.approved_by,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "msg_metadata": msg.msg_metadata,
            }

            # Check for media
            meta = msg.msg_metadata or {}
            if meta.get("type") in ("story_mention", "story_reply", "media_share", "audio"):
                has_media = True

            if msg.role == "user":
                turns.append({
                    "role": "lead",
                    "content": msg.content,
                    "timestamp": msg_dict["created_at"],
                    "intent": msg.intent,
                })
                lead_count += 1

            elif msg.role == "assistant":
                if is_real_stefano_message(msg_dict):
                    turns.append({
                        "role": "stefano_real",
                        "content": msg.content,
                        "timestamp": msg_dict["created_at"],
                        "intent": msg.intent,
                        "copilot_action": msg.copilot_action,
                    })
                    stefano_count += 1
                else:
                    # Bot message — include for context but mark as bot
                    turns.append({
                        "role": "bot",
                        "content": msg.content,
                        "timestamp": msg_dict["created_at"],
                        "intent": msg.intent,
                        "copilot_action": msg.copilot_action,
                    })
                    bot_excluded += 1

        stats["total_bot_messages_excluded"] += bot_excluded

        # Filter: need minimum Stefano messages
        if stefano_count < min_stefano_messages:
            stats["skipped_no_stefano"] += 1
            continue

        # Determine date range
        timestamps = [t["timestamp"] for t in turns if t.get("timestamp")]
        date_range = ""
        if timestamps:
            date_range = f"{timestamps[0][:10]} to {timestamps[-1][:10]}"

        # Classify topic
        topic = classify_topic([t for t in turns if t.get("intent")])

        # Lead category (map DB status to plan categories)
        status_map = {
            "nuevo": "NUEVO",
            "interesado": "INTERESADO",
            "caliente": "CALIENTE",
            "cliente": "CLIENTE",
            "fantasma": "FANTASMA",
            "amigo": "AMIGO",
            "colaborador": "COLABORADOR",
            "frio": "FRIO",
            "frío": "FRIO",
        }
        lead_category = status_map.get(lead.status or "nuevo", "OTRO")

        conv = {
            "id": f"conv_{len(conversations) + 1:04d}",
            "lead_id": str(lead.id),
            "lead_username": lead.username or "unknown",
            "lead_category": lead_category,
            "topic": topic,
            "turns": turns,
            "metadata": {
                "total_turns": len(turns),
                "stefano_messages": stefano_count,
                "lead_messages": lead_count,
                "bot_messages_excluded": bot_excluded,
                "has_media": has_media,
                "date_range": date_range,
                "lead_score": lead.score,
                "lead_status": lead.status,
            },
        }

        conversations.append(conv)
        stats["total_conversations"] += 1
        stats["total_stefano_messages"] += stefano_count
        stats["total_lead_messages"] += lead_count
        stats["by_category"][lead_category] += 1
        stats["by_topic"][topic] += 1
        stats["by_has_media"][has_media] += 1

        if limit and len(conversations) >= limit:
            break

    # Convert Counters to dicts for JSON serialization
    stats["by_category"] = dict(stats["by_category"])
    stats["by_topic"] = dict(stats["by_topic"])
    stats["by_has_media"] = {str(k): v for k, v in stats["by_has_media"].items()}

    return conversations, stats


def print_extraction_report(conversations: list[dict], stats: dict):
    """Print extraction summary."""
    print(f"\n{'='*60}")
    print(f"  Conversation Extraction Report")
    print(f"{'='*60}")
    print(f"\n  Leads scanned:         {stats['total_leads_scanned']}")
    print(f"  Conversations found:   {stats['total_conversations']}")
    print(f"  Stefano messages:      {stats['total_stefano_messages']}")
    print(f"  Lead messages:         {stats['total_lead_messages']}")
    print(f"  Bot messages excluded: {stats['total_bot_messages_excluded']}")

    print(f"\n  Skipped:")
    print(f"    Too few turns:       {stats['skipped_too_few_turns']}")
    print(f"    No Stefano msgs:     {stats['skipped_no_stefano']}")

    print(f"\n  By lead category:")
    for cat, count in sorted(stats["by_category"].items(), key=lambda x: -x[1]):
        print(f"    {cat:20s} {count}")

    print(f"\n  By topic:")
    for topic, count in sorted(stats["by_topic"].items(), key=lambda x: -x[1]):
        print(f"    {topic:20s} {count}")

    print(f"\n  Media conversations:   {stats['by_has_media'].get('True', 0)}")

    # Show distribution of Stefano messages per conversation
    if conversations:
        stef_counts = [c["metadata"]["stefano_messages"] for c in conversations]
        avg_stef = sum(stef_counts) / len(stef_counts)
        print(f"\n  Avg Stefano msgs/conv: {avg_stef:.1f}")
        print(f"  Max Stefano msgs/conv: {max(stef_counts)}")

        turn_counts = [c["metadata"]["total_turns"] for c in conversations]
        avg_turns = sum(turn_counts) / len(turn_counts)
        print(f"  Avg turns/conv:        {avg_turns:.1f}")
        print(f"  Max turns/conv:        {max(turn_counts)}")

    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Extract real Stefano conversations from DB",
    )
    parser.add_argument("--creator-id", default=STEFANO_CREATOR_ID, help="Creator UUID")
    parser.add_argument("--min-turns", type=int, default=3, help="Min exchanges per conversation")
    parser.add_argument("--min-stefano", type=int, default=1, help="Min Stefano messages per conversation")
    parser.add_argument("--limit", type=int, default=None, help="Max conversations to extract")
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--dry-run", action="store_true", help="Show stats only, don't save")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    session = get_db_session()
    try:
        conversations, stats = extract_conversations(
            session,
            creator_id=args.creator_id,
            min_turns=args.min_turns,
            min_stefano_messages=args.min_stefano,
            limit=args.limit,
        )

        print_extraction_report(conversations, stats)

        if args.dry_run:
            print("  [DRY RUN] No files saved.")
            return

        # Save output
        output_dir = Path(args.output) if args.output else Path(__file__).parent.parent / "results"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"real_conversations_{timestamp}.json"

        output = {
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "creator_id": args.creator_id,
            "stats": stats,
            "conversations": conversations,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)

        print(f"  Saved to: {output_path}")
        print(f"  File size: {output_path.stat().st_size / 1024:.1f} KB")

    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
