"""Leads endpoints with frontend compatibility"""
from fastapi import APIRouter, HTTPException, Body
import logging
import os
import json
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dm/leads", tags=["leads"])

# Get absolute path for storage
BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_PATH = BASE_DIR / "data" / "followers"

USE_DB = bool(os.getenv("DATABASE_URL"))
# If False, raise exception on DB failure. If True, silently fall back to JSON.
ENABLE_JSON_FALLBACK = os.getenv("ENABLE_JSON_FALLBACK", "false").lower() == "true"
db_service = None
if USE_DB:
    try:
        from api.services import db_service
        logger.info("leads.py: Using PostgreSQL (db_service loaded)")
    except ImportError:
        try:
            from api import db_service
            logger.info("leads.py: Using PostgreSQL (db_service from api)")
        except ImportError:
            logger.warning("leads.py: db_service import failed, JSON only")
            USE_DB = False

def adapt_leads_response(x): return x
def adapt_lead_response(x): return x

try:
    from api.utils.response_adapter import adapt_leads_response, adapt_lead_response
except ImportError:
    pass

def _get_json_path(creator_id: str, lead_id: str) -> Path:
    return STORAGE_PATH / creator_id / f"{lead_id}.json"

def _load_lead_json(creator_id: str, lead_id: str) -> dict:
    path = _get_json_path(creator_id, lead_id)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def _save_lead_json(creator_id: str, lead_id: str, data: dict):
    creator_dir = STORAGE_PATH / creator_id
    creator_dir.mkdir(parents=True, exist_ok=True)
    path = _get_json_path(creator_id, lead_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved lead to {path}")

@router.get("/{creator_id}")
async def get_leads(creator_id: str):
    if USE_DB:
        try:
            leads = db_service.get_leads(creator_id)
            if leads is not None:
                adapted = adapt_leads_response(leads)
                return {"status": "ok", "leads": adapted, "count": len(adapted)}
        except Exception as e:
            logger.error(f"DB get leads failed for {creator_id}: {e}")
            if not ENABLE_JSON_FALLBACK:
                raise HTTPException(status_code=500, detail=f"Database error: {e}")
            logger.warning(f"[FALLBACK] Returning empty leads for {creator_id}")
    return {"status": "ok", "leads": [], "count": 0}

@router.get("/{creator_id}/{lead_id}")
async def get_lead(creator_id: str, lead_id: str):
    if USE_DB:
        try:
            lead = db_service.get_lead_by_id(creator_id, lead_id)
            if lead:
                return {"status": "ok", "lead": adapt_lead_response(lead)}
        except Exception as e:
            logger.error(f"DB get lead failed: {e}")
            if not ENABLE_JSON_FALLBACK:
                raise HTTPException(status_code=500, detail=f"Database error: {e}")
            logger.warning(f"[FALLBACK] Trying JSON for lead {lead_id}")

    # Fallback to JSON (only if ENABLE_JSON_FALLBACK or not using DB)
    if ENABLE_JSON_FALLBACK or not USE_DB:
        lead_data = _load_lead_json(creator_id, lead_id)
        if lead_data:
            return {"status": "ok", "lead": lead_data}
    raise HTTPException(status_code=404, detail="Lead not found")

@router.post("/{creator_id}")
async def create_lead(creator_id: str, data: dict = Body(...)):
    # Try PostgreSQL first
    if USE_DB:
        try:
            result = db_service.create_lead(creator_id, data)
            if result:
                return {"status": "ok", "lead": adapt_lead_response(result)}
        except Exception as e:
            logger.warning(f"DB create lead failed: {e}")

    # Fallback to JSON
    try:
        lead_id = data.get("platform_user_id") or f"manual_{int(time.time())}"
        now = datetime.now().isoformat()
        new_lead = {
            "follower_id": lead_id,
            "creator_id": creator_id,
            "username": data.get("name", "Manual Lead"),
            "name": data.get("name", "Manual Lead"),
            "full_name": data.get("name", "Manual Lead"),
            "first_contact": now,
            "last_contact": now,
            "total_messages": 0,
            "purchase_intent_score": 0,
            "is_lead": True,
            "is_customer": False,
            "email": data.get("email", ""),
            "phone": data.get("phone", ""),
            "notes": data.get("notes", ""),
            "platform": data.get("platform", "manual"),
            "status": data.get("status", "new"),
        }
        _save_lead_json(creator_id, lead_id, new_lead)
        logger.info(f"Created lead {lead_id} via JSON fallback")
        return {"status": "ok", "lead": new_lead}
    except Exception as e:
        logger.error(f"JSON create lead failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create lead")

@router.post("/{creator_id}/manual")
async def create_manual_lead(creator_id: str, data: dict = Body(...)):
    # Try PostgreSQL first
    if USE_DB:
        try:
            result = db_service.create_lead(creator_id, data)
            if result:
                return {"status": "ok", "lead": adapt_lead_response(result)}
        except Exception as e:
            logger.warning(f"DB create lead failed: {e}")

    # Fallback to JSON
    try:
        lead_id = data.get("platform_user_id") or f"manual_{int(time.time())}"
        now = datetime.now().isoformat()
        new_lead = {
            "follower_id": lead_id,
            "creator_id": creator_id,
            "username": data.get("name", "Manual Lead"),
            "name": data.get("name", "Manual Lead"),
            "full_name": data.get("name", "Manual Lead"),
            "first_contact": now,
            "last_contact": now,
            "total_messages": 0,
            "purchase_intent_score": 0,
            "is_lead": True,
            "is_customer": False,
            "email": data.get("email", ""),
            "phone": data.get("phone", ""),
            "notes": data.get("notes", ""),
            "platform": data.get("platform", "manual"),
            "status": data.get("status", "new"),
        }
        _save_lead_json(creator_id, lead_id, new_lead)
        logger.info(f"Created manual lead {lead_id} via JSON fallback")
        return {"status": "ok", "lead": new_lead}
    except Exception as e:
        logger.error(f"JSON create lead failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create lead")

@router.put("/{creator_id}/{lead_id}")
async def update_lead(creator_id: str, lead_id: str, data: dict = Body(...)):
    # Try PostgreSQL first
    if USE_DB:
        try:
            result = db_service.update_lead(creator_id, lead_id, data)
            if result and isinstance(result, dict):
                return {"status": "ok", "message": "Lead updated", "lead": adapt_lead_response(result)}
        except Exception as e:
            logger.warning(f"DB update lead failed: {e}")

    # Fallback to JSON
    lead_data = _load_lead_json(creator_id, lead_id)
    if lead_data:
        if "name" in data:
            lead_data["name"] = data["name"]
            lead_data["username"] = data["name"]
            lead_data["full_name"] = data["name"]
        if "email" in data:
            lead_data["email"] = data["email"]
        if "phone" in data:
            lead_data["phone"] = data["phone"]
        if "notes" in data:
            lead_data["notes"] = data["notes"]
        if "status" in data:
            lead_data["status"] = data["status"]
        _save_lead_json(creator_id, lead_id, lead_data)
        logger.info(f"Updated lead {lead_id} via JSON fallback")
        return {"status": "ok", "message": "Lead updated", "lead": lead_data}

    raise HTTPException(status_code=404, detail="Lead not found")

@router.delete("/{creator_id}/{lead_id}")
async def delete_lead(creator_id: str, lead_id: str):
    # Try PostgreSQL first
    if USE_DB:
        try:
            success = db_service.delete_lead(creator_id, lead_id)
            if success:
                return {"status": "ok", "message": "Lead deleted"}
        except Exception as e:
            logger.warning(f"DB delete lead failed: {e}")

    # Fallback to JSON
    path = _get_json_path(creator_id, lead_id)
    if os.path.exists(path):
        os.remove(path)
        logger.info(f"Deleted lead {lead_id} via JSON fallback")
        return {"status": "ok", "message": "Lead deleted", "deleted": lead_id}

    raise HTTPException(status_code=404, detail="Lead not found")
