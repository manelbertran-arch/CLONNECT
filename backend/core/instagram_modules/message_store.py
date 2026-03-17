"""Message storage sub-module extracted from InstagramHandler."""
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from core.dm_agent_v2 import DMResponse
from core.instagram import InstagramMessage

logger = logging.getLogger("clonnect-instagram")


class MessageStore:
    """Handles recording and persisting messages to DB."""

    def __init__(
        self,
        creator_id: str,
        page_id: str,
        ig_user_id: str,
        status,
        recent_messages: list,
        recent_responses: list,
        extract_media_info_fn: Callable,
    ):
        self.creator_id = creator_id
        self.page_id = page_id
        self.ig_user_id = ig_user_id
        self.status = status
        self.recent_messages = recent_messages
        self.recent_responses = recent_responses
        self._extract_media_info = extract_media_info_fn

    def record_received(self, msg: InstagramMessage):
        """Record received message"""
        self.status.messages_received += 1
        self.status.last_message_time = datetime.now(timezone.utc).isoformat()

        record = {
            "type": "received",
            "follower_id": f"ig_{msg.sender_id}",
            "sender_id": msg.sender_id,
            "text": msg.text,
            "timestamp": self.status.last_message_time,
        }
        self.recent_messages.append(record)
        if len(self.recent_messages) > 10:
            self.recent_messages[:] = self.recent_messages[-10:]

    def record_sent(self):
        """Record sent message"""
        self.status.messages_sent += 1

    def record_response(self, msg: InstagramMessage, response: DMResponse):
        """Record response"""
        # V2 compatibility
        response_text = getattr(response, "content", None) or getattr(response, "response_text", "")
        intent_str = (
            response.intent.value if hasattr(response.intent, "value") else str(response.intent)
        )
        record = {
            "follower_id": f"ig_{msg.sender_id}",
            "sender_id": msg.sender_id,
            "input": msg.text,
            "response": response_text,
            "intent": intent_str,
            "confidence": response.confidence,
            "product": getattr(response, "product_mentioned", None),
            "escalate": getattr(response, "escalate_to_human", False),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.recent_responses.append(record)
        if len(self.recent_responses) > 10:
            self.recent_responses[:] = self.recent_responses[-10:]

    async def save_messages_to_db(
        self,
        msg: InstagramMessage,
        response: DMResponse,
        username: str = "",
        full_name: str = "",
    ) -> bool:
        """
        Save user message and bot response to database (AUTOPILOT mode).

        This is CRITICAL - without this, messages only exist in memory!

        Args:
            msg: Incoming Instagram message
            response: DM agent response
            username: User's Instagram username
            full_name: User's display name

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            from api.database import SessionLocal
            from api.models import Creator, Lead, Message

            session = SessionLocal()
            try:
                # Get creator
                creator = session.query(Creator).filter_by(name=self.creator_id).first()
                if not creator:
                    logger.error(f"[SaveMsg] Creator {self.creator_id} not found")
                    return False

                # Find lead (check both with and without ig_ prefix)
                lead = (
                    session.query(Lead)
                    .filter(
                        Lead.creator_id == creator.id,
                        Lead.platform_user_id.in_([f"ig_{msg.sender_id}", msg.sender_id]),
                    )
                    .first()
                )

                if not lead:
                    # Prevent creating leads for creator's own IDs (prevents ghost leads)
                    known_ids = {self.page_id, self.ig_user_id, "17841400506734756"}
                    if msg.sender_id in known_ids:
                        logger.warning(
                            f"[SaveMsg] Skipping lead creation for known creator ID: {msg.sender_id}"
                        )
                        return False

                    # Create lead if doesn't exist
                    # Use raw sender_id (no ig_ prefix) for consistency
                    try:
                        lead = Lead(
                            creator_id=creator.id,
                            platform="instagram",
                            platform_user_id=msg.sender_id,  # No prefix - prevents duplicates
                            username=username or None,
                            full_name=full_name or None,
                            source="instagram_dm",
                            status="nuevo",
                        )
                        session.add(lead)
                        session.commit()
                        logger.info(f"[SaveMsg] Created lead for {msg.sender_id}")
                    except Exception as e:
                        # Race condition: another request created the lead
                        session.rollback()
                        if "uq_lead_creator_platform" in str(e) or "duplicate" in str(e).lower():
                            logger.info(
                                "[SaveMsg] Lead already exists (race condition), fetching..."
                            )
                            lead = (
                                session.query(Lead)
                                .filter(
                                    Lead.creator_id == creator.id,
                                    Lead.platform_user_id.in_(
                                        [msg.sender_id, f"ig_{msg.sender_id}"]
                                    ),
                                )
                                .first()
                            )
                            if not lead:
                                logger.error(
                                    "[SaveMsg] Could not find lead after constraint error"
                                )
                                return False
                        else:
                            raise

                # Check if user message already exists (by platform_message_id)
                existing_user_msg = (
                    session.query(Message).filter_by(platform_message_id=msg.message_id).first()
                )

                if not existing_user_msg:
                    # Extract media/story info if present
                    media_info = None
                    msg_metadata = {}
                    content = msg.text

                    # Handle story messages first (story data is separate from attachments)
                    if msg.story:
                        story_data = msg.story
                        if story_data.get("reply_to"):
                            msg_metadata["type"] = "story_reply"
                            msg_metadata["link"] = story_data["reply_to"].get("link", "")
                        elif story_data.get("mention"):
                            msg_metadata["type"] = "story_mention"
                            msg_metadata["link"] = story_data["mention"].get("link", "")
                        # Extract CDN URL from attachments for stories
                        if msg.attachments:
                            att = msg.attachments[0]
                            cdn_url = (
                                att.get("video_data", {}).get("url")
                                or att.get("image_data", {}).get("url")
                                or (att.get("payload", {}).get("url") if isinstance(att.get("payload"), dict) else None)
                                or att.get("url")
                            )
                            if cdn_url:
                                msg_metadata["url"] = cdn_url
                        if not content:
                            content = {
                                "story_reply": "Respuesta a story",
                                "story_mention": "Mención en story",
                            }.get(msg_metadata.get("type", ""), "Story")
                    elif msg.attachments:
                        media_info = self._extract_media_info(msg.attachments)
                        if media_info:
                            msg_metadata["type"] = media_info.get("type", "unknown")
                            if media_info.get("url"):
                                msg_metadata["url"] = media_info["url"]
                            if media_info.get("permalink"):
                                msg_metadata["permalink"] = media_info["permalink"]
                            # Use descriptive content if no text
                            if not content:
                                media_type = media_info.get("type", "media")
                                content = {
                                    "image": "Sent a photo",
                                    "video": "Sent a video",
                                    "audio": "Sent a voice message",
                                    "gif": "Sent a GIF",
                                    "sticker": "Sent a sticker",
                                    "story_mention": "Mentioned you in their story",
                                    "share": "Shared a post",
                                    "shared_reel": "Shared a reel",
                                }.get(media_type, "Sent an attachment")

                    # MEDIA CAPTURE: Capture CDN URLs immediately before they expire
                    if msg_metadata.get("url"):
                        try:
                            from services.media_capture_service import (
                                capture_media_from_url,
                                is_cdn_url,
                            )

                            media_url = msg_metadata["url"]
                            if is_cdn_url(media_url):
                                media_type_for_capture = msg_metadata.get("type", "image")
                                if media_type_for_capture in (
                                    "video",
                                    "audio",
                                    "shared_video",
                                    "reel",
                                ):
                                    capture_type = "video"
                                else:
                                    capture_type = "image"

                                captured = await capture_media_from_url(
                                    url=media_url,
                                    media_type=capture_type,
                                    creator_id=self.creator_id,
                                )
                                if captured:
                                    msg_metadata["permanent_url"] = captured
                                    logger.info(f"[SaveMsg] Captured media for {msg.sender_id}")
                        except Exception as capture_err:
                            logger.warning(f"[SaveMsg] Media capture failed: {capture_err}")

                    # Save user message
                    user_msg = Message(
                        lead_id=lead.id,
                        role="user",
                        content=content or "[Media/Attachment]",
                        status="sent",
                        platform_message_id=msg.message_id,
                        msg_metadata=msg_metadata if msg_metadata else None,
                    )
                    session.add(user_msg)
                    logger.debug(f"[SaveMsg] Saved user message {msg.message_id}")

                # Get response text (V2 compatibility)
                response_text = getattr(response, "content", None) or getattr(
                    response, "response_text", ""
                )
                intent_str = (
                    response.intent.value
                    if hasattr(response.intent, "value")
                    else str(response.intent)
                )

                # Save bot response
                bot_msg = Message(
                    lead_id=lead.id,
                    role="assistant",
                    content=response_text,
                    status="sent",
                    intent=intent_str,
                    approved_by="autopilot",
                )
                session.add(bot_msg)

                # Update lead's last_contact and recalculate score
                lead.last_contact_at = datetime.now(timezone.utc)

                try:
                    from services.lead_scoring import recalculate_lead_score

                    recalculate_lead_score(session, str(lead.id))
                except Exception as score_err:
                    logger.warning(f"[SaveMsg] Scoring failed: {score_err}")

                session.commit()
                logger.info(f"[SaveMsg] Saved messages for {msg.sender_id} (lead_id={lead.id})")

                # Invalidate cache for this creator
                try:
                    from api.cache import api_cache

                    api_cache.invalidate(f"conversations:{self.creator_id}")
                    api_cache.invalidate(f"leads:{self.creator_id}")
                    api_cache.invalidate(
                        f"follower_detail:{self.creator_id}:{lead.platform_user_id}"
                    )
                except Exception as cache_err:
                    logger.debug(f"[SaveMsg] Cache invalidation failed: {cache_err}")

                # Notify frontend via SSE
                try:
                    from api.routers.events import notify_creator

                    await notify_creator(
                        self.creator_id,
                        "new_message",
                        {
                            "follower_id": lead.platform_user_id,
                            "role": "user",
                        },
                    )
                except Exception as sse_err:
                    logger.debug(f"[SaveMsg] SSE notification failed: {sse_err}")

                return True

            finally:
                session.close()

        except Exception as e:
            logger.error(f"[SaveMsg] Error saving messages: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return False

    async def save_user_message_to_db(
        self,
        msg: InstagramMessage,
        username: str = "",
        full_name: str = "",
    ) -> bool:
        """
        Save only user message to database (when bot doesn't respond).

        Used when creator already responded manually.

        Args:
            msg: Incoming Instagram message
            username: User's Instagram username
            full_name: User's display name

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            from api.database import SessionLocal
            from api.models import Creator, Lead, Message

            session = SessionLocal()
            try:
                # Get creator
                creator = session.query(Creator).filter_by(name=self.creator_id).first()
                if not creator:
                    logger.error(f"[SaveUserMsg] Creator {self.creator_id} not found")
                    return False

                # Find lead (check both with and without ig_ prefix)
                lead = (
                    session.query(Lead)
                    .filter(
                        Lead.creator_id == creator.id,
                        Lead.platform_user_id.in_([f"ig_{msg.sender_id}", msg.sender_id]),
                    )
                    .first()
                )

                if not lead:
                    # Prevent creating leads for creator's own IDs (prevents ghost leads)
                    known_ids = {self.page_id, self.ig_user_id, "17841400506734756"}
                    if msg.sender_id in known_ids:
                        logger.warning(
                            f"[SaveUserMsg] Skipping lead creation for known creator ID: {msg.sender_id}"
                        )
                        return False

                    # Create lead if doesn't exist
                    # Use raw sender_id (no ig_ prefix) for consistency
                    try:
                        lead = Lead(
                            creator_id=creator.id,
                            platform="instagram",
                            platform_user_id=msg.sender_id,  # No prefix - prevents duplicates
                            username=username or None,
                            full_name=full_name or None,
                            source="instagram_dm",
                            status="nuevo",
                        )
                        session.add(lead)
                        session.commit()
                        logger.info(f"[SaveUserMsg] Created lead for {msg.sender_id}")
                    except Exception as e:
                        # Race condition: another request created the lead
                        session.rollback()
                        if "uq_lead_creator_platform" in str(e) or "duplicate" in str(e).lower():
                            logger.info(
                                "[SaveUserMsg] Lead already exists (race condition), fetching..."
                            )
                            lead = (
                                session.query(Lead)
                                .filter(
                                    Lead.creator_id == creator.id,
                                    Lead.platform_user_id.in_(
                                        [msg.sender_id, f"ig_{msg.sender_id}"]
                                    ),
                                )
                                .first()
                            )
                            if not lead:
                                logger.error(
                                    "[SaveUserMsg] Could not find lead after constraint error"
                                )
                                return False
                        else:
                            raise

                # Check if user message already exists
                existing_msg = (
                    session.query(Message).filter_by(platform_message_id=msg.message_id).first()
                )

                if existing_msg:
                    logger.debug(f"[SaveUserMsg] Message {msg.message_id} already exists")
                    # Don't update last_contact_at for duplicate messages — it breaks
                    # conversation sort order when reconciliation reprocesses old messages.
                    return True

                # Extract media info if present
                media_info = None
                msg_metadata = {}
                content = msg.text
                if msg.attachments:
                    media_info = self._extract_media_info(msg.attachments)
                    if media_info:
                        msg_metadata["type"] = media_info.get("type", "unknown")
                        if media_info.get("url"):
                            msg_metadata["url"] = media_info["url"]
                        # Use descriptive content if no text
                        if not content:
                            media_type = media_info.get("type", "media")
                            content = {
                                "image": "Sent a photo",
                                "video": "Sent a video",
                                "audio": "Sent a voice message",
                                "gif": "Sent a GIF",
                                "sticker": "Sent a sticker",
                                "story_mention": "Mentioned you in their story",
                                "share": "Shared a post",
                                "shared_reel": "Shared a reel",
                            }.get(media_type, "Sent an attachment")

                # MEDIA CAPTURE: Capture CDN URLs immediately before they expire
                # Instagram CDN URLs expire after ~24 hours
                if msg_metadata.get("url"):
                    try:
                        from services.media_capture_service import (
                            capture_media_from_url,
                            is_cdn_url,
                        )

                        media_url = msg_metadata["url"]
                        if is_cdn_url(media_url):
                            media_type_for_capture = msg_metadata.get("type", "image")
                            if media_type_for_capture in ("video", "audio", "shared_video", "reel"):
                                capture_type = "video"
                            else:
                                capture_type = "image"

                            captured = await capture_media_from_url(
                                url=media_url,
                                media_type=capture_type,
                                creator_id=self.creator_id,
                            )
                            if captured:
                                msg_metadata["permanent_url"] = captured
                                logger.info(f"[SaveUserMsg] Captured media for {msg.sender_id}")
                    except Exception as capture_err:
                        logger.warning(f"[SaveUserMsg] Media capture failed: {capture_err}")

                # Save user message
                user_msg = Message(
                    lead_id=lead.id,
                    role="user",
                    content=content or "[Media/Attachment]",
                    status="sent",
                    platform_message_id=msg.message_id,
                    msg_metadata=msg_metadata if msg_metadata else None,
                )
                session.add(user_msg)

                # Update lead's last_contact and recalculate score
                lead.last_contact_at = datetime.now(timezone.utc)

                try:
                    from services.lead_scoring import recalculate_lead_score

                    recalculate_lead_score(session, str(lead.id))
                except Exception as score_err:
                    logger.warning(f"[SaveUserMsg] Scoring failed: {score_err}")

                session.commit()
                logger.info(
                    f"[SaveUserMsg] Saved user message for {msg.sender_id} (lead_id={lead.id})"
                )

                # Invalidate cache for this creator
                try:
                    from api.cache import api_cache

                    api_cache.invalidate(f"conversations:{self.creator_id}")
                    api_cache.invalidate(f"leads:{self.creator_id}")
                    api_cache.invalidate(
                        f"follower_detail:{self.creator_id}:{lead.platform_user_id}"
                    )
                except Exception as cache_err:
                    logger.debug(f"[SaveUserMsg] Cache invalidation failed: {cache_err}")

                # Notify frontend via SSE
                try:
                    from api.routers.events import notify_creator

                    await notify_creator(
                        self.creator_id,
                        "new_message",
                        {
                            "follower_id": lead.platform_user_id,
                            "role": "user",
                        },
                    )
                except Exception as sse_err:
                    logger.debug(f"[SaveUserMsg] SSE notification failed: {sse_err}")

                return True

            finally:
                session.close()

        except Exception as e:
            logger.error(f"[SaveUserMsg] Error saving user message: {e}")
            import traceback

            logger.error(traceback.format_exc())
            return False
