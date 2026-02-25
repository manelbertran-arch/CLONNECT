"""
Instagram Persistent Menu + Other Management Endpoints

Includes persistent menu configuration, cache clearing,
page connection, status checking, and creator listing.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from api.routers.instagram.webhook import (
    _creator_by_page_id_cache,
    _creator_handlers,
)

logger = logging.getLogger("clonnect-instagram")

router = APIRouter()


# =============================================================================
# DEBUG/CACHE ENDPOINTS
# =============================================================================


@router.get("/clear-cache")
async def clear_instagram_cache():
    """Clear handler and lookup caches - useful for debugging"""
    handlers_cleared = len(_creator_handlers)
    lookups_cleared = len(_creator_by_page_id_cache)
    _creator_handlers.clear()
    _creator_by_page_id_cache.clear()
    return {
        "status": "ok",
        "handlers_cleared": handlers_cleared,
        "lookups_cleared": lookups_cleared,
        "code_version": "V2_FIX_2026-01-29"
    }


# =============================================================================
# PERSISTENT MENU
# =============================================================================


@router.post("/persistent-menu/{creator_id}")
async def set_persistent_menu(creator_id: str, menu_items: List[Dict[str, Any]]):
    """
    Set Persistent Menu for a creator's Instagram.

    The persistent menu appears as a hamburger menu in the chat.

    Request body example:
    [
        {
            "type": "postback",
            "title": "Ver servicios",
            "payload": "SERVICES"
        },
        {
            "type": "postback",
            "title": "Reservar cita",
            "payload": "BOOKING"
        },
        {
            "type": "web_url",
            "title": "Visitar web",
            "url": "https://example.com"
        }
    ]
    """
    try:
        import httpx
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

            access_token = creator.instagram_token
            page_id = creator.instagram_page_id
        finally:
            session.close()

        if not access_token or not page_id:
            raise HTTPException(status_code=400, detail="No Instagram connection")

        # Format persistent menu
        persistent_menu = [
            {"locale": "default", "composer_input_disabled": False, "call_to_actions": menu_items}
        ]

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://graph.facebook.com/v21.0/{page_id}/messenger_profile",
                params={"access_token": access_token},
                json={"persistent_menu": persistent_menu},
            )

            result = response.json()

            if "error" in result:
                logger.error(f"Failed to set persistent menu: {result['error']}")
                raise HTTPException(
                    status_code=400, detail=result["error"].get("message", "Unknown error")
                )

            logger.info(f"Set persistent menu for {creator_id} with {len(menu_items)} items")

            return {"status": "ok", "creator_id": creator_id, "menu_items_set": len(menu_items)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting persistent menu: {e}")
        raise HTTPException(status_code=503, detail="Internal server error")


# =============================================================================
# CONNECT ENDPOINT: Register page_id for a creator
# =============================================================================


@router.post("/connect")
async def connect_instagram_page(
    creator_id: str = Query(..., description="Creator name/ID"),
    page_id: str = Query(..., description="Instagram/Facebook Page ID"),
    access_token: str = Query(None, description="Page access token (optional if already stored)"),
    ig_user_id: str = Query(None, description="Instagram User ID (optional, defaults to page_id)"),
):
    """
    Connect/register an Instagram page to a creator.

    This endpoint allows manual registration of a page_id when OAuth flow
    doesn't capture it automatically, or for testing purposes.
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()

            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

            # Update page_id
            creator.instagram_page_id = page_id

            # Update instagram_user_id (use page_id as default if not provided)
            creator.instagram_user_id = ig_user_id or page_id

            # Update token if provided
            if access_token:
                creator.instagram_token = access_token

            session.commit()

            logger.info(f"Connected Instagram page {page_id} to creator {creator_id}")

            return {
                "status": "ok",
                "creator_id": creator_id,
                "instagram_page_id": page_id,
                "instagram_user_id": creator.instagram_user_id,
                "token_updated": bool(access_token),
            }

        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error connecting Instagram page: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/status/{creator_id}")
async def get_instagram_status(creator_id: str):
    """
    Get Instagram connection status for a creator.
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()

            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

            connected = bool(creator.instagram_token and creator.instagram_page_id)

            # Get handler stats if connected
            handler_stats = {}
            if creator_id in _creator_handlers:
                handler = _creator_handlers[creator_id]
                handler_stats = handler.get_status()

            return {
                "status": "ok",
                "creator_id": creator_id,
                "connected": connected,
                "instagram_page_id": creator.instagram_page_id,
                "instagram_user_id": creator.instagram_user_id,
                "bot_active": creator.bot_active,
                "copilot_mode": creator.copilot_mode,
                "handler_stats": handler_stats,
            }

        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Instagram status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/creators")
async def list_instagram_creators():
    """
    List all creators with Instagram connections.
    Useful for debugging multi-creator setup.
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creators = session.query(Creator).filter(Creator.instagram_page_id.isnot(None)).all()

            return {
                "status": "ok",
                "count": len(creators),
                "creators": [
                    {
                        "creator_id": c.name,
                        "instagram_page_id": c.instagram_page_id,
                        "instagram_user_id": c.instagram_user_id,
                        "bot_active": c.bot_active,
                        "copilot_mode": c.copilot_mode,
                        "has_token": bool(c.instagram_token),
                    }
                    for c in creators
                ],
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error listing Instagram creators: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
