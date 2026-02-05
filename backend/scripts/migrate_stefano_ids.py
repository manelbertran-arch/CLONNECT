#!/usr/bin/env python3
"""
Migration script to add Instagram IDs to stefano_bonanno.

This script:
1. Sets the primary instagram_user_id and instagram_page_id
2. Adds the legacy ID to instagram_additional_ids
3. Clears the routing cache

Run with:
    DATABASE_URL=postgresql://... python scripts/migrate_stefano_ids.py
"""

import os
import sys

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def migrate_stefano():
    """Migrate Stefano's Instagram IDs."""
    from api.database import SessionLocal
    from api.models import Creator

    # IDs to set
    PRIMARY_ID = "25734915742865411"  # Current Instagram User ID
    LEGACY_ID = "17841400506734756"  # Legacy ID that webhooks are using
    CREATOR_NAME = "stefano_bonanno"

    session = SessionLocal()
    try:
        # Find creator
        creator = session.query(Creator).filter_by(name=CREATOR_NAME).first()

        if not creator:
            print(f"ERROR: Creator '{CREATOR_NAME}' not found")
            return False

        # Store old values
        old_values = {
            "instagram_user_id": creator.instagram_user_id,
            "instagram_page_id": creator.instagram_page_id,
            "instagram_additional_ids": creator.instagram_additional_ids,
        }

        print(f"Found creator: {creator.name} (id: {creator.id})")
        print(f"Old values: {old_values}")

        # Update primary IDs
        creator.instagram_user_id = PRIMARY_ID
        creator.instagram_page_id = PRIMARY_ID

        # Add legacy ID to additional_ids
        additional_ids = creator.instagram_additional_ids or []
        if LEGACY_ID not in additional_ids:
            additional_ids.append(LEGACY_ID)
        creator.instagram_additional_ids = additional_ids

        # Commit changes
        session.commit()

        # Verify
        session.refresh(creator)
        new_values = {
            "instagram_user_id": creator.instagram_user_id,
            "instagram_page_id": creator.instagram_page_id,
            "instagram_additional_ids": creator.instagram_additional_ids,
        }

        print(f"New values: {new_values}")
        print("Migration completed successfully!")

        # Clear routing cache
        try:
            from core.webhook_routing import clear_routing_cache

            clear_routing_cache()
            print("Routing cache cleared")
        except Exception as e:
            print(f"Warning: Could not clear cache: {e}")

        return True

    except Exception as e:
        print(f"ERROR: {e}")
        session.rollback()
        return False

    finally:
        session.close()


if __name__ == "__main__":
    print("=" * 50)
    print("Migrating Stefano's Instagram IDs")
    print("=" * 50)

    success = migrate_stefano()

    if success:
        print("\n✅ Migration successful!")
        print("\nNext steps:")
        print("1. Deploy to production")
        print("2. Run: python scripts/migrate_stefano_ids.py")
        print("3. Test webhook by sending a DM")
    else:
        print("\n❌ Migration failed")
        sys.exit(1)
