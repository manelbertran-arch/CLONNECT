"""
Copilot data models, constants, and utility functions.
"""

import re
from dataclasses import dataclass
from typing import Optional

# Debounce: wait this many seconds after the last burst message before regenerating
DEBOUNCE_SECONDS = 30

# Media detection patterns — these are not real text and should not get copilot suggestions
_MEDIA_HASH_PATTERN = re.compile(r"^[A-Za-z0-9+/=]{15,}$")
_ATTACHMENT_PLACEHOLDERS = {
    "sent an attachment",
    "[media]",
    "[imagen]",
    "[video]",
    "[audio]",
    "[sticker]",
    "[file]",
    "[gif]",
    "[document]",
    "[contact]",
    "[location]",
}


def is_non_text_message(content: str) -> bool:
    """Detect media keys, attachment placeholders, and non-text content."""
    if not content or not content.strip():
        return True

    stripped = content.strip()

    # Evolution API media keys (hash-like strings without spaces)
    if _MEDIA_HASH_PATTERN.match(stripped):
        return True

    # Attachment placeholders from Instagram/WhatsApp
    if stripped.lower() in _ATTACHMENT_PLACEHOLDERS:
        return True

    # "Sent a photo/video/reel" from IG handler
    if stripped.lower().startswith("sent a "):
        return True

    # "Shared a post/reel" from IG handler
    if stripped.lower().startswith("shared a "):
        return True

    return False


@dataclass
class PendingResponse:
    """Respuesta pendiente de aprobación"""

    id: str
    lead_id: str
    follower_id: str
    platform: str  # instagram, telegram
    user_message: str
    user_message_id: str
    suggested_response: str
    intent: str
    confidence: float
    created_at: str
    username: str = ""
    full_name: str = ""
