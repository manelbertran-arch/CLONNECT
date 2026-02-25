"""
DM Agent Phase 5: Post-processing.

Handles guardrails, validation, formatting, scoring,
background tasks, email capture, and escalation.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict

from core.agent_config import AGENT_THRESHOLDS
from core.dm.helpers import _message_mentions_product
from core.dm.public_api import _step_email_capture
from core.dm.models import (
    ContextBundle,
    DMResponse,
    DetectionResult,
    ENABLE_EMAIL_CAPTURE,
    ENABLE_FACT_TRACKING,
    ENABLE_GUARDRAILS,
    ENABLE_MESSAGE_SPLITTING,
    ENABLE_OUTPUT_VALIDATION,
    ENABLE_QUESTION_REMOVAL,
    ENABLE_REFLEXION,
    ENABLE_RESPONSE_FIXES,
    ENABLE_DNA_TRIGGERS,
)
from services import LeadStage, LLMResponse

if TYPE_CHECKING:
    from core.dm.agent import DMResponderAgentV2

logger = logging.getLogger(__name__)


async def phase_postprocessing(
    agent: "DMResponderAgentV2",
    message: str,
    sender_id: str,
    metadata: Dict,
    llm_response: LLMResponse,
    context: ContextBundle,
    detection: DetectionResult,
    cognitive_metadata: Dict,
) -> DMResponse:
    """Phase 5: Guardrails, validation, formatting, scoring."""
    _t3 = time.monotonic()
    intent_value = context.intent_value
    follower = context.follower
    history = context.history
    rag_results = context.rag_results

    response_content = llm_response.content

    # A2 FIX: Detect and break repetitive loops
    try:
        recent_bot_msgs = [
            m["content"] for m in history
            if m.get("role") == "assistant" and m.get("content")
        ][-3:]
        if recent_bot_msgs and response_content:
            resp_norm = response_content.strip().lower()[:50]
            for prev in recent_bot_msgs:
                prev_norm = prev.strip().lower()[:50]
                if resp_norm and prev_norm and resp_norm == prev_norm:
                    logger.warning("[A2] Repetitive loop detected — response matches recent message")
                    cognitive_metadata["loop_detected"] = True
                    response_content = "Contame más"
                    llm_response.content = response_content
                    break
    except Exception as e:
        logger.debug(f"Loop detection failed: {e}")

    # Step 7a: Output validation (prices, links)
    if ENABLE_OUTPUT_VALIDATION:
        try:
            from core.output_validator import validate_links, validate_prices

            known_prices = {p.get("name", ""): p.get("price", 0) for p in agent.products if p.get("price")}
            price_issues = validate_prices(response_content, known_prices)
            if price_issues:
                logger.warning(f"Output validation: {len(price_issues)} price issues")
                cognitive_metadata["output_validation_issues"] = [i.details for i in price_issues]
            known_links = [p.get("url", "") for p in agent.products if p.get("url")]
            link_issues, corrected = validate_links(response_content, known_links)
            if link_issues:
                logger.warning(f"Output validation: {len(link_issues)} link issues")
                response_content = corrected
        except Exception as e:
            logger.debug(f"Output validation failed: {e}")

    # Step 7a2: Apply response fixes
    if ENABLE_RESPONSE_FIXES:
        try:
            from core.response_fixes import apply_all_response_fixes

            fixed_response = apply_all_response_fixes(response_content, creator_id=agent.creator_id)
            if fixed_response and fixed_response != response_content:
                logger.debug("Response fixes applied")
                response_content = fixed_response
        except Exception as e:
            logger.debug(f"Response fixes failed: {e}")

    # Step 7a2b: Tone enforcement
    if agent.calibration:
        try:
            from services.tone_enforcer import enforce_tone

            response_content = enforce_tone(response_content, agent.calibration, sender_id=sender_id, message=message)
        except Exception as e:
            logger.debug(f"Tone enforcement failed: {e}")

    # Step 7a2c: Question removal
    if ENABLE_QUESTION_REMOVAL:
        try:
            from services.question_remover import process_questions

            response_content = process_questions(response_content, message)
        except Exception as e:
            logger.debug(f"Question removal failed: {e}")

    # Step 7a3: Reflexion analysis
    if ENABLE_REFLEXION:
        try:
            from core.reflexion_engine import get_reflexion_engine

            prev_bot = [m.get("content", "") for m in metadata.get("history", []) if m.get("role") == "assistant"]
            r_result = get_reflexion_engine().analyze_response(
                response=response_content, user_message=message, previous_bot_responses=prev_bot[-5:],
            )
            if r_result.needs_revision:
                cognitive_metadata["reflexion_issues"] = r_result.issues
                cognitive_metadata["reflexion_severity"] = r_result.severity
        except Exception as e:
            logger.debug(f"Reflexion failed: {e}")

    # Step 7b: Apply guardrails validation
    if ENABLE_GUARDRAILS and hasattr(agent, "guardrails"):
        try:
            creator_urls = [p.get("url", "") for p in agent.products if p.get("url")]
            creator_domains = set()
            for u in creator_urls:
                try:
                    domain = u.split("//")[-1].split("/")[0].replace("www.", "")
                    creator_domains.add(domain)
                except Exception:
                    pass
            guardrail_result = agent.guardrails.validate_response(
                query=message, response=response_content,
                context={"products": agent.products, "allowed_urls": list(creator_domains)},
            )
            if not guardrail_result.get("valid", True):
                logger.warning(f"Guardrail triggered: {guardrail_result.get('reason')}")
                if guardrail_result.get("corrected_response"):
                    response_content = guardrail_result["corrected_response"]
                cognitive_metadata["guardrail_triggered"] = guardrail_result.get("reason")
        except Exception as e:
            logger.debug(f"Guardrails check failed: {e}")

    # Step 7b: Length guidance
    try:
        from services.length_controller import detect_message_type, enforce_length

        msg_type = detect_message_type(message)
        response_content = enforce_length(response_content, message)
        cognitive_metadata["message_type"] = msg_type
    except Exception as e:
        logger.debug(f"Length control failed: {e}")

    # Step 7c: Format response for Instagram
    formatted_content = agent.instagram_service.format_message(response_content)

    # Step 7d: Inject payment link for purchase_intent
    if intent_value.lower() in ("purchase_intent", "want_to_buy") and agent.products:
        msg_lower = message.lower()
        resp_lower = formatted_content.lower()
        for p in agent.products:
            pname = p.get("name") or ""
            plink = p.get("payment_link") or p.get("url") or ""
            mentioned = (
                _message_mentions_product(pname, msg_lower)
                or _message_mentions_product(pname, resp_lower)
            )
            if pname and mentioned and plink and plink not in resp_lower:
                formatted_content = f"{formatted_content}\n\n{plink}"
                cognitive_metadata["payment_link_injected"] = plink
                logger.info(f"[Step 7d] Injected payment link for '{pname}': {plink}")
                break

    _t4 = time.monotonic()
    logger.info(f"[TIMING] Phase 5 (post-processing): {int((_t4 - _t3) * 1000)}ms")

    # CloneScore real-time logging
    if os.getenv("ENABLE_CLONE_SCORE", "false").lower() == "true":
        try:
            from services.clone_score_engine import CloneScoreEngine

            cs_engine = CloneScoreEngine()
            score_result = await cs_engine.evaluate_single(agent.creator_id, message, formatted_content, {})
            cognitive_metadata["clone_score"] = score_result.get("overall_score", 0)
            _style = score_result.get("dimension_scores", {}).get("style_fidelity", 0)
            logger.info(f"[CLONE_SCORE] style={_style:.1f}")
        except Exception as e:
            logger.debug(f"[CLONE_SCORE] eval failed: {e}")

    # Step 9: Update lead score
    new_stage = _update_lead_score(agent, follower, intent_value, metadata)

    # Step 9c: Email capture
    if ENABLE_EMAIL_CAPTURE:
        try:
            formatted_content = _step_email_capture(
                agent, message=message, formatted_content=formatted_content,
                intent_value=intent_value, sender_id=sender_id,
                follower=follower, platform=metadata.get("platform", "instagram"),
                cognitive_metadata=cognitive_metadata,
            )
        except Exception as e:
            logger.warning(f"Email capture step failed (non-blocking): {e}")

    # Steps 8, 8b, 9b: Background tasks
    asyncio.create_task(
        _background_post_response(
            agent, follower=follower, message=message,
            formatted_content=formatted_content, intent_value=intent_value,
            sender_id=sender_id, metadata=metadata,
            cognitive_metadata=cognitive_metadata,
        )
    )

    # Memory extraction (fire-and-forget)
    if os.getenv("ENABLE_MEMORY_ENGINE", "false").lower() == "true":
        try:
            from services.memory_engine import get_memory_engine

            mem_engine = get_memory_engine()
            conversation_msgs = [
                {"role": "user", "content": message},
                {"role": "assistant", "content": formatted_content},
            ]
            asyncio.create_task(mem_engine.add(agent.creator_id, sender_id, conversation_msgs))
        except Exception as e:
            logger.debug(f"[MEMORY] extraction failed: {e}")

    # Commitment detection (fire-and-forget)
    if os.getenv("ENABLE_COMMITMENT_TRACKING", "true").lower() == "true":
        try:
            from services.commitment_tracker import get_commitment_tracker

            async def _detect_commitments():
                try:
                    tracker = get_commitment_tracker()
                    tracker.detect_and_store(
                        response_text=formatted_content,
                        creator_id=agent.creator_id,
                        lead_id=sender_id,
                    )
                except Exception as e:
                    logger.debug(f"[COMMITMENT] detection failed: {e}")

            asyncio.create_task(_detect_commitments())
        except Exception as e:
            logger.debug(f"[COMMITMENT] setup failed: {e}")

    # Escalation notification
    from core.dm.agent import _check_and_notify_escalation

    asyncio.create_task(
        _check_and_notify_escalation(
            agent, intent_value=intent_value, follower=follower,
            sender_id=sender_id, message=message, metadata=metadata,
        )
    )

    # Message splitting
    message_parts = None
    if ENABLE_MESSAGE_SPLITTING:
        try:
            from services.message_splitter import get_message_splitter

            splitter = get_message_splitter()
            if splitter.should_split(formatted_content):
                parts = splitter.split(formatted_content, message)
                message_parts = [{"text": p.text, "delay": p.delay_before} for p in parts]
                logger.debug(f"Message split into {len(parts)} parts")
        except Exception as e:
            logger.debug(f"Message splitting failed: {e}")

    _t5 = time.monotonic()
    logger.info(
        f"[TIMING] Phase 5 (post+mem+nurture): {int((_t5 - _t3) * 1000)}ms "
        f"(guardrails={int((_t4 - _t3) * 1000)} async={int((_t5 - _t4) * 1000)})"
    )

    llm_meta = llm_response.metadata or {}

    # Confidence scoring
    try:
        from core.confidence_scorer import calculate_confidence

        scored_confidence = calculate_confidence(
            intent=intent_value, response_text=formatted_content,
            response_type="llm_generation", creator_id=agent.creator_id,
        )
    except Exception:
        scored_confidence = AGENT_THRESHOLDS.default_scored_confidence

    _dm_metadata = {
        "model": llm_response.model,
        "provider": llm_meta.get("provider", "unknown"),
        "latency_ms": llm_meta.get("latency_ms", 0),
        "rag_results": len(rag_results),
        "history_length": len(history),
        "follower_id": sender_id,
        "message_parts": message_parts,
    }
    if cognitive_metadata.get("best_of_n"):
        _dm_metadata["best_of_n"] = cognitive_metadata["best_of_n"]

    return DMResponse(
        content=formatted_content,
        intent=intent_value,
        lead_stage=new_stage.value if hasattr(new_stage, "value") else str(new_stage),
        confidence=scored_confidence,
        tokens_used=llm_response.tokens_used,
        metadata=_dm_metadata,
    )


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _update_lead_score(agent, follower, intent: str, metadata: Dict) -> LeadStage:
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


async def _background_post_response(agent, follower, message, formatted_content,
                                     intent_value, sender_id, metadata, cognitive_metadata) -> None:
    """Run memory save, nurturing, DNA triggers in background thread."""
    try:
        await asyncio.to_thread(
            _sync_post_response, agent, follower, message, formatted_content,
            intent_value, sender_id, metadata, cognitive_metadata,
        )
        logger.debug(f"[BACKGROUND] Post-response tasks completed for {sender_id}")
    except Exception as e:
        logger.error(f"[BACKGROUND] Post-response tasks failed: {e}", exc_info=True)


def _sync_post_response(agent, follower, message, formatted_content,
                         intent_value, sender_id, metadata, cognitive_metadata) -> None:
    """Synchronous post-response tasks (runs in thread pool)."""
    now = datetime.now(timezone.utc).isoformat()
    follower.last_messages.append({"role": "user", "content": message, "timestamp": now})

    is_copilot = False
    try:
        from core.copilot_service import get_copilot_service

        is_copilot = get_copilot_service().is_copilot_enabled(agent.creator_id)
    except Exception:
        pass

    if not is_copilot:
        follower.last_messages.append({"role": "assistant", "content": formatted_content, "timestamp": now})
    follower.last_messages = follower.last_messages[-20:]
    follower.total_messages += 1
    follower.last_contact = now

    # Fact tracking
    if ENABLE_FACT_TRACKING:
        from core.dm.helpers import track_facts
        track_facts(follower, message, formatted_content, agent.products)

    try:
        agent.memory_store._save_to_json(follower)
    except Exception as e:
        logger.debug(f"Memory save failed: {e}")

    # DNA update triggers
    if ENABLE_DNA_TRIGGERS:
        try:
            from services.dna_update_triggers import get_dna_triggers

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

    # Auto-schedule nurturing
    try:
        from core.nurturing import should_schedule_nurturing, get_nurturing_manager

        sequence_type = should_schedule_nurturing(
            intent=intent_value, has_purchased=follower.is_customer, creator_id=agent.creator_id,
        )
        if sequence_type:
            manager = get_nurturing_manager()
            followups = manager.schedule_followup(
                creator_id=agent.creator_id, follower_id=sender_id,
                sequence_type=sequence_type, product_name="",
            )
            if followups:
                logger.info(
                    f"[NURTURING] Auto-scheduled {len(followups)} followups "
                    f"(type={sequence_type}) for {sender_id}"
                )
                cognitive_metadata["nurturing_scheduled"] = sequence_type
    except Exception as e:
        logger.error(f"[NURTURING] Auto-trigger failed: {e}")
