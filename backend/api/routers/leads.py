"""Leads endpoints"""
from fastapi import APIRouter, HTTPException, Request
from datetime import datetime
import logging
import os
import json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dm/leads", tags=["leads"])

USE_DB = bool(os.getenv("DATABASE_URL"))
if USE_DB:
    try:
        from api.services import db_service
    except ImportError:
        from api import db_service

@router.get("/{creator_id}")
async def get_leads(creator_id: str):
    if USE_DB:
        try:
            leads = db_service.get_leads(creator_id)
            if leads is not None:
                return {"status": "ok", "leads": leads, "count": len(leads)}
        except Exception as e:
            logger.warning(f"DB get leads failed for {creator_id}: {e}")
    return {"status": "ok", "leads": [], "count": 0}

@router.post("/{creator_id}/manual")
async def create_manual_lead(creator_id: str, request: Request):
    try:
        data = await request.json()
        if USE_DB:
            try:
                result = db_service.create_lead(creator_id, data)
                if result:
                    return {"status": "ok", "lead": result}
            except Exception as e:
                logger.warning(f"DB create lead failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create lead")
    except Exception as e:
        logger.error(f"Create lead failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
