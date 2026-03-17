"""
Phase 0 — Data Cleaning and Bot Message Filtering

Reads all messages for a creator from DB, separates human creator messages
from AI copilot messages using metadata fields and heuristics, and outputs
clean structured data per lead.
"""

import logging
import re
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.personality_extraction.models import (
    CleanedConversation,
    CleanedMessage,
    CleaningStats,
    MessageOrigin,
)

logger = logging.getLogger(__name__)

# ── Bot detection heuristics ────────────────────────────────────────

# Phrases that strongly indicate AI-generated messages
BOT_PHRASES_STRONG = [
    "en qué puedo ayudarte",
    "puedo ayudarte",
    "no dudes en",
    "estoy aquí para",
    "con gusto te ayudo",
    "será un placer",
    "quedo a tu disposición",
    "feliz de ayudarte",
    "no dudes en contactarme",
    "estoy a tu disposición",
    "con mucho gusto",
    "me encantaría ayudarte",
    "estaré encantado de",
    "estaré encantada de",
    "si necesitas algo más",
    "no dudes en preguntar",
    "cualquier duda que tengas",
    "quedo atento a tu respuesta",
    "quedo atenta a tu respuesta",
]

# Phrases that weakly indicate AI-generated messages (need 2+ to flag)
BOT_PHRASES_WEAK = [
    "me llamó la atención",
    "llamó la atención",
    "me parece muy interesante tu",
    "me parece súper interesante",
    "qué interesante lo que",
    "me encanta lo que compartes",
    "gracias por compartir",
    "es genial que",
    "me alegra mucho",
    "qué bueno que",
]

# Compiled patterns for efficiency
_BOT_STRONG_PATTERNS = [re.compile(re.escape(p), re.IGNORECASE) for p in BOT_PHRASES_STRONG]
_BOT_WEAK_PATTERNS = [re.compile(re.escape(p), re.IGNORECASE) for p in BOT_PHRASES_WEAK]


def _count_bot_indicators(content: str) -> tuple[int, int]:
    """Count strong and weak bot indicators in a message."""
    strong = sum(1 for p in _BOT_STRONG_PATTERNS if p.search(content))
    weak = sum(1 for p in _BOT_WEAK_PATTERNS if p.search(content))
    return strong, weak


def _detect_message_origin(
    role: str,
    content: str,
    status: Optional[str],
    approved_by: Optional[str],
    has_suggested_response: bool = False,
    suggestion_matches_content: bool = False,
    msg_metadata: Optional[dict] = None,
) -> MessageOrigin:
    """
    Classify a creator message as real human or AI copilot.

    Priority order:
    1. Explicit metadata fields (highest confidence)
    2. Status/approved_by fields
    3. Heuristic detection (lowest confidence)
    """
    if role == "user":
        return MessageOrigin.LEAD

    # ── Priority 1: Explicit metadata ──
    if msg_metadata:
        source = msg_metadata.get("source", "")
        if source in ("copilot", "bot", "ai", "auto", "system"):
            return MessageOrigin.COPILOT_AI
        if source in ("creator", "human", "manual"):
            return MessageOrigin.CREATOR_REAL
        if msg_metadata.get("is_bot") or msg_metadata.get("is_ai"):
            return MessageOrigin.COPILOT_AI

    # ── Priority 2: Copilot workflow fields ──
    if status == "pending_approval":
        return MessageOrigin.COPILOT_AI
    if approved_by == "auto":
        return MessageOrigin.COPILOT_AI
    if approved_by == "creator":
        return MessageOrigin.CREATOR_REAL
    if has_suggested_response and not suggestion_matches_content:
        # Creator edited the bot's suggestion — treat as creator real
        return MessageOrigin.CREATOR_REAL
    if has_suggested_response and suggestion_matches_content:
        # Creator approved bot's suggestion without editing
        return MessageOrigin.COPILOT_AI

    # ── Priority 3: Historical sync (pre-copilot era) ──
    if approved_by == "historical_sync":
        # Messages imported during DM sync — assume creator real
        # but check heuristics
        strong, weak = _count_bot_indicators(content)
        if strong >= 1:
            return MessageOrigin.COPILOT_AI
        if weak >= 2:
            return MessageOrigin.ORIGIN_UNCERTAIN
        return MessageOrigin.CREATOR_REAL

    # ── Priority 4: Heuristic detection ──
    strong, weak = _count_bot_indicators(content)
    if strong >= 1:
        return MessageOrigin.COPILOT_AI
    if weak >= 2:
        return MessageOrigin.ORIGIN_UNCERTAIN

    # Default: creator real
    return MessageOrigin.CREATOR_REAL


def _detect_message_type(content: str, msg_metadata: Optional[dict]) -> str:
    """Detect the type of message from metadata or content."""
    if msg_metadata:
        msg_type = msg_metadata.get("type", "")
        if msg_type:
            type_map = {
                "story_mention": "story_mention",
                "story_reply": "story_reply",
                "reel_share": "reel_share",
                "post_share": "post_share",
                "audio": "audio",
                "voice": "audio",
                "image": "image",
                "video": "video",
                "link": "link",
                "sticker": "sticker",
                "gif": "gif",
            }
            return type_map.get(msg_type, "text")

        # Check for media URLs
        if msg_metadata.get("url") or msg_metadata.get("media_url"):
            if msg_metadata.get("is_audio") or msg_metadata.get("is_voice"):
                return "audio"
            return "media"

    # Content-based detection
    if content and content.startswith("[audio_message"):
        return "audio"
    if content and content.startswith("[story"):
        return "story_reply"

    return "text"


def extract_conversations(
    db: Session,
    creator_id: str,
    min_messages: int = 0,
    limit_leads: Optional[int] = None,
) -> tuple[list[CleanedConversation], CleaningStats]:
    """
    Extract and clean all conversations for a creator from the database.

    Args:
        db: Database session
        creator_id: Creator UUID or identifier
        min_messages: Minimum total messages per lead to include
        limit_leads: Max number of leads to process (None = all)

    Returns:
        Tuple of (cleaned conversations sorted by activity, cleaning stats)
    """
    logger.info("Starting data extraction for creator %s", creator_id)

    # Resolve creator name → UUID if a slug was passed instead of a UUID
    try:
        import uuid as _uuid
        _uuid.UUID(creator_id)
    except (ValueError, AttributeError):
        row = db.execute(
            text("SELECT id FROM creators WHERE name = :name"),
            {"name": creator_id},
        ).first()
        if row:
            creator_id = str(row[0])
        else:
            logger.warning("Creator %s not found in DB", creator_id)
            return [], CleaningStats()

    # Query all leads and their messages for this creator
    # Optimized: only select columns we need, minimize JSON transfer
    query = text("""
        SELECT
            l.id as lead_id,
            l.username,
            l.full_name,
            l.platform,
            m.role,
            m.content,
            m.status as msg_status,
            m.approved_by,
            CASE WHEN m.suggested_response IS NOT NULL AND m.suggested_response = m.content
                 THEN 'same' ELSE COALESCE(LEFT(m.suggested_response, 1), '') END as suggested_match,
            m.msg_metadata,
            m.created_at
        FROM leads l
        JOIN messages m ON m.lead_id = l.id
        WHERE l.creator_id = :creator_id
        ORDER BY l.id, m.created_at ASC
    """)

    rows = db.execute(query, {"creator_id": creator_id}).fetchall()
    logger.info("Fetched %d message rows for creator %s", len(rows), creator_id)

    if not rows:
        return [], CleaningStats()

    # Group messages by lead
    conversations: dict[str, CleanedConversation] = {}
    stats = CleaningStats()

    for row in rows:
        lead_id = str(row.lead_id)
        content = row.content or ""
        msg_metadata = row.msg_metadata if isinstance(row.msg_metadata, dict) else {}

        # Initialize conversation if new lead
        if lead_id not in conversations:
            conversations[lead_id] = CleanedConversation(
                lead_id=lead_id,
                username=row.username or "",
                full_name=row.full_name or "",
                platform=row.platform or "instagram",
            )

        conv = conversations[lead_id]

        # Detect origin (human vs bot)
        # suggested_match: 'same' if suggested_response == content, first char if exists, '' if null
        has_suggestion = row.suggested_match != ""
        suggestion_matches = row.suggested_match == "same"
        origin = _detect_message_origin(
            role=row.role,
            content=content,
            status=row.msg_status,
            approved_by=row.approved_by,
            has_suggested_response=has_suggestion,
            suggestion_matches_content=suggestion_matches,
            msg_metadata=msg_metadata,
        )

        # Detect message type
        msg_type = _detect_message_type(content, msg_metadata)

        # Create cleaned message
        msg = CleanedMessage(
            timestamp=row.created_at or datetime.now(),
            role="creator" if row.role == "assistant" else "lead",
            content=content,
            origin=origin,
            msg_type=msg_type,
            metadata=msg_metadata,
        )

        conv.messages.append(msg)
        conv.content_types.add(msg_type)

        # Update stats
        stats.total_messages += 1
        if origin == MessageOrigin.CREATOR_REAL:
            stats.creator_real += 1
            conv.creator_real_count += 1
        elif origin == MessageOrigin.COPILOT_AI:
            stats.copilot_ai += 1
            conv.copilot_ai_count += 1
        elif origin == MessageOrigin.ORIGIN_UNCERTAIN:
            stats.uncertain += 1
            conv.uncertain_count += 1
        elif origin == MessageOrigin.LEAD:
            stats.lead_messages += 1
            conv.lead_count += 1

    # Finalize conversations
    result = []
    for conv in conversations.values():
        conv.total_messages = len(conv.messages)
        if conv.messages:
            conv.first_message_at = conv.messages[0].timestamp
            conv.last_message_at = conv.messages[-1].timestamp

        # Apply filters
        if conv.total_messages < min_messages:
            continue

        result.append(conv)

    # Sort by creator_real_count descending (most active first)
    result.sort(key=lambda c: c.creator_real_count, reverse=True)

    # Apply lead limit
    if limit_leads and len(result) > limit_leads:
        result = result[:limit_leads]

    # Final stats
    stats.total_leads = len(result)
    stats.leads_with_enough_data = sum(1 for c in result if c.creator_real_count >= 3)
    denominator = stats.creator_real + stats.copilot_ai + stats.uncertain
    stats.clean_ratio = stats.creator_real / denominator if denominator > 0 else 0.0

    logger.info(
        "Extraction complete: %d leads, %d messages (real=%d, bot=%d, uncertain=%d, lead=%d), clean_ratio=%.1f%%",
        stats.total_leads,
        stats.total_messages,
        stats.creator_real,
        stats.copilot_ai,
        stats.uncertain,
        stats.lead_messages,
        stats.clean_ratio * 100,
    )

    return result, stats
