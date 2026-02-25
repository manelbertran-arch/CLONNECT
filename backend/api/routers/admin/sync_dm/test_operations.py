"""Test endpoints for sync verification and frontend testing."""
import logging
from datetime import datetime, timedelta, timezone

from api.auth import require_admin
from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/test-full-sync/{creator_id}/{username}")
async def test_full_sync_conversation(creator_id: str, username: str, admin: str = Depends(require_admin)):
    """
    TEST ENDPOINT: Sincronizar TODOS los mensajes de una conversacion especifica
    usando paginacion completa.

    Ejemplo: POST /admin/test-full-sync/manel_bertran_luque/stefanobonanno
    """
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
                        msg_text = "[Te menciono en su story]"
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
                        emoji = reactions[0].get("reaction", "\u2764\ufe0f")
                        # Ensure heart emoji has variation selector (U+FE0F) for red rendering
                        if emoji == "\u2764" or emoji == "\u2764":
                            emoji = "\u2764\ufe0f"
                        msg_text = f"[Reaccion: {emoji}]"
                        metadata["emoji"] = emoji
                    else:
                        msg_text = "[Reaccion]"
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


@router.post("/test-shared-post/{creator_id}/{lead_id}")
async def insert_test_shared_post(creator_id: str, lead_id: str, admin: str = Depends(require_admin)):
    """
    Insert a test shared_post message with thumbnail for frontend testing.
    """
    try:
        import uuid

        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Message

        if not DATABASE_URL or not SessionLocal:
            return {"error": "Database not configured"}

        # Get a real Instagram preview
        from api.services.screenshot_service import get_microlink_preview

        test_url = "https://www.instagram.com/p/C3xK7ZmOQVz/"
        preview = await get_microlink_preview(test_url)

        session = SessionLocal()
        try:
            # Verify creator and lead exist
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"error": f"Creator {creator_id} not found"}

            lead = session.query(Lead).filter_by(id=uuid.UUID(lead_id)).first()
            if not lead:
                return {"error": f"Lead {lead_id} not found"}

            # Create test message with shared_post
            msg_metadata = {
                "type": "shared_post",
                "platform": "instagram",
                "url": test_url,
                "thumbnail_url": preview.get("thumbnail_url") if preview else None,
                "title": preview.get("title") if preview else "Instagram Post",
                "author": preview.get("author") if preview else None,
            }

            test_msg = Message(
                lead_id=lead.id,
                role="user",
                content="Mira este post!",
                msg_metadata=msg_metadata,
                created_at=datetime.now(timezone.utc),
            )
            session.add(test_msg)
            session.commit()

            return {
                "status": "success",
                "message_id": str(test_msg.id),
                "metadata": msg_metadata,
                "lead_username": lead.username,
            }

        finally:
            session.close()

    except Exception as e:
        import traceback

        traceback.print_exc()
        return {"error": str(e)}
