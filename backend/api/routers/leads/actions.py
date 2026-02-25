"""Lead actions: activities, tasks, stats, and other endpoints"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from api.auth import require_creator_access
from api.database import get_db
from api.routers.leads.crud import USE_DB

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# LEAD ACTIVITIES
# =============================================================================


@router.get("/{creator_id}/{lead_id}/activities")
async def get_lead_activities(creator_id: str, lead_id: str, limit: int = 50, offset: int = 0, _auth: str = Depends(require_creator_access)):
    """Get activity history for a lead with pagination"""
    if USE_DB:
        try:
            from api.database import SessionLocal
            from api.models import Creator, Lead, LeadActivity

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    raise HTTPException(status_code=404, detail="Creator not found")

                # Find lead
                lead = (
                    session.query(Lead)
                    .filter_by(creator_id=creator.id, platform_user_id=lead_id)
                    .first()
                )

                if not lead:
                    try:
                        from uuid import UUID

                        lead = session.query(Lead).filter_by(id=UUID(lead_id)).first()
                    except ValueError as e:
                        logger.debug("Ignored ValueError in from uuid import UUID: %s", e)

                if not lead:
                    raise HTTPException(status_code=404, detail="Lead not found for activities")

                # Get total count
                total_count = session.query(LeadActivity).filter_by(lead_id=lead.id).count()

                # Get paginated activities
                activities = (
                    session.query(LeadActivity)
                    .filter_by(lead_id=lead.id)
                    .order_by(LeadActivity.created_at.desc())
                    .offset(offset)
                    .limit(limit)
                    .all()
                )

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
                            "created_at": a.created_at.isoformat() if a.created_at else None,
                        }
                        for a in activities
                    ],
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "has_more": offset + len(activities) < total_count,
                }
            finally:
                session.close()
        except HTTPException:
            raise
        except Exception as e:
            from api.utils.error_helpers import safe_error_detail

            raise HTTPException(status_code=500, detail=safe_error_detail(e, "get activities"))

    return {"status": "ok", "activities": []}


@router.post("/{creator_id}/{lead_id}/activities")
async def create_lead_activity(creator_id: str, lead_id: str, data: dict = Body(...), _auth: str = Depends(require_creator_access)):
    """Create a new activity for a lead (note, call, email, etc.)"""
    if USE_DB:
        try:
            from api.database import SessionLocal
            from api.models import Creator, Lead, LeadActivity

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    raise HTTPException(status_code=404, detail="Creator not found")

                # Find lead
                lead = (
                    session.query(Lead)
                    .filter_by(creator_id=creator.id, platform_user_id=lead_id)
                    .first()
                )

                if not lead:
                    try:
                        from uuid import UUID

                        lead = session.query(Lead).filter_by(id=UUID(lead_id)).first()
                    except ValueError as e:
                        logger.debug("Ignored ValueError in from uuid import UUID: %s", e)

                if not lead:
                    raise HTTPException(
                        status_code=404, detail="Lead not found for activity creation"
                    )

                activity = LeadActivity(
                    lead_id=lead.id,
                    creator_id=creator.id,
                    activity_type=data.get("activity_type", "note"),
                    description=data.get("description"),
                    extra_data=data.get("metadata", {}),
                    created_by=data.get("created_by", "creator"),
                )
                session.add(activity)

                # If it's a note, also update the lead's notes field
                if data.get("activity_type") == "note" and data.get("description"):
                    existing_notes = lead.notes or ""
                    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
                    new_note = f"[{timestamp}] {data['description']}"
                    lead.notes = (
                        f"{new_note}\n\n{existing_notes}".strip() if existing_notes else new_note
                    )

                session.commit()

                logger.info(f"Created activity for lead {lead_id}: {data.get('activity_type')}")
                return {
                    "status": "ok",
                    "activity": {
                        "id": str(activity.id),
                        "activity_type": activity.activity_type,
                        "description": activity.description,
                        "created_at": (
                            activity.created_at.isoformat() if activity.created_at else None
                        ),
                    },
                }
            finally:
                session.close()
        except HTTPException:
            raise
        except Exception as e:
            from api.utils.error_helpers import safe_error_detail

            raise HTTPException(status_code=500, detail=safe_error_detail(e, "create activity"))

    raise HTTPException(status_code=503, detail="Database not configured")


@router.delete("/{creator_id}/{lead_id}/activities/{activity_id}")
async def delete_lead_activity(creator_id: str, lead_id: str, activity_id: str, _auth: str = Depends(require_creator_access)):
    """Delete an activity from lead history"""
    if USE_DB:
        try:
            from uuid import UUID

            from api.database import SessionLocal
            from api.models import LeadActivity

            session = SessionLocal()
            try:
                activity = session.query(LeadActivity).filter_by(id=UUID(activity_id)).first()
                if not activity:
                    raise HTTPException(status_code=404, detail="Activity not found")

                session.delete(activity)
                session.commit()

                logger.info(f"Deleted activity {activity_id}")
                return {"status": "ok", "message": "Activity deleted"}
            finally:
                session.close()
        except HTTPException:
            raise
        except Exception as e:
            from api.utils.error_helpers import safe_error_detail

            raise HTTPException(status_code=500, detail=safe_error_detail(e, "delete activity"))

    raise HTTPException(status_code=503, detail="Database not configured")


# =============================================================================
# LEAD TASKS
# =============================================================================


@router.get("/{creator_id}/{lead_id}/tasks")
async def get_lead_tasks(creator_id: str, lead_id: str, include_completed: bool = False, _auth: str = Depends(require_creator_access)):
    """Get tasks for a lead"""
    if USE_DB:
        try:
            from api.database import SessionLocal
            from api.models import Creator, Lead, LeadTask

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    raise HTTPException(status_code=404, detail="Creator not found")

                # Find lead
                lead = (
                    session.query(Lead)
                    .filter_by(creator_id=creator.id, platform_user_id=lead_id)
                    .first()
                )

                if not lead:
                    try:
                        from uuid import UUID

                        lead = session.query(Lead).filter_by(id=UUID(lead_id)).first()
                    except ValueError as e:
                        logger.debug("Ignored ValueError in from uuid import UUID: %s", e)

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
                            "created_at": t.created_at.isoformat() if t.created_at else None,
                        }
                        for t in tasks
                    ],
                }
            finally:
                session.close()
        except HTTPException:
            raise
        except Exception as e:
            from api.utils.error_helpers import safe_error_detail

            raise HTTPException(status_code=500, detail=safe_error_detail(e, "get tasks"))

    return {"status": "ok", "tasks": []}


@router.post("/{creator_id}/{lead_id}/tasks")
async def create_lead_task(creator_id: str, lead_id: str, data: dict = Body(...), _auth: str = Depends(require_creator_access)):
    """Create a new task for a lead"""
    if not data.get("title"):
        raise HTTPException(status_code=400, detail="title is required")

    if USE_DB:
        try:
            from datetime import datetime as dt

            from api.database import SessionLocal
            from api.models import Creator, Lead, LeadActivity, LeadTask

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    raise HTTPException(status_code=404, detail="Creator not found")

                # Find lead
                lead = (
                    session.query(Lead)
                    .filter_by(creator_id=creator.id, platform_user_id=lead_id)
                    .first()
                )

                if not lead:
                    try:
                        from uuid import UUID

                        lead = session.query(Lead).filter_by(id=UUID(lead_id)).first()
                    except ValueError as e:
                        logger.debug("Ignored ValueError in from uuid import UUID: %s", e)

                if not lead:
                    raise HTTPException(status_code=404, detail="Lead not found for task creation")

                # Parse due_date if provided
                due_date = None
                if data.get("due_date"):
                    try:
                        due_date = dt.fromisoformat(data["due_date"].replace("Z", "+00:00"))
                    except ValueError as e:
                        logger.debug("Ignored ValueError in due_date = dt.fromisoformat(data['due_date'].re...: %s", e)

                task = LeadTask(
                    lead_id=lead.id,
                    creator_id=creator.id,
                    title=data["title"],
                    description=data.get("description"),
                    task_type=data.get("task_type", "follow_up"),
                    priority=data.get("priority", "medium"),
                    due_date=due_date,
                    assigned_to=data.get("assigned_to"),
                    created_by=data.get("created_by", "creator"),
                )
                session.add(task)

                # Log activity
                activity = LeadActivity(
                    lead_id=lead.id,
                    creator_id=creator.id,
                    activity_type="task_created",
                    description=f"Task created: {data['title']}",
                    created_by="creator",
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
                        "created_at": task.created_at.isoformat() if task.created_at else None,
                    },
                }
            finally:
                session.close()
        except HTTPException:
            raise
        except Exception as e:
            from api.utils.error_helpers import safe_error_detail

            raise HTTPException(status_code=500, detail=safe_error_detail(e, "create task"))

    raise HTTPException(status_code=503, detail="Database not configured")


@router.put("/{creator_id}/{lead_id}/tasks/{task_id}")
async def update_lead_task(creator_id: str, lead_id: str, task_id: str, data: dict = Body(...), _auth: str = Depends(require_creator_access)):
    """Update a task"""
    if USE_DB:
        try:
            from datetime import datetime as dt
            from uuid import UUID

            from api.database import SessionLocal
            from api.models import Creator, LeadActivity, LeadTask

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
                            created_by="creator",
                        )
                        session.add(activity)
                if "due_date" in data:
                    if data["due_date"]:
                        try:
                            task.due_date = dt.fromisoformat(
                                data["due_date"].replace("Z", "+00:00")
                            )
                        except ValueError as e:
                            logger.debug("Ignored ValueError in task.due_date = dt.fromisoformat(: %s", e)
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
                        "due_date": task.due_date.isoformat() if task.due_date else None,
                    },
                }
            finally:
                session.close()
        except HTTPException:
            raise
        except Exception as e:
            from api.utils.error_helpers import safe_error_detail

            raise HTTPException(status_code=500, detail=safe_error_detail(e, "update task"))

    raise HTTPException(status_code=503, detail="Database not configured")


@router.delete("/{creator_id}/{lead_id}/tasks/{task_id}")
async def delete_lead_task(creator_id: str, lead_id: str, task_id: str, _auth: str = Depends(require_creator_access)):
    """Delete a task"""
    if USE_DB:
        try:
            from uuid import UUID

            from api.database import SessionLocal
            from api.models import LeadTask

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
            from api.utils.error_helpers import safe_error_detail

            raise HTTPException(status_code=500, detail=safe_error_detail(e, "delete task"))

    raise HTTPException(status_code=503, detail="Database not configured")


# =============================================================================
# LEAD STATS (Monitoring/Analytics)
# =============================================================================


@router.get("/{creator_id}/{lead_id}/stats")
async def get_lead_stats(
    creator_id: str,
    lead_id: str,
    _auth: str = Depends(require_creator_access),
    db: Session = Depends(get_db),
):
    """
    Get INTELLIGENT monitoring stats for a lead using the signals system.
    Analyzes conversation to predict sale probability, detect product interest, and suggest next steps.
    """
    if USE_DB:
        try:
            from datetime import datetime, timezone

            from sqlalchemy.orm import load_only

            from api.models import Creator, Lead, Message
            from api.services.signals import analyze_conversation_signals

            creator = db.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                raise HTTPException(status_code=404, detail="Creator not found")

            # Find lead by platform_user_id or UUID
            lead = (
                db.query(Lead)
                .filter_by(creator_id=creator.id, platform_user_id=lead_id)
                .first()
            )

            if not lead:
                try:
                    from uuid import UUID

                    lead = db.query(Lead).filter_by(id=UUID(lead_id)).first()
                except ValueError as e:
                    logger.debug("Ignored ValueError in from uuid import UUID: %s", e)

            if not lead:
                raise HTTPException(status_code=404, detail="Lead not found")

            # Get recent messages ordered by time (limit to 200 for performance)
            # Only load role/content/created_at — skip msg_metadata (heavy JSON blobs)
            messages = (
                db.query(Message)
                .filter_by(lead_id=lead.id)
                .options(load_only(Message.role, Message.content, Message.created_at))
                .order_by(Message.created_at.desc())
                .limit(200)
                .all()
            )
            messages.reverse()  # Back to chronological order

            # Use the intelligent signals analyzer
            analysis = analyze_conversation_signals(messages, lead.status)

            # Calculate engagement level
            metrics = analysis["metricas_comportamiento"]
            lead_msg_count = metrics["total_mensajes_lead"]

            hours_since_response = None
            if lead.last_contact_at:
                lc = lead.last_contact_at
                if lc.tzinfo is None:
                    lc = lc.replace(tzinfo=timezone.utc)
                hours_since_response = (datetime.now(timezone.utc) - lc).total_seconds() / 3600

            if (
                lead_msg_count > 10
                and hours_since_response is not None
                and hours_since_response < 24
            ):
                engagement = "Alto"
                engagement_detalle = f"{lead_msg_count} mensajes · última respuesta hace {int(hours_since_response)}h"
            elif lead_msg_count >= 3 or (
                hours_since_response is not None and 24 <= hours_since_response <= 168
            ):
                engagement = "Medio"
                if hours_since_response and hours_since_response >= 24:
                    days = int(hours_since_response / 24)
                    engagement_detalle = (
                        f"{lead_msg_count} mensajes · última respuesta hace {days} días"
                    )
                else:
                    engagement_detalle = f"{lead_msg_count} mensajes"
            else:
                engagement = "Bajo"
                if hours_since_response and hours_since_response > 168:
                    days = int(hours_since_response / 24)
                    engagement_detalle = (
                        f"{lead_msg_count} mensajes · última respuesta hace {days} días"
                    )
                else:
                    engagement_detalle = f"{lead_msg_count} mensajes"

            # Build response with all the intelligent analysis
            return {
                "status": "ok",
                "stats": {
                    # Core prediction
                    "probabilidad_venta": analysis["probabilidad_venta"],
                    "confianza_prediccion": analysis["confianza_prediccion"],
                    "producto_detectado": analysis["producto_detectado"],
                    "valor_estimado": analysis["valor_estimado"],
                    # Signals
                    "senales_detectadas": analysis["senales_detectadas"],
                    "senales_por_categoria": analysis["senales_por_categoria"],
                    "total_senales": analysis["total_senales"],
                    # Next step
                    "siguiente_paso": analysis["siguiente_paso"],
                    # Engagement
                    "engagement": engagement,
                    "engagement_detalle": engagement_detalle,
                    # Metrics
                    "metricas": metrics,
                    "mensajes_lead": metrics["total_mensajes_lead"],
                    "mensajes_bot": metrics["total_mensajes_bot"],
                    # Timeline
                    "primer_contacto": (
                        lead.first_contact_at.isoformat() if lead.first_contact_at else None
                    ),
                    "ultimo_contacto": (
                        lead.last_contact_at.isoformat() if lead.last_contact_at else None
                    ),
                    "current_stage": lead.status,
                },
            }
        except HTTPException:
            raise
        except Exception as e:
            from api.utils.error_helpers import safe_error_detail

            raise HTTPException(status_code=500, detail=safe_error_detail(e, "get lead stats"))

    # Fallback for no DB
    return {
        "status": "ok",
        "stats": {
            "probabilidad_venta": 0,
            "confianza_prediccion": "Baja",
            "producto_detectado": None,
            "valor_estimado": 0,
            "senales_detectadas": [],
            "senales_por_categoria": {
                "compra": [],
                "interes": [],
                "objecion": [],
                "comportamiento": [],
            },
            "total_senales": 0,
            "siguiente_paso": {
                "accion": "esperar",
                "emoji": "⏳",
                "texto": "Esperando datos",
                "prioridad": "baja",
            },
            "engagement": "Bajo",
            "engagement_detalle": "Sin mensajes",
            "metricas": {},
            "mensajes_lead": 0,
            "mensajes_bot": 0,
            "primer_contacto": None,
            "ultimo_contacto": None,
            "current_stage": "nuevo",
        },
    }
