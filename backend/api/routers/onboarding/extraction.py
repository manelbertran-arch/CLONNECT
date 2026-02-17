"""Personality extraction endpoints — runs the intelligence extraction pipeline."""

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from api.auth import require_creator_access

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])

# In-memory progress tracking for background extractions
_extraction_progress: dict[str, dict] = {}


class ExtractionRequest(BaseModel):
    creator_name: Optional[str] = None
    skip_llm: bool = False
    limit_leads: Optional[int] = None


class ExtractionProgressResponse(BaseModel):
    status: str  # pending, running, completed, error
    phase: str = ""
    percent: int = 0
    details: dict = {}


@router.post("/extraction/{creator_id}/start")
async def start_extraction(
    creator_id: str,
    request: ExtractionRequest,
    background_tasks: BackgroundTasks,
    _auth=require_creator_access,
):
    """Start personality extraction in the background."""
    if creator_id in _extraction_progress and _extraction_progress[creator_id].get("status") == "running":
        raise HTTPException(400, "Extraction already running for this creator")

    _extraction_progress[creator_id] = {
        "status": "running",
        "phase": "starting",
        "percent": 0,
    }

    background_tasks.add_task(
        _run_extraction_background,
        creator_id,
        request.creator_name or "",
        request.skip_llm,
        request.limit_leads,
    )

    return {"status": "started", "message": "Extraction started in background"}


@router.get("/extraction/{creator_id}/progress")
async def get_extraction_progress(
    creator_id: str,
    _auth=require_creator_access,
):
    """Get extraction progress."""
    progress = _extraction_progress.get(creator_id)
    if not progress:
        return {"status": "idle", "phase": "", "percent": 0}
    return progress


@router.post("/extraction/{creator_id}/run")
async def run_extraction_sync(
    creator_id: str,
    request: ExtractionRequest,
    _auth=require_creator_access,
):
    """
    Run personality extraction synchronously (blocking).
    Use for testing or small datasets. For production, use /start.
    """
    from api.database import get_db_session
    from core.personality_extraction.extractor import PersonalityExtractor

    with get_db_session() as db:
        extractor = PersonalityExtractor(db)
        result = await extractor.run(
            creator_id=creator_id,
            creator_name=request.creator_name or "",
            skip_llm=request.skip_llm,
            limit_leads=request.limit_leads,
        )

    return {
        "status": "completed" if not result.errors else "completed_with_errors",
        "duration_seconds": result.duration_seconds,
        "cleaning_stats": {
            "total_messages": result.cleaning_stats.total_messages,
            "creator_real": result.cleaning_stats.creator_real,
            "copilot_ai": result.cleaning_stats.copilot_ai,
            "total_leads": result.cleaning_stats.total_leads,
            "clean_ratio": round(result.cleaning_stats.clean_ratio, 4),
        },
        "profile": {
            "messages_analyzed": result.personality_profile.messages_analyzed,
            "leads_analyzed": result.personality_profile.leads_analyzed,
            "confidence": result.personality_profile.confidence,
        },
        "bot_config": {
            "system_prompt_length": len(result.bot_configuration.system_prompt),
            "blacklist_count": len(result.bot_configuration.blacklist_phrases),
            "template_categories": len(result.bot_configuration.template_categories),
        },
        "copilot_rules": {
            "mode": result.copilot_rules.global_mode,
            "auto_pct": result.copilot_rules.auto_pct,
            "draft_pct": result.copilot_rules.draft_pct,
            "manual_pct": result.copilot_rules.manual_pct,
        },
        "errors": result.errors,
    }


async def _run_extraction_background(
    creator_id: str,
    creator_name: str,
    skip_llm: bool,
    limit_leads: Optional[int],
) -> None:
    """Background task that runs the extraction pipeline."""
    try:
        from api.database import get_db_session
        from core.personality_extraction.extractor import PersonalityExtractor

        _extraction_progress[creator_id] = {
            "status": "running",
            "phase": "data_cleaning",
            "percent": 10,
        }

        with get_db_session() as db:
            extractor = PersonalityExtractor(db)
            result = await extractor.run(
                creator_id=creator_id,
                creator_name=creator_name,
                skip_llm=skip_llm,
                limit_leads=limit_leads,
            )

        _extraction_progress[creator_id] = {
            "status": "completed" if not result.errors else "completed_with_errors",
            "phase": "done",
            "percent": 100,
            "details": {
                "duration_seconds": result.duration_seconds,
                "total_messages": result.cleaning_stats.total_messages,
                "total_leads": result.cleaning_stats.total_leads,
                "confidence": result.personality_profile.confidence,
                "errors": result.errors,
            },
        }

    except Exception as e:
        logger.error("Background extraction failed: %s", e, exc_info=True)
        _extraction_progress[creator_id] = {
            "status": "error",
            "phase": "failed",
            "percent": 0,
            "details": {"error": str(e)},
        }
