"""
Context Detector — Orchestration (v2 Universal/Multilingual).

Main entry point: detect_all(). Calls individual detectors,
builds factual context notes for the Recalling block.
No behavior instructions — only factual observations.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from core.intent_classifier import Intent, IntentClassifier
from services.intent_service import IntentClassifier as CanonicalIntentClassifier

from .detectors import (
    detect_b2b,
    detect_correction,
    detect_interest_level,
    detect_meta_message,
    detect_objection_type,
    extract_user_name,
)
from .intent_mapping import svc_to_core_intent
from .models import DetectedContext

logger = logging.getLogger(__name__)

# Canonical classifier — single instance, reused across calls.
# Canonical per fix/intent-dual-reconciliation. Tabla B mapping in intent_mapping.py.
# dm_history_service.py migration pending CASUAL bug fix — see docs/bugs/intent_classifier_casual_short_msg.md
_canonical_classifier = CanonicalIntentClassifier()


def detect_all(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    is_first_message: bool = True,
    use_llm_intent: bool = False,
) -> DetectedContext:
    """Run all detectors and return complete context.

    Main entry point for context detection.
    All results are factual observations — no behavior instructions.
    """
    ctx = DetectedContext()
    ctx.is_first_message = is_first_message

    if not message:
        ctx.build_context_notes()
        return ctx

    # 1. B2B context
    b2b = detect_b2b(message)
    if b2b.is_b2b:
        ctx.is_b2b = True
        ctx.company_context = b2b.company_context
        ctx.b2b_contact_name = b2b.contact_name

    # 2. Extract user name
    name = extract_user_name(message)
    if name:
        ctx.user_name = name
    elif b2b.contact_name:
        ctx.user_name = b2b.contact_name

    # 3. Classify intent — canonical: services.IntentClassifier (fix/intent-dual-reconciliation)
    svc_intent = _canonical_classifier.classify(message)
    ctx.intent = svc_to_core_intent(svc_intent)        # Tabla B
    ctx.intent_sub = svc_intent.value                  # granular svc value (e.g. "objection_price")
    logger.debug(
        "context-detector intent: svc=%s core=%s msg=%r",
        svc_intent.value, ctx.intent.value, message[:80],
    )

    # 4. Interest level (delegates to intent classifier)
    ctx.interest_level = detect_interest_level(message, ctx.intent)

    # 5. Meta-message
    ctx.is_meta_message = detect_meta_message(message)

    # 6. Correction
    ctx.is_correction = detect_correction(message)

    # 7. Objection type — ctx.intent == OBJECTION covers all svc sub-types via Tabla B
    if ctx.intent == Intent.OBJECTION:
        ctx.objection_type = detect_objection_type(message)

    # 8. Sentiment (positive only — frustration handled externally)
    positive_patterns = [
        r"\bgracias\b", r"\bgràcies\b", r"\bthanks?\b",
        r"\bgenial\b", r"\bperfecto\b", r"\bexcelente\b",
        r"\bincre[ií]ble\b", r"\bme encanta\b", r"\bgreat\b",
        r"\bperfecte\b", r"\bfantàstic\b",
    ]
    for pattern in positive_patterns:
        if re.search(pattern, message.lower()):
            ctx.sentiment = "positive"
            break

    # NOTE: sarcasm detection is intentionally NOT implemented here.
    # The LLM handles sarcasm natively via contextual understanding.
    # A rule-based stub for Spanish irony ("sí, claro...") would have low
    # precision and add no signal beyond what the LLM already detects.
    # Frustration is handled externally by FrustrationDetector v2.

    # Build factual context notes for Recalling block
    ctx.build_context_notes()

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
    """Async version — enhances with LLM intent classification if client provided."""
    ctx = detect_all(message, history, is_first_message, use_llm_intent=False)

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

            if result.intent == Intent.INTEREST_STRONG:
                ctx.interest_level = "strong"
            elif result.intent in (Intent.INTEREST_SOFT, Intent.QUESTION_PRODUCT):
                ctx.interest_level = "soft"

            # Rebuild context notes with updated intent
            ctx.build_context_notes()
        except Exception as e:
            logger.warning(f"LLM intent classification failed: {e}")

    return ctx


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def format_alerts_for_prompt(ctx: DetectedContext) -> str:
    """Backward compat — returns context notes formatted for injection.
    Prefer using ctx.context_notes directly in the Recalling block."""
    if not ctx.context_notes:
        return ""
    return "\n".join(f"• {note}" for note in ctx.context_notes)


def get_context_summary(ctx: DetectedContext) -> str:
    """Brief summary for logging."""
    parts = []
    if ctx.is_b2b:
        parts.append(f"B2B({ctx.company_context[:20]})" if ctx.company_context else "B2B")
    if ctx.interest_level != "none":
        parts.append(f"Interest({ctx.interest_level})")
    if ctx.user_name:
        parts.append(f"Name({ctx.user_name})")
    if ctx.is_meta_message:
        parts.append("Meta")
    if ctx.is_correction:
        parts.append("Correction")
    if ctx.objection_type:
        parts.append(f"Objection({ctx.objection_type})")
    if ctx.intent and ctx.intent != Intent.OTHER:
        parts.append(f"Intent({ctx.intent.value})")
    return " | ".join(parts) if parts else "neutral"
