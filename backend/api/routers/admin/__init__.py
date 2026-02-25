"""
Admin routers package.

Combines all admin-related routers into a single module.
Import the combined router using: from api.routers.admin import router

Structure:
- dangerous.py: Destructive operations (12 endpoints) - require admin auth
- tokens.py: OAuth and token management (6 endpoints)
- creators.py: Creator management (6 endpoints)
- debug.py: Debug and diagnostic endpoints (5 endpoints)
- leads.py: Lead management (8 endpoints)
- stats.py: Stats and monitoring (3 endpoints)
- sync_dm.py: DM sync operations (9 endpoints)
- sync_fixes.py: One-off fixes and migrations (7 endpoints)
- sync_media.py: Media and thumbnail operations (4 endpoints)
- sync_backup.py: Backup operations (2 endpoints)
- sync_ingestion.py: Ingestion testing (1 endpoint)
"""

from fastapi import APIRouter

# Import sub-routers
from .creators import router as creators_router
from .dangerous import router as dangerous_router
from .debug import router as debug_router
from .leads import router as leads_router
from .stats import router as stats_router
from .sync_backup import router as sync_backup_router
from .sync_dm import router as sync_dm_router
from .sync_fixes import router as sync_fixes_router
from .sync_ingestion import router as sync_ingestion_router
from .sync_media import router as sync_media_router
from .tokens import router as tokens_router
from .ingestion import router as ingestion_router

# Main router that combines all admin sub-routers
# Note: All sub-routers have prefix="/admin", so we don't add one here
router = APIRouter()

# Include all sub-routers
router.include_router(dangerous_router)
router.include_router(tokens_router)
router.include_router(creators_router)
router.include_router(debug_router)
router.include_router(leads_router)
router.include_router(stats_router)
router.include_router(sync_dm_router)
router.include_router(sync_fixes_router)
router.include_router(sync_media_router)
router.include_router(sync_backup_router)
router.include_router(sync_ingestion_router)
router.include_router(ingestion_router)

__all__ = [
    "router",
    "dangerous_router",
    "tokens_router",
    "creators_router",
    "debug_router",
    "leads_router",
    "stats_router",
    "sync_dm_router",
    "sync_fixes_router",
    "sync_media_router",
    "sync_backup_router",
    "sync_ingestion_router",
    "ingestion_router",
]
