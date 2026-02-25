"""
Sync DM operations package — all admin sync-related endpoints.

Sub-modules:
- sync_operations.py: DM sync, clean-and-sync, start-sync, sync-status, sync-continue, sync-leads
- fix_operations.py: fix-lead-timestamps, fix-reaction-emojis, fix-instagram-page-id, fix-lead-duplicates, apply-unique-constraint
- media_operations.py: generate-thumbnails, generate-link-previews, update-profile-pics
- migration_operations.py: run-migration, test-ingestion-v2, backup, backups
- test_operations.py: test-full-sync, test-shared-post
"""
from fastapi import APIRouter

from .fix_operations import router as fix_router
from .media_operations import router as media_router
from .migration_operations import router as migration_router
from .sync_operations import router as sync_router
from .test_operations import router as test_router

# Combined router that includes all sub-routers
router = APIRouter()
router.include_router(sync_router)
router.include_router(fix_router)
router.include_router(media_router)
router.include_router(migration_router)
router.include_router(test_router)

# Re-exports for backward compatibility
from .media_operations import (  # noqa: E402, F401
    INSTAGRAM_URL_REGEX,
    YOUTUBE_URL_REGEX,
    detect_url_in_metadata,
    generate_link_preview,
)

__all__ = [
    "router",
    "generate_link_preview",
    "detect_url_in_metadata",
    "INSTAGRAM_URL_REGEX",
    "YOUTUBE_URL_REGEX",
]
