"""Media processing, thumbnails, link previews, and profile pic endpoints."""
import logging
import re
from typing import Dict, Optional

from api.auth import require_admin
from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)

# URL patterns for link preview detection
INSTAGRAM_URL_REGEX = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)"
)
YOUTUBE_URL_REGEX = re.compile(
    r"https?://(?:www\.|m\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]+)"
)

router = APIRouter(prefix="/admin", tags=["admin"])


async def generate_link_preview(url: str, msg_metadata: Dict) -> Dict:
    """
    Generate preview for a URL and add to metadata.
    For YouTube: uses official thumbnail API (instant)
    For Instagram: uses Microlink API for thumbnail
    """
    try:
        # YouTube - use official thumbnail (instant, no browser needed)
        youtube_match = YOUTUBE_URL_REGEX.search(url)
        if youtube_match:
            video_id = youtube_match.group(1)
            return {
                **msg_metadata,
                "type": "shared_video",
                "platform": "youtube",
                "url": url,
                "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                "video_id": video_id,
            }

        # Instagram - use Microlink API for thumbnail
        instagram_match = INSTAGRAM_URL_REGEX.search(url)
        if instagram_match:
            try:
                from api.services.screenshot_service import get_microlink_preview

                microlink_result = await get_microlink_preview(url)
                if microlink_result and microlink_result.get("thumbnail_url"):
                    return {
                        **msg_metadata,
                        "type": "shared_post",
                        "platform": "instagram",
                        "url": url,
                        "thumbnail_url": microlink_result["thumbnail_url"],
                        "title": microlink_result.get("title"),
                        "author": microlink_result.get("author"),
                    }
            except Exception as e:
                logger.warning(f"Microlink error for {url}: {e}")

            # Fallback: mark for later processing if Microlink fails
            return {
                **msg_metadata,
                "type": "shared_post",
                "platform": "instagram",
                "url": url,
                "needs_thumbnail": True,
            }
    except Exception as e:
        logger.warning(f"Error generating link preview for {url}: {e}")

    return msg_metadata


def detect_url_in_metadata(msg_metadata: Dict) -> Optional[str]:
    """Extract URL from message metadata if present"""
    url = msg_metadata.get("url", "")
    if url and url.startswith("http"):
        return url
    return None


@router.post("/generate-thumbnails/{creator_id}")
async def generate_thumbnails(creator_id: str, limit: int = 10, admin: str = Depends(require_admin)):
    """
    Generate thumbnails for messages with needs_thumbnail=true.
    Processes Instagram posts/reels using Playwright screenshots.

    Args:
        creator_id: Creator name
        limit: Max number of thumbnails to generate (default 10)

    Returns:
        Count of thumbnails generated
    """
    try:
        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Message

        if not DATABASE_URL or not SessionLocal:
            return {"error": "Database not configured"}

        # Try to import screenshot service
        try:
            from api.services.screenshot_service import PLAYWRIGHT_AVAILABLE, ScreenshotService
        except ImportError:
            return {"error": "Screenshot service not available", "playwright_available": False}

        if not PLAYWRIGHT_AVAILABLE:
            return {"error": "Playwright not installed", "playwright_available": False}

        session = SessionLocal()
        results = {"thumbnails_generated": 0, "thumbnails_failed": 0, "messages_processed": 0}

        try:
            # Get creator
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"error": f"Creator {creator_id} not found"}

            # Find messages with needs_thumbnail flag
            leads = session.query(Lead).filter_by(creator_id=creator.id).all()
            lead_ids = [l.id for l in leads]

            if not lead_ids:
                return {"error": "No leads found for creator"}

            # Query messages that need thumbnails
            messages = session.query(Message).filter(Message.lead_id.in_(lead_ids)).all()

            processed = 0
            for msg in messages:
                if processed >= limit:
                    break

                metadata = msg.msg_metadata or {}

                # Check if needs thumbnail
                if not metadata.get("needs_thumbnail"):
                    continue

                url = metadata.get("url")
                if not url:
                    continue

                results["messages_processed"] += 1
                processed += 1

                try:
                    # Generate screenshot
                    preview = await ScreenshotService.capture_instagram_post(url)

                    if preview and (preview.get("thumbnail_base64") or preview.get("thumbnail_url")):
                        # Store URL reference only — never save base64 to DB (bloats msg_metadata)
                        if preview.get("thumbnail_url"):
                            metadata["permanent_url"] = preview["thumbnail_url"]
                        # thumbnail_base64 is intentionally NOT stored in DB
                        metadata["needs_thumbnail"] = False  # Mark as processed
                        metadata.pop("thumbnail_base64", None)  # Strip if present
                        msg.msg_metadata = metadata
                        results["thumbnails_generated"] += 1
                    else:
                        results["thumbnails_failed"] += 1

                except Exception as e:
                    logger.warning(f"Failed to generate thumbnail for {url}: {e}")
                    results["thumbnails_failed"] += 1

            session.commit()
            return {"status": "success", **results}

        finally:
            session.close()

    except Exception as e:
        import traceback

        traceback.print_exc()
        return {"error": str(e)}


@router.post("/update-profile-pics/{creator_id}")
async def update_profile_pics(creator_id: str, limit: int = 20, admin: str = Depends(require_admin)):
    """
    Endpoint ligero para actualizar SOLO fotos de perfil de Instagram.

    No hace sync de mensajes, solo obtiene profile_pic para leads existentes.
    Procesa en batches pequenos para evitar timeout.

    Args:
        creator_id: ID del creator
        limit: Maximo leads a procesar (default: 20)

    Returns:
        {"updated": 15, "failed": 2, "total": 17, "remaining": 5}
    """
    import asyncio

    import httpx
    from api.database import SessionLocal
    from api.models import Creator, Lead

    session = SessionLocal()
    try:
        # Get creator
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            from sqlalchemy import text

            creator = (
                session.query(Creator)
                .filter(text("id::text = :cid"))
                .params(cid=creator_id)
                .first()
            )

        if not creator:
            return {"status": "error", "error": f"Creator not found: {creator_id}"}

        # Check Instagram connection - support both page_id and user_id (IGAAT tokens)
        if not creator.instagram_token:
            return {"status": "error", "error": "Instagram not connected for this creator"}

        if not creator.instagram_page_id and not creator.instagram_user_id:
            return {"status": "error", "error": "Instagram page_id or user_id required"}

        access_token = creator.instagram_token
        # Use correct API based on token type
        if access_token.startswith("IGAAT"):
            api_base = "https://graph.instagram.com/v21.0"
        else:
            api_base = "https://graph.facebook.com/v21.0"

        # Get leads without profile pic
        leads_without_pic = (
            session.query(Lead)
            .filter(
                Lead.creator_id == creator.id,
                Lead.platform == "instagram",
                Lead.platform_user_id.isnot(None),
                Lead.profile_pic_url.is_(None),
            )
            .limit(limit)
            .all()
        )

        # Count total remaining
        total_remaining = (
            session.query(Lead)
            .filter(
                Lead.creator_id == creator.id,
                Lead.platform == "instagram",
                Lead.platform_user_id.isnot(None),
                Lead.profile_pic_url.is_(None),
            )
            .count()
        )

        results = {
            "updated": 0,
            "failed": 0,
            "total": len(leads_without_pic),
            "remaining": total_remaining - len(leads_without_pic),
            "details": [],
        }

        if not leads_without_pic:
            return {"status": "ok", "message": "All leads already have profile pics", **results}

        async with httpx.AsyncClient(timeout=10.0) as client:
            for lead in leads_without_pic:
                try:
                    # Fetch profile from Instagram API
                    resp = await client.get(
                        f"{api_base}/{lead.platform_user_id}",
                        params={
                            "fields": "id,username,name,profile_pic",
                            "access_token": access_token,
                        },
                    )

                    if resp.status_code == 200:
                        data = resp.json()
                        profile_pic = data.get("profile_pic")

                        if profile_pic:
                            lead.profile_pic_url = profile_pic
                            # Also update username if we got better data
                            if data.get("username") and not lead.username:
                                lead.username = data.get("username")
                            if data.get("name") and not lead.full_name:
                                lead.full_name = data.get("name")
                            session.commit()
                            results["updated"] += 1
                            results["details"].append(
                                {"username": lead.username, "status": "updated"}
                            )
                        else:
                            results["failed"] += 1
                            results["details"].append(
                                {"username": lead.username, "status": "no_pic_in_response"}
                            )
                    else:
                        results["failed"] += 1
                        results["details"].append(
                            {"username": lead.username, "status": f"api_error_{resp.status_code}"}
                        )

                    # Rate limiting: 500ms between requests
                    await asyncio.sleep(0.5)

                except Exception as e:
                    results["failed"] += 1
                    results["details"].append(
                        {"username": lead.username, "status": f"error: {str(e)[:50]}"}
                    )

        return {"status": "ok", **results}

    except Exception as e:
        logger.error(f"update_profile_pics error: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        session.close()


@router.post("/generate-link-previews/{creator_id}")
async def generate_link_previews(creator_id: str, limit: int = 50, admin: str = Depends(require_admin)):
    """
    Generate link previews for existing messages that have URLs but no preview.

    Finds messages containing URLs, extracts Open Graph metadata, and updates
    the msg_metadata field with link_preview data.

    Args:
        creator_id: ID del creator
        limit: Max messages to process (default: 50)

    Returns:
        {"updated": 10, "failed": 2, "no_urls": 38, "total": 50}
    """
    import asyncio

    from api.database import SessionLocal
    from api.models import Creator, Lead, Message
    from core.link_preview import extract_link_preview, extract_urls

    session = SessionLocal()
    try:
        # Get creator
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            from sqlalchemy import text

            creator = (
                session.query(Creator)
                .filter(text("id::text = :cid"))
                .params(cid=creator_id)
                .first()
            )

        if not creator:
            return {"status": "error", "error": f"Creator not found: {creator_id}"}

        # Find messages with URLs using JOIN (avoids N+1)
        messages = (
            session.query(Message)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(Lead.creator_id == creator.id, Message.content.ilike("%http%"))
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )

        if not messages:
            return {
                "status": "ok",
                "message": "No messages with URLs found",
                "updated": 0,
                "total": 0,
            }

        results = {
            "updated": 0,
            "failed": 0,
            "no_urls": 0,
            "already_has_preview": 0,
            "total": len(messages),
            "details": [],
        }

        for msg in messages:
            try:
                # Skip if already has link preview
                if msg.msg_metadata and msg.msg_metadata.get("link_preview"):
                    results["already_has_preview"] += 1
                    continue

                # Extract URLs
                urls = extract_urls(msg.content)
                if not urls:
                    results["no_urls"] += 1
                    continue

                # Get preview for first URL
                preview = await extract_link_preview(urls[0])

                if preview:
                    # Update message metadata (commit batched below)
                    current_metadata = msg.msg_metadata or {}
                    current_metadata["link_preview"] = preview
                    msg.msg_metadata = current_metadata

                    results["updated"] += 1
                    results["details"].append(
                        {
                            "url": urls[0][:50],
                            "title": (
                                preview.get("title", "")[:30] if preview.get("title") else None
                            ),
                            "status": "updated",
                        }
                    )

                    # Batch commit every 10 updates for efficiency
                    if results["updated"] % 10 == 0:
                        session.commit()
                else:
                    results["failed"] += 1
                    results["details"].append({"url": urls[0][:50], "status": "no_preview_data"})

                # Rate limiting - don't saturate external services
                await asyncio.sleep(0.3)

            except Exception as e:
                results["failed"] += 1
                logger.debug(f"Link preview error: {e}")

        # Final commit for remaining updates
        if results["updated"] % 10 != 0:
            session.commit()

        return {"status": "ok", **results}

    except Exception as e:
        logger.error(f"generate_link_previews error: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        session.close()
