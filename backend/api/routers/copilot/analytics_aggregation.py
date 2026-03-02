"""Aggregation, computation, and stats formatting for copilot analytics."""
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


# Map pattern types from autolearning evaluator to Spanish UI labels
PATTERN_UI_MAP = {
    "consistent_shortening": "Acortar respuestas",
    "consistent_lengthening": "Alargar respuestas",
    "tone_adjustment": "Ajuste de tono",
    "emoji_removal": "Quitar emojis",
    "emoji_addition": "Anadir emojis",
    "formality_increase": "Mas formal",
    "formality_decrease": "Mas informal",
    "greeting_change": "Cambio de saludo",
    "closing_change": "Cambio de despedida",
    "question_addition": "Anadir preguntas",
    "link_addition": "Anadir enlaces",
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
                "message": "Tu clon mejora cada dia. La tasa de acierto subio esta semana.",
            }

    if match_rate >= 0.80:
        return {
            "type": "high_match",
            "message": "Tu clon ya habla como tu. Puedes confiar en el modo automatico.",
        }

    if discard_rate > 0.40:
        return {
            "type": "high_discards",
            "message": "Muchos descartes. Prueba editar en vez de descartar para que el clon aprenda mas rapido.",
        }

    if edit_rate > 0.50:
        return {
            "type": "high_edits",
            "message": "Tus ediciones le ensenan mucho al clon. Sigue asi y veras menos ediciones pronto.",
        }

    return {
        "type": "keep_going",
        "message": "Cada aprobacion y edicion mejora a tu clon. Sigue entrenandolo.",
    }


def compute_copilot_stats(session, creator, days):
    """
    Compute full copilot stats including copilot metrics, legacy metrics,
    learning progress, and edit categories.

    Returns dict ready for HTTP response.
    """
    from sqlalchemy import func

    from api.models import Lead, Message

    since = datetime.now(timezone.utc) - timedelta(days=days)

    # -- COPILOT METRICS: Only messages with copilot_action set --
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

    # -- LEGACY METRICS: Messages without copilot_action --
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
        .limit(100)
        .all()
    )

    category_counts = {}
    for (diff,) in edit_categories:
        if isinstance(diff, dict):
            for cat in diff.get("categories", []):
                category_counts[cat] = category_counts.get(cat, 0) + 1

    # -- LEARNING PROGRESS from copilot_evaluations --
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
        from sqlalchemy import cast, Integer
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
            .limit(100)
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
        # Backward compatibility -- total includes both sections
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


def compute_learning_progress(session, creator):
    """
    Compute learning progress dashboard data including match rate,
    patterns, weekly stats, daily progress, and tip.

    Returns dict ready for HTTP response.
    """
    from sqlalchemy import Date, cast, func

    from api.models import Lead, Message

    since = datetime.now(timezone.utc) - timedelta(days=7)

    # -- Match rate + weekly stats from messages --
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

    # -- Learned patterns from copilot_evaluations --
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
            .limit(100)
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

    # -- Daily progress --
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
            .limit(100)
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
