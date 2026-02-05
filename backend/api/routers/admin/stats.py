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

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
async def admin_global_stats():
    """
    [ADMIN] Estadísticas globales de la plataforma.
    Requiere CLONNECT_ADMIN_KEY.
    """
    from api.routers.dm import get_dm_agent
    from core.creator_config import CreatorConfigManager

    try:
        config_manager = CreatorConfigManager()
        creators = config_manager.list_creators()

        total_messages = 0
        total_leads = 0
        total_hot_leads = 0
        total_conversations = 0
        active_bots = 0
        paused_bots = 0

        for creator_id in creators:
            config = config_manager.get_config(creator_id)
            if config:
                if config.is_active:
                    active_bots += 1
                else:
                    paused_bots += 1

            try:
                agent = get_dm_agent(creator_id)
                metrics = await agent.get_metrics()
                leads = await agent.get_leads()
                conversations = await agent.get_all_conversations(1000)

                total_messages += metrics.get("total_messages", 0)
                total_leads += len(leads)
                total_hot_leads += len([l for l in leads if l.get("score", 0) >= 0.7])
                total_conversations += len(conversations)
            except Exception as e:
                logger.warning(f"Failed to aggregate stats: {e}")

        return {
            "status": "ok",
            "stats": {
                "total_creators": len(creators),
                "active_bots": active_bots,
                "paused_bots": paused_bots,
                "total_messages": total_messages,
                "total_conversations": total_conversations,
                "total_leads": total_leads,
                "hot_leads": total_hot_leads,
            },
        }

    except Exception as e:
        logger.error(f"Error getting global stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations")
async def admin_all_conversations(creator_id: Optional[str] = None, limit: int = 100):
    """
    [ADMIN] Listar todas las conversaciones de todos los creadores.
    Opcionalmente filtrar por creator_id.
    Requiere CLONNECT_ADMIN_KEY.
    """
    from api.routers.dm import get_dm_agent
    from core.creator_config import CreatorConfigManager

    try:
        config_manager = CreatorConfigManager()
        if creator_id:
            creators = [creator_id]
        else:
            creators = config_manager.list_creators()

        all_conversations = []

        for cid in creators:
            try:
                agent = get_dm_agent(cid)
                conversations = await agent.get_all_conversations(limit)

                for conv in conversations:
                    conv["creator_id"] = cid
                    all_conversations.append(conv)
            except Exception as e:
                logger.warning(f"Failed to get conversations: {e}")

        # Ordenar por última actividad
        all_conversations.sort(key=lambda x: x.get("last_contact", ""), reverse=True)

        return {
            "status": "ok",
            "conversations": all_conversations[:limit],
            "total": len(all_conversations),
        }

    except Exception as e:
        logger.error(f"Error getting conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
async def admin_recent_alerts(limit: int = 50):
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
        raise HTTPException(status_code=500, detail=str(e))
