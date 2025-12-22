"""Dashboard endpoints with frontend compatibility"""
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

# Import config manager for bot status fallback
try:
    from core.creator_config import CreatorConfigManager
    config_manager = CreatorConfigManager()
except ImportError:
    config_manager = None

try:
    from api.utils.response_adapter import adapt_dashboard_response
except ImportError:
    def adapt_dashboard_response(x): return x

@router.get("/{creator_id}/overview")
async def dashboard_overview(creator_id: str):
    if USE_DB:
        try:
            metrics = db_service.get_dashboard_metrics(creator_id)
            if metrics:
                return adapt_dashboard_response(metrics)
        except Exception as e:
            logger.warning(f"DB metrics failed for {creator_id}: {e}")

    # Get real bot status from config manager
    bot_active = True  # Default to active
    if config_manager:
        try:
            bot_active = config_manager.is_bot_active(creator_id)
        except Exception:
            pass

    return adapt_dashboard_response({
        "status": "ok",
        "bot_active": bot_active,
        "creator_name": creator_id,
        "metrics": {},
        "total_leads": 0,
        "hot_leads": 0,
        "warm_leads": 0,
        "cold_leads": 0
    })

@router.put("/{creator_id}/toggle")
async def toggle_clone(creator_id: str, active: bool = None, reason: str = ""):
    if USE_DB:
        try:
            result = db_service.toggle_bot(creator_id, active)
            if result is not None:
                return {
                    "status": "ok",
                    "active": result,
                    "bot_active": result,
                    "botActive": result,
                    "clone_active": result  # Frontend compatibility
                }
        except Exception as e:
            logger.warning(f"DB toggle failed for {creator_id}: {e}")

    # Fallback to config manager
    if config_manager:
        try:
            config_manager.set_active(creator_id, active, reason)
            result = config_manager.is_bot_active(creator_id)
            return {
                "status": "ok",
                "active": result,
                "bot_active": result,
                "botActive": result,
                "clone_active": result
            }
        except Exception as e:
            logger.warning(f"Config toggle failed for {creator_id}: {e}")

    raise HTTPException(status_code=404, detail="Creator not found")
