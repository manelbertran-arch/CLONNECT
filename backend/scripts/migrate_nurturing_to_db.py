#!/usr/bin/env python3
"""
Migrate nurturing followups from JSON files to PostgreSQL.

This script migrates existing JSON-based nurturing followup data to the
PostgreSQL database. It's safe to run multiple times (idempotent).

Usage:
    python scripts/migrate_nurturing_to_db.py [--dry-run] [--creator CREATOR_ID]

Options:
    --dry-run       Show what would be migrated without actually doing it
    --creator ID    Only migrate data for specific creator

Environment:
    DATABASE_URL    PostgreSQL connection string (required)
"""

import sys
import json
import argparse
import logging
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.database import SessionLocal
from core.nurturing import FollowUp
from core.nurturing_db import NurturingFollowupDB

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Data directory
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "nurturing"


def get_json_files(creator_id: str = None) -> list:
    """Get list of JSON followup files to migrate."""
    files = []
    if not DATA_DIR.exists():
        logger.warning(f"Data directory not found: {DATA_DIR}")
        return files

    for file in DATA_DIR.glob("*_followups.json"):
        cid = file.stem.replace("_followups", "")
        if creator_id is None or cid == creator_id:
            files.append((cid, file))

    return files


def load_json_followups(file_path: Path) -> list:
    """Load followups from JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return [FollowUp.from_dict(item) for item in data]
    except Exception as e:
        logger.error(f"Error loading {file_path}: {e}")
        return []


def migrate_creator(session, creator_id: str, followups: list, dry_run: bool = False) -> dict:
    """Migrate followups for a single creator."""
    stats = {
        "total": len(followups),
        "migrated": 0,
        "skipped": 0,
        "errors": 0
    }

    for fu in followups:
        try:
            # Check if already exists
            existing = session.query(NurturingFollowupDB).filter(
                NurturingFollowupDB.id == fu.id
            ).first()

            if existing:
                stats["skipped"] += 1
                continue

            if not dry_run:
                db_followup = NurturingFollowupDB.from_followup(fu)
                session.add(db_followup)

            stats["migrated"] += 1

        except Exception as e:
            logger.error(f"Error migrating {fu.id}: {e}")
            stats["errors"] += 1

    if not dry_run:
        session.commit()

    return stats


def main():
    parser = argparse.ArgumentParser(description="Migrate nurturing data from JSON to PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated")
    parser.add_argument("--creator", type=str, help="Only migrate specific creator")
    args = parser.parse_args()

    # Check database connection
    if SessionLocal is None:
        logger.error("DATABASE_URL not configured. Set the environment variable and try again.")
        sys.exit(1)

    # Get files to migrate
    files = get_json_files(args.creator)
    if not files:
        logger.info("No JSON files found to migrate")
        sys.exit(0)

    logger.info(f"Found {len(files)} creator(s) to migrate")
    if args.dry_run:
        logger.info("DRY RUN - no changes will be made")

    # Migrate each creator
    total_stats = {
        "total": 0,
        "migrated": 0,
        "skipped": 0,
        "errors": 0
    }

    session = SessionLocal()
    try:
        for creator_id, file_path in files:
            logger.info(f"\nMigrating {creator_id}...")
            followups = load_json_followups(file_path)

            if not followups:
                logger.warning(f"No followups found in {file_path}")
                continue

            stats = migrate_creator(session, creator_id, followups, args.dry_run)

            logger.info(f"  Total: {stats['total']}")
            logger.info(f"  Migrated: {stats['migrated']}")
            logger.info(f"  Skipped (already exists): {stats['skipped']}")
            logger.info(f"  Errors: {stats['errors']}")

            # Accumulate totals
            for key in total_stats:
                total_stats[key] += stats[key]

    finally:
        session.close()

    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 50)
    logger.info(f"Total records: {total_stats['total']}")
    logger.info(f"Migrated: {total_stats['migrated']}")
    logger.info(f"Skipped: {total_stats['skipped']}")
    logger.info(f"Errors: {total_stats['errors']}")

    if args.dry_run:
        logger.info("\nThis was a DRY RUN. Run without --dry-run to actually migrate.")
    else:
        logger.info("\nMigration complete!")
        logger.info("To enable DB storage, set: NURTURING_USE_DB=true")


if __name__ == "__main__":
    main()
