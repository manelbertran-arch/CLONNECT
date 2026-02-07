"""
Length Controller - Guides response length to match creator style.

Based on Stefan's metrics:
- Average length: 38 chars
- Median length: 23 chars
- These are GUIDELINES, not hard limits. Complete sentences always win.
"""

import random
from dataclasses import dataclass
from typing import Optional


@dataclass
class LengthConfig:
    """Length configuration based on creator metrics."""

    min_length: int = 5
    target_length: int = 38
    soft_max: int = 150
    max_for_greeting: int = 30
    max_for_confirmation: int = 25
    max_for_emotional: int = 200


# Stefan's configuration based on real data analysis (3,061 human messages)
STEFAN_LENGTH_CONFIG = LengthConfig(
    min_length=3,
    target_length=38,
    soft_max=150,
    max_for_greeting=30,
    max_for_confirmation=25,
    max_for_emotional=200,
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

    # Affection messages
    affection = ["te quiero", "te amo", "te adoro"]
    if any(a in msg_lower for a in affection):
        return "affection"

    # Praise/compliments (long messages praising Stefan)
    if len(lead_message) > 50 and any(
        w in msg_lower for w in ["lindo", "genial", "increíble", "hermoso"]
    ):
        return "praise"

    # Emotional/long messages
    emotional_words = [
        "triste",
        "feliz",
        "emocionado",
        "preocupado",
        "difícil",
        "duro",
    ]
    if any(w in msg_lower for w in emotional_words):
        return "emotional"

    # Question - keep short answers
    if "?" in lead_message:
        return "question"

    return "normal"


def get_soft_max(message_type: str, config: LengthConfig = None) -> int:
    """Get soft max length based on message type (guideline, not hard limit)."""
    config = config or STEFAN_LENGTH_CONFIG

    length_map = {
        "greeting": config.max_for_greeting,
        "confirmation": config.max_for_confirmation,
        "emoji_only": 10,
        "laugh": 15,
        "thanks": config.max_for_confirmation,
        "emotional": config.max_for_emotional,
        "affection": 40,
        "praise": 40,
        "question": config.soft_max,
        "normal": config.soft_max,
    }

    return length_map.get(message_type, config.soft_max)


def enforce_length(response: str, lead_message: str, config: LengthConfig = None) -> str:
    """
    Soft length guidance - NEVER truncates mid-sentence.

    Only truncates if response is extremely long (>500 chars),
    and even then cuts at a sentence boundary.

    Args:
        response: Generated response
        lead_message: Original lead message
        config: Length configuration

    Returns:
        Response, possibly shortened but always complete sentences
    """
    config = config or STEFAN_LENGTH_CONFIG

    # Never truncate short responses
    if len(response) <= 200:
        return response

    # Only truncate if excessively long (>500 chars)
    if len(response) <= 500:
        return response

    # Find last sentence boundary before 500 chars
    for boundary in ["! ", "? ", ". ", "!\n", "?\n", ".\n"]:
        idx = response[:500].rfind(boundary)
        if idx > 100:
            return response[: idx + 1].strip()

    # If no sentence boundary found, return as-is (don't truncate mid-sentence)
    return response


# Short predefined responses for replacements
SHORT_REPLACEMENTS = {
    "greeting": ["Ey! 😊", "Buenas!", "Hola!", "Hey!", "Qué tal!", "👋"],
    "confirmation": ["Dale!", "Ok!", "Genial!", "Perfecto!", "👍", "Vale!", "Sí!"],
    "thanks": ["A ti!", "Nada!", "😊", "💙", "De nada!", "Gracias a ti!"],
    "laugh": ["Jaja", "Jajaja", "😂", "🤣", "Jeje"],
    "emoji_only": ["😊", "💙", "👍", "🙌", "❤️", "💪"],
    "affection": ["Yo a ti! 💙", "Igualmente! ❤️", "Y yo a ti!", "💙", "Un abrazo! 💙"],
    "praise": ["Gracias! 😊", "Muchas gracias!", "Qué lindo! 😊", "💙", "Gracias!"],
}


def get_short_replacement(message_type: str) -> Optional[str]:
    """Get a short predefined response for the message type."""
    options = SHORT_REPLACEMENTS.get(message_type, [])
    return random.choice(options) if options else None
