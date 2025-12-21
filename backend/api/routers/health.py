"""Health check endpoints"""
from fastapi import APIRouter
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

@router.get("/health/live")
def health_live():
    return {"status": "ok"}

@router.get("/health/ready")
async def health_ready():
    return {"status": "ok", "ready": True, "timestamp": datetime.now(timezone.utc).isoformat()}
