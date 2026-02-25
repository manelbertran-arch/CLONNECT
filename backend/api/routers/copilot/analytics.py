"""
Copilot Router - Analytics endpoints (stats, learning, comparisons, history, etc.).

Heavy DB queries live in analytics_queries.py;
aggregation/computation logic lives in analytics_aggregation.py.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_creator_access

# Re-export for backward compatibility (used by copilot/__init__.py and tests)
from .analytics_aggregation import PATTERN_UI_MAP, _compute_tip  # noqa: F401

logger = logging.getLogger(__name__)
router = APIRouter(tags=["copilot"])


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

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        enabled = getattr(creator, "copilot_mode", True)
        if enabled is None:
            enabled = True
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
    from api.database import SessionLocal
    from api.models import Creator

    from .analytics_queries import fetch_notifications

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            except ValueError:
                since_dt = datetime.now(timezone.utc) - timedelta(minutes=5)
        else:
            since_dt = datetime.now(timezone.utc) - timedelta(minutes=5)

        data = fetch_notifications(session, creator, since_dt)

        return {
            "creator_id": creator_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "new_messages_count": len(data["new_messages"]),
            "new_messages": data["new_messages"],
            "pending_count": len(data["pending_responses"]),
            "pending_responses": data["pending_responses"],
            "hot_leads_count": len(data["hot_leads"]),
            "hot_leads": data["hot_leads"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error getting notifications: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        session.close()


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
    from api.models import Creator

    from .analytics_queries import fetch_pending_for_lead

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        result = fetch_pending_for_lead(session, creator, lead_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Lead not found")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error getting pending for lead: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
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
    from api.database import SessionLocal
    from api.models import Creator

    from .analytics_aggregation import compute_copilot_stats

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        data = compute_copilot_stats(session, creator, days)
        return {"creator_id": creator_id, **data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error getting stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        session.close()


# =============================================================================
# GET /copilot/{creator_id}/learning-progress
# =============================================================================
@router.get("/{creator_id}/learning-progress")
async def get_learning_progress(
    creator_id: str,
    _auth: str = Depends(require_creator_access),
):
    """
    Get learning progress dashboard data for the clone training visualization.

    Returns match rate, learned patterns, weekly stats, daily progress, and a tip.
    """
    from api.database import SessionLocal
    from api.models import Creator

    from .analytics_aggregation import compute_learning_progress

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        data = compute_learning_progress(session, creator)
        return {"creator_id": creator_id, **data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error getting learning progress: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
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
    from api.database import SessionLocal
    from api.models import Creator

    from .analytics_queries import fetch_comparisons

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        data = fetch_comparisons(session, creator, offset, limit)
        return {"creator_id": creator_id, **data}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error getting comparisons: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        session.close()


# =============================================================================
# GET /copilot/{creator_id}/history
# =============================================================================
@router.get("/{creator_id}/history")
async def get_copilot_history(
    creator_id: str,
    limit: int = 50,
    offset: int = 0,
    _auth: str = Depends(require_creator_access),
):
    """
    Get full copilot action history for a creator.

    Includes all actions (approved, edited, discarded, manual_override, resolved_externally)
    ordered by most recent first. For resolved_externally items, includes similarity_score.
    """
    from api.database import SessionLocal
    from api.models import Creator

    from .analytics_queries import fetch_history

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        data = fetch_history(session, creator, offset, limit)
        return data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Copilot] Error getting history: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
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


# =============================================================================
# GET /copilot/{creator_id}/preference-pairs
# =============================================================================
@router.get("/{creator_id}/preference-pairs")
async def get_preference_pairs(
    creator_id: str,
    limit: int = 50,
    offset: int = 0,
    action_type: Optional[str] = None,
    unexported_only: bool = False,
    _auth: str = Depends(require_creator_access),
):
    """List preference pairs for export or viewing."""
    from api.database import SessionLocal
    from api.models import Creator
    from services.preference_pairs_service import get_pairs_for_export

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")
        pairs = get_pairs_for_export(
            creator.id, limit=limit, offset=offset,
            action_type=action_type, unexported_only=unexported_only,
        )
        return {"creator_id": creator_id, "count": len(pairs), "pairs": pairs}
    finally:
        session.close()
