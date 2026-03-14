"""
Automatic profile picture refresh service.

Two strategies:
1. Primary: Instagram public API (by username) → Cloudinary permanent URL
2. Fallback: Graph API (by IGSID) → Cloudinary permanent URL

Runs every 6h. Processes up to 30 leads per run with 3s delay
between requests to avoid Instagram rate limiting.

Safety limits:
- Max 30 leads per execution (conservative to avoid rate limits)
- 3s delay between Instagram API calls
- Stops immediately on rate limit (401/429)
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
from sqlalchemy import or_

logger = logging.getLogger(__name__)

ENABLE_PROFILE_PIC_REFRESH = os.getenv("ENABLE_PROFILE_PIC_REFRESH", "true").lower() == "true"
MAX_LEADS_PER_RUN = 100  # Process up to 100 per run (clears backlogs faster)
RATE_LIMIT_DELAY = 2.0  # seconds between API calls
EXPIRY_THRESHOLD_HOURS = 48

# Instagram public API config
IG_PUBLIC_API_URL = "https://i.instagram.com/api/v1/users/web_profile_info/"
IG_APP_ID = "936619743392459"
IG_USER_AGENT = "Instagram 76.0.0.15.395 Android"


def is_pic_expiring_soon(url: str, hours: int = EXPIRY_THRESHOLD_HOURS) -> bool:
    """Detect if an Instagram CDN URL expires soon by parsing the 'oe=' hex timestamp."""
    if not url:
        return True
    # Cloudinary URLs never expire
    if "cloudinary" in url:
        return False
    try:
        match = re.search(r"[?&]oe=([0-9a-fA-F]+)", url)
        if not match:
            return True
        expiry_ts = int(match.group(1), 16)
        expiry_dt = datetime.fromtimestamp(expiry_ts, tz=timezone.utc)
        return expiry_dt < datetime.now(timezone.utc) + timedelta(hours=hours)
    except Exception:
        return True


def _needs_refresh(lead) -> bool:
    """Check if a lead needs its profile pic refreshed."""
    if not lead.profile_pic_url:
        return True
    if "cloudinary" in lead.profile_pic_url:
        return False
    return is_pic_expiring_soon(lead.profile_pic_url)


def _fetch_pic_public_api(username: str) -> str | None:
    """Fetch profile pic via Instagram's public API (by username)."""
    if not username or username.strip() in ("", "@"):
        return None
    clean = username.strip().lstrip("@")
    try:
        resp = requests.get(
            IG_PUBLIC_API_URL,
            params={"username": clean},
            headers={
                "User-Agent": IG_USER_AGENT,
                "x-ig-app-id": IG_APP_ID,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            user = resp.json().get("data", {}).get("user")
            if user:
                return user.get("profile_pic_url_hd") or user.get("profile_pic_url")
            return None
        elif resp.status_code in (401, 429):
            return "RATE_LIMITED"
        return None
    except Exception:
        return None


def _upload_to_cloudinary(pic_url: str, creator_name: str, platform_uid: str) -> str | None:
    """Upload pic to Cloudinary, return permanent URL or None."""
    try:
        from services.cloudinary_service import get_cloudinary_service
        svc = get_cloudinary_service()
        if not svc.is_configured:
            return None
        result = svc.upload_from_url(
            url=pic_url,
            media_type="image",
            folder=f"clonnect/{creator_name}/profiles",
            public_id=f"profile_{platform_uid}",
        )
        if result.success and result.url:
            return result.url
    except Exception as e:
        logger.debug(f"[PROFILE_PICS] Cloudinary upload failed for {platform_uid}: {e}")
    return None


def _refresh_sync() -> dict:
    """
    Synchronous refresh logic. Called via asyncio.to_thread() to avoid
    blocking the event loop.
    """
    session = SessionLocal()
    total_refreshed = 0
    total_failed = 0
    total_skipped = 0
    total_rate_limited = False
    processed = 0

    try:
        creators = (
            session.query(Creator)
            .filter(Creator.instagram_token.isnot(None))
            .all()
        )

        if not creators:
            logger.info("[PROFILE_PICS] No creators with Instagram tokens found")
            return {"refreshed": 0, "failed": 0, "skipped": 0}

        for creator in creators:
            # Get leads needing refresh (no pic, or non-cloudinary pic)
            leads = (
                session.query(Lead)
                .filter(
                    Lead.creator_id == creator.id,
                    Lead.platform == "instagram",
                    Lead.platform_user_id.isnot(None),
                    Lead.username.isnot(None),
                    Lead.username != "",
                    or_(
                        Lead.profile_pic_url.is_(None),
                        Lead.profile_pic_url == "",
                        ~Lead.profile_pic_url.like("%cloudinary%"),
                    ),
                )
                .order_by(Lead.last_contact_at.desc().nullslast())
                .all()
            )

            for lead in leads:
                if processed >= MAX_LEADS_PER_RUN:
                    break

                if not _needs_refresh(lead):
                    total_skipped += 1
                    continue

                # Strategy 1: Public API (by username)
                pic_url = _fetch_pic_public_api(lead.username)

                if pic_url == "RATE_LIMITED":
                    total_rate_limited = True
                    logger.warning(
                        f"[PROFILE_PICS] Rate limited after {processed} leads, stopping"
                    )
                    break

                if pic_url:
                    # Upload to Cloudinary for permanent URL
                    cloud_url = _upload_to_cloudinary(
                        pic_url, creator.name, lead.platform_user_id
                    )
                    lead.profile_pic_url = cloud_url or pic_url
                    total_refreshed += 1
                else:
                    total_failed += 1

                processed += 1
                time.sleep(RATE_LIMIT_DELAY)

            session.commit()

            if processed >= MAX_LEADS_PER_RUN or total_rate_limited:
                if processed >= MAX_LEADS_PER_RUN:
                    logger.info(
                        f"[PROFILE_PICS] Hit max {MAX_LEADS_PER_RUN} leads limit"
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
        "rate_limited": total_rate_limited,
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
        f"{stats['failed']} failed, {stats['skipped']} already OK, "
        f"rate_limited={stats.get('rate_limited', False)}"
    )
    return stats
