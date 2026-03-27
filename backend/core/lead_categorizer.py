"""
Lead Categorization Service v2 — Intent-based, universal, bidirectional.

Replaces v1's 40 hardcoded regex patterns with intent-based classification.
Works for any language because it reads the intent from the detection phase
(which is already multilingual via the intent classifier).

Categories:
- NUEVO: Lead that just arrived, no intent signals
- INTERESADO: Shows curiosity, asks general questions
- CALIENTE: Ready to buy, asks about pricing/booking
- CLIENTE: Already purchased
- FANTASMA: No response in 7+ days (bidirectional: re-categorized on new message)
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class LeadCategory(Enum):
    """Sales funnel categories."""
    NUEVO = "nuevo"
    INTERESADO = "interesado"
    CALIENTE = "caliente"
    CLIENTE = "cliente"
    FANTASMA = "fantasma"


@dataclass
class CategoryInfo:
    """Category info for UI."""
    value: str
    label: str
    icon: str
    color: str
    description: str
    action_required: bool


# Frontend category config (unchanged from v1)
CATEGORY_CONFIG: Dict[str, CategoryInfo] = {
    "nuevo": CategoryInfo("nuevo", "Nuevo", "⚪", "#9CA3AF", "Acaba de llegar, el bot está saludando", False),
    "interesado": CategoryInfo("interesado", "Interesado", "🟡", "#F59E0B", "Hace preguntas, quiere saber más", False),
    "caliente": CategoryInfo("caliente", "Caliente", "🔴", "#EF4444", "¡Quiere comprar! Contacta personalmente", True),
    "cliente": CategoryInfo("cliente", "Cliente", "🟢", "#10B981", "Ya compró", False),
    "fantasma": CategoryInfo("fantasma", "Fantasma", "👻", "#6B7280", "No responde hace +7 días", False),
}

# Intents that indicate strong purchase intent → CALIENTE
_HOT_INTENTS = frozenset({
    "interest_strong", "purchase_intent", "purchase", "want_to_buy",
    "question_price", "objection_price",  # asking about price = hot
})

# Intents that indicate soft interest → INTERESADO
_WARM_INTENTS = frozenset({
    "interest_soft", "question_product", "question_general",
    "objection_time", "objection_later", "objection_doubt",
    "objection_works", "objection_not_for_me", "objection_complicated",
    "objection_already_have", "support", "feedback_negative",
})

# Casual intents → no category signal (stays at current level or NUEVO)
_NEUTRAL_INTENTS = frozenset({
    "greeting", "farewell", "thanks", "humor", "continuation",
    "media_share", "pool_response", "other",
})

DAYS_UNTIL_GHOST = 7


def categorize_from_intent(
    intent: str,
    is_customer: bool = False,
    days_since_last_msg: int = 0,
    history_count: int = 0,
) -> Tuple[LeadCategory, float, str]:
    """Categorize a lead based on the detected intent of their current message.

    Universal — works for any language because the intent classifier is
    already multilingual. No regex keyword matching needed.

    Bidirectional: a FANTASMA that sends a new message gets re-categorized
    based on the intent of that message (not stuck in ghost state).

    Args:
        intent: Intent string from detection phase (e.g. "interest_strong")
        is_customer: Whether the lead has already purchased
        days_since_last_msg: Days since last user message (for ghost detection)
        history_count: Total messages in conversation history

    Returns:
        (LeadCategory, score 0-1, reason)
    """
    # 1. CLIENTE — terminal state
    if is_customer:
        return LeadCategory.CLIENTE, 1.0, "Es cliente confirmado"

    # 2. FANTASMA — only if no new message (days > threshold)
    # If the lead IS sending a message right now, they're NOT a ghost anymore
    # (bidirectional: ghost → re-categorize by intent)
    if days_since_last_msg >= DAYS_UNTIL_GHOST:
        return LeadCategory.FANTASMA, 0.1, f"Sin respuesta hace {days_since_last_msg} días"

    # 3. CALIENTE — strong purchase intent
    intent_lower = intent.lower() if intent else ""
    if intent_lower in _HOT_INTENTS:
        score = 0.7 + min(0.3, history_count * 0.02)
        return LeadCategory.CALIENTE, min(1.0, score), f"Intent: {intent}"

    # 4. INTERESADO — soft interest or enough conversation
    if intent_lower in _WARM_INTENTS:
        score = 0.3 + min(0.2, history_count * 0.02)
        return LeadCategory.INTERESADO, score, f"Intent: {intent}"

    # 5. INTERESADO by message volume (3+ messages = active conversation)
    if history_count >= 3:
        return LeadCategory.INTERESADO, 0.25, f"Conversación activa ({history_count} msgs)"

    # 6. NUEVO — default
    return LeadCategory.NUEVO, 0.1, "Sin señales de intención"


def calculate_lead_score(
    intent_history: List[str],
    days_since_last_msg: int = 0,
    is_customer: bool = False,
) -> int:
    """Calculate numeric lead score (0-100) for dashboard and analytics.

    NOT injected in the LLM prompt — this is for the UI only.
    Universal — signals come from intent classifier, not from keywords.

    Args:
        intent_history: List of intent strings from past messages
        days_since_last_msg: Days since last user message
        is_customer: Whether already purchased

    Returns:
        Score 0-100
    """
    if is_customer:
        return 100

    score = 0
    for intent in intent_history:
        il = intent.lower() if intent else ""
        if il in _HOT_INTENTS:
            score += 30
        elif il in _WARM_INTENTS:
            score += 15
        elif il not in _NEUTRAL_INTENTS:
            score += 5

    # Message volume bonus (capped)
    score += min(20, len(intent_history) * 2)

    # Decay for inactivity
    if days_since_last_msg > 0:
        score -= min(score, days_since_last_msg * 3)

    return max(0, min(100, score))


# ─────────────────────────────────────────────────────────────────────
# Legacy compatibility (v1 API — consumed by mega_test_w2.py, helpers.py)
# ─────────────────────────────────────────────────────────────────────

class LeadCategorizer:
    """Legacy wrapper — delegates to categorize_from_intent internally.

    Kept for backward compatibility with get_lead_stage() in helpers.py
    and tests that call categorize(messages, is_customer, ...).
    """

    DAYS_UNTIL_GHOST = DAYS_UNTIL_GHOST

    def categorize(
        self,
        messages: List[Dict],
        is_customer: bool = False,
        last_user_message_time=None,
        last_bot_message_time=None,
    ) -> Tuple[LeadCategory, float, str]:
        from datetime import datetime, timezone

        # Calculate days since last user message
        days = 0
        if last_user_message_time:
            if last_user_message_time.tzinfo is None:
                last_user_message_time = last_user_message_time.replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - last_user_message_time).days
            # Only ghost if last message was from bot (user went silent)
            if last_bot_message_time and last_bot_message_time <= last_user_message_time:
                days = 0  # User responded more recently than bot

        # Extract last intent from user messages
        user_msgs = [m for m in messages if m.get("role") == "user"]
        last_intent = ""
        if user_msgs:
            last_intent = user_msgs[-1].get("intent", "") or ""

        return categorize_from_intent(
            intent=last_intent,
            is_customer=is_customer,
            days_since_last_msg=days,
            history_count=len(user_msgs),
        )


def get_category_from_intent_score(intent_score: float, is_customer: bool = False) -> str:
    """Map legacy intent_score to category string."""
    if is_customer:
        return "cliente"
    if intent_score >= 0.5:
        return "caliente"
    if intent_score >= 0.2:
        return "interesado"
    return "nuevo"


def get_intent_score_from_category(category: str) -> float:
    """Map category to legacy intent_score."""
    return {"nuevo": 0.1, "interesado": 0.35, "caliente": 0.7, "cliente": 1.0, "fantasma": 0.05}.get(category, 0.1)


def map_legacy_status_to_category(status: str) -> str:
    """Map legacy status to new category."""
    return {"new": "nuevo", "cold": "nuevo", "active": "interesado", "warm": "interesado", "hot": "caliente", "customer": "cliente"}.get(status.lower(), "nuevo")


def map_category_to_legacy_status(category: str) -> str:
    """Map new category to legacy status."""
    return {"nuevo": "new", "interesado": "active", "caliente": "hot", "cliente": "customer", "fantasma": "new"}.get(category.lower(), "new")


_lead_categorizer: Optional[LeadCategorizer] = None


def get_lead_categorizer() -> LeadCategorizer:
    """Get singleton LeadCategorizer instance."""
    global _lead_categorizer
    if _lead_categorizer is None:
        _lead_categorizer = LeadCategorizer()
    return _lead_categorizer
