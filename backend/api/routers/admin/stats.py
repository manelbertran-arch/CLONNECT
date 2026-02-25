"""
Stats and monitoring endpoints.

Provides platform-wide statistics and monitoring:
- Global stats across all creators
- Conversation listings
- Alert history
"""

import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
async def admin_global_stats(admin: str = Depends(require_admin)):
    """
    [ADMIN] Estadísticas globales de la plataforma.
    Requiere CLONNECT_ADMIN_KEY.

    Single query with subselects for ~10x faster response vs sequential queries.
    """
    from sqlalchemy import text

    from api.database import SessionLocal

    session = SessionLocal()
    try:
        row = session.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM creators) AS total_creators,
                (SELECT COUNT(*) FROM creators WHERE bot_active = true) AS active_bots,
                (SELECT COUNT(*) FROM messages) AS total_messages,
                (SELECT COUNT(*) FROM leads) AS total_leads,
                (SELECT COUNT(*) FROM leads WHERE status = 'hot') AS hot_leads,
                (SELECT COUNT(DISTINCT id) FROM leads WHERE last_contact_at IS NOT NULL) AS total_conversations
        """)).fetchone()

        total_creators = row[0] or 0
        active_bots = row[1] or 0

        return {
            "status": "ok",
            "stats": {
                "total_creators": total_creators,
                "active_bots": active_bots,
                "paused_bots": total_creators - active_bots,
                "total_messages": row[2] or 0,
                "total_conversations": row[5] or 0,
                "total_leads": row[3] or 0,
                "hot_leads": row[4] or 0,
            },
        }

    except Exception as e:
        logger.error(f"Error getting global stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        session.close()


@router.get("/conversations")
async def admin_all_conversations(creator_id: Optional[str] = None, limit: int = 100, admin: str = Depends(require_admin)):
    """
    [ADMIN] Listar todas las conversaciones de todos los creadores.
    Opcionalmente filtrar por creator_id.
    Requiere CLONNECT_ADMIN_KEY.

    Uses direct DB query for fast response (avoids instantiating N agents).
    """
    from sqlalchemy import text

    from api.database import SessionLocal

    try:
        session = SessionLocal()
        try:
            params: dict = {"limit": min(limit, 500)}
            if creator_id:
                sql = text("""
                    SELECT
                        l.id::text           AS id,
                        l.platform_user_id   AS platform_user_id,
                        l.username           AS username,
                        l.status             AS status,
                        l.last_contact_at    AS last_contact,
                        c.name               AS creator_id
                    FROM leads l
                    JOIN creators c ON c.id = l.creator_id
                    WHERE c.name = :creator_id
                    ORDER BY l.last_contact_at DESC NULLS LAST
                    LIMIT :limit
                """)
                params["creator_id"] = creator_id
            else:
                sql = text("""
                    SELECT
                        l.id::text           AS id,
                        l.platform_user_id   AS platform_user_id,
                        l.username           AS username,
                        l.status             AS status,
                        l.last_contact_at    AS last_contact,
                        c.name               AS creator_id
                    FROM leads l
                    JOIN creators c ON c.id = l.creator_id
                    ORDER BY l.last_contact_at DESC NULLS LAST
                    LIMIT :limit
                """)

            rows = session.execute(sql, params).fetchall()
            conversations = [
                {
                    "id": row[0],
                    "platform_user_id": row[1],
                    "username": row[2] or row[1],
                    "display_name": row[2] or row[1],
                    "status": row[3],
                    "last_contact": row[4].isoformat() if row[4] else None,
                    "creator_id": row[5],
                }
                for row in rows
            ]
        finally:
            session.close()

        return {
            "status": "ok",
            "conversations": conversations,
            "total": len(conversations),
        }

    except Exception as e:
        logger.error(f"Error getting conversations: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/pending-messages")
async def admin_pending_messages(admin: str = Depends(require_admin)):
    """View messages queued for retry."""
    from api.database import SessionLocal
    from api.models import PendingMessage
    with SessionLocal() as session:
        pending = session.query(PendingMessage).filter(
            PendingMessage.status == "pending"
        ).count()
        failed = session.query(PendingMessage).filter(
            PendingMessage.status == "failed_permanent"
        ).count()
        return {
            "pending_retry": pending,
            "failed_permanent": failed,
        }


@router.get("/alerts")
async def admin_recent_alerts(limit: int = 50, admin: str = Depends(require_admin)):
    """
    [ADMIN] Obtener alertas recientes del sistema.
    Requiere CLONNECT_ADMIN_KEY.

    Nota: Las alertas se envían a Telegram, este endpoint
    es para consultar un historial local si está habilitado.
    """
    try:
        # Leer alertas del log si existe
        alerts = []
        log_file = os.path.join(os.getenv("DATA_PATH", "./data"), "alerts.log")

        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                lines = f.readlines()[-limit:]
                for line in lines:
                    try:
                        alert = json.loads(line.strip())
                        alerts.append(alert)
                    except Exception as e:
                        logger.debug(f"Skipping malformed alert line: {e}")

        return {
            "status": "ok",
            "alerts": alerts,
            "total": len(alerts),
            "telegram_enabled": os.getenv("TELEGRAM_ALERTS_ENABLED", "false").lower() == "true",
        }

    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/feature-flags")
async def admin_feature_flags(admin: str = Depends(require_admin)):
    """View all feature flags and their current values."""
    from core.feature_flags import flags
    return {
        "flags": flags.to_dict(),
        "active": flags.active_count(),
        "inactive": flags.inactive_count(),
    }
