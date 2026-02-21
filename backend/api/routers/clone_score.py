"""
CloneScore Router — Endpoints for CloneScore evaluation results.

Endpoints:
- GET /clone-score/{creator_id}          — Latest score + trend
- GET /clone-score/{creator_id}/history  — Score history
- POST /clone-score/{creator_id}/evaluate — Trigger on-demand evaluation
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_creator_access

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clone-score", tags=["clone-score"])


@router.get("/{creator_id}")
async def get_latest_score(
    creator_id: str,
    _auth=Depends(require_creator_access),
):
    """Get the latest CloneScore with trend info."""
    from api.database import SessionLocal
    from api.models import CloneScoreEvaluation, Creator

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        latest = (
            session.query(CloneScoreEvaluation)
            .filter_by(creator_id=creator.id)
            .order_by(CloneScoreEvaluation.evaluated_at.desc())
            .first()
        )

        if not latest:
            return {
                "has_score": False,
                "message": "No evaluations yet. Run a batch evaluation first.",
            }

        previous = (
            session.query(CloneScoreEvaluation)
            .filter(
                CloneScoreEvaluation.creator_id == creator.id,
                CloneScoreEvaluation.evaluated_at < latest.evaluated_at,
            )
            .order_by(CloneScoreEvaluation.evaluated_at.desc())
            .first()
        )

        trend = None
        if previous:
            delta = latest.overall_score - previous.overall_score
            trend = {
                "direction": "up" if delta > 0 else "down" if delta < 0 else "stable",
                "delta": round(delta, 1),
                "previous_score": previous.overall_score,
            }

        score = latest.overall_score
        if score >= 90:
            label = "excelente"
        elif score >= 75:
            label = "bueno"
        elif score >= 60:
            label = "aceptable"
        elif score >= 40:
            label = "mejorable"
        else:
            label = "critico"

        return {
            "has_score": True,
            "overall_score": latest.overall_score,
            "label": label,
            "dimension_scores": latest.dimension_scores,
            "sample_size": latest.sample_size,
            "evaluated_at": latest.evaluated_at.isoformat(),
            "eval_type": latest.eval_type,
            "trend": trend,
            "metadata": latest.eval_metadata,
        }
    finally:
        session.close()


@router.get("/{creator_id}/history")
async def get_score_history(
    creator_id: str,
    days: int = 30,
    _auth=Depends(require_creator_access),
):
    """Get CloneScore history for the last N days."""
    from api.database import SessionLocal
    from api.models import CloneScoreEvaluation, Creator

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        since = datetime.now(timezone.utc) - timedelta(days=days)
        evaluations = (
            session.query(CloneScoreEvaluation)
            .filter(
                CloneScoreEvaluation.creator_id == creator.id,
                CloneScoreEvaluation.evaluated_at >= since,
            )
            .order_by(CloneScoreEvaluation.evaluated_at.asc())
            .all()
        )

        return {
            "creator_id": creator_id,
            "days": days,
            "evaluations": [
                {
                    "overall_score": e.overall_score,
                    "dimension_scores": e.dimension_scores,
                    "eval_type": e.eval_type,
                    "sample_size": e.sample_size,
                    "evaluated_at": e.evaluated_at.isoformat(),
                }
                for e in evaluations
            ],
            "count": len(evaluations),
        }
    finally:
        session.close()


@router.post("/{creator_id}/evaluate")
async def trigger_evaluation(
    creator_id: str,
    sample_size: int = 50,
    _auth=Depends(require_creator_access),
):
    """Trigger an on-demand CloneScore evaluation."""
    from api.database import SessionLocal
    from api.models import Creator
    from services.clone_score_engine import get_clone_score_engine

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")
        creator_db_id = creator.id
    finally:
        session.close()

    engine = get_clone_score_engine()
    result = await engine.evaluate_batch(
        creator_id=creator_id,
        creator_db_id=creator_db_id,
        sample_size=sample_size,
    )

    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])

    return result
