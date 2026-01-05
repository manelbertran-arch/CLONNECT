"""Health check endpoints"""
from fastapi import APIRouter
from datetime import datetime, timezone
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

# Version for tracking deployments
BUILD_VERSION = "2026.01.05.v2"

@router.get("/health/live")
def health_live():
    return {"status": "ok", "version": BUILD_VERSION}

@router.get("/health/ready")
async def health_ready():
    return {"status": "ok", "ready": True, "timestamp": datetime.now(timezone.utc).isoformat()}
