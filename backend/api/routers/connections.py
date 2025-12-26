"""
Connection management endpoints for integrations
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/connections", tags=["connections"])


class ConnectionStatus(BaseModel):
    """Status of a single connection"""
    connected: bool
    username: Optional[str] = None
    masked_token: Optional[str] = None  # Show last 4 chars only


class AllConnections(BaseModel):
    """All connection statuses"""
    instagram: ConnectionStatus
    telegram: ConnectionStatus
    whatsapp: ConnectionStatus
    stripe: ConnectionStatus
    hotmart: ConnectionStatus
    calendly: ConnectionStatus


class UpdateConnectionRequest(BaseModel):
    """Request to update a connection"""
    token: Optional[str] = None
    page_id: Optional[str] = None  # For Instagram/WhatsApp
    phone_id: Optional[str] = None  # For WhatsApp


def mask_token(token: Optional[str]) -> Optional[str]:
    """Mask a token showing only last 4 characters"""
    if not token or len(token) < 8:
        return None
    return f"****{token[-4:]}"


@router.get("/{creator_id}")
async def get_connections(creator_id: str) -> AllConnections:
    """Get all connection statuses for a creator"""
    # Default empty connections
    empty_connections = AllConnections(
        instagram=ConnectionStatus(connected=False),
        telegram=ConnectionStatus(connected=False),
        whatsapp=ConnectionStatus(connected=False),
        stripe=ConnectionStatus(connected=False),
        hotmart=ConnectionStatus(connected=False),
        calendly=ConnectionStatus(connected=False)
    )

    try:
        from api.database import DATABASE_URL, SessionLocal
        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                from api.models import Creator
                creator = session.query(Creator).filter_by(name=creator_id).first()

                if not creator:
                    # Return empty connections instead of 404
                    return empty_connections

                return AllConnections(
                    instagram=ConnectionStatus(
                        connected=bool(creator.instagram_token and len(creator.instagram_token) > 10),
                        username=creator.instagram_page_id if creator.instagram_token else None,
                        masked_token=mask_token(creator.instagram_token)
                    ),
                    telegram=ConnectionStatus(
                        connected=bool(creator.telegram_bot_token and len(creator.telegram_bot_token) > 10),
                        username="Bot configured" if creator.telegram_bot_token else None,
                        masked_token=mask_token(creator.telegram_bot_token)
                    ),
                    whatsapp=ConnectionStatus(
                        connected=bool(creator.whatsapp_token and creator.whatsapp_phone_id),
                        username=creator.whatsapp_phone_id if creator.whatsapp_token else None,
                        masked_token=mask_token(creator.whatsapp_token)
                    ),
                    stripe=ConnectionStatus(
                        connected=bool(creator.stripe_api_key and len(creator.stripe_api_key) > 10),
                        username="API Key configured" if creator.stripe_api_key else None,
                        masked_token=mask_token(creator.stripe_api_key)
                    ),
                    hotmart=ConnectionStatus(
                        connected=bool(creator.hotmart_token and len(creator.hotmart_token) > 10),
                        username="Token configured" if creator.hotmart_token else None,
                        masked_token=mask_token(creator.hotmart_token)
                    ),
                    calendly=ConnectionStatus(
                        connected=bool(creator.calendly_token and len(creator.calendly_token) > 10),
                        username="Connected" if creator.calendly_token else None,
                        masked_token=mask_token(creator.calendly_token)
                    )
                )
            finally:
                session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting connections: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # Fallback: return empty connections
    return empty_connections


@router.post("/{creator_id}/instagram")
async def update_instagram(creator_id: str, data: UpdateConnectionRequest):
    """Update Instagram connection"""
    return await _update_connection(creator_id, "instagram", data)


@router.post("/{creator_id}/telegram")
async def update_telegram(creator_id: str, data: UpdateConnectionRequest):
    """Update Telegram connection"""
    return await _update_connection(creator_id, "telegram", data)


@router.post("/{creator_id}/whatsapp")
async def update_whatsapp(creator_id: str, data: UpdateConnectionRequest):
    """Update WhatsApp connection"""
    return await _update_connection(creator_id, "whatsapp", data)


@router.post("/{creator_id}/stripe")
async def update_stripe(creator_id: str, data: UpdateConnectionRequest):
    """Update Stripe connection"""
    return await _update_connection(creator_id, "stripe", data)


@router.post("/{creator_id}/hotmart")
async def update_hotmart(creator_id: str, data: UpdateConnectionRequest):
    """Update Hotmart connection"""
    return await _update_connection(creator_id, "hotmart", data)


@router.post("/{creator_id}/calendly")
async def update_calendly(creator_id: str, data: UpdateConnectionRequest):
    """Update Calendly connection"""
    return await _update_connection(creator_id, "calendly", data)


@router.delete("/{creator_id}/{platform}")
async def disconnect_platform(creator_id: str, platform: str):
    """Disconnect a platform by clearing its token"""
    valid_platforms = ["instagram", "telegram", "whatsapp", "stripe", "hotmart", "calendly"]
    if platform not in valid_platforms:
        raise HTTPException(status_code=400, detail=f"Unknown platform: {platform}")

    try:
        from api.database import DATABASE_URL, SessionLocal
        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                from api.models import Creator
                creator = session.query(Creator).filter_by(name=creator_id).first()

                if not creator:
                    raise HTTPException(status_code=404, detail="Creator not found")

                # Clear the appropriate token
                if platform == "instagram":
                    creator.instagram_token = None
                    creator.instagram_page_id = None
                elif platform == "telegram":
                    creator.telegram_bot_token = None
                elif platform == "whatsapp":
                    creator.whatsapp_token = None
                    creator.whatsapp_phone_id = None
                elif platform == "stripe":
                    creator.stripe_api_key = None
                elif platform == "hotmart":
                    creator.hotmart_token = None
                elif platform == "calendly":
                    creator.calendly_token = None

                session.commit()
                logger.info(f"Disconnected {platform} for {creator_id}")
                return {"status": "disconnected", "platform": platform}
            finally:
                session.close()
        else:
            # No database - just return success (nothing to disconnect)
            return {"status": "disconnected", "platform": platform}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disconnecting {platform}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _update_connection(creator_id: str, platform: str, data: UpdateConnectionRequest):
    """Internal function to update a connection"""
    try:
        from api.database import DATABASE_URL, SessionLocal
        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                from api.models import Creator
                creator = session.query(Creator).filter_by(name=creator_id).first()

                if not creator:
                    raise HTTPException(status_code=404, detail="Creator not found")

                # Update the appropriate fields
                if platform == "instagram":
                    if data.token:
                        creator.instagram_token = data.token
                    if data.page_id:
                        creator.instagram_page_id = data.page_id
                elif platform == "telegram":
                    if data.token:
                        creator.telegram_bot_token = data.token
                elif platform == "whatsapp":
                    if data.token:
                        creator.whatsapp_token = data.token
                    if data.phone_id:
                        creator.whatsapp_phone_id = data.phone_id
                elif platform == "stripe":
                    if data.token:
                        creator.stripe_api_key = data.token
                elif platform == "hotmart":
                    if data.token:
                        creator.hotmart_token = data.token
                elif platform == "calendly":
                    if data.token:
                        creator.calendly_token = data.token

                session.commit()
                logger.info(f"Updated {platform} connection for {creator_id}")
                return {"status": "connected", "platform": platform}
            finally:
                session.close()
        else:
            # No database - return success but warn
            logger.warning(f"No database configured - connection for {platform} not persisted")
            return {"status": "connected", "platform": platform, "warning": "No database - not persisted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating {platform}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
