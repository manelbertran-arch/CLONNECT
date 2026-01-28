"""
Creator Router - Creator configuration and management endpoints
Extracted from main.py as part of refactoring
"""
import logging
import os
from typing import Optional

from fastapi import APIRouter, Body, Header, HTTPException

logger = logging.getLogger(__name__)

# Core imports
from core.creator_config import CreatorConfig, CreatorConfigManager
from core.memory import MemoryStore

# Database imports
USE_DB = bool(os.getenv("DATABASE_URL"))
if USE_DB:
    try:
        from api.services import db_service
    except ImportError:
        from api import db_service
else:
    db_service = None

router = APIRouter(tags=["creator"])

# Global instances
config_manager = CreatorConfigManager()
memory_store = MemoryStore()


# ---------------------------------------------------------
# CREATOR CONFIG ENDPOINTS
# ---------------------------------------------------------
@router.post("/creator/config")
async def create_creator_config(config_data: dict):
    """Crear configuracion de creador"""
    try:
        config = CreatorConfig(**config_data)
        config_id = config_manager.create_config(config)
        return {"status": "ok", "creator_id": config_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/creator/config/{creator_id}")
async def get_creator_config(creator_id: str):
    """Obtener configuracion de creador"""
    # PostgreSQL first - auto-create if doesn't exist
    if USE_DB and db_service:
        try:
            config = db_service.get_or_create_creator(creator_id)
            if config:
                return {"status": "ok", "config": config}
            logger.warning(f"get_or_create_creator returned None for {creator_id}")
        except Exception as e:
            logger.error(f"Error getting creator config from DB: {e}")

    # Fallback to JSON config manager
    config = config_manager.get_config(creator_id)
    if config:
        return {"status": "ok", "config": config.to_dict()}

    # Ultimate fallback - return default config instead of 404
    logger.warning(f"Returning default config for creator '{creator_id}'")
    return {
        "status": "ok",
        "config": {
            "id": creator_id,
            "name": creator_id,
            "email": None,
            "bot_active": True,
            "clone_tone": "friendly",
            "clone_style": "",
            "clone_name": creator_id,
            "clone_vocabulary": "",
            "welcome_message": "",
            "other_payment_methods": {},
            "knowledge_about": {},
        },
    }


@router.put("/creator/config/{creator_id}")
async def update_creator_config(creator_id: str, updates: dict = Body(...)):
    """Actualizar configuracion de creador"""
    config = config_manager.update_config(creator_id, updates)
    # PostgreSQL first
    if USE_DB and db_service:
        success = db_service.update_creator(creator_id, updates)
        if success:
            return {"status": "ok", "message": "Config updated"}
    if not config:
        raise HTTPException(status_code=404, detail="Creator not found")
    return {"status": "ok", "config": config.to_dict()}


@router.delete("/creator/config/{creator_id}")
async def delete_creator_config(creator_id: str):
    """Eliminar configuracion de creador"""
    success = config_manager.delete_config(creator_id)
    if not success:
        raise HTTPException(status_code=404, detail="Creator not found")
    return {"status": "ok"}


@router.get("/creator/list")
async def list_creators():
    """Listar todos los creadores"""
    creators = config_manager.list_creators()
    return {"status": "ok", "creators": creators, "count": len(creators)}


# ---------------------------------------------------------
# CREATOR DATA RESET
# ---------------------------------------------------------
@router.delete("/creator/{creator_id}/reset")
async def reset_creator_data(
    creator_id: str, x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """
    Reset all test/follower data for a creator.

    Deletes:
    - All followers (data/followers/{creator_id}/)
    - All analytics (data/analytics/{creator_id}/)

    Keeps:
    - Creator config (data/creators/{creator_id}.json)
    - Products (data/products/{creator_id}/)

    Requires creator API key or admin key.
    """
    from api.auth import require_creator_or_admin

    await require_creator_or_admin(creator_id, x_api_key)

    data_path = os.getenv("DATA_PATH", "./data")
    deleted = {"followers": 0, "analytics": 0}
    errors = []

    # Delete followers directory
    followers_path = os.path.join(data_path, "followers", creator_id)
    if os.path.exists(followers_path):
        try:
            for file in os.listdir(followers_path):
                file_path = os.path.join(followers_path, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    deleted["followers"] += 1
            logger.info(f"Deleted {deleted['followers']} follower files for {creator_id}")
        except Exception as e:
            errors.append(f"Error deleting followers: {e}")
            logger.error(f"Error deleting followers for {creator_id}: {e}")

    # Delete analytics directory
    analytics_path = os.path.join(data_path, "analytics", creator_id)
    if os.path.exists(analytics_path):
        try:
            for file in os.listdir(analytics_path):
                file_path = os.path.join(analytics_path, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    deleted["analytics"] += 1
            logger.info(f"Deleted {deleted['analytics']} analytics files for {creator_id}")
        except Exception as e:
            errors.append(f"Error deleting analytics: {e}")
            logger.error(f"Error deleting analytics for {creator_id}: {e}")

    # Clear memory store cache if exists
    try:
        memory_store.clear_creator_cache(creator_id)
    except Exception as e:
        logger.debug(f"Memory store cache clear skipped: {e}")

    return {
        "status": "ok" if not errors else "partial",
        "creator_id": creator_id,
        "deleted": deleted,
        "errors": errors if errors else None,
        "note": "Config and products were preserved",
    }
