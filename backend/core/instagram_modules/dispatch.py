"""
Instagram response dispatch — copilot and autopilot modes.

Handles routing DM agent responses to either copilot (pending approval)
or autopilot (auto-send) mode.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger("clonnect-instagram")


async def dispatch_response(
    handler,
    message,
    response,
    response_text: str,
    intent_str: str,
    username: str,
    full_name: str,
    copilot_enabled: bool,
) -> Dict[str, Any]:
    """Dispatch a DM response through copilot or autopilot mode."""
    if copilot_enabled:
        return await _handle_copilot_mode(
            handler, message, response, response_text, intent_str, username, full_name
        )
    else:
        return await _handle_autopilot_mode(
            handler, message, response, response_text, intent_str, username, full_name
        )


async def _handle_copilot_mode(
    handler, message, response, response_text, intent_str, username, full_name
) -> Dict[str, Any]:
    """COPILOT MODE: Save as pending approval, don't send."""
    from core.copilot_service import get_copilot_service
    from core.instagram_modules.echo import has_creator_responded_recently

    copilot = get_copilot_service()

    # Anti-zombie check #1: Creator already responded?
    creator_already_responded = await has_creator_responded_recently(
        handler, message.sender_id, window_seconds=1800
    )
    if creator_already_responded:
        logger.info(
            f"[Copilot:AntiZombie] Skipping suggestion for {message.sender_id} — "
            "creator already responded"
        )
        await handler._save_user_message_to_db(
            msg=message, username=username, full_name=full_name,
        )
        return {
            "message_id": message.message_id,
            "sender_id": message.sender_id,
            "copilot_mode": True,
            "status": "skipped_creator_responded",
        }

    # Anti-zombie check #2: Already has pending suggestion?
    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message as MsgModel

        _session = SessionLocal()
        try:
            _creator = _session.query(Creator).filter_by(name=handler.creator_id).first()
            if _creator:
                _lead = (
                    _session.query(Lead)
                    .filter(
                        Lead.creator_id == _creator.id,
                        Lead.platform_user_id.in_([message.sender_id, f"ig_{message.sender_id}"]),
                    )
                    .first()
                )
                if _lead:
                    existing_pending = (
                        _session.query(MsgModel)
                        .filter(
                            MsgModel.lead_id == _lead.id,
                            MsgModel.role == "assistant",
                            MsgModel.status == "pending_approval",
                        )
                        .first()
                    )
                    if existing_pending:
                        logger.info(
                            f"[Copilot:AntiZombie] Skipping — already has pending "
                            f"suggestion {existing_pending.id} for {message.sender_id}"
                        )
                        await handler._save_user_message_to_db(
                            msg=message, username=username, full_name=full_name,
                        )
                        return {
                            "message_id": message.message_id,
                            "sender_id": message.sender_id,
                            "copilot_mode": True,
                            "status": "skipped_existing_pending",
                        }
        finally:
            _session.close()
    except Exception as e:
        logger.warning(f"[Copilot:AntiZombie] Pending check failed: {e}")

    # Extract media info for attachment messages
    copilot_user_msg = message.text
    copilot_msg_metadata = {}

    if message.story:
        story_data = message.story
        if story_data.get("reply_to"):
            copilot_msg_metadata["type"] = "story_reply"
            copilot_msg_metadata["link"] = story_data["reply_to"].get("link", "")
        elif story_data.get("mention"):
            copilot_msg_metadata["type"] = "story_mention"
            copilot_msg_metadata["link"] = story_data["mention"].get("link", "")
        if message.attachments:
            att = message.attachments[0]
            cdn_url = (
                att.get("video_data", {}).get("url")
                or att.get("image_data", {}).get("url")
                or (att.get("payload", {}).get("url") if isinstance(att.get("payload"), dict) else None)
                or att.get("url")
            )
            if cdn_url:
                copilot_msg_metadata["url"] = cdn_url
    elif message.attachments:
        from core.instagram_modules.media import extract_media_info

        media_info = extract_media_info(message.attachments)
        if media_info:
            copilot_msg_metadata["type"] = media_info.get("type", "unknown")
            if media_info.get("url"):
                copilot_msg_metadata["url"] = media_info["url"]
            if media_info.get("permalink"):
                copilot_msg_metadata["permalink"] = media_info["permalink"]
            if not copilot_user_msg:
                media_type = media_info.get("type", "media")
                copilot_user_msg = {
                    "image": "Sent a photo",
                    "video": "Sent a video",
                    "audio": "Sent a voice message",
                    "gif": "Sent a GIF",
                    "sticker": "Sent a sticker",
                    "story_mention": "Mentioned you in their story",
                    "share": "Shared a post",
                    "shared_reel": "Shared a reel",
                }.get(media_type, "Sent an attachment")
    if not copilot_user_msg:
        copilot_user_msg = "[Media/Attachment]"

    # Carry Best-of-N candidates from DM response metadata
    if response.metadata and response.metadata.get("best_of_n"):
        copilot_msg_metadata["best_of_n"] = response.metadata["best_of_n"]

    pending = await copilot.create_pending_response(
        creator_id=handler.creator_id,
        lead_id="",
        follower_id=message.sender_id,
        platform="instagram",
        user_message=copilot_user_msg,
        user_message_id=message.message_id,
        suggested_response=response_text,
        intent=intent_str,
        confidence=response.confidence,
        username=username,
        full_name=full_name,
        msg_metadata=copilot_msg_metadata if copilot_msg_metadata else None,
    )

    logger.info(f"[Copilot] Created pending response {pending.id} for {message.sender_id}")

    return {
        "message_id": message.message_id,
        "sender_id": message.sender_id,
        "copilot_mode": True,
        "pending_id": pending.id,
        "suggested_response": response_text,
        "intent": intent_str,
        "confidence": response.confidence,
        "status": "pending_approval",
    }


async def _handle_autopilot_mode(
    handler, message, response, response_text, intent_str, username, full_name
) -> Dict[str, Any]:
    """AUTOPILOT MODE: Check if creator already responded before sending."""
    from core.instagram_modules.echo import has_creator_responded_recently

    creator_already_responded = await has_creator_responded_recently(
        handler, message.sender_id, window_seconds=300
    )

    if creator_already_responded:
        logger.info(
            f"[AntiDup] Skipping autopilot response to {message.sender_id} - "
            "creator already responded"
        )
        await handler._save_user_message_to_db(
            msg=message, username=username, full_name=full_name,
        )
        return {
            "message_id": message.message_id,
            "sender_id": message.sender_id,
            "copilot_mode": False,
            "status": "skipped_creator_responded",
            "reason": "Creator already responded manually",
        }

    # Bot sends directly (guarded by send_response)
    sent = await handler.send_response(message.sender_id, response_text)

    await handler._save_user_message_to_db(
        msg=message, username=username, full_name=full_name,
    )

    if sent:
        await handler.dm_agent.save_manual_message(
            message.sender_id, response_text, sent=True
        )
        return {
            "message_id": message.message_id,
            "sender_id": message.sender_id,
            "copilot_mode": False,
            "response": response_text[:50] + "...",
            "intent": intent_str,
            "confidence": response.confidence,
            "status": "sent",
        }

    # Guard blocked — save as pending instead
    from core.copilot_service import get_copilot_service
    copilot = get_copilot_service()

    pending = await copilot.create_pending_response(
        creator_id=handler.creator_id,
        lead_id="",
        follower_id=message.sender_id,
        platform="instagram",
        user_message=message.text or "[Media/Attachment]",
        user_message_id=message.message_id,
        suggested_response=response_text,
        intent=intent_str,
        confidence=response.confidence,
        username=username,
        full_name=full_name,
    )

    return {
        "message_id": message.message_id,
        "sender_id": message.sender_id,
        "copilot_mode": False,
        "autopilot_blocked": True,
        "pending_id": pending.id,
        "suggested_response": response_text,
        "intent": intent_str,
        "confidence": response.confidence,
        "status": "pending_approval",
    }
