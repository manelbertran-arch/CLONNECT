"""
Evaluator Feedback Router — Capture and retrieve human evaluator feedback.

Endpoints:
- POST /feedback                        — Save evaluator feedback
- GET  /feedback/{creator_id}           — List feedback (paginated, filterable)
- GET  /feedback/{creator_id}/stats     — Aggregate stats across all feedback types
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import require_creator_access

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackPayload(BaseModel):
    creator_id: str  # Creator slug (e.g. "iris_bertran")
    evaluator_id: str = "manel"
    user_message: str
    bot_response: str
    coherencia: Optional[int] = Field(None, ge=1, le=5)
    lo_enviarias: Optional[int] = Field(None, ge=1, le=5)
    ideal_response: Optional[str] = None
    error_tags: Optional[list] = None
    error_free_text: Optional[str] = None
    conversation_id: Optional[str] = None
    intent_detected: Optional[str] = None
    doc_d_version: Optional[str] = None
    model_id: Optional[str] = None


@router.post("")
async def save_feedback(payload: FeedbackPayload, _auth=Depends(require_creator_access)):
    """Save structured evaluator feedback. Auto-creates preference pair + gold example."""
    from api.database import SessionLocal
    from api.models import Creator

    # Resolve creator slug to DB UUID
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter(Creator.name == payload.creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail=f"Creator '{payload.creator_id}' not found")
        creator_db_id = creator.id
    finally:
        session.close()

    from services.feedback_store import save_feedback as _save

    result = _save(
        creator_db_id=creator_db_id,
        evaluator_id=payload.evaluator_id,
        user_message=payload.user_message,
        bot_response=payload.bot_response,
        coherencia=payload.coherencia,
        lo_enviarias=payload.lo_enviarias,
        ideal_response=payload.ideal_response,
        error_tags=payload.error_tags,
        error_free_text=payload.error_free_text,
        conversation_id=payload.conversation_id,
        intent_detected=payload.intent_detected,
        doc_d_version=payload.doc_d_version,
        model_id=payload.model_id,
    )

    if result is None:
        raise HTTPException(status_code=500, detail="Failed to save feedback (check ENABLE_EVALUATOR_FEEDBACK)")

    return result


@router.get("/{creator_id}")
async def list_feedback(
    creator_id: str,
    evaluator_id: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    min_coherencia: Optional[int] = Query(default=None, ge=1, le=5),
    min_lo_enviarias: Optional[int] = Query(default=None, ge=1, le=5),
    with_ideal_only: bool = False,
    _auth: str = Depends(require_creator_access),
):
    """List evaluator feedback for a creator, with optional filters."""
    from api.database import SessionLocal
    from api.models import Creator

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter(Creator.name == creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail=f"Creator '{creator_id}' not found")
        creator_db_id = creator.id
    finally:
        session.close()

    from services.feedback_store import get_feedback

    return get_feedback(
        creator_db_id=creator_db_id,
        evaluator_id=evaluator_id,
        limit=limit,
        offset=offset,
        min_coherencia=min_coherencia,
        min_lo_enviarias=min_lo_enviarias,
        with_ideal_only=with_ideal_only,
    )


@router.get("/{creator_id}/stats")
async def feedback_stats(creator_id: str, _auth: str = Depends(require_creator_access)):
    """Aggregate stats across all feedback types for a creator."""
    from api.database import SessionLocal
    from api.models import Creator

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter(Creator.name == creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail=f"Creator '{creator_id}' not found")
        creator_db_id = creator.id
    finally:
        session.close()

    from services.feedback_store import get_feedback_stats

    return get_feedback_stats(creator_db_id=creator_db_id)
