"""
Intent Service - Classify user message intents.

Extracted from dm_agent.py as part of REFACTOR-PHASE2.
Uses keyword-based classification for fast, deterministic results.
"""
from enum import Enum
from typing import Optional


class Intent(Enum):
    """Possible user message intents."""

    # Greetings and social
    GREETING = "greeting"
    GENERAL_CHAT = "general_chat"
    THANKS = "thanks"
    GOODBYE = "goodbye"

    # Interest levels
    INTEREST_SOFT = "interest_soft"
    INTEREST_STRONG = "interest_strong"
    PURCHASE_INTENT = "purchase_intent"

    # Acknowledgments and corrections
    ACKNOWLEDGMENT = "acknowledgment"
    CORRECTION = "correction"

    # Objections
    OBJECTION_PRICE = "objection_price"
    OBJECTION_TIME = "objection_time"
    OBJECTION_DOUBT = "objection_doubt"
    OBJECTION_LATER = "objection_later"
    OBJECTION_WORKS = "objection_works"
    OBJECTION_NOT_FOR_ME = "objection_not_for_me"
    OBJECTION_COMPLICATED = "objection_complicated"
    OBJECTION_ALREADY_HAVE = "objection_already_have"

    # Questions
    QUESTION_PRODUCT = "question_product"
    QUESTION_GENERAL = "question_general"
    PRODUCT_QUESTION = "product_question"  # Alias for compatibility

    # Actions
    LEAD_MAGNET = "lead_magnet"
    BOOKING = "booking"

    # Support and escalation
    SUPPORT = "support"
    ESCALATION = "escalation"

    # v10.2: New sub-categories (previously all fell into OTHER)
    HUMOR = "humor"
    REACTION = "reaction"
    ENCOURAGEMENT = "encouragement"
    CONTINUATION = "continuation"
    CASUAL = "casual"

    # Fallback
    OTHER = "other"


class IntentClassifier:
    """Classify user message intents using keyword matching."""

    # Greeting patterns
    GREETING_PATTERNS = [
        "hola",
        "hello",
        "hi",
        "buenos dias",
        "buenos días",
        "buenas tardes",
        "buenas noches",
        "buenas",
        "qué tal",
        "que tal",
        "saludos",
        "hey",
    ]

    # Purchase intent patterns
    PURCHASE_PATTERNS = [
        "quiero comprar",
        "quiero adquirir",
        "me interesa comprar",
        "cómo compro",
        "como compro",
        "donde compro",
        "dónde compro",
        "link de compra",
        "enlace de compra",
        "quiero pagar",
        "cómo pago",
        "como pago",
        "quiero el curso",
        "quiero inscribirme",
        "quiero apuntarme",
        "me apunto",
        "lo quiero",
        "lo compro",
    ]

    # Product question patterns
    PRODUCT_QUESTION_PATTERNS = [
        "qué incluye",
        "que incluye",
        "cuánto cuesta",
        "cuanto cuesta",
        "precio",
        "cómo funciona",
        "como funciona",
        "qué es",
        "que es",
        "de qué trata",
        "de que trata",
        "contenido",
        "módulos",
        "modulos",
        "duración",
        "duracion",
        "garantía",
        "garantia",
    ]

    # Thanks patterns
    THANKS_PATTERNS = [
        "gracias",
        "muchas gracias",
        "thank",
        "thanks",
        "agradezco",
        "te agradezco",
    ]

    # Goodbye patterns
    GOODBYE_PATTERNS = [
        "adios",
        "adiós",
        "hasta luego",
        "bye",
        "chao",
        "nos vemos",
        "hasta pronto",
    ]

    def __init__(self) -> None:
        """Initialize the intent classifier."""

    # v10.2: New category patterns
    HUMOR_KEYWORDS = ["jaja", "jeje", "ajaj", "😂", "🤣", "gracioso", "morí de risa"]
    REACTION_KEYWORDS = ["que lindo", "hermoso", "bello", "genial", "increíble",
                         "me encanta", "espectacular", "wow", "que bueno"]
    ENCOURAGEMENT_KEYWORDS = ["logré", "conseguí", "pude", "empecé", "terminé",
                              "me fue bien", "cuesta", "difícil", "miedo", "ansiedad"]
    CONTINUATION_KEYWORDS = ["sí", "si", "claro", "dale", "ok", "perfecto",
                             "bueno", "exacto", "totalmente", "tal cual"]
    CASUAL_PATTERNS = ["jaja", "jeje", "😊", "💙", "👍", "🔥"]

    def classify(self, message: str, context: Optional[dict] = None) -> Intent:
        """
        Classify user message intent.

        Enhanced v10.2: reduces "other" from 57% to <20% by adding
        humor, reaction, encouragement, continuation, casual categories.

        Args:
            message: The user message to classify
            context: Optional conversation context for context-aware classification

        Returns:
            Intent enum value representing the classified intent
        """
        if not isinstance(message, str):
            message = str(message) if message else ""

        msg = message.lower().strip()

        if not msg:
            return Intent.OTHER

        # Priority 1: Sales intents (high value)
        if any(pattern in msg for pattern in self.PURCHASE_PATTERNS):
            return Intent.PURCHASE_INTENT

        if any(pattern in msg for pattern in self.PRODUCT_QUESTION_PATTERNS):
            return Intent.PRODUCT_QUESTION

        # Priority 2: Social intents
        if any(pattern in msg for pattern in self.GREETING_PATTERNS):
            return Intent.GREETING

        if any(pattern in msg for pattern in self.THANKS_PATTERNS):
            return Intent.THANKS

        if any(pattern in msg for pattern in self.GOODBYE_PATTERNS):
            return Intent.GOODBYE

        # Priority 3: v10.2 sub-categories (previously all OTHER)
        msg_clean = msg.rstrip("!").rstrip(".").rstrip("?").strip()

        # Continuation: short affirmations
        if len(msg) < 30 and msg_clean in self.CONTINUATION_KEYWORDS:
            return Intent.CONTINUATION

        # Humor: laughs and funny reactions
        if any(kw in msg for kw in self.HUMOR_KEYWORDS):
            return Intent.HUMOR

        # Reaction: positive reactions to something shared
        if any(kw in msg for kw in self.REACTION_KEYWORDS):
            return Intent.REACTION

        # Encouragement: user shares struggle or achievement
        if any(kw in msg for kw in self.ENCOURAGEMENT_KEYWORDS):
            return Intent.ENCOURAGEMENT

        # Casual: short messages with emojis, no substance
        if len(msg) < 40 and "?" not in msg:
            import re
            emoji_count = len(re.findall(
                r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]", msg
            ))
            if emoji_count >= 1 or len(msg) < 15:
                return Intent.CASUAL

        # General question
        if "?" in msg:
            return Intent.QUESTION_GENERAL

        # Default fallback
        return Intent.OTHER
