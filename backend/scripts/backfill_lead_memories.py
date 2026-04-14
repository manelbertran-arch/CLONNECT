#!/usr/bin/env python3
"""Backfill memories for leads affected by BUG-001 (ig_ prefix resolution failure).

These leads have messages post-Sprint 3 (2026-04-10) but 0 extracted memories
because _resolve_lead_uuid couldn't match "ig_XXXX" to "XXXX" in the DB.

Usage: source .env && python3 scripts/backfill_lead_memories.py [--dry-run]
"""
import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill_memories")


async def main():
    dry_run = "--dry-run" in sys.argv

    if not os.getenv("DATABASE_URL"):
        logger.error("DATABASE_URL not set — run: source .env && python3 scripts/backfill_lead_memories.py")
        sys.exit(1)

    # Force memory engine on for this script
    os.environ["ENABLE_MEMORY_ENGINE"] = "true"

    from api.database import SessionLocal
    from sqlalchemy import text

    # Step 1: Find affected leads (no ig_ prefix, no memories, has messages post-Sprint 3)
    session = SessionLocal()
    try:
        rows = session.execute(text("""
            SELECT l.id, l.platform_user_id, l.username, c.name as creator_name
            FROM leads l
            JOIN creators c ON l.creator_id = c.id
            WHERE c.name = 'iris_bertran'
              AND l.platform_user_id NOT LIKE 'ig_%%'
              AND NOT EXISTS (
                SELECT 1 FROM lead_memories lm
                WHERE lm.lead_id = l.id AND lm.is_active = true
              )
              AND EXISTS (
                SELECT 1 FROM messages m
                WHERE m.lead_id = l.id AND m.created_at >= '2026-04-10'
              )
        """)).fetchall()
    finally:
        session.close()

    logger.info("Found %d leads to backfill", len(rows))

    if dry_run:
        for r in rows:
            logger.info("  [DRY-RUN] lead=%s username=%s platform_uid=%s", r[0], r[2], r[1])
        logger.info("[DRY-RUN] Would backfill %d leads. Run without --dry-run to execute.", len(rows))
        return

    # Step 2: For each lead, load last 10 messages and run extraction
    from services.memory_engine import get_memory_engine

    engine = get_memory_engine()
    success = 0
    failed = 0

    for lead_uuid, platform_uid, username, creator_name in rows:
        try:
            # Load messages (pattern from cpe_generate_test_set.py:186-195)
            session = SessionLocal()
            try:
                msgs = session.execute(text("""
                    SELECT role, content FROM messages
                    WHERE lead_id = CAST(:lid AS uuid)
                      AND deleted_at IS NULL
                      AND content IS NOT NULL
                      AND length(content) > 1
                    ORDER BY created_at DESC
                    LIMIT 10
                """), {"lid": str(lead_uuid)}).fetchall()
            finally:
                session.close()

            if len(msgs) < 2:
                logger.info("  skip lead=%s (%s) — only %d messages", str(lead_uuid)[:8], username, len(msgs))
                continue

            # Format as role/content dicts (reversed to chronological order)
            conversation_msgs = [
                {"role": m.role, "content": m.content[:300]}
                for m in reversed(msgs)
            ]

            # Pass lead UUID directly (bypasses _resolve_lead_uuid prefix issue)
            result = await engine.add(creator_name, str(lead_uuid), conversation_msgs)
            logger.info("  backfill lead=%s (%s) — %d facts stored", str(lead_uuid)[:8], username, len(result))
            success += 1

            await asyncio.sleep(1.5)  # Rate limit LLM calls

        except Exception as e:
            logger.error("  FAILED lead=%s: %s", str(lead_uuid)[:8], e)
            failed += 1

    logger.info("Done: %d success, %d failed out of %d total", success, failed, len(rows))


if __name__ == "__main__":
    asyncio.run(main())
