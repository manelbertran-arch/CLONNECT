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


# BUG-EP-04 fix: Shared fact-tracking function (was duplicated in two code paths).
# BUG-EP-05 fix: Added multilingual regex (ES/CA/EN/IT).
def _extract_facts(
    assistant_msg: str, user_msg: str, products: list, follower_name: str | None = None,
) -> list[str]:
    """Extract fact tags from assistant + user messages. Returns list of tag strings."""
    facts: list[str] = []
    if re.search(r"\d+\s*€|\d+\s*euros?|\$\d+|\d+\s*USD", assistant_msg, re.IGNORECASE):
        facts.append("PRICE_GIVEN")
    if "https://" in assistant_msg or "http://" in assistant_msg:
        facts.append("LINK_SHARED")
    if products:
        for prod in products:
            prod_name = prod.get("name", "").lower()
            if prod_name and len(prod_name) > 3 and prod_name in assistant_msg.lower():
                facts.append("PRODUCT_EXPLAINED")
                break
    # ES + CA + EN + IT objection handling
    if re.search(
        r"entiendo tu (duda|preocupación)|es normal|no te preocupes|garantía|devolución"
        r"|I understand your concern|don't worry|garanzia|non preoccuparti"
        r"|entenc el teu dubte|no et preocupis",
        assistant_msg, re.IGNORECASE,
    ):
        facts.append("OBJECTION_RAISED")
    # ES + CA + EN + IT interest signals
    if re.search(
        r"me interesa|quiero saber|cuéntame|suena bien|me gusta"
        r"|I'm interested|tell me more|sounds good|I like"
        r"|m'interessa|vull saber|explica'm|mi interessa|voglio sapere",
        user_msg, re.IGNORECASE,
    ):
        facts.append("INTEREST_EXPRESSED")
    if re.search(
        r"reserva|agenda|cita|llamada|reunión|calendly|cal\.com"
        r"|booking|appointment|meeting|call|prenotazione|appuntamento",
        assistant_msg, re.IGNORECASE,
    ):
        facts.append("APPOINTMENT_MENTIONED")
    if re.search(
        r"@\w{3,}|[\w.-]+@[\w.-]+\.\w+|\+?\d{9,}|wa\.me|whatsapp",
        assistant_msg, re.IGNORECASE,
    ):
        facts.append("CONTACT_SHARED")
    if "?" in assistant_msg:
        facts.append("QUESTION_ASKED")
    if follower_name and len(follower_name) > 2 and follower_name.lower() in assistant_msg.lower():
        facts.append("NAME_USED")
    return facts

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
    except Exception as e:
        logger.debug(f"[POST_RESPONSE] copilot check failed: {e}")

    if not is_copilot:
        follower.last_messages.append(
            {"role": "assistant", "content": formatted_content, "timestamp": now}
        )
    follower.last_messages = follower.last_messages[-20:]
    follower.total_messages += 1
    follower.last_contact = now

    # BUG-EP-04 fix: Use shared _extract_facts() instead of inline duplicate
    if ENABLE_FACT_TRACKING:
        try:
            facts = _extract_facts(formatted_content, message, agent.products or [], follower.name)
            if facts:
                follower.last_messages[-1]["facts"] = facts
        except Exception as e:
            logger.debug(f"Fact tracking failed: {e}")

    # BUG-UC-02 fix: Persist detected user name from context_signals
    try:
        _ctx_sigs = cognitive_metadata.get("context_signals", {})
        _detected_name = _ctx_sigs.get("user_name", "")
        if _detected_name and not follower.name:
            follower.name = _detected_name
            logger.info(f"[UC-FIX] Persisted detected name '{_detected_name}' for {sender_id}")
    except Exception as e:
        logger.debug(f"Name persistence failed: {e}")

    # BUG-UC-01 fix: Detect and persist lead's language.
    # Only update when stored language is still the default "es" to avoid
    # overwriting a confirmed non-ES language with a false "es" detection
    # on short/ambiguous messages (reviewer Issue 3).
    try:
        _current_lang = getattr(follower, "preferred_language", "es") or "es"
        if _current_lang == "es" and len(message.strip()) >= 10:
            from core.i18n import detect_language as _detect_lang
            _detected_lang = _detect_lang(message)
            if _detected_lang and _detected_lang != "es" and _detected_lang != "unknown":
                follower.preferred_language = _detected_lang
                logger.info(f"[UC-FIX] Updated language to '{_detected_lang}' for {sender_id}")
    except Exception as e:
        logger.debug(f"Language detection failed: {e}")

    # BUG-EP-01 fix: Index messages into conversation_embeddings for episodic search.
    # Without this, _episodic_search() finds nothing for Instagram leads.
    if os.getenv("ENABLE_SEMANTIC_MEMORY_PGVECTOR", "true").lower() == "true":
        try:
            from core.semantic_memory_pgvector import get_semantic_memory
            sm = get_semantic_memory(agent.creator_id, sender_id)
            sm.add_message("user", message)
            if not is_copilot:
                sm.add_message("assistant", formatted_content)
        except Exception as e:
            logger.debug(f"[EPISODIC] Embedding indexing failed: {e}")

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

    # BUG-EP-04 fix: Use shared _extract_facts() instead of inline duplicate
    if ENABLE_FACT_TRACKING:
        try:
            facts = _extract_facts(
                assistant_message, user_message, agent.products or [],
                getattr(follower, "name", None),
            )
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


def check_response_loop(current_response: str, last_responses: list) -> bool:
    """
    Check if current_response is too similar to recent past responses (loop detection).

    Uses first-50-chars comparison for exact match, and word overlap for fuzzy.

    Args:
        current_response: The response being evaluated
        last_responses: List of previous bot responses

    Returns:
        True if a loop is detected, False otherwise
    """
    if not current_response or not last_responses:
        return False

    current_prefix = current_response[:50].strip().lower()

    for prev in last_responses:
        if not prev:
            continue
        prev_prefix = prev[:50].strip().lower()

        # Exact prefix match (first 50 chars)
        if current_prefix and prev_prefix and current_prefix == prev_prefix:
            return True

        # High word overlap
        current_words = set(re.findall(r'\b\w{4,}\b', current_response.lower()))
        prev_words = set(re.findall(r'\b\w{4,}\b', prev.lower()))
        if current_words and prev_words:
            overlap = len(current_words & prev_words) / max(len(current_words), 1)
            if overlap > 0.8:
                return True

    return False
