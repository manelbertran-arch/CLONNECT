"""
OAuth endpoints for platform integrations
Click-and-play authentication for beta testers
"""
import os
import logging
import secrets
from urllib.parse import urlencode
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/oauth", tags=["oauth"])

# Frontend URL for redirects after OAuth
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://clonnect.vercel.app")
# Backend API URL for OAuth callbacks
API_URL = os.getenv("API_URL", "https://api-clonnect.up.railway.app")


@router.get("/debug")
async def oauth_debug():
    """Debug endpoint to verify OAuth configuration (remove in production)"""
    stripe_id = os.getenv("STRIPE_CLIENT_ID", "")
    stripe_secret = os.getenv("STRIPE_SECRET_KEY", "")
    return {
        "api_url": API_URL,
        "frontend_url": FRONTEND_URL,
        "stripe": {
            "client_id_set": bool(stripe_id),
            "client_id_length": len(stripe_id),
            "client_id_prefix": stripe_id[:10] if len(stripe_id) > 10 else "NOT_SET",
            "secret_set": bool(stripe_secret),
        },
        "meta": {
            "app_id_set": bool(os.getenv("META_APP_ID", "")),
        },
        "paypal": {
            "client_id_set": bool(os.getenv("PAYPAL_CLIENT_ID", "")),
        },
        "calendly": {
            "client_id_set": bool(os.getenv("CALENDLY_CLIENT_ID", "")),
        }
    }


# =============================================================================
# INSTAGRAM / META
# =============================================================================
META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_REDIRECT_URI = os.getenv("META_REDIRECT_URI", f"{API_URL}/oauth/instagram/callback")

@router.get("/instagram/start")
async def instagram_oauth_start(creator_id: str):
    """Start Instagram OAuth flow"""
    if not META_APP_ID:
        raise HTTPException(status_code=500, detail="META_APP_ID not configured")

    # Store state for CSRF protection
    state = f"{creator_id}:{secrets.token_urlsafe(16)}"

    params = {
        "client_id": META_APP_ID,
        "redirect_uri": META_REDIRECT_URI,
        "scope": "instagram_basic,instagram_manage_messages,pages_messaging,pages_show_list",
        "response_type": "code",
        "state": state,
    }

    auth_url = f"https://www.facebook.com/v18.0/dialog/oauth?{urlencode(params)}"
    return {"auth_url": auth_url, "state": state}


@router.get("/instagram/callback")
async def instagram_oauth_callback(code: str = Query(...), state: str = Query("")):
    """Handle Instagram OAuth callback"""
    import httpx

    if not META_APP_ID or not META_APP_SECRET:
        raise HTTPException(status_code=500, detail="Meta credentials not configured")

    # Extract creator_id from state
    creator_id = state.split(":")[0] if ":" in state else "manel"

    try:
        async with httpx.AsyncClient() as client:
            # Exchange code for access token
            token_response = await client.get(
                "https://graph.facebook.com/v18.0/oauth/access_token",
                params={
                    "client_id": META_APP_ID,
                    "client_secret": META_APP_SECRET,
                    "redirect_uri": META_REDIRECT_URI,
                    "code": code,
                }
            )
            token_data = token_response.json()

            if "error" in token_data:
                logger.error(f"Meta token error: {token_data}")
                return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=instagram_auth_failed")

            access_token = token_data.get("access_token")

            # Get Instagram Business Account ID
            pages_response = await client.get(
                "https://graph.facebook.com/v18.0/me/accounts",
                params={"access_token": access_token}
            )
            pages_data = pages_response.json()

            instagram_page_id = None
            if pages_data.get("data"):
                page_id = pages_data["data"][0]["id"]
                # Get Instagram account linked to page
                ig_response = await client.get(
                    f"https://graph.facebook.com/v18.0/{page_id}",
                    params={
                        "fields": "instagram_business_account",
                        "access_token": access_token
                    }
                )
                ig_data = ig_response.json()
                instagram_page_id = ig_data.get("instagram_business_account", {}).get("id")

            # Save to database
            await _save_connection(creator_id, "instagram", access_token, instagram_page_id)

            return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&success=instagram")

    except Exception as e:
        logger.error(f"Instagram OAuth error: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=instagram_failed")


# =============================================================================
# STRIPE CONNECT
# =============================================================================

@router.get("/stripe/start")
async def stripe_oauth_start(creator_id: str):
    """Start Stripe Connect OAuth flow"""
    # Read env vars dynamically to pick up changes without restart
    stripe_client_id = os.getenv("STRIPE_CLIENT_ID", "").strip()
    stripe_redirect_uri = os.getenv("STRIPE_REDIRECT_URI", f"{API_URL}/oauth/stripe/callback")

    logger.info(f"Stripe OAuth start - client_id exists: {bool(stripe_client_id)}, length: {len(stripe_client_id)}")

    if not stripe_client_id:
        raise HTTPException(status_code=500, detail="STRIPE_CLIENT_ID not configured")

    state = f"{creator_id}:{secrets.token_urlsafe(16)}"

    params = {
        "client_id": stripe_client_id,
        "response_type": "code",
        "scope": "read_write",
        "redirect_uri": stripe_redirect_uri,
        "state": state,
    }

    auth_url = f"https://connect.stripe.com/oauth/authorize?{urlencode(params)}"
    logger.info(f"Stripe OAuth URL generated with redirect: {stripe_redirect_uri}")
    return {"auth_url": auth_url, "state": state}


@router.get("/stripe/callback")
async def stripe_oauth_callback(code: str = Query(...), state: str = Query("")):
    """Handle Stripe OAuth callback"""
    import httpx

    stripe_secret_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    if not stripe_secret_key:
        raise HTTPException(status_code=500, detail="Stripe credentials not configured")

    creator_id = state.split(":")[0] if ":" in state else "manel"

    try:
        async with httpx.AsyncClient() as client:
            # Exchange code for access token
            token_response = await client.post(
                "https://connect.stripe.com/oauth/token",
                data={
                    "client_secret": stripe_secret_key,
                    "code": code,
                    "grant_type": "authorization_code",
                }
            )
            token_data = token_response.json()

            if "error" in token_data:
                logger.error(f"Stripe token error: {token_data}")
                return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=stripe_auth_failed")

            access_token = token_data.get("access_token")
            stripe_user_id = token_data.get("stripe_user_id")

            # Save to database
            await _save_connection(creator_id, "stripe", access_token, stripe_user_id)

            return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&success=stripe")

    except Exception as e:
        logger.error(f"Stripe OAuth error: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=stripe_failed")


# =============================================================================
# PAYPAL
# =============================================================================
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_REDIRECT_URI = os.getenv("PAYPAL_REDIRECT_URI", f"{API_URL}/oauth/paypal/callback")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")  # sandbox or live

@router.get("/paypal/start")
async def paypal_oauth_start(creator_id: str):
    """Start PayPal OAuth flow"""
    if not PAYPAL_CLIENT_ID:
        raise HTTPException(status_code=500, detail="PAYPAL_CLIENT_ID not configured")

    state = f"{creator_id}:{secrets.token_urlsafe(16)}"

    base_url = "https://www.sandbox.paypal.com" if PAYPAL_MODE == "sandbox" else "https://www.paypal.com"

    params = {
        "client_id": PAYPAL_CLIENT_ID,
        "response_type": "code",
        "scope": "openid email https://uri.paypal.com/services/paypalattributes",
        "redirect_uri": PAYPAL_REDIRECT_URI,
        "state": state,
    }

    auth_url = f"{base_url}/signin/authorize?{urlencode(params)}"
    return {"auth_url": auth_url, "state": state}


@router.get("/paypal/callback")
async def paypal_oauth_callback(code: str = Query(...), state: str = Query("")):
    """Handle PayPal OAuth callback"""
    import httpx
    import base64

    if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="PayPal credentials not configured")

    creator_id = state.split(":")[0] if ":" in state else "manel"

    try:
        base_url = "https://api-m.sandbox.paypal.com" if PAYPAL_MODE == "sandbox" else "https://api-m.paypal.com"

        # Create Basic Auth header
        credentials = base64.b64encode(f"{PAYPAL_CLIENT_ID}:{PAYPAL_CLIENT_SECRET}".encode()).decode()

        async with httpx.AsyncClient() as client:
            # Exchange code for access token
            token_response = await client.post(
                f"{base_url}/v1/oauth2/token",
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": PAYPAL_REDIRECT_URI,
                }
            )
            token_data = token_response.json()

            if "error" in token_data:
                logger.error(f"PayPal token error: {token_data}")
                return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=paypal_auth_failed")

            access_token = token_data.get("access_token")

            # Get user info
            user_response = await client.get(
                f"{base_url}/v1/identity/oauth2/userinfo?schema=paypalv1.1",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_data = user_response.json()
            paypal_email = user_data.get("emails", [{}])[0].get("value", "")

            # Save to database
            await _save_connection(creator_id, "paypal", access_token, paypal_email)

            return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&success=paypal")

    except Exception as e:
        logger.error(f"PayPal OAuth error: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=paypal_failed")


# =============================================================================
# CALENDLY
# =============================================================================
CALENDLY_CLIENT_ID = os.getenv("CALENDLY_CLIENT_ID", "")
CALENDLY_CLIENT_SECRET = os.getenv("CALENDLY_CLIENT_SECRET", "")
CALENDLY_REDIRECT_URI = os.getenv("CALENDLY_REDIRECT_URI", f"{API_URL}/oauth/calendly/callback")

@router.get("/calendly/start")
async def calendly_oauth_start(creator_id: str):
    """Start Calendly OAuth flow"""
    if not CALENDLY_CLIENT_ID:
        raise HTTPException(status_code=500, detail="CALENDLY_CLIENT_ID not configured")

    state = f"{creator_id}:{secrets.token_urlsafe(16)}"

    params = {
        "client_id": CALENDLY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": CALENDLY_REDIRECT_URI,
        "state": state,
    }

    auth_url = f"https://auth.calendly.com/oauth/authorize?{urlencode(params)}"
    return {"auth_url": auth_url, "state": state}


@router.get("/calendly/callback")
async def calendly_oauth_callback(code: str = Query(...), state: str = Query("")):
    """Handle Calendly OAuth callback"""
    import httpx

    if not CALENDLY_CLIENT_ID or not CALENDLY_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Calendly credentials not configured")

    creator_id = state.split(":")[0] if ":" in state else "manel"

    try:
        async with httpx.AsyncClient() as client:
            # Exchange code for access token
            token_response = await client.post(
                "https://auth.calendly.com/oauth/token",
                data={
                    "client_id": CALENDLY_CLIENT_ID,
                    "client_secret": CALENDLY_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": CALENDLY_REDIRECT_URI,
                }
            )
            token_data = token_response.json()

            if "error" in token_data:
                logger.error(f"Calendly token error: {token_data}")
                return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=calendly_auth_failed")

            access_token = token_data.get("access_token")

            # Get user info
            user_response = await client.get(
                "https://api.calendly.com/users/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_data = user_response.json()
            calendly_uri = user_data.get("resource", {}).get("uri", "")

            # Save to database
            await _save_connection(creator_id, "calendly", access_token, calendly_uri)

            return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&success=calendly")

    except Exception as e:
        logger.error(f"Calendly OAuth error: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=calendly_failed")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

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
                    creator = Creator(name=creator_id, email=f"{creator_id}@clonnect.com")
                    session.add(creator)

                if platform == "instagram":
                    creator.instagram_token = token
                    creator.instagram_page_id = extra_id
                elif platform == "stripe":
                    creator.stripe_api_key = token
                elif platform == "paypal":
                    creator.paypal_token = token
                    creator.paypal_email = extra_id
                elif platform == "calendly":
                    creator.calendly_token = token

                session.commit()
                logger.info(f"Saved {platform} connection for {creator_id}")
            finally:
                session.close()
    except Exception as e:
        logger.error(f"Error saving {platform} connection: {e}")
        raise
