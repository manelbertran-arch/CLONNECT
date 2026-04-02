"""
Helper methods for DM Agent V2.

Extracted from DMResponderAgentV2 class methods. Each function takes `agent`
as first parameter (the DMResponderAgentV2 instance).
"""

import logging
import re
from typing import Dict, List

from core.dm.models import DMResponse

logger = logging.getLogger(__name__)

# BUG-RAG-02 fix: Patterns that look like prompt injection in RAG chunks.
# Strip lines matching these from retrieved content before injecting into prompt.
_INJECTION_PATTERNS = re.compile(
    r"^("
    r"(you are|tu eres|eres un|act as|ignore|system:|<\|im_start|<\|system)"
    r"|"
    r"(ignore (all |the )?(previous|above|prior)|forget (all |your )?(instructions|rules))"
    r"|"
    r"(do not|don't|no) follow (the )?(previous|above|prior|original)"
    r")",
    re.IGNORECASE | re.MULTILINE,
)


def _sanitize_rag_content(content: str) -> str:
    """BUG-RAG-02 fix: Strip prompt injection patterns from RAG chunks."""
    lines = content.split("\n")
    safe_lines = [line for line in lines if not _INJECTION_PATTERNS.match(line.strip())]
    return "\n".join(safe_lines)


def format_rag_context(agent, rag_results: List[Dict]) -> str:
    """Format RAG results as context for the prompt.

    Source-aware formatting:
    - product_catalog/faq: full content (500 chars), no source prefix
    - creator content (reel/post): includes source tag with date/URL
      so the LLM can reference "en mi reel del martes" naturally.

    Score hidden from LLM (internal ranking only).
    BUG-RAG-02 fix: Sanitizes chunk content against prompt injection.
    """
    if not rag_results:
        return ""

    # Subtle header — hints "use if relevant", never forces a sales pitch.
    # The model decides if the info fits the conversation naturally.
    context_parts = ["(Info disponible — usa solo si el lead pregunta o es relevante):"]
    for result in rag_results[:3]:
        meta = result.get("metadata", {})
        source_type = meta.get("type", "")
        title = meta.get("title", "")
        source_url = meta.get("source_url", "")
        max_len = 500 if source_type in ("product_catalog", "faq") else 300
        content = result.get("content", result.get("text", ""))[:max_len]

        # BUG-RAG-02 fix: Sanitize against prompt injection
        content = _sanitize_rag_content(content)
        if not content.strip():
            continue

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
            messages = follower.last_messages[-12:] if follower.last_messages else []
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


def _clean_media_placeholders(history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Replace meaningless media placeholder text with descriptive labels.

    Reuses MEDIA_PLACEHOLDERS from detection.py as the canonical set.
    Only modifies user messages (assistant messages never contain placeholders).
    """
    from core.dm.phases.detection import MEDIA_PLACEHOLDERS

    for msg in history:
        if msg.get("role") != "user":
            continue
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        normalized = content.lower().rstrip(".")
        if normalized not in MEDIA_PLACEHOLDERS:
            continue
        # Classify by media type keywords
        lo = normalized
        if any(w in lo for w in ("photo", "foto", "image", "imagen", "📷", "📸")):
            msg["content"] = "[Lead envio una foto]"
        elif any(w in lo for w in ("video", "reel")):
            msg["content"] = "[Lead envio un video]"
        elif any(w in lo for w in ("audio", "voice", "voz", "🎤")):
            msg["content"] = "[Lead envio un audio]"
        elif any(w in lo for w in ("sticker", "gif")):
            msg["content"] = "[Lead envio un sticker]"
        elif any(w in lo for w in ("story", "historia")):
            msg["content"] = "[Lead compartio una story]"
        else:
            msg["content"] = "[Lead envio contenido multimedia]"
    return history


def get_history_from_follower(agent, follower) -> List[Dict[str, str]]:
    """Extract conversation history from follower memory.

    Filters to current session only using ConversationBoundaryDetector,
    so the bot doesn't mix context from conversations days apart.
    """
    history = []
    for msg in follower.last_messages[-10:]:
        if isinstance(msg, dict) and not msg.get("deleted"):
            history.append(
                {
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                    "created_at": msg.get("created_at"),
                }
            )

    # Filter to current session only
    if history and any(m.get("created_at") for m in history):
        try:
            from core.conversation_boundary import ConversationBoundaryDetector
            current_session = ConversationBoundaryDetector().get_current_session(history)
            if current_session:
                history = current_session
        except Exception as e:
            logger.warning(f"[SESSION] Boundary detection failed, using full history: {e}")

    # Strip created_at before returning (downstream expects only role+content)
    clean = [{"role": m["role"], "content": m["content"]} for m in history]
    return _clean_media_placeholders(clean)


def get_history_from_db(creator_id: str, follower_id: str, limit: int = 10) -> List[Dict[str, str]]:
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
                session.query(Message.role, Message.content, Message.created_at)
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
            history = [
                {"role": m.role, "content": m.content, "created_at": m.created_at}
                for m in reversed(messages)
                if m.content
            ]

            # Filter to current session only
            if history:
                try:
                    from core.conversation_boundary import ConversationBoundaryDetector
                    current_session = ConversationBoundaryDetector().get_current_session(history)
                    if current_session:
                        history = current_session
                except Exception as e:
                    logger.warning(f"[SESSION-DB] Boundary detection failed: {e}")

            # Strip created_at (downstream expects only role+content)
            clean = [{"role": m["role"], "content": m["content"]} for m in history]
            return _clean_media_placeholders(clean)
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
