"""
Onboarding routers package.

Combines all onboarding-related routers into a single module.
Import the combined router using: from api.routers.onboarding import router

Structure:
- progress.py: Checklist status and visual onboarding (4 endpoints)
- clone.py: Wizard onboarding and clone creation (3 endpoints)
- pipeline.py: Magic Slice and full setup pipeline (6 endpoints)
- scrape.py: Instagram scraping onboarding (1 endpoint)
- seed_data.py: Demo data seeding (2 endpoints)
- setup.py: Manual/quick setup and full reset (3 endpoints)
- auto_setup.py: Full auto-setup V2 with background (3 endpoints)
- sync.py: Instagram API post sync (1 endpoint)
- dm_sync.py: Instagram DM history sync (4 endpoints)
- extraction.py: Personality extraction pipeline (3 endpoints)
"""

from fastapi import APIRouter

# Import sub-routers
from .auto_setup import router as auto_setup_router
from .clone import router as clone_router
from .dm_sync import router as dm_sync_router
from .extraction import router as extraction_router
from .pipeline import router as pipeline_router
from .progress import router as progress_router
from .scrape import router as scrape_router
from .seed_data import router as seed_data_router
from .setup import router as setup_router
from .sync import router as sync_router

# Main router that combines all onboarding sub-routers
# Note: All sub-routers have prefix="/onboarding", so we don't add one here
router = APIRouter()

# Include all sub-routers
router.include_router(progress_router)
router.include_router(clone_router)
router.include_router(pipeline_router)
router.include_router(scrape_router)
router.include_router(seed_data_router)
router.include_router(setup_router)
router.include_router(auto_setup_router)
router.include_router(sync_router)
router.include_router(dm_sync_router)
router.include_router(extraction_router)

__all__ = [
    "router",
    "progress_router",
    "clone_router",
    "pipeline_router",
    "scrape_router",
    "seed_data_router",
    "setup_router",
    "auto_setup_router",
    "sync_router",
    "dm_sync_router",
    "extraction_router",
]
