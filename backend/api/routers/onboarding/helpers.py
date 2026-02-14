"""Shared state, DB helpers, and Pydantic models for onboarding sub-routers."""

import logging
from typing import Dict, List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# =============================================================================
# SETUP STATUS - Now persisted in DB (with memory cache for fast access)
# =============================================================================

setup_status: Dict[str, Dict] = {}  # Memory cache, also persisted to DB


def _update_clone_status_db(creator_id: str, status_data: Dict):
    """Persist clone setup status to database (survives deploys)."""
    try:
        from datetime import datetime, timezone

        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if creator:
                creator.clone_status = status_data.get("status", "in_progress")
                creator.clone_progress = status_data
                if status_data.get("status") == "in_progress" and not creator.clone_started_at:
                    creator.clone_started_at = datetime.now(timezone.utc)
                if status_data.get("status") in ["completed", "failed"]:
                    creator.clone_completed_at = datetime.now(timezone.utc)
                session.commit()
                logger.debug(
                    f"[CloneStatus] Saved to DB: {creator_id} -> {status_data.get('status')}"
                )
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"[CloneStatus] Failed to save to DB: {e}")


def _get_clone_status_db(creator_id: str) -> Optional[Dict]:
    """Get clone setup status from database."""
    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if creator and creator.clone_progress:
                return creator.clone_progress
            elif creator:
                return {
                    "status": creator.clone_status or "pending",
                    "progress": (
                        0
                        if creator.clone_status == "pending"
                        else 100 if creator.clone_status == "completed" else 0
                    ),
                    "current_step": (
                        "completed" if creator.clone_status == "completed" else "pending"
                    ),
                    "steps_completed": [],
                    "errors": [],
                    "warnings": [],
                    "result": {},
                }
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"[CloneStatus] Failed to read from DB: {e}")
    return None


# =============================================================================
# PYDANTIC MODELS FOR MAGIC SLICE ONBOARDING
# =============================================================================


class PostInput(BaseModel):
    """Post input for onboarding."""

    caption: str
    post_id: Optional[str] = None
    post_type: Optional[str] = "instagram_post"
    url: Optional[str] = None
    permalink: Optional[str] = None
    timestamp: Optional[str] = None
    likes_count: Optional[int] = None
    comments_count: Optional[int] = None


class QuickOnboardRequest(BaseModel):
    """Request simplificado para onboarding rapido."""

    creator_id: str
    posts: List[PostInput]


class FullOnboardRequest(BaseModel):
    """Request completo para onboarding."""

    creator_id: str
    instagram_username: Optional[str] = None
    instagram_access_token: Optional[str] = None
    manual_posts: Optional[List[Dict]] = None
    scraping_method: str = "manual"
    max_posts: int = 50
