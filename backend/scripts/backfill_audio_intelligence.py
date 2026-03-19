"""Backfill existing audio messages with the 4-layer intelligence pipeline.

Processes messages that have raw transcription but no audio_intel structured data.
Catches BOTH formats:
- Instagram: msg_metadata.transcript_raw
- WhatsApp:  msg_metadata.transcription

Usage:
    railway run python3.11 scripts/backfill_audio_intelligence.py [--limit N] [--dry-run]
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


async def backfill(limit: int = 50, dry_run: bool = False, force: bool = False):
    """Reprocess audio messages through 4-layer pipeline."""
    from sqlalchemy import text

    from api.database import SessionLocal
    from services.audio_intelligence import get_audio_intelligence

    db = SessionLocal()
    service = get_audio_intelligence()

    try:
        # Find audio messages with transcription
        # Covers both WhatsApp (transcription) and Instagram (transcript_raw)
        # --force: reprocess even if audio_intel already exists
        filter_clause = "" if force else "AND msg_metadata->'audio_intel' IS NULL"
        rows = db.execute(
            text(f"""
            SELECT m.id, m.content, m.role, m.msg_metadata, m.created_at
            FROM messages m
            WHERE msg_metadata->>'type' = 'audio'
              AND (
                msg_metadata->>'transcription' IS NOT NULL
                OR msg_metadata->>'transcript_raw' IS NOT NULL
              )
              {filter_clause}
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
            content = row[1]
            role = row[2]
            metadata = row[3] if isinstance(row[3], dict) else json.loads(row[3] or "{}")
            created_at = row[4]

            # Extract raw text from whichever field exists
            raw_text = (
                metadata.get("transcript_raw")
                or metadata.get("transcription")
                or ""
            ).strip()

            if not raw_text:
                continue

            platform = metadata.get("platform", "unknown")

            if dry_run:
                logger.info(
                    "[DRY RUN] %s | %s | role=%s | %d chars | %s",
                    msg_id, platform, role, len(raw_text), str(created_at)[:19],
                )
                logger.info("  RAW: %s", raw_text[:120])
                processed += 1
                continue

            try:
                # Use stored language from audio_intel or detected_language, fallback to "es"
                lang = (
                    metadata.get("detected_language")
                    or (metadata.get("audio_intel") or {}).get("language")
                    or "es"
                )
                result = await service.process(
                    raw_text=raw_text,
                    duration_seconds=int(metadata.get("duration", 0)),
                    language=lang,
                    role=role or "user",
                )

                # Preserve original transcription as backup
                if not metadata.get("transcript_raw"):
                    metadata["transcript_raw"] = raw_text

                # Update metadata with structured data
                metadata.update(result.to_legacy_fields())
                metadata["audio_intel"] = result.to_metadata()

                db.execute(
                    text("""
                    UPDATE messages
                    SET msg_metadata = cast(:meta as jsonb)
                    WHERE id = :id
                    """),
                    {"meta": json.dumps(metadata), "id": str(msg_id)},
                )

                processed += 1
                logger.info(
                    "[Backfill] %s (%s): Raw:%d → Clean:%d → Summary:%d (%dms)",
                    msg_id,
                    platform,
                    len(raw_text),
                    len(result.clean_text),
                    len(result.summary),
                    result.processing_time_ms,
                )
                logger.info("  SUMMARY: %s", result.summary[:150])

            except Exception as e:
                errors += 1
                logger.error("[Backfill] %s failed: %s", msg_id, e)

        if not dry_run and processed > 0:
            db.commit()
            logger.info("Committed %d updates to database", processed)

        logger.info(
            "Backfill complete: %d processed, %d errors, %d total found",
            processed, errors, len(rows),
        )
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Backfill audio intelligence")
    parser.add_argument("--limit", type=int, default=50, help="Max messages to process")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    parser.add_argument("--force", action="store_true", help="Reprocess even if audio_intel exists")
    args = parser.parse_args()

    asyncio.run(backfill(limit=args.limit, dry_run=args.dry_run, force=args.force))
