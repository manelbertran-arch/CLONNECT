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
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/copilot", tags=["copilot"])


class ApproveRequest(BaseModel):
    edited_text: Optional[str] = None


class ToggleRequest(BaseModel):
    enabled: bool


# =============================================================================
# GET /copilot/{creator_id}/pending
# =============================================================================
@router.get("/{creator_id}/pending")
async def get_pending_responses(creator_id: str, limit: int = 50):
    """
    Obtener todas las respuestas pendientes de aprobación.

    Returns:
        List de respuestas pendientes con info del usuario y sugerencia del bot
    """
    from core.copilot_service import get_copilot_service

    service = get_copilot_service()
    pending = await service.get_pending_responses(creator_id, limit)

    return {
        "creator_id": creator_id,
        "pending_count": len(pending),
        "pending_responses": pending
    }


# =============================================================================
# POST /copilot/{creator_id}/approve/{message_id}
# =============================================================================
@router.post("/{creator_id}/approve/{message_id}")
async def approve_response(creator_id: str, message_id: str, request: ApproveRequest = None):
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
@router.post("/{creator_id}/discard/{message_id}")
async def discard_response(creator_id: str, message_id: str):
    """
    Descartar una respuesta sin enviarla.

    Args:
        message_id: ID del mensaje pendiente

    Returns:
        Confirmación del descarte
    """
    from core.copilot_service import get_copilot_service

    service = get_copilot_service()
    result = await service.discard_response(creator_id, message_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to discard"))

    return result


# =============================================================================
# GET /copilot/{creator_id}/status
# =============================================================================
@router.get("/{creator_id}/status")
async def get_copilot_status(creator_id: str):
    """
    Obtener estado del modo copilot para un creador.

    Returns:
        - enabled: Si el modo copilot está activado
        - pending_count: Número de respuestas pendientes
    """
    from core.copilot_service import get_copilot_service
    from api.database import SessionLocal
    from api.models import Creator

    service = get_copilot_service()
    enabled = service.is_copilot_enabled(creator_id)

    pending = await service.get_pending_responses(creator_id, limit=100)

    return {
        "creator_id": creator_id,
        "copilot_enabled": enabled,
        "pending_count": len(pending),
        "status": "active" if enabled else "disabled"
    }


# =============================================================================
# PUT /copilot/{creator_id}/toggle
# =============================================================================
@router.put("/{creator_id}/toggle")
async def toggle_copilot_mode(creator_id: str, request: ToggleRequest):
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

        logger.info(f"[Copilot] Mode {'enabled' if request.enabled else 'disabled'} for {creator_id}")

        return {
            "creator_id": creator_id,
            "copilot_enabled": request.enabled,
            "message": f"Copilot mode {'enabled' if request.enabled else 'disabled'}"
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
async def get_notifications(creator_id: str, since: Optional[str] = None):
    """
    Endpoint de polling para notificaciones en tiempo real.

    Args:
        since: ISO timestamp - solo retorna notificaciones después de esta fecha

    Returns:
        - new_messages: Mensajes nuevos recibidos
        - pending_responses: Respuestas pendientes de aprobar
        - hot_leads: Leads que se volvieron HOT
    """
    from api.database import SessionLocal
    from api.models import Creator, Lead, Message
    from datetime import timedelta

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        # Parse since timestamp
        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace('Z', '+00:00'))
            except:
                since_dt = datetime.now(timezone.utc) - timedelta(minutes=5)
        else:
            since_dt = datetime.now(timezone.utc) - timedelta(minutes=5)

        # Nuevos mensajes de usuarios
        new_user_messages = session.query(Message, Lead).join(
            Lead, Message.lead_id == Lead.id
        ).filter(
            Lead.creator_id == creator.id,
            Message.role == "user",
            Message.created_at > since_dt
        ).order_by(Message.created_at.desc()).limit(20).all()

        new_messages = []
        for msg, lead in new_user_messages:
            new_messages.append({
                "id": str(msg.id),
                "lead_id": str(lead.id),
                "follower_id": lead.platform_user_id,
                "username": lead.username or "",
                "platform": lead.platform,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else ""
            })

        # Respuestas pendientes
        pending = session.query(Message, Lead).join(
            Lead, Message.lead_id == Lead.id
        ).filter(
            Lead.creator_id == creator.id,
            Message.status == "pending_approval",
            Message.role == "assistant"
        ).order_by(Message.created_at.desc()).limit(20).all()

        pending_responses = []
        for msg, lead in pending:
            # Obtener mensaje del usuario
            user_msg = session.query(Message).filter(
                Message.lead_id == lead.id,
                Message.role == "user"
            ).order_by(Message.created_at.desc()).first()

            pending_responses.append({
                "id": str(msg.id),
                "lead_id": str(lead.id),
                "follower_id": lead.platform_user_id,
                "username": lead.username or "",
                "platform": lead.platform,
                "user_message": user_msg.content if user_msg else "",
                "suggested_response": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else ""
            })

        # Hot leads recientes
        hot_leads = session.query(Lead).filter(
            Lead.creator_id == creator.id,
            Lead.status == "hot",
            Lead.last_contact_at > since_dt
        ).order_by(Lead.last_contact_at.desc()).limit(10).all()

        hot_leads_data = [
            {
                "id": str(lead.id),
                "follower_id": lead.platform_user_id,
                "username": lead.username or "",
                "platform": lead.platform,
                "purchase_intent": lead.purchase_intent or 0.0,
                "last_contact": lead.last_contact_at.isoformat() if lead.last_contact_at else ""
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
            "hot_leads": hot_leads_data
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
async def approve_all_pending(creator_id: str):
    """
    Aprobar todas las respuestas pendientes de una vez.
    Útil para modo "confiar en el bot".
    """
    from core.copilot_service import get_copilot_service

    service = get_copilot_service()
    pending = await service.get_pending_responses(creator_id)

    results = {
        "approved": 0,
        "failed": 0,
        "errors": []
    }

    for item in pending:
        result = await service.approve_response(creator_id, item["id"])
        if result.get("success"):
            results["approved"] += 1
        else:
            results["failed"] += 1
            results["errors"].append({
                "message_id": item["id"],
                "error": result.get("error")
            })

    return {
        "creator_id": creator_id,
        "results": results
    }
