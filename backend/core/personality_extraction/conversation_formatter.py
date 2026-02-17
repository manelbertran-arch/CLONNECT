"""
Phase 1 — Conversation Formatter (Doc A)

Formats cleaned conversations into structured text documents,
one block per lead, with chronological messages, gap detection,
and copilot markers.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from core.personality_extraction.models import (
    CleanedConversation,
    CleanedMessage,
    FormattedConversation,
    MessageOrigin,
)

logger = logging.getLogger(__name__)

# Gap threshold: if no response within this time, mark as [SIN RESPUESTA]
NO_RESPONSE_THRESHOLD = timedelta(hours=48)

# Type labels for non-text messages
TYPE_LABELS = {
    "audio": "[audio_message — contenido no disponible]",
    "story_reply": "[story_reply]",
    "story_mention": "[story_mention]",
    "reel_share": "[reel_share]",
    "post_share": "[post_share]",
    "image": "[image]",
    "video": "[video]",
    "link": "[link]",
    "media": "[media]",
    "sticker": "[sticker]",
    "gif": "[gif]",
}


def _format_timestamp(dt: datetime) -> str:
    """Format datetime as [YYYY-MM-DD HH:MM]."""
    return dt.strftime("[%Y-%m-%d %H:%M]")


def _format_message_content(msg: CleanedMessage) -> str:
    """Format a single message with type indicators."""
    content = msg.content or ""

    if msg.msg_type != "text" and msg.msg_type in TYPE_LABELS:
        label = TYPE_LABELS[msg.msg_type]
        if content:
            # Include content context for story replies etc.
            story_url = msg.metadata.get("url", "")
            if story_url:
                return f'{label} → "{content}" (story: {story_url})'
            return f'{label} → "{content}"'
        return label

    return content


def _detect_response_gaps(messages: list[CleanedMessage]) -> list[tuple[int, str]]:
    """
    Detect gaps where the creator didn't respond to a lead message.

    Returns list of (index_after_which_to_insert_gap, gap_note).
    """
    gaps = []

    for i, msg in enumerate(messages):
        if msg.origin != MessageOrigin.LEAD:
            continue

        # Look for a creator response after this lead message
        found_creator_response = False
        for j in range(i + 1, len(messages)):
            next_msg = messages[j]
            if next_msg.origin == MessageOrigin.CREATOR_REAL:
                found_creator_response = True
                break
            if next_msg.origin == MessageOrigin.LEAD:
                # Another lead message before creator responded
                break

        if not found_creator_response:
            # Check if this is the last lead message in the conversation
            remaining_creator = any(
                m.origin == MessageOrigin.CREATOR_REAL for m in messages[i + 1:]
            )
            if not remaining_creator and i < len(messages) - 1:
                gaps.append(
                    (i, "CREADOR: [SIN RESPUESTA del creador real en este hilo]")
                )
            elif not remaining_creator and i == len(messages) - 1:
                gaps.append(
                    (i, "CREADOR: [SIN RESPUESTA — posible respuesta por audio o canal externo]")
                )

    return gaps


def format_conversation(conv: CleanedConversation) -> FormattedConversation:
    """
    Format a single cleaned conversation into the Doc A format.

    Includes all lead messages and creator real messages.
    Copilot AI messages are shown as [COPILOTO IA — EXCLUIDO].
    Response gaps are marked.
    """
    # Build header
    name_display = conv.full_name or conv.username or "Unknown"
    username_display = f"@{conv.username}" if conv.username else ""

    period_start = conv.first_message_at.strftime("%Y-%m-%d") if conv.first_message_at else "?"
    period_end = conv.last_message_at.strftime("%Y-%m-%d") if conv.last_message_at else "?"

    content_types_str = ", ".join(sorted(conv.content_types)) if conv.content_types else "texto"

    header = (
        f"{'=' * 60}\n"
        f"LEAD: {name_display} ({username_display})\n"
        f"Total mensajes: {conv.total_messages} | "
        f"Creador real: {conv.creator_real_count} | "
        f"Copiloto IA (excluidos): {conv.copilot_ai_count} | "
        f"Lead: {conv.lead_count}\n"
        f"Período: {period_start} → {period_end}\n"
        f"Tipos de contenido: {content_types_str}\n"
        f"{'=' * 60}"
    )

    # Build body
    lines = ["", "CONVERSACIÓN COMPLETA (solo mensajes del creador real + todos los del lead):", "─" * 40]

    # Detect response gaps
    gaps = _detect_response_gaps(conv.messages)
    gap_indices = {g[0]: g[1] for g in gaps}

    # Group messages by timestamp proximity (same minute = same block)
    prev_timestamp: Optional[datetime] = None
    prev_date: Optional[str] = None

    for i, msg in enumerate(conv.messages):
        # Add timestamp header when time changes significantly (>5 min gap)
        current_ts = msg.timestamp
        show_timestamp = False
        if prev_timestamp is None:
            show_timestamp = True
        elif (current_ts - prev_timestamp) > timedelta(minutes=5):
            show_timestamp = True

        # Add date separator for new days
        current_date = current_ts.strftime("%Y-%m-%d")
        if current_date != prev_date and prev_date is not None:
            lines.append("")

        if show_timestamp:
            lines.append(f"\n{_format_timestamp(current_ts)}")

        # Format message based on origin
        content = _format_message_content(msg)

        if msg.origin == MessageOrigin.COPILOT_AI:
            lines.append(f'[COPILOTO IA — EXCLUIDO]: "{content}"')
        elif msg.origin == MessageOrigin.ORIGIN_UNCERTAIN:
            lines.append(f'[ORIGEN INCIERTO — EXCLUIDO]: "{content}"')
        elif msg.origin == MessageOrigin.CREATOR_REAL:
            lines.append(f"CREADOR: {content}")
        elif msg.origin == MessageOrigin.LEAD:
            lines.append(f"LEAD: {content}")

        # Insert gap marker if applicable
        if i in gap_indices:
            lines.append(gap_indices[i])

        prev_timestamp = current_ts
        prev_date = current_date

    lines.extend(["", "─" * 40, "FIN CONVERSACIÓN"])

    body = "\n".join(lines)

    return FormattedConversation(
        lead_id=conv.lead_id,
        username=conv.username,
        full_name=conv.full_name,
        header=header,
        body=body,
        total_messages=conv.total_messages,
        creator_real_count=conv.creator_real_count,
        copilot_excluded_count=conv.copilot_ai_count + conv.uncertain_count,
        lead_count=conv.lead_count,
        period_start=period_start,
        period_end=period_end,
        content_types=sorted(conv.content_types),
    )


def format_all_conversations(
    conversations: list[CleanedConversation],
) -> list[FormattedConversation]:
    """Format all conversations into Doc A format."""
    formatted = []
    for conv in conversations:
        try:
            formatted.append(format_conversation(conv))
        except Exception as e:
            logger.error("Failed to format conversation for lead %s: %s", conv.lead_id, e)
    return formatted


def generate_doc_a(formatted: list[FormattedConversation]) -> str:
    """Generate the complete Doc A text from formatted conversations."""
    sections = [
        "# DOCUMENTO A: CONVERSACIONES CRUDAS SEGREGADAS POR LEAD",
        f"Total leads: {len(formatted)}",
        f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    for conv in formatted:
        sections.append(conv.header)
        sections.append(conv.body)
        sections.append("")

    return "\n".join(sections)
