"""Backfill existing audio messages with the 4-layer intelligence pipeline.

Processes messages that have raw transcription but no audio_intel structured data.

Usage:
    python scripts/backfill_audio_intelligence.py [--limit N] [--dry-run]
"""

import asyncio
import json
import logging
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Force-enable audio intelligence for backfill (before importing service)
os.environ["ENABLE_AUDIO_INTELLIGENCE"] = "true"

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


async def backfill(limit: int = 50, dry_run: bool = False):
    """Reprocess audio messages through 4-layer pipeline."""
    from sqlalchemy import text

    from api.database import SessionLocal
    from services.audio_intelligence import get_audio_intelligence

    db = SessionLocal()
    service = get_audio_intelligence()

    try:
        # Find audio messages that need processing
        rows = db.execute(
            text("""
            SELECT m.id, m.content, m.role, m.msg_metadata
            FROM messages m
            WHERE m.msg_metadata->>'type' = 'audio'
              AND m.msg_metadata->>'transcript_raw' IS NOT NULL
              AND m.msg_metadata->>'audio_intel' IS NULL
            ORDER BY m.created_at DESC
            LIMIT :limit
            """),
            {"limit": limit},
        ).fetchall()

        logger.info("Found %d audio messages to backfill", len(rows))
        processed = 0
        errors = 0

        for row in rows:
            msg_id = row[0]
            role = row[2]
            metadata = row[3] if isinstance(row[3], dict) else json.loads(row[3] or "{}")

            raw_text = metadata.get("transcript_raw", "")
            if not raw_text:
                continue

            if dry_run:
                logger.info("[DRY RUN] Would process %s (role=%s, %d chars)", msg_id, role, len(raw_text))
                processed += 1
                continue

            try:
                result = await service.process(
                    raw_text=raw_text,
                    duration_seconds=int(metadata.get("duration", 0)),
                    language="es",
                    role=role or "user",
                )

                # Update metadata with new fields
                metadata.update(result.to_legacy_fields())
                metadata["audio_intel"] = result.to_metadata()

                db.execute(
                    text("""
                    UPDATE messages
                    SET msg_metadata = :meta
                    WHERE id = :id
                    """),
                    {"meta": json.dumps(metadata), "id": str(msg_id)},
                )

                processed += 1
                logger.info(
                    "[Backfill] %s: %d chars → summary: '%s' (%dms)",
                    msg_id,
                    len(raw_text),
                    result.summary[:60],
                    result.processing_time_ms,
                )
            except Exception as e:
                errors += 1
                logger.error("[Backfill] %s failed: %s", msg_id, e)

        if not dry_run:
            db.commit()

        logger.info(
            "Backfill complete: %d processed, %d errors, %d total",
            processed, errors, len(rows),
        )
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Backfill audio intelligence")
    parser.add_argument("--limit", type=int, default=50, help="Max messages to process")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    args = parser.parse_args()

    asyncio.run(backfill(limit=args.limit, dry_run=args.dry_run))
