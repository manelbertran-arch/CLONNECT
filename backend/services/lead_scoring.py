"""
Lead Classification + Scoring V2 — Intelligent Relationship-Based Scoring.

Architecture:
  1. extract_signals(session, lead) → Dict of conversation signals
  2. classify_relationship(signals) → Relationship type string
  3. calculate_score(relationship_type, signals) → Score 0-100

Key insight: WHO says what matters. Only follower keywords count for
purchase intent. Creator mentioning "precio" is a sales pitch, not a signal.

Relationship types:
  cliente, lead_caliente, lead_tibio, curioso, amigo, colaborador,
  fan, nuevo, fantasma

Status mapping (for CRM pipeline):
  cliente → cliente
  lead_caliente → caliente
  lead_tibio → interesado
  curioso → interesado
  amigo, colaborador, fan, nuevo → nuevo
  fantasma → fantasma
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# KEYWORD DICTIONARIES — Only FOLLOWER messages checked for purchase/interest
# =============================================================================

FOLLOWER_PURCHASE_KEYWORDS = [
    "precio", "cuánto", "cuanto", "cuesta", "comprar", "pagar",
    "contratar", "inscribirme", "quiero comprar",
    "cómo pago", "como pago", "método de pago", "transferencia",
    "price", "cost", "buy", "purchase", "pay",
]

FOLLOWER_INTEREST_KEYWORDS = [
    "me interesa", "quiero saber", "necesito", "me gustaría",
    "cuéntame más", "cómo funciona", "como funciona",
    "qué incluye", "que incluye", "info", "información",
    "detalles", "interesado", "interesada",
    "interested", "tell me more", "how does it work",
]

FOLLOWER_SCHEDULING_KEYWORDS = [
    "reservar", "agendar", "cita", "sesión", "sesion",
    "horario", "disponibilidad", "calendario", "fecha", "hora",
    "call", "meeting", "appointment", "schedule", "book",
]

SOCIAL_KEYWORDS = [
    "jaja", "jeje", "haha", "hehe",
    "amigo", "hermano", "bro", "crack", "capo", "leyenda",
    "abrazo", "tío", "tio", "pana", "compa", "wey", "máquina",
    "un abrazo", "te quiero", "cuídate",
]

COLLABORATION_KEYWORDS = [
    "collab", "colaborar", "colaboración", "proyecto juntos",
    "partners", "together", "proyecto", "propuesta",
    "trabajar juntos", "alianza",
]

NEGATIVE_KEYWORDS = [
    "no me interesa", "no puedo", "caro", "muy caro", "no gracias",
    "después", "luego", "ahora no", "no tengo",
    "not interested", "too expensive", "can't afford",
]

# Status mapping: relationship_type → CRM status
RELATIONSHIP_TO_STATUS = {
    "cliente": "cliente",
    "lead_caliente": "caliente",
    "lead_tibio": "interesado",
    "curioso": "interesado",
    "amigo": "nuevo",
    "colaborador": "nuevo",
    "fan": "nuevo",
    "nuevo": "nuevo",
    "fantasma": "fantasma",
}

# Score ranges by relationship type: (min, max)
SCORE_RANGES = {
    "cliente": (75, 100),
    "lead_caliente": (55, 85),
    "lead_tibio": (30, 60),
    "curioso": (15, 35),
    "amigo": (10, 25),
    "colaborador": (10, 25),
    "fan": (3, 15),
    "nuevo": (0, 15),
    "fantasma": (0, 10),
}


# =============================================================================
# STEP 1: Extract Signals
# =============================================================================

def extract_signals(session, lead) -> Dict[str, Any]:
    """
    Extract conversation signals from a lead's message history.

    Distinguishes between follower messages (role="user") and
    creator messages (role="assistant") for keyword analysis.
    """
    from api.models import Message

    messages = (
        session.query(
            Message.role, Message.content, Message.intent,
            Message.created_at, Message.msg_metadata,
        )
        .filter(
            Message.lead_id == lead.id,
            Message.content.isnot(None),
            Message.content != "",
        )
        .order_by(Message.created_at.asc())
        .all()
    )

    signals: Dict[str, Any] = {
        # Counts
        "total_messages": len(messages),
        "follower_messages": 0,
        "creator_messages": 0,
        # Keyword hits (FOLLOWER only)
        "follower_purchase_hits": 0,
        "follower_interest_hits": 0,
        "follower_scheduling_hits": 0,
        "follower_negative_hits": 0,
        # Social signals (both sides)
        "social_hits": 0,
        "collaboration_hits": 0,
        # Content patterns
        "follower_avg_length": 0.0,
        "short_reactions": 0,
        "story_replies": 0,
        # Engagement
        "bidirectional_ratio": 0.0,
        # Intents (from intent classifier)
        "strong_intents": 0,
        "soft_intents": 0,
        # Recency
        "days_since_last": 999,
        "days_since_first": 999,
        # Flags
        "is_existing_customer": lead.status == "cliente",
    }

    follower_lengths = []

    for role, content, intent, created_at, msg_metadata in messages:
        text = (content or "").strip().lower()

        if role == "user":
            signals["follower_messages"] += 1
            follower_lengths.append(len(text))

            # Short reaction detection (emoji-only, "ok", "si", etc.)
            if len(text) <= 5:
                signals["short_reactions"] += 1

            # Story reply detection via metadata
            meta = msg_metadata or {}
            if meta.get("type") in ("story_mention", "story_reply"):
                signals["story_replies"] += 1
            elif any(p in text for p in [
                "replied to your story", "respondió a tu historia",
                "mencionó tu historia",
            ]):
                signals["story_replies"] += 1

            # Purchase keywords (FOLLOWER ONLY)
            if any(kw in text for kw in FOLLOWER_PURCHASE_KEYWORDS):
                signals["follower_purchase_hits"] += 1

            # Interest keywords (FOLLOWER ONLY)
            if any(kw in text for kw in FOLLOWER_INTEREST_KEYWORDS):
                signals["follower_interest_hits"] += 1

            # Scheduling keywords (FOLLOWER ONLY)
            if any(kw in text for kw in FOLLOWER_SCHEDULING_KEYWORDS):
                signals["follower_scheduling_hits"] += 1

            # Negative keywords (FOLLOWER ONLY)
            if any(kw in text for kw in NEGATIVE_KEYWORDS):
                signals["follower_negative_hits"] += 1

            # Intent signals
            if intent in ("purchase", "interest_strong"):
                signals["strong_intents"] += 1
            elif intent in ("interest_soft", "question_product", "product_question"):
                signals["soft_intents"] += 1

        elif role == "assistant":
            signals["creator_messages"] += 1

        # Social and collaboration keywords (both sides count)
        if any(kw in text for kw in SOCIAL_KEYWORDS):
            signals["social_hits"] += 1

        if any(kw in text for kw in COLLABORATION_KEYWORDS):
            signals["collaboration_hits"] += 1

    # Derived metrics
    if follower_lengths:
        signals["follower_avg_length"] = sum(follower_lengths) / len(follower_lengths)

    f = signals["follower_messages"]
    c = signals["creator_messages"]
    if max(f, c) > 0:
        signals["bidirectional_ratio"] = min(f, c) / max(f, c)

    # Recency
    if lead.last_contact_at:
        lca = lead.last_contact_at
        if hasattr(lca, "tzinfo") and lca.tzinfo is None:
            lca = lca.replace(tzinfo=timezone.utc)
        signals["days_since_last"] = (datetime.now(timezone.utc) - lca).days

    if lead.first_contact_at:
        fca = lead.first_contact_at
        if hasattr(fca, "tzinfo") and fca.tzinfo is None:
            fca = fca.replace(tzinfo=timezone.utc)
        signals["days_since_first"] = (datetime.now(timezone.utc) - fca).days

    return signals


# =============================================================================
# STEP 2: Classify Relationship
# =============================================================================

def classify_relationship(signals: Dict[str, Any]) -> str:
    """
    Classify the lead's relationship type based on extracted signals.

    Priority order (first match wins):
      1. cliente — already marked as customer
      2. lead_caliente — follower uses strong purchase keywords
      3. lead_tibio — follower shows soft interest
      4. colaborador — collaboration keywords present
      5. amigo — high bidirectionality + social signals
      6. fan — mostly short reactions / story replies
      7. curioso — some engagement but no clear intent
      8. fantasma — inactive 14+ days
      9. nuevo — default
    """
    # 1. CLIENTE — preserve existing customer status
    if signals["is_existing_customer"]:
        return "cliente"

    # 2. LEAD_CALIENTE — follower actively asking about purchase/scheduling
    if signals["follower_purchase_hits"] >= 2 or (
        signals["follower_purchase_hits"] >= 1
        and signals["follower_scheduling_hits"] >= 1
    ):
        return "lead_caliente"

    if (
        signals["strong_intents"] >= 2
        and signals["follower_purchase_hits"] >= 1
    ):
        return "lead_caliente"

    # 3. LEAD_TIBIO — follower shows interest
    if signals["follower_interest_hits"] >= 2 or (
        signals["follower_interest_hits"] >= 1
        and signals["follower_purchase_hits"] >= 1
    ):
        return "lead_tibio"

    if (
        signals["follower_scheduling_hits"] >= 1
        and signals["follower_interest_hits"] >= 1
    ):
        return "lead_tibio"

    # 4. COLABORADOR — collaboration signals
    if signals["collaboration_hits"] >= 2:
        return "colaborador"

    # 5. AMIGO — high bidirectionality + social + volume
    is_bidirectional = signals["bidirectional_ratio"] >= 0.4
    has_social = signals["social_hits"] >= 3
    has_volume = signals["total_messages"] >= 10

    if is_bidirectional and has_social and has_volume:
        return "amigo"

    # Also amigo if very high bidirectionality and volume
    if signals["bidirectional_ratio"] >= 0.6 and signals["total_messages"] >= 20:
        return "amigo"

    # 6. FAN — mostly reactions, story replies, short messages
    if signals["follower_messages"] >= 3:
        reaction_ratio = (
            (signals["short_reactions"] + signals["story_replies"])
            / max(signals["follower_messages"], 1)
        )
        if reaction_ratio >= 0.6 and signals["follower_purchase_hits"] == 0:
            return "fan"

    # 7. CURIOSO — some messages, soft signals, but no purchase intent
    if signals["follower_messages"] >= 3 and (
        signals["soft_intents"] >= 1
        or signals["follower_interest_hits"] >= 1
    ):
        return "curioso"

    # 8. FANTASMA — inactive 14+ days with prior activity
    if signals["days_since_last"] >= 14 and signals["total_messages"] >= 2:
        return "fantasma"

    # 9. NUEVO — default
    return "nuevo"


# =============================================================================
# STEP 3: Calculate Score Within Type
# =============================================================================

def calculate_score(relationship_type: str, signals: Dict[str, Any]) -> int:
    """
    Calculate a score within the type's fixed range based on signal quality.

    Each type has a (min, max) range. A 0.0-1.0 quality factor determines
    where within that range the lead falls.
    """
    min_score, max_score = SCORE_RANGES.get(relationship_type, (0, 15))
    range_size = max_score - min_score

    # Calculate quality factor (0.0-1.0) based on type
    quality = 0.5

    if relationship_type == "cliente":
        quality = 0.7
        if signals["days_since_last"] <= 7:
            quality += 0.2
        elif signals["days_since_last"] <= 30:
            quality += 0.1
        if signals["follower_messages"] >= 10:
            quality += 0.1

    elif relationship_type == "lead_caliente":
        quality = 0.5
        quality += min(0.2, signals["follower_purchase_hits"] * 0.1)
        quality += min(0.15, signals["follower_scheduling_hits"] * 0.075)
        quality += min(0.1, signals["strong_intents"] * 0.05)
        if signals["days_since_last"] <= 3:
            quality += 0.1
        if signals["follower_negative_hits"] > 0:
            quality -= 0.15

    elif relationship_type == "lead_tibio":
        quality = 0.4
        quality += min(0.2, signals["follower_interest_hits"] * 0.1)
        quality += min(0.15, signals["soft_intents"] * 0.05)
        quality += min(0.1, signals["follower_purchase_hits"] * 0.1)
        if signals["days_since_last"] <= 7:
            quality += 0.1
        if signals["follower_negative_hits"] > 0:
            quality -= 0.2

    elif relationship_type == "curioso":
        quality = 0.3
        quality += min(0.3, signals["follower_messages"] * 0.03)
        if signals["soft_intents"] >= 2:
            quality += 0.15
        if signals["days_since_last"] <= 7:
            quality += 0.15

    elif relationship_type == "amigo":
        quality = 0.3
        quality += min(0.3, signals["social_hits"] * 0.03)
        quality += min(0.2, signals["total_messages"] * 0.005)
        if signals["bidirectional_ratio"] >= 0.6:
            quality += 0.1

    elif relationship_type == "colaborador":
        quality = 0.5
        quality += min(0.2, signals["collaboration_hits"] * 0.1)
        if signals["total_messages"] >= 10:
            quality += 0.15

    elif relationship_type == "fan":
        quality = 0.3
        quality += min(0.3, signals["story_replies"] * 0.1)
        quality += min(0.2, signals["follower_messages"] * 0.02)
        if signals["days_since_last"] <= 7:
            quality += 0.15

    elif relationship_type == "fantasma":
        quality = 0.5
        if signals["days_since_last"] >= 60:
            quality = 0.2
        elif signals["days_since_last"] >= 30:
            quality = 0.3

    elif relationship_type == "nuevo":
        quality = 0.3
        quality += min(0.3, signals["follower_messages"] * 0.1)
        if signals["days_since_last"] <= 3:
            quality += 0.2

    # Clamp quality
    quality = max(0.0, min(1.0, quality))

    score = min_score + int(range_size * quality)
    return max(0, min(100, score))


# =============================================================================
# MAIN ENTRY POINT — Same signature as V1 for backward compatibility
# =============================================================================

def recalculate_lead_score(session, lead_id: str) -> Optional[Tuple[float, str]]:
    """
    Recalculate a lead's score using V2 intelligent classification.

    This is the SINGLE SOURCE OF TRUTH for lead scoring.
    All code paths that need to update a lead's score should call this function.

    Pipeline: extract_signals → classify_relationship → calculate_score

    Args:
        session: SQLAlchemy session
        lead_id: Lead UUID string

    Returns:
        Tuple of (purchase_intent 0.0-1.0, status string) or None if not found
    """
    from api.models import Lead

    try:
        lead = session.query(Lead).filter_by(id=lead_id).first()
    except Exception as e:
        logger.error(f"[SCORING-V2] DB query failed for lead_id={lead_id}: {e}")
        return None

    if not lead:
        logger.warning(f"[SCORING-V2] Lead not found: {lead_id}")
        return None

    # Step 1: Extract signals
    signals = extract_signals(session, lead)

    # Step 2: Classify relationship
    relationship_type = classify_relationship(signals)

    # Step 3: Calculate score within type range
    score = calculate_score(relationship_type, signals)

    # Determine CRM status
    new_status = RELATIONSHIP_TO_STATUS.get(relationship_type, "nuevo")

    # Update lead
    lead.relationship_type = relationship_type
    lead.score = score
    lead.purchase_intent = score / 100.0
    lead.status = new_status
    lead.score_updated_at = datetime.now(timezone.utc)

    logger.info(
        f"[SCORING-V2] {lead.username or lead.platform_user_id}: "
        f"type={relationship_type}, score={score}, status={new_status} "
        f"(msgs={signals['total_messages']}, follower={signals['follower_messages']}, "
        f"purchase_kw={signals['follower_purchase_hits']}, "
        f"interest_kw={signals['follower_interest_hits']}, "
        f"social={signals['social_hits']}, "
        f"bidir={signals['bidirectional_ratio']:.2f})"
    )

    return score / 100.0, new_status


def batch_recalculate_scores(session, creator_id: str) -> dict:
    """
    Recalculate scores for all leads of a creator using V2 algorithm.

    Returns distribution by relationship_type for verification.
    """
    from api.models import Creator, Lead

    creator = session.query(Creator).filter_by(name=creator_id).first()
    if not creator:
        try:
            creator = session.query(Creator).filter_by(id=creator_id).first()
        except Exception:
            pass
    if not creator:
        return {"error": f"Creator {creator_id} not found"}

    leads = session.query(Lead).filter_by(creator_id=creator.id).all()

    results = {
        "total": len(leads),
        "updated": 0,
        "by_status": {},
        "by_relationship_type": {},
    }

    for lead in leads:
        result = recalculate_lead_score(session, str(lead.id))
        if result:
            results["updated"] += 1
            _, status = result
            results["by_status"][status] = results["by_status"].get(status, 0) + 1
            rt = lead.relationship_type or "unknown"
            results["by_relationship_type"][rt] = (
                results["by_relationship_type"].get(rt, 0) + 1
            )

    session.commit()

    logger.info(
        f"[SCORING-V2] Batch complete: {results['updated']}/{results['total']} leads. "
        f"Types: {results['by_relationship_type']} | Status: {results['by_status']}"
    )

    return results
