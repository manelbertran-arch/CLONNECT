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
        pass

    def classify(self, message: str, context: Optional[dict] = None) -> Intent:
        """
        Classify user message intent.

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

        # Check purchase intent first (high priority)
        if any(pattern in msg for pattern in self.PURCHASE_PATTERNS):
            return Intent.PURCHASE_INTENT

        # Check product questions
        if any(pattern in msg for pattern in self.PRODUCT_QUESTION_PATTERNS):
            return Intent.PRODUCT_QUESTION

        # Check greetings
        if any(pattern in msg for pattern in self.GREETING_PATTERNS):
            return Intent.GREETING

        # Check thanks
        if any(pattern in msg for pattern in self.THANKS_PATTERNS):
            return Intent.THANKS

        # Check goodbye
        if any(pattern in msg for pattern in self.GOODBYE_PATTERNS):
            return Intent.GOODBYE

        # Default fallback
        return Intent.OTHER
