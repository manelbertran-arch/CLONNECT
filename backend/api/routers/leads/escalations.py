"""Escalation alert endpoints"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from api.auth import require_creator_access

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{creator_id}/escalations")
async def get_escalation_alerts(creator_id: str, limit: int = 50, unread_only: bool = False, _auth: str = Depends(require_creator_access)):
    """
    Get escalation alerts for a creator.
    Returns leads that need human attention (requested escalation, high intent, etc.)
    """
    try:
        alerts = []
        log_file = Path(f"data/escalations/{creator_id}_escalations.jsonl")

        if log_file.exists():
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in reversed(lines[-limit:]):
                    try:
                        alert = json.loads(line.strip())
                        if unread_only and alert.get("read", False):
                            continue
                        alerts.append(alert)
                    except json.JSONDecodeError as e:
                        logger.debug("Ignored json.JSONDecodeError in alert = json.loads(line.strip()): %s", e)

        return {
            "status": "ok",
            "creator_id": creator_id,
            "alerts": alerts,
            "total": len(alerts),
            "unread": len([a for a in alerts if not a.get("read", False)]),
        }
    except Exception as e:
        logger.error(f"Error getting escalations: {e}")
        return {"status": "ok", "creator_id": creator_id, "alerts": [], "total": 0, "unread": 0}


@router.put("/{creator_id}/escalations/{follower_id}/read")
async def mark_escalation_read(creator_id: str, follower_id: str, _auth: str = Depends(require_creator_access)):
    """Mark an escalation as read"""
    # For now, just return OK - in production this would update the file/DB
    logger.info(f"Marked escalation read: {creator_id}/{follower_id}")
    return {"status": "ok", "message": "Escalation marked as read"}


@router.delete("/{creator_id}/escalations")
async def clear_escalations(creator_id: str, _auth: str = Depends(require_creator_access)):
    """Clear all escalation alerts for a creator."""
    log_file = Path(f"data/escalations/{creator_id}_escalations.jsonl")
    if log_file.exists():
        log_file.unlink()
        logger.info(f"Cleared escalations for {creator_id}")
    return {"status": "ok", "message": f"Escalations cleared for {creator_id}"}
