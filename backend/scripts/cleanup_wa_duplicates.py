"""
Cleanup WhatsApp message duplicates — delete all but one copy of each message.

The WhatsApp onboarding pipeline (_store_messages) was missing dedup checks,
causing every historical message to be re-inserted on each Evolution API
reconnection (50-60x duplication per message).

This script keeps the OLDEST copy (by id) of each unique
(lead_id, platform_message_id) pair and deletes the rest.

Usage:
    railway run python3 scripts/cleanup_wa_duplicates.py --dry-run
    railway run python3 scripts/cleanup_wa_duplicates.py
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [DEDUP] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def cleanup(dry_run: bool = True, creator_name: str = None):
    from sqlalchemy import text
    from api.database import SessionLocal

    session = SessionLocal()
    try:
        # Scope to creator if specified (creators table has 'name' column)
        creator_join = ""
        creator_filter = ""
        params = {}
        if creator_name:
            creator_join = "JOIN creators c ON l.creator_id = c.id"
            creator_filter = "AND c.name = :cname"
            params["cname"] = creator_name

        # Count total duplicates first
        count_sql = text(f"""
            SELECT count(*) FROM messages m
            JOIN leads l ON m.lead_id = l.id
            {creator_join}
            WHERE l.platform = 'whatsapp'
            {creator_filter}
            AND m.platform_message_id IS NOT NULL
            AND m.id NOT IN (
                SELECT DISTINCT ON (lead_id, platform_message_id) id
                FROM messages
                WHERE platform_message_id IS NOT NULL
                ORDER BY lead_id, platform_message_id, created_at ASC, id ASC
            )
        """)
        result = session.execute(count_sql, params).scalar()
        logger.info(f"Found {result:,} duplicate messages to delete")

        if result == 0:
            logger.info("No duplicates found!")
            return

        # Also count messages without platform_message_id that are dupes
        count_null_sql = text(f"""
            SELECT count(*) FROM messages m
            JOIN leads l ON m.lead_id = l.id
            {creator_join}
            WHERE l.platform = 'whatsapp'
            {creator_filter}
            AND m.platform_message_id IS NULL
            AND m.id NOT IN (
                SELECT DISTINCT ON (lead_id, role, content) id
                FROM messages
                WHERE platform_message_id IS NULL
                ORDER BY lead_id, role, content, created_at ASC, id ASC
            )
        """)
        null_dupes = session.execute(count_null_sql, params).scalar()
        logger.info(f"Found {null_dupes:,} additional duplicates (no platform_message_id)")

        if dry_run:
            # Show per-lead stats
            stats_sql = text(f"""
                SELECT l.full_name, l.platform_user_id,
                       count(*) as total,
                       count(DISTINCT m.platform_message_id) as unique_pmids
                FROM messages m
                JOIN leads l ON m.lead_id = l.id
                {creator_join}
                WHERE l.platform = 'whatsapp'
                {creator_filter}
                AND m.platform_message_id IS NOT NULL
                GROUP BY l.full_name, l.platform_user_id
                HAVING count(*) > count(DISTINCT m.platform_message_id) * 2
                ORDER BY count(*) DESC
                LIMIT 20
            """)
            stats = session.execute(stats_sql, params).fetchall()
            logger.info("Top 20 leads by duplication:")
            for s in stats:
                ratio = s[2] / s[3] if s[3] > 0 else 0
                logger.info(f"  {s[0] or s[1]}: {s[2]:,} total, {s[3]:,} unique ({ratio:.1f}x)")

            logger.info(f"\n[DRY RUN] Would delete {result + null_dupes:,} duplicate messages")
            logger.info("Run without --dry-run to execute deletion")
            return

        # Delete duplicates with platform_message_id (in batches)
        logger.info("Deleting duplicates with platform_message_id...")
        deleted_total = 0
        batch_size = 10000

        while True:
            delete_sql = text(f"""
                DELETE FROM messages
                WHERE id IN (
                    SELECT m.id FROM messages m
                    JOIN leads l ON m.lead_id = l.id
                    {creator_join}
                    WHERE l.platform = 'whatsapp'
                    {creator_filter}
                    AND m.platform_message_id IS NOT NULL
                    AND m.id NOT IN (
                        SELECT DISTINCT ON (lead_id, platform_message_id) id
                        FROM messages
                        WHERE platform_message_id IS NOT NULL
                        ORDER BY lead_id, platform_message_id, created_at ASC, id ASC
                    )
                    LIMIT :batch_size
                )
            """)
            res = session.execute(delete_sql, {**params, "batch_size": batch_size})
            deleted = res.rowcount
            session.commit()
            deleted_total += deleted
            logger.info(f"  Deleted batch: {deleted:,} (total so far: {deleted_total:,})")
            if deleted < batch_size:
                break

        # Delete duplicates without platform_message_id
        logger.info("Deleting duplicates without platform_message_id...")
        delete_null_sql = text(f"""
            DELETE FROM messages
            WHERE id IN (
                SELECT m.id FROM messages m
                JOIN leads l ON m.lead_id = l.id
                {creator_join}
                WHERE l.platform = 'whatsapp'
                {creator_filter}
                AND m.platform_message_id IS NULL
                AND m.id NOT IN (
                    SELECT DISTINCT ON (lead_id, role, content) id
                    FROM messages
                    WHERE platform_message_id IS NULL
                    ORDER BY lead_id, role, content, created_at ASC, id ASC
                )
            )
        """)
        res = session.execute(delete_null_sql, params)
        null_deleted = res.rowcount
        session.commit()
        deleted_total += null_deleted
        logger.info(f"  Deleted {null_deleted:,} null-pmid duplicates")

        logger.info(f"\nDEDUP COMPLETE: {deleted_total:,} duplicate messages deleted")

    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="Cleanup WA message duplicates")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted")
    parser.add_argument("--creator", type=str, default=None, help="Only clean specific creator")
    args = parser.parse_args()

    cleanup(dry_run=args.dry_run, creator_name=args.creator)


if __name__ == "__main__":
    main()
