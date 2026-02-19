"""
Autolearning API — endpoints for viewing and managing learning rules.

Provides visibility into the autolearning feedback loop:
- List active rules for a creator
- View rule stats and effectiveness
- Manually deactivate/reactivate rules
- Trigger consolidation on demand
"""

import logging
from typing import Optional

from api.database import SessionLocal
from api.models import Creator, LearningRule
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/autolearning", tags=["autolearning"])


@router.get("/{creator_id}/rules")
async def list_rules(
    creator_id: str,
    active_only: bool = Query(True, description="Filter to active rules only"),
    pattern: Optional[str] = Query(None, description="Filter by pattern"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List learning rules for a creator."""
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        query = session.query(LearningRule).filter(
            LearningRule.creator_id == creator.id
        )
        if active_only:
            query = query.filter(LearningRule.is_active.is_(True))
        if pattern:
            query = query.filter(LearningRule.pattern == pattern)

        total = query.count()
        rules = (
            query.order_by(LearningRule.confidence.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return {
            "creator": creator_id,
            "total": total,
            "rules": [
                {
                    "id": str(r.id),
                    "rule_text": r.rule_text,
                    "pattern": r.pattern,
                    "confidence": r.confidence,
                    "times_applied": r.times_applied,
                    "times_helped": r.times_helped,
                    "help_ratio": round(r.times_helped / r.times_applied, 2) if r.times_applied > 0 else 0,
                    "example_bad": r.example_bad,
                    "example_good": r.example_good,
                    "applies_to_relationship_types": r.applies_to_relationship_types or [],
                    "applies_to_message_types": r.applies_to_message_types or [],
                    "applies_to_lead_stages": r.applies_to_lead_stages or [],
                    "is_active": r.is_active,
                    "version": r.version,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "superseded_by": str(r.superseded_by) if r.superseded_by else None,
                }
                for r in rules
            ],
        }
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


@router.post("/{creator_id}/rules/{rule_id}/deactivate")
async def deactivate_rule(creator_id: str, rule_id: str):
    """Manually deactivate a learning rule."""
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        rule = (
            session.query(LearningRule)
            .filter(LearningRule.id == rule_id, LearningRule.creator_id == creator.id)
            .first()
        )
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        rule.is_active = False
        session.commit()

        return {"status": "deactivated", "rule_id": rule_id}
    finally:
        session.close()


@router.post("/{creator_id}/rules/{rule_id}/reactivate")
async def reactivate_rule(creator_id: str, rule_id: str):
    """Manually reactivate a learning rule."""
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        rule = (
            session.query(LearningRule)
            .filter(LearningRule.id == rule_id, LearningRule.creator_id == creator.id)
            .first()
        )
        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        rule.is_active = True
        session.commit()

        return {"status": "reactivated", "rule_id": rule_id}
    finally:
        session.close()


@router.post("/{creator_id}/consolidate")
async def trigger_consolidation(creator_id: str):
    """Manually trigger rule consolidation for a creator."""
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        from services.learning_consolidator import consolidate_rules_for_creator

        result = await consolidate_rules_for_creator(creator_id, creator.id)

        return {
            "creator": creator_id,
            **result,
        }
    finally:
        session.close()
