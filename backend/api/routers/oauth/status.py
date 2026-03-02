"""OAuth status endpoint + shared helper."""

import logging
import os

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(tags=["oauth"])

# Frontend URL for redirects after OAuth
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://www.clonnectapp.com")
# Backend API URL for OAuth callbacks
API_URL = os.getenv("API_URL", "https://api.clonnectapp.com")


async def _save_connection(creator_id: str, platform: str, token: str, extra_id: str = None):
    """Save OAuth connection to database"""
    try:
        from api.database import DATABASE_URL, SessionLocal

        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                from api.models import Creator

                creator = session.query(Creator).filter_by(name=creator_id).first()

                if not creator:
                    logger.warning(f"Creator {creator_id} not found, creating...")
                    try:
                        creator = Creator(name=creator_id, email=f"{creator_id}@clonnect.com")
                        session.add(creator)
                        session.flush()
                    except Exception:
                        session.rollback()
                        creator = session.query(Creator).filter_by(name=creator_id).first()
                        if not creator:
                            raise

                if platform == "instagram":
                    creator.instagram_token = token
                    creator.instagram_page_id = extra_id
                elif platform == "whatsapp":
                    creator.whatsapp_token = token
                    creator.whatsapp_phone_id = extra_id
                elif platform == "stripe":
                    creator.stripe_api_key = token
                elif platform == "paypal":
                    creator.paypal_token = token
                    creator.paypal_email = extra_id

                session.commit()
                logger.info(f"Saved {platform} connection for {creator_id}")
            finally:
                session.close()
    except Exception as e:
        logger.error(f"Error saving {platform} connection: {e}")
        raise


@router.get("/status/{creator_id}")
async def get_oauth_status(creator_id: str):
    """
    Get OAuth connection status for all platforms.
    Shows token expiry, refresh capability, and connection health.
    """
    from datetime import datetime, timezone

    try:
        from api.database import SessionLocal
        from api.models import Creator

        with SessionLocal() as db:
            creator = db.query(Creator).filter_by(name=creator_id).first()

            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

            now = datetime.now(timezone.utc)

            def get_token_status(token, refresh_token, expires_at):
                if not token:
                    return {
                        "connected": False,
                        "status": "not_connected",
                        "message": "Not connected",
                    }

                if not expires_at:
                    return {
                        "connected": True,
                        "status": "unknown_expiry",
                        "has_refresh_token": bool(refresh_token),
                        "message": "Connected (expiry unknown)",
                    }

                time_left = expires_at - now
                seconds_left = time_left.total_seconds()

                if seconds_left <= 0:
                    status = "expired"
                    message = "Token expired"
                elif seconds_left < 300:  # 5 minutes
                    status = "expiring_soon"
                    message = f"Expires in {int(seconds_left)}s"
                elif seconds_left < 3600:  # 1 hour
                    status = "valid"
                    message = f"Expires in {int(seconds_left/60)}min"
                else:
                    hours = seconds_left / 3600
                    status = "valid"
                    message = f"Expires in {hours:.1f}h"

                return {
                    "connected": True,
                    "status": status,
                    "has_refresh_token": bool(refresh_token),
                    "can_auto_refresh": bool(refresh_token),
                    "expires_at": expires_at.isoformat() if expires_at else None,
                    "seconds_until_expiry": int(seconds_left),
                    "message": message,
                }

            google_status = get_token_status(
                creator.google_access_token,
                creator.google_refresh_token,
                creator.google_token_expires_at,
            )

            return {
                "status": "ok",
                "creator_id": creator_id,
                "platforms": {"google": google_status},
                "summary": {
                    "total_connected": 1 if google_status["connected"] else 0,
                    "needs_attention": google_status.get("status") in ["expired", "expiring_soon"],
                },
            }

    except HTTPException:
        raise
    except Exception as e:
        from api.utils.error_helpers import safe_error_detail

        raise HTTPException(status_code=500, detail=safe_error_detail(e, "OAuth status check"))
