"""
Length Controller - Adaptive response length based on conversation context.

Updated 2026-02-07 from analysis of 2,967 real Stefan messages (PostgreSQL).

KEY FINDING: Response length varies up to 5x by context:
- Objection handling: median 53 chars (longest - needs persuasion)
- General conversation: median 23 chars (baseline)
- Interest signals: median 10 chars (shortest - just acknowledge)

The assumption that Stefan "always responds ~31 chars" is INCORRECT.
These are GUIDELINES, not hard limits. Complete sentences always win.
"""

import logging
import random
import re
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ContextLengthRule:
    """Length guideline for a specific conversation context."""

    target: int  # Median response length (chars) from real data
    soft_min: int  # P10 - 10th percentile
    soft_max: int  # P90 - 90th percentile (normal range ceiling)
    hard_max: int  # P99 - allows outliers when needed
    n_samples: int  # Number of data points backing this rule


# ─────────────────────────────────────────────────────────────────────────────
# Data-driven rules from 2,967 real Stefan messages (2026-02-07 PostgreSQL)
# P10=soft_min, median=target, P90=soft_max, P99=hard_max
# ─────────────────────────────────────────────────────────────────────────────
CONTEXT_LENGTH_RULES: Dict[str, ContextLengthRule] = {
    # Objections need longer, persuasive responses (5x longer than interest!)
    "objecion": ContextLengthRule(target=53, soft_min=10, soft_max=277, hard_max=277, n_samples=9),
    # Price questions: moderate, explain value
    "pregunta_precio": ContextLengthRule(target=22, soft_min=8, soft_max=46, hard_max=162, n_samples=29),
    # Product questions: concise but informative
    "pregunta_producto": ContextLengthRule(target=21, soft_min=7, soft_max=43, hard_max=55, n_samples=50),
    # General questions: quick direct answers
    "pregunta_general": ContextLengthRule(target=17, soft_min=6, soft_max=56, hard_max=101, n_samples=121),
    # Greetings: short and warm
    "saludo": ContextLengthRule(target=17, soft_min=11, soft_max=31, hard_max=44, n_samples=21),
    # Thanks/appreciation: brief acknowledgment
    "agradecimiento": ContextLengthRule(target=22, soft_min=10, soft_max=51, hard_max=705, n_samples=72),
    # Interest signals: shortest - just acknowledge, don't oversell
    "interes": ContextLengthRule(target=10, soft_min=6, soft_max=34, hard_max=61, n_samples=24),
    # Story mentions: short reaction
    "story_mention": ContextLengthRule(target=18, soft_min=8, soft_max=28, hard_max=80, n_samples=55),
    # Casual conversation: relaxed, variable
    "casual": ContextLengthRule(target=18, soft_min=6, soft_max=42, hard_max=73, n_samples=39),
    # Conversation starters (no previous message)
    "inicio_conversacion": ContextLengthRule(target=20, soft_min=8, soft_max=51, hard_max=663, n_samples=161),
    # Default/other: wide range
    "otro": ContextLengthRule(target=23, soft_min=10, soft_max=60, hard_max=569, n_samples=2386),
}

# Default rule for unrecognized contexts
DEFAULT_RULE = ContextLengthRule(target=23, soft_min=10, soft_max=60, hard_max=300, n_samples=0)


# ─── Legacy LengthConfig (backward compatibility) ──────────────────────────

@dataclass
class LengthConfig:
    """Legacy length configuration - kept for backward compatibility."""

    min_length: int = 3
    target_length: int = 23  # Updated: median of all messages
    soft_max: int = 150
    max_for_greeting: int = 31  # Updated: P90 of saludo
    max_for_confirmation: int = 25
    max_for_emotional: int = 277  # Updated: P90 of objecion


# Stefan's configuration (backward-compatible global)
STEFAN_LENGTH_CONFIG = LengthConfig()


# ─── Context Classification ────────────────────────────────────────────────

def classify_lead_context(lead_message: str) -> str:
    """
    Classify the lead's message into a context category for adaptive length.

    This determines HOW LONG Stefan's response should be based on what
    the lead said. More granular than legacy detect_message_type().

    Args:
        lead_message: The message from the lead (user).

    Returns:
        Context category string matching CONTEXT_LENGTH_RULES keys.
    """
    if not lead_message:
        return "inicio_conversacion"

    msg = lead_message.lower().strip()

    # Story mention (Instagram-specific)
    if "mentioned you in their story" in msg or (
        "story" in msg and ("mencion" in msg or "mention" in msg)
    ):
        return "story_mention"

    # Greeting
    greetings = [
        "hola", "hey", "buenas", "que tal", "qué tal",
        "buenos días", "buenos dias", "buenas tardes",
        "buenas noches", "ey", "hi", "hello", "ola",
    ]
    if any(g in msg for g in greetings) and len(msg) < 40:
        return "saludo"

    # Interest (check BEFORE product - "me interesa el programa" is interest, not product inquiry)
    interest_words = [
        "me interesa", "quiero", "necesito", "apuntarme", "inscribirme",
        "contratar", "comprar", "empezar", "unirme", "matricularme",
        "me apunto", "lo quiero", "dónde pago", "donde pago",
        "cómo pago", "como pago", "link", "enlace",
    ]
    if any(w in msg for w in interest_words):
        return "interes"

    # Price question
    price_words = [
        "cuánto", "cuanto", "precio", "cuesta", "vale", "tarifa",
        "coste", "cost", "pagar", "inversión", "inversion",
        "descuento", "oferta", "euros", "€", "dolares", "$",
    ]
    if any(w in msg for w in price_words):
        return "pregunta_precio"

    # Product question
    product_words = [
        "qué incluye", "que incluye", "cómo funciona", "como funciona",
        "qué es", "que es", "información", "informacion", "info",
        "detalles", "contenido", "curso", "programa", "sesión", "sesion",
        "formación", "formacion", "coaching", "mentoría", "mentoria",
        "masterclass", "servicio", "asesoría", "asesoria",
    ]
    if any(w in msg for w in product_words):
        return "pregunta_producto"

    # Objection
    objection_words = [
        "caro", "no puedo", "no sé si", "no se si", "dudas", "pensarlo",
        "pensármelo", "pensar", "mucho dinero", "presupuesto",
        "no me convence", "no creo", "complicado", "difícil", "dificil",
    ]
    if any(w in msg for w in objection_words) and len(msg) > 10:
        return "objecion"

    # Thanks / appreciation
    thanks_words = [
        "gracias", "genial", "perfecto", "increíble", "increible",
        "muchas gracias", "mil gracias", "te agradezco", "agradecido",
        "thanks", "thank",
    ]
    if any(w in msg for w in thanks_words):
        return "agradecimiento"

    # Casual / informal (emojis, laughs)
    casual_score = 0
    if re.search(r"jaj|hah|jej|😂|🤣", msg):
        casual_score += 1
    if len(msg) < 15:
        casual_score += 1
    emoji_count = len(re.findall(r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]", msg))
    if emoji_count >= 2:
        casual_score += 1
    if casual_score >= 2 or (len(msg) < 8 and emoji_count >= 1):
        return "casual"

    # Generic question
    if "?" in lead_message:
        return "pregunta_general"

    return "otro"


def get_context_rule(context: str) -> ContextLengthRule:
    """Get the length rule for a conversation context."""
    return CONTEXT_LENGTH_RULES.get(context, DEFAULT_RULE)


# ─── Original API (backward compatible) ────────────────────────────────────

def detect_message_type(lead_message: str) -> str:
    """
    Classify lead message context for adaptive length.

    Backward-compatible: callers that used the old return values
    ('greeting', 'confirmation', etc.) will get the new context names instead.
    The new names are used throughout CONTEXT_LENGTH_RULES.
    """
    return classify_lead_context(lead_message)


def get_soft_max(message_type: str, config: Optional[LengthConfig] = None) -> int:
    """Get soft max length based on context (P90 from real data)."""
    rule = get_context_rule(message_type)
    return rule.soft_max


def enforce_length(
    response: str,
    lead_message: str,
    config: Optional[LengthConfig] = None,
    context: Optional[str] = None,
) -> str:
    """
    Adaptive length enforcement based on conversation context.

    Uses real data from 2,967 messages. NEVER truncates mid-sentence.
    Only trims at sentence boundaries when response significantly exceeds
    the hard_max for its context type.

    Args:
        response: Generated response.
        lead_message: Original lead message.
        config: Legacy config (kept for backward compatibility).
        context: Optional pre-classified context. Auto-detects if None.

    Returns:
        Response, possibly shortened but always complete sentences.
    """
    if context is None:
        context = classify_lead_context(lead_message)

    rule = get_context_rule(context)
    resp_len = len(response)

    # Never truncate if within observed hard_max for this context
    if resp_len <= rule.hard_max:
        return response

    # Allow 1.5x headroom above hard_max (bot may need more than Stefan)
    headroom = max(int(rule.hard_max * 1.5), 200)
    if resp_len <= headroom:
        return response

    # Response is excessively long for this context - trim at sentence boundary
    trim_at = headroom
    for boundary in ["! ", "? ", ". ", "!\n", "?\n", ".\n"]:
        idx = response[:trim_at].rfind(boundary)
        if idx > rule.soft_max:
            return response[: idx + 1].strip()

    # No sentence boundary found - return as-is rather than cut mid-sentence
    return response


# ─── New: Length Guidance for LLM Prompts ──────────────────────────────────

def get_length_guidance_prompt(lead_message: str, context: Optional[str] = None) -> str:
    """
    Generate a length guidance instruction for the LLM prompt.

    Instead of truncating AFTER generation, this guides the LLM BEFORE
    generation to produce responses of the right length for context.

    Args:
        lead_message: The message from the lead.
        context: Optional pre-classified context.

    Returns:
        A string instruction to embed in the LLM system prompt.
    """
    if context is None:
        context = classify_lead_context(lead_message)

    rule = get_context_rule(context)

    # Map context to natural language description
    context_descriptions = {
        "objecion": "handling an objection - explain value convincingly",
        "pregunta_precio": "answering a price question - be clear and direct",
        "pregunta_producto": "answering a product question - concise but informative",
        "pregunta_general": "answering a general question - quick direct answer",
        "saludo": "responding to a greeting - short and warm",
        "agradecimiento": "acknowledging thanks - brief and genuine",
        "interes": "lead shows interest - just confirm/acknowledge, don't oversell",
        "story_mention": "reacting to a story mention - short warm reaction",
        "casual": "casual chat - relaxed, natural length",
        "inicio_conversacion": "starting a conversation - moderate friendly opener",
        "otro": "normal conversation - keep it natural and concise",
    }

    description = context_descriptions.get(context, "normal conversation")

    return (
        f"[Length: You're {description}. "
        f"Target ~{rule.target} chars (range {rule.soft_min}-{rule.soft_max}). "
        f"Complete sentences always win over length targets.]"
    )


# ─── Short Predefined Responses ────────────────────────────────────────────

SHORT_REPLACEMENTS = {
    # New context-based keys
    "saludo": ["Ey! 😊", "Buenas!", "Hola!", "Hey!", "Qué tal!", "👋"],
    "agradecimiento": ["A ti!", "Nada!", "😊", "💙", "De nada!", "Gracias a ti!"],
    "casual": ["Jaja", "Jajaja", "😂", "🤣", "Jeje", "😊", "💙"],
    # Legacy keys (backward compatibility for callers using old type names)
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
