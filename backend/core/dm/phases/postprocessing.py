"""Phase 5: Post-processing — guardrails, validation, formatting, scoring."""

import asyncio
import logging
import os
import re
import time
from typing import Dict

from core.agent_config import AGENT_THRESHOLDS
from core.dm.models import ContextBundle, DetectionResult, DMResponse
from core.dm.text_utils import _message_mentions_product
from core.output_validator import validate_links, validate_prices
from core.reflexion_engine import get_reflexion_engine
from core.response_fixes import apply_all_response_fixes
from services import LLMResponse
from services.length_controller import detect_message_type, enforce_length
from services.message_splitter import get_message_splitter
from services.question_remover import process_questions

logger = logging.getLogger(__name__)

# Feature flags for postprocessing phase
ENABLE_OUTPUT_VALIDATION = os.getenv("ENABLE_OUTPUT_VALIDATION", "true").lower() == "true"
ENABLE_RESPONSE_FIXES = os.getenv("ENABLE_RESPONSE_FIXES", "true").lower() == "true"
ENABLE_QUESTION_REMOVAL = os.getenv("ENABLE_QUESTION_REMOVAL", "true").lower() == "true"
ENABLE_REFLEXION = os.getenv("ENABLE_REFLEXION", "true").lower() == "true"
ENABLE_PPA = os.getenv("ENABLE_PPA", "false").lower() == "true"
ENABLE_SCORE_BEFORE_SPEAK = os.getenv("ENABLE_SCORE_BEFORE_SPEAK", "false").lower() == "true"
ENABLE_GUARDRAILS = os.getenv("ENABLE_GUARDRAILS", "true").lower() == "true"
ENABLE_EMAIL_CAPTURE = os.getenv("ENABLE_EMAIL_CAPTURE", "false").lower() == "true"
ENABLE_MESSAGE_SPLITTING = os.getenv("ENABLE_MESSAGE_SPLITTING", "true").lower() == "true"


async def phase_postprocessing(
    agent, message: str, sender_id: str, metadata: Dict,
    llm_response: LLMResponse, context: ContextBundle,
    detection: DetectionResult, cognitive_metadata: Dict,
) -> DMResponse:
    """Phase 5: Guardrails, validation, formatting, scoring."""
    _t3 = time.monotonic()
    # Alias context fields for code compatibility
    intent_value = context.intent_value
    follower = context.follower
    history = context.history
    rag_results = context.rag_results

    response_content = llm_response.content

    # A2 FIX: Detect and break repetitive loops
    # Only compare against the immediately previous bot message using full-string
    # equality to avoid false positives from responses with similar openings.
    try:
        last_bot_msgs = [
            m["content"] for m in history
            if m.get("role") == "assistant" and m.get("content")
        ][-1:]
        if last_bot_msgs and response_content:
            resp_norm = response_content.strip().lower()
            prev_norm = last_bot_msgs[0].strip().lower()
            if resp_norm and prev_norm and resp_norm == prev_norm:
                logger.warning(
                    "[A2] Repetitive loop detected — response is exact duplicate of last message"
                )
                cognitive_metadata["loop_detected"] = True
                response_content = "Cuéntame más"
                llm_response.content = response_content
    except Exception as e:
        logger.debug(f"Loop detection failed: {e}")

    # A2b: Detect intra-response repetition anywhere in the string
    # (e.g. "Que vagi be germana JAJAJAJAJAJAJAJA..." — loop starts mid-response)
    # Only trigger on longer responses (> 50 chars) to avoid chopping natural
    # short expressions like "jajajaja" (8 chars) or "dale dale" (9 chars).
    try:
        if response_content and len(response_content) > 50:
            _resp_lower = response_content.lower()
            _match = re.search(r'(.{2,8})\1{4,}', _resp_lower)
            if _match:
                _pat = _match.group(1)
                _count = _resp_lower.count(_pat)
                _coverage = (_count * len(_pat)) / len(_resp_lower)
                if _coverage > 0.5 and _count > 5:
                    # Keep prefix before the loop + one clean occurrence (not * 3,
                    # which itself looks like a repetition loop to readers).
                    _prefix = response_content[:_match.start()]
                    _pat_orig = response_content[_match.start():_match.start() + len(_pat)]
                    response_content = _prefix + _pat_orig
                    logger.warning(
                        f"[A2b] Intra-response repetition: "
                        f"'{_pat}' covers {_coverage:.0%} of response ({_count}x) — truncated"
                    )
                    cognitive_metadata["repetition_truncated"] = _pat
                    llm_response.content = response_content
    except Exception as e:
        logger.debug(f"Intra-response repetition detection failed: {e}")

    # Step 7a: Output validation (prices, links)
    if ENABLE_OUTPUT_VALIDATION:
        try:
            # Build known prices from products
            known_prices = {
                p.get("name", ""): p.get("price", 0)
                for p in agent.products
                if p.get("price")
            }
            price_issues = validate_prices(response_content, known_prices)
            if price_issues:
                logger.warning(f"Output validation: {len(price_issues)} price issues")
                cognitive_metadata["output_validation_issues"] = [
                    i.details for i in price_issues
                ]
            # Build known links from products
            known_links = [p.get("url", "") for p in agent.products if p.get("url")]
            link_issues, corrected = validate_links(response_content, known_links)
            if link_issues:
                logger.warning(f"Output validation: {len(link_issues)} link issues")
                response_content = corrected  # Apply corrections
        except Exception as e:
            logger.debug(f"Output validation failed: {e}")

    # Step 7a2: Apply response fixes (typos, formatting, patterns)
    if ENABLE_RESPONSE_FIXES:
        try:
            fixed_response = apply_all_response_fixes(
                response_content, creator_id=agent.creator_id,
            )
            if fixed_response and fixed_response != response_content:
                logger.debug("Response fixes applied")
                response_content = fixed_response
        except Exception as e:
            logger.debug(f"Response fixes failed: {e}")

    # Step 7a2b: Tone enforcement (emoji/excl/question rates from calibration)
    if agent.calibration:
        try:
            from services.tone_enforcer import enforce_tone

            response_content = enforce_tone(
                response_content, agent.calibration,
                sender_id=sender_id, message=message,
            )
        except Exception as e:
            logger.debug(f"Tone enforcement failed: {e}")

    # Step 7a2c: Question removal
    if ENABLE_QUESTION_REMOVAL:
        try:
            response_content = process_questions(response_content, message)
        except Exception as e:
            logger.debug(f"Question removal failed: {e}")

    # Step 7a3: Reflexion analysis for response quality (legacy)
    if ENABLE_REFLEXION:
        try:
            prev_bot = [
                m.get("content", "")
                for m in metadata.get("history", [])
                if m.get("role") == "assistant"
            ]
            r_result = get_reflexion_engine().analyze_response(
                response=response_content,
                user_message=message,
                previous_bot_responses=prev_bot[-5:],
            )
            if r_result.needs_revision:
                cognitive_metadata["reflexion_issues"] = r_result.issues
                cognitive_metadata["reflexion_severity"] = r_result.severity
        except Exception as e:
            logger.debug(f"Reflexion failed: {e}")

    # Step 7a4: Score Before You Speak (supersedes PPA when enabled)
    if ENABLE_SCORE_BEFORE_SPEAK and agent.calibration:
        try:
            from core.reasoning.ppa import score_before_speak

            follower_name = (follower or {}).get("full_name", "") or (follower or {}).get("username", "")
            sbs_result = await score_before_speak(
                response=response_content,
                calibration=agent.calibration,
                system_prompt=context.system_prompt,
                user_prompt=metadata.get("_full_prompt", ""),
                lead_name=follower_name,
                detected_language=detection.language if hasattr(detection, "language") else "ca",
                creator_id=agent.creator_id,
                creator_name=getattr(agent, "creator_name", ""),
            )
            cognitive_metadata["sbs_score"] = round(sbs_result.alignment_score, 2)
            cognitive_metadata["sbs_scores"] = sbs_result.scores
            cognitive_metadata["sbs_path"] = sbs_result.path
            cognitive_metadata["sbs_llm_calls"] = sbs_result.total_llm_calls
            if sbs_result.path != "pass":
                response_content = sbs_result.response
                logger.info(
                    "[SBS] path=%s score=%.2f calls=%d",
                    sbs_result.path, sbs_result.alignment_score, sbs_result.total_llm_calls,
                )
        except Exception as e:
            logger.debug(f"Score Before You Speak failed: {e}")

    # Step 7a4b: Post Persona Alignment (PPA) — fallback when SBS is disabled
    elif ENABLE_PPA and agent.calibration:
        try:
            from core.reasoning.ppa import apply_ppa

            follower_name = (follower or {}).get("full_name", "") or (follower or {}).get("username", "")
            ppa_result = await apply_ppa(
                response=response_content,
                calibration=agent.calibration,
                lead_name=follower_name,
                detected_language=detection.language if hasattr(detection, "language") else "ca",
                creator_id=agent.creator_id,
                creator_name=getattr(agent, "creator_name", ""),
            )
            cognitive_metadata["ppa_score"] = round(ppa_result.alignment_score, 2)
            cognitive_metadata["ppa_scores"] = ppa_result.scores
            if ppa_result.was_refined:
                response_content = ppa_result.response
                cognitive_metadata["ppa_refined"] = True
                logger.info("[PPA] Response refined (score=%.2f)", ppa_result.alignment_score)
        except Exception as e:
            logger.debug(f"PPA failed: {e}")

    # Step 7b: Apply guardrails validation
    if ENABLE_GUARDRAILS and hasattr(agent, "guardrails"):
        try:
            # Build allowed URLs from creator's products and booking links
            creator_urls = []
            for p in agent.products:
                url = p.get("url", "")
                if url:
                    creator_urls.append(url)
            # Extract unique domains from product URLs for whitelist
            creator_domains = set()
            for u in creator_urls:
                # Extract domain: "https://www.example.com/path" -> "example.com"
                try:
                    domain = u.split("//")[-1].split("/")[0].replace("www.", "")
                    creator_domains.add(domain)
                except Exception as e:
                    logger.warning(f"Failed to parse URL domain '{u}': {e}")
            guardrail_result = agent.guardrails.validate_response(
                query=message,
                response=response_content,
                context={
                    "products": agent.products,
                    "allowed_urls": list(creator_domains),
                },
            )
            if not guardrail_result.get("valid", True):
                logger.warning(f"Guardrail triggered: {guardrail_result.get('reason')}")
                if guardrail_result.get("corrected_response"):
                    response_content = guardrail_result["corrected_response"]
                cognitive_metadata["guardrail_triggered"] = guardrail_result.get("reason")
        except Exception as e:
            logger.debug(f"Guardrails check failed: {e}")

    # Step 7b: Apply soft length guidance based on message type
    try:
        msg_type = detect_message_type(message)
        response_content = enforce_length(response_content, message, creator_id=agent.creator_id)
        cognitive_metadata["message_type"] = msg_type
    except Exception as e:
        logger.debug(f"Length control failed: {e}")

    # Step 7c: Format response for Instagram
    formatted_content = agent.instagram_service.format_message(response_content)

    # Step 7d: Inject payment link for purchase_intent if missing
    if intent_value.lower() in ("purchase_intent", "want_to_buy") and agent.products:
        msg_lower = message.lower()
        resp_lower = formatted_content.lower()
        for p in agent.products:
            pname = p.get("name") or ""
            plink = p.get("payment_link") or p.get("url") or ""
            # Match product in user message OR bot response
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

    # CloneScore real-time logging (non-blocking, CPU-only style_fidelity)
    if os.getenv("ENABLE_CLONE_SCORE", "false").lower() == "true":
        try:
            from services.clone_score_engine import CloneScoreEngine
            cs_engine = CloneScoreEngine()
            score_result = await cs_engine.evaluate_single(
                agent.creator_id, message, formatted_content, {}
            )
            cognitive_metadata["clone_score"] = score_result.get("overall_score", 0)
            _style = score_result.get("dimension_scores", {}).get("style_fidelity", 0)
            logger.info(f"[CLONE_SCORE] style={_style:.1f}")
        except Exception as e:
            logger.debug(f"[CLONE_SCORE] eval failed: {e}")

    # Step 9: Update lead score (synchronous - needed for response)
    new_stage = agent._update_lead_score(follower, intent_value, metadata)

    # Step 9a: Update conversation state machine (fire-and-forget)
    try:
        from core.conversation_state import get_state_manager

        state_mgr = get_state_manager()
        conv_state = state_mgr.get_state(sender_id, agent.creator_id)
        state_mgr.update_state(conv_state, message, intent_value, formatted_content)
    except Exception as e:
        logger.debug(f"[STATE] update failed: {e}")

    # Step 9c: Email capture (non-blocking) — disabled by default
    if ENABLE_EMAIL_CAPTURE:
        try:
            formatted_content = agent._step_email_capture(
                message=message,
                formatted_content=formatted_content,
                intent_value=intent_value,
                sender_id=sender_id,
                follower=follower,
                platform=metadata.get("platform", "instagram"),
                cognitive_metadata=cognitive_metadata,
            )
        except Exception as e:
            logger.warning(f"Email capture step failed (non-blocking): {e}")

    # Steps 8, 8b, 9b: Run in background thread (non-blocking)
    asyncio.create_task(
        agent._background_post_response(
            follower=follower,
            message=message,
            formatted_content=formatted_content,
            intent_value=intent_value,
            sender_id=sender_id,
            metadata=metadata,
            cognitive_metadata=cognitive_metadata,
        )
    )

    # Memory extraction (extract facts from conversation — fire-and-forget)
    if os.getenv("ENABLE_MEMORY_ENGINE", "false").lower() == "true":
        try:
            from services.memory_engine import get_memory_engine
            mem_engine = get_memory_engine()
            conversation_msgs = [
                {"role": "user", "content": message},
                {"role": "assistant", "content": formatted_content},
            ]
            asyncio.create_task(
                mem_engine.add(agent.creator_id, sender_id, conversation_msgs)
            )
        except Exception as e:
            logger.debug(f"[MEMORY] extraction failed: {e}")

    # ECHO Engine: Detect commitments in bot response (Sprint 4 — fire-and-forget)
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

    # Step 10: Escalation notification (async, lightweight)
    asyncio.create_task(
        agent._check_and_notify_escalation(
            intent_value=intent_value,
            follower=follower,
            sender_id=sender_id,
            message=message,
            metadata=metadata,
        )
    )

    # Step 10b: Message splitting (store in metadata for caller)
    message_parts = None
    if ENABLE_MESSAGE_SPLITTING:
        try:
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
    # A4: Include model/provider/latency in metadata for auditing
    llm_meta = llm_response.metadata or {}

    # Confidence scoring (multi-factor)
    try:
        from core.confidence_scorer import calculate_confidence
        scored_confidence = calculate_confidence(
            intent=intent_value,
            response_text=formatted_content,
            response_type="llm_generation",
            creator_id=agent.creator_id,
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
