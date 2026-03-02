"""
Confidence Scorer — Multi-factor confidence scoring for copilot suggestions.

Factors (weights sum to 1.0):
  - intent_confidence (0.30): How clear is the user's intent?
  - response_type (0.20): Pool match vs LLM generation vs edge case
  - historical_rate (0.30): Creator's historical approval rate for similar intents
  - length_quality (0.10): Is response length appropriate?
  - blacklist_check (0.10): Does response contain known bad patterns?
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Intent → base confidence mapping (all lowercase keys)
_INTENT_SCORES = {
    "greeting": 0.95,
    "interest_soft": 0.80,
    "interest_strong": 0.75,
    "question_product": 0.70,
    "question_general": 0.65,
    "purchase": 0.60,
    "objection": 0.55,
    "booking": 0.65,
    "follow_up": 0.70,
    "sensitive_content": 0.30,
    "edge_case_escalation": 0.25,
    "pool_response": 0.85,
    "other": 0.50,
    "error": 0.0,
}

# Response type → confidence
_RESPONSE_TYPE_SCORES = {
    "pool_match": 0.90,       # Pre-approved template
    "llm_generation": 0.70,   # LLM-generated
    "edge_escalation": 0.30,  # Edge case fallback
    "error_fallback": 0.05,   # Error
}

# Blacklisted patterns that reduce confidence
_BLACKLIST_PATTERNS = [
    re.compile(r"(?:soy|me llamo)\s+\w+", re.IGNORECASE),          # Identity claim
    re.compile(r"COMPRA\s+AHORA", re.IGNORECASE),                   # Raw CTA
    re.compile(r"://www\.", re.IGNORECASE),                          # Broken link
    re.compile(r"ERROR:", re.IGNORECASE),                            # Error leak
    re.compile(r"(?:TypeError|ValueError|KeyError)", re.IGNORECASE), # Exception leak
    re.compile(r"qu[eé]\s+te\s+llam[oó]\s+la\s+atenci[oó]n", re.IGNORECASE),  # Catchphrase
]


def calculate_confidence(
    intent: str,
    response_text: str,
    response_type: str = "llm_generation",
    creator_id: Optional[str] = None,
) -> float:
    """
    Calculate multi-factor confidence score for a bot suggestion.

    Args:
        intent: Detected user intent (greeting, interest_soft, etc.)
        response_text: The bot's suggested response text
        response_type: How the response was generated (pool_match, llm_generation, etc.)
        creator_id: Optional creator ID for historical rate lookup

    Returns:
        Confidence score between 0.0 and 1.0
    """
    if not response_text:
        return 0.0

    # Factor 1: Intent confidence (weight 0.30)
    intent_key = (intent or "other").lower().replace("intent.", "")
    intent_score = _INTENT_SCORES.get(intent_key, 0.50)

    # Factor 2: Response type (weight 0.20)
    type_score = _RESPONSE_TYPE_SCORES.get(response_type, 0.70)

    # Factor 3: Historical approval rate (weight 0.30)
    historical_score = _get_historical_rate(creator_id, intent_key)

    # Factor 4: Length quality (weight 0.10)
    length_score = _score_length(response_text)

    # Factor 5: Blacklist check (weight 0.10)
    blacklist_score = _score_blacklist(response_text)

    # Weighted sum
    confidence = (
        0.30 * intent_score
        + 0.20 * type_score
        + 0.30 * historical_score
        + 0.10 * length_score
        + 0.10 * blacklist_score
    )

    return round(min(1.0, max(0.0, confidence)), 3)


def _get_historical_rate(creator_id: Optional[str], intent: str) -> float:
    """
    Get historical approval rate for this creator + intent combination.
    Falls back to 0.7 (neutral) if no data available.
    """
    if not creator_id:
        return 0.70

    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message

        session = SessionLocal()
        try:
            creator = session.query(Creator.id).filter_by(name=creator_id).first()
            if not creator:
                return 0.70

            # Count approved vs total for this intent in last 30 days
            from datetime import datetime, timedelta, timezone

            since = datetime.now(timezone.utc) - timedelta(days=30)

            total = (
                session.query(Message.id)
                .join(Lead, Message.lead_id == Lead.id)
                .filter(
                    Lead.creator_id == creator[0],
                    Message.role == "assistant",
                    Message.copilot_action.isnot(None),
                    Message.intent == intent,
                    Message.created_at >= since,
                )
                .count()
            )

            if total < 5:
                return 0.70  # Not enough data, use neutral

            approved = (
                session.query(Message.id)
                .join(Lead, Message.lead_id == Lead.id)
                .filter(
                    Lead.creator_id == creator[0],
                    Message.role == "assistant",
                    Message.copilot_action.in_(["approved", "edited"]),
                    Message.intent == intent,
                    Message.created_at >= since,
                )
                .count()
            )

            return round(approved / total, 3)
        finally:
            session.close()
    except Exception as e:
        logger.debug(f"[ConfidenceScorer] Historical rate lookup failed: {e}")
        return 0.70


def _score_length(text: str) -> float:
    """Score response length quality. Ideal: 20-200 chars."""
    length = len(text)
    if length < 5:
        return 0.1
    if length < 20:
        return 0.5
    if length <= 200:
        return 1.0
    if length <= 400:
        return 0.7
    return 0.4  # Very long responses are suspicious


def _score_blacklist(text: str) -> float:
    """Score based on blacklisted patterns. 1.0 = clean, 0.0 = many matches."""
    matches = sum(1 for p in _BLACKLIST_PATTERNS if p.search(text))
    if matches == 0:
        return 1.0
    if matches == 1:
        return 0.5
    return 0.1


def get_historical_rates(creator_id: str) -> dict:
    """
    Get historical approval rates by intent for a creator.
    Used by the confidence calibration and autolearning engine.
    """
    try:
        from sqlalchemy import func

        from api.database import SessionLocal
        from api.models import Creator, Lead, Message

        session = SessionLocal()
        try:
            creator = session.query(Creator.id).filter_by(name=creator_id).first()
            if not creator:
                return {"rates": {}, "total_actions": 0}

            from datetime import datetime, timedelta, timezone

            since = datetime.now(timezone.utc) - timedelta(days=30)

            # Get action counts by intent
            rows = (
                session.query(
                    Message.intent,
                    Message.copilot_action,
                    func.count().label("cnt"),
                )
                .join(Lead, Message.lead_id == Lead.id)
                .filter(
                    Lead.creator_id == creator[0],
                    Message.role == "assistant",
                    Message.copilot_action.isnot(None),
                    Message.created_at >= since,
                )
                .group_by(Message.intent, Message.copilot_action)
                .limit(50)
                .all()
            )

            # Build per-intent rates
            intent_data: dict = {}
            for intent, action, count in rows:
                key = intent or "unknown"
                if key not in intent_data:
                    intent_data[key] = {"approved": 0, "edited": 0, "discarded": 0, "manual": 0, "total": 0}
                if action == "approved":
                    intent_data[key]["approved"] += count
                elif action == "edited":
                    intent_data[key]["edited"] += count
                elif action == "discarded":
                    intent_data[key]["discarded"] += count
                elif action == "manual_override":
                    intent_data[key]["manual"] += count
                intent_data[key]["total"] += count

            rates = {}
            total = 0
            for intent, data in intent_data.items():
                if data["total"] > 0:
                    rates[intent] = {
                        "approval_rate": round((data["approved"] + data["edited"]) / data["total"], 3),
                        "edit_rate": round(data["edited"] / data["total"], 3),
                        "discard_rate": round(data["discarded"] / data["total"], 3),
                        "total": data["total"],
                    }
                    total += data["total"]

            return {"rates": rates, "total_actions": total}
        finally:
            session.close()
    except Exception as e:
        logger.error(f"[ConfidenceScorer] Error getting historical rates: {e}")
        return {"rates": {}, "total_actions": 0}
