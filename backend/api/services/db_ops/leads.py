"""
Lead CRUD operations — sync and async variants.
"""

import logging
import uuid
from datetime import datetime

from api.services.db_ops.common import USE_POSTGRES, get_session
from api.utils.creator_resolver import resolve_creator_safe

logger = logging.getLogger(__name__)


def get_leads(creator_name: str, include_archived: bool = False, limit: int = 100):
    """Get leads for a creator with pagination.

    Args:
        creator_name: Creator's name
        include_archived: Include archived/spam leads
        limit: Maximum leads to return (default 100 for performance)
    """
    session = get_session()
    if not session:
        return []
    try:
        from api.models import Creator, Lead, Message
        from sqlalchemy import desc, not_

        creator = resolve_creator_safe(session, creator_name)
        if not creator:
            return []
        # Filter out archived and spam leads by default
        query = session.query(Lead).filter_by(creator_id=creator.id)
        if not include_archived:
            query = query.filter(not_(Lead.status.in_(["archived", "spam"])))
        # Add limit for performance (was loading ALL leads before)
        leads = query.order_by(Lead.last_contact_at.desc()).limit(limit).all()

        # Get last message for each lead using DISTINCT ON (PostgreSQL optimization)
        lead_ids = [lead.id for lead in leads]
        last_messages = {}
        if lead_ids:
            # DISTINCT ON is much faster than subquery + JOIN
            # Only include sent/edited messages (exclude pending_approval copilot drafts)
            last_msg_query = (
                session.query(Message)
                .filter(
                    Message.lead_id.in_(lead_ids),
                    Message.status.in_(["sent", "edited"]),
                )
                .distinct(Message.lead_id)
                .order_by(Message.lead_id, desc(Message.created_at))
            )
            for msg in last_msg_query.all():
                last_messages[msg.lead_id] = msg

        result = []
        for lead in leads:
            # Get last message preview and role
            last_msg = last_messages.get(lead.id)
            last_message_preview = None
            last_message_role = None
            if last_msg:
                content = last_msg.content or ""
                last_message_preview = content[:50] + "..." if len(content) > 50 else content
                last_message_role = last_msg.role

            # is_unread: true if last message is from user (follower) - awaiting creator response
            is_unread = last_message_role == "user"

            # is_verified: from context JSON (populated by Instagram API)
            context = lead.context or {}
            is_verified = context.get("is_verified", False)

            result.append(
                {
                    "id": str(lead.id),
                    "follower_id": str(lead.id),
                    "platform_user_id": lead.platform_user_id,
                    "platform": lead.platform,
                    "username": lead.username,
                    "full_name": lead.full_name,
                    "profile_pic_url": lead.profile_pic_url,
                    "status": lead.status,
                    "score": lead.score,
                    "purchase_intent": lead.purchase_intent,
                    "relationship_type": lead.relationship_type or "nuevo",
                    "last_contact_at": (
                        lead.last_contact_at.isoformat() if lead.last_contact_at else None
                    ),
                    # Instagram-like UX fields (FIX 2026-02-02)
                    "last_message_preview": last_message_preview,
                    "last_message_role": last_message_role,
                    "is_unread": is_unread,
                    "is_verified": is_verified,
                    # CRM fields from direct columns (not context JSON)
                    "email": lead.email,
                    "phone": lead.phone,
                    "notes": lead.notes,
                    "tags": lead.tags,
                    "deal_value": lead.deal_value,
                }
            )
        return result
    finally:
        session.close()


def create_lead(creator_name: str, data: dict):
    import time
    start = time.time()
    session = get_session()
    if not session:
        logger.warning("create_lead: no database session available")
        return None
    try:
        from api.models import Creator, Lead

        t1 = time.time()
        creator = resolve_creator_safe(session, creator_name)
        logger.info(f"⏱️ create_lead: query creator took {time.time()-t1:.2f}s")

        if not creator:
            logger.warning(f"create_lead: creator '{creator_name}' not found, creating it")
            creator = Creator(name=creator_name)
            session.add(creator)
            session.commit()

        # Build context with optional fields (email, phone, notes stored in JSON)
        context = {}
        if data.get("email"):
            context["email"] = data.get("email")
        if data.get("phone"):
            context["phone"] = data.get("phone")
        if data.get("notes"):
            context["notes"] = data.get("notes")

        # Use "name" field for both username and full_name if specific fields not provided
        name_value = data.get("name", "")
        lead = Lead(
            creator_id=creator.id,
            platform=data.get("platform", "manual"),
            platform_user_id=data.get("platform_user_id") or str(uuid.uuid4()),
            username=data.get("username") or name_value,
            full_name=data.get("full_name") or name_value,
            source=data.get("source", f"{data.get('platform', 'manual')}_dm"),
            status=data.get("status", "new"),
            score=data.get("score", 0),
            purchase_intent=data.get("purchase_intent", 0.0),
            context=context,
        )
        session.add(lead)
        t2 = time.time()
        session.commit()
        logger.info(f"⏱️ create_lead: commit took {time.time()-t2:.2f}s")
        logger.info(f"⏱️ create_lead: TOTAL {time.time()-start:.2f}s for {creator_name}")
        return {
            "id": str(lead.id),
            "platform_user_id": lead.platform_user_id,
            "username": lead.username,
            "full_name": lead.full_name,
            "platform": lead.platform,
            "status": lead.status,
            "score": lead.score,
            "purchase_intent": lead.purchase_intent,
            "relationship_type": lead.relationship_type or "nuevo",
            "email": context.get("email"),
            "phone": context.get("phone"),
            "notes": context.get("notes"),
        }
    except Exception as e:
        logger.error(f"create_lead error: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def update_lead(creator_name: str, lead_id: str, data: dict):
    session = get_session()
    if not session:
        return False
    try:
        from api.models import Creator, Lead

        creator = resolve_creator_safe(session, creator_name)
        if not creator:
            logger.warning(f"update_lead: creator '{creator_name}' not found")
            return False

        # Try to find lead by UUID first, then by platform_user_id
        lead = None
        try:
            lead = (
                session.query(Lead).filter_by(creator_id=creator.id, id=uuid.UUID(lead_id)).first()
            )
        except (ValueError, AttributeError):
            pass  # Not a valid UUID, try platform_user_id

        if not lead:
            lead = (
                session.query(Lead)
                .filter_by(creator_id=creator.id, platform_user_id=lead_id)
                .first()
            )

        if lead:
            logger.info(f"update_lead: lead {lead_id} found")

            # CRM fields are now direct columns on Lead model
            _crm_fields = ["email", "phone", "notes", "tags", "deal_value", "source", "assigned_to"]

            for key, value in data.items():
                if hasattr(lead, key):
                    setattr(lead, key, value)
                    logger.info(f"update_lead: setting {key} = {value}")

            # Also update name fields if provided
            if "name" in data:
                lead.full_name = data["name"]
                if not lead.username:
                    lead.username = data["name"]

            session.commit()
            logger.info(f"update_lead: committed lead {lead_id}")
            return {
                "id": str(lead.id),
                "platform_user_id": lead.platform_user_id,
                "username": lead.username,
                "full_name": lead.full_name,
                "platform": lead.platform,
                "status": lead.status,
                "score": lead.score,
                "purchase_intent": lead.purchase_intent,
                "relationship_type": lead.relationship_type or "nuevo",
                "email": lead.email,
                "phone": lead.phone,
                "notes": lead.notes,
                "tags": lead.tags,
                "deal_value": lead.deal_value,
            }
        logger.warning(f"update_lead: lead '{lead_id}' not found")
        return None
    except Exception as e:
        logger.error(f"update_lead error: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def delete_lead(creator_name: str, lead_id: str):
    """
    Delete a lead using raw SQL for speed.
    ORM cascade is slow with many messages - this uses bulk DELETE.
    """
    session = get_session()
    if not session:
        return False
    try:
        from api.models import Creator, Lead
        from sqlalchemy import text

        creator = resolve_creator_safe(session, creator_name)
        if not creator:
            logger.warning(f"delete_lead: creator '{creator_name}' not found")
            return False

        # Try to find lead by UUID first, then by platform_user_id
        lead_uuid = None
        try:
            lead_uuid = uuid.UUID(lead_id)
            lead = session.query(Lead).filter_by(creator_id=creator.id, id=lead_uuid).first()
        except (ValueError, AttributeError):
            lead = (
                session.query(Lead)
                .filter_by(creator_id=creator.id, platform_user_id=lead_id)
                .first()
            )

        if not lead:
            logger.warning(f"delete_lead: lead '{lead_id}' not found")
            return False

        lead_uuid = lead.id
        platform_user_id = lead.platform_user_id

        # FAST: Use raw SQL bulk DELETE (not ORM cascade which is slow)
        # Delete related records first (FK constraints)
        session.execute(
            text("DELETE FROM lead_activities WHERE lead_id = :lid"), {"lid": lead_uuid}
        )
        session.execute(text("DELETE FROM lead_tasks WHERE lead_id = :lid"), {"lid": lead_uuid})
        session.execute(text("DELETE FROM csat_ratings WHERE lead_id = :lid"), {"lid": lead_uuid})
        session.execute(text("DELETE FROM messages WHERE lead_id = :lid"), {"lid": lead_uuid})

        # Add to dismissed_leads blocklist so it doesn't reappear on sync
        session.execute(
            text(
                """
            INSERT INTO dismissed_leads (creator_id, platform_user_id, dismissed_at)
            VALUES (:cid, :puid, NOW())
            ON CONFLICT (creator_id, platform_user_id) DO NOTHING
        """
            ),
            {"cid": creator.id, "puid": platform_user_id},
        )

        # Now delete the lead itself
        session.execute(text("DELETE FROM leads WHERE id = :lid"), {"lid": lead_uuid})

        session.commit()
        logger.info(f"delete_lead: deleted lead {lead_id} (fast SQL)")
        return True
    except Exception as e:
        logger.error(f"delete_lead error: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def get_lead_by_id(creator_name: str, lead_id: str):
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Creator, Lead

        creator = resolve_creator_safe(session, creator_name)
        if not creator:
            return None

        # Try to find lead by UUID first, then by platform_user_id
        lead = None
        try:
            lead = (
                session.query(Lead).filter_by(creator_id=creator.id, id=uuid.UUID(lead_id)).first()
            )
        except (ValueError, AttributeError):
            pass  # Not a valid UUID, try platform_user_id

        if not lead:
            lead = (
                session.query(Lead)
                .filter_by(creator_id=creator.id, platform_user_id=lead_id)
                .first()
            )

        if lead:
            return {
                "id": str(lead.id),
                "platform_user_id": lead.platform_user_id,
                "platform": lead.platform,
                "username": lead.username,
                "full_name": lead.full_name,
                "status": lead.status,
                "score": lead.score,
                "purchase_intent": lead.purchase_intent,
                "relationship_type": lead.relationship_type or "nuevo",
                # CRM fields from direct columns
                "email": lead.email,
                "phone": lead.phone,
                "notes": lead.notes,
                "tags": lead.tags,
                "deal_value": lead.deal_value,
                "context": lead.context or {},
            }
        return None
    finally:
        session.close()


# Async lead operations are in leads_async.py
# Re-exported here for convenience
from api.services.db_ops.leads_async import (  # noqa: E402, F401
    create_lead_async,
    get_lead_by_platform_id,
    get_or_create_lead,
)
