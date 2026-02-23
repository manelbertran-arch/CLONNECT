"""
Onboarding routers package.

Combines all onboarding-related routers into a single module.
Import the combined router using: from api.routers.onboarding import router

Active (16 endpoints):
- progress.py: Checklist status and visual onboarding (4 endpoints)
- clone.py: Wizard onboarding and clone creation (3 endpoints)
- setup.py: Full reset for testing (1 endpoint, admin-only)
- dm_sync.py: Instagram DM history sync (4 endpoints)
- extraction.py: Personality extraction pipeline (3 endpoints)
- verification.py: Post-onboarding health checks (1 endpoint)

Disabled (P1-B7 + P3-C1):
- pipeline.py: Demo values, asyncio.sleep — kept for reference only
- helpers.py: Shared models used by pipeline.py

Deleted (P3-C1, 2026-02-19):
- auto_setup.py: Superseded by clone.py
- seed_data.py: Hardcoded demo data injection
- scrape.py: Instagram scraping (no callers)
- sync.py: Instagram API post sync (no callers)
"""

from fastapi import APIRouter

# Import sub-routers (active only)
from .clone import router as clone_router
from .dm_sync import router as dm_sync_router
from .extraction import router as extraction_router
from .pipeline import router as pipeline_router
from .progress import router as progress_router
from .setup import router as setup_router
from .verification import router as verification_router

# Main router that combines all onboarding sub-routers
# Note: All sub-routers have prefix="/onboarding", so we don't add one here
router = APIRouter()

# Include active sub-routers only
router.include_router(progress_router)
router.include_router(clone_router)
router.include_router(setup_router)
router.include_router(dm_sync_router)
router.include_router(extraction_router)
router.include_router(verification_router)
router.include_router(pipeline_router)

__all__ = [
    "router",
    "progress_router",
    "clone_router",
    "setup_router",
    "dm_sync_router",
    "extraction_router",
    "verification_router",
]
