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

    # Pricing (separated from product_question for strategy routing)
    PRICING = "pricing"

    # Feedback
    FEEDBACK_NEGATIVE = "feedback_negative"

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

    # Pricing patterns (separated for strategy routing — strategy.py checks "pricing")
    PRICING_PATTERNS = [
        "cuánto cuesta",
        "cuanto cuesta",
        "cuánto vale",
        "cuanto vale",
        "cuál es el precio",
        "cual es el precio",
        "precio de",
        "cuánto es",
        "cuanto es",
        "me dices el precio",
        "precio",
    ]

    # Product question patterns (content/structure questions, not pricing)
    PRODUCT_QUESTION_PATTERNS = [
        "qué incluye",
        "que incluye",
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

    # Objection patterns
    OBJECTION_PRICE_PATTERNS = [
        "muy caro", "es caro", "demasiado caro", "no me alcanza",
        "no puedo pagarlo", "no tengo ese presupuesto", "fuera de mi presupuesto",
        "mucho dinero", "sale muy caro", "no tengo el dinero",
    ]

    OBJECTION_TIME_PATTERNS = [
        "no tengo tiempo", "no me da tiempo", "no tengo disponibilidad",
        "estoy muy ocupado", "estoy muy ocupada", "no puedo ahora",
        "demasiado tiempo", "no tengo hueco",
    ]

    OBJECTION_DOUBT_PATTERNS = [
        "no sé si", "no se si", "no estoy seguro", "no estoy segura",
        "tengo dudas", "me da miedo que", "funcionará", "no sé si me servirá",
        "no sé si funciona",
    ]

    OBJECTION_LATER_PATTERNS = [
        "lo pienso", "me lo pienso", "lo pensaré", "te aviso",
        "luego te digo", "más adelante", "mas adelante", "en otro momento",
        "ya veré", "ya veremos", "lo considero",
    ]

    OBJECTION_NOT_FOR_ME_PATTERNS = [
        "no creo que sea para mí", "no creo que sea para mi",
        "no es para mí", "no es para mi",
        "no creo que me sirva", "no creo que funcione para mí",
        "no es lo que busco", "no me encaja",
    ]

    # Interest patterns
    INTEREST_STRONG_PATTERNS = [
        "me interesa mucho", "muy interesado", "muy interesada",
        "quiero saber más", "quiero saber mas", "cuéntame más",
        "me interesa bastante", "estoy muy interesado", "estoy muy interesada",
        "me interesa un montón",
    ]

    INTEREST_SOFT_PATTERNS = [
        "suena interesante", "me parece interesante", "me llama la atención",
        "me lo estoy pensando", "podría ser interesante", "no está mal",
    ]

    # Escalation patterns
    ESCALATION_PATTERNS = [
        "quiero hablar con una persona", "hablar con alguien real",
        "con un humano", "con una persona real", "con el creador",
        "quiero que me llames", "prefiero hablar",
        "necesito hablar con alguien",
    ]

    # Support patterns
    SUPPORT_PATTERNS = [
        "no me funciona el acceso", "no funciona el acceso", "no puedo acceder",
        "tengo un problema con", "error en", "no me llega",
        "no puedo entrar", "no aparece el contenido", "no veo el contenido",
        "problema técnico", "tengo un error", "fallo técnico",
    ]

    # Feedback negative patterns
    FEEDBACK_NEGATIVE_PATTERNS = [
        "malísimo", "muy malo", "pésimo", "horrible", "decepcionante",
        "no vale la pena", "no merece la pena", "me ha decepcionado",
        "no cumplió", "no cumple", "una estafa", "mala calidad",
        "muy mal", "fatal",
    ]

    # Booking patterns
    BOOKING_PATTERNS = [
        "reservar", "agendar", "pedir cita", "hacer una cita",
        "cuando tienes disponibilidad", "próxima sesión",
        "próxima cita", "quiero una sesión",
    ]

    # Lead magnet patterns
    LEAD_MAGNET_PATTERNS = [
        "quiero el pdf", "quiero el ebook", "quiero el recurso gratuito",
        "cómo consigo", "como consigo", "quiero descargar",
        "el regalo", "recurso gratis", "el bonus gratuito",
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

        if any(pattern in msg for pattern in self.PRICING_PATTERNS):
            return Intent.PRICING

        if any(pattern in msg for pattern in self.PRODUCT_QUESTION_PATTERNS):
            return Intent.PRODUCT_QUESTION

        # Priority 2: Social intents
        if any(pattern in msg for pattern in self.GREETING_PATTERNS):
            return Intent.GREETING

        if any(pattern in msg for pattern in self.THANKS_PATTERNS):
            return Intent.THANKS

        if any(pattern in msg for pattern in self.GOODBYE_PATTERNS):
            return Intent.GOODBYE

        # Priority 2.5: Objections, interests, escalation, support
        if any(p in msg for p in self.OBJECTION_PRICE_PATTERNS):
            return Intent.OBJECTION_PRICE

        if any(p in msg for p in self.OBJECTION_TIME_PATTERNS):
            return Intent.OBJECTION_TIME

        if any(p in msg for p in self.OBJECTION_DOUBT_PATTERNS):
            return Intent.OBJECTION_DOUBT

        if any(p in msg for p in self.OBJECTION_LATER_PATTERNS):
            return Intent.OBJECTION_LATER

        if any(p in msg for p in self.OBJECTION_NOT_FOR_ME_PATTERNS):
            return Intent.OBJECTION_NOT_FOR_ME

        if any(p in msg for p in self.INTEREST_STRONG_PATTERNS):
            return Intent.INTEREST_STRONG

        if any(p in msg for p in self.INTEREST_SOFT_PATTERNS):
            return Intent.INTEREST_SOFT

        if any(p in msg for p in self.ESCALATION_PATTERNS):
            return Intent.ESCALATION

        if any(p in msg for p in self.SUPPORT_PATTERNS):
            return Intent.SUPPORT

        if any(p in msg for p in self.FEEDBACK_NEGATIVE_PATTERNS):
            return Intent.FEEDBACK_NEGATIVE

        if any(p in msg for p in self.BOOKING_PATTERNS):
            return Intent.BOOKING

        if any(p in msg for p in self.LEAD_MAGNET_PATTERNS):
            return Intent.LEAD_MAGNET

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
