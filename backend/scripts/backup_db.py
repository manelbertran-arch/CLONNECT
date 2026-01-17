#!/usr/bin/env python3
"""
Database Backup Script for Clonnect
Exports critical data to JSON files for disaster recovery.

Usage:
    python scripts/backup_db.py                    # Full backup
    python scripts/backup_db.py --creators-only    # Only creators and config
    python scripts/backup_db.py --output /path     # Custom output directory

The script exports:
- creators (config, tokens, settings)
- leads (with scores and status)
- products (catalog)
- messages (conversation history)
- booking_links (calendar config)

Backups are stored in data/backups/{timestamp}/ by default.
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_database_url():
    """Get database URL from environment"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable not set")
    return db_url


def export_table_to_json(session, table_name: str, output_dir: Path, limit: int = None) -> int:
    """Export a table to JSON file"""
    try:
        query = f"SELECT * FROM {table_name}"
        if limit:
            query += f" LIMIT {limit}"

        result = session.execute(text(query))
        rows = result.fetchall()
        columns = result.keys()

        data = []
        for row in rows:
            row_dict = {}
            for i, col in enumerate(columns):
                value = row[i]
                # Handle datetime serialization
                if hasattr(value, 'isoformat'):
                    value = value.isoformat()
                # Handle UUID serialization
                elif hasattr(value, 'hex'):
                    value = str(value)
                row_dict[col] = value
            data.append(row_dict)

        output_file = output_dir / f"{table_name}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

        logger.info(f"Exported {len(data)} rows from {table_name}")
        return len(data)

    except Exception as e:
        logger.error(f"Error exporting {table_name}: {e}")
        return 0


def run_backup(output_base: str = None, creators_only: bool = False):
    """Run database backup"""

    # Setup output directory
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if output_base:
        output_dir = Path(output_base) / timestamp
    else:
        output_dir = Path("data/backups") / timestamp

    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Backup directory: {output_dir}")

    # Connect to database
    db_url = get_database_url()
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Tables to backup
        if creators_only:
            tables = [
                "creators",
                "products",
                "booking_links",
                "nurturing_sequences",
                "knowledge_base",
            ]
        else:
            tables = [
                # Core tables (always backup)
                "creators",
                "products",
                "leads",
                "booking_links",
                "nurturing_sequences",
                "knowledge_base",
                "tone_profiles",
                # Activity tables
                "lead_activities",
                "lead_tasks",
                "calendar_bookings",
                # Messages (can be large)
                "messages",
            ]

        stats = {"timestamp": timestamp, "tables": {}}

        for table in tables:
            try:
                count = export_table_to_json(session, table, output_dir)
                stats["tables"][table] = count
            except Exception as e:
                logger.error(f"Failed to backup {table}: {e}")
                stats["tables"][table] = f"ERROR: {e}"

        # Save backup metadata
        meta_file = output_dir / "_backup_meta.json"
        with open(meta_file, 'w') as f:
            json.dump({
                "timestamp": timestamp,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "creators_only": creators_only,
                "stats": stats
            }, f, indent=2)

        logger.info(f"Backup completed: {output_dir}")
        logger.info(f"Stats: {json.dumps(stats['tables'], indent=2)}")

        return output_dir

    finally:
        session.close()


def restore_table_from_json(session, table_name: str, json_file: Path) -> int:
    """Restore a table from JSON file (CAREFUL: Replaces existing data!)"""
    logger.warning(f"Restoring {table_name} from {json_file} - This will replace existing data!")

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not data:
        logger.info(f"No data to restore for {table_name}")
        return 0

    # This is a simplified restore - for production use proper upsert logic
    # or database-level restore tools (pg_restore)
    logger.info(f"Would restore {len(data)} rows to {table_name}")
    logger.info("Use pg_restore or manual SQL for actual restore")

    return len(data)


def list_backups(backup_dir: str = "data/backups"):
    """List available backups"""
    backup_path = Path(backup_dir)

    if not backup_path.exists():
        logger.info("No backups found")
        return []

    backups = []
    for item in sorted(backup_path.iterdir(), reverse=True):
        if item.is_dir():
            meta_file = item / "_backup_meta.json"
            if meta_file.exists():
                with open(meta_file) as f:
                    meta = json.load(f)
                backups.append({
                    "dir": str(item),
                    "timestamp": meta.get("timestamp"),
                    "created_at": meta.get("created_at"),
                    "tables": list(meta.get("stats", {}).get("tables", {}).keys())
                })

    return backups


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clonnect Database Backup")
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--creators-only", action="store_true", help="Only backup creator config")
    parser.add_argument("--list", action="store_true", help="List available backups")

    args = parser.parse_args()

    if args.list:
        backups = list_backups()
        print(json.dumps(backups, indent=2))
    else:
        run_backup(output_base=args.output, creators_only=args.creators_only)
