"""
Autolearning Evaluator — Daily and weekly copilot evaluation engine.

Daily evaluation:
  - Aggregates copilot actions from the last 24h
  - Detects patterns (e.g., "creator always shortens responses")
  - Stores snapshot in copilot_evaluations table

Weekly recalibration:
  - Analyzes last 7 daily evaluations
  - Detects trends (improving/degrading approval rate)
  - Generates recommendations for confidence threshold adjustments
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


async def run_daily_evaluation(creator_id: str, creator_db_id, eval_date: Optional[date] = None):
    """
    Run daily evaluation for a single creator.

    Collects all copilot actions from the past 24 hours,
    aggregates them, detects patterns, and stores the result.
    """
    from sqlalchemy import func

    from api.database import SessionLocal
    from api.models import CopilotEvaluation, Lead, Message

    if eval_date is None:
        eval_date = date.today()

    since = datetime.combine(eval_date - timedelta(days=1), datetime.min.time()).replace(tzinfo=timezone.utc)
    until = datetime.combine(eval_date, datetime.min.time()).replace(tzinfo=timezone.utc)

    session = SessionLocal()
    try:
        # Check if already evaluated
        existing = (
            session.query(CopilotEvaluation.id)
            .filter_by(creator_id=creator_db_id, eval_type="daily", eval_date=eval_date)
            .first()
        )
        if existing:
            logger.debug(f"[AUTOLEARN] Daily eval already exists for {creator_id} on {eval_date}")
            return {"skipped": True}

        # Aggregate actions
        rows = (
            session.query(
                Message.copilot_action,
                func.count().label("cnt"),
                func.avg(Message.response_time_ms).label("avg_rt"),
                func.avg(Message.confidence_score).label("avg_conf"),
            )
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator_db_id,
                Message.role == "assistant",
                Message.copilot_action.isnot(None),
                Message.created_at >= since,
                Message.created_at < until,
            )
            .group_by(Message.copilot_action)
            .all()
        )

        if not rows:
            logger.debug(f"[AUTOLEARN] No copilot actions for {creator_id} on {eval_date}")
            return {"skipped": True, "reason": "no_actions"}

        # Build metrics
        action_counts = {}
        total = 0
        avg_response_time = None
        avg_confidence = None
        for action, cnt, avg_rt, avg_conf in rows:
            action_counts[action] = cnt
            total += cnt
            if avg_rt:
                avg_response_time = round(float(avg_rt))
            if avg_conf:
                avg_confidence = round(float(avg_conf), 3)

        approved = action_counts.get("approved", 0)
        edited = action_counts.get("edited", 0)
        discarded = action_counts.get("discarded", 0)
        manual = action_counts.get("manual_override", 0)

        metrics = {
            "total_actions": total,
            "approved": approved,
            "edited": edited,
            "discarded": discarded,
            "manual_override": manual,
            "approval_rate": round((approved + edited) / total, 3) if total else 0,
            "edit_rate": round(edited / total, 3) if total else 0,
            "discard_rate": round(discarded / total, 3) if total else 0,
            "avg_response_time_ms": avg_response_time,
            "avg_confidence": avg_confidence,
        }

        # Detect patterns from edit diffs
        patterns = _detect_daily_patterns(session, creator_db_id, since, until)

        evaluation = CopilotEvaluation(
            creator_id=creator_db_id,
            eval_type="daily",
            eval_date=eval_date,
            metrics=metrics,
            patterns=patterns,
        )
        session.add(evaluation)
        session.commit()

        logger.info(
            f"[AUTOLEARN] Daily eval for {creator_id}: "
            f"{total} actions, {metrics['approval_rate']*100:.0f}% approval, "
            f"{len(patterns)} patterns"
        )
        return {"stored": True, "metrics": metrics, "patterns": patterns}

    except Exception as e:
        logger.error(f"[AUTOLEARN] Daily eval error for {creator_id}: {e}")
        session.rollback()
        return {"error": str(e)}
    finally:
        session.close()


def _detect_daily_patterns(session, creator_db_id, since, until) -> list:
    """Detect recurring edit patterns from the day's actions."""
    from api.models import Lead, Message

    patterns = []

    # Get all edit diffs for the period
    diffs = (
        session.query(Message.edit_diff)
        .join(Lead, Message.lead_id == Lead.id)
        .filter(
            Lead.creator_id == creator_db_id,
            Message.copilot_action == "edited",
            Message.edit_diff.isnot(None),
            Message.created_at >= since,
            Message.created_at < until,
        )
        .all()
    )

    if not diffs:
        return patterns

    # Count categories
    category_counts = {}
    total_diffs = 0
    total_length_delta = 0
    for (diff,) in diffs:
        if isinstance(diff, dict):
            total_diffs += 1
            total_length_delta += diff.get("length_delta", 0)
            for cat in diff.get("categories", []):
                category_counts[cat] = category_counts.get(cat, 0) + 1

    if total_diffs == 0:
        return patterns

    # Pattern: consistently shortening
    if category_counts.get("shortened", 0) >= total_diffs * 0.5:
        patterns.append({
            "type": "consistent_shortening",
            "frequency": round(category_counts["shortened"] / total_diffs, 2),
            "avg_delta": round(total_length_delta / total_diffs),
            "suggestion": "Reduce max_tokens or add conciseness instruction to system prompt",
        })

    # Pattern: consistently removing questions
    if category_counts.get("removed_question", 0) >= total_diffs * 0.4:
        patterns.append({
            "type": "question_removal",
            "frequency": round(category_counts["removed_question"] / total_diffs, 2),
            "suggestion": "Reduce question frequency in system prompt",
        })

    # Pattern: complete rewrites indicate poor fit
    if category_counts.get("complete_rewrite", 0) >= total_diffs * 0.3:
        patterns.append({
            "type": "high_rewrite_rate",
            "frequency": round(category_counts["complete_rewrite"] / total_diffs, 2),
            "suggestion": "Review system prompt — bot tone may not match creator style",
        })

    # Pattern: emoji removal
    if category_counts.get("removed_emoji", 0) >= total_diffs * 0.4:
        patterns.append({
            "type": "emoji_removal",
            "frequency": round(category_counts["removed_emoji"] / total_diffs, 2),
            "suggestion": "Reduce emoji usage in system prompt",
        })

    return patterns


async def run_weekly_recalibration(creator_id: str, creator_db_id, week_end: Optional[date] = None):
    """
    Run weekly recalibration for a creator.

    Analyzes the last 7 daily evaluations, detects trends,
    and generates confidence threshold recommendations.
    """
    from api.database import SessionLocal
    from api.models import CopilotEvaluation

    if week_end is None:
        week_end = date.today()

    week_start = week_end - timedelta(days=7)

    session = SessionLocal()
    try:
        # Check if already evaluated
        existing = (
            session.query(CopilotEvaluation.id)
            .filter_by(creator_id=creator_db_id, eval_type="weekly", eval_date=week_end)
            .first()
        )
        if existing:
            return {"skipped": True}

        # Get daily evals for the week
        daily_evals = (
            session.query(CopilotEvaluation)
            .filter(
                CopilotEvaluation.creator_id == creator_db_id,
                CopilotEvaluation.eval_type == "daily",
                CopilotEvaluation.eval_date >= week_start,
                CopilotEvaluation.eval_date <= week_end,
            )
            .order_by(CopilotEvaluation.eval_date)
            .all()
        )

        if len(daily_evals) < 3:
            logger.debug(f"[AUTOLEARN] Not enough daily evals for weekly ({len(daily_evals)}/3)")
            return {"skipped": True, "reason": "insufficient_data"}

        # Aggregate weekly metrics
        total_actions = sum(e.metrics.get("total_actions", 0) for e in daily_evals)
        if total_actions == 0:
            return {"skipped": True, "reason": "no_actions"}

        approval_rates = [e.metrics.get("approval_rate", 0) for e in daily_evals if e.metrics.get("total_actions", 0) > 0]
        edit_rates = [e.metrics.get("edit_rate", 0) for e in daily_evals if e.metrics.get("total_actions", 0) > 0]
        discard_rates = [e.metrics.get("discard_rate", 0) for e in daily_evals if e.metrics.get("total_actions", 0) > 0]

        metrics = {
            "total_actions": total_actions,
            "days_with_data": len(daily_evals),
            "avg_approval_rate": round(sum(approval_rates) / len(approval_rates), 3) if approval_rates else 0,
            "avg_edit_rate": round(sum(edit_rates) / len(edit_rates), 3) if edit_rates else 0,
            "avg_discard_rate": round(sum(discard_rates) / len(discard_rates), 3) if discard_rates else 0,
        }

        # Detect trends
        recommendations = _generate_weekly_recommendations(daily_evals, metrics)

        # Collect all patterns from the week
        all_patterns = []
        for ev in daily_evals:
            if ev.patterns:
                all_patterns.extend(ev.patterns)

        # Deduplicate pattern types and count frequency
        pattern_summary = {}
        for p in all_patterns:
            ptype = p.get("type", "unknown")
            if ptype not in pattern_summary:
                pattern_summary[ptype] = {"count": 0, "suggestion": p.get("suggestion", "")}
            pattern_summary[ptype]["count"] += 1

        weekly_eval = CopilotEvaluation(
            creator_id=creator_db_id,
            eval_type="weekly",
            eval_date=week_end,
            metrics=metrics,
            patterns=list(pattern_summary.values()) if pattern_summary else None,
            recommendations=recommendations,
        )
        session.add(weekly_eval)
        session.commit()

        logger.info(
            f"[AUTOLEARN] Weekly recalibration for {creator_id}: "
            f"{total_actions} actions, {metrics['avg_approval_rate']*100:.0f}% avg approval, "
            f"{len(recommendations)} recommendations"
        )
        return {"stored": True, "metrics": metrics, "recommendations": recommendations}

    except Exception as e:
        logger.error(f"[AUTOLEARN] Weekly recalibration error for {creator_id}: {e}")
        session.rollback()
        return {"error": str(e)}
    finally:
        session.close()


def _generate_weekly_recommendations(daily_evals, metrics: dict) -> list:
    """Generate actionable recommendations based on weekly patterns."""
    recommendations = []

    avg_approval = metrics.get("avg_approval_rate", 0)
    avg_edit = metrics.get("avg_edit_rate", 0)
    avg_discard = metrics.get("avg_discard_rate", 0)

    # Trend: approval rate improving over the week?
    if len(daily_evals) >= 3:
        first_half = daily_evals[: len(daily_evals) // 2]
        second_half = daily_evals[len(daily_evals) // 2:]

        first_approval = sum(
            e.metrics.get("approval_rate", 0) for e in first_half
            if e.metrics.get("total_actions", 0) > 0
        ) / max(1, len(first_half))
        second_approval = sum(
            e.metrics.get("approval_rate", 0) for e in second_half
            if e.metrics.get("total_actions", 0) > 0
        ) / max(1, len(second_half))

        if second_approval > first_approval + 0.1:
            recommendations.append({
                "type": "improving_trend",
                "detail": f"Approval rate improved from {first_approval*100:.0f}% to {second_approval*100:.0f}%",
                "action": "none",
            })
        elif first_approval > second_approval + 0.1:
            recommendations.append({
                "type": "degrading_trend",
                "detail": f"Approval rate dropped from {first_approval*100:.0f}% to {second_approval*100:.0f}%",
                "action": "review_system_prompt",
            })

    # High discard rate
    if avg_discard > 0.4:
        recommendations.append({
            "type": "high_discard_rate",
            "detail": f"Discard rate is {avg_discard*100:.0f}% — bot responses often off-target",
            "action": "review_system_prompt",
        })

    # High edit rate
    if avg_edit > 0.5:
        recommendations.append({
            "type": "high_edit_rate",
            "detail": f"Edit rate is {avg_edit*100:.0f}% — bot tone needs tuning",
            "action": "adjust_tone_profile",
        })

    # Very high approval — bot is doing well
    if avg_approval > 0.85 and metrics.get("total_actions", 0) >= 20:
        recommendations.append({
            "type": "high_performance",
            "detail": f"Approval rate is {avg_approval*100:.0f}% — consider switching to auto mode",
            "action": "suggest_auto_mode",
        })

    return recommendations
