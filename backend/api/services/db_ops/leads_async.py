"""
Async lead operations — get_lead_by_platform_id, create_lead_async, get_or_create_lead.
"""

import logging
import uuid
from datetime import datetime

from api.services.db_ops.common import USE_POSTGRES, get_session
from api.utils.creator_resolver import resolve_creator_safe

logger = logging.getLogger(__name__)


async def get_lead_by_platform_id(creator_id: str, platform_id: str) -> dict:
    """Get a lead by their platform-specific ID (e.g., tg_123, ig_456)"""
    if not USE_POSTGRES:
        return None
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Creator, Lead

        # Get creator by name or UUID
        creator = resolve_creator_safe(session, creator_id)
        if not creator:
            return None
        # Find lead by platform_user_id
        lead = (
            session.query(Lead)
            .filter_by(creator_id=creator.id, platform_user_id=platform_id)
            .first()
        )
        if lead:
            return {
                "id": str(lead.id),
                "creator_id": str(creator.id),
                "platform_user_id": lead.platform_user_id,
                "platform": lead.platform,
                "username": lead.username,
                "full_name": lead.full_name,
                "status": lead.status,
            }
        return None
    except Exception as e:
        logger.error(f"get_lead_by_platform_id error: {e}")
        return None
    finally:
        session.close()


async def create_lead_async(creator_id: str, data: dict) -> dict:
    """Create a new lead for dm_agent integration (async version).

    FIX: Added duplicate check to prevent race conditions from creating duplicate leads.
    """
    if not USE_POSTGRES:
        return None
    session = get_session()
    if not session:
        return None
    try:
        from api.models import Creator, Lead

        # Get creator by name or UUID
        creator = resolve_creator_safe(session, creator_id)
        if not creator:
            logger.warning(f"Creator not found: {creator_id}")
            return None

        platform_user_id = data.get("platform_user_id", str(uuid.uuid4()))

        # DUPLICATE CHECK: Prevent race condition duplicates
        existing = (
            session.query(Lead)
            .filter_by(creator_id=creator.id, platform_user_id=platform_user_id)
            .first()
        )
        if existing:
            logger.info(f"Lead already exists for {platform_user_id}, returning existing")
            return {"id": str(existing.id), "status": "existing"}

        # Create new lead
        lead = Lead(
            creator_id=creator.id,
            platform=data.get("platform", "telegram"),
            platform_user_id=platform_user_id,
            username=data.get("username", ""),
            full_name=data.get("full_name") or data.get("name", ""),
            status="new",
            score=0,
            purchase_intent=0.0,
        )
        session.add(lead)
        session.commit()
        return {"id": str(lead.id), "status": "created"}
    except Exception as e:
        logger.error(f"create_lead error: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def get_or_create_lead(
    creator_name: str,
    platform_user_id: str,
    platform: str = "instagram",
    username: str = None,
    full_name: str = None,
    profile_pic_url: str = None,
) -> dict:
    """
    Get existing lead or create new one. Used by Instagram webhook handlers.

    This is the primary function for ensuring a lead exists when processing
    incoming messages or interactions.
    """
    session = get_session()
    if not session:
        logger.warning("get_or_create_lead: no database session available")
        return None

    try:
        from datetime import timezone

        from api.models import Creator, DismissedLead, Lead

        # Get creator by name or UUID
        creator = resolve_creator_safe(session, creator_name)
        if not creator:
            logger.warning(f"get_or_create_lead: creator '{creator_name}' not found")
            return None

        # Check if lead already exists - check both with and without ig_ prefix
        # to prevent duplicates from different sources
        raw_id = (
            platform_user_id.replace("ig_", "")
            if platform_user_id.startswith("ig_")
            else platform_user_id
        )
        possible_ids = [platform_user_id, f"ig_{raw_id}", raw_id]
        # Remove duplicates while preserving order
        possible_ids = list(dict.fromkeys(possible_ids))

        lead = (
            session.query(Lead)
            .filter(Lead.creator_id == creator.id, Lead.platform_user_id.in_(possible_ids))
            .first()
        )

        if lead:
            # Update profile info if provided and changed
            if username and lead.username != username:
                lead.username = username
            if full_name and lead.full_name != full_name:
                lead.full_name = full_name
            if profile_pic_url and lead.profile_pic_url != profile_pic_url:
                lead.profile_pic_url = profile_pic_url

            # Always update last_contact_at
            lead.last_contact_at = datetime.now(timezone.utc)
            session.commit()

            return {
                "id": str(lead.id),
                "creator_id": str(creator.id),
                "platform_user_id": lead.platform_user_id,
                "username": lead.username,
                "full_name": lead.full_name,
                "status": lead.status,
            }

        # Check if this lead was dismissed (deleted by creator)
        # Must check all possible ID formats in the blocklist
        is_dismissed = (
            session.query(DismissedLead)
            .filter(
                DismissedLead.creator_id == creator.id,
                DismissedLead.platform_user_id.in_(possible_ids),
            )
            .first()
        )
        if is_dismissed:
            logger.info(
                f"get_or_create_lead: BLOCKED dismissed lead {platform_user_id} "
                f"(dismissed as {is_dismissed.platform_user_id})"
            )
            return None

        # Create new lead
        now = datetime.now(timezone.utc)
        lead = Lead(
            creator_id=creator.id,
            platform=platform,
            platform_user_id=platform_user_id,
            username=username or platform_user_id,
            full_name=full_name or username or "",
            profile_pic_url=profile_pic_url,
            source=f"{platform}_dm",
            status="new",
            score=0,
            purchase_intent=0.0,
            first_contact_at=now,
            last_contact_at=now,
        )
        session.add(lead)
        session.commit()

        logger.info(f"get_or_create_lead: created new lead {lead.id} for {platform_user_id}")

        return {
            "id": str(lead.id),
            "creator_id": str(creator.id),
            "platform_user_id": lead.platform_user_id,
            "username": lead.username,
            "full_name": lead.full_name,
            "status": lead.status,
        }

    except Exception as e:
        logger.error(f"get_or_create_lead error: {e}")
        session.rollback()
        return None
    finally:
        session.close()
