"""
Helper methods for DM Agent V2.

Extracted from DMResponderAgentV2 class methods. Each function takes `agent`
as first parameter (the DMResponderAgentV2 instance).
"""

import logging
from typing import Dict, List

from core.dm.models import DMResponse

logger = logging.getLogger(__name__)


def format_rag_context(agent, rag_results: List[Dict]) -> str:
    """Format RAG results as context for the prompt."""
    if not rag_results:
        return ""

    context_parts = ["Informacion relevante:"]
    for result in rag_results[:3]:
        content = result.get("content", "")[:200]
        score = result.get("score", 0)
        context_parts.append(f"- [{score:.2f}] {content}")

    return "\n".join(context_parts)


def get_lead_stage(agent, follower, metadata: Dict) -> str:
    """Get current lead stage for user."""
    from services import LeadStage

    if metadata.get("lead_stage"):
        return metadata["lead_stage"]

    # Try advanced categorizer first
    from core.dm.text_utils import _PRODUCT_STOPWORDS  # ensure module loaded
    import os
    ENABLE_LEAD_CATEGORIZER = os.getenv("ENABLE_LEAD_CATEGORIZER", "true").lower() == "true"

    if ENABLE_LEAD_CATEGORIZER:
        try:
            from core.lead_categorizer import get_lead_categorizer
            messages = follower.last_messages[-20:] if follower.last_messages else []
            category, score, reason = get_lead_categorizer().categorize(
                messages=messages,
                is_customer=follower.is_customer,
            )
            logger.debug(f"Lead categorizer: {category.value} ({reason})")
            return category.value
        except Exception as e:
            logger.debug(f"Lead categorizer failed: {e}")

    # Fallback to simple score-based logic
    if follower.is_customer:
        return LeadStage.CLIENTE.value
    if follower.purchase_intent_score >= 0.7:
        return LeadStage.CALIENTE.value
    if follower.purchase_intent_score >= 0.4:
        return LeadStage.INTERESADO.value
    return LeadStage.NUEVO.value


def get_history_from_follower(agent, follower) -> List[Dict[str, str]]:
    """Extract conversation history from follower memory."""
    history = []
    for msg in follower.last_messages[-20:]:
        if isinstance(msg, dict):
            history.append(
                {
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                }
            )
    return history


def get_conversation_summary(agent, follower) -> str:
    """Get a brief summary of recent conversation for notification."""
    if not follower.last_messages:
        return "Sin historial previo"

    # Get last 3 exchanges
    recent = follower.last_messages[-6:]
    summary_parts = []
    for msg in recent:
        if isinstance(msg, dict):
            role = "\U0001f464" if msg.get("role") == "user" else "\U0001f916"
            content = msg.get("content", "")[:100]
            summary_parts.append(f"{role} {content}")

    return "\n".join(summary_parts) if summary_parts else "Sin historial"


def error_response(agent, error: str) -> DMResponse:
    """Generate error response."""
    from services import LeadStage

    return DMResponse(
        content="Lo siento, hubo un error procesando tu mensaje. Por favor intenta de nuevo.",
        intent="ERROR",
        lead_stage=LeadStage.NUEVO.value,
        confidence=0.0,
        metadata={"error": error},
    )


def detect_platform(agent, follower_id: str) -> str:
    """Detect platform from follower_id prefix."""
    if follower_id.startswith("ig_"):
        return "instagram"
    if follower_id.startswith("tg_"):
        return "telegram"
    if follower_id.startswith("wa_"):
        return "whatsapp"
    return "instagram"  # Default
