#!/usr/bin/env python3
"""
Recategorize all existing leads based on their message content.

This script analyzes all leads and updates their status (nuevo/interesado/caliente)
based on keywords detected in their messages.

Usage:
    python scripts/recategorize_leads.py [--dry-run]

FIX 2026-02-02: One-time migration to properly categorize leads that were
previously all marked as "nuevo" regardless of message content.
"""
import sys
import os
import argparse

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, List

from core.lead_categorization import calcular_categoria, categoria_a_status_legacy


def get_db_session():
    """Get database session."""
    try:
        os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/clonnect")
        from api.database import SessionLocal
        return SessionLocal()
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None


def get_lead_messages(session, lead_id: str) -> List[Dict]:
    """Get messages for a lead."""
    from api.models import Message

    messages = session.query(Message).filter_by(lead_id=lead_id).order_by(Message.created_at).all()

    result = []
    for msg in messages:
        result.append({
            "role": msg.role,
            "content": msg.content or "",
            "created_at": msg.created_at
        })
    return result


def recategorize_leads(dry_run: bool = False):
    """Recategorize all leads based on message content."""
    session = get_db_session()
    if not session:
        print("Failed to connect to database")
        return

    try:
        from api.models import Lead

        # Get all leads with message counts
        leads = session.query(Lead).all()

        print(f"\n{'='*70}")
        print(f"RECATEGORIZING {len(leads)} LEADS")
        print(f"{'='*70}")
        print(f"{'Dry run' if dry_run else 'LIVE MODE'} - changes {'will NOT' if dry_run else 'WILL'} be saved\n")

        stats = {
            "total": len(leads),
            "unchanged": 0,
            "upgraded": 0,
            "by_status": {}
        }

        changes = []

        for lead in leads:
            # Get messages
            messages = get_lead_messages(session, lead.id)
            msg_count = len(messages)

            # Get last user message time
            last_user_msg_time = None
            for msg in reversed(messages):
                if msg["role"] == "user" and msg.get("created_at"):
                    last_user_msg_time = msg["created_at"]
                    break

            # Calculate new category
            result = calcular_categoria(
                mensajes=messages,
                es_cliente=(lead.status == "cliente" or lead.status == "customer"),
                ultimo_mensaje_lead=last_user_msg_time,
                lead_created_at=lead.first_contact_at
            )

            new_status = categoria_a_status_legacy(result.categoria)
            old_status = lead.status or "new"

            # Track stats
            stats["by_status"][new_status] = stats["by_status"].get(new_status, 0) + 1

            if old_status != new_status:
                changes.append({
                    "username": lead.username or lead.platform_user_id,
                    "msg_count": msg_count,
                    "old": old_status,
                    "new": new_status,
                    "intent": result.intent_score,
                    "keywords": result.keywords_detectados[:3],
                    "razones": result.razones[:2]
                })

                if not dry_run:
                    lead.status = new_status
                    lead.purchase_intent = result.intent_score

                stats["upgraded"] += 1
            else:
                stats["unchanged"] += 1

        # Print changes
        if changes:
            print(f"\n{'USERNAME':<25} {'MSGS':>5} {'OLD':<12} {'NEW':<12} {'INTENT':>6} KEYWORDS")
            print("-" * 85)
            for c in sorted(changes, key=lambda x: x["msg_count"], reverse=True):
                keywords_str = ", ".join(c["keywords"][:3]) if c["keywords"] else "-"
                print(f"{c['username'][:24]:<25} {c['msg_count']:>5} {c['old']:<12} {c['new']:<12} {c['intent']:>6.2f} {keywords_str}")
        else:
            print("No changes needed - all leads are correctly categorized.")

        # Commit if not dry run
        if not dry_run and changes:
            session.commit()
            print(f"\n✅ Committed {len(changes)} changes to database")

        # Print summary
        print(f"\n{'='*70}")
        print("SUMMARY")
        print(f"{'='*70}")
        print(f"Total leads:     {stats['total']}")
        print(f"Unchanged:       {stats['unchanged']}")
        print(f"Recategorized:   {stats['upgraded']}")
        print(f"\nNew status distribution:")
        for status, count in sorted(stats["by_status"].items()):
            pct = count / stats["total"] * 100 if stats["total"] > 0 else 0
            print(f"  {status:<12}: {count:>4} ({pct:.1f}%)")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recategorize leads based on message content")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without saving")
    args = parser.parse_args()

    recategorize_leads(dry_run=args.dry_run)
