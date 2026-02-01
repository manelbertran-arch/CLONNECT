#!/usr/bin/env python3
"""
Load Conversation History from Instagram API

This script loads ALL conversation history from Instagram API for the last N weeks.
It uses pagination to fetch all conversations and all messages, deduplicating by message ID.

Usage:
    python scripts/load_conversation_history.py [--dry-run] [--creator CREATOR_ID] [--weeks N]

Options:
    --dry-run       Show what would be imported without making changes
    --creator       Only process a specific creator (by name)
    --weeks         Number of weeks to look back (default: 5)

Example:
    python scripts/load_conversation_history.py --creator stefano_bonanno --weeks 5
"""

import asyncio
import argparse
import logging
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def load_history(dry_run: bool = False, creator_filter: str = None, weeks: int = 5):
    """
    Load conversation history from Instagram API.
    """
    from api.database import SessionLocal
    from api.models import Creator, Lead, Message
    from core.dm_history_service import DMHistoryService

    session = SessionLocal()
    service = DMHistoryService()

    total_stats = {
        "creators_processed": 0,
        "conversations_found": 0,
        "leads_created": 0,
        "leads_updated": 0,
        "messages_imported": 0,
        "messages_skipped_duplicate": 0,
        "messages_filtered": 0,
        "errors": [],
    }

    try:
        # Get creators with Instagram tokens
        query = session.query(Creator).filter(
            Creator.instagram_token.isnot(None),
            Creator.instagram_token != ""
        )

        if creator_filter:
            query = query.filter(Creator.name == creator_filter)

        creators = query.all()
        logger.info(f"Found {len(creators)} creator(s) with Instagram tokens")

        if not creators:
            logger.warning("No creators found with Instagram tokens")
            return total_stats

        for creator in creators:
            logger.info(f"\n{'='*60}")
            logger.info(f"Processing creator: {creator.name}")
            logger.info(f"{'='*60}")

            # Check if we have required fields
            if not creator.instagram_token:
                logger.warning(f"Skipping {creator.name}: No Instagram token")
                continue

            # Show current state
            current_leads = session.query(Lead).filter_by(
                creator_id=creator.id,
                platform="instagram"
            ).count()

            current_messages = session.query(Message).join(Lead).filter(
                Lead.creator_id == creator.id,
                Lead.platform == "instagram"
            ).count()

            logger.info(f"Current state: {current_leads} leads, {current_messages} messages")

            if dry_run:
                logger.info(f"[DRY RUN] Would load history for {creator.name}")
                logger.info(f"  - Token: {creator.instagram_token[:10]}...{creator.instagram_token[-4:]}")
                logger.info(f"  - Page ID: {creator.instagram_page_id}")
                logger.info(f"  - IG User ID: {creator.instagram_user_id}")
                logger.info(f"  - Weeks to look back: {weeks}")
                continue

            # Load history
            try:
                max_age_days = weeks * 7
                stats = await service.load_dm_history(
                    creator_id=creator.name,
                    access_token=creator.instagram_token,
                    page_id=creator.instagram_page_id or "",
                    ig_user_id=creator.instagram_user_id or "",
                    max_age_days=max_age_days,
                    use_pagination=True  # Enable full pagination
                )

                total_stats["creators_processed"] += 1
                total_stats["conversations_found"] += stats.get("conversations_found", 0)
                total_stats["leads_created"] += stats.get("leads_created", 0)
                total_stats["leads_updated"] += stats.get("leads_updated", 0)
                total_stats["messages_imported"] += stats.get("messages_imported", 0)
                total_stats["messages_skipped_duplicate"] += stats.get("messages_skipped_duplicate", 0)
                total_stats["messages_filtered"] += stats.get("messages_filtered", 0)
                total_stats["errors"].extend(stats.get("errors", []))

                logger.info(f"Creator {creator.name} stats:")
                logger.info(f"  - Conversations: {stats.get('conversations_found', 0)}")
                logger.info(f"  - Leads created: {stats.get('leads_created', 0)}")
                logger.info(f"  - Leads updated: {stats.get('leads_updated', 0)}")
                logger.info(f"  - Messages imported: {stats.get('messages_imported', 0)}")
                logger.info(f"  - Duplicates skipped: {stats.get('messages_skipped_duplicate', 0)}")
                logger.info(f"  - Filtered (old/empty): {stats.get('messages_filtered', 0)}")

            except Exception as e:
                error_msg = f"Error processing {creator.name}: {e}"
                logger.error(error_msg)
                total_stats["errors"].append(error_msg)
                import traceback
                traceback.print_exc()

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

    # Print summary
    logger.info(f"\n{'='*60}")
    logger.info("LOAD HISTORY SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Creators processed: {total_stats['creators_processed']}")
    logger.info(f"Conversations found: {total_stats['conversations_found']}")
    logger.info(f"Leads created: {total_stats['leads_created']}")
    logger.info(f"Leads updated: {total_stats['leads_updated']}")
    logger.info(f"Messages imported: {total_stats['messages_imported']}")
    logger.info(f"Duplicates skipped: {total_stats['messages_skipped_duplicate']}")
    logger.info(f"Filtered (old/empty): {total_stats['messages_filtered']}")

    if total_stats["errors"]:
        logger.info(f"\nErrors ({len(total_stats['errors'])}):")
        for err in total_stats["errors"][:10]:
            logger.info(f"  - {err}")

    if dry_run:
        logger.info("\n[DRY RUN] No changes were made")

    return total_stats


def main():
    parser = argparse.ArgumentParser(
        description="Load conversation history from Instagram API"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be imported without making changes"
    )
    parser.add_argument(
        "--creator",
        type=str,
        help="Only process a specific creator (by name)"
    )
    parser.add_argument(
        "--weeks",
        type=int,
        default=5,
        help="Number of weeks to look back (default: 5)"
    )
    args = parser.parse_args()

    asyncio.run(load_history(
        dry_run=args.dry_run,
        creator_filter=args.creator,
        weeks=args.weeks
    ))


if __name__ == "__main__":
    main()
