"""
One-off migration: Upload oversized base64 media to Cloudinary.

Finds messages where thumbnail_base64 > 5MB (too large for API response),
uploads to Cloudinary, stores permanent_url, and clears the base64 from DB.

Usage:
    CLOUDINARY_URL=cloudinary://key:secret@cloud python scripts/migrate_base64_to_cloudinary.py [--dry-run]
"""

import asyncio
import base64
import json
import os
import sys
import tempfile
import time

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import cloudinary
import cloudinary.uploader
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL")
CLOUDINARY_URL = os.getenv("CLOUDINARY_URL")
BASE64_THRESHOLD = int(os.getenv("BASE64_THRESHOLD", "0"))  # 0 = migrate ALL remaining base64
DRY_RUN = "--dry-run" in sys.argv


def configure_cloudinary():
    """Configure Cloudinary from CLOUDINARY_URL env var."""
    if not CLOUDINARY_URL:
        print("ERROR: CLOUDINARY_URL not set. Pass it as env var.")
        sys.exit(1)
    cloudinary.config()
    print(f"Cloudinary configured: cloud_name={cloudinary.config().cloud_name}")


def get_oversized_messages(engine):
    """Find messages with base64 > threshold."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT m.id,
                   m.msg_metadata->>'type' as media_type,
                   LENGTH(m.msg_metadata->>'thumbnail_base64') as base64_len,
                   m.msg_metadata->>'thumbnail_base64' as thumbnail_base64,
                   m.msg_metadata->>'permanent_url' as permanent_url,
                   m.msg_metadata->>'cloudinary_id' as cloudinary_id,
                   l.creator_id
            FROM messages m
            JOIN leads l ON m.lead_id = l.id
            WHERE m.msg_metadata IS NOT NULL
              AND m.msg_metadata->>'thumbnail_base64' IS NOT NULL
              AND LENGTH(m.msg_metadata->>'thumbnail_base64') > :threshold
              AND m.msg_metadata->>'cloudinary_id' IS NULL
            ORDER BY LENGTH(m.msg_metadata->>'thumbnail_base64') ASC
        """), {"threshold": BASE64_THRESHOLD})
        return [dict(row._mapping) for row in result]


def upload_to_cloudinary(base64_data: str, media_type: str, creator_id: str, msg_id: str):
    """Upload base64 data to Cloudinary, return (url, public_id) or (None, error)."""
    # Determine resource type
    is_video = "video" in base64_data[:30]
    resource_type = "video" if is_video else "image"

    # Strip data URI prefix for Cloudinary
    # Cloudinary accepts data URIs directly
    try:
        result = cloudinary.uploader.upload(
            base64_data,
            resource_type=resource_type,
            folder=f"clonnect/{creator_id}/media",
            public_id=f"migrated_{msg_id[:8]}",
            tags=["instagram", "migrated", f"creator_{creator_id}"],
            overwrite=False,
            timeout=120,
        )
        return result.get("secure_url"), result.get("public_id"), None
    except Exception as e:
        return None, None, str(e)


def update_message_metadata(engine, msg_id: str, cloudinary_url: str, public_id: str):
    """Update message metadata with Cloudinary URL and remove base64."""
    with engine.connect() as conn:
        conn.execute(text("""
            UPDATE messages
            SET msg_metadata = msg_metadata
                || jsonb_build_object(
                    'permanent_url', :url,
                    'cloudinary_id', :public_id
                )
                - 'thumbnail_base64'
            WHERE id = :msg_id
        """), {"url": cloudinary_url, "public_id": public_id, "msg_id": msg_id})
        conn.commit()


def main():
    print(f"{'[DRY RUN] ' if DRY_RUN else ''}Base64 → Cloudinary Migration")
    print(f"Threshold: {BASE64_THRESHOLD / 1_000_000:.1f} MB")
    print()

    configure_cloudinary()

    engine = create_engine(DATABASE_URL)
    messages = get_oversized_messages(engine)

    print(f"Found {len(messages)} messages with base64 > {BASE64_THRESHOLD / 1_000_000:.1f} MB")
    if not messages:
        print("Nothing to migrate.")
        return

    total_bytes = sum(m["base64_len"] for m in messages)
    print(f"Total base64 data: {total_bytes / 1_000_000:.1f} MB")
    print()

    uploaded = 0
    failed = 0
    skipped = 0

    for i, msg in enumerate(messages, 1):
        msg_id = str(msg["id"])
        media_type = msg["media_type"]
        creator_id = str(msg["creator_id"])
        size_mb = msg["base64_len"] / 1_000_000

        print(f"[{i}/{len(messages)}] {msg_id[:8]}... ({media_type}, {size_mb:.1f} MB) ", end="", flush=True)

        if msg.get("cloudinary_id"):
            print("SKIP (already on Cloudinary)")
            skipped += 1
            continue

        if DRY_RUN:
            print("DRY RUN — would upload")
            continue

        url, public_id, error = upload_to_cloudinary(
            msg["thumbnail_base64"],
            media_type,
            creator_id,
            msg_id,
        )

        if error:
            print(f"FAILED: {error}")
            failed += 1
            # Brief pause on error to avoid rate limits
            time.sleep(2)
            continue

        # Update DB: set permanent_url, remove base64
        update_message_metadata(engine, msg_id, url, public_id)
        uploaded += 1
        print(f"OK → {public_id}")

        # Rate limit: Cloudinary allows ~500 uploads/hour on free plan
        time.sleep(1)

    print()
    print(f"Done: {uploaded} uploaded, {failed} failed, {skipped} skipped")
    if uploaded > 0:
        saved_mb = sum(
            m["base64_len"]
            for m in messages
            if not m.get("cloudinary_id")
        ) / 1_000_000
        print(f"DB space freed: ~{saved_mb:.0f} MB (base64 removed from msg_metadata)")


if __name__ == "__main__":
    main()
