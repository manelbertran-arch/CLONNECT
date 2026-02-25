"""Messaging webhook handlers — decomposed by platform."""
from fastapi import APIRouter

from .instagram_webhook import router as instagram_router
from .whatsapp_webhook import router as whatsapp_router
from .telegram_webhook import router as telegram_router
from .evolution_webhook import EVOLUTION_INSTANCE_MAP, router as evolution_router

router = APIRouter()
router.include_router(instagram_router)
router.include_router(whatsapp_router)
router.include_router(telegram_router)
router.include_router(evolution_router)

__all__ = ["router", "EVOLUTION_INSTANCE_MAP"]
