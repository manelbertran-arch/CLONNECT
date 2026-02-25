"""
Dangerous/destructive admin endpoints.

All endpoints in this module require admin authentication and handle
destructive operations like delete, reset, nuclear options.

These are the 12 endpoints protected with require_admin.

This file is a thin stub that combines sub-module routers:
- dangerous_user_ops: Creator/user operations
- dangerous_lead_ops: Lead cleanup operations
- dangerous_system_ops: System resets
"""

from fastapi import APIRouter

from .dangerous_lead_ops import router as lead_ops_router
from .dangerous_system_ops import router as system_ops_router
from .dangerous_user_ops import router as user_ops_router

router = APIRouter(prefix="/admin", tags=["admin"])

router.include_router(user_ops_router)
router.include_router(lead_ops_router)
router.include_router(system_ops_router)
