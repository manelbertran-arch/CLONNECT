"""Dashboard endpoints: gamified dashboard, rule stats, gold examples, preference profile, curation."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from api.cache import api_cache
from api.database import SessionLocal
from api.models import Creator, GoldExample, Lead, LearningRule, Message
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import case, cast, func, Date
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# GAMIFIED DASHBOARD — Constants and helpers
# =============================================================================

LEVELS = [
    (0, "Beb\u00e9", "\U0001f476"),
    (25, "Novato", "\U0001f423"),
    (100, "Aprendiz", "\U0001f4d8"),
    (250, "Capaz", "\U0001f4aa"),
    (500, "H\u00e1bil", "\U0001f3af"),
    (1000, "Experto", "\u2b50"),
    (2000, "Maestro", "\U0001f3c6"),
    (5000, "Tu gemelo", "\U0001f916"),
]

INTENT_LABELS = {
    "greeting": "Saludos",
    "question_product": "Preguntas de producto",
    "question_general": "Preguntas generales",
    "objection": "Objeciones",
    "interest": "Inter\u00e9s",
    "purchase_intent": "Intenci\u00f3n de compra",
    "booking": "Reservas",
    "complaint": "Quejas",
    "follow_up": "Seguimiento",
    "farewell": "Despedidas",
    "gratitude": "Agradecimiento",
    "spam": "Spam",
    "unknown": "Otros",
}

PATTERN_LABELS = {
    "shorten_response": "Brevedad",
    "lengthen_response": "Detalle",
    "more_formal": "Formalidad",
    "less_formal": "Cercan\u00eda",
    "add_emoji": "Emojis",
    "remove_emoji": "Sin emojis",
    "change_greeting": "Saludos",
    "change_closing": "Cierres",
    "add_question": "Preguntas",
    "remove_question": "Sin preguntas",
    "change_tone": "Tono",
    "add_info": "Informaci\u00f3n",
    "remove_info": "Menos info",
    "complete_rewrite": "Reescritura",
    "pricing_response": "Precios",
    "objection_handling": "Objeciones",
}

ACHIEVEMENTS = [
    {"id": "first_approval", "name": "Primera aprobaci\u00f3n", "icon": "\u2705", "description": "Aprueba tu primera sugerencia del clon", "check": lambda d: d["approved"] >= 1},
    {"id": "ten_approvals", "name": "Racha de 10", "icon": "\U0001f51f", "description": "Aprueba 10 sugerencias", "check": lambda d: d["approved"] >= 10},
    {"id": "fifty_approvals", "name": "Medio centenar", "icon": "5\ufe0f\u20e30\ufe0f\u20e3", "description": "Aprueba 50 sugerencias", "check": lambda d: d["approved"] >= 50},
    {"id": "first_edit", "name": "Maestro editor", "icon": "\u270f\ufe0f", "description": "Edita tu primera sugerencia para ense\u00f1ar al clon", "check": lambda d: d["edited"] >= 1},
    {"id": "first_rule", "name": "Primera regla", "icon": "\U0001f4cf", "description": "Tu clon aprendi\u00f3 su primera regla", "check": lambda d: d["total_rules"] >= 1},
    {"id": "five_rules", "name": "Cinco reglas", "icon": "\U0001f4da", "description": "Tu clon tiene 5 reglas aprendidas", "check": lambda d: d["total_rules"] >= 5},
    {"id": "streak_3", "name": "Racha de 3 d\u00edas", "icon": "\U0001f525", "description": "Usa el copiloto 3 d\u00edas seguidos", "check": lambda d: d["streak"] >= 3},
    {"id": "streak_7", "name": "Semana perfecta", "icon": "\U0001f5d3\ufe0f", "description": "Usa el copiloto 7 d\u00edas seguidos", "check": lambda d: d["streak"] >= 7},
    {"id": "level_3", "name": "Aprendiz", "icon": "\U0001f4d8", "description": "Alcanza el nivel Aprendiz (100 XP)", "check": lambda d: d["xp"] >= 100},
    {"id": "level_5", "name": "H\u00e1bil", "icon": "\U0001f3af", "description": "Alcanza el nivel H\u00e1bil (500 XP)", "check": lambda d: d["xp"] >= 500},
    {"id": "autopilot_ready", "name": "Piloto autom\u00e1tico", "icon": "\U0001f680", "description": "Un intent alcanza status 'ready'", "check": lambda d: d["has_ready_intent"]},
]


def _get_level(xp: int) -> Dict[str, Any]:
    """Compute level info from XP."""
    level_num = 0
    level_name = LEVELS[0][1]
    level_emoji = LEVELS[0][2]
    level_threshold = 0

    for i, (threshold, name, emoji) in enumerate(LEVELS):
        if xp >= threshold:
            level_num = i
            level_name = name
            level_emoji = emoji
            level_threshold = threshold

    # Next level
    next_idx = level_num + 1
    if next_idx < len(LEVELS):
        next_xp = LEVELS[next_idx][0]
        next_name = LEVELS[next_idx][1]
        range_xp = next_xp - level_threshold
        progress = ((xp - level_threshold) / range_xp * 100) if range_xp > 0 else 100
    else:
        next_xp = None
        next_name = None
        progress = 100.0

    return {
        "number": level_num,
        "name": level_name,
        "emoji": level_emoji,
        "xp_threshold": level_threshold,
        "next_level_xp": next_xp,
        "next_level_name": next_name,
        "progress_pct": round(progress, 1),
    }


def _compute_streak(session: Session, creator_uuid) -> int:
    """Compute consecutive days streak from today."""
    rows = (
        session.query(cast(Message.created_at, Date))
        .join(Lead, Message.lead_id == Lead.id)
        .filter(
            Lead.creator_id == creator_uuid,
            Message.role == "assistant",
            Message.copilot_action.in_(["approved", "edited", "discarded"]),
        )
        .distinct()
        .order_by(cast(Message.created_at, Date).desc())
        .limit(60)
        .all()
    )

    if not rows:
        return 0

    dates = sorted({r[0] for r in rows}, reverse=True)
    today = datetime.now(timezone.utc).date()

    # Start from today or yesterday
    if dates[0] == today:
        streak = 1
        expected = today - timedelta(days=1)
    elif dates[0] == today - timedelta(days=1):
        streak = 1
        expected = today - timedelta(days=2)
    else:
        return 0

    for d in dates[1:]:
        if d == expected:
            streak += 1
            expected -= timedelta(days=1)
        else:
            break

    return streak


def _edit_severity(edit_diff: Optional[Dict]) -> str:
    """Compute edit severity from edit_diff JSON."""
    if not edit_diff or not isinstance(edit_diff, dict):
        return "none"
    categories = edit_diff.get("categories", [])
    if not categories:
        return "none"
    if "complete_rewrite" in categories or len(categories) >= 3:
        return "high"
    if len(categories) >= 2:
        return "medium"
    return "low"


def _autopilot_status(
    total: int, approved: int, edited: int, discarded: int,
    recent_discards: int, avg_severity: str
) -> str:
    """Determine autopilot readiness for an intent."""
    if total < 5:
        return "needs_data"
    approval_rate = approved / total if total > 0 else 0
    if approval_rate >= 0.9 and avg_severity in ("none", "low") and recent_discards <= 1:
        return "ready"
    if approval_rate >= 0.7:
        return "learning"
    return "needs_work"


@router.get("/{creator_id}/dashboard")
async def get_dashboard(creator_id: str):
    """Gamified autolearning dashboard with XP, levels, skills, achievements."""
    # Check cache
    cache_key = f"autolearning_dashboard:{creator_id}"
    cached = api_cache.get(cache_key)
    if cached:
        return cached

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        cid = creator.id

        # Q1 — XP + action breakdown
        xp_row = (
            session.query(
                func.coalesce(
                    func.sum(
                        case(
                            (Message.copilot_action == "approved", 3),
                            (Message.copilot_action == "edited", 2),
                            else_=1,
                        )
                    ),
                    0,
                ).label("xp"),
                func.count(Message.id).filter(Message.copilot_action == "approved").label("approved"),
                func.count(Message.id).filter(Message.copilot_action == "edited").label("edited"),
                func.count(Message.id).filter(Message.copilot_action == "discarded").label("discarded"),
            )
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == cid,
                Message.role == "assistant",
                Message.copilot_action.in_(["approved", "edited", "discarded"]),
            )
            .first()
        )

        total_xp = int(xp_row.xp) if xp_row.xp else 0
        approved = int(xp_row.approved) if xp_row.approved else 0
        edited = int(xp_row.edited) if xp_row.edited else 0
        discarded = int(xp_row.discarded) if xp_row.discarded else 0

        # Q2 — Streak
        streak = _compute_streak(session, cid)

        # Q3 — Autopilot by intent
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
        intent_rows = (
            session.query(
                Message.intent,
                func.count(Message.id).label("total"),
                func.count(Message.id).filter(Message.copilot_action == "approved").label("approved"),
                func.count(Message.id).filter(Message.copilot_action == "edited").label("edited"),
                func.count(Message.id).filter(Message.copilot_action == "discarded").label("discarded"),
                func.count(Message.id).filter(
                    Message.copilot_action == "discarded",
                    Message.created_at >= seven_days_ago,
                ).label("recent_discards"),
                func.count(
                    func.distinct(cast(Message.created_at, Date))
                ).label("consistency_days"),
            )
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == cid,
                Message.role == "assistant",
                Message.copilot_action.in_(["approved", "edited", "discarded"]),
                Message.intent.isnot(None),
            )
            .group_by(Message.intent)
            .limit(100)
            .all()
        )

        # For severity per intent, get edited messages
        edited_msgs = (
            session.query(Message.intent, Message.edit_diff)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == cid,
                Message.role == "assistant",
                Message.copilot_action == "edited",
                Message.intent.isnot(None),
            )
            .limit(100)
            .all()
        )

        # Compute avg severity per intent
        severity_map: Dict[str, List[str]] = {}
        for msg_intent, diff in edited_msgs:
            severity_map.setdefault(msg_intent, []).append(_edit_severity(diff))

        def _avg_severity(intent: str) -> str:
            severities = severity_map.get(intent, [])
            if not severities:
                return "none"
            scores = {"none": 0, "low": 1, "medium": 2, "high": 3}
            avg = sum(scores.get(s, 0) for s in severities) / len(severities)
            if avg < 0.5:
                return "none"
            if avg < 1.5:
                return "low"
            if avg < 2.5:
                return "medium"
            return "high"

        has_ready_intent = False
        autopilot_readiness = []
        for row in intent_rows:
            intent = row.intent or "unknown"
            severity = _avg_severity(intent)
            status = _autopilot_status(
                row.total, row.approved, row.edited, row.discarded,
                row.recent_discards, severity,
            )
            if status == "ready":
                has_ready_intent = True

            rate = row.approved / row.total if row.total > 0 else 0
            autopilot_readiness.append({
                "intent": intent,
                "label": INTENT_LABELS.get(intent, intent.replace("_", " ").title()),
                "total": row.total,
                "approved": row.approved,
                "edited": row.edited,
                "discarded": row.discarded,
                "approval_rate": round(rate, 2),
                "avg_edit_severity": severity,
                "recent_discards": row.recent_discards,
                "consistency_days": row.consistency_days,
                "status": status,
            })

        autopilot_readiness.sort(key=lambda x: x["total"], reverse=True)

        # Q4 — Lessons: last 20 edited/discarded messages with linked rules
        lesson_msgs = (
            session.query(Message, LearningRule)
            .join(Lead, Message.lead_id == Lead.id)
            .outerjoin(LearningRule, LearningRule.source_message_id == Message.id)
            .filter(
                Lead.creator_id == cid,
                Message.role == "assistant",
                Message.copilot_action.in_(["approved", "edited", "discarded"]),
            )
            .order_by(Message.created_at.desc())
            .limit(20)
            .all()
        )

        lessons = []
        for msg, rule in lesson_msgs:
            lesson = {
                "id": str(msg.id),
                "intent": msg.intent or "unknown",
                "action": msg.copilot_action,
                "suggested_response": msg.suggested_response,
                "final_response": msg.content if msg.copilot_action != "discarded" else None,
                "edit_diff": msg.edit_diff,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "linked_rule": None,
            }
            if rule:
                lesson["linked_rule"] = {
                    "id": str(rule.id),
                    "rule_text": rule.rule_text,
                    "pattern": rule.pattern,
                }
            lessons.append(lesson)

        # Q5 — Skills from learning rules
        skill_rows = (
            session.query(
                LearningRule.pattern,
                func.count(LearningRule.id).label("rule_count"),
                func.avg(LearningRule.confidence).label("avg_confidence"),
                func.sum(LearningRule.times_applied).label("total_applied"),
                func.sum(LearningRule.times_helped).label("total_helped"),
            )
            .filter(
                LearningRule.creator_id == cid,
                LearningRule.is_active.is_(True),
            )
            .group_by(LearningRule.pattern)
            .order_by(func.sum(LearningRule.times_applied).desc())
            .limit(100)
            .all()
        )

        total_rules = (
            session.query(func.count(LearningRule.id))
            .filter(LearningRule.creator_id == cid, LearningRule.is_active.is_(True))
            .scalar() or 0
        )

        skills = []
        for row in skill_rows:
            applied = int(row.total_applied or 0)
            helped = int(row.total_helped or 0)
            conf = float(row.avg_confidence) if row.avg_confidence else 0
            ratio = helped / applied if applied > 0 else 0

            if conf >= 0.8 and ratio >= 0.7:
                skill_status = "mastered"
            elif conf >= 0.5:
                skill_status = "learning"
            else:
                skill_status = "detected"

            skills.append({
                "pattern": row.pattern,
                "label": PATTERN_LABELS.get(row.pattern, row.pattern.replace("_", " ").title()),
                "rule_count": row.rule_count,
                "avg_confidence": round(conf, 2),
                "total_applied": applied,
                "total_helped": helped,
                "help_ratio": round(ratio, 2),
                "status": skill_status,
            })

        # Achievements
        achievement_data = {
            "approved": approved,
            "edited": edited,
            "discarded": discarded,
            "total_rules": total_rules,
            "streak": streak,
            "xp": total_xp,
            "has_ready_intent": has_ready_intent,
        }

        achievements = []
        for ach in ACHIEVEMENTS:
            achievements.append({
                "id": ach["id"],
                "name": ach["name"],
                "icon": ach["icon"],
                "unlocked": ach["check"](achievement_data),
                "description": ach["description"],
            })

        result = {
            "creator_id": creator_id,
            "clone_xp": {
                "total_xp": total_xp,
                "level": _get_level(total_xp),
                "streak": {"current": streak},
                "breakdown": {
                    "approved": approved,
                    "edited": edited,
                    "discarded": discarded,
                },
            },
            "autopilot_readiness": autopilot_readiness,
            "lessons": lessons,
            "skills": skills,
            "achievements": achievements,
        }

        api_cache.set(cache_key, result, ttl_seconds=60)
        return result
    finally:
        session.close()


@router.get("/{creator_id}/stats")
async def rule_stats(creator_id: str):
    """Get aggregated autolearning stats for a creator."""
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        active_count = (
            session.query(func.count(LearningRule.id))
            .filter(LearningRule.creator_id == creator.id, LearningRule.is_active.is_(True))
            .scalar()
        )
        total_count = (
            session.query(func.count(LearningRule.id))
            .filter(LearningRule.creator_id == creator.id)
            .scalar()
        )
        patterns = (
            session.query(LearningRule.pattern, func.count(LearningRule.id))
            .filter(LearningRule.creator_id == creator.id, LearningRule.is_active.is_(True))
            .group_by(LearningRule.pattern)
            .order_by(func.count(LearningRule.id).desc())
            .limit(100)
            .all()
        )
        avg_confidence = (
            session.query(func.avg(LearningRule.confidence))
            .filter(LearningRule.creator_id == creator.id, LearningRule.is_active.is_(True))
            .scalar()
        )

        return {
            "creator": creator_id,
            "active_rules": active_count,
            "total_rules": total_count,
            "superseded_rules": total_count - active_count,
            "avg_confidence": round(float(avg_confidence), 3) if avg_confidence else 0,
            "patterns": [{"pattern": p, "count": c} for p, c in patterns],
        }
    finally:
        session.close()


@router.get("/{creator_id}/gold-examples")
async def get_gold_examples(
    creator_id: str,
    limit: int = Query(default=20, le=100),
):
    """List active gold examples for a creator."""
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        examples = (
            session.query(GoldExample)
            .filter(
                GoldExample.creator_id == creator.id,
                GoldExample.is_active.is_(True),
            )
            .order_by(GoldExample.quality_score.desc())
            .limit(limit)
            .all()
        )

        return {
            "creator_id": creator_id,
            "count": len(examples),
            "examples": [
                {
                    "id": str(e.id),
                    "user_message": e.user_message,
                    "creator_response": e.creator_response,
                    "intent": e.intent,
                    "lead_stage": e.lead_stage,
                    "source": e.source,
                    "quality_score": e.quality_score,
                    "times_used": e.times_used,
                    "times_helpful": e.times_helpful,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in examples
            ],
        }
    finally:
        session.close()


@router.get("/{creator_id}/preference-profile")
async def get_preference_profile(creator_id: str):
    """Compute and return the creator's preference profile."""
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")
        cid = creator.id
    finally:
        session.close()

    from services.preference_profile_service import compute_preference_profile

    profile = compute_preference_profile(cid)
    if not profile:
        return {"creator_id": creator_id, "profile": None, "message": "Insufficient data (need 10+ messages)"}
    return {"creator_id": creator_id, "profile": profile}


@router.post("/{creator_id}/curate-examples")
async def curate_gold_examples(creator_id: str):
    """Manually trigger gold examples curation from recent copilot messages."""
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")
        cid = creator.id
    finally:
        session.close()

    from services.gold_examples_service import curate_examples

    result = await curate_examples(creator_id, cid)
    return {"creator_id": creator_id, **result}
