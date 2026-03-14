"""
DM Conversations - Conversation management endpoints
(get_conversations, mark_conversation_read, archive, spam, reset, delete, sync, etc.)
"""

import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

# Database availability check
try:
    pass

    USE_DB = True
except Exception:
    USE_DB = False
    logger.warning("Database service not available in dm conversations router")

router = APIRouter()


def _media_description(metadata: dict | None) -> str:
    """Generate descriptive text for media messages with no text content."""
    if not metadata:
        return ""
    meta_type = metadata.get("type", "")
    return {
        "image": "Sent a photo",
        "video": "Sent a video",
        "audio": "Sent a voice message",
        "gif": "Sent a GIF",
        "sticker": "Sent a sticker",
        "story_mention": "Mentioned you in their story",
        "story_reply": "Replied to your story",
        "story_reaction": f"Reacted {metadata.get('emoji', '❤️')} to your story",
        "share": "Shared a post",
        "shared_post": "Shared a post",
        "shared_reel": "Shared a reel",
        "shared_video": "Shared a video",
        "reel": "Shared a reel",
        "reaction": metadata.get("emoji", "❤️"),
        "link_preview": "Sent a link",
    }.get(meta_type, "Sent an attachment" if meta_type else "")


@router.get("/conversations/{creator_id}")
async def get_conversations(creator_id: str, limit: int = 500, offset: int = 0, platform: str = None):
    """Listar conversaciones del creador - OPTIMIZED with caching"""
    import time as _time

    from api.cache import api_cache

    # Check cache first (60s TTL - matches startup.py cache refresh)
    cache_key = f"conversations:{creator_id}:{limit}:{offset}:{platform or 'all'}"
    cached = api_cache.get(cache_key)
    if cached:
        logger.info(f"[CONV] {creator_id}: cache HIT (key={cache_key})")
        return cached
    logger.info(f"[CONV] {creator_id}: cache MISS (key={cache_key})")

    start_time = _time.time()

    try:
        if USE_DB:
            from api.models import Creator, Lead, Message
            from api.services.db_service import get_session
            from sqlalchemy import func, not_

            session = get_session()
            if session:
                try:
                    creator = session.query(Creator).filter_by(name=creator_id).first()
                    if not creator:
                        return {"status": "ok", "conversations": [], "count": 0}

                    # OPTIMIZED: Single query for leads with message counts
                    # FIX: Only count sent/edited messages (consistent with last_msg query)
                    msg_count_subq = (
                        session.query(Message.lead_id, func.count(Message.id).label("msg_count"))
                        .filter(Message.role == "user", Message.status.in_(["sent", "edited"]))
                        .group_by(Message.lead_id)
                        .subquery()
                    )

                    # Pending copilot suggestions per lead
                    pending_copilot_subq = (
                        session.query(Message.lead_id, func.count(Message.id).label("pending_count"))
                        .filter(
                            Message.role == "assistant",
                            Message.status == "pending_approval",
                        )
                        .group_by(Message.lead_id)
                        .subquery()
                    )

                    # Base filters (platform-aware)
                    base_filters = [
                        Lead.creator_id == creator.id,
                        not_(Lead.status.in_(["archived", "spam"])),
                    ]
                    if platform:
                        base_filters.append(Lead.platform == platform)

                    # Count total for pagination
                    total_count = (
                        session.query(func.count(Lead.id))
                        .filter(*base_filters)
                        .scalar()
                    )

                    # When limit >= 500, return ALL active leads so mixed-platform
                    # dashboards (IG + WA) show every conversation regardless of
                    # last_contact_at ordering (WA leads would otherwise bury IG).
                    effective_limit = total_count if limit >= 500 else limit
                    results = (
                        session.query(
                            Lead,
                            func.coalesce(msg_count_subq.c.msg_count, 0).label("total_messages"),
                            func.coalesce(pending_copilot_subq.c.pending_count, 0).label("pending_copilot"),
                        )
                        .outerjoin(msg_count_subq, Lead.id == msg_count_subq.c.lead_id)
                        .outerjoin(pending_copilot_subq, Lead.id == pending_copilot_subq.c.lead_id)
                        .filter(*base_filters)
                        .order_by(Lead.last_contact_at.desc())
                        .offset(offset)
                        .limit(effective_limit)
                        .all()
                    )

                    # OPTIMIZED: Get last message for each lead in ONE query
                    lead_ids = [lead.id for lead, _, _ in results]

                    # Subquery to get the latest SENT message per lead
                    last_msg_subq = (
                        session.query(
                            Message.lead_id, func.max(Message.created_at).label("max_date")
                        )
                        .filter(
                            Message.lead_id.in_(lead_ids),
                            Message.status.in_(["sent", "edited"]),
                            Message.deleted_at.is_(None),
                        )
                        .group_by(Message.lead_id)
                        .subquery()
                    )

                    last_messages_query = (
                        session.query(Message)
                        .join(
                            last_msg_subq,
                            (Message.lead_id == last_msg_subq.c.lead_id)
                            & (Message.created_at == last_msg_subq.c.max_date),
                        )
                        .filter(
                            Message.status.in_(["sent", "edited"]),
                            Message.deleted_at.is_(None),
                        )
                        .all()
                    )

                    # Build lookup dict for last messages
                    last_msg_by_lead = {msg.lead_id: msg for msg in last_messages_query}

                    conversations = []
                    for lead, msg_count, pending_copilot in results:
                        ctx = lead.context or {}

                        # Get last message from pre-fetched data
                        last_msg = last_msg_by_lead.get(lead.id)
                        last_messages = []
                        last_message_preview = None
                        last_message_role = None

                        if last_msg:
                            # Reactions: show descriptive text instead of raw emoji
                            meta = last_msg.msg_metadata or {}
                            if meta.get("type") == "reaction":
                                emoji = meta.get("emoji", "❤️")
                                display_content = f"Reaccionó {emoji} a tu mensaje"
                            else:
                                # Fallback chain: text → media description → generic attachment label
                                display_content = (
                                    last_msg.content
                                    or _media_description(last_msg.msg_metadata)
                                    or "Sent an attachment"
                                )

                            last_messages = [
                                {
                                    "role": last_msg.role,
                                    "content": display_content[:200],
                                    "timestamp": (
                                        last_msg.created_at.isoformat()
                                        if last_msg.created_at
                                        else None
                                    ),
                                }
                            ]
                            # Instagram-like UX fields
                            last_message_preview = (
                                display_content[:50] + "..."
                                if len(display_content) > 50
                                else display_content
                            )
                            last_message_role = last_msg.role

                        # is_unread: Check if last user message is after last_read_at
                        last_read_at = ctx.get("last_read_at")
                        last_user_msg_time = (
                            last_msg.created_at.isoformat()
                            if last_msg and last_msg.role == "user" and last_msg.created_at
                            else None
                        )
                        if last_read_at and last_user_msg_time:
                            # Compare timestamps - unread if user message is after read time
                            is_unread = last_user_msg_time > last_read_at
                        else:
                            # Fallback: unread if last message is from user
                            is_unread = last_message_role == "user"
                        # is_verified: from context JSON (populated by Instagram API)
                        is_verified = ctx.get("is_verified", False)

                        conversations.append(
                            {
                                "follower_id": lead.platform_user_id,
                                "id": str(lead.id),
                                "username": lead.username or lead.platform_user_id,
                                "name": lead.full_name or lead.username or "",
                                "platform": lead.platform or "instagram",
                                "profile_pic_url": lead.profile_pic_url,
                                "total_messages": msg_count,
                                "purchase_intent": lead.purchase_intent or 0.0,
                                "purchase_intent_score": lead.purchase_intent or 0.0,
                                "score": lead.score or 0,
                                "status": lead.status or "nuevo",
                                "relationship_type": lead.relationship_type or "nuevo",
                                "is_lead": True,
                                "last_contact": (
                                    lead.last_contact_at.isoformat()
                                    if lead.last_contact_at
                                    else None
                                ),
                                "last_messages": last_messages,
                                # Instagram-like UX fields (FIX 2026-02-02)
                                "last_message_preview": last_message_preview,
                                "last_message_role": last_message_role,
                                "is_unread": is_unread,
                                "is_verified": is_verified,
                                # Copilot pending
                                "has_pending_copilot": pending_copilot > 0,
                                # CRM fields
                                "email": ctx.get("email") or lead.email or "",
                                "phone": ctx.get("phone") or lead.phone or "",
                                "notes": ctx.get("notes") or lead.notes or "",
                            }
                        )

                    elapsed = _time.time() - start_time
                    logger.info(
                        f"[CONV] {creator_id}: {len(conversations)} conversations in {elapsed:.2f}s (DB query)"
                    )
                    has_more = (offset + limit) < total_count

                    # Counts by status for summary cards (single GROUP BY)
                    counts_rows = (
                        session.query(Lead.status, func.count(Lead.id))
                        .filter(*base_filters)
                        .group_by(Lead.status)
                        .all()
                    )
                    counts_by_status = {s: c for s, c in counts_rows}

                    result = {
                        "status": "ok",
                        "conversations": conversations,
                        "count": len(conversations),
                        "total": total_count,
                        "has_more": has_more,
                        "offset": offset,
                        "limit": limit,
                        "counts_by_status": counts_by_status,
                    }
                    # Cache for 30s — SSE invalidates on new messages, so long TTL is safe
                    api_cache.set(cache_key, result, ttl_seconds=30)
                    return result
                finally:
                    session.close()

        # Fallback to JSON if PostgreSQL not available
        from .processing import get_dm_agent

        agent = get_dm_agent(creator_id)
        conversations = await agent.get_all_conversations(limit)
        filtered = [c for c in conversations if not c.get("archived") and not c.get("spam")]
        return {"status": "ok", "conversations": filtered, "count": len(filtered)}

    except Exception as e:
        logger.error(f"get_conversations error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/conversations/{creator_id}/{follower_id}/mark-read")
async def mark_conversation_read(creator_id: str, follower_id: str):
    """Mark a conversation as read by updating last_read_at in lead context"""
    if not USE_DB:
        return {"status": "ok", "message": "No database - skipped"}

    try:
        from api.models import Creator, Lead
        from api.services.db_service import get_session

        session = get_session()
        if not session:
            return {"status": "error", "message": "No database session"}

        try:
            # Find creator
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"status": "error", "message": "Creator not found"}

            # Find lead by platform_user_id
            lead = (
                session.query(Lead)
                .filter(
                    Lead.creator_id == creator.id,
                    Lead.platform_user_id == follower_id,
                )
                .first()
            )

            if lead:
                # Update context with last_read_at timestamp
                context = lead.context or {}
                context["last_read_at"] = datetime.now(timezone.utc).isoformat()
                lead.context = context
                session.commit()
                logger.info(f"[MarkRead] {creator_id}/{follower_id} marked as read")
                return {"status": "ok", "message": "Conversation marked as read"}
            else:
                return {"status": "error", "message": "Lead not found"}

        finally:
            session.close()

    except Exception as e:
        logger.error(f"mark_conversation_read error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ============ CONVERSATION ACTIONS ============


@router.post("/conversations/{creator_id}/{conversation_id}/archive")
async def archive_conversation_endpoint(creator_id: str, conversation_id: str):
    from api.cache import api_cache

    # Try PostgreSQL first
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services import db_service

            success = db_service.archive_conversation(creator_id, conversation_id)
            if success:
                api_cache.invalidate(f"conversations:{creator_id}")
                return {"status": "ok", "archived": True}
        except Exception as e:
            logger.warning(f"PostgreSQL archive failed: {e}")
    # Fallback to JSON files
    try:
        file_path = f"data/followers/{creator_id}/{conversation_id}.json"
        if not os.path.exists(file_path):
            return {"status": "error", "message": "Conversation not found"}
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["archived"] = True
        data["is_lead"] = False
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return {"status": "ok", "archived": True}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/conversations/{creator_id}/{conversation_id}/spam")
async def mark_conversation_spam_endpoint(creator_id: str, conversation_id: str):
    from api.cache import api_cache

    # Try PostgreSQL first
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services import db_service

            success = db_service.mark_conversation_spam(creator_id, conversation_id)
            if success:
                api_cache.invalidate(f"conversations:{creator_id}")
                return {"status": "ok", "spam": True}
        except Exception as e:
            logger.warning(f"PostgreSQL spam failed: {e}")
    # Fallback to JSON files
    try:
        from .processing import get_dm_agent

        file_path = f"data/followers/{creator_id}/{conversation_id}.json"
        if not os.path.exists(file_path):
            return {"status": "error", "message": "Conversation not found"}
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["spam"] = True
        data["is_lead"] = False
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # Invalidate cache
        agent = get_dm_agent(creator_id)
        cache_key = f"{creator_id}:{conversation_id}"
        if cache_key in agent.memory_store._cache:
            del agent.memory_store._cache[cache_key]
        return {"status": "ok", "spam": True}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.delete("/conversations/{creator_id}/{conversation_id}")
async def delete_conversation_endpoint(creator_id: str, conversation_id: str):
    from api.cache import api_cache

    # Try PostgreSQL first
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services import db_service

            success = db_service.delete_conversation(creator_id, conversation_id)
            if success:
                api_cache.invalidate(f"conversations:{creator_id}")
                return {"status": "ok", "deleted": conversation_id}

            # Lead not found -- check if already deleted (dismissed)
            from api.database import SessionLocal
            from api.models import Creator, DismissedLead

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if creator:
                    dismissed = (
                        session.query(DismissedLead)
                        .filter_by(creator_id=creator.id, platform_user_id=conversation_id)
                        .first()
                    )
                    if dismissed:
                        api_cache.invalidate(f"conversations:{creator_id}")
                        return {"status": "ok", "deleted": conversation_id, "already_deleted": True}
            finally:
                session.close()

            raise HTTPException(status_code=404, detail="Conversation not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"PostgreSQL delete failed for {conversation_id}: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")
    # Fallback to JSON files (non-DB setups only)
    try:
        file_path = f"data/followers/{creator_id}/{conversation_id}.json"
        if not os.path.exists(file_path):
            raise HTTPException(
                status_code=404, detail="Conversation not found"
            )
        os.remove(file_path)
        return {"status": "ok", "deleted": conversation_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


# ============ ARCHIVED/SPAM MANAGEMENT ============


@router.get("/conversations/{creator_id}/archived")
async def get_archived_conversations(creator_id: str):
    """Get all archived and spam conversations"""
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.models import Creator, Lead, Message
            from api.services.db_service import get_session

            session = get_session()
            if not session:
                return {"status": "error", "conversations": []}

            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    return {"status": "ok", "conversations": []}

                leads = (
                    session.query(Lead)
                    .filter_by(creator_id=creator.id)
                    .filter(Lead.status.in_(["archived", "spam"]))
                    .order_by(Lead.last_contact_at.desc())
                    .all()
                )

                conversations = []
                for lead in leads:
                    # Only count user messages, not bot responses
                    msg_count = (
                        session.query(Message).filter_by(lead_id=lead.id, role="user").count()
                    )
                    conversations.append(
                        {
                            "id": str(lead.id),
                            "follower_id": lead.platform_user_id or str(lead.id),
                            "username": lead.username,
                            "name": lead.full_name,
                            "platform": lead.platform or "instagram",
                            "status": lead.status,
                            "score": lead.score or 0,
                            "relationship_type": lead.relationship_type or "nuevo",
                            "total_messages": msg_count,
                            "purchase_intent": lead.purchase_intent or 0.0,
                            "last_contact": (
                                lead.last_contact_at.isoformat() if lead.last_contact_at else None
                            ),
                        }
                    )

                return {"status": "ok", "conversations": conversations}
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Get archived failed: {e}")
            return {"status": "error", "message": str(e), "conversations": []}
    return {"status": "ok", "conversations": []}


@router.post("/conversations/{creator_id}/{conversation_id}/restore")
async def restore_conversation(creator_id: str, conversation_id: str):
    """Restore an archived/spam conversation back to 'new' status"""
    from api.cache import api_cache

    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services import db_service

            count = db_service.reset_conversation_status(creator_id, conversation_id)
            if count > 0:
                api_cache.invalidate(f"conversations:{creator_id}")
                return {"status": "ok", "restored": True}
            return {"status": "error", "message": "Conversation not found or not archived/spam"}
        except Exception as e:
            logger.warning(f"Restore failed: {e}")
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "Database not configured"}


@router.post("/conversations/{creator_id}/reset")
async def reset_conversations(creator_id: str):
    """Reset all archived/spam conversations back to 'new' status"""
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services import db_service

            count = db_service.reset_conversation_status(creator_id)
            return {"status": "ok", "reset_count": count}
        except Exception as e:
            logger.warning(f"Reset failed: {e}")
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "Database not configured"}


@router.post("/conversations/{creator_id}/sync-messages")
async def sync_messages_from_json_endpoint(creator_id: str):
    """Sync all messages from JSON files to PostgreSQL (one-time migration)"""
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services.data_sync import sync_messages_from_json

            stats = sync_messages_from_json(creator_id)
            return {"status": "ok", **stats}
        except Exception as e:
            logger.warning(f"Message sync failed: {e}")
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "Database not configured"}


@router.post("/conversations/{creator_id}/sync-timestamps")
async def sync_last_contact_timestamps(creator_id: str):
    """Sync last_contact_at for all leads based on their actual last message time."""
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if not USE_DB:
        return {"status": "error", "message": "Database not configured"}

    try:
        from api.models import Creator, Lead, Message
        from api.services.db_service import get_session
        from sqlalchemy import func

        session = get_session()
        if not session:
            return {"status": "error", "message": "Could not get database session"}

        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"status": "error", "message": f"Creator {creator_id} not found"}

            # Get all leads with their actual last message time
            leads_with_last_msg = (
                session.query(
                    Lead.id,
                    Lead.username,
                    Lead.last_contact_at,
                    func.max(Message.created_at).label("last_msg_time"),
                )
                .outerjoin(Message, Lead.id == Message.lead_id)
                .filter(Lead.creator_id == creator.id)
                .group_by(Lead.id)
                .all()
            )

            updated = 0
            for lead_id, username, last_contact, last_msg_time in leads_with_last_msg:
                if last_msg_time and (not last_contact or last_msg_time > last_contact):
                    session.query(Lead).filter_by(id=lead_id).update(
                        {"last_contact_at": last_msg_time}
                    )
                    updated += 1
                    logger.info(
                        f"[SyncTimestamps] Updated {username}: {last_contact} -> {last_msg_time}"
                    )

            session.commit()
            return {
                "status": "ok",
                "leads_checked": len(leads_with_last_msg),
                "leads_updated": updated,
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"[SyncTimestamps] Error: {e}")
        return {"status": "error", "message": str(e)}
