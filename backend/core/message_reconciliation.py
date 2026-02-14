"""
Message Reconciliation System

Automatic reconciliation of Instagram messages between API and database.
Runs as part of the nurturing scheduler to ensure no messages are lost.

Features:
- Periodic reconciliation every 5 minutes
- Startup reconciliation of last 24 hours
- Gap detection health check
- No duplicates (checks by platform_message_id)
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("clonnect-reconciliation")

# Configuration
RECONCILIATION_LOOKBACK_HOURS = 24  # How far back to check on startup
RECONCILIATION_INTERVAL_MINUTES = 5  # How often to run periodic reconciliation
MAX_CONVERSATIONS_PER_CYCLE = 20  # Limit per reconciliation cycle (reduced to avoid API limits)


async def _fetch_profile_for_lead(user_id: str, access_token: str) -> Dict[str, Any]:
    """
    Fetch Instagram profile for a lead.
    Returns dict with username, name, profile_pic or empty dict on failure.
    """
    try:
        from core.instagram_profile import fetch_instagram_profile_with_retry

        result = await fetch_instagram_profile_with_retry(user_id, access_token, max_retries=1)
        if result.success and result.profile:
            return result.profile
    except Exception as e:
        logger.debug(f"[Reconciliation] Profile fetch failed for {user_id}: {e}")

    return {}


def _extract_media_from_attachments(attachments: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extract media info from Instagram message attachments.

    FIX 2026-02-05: Support both Meta formats:
    - New format (Instagram Messaging API): payload.url
    - Legacy format: image_data.url, video_data.url, audio_data.url

    Returns dict with:
        - type: 'image', 'video', 'audio', 'story_mention', 'share', etc.
        - url: Media URL if available
        - content_text: Human-readable description for the message content
    """
    if not attachments:
        return {}

    att = attachments[0]  # Usually only one attachment
    att_type = (att.get("type") or "").lower()

    # Extract URL - try payload.url FIRST (new Instagram Messaging API format)
    media_url = None
    payload = att.get("payload", {})
    if isinstance(payload, dict) and payload.get("url"):
        media_url = payload["url"]
    # Then try legacy formats
    elif att.get("video_data", {}).get("url"):
        media_url = att["video_data"]["url"]
    elif att.get("image_data", {}).get("url"):
        media_url = att["image_data"]["url"]
    elif att.get("audio_data", {}).get("url"):
        media_url = att["audio_data"]["url"]
    elif att.get("story", {}).get("url"):
        media_url = att["story"]["url"]
    elif att.get("story", {}).get("mention", {}).get("link"):
        media_url = att["story"]["mention"]["link"]
    elif att.get("share", {}).get("link"):
        media_url = att["share"]["link"]
    elif att.get("url"):
        media_url = att["url"]

    # Deep fallback: search any URL-like field
    if not media_url:
        for key, value in att.items():
            if isinstance(value, str) and value.startswith("https://"):
                media_url = value
                break
            elif isinstance(value, dict):
                for subkey, subval in value.items():
                    if isinstance(subval, str) and subval.startswith("https://"):
                        media_url = subval
                        break

    # Determine type and content text based on att_type or structure
    media_type = "unknown"
    content_text = "Sent an attachment"

    # Check by type field first
    if att_type == "image":
        media_type = "image"
        content_text = "Sent a photo"
    elif att_type == "video":
        media_type = "video"
        content_text = "Sent a video"
    elif att_type == "audio":
        media_type = "audio"
        content_text = "Sent a voice message"
    elif att_type == "animated_image" or att_type == "animated_gif":
        media_type = "gif"
        content_text = "Sent a GIF"
    elif att_type == "sticker":
        media_type = "sticker"
        content_text = "Sent a sticker"
    elif att_type == "story_mention" or "story" in att_type:
        media_type = "story_mention"
        content_text = "Mentioned you in their story"
    elif att_type == "share":
        media_type = "share"
        share_link = att.get("share", {}).get("link", "") or media_url or ""
        if "reel" in share_link.lower():
            media_type = "shared_reel"
            content_text = "Shared a reel"
        else:
            content_text = "Shared a post"
    elif att_type == "reel":
        media_type = "shared_reel"
        content_text = "Shared a reel"
    # Fallback: check by structure if type field is missing/generic
    elif att.get("image_data"):
        media_type = "image"
        content_text = "Sent a photo"
    elif att.get("video_data"):
        media_type = "video"
        content_text = "Sent a video"
    elif att.get("audio_data"):
        media_type = "audio"
        content_text = "Sent a voice message"
    elif att.get("story"):
        media_type = "story_mention"
        content_text = "Mentioned you in their story"
    elif att.get("share"):
        media_type = "share"
        content_text = "Shared a post"

    result = {
        "type": media_type,
        "content_text": content_text,
    }

    if media_url:
        result["url"] = media_url

    return result


async def _queue_profile_enrichment(creator_id: str, user_id: str) -> None:
    """Queue a lead for profile enrichment retry."""
    try:
        from api.database import SessionLocal
        from api.models import SyncQueue

        session = SessionLocal()
        try:
            # Check if already queued
            existing = (
                session.query(SyncQueue)
                .filter_by(
                    creator_id=creator_id,
                    conversation_id=f"profile_retry:{user_id}",
                )
                .filter(SyncQueue.status.in_(["pending", "processing"]))
                .first()
            )
            if existing:
                return

            queue_item = SyncQueue(
                creator_id=creator_id,
                conversation_id=f"profile_retry:{user_id}",
                status="pending",
                attempts=0,
            )
            session.add(queue_item)
            session.commit()
            logger.debug(f"[Reconciliation] Queued profile retry for {user_id}")

        finally:
            session.close()

    except Exception as e:
        logger.error(f"[Reconciliation] Failed to queue profile retry: {e}")


async def enrich_leads_without_profile(
    creator_id: str, access_token: str, limit: int = 10
) -> Dict[str, int]:
    """
    Find and enrich leads that don't have profile info.
    Called periodically to fix leads created without profiles.

    Returns:
        Dict with counts: processed, enriched, failed
    """
    from api.database import SessionLocal
    from api.models import Creator, Lead

    result = {"processed": 0, "enriched": 0, "failed": 0, "queued": 0}

    session = SessionLocal()
    try:
        # Get creator
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            return result

        # Find leads without username
        leads_to_enrich = (
            session.query(Lead)
            .filter(
                Lead.creator_id == creator.id,
                Lead.platform == "instagram",
                (Lead.username.is_(None)) | (Lead.username == ""),
            )
            .limit(limit)
            .all()
        )

        for lead in leads_to_enrich:
            result["processed"] += 1

            # Extract user_id from platform_user_id (ig_XXXXX -> XXXXX)
            user_id = lead.platform_user_id.replace("ig_", "")

            # Try to fetch profile
            profile = await _fetch_profile_for_lead(user_id, access_token)

            if profile.get("username"):
                lead.username = profile["username"]
                lead.full_name = profile.get("name") or lead.full_name
                lead.profile_pic_url = profile.get("profile_pic") or lead.profile_pic_url

                # Clear pending flag
                if lead.context and isinstance(lead.context, dict):
                    lead.context.pop("profile_pending", None)

                session.commit()
                result["enriched"] += 1
                logger.info(f"[Reconciliation] Enriched lead {user_id} -> @{profile['username']}")
            else:
                # Queue for retry
                await _queue_profile_enrichment(creator_id, user_id)
                result["queued"] += 1
                result["failed"] += 1

    except Exception as e:
        logger.error(f"[Reconciliation] Error enriching leads: {e}")

    finally:
        session.close()

    return result


async def get_instagram_conversations(
    access_token: str,
    ig_user_id: str,
    since: Optional[datetime] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Fetch conversations from Instagram API with messages.

    Args:
        access_token: Instagram access token
        ig_user_id: Instagram user ID (page_id for creator)
        since: Only fetch messages since this time
        limit: Max conversations to fetch (default 20 to avoid API limits)

    Returns:
        List of conversations with messages
    """
    conversations = []

    # Determine API base
    api_base = "https://graph.instagram.com/v21.0"
    if access_token.startswith("EAA"):
        api_base = "https://graph.facebook.com/v21.0"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # First, fetch conversation IDs only (smaller request)
            url = f"{api_base}/{ig_user_id}/conversations"
            params = {
                "fields": "id,participants",
                "access_token": access_token,
                "limit": limit,
            }

            resp = await client.get(url, params=params)

            if resp.status_code != 200:
                logger.error(f"[Reconciliation] API error: {resp.status_code} - {resp.text[:200]}")
                return []

            data = resp.json()
            conv_list = data.get("data", [])

            logger.debug(f"[Reconciliation] Fetched {len(conv_list)} conversation IDs")

            # Then fetch messages for each conversation separately
            for conv in conv_list:
                conv_id = conv.get("id")
                if not conv_id:
                    continue

                try:
                    # Fetch messages for this conversation using /messages endpoint
                    # This format returns more attachment data (story, share, etc.)
                    msg_url = f"{api_base}/{conv_id}/messages"
                    msg_params = {
                        "fields": "id,message,from,to,created_time,attachments,story,share,shares,sticker",
                        "access_token": access_token,
                        "limit": 25,
                    }

                    msg_resp = await client.get(msg_url, params=msg_params)

                    if msg_resp.status_code == 200:
                        msg_data = msg_resp.json()
                        # Format response to match expected structure
                        conv["messages"] = {"data": msg_data.get("data", [])}
                        conversations.append(conv)
                    else:
                        logger.debug(f"[Reconciliation] Could not fetch messages for {conv_id}")
                        # Still add conversation without messages
                        conversations.append(conv)

                    # Small delay to avoid rate limits
                    await asyncio.sleep(0.1)

                except Exception as e:
                    logger.debug(f"[Reconciliation] Error fetching messages for {conv_id}: {e}")
                    conversations.append(conv)

            logger.debug(
                f"[Reconciliation] Fetched {len(conversations)} conversations with messages"
            )

        except Exception as e:
            logger.error(f"[Reconciliation] Error fetching conversations: {e}")

    return conversations


async def get_db_message_ids(
    creator_id: str,
    since: Optional[datetime] = None,
) -> set:
    """
    Get all platform_message_ids from database for a creator.

    Args:
        creator_id: Creator name/ID
        since: Only get messages since this time

    Returns:
        Set of platform_message_ids
    """
    def _query_message_ids():
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message

        message_ids = set()
        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                logger.warning(f"[Reconciliation] Creator {creator_id} not found")
                return message_ids

            leads = session.query(Lead).filter_by(creator_id=creator.id).all()
            lead_ids = [lead.id for lead in leads]
            if not lead_ids:
                return message_ids

            query = session.query(Message.platform_message_id).filter(
                Message.lead_id.in_(lead_ids),
                Message.platform_message_id.isnot(None),
            )
            if since:
                query = query.filter(Message.created_at >= since)

            results = query.all()
            message_ids = {r[0] for r in results if r[0]}
            logger.debug(f"[Reconciliation] Found {len(message_ids)} existing messages in DB")
            return message_ids
        finally:
            session.close()

    return await asyncio.to_thread(_query_message_ids)


async def reconcile_messages_for_creator(
    creator_id: str,
    access_token: str,
    ig_user_id: str,
    lookback_hours: int = 24,
) -> Dict[str, Any]:
    """
    Reconcile messages for a single creator.

    Fetches conversations from Instagram API, compares with DB,
    and inserts missing messages.

    Args:
        creator_id: Creator name/ID
        access_token: Instagram access token
        ig_user_id: Instagram user ID
        lookback_hours: How many hours to look back

    Returns:
        Dict with reconciliation results
    """
    from api.database import SessionLocal
    from api.models import Creator, Lead, Message

    result = {
        "creator_id": creator_id,
        "conversations_checked": 0,
        "messages_found": 0,
        "messages_missing": 0,
        "messages_inserted": 0,
        "errors": [],
    }

    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    # Get existing message IDs from DB
    existing_ids = await get_db_message_ids(creator_id, since)

    # Fetch conversations from Instagram
    conversations = await get_instagram_conversations(
        access_token=access_token,
        ig_user_id=ig_user_id,
        since=since,
        limit=MAX_CONVERSATIONS_PER_CYCLE,
    )

    result["conversations_checked"] = len(conversations)

    if not conversations:
        return result

    def _get_creator_with_ids():
        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return None
            return {
                "id": creator.id,
                "instagram_user_id": creator.instagram_user_id,
                "instagram_page_id": creator.instagram_page_id,
            }
        finally:
            session.close()

    creator_data = await asyncio.to_thread(_get_creator_with_ids)
    if not creator_data:
        result["errors"].append(f"Creator {creator_id} not found")
        return result

    session = SessionLocal()
    try:
        # Load creator ORM object for FK references
        creator = session.query(Creator).get(creator_data["id"])

        for conv in conversations:
            conv_id = conv.get("id", "")
            messages_data = conv.get("messages", {}).get("data", [])
            participants = conv.get("participants", {}).get("data", [])

            # Find the follower (non-creator participant)
            # Exclude both ig_user_id AND instagram_page_id to avoid creating leads
            # for the creator's own account (which can have multiple IDs)
            creator_ids = {ig_user_id}
            if creator.instagram_user_id:
                creator_ids.add(creator.instagram_user_id)
            if creator.instagram_page_id:
                creator_ids.add(creator.instagram_page_id)
            # Add legacy creator ID that was previously used (prevents ghost leads)
            creator_ids.add("17841400506734756")

            follower_id = None
            for p in participants:
                p_id = p.get("id", "")
                if p_id and p_id not in creator_ids:
                    follower_id = p_id
                    break

            if not follower_id:
                continue

            # Find or create lead
            # Check for both ig_prefixed and non-prefixed variants to avoid duplicates
            lead = (
                session.query(Lead)
                .filter(
                    Lead.creator_id == creator.id,
                    Lead.platform_user_id.in_([f"ig_{follower_id}", follower_id]),
                )
                .first()
            )

            if not lead:
                # FIX: Don't create lead if there are no new USER messages to insert
                # This prevents "ghost leads" when creator sends messages to someone who never wrote
                # IMPORTANT: Only count messages FROM the follower, not creator echo messages
                has_new_user_messages = False
                for msg in messages_data:
                    msg_id = msg.get("id", "")
                    msg_from_id = msg.get("from", {}).get("id", "")
                    # Only count messages FROM the follower (user), not from creator (echo)
                    if msg_id and msg_id not in existing_ids and msg_from_id == follower_id:
                        # Check DB directly
                        existing = (
                            session.query(Message).filter_by(platform_message_id=msg_id).first()
                        )
                        if not existing:
                            has_new_user_messages = True
                            break

                if not has_new_user_messages:
                    logger.debug(
                        f"[Reconciliation] Skipping lead creation for {follower_id} - no new USER messages (only echo)"
                    )
                    continue

                # Check if this lead is in the dismissed blocklist
                # If so, skip - creator previously deleted this conversation
                from api.models import DismissedLead

                is_dismissed = (
                    session.query(DismissedLead)
                    .filter_by(creator_id=creator.id, platform_user_id=follower_id)
                    .first()
                )
                if is_dismissed:
                    logger.debug(
                        f"[Reconciliation] Skipping {follower_id}: in dismissed_leads blocklist"
                    )
                    continue

                # Create new lead and try to enrich with profile
                # Use raw follower_id (no ig_ prefix) for consistency with other services
                profile_data = await _fetch_profile_for_lead(follower_id, access_token)

                lead = Lead(
                    creator_id=creator.id,
                    platform="instagram",
                    platform_user_id=follower_id,  # No prefix - consistent with webhook handler
                    username=profile_data.get("username") or None,
                    full_name=profile_data.get("name") or None,
                    profile_pic_url=profile_data.get("profile_pic") or None,
                    status="nuevo",
                    context={
                        "source": "reconciliation",
                        "profile_pending": not profile_data.get("username"),
                    },
                )
                session.add(lead)
                session.commit()

                # Queue profile retry if fetch failed
                if not profile_data.get("username"):
                    await _queue_profile_enrichment(creator_id, follower_id)

                logger.info(
                    f"[Reconciliation] Created lead for {follower_id} "
                    f"(username={profile_data.get('username', 'pending')})"
                )

            # Process messages
            for msg in messages_data:
                msg_id = msg.get("id", "")
                result["messages_found"] += 1

                if not msg_id:
                    continue

                # Check if already exists
                if msg_id in existing_ids:
                    continue

                # Check DB directly (in case it was added after our initial query)
                existing = session.query(Message).filter_by(platform_message_id=msg_id).first()
                if existing:
                    existing_ids.add(msg_id)
                    continue

                result["messages_missing"] += 1

                # Parse message data
                msg_text = msg.get("message", "")
                msg_from = msg.get("from", {})
                msg_from_id = msg_from.get("id", "")
                created_time_str = msg.get("created_time", "")
                attachments = msg.get("attachments", {}).get("data", [])
                story_data = msg.get("story")
                share_data = msg.get("share")
                shares_data = msg.get("shares", {}).get("data", [])
                sticker_data = msg.get("sticker")

                # Determine role
                role = "user" if msg_from_id == follower_id else "assistant"

                # Parse timestamp
                created_at = None
                if created_time_str:
                    try:
                        created_at = datetime.fromisoformat(created_time_str.replace("Z", "+00:00"))
                    except Exception:
                        created_at = datetime.now(timezone.utc)

                # Parse media - check attachments, story, share, sticker
                media_info = {}
                content = msg_text

                # Check story data first (story mentions/replies)
                if story_data:
                    story_link = story_data.get("link") or story_data.get("url")
                    mention_link = story_data.get("mention", {}).get("link")
                    reply_link = story_data.get("reply_to", {}).get("link")
                    media_url = story_link or mention_link or reply_link
                    media_info = {
                        "type": "story_mention",
                        "content_text": "Mentioned you in their story",
                    }
                    if media_url:
                        media_info["url"] = media_url
                    logger.info(
                        f"[Reconciliation] Story data for msg {msg_id[:20]}: url={bool(media_url)}"
                    )

                # Check share data
                elif share_data:
                    share_link = share_data.get("link") or share_data.get("url")
                    media_info = {
                        "type": "share",
                        "content_text": "Shared a post",
                    }
                    if share_link:
                        media_info["url"] = share_link
                        if "reel" in share_link.lower():
                            media_info["type"] = "shared_reel"
                            media_info["content_text"] = "Shared a reel"

                # Check shares array
                elif shares_data:
                    share = shares_data[0]
                    share_link = share.get("link") or share.get("url")
                    media_info = {
                        "type": "share",
                        "content_text": "Shared content",
                    }
                    if share_link:
                        media_info["url"] = share_link

                # Check sticker
                elif sticker_data:
                    media_info = {
                        "type": "sticker",
                        "content_text": "Sent a sticker",
                    }
                    if isinstance(sticker_data, str):
                        media_info["url"] = sticker_data

                # Check attachments
                elif attachments:
                    media_info = _extract_media_from_attachments(attachments)
                    logger.info(
                        f"[Reconciliation] Attachments for msg {msg_id[:20]}...: "
                        f"count={len(attachments)}, media_info={media_info}"
                    )

                # Set content text
                if not content and media_info:
                    content = media_info.get("content_text", "Sent an attachment")
                elif not content:
                    content = "[Media/Attachment]"

                # Build metadata
                metadata = {
                    "source": "reconciliation",
                    "conversation_id": conv_id,
                    "original_from_id": msg_from_id,
                }
                if media_info:
                    if media_info.get("type"):
                        metadata["type"] = media_info["type"]
                    if media_info.get("url"):
                        metadata["url"] = media_info["url"]
                        # Capture media from CDN URL before it expires
                        try:
                            from services.media_capture_service import (
                                capture_media_from_url,
                                is_cdn_url,
                            )

                            media_url = media_info["url"]
                            if is_cdn_url(media_url):
                                media_type_for_capture = (
                                    "video"
                                    if media_info.get("type")
                                    in ["video", "story_mention", "shared_reel"]
                                    else "image"
                                )
                                captured = await capture_media_from_url(
                                    media_url,
                                    media_type=media_type_for_capture,
                                    creator_id=creator_id,
                                )
                                if captured:
                                    if captured.startswith("data:"):
                                        metadata["thumbnail_base64"] = captured
                                        logger.info(
                                            f"[Reconciliation] Captured media as base64 for msg {msg_id[:20]}"
                                        )
                                    else:
                                        metadata["permanent_url"] = captured
                                        logger.info(
                                            f"[Reconciliation] Captured media to Cloudinary for msg {msg_id[:20]}"
                                        )
                        except Exception as e:
                            logger.warning(f"[Reconciliation] Media capture failed: {e}")

                # Insert message
                try:
                    new_msg = Message(
                        lead_id=lead.id,
                        role=role,
                        content=content,
                        platform_message_id=msg_id,
                        status="sent",
                        msg_metadata=metadata,
                        created_at=created_at,
                    )
                    session.add(new_msg)

                    # Update lead's last_contact_at so conversation rises to top
                    if role == "user":
                        lead.last_contact_at = datetime.now(timezone.utc)
                        session.add(lead)

                    session.commit()

                    existing_ids.add(msg_id)
                    result["messages_inserted"] += 1

                    logger.debug(f"[Reconciliation] Inserted message {msg_id}")

                except Exception as e:
                    session.rollback()
                    result["errors"].append(f"Failed to insert {msg_id}: {str(e)}")
                    logger.error(f"[Reconciliation] Failed to insert message: {e}")

            # Yield to event loop between conversations
            await asyncio.sleep(0)

    except Exception as e:
        result["errors"].append(str(e))
        logger.error(f"[Reconciliation] Error: {e}")

    finally:
        session.close()

    if result["messages_inserted"] > 0:
        logger.info(
            f"[Reconciliation] {creator_id}: inserted {result['messages_inserted']} "
            f"missing messages out of {result['messages_found']} found"
        )

    return result


async def run_reconciliation_cycle(lookback_hours: int = 1) -> Dict[str, Any]:
    """
    Run reconciliation for all creators with Instagram connections.

    Args:
        lookback_hours: How many hours to look back

    Returns:
        Dict with overall results
    """
    from api.database import SessionLocal
    from api.models import Creator

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "lookback_hours": lookback_hours,
        "creators_processed": 0,
        "total_missing": 0,
        "total_inserted": 0,
        "by_creator": [],
    }

    def _get_active_ig_creators():
        session = SessionLocal()
        try:
            creators = (
                session.query(Creator)
                .filter(
                    Creator.instagram_token.isnot(None),
                    Creator.instagram_token != "",
                    Creator.bot_active.is_(True),
                )
                .all()
            )
            return [
                {
                    "name": c.name,
                    "token": c.instagram_token,
                    "ig_user_id": c.instagram_user_id or c.instagram_page_id,
                }
                for c in creators
                if c.instagram_user_id or c.instagram_page_id
            ]
        finally:
            session.close()

    creator_infos = await asyncio.to_thread(_get_active_ig_creators)

    if not creator_infos:
        logger.debug("[Reconciliation] No active creators with Instagram found")
        return results

    for creator_info in creator_infos:
        try:
            result = await reconcile_messages_for_creator(
                creator_id=creator_info["name"],
                access_token=creator_info["token"],
                ig_user_id=creator_info["ig_user_id"],
                lookback_hours=lookback_hours,
            )

            results["creators_processed"] += 1
            results["total_missing"] += result["messages_missing"]
            results["total_inserted"] += result["messages_inserted"]
            results["by_creator"].append(result)

        except Exception as e:
            logger.error(f"[Reconciliation] Error for {creator_info['name']}: {e}")
            results["by_creator"].append(
                {
                    "creator_id": creator_info["name"],
                    "error": str(e),
                }
            )

    if results["total_inserted"] > 0:
        logger.info(
            f"[Reconciliation] Cycle complete: {results['total_inserted']} messages "
            f"inserted for {results['creators_processed']} creators"
        )

    return results


async def check_message_gaps() -> Dict[str, Any]:
    """
    Health check to detect gaps between Instagram and DB.

    Compares latest message timestamp in Instagram vs DB for each creator.

    Returns:
        Dict with gap detection results
    """
    from api.database import SessionLocal
    from api.models import Creator, Lead, Message

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "creators_checked": 0,
        "gaps_detected": 0,
        "creators_with_gaps": [],
    }

    session = SessionLocal()
    try:
        # Get all creators with Instagram connections
        creators = (
            session.query(Creator)
            .filter(
                Creator.instagram_token.isnot(None),
                Creator.instagram_token != "",
            )
            .all()
        )

        for creator in creators:
            ig_user_id = creator.instagram_user_id or creator.instagram_page_id
            if not ig_user_id:
                continue

            results["creators_checked"] += 1

            # Get latest message time from DB
            leads = session.query(Lead).filter_by(creator_id=creator.id).all()
            lead_ids = [lead.id for lead in leads]

            db_latest = None
            if lead_ids:
                latest_msg = (
                    session.query(Message)
                    .filter(Message.lead_id.in_(lead_ids))
                    .order_by(Message.created_at.desc())
                    .first()
                )
                if latest_msg:
                    db_latest = latest_msg.created_at

            # Get latest message time from Instagram (quick check)
            conversations = await get_instagram_conversations(
                access_token=creator.instagram_token,
                ig_user_id=ig_user_id,
                limit=1,
            )

            ig_latest = None
            if conversations:
                messages = conversations[0].get("messages", {}).get("data", [])
                if messages:
                    created_time = messages[0].get("created_time", "")
                    if created_time:
                        try:
                            ig_latest = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
                        except Exception:
                            pass

            # Detect gap
            if ig_latest and db_latest:
                gap_minutes = (ig_latest - db_latest).total_seconds() / 60
                if gap_minutes > 5:  # More than 5 minutes gap
                    results["gaps_detected"] += 1
                    results["creators_with_gaps"].append(
                        {
                            "creator_id": creator.name,
                            "db_latest": db_latest.isoformat() if db_latest else None,
                            "ig_latest": ig_latest.isoformat() if ig_latest else None,
                            "gap_minutes": round(gap_minutes, 1),
                        }
                    )
            elif ig_latest and not db_latest:
                # Instagram has messages but DB is empty
                results["gaps_detected"] += 1
                results["creators_with_gaps"].append(
                    {
                        "creator_id": creator.name,
                        "db_latest": None,
                        "ig_latest": ig_latest.isoformat(),
                        "gap_minutes": None,
                        "note": "DB empty, Instagram has messages",
                    }
                )

    finally:
        session.close()

    return results


# State for tracking last reconciliation
_last_reconciliation: Optional[str] = None
_reconciliation_count: int = 0


async def run_startup_reconciliation():
    """
    Run reconciliation on server startup.
    Recovers messages from the last 24 hours.
    """
    global _last_reconciliation, _reconciliation_count

    logger.info(
        f"[Reconciliation] Starting startup reconciliation (last {RECONCILIATION_LOOKBACK_HOURS}h)"
    )

    try:
        result = await run_reconciliation_cycle(lookback_hours=RECONCILIATION_LOOKBACK_HOURS)

        _last_reconciliation = datetime.now(timezone.utc).isoformat()
        _reconciliation_count += 1

        if result["total_inserted"] > 0:
            logger.info(
                f"[Reconciliation] Startup complete: recovered {result['total_inserted']} messages"
            )
        else:
            logger.info("[Reconciliation] Startup complete: no missing messages found")

        return result

    except Exception as e:
        logger.error(f"[Reconciliation] Startup reconciliation failed: {e}")
        return {"error": str(e)}


async def run_periodic_reconciliation():
    """
    Run periodic reconciliation (called by scheduler).
    Checks for messages from the last hour.
    """
    global _last_reconciliation, _reconciliation_count

    try:
        result = await run_reconciliation_cycle(lookback_hours=1)

        _last_reconciliation = datetime.now(timezone.utc).isoformat()
        _reconciliation_count += 1

        return result

    except Exception as e:
        logger.error(f"[Reconciliation] Periodic reconciliation failed: {e}")
        return {"error": str(e)}


def get_reconciliation_status() -> Dict[str, Any]:
    """Get current reconciliation status."""
    return {
        "last_run": _last_reconciliation,
        "total_runs": _reconciliation_count,
        "lookback_hours_startup": RECONCILIATION_LOOKBACK_HOURS,
        "interval_minutes": RECONCILIATION_INTERVAL_MINUTES,
    }
