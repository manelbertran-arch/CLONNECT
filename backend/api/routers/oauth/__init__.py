"""OAuth endpoints -- decomposed by platform."""
from fastapi import APIRouter

from .google import router as google_router
from .instagram import router as instagram_router
from .paypal import router as paypal_router
from .status import router as status_router
from .stripe import router as stripe_router
from .whatsapp import router as whatsapp_router

router = APIRouter(prefix="/oauth", tags=["oauth"])
router.include_router(instagram_router)
router.include_router(whatsapp_router)
router.include_router(stripe_router)
router.include_router(paypal_router)
router.include_router(google_router)
router.include_router(status_router)

# Re-export symbols used by external modules so that
# `from api.routers.oauth import <name>` keeps working.
from .google import (  # noqa: E402, F401
    create_google_meet_event,
    delete_google_calendar_event,
    get_google_freebusy,
    get_valid_google_token,
    refresh_google_token,
)
from .instagram import (  # noqa: E402, F401
    INSTAGRAM_APP_ID,
    META_APP_ID,
    _auto_onboard_after_instagram_oauth,
    _simple_dm_sync_internal,
)
from .status import _save_connection  # noqa: E402, F401
