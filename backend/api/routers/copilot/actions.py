"""
Copilot Router - Action endpoints (approve, discard, toggle, manual, etc.).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import require_creator_access

logger = logging.getLogger(__name__)
router = APIRouter(tags=["copilot"])


class ApproveRequest(BaseModel):
    edited_text: Optional[str] = None
    chosen_index: Optional[int] = None  # Index into best_of_n candidates[]


class ToggleRequest(BaseModel):
    enabled: bool


class ManualResponseRequest(BaseModel):
    """Body for manual response tracking (creator writes from scratch)."""
    content: str
    response_time_ms: Optional[int] = None


class DiscardRequest(BaseModel):
    """Optional body for discard with reason."""
    reason: Optional[str] = None


class MarkExportedRequest(BaseModel):
    pair_ids: list[str]


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

    edited_text = request.edited_text if request else None
    chosen_index = request.chosen_index if request else None
    logger.info(f"[Copilot] POST approve: creator={creator_id} msg={message_id} edited={edited_text is not None} chosen_index={chosen_index}")

    service = get_copilot_service()
    result = await service.approve_response(creator_id, message_id, edited_text, chosen_index)

    if not result.get("success"):
        logger.warning(f"[Copilot] Approve failed: {result.get('error')}")
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to approve"))

    logger.info(f"[Copilot] Approve success: msg={message_id} was_edited={result.get('was_edited')}")
    return result


# =============================================================================
# POST /copilot/{creator_id}/discard/{message_id}
# =============================================================================
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
# POST /copilot/{creator_id}/discard-all
# =============================================================================
@router.post("/{creator_id}/discard-all")
async def discard_all_pending(creator_id: str, _auth: str = Depends(require_creator_access)):
    """Discard ALL pending suggestions for this creator (used for bulk cleanup)."""
    from sqlalchemy import func

    from api.database import SessionLocal
    from api.models import Creator, Lead, Message

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        now = datetime.now(timezone.utc)
        count = (
            session.query(Message)
            .filter(
                Message.lead_id.in_(
                    session.query(Lead.id).filter(Lead.creator_id == creator.id)
                ),
                Message.role == "assistant",
                Message.status == "pending_approval",
            )
            .update(
                {
                    Message.status: "discarded",
                    Message.copilot_action: "bulk_purge",
                    Message.approved_at: now,
                },
                synchronize_session="fetch",
            )
        )
        session.commit()

        logger.info(f"[Copilot] Bulk discarded {count} pending suggestions for {creator_id}")
        return {"success": True, "discarded_count": count, "creator_id": creator_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error in discard-all: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        session.close()


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
        raise HTTPException(status_code=500, detail="Internal server error")
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

        # Autolearning hook: fire-and-forget rule extraction from manual override
        try:
            import asyncio as _aio
            from api.models import Creator as _Cr
            from services.autolearning_analyzer import analyze_creator_action

            _creator = session.query(_Cr).filter_by(name=creator_id).first()
            if _creator:
                _aio.create_task(analyze_creator_action(
                    action="manual_override",
                    creator_id=creator_id,
                    creator_db_id=_creator.id,
                    suggested_response=original_suggestion,
                    final_response=body.content,
                    edit_diff=edit_diff,
                    intent=None,
                    lead_stage=lead.status,
                    relationship_type=getattr(lead, "relationship_type", None),
                    source_message_id=manual_msg.id,
                ))
        except Exception as learn_err:
            logger.debug(f"[Copilot] Autolearning manual hook failed: {learn_err}")

        # Preference pairs hook: fire-and-forget training data collection
        try:
            from services.preference_pairs_service import create_pairs_from_action

            if _creator:
                _aio.create_task(create_pairs_from_action(
                    action="manual_override",
                    creator_db_id=_creator.id,
                    source_message_id=manual_msg.id,
                    suggested_response=original_suggestion,
                    final_response=body.content,
                    intent=None,
                    lead_stage=lead.status,
                    edit_diff=edit_diff,
                ))
        except Exception as pp_err:
            logger.debug(f"[Copilot] Preference pairs manual hook failed: {pp_err}")

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
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        session.close()


# =============================================================================
# POST /copilot/{creator_id}/preference-pairs/mark-exported
# =============================================================================
@router.post("/{creator_id}/preference-pairs/mark-exported")
async def mark_pairs_exported(
    creator_id: str,
    body: MarkExportedRequest,
    _auth: str = Depends(require_creator_access),
):
    """Mark preference pairs as exported for training."""
    from services.preference_pairs_service import mark_exported

    count = mark_exported(body.pair_ids)
    return {"creator_id": creator_id, "marked": count}
