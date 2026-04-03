"""
Evaluator Feedback Router — Capture and retrieve human evaluator feedback.

Endpoints:
- POST /feedback                        — Save evaluator feedback
- GET  /feedback/{creator_id}           — List feedback (paginated, filterable)
- GET  /feedback/{creator_id}/stats     — Aggregate stats across all feedback types
"""

import asyncio
import logging
import time
from collections import defaultdict
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from api.auth import require_creator_access

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/feedback", tags=["feedback"])


# ---------------------------------------------------------------------------
# FIX FB-04: Simple per-evaluator rate limiter (10 req/min)
# ---------------------------------------------------------------------------
_feedback_timestamps: dict = defaultdict(list)
_FEEDBACK_RPM = 10


def _check_rate_limit(evaluator_id: str) -> None:
    now = time.time()
    window = now - 60
    timestamps = _feedback_timestamps[evaluator_id]
    # Prune old entries
    _feedback_timestamps[evaluator_id] = [t for t in timestamps if t > window]
    if len(_feedback_timestamps[evaluator_id]) >= _FEEDBACK_RPM:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: max {_FEEDBACK_RPM} feedback submissions per minute",
        )
    _feedback_timestamps[evaluator_id].append(now)


# ---------------------------------------------------------------------------
# FIX FB-05: Validated error tag model
# ---------------------------------------------------------------------------

class ErrorTag(BaseModel):
    type: str = Field(..., max_length=50)
    detail: str = Field("", max_length=500)


class FeedbackPayload(BaseModel):
    creator_id: str  # Creator slug (e.g. "iris_bertran")
    evaluator_id: str = "manel"
    user_message: str
    bot_response: str
    coherencia: Optional[int] = Field(None, ge=1, le=5)
    lo_enviarias: Optional[int] = Field(None, ge=1, le=5)
    ideal_response: Optional[str] = None
    error_tags: Optional[List[ErrorTag]] = Field(None, max_length=20)
    error_free_text: Optional[str] = Field(None, max_length=2000)
    conversation_id: Optional[str] = None
    source_message_id: Optional[str] = None
    intent_detected: Optional[str] = None
    doc_d_version: Optional[str] = None
    model_id: Optional[str] = None
    system_prompt_hash: Optional[str] = None

    @field_validator("error_tags")
    @classmethod
    def validate_error_tags_length(cls, v):
        if v is not None and len(v) > 20:
            raise ValueError("Maximum 20 error tags allowed")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_creator(creator_slug: str):
    """Resolve creator slug to DB UUID. Sync — must be called via to_thread."""
    from api.database import SessionLocal
    from api.models import Creator

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter(Creator.name == creator_slug).first()
        if not creator:
            return None
        return creator.id
    finally:
        session.close()


def _do_save_feedback(creator_db_id, payload: dict):
    """Sync wrapper for feedback_store.save_feedback."""
    from services.feedback_store import save_feedback as _save
    return _save(**{"creator_db_id": creator_db_id, **payload})


def _do_get_feedback(creator_db_id, **kwargs):
    from services.feedback_store import get_feedback
    return get_feedback(creator_db_id=creator_db_id, **kwargs)


def _do_get_stats(creator_db_id):
    from services.feedback_store import get_feedback_stats
    return get_feedback_stats(creator_db_id=creator_db_id)


# ---------------------------------------------------------------------------
# Endpoints — FIX FB-06: All sync DB calls via asyncio.to_thread
# ---------------------------------------------------------------------------

@router.post("")
async def save_feedback(payload: FeedbackPayload, _auth=Depends(require_creator_access)):
    """Save structured evaluator feedback. Auto-creates preference pair + gold example."""
    # FIX FB-04: Rate limit
    _check_rate_limit(payload.evaluator_id)

    # Resolve creator slug → UUID (async-safe)
    creator_db_id = await asyncio.to_thread(_resolve_creator, payload.creator_id)
    if creator_db_id is None:
        raise HTTPException(status_code=404, detail=f"Creator '{payload.creator_id}' not found")

    # Build kwargs for save_feedback
    save_kwargs = {
        "evaluator_id": payload.evaluator_id,
        "user_message": payload.user_message,
        "bot_response": payload.bot_response,
        "coherencia": payload.coherencia,
        "lo_enviarias": payload.lo_enviarias,
        "ideal_response": payload.ideal_response,
        "error_tags": [t.model_dump() for t in payload.error_tags] if payload.error_tags else None,
        "error_free_text": payload.error_free_text,
        "conversation_id": payload.conversation_id,
        "source_message_id": payload.source_message_id,
        "intent_detected": payload.intent_detected,
        "doc_d_version": payload.doc_d_version,
        "model_id": payload.model_id,
        "system_prompt_hash": payload.system_prompt_hash,
    }

    result = await asyncio.to_thread(_do_save_feedback, creator_db_id, save_kwargs)

    # FIX FB-07: Handle distinct status codes
    if result.get("status") == "disabled":
        raise HTTPException(status_code=403, detail="Evaluator feedback is disabled (ENABLE_EVALUATOR_FEEDBACK=false)")
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=f"Failed to save feedback: {result.get('message', 'unknown')}")

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
    creator_db_id = await asyncio.to_thread(_resolve_creator, creator_id)
    if creator_db_id is None:
        raise HTTPException(status_code=404, detail=f"Creator '{creator_id}' not found")

    return await asyncio.to_thread(
        _do_get_feedback,
        creator_db_id,
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
    creator_db_id = await asyncio.to_thread(_resolve_creator, creator_id)
    if creator_db_id is None:
        raise HTTPException(status_code=404, detail=f"Creator '{creator_id}' not found")

    result = await asyncio.to_thread(_do_get_stats, creator_db_id)

    # FIX FB-08: Propagate error status
    if isinstance(result, dict) and result.get("status") == "error":
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {result.get('message', 'unknown')}")

    return result
