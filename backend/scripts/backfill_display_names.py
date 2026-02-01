#!/usr/bin/env python3
"""
Backfill Display Names for Existing Leads

This script updates existing leads that have a username but no full_name
by fetching the display name from Instagram API.

Usage:
    python scripts/backfill_display_names.py [--dry-run] [--creator CREATOR_ID]

Options:
    --dry-run       Show what would be updated without making changes
    --creator       Only process leads for a specific creator
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


async def backfill_display_names(dry_run: bool = False, creator_filter: str = None):
    """
    Fetch display names for leads that are missing full_name.
    """
    from api.database import SessionLocal
    from api.models import Creator, Lead
    from core.instagram import InstagramConnector

    session = SessionLocal()
    stats = {
        "total_leads": 0,
        "missing_full_name": 0,
        "updated": 0,
        "errors": 0,
        "skipped_no_token": 0,
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

        for creator in creators:
            logger.info(f"\n{'='*50}")
            logger.info(f"Processing creator: {creator.name}")
            logger.info(f"{'='*50}")

            # Get leads missing full_name for this creator
            leads = session.query(Lead).filter(
                Lead.creator_id == creator.id,
                Lead.platform == "instagram",
                Lead.platform_user_id.isnot(None),
                (Lead.full_name.is_(None)) | (Lead.full_name == "")
            ).all()

            stats["total_leads"] += len(leads)
            stats["missing_full_name"] += len(leads)

            logger.info(f"Found {len(leads)} leads missing display name")

            if not leads:
                continue

            # Initialize Instagram connector
            try:
                connector = InstagramConnector(
                    access_token=creator.instagram_token,
                    page_id=creator.instagram_page_id or "",
                    ig_user_id=creator.instagram_user_id or "",
                )
            except Exception as e:
                logger.error(f"Failed to create connector for {creator.name}: {e}")
                stats["skipped_no_token"] += len(leads)
                continue

            # Process each lead
            for lead in leads:
                try:
                    profile = await connector.get_user_profile(lead.platform_user_id)

                    if profile and profile.name:
                        logger.info(
                            f"  Lead {lead.username or lead.platform_user_id}: "
                            f"'{lead.username}' -> display name: '{profile.name}'"
                        )

                        if not dry_run:
                            lead.full_name = profile.name
                            session.commit()

                        stats["updated"] += 1
                    else:
                        logger.debug(f"  Lead {lead.platform_user_id}: No display name available")

                except Exception as e:
                    logger.warning(f"  Error fetching profile for {lead.platform_user_id}: {e}")
                    stats["errors"] += 1

                # Rate limiting - Instagram API has limits
                await asyncio.sleep(0.5)

            await connector.close()

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        session.close()

    # Print summary
    logger.info(f"\n{'='*50}")
    logger.info("BACKFILL SUMMARY")
    logger.info(f"{'='*50}")
    logger.info(f"Total leads processed: {stats['total_leads']}")
    logger.info(f"Leads missing full_name: {stats['missing_full_name']}")
    logger.info(f"Successfully updated: {stats['updated']}")
    logger.info(f"Errors: {stats['errors']}")
    logger.info(f"Skipped (no token): {stats['skipped_no_token']}")

    if dry_run:
        logger.info("\n⚠️  DRY RUN - No changes were made")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Backfill display names for existing leads")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be updated without making changes")
    parser.add_argument("--creator", type=str, help="Only process leads for a specific creator")
    args = parser.parse_args()

    asyncio.run(backfill_display_names(dry_run=args.dry_run, creator_filter=args.creator))


if __name__ == "__main__":
    main()
