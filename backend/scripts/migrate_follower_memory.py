#!/usr/bin/env python3
"""
Migrate Follower Memory from JSON files to PostgreSQL.

This script is idempotent - can be run multiple times safely.
It will skip records that already exist in the database.

Usage:
    python -m scripts.migrate_follower_memory
    python -m scripts.migrate_follower_memory --dry-run
    python -m scripts.migrate_follower_memory --creator fitpack_global
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.database import SessionLocal
from api.models import FollowerMemoryDB


def migrate_follower(db, creator_id: str, follower_id: str, data: dict, dry_run: bool = False) -> tuple:
    """
    Migrate a single follower record.

    Returns: (status, message)
        status: 'created', 'skipped', 'updated', 'error'
    """
    try:
        # Check if already exists
        existing = db.query(FollowerMemoryDB).filter(
            FollowerMemoryDB.creator_id == creator_id,
            FollowerMemoryDB.follower_id == follower_id
        ).first()

        if existing:
            return ('skipped', f"Already exists: {creator_id}/{follower_id}")

        if dry_run:
            return ('dry_run', f"Would create: {creator_id}/{follower_id}")

        # Create new record
        record = FollowerMemoryDB(
            creator_id=creator_id,
            follower_id=follower_id,
            username=data.get('username', ''),
            name=data.get('name', ''),
            first_contact=data.get('first_contact', ''),
            last_contact=data.get('last_contact', ''),
            total_messages=data.get('total_messages', 0),
            interests=data.get('interests', []),
            products_discussed=data.get('products_discussed', []),
            objections_raised=data.get('objections_raised', []),
            purchase_intent_score=data.get('purchase_intent_score', 0.0),
            is_lead=data.get('is_lead', False),
            is_customer=data.get('is_customer', False),
            status=data.get('status', 'new'),
            preferred_language=data.get('preferred_language', 'es'),
            last_messages=data.get('last_messages', [])[-20:],
            links_sent_count=data.get('links_sent_count', 0),
            last_link_message_num=data.get('last_link_message_num', 0),
            objections_handled=data.get('objections_handled', []),
            arguments_used=data.get('arguments_used', []),
            greeting_variant_index=data.get('greeting_variant_index', 0),
            last_greeting_style=data.get('last_greeting_style', ''),
            last_emojis_used=data.get('last_emojis_used', [])[-5:],
            messages_since_name_used=data.get('messages_since_name_used', 0),
            alternative_contact=data.get('alternative_contact', ''),
            alternative_contact_type=data.get('alternative_contact_type', ''),
            contact_requested=data.get('contact_requested', False),
        )
        db.add(record)
        return ('created', f"Created: {creator_id}/{follower_id}")

    except Exception as e:
        return ('error', f"Error migrating {creator_id}/{follower_id}: {e}")


def migrate_creator(db, creator_dir: Path, dry_run: bool = False) -> dict:
    """Migrate all followers for a single creator."""
    creator_id = creator_dir.name
    stats = {'created': 0, 'skipped': 0, 'errors': 0, 'dry_run': 0}

    # Find all JSON files
    json_files = list(creator_dir.glob("*.json"))

    for json_file in json_files:
        if json_file.name == '.gitkeep':
            continue

        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            follower_id = data.get('follower_id', json_file.stem)

            status, message = migrate_follower(db, creator_id, follower_id, data, dry_run)

            if status == 'created':
                stats['created'] += 1
                print(f"  ✅ {message}")
            elif status == 'skipped':
                stats['skipped'] += 1
                print(f"  ⏭️  {message}")
            elif status == 'dry_run':
                stats['dry_run'] += 1
                print(f"  🔍 {message}")
            else:
                stats['errors'] += 1
                print(f"  ❌ {message}")

        except json.JSONDecodeError as e:
            stats['errors'] += 1
            print(f"  ❌ Invalid JSON in {json_file}: {e}")
        except Exception as e:
            stats['errors'] += 1
            print(f"  ❌ Error reading {json_file}: {e}")

    return stats


def main():
    parser = argparse.ArgumentParser(description='Migrate Follower Memory from JSON to PostgreSQL')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be migrated without making changes')
    parser.add_argument('--creator', type=str, help='Migrate only specific creator')
    parser.add_argument('--data-dir', type=str, default='data/followers', help='Path to followers data directory')
    args = parser.parse_args()

    print("=" * 60)
    print("Follower Memory Migration: JSON → PostgreSQL")
    print("=" * 60)

    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
    print()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"❌ Data directory not found: {data_dir}")
        sys.exit(1)

    # Get list of creator directories
    if args.creator:
        creator_dirs = [data_dir / args.creator]
        if not creator_dirs[0].exists():
            print(f"❌ Creator directory not found: {creator_dirs[0]}")
            sys.exit(1)
    else:
        creator_dirs = [d for d in data_dir.iterdir() if d.is_dir()]

    print(f"📁 Found {len(creator_dirs)} creator directories")
    print()

    # Initialize database session
    db = SessionLocal()

    total_stats = {'created': 0, 'skipped': 0, 'errors': 0, 'dry_run': 0}

    try:
        for creator_dir in sorted(creator_dirs):
            if creator_dir.name.startswith('.'):
                continue

            print(f"📦 Processing: {creator_dir.name}")
            stats = migrate_creator(db, creator_dir, args.dry_run)

            for key in total_stats:
                total_stats[key] += stats[key]

            if not args.dry_run:
                db.commit()
            print()

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()

    # Print summary
    print("=" * 60)
    print("Migration Summary")
    print("=" * 60)
    if args.dry_run:
        print(f"🔍 Would create: {total_stats['dry_run']}")
    else:
        print(f"✅ Created: {total_stats['created']}")
    print(f"⏭️  Skipped (already exist): {total_stats['skipped']}")
    print(f"❌ Errors: {total_stats['errors']}")
    print("=" * 60)

    if total_stats['errors'] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
