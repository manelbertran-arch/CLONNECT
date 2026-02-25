"""
DM Agent Public API methods.

Knowledge management, follower detail, status updates,
and manual message handling.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from core.dm.models import ENABLE_FACT_TRACKING

if TYPE_CHECKING:
    from core.dm.agent import DMResponderAgentV2

logger = logging.getLogger(__name__)


def add_knowledge(agent: "DMResponderAgentV2", content: str, metadata: Optional[Dict] = None) -> str:
    """Add knowledge to RAG index."""
    agent.semantic_rag.add_document(
        doc_id=f"manual_{len(agent.semantic_rag._documents)}",
        text=content,
        metadata=metadata or {},
    )
    return f"manual_{len(agent.semantic_rag._documents) - 1}"


def add_knowledge_batch(agent: "DMResponderAgentV2", documents: List[Dict[str, Any]]) -> List[str]:
    """Add multiple documents to RAG index."""
    doc_ids = []
    for doc in documents:
        agent.semantic_rag.add_document(
            doc_id=f"batch_{len(agent.semantic_rag._documents)}",
            text=doc.get("content", ""),
            metadata=doc.get("metadata", {}),
        )
        doc_id = f"batch_{len(agent.semantic_rag._documents) - 1}"
        doc_ids.append(doc_id)
    return doc_ids


def clear_knowledge(agent: "DMResponderAgentV2") -> None:
    """Clear all knowledge from RAG index."""
    agent.semantic_rag._documents.clear()
    agent.semantic_rag._doc_list.clear()


def get_stats(agent: "DMResponderAgentV2") -> Dict[str, Any]:
    """Get agent statistics."""
    return {
        "creator_id": agent.creator_id,
        "config": {
            "llm_provider": agent.config.llm_provider.value,
            "llm_model": agent.config.llm_model,
            "temperature": agent.config.temperature,
        },
        "llm": agent.llm_service.get_stats(),
        "rag": {"total_documents": agent.semantic_rag.count()},
        "memory": {"cache_size": agent.memory_store.get_cache_size()},
        "instagram": agent.instagram_service.get_stats(),
    }


def health_check(agent: "DMResponderAgentV2") -> Dict[str, bool]:
    """Check health of all services."""
    return {
        "intent_classifier": agent.intent_classifier is not None,
        "prompt_builder": agent.prompt_builder is not None,
        "memory_store": agent.memory_store is not None,
        "rag_service": agent.semantic_rag is not None,
        "llm_service": agent.llm_service is not None,
        "lead_service": agent.lead_service is not None,
        "instagram_service": agent.instagram_service is not None,
    }


async def get_follower_detail(agent: "DMResponderAgentV2", follower_id: str) -> Optional[Dict[str, Any]]:
    """Get unified follower profile from multiple data sources."""
    follower = await agent.memory_store.get(agent.creator_id, follower_id)
    if not follower:
        return None

    result = {
        "follower_id": follower.follower_id,
        "username": follower.username,
        "name": follower.name,
        "platform": _detect_platform(follower_id),
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
        "email": None,
        "phone": None,
        "notes": None,
        "deal_value": None,
        "tags": [],
        "source": None,
        "assigned_to": None,
        "funnel_phase": None,
        "funnel_context": {},
        "weighted_interests": {},
        "preferences": {},
        "interested_products": [],
    }

    try:
        result = await _enrich_from_database(agent, result, follower_id)
    except Exception as e:
        logger.warning(f"Could not enrich follower data from DB: {e}")

    return result


async def save_manual_message(agent: "DMResponderAgentV2", follower_id: str, message_text: str, sent: bool = True) -> bool:
    """Save a manually sent message in the conversation history."""
    try:
        follower = await agent.memory_store.get(agent.creator_id, follower_id)
        if not follower:
            logger.warning(f"Follower {follower_id} not found for saving manual message")
            return False

        timestamp = datetime.now(timezone.utc).isoformat()
        follower.last_messages.append({
            "role": "assistant",
            "content": message_text,
            "timestamp": timestamp,
            "manual": True,
            "sent": sent,
        })
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
    agent: "DMResponderAgentV2", follower_id: str, status: str,
    purchase_intent: float, is_customer: bool = False,
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


async def update_follower_memory(agent: "DMResponderAgentV2", follower, user_message: str,
                                  assistant_message: str, intent: str) -> None:
    """Update follower memory with new messages."""
    import re

    now = datetime.now(timezone.utc).isoformat()
    follower.last_messages.append({"role": "user", "content": user_message, "timestamp": now})
    follower.last_messages.append({"role": "assistant", "content": assistant_message, "timestamp": now})
    follower.last_messages = follower.last_messages[-20:]

    if ENABLE_FACT_TRACKING:
        try:
            facts = []
            if re.search(r"\d+\s*€|\d+\s*euros?|\$\d+", assistant_message, re.IGNORECASE):
                facts.append("PRICE_GIVEN")
            if "https://" in assistant_message or "http://" in assistant_message:
                facts.append("LINK_SHARED")
            if agent.products:
                for prod in agent.products:
                    prod_name = prod.get("name", "").lower()
                    if prod_name and len(prod_name) > 3 and prod_name in assistant_message.lower():
                        facts.append("PRODUCT_EXPLAINED")
                        break
            if re.search(r"entiendo tu (duda|preocupación)|es normal|no te preocupes|garantía|devolución", assistant_message, re.IGNORECASE):
                facts.append("OBJECTION_RAISED")
            if re.search(r"me interesa|quiero saber|cuéntame|suena bien|me gusta", user_message, re.IGNORECASE):
                facts.append("INTEREST_EXPRESSED")
            if re.search(r"reserva|agenda|cita|llamada|reunión|calendly|cal\.com", assistant_message, re.IGNORECASE):
                facts.append("APPOINTMENT_MENTIONED")
            if re.search(r"@\w{3,}|[\w.-]+@[\w.-]+\.\w+|\+?\d{9,}|wa\.me|whatsapp", assistant_message, re.IGNORECASE):
                facts.append("CONTACT_SHARED")
            if "?" in assistant_message:
                facts.append("QUESTION_ASKED")
            if follower.name and len(follower.name) > 2 and follower.name.lower() in assistant_message.lower():
                facts.append("NAME_USED")
            if facts:
                follower.last_messages[-1]["facts"] = facts
                logger.debug(f"Facts tracked: {facts}")
        except Exception as e:
            logger.debug(f"Fact tracking failed: {e}")

    follower.total_messages += 1
    follower.last_contact = now
    await agent.memory_store.save(follower)


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _detect_platform(follower_id: str) -> str:
    """Detect platform from follower_id prefix."""
    if follower_id.startswith("ig_"):
        return "instagram"
    if follower_id.startswith("tg_"):
        return "telegram"
    if follower_id.startswith("wa_"):
        return "whatsapp"
    return "instagram"


async def _enrich_from_database(agent: "DMResponderAgentV2", result: Dict, follower_id: str) -> Dict:
    """Enrich follower data from PostgreSQL tables."""
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


# =============================================================================
# EMAIL CAPTURE & IDENTITY RESOLUTION (moved from postprocessing)
# =============================================================================

# Intents where we should NOT ask for email
_EMAIL_SKIP_INTENTS = frozenset({
    "escalation", "support", "sensitive", "crisis",
    "feedback_negative", "spam", "other",
})


def _step_email_capture(
    agent, message: str, formatted_content: str, intent_value: str,
    sender_id: str, follower, platform: str, cognitive_metadata: dict,
) -> str:
    """Step 9c: Email capture logic."""
    from core.unified_profile_service import extract_email, process_email_capture, should_ask_email, record_email_ask

    detected_email = extract_email(message)
    if detected_email:
        result = process_email_capture(
            email=detected_email, platform=platform,
            platform_user_id=sender_id, creator_id=agent.creator_id, name=follower.name,
        )
        if not result.get("error"):
            try:
                from api.services.db_service import update_lead

                update_lead(agent.creator_id, sender_id, {"email": detected_email})
            except Exception as e:
                logger.debug(f"Failed to update lead email: {e}")
            _trigger_identity_resolution(agent, sender_id, platform)
            cognitive_metadata["email_captured"] = detected_email
            logger.info(f"[EMAIL] Captured {detected_email} for {sender_id}")
            capture_response = result.get("response")
            if capture_response:
                return agent.instagram_service.format_message(capture_response)
        return formatted_content

    if intent_value.lower() in _EMAIL_SKIP_INTENTS:
        return formatted_content

    decision = should_ask_email(
        platform=platform, platform_user_id=sender_id, creator_id=agent.creator_id,
        intent=intent_value, message_count=follower.total_messages,
        is_friend=cognitive_metadata.get("relationship_type") == "amigo",
        is_customer=getattr(follower, "is_customer", False),
    )
    if decision.should_ask and decision.message:
        formatted_content = f"{formatted_content}\n\n{decision.message}"
        record_email_ask(platform=platform, platform_user_id=sender_id, creator_id=agent.creator_id)
        cognitive_metadata["email_asked"] = decision.reason
        logger.info(f"[EMAIL] Ask appended for {sender_id} (reason={decision.reason})")

    return formatted_content


def _trigger_identity_resolution(agent, sender_id: str, platform: str) -> None:
    """Fire-and-forget identity resolution for a lead."""
    try:
        from api.services.db_service import get_session
        from api.models import Lead

        session = get_session()
        if not session:
            return
        try:
            from api.models import Creator

            creator = session.query(Creator).filter_by(name=agent.creator_id).first()
            if not creator:
                return
            lead = session.query(Lead).filter(
                Lead.creator_id == creator.id, Lead.platform_user_id == sender_id
            ).first()
            if not lead:
                return
            lead_id = str(lead.id)
        finally:
            session.close()

        from core.identity_resolver import resolve_identity

        asyncio.create_task(resolve_identity(agent.creator_id, lead_id, platform))
    except Exception as e:
        logger.debug(f"[IDENTITY] trigger failed: {e}")
