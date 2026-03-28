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
    """Format RAG results as context for the prompt.

    Source-aware formatting:
    - product_catalog/faq: full content (500 chars), no source prefix
    - creator content (reel/post): includes source tag with date/URL
      so the LLM can reference "en mi reel del martes" naturally.

    Score hidden from LLM (internal ranking only).
    """
    if not rag_results:
        return ""

    creator_name = getattr(agent, "creator_name", None) or "el creador"
    context_parts = [f"Informacion relevante de {creator_name}:"]
    for result in rag_results[:3]:
        meta = result.get("metadata", {})
        source_type = meta.get("type", "")
        title = meta.get("title", "")
        source_url = meta.get("source_url", "")
        max_len = 500 if source_type in ("product_catalog", "faq") else 300
        content = result.get("content", "")[:max_len]

        # Build source tag for creator content (reels, posts, videos)
        source_tag = ""
        if source_type in ("video", "instagram_post", "carousel", "reel"):
            if title:
                source_tag = f"[De tu contenido: {title}] "
            elif source_url:
                source_tag = f"[De tu contenido: {source_url}] "
        elif source_type == "faq":
            source_tag = ""  # FAQ is self-contained
        elif title and title not in content[:50]:
            source_tag = f"[{title}] "

        context_parts.append(f"- {source_tag}{content}")

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
        if isinstance(msg, dict) and not msg.get("deleted"):
            history.append(
                {
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                }
            )
    return history


def get_history_from_db(creator_id: str, follower_id: str, limit: int = 20) -> List[Dict[str, str]]:
    """Fallback: load conversation history from PostgreSQL when JSON files don't exist.

    Args:
        creator_id: Creator slug (e.g. "iris_bertran")
        follower_id: Platform user ID (e.g. "wa_34639066982")
        limit: Max messages to return

    Returns:
        List of {role, content} dicts in chronological order, or [] on any error.
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message
        from api.utils.creator_resolver import resolve_creator_safe

        session = SessionLocal()
        try:
            creator = resolve_creator_safe(session, creator_id)
            if not creator:
                return []

            lead = (
                session.query(Lead)
                .filter(Lead.creator_id == creator.id, Lead.platform_user_id == follower_id)
                .first()
            )
            if not lead:
                return []

            messages = (
                session.query(Message.role, Message.content)
                .filter(
                    Message.lead_id == lead.id,
                    Message.status != "discarded",  # exclude rejected copilot suggestions
                    Message.deleted_at.is_(None),
                )
                .order_by(Message.created_at.desc())
                .limit(limit)
                .all()
            )

            # Return in chronological order (oldest first)
            return [
                {"role": m.role, "content": m.content}
                for m in reversed(messages)
                if m.content
            ]
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"[HISTORY-DB] Failed to load history from DB: {e}")
        return []


def get_conversation_summary(agent, follower) -> str:
    """Get a brief summary of recent conversation for notification."""
    if not follower.last_messages:
        return "Sin historial previo"

    # Get last 3 exchanges
    recent = follower.last_messages[-6:]
    summary_parts = []
    for msg in recent:
        if isinstance(msg, dict) and not msg.get("deleted"):
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
