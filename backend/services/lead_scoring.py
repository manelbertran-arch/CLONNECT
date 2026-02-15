"""
Comprehensive lead scoring service.

Replaces the broken single-intent scoring with a multi-factor approach
that considers message count, engagement ratio, recency, content signals,
and classified intents.

Scoring factors (0-100 scale, stored as 0.0-1.0 in purchase_intent):
  - Message count:     max 30 pts  (+2 per message)
  - Recency:           max 15 pts  (based on days since last contact)
  - Engagement ratio:  max 20 pts  (user messages / total messages)
  - Intent signals:    max 20 pts  (from classified intents)
  - Content signals:   max 15 pts  (keyword analysis of recent messages)

Status thresholds (Spanish, matching frontend):
  - score >= 70  → "caliente"
  - score >= 40  → "interesado"
  - score >= 0   → "nuevo"
  - last_contact > 14 days AND score < 30 → "fantasma"
"""

import logging
import re
from datetime import datetime, timezone
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# --- Purchase keywords (Spanish + English) ---
PURCHASE_KEYWORDS = [
    "precio", "cuánto", "cuanto", "cuesta", "comprar", "pagar",
    "contratar", "reservar", "agendar", "inscribirme", "quiero comprar",
    "cómo pago", "como pago", "método de pago", "transferencia",
    "price", "cost", "buy", "purchase", "book", "pay",
]

INTEREST_KEYWORDS = [
    "me interesa", "quiero", "necesito", "me gustaría", "cuéntame más",
    "cómo funciona", "como funciona", "qué incluye", "que incluye",
    "info", "información", "detalles", "interesado", "interesada",
    "interested", "tell me more", "how does it work",
]

ENGAGEMENT_KEYWORDS = [
    "gracias", "genial", "increíble", "me encanta", "buenísimo",
    "excelente", "perfecto", "vale", "dale", "vamos",
    "thanks", "great", "amazing", "love it", "perfect",
]

NEGATIVE_KEYWORDS = [
    "no me interesa", "no puedo", "caro", "muy caro", "no gracias",
    "después", "luego", "ahora no", "no tengo",
    "not interested", "too expensive", "can't afford",
]

# --- Intent score mappings ---
INTENT_SCORES = {
    "purchase": 20,
    "interest_strong": 18,
    "interest_soft": 12,
    "question_product": 10,
    "product_question": 10,
    "thanks": 5,
    "greeting": 3,
    "casual": 2,
    "pool_response": 2,
    "other": 1,
    "objection": -5,
    "support": 5,
}


def recalculate_lead_score(session, lead_id: str) -> Optional[Tuple[float, str]]:
    """
    Recalculate a lead's score based on all available evidence.

    Args:
        session: SQLAlchemy session
        lead_id: Lead UUID

    Returns:
        Tuple of (purchase_intent 0-1, status string) or None if lead not found
    """
    from api.models import Lead, Message

    lead = session.query(Lead).filter_by(id=lead_id).first()
    if not lead:
        return None

    # --- Gather data ---
    total_messages = (
        session.query(Message)
        .filter(Message.lead_id == lead.id)
        .count()
    )

    user_messages = (
        session.query(Message)
        .filter(Message.lead_id == lead.id, Message.role == "user")
        .count()
    )

    # Get classified intents
    intent_rows = (
        session.query(Message.intent)
        .filter(
            Message.lead_id == lead.id,
            Message.intent.isnot(None),
            Message.intent != "",
        )
        .all()
    )
    intents = [r[0] for r in intent_rows]

    # Get recent user messages for content analysis (last 20)
    recent_user_msgs = (
        session.query(Message.content)
        .filter(
            Message.lead_id == lead.id,
            Message.role == "user",
            Message.content.isnot(None),
            Message.content != "",
        )
        .order_by(Message.created_at.desc())
        .limit(20)
        .all()
    )
    recent_texts = [r[0].lower() for r in recent_user_msgs if r[0]]

    # --- Calculate score components ---
    score = 0

    # 1. Message count (max 30 pts: +2 per message, capped)
    msg_score = min(30, total_messages * 2)
    score += msg_score

    # 2. Recency (max 15 pts)
    recency_score = 0
    if lead.last_contact_at:
        if hasattr(lead.last_contact_at, "tzinfo") and lead.last_contact_at.tzinfo is None:
            last_contact = lead.last_contact_at.replace(tzinfo=timezone.utc)
        else:
            last_contact = lead.last_contact_at
        days_since = (datetime.now(timezone.utc) - last_contact).days
        if days_since <= 1:
            recency_score = 15
        elif days_since <= 3:
            recency_score = 12
        elif days_since <= 7:
            recency_score = 10
        elif days_since <= 14:
            recency_score = 5
        elif days_since <= 30:
            recency_score = 2
        else:
            recency_score = -5
    score += recency_score

    # 3. Engagement ratio (max 20 pts)
    engagement_score = 0
    if total_messages > 0 and user_messages > 0:
        ratio = user_messages / total_messages
        if ratio >= 0.5:
            engagement_score = 20
        elif ratio >= 0.4:
            engagement_score = 15
        elif ratio >= 0.3:
            engagement_score = 10
        elif ratio >= 0.2:
            engagement_score = 5
    score += engagement_score

    # 4. Intent signals (max 20 pts — take the best intent signal)
    intent_score = 0
    for intent in intents:
        intent_key = (intent or "").lower().strip()
        pts = INTENT_SCORES.get(intent_key, 0)
        if pts > intent_score:
            intent_score = pts
    intent_score = min(20, intent_score)
    score += intent_score

    # 5. Content signals (max 15 pts — scan recent user messages)
    content_score = 0
    has_purchase = False
    has_interest = False
    has_engagement = False
    has_negative = False

    for text in recent_texts:
        if any(kw in text for kw in PURCHASE_KEYWORDS):
            has_purchase = True
        if any(kw in text for kw in INTEREST_KEYWORDS):
            has_interest = True
        if any(kw in text for kw in ENGAGEMENT_KEYWORDS):
            has_engagement = True
        if any(kw in text for kw in NEGATIVE_KEYWORDS):
            has_negative = True

    if has_purchase:
        content_score += 15
    elif has_interest:
        content_score += 10
    elif has_engagement:
        content_score += 5

    if has_negative:
        content_score -= 5

    content_score = max(0, min(15, content_score))
    score += content_score

    # --- Clamp 0-100 ---
    score = max(0, min(100, score))

    # --- Determine status ---
    days_since_contact = 999
    if lead.last_contact_at:
        if hasattr(lead.last_contact_at, "tzinfo") and lead.last_contact_at.tzinfo is None:
            last_contact = lead.last_contact_at.replace(tzinfo=timezone.utc)
        else:
            last_contact = lead.last_contact_at
        days_since_contact = (datetime.now(timezone.utc) - last_contact).days

    # Keep "cliente" status if already set
    if lead.status == "cliente":
        new_status = "cliente"
    elif days_since_contact >= 14 and score < 30:
        new_status = "fantasma"
    elif score >= 70:
        new_status = "caliente"
    elif score >= 40:
        new_status = "interesado"
    else:
        new_status = "nuevo"

    # --- Update lead ---
    purchase_intent = score / 100.0
    lead.purchase_intent = purchase_intent
    lead.score = score
    lead.status = new_status

    logger.info(
        f"[SCORING] {lead.username or lead.platform_user_id}: "
        f"score={score} (msgs={msg_score}, recency={recency_score}, "
        f"engage={engagement_score}, intent={intent_score}, content={content_score}) "
        f"→ status={new_status}"
    )

    return purchase_intent, new_status


def batch_recalculate_scores(session, creator_id: str) -> dict:
    """
    Recalculate scores for all leads of a creator.

    Args:
        session: SQLAlchemy session
        creator_id: Creator UUID

    Returns:
        Dict with results summary
    """
    from api.models import Creator, Lead

    # Try by name first (most common), then by UUID
    creator = session.query(Creator).filter_by(name=creator_id).first()
    if not creator:
        try:
            creator = session.query(Creator).filter_by(id=creator_id).first()
        except Exception:
            pass
    if not creator:
        return {"error": f"Creator {creator_id} not found"}

    leads = session.query(Lead).filter_by(creator_id=creator.id).all()

    results = {"total": len(leads), "updated": 0, "by_status": {}}

    for lead in leads:
        result = recalculate_lead_score(session, str(lead.id))
        if result:
            results["updated"] += 1
            _, status = result
            results["by_status"][status] = results["by_status"].get(status, 0) + 1

    session.commit()

    logger.info(
        f"[SCORING] Batch recalculation complete: "
        f"{results['updated']}/{results['total']} leads updated. "
        f"Distribution: {results['by_status']}"
    )

    return results
