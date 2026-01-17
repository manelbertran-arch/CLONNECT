"""Creator config endpoints"""
from fastapi import APIRouter, HTTPException, Body
import logging
import os

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/creator/config", tags=["config"])

USE_DB = bool(os.getenv("DATABASE_URL"))
if USE_DB:
    try:
        from api.services import db_service
    except ImportError:
        from api import db_service

@router.get("/{creator_id}")
async def get_creator_config(creator_id: str):
    if USE_DB:
        try:
            config = db_service.get_creator_by_name(creator_id)
            if config:
                return {"status": "ok", "config": config}
        except Exception as e:
            logger.warning(f"DB get config failed for {creator_id}: {e}")
    raise HTTPException(status_code=404, detail="Creator not found")

@router.put("/{creator_id}")
async def update_creator_config(creator_id: str, updates: dict = Body(...)):
    if USE_DB:
        try:
            success = db_service.update_creator(creator_id, updates)
            if success:
                return {"status": "ok", "message": "Config updated"}
        except Exception as e:
            logger.warning(f"DB update config failed for {creator_id}: {e}")
    raise HTTPException(status_code=404, detail="Creator not found")


# =============================================================================
# PRODUCT PRICE CONFIG (for lead scoring)
# =============================================================================

@router.get("/{creator_id}/product-price")
async def get_product_price(creator_id: str):
    """
    Get product price configuration for lead scoring.

    Returns:
        product_price: float (default 97.0)
    """
    if USE_DB:
        try:
            from api.database import SessionLocal
            from api.models import Creator

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if creator:
                    return {
                        "status": "ok",
                        "product_price": creator.product_price or 97.0
                    }
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Get product price failed: {e}")
    raise HTTPException(status_code=404, detail="Creator not found")


@router.post("/{creator_id}/product-price")
async def update_product_price(creator_id: str, data: dict = Body(...)):
    """
    Update product price for lead scoring.

    Body:
        product_price: float (e.g., 97.0, 200.0, 497.0)
    """
    if USE_DB:
        try:
            from api.database import SessionLocal
            from api.models import Creator

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if creator:
                    price = data.get("product_price", 97.0)
                    if price < 0:
                        raise HTTPException(status_code=400, detail="Product price must be positive")

                    creator.product_price = float(price)
                    session.commit()

                    logger.info(f"Updated product price for {creator_id}: €{price}")
                    return {
                        "status": "ok",
                        "message": "Product price updated",
                        "product_price": creator.product_price
                    }
            finally:
                session.close()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Update product price failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=404, detail="Creator not found")


# =============================================================================
# EMAIL CAPTURE CONFIG
# =============================================================================

@router.get("/{creator_id}/email-capture")
async def get_email_capture_config(creator_id: str):
    """
    Get email capture configuration for a creator.

    Returns:
        enabled: bool
        ask_after_messages: int
        offer_type: "none" | "discount" | "content" | "priority" | "custom"
        offer_config: dict with type-specific settings
    """
    if USE_DB:
        try:
            from api.database import SessionLocal
            from api.models import Creator

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if creator:
                    config = creator.email_capture_config or {
                        "enabled": True,
                        "ask_after_messages": 3,
                        "offer_type": "none",
                        "offer_config": None
                    }
                    return {"status": "ok", "config": config}
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Get email capture config failed: {e}")
    raise HTTPException(status_code=404, detail="Creator not found")


@router.post("/{creator_id}/email-capture")
async def update_email_capture_config(creator_id: str, config: dict = Body(...)):
    """
    Update email capture configuration for a creator.

    Body:
        enabled: bool
        ask_after_messages: int (default 3)
        offer_type: "none" | "discount" | "content" | "priority" | "custom"
        offer_config: dict
            - discount: { "percent": 10, "code": "VIP10" }
            - content: { "description": "mi guia PDF", "url": "https://..." }
            - priority: { "description": "lanzamientos y ofertas" }
            - custom: { "message": "texto personalizado" }
    """
    if USE_DB:
        try:
            from api.database import SessionLocal
            from api.models import Creator

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if creator:
                    # Validate config
                    valid_offer_types = ["none", "discount", "content", "priority", "custom"]
                    offer_type = config.get("offer_type", "none")
                    if offer_type not in valid_offer_types:
                        raise HTTPException(
                            status_code=400,
                            detail=f"offer_type must be one of: {valid_offer_types}"
                        )

                    # Update config
                    creator.email_capture_config = {
                        "enabled": config.get("enabled", True),
                        "ask_after_messages": config.get("ask_after_messages", 3),
                        "offer_type": offer_type,
                        "offer_config": config.get("offer_config")
                    }
                    session.commit()

                    logger.info(f"Updated email capture config for {creator_id}: {offer_type}")
                    return {
                        "status": "ok",
                        "message": "Email capture config updated",
                        "config": creator.email_capture_config
                    }
            finally:
                session.close()
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Update email capture config failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    raise HTTPException(status_code=404, detail="Creator not found")


# =============================================================================
# UNIFIED PROFILES API
# =============================================================================

@router.get("/unified-profile/{email}")
async def get_unified_profile_by_email(email: str):
    """
    Get unified profile by email with all linked platform identities.
    """
    try:
        from core.unified_profile_service import (
            get_unified_profile_by_email as get_profile,
            get_all_platform_identities
        )

        profile = get_profile(email)
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")

        # Get all platform identities
        identities = get_all_platform_identities(profile["id"])

        return {
            "status": "ok",
            "profile": profile,
            "platform_identities": identities
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get unified profile failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
