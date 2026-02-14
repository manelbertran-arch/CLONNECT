"""
Token and OAuth management endpoints.

Handles Instagram/Facebook token operations:
- Token refresh (automatic and manual)
- Token exchange (short-lived to long-lived)
- Token setting and configuration
- Instagram ID fixes
- Webhook subscription management (SPEC-004B)
"""

import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/oauth/status/{creator_id}")
async def get_oauth_status(creator_id: str):
    """
    Get OAuth token status for a creator.

    Returns token validity, expiration date, and days remaining.
    """
    try:
        from datetime import datetime

        from api.database import SessionLocal

        session = SessionLocal()
        try:
            result = session.execute(
                text("""
                    SELECT name, instagram_token, instagram_token_expires_at
                    FROM creators
                    WHERE id::text = :cid OR name = :cid
                """),
                {"cid": creator_id},
            ).fetchone()

            if not result:
                raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

            creator_name, token, expires_at = result

            if not token:
                return {
                    "creator": creator_name,
                    "token_valid": False,
                    "token_present": False,
                    "expires_at": None,
                    "days_remaining": None,
                }

            days_remaining = None
            token_expired = False
            if expires_at:
                now = datetime.utcnow()
                if expires_at.tzinfo:
                    expires_at_naive = expires_at.replace(tzinfo=None)
                else:
                    expires_at_naive = expires_at
                days_remaining = (expires_at_naive - now).days
                token_expired = days_remaining < 0

            return {
                "creator": creator_name,
                "token_valid": not token_expired,
                "token_present": True,
                "token_prefix": token[:15] + "..." if token else None,
                "token_type": (
                    "PAGE (EAA)" if token.startswith("EAA")
                    else "INSTAGRAM (IGAAT)" if token.startswith("IGAAT")
                    else "UNKNOWN"
                ),
                "expires_at": expires_at.isoformat() if expires_at else None,
                "days_remaining": days_remaining,
            }
        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth status check failed for {creator_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh-all-tokens")
async def refresh_all_instagram_tokens():
    """
    Cron job: Revisar todos los tokens de Instagram y refrescar los que expiran pronto.

    Diseñado para ser llamado diariamente por un cron job.

    Refresca tokens que expiran en menos de 7 días.
    Los tokens long-lived duran 60 días y se pueden refrescar indefinidamente.
    """
    try:
        from api.database import SessionLocal
        from core.token_refresh_service import refresh_all_creator_tokens

        session = SessionLocal()
        try:
            result = await refresh_all_creator_tokens(session)
            return {"status": "success", **result}
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/refresh-token/{creator_id}")
async def refresh_creator_token(creator_id: str):
    """
    Refrescar el token de Instagram de un creator específico.

    Args:
        creator_id: Nombre o UUID del creator

    Returns:
        Estado del refresh (success/skip/error)
    """
    try:
        from api.database import SessionLocal
        from core.token_refresh_service import check_and_refresh_if_needed

        session = SessionLocal()
        try:
            result = await check_and_refresh_if_needed(creator_id, session)
            return {"status": "success" if result.get("success") else "error", **result}
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Token refresh failed for {creator_id}: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/exchange-token/{creator_id}")
async def exchange_short_lived_token(creator_id: str, short_lived_token: str):
    """
    Convertir un token short-lived (1-2h) a long-lived (60 días).

    Usar después del OAuth flow para obtener un token duradero.

    Args:
        creator_id: Nombre o UUID del creator
        short_lived_token: Token de corta duración del OAuth

    Returns:
        Nuevo token long-lived y fecha de expiración
    """
    try:
        from api.database import SessionLocal
        from core.token_refresh_service import exchange_for_long_lived_token

        # Exchange token
        new_token_data = await exchange_for_long_lived_token(short_lived_token)

        if not new_token_data:
            return {
                "status": "error",
                "error": "Failed to exchange token. Check META_APP_SECRET is configured.",
            }

        # Save to database
        session = SessionLocal()
        try:
            session.execute(
                text(
                    """
                    UPDATE creators
                    SET instagram_token = :token,
                        instagram_token_expires_at = :expires_at
                    WHERE id::text = :cid OR name = :cid
                """
                ),
                {
                    "token": new_token_data["token"],
                    "expires_at": new_token_data["expires_at"],
                    "cid": creator_id,
                },
            )
            session.commit()

            return {
                "status": "success",
                "token_prefix": new_token_data["token"][:20] + "...",
                "expires_at": new_token_data["expires_at"].isoformat(),
                "expires_in_days": new_token_data["expires_in"] // 86400,
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Token exchange failed for {creator_id}: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/set-token/{creator_id}")
async def set_creator_token(creator_id: str, token: str, instagram_user_id: str = None):
    """
    Set Instagram token directly for a creator.

    Use this when you already have a valid long-lived token
    (e.g., from Meta Developer Portal or manual OAuth).

    Args:
        creator_id: Nombre del creator
        token: Token de Instagram válido
        instagram_user_id: ID de usuario de Instagram (opcional)
    """
    try:
        from api.database import SessionLocal

        session = SessionLocal()
        try:
            # Build update query
            if instagram_user_id:
                session.execute(
                    text(
                        """
                        UPDATE creators
                        SET instagram_token = :token,
                            instagram_user_id = :ig_user_id
                        WHERE name = :cid
                    """
                    ),
                    {"token": token, "ig_user_id": instagram_user_id, "cid": creator_id},
                )
            else:
                session.execute(
                    text(
                        """
                        UPDATE creators
                        SET instagram_token = :token
                        WHERE name = :cid
                    """
                    ),
                    {"token": token, "cid": creator_id},
                )
            session.commit()

            return {
                "status": "success",
                "creator_id": creator_id,
                "token_prefix": token[:20] + "...",
                "instagram_user_id": instagram_user_id,
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Set token failed for {creator_id}: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/set-page-token/{creator_id}")
async def set_page_access_token(creator_id: str, token: str):
    """
    Manually set a Page Access Token for Instagram Messaging.

    Use this when the OAuth flow doesn't return a proper Page token.
    Get the token from Graph API Explorer:
    1. Go to https://developers.facebook.com/tools/explorer/
    2. Select your App
    3. Select "Page" (not User) for the token type
    4. Add permissions: pages_messaging, instagram_manage_messages
    5. Generate and copy the token

    Args:
        creator_id: Creator name or UUID
        token: Page Access Token (should start with 'EAA')
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator

        # Validate token format
        if not token.startswith("EAA"):
            logger.warning("Token doesn't start with EAA - may not be a Page token")

        session = SessionLocal()
        try:
            creator = (
                session.query(Creator)
                .filter((Creator.name == creator_id) | (Creator.id == creator_id))
                .first()
            )

            if not creator:
                return {"status": "error", "error": f"Creator {creator_id} not found"}

            old_prefix = creator.instagram_token[:15] if creator.instagram_token else "NONE"
            creator.instagram_token = token
            session.commit()

            logger.info(f"Set Page token for {creator_id}: {old_prefix}... -> {token[:15]}...")

            return {
                "status": "success",
                "creator_id": creator_id,
                "old_token_prefix": old_prefix,
                "new_token_prefix": token[:15] + "...",
                "token_type": (
                    "PAGE (EAA)"
                    if token.startswith("EAA")
                    else "INSTAGRAM (IGAAT)" if token.startswith("IGAAT") else "UNKNOWN"
                ),
                "valid_for_messaging": token.startswith("EAA"),
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error setting page token: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/fix-instagram-ids/{creator_id}")
async def fix_instagram_ids(creator_id: str):
    """
    Fix instagram_user_id using the real ID from the token, and clean up ghost leads.
    """
    import requests

    from api.database import SessionLocal
    from api.models import Creator

    session = SessionLocal()
    results = {
        "old_values": {},
        "new_values": {},
        "ghost_leads_deleted": [],
        "cache_cleared": False,
    }

    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

        if not creator.instagram_token:
            raise HTTPException(status_code=400, detail="Creator has no Instagram token")

        # Store old values
        results["old_values"] = {
            "instagram_user_id": creator.instagram_user_id,
            "instagram_page_id": creator.instagram_page_id,
        }

        token = creator.instagram_token

        # Get real Instagram User ID from token
        url = "https://graph.instagram.com/me"
        params = {"access_token": token, "fields": "id,username"}
        response = requests.get(url, params=params, timeout=10)

        if response.status_code != 200:
            return {
                "status": "error",
                "error": f"Instagram API error: {response.status_code}",
                "detail": response.text[:500],
            }

        data = response.json()
        real_ig_user_id = data.get("id")
        ig_username = data.get("username")

        # Update creator with correct ID
        # For IGAAT tokens, use the same ID for both user_id and page_id
        # because Meta webhooks send this ID as the recipient
        creator.instagram_user_id = real_ig_user_id
        creator.instagram_page_id = real_ig_user_id  # Same ID for routing
        session.commit()

        results["new_values"] = {
            "instagram_user_id": real_ig_user_id,
            "instagram_page_id": real_ig_user_id,
            "instagram_username": ig_username,
        }

        # Delete ghost leads (0 messages)
        ghost_leads = session.execute(
            text(
                """
                SELECT l.id, l.platform_user_id, l.username
                FROM leads l
                WHERE l.creator_id = :cid
                AND NOT EXISTS (SELECT 1 FROM messages m WHERE m.lead_id = l.id)
            """
            ),
            {"cid": str(creator.id)},
        ).fetchall()

        for lead in ghost_leads:
            lead_id, platform_user_id, username = lead
            session.execute(text("DELETE FROM leads WHERE id = :id"), {"id": str(lead_id)})
            results["ghost_leads_deleted"].append(
                {"platform_user_id": platform_user_id, "username": username}
            )

        session.commit()

        # Clear lookup cache
        try:
            from api.routers.instagram import _creator_by_page_id_cache

            _creator_by_page_id_cache.clear()
            results["cache_cleared"] = True
        except Exception:
            pass

        results["status"] = "ok"
        return results

    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Error fixing Instagram IDs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@router.post("/instagram/subscribe-feed")
async def subscribe_to_feed_webhooks():
    """
    Subscribe to Instagram feed webhooks (SPEC-004B).

    Calls the Meta Graph API to subscribe the app to "feed" events
    in addition to "messaging". This enables real-time content ingestion
    when a creator publishes a new post/reel.

    Requires env vars: META_APP_ID, META_APP_SECRET (for app access token).

    Alternative: Subscribe manually via Meta Developer Dashboard →
    App → Webhooks → Instagram → feed → Subscribe.
    """
    import os

    import httpx

    app_id = os.getenv("META_APP_ID", "")
    app_secret = os.getenv("META_APP_SECRET", "")
    verify_token = os.getenv("INSTAGRAM_VERIFY_TOKEN", "clonnect_verify_2024")
    callback_url = "https://www.clonnectapp.com/webhook/instagram"

    if not app_id or not app_secret:
        return {
            "status": "error",
            "error": "META_APP_ID and META_APP_SECRET env vars required",
            "manual_instructions": {
                "step1": "Go to Meta Developer → Your App → Webhooks",
                "step2": "Select 'Instagram' object",
                "step3": "Subscribe to 'feed' field",
                "step4": f"Callback URL: {callback_url}",
                "step5": f"Verify token: {verify_token}",
            },
        }

    # Get app access token
    app_access_token = f"{app_id}|{app_secret}"

    url = f"https://graph.facebook.com/v21.0/{app_id}/subscriptions"
    params = {
        "object": "instagram",
        "callback_url": callback_url,
        "fields": "feed,messaging",
        "verify_token": verify_token,
        "access_token": app_access_token,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, params=params)

            if resp.status_code == 200:
                data = resp.json()
                logger.info(f"[FEED-WEBHOOK] Subscribed to feed+messaging: {data}")
                return {
                    "status": "subscribed",
                    "fields": ["feed", "messaging"],
                    "callback_url": callback_url,
                    "response": data,
                }

            logger.error(f"[FEED-WEBHOOK] Subscription failed: {resp.status_code} {resp.text}")
            return {
                "status": "error",
                "http_status": resp.status_code,
                "error": resp.text[:500],
                "manual_instructions": {
                    "step1": "Go to Meta Developer → Your App → Webhooks",
                    "step2": "Select 'Instagram' object",
                    "step3": "Subscribe to 'feed' field",
                    "step4": f"Callback URL: {callback_url}",
                    "step5": f"Verify token: {verify_token}",
                },
            }

    except Exception as e:
        logger.error(f"[FEED-WEBHOOK] Subscription request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
