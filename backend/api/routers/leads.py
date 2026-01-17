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


# =============================================================================
# STATUS UPDATE (for drag & drop)
# =============================================================================

@router.put("/{creator_id}/{lead_id}/status")
async def update_lead_status(creator_id: str, lead_id: str, data: dict = Body(...)):
    """
    Quick status update for drag & drop in Pipeline.
    Also creates an activity log entry.
    """
    new_status = data.get("status")
    if not new_status:
        raise HTTPException(status_code=400, detail="status is required")

    valid_statuses = ["nuevo", "interesado", "caliente", "cliente", "fantasma"]
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    if USE_DB:
        try:
            from api.database import SessionLocal
            from api.models import Lead, LeadActivity, Creator

            session = SessionLocal()
            try:
                # Get creator
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    raise HTTPException(status_code=404, detail="Creator not found")

                # Get lead by platform_user_id or UUID
                lead = session.query(Lead).filter_by(
                    creator_id=creator.id,
                    platform_user_id=lead_id
                ).first()

                if not lead:
                    # Try by UUID
                    try:
                        from uuid import UUID
                        lead = session.query(Lead).filter_by(id=UUID(lead_id)).first()
                    except:
                        pass

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
                    created_by="creator"
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
                        "status": lead.status
                    }
                }
            finally:
                session.close()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"DB update lead status failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=500, detail="Database not configured")


# =============================================================================
# LEAD ACTIVITIES
# =============================================================================

@router.get("/{creator_id}/{lead_id}/activities")
async def get_lead_activities(creator_id: str, lead_id: str, limit: int = 50):
    """Get activity history for a lead"""
    if USE_DB:
        try:
            from api.database import SessionLocal
            from api.models import Lead, LeadActivity, Creator

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    raise HTTPException(status_code=404, detail="Creator not found")

                # Find lead
                lead = session.query(Lead).filter_by(
                    creator_id=creator.id,
                    platform_user_id=lead_id
                ).first()

                if not lead:
                    try:
                        from uuid import UUID
                        lead = session.query(Lead).filter_by(id=UUID(lead_id)).first()
                    except:
                        pass

                if not lead:
                    raise HTTPException(status_code=404, detail="Lead not found for activities")

                activities = session.query(LeadActivity).filter_by(
                    lead_id=lead.id
                ).order_by(LeadActivity.created_at.desc()).limit(limit).all()

                return {
                    "status": "ok",
                    "activities": [
                        {
                            "id": str(a.id),
                            "activity_type": a.activity_type,
                            "description": a.description,
                            "old_value": a.old_value,
                            "new_value": a.new_value,
                            "metadata": a.extra_data or {},
                            "created_by": a.created_by,
                            "created_at": a.created_at.isoformat() if a.created_at else None
                        }
                        for a in activities
                    ]
                }
            finally:
                session.close()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Get activities failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return {"status": "ok", "activities": []}


@router.post("/{creator_id}/{lead_id}/activities")
async def create_lead_activity(creator_id: str, lead_id: str, data: dict = Body(...)):
    """Create a new activity for a lead (note, call, email, etc.)"""
    if USE_DB:
        try:
            from api.database import SessionLocal
            from api.models import Lead, LeadActivity, Creator

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    raise HTTPException(status_code=404, detail="Creator not found")

                # Find lead
                lead = session.query(Lead).filter_by(
                    creator_id=creator.id,
                    platform_user_id=lead_id
                ).first()

                if not lead:
                    try:
                        from uuid import UUID
                        lead = session.query(Lead).filter_by(id=UUID(lead_id)).first()
                    except:
                        pass

                if not lead:
                    raise HTTPException(status_code=404, detail="Lead not found for activity creation")

                activity = LeadActivity(
                    lead_id=lead.id,
                    creator_id=creator.id,
                    activity_type=data.get("activity_type", "note"),
                    description=data.get("description"),
                    extra_data=data.get("metadata", {}),
                    created_by=data.get("created_by", "creator")
                )
                session.add(activity)

                # If it's a note, also update the lead's notes field
                if data.get("activity_type") == "note" and data.get("description"):
                    existing_notes = lead.notes or ""
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
                    new_note = f"[{timestamp}] {data['description']}"
                    lead.notes = f"{new_note}\n\n{existing_notes}".strip() if existing_notes else new_note

                session.commit()

                logger.info(f"Created activity for lead {lead_id}: {data.get('activity_type')}")
                return {
                    "status": "ok",
                    "activity": {
                        "id": str(activity.id),
                        "activity_type": activity.activity_type,
                        "description": activity.description,
                        "created_at": activity.created_at.isoformat() if activity.created_at else None
                    }
                }
            finally:
                session.close()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Create activity failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=500, detail="Database not configured")


# =============================================================================
# LEAD TASKS
# =============================================================================

@router.get("/{creator_id}/{lead_id}/tasks")
async def get_lead_tasks(creator_id: str, lead_id: str, include_completed: bool = False):
    """Get tasks for a lead"""
    if USE_DB:
        try:
            from api.database import SessionLocal
            from api.models import Lead, LeadTask, Creator

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    raise HTTPException(status_code=404, detail="Creator not found")

                # Find lead
                lead = session.query(Lead).filter_by(
                    creator_id=creator.id,
                    platform_user_id=lead_id
                ).first()

                if not lead:
                    try:
                        from uuid import UUID
                        lead = session.query(Lead).filter_by(id=UUID(lead_id)).first()
                    except:
                        pass

                if not lead:
                    raise HTTPException(status_code=404, detail="Lead not found for tasks")

                query = session.query(LeadTask).filter_by(lead_id=lead.id)
                if not include_completed:
                    query = query.filter(LeadTask.status != "completed")

                tasks = query.order_by(LeadTask.due_date.asc().nullslast()).all()

                return {
                    "status": "ok",
                    "tasks": [
                        {
                            "id": str(t.id),
                            "title": t.title,
                            "description": t.description,
                            "task_type": t.task_type,
                            "priority": t.priority,
                            "status": t.status,
                            "due_date": t.due_date.isoformat() if t.due_date else None,
                            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                            "assigned_to": t.assigned_to,
                            "created_at": t.created_at.isoformat() if t.created_at else None
                        }
                        for t in tasks
                    ]
                }
            finally:
                session.close()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Get tasks failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return {"status": "ok", "tasks": []}


@router.post("/{creator_id}/{lead_id}/tasks")
async def create_lead_task(creator_id: str, lead_id: str, data: dict = Body(...)):
    """Create a new task for a lead"""
    if not data.get("title"):
        raise HTTPException(status_code=400, detail="title is required")

    if USE_DB:
        try:
            from api.database import SessionLocal
            from api.models import Lead, LeadTask, LeadActivity, Creator
            from datetime import datetime as dt

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    raise HTTPException(status_code=404, detail="Creator not found")

                # Find lead
                lead = session.query(Lead).filter_by(
                    creator_id=creator.id,
                    platform_user_id=lead_id
                ).first()

                if not lead:
                    try:
                        from uuid import UUID
                        lead = session.query(Lead).filter_by(id=UUID(lead_id)).first()
                    except:
                        pass

                if not lead:
                    raise HTTPException(status_code=404, detail="Lead not found for task creation")

                # Parse due_date if provided
                due_date = None
                if data.get("due_date"):
                    try:
                        due_date = dt.fromisoformat(data["due_date"].replace("Z", "+00:00"))
                    except:
                        pass

                task = LeadTask(
                    lead_id=lead.id,
                    creator_id=creator.id,
                    title=data["title"],
                    description=data.get("description"),
                    task_type=data.get("task_type", "follow_up"),
                    priority=data.get("priority", "medium"),
                    due_date=due_date,
                    assigned_to=data.get("assigned_to"),
                    created_by=data.get("created_by", "creator")
                )
                session.add(task)

                # Log activity
                activity = LeadActivity(
                    lead_id=lead.id,
                    creator_id=creator.id,
                    activity_type="task_created",
                    description=f"Task created: {data['title']}",
                    created_by="creator"
                )
                session.add(activity)

                session.commit()

                logger.info(f"Created task for lead {lead_id}: {data['title']}")
                return {
                    "status": "ok",
                    "task": {
                        "id": str(task.id),
                        "title": task.title,
                        "description": task.description,
                        "task_type": task.task_type,
                        "priority": task.priority,
                        "status": task.status,
                        "due_date": task.due_date.isoformat() if task.due_date else None,
                        "created_at": task.created_at.isoformat() if task.created_at else None
                    }
                }
            finally:
                session.close()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Create task failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=500, detail="Database not configured")


@router.put("/{creator_id}/{lead_id}/tasks/{task_id}")
async def update_lead_task(creator_id: str, lead_id: str, task_id: str, data: dict = Body(...)):
    """Update a task"""
    if USE_DB:
        try:
            from api.database import SessionLocal
            from api.models import LeadTask, LeadActivity, Creator
            from uuid import UUID
            from datetime import datetime as dt

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    raise HTTPException(status_code=404, detail="Creator not found")

                task = session.query(LeadTask).filter_by(id=UUID(task_id)).first()
                if not task:
                    raise HTTPException(status_code=404, detail="Task not found")

                # Update fields
                if "title" in data:
                    task.title = data["title"]
                if "description" in data:
                    task.description = data["description"]
                if "task_type" in data:
                    task.task_type = data["task_type"]
                if "priority" in data:
                    task.priority = data["priority"]
                if "status" in data:
                    old_status = task.status
                    task.status = data["status"]
                    if data["status"] == "completed" and old_status != "completed":
                        task.completed_at = dt.now()
                        # Log completion
                        activity = LeadActivity(
                            lead_id=task.lead_id,
                            creator_id=creator.id,
                            activity_type="task_completed",
                            description=f"Task completed: {task.title}",
                            created_by="creator"
                        )
                        session.add(activity)
                if "due_date" in data:
                    if data["due_date"]:
                        try:
                            task.due_date = dt.fromisoformat(data["due_date"].replace("Z", "+00:00"))
                        except:
                            pass
                    else:
                        task.due_date = None
                if "assigned_to" in data:
                    task.assigned_to = data["assigned_to"]

                session.commit()

                logger.info(f"Updated task {task_id}")
                return {
                    "status": "ok",
                    "task": {
                        "id": str(task.id),
                        "title": task.title,
                        "status": task.status,
                        "due_date": task.due_date.isoformat() if task.due_date else None
                    }
                }
            finally:
                session.close()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Update task failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=500, detail="Database not configured")


@router.delete("/{creator_id}/{lead_id}/tasks/{task_id}")
async def delete_lead_task(creator_id: str, lead_id: str, task_id: str):
    """Delete a task"""
    if USE_DB:
        try:
            from api.database import SessionLocal
            from api.models import LeadTask
            from uuid import UUID

            session = SessionLocal()
            try:
                task = session.query(LeadTask).filter_by(id=UUID(task_id)).first()
                if not task:
                    raise HTTPException(status_code=404, detail="Task not found")

                session.delete(task)
                session.commit()

                logger.info(f"Deleted task {task_id}")
                return {"status": "ok", "message": "Task deleted"}
            finally:
                session.close()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Delete task failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=500, detail="Database not configured")
