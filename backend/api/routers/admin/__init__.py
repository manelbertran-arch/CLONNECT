"""
Admin routers package.

Combines all admin-related routers into a single module.
Import the combined router using: from api.routers.admin import router

Structure:
- dangerous.py: Destructive operations (12 endpoints) - require admin auth
- admin_core.py: Non-destructive admin endpoints
"""

from fastapi import APIRouter

# Import the core admin router (non-destructive endpoints)
# This is the original admin.py, renamed to admin_core.py
from ..admin_core import router as admin_core_router
from .dangerous import router as dangerous_router

# Main router that combines all admin sub-routers
# Note: Both sub-routers already have prefix="/admin", so we don't add one here
router = APIRouter()

# Include dangerous endpoints (12 destructive operations with require_admin)
router.include_router(dangerous_router)

# Include core admin endpoints (non-destructive operations)
router.include_router(admin_core_router)

__all__ = ["router", "dangerous_router", "admin_core_router"]
