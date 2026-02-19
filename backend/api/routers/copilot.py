"""
Copilot Router - Endpoints para el modo de aprobación de respuestas.

Endpoints:
- GET /copilot/{creator_id}/pending - Obtener respuestas pendientes
- POST /copilot/{creator_id}/approve/{message_id} - Aprobar respuesta
- POST /copilot/{creator_id}/edit/{message_id} - Editar y aprobar respuesta
- POST /copilot/{creator_id}/discard/{message_id} - Descartar respuesta
- GET /copilot/{creator_id}/status - Estado del modo copilot
- PUT /copilot/{creator_id}/toggle - Activar/desactivar modo copilot
- GET /copilot/{creator_id}/notifications - Notificaciones en tiempo real (polling)
- POST /copilot/{creator_id}/manual/{lead_id} - Track manual response (creator writes from scratch)
- GET /copilot/{creator_id}/stats - Copilot action statistics
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import require_creator_access

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/copilot", tags=["copilot"])


class ApproveRequest(BaseModel):
    edited_text: Optional[str] = None


class ToggleRequest(BaseModel):
    enabled: bool


class ManualResponseRequest(BaseModel):
    """Body for manual response tracking (creator writes from scratch)."""
    content: str
    response_time_ms: Optional[int] = None


# =============================================================================
# GET /copilot/{creator_id}/pending
# =============================================================================
@router.get("/{creator_id}/pending")
async def get_pending_responses(creator_id: str, limit: int = 500, offset: int = 0, include_context: bool = False, _auth: str = Depends(require_creator_access)):
    """
    Obtener todas las respuestas pendientes de aprobación con paginación.

    Args:
        include_context: If True, include conversation_context (last 2 sessions, max 15 msgs) per pending item

    Returns:
        List de respuestas pendientes con info del usuario y sugerencia del bot
    """
    from core.copilot_service import get_copilot_service

    service = get_copilot_service()
    result = await service.get_pending_responses(creator_id, limit, offset, include_context=include_context)

    # Handle both old (list) and new (dict with pagination) return formats
    if isinstance(result, dict):
        return {
            "creator_id": creator_id,
            "pending_count": len(result.get("pending", [])),
            "pending_responses": result.get("pending", []),
            "total_count": result.get("total_count", 0),
            "limit": limit,
            "offset": offset,
            "has_more": result.get("has_more", False),
        }
    else:
        # Backwards compatibility with old list format
        return {
            "creator_id": creator_id,
            "pending_count": len(result),
            "pending_responses": result,
            "total_count": len(result),
            "limit": limit,
            "offset": offset,
            "has_more": False,
        }


# =============================================================================
# POST /copilot/{creator_id}/approve/{message_id}
# =============================================================================
@router.post("/{creator_id}/approve/{message_id}")
async def approve_response(creator_id: str, message_id: str, request: ApproveRequest = None, _auth: str = Depends(require_creator_access)):
    """
    Aprobar una respuesta sugerida y enviarla.

    Args:
        message_id: ID del mensaje pendiente
        request.edited_text: Texto editado (opcional, si None se envía la sugerencia original)

    Returns:
        Resultado del envío
    """
    from core.copilot_service import get_copilot_service

    service = get_copilot_service()
    edited_text = request.edited_text if request else None

    result = await service.approve_response(creator_id, message_id, edited_text)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to approve"))

    return result


# =============================================================================
# POST /copilot/{creator_id}/discard/{message_id}
# =============================================================================
class DiscardRequest(BaseModel):
    """Optional body for discard with reason."""
    reason: Optional[str] = None


@router.post("/{creator_id}/discard/{message_id}")
async def discard_response(
    creator_id: str,
    message_id: str,
    body: Optional[DiscardRequest] = None,
    _auth: str = Depends(require_creator_access),
):
    """
    Descartar una respuesta sin enviarla.

    Args:
        message_id: ID del mensaje pendiente
        body: Optional — { "reason": "wrong tone" }

    Returns:
        Confirmación del descarte
    """
    import time

    from core.copilot_service import get_copilot_service

    start = time.time()
    service = get_copilot_service()
    discard_reason = body.reason if body else None
    result = await service.discard_response(creator_id, message_id, discard_reason=discard_reason)
    elapsed = time.time() - start

    logger.info(f"Copilot discard took {elapsed:.2f}s for message {message_id} reason={discard_reason}")

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to discard"))

    return result


# =============================================================================
# GET /copilot/{creator_id}/status
# =============================================================================
@router.get("/{creator_id}/status")
async def get_copilot_status(creator_id: str, _auth: str = Depends(require_creator_access)):
    """
    Obtener estado del modo copilot para un creador.

    Returns:
        - enabled: Si el modo copilot está activado
        - pending_count: Número de respuestas pendientes
    """
    from api.database import SessionLocal
    from api.models import Creator
    from core.copilot_service import get_copilot_service

    # Read directly from DB to avoid multi-worker cache inconsistency
    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        # Read copilot_mode directly from DB (bypass cache)
        enabled = getattr(creator, "copilot_mode", True)
        if enabled is None:
            enabled = True  # Default to True if NULL
    finally:
        session.close()

    service = get_copilot_service()
    pending = await service.get_pending_responses(creator_id, limit=100)

    return {
        "creator_id": creator_id,
        "copilot_enabled": enabled,
        "pending_count": len(pending),
        "status": "active" if enabled else "disabled",
    }


# =============================================================================
# PUT /copilot/{creator_id}/toggle
# =============================================================================
@router.put("/{creator_id}/toggle")
async def toggle_copilot_mode(creator_id: str, request: ToggleRequest, _auth: str = Depends(require_creator_access)):
    """
    Activar o desactivar el modo copilot.

    Si se desactiva:
    - El bot enviará respuestas automáticamente sin aprobación
    - Las respuestas pendientes se mantienen (pueden aprobarse o descartarse)
    """
    from api.database import SessionLocal
    from api.models import Creator
    from core.copilot_service import get_copilot_service

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        creator.copilot_mode = request.enabled
        session.commit()

        # Invalidate cache so status endpoint returns fresh data
        service = get_copilot_service()
        service.invalidate_copilot_cache(creator_id)

        logger.info(
            f"[Copilot] Mode {'enabled' if request.enabled else 'disabled'} for {creator_id}"
        )

        return {
            "creator_id": creator_id,
            "copilot_enabled": request.enabled,
            "message": f"Copilot mode {'enabled' if request.enabled else 'disabled'}",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error toggling mode: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


# =============================================================================
# GET /copilot/{creator_id}/notifications
# =============================================================================
@router.get("/{creator_id}/notifications")
async def get_notifications(creator_id: str, since: Optional[str] = None, _auth: str = Depends(require_creator_access)):
    """
    Endpoint de polling para notificaciones en tiempo real.

    Args:
        since: ISO timestamp - solo retorna notificaciones después de esta fecha

    Returns:
        - new_messages: Mensajes nuevos recibidos
        - pending_responses: Respuestas pendientes de aprobar
        - hot_leads: Leads que se volvieron HOT
    """
    from datetime import timedelta

    from api.database import SessionLocal
    from api.models import Creator, Lead, Message

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        # Parse since timestamp
        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                since_dt = datetime.now(timezone.utc) - timedelta(minutes=5)
        else:
            since_dt = datetime.now(timezone.utc) - timedelta(minutes=5)

        # Nuevos mensajes de usuarios (increased from 20 to 50)
        new_user_messages = (
            session.query(Message, Lead)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id, Message.role == "user", Message.created_at > since_dt
            )
            .order_by(Message.created_at.desc())
            .limit(50)
            .all()
        )

        new_messages = []
        for msg, lead in new_user_messages:
            new_messages.append(
                {
                    "id": str(msg.id),
                    "lead_id": str(lead.id),
                    "follower_id": lead.platform_user_id,
                    "username": lead.username or "",
                    "platform": lead.platform,
                    "content": msg.content,
                    "created_at": msg.created_at.isoformat() if msg.created_at else "",
                }
            )

        # Respuestas pendientes (increased from 20 to 50)
        pending = (
            session.query(Message, Lead)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.status == "pending_approval",
                Message.role == "assistant",
            )
            .order_by(Message.created_at.desc())
            .limit(50)
            .all()
        )

        pending_responses = []
        for msg, lead in pending:
            # Obtener mensaje del usuario
            user_msg = (
                session.query(Message)
                .filter(Message.lead_id == lead.id, Message.role == "user")
                .order_by(Message.created_at.desc())
                .first()
            )

            pending_responses.append(
                {
                    "id": str(msg.id),
                    "lead_id": str(lead.id),
                    "follower_id": lead.platform_user_id,
                    "username": lead.username or "",
                    "platform": lead.platform,
                    "user_message": user_msg.content if user_msg else "",
                    "suggested_response": msg.content,
                    "created_at": msg.created_at.isoformat() if msg.created_at else "",
                }
            )

        # Hot leads recientes (increased from 10 to 25)
        hot_leads = (
            session.query(Lead)
            .filter(
                Lead.creator_id == creator.id, Lead.status == "hot", Lead.last_contact_at > since_dt
            )
            .order_by(Lead.last_contact_at.desc())
            .limit(25)
            .all()
        )

        hot_leads_data = [
            {
                "id": str(lead.id),
                "follower_id": lead.platform_user_id,
                "username": lead.username or "",
                "platform": lead.platform,
                "purchase_intent": lead.purchase_intent or 0.0,
                "last_contact": lead.last_contact_at.isoformat() if lead.last_contact_at else "",
            }
            for lead in hot_leads
        ]

        return {
            "creator_id": creator_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "new_messages_count": len(new_messages),
            "new_messages": new_messages,
            "pending_count": len(pending_responses),
            "pending_responses": pending_responses,
            "hot_leads_count": len(hot_leads_data),
            "hot_leads": hot_leads_data,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error getting notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


# =============================================================================
# POST /copilot/{creator_id}/approve-all
# =============================================================================
@router.post("/{creator_id}/approve-all")
async def approve_all_pending(creator_id: str, _auth: str = Depends(require_creator_access)):
    """
    Aprobar todas las respuestas pendientes de una vez.
    Útil para modo "confiar en el bot".
    """
    from core.copilot_service import get_copilot_service

    service = get_copilot_service()
    pending = await service.get_pending_responses(creator_id)

    results = {"approved": 0, "failed": 0, "errors": []}

    for item in pending:
        result = await service.approve_response(creator_id, item["id"])
        if result.get("success"):
            results["approved"] += 1
        else:
            results["failed"] += 1
            results["errors"].append({"message_id": item["id"], "error": result.get("error")})

    return {"creator_id": creator_id, "results": results}


# =============================================================================
# GET /copilot/{creator_id}/pending-for-lead/{lead_id}
# =============================================================================
@router.get("/{creator_id}/pending-for-lead/{lead_id}")
async def get_pending_for_lead(creator_id: str, lead_id: str, _auth: str = Depends(require_creator_access)):
    """
    Get the pending copilot suggestion for a specific lead, with conversation context.

    Used by the inbox CopilotBanner to show inline approve/edit/discard.
    Returns null if no pending suggestion exists.
    """
    from api.database import SessionLocal
    from api.models import Creator, Lead, Message
    from core.copilot_service import get_copilot_service

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        # Find the lead
        lead = session.query(Lead).filter_by(id=lead_id, creator_id=creator.id).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # Find pending suggestion for this lead
        pending_msg = (
            session.query(Message)
            .filter(
                Message.lead_id == lead.id,
                Message.role == "assistant",
                Message.status == "pending_approval",
            )
            .order_by(Message.created_at.desc())
            .first()
        )

        if not pending_msg:
            return {"pending": None}

        # Get last user message
        user_msg = (
            session.query(Message)
            .filter(Message.lead_id == lead.id, Message.role == "user")
            .order_by(Message.created_at.desc())
            .first()
        )

        service = get_copilot_service()
        context = service._get_conversation_context(session, lead.id)

        return {
            "pending": {
                "id": str(pending_msg.id),
                "lead_id": str(lead.id),
                "follower_id": lead.platform_user_id,
                "platform": lead.platform,
                "username": lead.username or "",
                "full_name": lead.full_name or "",
                "user_message": user_msg.content if user_msg else "",
                "suggested_response": pending_msg.content,
                "intent": pending_msg.intent or "",
                "created_at": pending_msg.created_at.isoformat() if pending_msg.created_at else "",
                "status": pending_msg.status,
                "conversation_context": context,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error getting pending for lead: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


# =============================================================================
# POST /copilot/{creator_id}/manual/{lead_id}
# =============================================================================
@router.post("/{creator_id}/manual/{lead_id}")
async def track_manual_response(
    creator_id: str,
    lead_id: str,
    body: ManualResponseRequest,
    _auth: str = Depends(require_creator_access),
):
    """
    Track when creator writes a manual response from scratch (bypassing bot suggestion).

    This records copilot_action='manual_override' on the sent message
    so the autolearning engine can compare manual vs bot patterns.
    """
    from api.database import SessionLocal
    from api.models import Lead, Message

    session = SessionLocal()
    try:
        lead = session.query(Lead).filter_by(id=lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        now = datetime.now(timezone.utc)

        # Discard any existing pending_approval for this lead (creator chose manual)
        existing_pending = (
            session.query(Message)
            .filter(
                Message.lead_id == lead.id,
                Message.role == "assistant",
                Message.status == "pending_approval",
            )
            .first()
        )

        original_suggestion = None
        if existing_pending:
            original_suggestion = existing_pending.content
            existing_pending.status = "discarded"
            existing_pending.approved_at = now
            existing_pending.approved_by = "creator"
            existing_pending.copilot_action = "discarded"
            if existing_pending.created_at:
                delta = now - existing_pending.created_at
                existing_pending.response_time_ms = int(delta.total_seconds() * 1000)

        # Record the manual message with copilot_action tracking
        from core.copilot_service import get_copilot_service

        service = get_copilot_service()
        edit_diff = None
        if original_suggestion:
            edit_diff = service._calculate_edit_diff(original_suggestion, body.content)

        manual_msg = Message(
            lead_id=lead.id,
            role="assistant",
            content=body.content,
            status="sent",
            copilot_action="manual_override",
            response_time_ms=body.response_time_ms,
            edit_diff=edit_diff,
        )
        session.add(manual_msg)
        session.commit()

        logger.info(
            f"[Copilot] Manual response tracked for lead {lead_id} by {creator_id}"
        )

        return {
            "success": True,
            "message_id": str(manual_msg.id),
            "had_pending_suggestion": original_suggestion is not None,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error tracking manual response: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


# =============================================================================
# GET /copilot/{creator_id}/stats
# =============================================================================
@router.get("/{creator_id}/stats")
async def get_copilot_stats(
    creator_id: str,
    days: int = 30,
    _auth: str = Depends(require_creator_access),
):
    """
    Get copilot action statistics for a creator.

    Returns two sections:
    - copilot_metrics: Real creator decisions (approve/edit/discard/manual) from copilot era
    - legacy_metrics: Historical auto-sent bot messages from before copilot was enabled
    """
    from datetime import timedelta

    from sqlalchemy import func

    from api.database import SessionLocal
    from api.models import Creator, Lead, Message

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        since = datetime.now(timezone.utc) - timedelta(days=days)

        # ── COPILOT METRICS: Only messages with copilot_action set ──
        copilot_stats = (
            session.query(
                func.count().label("total"),
                func.count(func.nullif(Message.copilot_action != "approved", True)).label("approved"),
                func.count(func.nullif(Message.copilot_action != "edited", True)).label("edited"),
                func.count(func.nullif(Message.copilot_action != "discarded", True)).label("discarded"),
                func.count(func.nullif(Message.copilot_action != "manual_override", True)).label("manual"),
                func.avg(Message.response_time_ms).label("avg_response_time_ms"),
                func.avg(Message.confidence_score).label("avg_confidence"),
            )
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.role == "assistant",
                Message.copilot_action.isnot(None),
                Message.created_at >= since,
            )
            .first()
        )

        # Pending count
        pending_count = (
            session.query(func.count())
            .select_from(Message)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.role == "assistant",
                Message.status == "pending_approval",
            )
            .scalar() or 0
        )

        c_total = copilot_stats.total or 0
        c_approved = copilot_stats.approved or 0
        c_edited = copilot_stats.edited or 0
        c_discarded = copilot_stats.discarded or 0
        c_manual = copilot_stats.manual or 0

        # ── LEGACY METRICS: Messages without copilot_action ──
        legacy_auto_sent = (
            session.query(func.count())
            .select_from(Message)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.role == "assistant",
                Message.copilot_action.is_(None),
                Message.status == "sent",
                Message.approved_by.is_(None),
                Message.created_at >= since,
            )
            .scalar() or 0
        )

        legacy_creator_manual = (
            session.query(func.count())
            .select_from(Message)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.role == "assistant",
                Message.copilot_action.is_(None),
                Message.approved_by == "creator_manual",
                Message.created_at >= since,
            )
            .scalar() or 0
        )

        legacy_discarded = (
            session.query(func.count())
            .select_from(Message)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.role == "assistant",
                Message.copilot_action.is_(None),
                Message.status == "discarded",
                Message.created_at >= since,
            )
            .scalar() or 0
        )

        legacy_expired = (
            session.query(func.count())
            .select_from(Message)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.role == "assistant",
                Message.status == "expired",
                Message.created_at >= since,
            )
            .scalar() or 0
        )

        # Edit category breakdown
        edit_categories = (
            session.query(Message.edit_diff)
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator.id,
                Message.copilot_action == "edited",
                Message.edit_diff.isnot(None),
                Message.created_at >= since,
            )
            .all()
        )

        category_counts = {}
        for (diff,) in edit_categories:
            if isinstance(diff, dict):
                for cat in diff.get("categories", []):
                    category_counts[cat] = category_counts.get(cat, 0) + 1

        # ── LEARNING PROGRESS from copilot_evaluations ──
        learning_progress = {
            "days_active": 0,
            "total_interactions": 0,
            "patterns_detected": [],
        }
        try:
            from api.models import CopilotEvaluation

            days_active = (
                session.query(func.count(func.distinct(CopilotEvaluation.eval_date)))
                .filter(
                    CopilotEvaluation.creator_id == creator.id,
                    CopilotEvaluation.eval_type == "daily",
                )
                .scalar() or 0
            )

            # Sum total_actions from daily evaluations
            from sqlalchemy import cast, Integer
            total_interactions_result = (
                session.query(
                    func.sum(cast(CopilotEvaluation.metrics["total_actions"].astext, Integer))
                )
                .filter(
                    CopilotEvaluation.creator_id == creator.id,
                    CopilotEvaluation.eval_type == "daily",
                )
                .scalar() or 0
            )

            # Collect distinct pattern types
            pattern_rows = (
                session.query(CopilotEvaluation.patterns)
                .filter(
                    CopilotEvaluation.creator_id == creator.id,
                    CopilotEvaluation.eval_type == "daily",
                    CopilotEvaluation.patterns.isnot(None),
                )
                .all()
            )
            pattern_types = set()
            for (patterns,) in pattern_rows:
                if isinstance(patterns, list):
                    for p in patterns:
                        if isinstance(p, dict) and "type" in p:
                            pattern_types.add(p["type"])

            learning_progress = {
                "days_active": days_active,
                "total_interactions": int(total_interactions_result),
                "patterns_detected": sorted(pattern_types),
            }
        except Exception as lp_err:
            logger.warning(f"[Copilot] Learning progress query failed: {lp_err}")

        return {
            "creator_id": creator_id,
            "period_days": days,
            "learning_progress": learning_progress,
            # Copilot-era metrics (real creator decisions)
            "copilot_metrics": {
                "total": c_total,
                "approved": c_approved,
                "edited": c_edited,
                "discarded": c_discarded,
                "manual_override": c_manual,
                "pending": pending_count,
                "approval_rate": round(c_approved / c_total, 3) if c_total else 0,
                "edit_rate": round(c_edited / c_total, 3) if c_total else 0,
                "discard_rate": round(c_discarded / c_total, 3) if c_total else 0,
                "manual_rate": round(c_manual / c_total, 3) if c_total else 0,
                "avg_response_time_ms": round(copilot_stats.avg_response_time_ms) if copilot_stats.avg_response_time_ms else None,
                "avg_confidence": round(float(copilot_stats.avg_confidence), 3) if copilot_stats.avg_confidence else None,
                "edit_categories": category_counts,
            },
            # Legacy metrics (pre-copilot automatic mode)
            "legacy_metrics": {
                "auto_sent": legacy_auto_sent,
                "creator_manual": legacy_creator_manual,
                "discarded": legacy_discarded,
                "expired": legacy_expired,
                "total": legacy_auto_sent + legacy_creator_manual + legacy_discarded + legacy_expired,
            },
            # Backward compatibility — total includes both sections
            "total_actions": c_total,
            "approved": c_approved,
            "edited": c_edited,
            "discarded": c_discarded,
            "manual_override": c_manual,
            "approval_rate": round(c_approved / c_total, 3) if c_total else 0,
            "edit_rate": round(c_edited / c_total, 3) if c_total else 0,
            "discard_rate": round(c_discarded / c_total, 3) if c_total else 0,
            "manual_rate": round(c_manual / c_total, 3) if c_total else 0,
            "avg_response_time_ms": round(copilot_stats.avg_response_time_ms) if copilot_stats.avg_response_time_ms else None,
            "avg_confidence": round(float(copilot_stats.avg_confidence), 3) if copilot_stats.avg_confidence else None,
            "edit_categories": category_counts,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


# =============================================================================
# GET /copilot/{creator_id}/comparisons
# =============================================================================
@router.get("/{creator_id}/comparisons")
async def get_copilot_comparisons(
    creator_id: str,
    limit: int = 500,
    offset: int = 0,
    _auth: str = Depends(require_creator_access),
):
    """
    Get side-by-side comparisons of bot suggestions vs real creator responses.

    Two sources of comparisons:
    1. Copilot-era: messages with copilot_action='edited' (suggested_response vs content)
    2. Legacy: bot auto-sent messages paired with nearby creator manual responses
       for the same lead (what bot said vs what creator actually said)
    """
    from sqlalchemy import text

    from api.database import SessionLocal
    from api.models import Creator

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        # Use raw SQL for the lateral join to pair bot auto-sent with creator manual
        rows = session.execute(text("""
            WITH
            -- Source 1: Copilot-era edits (bot suggested → creator edited)
            copilot_edits AS (
                SELECT
                    m.id, m.lead_id, m.suggested_response as bot_suggestion, m.content as creator_response,
                    m.copilot_action as action, m.edit_diff, m.confidence_score,
                    m.response_time_ms, m.created_at,
                    COALESCE(l.full_name, l.username, l.platform_user_id) as lead_name,
                    l.platform, l.platform_user_id,
                    (m.suggested_response = m.content) as is_identical,
                    'copilot' as source,
                    NULL::json as creator_responses_json
                FROM messages m
                JOIN leads l ON m.lead_id = l.id
                WHERE l.creator_id = :creator_id
                AND m.role = 'assistant'
                AND m.copilot_action IN ('edited', 'manual_override', 'approved')
                AND m.suggested_response IS NOT NULL
            ),
            -- Source 2: Legacy — bot auto-sent paired with ALL creator manual responses
            bot_auto AS (
                SELECT m.id, m.lead_id, m.content as bot_suggestion,
                       m.created_at, m.intent, m.confidence_score,
                       COALESCE(l.full_name, l.username, l.platform_user_id) as lead_name,
                       l.platform, l.platform_user_id
                FROM messages m
                JOIN leads l ON m.lead_id = l.id
                WHERE l.creator_id = :creator_id
                AND m.role = 'assistant'
                AND m.copilot_action IS NULL
                AND (m.approved_by IS NULL OR m.approved_by = 'auto')
                AND m.status = 'sent'
                AND m.content NOT IN ('Mentioned you in their story', 'Shared content')
            ),
            legacy_pairs AS (
                SELECT
                    ba.id, ba.lead_id, ba.bot_suggestion, cr.first_response as creator_response,
                    'legacy_comparison' as action,
                    NULL::json as edit_diff, ba.confidence_score,
                    NULL::integer as response_time_ms,
                    ba.created_at,
                    ba.lead_name, ba.platform, ba.platform_user_id,
                    (ba.bot_suggestion = cr.first_response) as is_identical,
                    'legacy' as source,
                    cr.all_responses as creator_responses_json
                FROM bot_auto ba
                CROSS JOIN LATERAL (
                    SELECT
                        (SELECT content FROM messages
                         WHERE lead_id = ba.lead_id AND role = 'assistant'
                         AND approved_by = 'creator_manual'
                         AND created_at BETWEEN ba.created_at - INTERVAL '4 hours'
                                             AND ba.created_at + INTERVAL '24 hours'
                         ORDER BY created_at ASC LIMIT 1
                        ) as first_response,
                        (SELECT json_agg(json_build_object(
                            'content', content,
                            'timestamp', created_at::text
                         ) ORDER BY created_at ASC)
                         FROM messages
                         WHERE lead_id = ba.lead_id AND role = 'assistant'
                         AND approved_by = 'creator_manual'
                         AND created_at BETWEEN ba.created_at - INTERVAL '4 hours'
                                             AND ba.created_at + INTERVAL '24 hours'
                        ) as all_responses
                ) cr
                WHERE cr.first_response IS NOT NULL
            ),
            -- Combine both sources
            all_comparisons AS (
                SELECT * FROM copilot_edits
                UNION ALL
                SELECT * FROM legacy_pairs
            )
            SELECT * FROM all_comparisons
            ORDER BY created_at DESC
            OFFSET :offset
            LIMIT :limit_plus_one
        """), {
            "creator_id": str(creator.id),
            "offset": offset,
            "limit_plus_one": limit + 1,
        }).fetchall()

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        # B3: Collect conversation context per unique lead
        from core.copilot_service import get_copilot_service

        copilot_svc = get_copilot_service()
        lead_context_cache: dict = {}

        comparisons = []
        for row in rows:
            # Build creator_responses array
            creator_responses = None
            if row.creator_responses_json:
                creator_responses = row.creator_responses_json

            # B3: Get conversation context (cached per lead)
            lead_id = row.lead_id
            if lead_id not in lead_context_cache:
                try:
                    before_ts = row.created_at if row.created_at else None
                    lead_context_cache[lead_id] = copilot_svc._get_conversation_context(
                        session, lead_id, max_messages=5, before_timestamp=before_ts
                    )
                except Exception:
                    lead_context_cache[lead_id] = []

            comparisons.append({
                "message_id": str(row.id),
                "bot_original": row.bot_suggestion or "",
                "creator_final": row.creator_response or "",
                "action": row.action,
                "edit_diff": row.edit_diff,
                "confidence": row.confidence_score,
                "response_time_ms": row.response_time_ms,
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "username": row.lead_name or "",
                "platform": row.platform,
                "is_identical": row.is_identical,
                "source": row.source,
                "creator_responses": creator_responses,
                "conversation_context": lead_context_cache.get(lead_id, []),
            })

        return {
            "creator_id": creator_id,
            "comparisons": comparisons,
            "count": len(comparisons),
            "has_more": has_more,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error getting comparisons: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


# =============================================================================
# GET /copilot/{creator_id}/historical-rates
# =============================================================================
@router.get("/{creator_id}/historical-rates")
async def get_historical_rates(
    creator_id: str,
    _auth: str = Depends(require_creator_access),
):
    """
    Get historical approval rates per intent for confidence calibration.

    Used by the autolearning engine to adjust confidence thresholds
    based on how the creator has historically acted on each intent type.
    """
    from core.confidence_scorer import get_historical_rates

    result = get_historical_rates(creator_id)
    return {"creator_id": creator_id, **result}
