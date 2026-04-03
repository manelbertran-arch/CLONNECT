"""Analysis endpoints: consolidation trigger, pattern analysis."""

import logging

from api.database import SessionLocal
from api.models import Creator, LearningRule
from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/{creator_id}/consolidate")
async def trigger_consolidation(creator_id: str):
    """Manually trigger rule consolidation for a creator."""
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        from services.persona_compiler import compile_persona as consolidate_rules_for_creator

        result = await consolidate_rules_for_creator(creator_id, creator.id)

        return {
            "creator": creator_id,
            **result,
        }
    finally:
        session.close()


@router.post("/{creator_id}/analyze-patterns")
async def analyze_patterns(creator_id: str):
    """Manually trigger LLM-as-Judge pattern analysis on accumulated preference pairs."""
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")
        cid = creator.id
    finally:
        session.close()

    from services.persona_compiler import compile_persona as run_pattern_analysis

    result = await run_pattern_analysis(creator_id, cid)
    return {"creator_id": creator_id, **result}


@router.get("/{creator_id}/pattern-analysis")
async def get_pattern_analysis(
    creator_id: str,
    limit: int = Query(default=20, le=100),
):
    """View learning rules derived from pattern batch analysis."""
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        rules = (
            session.query(LearningRule)
            .filter(
                LearningRule.creator_id == creator.id,
                LearningRule.is_active.is_(True),
                LearningRule.source == "pattern_batch",
            )
            .order_by(LearningRule.created_at.desc())
            .limit(limit)
            .all()
        )

        return {
            "creator_id": creator_id,
            "count": len(rules),
            "rules": [
                {
                    "id": str(r.id),
                    "rule_text": r.rule_text,
                    "pattern": r.pattern,
                    "example_bad": r.example_bad,
                    "example_good": r.example_good,
                    "confidence": r.confidence,
                    "source": r.source,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rules
            ],
        }
    finally:
        session.close()
