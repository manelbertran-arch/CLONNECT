"""
Post-response processing for DM Agent V2.

Background tasks that run after the LLM response is generated:
- Memory save, nurturing, DNA triggers
- Follower memory update with fact tracking
- Lead score update
- Email capture
- Escalation notification
- Identity resolution
"""

import asyncio
import logging
import os
import re
import time as _time_mod
from datetime import datetime, timezone
from typing import Dict

from core.notifications import EscalationNotification, get_notification_service
from services import LeadStage
from services.dna_update_triggers import get_dna_triggers

logger = logging.getLogger(__name__)

# Feature flags (read at import time, same as original)
ENABLE_FACT_TRACKING = os.getenv("ENABLE_FACT_TRACKING", "true").lower() == "true"
ENABLE_DNA_TRIGGERS = os.getenv("ENABLE_DNA_TRIGGERS", "true").lower() == "true"

# Intents where we should NOT ask for email
_EMAIL_SKIP_INTENTS = frozenset({
    "escalation", "support", "sensitive", "crisis",
    "feedback_negative", "spam", "other",
})


async def background_post_response(
    agent,
    follower,
    message: str,
    formatted_content: str,
    intent_value: str,
    sender_id: str,
    metadata: Dict,
    cognitive_metadata: Dict,
) -> None:
    """Run memory save, nurturing, DNA triggers, and escalation in background thread."""
    try:
        await asyncio.to_thread(
            sync_post_response,
            agent, follower, message, formatted_content, intent_value,
            sender_id, metadata, cognitive_metadata,
        )
        logger.debug(f"[BACKGROUND] Post-response tasks completed for {sender_id}")
    except Exception as e:
        logger.error(f"[BACKGROUND] Post-response tasks failed: {e}", exc_info=True)


def sync_post_response(
    agent,
    follower,
    message: str,
    formatted_content: str,
    intent_value: str,
    sender_id: str,
    metadata: Dict,
    cognitive_metadata: Dict,
) -> None:
    """Synchronous post-response tasks (runs in thread pool)."""
    now = datetime.now(timezone.utc).isoformat()
    follower.last_messages.append(
        {"role": "user", "content": message, "timestamp": now}
    )

    # COPILOT FIX: Don't save bot suggestion to memory in copilot mode.
    is_copilot = False
    try:
        from core.copilot_service import get_copilot_service
        is_copilot = get_copilot_service().is_copilot_enabled(agent.creator_id)
    except Exception:
        pass

    if not is_copilot:
        follower.last_messages.append(
            {"role": "assistant", "content": formatted_content, "timestamp": now}
        )
    follower.last_messages = follower.last_messages[-20:]
    follower.total_messages += 1
    follower.last_contact = now

    # Fact tracking
    if ENABLE_FACT_TRACKING:
        try:
            facts = []
            if re.search(r"\d+\s*€|\d+\s*euros?|\$\d+", formatted_content, re.IGNORECASE):
                facts.append("PRICE_GIVEN")
            if "https://" in formatted_content or "http://" in formatted_content:
                facts.append("LINK_SHARED")
            if agent.products:
                for prod in agent.products:
                    prod_name = prod.get("name", "").lower()
                    if prod_name and len(prod_name) > 3 and prod_name in formatted_content.lower():
                        facts.append("PRODUCT_EXPLAINED")
                        break
            if re.search(r"entiendo tu (duda|preocupación)|es normal|no te preocupes|garantía|devolución", formatted_content, re.IGNORECASE):
                facts.append("OBJECTION_RAISED")
            if re.search(r"me interesa|quiero saber|cuéntame|suena bien|me gusta", message, re.IGNORECASE):
                facts.append("INTEREST_EXPRESSED")
            if re.search(r"reserva|agenda|cita|llamada|reunión|calendly|cal\.com", formatted_content, re.IGNORECASE):
                facts.append("APPOINTMENT_MENTIONED")
            if re.search(r"@\w{3,}|[\w.-]+@[\w.-]+\.\w+|\+?\d{9,}|wa\.me|whatsapp", formatted_content, re.IGNORECASE):
                facts.append("CONTACT_SHARED")
            if "?" in formatted_content:
                facts.append("QUESTION_ASKED")
            if follower.name and len(follower.name) > 2 and follower.name.lower() in formatted_content.lower():
                facts.append("NAME_USED")
            if facts:
                follower.last_messages[-1]["facts"] = facts
        except Exception as e:
            logger.debug(f"Fact tracking failed: {e}")

    # Save to JSON storage (sync file I/O)
    try:
        agent.memory_store._save_to_json(follower)
    except Exception as e:
        logger.debug(f"Memory save failed: {e}")

    # Step 8b: Check DNA update triggers
    if ENABLE_DNA_TRIGGERS:
        try:
            triggers = get_dna_triggers()
            existing_dna = metadata.get("dna_data")

            is_seed_dna = (
                existing_dna
                and existing_dna.get("total_messages_analyzed", 0) == 0
                and follower.total_messages >= 5
            )

            if is_seed_dna or triggers.should_update(existing_dna, follower.total_messages):
                msgs = follower.last_messages[-30:]
                triggers.schedule_async_update(agent.creator_id, sender_id, msgs)
                cognitive_metadata["dna_update_scheduled"] = True
                if is_seed_dna:
                    logger.info(
                        f"[DNA-TRIGGER] Seed DNA upgrade scheduled for {sender_id} "
                        f"(messages={follower.total_messages})"
                    )
        except Exception as e:
            logger.debug(f"DNA trigger check failed: {e}")

    # Step 9b: Auto-schedule nurturing based on intent
    try:
        from core.nurturing import should_schedule_nurturing, get_nurturing_manager

        sequence_type = should_schedule_nurturing(
            intent=intent_value,
            has_purchased=follower.is_customer,
            creator_id=agent.creator_id,
        )
        if sequence_type:
            manager = get_nurturing_manager()
            followups = manager.schedule_followup(
                creator_id=agent.creator_id,
                follower_id=sender_id,
                sequence_type=sequence_type,
                product_name="",
            )
            if followups:
                logger.info(
                    f"[NURTURING] Auto-scheduled {len(followups)} followups "
                    f"(type={sequence_type}) for {sender_id}"
                )
                cognitive_metadata["nurturing_scheduled"] = sequence_type
    except Exception as e:
        logger.error(f"[NURTURING] Auto-trigger failed: {e}")


async def update_follower_memory(
    agent,
    follower,
    user_message: str,
    assistant_message: str,
    intent: str,
) -> None:
    """Update follower memory with new messages."""
    now = datetime.now(timezone.utc).isoformat()

    follower.last_messages.append(
        {"role": "user", "content": user_message, "timestamp": now}
    )
    follower.last_messages.append(
        {"role": "assistant", "content": assistant_message, "timestamp": now}
    )

    follower.last_messages = follower.last_messages[-20:]

    # Track facts in assistant response (9 types)
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
                    if (
                        prod_name
                        and len(prod_name) > 3
                        and prod_name in assistant_message.lower()
                    ):
                        facts.append("PRODUCT_EXPLAINED")
                        break
            if re.search(
                r"entiendo tu (duda|preocupación)|es normal|no te preocupes|garantía|devolución",
                assistant_message, re.IGNORECASE,
            ):
                facts.append("OBJECTION_RAISED")
            if re.search(
                r"me interesa|quiero saber|cuéntame|suena bien|me gusta",
                user_message, re.IGNORECASE,
            ):
                facts.append("INTEREST_EXPRESSED")
            if re.search(
                r"reserva|agenda|cita|llamada|reunión|calendly|cal\.com",
                assistant_message, re.IGNORECASE,
            ):
                facts.append("APPOINTMENT_MENTIONED")
            if re.search(
                r"@\w{3,}|[\w.-]+@[\w.-]+\.\w+|\+?\d{9,}|wa\.me|whatsapp",
                assistant_message, re.IGNORECASE,
            ):
                facts.append("CONTACT_SHARED")
            if "?" in assistant_message:
                facts.append("QUESTION_ASKED")
            if (
                follower.name
                and len(follower.name) > 2
                and follower.name.lower() in assistant_message.lower()
            ):
                facts.append("NAME_USED")
            if facts:
                follower.last_messages[-1]["facts"] = facts
                logger.debug(f"Facts tracked: {facts}")
        except Exception as e:
            logger.debug(f"Fact tracking failed: {e}")

    follower.total_messages += 1
    follower.last_contact = now
    await agent.memory_store.save(follower)


def update_lead_score(agent, follower, intent: str, metadata: Dict) -> LeadStage:
    """Update and return lead stage based on interaction."""
    new_score = agent.lead_service.calculate_intent_score(
        current_score=follower.purchase_intent_score or 0.0,
        intent=intent.upper() if intent else "OTHER",
        has_direct_purchase_keywords=(intent in ["purchase_intent", "PURCHASE_INTENT"]),
    )
    follower.purchase_intent_score = new_score

    return agent.lead_service.determine_stage(
        score=int(new_score * 100),
        days_since_contact=metadata.get("days_since_contact", 0),
        is_customer=follower.is_customer,
    )


def step_email_capture(
    agent,
    message: str,
    formatted_content: str,
    intent_value: str,
    sender_id: str,
    follower,
    platform: str,
    cognitive_metadata: dict,
) -> str:
    """Step 9c: Email capture logic."""
    from core.unified_profile_service import (
        extract_email,
        process_email_capture,
        should_ask_email,
        record_email_ask,
    )

    detected_email = extract_email(message)
    if detected_email:
        result = process_email_capture(
            email=detected_email,
            platform=platform,
            platform_user_id=sender_id,
            creator_id=agent.creator_id,
            name=follower.name,
        )
        if not result.get("error"):
            try:
                from api.services.db_service import update_lead
                update_lead(agent.creator_id, sender_id, {"email": detected_email})
            except Exception as e:
                logger.debug(f"Failed to update lead email: {e}")

            trigger_identity_resolution(agent, sender_id, platform)

            cognitive_metadata["email_captured"] = detected_email
            logger.info(f"[EMAIL] Captured {detected_email} for {sender_id}")
            capture_response = result.get("response")
            if capture_response:
                return agent.instagram_service.format_message(capture_response)
        return formatted_content

    if intent_value.lower() in _EMAIL_SKIP_INTENTS:
        return formatted_content

    decision = should_ask_email(
        platform=platform,
        platform_user_id=sender_id,
        creator_id=agent.creator_id,
        intent=intent_value,
        message_count=follower.total_messages,
        is_friend=cognitive_metadata.get("relationship_type") == "amigo",
        is_customer=getattr(follower, "is_customer", False),
    )

    if decision.should_ask and decision.message:
        formatted_content = f"{formatted_content}\n\n{decision.message}"
        record_email_ask(
            platform=platform,
            platform_user_id=sender_id,
            creator_id=agent.creator_id,
        )
        cognitive_metadata["email_asked"] = decision.reason
        logger.info(f"[EMAIL] Ask appended for {sender_id} (reason={decision.reason})")

    return formatted_content


async def check_and_notify_escalation(
    agent,
    intent_value: str,
    follower,
    sender_id: str,
    message: str,
    metadata: Dict,
) -> None:
    """Check if intent warrants escalation notification and send if needed."""
    escalation_intents = {"escalation", "support", "feedback_negative"}
    intent_lower = intent_value.lower() if intent_value else ""

    should_notify = intent_lower in escalation_intents
    is_hot_lead = (
        follower.purchase_intent_score
        and follower.purchase_intent_score >= 0.8
        and intent_lower == "interest_strong"
    )

    if not should_notify and not is_hot_lead:
        return

    try:
        notification_service = get_notification_service()

        if intent_lower == "escalation":
            reason = "Usuario solicitó hablar con una persona real"
        elif intent_lower == "support":
            reason = "Usuario reportó un problema o necesita soporte"
        elif intent_lower == "feedback_negative":
            reason = "Usuario expresó insatisfacción o feedback negativo"
        elif is_hot_lead:
            reason = f"\U0001f525 HOT LEAD - Intención de compra: {follower.purchase_intent_score:.0%}"
        else:
            reason = f"Escalación automática por intent: {intent_value}"

        notification = EscalationNotification(
            creator_id=agent.creator_id,
            follower_id=sender_id,
            follower_username=follower.username or sender_id,
            follower_name=metadata.get("name", ""),
            reason=reason,
            last_message=message[:500],
            conversation_summary=agent._get_conversation_summary(follower),
            purchase_intent_score=follower.purchase_intent_score or 0.0,
            total_messages=follower.total_messages or 0,
            products_discussed=follower.products_discussed or [],
        )

        _t_notif = _time_mod.time()
        results = await notification_service.notify_escalation(notification)
        _elapsed = _time_mod.time() - _t_notif
        logger.info(
            f"[A17] DM→Telegram escalation: {_elapsed:.1f}s for {sender_id}: {results}"
        )

    except Exception as e:
        logger.error(f"Failed to send escalation notification: {e}")


def trigger_identity_resolution(agent, sender_id: str, platform: str) -> None:
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
            lead = (
                session.query(Lead)
                .filter(Lead.creator_id == creator.id, Lead.platform_user_id == sender_id)
                .first()
            )
            if not lead:
                return
            lead_id = str(lead.id)
        finally:
            session.close()

        from core.identity_resolver import resolve_identity
        asyncio.create_task(resolve_identity(agent.creator_id, lead_id, platform))
    except Exception as e:
        logger.debug(f"[IDENTITY] trigger failed: {e}")
