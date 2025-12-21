"""Dashboard endpoints"""
from fastapi import APIRouter, HTTPException
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])

USE_DB = bool(os.getenv("DATABASE_URL"))
if USE_DB:
    try:
        from api.services import db_service
    except ImportError:
        from api import db_service

@router.get("/{creator_id}/overview")
async def dashboard_overview(creator_id: str):
    if USE_DB:
        try:
            metrics = db_service.get_dashboard_metrics(creator_id)
            if metrics:
                return metrics
        except Exception as e:
            logger.warning(f"DB metrics failed for {creator_id}: {e}")
    return {"status": "ok", "metrics": {}, "bot_active": False, "creator_name": creator_id}

@router.put("/{creator_id}/toggle")
async def toggle_clone(creator_id: str, active: bool, reason: str = ""):
    if USE_DB:
        try:
            result = db_service.toggle_bot(creator_id, active)
            if result is not None:
                return {"status": "ok", "active": result}
        except Exception as e:
            logger.warning(f"DB toggle failed for {creator_id}: {e}")
    raise HTTPException(status_code=404, detail="Creator not found")
