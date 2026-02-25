"""
Message operations (save, retrieve, count).
"""

import logging
from datetime import datetime

from api.utils.creator_resolver import resolve_creator_safe
from .session import get_session, USE_POSTGRES

logger = logging.getLogger(__name__)


async def save_message(
    lead_id: str,
    role: str,
    content: str,
    intent: str = None,
    platform_message_id: str = None,
    metadata: dict = None,
) -> dict:
    """Save a message to the database for dm_agent integration.

    FIX: Added duplicate detection to prevent webhook message duplication.
    Checks for existing message with same content+lead within last 5 minutes.

    NOTE: Link preview extraction is done asynchronously via background job,
    not during save_message, to avoid blocking the webhook.

    Args:
        lead_id: UUID of the lead
        role: 'user' or 'assistant'
        content: Message text
        intent: Optional intent classification
        platform_message_id: Optional platform-specific message ID
        metadata: Optional dict with type, url, emoji, link_preview, etc.
    """
    if not USE_POSTGRES:
        return None
    session = get_session()
    if not session:
        return None
    try:
        import uuid as uuid_module
        from datetime import timedelta, timezone

        from api.models import Message

        # Convert lead_id string to UUID
        lead_uuid = uuid_module.UUID(lead_id) if isinstance(lead_id, str) else lead_id

        # DUPLICATE CHECK: Check if same message exists for this lead in last 5 minutes
        # This prevents webhook retries from creating duplicate messages
        five_minutes_ago = datetime.now(timezone.utc) - timedelta(minutes=5)
        existing = (
            session.query(Message)
            .filter(
                Message.lead_id == lead_uuid,
                Message.role == role,
                Message.content == content,
                Message.created_at >= five_minutes_ago,
            )
            .first()
        )

        if existing:
            logger.info(f"Duplicate message detected for lead {lead_id}, skipping (role={role})")
            return {"id": str(existing.id), "status": "duplicate_skipped"}

        # Also check by platform_message_id if provided
        if platform_message_id:
            existing_by_id = (
                session.query(Message)
                .filter(Message.platform_message_id == platform_message_id)
                .first()
            )
            if existing_by_id:
                logger.info(f"Duplicate message by platform_message_id: {platform_message_id}")
                return {"id": str(existing_by_id.id), "status": "duplicate_skipped"}

        # Build metadata (link preview extraction moved to background job)
        msg_metadata = metadata.copy() if metadata else {}

        # Create new message
        message = Message(
            lead_id=lead_uuid,
            role=role,  # 'user' or 'assistant'
            content=content,
            intent=intent,
            platform_message_id=platform_message_id,
            msg_metadata=msg_metadata if msg_metadata else None,
            created_at=datetime.now(timezone.utc),
        )
        session.add(message)
        session.commit()
        message_id = str(message.id)
        logger.info(f"Saved message for lead {lead_id}: role={role}")

        # Schedule background link preview extraction (fire-and-forget)
        if content and "http" in content.lower():
            try:
                from core.link_preview import schedule_link_preview_extraction

                schedule_link_preview_extraction(message_id, content)
            except Exception as e:
                logger.debug(f"Could not schedule link preview: {e}")

        return {"id": message_id, "status": "saved"}
    except Exception as e:
        logger.error(f"save_message error: {e}")
        session.rollback()
        return None
    finally:
        session.close()


async def get_messages(creator_id: str, follower_id: str = None, limit: int = 50) -> list:
    """Get messages for a creator"""
    if not USE_POSTGRES:
        return []
    session = get_session()
    if not session:
        return []
    try:
        from api.models import Creator, Lead, Message

        creator = resolve_creator_safe(session, creator_id)
        if not creator:
            return []
        query = session.query(Message).join(Lead).filter(Lead.creator_id == creator.id)
        if follower_id:
            query = query.filter(Lead.platform_user_id == follower_id)
        messages = query.order_by(Message.created_at.desc()).limit(limit).all()
        return [
            {
                "id": str(m.id),
                "role": m.role,
                "content": m.content,
                "intent": m.intent,
                "created_at": str(m.created_at),
            }
            for m in messages
        ]
    except Exception as e:
        logger.error(f"get_messages error: {e}")
        return []
    finally:
        session.close()


async def get_message_count(creator_id: str) -> int:
    """Get total message count for a creator (only user messages, not bot responses)"""
    if not USE_POSTGRES:
        return 0
    session = get_session()
    if not session:
        return 0
    try:
        from api.models import Creator, Lead, Message

        creator = resolve_creator_safe(session, creator_id)
        if not creator:
            return 0
        count = (
            session.query(Message)
            .join(Lead)
            .filter(Lead.creator_id == creator.id, Message.role == "user")
            .count()
        )
        return count
    except Exception as e:
        logger.error(f"get_message_count error: {e}")
        return 0
    finally:
        session.close()


def get_messages_by_lead_id(lead_id: str, limit: int = 50) -> list:
    """Get messages for a specific lead by UUID (sync version for /dm/conversations)"""
    if not USE_POSTGRES:
        return []
    session = get_session()
    if not session:
        return []
    try:
        import uuid as uuid_module

        from api.models import Message

        lead_uuid = uuid_module.UUID(lead_id) if isinstance(lead_id, str) else lead_id
        messages = (
            session.query(Message)
            .filter(Message.lead_id == lead_uuid)
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {"role": m.role, "content": m.content, "timestamp": str(m.created_at)}
            for m in reversed(messages)  # Return in chronological order
        ]
    except Exception as e:
        logger.error(f"get_messages_by_lead_id error: {e}")
        return []
    finally:
        session.close()


def get_recent_messages(creator_id: str, follower_id: str, limit: int = 4) -> list:
    """Get recent messages for a follower (sync version for thanks detection)"""
    if not USE_POSTGRES:
        return []
    session = get_session()
    if not session:
        return []
    try:
        from api.models import Creator, Lead, Message

        creator = resolve_creator_safe(session, creator_id)
        if not creator:
            return []

        lead = (
            session.query(Lead)
            .filter(Lead.creator_id == creator.id, Lead.platform_user_id == follower_id)
            .first()
        )
        if not lead:
            return []

        messages = (
            session.query(Message)
            .filter(Message.lead_id == lead.id)
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {"role": m.role, "content": m.content, "timestamp": str(m.created_at)}
            for m in messages  # Most recent first
        ]
    except Exception as e:
        logger.error(f"get_recent_messages error: {e}")
        return []
    finally:
        session.close()


def count_user_messages_by_lead_id(lead_id: str) -> int:
    """Count user messages for a specific lead by UUID (sync version)"""
    if not USE_POSTGRES:
        return 0
    session = get_session()
    if not session:
        return 0
    try:
        import uuid as uuid_module

        from api.models import Message

        lead_uuid = uuid_module.UUID(lead_id) if isinstance(lead_id, str) else lead_id
        count = (
            session.query(Message)
            .filter(Message.lead_id == lead_uuid, Message.role == "user")
            .count()
        )
        return count
    except Exception as e:
        logger.error(f"count_user_messages_by_lead_id error: {e}")
        return 0
    finally:
        session.close()
