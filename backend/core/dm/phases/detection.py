"""Phase 1: Detection — sensitive content, frustration, pool response, edge cases."""

import logging
import os
from typing import Dict

from core.agent_config import AGENT_THRESHOLDS
from core.context_detector import detect_all as detect_context
from core.dm.models import DMResponse, DetectionResult
from core.dm.text_utils import _message_mentions_product
from core.sensitive_detector import detect_sensitive_content, get_crisis_resources

logger = logging.getLogger(__name__)

# Platform placeholders sent instead of actual media content
MEDIA_PLACEHOLDERS = {
    "sent an attachment",
    "sent a photo",
    "sent a video",
    "shared a reel",
    "shared a story",
    "sent a voice message",
    "[image]", "[video]", "[sticker]",
    "[🏷️ sticker]",
    "[audio]",
    "[🎤 audio]",
    "[🎤 audio message]",
    "envió un archivo adjunto",
    "envió una foto",
    "envió un video",
    "compartió un reel",
    "compartió una historia",
}

# Feature flags for detection phase
ENABLE_SENSITIVE_DETECTION = os.getenv("ENABLE_SENSITIVE_DETECTION", "true").lower() == "true"
ENABLE_FRUSTRATION_DETECTION = os.getenv("ENABLE_FRUSTRATION_DETECTION", "true").lower() == "true"
ENABLE_CONTEXT_DETECTION = os.getenv("ENABLE_CONTEXT_DETECTION", "true").lower() == "true"
ENABLE_EDGE_CASE_DETECTION = os.getenv("ENABLE_EDGE_CASE_DETECTION", "true").lower() == "true"


async def phase_detection(
    agent, message: str, sender_id: str, metadata: Dict, cognitive_metadata: Dict
) -> DetectionResult:
    """Phase 1: Sensitive content, frustration, pool response, edge cases."""
    result = DetectionResult()

    # PRE-PIPELINE: Media placeholder detection
    # Instagram/WhatsApp send placeholder text like "Sent an attachment" instead of
    # actual content. Flag it so the LLM reacts naturally instead of asking "what?".
    msg_stripped = message.strip().lower().rstrip(".")
    if msg_stripped in MEDIA_PLACEHOLDERS:
        metadata["is_media_placeholder"] = True
        cognitive_metadata["intent_override"] = "media_share"  # NOTE: written, not consumed downstream
        logger.info("Media placeholder detected: %s", message.strip())

    # PRE-PIPELINE: SENSITIVE CONTENT DETECTION (Security)
    if ENABLE_SENSITIVE_DETECTION:
        try:
            sensitive_result = detect_sensitive_content(message)
            if sensitive_result and sensitive_result.confidence >= AGENT_THRESHOLDS.sensitive_confidence:
                logger.warning(f"Sensitive content detected: {sensitive_result.type.value}")
                cognitive_metadata["sensitive_detected"] = True
                cognitive_metadata["sensitive_category"] = sensitive_result.type.value
                if sensitive_result.confidence >= AGENT_THRESHOLDS.sensitive_escalation:
                    crisis_response = get_crisis_resources(language="es")
                    result.pool_response = DMResponse(
                        content=crisis_response,
                        intent="sensitive_content",
                        lead_stage="unknown",
                        confidence=sensitive_result.confidence,
                        tokens_used=0,
                        metadata={"sensitive_category": sensitive_result.type.value},
                    )
                    return result
        except Exception as e:
            # FAIL-CLOSED: if we can't verify it's NOT a crisis, escalate to human
            logger.error(f"CRITICAL: Sensitive detection failed, escalating by default: {e}")
            creator_name = getattr(agent, "creator_id", "el creador")
            result.pool_response = DMResponse(
                content=(
                    f"Ahora mismo no puedo responderte bien. "
                    f"Le paso tu mensaje a {creator_name} directamente 🙏"
                ),
                intent="sensitive_detection_failure",
                lead_stage="unknown",
                confidence=1.0,
                tokens_used=0,
                metadata={"sensitive_failsafe": True, "error": str(e)},
            )
            return result

    # Step 1a: Detect frustration level
    if ENABLE_FRUSTRATION_DETECTION and hasattr(agent, "frustration_detector"):
        try:
            history = metadata.get("history", [])
            prev_messages = [
                m.get("content", "") for m in history if m.get("role") == "user"
            ]
            result.frustration_signals, result.frustration_level = (
                agent.frustration_detector.analyze_message(message, sender_id, prev_messages)
            )
            if result.frustration_level > 0.3:
                logger.info(f"Frustration detected: {result.frustration_level:.2f}")
                cognitive_metadata["frustration_level"] = result.frustration_level
        except Exception as e:
            logger.debug(f"Frustration detection failed: {e}")

    # Step 1b: Detect context signals (sarcasm, B2B, etc.)
    # NOTE: context_signals stored on result but not consumed in generation phase
    if ENABLE_CONTEXT_DETECTION:
        try:
            history = metadata.get("history", [])
            result.context_signals = detect_context(message, history)
            if result.context_signals and result.context_signals.alerts:
                cognitive_metadata["context_signals"] = result.context_signals.to_dict()
        except Exception as e:
            logger.debug(f"Context detection failed: {e}")

    # Step 1c: Try pool response for simple messages (fast path)
    if hasattr(agent, "response_variator"):
        msg_lower = message.lower()
        mentions_product = False
        if agent.products:
            for p in agent.products:
                pname = p.get("name") or ""
                if pname and _message_mentions_product(pname, msg_lower):
                    mentions_product = True
                    break

        if not mentions_product and len(message.strip()) <= 80:
            from services.length_controller import classify_lead_context
            pool_context = classify_lead_context(message)
            conv_id = metadata.get("conversation_id", sender_id)

            pool_result = agent.response_variator.try_pool_response(
                message,
                conv_id=conv_id,
                turn_index=metadata.get("turn_index", 0),
                context=pool_context,
                creator_id=agent.creator_id,
            )
            if pool_result.matched and pool_result.confidence >= AGENT_THRESHOLDS.pool_confidence:
                import random as _rng
                if _rng.random() < 0.30:
                    multi_bubbles = agent.response_variator.try_multi_bubble(
                        message, creator_id=agent.creator_id, conv_id=conv_id,
                    )
                    if multi_bubbles:
                        logger.debug(f"Multi-bubble matched: {len(multi_bubbles)} bubbles")
                        result.pool_response = DMResponse(
                            content=multi_bubbles[0],
                            intent="pool_response",
                            lead_stage="unknown",
                            confidence=0.85,
                            tokens_used=0,
                            metadata={
                                "pool_category": "multi_bubble",
                                "used_pool": True,
                                "message_parts": [
                                    {"text": b, "delay": 0.8} for b in multi_bubbles
                                ],
                            },
                        )
                        return result

                logger.debug(f"Pool response matched: {pool_result.category}")
                result.pool_response = DMResponse(
                    content=pool_result.response,
                    intent="pool_response",
                    lead_stage="unknown",
                    confidence=pool_result.confidence,
                    tokens_used=0,
                    metadata={"pool_category": pool_result.category, "used_pool": True},
                )
                return result

    # Step 1d: Edge case detection
    if ENABLE_EDGE_CASE_DETECTION and hasattr(agent, "edge_case_handler"):
        try:
            edge_result = agent.edge_case_handler.detect(message)
            if edge_result.should_escalate:
                logger.info(f"Edge case escalation: {edge_result.edge_type}")
                result.edge_case_response = DMResponse(
                    content=edge_result.suggested_response
                    or "Entiendo, déjame consultarlo y te respondo.",
                    intent="edge_case_escalation",
                    lead_stage="unknown",
                    confidence=edge_result.confidence,
                    metadata={
                        "edge_type": str(edge_result.edge_type),
                        "escalated": True,
                    },
                )
                return result
        except Exception as e:
            logger.debug(f"Edge case detection failed: {e}")

    return result
