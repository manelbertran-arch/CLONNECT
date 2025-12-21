"""Leads endpoints with frontend compatibility"""
from fastapi import APIRouter, HTTPException, Body
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dm/leads", tags=["leads"])

USE_DB = bool(os.getenv("DATABASE_URL"))
if USE_DB:
    try:
        from api.services import db_service
    except ImportError:
        from api import db_service

try:
    from api.utils.response_adapter import adapt_leads_response, adapt_lead_response
except ImportError:
    def adapt_leads_response(x): return x
    def adapt_lead_response(x): return x

@router.get("/{creator_id}")
async def get_leads(creator_id: str):
    if USE_DB:
        try:
            leads = db_service.get_leads(creator_id)
            if leads is not None:
                adapted = adapt_leads_response(leads)
                return {"status": "ok", "leads": adapted, "count": len(adapted)}
        except Exception as e:
            logger.warning(f"DB get leads failed for {creator_id}: {e}")
    return {"status": "ok", "leads": [], "count": 0}

@router.get("/{creator_id}/{lead_id}")
async def get_lead(creator_id: str, lead_id: str):
    if USE_DB:
        try:
            lead = db_service.get_lead_by_id(creator_id, lead_id)
            if lead:
                return {"status": "ok", "lead": adapt_lead_response(lead)}
        except Exception as e:
            logger.warning(f"DB get lead failed: {e}")
    raise HTTPException(status_code=404, detail="Lead not found")

@router.post("/{creator_id}")
async def create_lead(creator_id: str, data: dict = Body(...)):
    if USE_DB:
        try:
            result = db_service.create_lead(creator_id, data)
            if result:
                return {"status": "ok", "lead": adapt_lead_response(result)}
        except Exception as e:
            logger.warning(f"DB create lead failed: {e}")
    raise HTTPException(status_code=500, detail="Failed to create lead")

@router.post("/{creator_id}/manual")
async def create_manual_lead(creator_id: str, data: dict = Body(...)):
    if USE_DB:
        try:
            result = db_service.create_lead(creator_id, data)
            if result:
                return {"status": "ok", "lead": adapt_lead_response(result)}
        except Exception as e:
            logger.warning(f"DB create lead failed: {e}")
    raise HTTPException(status_code=500, detail="Failed to create lead")

@router.put("/{creator_id}/{lead_id}")
async def update_lead(creator_id: str, lead_id: str, data: dict = Body(...)):
    if USE_DB:
        try:
            success = db_service.update_lead(creator_id, lead_id, data)
            if success:
                return {"status": "ok", "message": "Lead updated"}
        except Exception as e:
            logger.warning(f"DB update lead failed: {e}")
    raise HTTPException(status_code=404, detail="Lead not found")

@router.delete("/{creator_id}/{lead_id}")
async def delete_lead(creator_id: str, lead_id: str):
    if USE_DB:
        try:
            success = db_service.delete_lead(creator_id, lead_id)
            if success:
                return {"status": "ok", "message": "Lead deleted"}
        except Exception as e:
            logger.warning(f"DB delete lead failed: {e}")
    raise HTTPException(status_code=404, detail="Lead not found")
