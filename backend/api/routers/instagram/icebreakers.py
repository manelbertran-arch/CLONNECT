"""
Instagram Ice Breakers Management

Endpoints for setting, getting, and deleting Ice Breakers
for creator Instagram accounts via the Meta Graph API.
"""

import logging
from typing import Dict, List

from fastapi import APIRouter, HTTPException

logger = logging.getLogger("clonnect-instagram")

router = APIRouter()


@router.post("/icebreakers/{creator_id}")
async def set_ice_breakers(creator_id: str, ice_breakers: List[Dict[str, str]]):
    """
    Set Ice Breakers for a creator's Instagram.

    Ice Breakers are conversation starters shown to users when they open
    a new conversation. Meta allows up to 4 ice breakers.

    Request body:
    [
        {"question": "¿Cuánto cuestan tus servicios?", "payload": "PRICING"},
        {"question": "¿Qué incluye el programa?", "payload": "FEATURES"},
        {"question": "¿Cómo puedo reservar?", "payload": "BOOKING"},
        {"question": "Quiero más información", "payload": "INFO"}
    ]
    """
    try:
        import httpx
        from api.database import SessionLocal
        from api.models import Creator

        # Get creator's token
        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

            if not creator.instagram_token or not creator.instagram_page_id:
                raise HTTPException(status_code=400, detail="Creator has no Instagram connection")

            access_token = creator.instagram_token
            page_id = creator.instagram_page_id
        finally:
            session.close()

        # Validate ice breakers (max 4)
        if len(ice_breakers) > 4:
            raise HTTPException(status_code=400, detail="Maximum 4 ice breakers allowed")

        # Format for Meta API
        formatted_icebreakers = [
            {"question": ib["question"], "payload": ib.get("payload", ib["question"][:20])}
            for ib in ice_breakers
        ]

        # Set ice breakers via Meta API
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"https://graph.facebook.com/v21.0/{page_id}/messenger_profile",
                params={"access_token": access_token},
                json={"ice_breakers": formatted_icebreakers},
            )

            result = response.json()

            if "error" in result:
                logger.error(f"Failed to set ice breakers: {result['error']}")
                raise HTTPException(
                    status_code=400, detail=result["error"].get("message", "Unknown error")
                )

            logger.info(f"Set {len(ice_breakers)} ice breakers for {creator_id}")

            return {
                "status": "ok",
                "creator_id": creator_id,
                "ice_breakers_set": len(ice_breakers),
                "ice_breakers": formatted_icebreakers,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting ice breakers: {e}")
        raise HTTPException(status_code=503, detail="Internal server error")


@router.get("/icebreakers/{creator_id}")
async def get_ice_breakers(creator_id: str):
    """
    Get current Ice Breakers for a creator.
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

            if not creator.instagram_token or not creator.instagram_page_id:
                return {"status": "ok", "ice_breakers": [], "info": "No Instagram connection"}

            access_token = creator.instagram_token
            page_id = creator.instagram_page_id
        finally:
            session.close()

        # Get ice breakers via Meta API
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"https://graph.facebook.com/v21.0/{page_id}/messenger_profile",
                params={"access_token": access_token, "fields": "ice_breakers"},
            )

            result = response.json()
            ice_breakers = result.get("data", [{}])[0].get("ice_breakers", [])

            return {"status": "ok", "creator_id": creator_id, "ice_breakers": ice_breakers}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ice breakers: {e}")
        raise HTTPException(status_code=503, detail="Internal server error")


@router.delete("/icebreakers/{creator_id}")
async def delete_ice_breakers(creator_id: str):
    """
    Delete all Ice Breakers for a creator.
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
            return {"status": "ok", "info": "No Instagram connection"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"https://graph.facebook.com/v21.0/{page_id}/messenger_profile",
                params={"access_token": access_token},
                json={"fields": ["ice_breakers"]},
            )

            result = response.json()

            if result.get("success"):
                logger.info(f"Deleted ice breakers for {creator_id}")
                return {"status": "ok", "deleted": True}
            else:
                return {"status": "ok", "deleted": False, "result": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting ice breakers: {e}")
        raise HTTPException(status_code=503, detail="Internal server error")
