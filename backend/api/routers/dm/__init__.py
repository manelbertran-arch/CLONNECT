"""
DM Router Package - Endpoints for direct message management
Decomposed from monolithic dm.py into sub-modules.
"""

from fastapi import APIRouter

from .processing import router as processing_router
from .conversations import router as conversations_router
from .followers import router as followers_router
from .debug import router as debug_router

router = APIRouter(prefix="/dm", tags=["dm"])
router.include_router(processing_router)
router.include_router(conversations_router)
router.include_router(followers_router)
router.include_router(debug_router)

# Re-exports for backward compatibility
from .processing import get_dm_agent  # noqa: F401  (used by admin/creators.py, admin/stats.py)
from .conversations import get_conversations  # noqa: F401  (used by api/startup.py)
