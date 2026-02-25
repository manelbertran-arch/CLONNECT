"""
Context Detector - Orchestration Functions

Main detection orchestration and utility functions.
Detectors only INFORM, they do NOT respond. The LLM decides what to do.

Part of refactor/context-injection-v2
"""

import logging
import re
from typing import Any, Dict, List, Optional

from core.intent_classifier import Intent, IntentClassifier, classify_intent_simple

from .detectors import (
    detect_b2b,
    detect_correction,
    detect_frustration,
    detect_interest_level,
    detect_meta_message,
    detect_objection_type,
    detect_sarcasm,
    extract_user_name,
)
from .models import DetectedContext

logger = logging.getLogger(__name__)


def detect_all(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    is_first_message: bool = True,
    use_llm_intent: bool = False,
) -> DetectedContext:
    """
    Run all detectors and return complete context.

    This is the main entry point for context detection.

    Args:
        message: Current user message
        history: Conversation history (optional)
        is_first_message: Whether this is the first message
        use_llm_intent: Whether to use LLM for intent (requires async)

    Returns:
        DetectedContext with all detected signals and alerts
    """
    ctx = DetectedContext()
    ctx.is_first_message = is_first_message

    if not message:
        ctx.build_alerts()
        return ctx

    # 1. Detect frustration
    frustration = detect_frustration(message, history)
    if frustration.is_frustrated:
        ctx.frustration_level = frustration.level
        ctx.frustration_reason = frustration.reason
        ctx.sentiment = "frustrated"

    # 2. Detect sarcasm (only if not already frustrated)
    if ctx.sentiment != "frustrated":
        sarcasm = detect_sarcasm(message)
        if sarcasm.is_sarcastic and sarcasm.confidence >= 0.6:
            ctx.sentiment = "sarcastic"

    # 3. Detect B2B context
    b2b = detect_b2b(message)
    if b2b.is_b2b:
        ctx.is_b2b = True
        ctx.company_context = b2b.company_context
        ctx.b2b_contact_name = b2b.contact_name

        # B2B context should reset frustration detection
        # "ya hab\u00edamos trabajado" should NOT be seen as frustrated
        if b2b.collaboration_type == "previous_work":
            ctx.frustration_level = "none"
            ctx.frustration_reason = ""
            if ctx.sentiment == "frustrated":
                ctx.sentiment = "neutral"

    # 4. Extract user name
    name = extract_user_name(message)
    if name:
        ctx.user_name = name
    elif b2b.contact_name:
        ctx.user_name = b2b.contact_name

    # 5. Classify intent (simple, non-LLM)
    intent_str = classify_intent_simple(message)
    intent_map = {
        "interest_strong": Intent.INTEREST_STRONG,
        "purchase": Intent.INTEREST_STRONG,
        "interest_soft": Intent.INTEREST_SOFT,
        "question_product": Intent.QUESTION_PRODUCT,
        "objection": Intent.OBJECTION,
        "greeting": Intent.GREETING,
        "support": Intent.SUPPORT,
        "other": Intent.OTHER,
    }
    ctx.intent = intent_map.get(intent_str, Intent.OTHER)
    ctx.intent_sub = intent_str

    # 6. Detect interest level
    ctx.interest_level = detect_interest_level(message, ctx.intent)

    # 7. Detect meta-message
    ctx.is_meta_message = detect_meta_message(message)

    # 8. Detect correction
    ctx.is_correction = detect_correction(message)

    # 9. Detect objection type
    if ctx.intent == Intent.OBJECTION or intent_str == "objection":
        ctx.objection_type = detect_objection_type(message)

    # 10. Check for positive sentiment (if not already set)
    if ctx.sentiment == "neutral":
        positive_patterns = [
            r"\bgracias\b",
            r"\bgenial\b",
            r"\bperfecto\b",
            r"\bexcelente\b",
            r"\bincre[\u00edi]ble\b",
            r"\bme encanta\b",
        ]
        for pattern in positive_patterns:
            if re.search(pattern, message.lower()):
                ctx.sentiment = "positive"
                break

    # Build alerts
    ctx.build_alerts()

    return ctx


# =============================================================================
# ASYNC VERSION (for LLM intent classification)
# =============================================================================


async def detect_all_async(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    is_first_message: bool = True,
    llm_client=None,
    creator_context: str = "",
) -> DetectedContext:
    """
    Async version of detect_all that can use LLM for intent classification.

    Args:
        message: Current user message
        history: Conversation history (optional)
        is_first_message: Whether this is the first message
        llm_client: Optional LLM client for intent classification
        creator_context: Context about the creator for intent classification

    Returns:
        DetectedContext with all detected signals and alerts
    """
    # Start with sync detection
    ctx = detect_all(message, history, is_first_message, use_llm_intent=False)

    # If LLM client provided, enhance intent classification
    if llm_client:
        try:
            classifier = IntentClassifier(llm_client)
            result = await classifier.classify(
                message,
                creator_context=creator_context,
                conversation_history=history,
                use_llm=True,
            )
            ctx.intent = result.intent
            ctx.intent_confidence = result.confidence
            ctx.intent_sub = result.sub_intent

            # Update interest level based on LLM intent
            if result.intent == Intent.INTEREST_STRONG:
                ctx.interest_level = "strong"
            elif result.intent in (Intent.INTEREST_SOFT, Intent.QUESTION_PRODUCT):
                ctx.interest_level = "soft"

            # Rebuild alerts with new data
            ctx.build_alerts()
        except Exception as e:
            logger.warning(f"LLM intent classification failed: {e}")

    return ctx


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def format_alerts_for_prompt(ctx: DetectedContext) -> str:
    """
    Format detected context alerts for LLM prompt injection.

    Args:
        ctx: DetectedContext with alerts

    Returns:
        Formatted string for prompt injection
    """
    if not ctx.alerts:
        return ""

    lines = ["=== ALERTAS DE CONTEXTO ==="]
    for alert in ctx.alerts:
        lines.append(f"\u2022 {alert}")
    lines.append("")

    return "\n".join(lines)


def get_context_summary(ctx: DetectedContext) -> str:
    """
    Get a brief summary of detected context for logging.

    Args:
        ctx: DetectedContext

    Returns:
        Brief summary string
    """
    parts = []

    if ctx.is_b2b:
        parts.append(f"B2B({ctx.company_context[:20]})" if ctx.company_context else "B2B")

    if ctx.frustration_level != "none":
        parts.append(f"Frustration({ctx.frustration_level})")

    if ctx.sentiment == "sarcastic":
        parts.append("Sarcasm")

    if ctx.interest_level != "none":
        parts.append(f"Interest({ctx.interest_level})")

    if ctx.user_name:
        parts.append(f"Name({ctx.user_name})")

    # Only add intent if it's meaningful (not OTHER)
    if ctx.intent and ctx.intent != Intent.OTHER:
        parts.append(f"Intent({ctx.intent.value})")

    return " | ".join(parts) if parts else "neutral"
