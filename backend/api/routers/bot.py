"""
Bot Router - Bot control endpoints (pause/resume/status)
Extracted from main.py as part of refactoring
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Core imports
from core.creator_config import CreatorConfigManager

router = APIRouter(prefix="/bot", tags=["bot"])

# Global instance
config_manager = CreatorConfigManager()


# ---------------------------------------------------------
# PYDANTIC MODELS
# ---------------------------------------------------------
class PauseBotRequest(BaseModel):
    reason: Optional[str] = None


# ---------------------------------------------------------
# BOT CONTROL ENDPOINTS
# ---------------------------------------------------------
@router.post("/{creator_id}/pause")
async def pause_bot(
    creator_id: str,
    request: PauseBotRequest = PauseBotRequest(),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    """
    Pausar el bot para un creador.
    Los mensajes entrantes no seran respondidos.
    """
    from api.auth import require_creator_or_admin

    await require_creator_or_admin(creator_id, x_api_key)

    success = config_manager.set_active(creator_id, False, request.reason or "Pausado manualmente")

    if not success:
        raise HTTPException(status_code=404, detail="Creator not found")

    logger.info(f"Bot paused for creator {creator_id}")

    return {
        "status": "ok",
        "creator_id": creator_id,
        "bot_active": False,
        "reason": request.reason or "Pausado manualmente",
    }


@router.post("/{creator_id}/resume")
async def resume_bot(creator_id: str, x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    """
    Reanudar el bot para un creador.
    El bot volvera a responder mensajes.
    """
    from api.auth import require_creator_or_admin

    await require_creator_or_admin(creator_id, x_api_key)

    success = config_manager.set_active(creator_id, True)

    if not success:
        raise HTTPException(status_code=404, detail="Creator not found")

    logger.info(f"Bot resumed for creator {creator_id}")

    return {"status": "ok", "creator_id": creator_id, "bot_active": True}


@router.get("/{creator_id}/status")
async def get_bot_status(
    creator_id: str, x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """
    Obtener estado del bot para un creador.
    Looks up from DB (authoritative) with file-based config as fallback.
    """
    from api.auth import require_creator_or_admin
    from api.database import SessionLocal
    from sqlalchemy import text

    await require_creator_or_admin(creator_id, x_api_key)

    # Try DB first (authoritative for all creators)
    try:
        session = SessionLocal()
        try:
            row = session.execute(
                text("SELECT id, name, bot_active FROM creators WHERE name = :name LIMIT 1"),
                {"name": creator_id},
            ).fetchone()
        finally:
            session.close()

        if row:
            return {
                "status": "ok",
                "creator_id": creator_id,
                "exists": True,
                "active": bool(row[2]),
                "source": "db",
            }
    except Exception as e:
        logger.debug(f"DB lookup failed for bot status {creator_id}: {e}")

    # Fallback: file-based config
    file_status = config_manager.get_bot_status(creator_id)
    if not file_status.get("exists"):
        raise HTTPException(status_code=404, detail="Creator not found")

    return {"status": "ok", "creator_id": creator_id, **file_status}
