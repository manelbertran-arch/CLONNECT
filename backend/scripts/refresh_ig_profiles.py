"""
Refresh Instagram lead profiles — fetch username, name, and profile pic from IG API.

Handles two cases:
1. Leads without username/name (numeric-only profiles from webhooks)
2. Leads without profile_pic_url or with expired CDN URLs

Uploads profile pics to Cloudinary for permanent storage.

Usage:
    railway run python3 scripts/refresh_ig_profiles.py stefano_bonanno --dry-run
    railway run python3 scripts/refresh_ig_profiles.py stefano_bonanno
    railway run python3 scripts/refresh_ig_profiles.py iris_bertran --limit 50
    railway run python3 scripts/refresh_ig_profiles.py --all
"""

import argparse
import asyncio
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [IG-PROFILE] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

for name in ["httpx", "httpcore", "urllib3"]:
    logging.getLogger(name).setLevel(logging.WARNING)


def is_pic_expired_or_missing(url: str) -> bool:
    """Check if profile pic URL is missing, empty, or expired."""
    if not url or not url.strip():
        return True
    # Cloudinary URLs never expire
    if "cloudinary" in url:
        return False
    # Parse Instagram CDN expiry from oe= parameter
    match = re.search(r"[?&]oe=([0-9a-fA-F]+)", url)
    if not match:
        return True
    try:
        expiry_ts = int(match.group(1), 16)
        expiry_dt = datetime.fromtimestamp(expiry_ts, tz=timezone.utc)
        return expiry_dt < datetime.now(timezone.utc) + timedelta(hours=6)
    except Exception:
        return True


async def refresh_profiles(creator_name: str, dry_run: bool = False, limit: int = 300):
    import httpx
    from api.database import SessionLocal
    from api.models import Creator, Lead

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_name).first()
        if not creator:
            logger.error(f"Creator not found: {creator_name}")
            return
        if not creator.instagram_token:
            logger.error(f"No Instagram token for {creator_name}")
            return

        token = creator.instagram_token
        creator_uuid = creator.id

        logger.info(f"Creator: {creator_name} (UUID={creator_uuid})")
        logger.info(f"Token type: {'IGAAT' if token.startswith('IGAAT') else 'PAGE (EAA)'}")

        # Get all IG leads for this creator
        leads = (
            session.query(Lead)
            .filter(
                Lead.creator_id == creator_uuid,
                Lead.platform == "instagram",
            )
            .all()
        )

        # Categorize leads
        no_username = []
        no_pic = []
        expired_pic = []
        ok = []

        for lead in leads:
            puid = lead.platform_user_id or ""
            # Strip ig_ prefix for API calls
            ig_id = puid.replace("ig_", "") if puid.startswith("ig_") else puid

            has_username = lead.username and lead.username.strip() and lead.username != puid
            has_pic = lead.profile_pic_url and lead.profile_pic_url.strip()

            if not has_username:
                no_username.append((lead, ig_id))
            elif not has_pic:
                no_pic.append((lead, ig_id))
            elif is_pic_expired_or_missing(lead.profile_pic_url):
                expired_pic.append((lead, ig_id))
            else:
                ok.append(lead)

        logger.info(f"Total IG leads: {len(leads)}")
        logger.info(f"  No username: {len(no_username)}")
        logger.info(f"  No profile pic: {len(no_pic)}")
        logger.info(f"  Expired pic: {len(expired_pic)}")
        logger.info(f"  OK: {len(ok)}")

        # Priority: first resolve leads without username, then those without pics
        to_refresh = no_username + no_pic + expired_pic
        to_refresh = to_refresh[:limit]

        logger.info(f"Will refresh {len(to_refresh)} leads (limit={limit}, dry_run={dry_run})")

        # Initialize Cloudinary service
        cloudinary_svc = None
        try:
            from services.cloudinary_service import get_cloudinary_service
            cloudinary_svc = get_cloudinary_service()
            if cloudinary_svc.is_configured:
                logger.info("Cloudinary configured — will upload profile pics")
            else:
                logger.warning("Cloudinary NOT configured — will use CDN URLs (expire in ~7 days)")
                cloudinary_svc = None
        except Exception:
            logger.warning("Cloudinary not available")

        updated = 0
        errors = 0
        rate_limited = 0

        async with httpx.AsyncClient(timeout=10.0) as client:
            for i, (lead, ig_id) in enumerate(to_refresh):
                if not ig_id:
                    continue

                # Fetch profile from Instagram API
                api_base = "https://graph.instagram.com/v21.0"
                if token.startswith("EAA"):
                    api_base = "https://graph.facebook.com/v21.0"

                try:
                    resp = await client.get(
                        f"{api_base}/{ig_id}",
                        params={
                            "fields": "id,username,name,profile_pic",
                            "access_token": token,
                        },
                    )

                    if resp.status_code == 429 or (resp.status_code == 400 and "limit" in resp.text.lower()):
                        rate_limited += 1
                        logger.warning(f"[{i+1}/{len(to_refresh)}] Rate limited — waiting 60s")
                        await asyncio.sleep(60)
                        continue

                    if resp.status_code != 200:
                        error_data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                        error_msg = error_data.get("error", {}).get("message", f"HTTP {resp.status_code}")
                        logger.warning(f"[{i+1}/{len(to_refresh)}] {ig_id}: {error_msg}")
                        errors += 1
                        await asyncio.sleep(1)
                        continue

                    data = resp.json()
                    username = data.get("username", "")
                    name = data.get("name", "")
                    pic_url = data.get("profile_pic", "")

                    if dry_run:
                        old_user = lead.username or ""
                        old_name = lead.full_name or ""
                        changes = []
                        if username and username != old_user:
                            changes.append(f"user: {old_user!r} → {username!r}")
                        if name and name != old_name:
                            changes.append(f"name: {old_name!r} → {name!r}")
                        if pic_url:
                            changes.append("pic: ✓")
                        logger.info(f"[DRY {i+1}/{len(to_refresh)}] {ig_id}: {', '.join(changes) or 'no changes'}")
                        updated += 1
                        await asyncio.sleep(0.3)
                        continue

                    # Upload pic to Cloudinary
                    final_pic_url = pic_url
                    if pic_url and cloudinary_svc:
                        try:
                            cloud_result = cloudinary_svc.upload_from_url(
                                url=pic_url,
                                media_type="image",
                                folder=f"clonnect/{creator_name}/profiles",
                                public_id=f"profile_{ig_id}",
                            )
                            if cloud_result.success and cloud_result.url:
                                final_pic_url = cloud_result.url
                                logger.debug(f"  Cloudinary: {final_pic_url[:60]}")
                        except Exception as cloud_err:
                            logger.warning(f"  Cloudinary upload failed: {cloud_err}")

                    # Update lead in DB
                    changed = False
                    if username and (not lead.username or not lead.username.strip() or lead.username == lead.platform_user_id):
                        lead.username = username
                        changed = True
                    if name and (not lead.full_name or not lead.full_name.strip() or lead.full_name == lead.platform_user_id):
                        lead.full_name = name
                        changed = True
                    if final_pic_url:
                        lead.profile_pic_url = final_pic_url
                        changed = True

                    if changed:
                        session.commit()
                        updated += 1
                        logger.info(
                            f"[{i+1}/{len(to_refresh)}] {ig_id}: "
                            f"user={username or '-'}, name={name or '-'}, "
                            f"pic={'cloudinary' if final_pic_url and 'cloudinary' in final_pic_url else 'cdn' if final_pic_url else 'none'}"
                        )

                except Exception as e:
                    logger.warning(f"[{i+1}/{len(to_refresh)}] {ig_id}: Error — {e}")
                    errors += 1

                # Rate limit: ~3 requests per second
                await asyncio.sleep(0.35)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()

    logger.info("=" * 60)
    logger.info("PROFILE REFRESH COMPLETE")
    logger.info(f"  Updated: {updated}")
    logger.info(f"  Errors: {errors}")
    logger.info(f"  Rate limited: {rate_limited}")
    logger.info(f"  Dry run: {dry_run}")


async def refresh_all(dry_run: bool = False, limit: int = 300):
    from api.database import SessionLocal
    from api.models import Creator

    session = SessionLocal()
    creators = session.query(Creator).filter(Creator.instagram_token.isnot(None)).all()
    session.close()

    for creator in creators:
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing creator: {creator.name}")
        await refresh_profiles(creator.name, dry_run=dry_run, limit=limit)


def main():
    parser = argparse.ArgumentParser(description="Refresh IG lead profiles")
    parser.add_argument("creator_name", nargs="?", help="Creator slug (or --all)")
    parser.add_argument("--all", action="store_true", help="Refresh all creators")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be updated")
    parser.add_argument("--limit", type=int, default=300, help="Max leads to refresh")
    args = parser.parse_args()

    if args.all:
        asyncio.run(refresh_all(dry_run=args.dry_run, limit=args.limit))
    elif args.creator_name:
        asyncio.run(refresh_profiles(args.creator_name, dry_run=args.dry_run, limit=args.limit))
    else:
        parser.error("Provide creator_name or --all")


if __name__ == "__main__":
    main()
