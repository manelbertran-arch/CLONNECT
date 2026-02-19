"""
Onboarding routers package.

Combines all onboarding-related routers into a single module.
Import the combined router using: from api.routers.onboarding import router

Structure (active):
- progress.py: Checklist status and visual onboarding (4 endpoints)
- clone.py: Wizard onboarding and clone creation (3 endpoints)
- scrape.py: Instagram scraping onboarding (1 endpoint)
- setup.py: Manual/quick setup and full reset (3 endpoints)
- sync.py: Instagram API post sync (1 endpoint)
- dm_sync.py: Instagram DM history sync (4 endpoints)
- extraction.py: Personality extraction pipeline (3 endpoints)

Disabled (P1-B7, 2026-02-18):
- pipeline.py: Dead code — demo values, asyncio.sleep, no frontend usage (11 endpoints)
- seed_data.py: Dead code — fake demo data injection (2 endpoints)
- auto_setup.py: Superseded by clone.py — uses incompatible ToneProfile/FAQ generators (3 endpoints)
"""

from fastapi import APIRouter

# Import sub-routers (active only)
from .clone import router as clone_router
from .dm_sync import router as dm_sync_router
from .extraction import router as extraction_router
from .progress import router as progress_router
from .scrape import router as scrape_router
from .setup import router as setup_router
from .sync import router as sync_router
from .verification import router as verification_router

# Main router that combines all onboarding sub-routers
# Note: All sub-routers have prefix="/onboarding", so we don't add one here
router = APIRouter()

# Include active sub-routers only
router.include_router(progress_router)
router.include_router(clone_router)
router.include_router(scrape_router)
router.include_router(setup_router)
router.include_router(sync_router)
router.include_router(dm_sync_router)
router.include_router(extraction_router)
router.include_router(verification_router)

# DISABLED (P1-B7): pipeline.py, seed_data.py, auto_setup.py
# Files preserved for reference but not registered as routers.
# To re-enable, uncomment the imports and include_router calls below:
# from .auto_setup import router as auto_setup_router
# from .pipeline import router as pipeline_router
# from .seed_data import router as seed_data_router
# router.include_router(pipeline_router)
# router.include_router(seed_data_router)
# router.include_router(auto_setup_router)

__all__ = [
    "router",
    "progress_router",
    "clone_router",
    "scrape_router",
    "setup_router",
    "sync_router",
    "dm_sync_router",
    "extraction_router",
    "verification_router",
]
