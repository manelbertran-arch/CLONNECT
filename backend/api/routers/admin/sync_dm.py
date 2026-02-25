"""DM sync and conversation sync endpoints."""
import json
import logging
import os
import re
from typing import Dict, Optional

from api.auth import require_admin
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

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


# Only enable if ENABLE_DEMO_RESET is set (default true for testing)
DEMO_RESET_ENABLED = os.getenv("ENABLE_DEMO_RESET", "true").lower() == "true"


@router.post("/test-full-sync/{creator_id}/{username}")
async def test_full_sync_conversation(creator_id: str, username: str, admin: str = Depends(require_admin)):
    """
    TEST ENDPOINT: Sincronizar TODOS los mensajes de una conversación específica
    usando paginación completa.

    Ejemplo: POST /admin/test-full-sync/manel_bertran_luque/stefanobonanno
    """
    from datetime import datetime, timedelta, timezone

    import httpx
    from api.database import SessionLocal
    from api.models import Creator, Lead, Message

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

        access_token = creator.instagram_token
        ig_user_id = creator.instagram_user_id
        ig_page_id = creator.instagram_page_id

        if not access_token:
            raise HTTPException(status_code=400, detail="Creator has no Instagram token")

        # Dual API strategy
        if ig_page_id:
            api_base = "https://graph.facebook.com/v21.0"
            conv_id_for_api = ig_page_id
            conv_extra_params = {"platform": "instagram"}
        else:
            api_base = "https://graph.instagram.com/v21.0"
            conv_id_for_api = ig_user_id
            conv_extra_params = {}

        creator_ids = {ig_user_id, ig_page_id} - {None}

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Step 1: Get all conversations to find the one with the target username
            conv_resp = await client.get(
                f"{api_base}/{conv_id_for_api}/conversations",
                params={
                    **conv_extra_params,
                    "access_token": access_token,
                    "limit": 50,
                    "fields": "id,updated_time",
                },
            )

            if conv_resp.status_code != 200:
                raise HTTPException(
                    status_code=500, detail=f"Conversations API error: {conv_resp.status_code}"
                )

            conversations = conv_resp.json().get("data", [])

            # Find the conversation with the target username
            target_conv_id = None
            target_follower_id = None

            for conv in conversations:
                conv_id = conv.get("id")
                if not conv_id:
                    continue

                # Fetch messages to identify participant
                msg_resp = await client.get(
                    f"{api_base}/{conv_id}/messages",
                    params={
                        "fields": "id,message,from,to,created_time",
                        "access_token": access_token,
                        "limit": 5,
                    },
                )

                if msg_resp.status_code != 200:
                    continue

                messages = msg_resp.json().get("data", [])
                for msg in messages:
                    from_data = msg.get("from", {})
                    if from_data.get("username") == username:
                        target_conv_id = conv_id
                        target_follower_id = from_data.get("id")
                        break

                    to_data = msg.get("to", {}).get("data", [])
                    for recipient in to_data:
                        if recipient.get("username") == username:
                            target_conv_id = conv_id
                            target_follower_id = recipient.get("id")
                            break

                    if target_conv_id:
                        break

                if target_conv_id:
                    break

            if not target_conv_id:
                raise HTTPException(
                    status_code=404, detail=f"Conversation with {username} not found"
                )

            # Step 2: Fetch ALL messages with pagination
            # Request extended fields to capture media, stories, reactions, etc.
            all_messages = []
            msg_url = f"{api_base}/{target_conv_id}/messages"
            msg_params = {
                "fields": "id,message,from,to,created_time,attachments,story,shares,reactions,sticker",
                "access_token": access_token,
                "limit": 50,
            }

            pages_fetched = 0
            max_pages = 20  # Safety limit: 50 * 20 = 1000 messages max

            while msg_url and pages_fetched < max_pages:
                msg_resp = await client.get(msg_url, params=msg_params)

                if msg_resp.status_code != 200:
                    logger.warning(
                        f"Messages API error {msg_resp.status_code} on page {pages_fetched}"
                    )
                    break

                msg_data = msg_resp.json()
                page_messages = msg_data.get("data", [])
                all_messages.extend(page_messages)

                # Check for next page
                paging = msg_data.get("paging", {})
                next_url = paging.get("next")

                if next_url:
                    msg_url = next_url
                    msg_params = {}  # Next URL includes params
                    pages_fetched += 1
                    logger.info(
                        f"[FullSync] Fetched page {pages_fetched}, total messages: {len(all_messages)}"
                    )
                else:
                    break

            logger.info(
                f"[FullSync] Total pages: {pages_fetched + 1}, total messages: {len(all_messages)}"
            )

            # Step 3: Get or create lead - check both with and without ig_ prefix
            days_limit_ago = datetime.now().astimezone() - timedelta(days=180)

            lead = (
                session.query(Lead)
                .filter(
                    Lead.creator_id == creator.id,
                    Lead.platform == "instagram",
                    Lead.platform_user_id.in_([target_follower_id, f"ig_{target_follower_id}"]),
                )
                .first()
            )

            if not lead:
                lead = Lead(
                    creator_id=creator.id,
                    platform="instagram",
                    platform_user_id=target_follower_id,
                    username=username,
                    status="new",
                )
                session.add(lead)
                session.commit()

            # Step 4: Save all messages (including media, reactions, stories)
            saved_count = 0
            skipped_duplicate = 0
            updated_unknown = 0  # Messages updated from unknown to proper type
            skipped_old = 0
            skipped_no_id = 0
            content_types = {
                "text": 0,
                "attachment": 0,
                "story": 0,
                "share": 0,
                "reaction": 0,
                "sticker": 0,
                "unknown": 0,
            }

            for msg in all_messages:
                msg_id = msg.get("id")
                if not msg_id:
                    skipped_no_id += 1
                    continue

                # Detect content type and build message text
                msg_text = msg.get("message", "")
                metadata = {}

                if msg_text:
                    content_types["text"] += 1
                elif msg.get("share"):
                    # Shared content (singular - shared post/reel)
                    share_data = msg.get("share", {})
                    share_link = share_data.get("link", "")
                    msg_text = "[Post compartido]" if share_link else "[Contenido compartido]"
                    metadata["type"] = "share"
                    metadata["url"] = share_link
                    metadata["thumbnail_url"] = share_data.get("image_url", "")
                    metadata["name"] = share_data.get("name", "")
                    content_types["share"] += 1
                elif msg.get("attachments"):
                    # Media attachment (image, video, file)
                    # FIX 2026-02-02: Support both Meta formats:
                    # - Dict format: {"data": [{...}]}
                    # - List format: [{...}]
                    raw_attachments = msg.get("attachments", {})
                    if isinstance(raw_attachments, dict):
                        attachments = raw_attachments.get("data", [])
                    elif isinstance(raw_attachments, list):
                        attachments = raw_attachments
                    else:
                        attachments = []
                    if attachments:
                        att = attachments[0]
                        att_type_raw = (att.get("type") or "").lower()

                        # Structure-based detection (Instagram often omits explicit type)
                        has_video = att.get("video_data") is not None
                        has_image = att.get("image_data") is not None
                        has_audio = att.get("audio_data") is not None
                        is_sticker = att.get("render_as_sticker", False)
                        is_animated = att.get("animated_gif_url") is not None

                        # Try new payload format first, then legacy formats
                        payload = att.get("payload", {})
                        payload_url = payload.get("url") if isinstance(payload, dict) else None
                        legacy_url = (
                            att.get("video_data", {}).get("url")
                            or att.get("image_data", {}).get("url")
                            or att.get("audio_data", {}).get("url")
                            or att.get("url")
                        )
                        att_url = payload_url or legacy_url or ""

                        # Determine type: prefer structure-based, fallback to explicit type
                        if "video" in att_type_raw or has_video:
                            msg_text = "[Video]"
                            metadata["type"] = "video"
                        elif "audio" in att_type_raw or has_audio:
                            msg_text = "[Audio]"
                            metadata["type"] = "audio"
                        elif is_sticker:
                            msg_text = "[Sticker]"
                            metadata["type"] = "sticker"
                        elif is_animated or "gif" in att_type_raw:
                            msg_text = "[GIF]"
                            metadata["type"] = "gif"
                            att_url = att.get("animated_gif_url") or att_url
                        elif "image" in att_type_raw or "photo" in att_type_raw or has_image:
                            msg_text = "[Imagen]"
                            metadata["type"] = "image"
                        elif "share" in att_type_raw or "post" in att_type_raw:
                            msg_text = "[Post compartido]"
                            metadata["type"] = "shared_post"
                        elif att_type_raw:
                            msg_text = f"[{att_type_raw.title()}]"
                            metadata["type"] = att_type_raw
                        else:
                            msg_text = "[Archivo]"
                            metadata["type"] = "file"
                        metadata["url"] = att_url
                        metadata["captured_at"] = datetime.now(timezone.utc).isoformat()
                    else:
                        msg_text = "[Adjunto]"
                        metadata["type"] = "attachment"
                    content_types["attachment"] += 1
                elif msg.get("story"):
                    # Story mention or reply
                    story = msg.get("story", {})
                    if story.get("mention"):
                        msg_text = "[Te mencionó en su story]"
                        metadata["type"] = "story_mention"
                    else:
                        msg_text = "[Respuesta a story]"
                        metadata["type"] = "story_reply"
                    metadata["story_id"] = story.get("id", "")
                    content_types["story"] += 1
                elif msg.get("shares"):
                    # Shared content (post, reel, profile)
                    shares = msg.get("shares", {}).get("data", [])
                    if shares:
                        share = shares[0]
                        share_link = share.get("link", "")
                        msg_text = (
                            f"[Compartido: {share_link}]"
                            if share_link
                            else "[Contenido compartido]"
                        )
                        metadata["type"] = "share"
                        metadata["url"] = share_link
                    else:
                        msg_text = "[Contenido compartido]"
                        metadata["type"] = "share"
                    content_types["share"] += 1
                elif msg.get("reactions"):
                    # Reaction to a message
                    reactions = msg.get("reactions", {}).get("data", [])
                    if reactions:
                        emoji = reactions[0].get("reaction", "❤️")
                        # Ensure heart emoji has variation selector (U+FE0F) for red rendering
                        if emoji == "❤" or emoji == "\u2764":
                            emoji = "❤️"
                        msg_text = f"[Reacción: {emoji}]"
                        metadata["emoji"] = emoji
                    else:
                        msg_text = "[Reacción]"
                    metadata["type"] = "reaction"
                    content_types["reaction"] += 1
                elif msg.get("sticker"):
                    # Sticker
                    msg_text = "[Sticker]"
                    metadata["type"] = "sticker"
                    metadata["sticker_id"] = msg.get("sticker", "")
                    content_types["sticker"] += 1
                else:
                    # Check if this is an empty/deleted message (no content at all)
                    has_any_content = (
                        msg.get("message")
                        or msg.get("attachments")
                        or msg.get("share")
                        or msg.get("shares")
                        or msg.get("story")
                        or msg.get("sticker")
                        or msg.get("reactions")
                    )
                    if not has_any_content:
                        # Empty message - likely deleted or expired media
                        msg_text = "[Mensaje eliminado]"
                        metadata["type"] = "deleted"
                        content_types["deleted"] = content_types.get("deleted", 0) + 1
                    else:
                        # Truly unknown type - save with debug info
                        msg_text = "[Media]"
                        metadata["type"] = "unknown"
                        metadata["raw_keys"] = list(msg.keys())
                        content_types["unknown"] += 1

                # Check timestamp
                msg_time = None
                if msg.get("created_time"):
                    try:
                        msg_time = datetime.fromisoformat(
                            msg["created_time"].replace("+0000", "+00:00")
                        )
                        if msg_time < days_limit_ago:
                            skipped_old += 1
                            continue
                    except ValueError as e:
                        logger.debug("Ignored ValueError in msg_time = datetime.fromisoformat(: %s", e)

                # Check for duplicate - but UPDATE if existing has type="unknown"
                existing = session.query(Message).filter_by(platform_message_id=msg_id).first()
                if existing:
                    # If existing message has unknown type and new extraction has better type, update it
                    existing_type = (existing.msg_metadata or {}).get("type", "")
                    new_type = metadata.get("type", "unknown")
                    if existing_type == "unknown" and new_type != "unknown":
                        # Update the existing message with new metadata
                        existing.content = msg_text
                        existing.msg_metadata = metadata
                        updated_unknown += 1
                    else:
                        skipped_duplicate += 1
                    continue

                # Determine role
                from_id = msg.get("from", {}).get("id")
                role = "assistant" if from_id in creator_ids else "user"

                new_msg = Message(
                    lead_id=lead.id,
                    role=role,
                    content=msg_text,
                    platform_message_id=msg_id,
                    msg_metadata=metadata if metadata else {},
                )
                if msg_time:
                    new_msg.created_at = msg_time
                session.add(new_msg)
                saved_count += 1

            session.commit()

            # Update lead timestamps
            lead_messages = (
                session.query(Message).filter_by(lead_id=lead.id).order_by(Message.created_at).all()
            )
            if lead_messages:
                lead.first_contact_at = lead_messages[0].created_at
                lead.last_contact_at = lead_messages[-1].created_at
                session.commit()

            return {
                "status": "success",
                "username": username,
                "conversation_id": target_conv_id,
                "follower_id": target_follower_id,
                "pages_fetched": pages_fetched + 1,
                "total_api_messages": len(all_messages),
                "messages_saved": saved_count,
                "updated_unknown": updated_unknown,
                "skipped_duplicate": skipped_duplicate,
                "skipped_old": skipped_old,
                "skipped_no_id": skipped_no_id,
                "content_types": content_types,
                "lead_id": str(lead.id),
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FullSync] Error: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        session.close()


@router.post("/clean-and-sync/{creator_id}")
async def clean_and_sync(creator_id: str, max_convs: int = 10, admin: str = Depends(require_admin)):
    """
    Limpia mensajes huérfanos y hace sync limpio.

    1. Elimina TODOS los mensajes con platform_message_id de Instagram
    2. Ejecuta un sync fresco
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator, Message

        session = SessionLocal()
        results = {"cleaned": {"orphaned_messages": 0}, "sync": {}}

        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"error": f"Creator '{creator_id}' not found"}

            # 1. Eliminar TODOS los mensajes de Instagram (empezar fresco)
            deleted = (
                session.query(Message)
                .filter(Message.platform_message_id.like("aWdf%"))
                .delete(synchronize_session="fetch")
            )
            results["cleaned"]["orphaned_messages"] = deleted
            session.commit()
            logger.info(f"Deleted {deleted} Instagram messages for clean sync")

        finally:
            session.close()

        # 2. Ejecutar sync
        sync_result = await simple_dm_sync(creator_id, max_convs)
        results["sync"] = sync_result

        return results

    except Exception as e:
        import traceback

        return {"error": str(e), "traceback": traceback.format_exc()}


@router.post("/simple-dm-sync/{creator_id}")
async def simple_dm_sync(creator_id: str, max_convs: int = 10, admin: str = Depends(require_admin)):
    """
    [DEPRECATED] Use /onboarding/sync-instagram-dms-background instead.

    Simple DM sync with rate limiting (2s delay between conversations).
    """
    import asyncio
    import logging
    from datetime import datetime

    import httpx
    from api.services import db_service

    _logger = logging.getLogger(__name__)
    _logger.warning(f"[DEPRECATED] /admin/simple-dm-sync called for {creator_id}")

    DELAY_BETWEEN_CONVS = 2.0

    results = {
        "conversations_processed": 0,
        "messages_saved": 0,
        "messages_empty": 0,
        "messages_duplicate": 0,
        "messages_filtered_180days": 0,
        "messages_with_attachments": 0,
        "leads_created": 0,
        "errors": [],
        "rate_limited": False,
    }

    # First check Instagram credentials using centralized function
    creds = db_service.get_instagram_credentials(creator_id)
    if not creds["success"]:
        return {"error": creds["error"]}

    # IMPORTANT: Instagram has TWO IDs for the same account:
    # - page_id: appears in message from.id (e.g., 17841407135263418)
    # - user_id: used for API calls (e.g., 26196963493255185)
    # We need to check BOTH when identifying if a message is from the creator
    ig_user_id = creds["user_id"] or creds["page_id"]
    ig_page_id = creds["page_id"]
    creator_ids = {ig_user_id, ig_page_id} - {None}  # Set of all creator IDs
    access_token = creds["token"]

    try:
        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Message

        if not DATABASE_URL or not SessionLocal:
            return {"error": "Database not configured"}

        session = SessionLocal()
        try:
            # Get creator for UUID (needed for FK relationships)
            creator = session.query(Creator).filter_by(name=creator_id).first()

            # FIX: Check token type FIRST to determine API
            # IGAAT tokens (Instagram Graph API) only work with graph.instagram.com
            # EAA tokens (Page Access) work with graph.facebook.com
            is_igaat_token = access_token.startswith("IGAAT")
            is_page_token = access_token.startswith("EAA")

            if is_igaat_token:
                # IGAAT tokens MUST use Instagram API
                api_base = "https://graph.instagram.com/v21.0"
                conv_id_for_api = ig_user_id or ig_page_id
                conv_extra_params = {}
            elif is_page_token and ig_page_id:
                # Page tokens use Facebook API with page_id
                api_base = "https://graph.facebook.com/v21.0"
                conv_id_for_api = ig_page_id
                conv_extra_params = {"platform": "instagram"}
            else:
                # Fallback to Instagram API
                api_base = "https://graph.instagram.com/v21.0"
                conv_id_for_api = ig_user_id or ig_page_id
                conv_extra_params = {}

            async with httpx.AsyncClient(timeout=60.0) as client:
                # Get conversations with updated_time
                conv_resp = await client.get(
                    f"{api_base}/{conv_id_for_api}/conversations",
                    params={
                        **conv_extra_params,
                        "access_token": access_token,
                        "limit": max_convs,
                        "fields": "id,updated_time",
                    },
                )

                if conv_resp.status_code != 200:
                    return {"error": f"Conversations API error: {conv_resp.json()}"}

                conversations = conv_resp.json().get("data", [])

                # REGLA 1: Ordenar por updated_time (más reciente primero)
                conversations.sort(key=lambda c: c.get("updated_time", ""), reverse=True)

                for conv_idx, conv in enumerate(conversations):
                    conv_id = conv.get("id")
                    if not conv_id:
                        continue

                    # Rate limiting: delay between conversations
                    if conv_idx > 0:
                        _logger.info(
                            f"[DMSync] Rate limit delay: {DELAY_BETWEEN_CONVS}s before conv {conv_idx + 1}/{len(conversations)}"
                        )
                        await asyncio.sleep(DELAY_BETWEEN_CONVS)

                    try:
                        # Get messages for this conversation (REGLA 3+4: attachments, stories, reactions)
                        msg_resp = await client.get(
                            f"{api_base}/{conv_id}/messages",
                            params={
                                "fields": "id,message,from,to,created_time,attachments,story,reactions",
                                "access_token": access_token,
                                "limit": 50,
                            },
                        )

                        if msg_resp.status_code != 200:
                            error_data = msg_resp.json().get("error", {})
                            # Check for rate limit
                            if error_data.get("code") in [4, 17]:
                                results["errors"].append(
                                    f"Rate limit hit at conv {results['conversations_processed']}"
                                )
                                break
                            continue

                        messages = msg_resp.json().get("data", [])
                        if not messages:
                            continue

                        # Find the follower (non-creator participant)
                        # Check BOTH creator IDs (user_id and page_id)
                        follower_id = None
                        follower_username = None

                        for msg in messages:
                            from_data = msg.get("from", {})
                            from_id = from_data.get("id")
                            # Follower is someone whose ID is NOT in creator_ids
                            if from_id and from_id not in creator_ids:
                                follower_id = from_id
                                follower_username = from_data.get("username", "unknown")
                                break

                        if not follower_id:
                            # Check "to" field
                            for msg in messages:
                                to_data = msg.get("to", {}).get("data", [])
                                for recipient in to_data:
                                    if recipient.get("id") not in creator_ids:
                                        follower_id = recipient.get("id")
                                        follower_username = recipient.get("username", "unknown")
                                        break
                                if follower_id:
                                    break

                        if not follower_id:
                            continue

                        # Fetch profile picture from Instagram API
                        follower_profile_pic = None
                        try:
                            profile_resp = await client.get(
                                f"{api_base}/{follower_id}",
                                params={
                                    "fields": "id,username,name,profile_pic",
                                    "access_token": access_token,
                                },
                            )
                            if profile_resp.status_code == 200:
                                profile_data = profile_resp.json()
                                follower_profile_pic = profile_data.get("profile_pic")
                                # Also update username/name if we got better data
                                if profile_data.get("username"):
                                    follower_username = profile_data.get("username")
                        except Exception as e:
                            logger.warning(f"Could not fetch profile for {follower_id}: {e}")

                        # Get or create lead - check both with and without ig_ prefix
                        lead = (
                            session.query(Lead)
                            .filter(
                                Lead.creator_id == creator.id,
                                Lead.platform == "instagram",
                                Lead.platform_user_id.in_([follower_id, f"ig_{follower_id}"]),
                            )
                            .first()
                        )

                        # Parse conversation updated_time as fallback
                        conv_updated_time = None
                        if conv.get("updated_time"):
                            try:
                                conv_updated_time = datetime.fromisoformat(
                                    conv["updated_time"].replace("+0000", "+00:00")
                                )
                            except ValueError as e:
                                logger.debug("Ignored ValueError in conv_updated_time = datetime.fromisoformat(: %s", e)

                        # Parse message timestamps for first/last contact
                        all_msg_timestamps = []
                        user_msg_timestamps = []

                        for msg in messages:
                            if msg.get("created_time"):
                                try:
                                    ts = datetime.fromisoformat(
                                        msg["created_time"].replace("+0000", "+00:00")
                                    )
                                    all_msg_timestamps.append(ts)

                                    # Solo contar mensajes del follower para last_contact
                                    from_id = msg.get("from", {}).get("id")
                                    if from_id and from_id != ig_user_id:
                                        user_msg_timestamps.append(ts)
                                except ValueError as e:
                                    logger.debug("Ignored ValueError in ts = datetime.fromisoformat(: %s", e)

                        first_msg_time = (
                            min(all_msg_timestamps) if all_msg_timestamps else conv_updated_time
                        )
                        # IMPORTANTE: usar último mensaje del USUARIO para fantasma
                        last_user_msg_time = (
                            max(user_msg_timestamps) if user_msg_timestamps else first_msg_time
                        )

                        if not lead:
                            lead = Lead(
                                creator_id=creator.id,
                                platform="instagram",
                                platform_user_id=follower_id,
                                username=follower_username,
                                profile_pic_url=follower_profile_pic,
                                status="new",
                                first_contact_at=first_msg_time,
                                # IMPORTANTE: usar último mensaje del USUARIO para fantasma
                                last_contact_at=last_user_msg_time or first_msg_time,
                            )
                            session.add(lead)
                            session.commit()
                            results["leads_created"] += 1
                        else:
                            # Update timestamps if we have older/newer messages
                            if first_msg_time and (
                                not lead.first_contact_at or first_msg_time < lead.first_contact_at
                            ):
                                lead.first_contact_at = first_msg_time
                            # IMPORTANTE: solo actualizar si hay mensaje del USUARIO más reciente
                            if last_user_msg_time and (
                                not lead.last_contact_at
                                or last_user_msg_time > lead.last_contact_at
                            ):
                                lead.last_contact_at = last_user_msg_time
                            # Update profile pic if we got one and lead doesn't have it
                            if follower_profile_pic and not lead.profile_pic_url:
                                lead.profile_pic_url = follower_profile_pic
                            session.commit()

                        # REGLA 2: Calcular límite de 90 días
                        from datetime import timedelta

                        # 180 days for initial import (captures more valuable conversations)
                        days_limit_ago = datetime.now().astimezone() - timedelta(days=180)

                        # Save messages
                        messages_saved_this_conv = 0
                        for msg in messages:
                            msg_id = msg.get("id")
                            msg_text = msg.get("message", "")
                            msg_metadata = {}  # Initialize for all messages

                            # REGLA 3+4: Si no hay texto, procesar attachments, stories y reacciones
                            if not msg_text:
                                # REGLA 4: Primero verificar stories y reacciones
                                story_data = msg.get("story", {})
                                reactions_data = msg.get("reactions", {}).get("data", [])

                                # Obtener emoji de reacción si existe
                                reaction_emoji = None
                                if reactions_data:
                                    reaction_emoji = reactions_data[0].get("emoji", "❤️")
                                    # Ensure heart emoji has variation selector (U+FE0F) for red rendering
                                    if reaction_emoji == "❤" or reaction_emoji == "\u2764":
                                        reaction_emoji = "❤️"

                                # Obtener link de story si existe
                                story_link = None
                                story_type = None
                                if story_data.get("reply_to"):
                                    story_link = story_data["reply_to"].get("link", "")
                                    story_type = "reply_to"
                                elif story_data.get("mention"):
                                    story_link = story_data["mention"].get("link", "")
                                    story_type = "mention"

                                # Build message with metadata for frontend rendering
                                # (msg_metadata already initialized at loop start)

                                # Construir mensaje según combinación
                                if story_type and reaction_emoji:
                                    msg_text = f"Reacción {reaction_emoji} a story"
                                    msg_metadata = {
                                        "type": "story_reaction",
                                        "url": story_link,
                                        "emoji": reaction_emoji,
                                    }
                                elif story_type == "reply_to":
                                    msg_text = "Respuesta a story"
                                    msg_metadata = {"type": "story_reply", "url": story_link}
                                elif story_type == "mention":
                                    msg_text = "Mención en story"
                                    msg_metadata = {"type": "story_mention", "url": story_link}
                                elif reaction_emoji:
                                    msg_text = f"Reacción {reaction_emoji}"
                                    msg_metadata = {"type": "reaction", "emoji": reaction_emoji}

                                # REGLA 3: Si aún no hay texto, procesar attachments
                                if not msg_text:
                                    # Check for share field at message level (shared posts/reels)
                                    share_data = msg.get("share")
                                    if share_data:
                                        logger.debug("Share field found: %s", share_data)
                                        msg_text = "Post compartido"
                                        msg_metadata = {
                                            "type": "shared_post",
                                            "url": share_data.get("link", ""),
                                            "thumbnail_url": share_data.get("image_url", ""),
                                            "name": share_data.get("name", ""),
                                            "description": share_data.get("description", ""),
                                        }
                                    else:
                                        attachments = msg.get("attachments", {}).get("data", [])
                                        if attachments:
                                            for att in attachments:
                                                # DEBUG: Log attachment structure
                                                logger.debug("Attachment: %s", att)

                                                att_type = (att.get("type") or "").lower()

                                                # Instagram sends structure-based types (no explicit type field)
                                                has_video = att.get("video_data") is not None
                                                has_image = att.get("image_data") is not None
                                                has_audio = att.get("audio_data") is not None
                                                is_sticker = att.get("render_as_sticker", False)
                                                is_animated = (
                                                    att.get("animated_gif_url") is not None
                                                )

                                                # Get URL based on structure
                                                # FIX 2026-02-02: Try payload.url first (new format)
                                                payload = att.get("payload", {})
                                                payload_url = (
                                                    payload.get("url")
                                                    if isinstance(payload, dict)
                                                    else None
                                                )

                                                if payload_url:
                                                    att_url = payload_url
                                                elif has_video:
                                                    att_url = att["video_data"].get("url")
                                                elif has_image:
                                                    att_url = att["image_data"].get("url")
                                                elif has_audio:
                                                    att_url = att["audio_data"].get("url")
                                                else:
                                                    att_url = att.get("url")

                                                # Detect type by structure or explicit type
                                                if "video" in att_type or has_video:
                                                    msg_text = "Video"
                                                    msg_metadata = {"type": "video", "url": att_url}
                                                elif "audio" in att_type or has_audio:
                                                    msg_text = "Audio"
                                                    msg_metadata = {"type": "audio", "url": att_url}
                                                elif is_sticker or is_animated:
                                                    # GIFs/Stickers
                                                    gif_url = att.get("animated_gif_url") or att_url
                                                    msg_text = "GIF"
                                                    msg_metadata = {"type": "gif", "url": gif_url}
                                                elif (
                                                    "share" in att_type
                                                    or "post" in att_type
                                                    or "media_share" in att_type
                                                ):
                                                    # Shared post (explicit type)
                                                    post_url = (
                                                        att.get("target", {}).get("url") or att_url
                                                    )
                                                    thumbnail_url = (
                                                        att.get("image_data", {}).get("url")
                                                        if att.get("image_data")
                                                        else att.get("preview_url")
                                                    )
                                                    msg_text = "Post compartido"
                                                    msg_metadata = {
                                                        "type": "shared_post",
                                                        "url": post_url,
                                                        "thumbnail_url": thumbnail_url,
                                                    }
                                                elif (
                                                    "image" in att_type
                                                    or "photo" in att_type
                                                    or has_image
                                                ):
                                                    msg_text = "Imagen"
                                                    msg_metadata = {"type": "image", "url": att_url}
                                                elif "link" in att_type:
                                                    msg_text = "Link"
                                                    msg_metadata = {"type": "link", "url": att_url}
                                                else:
                                                    # Unknown type - still save it
                                                    msg_text = "Archivo"
                                                    msg_metadata = {"type": "file", "url": att_url}
                                                break  # Solo usar el primer attachment

                            if not msg_text or not msg_id:
                                results["messages_empty"] += 1
                                continue

                            # REGLA 2: Filtrar por 90 días
                            msg_time_str = msg.get("created_time")
                            if msg_time_str:
                                try:
                                    msg_timestamp = datetime.fromisoformat(
                                        msg_time_str.replace("+0000", "+00:00")
                                    )
                                    if msg_timestamp < days_limit_ago:
                                        results["messages_filtered_180days"] += 1
                                        continue  # Skip messages older than 180 days
                                except ValueError as e:
                                    logger.debug("Ignored ValueError in msg_timestamp = datetime.fromisoformat(: %s", e)

                            # Track attachment processing
                            if msg_text.startswith("[") and msg_text.endswith("]"):
                                results["messages_with_attachments"] += 1

                            # Check if already exists
                            existing = (
                                session.query(Message).filter_by(platform_message_id=msg_id).first()
                            )

                            if existing:
                                results["messages_duplicate"] += 1
                                continue

                            from_data = msg.get("from", {})
                            # Check if sender is the creator (could be user_id OR page_id)
                            is_from_creator = from_data.get("id") in creator_ids
                            role = "assistant" if is_from_creator else "user"

                            # LINK PREVIEW: Enhance metadata with thumbnails for shared content
                            url_to_preview = detect_url_in_metadata(msg_metadata)
                            if url_to_preview:
                                msg_metadata = await generate_link_preview(
                                    url_to_preview, msg_metadata
                                )

                            new_msg = Message(
                                lead_id=lead.id,
                                role=role,
                                content=msg_text,
                                platform_message_id=msg_id,
                                msg_metadata=msg_metadata if msg_metadata else {},
                            )

                            # Parse timestamp
                            msg_time = msg.get("created_time")
                            if msg_time:
                                try:
                                    new_msg.created_at = datetime.fromisoformat(
                                        msg_time.replace("+0000", "+00:00")
                                    )
                                except ValueError as e:
                                    logger.debug("Ignored ValueError in new_msg.created_at = datetime.fromisoformat(: %s", e)

                            session.add(new_msg)
                            results["messages_saved"] += 1
                            messages_saved_this_conv += 1

                        session.commit()
                        results["conversations_processed"] += 1

                        # Auto-categorizar lead después de guardar mensajes
                        if messages_saved_this_conv > 0:
                            try:
                                from core.lead_categorization import (
                                    calcular_categoria,
                                    categoria_a_status_legacy,
                                )

                                # Obtener mensajes del lead para categorización
                                lead_messages = (
                                    session.query(Message)
                                    .filter_by(lead_id=lead.id)
                                    .order_by(Message.created_at)
                                    .all()
                                )
                                mensajes_para_cat = [
                                    {"role": m.role, "content": m.content or ""}
                                    for m in lead_messages
                                ]

                                # Calcular categoría
                                cat_result = calcular_categoria(
                                    mensajes=mensajes_para_cat,
                                    es_cliente=lead.status == "customer",
                                    ultimo_mensaje_lead=lead.last_contact_at,
                                    lead_created_at=lead.first_contact_at,
                                )

                                # Actualizar lead
                                new_status = categoria_a_status_legacy(cat_result.categoria)
                                if lead.status != new_status:
                                    lead.status = new_status
                                    # Recalculate multi-factor score
                                    try:
                                        from services.lead_scoring import recalculate_lead_score
                                        recalculate_lead_score(session, str(lead.id))
                                    except Exception as se:
                                        logger.warning(f"Scoring failed: {se}")
                                        lead.purchase_intent = cat_result.intent_score
                                        lead.score = max(0, min(100, int(cat_result.intent_score * 100)))
                                    session.commit()
                                    logger.info(
                                        f"Lead {lead.username} auto-categorizado: {cat_result.categoria} (intent: {cat_result.intent_score:.2f})"
                                    )

                            except Exception as cat_error:
                                logger.warning(f"Error en auto-categorización: {cat_error}")

                    except Exception as e:
                        results["errors"].append(f"Conv error: {str(e)}")
                        continue

            return {"status": "success", **results}

        finally:
            session.close()

    except Exception as e:
        import traceback

        traceback.print_exc()
        return {"error": str(e), **results}


# =============================================================================
# SYNC QUEUE SYSTEM - Sincronización inteligente con rate limiting
# =============================================================================


@router.post("/start-sync/{creator_id}")
async def start_sync(creator_id: str, background_tasks: BackgroundTasks, admin: str = Depends(require_admin)):
    """
    Inicia sincronización de DMs en background.

    Características:
    - Retorna inmediatamente (no-bloqueante)
    - Procesa 1 conversación cada 3 segundos
    - Pausa automática si hay rate limit
    - Guarda progreso después de cada job

    Uso:
    1. POST /admin/start-sync/fitpack_global → inicia sync
    2. GET /admin/sync-status/fitpack_global → ver progreso
    """
    from api.database import SessionLocal
    from core.sync_worker import run_sync_worker_iteration, start_sync_for_creator

    # Start the sync (queues conversations)
    result = await start_sync_for_creator(creator_id)

    if result["status"] == "started":
        # Run worker in background
        async def run_worker():
            session = SessionLocal()
            try:
                await run_sync_worker_iteration(session, creator_id)
            finally:
                session.close()

        background_tasks.add_task(run_worker)

    return result


@router.get("/sync-status/{creator_id}")
async def sync_status(creator_id: str, admin: str = Depends(require_admin)):
    """
    Obtiene el estado actual del sync.

    Respuestas posibles:
    - status: "not_started" → No hay sync activo
    - status: "running" → Procesando conversaciones
    - status: "rate_limited" → Pausado por rate limit (auto-resume)
    - status: "completed" → Terminado
    """
    from core.sync_worker import get_sync_status

    return get_sync_status(creator_id)


@router.post("/sync-continue/{creator_id}")
async def sync_continue(creator_id: str, background_tasks: BackgroundTasks, admin: str = Depends(require_admin)):
    """
    Continúa el sync si hay jobs pendientes.
    Útil para reanudar después de rate limit.
    """
    from api.database import SessionLocal
    from core.sync_worker import get_sync_status, run_sync_worker_iteration

    status = get_sync_status(creator_id)

    if status["status"] == "not_started":
        return {"error": "No sync started. Use /start-sync first."}

    if status["pending_jobs"] == 0:
        return {"message": "No pending jobs. Sync complete."}

    # Run worker in background
    async def run_worker():
        session = SessionLocal()
        try:
            await run_sync_worker_iteration(session, creator_id)
        finally:
            session.close()

    background_tasks.add_task(run_worker)

    return {
        "status": "continuing",
        "pending_jobs": status["pending_jobs"],
        "message": "Sync resumed in background",
    }


# =============================================================================
# LEAD SYNC: Categorize and score leads based on their conversations
# =============================================================================


@router.post("/sync-leads/{creator_id}")
async def sync_leads_from_conversations(
    creator_id: str, recategorize: bool = False, limit: int = 100, admin: str = Depends(require_admin)
):
    """
    Sync and categorize leads from their conversations.

    This endpoint:
    1. Gets all leads for a creator
    2. Analyzes their messages for purchase intent signals
    3. Updates status (nuevo/interesado/caliente/fantasma) and purchase_intent score
    4. Returns statistics about the sync

    Args:
        creator_id: Creator name or UUID
        recategorize: If True, re-categorize all leads. If False, only process leads with status 'new'
        limit: Maximum number of leads to process

    Returns:
        {
            "total_leads": 50,
            "categorized": {"nuevo": 10, "interesado": 25, "caliente": 5, "fantasma": 8, "cliente": 2},
            "updated": 40,
            "skipped": 10,
            "details": [...]
        }
    """

    from api.database import SessionLocal
    from api.models import Creator, Lead, Message
    from core.lead_categorization import calcular_categoria, categoria_a_status_legacy
    from sqlalchemy import text

    session = SessionLocal()
    try:
        # Get creator
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            creator = (
                session.query(Creator)
                .filter(text("id::text = :cid"))
                .params(cid=creator_id)
                .first()
            )

        if not creator:
            raise HTTPException(status_code=404, detail=f"Creator not found: {creator_id}")

        # Get leads to process
        query = session.query(Lead).filter(Lead.creator_id == creator.id)

        # If not recategorizing, only process new leads
        if not recategorize:
            query = query.filter(Lead.status == "new")

        leads = query.order_by(Lead.last_contact_at.desc()).limit(limit).all()

        if not leads:
            return {
                "status": "ok",
                "message": "No leads to process",
                "total_leads": 0,
                "updated": 0,
            }

        # Get all messages for these leads in single query (avoid N+1)
        lead_ids = [lead.id for lead in leads]
        messages_query = (
            session.query(Message)
            .filter(Message.lead_id.in_(lead_ids))
            .order_by(Message.lead_id, Message.created_at)
            .all()
        )

        # Group messages by lead_id
        messages_by_lead = {}
        for msg in messages_query:
            if msg.lead_id not in messages_by_lead:
                messages_by_lead[msg.lead_id] = []
            messages_by_lead[msg.lead_id].append(
                {"role": msg.role, "content": msg.content or "", "created_at": msg.created_at}
            )

        results = {
            "total_leads": len(leads),
            "updated": 0,
            "skipped": 0,
            "categorized": {
                "nuevo": 0,
                "interesado": 0,
                "caliente": 0,
                "cliente": 0,
                "fantasma": 0,
            },
            "details": [],
        }

        for lead in leads:
            try:
                msgs = messages_by_lead.get(lead.id, [])

                # Get last message from user for fantasma detection
                user_msgs = [m for m in msgs if m["role"] == "user"]
                last_user_msg_time = user_msgs[-1]["created_at"] if user_msgs else None

                # Check if is_customer from context
                ctx = lead.context or {}
                is_cliente = ctx.get("is_customer", False)

                # Calculate category
                result = calcular_categoria(
                    mensajes=msgs,
                    es_cliente=is_cliente,
                    ultimo_mensaje_lead=last_user_msg_time,
                    dias_fantasma=7,
                    lead_created_at=lead.first_contact_at,
                )

                # Map category to legacy status for compatibility
                new_status = categoria_a_status_legacy(result.categoria)

                # Check if update needed
                if (
                    lead.status == new_status
                    and abs((lead.purchase_intent or 0) - result.intent_score) < 0.01
                ):
                    results["skipped"] += 1
                    continue

                # Update lead
                old_status = lead.status
                lead.status = new_status
                # Recalculate multi-factor score
                try:
                    from services.lead_scoring import recalculate_lead_score
                    recalculate_lead_score(session, str(lead.id))
                except Exception as se:
                    logger.warning(f"Scoring failed: {se}")
                    lead.purchase_intent = result.intent_score
                    lead.score = max(0, min(100, int(result.intent_score * 100)))

                results["updated"] += 1
                results["categorized"][result.categoria] += 1
                results["details"].append(
                    {
                        "lead_id": str(lead.id),
                        "username": lead.username,
                        "old_status": old_status,
                        "new_status": new_status,
                        "categoria": result.categoria,
                        "intent_score": round(result.intent_score, 2),
                        "razones": result.razones[:2],
                        "total_messages": len(msgs),
                    }
                )

                # Batch commit every 20 updates
                if results["updated"] % 20 == 0:
                    session.commit()

            except Exception as e:
                logger.warning(f"Error categorizing lead {lead.id}: {e}")
                results["skipped"] += 1

        # Final commit
        session.commit()

        logger.info(
            f"Sync leads for {creator_id}: {results['updated']} updated, {results['skipped']} skipped"
        )
        return {"status": "ok", **results}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"sync_leads error: {e}")
        session.rollback()
        return {"status": "error", "error": str(e)}
    finally:
        session.close()
