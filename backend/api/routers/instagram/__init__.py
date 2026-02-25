"""
Instagram Router Package - Multi-Creator Support

BLOQUE 1+2: Multi-Creator Routing for Instagram Webhooks.
Routes incoming webhooks to the correct creator based on page_id.

Features:
- page_id -> creator_id mapping via database lookup
- Dynamic handler creation per creator
- Ice Breakers support
- Stories Reply handling
- Persistent Menu configuration
"""

from fastapi import APIRouter

# Import sub-routers
from api.routers.instagram.webhook import router as webhook_router
from api.routers.instagram.icebreakers import router as icebreakers_router
from api.routers.instagram.menu import router as menu_router

# Re-export all public symbols from sub-modules
from api.routers.instagram.webhook import (
    _creator_by_page_id_cache,
    _creator_handlers,
    _CREATOR_LOOKUP_CACHE_TTL,
    _handle_story_mention,
    _handle_story_reply,
    _register_story_interaction,
    extract_page_id_from_payload,
    get_creator_by_ig_user_id,
    get_creator_by_page_id,
    get_handler_for_creator,
    instagram_stories_webhook,
    instagram_webhook_receive,
    instagram_webhook_verify,
    VERIFY_TOKEN,
)

from api.routers.instagram.icebreakers import (
    delete_ice_breakers,
    get_ice_breakers,
    set_ice_breakers,
)

from api.routers.instagram.menu import (
    clear_instagram_cache,
    connect_instagram_page,
    get_instagram_status,
    list_instagram_creators,
    set_persistent_menu,
)

# Combined router with original prefix and tags
router = APIRouter(prefix="/instagram", tags=["instagram"])
router.include_router(webhook_router)
router.include_router(icebreakers_router)
router.include_router(menu_router)

__all__ = [
    "router",
    # Shared state / helpers (used externally)
    "_creator_by_page_id_cache",
    "_creator_handlers",
    "_CREATOR_LOOKUP_CACHE_TTL",
    "get_creator_by_page_id",
    "get_creator_by_ig_user_id",
    "get_handler_for_creator",
    "extract_page_id_from_payload",
    # Webhook endpoints
    "instagram_webhook_verify",
    "instagram_webhook_receive",
    "instagram_stories_webhook",
    "_handle_story_mention",
    "_handle_story_reply",
    "_register_story_interaction",
    "VERIFY_TOKEN",
    # Icebreaker endpoints
    "set_ice_breakers",
    "get_ice_breakers",
    "delete_ice_breakers",
    # Menu / management endpoints
    "set_persistent_menu",
    "clear_instagram_cache",
    "connect_instagram_page",
    "get_instagram_status",
    "list_instagram_creators",
]
