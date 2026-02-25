"""Lead CRUD endpoints with frontend compatibility"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.auth import require_creator_access
from api.database import get_db
from api.schemas.leads import LeadCreate, LeadUpdate, LeadStatusUpdate

logger = logging.getLogger(__name__)
router = APIRouter()

# Get absolute path for storage
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
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


def adapt_leads_response(x):
    return x


def adapt_lead_response(x):
    return x


try:
    from api.utils.response_adapter import adapt_lead_response, adapt_leads_response
except ImportError as e:
    logger.debug("Ignored ImportError in from api.utils.response_adapter import adapt_le...: %s", e)


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
async def get_leads(creator_id: str, limit: int = 100, _auth: str = Depends(require_creator_access)):
    """Get leads for a creator with caching.

    Args:
        creator_id: Creator's name/ID
        limit: Maximum leads to return (default 100 for performance)
    """
    from api.cache import api_cache

    # Check cache first (30s TTL)
    cache_key = f"leads:{creator_id}:{limit}"
    cached = api_cache.get(cache_key)
    if cached:
        logger.debug(f"[LEADS] {creator_id}: cache HIT")
        return cached

    if USE_DB:
        try:
            leads = db_service.get_leads(creator_id, limit=limit)
            if leads is not None:
                adapted = adapt_leads_response(leads)
                result = {"status": "ok", "leads": adapted, "count": len(adapted)}
                # Cache for 30 seconds (matches frontend polling interval)
                api_cache.set(cache_key, result, ttl_seconds=30)
                return result
        except Exception as e:
            logger.error(f"DB get leads failed for {creator_id}: {e}")
            if not ENABLE_JSON_FALLBACK:
                raise HTTPException(status_code=500, detail="Internal database error")
            logger.warning(f"[FALLBACK] Returning empty leads for {creator_id}")
    return {"status": "ok", "leads": [], "count": 0}


@router.get("/{creator_id}/{lead_id}")
async def get_lead(creator_id: str, lead_id: str, _auth: str = Depends(require_creator_access)):
    if USE_DB:
        try:
            lead = db_service.get_lead_by_id(creator_id, lead_id)
            if lead:
                return {"status": "ok", "lead": adapt_lead_response(lead)}
        except Exception as e:
            logger.error(f"DB get lead failed: {e}")
            if not ENABLE_JSON_FALLBACK:
                raise HTTPException(status_code=500, detail="Internal database error")
            logger.warning(f"[FALLBACK] Trying JSON for lead {lead_id}")

    # Fallback to JSON (only if ENABLE_JSON_FALLBACK or not using DB)
    if ENABLE_JSON_FALLBACK or not USE_DB:
        lead_data = _load_lead_json(creator_id, lead_id)
        if lead_data:
            return {"status": "ok", "lead": lead_data}
    raise HTTPException(status_code=404, detail="Lead not found")


@router.post("/{creator_id}")
async def create_lead(creator_id: str, data: LeadCreate, _auth: str = Depends(require_creator_access)):
    data_dict = data.model_dump(exclude_unset=True)
    # Try PostgreSQL first
    if USE_DB:
        try:
            result = db_service.create_lead(creator_id, data_dict)
            if result:
                return {"status": "ok", "lead": adapt_lead_response(result)}
        except Exception as e:
            logger.warning(f"DB create lead failed: {e}")

    # Fallback to JSON
    try:
        lead_id = data_dict.get("platform_user_id") or f"manual_{int(time.time())}"
        now = datetime.now(timezone.utc).isoformat()
        new_lead = {
            "follower_id": lead_id,
            "creator_id": creator_id,
            "username": data_dict.get("name", "Manual Lead"),
            "name": data_dict.get("name", "Manual Lead"),
            "full_name": data_dict.get("name", "Manual Lead"),
            "first_contact": now,
            "last_contact": now,
            "total_messages": 0,
            "purchase_intent_score": 0,
            "is_lead": True,
            "is_customer": False,
            "email": data_dict.get("email", ""),
            "phone": data_dict.get("phone", ""),
            "notes": data_dict.get("notes", ""),
            "platform": data_dict.get("platform", "manual"),
            "status": data_dict.get("status", "new"),
        }
        _save_lead_json(creator_id, lead_id, new_lead)
        logger.info(f"Created lead {lead_id} via JSON fallback")
        return {"status": "ok", "lead": new_lead}
    except Exception as e:
        logger.error(f"JSON create lead failed: {e}")
        raise HTTPException(status_code=400, detail="Failed to create lead: invalid data")


@router.post("/{creator_id}/manual")
async def create_manual_lead(creator_id: str, data: LeadCreate, _auth: str = Depends(require_creator_access)):
    from api.cache import api_cache

    data_dict = data.model_dump(exclude_unset=True)
    start = time.time()
    # Try PostgreSQL first
    if USE_DB:
        try:
            result = db_service.create_lead(creator_id, data_dict)
            if result:
                api_cache.invalidate(f"conversations:{creator_id}")
                logger.info(f"⏱️ Lead create took {time.time()-start:.2f}s")
                return {"status": "ok", "lead": adapt_lead_response(result)}
        except Exception as e:
            logger.warning(f"DB create lead failed: {e}")

    # Fallback to JSON
    try:
        lead_id = data_dict.get("platform_user_id") or f"manual_{int(time.time())}"
        now = datetime.now(timezone.utc).isoformat()
        new_lead = {
            "follower_id": lead_id,
            "creator_id": creator_id,
            "username": data_dict.get("name", "Manual Lead"),
            "name": data_dict.get("name", "Manual Lead"),
            "full_name": data_dict.get("name", "Manual Lead"),
            "first_contact": now,
            "last_contact": now,
            "total_messages": 0,
            "purchase_intent_score": 0,
            "is_lead": True,
            "is_customer": False,
            "email": data_dict.get("email", ""),
            "phone": data_dict.get("phone", ""),
            "notes": data_dict.get("notes", ""),
            "platform": data_dict.get("platform", "manual"),
            "status": data_dict.get("status", "new"),
        }
        _save_lead_json(creator_id, lead_id, new_lead)
        logger.info(f"Created manual lead {lead_id} via JSON fallback")
        return {"status": "ok", "lead": new_lead}
    except Exception as e:
        logger.error(f"JSON create lead failed: {e}")
        raise HTTPException(status_code=400, detail="Failed to create lead: invalid data")


@router.put("/{creator_id}/{lead_id}")
async def update_lead(creator_id: str, lead_id: str, data: LeadUpdate, _auth: str = Depends(require_creator_access)):
    data_dict = data.model_dump(exclude_unset=True)
    # Try PostgreSQL first
    if USE_DB:
        try:
            result = db_service.update_lead(creator_id, lead_id, data_dict)
            if result and isinstance(result, dict):
                return {
                    "status": "ok",
                    "message": "Lead updated",
                    "lead": adapt_lead_response(result),
                }
        except Exception as e:
            logger.warning(f"DB update lead failed: {e}")

    # Fallback to JSON
    lead_data = _load_lead_json(creator_id, lead_id)
    if lead_data:
        if "name" in data_dict:
            lead_data["name"] = data_dict["name"]
            lead_data["username"] = data_dict["name"]
            lead_data["full_name"] = data_dict["name"]
        if "email" in data_dict:
            lead_data["email"] = data_dict["email"]
        if "phone" in data_dict:
            lead_data["phone"] = data_dict["phone"]
        if "notes" in data_dict:
            lead_data["notes"] = data_dict["notes"]
        if "status" in data_dict:
            lead_data["status"] = data_dict["status"]
        _save_lead_json(creator_id, lead_id, lead_data)
        logger.info(f"Updated lead {lead_id} via JSON fallback")
        return {"status": "ok", "message": "Lead updated", "lead": lead_data}

    raise HTTPException(status_code=404, detail="Lead not found")


@router.delete("/{creator_id}/{lead_id}")
async def delete_lead(creator_id: str, lead_id: str, _auth: str = Depends(require_creator_access)):
    from api.cache import api_cache

    start = time.time()
    # Try PostgreSQL first
    if USE_DB:
        try:
            success = db_service.delete_lead(creator_id, lead_id)
            if success:
                api_cache.invalidate(f"conversations:{creator_id}")
                logger.info(f"⏱️ Lead delete took {time.time()-start:.2f}s")
                return {"status": "ok", "message": "Lead deleted", "deleted": lead_id}

            # Lead not found — check if already deleted (dismissed)
            from api.database import SessionLocal
            from api.models import Creator, DismissedLead

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if creator:
                    dismissed = (
                        session.query(DismissedLead)
                        .filter_by(creator_id=creator.id, platform_user_id=lead_id)
                        .first()
                    )
                    if dismissed:
                        api_cache.invalidate(f"conversations:{creator_id}")
                        return {"status": "ok", "message": "Lead already deleted", "deleted": lead_id}
            finally:
                session.close()

            raise HTTPException(status_code=404, detail="Lead not found")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"DB delete lead failed: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # Fallback to JSON (non-DB setups only)
    path = _get_json_path(creator_id, lead_id)
    if os.path.exists(path):
        os.remove(path)
        logger.info(f"Deleted lead {lead_id} via JSON fallback")
        return {"status": "ok", "message": "Lead deleted", "deleted": lead_id}

    raise HTTPException(status_code=404, detail="Lead not found")


# =============================================================================
# STATUS UPDATE (for drag & drop)
# =============================================================================


@router.put("/{creator_id}/{lead_id}/status")
async def update_lead_status(creator_id: str, lead_id: str, data: LeadStatusUpdate, _auth: str = Depends(require_creator_access)):
    """
    Quick status update for drag & drop in Pipeline.
    Also creates an activity log entry.
    """
    new_status = data.status
    if not new_status:
        raise HTTPException(status_code=400, detail="status is required")

    valid_statuses = ["cliente", "caliente", "colaborador", "amigo", "nuevo", "frío"]
    if new_status not in valid_statuses:
        raise HTTPException(
            status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}"
        )

    if USE_DB:
        try:
            from api.database import SessionLocal
            from api.models import Creator, Lead, LeadActivity

            session = SessionLocal()
            try:
                # Get creator
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    raise HTTPException(status_code=404, detail="Creator not found")

                # Get lead by platform_user_id or UUID
                lead = (
                    session.query(Lead)
                    .filter_by(creator_id=creator.id, platform_user_id=lead_id)
                    .first()
                )

                if not lead:
                    # Try by UUID
                    try:
                        from uuid import UUID

                        lead = session.query(Lead).filter_by(id=UUID(lead_id)).first()
                    except ValueError as e:
                        logger.debug("Ignored ValueError in from uuid import UUID: %s", e)

                if not lead:
                    raise HTTPException(status_code=404, detail="Lead not found in database")

                old_status = lead.status
                lead.status = new_status

                # Create activity log
                activity = LeadActivity(
                    lead_id=lead.id,
                    creator_id=creator.id,
                    activity_type="status_change",
                    description=f"Status changed from {old_status} to {new_status}",
                    old_value=old_status,
                    new_value=new_status,
                    created_by="creator",
                )
                session.add(activity)
                session.commit()

                logger.info(f"Updated lead {lead_id} status: {old_status} -> {new_status}")
                return {
                    "status": "ok",
                    "message": "Status updated",
                    "lead": {
                        "id": str(lead.id),
                        "platform_user_id": lead.platform_user_id,
                        "status": lead.status,
                    },
                }
            finally:
                session.close()
        except HTTPException:
            raise
        except Exception as e:
            from api.utils.error_helpers import safe_error_detail

            raise HTTPException(status_code=500, detail=safe_error_detail(e, "lead status update"))

    raise HTTPException(status_code=503, detail="Database not configured")
