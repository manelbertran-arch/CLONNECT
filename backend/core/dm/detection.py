"""
DM Agent Phase 1: Detection.

Handles sensitive content, frustration, pool responses, and edge cases.
Returns early (fast path) when possible.
"""

import logging
from typing import TYPE_CHECKING, Dict

from core.agent_config import AGENT_THRESHOLDS
from core.dm.helpers import _message_mentions_product
from core.dm.models import (
    DMResponse,
    DetectionResult,
    ENABLE_CONTEXT_DETECTION,
    ENABLE_EDGE_CASE_DETECTION,
    ENABLE_FRUSTRATION_DETECTION,
    ENABLE_SENSITIVE_DETECTION,
)

if TYPE_CHECKING:
    from core.dm.agent import DMResponderAgentV2

logger = logging.getLogger(__name__)


async def phase_detection(
    agent: "DMResponderAgentV2",
    message: str,
    sender_id: str,
    metadata: Dict,
    cognitive_metadata: Dict,
) -> DetectionResult:
    """Phase 1: Sensitive content, frustration, pool response, edge cases."""
    result = DetectionResult()

    # PRE-PIPELINE: SENSITIVE CONTENT DETECTION (Security)
    if ENABLE_SENSITIVE_DETECTION:
        try:
            from core.sensitive_detector import detect_sensitive_content, get_crisis_resources

            sensitive_result = detect_sensitive_content(message)
            if sensitive_result and sensitive_result.confidence >= AGENT_THRESHOLDS.sensitive_confidence:
                logger.warning(f"Sensitive content detected: {sensitive_result.category}")
                cognitive_metadata["sensitive_detected"] = True
                cognitive_metadata["sensitive_category"] = sensitive_result.category
                if sensitive_result.confidence >= AGENT_THRESHOLDS.sensitive_escalation:
                    crisis_response = get_crisis_resources(language="es")
                    result.pool_response = DMResponse(
                        content=crisis_response,
                        intent="sensitive_content",
                        lead_stage="unknown",
                        confidence=sensitive_result.confidence,
                        tokens_used=0,
                        metadata={"sensitive_category": sensitive_result.category},
                    )
                    return result
        except Exception as e:
            logger.debug(f"Sensitive detection failed: {e}")

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
    if ENABLE_CONTEXT_DETECTION:
        try:
            from core.context_detector import detect_all as detect_context

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
