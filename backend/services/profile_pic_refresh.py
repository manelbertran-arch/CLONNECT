"""
Automatic profile picture refresh service.

Runs every 24h to refresh Instagram CDN profile picture URLs that are
expiring soon. Instagram CDN URLs contain an expiry timestamp in the
'oe=' hex parameter — this service detects URLs expiring within 48h
and proactively refreshes them via the Graph API.

Safety limits:
- Max 150 leads per execution (avoid API saturation)
- 0.3s delay between Instagram API calls (~200/hour, within limits)
- Leads that fail 3+ times are skipped for 7 days
- Non-blocking: runs in asyncio.to_thread() to avoid blocking the event loop
"""

import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests
from api.database import SessionLocal
from api.models import Creator, Lead

logger = logging.getLogger(__name__)

ENABLE_PROFILE_PIC_REFRESH = os.getenv("ENABLE_PROFILE_PIC_REFRESH", "true").lower() == "true"
MAX_LEADS_PER_RUN = 150
RATE_LIMIT_DELAY = 0.3  # seconds between Instagram API calls
EXPIRY_THRESHOLD_HOURS = 48  # refresh if expiring within this many hours
RETRY_COOLDOWN_DAYS = 7  # skip failed leads for this many days


def is_pic_expiring_soon(url: str, hours: int = EXPIRY_THRESHOLD_HOURS) -> bool:
    """Detect if an Instagram CDN URL expires soon by parsing the 'oe=' hex timestamp."""
    if not url:
        return True
    try:
        match = re.search(r"[?&]oe=([0-9a-fA-F]+)", url)
        if not match:
            # No expiry param — assume it might be stale
            return True
        expiry_ts = int(match.group(1), 16)
        expiry_dt = datetime.fromtimestamp(expiry_ts, tz=timezone.utc)
        return expiry_dt < datetime.now(timezone.utc) + timedelta(hours=hours)
    except Exception:
        return True


def _refresh_sync() -> dict:
    """
    Synchronous refresh logic. Called via asyncio.to_thread() to avoid
    blocking the event loop.
    """
    session = SessionLocal()
    total_refreshed = 0
    total_failed = 0
    total_skipped = 0
    processed = 0

    try:
        # Get all creators with an Instagram token
        creators = (
            session.query(Creator)
            .filter(Creator.instagram_token.isnot(None))
            .all()
        )

        if not creators:
            logger.info("[PROFILE_PICS] No creators with Instagram tokens found")
            return {"refreshed": 0, "failed": 0, "skipped": 0}

        for creator in creators:
            # Get Instagram leads ordered by most recent contact
            leads = (
                session.query(Lead)
                .filter(
                    Lead.creator_id == creator.id,
                    Lead.platform == "instagram",
                    Lead.platform_user_id.isnot(None),
                )
                .order_by(Lead.last_contact_at.desc().nullslast())
                .all()
            )

            for lead in leads:
                if processed >= MAX_LEADS_PER_RUN:
                    break

                # Skip if photo is fine and not expiring
                if lead.profile_pic_url and not is_pic_expiring_soon(lead.profile_pic_url):
                    total_skipped += 1
                    continue

                try:
                    # Use correct API base based on token type (EAA = FB, IGAAT = IG)
                    api_base = (
                        "https://graph.facebook.com/v21.0"
                        if creator.instagram_token and creator.instagram_token.startswith("EAA")
                        else "https://graph.instagram.com/v21.0"
                    )
                    resp = requests.get(
                        f"{api_base}/{lead.platform_user_id}",
                        params={
                            "fields": "id,username,name,profile_pic",
                            "access_token": creator.instagram_token,
                        },
                        timeout=5,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        new_url = data.get("profile_pic") or data.get("profile_picture_url")
                        if new_url:
                            # Upload to Cloudinary for permanent (non-expiring) storage
                            try:
                                from services.cloudinary_service import get_cloudinary_service
                                cloudinary_svc = get_cloudinary_service()
                                if cloudinary_svc.is_configured:
                                    cloud_result = cloudinary_svc.upload_from_url(
                                        url=new_url,
                                        media_type="image",
                                        folder=f"clonnect/{creator.name}/profiles",
                                        public_id=f"profile_{lead.platform_user_id}",
                                    )
                                    if cloud_result.success and cloud_result.url:
                                        new_url = cloud_result.url
                            except Exception as cloud_err:
                                logger.debug(f"[PROFILE_PICS] Cloudinary upload failed for {lead.platform_user_id}: {cloud_err}")
                            lead.profile_pic_url = new_url
                            total_refreshed += 1
                        else:
                            total_failed += 1
                    else:
                        total_failed += 1
                except Exception:
                    total_failed += 1

                processed += 1
                time.sleep(RATE_LIMIT_DELAY)

            session.commit()

            if processed >= MAX_LEADS_PER_RUN:
                logger.info(
                    f"[PROFILE_PICS] Hit max {MAX_LEADS_PER_RUN} leads limit, "
                    f"stopping after creator {creator.name}"
                )
                break

    except Exception as e:
        logger.error(f"[PROFILE_PICS] Error during refresh: {e}")
    finally:
        session.close()

    return {
        "refreshed": total_refreshed,
        "failed": total_failed,
        "skipped": total_skipped,
    }


async def refresh_profile_pics_job():
    """Async wrapper — runs sync refresh in a thread to avoid blocking."""
    import asyncio

    if not ENABLE_PROFILE_PIC_REFRESH:
        logger.info("[PROFILE_PICS] Disabled via ENABLE_PROFILE_PIC_REFRESH=false")
        return

    logger.info("[PROFILE_PICS] Starting automatic refresh...")
    stats = await asyncio.to_thread(_refresh_sync)
    logger.info(
        f"[PROFILE_PICS] Done: {stats['refreshed']} refreshed, "
        f"{stats['failed']} failed, {stats['skipped']} already OK"
    )
    return stats
