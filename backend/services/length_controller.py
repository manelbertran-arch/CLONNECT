"""
Length Controller - Adaptive response length based on conversation context.

Per-creator length rules loaded from calibration files. When no calibration
exists for a creator, length enforcement is skipped entirely (zero hardcoding).

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


# No default rules — all thresholds MUST come from per-creator calibration data.
# When no calibration exists, length enforcement is skipped entirely.
DEFAULT_LENGTH_RULES: Dict[str, ContextLengthRule] = {}

# Backward-compatible alias
CONTEXT_LENGTH_RULES = DEFAULT_LENGTH_RULES

# Default rule: None signals "no data available, skip enforcement"
DEFAULT_RULE: Optional[ContextLengthRule] = None

# Per-creator rules cache: creator_id -> Dict[str, ContextLengthRule]
_creator_rules_cache: Dict[str, Dict[str, ContextLengthRule]] = {}


def load_creator_length_rules(creator_id: str) -> Dict[str, ContextLengthRule]:
    """Load per-creator length rules from calibration file.

    Reads calibration.baseline and calibration.context_soft_max to build
    creator-specific ContextLengthRule instances. Falls back to DEFAULT_LENGTH_RULES
    for creators without calibration data.

    Results are cached in-memory.
    """
    if creator_id in _creator_rules_cache:
        return _creator_rules_cache[creator_id]

    try:
        from services.calibration_loader import load_calibration

        cal = load_calibration(creator_id)
        if not cal:
            logger.warning("length_controller: no calibration for %s, skipping length enforcement", creator_id)
            _creator_rules_cache[creator_id] = {}
            return {}

        baseline = cal.get("baseline", {})
        context_maxes = cal.get("context_soft_max", {})

        if not baseline and not context_maxes:
            logger.warning("length_controller: no baseline/context data for %s, skipping", creator_id)
            _creator_rules_cache[creator_id] = {}
            return {}

        # Global baseline from calibration (creator's own data)
        global_median = baseline.get("median_length")
        global_soft_max = baseline.get("soft_max")

        if global_median is None:
            logger.warning("length_controller: no median_length in calibration for %s, skipping", creator_id)
            _creator_rules_cache[creator_id] = {}
            return {}

        if global_soft_max is None:
            global_soft_max = int(global_median * 3)  # derived from creator's own median

        # Build rules from context_maxes (creator's own per-context data)
        rules = {}
        for ctx, sm in context_maxes.items():
            if sm is not None:
                rules[ctx] = ContextLengthRule(
                    target=min(int(sm * 0.6), sm),
                    soft_min=max(3, int(sm * 0.15)),
                    soft_max=sm,
                    hard_max=int(sm * 1.5),
                    n_samples=0,
                )

        # Map calibration context names to length_controller context names
        cal_to_lc = {
            "precio": "pregunta_precio",
            "lead_caliente": "interes",
            "personal": "casual",
            "clase": "casual",
        }
        for cal_ctx, lc_ctx in cal_to_lc.items():
            if cal_ctx in context_maxes:
                sm = context_maxes[cal_ctx]
                rules[lc_ctx] = ContextLengthRule(
                    target=min(int(sm * 0.6), sm),
                    soft_min=max(3, int(sm * 0.15)),
                    soft_max=sm,
                    hard_max=int(sm * 1.5),
                    n_samples=0,
                )

        # Add a fallback "otro" rule from global baseline if not present
        if "otro" not in rules:
            rules["otro"] = ContextLengthRule(
                target=global_median,
                soft_min=max(3, int(global_median * 0.3)),
                soft_max=global_soft_max,
                hard_max=int(global_soft_max * 1.5),
                n_samples=0,
            )

        _creator_rules_cache[creator_id] = rules
        logger.info(
            "Loaded creator length rules for %s: %d contexts, global_median=%s",
            creator_id, len(rules), global_median,
        )
        return rules

    except Exception as e:
        logger.debug("Failed to load creator length rules for %s: %s", creator_id, e)
        _creator_rules_cache[creator_id] = {}
        return {}

# v10.2: Aliases for new sub-categories that inherit from existing contexts
CONTEXT_ALIASES = {
    "humor": "casual",
    "reaccion": "casual",
    "reaction": "casual",
    "apoyo_emocional": "otro",
    "encouragement": "otro",
    "compartir_logro": "otro",
    "continuacion": "casual",
    "continuation": "casual",
    "gratitude": "agradecimiento",
    "greeting": "saludo",
}


# ─── Legacy LengthConfig (backward compatibility) ──────────────────────────

@dataclass
class LengthConfig:
    """Legacy length configuration - kept for backward compatibility.
    Values are unused — all thresholds come from per-creator calibration.
    """
    min_length: int = 3
    target_length: int = 0
    soft_max: int = 0
    max_for_greeting: int = 0
    max_for_confirmation: int = 0
    max_for_emotional: int = 0


# ─── Context Classification ────────────────────────────────────────────────

def classify_lead_context(lead_message: str) -> str:
    """
    Classify the lead's message into a context category for adaptive length.

    This determines HOW LONG the creator's response should be based on what
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

    # Greeting (use word boundaries for short words to avoid "hi" matching "coaching")
    greeting_phrases = [
        "hola", "hey", "buenas", "que tal", "qué tal",
        "buenos días", "buenos dias", "buenas tardes",
        "buenas noches", "hello",
    ]
    greeting_short = ["ey", "hi", "ola"]  # Need word-boundary check
    is_greeting = any(g in msg for g in greeting_phrases)
    if not is_greeting:
        is_greeting = any(re.search(rf"\b{g}\b", msg) for g in greeting_short)
    if is_greeting and len(msg) < 40:
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
    # Guard: messages with "?" are questions, not thanks (e.g. "suena genial, ¿cuál?")
    thanks_words = [
        "gracias", "genial", "perfecto", "increíble", "increible",
        "muchas gracias", "mil gracias", "te agradezco", "agradecido",
        "thanks", "thank",
    ]
    if any(w in msg for w in thanks_words):
        if "?" not in msg or len(msg) < 30:
            return "agradecimiento"

    # Humor (v10.2) — laughs and funny reactions
    if re.search(r"jaj|hah|jej|😂|🤣", msg):
        return "humor"

    # Reaction (v10.2) — positive reactions
    reaction_words = [
        "que lindo", "hermoso", "genial", "espectacular",
        "increíble", "increible", "me encanta", "que bueno", "wow",
    ]
    if any(w in msg for w in reaction_words):
        return "reaccion"

    # Continuation (v10.2) — short affirmations
    continuations = ["sí", "si", "claro", "dale", "ok", "bueno", "exacto", "totalmente", "tal cual"]
    msg_stripped = msg.rstrip("!").rstrip(".").strip()
    if msg_stripped in continuations and len(msg) < 30:
        return "continuacion"

    # Encouragement (v10.2) — user shares struggle or achievement
    encourage_words = [
        "logré", "conseguí", "pude", "empecé", "terminé",
        "cuesta", "difícil", "dificil", "miedo", "ansiedad",
    ]
    if any(w in msg for w in encourage_words):
        return "apoyo_emocional"

    # Casual / informal (emojis, short)
    casual_score = 0
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

    # Short messages without question marks (v10.2) — reduce "otro"
    if len(msg) < 40 and "?" not in msg:
        return "casual"

    return "otro"


def get_context_rule(context: str, creator_id: Optional[str] = None) -> Optional[ContextLengthRule]:
    """Get the length rule for a conversation context.

    When creator_id is provided, uses per-creator rules from calibration.
    Returns None if no calibration data exists for this creator/context.
    """
    rules = load_creator_length_rules(creator_id) if creator_id else {}
    if not rules:
        return None
    if context in rules:
        return rules[context]
    # Check aliases for sub-categories
    alias = CONTEXT_ALIASES.get(context)
    if alias and alias in rules:
        return rules[alias]
    # Fall back to "otro" if available (derived from creator's global median)
    return rules.get("otro")


# ─── Original API (backward compatible) ────────────────────────────────────

def detect_message_type(lead_message: str) -> str:
    """
    Classify lead message context for adaptive length.

    Backward-compatible: callers that used the old return values
    ('greeting', 'confirmation', etc.) will get the new context names instead.
    The new names are used throughout CONTEXT_LENGTH_RULES.
    """
    return classify_lead_context(lead_message)


def get_soft_max(message_type: str, config: Optional[LengthConfig] = None, creator_id: Optional[str] = None) -> Optional[int]:
    """Get soft max length based on context. Returns None if no data."""
    rule = get_context_rule(message_type, creator_id=creator_id)
    return rule.soft_max if rule else None


def enforce_length(
    response: str,
    lead_message: str,
    config: Optional[LengthConfig] = None,
    context: Optional[str] = None,
    creator_id: Optional[str] = None,
) -> str:
    """
    Adaptive length enforcement based on conversation context.

    Uses per-creator rules from calibration when creator_id is provided,
    falls back to defaults. NEVER truncates mid-sentence. Only trims at
    sentence boundaries when response significantly exceeds hard_max.

    Args:
        response: Generated response.
        lead_message: Original lead message.
        config: Legacy config (kept for backward compatibility).
        context: Optional pre-classified context. Auto-detects if None.
        creator_id: Optional creator ID for per-creator length rules.

    Returns:
        Response, possibly shortened but always complete sentences.
    """
    # ARC4: kill switch for shadow testing — DISABLE_M6_NORMALIZE_LENGTH=true skips enforcement
    import os
    if os.getenv("DISABLE_M6_NORMALIZE_LENGTH", "false").lower() == "true":
        return response

    if context is None:
        context = classify_lead_context(lead_message)

    rule = get_context_rule(context, creator_id=creator_id)

    # No calibration data → skip length enforcement entirely
    if rule is None:
        logger.warning("length_controller: no percentiles in profile for %s, skipping", creator_id or "unknown")
        return response

    resp_len = len(response)

    # Never truncate if within observed hard_max for this context
    if resp_len <= rule.hard_max:
        return response

    # Allow headroom above hard_max (proportional to creator's data)
    headroom = int(rule.hard_max * 1.5)
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

def get_length_guidance_prompt(
    lead_message: str, context: Optional[str] = None, creator_id: Optional[str] = None,
) -> str:
    """
    Generate a length guidance instruction for the LLM prompt.

    Instead of truncating AFTER generation, this guides the LLM BEFORE
    generation to produce responses of the right length for context.

    Args:
        lead_message: The message from the lead.
        context: Optional pre-classified context.
        creator_id: Optional creator ID for per-creator length rules.

    Returns:
        A string instruction to embed in the LLM system prompt.
    """
    if context is None:
        context = classify_lead_context(lead_message)

    rule = get_context_rule(context, creator_id=creator_id)

    if rule is None:
        return ""  # No calibration data → no length guidance

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

    # v10.2: Check aliases for sub-categories (e.g., "humor" -> "casual")
    resolved = CONTEXT_ALIASES.get(context, context)
    description = context_descriptions.get(context) or context_descriptions.get(resolved, "normal conversation")

    return (
        f"[Length: You're {description}. "
        f"Target ~{rule.target} chars (range {rule.soft_min}-{rule.soft_max}). "
        "Complete sentences always win over length targets.]"
    )


# ─── Short Predefined Responses ────────────────────────────────────────────
# No hardcoded lists — loaded from creator's calibration short_response_pool.

# Cache: creator_id -> {context: [responses]}
_short_replacement_cache: Dict[str, Dict] = {}


def _load_short_replacements(creator_id: str) -> Dict[str, list]:
    """Load short response pool from creator's calibration data."""
    if creator_id in _short_replacement_cache:
        return _short_replacement_cache[creator_id]

    pool: Dict[str, list] = {}
    try:
        from services.calibration_loader import load_calibration
        cal = load_calibration(creator_id)
        if cal:
            # Try dedicated short_response_pool first
            raw_pool = cal.get("short_response_pool", {})
            if isinstance(raw_pool, dict):
                pool = raw_pool
            elif isinstance(raw_pool, list):
                pool = {"default": raw_pool}
            # Fallback: extract short responses from few-shot examples
            if not pool:
                examples = cal.get("few_shot_examples", [])
                for ex in examples:
                    resp = ex.get("response", "").strip()
                    if resp and len(resp) < 20:
                        ctx = ex.get("context", "default")
                        pool.setdefault(ctx, []).append(resp)
    except Exception as e:
        logger.debug("_load_short_replacements: failed for %s: %s", creator_id, e)

    _short_replacement_cache[creator_id] = pool
    return pool


def get_short_replacement(message_type: str, creator_id: Optional[str] = None) -> Optional[str]:
    """Get a short predefined response for the message type from creator data."""
    if not creator_id:
        return None
    pool = _load_short_replacements(creator_id)
    if not pool:
        return None
    options = pool.get(message_type, pool.get("default", []))
    return random.choice(options) if options else None
