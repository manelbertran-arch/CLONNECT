"""
Instagram DM Backfill — Import missing messages from the last N days.

Fetches conversations from the Instagram Graph API, compares with DB,
and inserts any missing messages. Does NOT trigger bot suggestions.

Usage:
    railway run python3 scripts/ig_backfill.py iris_bertran --days 3 --dry-run
    railway run python3 scripts/ig_backfill.py iris_bertran --days 3
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [IG-BACKFILL] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

for name in ["httpx", "httpcore", "urllib3"]:
    logging.getLogger(name).setLevel(logging.WARNING)


async def backfill(creator_name: str, days: int = 3, dry_run: bool = False, max_convs: int = 100):
    from api.database import SessionLocal
    from api.models import Creator, Lead, Message
    from core.instagram import InstagramConnector

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            logger.error(f"Creator not found: {creator_name}")
            return
        if not creator.instagram_token:
            logger.error(f"No Instagram token for {creator_name}")
            return

        creator_uuid = creator.id
        ig_user_id = creator.instagram_user_id
        page_id = creator.instagram_page_id

        logger.info(f"Creator: {creator_name} (UUID={creator_uuid})")
        logger.info(f"IG user ID: {ig_user_id}, Page ID: {page_id}")
        logger.info(f"Token length: {len(creator.instagram_token)}")
        logger.info(f"Backfill window: last {days} days, dry_run={dry_run}")
    finally:
        session.close()

    # Cutoff date
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    logger.info(f"Cutoff: {cutoff.isoformat()}")

    # Connect to Instagram API
    connector = InstagramConnector(
        access_token=creator.instagram_token,
        page_id=page_id or "",
        ig_user_id=ig_user_id or "",
    )

    # Fetch conversations
    logger.info("Fetching conversations from IG API...")
    try:
        conversations = await connector.get_all_conversations(
            max_pages=5, cutoff_date=cutoff
        )
    except Exception as e:
        logger.error(f"Failed to fetch conversations: {e}")
        return

    logger.info(f"Found {len(conversations)} conversations")

    total_new = 0
    total_existing = 0
    total_errors = 0
    leads_updated = 0

    for i, conv in enumerate(conversations[:max_convs]):
        conv_id = conv.get("id")
        participants = conv.get("participants", {}).get("data", [])

        # Find the other participant
        other = None
        for p in participants:
            if str(p.get("id")) != str(ig_user_id):
                other = p
                break
        if not other:
            continue

        other_ig_id = str(other.get("id", ""))
        other_username = other.get("username", "")

        # Fetch messages for this conversation
        try:
            messages = await connector.get_all_conversation_messages(
                conv_id, max_pages=5, cutoff_date=cutoff
            )
        except Exception as e:
            logger.warning(f"Failed to fetch messages for {other_username or other_ig_id}: {e}")
            total_errors += 1
            continue

        if not messages:
            continue

        # Get or create lead
        session = SessionLocal()
        try:
            lead = (
                session.query(Lead)
                .filter(Lead.creator_id == creator_uuid, Lead.platform_user_id == other_ig_id)
                .first()
            )
            if not lead:
                # Also try with ig_ prefix
                lead = (
                    session.query(Lead)
                    .filter(
                        Lead.creator_id == creator_uuid,
                        Lead.platform_user_id == f"ig_{other_ig_id}",
                    )
                    .first()
                )
            if not lead:
                if dry_run:
                    logger.info(f"  [DRY] Would create lead: {other_username or other_ig_id}")
                    continue
                lead = Lead(
                    creator_id=creator_uuid,
                    platform_user_id=other_ig_id,
                    platform="instagram",
                    username=other_username,
                    full_name=other_username,
                    status="nuevo",
                )
                session.add(lead)
                session.flush()
                logger.info(f"  Created lead: {other_username or other_ig_id}")

            lead_id = lead.id

            # Get existing message IDs for this lead
            existing_mids = set()
            existing = (
                session.query(Message.platform_message_id)
                .filter(
                    Message.lead_id == lead_id,
                    Message.platform_message_id.isnot(None),
                )
                .all()
            )
            existing_mids = {r[0] for r in existing}

            # Insert missing messages
            conv_new = 0
            batch = []
            for msg in messages:
                mid = msg.get("id", "")
                if mid in existing_mids:
                    total_existing += 1
                    continue

                content = msg.get("message", "")
                if not content:
                    # Check for attachments/media
                    attachments = msg.get("attachments", {}).get("data", [])
                    if attachments:
                        att_type = attachments[0].get("type", "unknown")
                        content = f"[{att_type}]"
                    else:
                        continue

                from_id = str(msg.get("from", {}).get("id", ""))
                from_creator = from_id == str(ig_user_id)
                created_time = msg.get("created_time", "")

                created_at = datetime.now(timezone.utc)
                if created_time:
                    try:
                        created_at = datetime.fromisoformat(
                            created_time.replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        pass

                if dry_run:
                    role = "assistant" if from_creator else "user"
                    logger.info(f"  [DRY] {role}: {content[:60]}... ({created_at})")
                    conv_new += 1
                    continue

                batch.append(Message(
                    lead_id=lead_id,
                    role="assistant" if from_creator else "user",
                    content=content,
                    status="sent",
                    approved_by="ig_backfill",
                    platform_message_id=mid,
                    msg_metadata={"source": "ig_backfill"},
                    created_at=created_at,
                ))
                conv_new += 1

            if batch:
                session.bulk_save_objects(batch)
                # Update lead's last_contact_at
                latest = max(b.created_at for b in batch)
                if not lead.last_contact_at or latest > lead.last_contact_at:
                    lead.last_contact_at = latest
                session.commit()
                leads_updated += 1

            if conv_new > 0:
                total_new += conv_new
                logger.info(
                    f"  [{i+1}/{len(conversations)}] {other_username or other_ig_id}: "
                    f"+{conv_new} new msgs (skipped {total_existing} existing)"
                )

        except Exception as e:
            logger.error(f"Error processing {other_username}: {e}")
            session.rollback()
            total_errors += 1
        finally:
            session.close()

        # Rate limit
        await asyncio.sleep(0.3)

    logger.info("=" * 60)
    logger.info(f"BACKFILL COMPLETE")
    logger.info(f"  New messages inserted: {total_new}")
    logger.info(f"  Already existed: {total_existing}")
    logger.info(f"  Leads updated: {leads_updated}")
    logger.info(f"  Errors: {total_errors}")
    logger.info(f"  Dry run: {dry_run}")


def main():
    parser = argparse.ArgumentParser(description="Instagram DM Backfill")
    parser.add_argument("creator_name", help="Creator slug")
    parser.add_argument("--days", type=int, default=3, help="Days to backfill")
    parser.add_argument("--dry-run", action="store_true", help="Don't insert, just show what would be imported")
    parser.add_argument("--max-convs", type=int, default=100, help="Max conversations to process")
    args = parser.parse_args()

    asyncio.run(backfill(args.creator_name, args.days, args.dry_run, args.max_convs))


if __name__ == "__main__":
    main()
