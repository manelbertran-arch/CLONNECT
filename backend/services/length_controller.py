"""
Length Controller - Controls response length to match creator style.

Based on Stefan's metrics:
- Average length: 22 chars
- Median length: 18 chars
- Target for bot: 20-28 chars max
"""

import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class LengthConfig:
    """Length configuration based on creator metrics."""

    min_length: int = 5
    target_length: int = 20
    max_length: int = 28
    max_for_greeting: int = 12
    max_for_confirmation: int = 15
    max_for_emotional: int = 45


# Stefan's configuration based on real data analysis
STEFAN_LENGTH_CONFIG = LengthConfig(
    min_length=3,
    target_length=20,
    max_length=28,
    max_for_greeting=12,
    max_for_confirmation=15,
    max_for_emotional=50,
)


def detect_message_type(lead_message: str) -> str:
    """Detect message type to adjust response length."""
    msg_lower = lead_message.lower().strip()

    # Greetings
    greetings = ["hola", "hey", "buenas", "ey", "hi", "hello", "que tal", "qué tal"]
    if any(g in msg_lower for g in greetings) and len(msg_lower) < 20:
        return "greeting"

    # Confirmations
    confirmations = ["ok", "dale", "vale", "perfecto", "genial", "bueno", "sí", "si", "claro"]
    if msg_lower.rstrip("!").rstrip(".") in confirmations:
        return "confirmation"

    # Emoji only
    if all(ord(c) > 127000 or c.isspace() for c in msg_lower):
        return "emoji_only"

    # Laughs
    if msg_lower.startswith("jaj") or msg_lower.startswith("hah"):
        return "laugh"

    # Thanks
    thanks = ["gracias", "thanks", "thx", "grax"]
    if any(t in msg_lower for t in thanks):
        return "thanks"

    # Emotional/long messages
    emotional_words = [
        "triste",
        "feliz",
        "emocionado",
        "preocupado",
        "difícil",
        "duro",
        "increíble",
    ]
    if any(w in msg_lower for w in emotional_words) or len(lead_message) > 100:
        return "emotional"

    # Question
    if "?" in lead_message:
        return "question"

    return "normal"


def get_max_length(message_type: str, config: LengthConfig = None) -> int:
    """Get max length based on message type."""
    config = config or STEFAN_LENGTH_CONFIG

    length_map = {
        "greeting": config.max_for_greeting,
        "confirmation": config.max_for_confirmation,
        "emoji_only": 8,
        "laugh": 10,
        "thanks": config.max_for_confirmation,
        "emotional": config.max_for_emotional,
        "question": config.max_length + 10,
        "normal": config.max_length,
    }

    return length_map.get(message_type, config.max_length)


def truncate_response(response: str, max_length: int) -> str:
    """
    Intelligently truncate response if it exceeds max length.
    Preserves final emojis and punctuation.
    """
    if len(response) <= max_length:
        return response

    # Extract final emoji if exists
    final_emoji = ""
    if response and ord(response[-1]) > 127000:
        final_emoji = response[-1]
        response = response[:-1].rstrip()

    # Reserve space for punctuation
    effective_max = max_length - 1

    # Find natural cut point
    truncated = response[:effective_max]

    # Try to cut at space
    last_space = truncated.rfind(" ")
    if last_space > effective_max * 0.5:
        truncated = truncated[:last_space]

    # Clean incomplete punctuation
    truncated = truncated.rstrip(".,!?;: ")

    # Add closing punctuation if needed
    if truncated and truncated[-1].isalnum():
        truncated += "!"

    # Final length check - force truncate if still too long
    if len(truncated) > max_length:
        truncated = truncated[: max_length - 1] + "!"

    # Restore emoji if it fits
    if final_emoji and len(truncated) + 1 <= max_length:
        truncated = (
            truncated[:-1] + final_emoji if truncated.endswith("!") else truncated + final_emoji
        )

    return truncated[:max_length]  # Final safety check


def enforce_length(response: str, lead_message: str, config: LengthConfig = None) -> str:
    """
    Adjust response length based on context.

    Args:
        response: Generated response
        lead_message: Original lead message
        config: Length configuration

    Returns:
        Response adjusted to appropriate length
    """
    config = config or STEFAN_LENGTH_CONFIG

    message_type = detect_message_type(lead_message)
    max_len = get_max_length(message_type, config)

    if len(response) > max_len:
        return truncate_response(response, max_len)

    return response


# Short predefined responses for replacements
SHORT_REPLACEMENTS = {
    "greeting": ["Ey! 😊", "Buenas!", "Hola!", "Hey!", "Qué tal!", "👋"],
    "confirmation": ["Dale!", "Ok!", "Genial!", "Perfecto!", "👍", "Vale!", "Sí!"],
    "thanks": ["A ti!", "Nada!", "😊", "💙", "De nada!", "Gracias a ti!"],
    "laugh": ["Jaja", "Jajaja", "😂", "🤣", "Jeje"],
    "emoji_only": ["😊", "💙", "👍", "🙌", "❤️", "💪"],
}


def get_short_replacement(message_type: str) -> Optional[str]:
    """Get a short predefined response for the message type."""
    options = SHORT_REPLACEMENTS.get(message_type, [])
    return random.choice(options) if options else None
