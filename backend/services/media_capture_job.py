"""
Periodic media capture job.

Scans messages with temporary CDN URLs that are missing a permanent backup
(thumbnail_base64 or permanent_url) and captures them before the CDN link
expires. Instagram CDN URLs typically expire after ~24 hours.

Runs every 6 hours. Processes up to 100 messages per run to avoid
overloading the event loop and hitting API rate limits.

Uses the existing media_capture_service.py for actual download + encoding.
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

logger = logging.getLogger(__name__)

ENABLE_MEDIA_CAPTURE = os.getenv("ENABLE_MEDIA_CAPTURE", "true").lower() == "true"
MEDIA_CAPTURE_INTERVAL = int(os.getenv("MEDIA_CAPTURE_INTERVAL_SECONDS", "21600"))  # 6h
MEDIA_CAPTURE_INITIAL_DELAY = int(os.getenv("MEDIA_CAPTURE_INITIAL_DELAY", "180"))  # 3min
MAX_MESSAGES_PER_RUN = 100
RATE_LIMIT_DELAY = 0.5  # seconds between downloads


def _parse_cdn_expiry(url: str) -> datetime | None:
    """Extract expiry timestamp from CDN URL's oe= hex parameter."""
    if not url:
        return None
    match = re.search(r"[?&]oe=([0-9a-fA-F]+)", url)
    if not match:
        return None
    try:
        ts = int(match.group(1), 16)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except (ValueError, OSError):
        return None


def _capture_sync() -> Dict[str, Any]:
    """
    Synchronous capture logic. Runs in asyncio.to_thread() to avoid
    blocking the event loop.
    """
    import json

    import requests
    from api.database import SessionLocal
    from sqlalchemy import text

    session = SessionLocal()
    captured = 0
    skipped = 0
    expired = 0
    errors = 0

    try:
        # Find messages with CDN URLs that lack a permanent backup.
        # Target: msg_metadata has 'url' with CDN domain but no thumbnail_base64.
        rows = session.execute(
            text("""
                SELECT m.id, m.msg_metadata
                FROM messages m
                WHERE m.msg_metadata IS NOT NULL
                  AND m.msg_metadata::text LIKE '%lookaside.fbsbx.com%'
                  AND NOT m.msg_metadata::text LIKE '%thumbnail_base64%'
                  AND NOT m.msg_metadata::text LIKE '%permanent_url%'
                ORDER BY m.created_at DESC
                LIMIT :lim
            """),
            {"lim": MAX_MESSAGES_PER_RUN},
        ).fetchall()

        if not rows:
            logger.info("[MEDIA_CAPTURE] No messages need media capture")
            return {"captured": 0, "skipped": 0, "expired": 0, "errors": 0}

        logger.info(f"[MEDIA_CAPTURE] Found {len(rows)} messages to process")

        for msg_id, metadata in rows:
            meta = metadata if isinstance(metadata, dict) else {}
            if isinstance(metadata, str):
                try:
                    meta = json.loads(metadata) if metadata else {}
                except (json.JSONDecodeError, TypeError):
                    meta = {}

            url = meta.get("url", "")
            if not url:
                skipped += 1
                continue

            # Check if CDN URL already expired
            expiry = _parse_cdn_expiry(url)
            if expiry and expiry < datetime.now(timezone.utc):
                expired += 1
                continue

            # Download and encode as base64
            try:
                resp = requests.get(url, timeout=15, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ClonnectBot/1.0)"
                })
                if resp.status_code == 200:
                    content = resp.content
                    # Skip files > 5MB
                    if len(content) > 5 * 1024 * 1024:
                        skipped += 1
                        continue

                    content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
                    import base64 as b64mod
                    b64 = b64mod.b64encode(content).decode("utf-8")
                    meta["thumbnail_base64"] = f"data:{content_type};base64,{b64}"

                    session.execute(
                        text("UPDATE messages SET msg_metadata = :meta WHERE id = :mid"),
                        {"meta": json.dumps(meta), "mid": str(msg_id)},
                    )
                    session.commit()
                    captured += 1
                elif resp.status_code in (403, 404, 410):
                    # CDN URL expired or forbidden
                    expired += 1
                else:
                    errors += 1
                    logger.warning(
                        f"[MEDIA_CAPTURE] HTTP {resp.status_code} for msg {msg_id}"
                    )
            except requests.exceptions.Timeout:
                errors += 1
            except Exception as e:
                errors += 1
                logger.warning(f"[MEDIA_CAPTURE] Error capturing msg {msg_id}: {e}")

            import time
            time.sleep(RATE_LIMIT_DELAY)

    except Exception as e:
        logger.error(f"[MEDIA_CAPTURE] Job error: {e}")
    finally:
        session.close()

    return {
        "captured": captured,
        "skipped": skipped,
        "expired": expired,
        "errors": errors,
    }


async def media_capture_job():
    """Async wrapper - runs sync capture in a thread to avoid blocking."""
    if not ENABLE_MEDIA_CAPTURE:
        logger.info("[MEDIA_CAPTURE] Disabled via ENABLE_MEDIA_CAPTURE=false")
        return {}

    logger.info("[MEDIA_CAPTURE] Starting periodic media capture...")
    stats = await asyncio.to_thread(_capture_sync)
    logger.info(
        f"[MEDIA_CAPTURE] Done: {stats['captured']} captured, "
        f"{stats['expired']} CDN expired, "
        f"{stats['skipped']} skipped, "
        f"{stats['errors']} errors"
    )
    return stats
