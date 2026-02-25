"""
Follower management API for DM Agent V2.

Public API methods for follower profiles, manual messages, and status updates.
Each function takes `agent` as first parameter.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def get_follower_detail(agent, follower_id: str) -> Optional[Dict[str, Any]]:
    """Get unified follower profile from multiple data sources."""
    follower = await agent.memory_store.get(agent.creator_id, follower_id)

    if not follower:
        return None

    result = {
        "follower_id": follower.follower_id,
        "username": follower.username,
        "name": follower.name,
        "platform": agent._detect_platform(follower_id),
        "profile_pic_url": None,
        "first_contact": follower.first_contact,
        "last_contact": follower.last_contact,
        "total_messages": follower.total_messages,
        "interests": follower.interests or [],
        "products_discussed": follower.products_discussed or [],
        "objections_raised": follower.objections_raised or [],
        "purchase_intent_score": follower.purchase_intent_score or 0.0,
        "is_lead": follower.is_lead,
        "is_customer": follower.is_customer,
        "status": getattr(follower, "status", None),
        "preferred_language": follower.preferred_language or "es",
        "last_messages": follower.last_messages[-20:] if follower.last_messages else [],
        # CRM fields (from leads) - defaults
        "email": None,
        "phone": None,
        "notes": None,
        "deal_value": None,
        "tags": [],
        "source": None,
        "assigned_to": None,
        # Funnel fields (from conversation_states) - defaults
        "funnel_phase": None,
        "funnel_context": {},
        # Behavior profile (from user_profiles) - defaults
        "weighted_interests": {},
        "preferences": {},
        "interested_products": [],
    }

    # Step 2: Enrich from PostgreSQL if available
    try:
        result = await enrich_from_database(agent, result, follower_id)
    except Exception as e:
        logger.warning(f"Could not enrich follower data from DB: {e}")

    return result


async def enrich_from_database(
    agent, result: Dict[str, Any], follower_id: str
) -> Dict[str, Any]:
    """Enrich follower data from PostgreSQL tables using JOINs."""
    if not os.getenv("DATABASE_URL"):
        return result

    try:
        from api.models import ConversationStateDB, Lead, UserProfileDB
        from api.services.db_service import get_session

        session = get_session()
        if not session:
            return result

        try:
            lead = session.query(Lead).filter(Lead.platform_user_id == follower_id).first()
            if lead:
                result["email"] = lead.email
                result["phone"] = lead.phone
                result["notes"] = lead.notes
                result["deal_value"] = lead.deal_value
                result["tags"] = lead.tags or []
                result["source"] = lead.source
                result["assigned_to"] = lead.assigned_to
                result["profile_pic_url"] = lead.profile_pic_url
                if lead.status:
                    result["status"] = lead.status

            conv_state = (
                session.query(ConversationStateDB)
                .filter(
                    ConversationStateDB.creator_id == agent.creator_id,
                    ConversationStateDB.follower_id == follower_id,
                )
                .first()
            )
            if conv_state:
                result["funnel_phase"] = conv_state.phase
                result["funnel_context"] = conv_state.context or {}

            user_profile = (
                session.query(UserProfileDB)
                .filter(
                    UserProfileDB.creator_id == agent.creator_id,
                    UserProfileDB.user_id == follower_id,
                )
                .first()
            )
            if user_profile:
                result["weighted_interests"] = user_profile.interests or {}
                result["preferences"] = user_profile.preferences or {}
                result["interested_products"] = user_profile.interested_products or []

        finally:
            session.close()

    except ImportError:
        logger.debug("Database models not available for enrichment")
    except Exception as e:
        logger.warning(f"Database enrichment failed: {e}")

    return result


async def save_manual_message(
    agent, follower_id: str, message_text: str, sent: bool = True
) -> bool:
    """Save a manually sent message in the conversation history."""
    try:
        follower = await agent.memory_store.get(agent.creator_id, follower_id)

        if not follower:
            logger.warning(f"Follower {follower_id} not found for saving manual message")
            return False

        timestamp = datetime.now(timezone.utc).isoformat()
        follower.last_messages.append(
            {
                "role": "assistant",
                "content": message_text,
                "timestamp": timestamp,
                "manual": True,
                "sent": sent,
            }
        )

        if len(follower.last_messages) > 50:
            follower.last_messages = follower.last_messages[-50:]

        follower.last_contact = timestamp
        await agent.memory_store.save(follower)

        logger.info(f"Saved manual message for {follower_id}")
        return True

    except Exception as e:
        logger.error(f"Error saving manual message: {e}")
        return False


async def update_follower_status(
    agent, follower_id: str, status: str, purchase_intent: float, is_customer: bool = False
) -> bool:
    """Update the lead status for a follower."""
    try:
        follower = await agent.memory_store.get(agent.creator_id, follower_id)

        if not follower:
            logger.warning(f"Follower {follower_id} not found for status update")
            return False

        old_score = follower.purchase_intent_score
        follower.purchase_intent_score = purchase_intent

        if purchase_intent >= 0.3:
            follower.is_lead = True

        if is_customer:
            follower.is_customer = True

        await agent.memory_store.save(follower)

        logger.info(
            f"Updated status for {follower_id}: {status} (intent: {old_score:.0%} -> {purchase_intent:.0%})"
        )
        return True

    except Exception as e:
        logger.error(f"Error updating follower status: {e}")
        return False
