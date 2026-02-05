"""
Admin routers package.

Combines all admin-related routers into a single module.
Import the combined router using: from api.routers.admin import router

Structure:
- dangerous.py: Destructive operations (12 endpoints) - require admin auth
- tokens.py: OAuth and token management (6 endpoints)
- admin_core.py: Remaining admin endpoints (being split)
"""

from fastapi import APIRouter

# Import sub-routers
from ..admin_core import router as admin_core_router
from .dangerous import router as dangerous_router
from .tokens import router as tokens_router

# Main router that combines all admin sub-routers
# Note: All sub-routers have prefix="/admin", so we don't add one here
router = APIRouter()

# Include all sub-routers
router.include_router(dangerous_router)
router.include_router(tokens_router)
router.include_router(admin_core_router)

__all__ = ["router", "dangerous_router", "tokens_router", "admin_core_router"]
