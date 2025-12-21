"""Creator config endpoints"""
from fastapi import APIRouter, HTTPException, Body
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/creator/config", tags=["config"])

USE_DB = bool(os.getenv("DATABASE_URL"))
if USE_DB:
    try:
        from api.services import db_service
    except ImportError:
        from api import db_service

@router.get("/{creator_id}")
async def get_creator_config(creator_id: str):
    if USE_DB:
        try:
            config = db_service.get_creator_by_name(creator_id)
            if config:
                return {"status": "ok", "config": config}
        except Exception as e:
            logger.warning(f"DB get config failed for {creator_id}: {e}")
    raise HTTPException(status_code=404, detail="Creator not found")

@router.put("/{creator_id}")
async def update_creator_config(creator_id: str, updates: dict = Body(...)):
    if USE_DB:
        try:
            success = db_service.update_creator(creator_id, updates)
            if success:
                return {"status": "ok", "message": "Config updated"}
        except Exception as e:
            logger.warning(f"DB update config failed for {creator_id}: {e}")
    raise HTTPException(status_code=404, detail="Creator not found")
