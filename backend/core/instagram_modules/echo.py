"""
Instagram echo, reaction, and anti-duplication handlers.

Records creator manual responses, processes reaction events,
and checks if creator already responded recently.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from services.cloudinary_service import get_cloudinary_service

logger = logging.getLogger("clonnect-instagram")


async def record_creator_manual_response(handler, echo_msg: Dict[str, Any]) -> bool:
    """
    Record a creator's manual response in the database.
    This allows us to detect if creator already responded before bot sends.
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message

        session = SessionLocal()
        try:
            # Find creator
            creator = session.query(Creator).filter_by(name=handler.creator_id).first()
            if not creator:
                logger.warning(f"[Echo] Creator {handler.creator_id} not found")
                return False

            # The recipient of an echo message is the follower
            follower_id = echo_msg["recipient_id"]

            # Find or create lead
            lead = (
                session.query(Lead)
                .filter_by(creator_id=creator.id, platform_user_id=follower_id)
                .first()
            )

            if not lead:
                # Also check with ig_ prefix
                lead = (
                    session.query(Lead)
                    .filter_by(creator_id=creator.id, platform_user_id=f"ig_{follower_id}")
                    .first()
                )

            if not lead:
                logger.info(f"[Echo] Lead not found for {follower_id}, skipping record")
                return False

            # Check if this exact message already exists (avoid duplicates)
            existing = (
                session.query(Message)
                .filter_by(lead_id=lead.id, platform_message_id=echo_msg["message_id"])
                .first()
            )

            if existing:
                logger.debug(f"[Echo] Message {echo_msg['message_id']} already recorded")
                # Still update last_contact_at even if message exists
                lead.last_contact_at = datetime.now(timezone.utc)
                session.commit()
                return True

            # Extract media info from echo attachments (if any)
            msg_meta: Dict[str, Any] = {"source": "instagram_echo", "is_manual": True}
            attachments = echo_msg.get("attachments", [])
            if attachments:
                from core.instagram_modules.media import extract_media_info

                media_info = extract_media_info(attachments)
                if media_info:
                    media_url = media_info.get("url")
                    media_type = media_info.get("type", "unknown")

                    # Capture CDN media permanently before it expires
                    if media_url:
                        try:
                            from services.media_capture_service import capture_media_from_url, is_cdn_url

                            uploaded = False
                            cloudinary_svc = get_cloudinary_service()
                            if cloudinary_svc.is_configured and is_cdn_url(media_url):
                                folder = f"clonnect/{handler.creator_id or 'unknown'}/media"
                                result = cloudinary_svc.upload_from_url(
                                    url=media_url,
                                    media_type=media_type,
                                    folder=folder,
                                    tags=["instagram", "echo", f"creator_{handler.creator_id}"],
                                )
                                if result.success:
                                    media_info["original_url"] = media_url
                                    media_info["url"] = result.url
                                    media_info["cloudinary_id"] = result.public_id
                                    uploaded = True
                                    logger.info(f"[Echo] Media uploaded to Cloudinary: {result.public_id}")

                            # Fallback: base64 or permanent_url
                            if not uploaded and is_cdn_url(media_url):
                                captured = await capture_media_from_url(
                                    url=media_url,
                                    media_type=media_type,
                                    creator_id=handler.creator_id,
                                )
                                if captured:
                                    media_info["permanent_url"] = captured
                        except Exception as e:
                            logger.warning(f"[Echo] Media capture failed: {e}")

                    # Merge media fields into msg_metadata
                    for key in ("type", "url", "permanent_url",
                                "original_url", "cloudinary_id", "permalink"):
                        if key in media_info:
                            msg_meta[key] = media_info[key]

            # Record the creator's manual response
            msg = Message(
                lead_id=lead.id,
                role="assistant",
                content=echo_msg["text"],
                status="sent",
                approved_by="creator_manual",
                platform_message_id=echo_msg["message_id"],
                msg_metadata=msg_meta,
            )
            session.add(msg)

            # Update lead last_contact
            lead.last_contact_at = datetime.now(timezone.utc)

            # Auto-discard pending copilot suggestions for this lead
            try:
                from core.copilot_service import get_copilot_service

                get_copilot_service().auto_discard_pending_for_lead(
                    lead.id, session=session,
                    creator_response=echo_msg["text"],
                    creator_id=handler.creator_id,
                )
            except Exception as e:
                logger.warning(f"[Echo] Auto-discard failed: {e}")

            session.commit()

            # Invalidate cache and notify frontend
            try:
                from api.cache import api_cache

                api_cache.invalidate(f"conversations:{handler.creator_id}")
                api_cache.invalidate(
                    f"follower_detail:{handler.creator_id}:{lead.platform_user_id}"
                )
            except Exception as e:
                logger.debug(f"[Echo] cache invalidation failed: {e}")

            try:
                from api.routers.events import notify_creator

                await notify_creator(
                    handler.creator_id,
                    "new_message",
                    {"follower_id": lead.platform_user_id, "role": "assistant"},
                )
            except Exception as e:
                logger.debug(f"[Echo] SSE notify failed: {e}")

            logger.info(f"[Echo] Recorded creator manual response to {follower_id}")
            return True

        finally:
            session.close()

    except Exception as e:
        logger.error(f"[Echo] Error recording creator response: {e}")
        return False


async def process_reaction_events(handler, payload: Dict[str, Any]) -> int:
    """
    Process message reaction events from webhook.

    Reactions are saved as messages with metadata.type="reaction" so the
    frontend can render them as small emoji bubbles. They do NOT trigger
    the bot response pipeline.
    """
    recorded = 0

    try:
        for entry in payload.get("entry", []):
            for messaging in entry.get("messaging", []):
                if "reaction" not in messaging:
                    continue

                reaction_data = messaging["reaction"]
                action = reaction_data.get("action", "")

                if action != "react":
                    continue

                sender_id = messaging.get("sender", {}).get("id", "")
                recipient_id = messaging.get("recipient", {}).get("id", "")

                # Determine emoji
                emoji = reaction_data.get("emoji", "")
                if not emoji:
                    reaction_type = reaction_data.get("reaction", "love")
                    emoji_map = {
                        "love": "❤️", "haha": "😂", "wow": "😮",
                        "sad": "😢", "angry": "😠", "like": "👍",
                    }
                    emoji = emoji_map.get(reaction_type, "❤️")

                if emoji == "❤" or emoji == "\u2764":
                    emoji = "❤️"

                reacted_to_mid = reaction_data.get("mid", "")

                # Determine role
                known_ids = getattr(handler, "known_creator_ids", set())
                if not known_ids:
                    known_ids = {handler.page_id, handler.ig_user_id}
                role = "assistant" if sender_id in known_ids else "user"

                follower_id = sender_id if role == "user" else recipient_id

                # Save to DB
                try:
                    from api.database import SessionLocal
                    from api.models import Creator, Lead, Message

                    session = SessionLocal()
                    try:
                        creator = session.query(Creator).filter_by(name=handler.creator_id).first()
                        if not creator:
                            continue

                        lead = (
                            session.query(Lead)
                            .filter_by(creator_id=creator.id, platform_user_id=follower_id)
                            .first()
                        )
                        if not lead:
                            lead = (
                                session.query(Lead)
                                .filter_by(creator_id=creator.id, platform_user_id=f"ig_{follower_id}")
                                .first()
                            )
                        if not lead:
                            logger.debug(f"[Reaction] Lead not found for {follower_id}")
                            continue

                        # Check duplicate
                        from sqlalchemy import text as sa_text
                        existing = (
                            session.query(Message)
                            .filter(
                                Message.lead_id == lead.id,
                                sa_text("msg_metadata->>'type' = 'reaction'"),
                                sa_text("msg_metadata->>'reacted_to_mid' = :mid"),
                                Message.role == role,
                            )
                            .params(mid=reacted_to_mid)
                            .first()
                        )
                        if existing:
                            logger.debug(f"[Reaction] Already recorded reaction on {reacted_to_mid}")
                            continue

                        msg = Message(
                            lead_id=lead.id,
                            role=role,
                            content=emoji,
                            status="sent",
                            msg_metadata={
                                "type": "reaction",
                                "emoji": emoji,
                                "reacted_to_mid": reacted_to_mid,
                            },
                        )
                        session.add(msg)
                        lead.last_contact_at = datetime.now(timezone.utc)
                        session.commit()
                        recorded += 1
                        logger.info(
                            f"[Reaction] {role} reacted {emoji} to {reacted_to_mid} "
                            f"(lead={lead.username})"
                        )

                        # Invalidate cache and notify frontend
                        try:
                            from api.cache import api_cache
                            api_cache.invalidate(f"conversations:{handler.creator_id}")
                            api_cache.invalidate(
                                f"follower_detail:{handler.creator_id}:{lead.platform_user_id}"
                            )
                        except Exception as e:
                            logger.debug(f"[Echo:Reaction] cache invalidation failed: {e}")

                        try:
                            from api.routers.events import notify_creator
                            await notify_creator(
                                handler.creator_id,
                                "new_message",
                                {"follower_id": lead.platform_user_id, "role": role},
                            )
                        except Exception as e:
                            logger.debug(f"[Echo:Reaction] SSE notify failed: {e}")
                    finally:
                        session.close()
                except Exception as e:
                    logger.error(f"[Reaction] Error saving reaction: {e}")

    except Exception as e:
        logger.error(f"[Reaction] Error processing reaction events: {e}")

    return recorded


async def has_creator_responded_recently(
    handler, follower_id: str, window_seconds: int = 300
) -> bool:
    """
    Check if the creator has manually responded to this follower recently.
    Used to prevent duplicate bot responses when creator already replied.
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=handler.creator_id).first()
            if not creator:
                return False

            lead = (
                session.query(Lead)
                .filter_by(creator_id=creator.id, platform_user_id=follower_id)
                .first()
            )

            if not lead:
                lead = (
                    session.query(Lead)
                    .filter_by(creator_id=creator.id, platform_user_id=f"ig_{follower_id}")
                    .first()
                )

            if not lead:
                return False

            from datetime import timedelta

            cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)

            recent_creator_msg = (
                session.query(Message)
                .filter(
                    Message.lead_id == lead.id,
                    Message.role == "assistant",
                    Message.created_at >= cutoff_time,
                )
                .order_by(Message.created_at.desc())
                .first()
            )

            if recent_creator_msg:
                is_manual = (
                    recent_creator_msg.approved_by == "creator_manual"
                    or (recent_creator_msg.msg_metadata or {}).get("is_manual") is True
                )

                last_user_msg = (
                    session.query(Message)
                    .filter(Message.lead_id == lead.id, Message.role == "user")
                    .order_by(Message.created_at.desc())
                    .first()
                )

                if last_user_msg and recent_creator_msg.created_at > last_user_msg.created_at:
                    logger.info(
                        f"[AntiDup] Creator already responded to {follower_id} "
                        f"(manual={is_manual}, msg_id={recent_creator_msg.id})"
                    )
                    return True

            return False

        finally:
            session.close()

    except Exception as e:
        logger.error(f"[AntiDup] Error checking creator response: {e}")
        return False
