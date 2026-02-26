"""
Creator management endpoints.

Handles creator-related operations:
- List all creators with stats
- Pause/resume creator bots
- Demo status and rate limiter management
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

DEMO_RESET_ENABLED = os.getenv("ENABLE_DEMO_RESET", "true").lower() == "true"


@router.get("/demo-status")
async def get_demo_status(admin: str = Depends(require_admin)):
    """Check if demo reset is enabled and get current data counts"""
    counts = {}

    try:
        from api.database import DATABASE_URL, SessionLocal

        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                from api.models import Creator, Lead, Message, NurturingSequence, Product

                counts["creators"] = session.query(Creator).count()
                counts["leads"] = session.query(Lead).count()
                counts["messages"] = session.query(Message).count()
                counts["products"] = session.query(Product).count()
                counts["sequences"] = session.query(NurturingSequence).count()

                # Get bot status and onboarding status
                creators = session.query(Creator).all()
                counts["creator_statuses"] = {
                    c.name: {
                        "bot_active": c.bot_active,
                        "onboarding_completed": c.onboarding_completed,
                        "copilot_mode": c.copilot_mode,
                        "has_instagram": bool(c.instagram_token),
                    }
                    for c in creators
                }

            finally:
                session.close()
    except Exception as e:
        counts["db_error"] = str(e)

    # Check tone profiles
    try:
        from core.tone_service import list_profiles

        counts["tone_profiles"] = list_profiles()
    except Exception as e:
        counts["tone_profiles_error"] = str(e)

    # Check RAG documents
    try:
        from core.rag import get_hybrid_rag

        rag = get_hybrid_rag()
        counts["rag_documents"] = rag.count()
    except Exception as e:
        counts["rag_error"] = str(e)

    return {
        "demo_reset_enabled": DEMO_RESET_ENABLED,
        "counts": counts,
        "endpoints": {
            "reset_all": "POST /admin/reset-db",
            "reset_creator": "POST /admin/reset-creator/{creator_id}",
            "demo_status": "GET /admin/demo-status",
        },
    }


@router.get("/creators")
async def admin_list_creators(admin: str = Depends(require_admin)):
    """
    [ADMIN] Listar todos los creadores con estadísticas básicas.
    Requiere CLONNECT_ADMIN_KEY.

    Uses single optimised DB query (~10x faster than agent-based approach).
    """
    from sqlalchemy import text

    from api.database import SessionLocal

    try:
        session = SessionLocal()
        try:
            rows = session.execute(text("""
                SELECT
                    c.name                          AS creator_id,
                    c.name                          AS name,
                    c.instagram_handle              AS instagram_handle,
                    c.bot_active                    AS is_active,
                    c.updated_at                    AS updated_at,
                    COUNT(DISTINCT l.id)            AS total_leads,
                    COUNT(DISTINCT m.id)            AS total_messages,
                    COUNT(DISTINCT CASE WHEN l.status = 'caliente' THEN l.id END) AS hot_leads
                FROM creators c
                LEFT JOIN leads l ON l.creator_id = c.id
                LEFT JOIN messages m ON m.lead_id = l.id
                GROUP BY c.id, c.name, c.instagram_handle, c.bot_active, c.updated_at
                ORDER BY c.name
            """)).fetchall()
        finally:
            session.close()

        creator_stats = [
            {
                "creator_id": row[0],
                "name": row[1],
                "instagram_handle": row[2],
                "is_active": bool(row[3]),
                "pause_reason": None,
                "updated_at": row[4].isoformat() if row[4] else None,
                "total_leads": row[5] or 0,
                "total_messages": row[6] or 0,
                "hot_leads": row[7] or 0,
            }
            for row in rows
        ]

        return {"status": "ok", "creators": creator_stats, "total": len(creator_stats)}

    except Exception as e:
        logger.error(f"Error listing creators: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/creators/{creator_id}/pause")
async def admin_pause_creator(creator_id: str, reason: str = "Pausado por admin", admin: str = Depends(require_admin)):
    """
    [ADMIN] Pausar el bot de cualquier creador.
    Requiere CLONNECT_ADMIN_KEY.
    """
    from core.creator_config import CreatorConfigManager

    try:
        config_manager = CreatorConfigManager()
        success = config_manager.set_active(creator_id, False, reason)

        if not success:
            raise HTTPException(status_code=404, detail="Creator not found")

        logger.warning(f"Admin paused bot for creator {creator_id}: {reason}")

        return {"status": "ok", "creator_id": creator_id, "is_active": False, "reason": reason}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing creator: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/creators/{creator_id}/resume")
async def admin_resume_creator(creator_id: str, admin: str = Depends(require_admin)):
    """
    [ADMIN] Reanudar el bot de cualquier creador.
    Requiere CLONNECT_ADMIN_KEY.
    """
    from core.creator_config import CreatorConfigManager

    try:
        config_manager = CreatorConfigManager()
        success = config_manager.set_active(creator_id, True)

        if not success:
            raise HTTPException(status_code=404, detail="Creator not found")

        logger.info(f"Admin resumed bot for creator {creator_id}")

        return {"status": "ok", "creator_id": creator_id, "is_active": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming creator: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/reset-rate-limiter/{creator_id}")
async def admin_reset_rate_limiter(creator_id: str, admin: str = Depends(require_admin)):
    """Reset Instagram rate limiter backoff for a creator."""
    try:
        from core.instagram_rate_limiter import get_instagram_rate_limiter

        limiter = get_instagram_rate_limiter()
        result = limiter.reset_backoff(creator_id)
        return {"status": "success", **result}
    except Exception as e:
        logger.error(f"Error resetting rate limiter: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/rate-limiter-stats")
async def admin_rate_limiter_stats(creator_id: str = None, admin: str = Depends(require_admin)):
    """Get Instagram rate limiter statistics."""
    try:
        from core.instagram_rate_limiter import get_instagram_rate_limiter

        limiter = get_instagram_rate_limiter()
        return limiter.get_stats(creator_id)
    except Exception as e:
        logger.error(f"Error getting rate limiter stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
