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
- sync_dm/: Sync operations package (23 endpoints)
  - sync_operations.py: DM sync, clean-and-sync, start-sync, sync-status, sync-continue, sync-leads
  - fix_operations.py: fix-lead-timestamps, fix-reaction-emojis, fix-instagram-page-id, etc.
  - media_operations.py: generate-thumbnails, generate-link-previews, update-profile-pics
  - migration_operations.py: run-migration, test-ingestion-v2, backup, backups
  - test_operations.py: test-full-sync, test-shared-post
"""

from fastapi import APIRouter

# Import sub-routers
from .creators import router as creators_router
from .dangerous import router as dangerous_router
from .debug import router as debug_router
from .ingestion import router as ingestion_router
from .leads import router as leads_router
from .stats import router as stats_router
from .sync_dm import router as sync_dm_router
from .tokens import router as tokens_router

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
    "ingestion_router",
]
