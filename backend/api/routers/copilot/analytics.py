"""
Copilot Router - Analytics endpoints (stats, learning, comparisons, history, etc.).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_creator_access

logger = logging.getLogger(__name__)
router = APIRouter(tags=["copilot"])


# =============================================================================
# GET /copilot/{creator_id}/status
# =============================================================================
@router.get("/{creator_id}/status")
async def get_copilot_status(creator_id: str, _auth: str = Depends(require_creator_access)):
    """
    Obtener estado del modo copilot para un creador.

    Returns:
        - enabled: Si el modo copilot está activado
        - pending_count: Número de respuestas pendientes
    """
    from api.database import SessionLocal
    from api.models import Creator
    from core.copilot_service import get_copilot_service

    # Read directly from DB to avoid multi-worker cache inconsistency
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        # Read copilot_mode directly from DB (bypass cache)
        enabled = getattr(creator, "copilot_mode", True)
        if enabled is None:
            enabled = True  # Default to True if NULL
    finally:
        session.close()

    service = get_copilot_service()
    pending = await service.get_pending_responses(creator_id, limit=100)

    return {
        "creator_id": creator_id,
        "copilot_enabled": enabled,
        "pending_count": len(pending),
        "status": "active" if enabled else "disabled",
    }


# =============================================================================
# GET /copilot/{creator_id}/notifications
# =============================================================================
@router.get("/{creator_id}/notifications")
async def get_notifications(creator_id: str, since: Optional[str] = None, _auth: str = Depends(require_creator_access)):
    """
    Endpoint de polling para notificaciones en tiempo real.

    Args:
        since: ISO timestamp - solo retorna notificaciones después de esta fecha

    Returns:
        - new_messages: Mensajes nuevos recibidos
        - pending_responses: Respuestas pendientes de aprobar
        - hot_leads: Leads que se volvieron HOT
    """
    from datetime import timedelta

    from api.database import SessionLocal
    from api.models import Creator, Lead, Message

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        # Parse since timestamp
        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                since_dt = datetime.now(timezone.utc) - timedelta(minutes=5)
        else:
            since_dt = datetime.now(timezone.utc) - timedelta(minutes=5)

        # Nuevos mensajes de usuarios (increased from 20 to 50)
        new_user_messages = (
            session.query(Message, Lead)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id, Message.role == "user", Message.created_at > since_dt
            )
            .order_by(Message.created_at.desc())
            .limit(50)
            .all()
        )

        new_messages = []
        for msg, lead in new_user_messages:
            new_messages.append(
                {
                    "id": str(msg.id),
                    "lead_id": str(lead.id),
                    "follower_id": lead.platform_user_id,
                    "username": lead.username or "",
                    "platform": lead.platform,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat() if msg.created_at else "",
                }
            )

        # Respuestas pendientes (increased from 20 to 50)
        pending = (
            session.query(Message, Lead)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.status == "pending_approval",
                Message.role == "assistant",
            )
            .order_by(Message.created_at.desc())
            .limit(50)
            .all()
        )

        pending_responses = []
        for msg, lead in pending:
            # Obtener mensaje del usuario
            user_msg = (
                session.query(Message)
                .filter(Message.lead_id == lead.id, Message.role == "user")
                .order_by(Message.created_at.desc())
                .first()
            )

            pending_responses.append(
                {
                    "id": str(msg.id),
                    "lead_id": str(lead.id),
                    "follower_id": lead.platform_user_id,
                    "username": lead.username or "",
                    "platform": lead.platform,
                    "user_message": user_msg.content if user_msg else "",
                    "suggested_response": msg.content,
                    "created_at": msg.created_at.isoformat() if msg.created_at else "",
                }
            )

        # Hot leads recientes (increased from 10 to 25)
        hot_leads = (
            session.query(Lead)
            .filter(
                Lead.creator_id == creator.id, Lead.status == "hot", Lead.last_contact_at > since_dt
            )
            .order_by(Lead.last_contact_at.desc())
            .limit(25)
            .all()
        )

        hot_leads_data = [
            {
                "id": str(lead.id),
                "follower_id": lead.platform_user_id,
                "username": lead.username or "",
                "platform": lead.platform,
                "purchase_intent": lead.purchase_intent or 0.0,
                "last_contact": lead.last_contact_at.isoformat() if lead.last_contact_at else "",
            }
            for lead in hot_leads
        ]

        return {
            "creator_id": creator_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "new_messages_count": len(new_messages),
            "new_messages": new_messages,
            "pending_count": len(pending_responses),
            "pending_responses": pending_responses,
            "hot_leads_count": len(hot_leads_data),
            "hot_leads": hot_leads_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error getting notifications: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        session.close()


# =============================================================================
# GET /copilot/{creator_id}/pending-for-lead/{lead_id}
# =============================================================================
@router.get("/{creator_id}/pending-for-lead/{lead_id}")
async def get_pending_for_lead(creator_id: str, lead_id: str, _auth: str = Depends(require_creator_access)):
    """
    Get the pending copilot suggestion for a specific lead, with conversation context.

    Used by the inbox CopilotBanner to show inline approve/edit/discard.
    Returns null if no pending suggestion exists.
    """
    from api.database import SessionLocal
    from api.models import Creator, Lead, Message
    from core.copilot_service import get_copilot_service

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        # Find the lead
        lead = session.query(Lead).filter_by(id=lead_id, creator_id=creator.id).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # Find pending suggestion for this lead
        pending_msg = (
            session.query(Message)
            .filter(
                Message.lead_id == lead.id,
                Message.role == "assistant",
                Message.status == "pending_approval",
            )
            .order_by(Message.created_at.desc())
            .first()
        )

        if not pending_msg:
            return {"pending": None}

        # Get last user message
        user_msg = (
            session.query(Message)
            .filter(Message.lead_id == lead.id, Message.role == "user")
            .order_by(Message.created_at.desc())
            .first()
        )

        service = get_copilot_service()
        context = service._get_conversation_context(session, lead.id)

        # Extract best_of_n candidates from msg_metadata
        bon = (pending_msg.msg_metadata or {}).get("best_of_n", {})
        candidates_list = None
        if bon.get("candidates"):
            candidates_list = [
                {"content": c["content"], "temperature": c["temperature"],
                 "confidence": c.get("confidence", 0), "rank": c.get("rank", 0)}
                for c in bon["candidates"]
            ]

        pending_dict = {
            "id": str(pending_msg.id),
            "lead_id": str(lead.id),
            "follower_id": lead.platform_user_id,
            "platform": lead.platform,
            "username": lead.username or "",
            "full_name": lead.full_name or "",
            "user_message": user_msg.content if user_msg else "",
            "suggested_response": pending_msg.content,
            "intent": pending_msg.intent or "",
            "created_at": pending_msg.created_at.isoformat() if pending_msg.created_at else "",
            "status": pending_msg.status,
            "conversation_context": context,
            "confidence": pending_msg.confidence_score,
        }
        if candidates_list:
            pending_dict["candidates"] = candidates_list

        return {"pending": pending_dict}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error getting pending for lead: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        session.close()


# =============================================================================
# GET /copilot/{creator_id}/stats
# =============================================================================
@router.get("/{creator_id}/stats")
async def get_copilot_stats(
    creator_id: str,
    days: int = 30,
    _auth: str = Depends(require_creator_access),
):
    """
    Get copilot action statistics for a creator.

    Returns two sections:
    - copilot_metrics: Real creator decisions (approve/edit/discard/manual) from copilot era
    - legacy_metrics: Historical auto-sent bot messages from before copilot was enabled
    """
    from datetime import timedelta

    from sqlalchemy import func

    from api.database import SessionLocal
    from api.models import Creator, Lead, Message

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        since = datetime.now(timezone.utc) - timedelta(days=days)

        # ── COPILOT METRICS: Only messages with copilot_action set ──
        copilot_stats = (
            session.query(
                func.count().label("total"),
                func.count(func.nullif(Message.copilot_action != "approved", True)).label("approved"),
                func.count(func.nullif(Message.copilot_action != "edited", True)).label("edited"),
                func.count(func.nullif(Message.copilot_action != "discarded", True)).label("discarded"),
                func.count(func.nullif(Message.copilot_action != "manual_override", True)).label("manual"),
                func.count(func.nullif(Message.copilot_action != "resolved_externally", True)).label("resolved_ext"),
                func.avg(Message.response_time_ms).label("avg_response_time_ms"),
                func.avg(Message.confidence_score).label("avg_confidence"),
            )
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.role == "assistant",
                Message.copilot_action.isnot(None),
                Message.created_at >= since,
            )
            .first()
        )

        # Pending count
        pending_count = (
            session.query(func.count())
            .select_from(Message)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.role == "assistant",
                Message.status == "pending_approval",
            )
            .scalar() or 0
        )

        c_total = copilot_stats.total or 0
        c_approved = copilot_stats.approved or 0
        c_edited = copilot_stats.edited or 0
        c_discarded = copilot_stats.discarded or 0
        c_manual = copilot_stats.manual or 0
        c_resolved_ext = copilot_stats.resolved_ext or 0

        # ── LEGACY METRICS: Messages without copilot_action ──
        legacy_auto_sent = (
            session.query(func.count())
            .select_from(Message)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.role == "assistant",
                Message.copilot_action.is_(None),
                Message.status == "sent",
                Message.approved_by.is_(None),
                Message.created_at >= since,
            )
            .scalar() or 0
        )

        legacy_creator_manual = (
            session.query(func.count())
            .select_from(Message)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.role == "assistant",
                Message.copilot_action.is_(None),
                Message.approved_by == "creator_manual",
                Message.created_at >= since,
            )
            .scalar() or 0
        )

        legacy_discarded = (
            session.query(func.count())
            .select_from(Message)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.role == "assistant",
                Message.copilot_action.is_(None),
                Message.status == "discarded",
                Message.created_at >= since,
            )
            .scalar() or 0
        )

        legacy_expired = (
            session.query(func.count())
            .select_from(Message)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.role == "assistant",
                Message.status == "expired",
                Message.created_at >= since,
            )
            .scalar() or 0
        )

        # Edit category breakdown
        edit_categories = (
            session.query(Message.edit_diff)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.copilot_action == "edited",
                Message.edit_diff.isnot(None),
                Message.created_at >= since,
            )
            .all()
        )

        category_counts = {}
        for (diff,) in edit_categories:
            if isinstance(diff, dict):
                for cat in diff.get("categories", []):
                    category_counts[cat] = category_counts.get(cat, 0) + 1

        # ── LEARNING PROGRESS from copilot_evaluations ──
        learning_progress = {
            "days_active": 0,
            "total_interactions": 0,
            "patterns_detected": [],
        }
        try:
            from api.models import CopilotEvaluation

            days_active = (
                session.query(func.count(func.distinct(CopilotEvaluation.eval_date)))
                .filter(
                    CopilotEvaluation.creator_id == creator.id,
                    CopilotEvaluation.eval_type == "daily",
                )
                .scalar() or 0
            )

            # Sum total_actions from daily evaluations
            from sqlalchemy import cast, Integer, text
            total_interactions_result = (
                session.query(
                    func.sum(cast(CopilotEvaluation.metrics["total_actions"].as_string(), Integer))
                )
                .filter(
                    CopilotEvaluation.creator_id == creator.id,
                    CopilotEvaluation.eval_type == "daily",
                )
                .scalar() or 0
            )

            # Collect distinct pattern types
            pattern_rows = (
                session.query(CopilotEvaluation.patterns)
                .filter(
                    CopilotEvaluation.creator_id == creator.id,
                    CopilotEvaluation.eval_type == "daily",
                    CopilotEvaluation.patterns.isnot(None),
                )
                .all()
            )
            pattern_types = set()
            for (patterns,) in pattern_rows:
                if isinstance(patterns, list):
                    for p in patterns:
                        if isinstance(p, dict) and "type" in p:
                            pattern_types.add(p["type"])

            learning_progress = {
                "days_active": days_active,
                "total_interactions": int(total_interactions_result),
                "patterns_detected": sorted(pattern_types),
            }
        except Exception as lp_err:
            logger.warning(f"[Copilot] Learning progress query failed: {lp_err}")

        return {
            "creator_id": creator_id,
            "period_days": days,
            "learning_progress": learning_progress,
            # Copilot-era metrics (real creator decisions)
            "copilot_metrics": {
                "total": c_total,
                "approved": c_approved,
                "edited": c_edited,
                "discarded": c_discarded,
                "manual_override": c_manual,
                "resolved_externally": c_resolved_ext,
                "resolved_ext_rate": round(c_resolved_ext / c_total, 3) if c_total else 0,
                "pending": pending_count,
                "approval_rate": round(c_approved / c_total, 3) if c_total else 0,
                "edit_rate": round(c_edited / c_total, 3) if c_total else 0,
                "discard_rate": round(c_discarded / c_total, 3) if c_total else 0,
                "manual_rate": round(c_manual / c_total, 3) if c_total else 0,
                "avg_response_time_ms": round(copilot_stats.avg_response_time_ms) if copilot_stats.avg_response_time_ms else None,
                "avg_confidence": round(float(copilot_stats.avg_confidence), 3) if copilot_stats.avg_confidence else None,
                "edit_categories": category_counts,
            },
            # Legacy metrics (pre-copilot automatic mode)
            "legacy_metrics": {
                "auto_sent": legacy_auto_sent,
                "creator_manual": legacy_creator_manual,
                "discarded": legacy_discarded,
                "expired": legacy_expired,
                "total": legacy_auto_sent + legacy_creator_manual + legacy_discarded + legacy_expired,
            },
            # Backward compatibility — total includes both sections
            "total_actions": c_total,
            "approved": c_approved,
            "edited": c_edited,
            "discarded": c_discarded,
            "manual_override": c_manual,
            "resolved_externally": c_resolved_ext,
            "approval_rate": round(c_approved / c_total, 3) if c_total else 0,
            "edit_rate": round(c_edited / c_total, 3) if c_total else 0,
            "discard_rate": round(c_discarded / c_total, 3) if c_total else 0,
            "manual_rate": round(c_manual / c_total, 3) if c_total else 0,
            "avg_response_time_ms": round(copilot_stats.avg_response_time_ms) if copilot_stats.avg_response_time_ms else None,
            "avg_confidence": round(float(copilot_stats.avg_confidence), 3) if copilot_stats.avg_confidence else None,
            "edit_categories": category_counts,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error getting stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        session.close()


# =============================================================================
# GET /copilot/{creator_id}/learning-progress
# =============================================================================

# Map pattern types from autolearning evaluator to Spanish UI labels
PATTERN_UI_MAP = {
    "consistent_shortening": "Acortar respuestas",
    "consistent_lengthening": "Alargar respuestas",
    "tone_adjustment": "Ajuste de tono",
    "emoji_removal": "Quitar emojis",
    "emoji_addition": "Añadir emojis",
    "formality_increase": "Más formal",
    "formality_decrease": "Más informal",
    "greeting_change": "Cambio de saludo",
    "closing_change": "Cambio de despedida",
    "question_addition": "Añadir preguntas",
    "link_addition": "Añadir enlaces",
    "price_mention": "Mencionar precios",
    "cta_adjustment": "Ajuste de CTA",
    "high_discard_rate": "Descartes frecuentes",
    "high_edit_rate": "Ediciones frecuentes",
}


def _compute_tip(match_rate: float, has_enough_data: bool, weekly_stats: dict, daily_progress: list) -> dict:
    """Generate a contextual gamification tip based on learning data."""
    if not has_enough_data:
        return {
            "type": "needs_data",
            "message": "Sigue aprobando o editando respuestas para que tu clon aprenda tu estilo.",
        }

    discard_rate = weekly_stats["discarded"] / weekly_stats["total"] if weekly_stats["total"] > 0 else 0
    edit_rate = weekly_stats["edited"] / weekly_stats["total"] if weekly_stats["total"] > 0 else 0

    # Check for improving trend
    if len(daily_progress) >= 3:
        first_half = daily_progress[: len(daily_progress) // 2]
        second_half = daily_progress[len(daily_progress) // 2 :]
        first_avg = sum(d["match_rate"] for d in first_half) / len(first_half) if first_half else 0
        second_avg = sum(d["match_rate"] for d in second_half) / len(second_half) if second_half else 0
        if second_avg > first_avg + 0.05:
            return {
                "type": "improving",
                "message": "Tu clon mejora cada dia. La tasa de acierto subió esta semana.",
            }

    if match_rate >= 0.80:
        return {
            "type": "high_match",
            "message": "Tu clon ya habla como tú. Puedes confiar en el modo automático.",
        }

    if discard_rate > 0.40:
        return {
            "type": "high_discards",
            "message": "Muchos descartes. Prueba editar en vez de descartar para que el clon aprenda más rápido.",
        }

    if edit_rate > 0.50:
        return {
            "type": "high_edits",
            "message": "Tus ediciones le enseñan mucho al clon. Sigue así y verás menos ediciones pronto.",
        }

    return {
        "type": "keep_going",
        "message": "Cada aprobación y edición mejora a tu clon. Sigue entrenándolo.",
    }


@router.get("/{creator_id}/learning-progress")
async def get_learning_progress(
    creator_id: str,
    _auth: str = Depends(require_creator_access),
):
    """
    Get learning progress dashboard data for the clone training visualization.

    Returns match rate, learned patterns, weekly stats, daily progress, and a tip.
    """
    from sqlalchemy import Date, cast, func

    from api.database import SessionLocal
    from api.models import Creator, Lead, Message

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        since = datetime.now(timezone.utc) - timedelta(days=7)

        # ── Match rate + weekly stats from messages ──
        copilot_actions = (
            session.query(
                func.count().label("total"),
                func.count(func.nullif(Message.copilot_action != "approved", True)).label("approved"),
                func.count(func.nullif(Message.copilot_action != "edited", True)).label("edited"),
                func.count(func.nullif(Message.copilot_action != "discarded", True)).label("discarded"),
            )
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.role == "assistant",
                Message.copilot_action.in_(["approved", "edited", "discarded"]),
                Message.created_at >= since,
            )
            .first()
        )

        total = copilot_actions.total or 0
        approved = copilot_actions.approved or 0
        edited = copilot_actions.edited or 0
        discarded = copilot_actions.discarded or 0
        has_enough_data = total >= 5
        match_rate_value = round(approved / total, 3) if total > 0 else 0

        weekly_stats = {
            "approved": approved,
            "edited": edited,
            "discarded": discarded,
            "total": total,
        }

        # ── Learned patterns from copilot_evaluations ──
        learned_patterns = []
        try:
            from api.models import CopilotEvaluation

            pattern_rows = (
                session.query(CopilotEvaluation.patterns)
                .filter(
                    CopilotEvaluation.creator_id == creator.id,
                    CopilotEvaluation.eval_type == "daily",
                    CopilotEvaluation.patterns.isnot(None),
                    CopilotEvaluation.eval_date >= since.date(),
                )
                .all()
            )

            # Merge patterns by type, keeping highest frequency
            pattern_map: dict = {}
            for (patterns,) in pattern_rows:
                if isinstance(patterns, list):
                    for p in patterns:
                        if isinstance(p, dict) and "type" in p:
                            ptype = p["type"]
                            freq = p.get("frequency", 0)
                            if ptype not in pattern_map or freq > pattern_map[ptype].get("frequency", 0):
                                pattern_map[ptype] = p

            for ptype, p in sorted(pattern_map.items(), key=lambda x: x[1].get("frequency", 0), reverse=True):
                label = PATTERN_UI_MAP.get(ptype, ptype.replace("_", " ").capitalize())
                learned_patterns.append({
                    "type": ptype,
                    "label": label,
                    "description": p.get("description", ""),
                    "frequency": round(p.get("frequency", 0), 2),
                })
        except Exception as pat_err:
            logger.warning(f"[Copilot] Learning patterns query failed: {pat_err}")

        # ── Daily progress ──
        daily_progress = []
        try:
            # Try copilot_evaluations first
            from api.models import CopilotEvaluation

            daily_evals = (
                session.query(
                    CopilotEvaluation.eval_date,
                    CopilotEvaluation.metrics,
                )
                .filter(
                    CopilotEvaluation.creator_id == creator.id,
                    CopilotEvaluation.eval_type == "daily",
                    CopilotEvaluation.eval_date >= since.date(),
                )
                .order_by(CopilotEvaluation.eval_date)
                .all()
            )

            if daily_evals:
                for eval_row in daily_evals:
                    metrics = eval_row.metrics or {}
                    total_actions = metrics.get("total_actions", 0)
                    approved_actions = metrics.get("approved", 0)
                    rate = round(approved_actions / total_actions, 3) if total_actions > 0 else 0
                    daily_progress.append({
                        "date": str(eval_row.eval_date),
                        "match_rate": rate,
                        "total": total_actions,
                    })
            else:
                # Fallback: group messages by date
                daily_rows = (
                    session.query(
                        cast(Message.created_at, Date).label("day"),
                        func.count().label("total"),
                        func.count(func.nullif(Message.copilot_action != "approved", True)).label("approved"),
                    )
                    .join(Lead, Message.lead_id == Lead.id)
                    .filter(
                        Lead.creator_id == creator.id,
                        Message.role == "assistant",
                        Message.copilot_action.in_(["approved", "edited", "discarded"]),
                        Message.created_at >= since,
                    )
                    .group_by(cast(Message.created_at, Date))
                    .order_by(cast(Message.created_at, Date))
                    .all()
                )

                for row in daily_rows:
                    day_total = row.total or 0
                    day_approved = row.approved or 0
                    rate = round(day_approved / day_total, 3) if day_total > 0 else 0
                    daily_progress.append({
                        "date": str(row.day),
                        "match_rate": rate,
                        "total": day_total,
                    })
        except Exception as dp_err:
            logger.warning(f"[Copilot] Daily progress query failed: {dp_err}")

        has_temporal_data = len(daily_progress) >= 3
        tip = _compute_tip(match_rate_value, has_enough_data, weekly_stats, daily_progress)

        return {
            "creator_id": creator_id,
            "match_rate": {
                "value": match_rate_value,
                "total_suggestions": total,
                "pure_approvals": approved,
                "has_enough_data": has_enough_data,
            },
            "learned_patterns": learned_patterns,
            "weekly_stats": weekly_stats,
            "daily_progress": daily_progress,
            "has_temporal_data": has_temporal_data,
            "tip": tip,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error getting learning progress: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        session.close()


# =============================================================================
# GET /copilot/{creator_id}/comparisons
# =============================================================================
@router.get("/{creator_id}/comparisons")
async def get_copilot_comparisons(
    creator_id: str,
    limit: int = 500,
    offset: int = 0,
    _auth: str = Depends(require_creator_access),
):
    """
    Get side-by-side comparisons of bot suggestions vs real creator responses.

    Two sources of comparisons:
    1. Copilot-era: messages with copilot_action='edited' (suggested_response vs content)
    2. Legacy: bot auto-sent messages paired with nearby creator manual responses
       for the same lead (what bot said vs what creator actually said)
    """
    from sqlalchemy import text

    from api.database import SessionLocal
    from api.models import Creator

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        # Use raw SQL for the lateral join to pair bot auto-sent with creator manual
        rows = session.execute(text("""
            WITH
            -- Source 1: Copilot-era edits (bot suggested → creator edited)
            copilot_edits AS (
                SELECT
                    m.id, m.lead_id, m.suggested_response as bot_suggestion, m.content as creator_response,
                    m.copilot_action as action, m.edit_diff, m.confidence_score,
                    m.response_time_ms, m.created_at,
                    COALESCE(l.full_name, l.username, l.platform_user_id) as lead_name,
                    l.platform, l.platform_user_id,
                    (m.suggested_response = m.content) as is_identical,
                    'copilot' as source,
                    NULL::json as creator_responses_json
                FROM messages m
                JOIN leads l ON m.lead_id = l.id
                WHERE l.creator_id = :creator_id
                AND m.role = 'assistant'
                AND m.copilot_action IN ('edited', 'manual_override', 'approved', 'resolved_externally')
                AND m.suggested_response IS NOT NULL
            ),
            -- Source 2: Legacy — bot auto-sent paired with ALL creator manual responses
            bot_auto AS (
                SELECT m.id, m.lead_id, m.content as bot_suggestion,
                       m.created_at, m.intent, m.confidence_score,
                       COALESCE(l.full_name, l.username, l.platform_user_id) as lead_name,
                       l.platform, l.platform_user_id
                FROM messages m
                JOIN leads l ON m.lead_id = l.id
                WHERE l.creator_id = :creator_id
                AND m.role = 'assistant'
                AND m.copilot_action IS NULL
                AND (m.approved_by IS NULL OR m.approved_by = 'auto')
                AND m.status = 'sent'
                AND m.content NOT IN ('Mentioned you in their story', 'Shared content')
            ),
            legacy_pairs AS (
                SELECT
                    ba.id, ba.lead_id, ba.bot_suggestion, cr.first_response as creator_response,
                    'legacy_comparison' as action,
                    NULL::json as edit_diff, ba.confidence_score,
                    NULL::integer as response_time_ms,
                    ba.created_at,
                    ba.lead_name, ba.platform, ba.platform_user_id,
                    (ba.bot_suggestion = cr.first_response) as is_identical,
                    'legacy' as source,
                    cr.all_responses as creator_responses_json
                FROM bot_auto ba
                CROSS JOIN LATERAL (
                    SELECT
                        (SELECT content FROM messages
                         WHERE lead_id = ba.lead_id AND role = 'assistant'
                         AND approved_by = 'creator_manual'
                         AND created_at BETWEEN ba.created_at - INTERVAL '4 hours'
                                             AND ba.created_at + INTERVAL '24 hours'
                         ORDER BY created_at ASC LIMIT 1
                        ) as first_response,
                        (SELECT json_agg(json_build_object(
                            'content', content,
                            'timestamp', created_at::text
                         ) ORDER BY created_at ASC)
                         FROM messages
                         WHERE lead_id = ba.lead_id AND role = 'assistant'
                         AND approved_by = 'creator_manual'
                         AND created_at BETWEEN ba.created_at - INTERVAL '4 hours'
                                             AND ba.created_at + INTERVAL '24 hours'
                        ) as all_responses
                ) cr
                WHERE cr.first_response IS NOT NULL
            ),
            -- Combine both sources
            all_comparisons AS (
                SELECT * FROM copilot_edits
                UNION ALL
                SELECT * FROM legacy_pairs
            )
            SELECT * FROM all_comparisons
            ORDER BY created_at DESC
            OFFSET :offset
            LIMIT :limit_plus_one
        """), {
            "creator_id": str(creator.id),
            "offset": offset,
            "limit_plus_one": limit + 1,
        }).fetchall()

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        # B3: Collect conversation context per unique lead
        from core.copilot_service import get_copilot_service

        copilot_svc = get_copilot_service()
        lead_context_cache: dict = {}

        comparisons = []
        for row in rows:
            # Build creator_responses array
            creator_responses = None
            if row.creator_responses_json:
                creator_responses = row.creator_responses_json

            # B3: Get conversation context (cached per lead)
            lead_id = row.lead_id
            if lead_id not in lead_context_cache:
                try:
                    before_ts = row.created_at if row.created_at else None
                    lead_context_cache[lead_id] = copilot_svc._get_conversation_context(
                        session, lead_id, max_messages=5, before_timestamp=before_ts
                    )
                except Exception:
                    lead_context_cache[lead_id] = []

            comparisons.append({
                "message_id": str(row.id),
                "bot_original": row.bot_suggestion or "",
                "creator_final": row.creator_response or "",
                "action": row.action,
                "edit_diff": row.edit_diff,
                "confidence": row.confidence_score,
                "response_time_ms": row.response_time_ms,
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "username": row.lead_name or "",
                "platform": row.platform,
                "is_identical": row.is_identical,
                "source": row.source,
                "creator_responses": creator_responses,
                "conversation_context": lead_context_cache.get(lead_id, []),
            })

        return {
            "creator_id": creator_id,
            "comparisons": comparisons,
            "count": len(comparisons),
            "has_more": has_more,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error getting comparisons: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        session.close()


# =============================================================================
# GET /copilot/{creator_id}/history
# =============================================================================
@router.get("/{creator_id}/history")
async def get_copilot_history(
    creator_id: str,
    limit: int = 50,
    offset: int = 0,
    _auth: str = Depends(require_creator_access),
):
    """
    Get full copilot action history for a creator.

    Includes all actions (approved, edited, discarded, manual_override, resolved_externally)
    ordered by most recent first. For resolved_externally items, includes similarity_score.
    """
    from sqlalchemy import func

    from api.database import SessionLocal
    from api.models import Creator, Lead, Message

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        # Query messages with copilot_action, join with Lead
        query = (
            session.query(
                Message.id,
                Message.lead_id,
                Message.status,
                Message.copilot_action,
                Message.suggested_response,
                Message.content,
                Message.intent,
                Message.confidence_score,
                Message.response_time_ms,
                Message.created_at,
                Message.approved_at,
                Message.msg_metadata,
                Lead.username,
                Lead.platform,
                Lead.platform_user_id,
            )
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.role == "assistant",
                Message.copilot_action.isnot(None),
            )
            .order_by(Message.created_at.desc())
            .offset(offset)
            .limit(limit + 1)
        )

        rows = query.all()
        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        # Build items
        items = []
        for row in rows:
            meta = row.msg_metadata or {}
            similarity = meta.get("similarity_score") if row.copilot_action == "resolved_externally" else None

            items.append({
                "id": str(row.id),
                "lead_name": row.username or row.platform_user_id or "",
                "platform": row.platform,
                "status": row.status,
                "copilot_action": row.copilot_action,
                "bot_suggestion": row.suggested_response or "",
                "creator_actual": row.content or "",
                "similarity_score": similarity,
                "confidence": row.confidence_score,
                "intent": row.intent or "",
                "response_time_ms": row.response_time_ms,
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "resolved_at": row.approved_at.isoformat() if row.approved_at else "",
            })

        # Aggregate stats
        stats_query = (
            session.query(
                Message.copilot_action,
                func.count().label("cnt"),
            )
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.role == "assistant",
                Message.copilot_action.isnot(None),
            )
            .group_by(Message.copilot_action)
            .all()
        )

        action_counts = {action: cnt for action, cnt in stats_query}
        total_all = sum(action_counts.values())

        # Average similarity for resolved_externally
        avg_sim = None
        resolved_ext_count = action_counts.get("resolved_externally", 0)
        if resolved_ext_count > 0:
            from sqlalchemy import text as sa_text

            avg_sim_result = session.execute(sa_text("""
                SELECT AVG((msg_metadata->>'similarity_score')::float)
                FROM messages m
                JOIN leads l ON m.lead_id = l.id
                WHERE l.creator_id = :cid
                AND m.copilot_action = 'resolved_externally'
                AND m.msg_metadata->>'similarity_score' IS NOT NULL
            """), {"cid": str(creator.id)}).scalar()
            if avg_sim_result is not None:
                avg_sim = round(float(avg_sim_result), 2)

        stats = {
            "total": total_all,
            "approved": action_counts.get("approved", 0),
            "edited": action_counts.get("edited", 0),
            "discarded": action_counts.get("discarded", 0),
            "manual_override": action_counts.get("manual_override", 0),
            "resolved_externally": resolved_ext_count,
            "avg_similarity": avg_sim,
        }

        return {
            "items": items,
            "stats": stats,
            "count": len(items),
            "has_more": has_more,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error getting history: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        session.close()


# =============================================================================
# GET /copilot/{creator_id}/historical-rates
# =============================================================================
@router.get("/{creator_id}/historical-rates")
async def get_historical_rates(
    creator_id: str,
    _auth: str = Depends(require_creator_access),
):
    """
    Get historical approval rates per intent for confidence calibration.

    Used by the autolearning engine to adjust confidence thresholds
    based on how the creator has historically acted on each intent type.
    """
    from core.confidence_scorer import get_historical_rates

    result = get_historical_rates(creator_id)
    return {"creator_id": creator_id, **result}


# =============================================================================
# GET /copilot/{creator_id}/preference-pairs
# =============================================================================
@router.get("/{creator_id}/preference-pairs")
async def get_preference_pairs(
    creator_id: str,
    limit: int = 50,
    offset: int = 0,
    action_type: Optional[str] = None,
    unexported_only: bool = False,
    _auth: str = Depends(require_creator_access),
):
    """List preference pairs for export or viewing."""
    from api.database import SessionLocal
    from api.models import Creator
    from services.preference_pairs_service import get_pairs_for_export

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")
        pairs = get_pairs_for_export(
            creator.id, limit=limit, offset=offset,
            action_type=action_type, unexported_only=unexported_only,
        )
        return {"creator_id": creator_id, "count": len(pairs), "pairs": pairs}
    finally:
        session.close()
