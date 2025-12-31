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
    stripe_secret = os.getenv("STRIPE_SECRET_KEY", "")
    return {
        "api_url": API_URL,
        "frontend_url": FRONTEND_URL,
        "stripe": {
            "method": "Account Links API (no OAuth needed)",
            "secret_key_set": bool(stripe_secret),
            "secret_key_prefix": stripe_secret[:7] + "..." if len(stripe_secret) > 10 else "NOT_SET",
        },
        "meta": {
            "app_id_set": bool(os.getenv("META_APP_ID", "")),
        },
        "paypal": {
            "client_id_set": bool(os.getenv("PAYPAL_CLIENT_ID", "")),
        },
        "calendly": {
            "client_id_set": bool(os.getenv("CALENDLY_CLIENT_ID", "")),
        },
        "zoom": {
            "client_id_set": bool(os.getenv("ZOOM_CLIENT_ID", "")),
        },
        "google": {
            "client_id_set": bool(os.getenv("GOOGLE_CLIENT_ID", "")),
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

    # Basic scopes - messaging requires adding permissions in Meta dashboard first
    params = {
        "client_id": META_APP_ID,
        "redirect_uri": META_REDIRECT_URI,
        "scope": "public_profile,pages_show_list",
        "response_type": "code",
        "state": state,
    }

    auth_url = f"https://www.facebook.com/v21.0/dialog/oauth?{urlencode(params)}"
    return {"auth_url": auth_url, "state": state}


@router.get("/instagram/callback")
async def instagram_oauth_callback(
    code: str = Query(None),
    state: str = Query(""),
    error_code: str = Query(None),
    error_message: str = Query(None)
):
    """Handle Instagram OAuth callback"""
    import httpx

    # Handle OAuth errors (like invalid scopes)
    if error_code or error_message:
        logger.error(f"Instagram OAuth error: {error_code} - {error_message}")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=instagram_scope_error")

    if not code:
        logger.error("Instagram OAuth: No code received")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=instagram_no_code")

    if not META_APP_ID or not META_APP_SECRET:
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=instagram_not_configured")

    # Extract creator_id from state
    creator_id = state.split(":")[0] if ":" in state else "manel"

    try:
        async with httpx.AsyncClient() as client:
            # Exchange code for access token
            token_response = await client.get(
                "https://graph.facebook.com/v21.0/oauth/access_token",
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
# WHATSAPP BUSINESS
# =============================================================================
WHATSAPP_REDIRECT_URI = os.getenv("WHATSAPP_REDIRECT_URI", f"{API_URL}/oauth/whatsapp/callback")

@router.get("/whatsapp/start")
async def whatsapp_oauth_start(creator_id: str):
    """
    Start WhatsApp Business OAuth flow.

    WhatsApp Business uses Facebook Login with specific scopes for
    WhatsApp Business Management API access.
    """
    if not META_APP_ID:
        raise HTTPException(status_code=500, detail="META_APP_ID not configured")

    # Store state for CSRF protection
    state = f"{creator_id}:{secrets.token_urlsafe(16)}"

    # WhatsApp Business scopes - requires approved Meta Business app
    # Reference: https://developers.facebook.com/docs/whatsapp/embedded-signup/
    params = {
        "client_id": META_APP_ID,
        "redirect_uri": WHATSAPP_REDIRECT_URI,
        "scope": "whatsapp_business_management,whatsapp_business_messaging,business_management",
        "response_type": "code",
        "state": state,
        "config_id": os.getenv("WHATSAPP_CONFIG_ID", ""),  # Embedded Signup config
    }

    # Remove empty config_id if not set
    if not params["config_id"]:
        del params["config_id"]

    auth_url = f"https://www.facebook.com/v21.0/dialog/oauth?{urlencode(params)}"
    return {"auth_url": auth_url, "state": state}


@router.get("/whatsapp/callback")
async def whatsapp_oauth_callback(
    code: str = Query(None),
    state: str = Query(""),
    error_code: str = Query(None),
    error_message: str = Query(None)
):
    """Handle WhatsApp Business OAuth callback"""
    import httpx

    # Handle OAuth errors
    if error_code or error_message:
        logger.error(f"WhatsApp OAuth error: {error_code} - {error_message}")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=whatsapp_scope_error")

    if not code:
        logger.error("WhatsApp OAuth: No code received")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=whatsapp_no_code")

    if not META_APP_ID or not META_APP_SECRET:
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=whatsapp_not_configured")

    # Extract creator_id from state
    creator_id = state.split(":")[0] if ":" in state else "manel"

    try:
        async with httpx.AsyncClient() as client:
            # Exchange code for access token
            token_response = await client.get(
                "https://graph.facebook.com/v21.0/oauth/access_token",
                params={
                    "client_id": META_APP_ID,
                    "client_secret": META_APP_SECRET,
                    "redirect_uri": WHATSAPP_REDIRECT_URI,
                    "code": code,
                }
            )
            token_data = token_response.json()

            if "error" in token_data:
                logger.error(f"WhatsApp token error: {token_data}")
                return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=whatsapp_auth_failed")

            access_token = token_data.get("access_token")

            # Get WhatsApp Business Account and Phone Number ID
            # First, get the user's business accounts
            waba_response = await client.get(
                "https://graph.facebook.com/v21.0/me/businesses",
                params={"access_token": access_token}
            )
            waba_data = waba_response.json()

            phone_number_id = None
            waba_id = None

            # Find WhatsApp Business Account
            if waba_data.get("data"):
                business_id = waba_data["data"][0]["id"]

                # Get WhatsApp Business Accounts owned by this business
                owned_wabas = await client.get(
                    f"https://graph.facebook.com/v21.0/{business_id}/owned_whatsapp_business_accounts",
                    params={"access_token": access_token}
                )
                owned_data = owned_wabas.json()

                if owned_data.get("data"):
                    waba_id = owned_data["data"][0]["id"]

                    # Get phone numbers for this WABA
                    phones_response = await client.get(
                        f"https://graph.facebook.com/v21.0/{waba_id}/phone_numbers",
                        params={"access_token": access_token}
                    )
                    phones_data = phones_response.json()

                    if phones_data.get("data"):
                        phone_number_id = phones_data["data"][0]["id"]
                        logger.info(f"Found WhatsApp phone number ID: {phone_number_id}")

            # Save to database
            await _save_connection(creator_id, "whatsapp", access_token, phone_number_id)

            return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&success=whatsapp")

    except Exception as e:
        logger.error(f"WhatsApp OAuth error: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=whatsapp_failed")


# =============================================================================
# STRIPE CONNECT (using Account Links API - modern approach)
# =============================================================================

@router.get("/stripe/start")
async def stripe_oauth_start(creator_id: str):
    """Start Stripe Connect onboarding using Account Links API"""
    import httpx

    stripe_secret_key = os.getenv("STRIPE_SECRET_KEY", "").strip()

    if not stripe_secret_key:
        raise HTTPException(status_code=500, detail="STRIPE_SECRET_KEY not configured")

    logger.info(f"Starting Stripe Connect for creator: {creator_id}")

    try:
        async with httpx.AsyncClient() as client:
            # Step 1: Create a Stripe Express connected account
            account_response = await client.post(
                "https://api.stripe.com/v1/accounts",
                headers={"Authorization": f"Bearer {stripe_secret_key}"},
                data={
                    "type": "express",
                    "metadata[creator_id]": creator_id,
                }
            )
            account_data = account_response.json()

            if "error" in account_data:
                logger.error(f"Stripe account creation error: {account_data}")
                raise HTTPException(status_code=400, detail=account_data["error"]["message"])

            account_id = account_data["id"]
            logger.info(f"Created Stripe account: {account_id}")

            # Step 2: Create an Account Link for onboarding
            link_response = await client.post(
                "https://api.stripe.com/v1/account_links",
                headers={"Authorization": f"Bearer {stripe_secret_key}"},
                data={
                    "account": account_id,
                    "refresh_url": f"{API_URL}/oauth/stripe/refresh?creator_id={creator_id}&account_id={account_id}",
                    "return_url": f"{API_URL}/oauth/stripe/callback?creator_id={creator_id}&account_id={account_id}",
                    "type": "account_onboarding",
                }
            )
            link_data = link_response.json()

            if "error" in link_data:
                logger.error(f"Stripe account link error: {link_data}")
                raise HTTPException(status_code=400, detail=link_data["error"]["message"])

            auth_url = link_data["url"]
            logger.info(f"Created Stripe onboarding link for account: {account_id}")

            return {"auth_url": auth_url, "account_id": account_id}

    except httpx.RequestError as e:
        logger.error(f"Stripe API request error: {e}")
        raise HTTPException(status_code=500, detail="Failed to connect to Stripe")


@router.get("/stripe/callback")
async def stripe_oauth_callback(creator_id: str = Query("manel"), account_id: str = Query(...)):
    """Handle Stripe Connect onboarding completion"""
    import httpx

    stripe_secret_key = os.getenv("STRIPE_SECRET_KEY", "").strip()

    if not stripe_secret_key:
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=stripe_not_configured")

    try:
        async with httpx.AsyncClient() as client:
            # Verify the account status
            account_response = await client.get(
                f"https://api.stripe.com/v1/accounts/{account_id}",
                headers={"Authorization": f"Bearer {stripe_secret_key}"}
            )
            account_data = account_response.json()

            if "error" in account_data:
                logger.error(f"Stripe account fetch error: {account_data}")
                return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=stripe_auth_failed")

            # Check if onboarding is complete
            charges_enabled = account_data.get("charges_enabled", False)
            payouts_enabled = account_data.get("payouts_enabled", False)

            logger.info(f"Stripe account {account_id} - charges: {charges_enabled}, payouts: {payouts_enabled}")

            # Save to database (store account_id as the token)
            await _save_connection(creator_id, "stripe", account_id, account_data.get("email"))

            return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&success=stripe")

    except Exception as e:
        logger.error(f"Stripe callback error: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=stripe_failed")


@router.get("/stripe/refresh")
async def stripe_oauth_refresh(creator_id: str = Query("manel"), account_id: str = Query(...)):
    """Handle Stripe Connect refresh (when link expires)"""
    import httpx

    stripe_secret_key = os.getenv("STRIPE_SECRET_KEY", "").strip()

    if not stripe_secret_key:
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=stripe_not_configured")

    try:
        async with httpx.AsyncClient() as client:
            # Create a new Account Link
            link_response = await client.post(
                "https://api.stripe.com/v1/account_links",
                headers={"Authorization": f"Bearer {stripe_secret_key}"},
                data={
                    "account": account_id,
                    "refresh_url": f"{API_URL}/oauth/stripe/refresh?creator_id={creator_id}&account_id={account_id}",
                    "return_url": f"{API_URL}/oauth/stripe/callback?creator_id={creator_id}&account_id={account_id}",
                    "type": "account_onboarding",
                }
            )
            link_data = link_response.json()

            if "error" in link_data:
                logger.error(f"Stripe refresh link error: {link_data}")
                return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=stripe_refresh_failed")

            return RedirectResponse(link_data["url"])

    except Exception as e:
        logger.error(f"Stripe refresh error: {e}")
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

# In-memory store for PKCE code_verifier (in production, use Redis or DB)
_calendly_pkce_store: dict = {}


def _generate_pkce_pair() -> tuple[str, str]:
    """
    Generate PKCE code_verifier and code_challenge pair.

    Returns:
        (code_verifier, code_challenge)
    """
    import hashlib
    import base64

    # Generate code_verifier: 43-128 characters, base64url
    code_verifier = secrets.token_urlsafe(64)[:128]

    # Generate code_challenge: SHA256(code_verifier), base64url encoded
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().rstrip("=")

    return code_verifier, code_challenge


@router.get("/calendly/start")
async def calendly_oauth_start(creator_id: str):
    """Start Calendly OAuth flow with PKCE"""
    if not CALENDLY_CLIENT_ID:
        raise HTTPException(status_code=500, detail="CALENDLY_CLIENT_ID not configured")

    # Generate PKCE pair
    code_verifier, code_challenge = _generate_pkce_pair()

    # Generate state with unique identifier
    state_id = secrets.token_urlsafe(16)
    state = f"{creator_id}:{state_id}"

    # Store code_verifier for later retrieval (keyed by state_id)
    _calendly_pkce_store[state_id] = code_verifier

    params = {
        "client_id": CALENDLY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": CALENDLY_REDIRECT_URI,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    auth_url = f"https://auth.calendly.com/oauth/authorize?{urlencode(params)}"
    return {"auth_url": auth_url, "state": state}


@router.get("/calendly/callback")
async def calendly_oauth_callback(code: str = Query(...), state: str = Query("")):
    """Handle Calendly OAuth callback with PKCE"""
    import httpx
    from datetime import datetime, timezone, timedelta

    if not CALENDLY_CLIENT_ID or not CALENDLY_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Calendly credentials not configured")

    # Extract creator_id and state_id from state
    parts = state.split(":")
    creator_id = parts[0] if parts else "manel"
    state_id = parts[1] if len(parts) > 1 else ""

    # Retrieve code_verifier from store
    code_verifier = _calendly_pkce_store.pop(state_id, None)

    if not code_verifier:
        logger.error(f"Calendly OAuth: code_verifier not found for state {state_id}")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=calendly_invalid_state")

    try:
        async with httpx.AsyncClient() as client:
            # Exchange code for access token (with PKCE code_verifier)
            token_response = await client.post(
                "https://auth.calendly.com/oauth/token",
                data={
                    "client_id": CALENDLY_CLIENT_ID,
                    "client_secret": CALENDLY_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": CALENDLY_REDIRECT_URI,
                    "code_verifier": code_verifier,
                }
            )
            token_data = token_response.json()

            if "error" in token_data:
                logger.error(f"Calendly token error: {token_data}")
                return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=calendly_auth_failed")

            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 7200)  # Default 2 hours

            # Calculate expiration time
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            # Get user info
            user_response = await client.get(
                "https://api.calendly.com/users/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_data = user_response.json()
            calendly_uri = user_data.get("resource", {}).get("uri", "")

            # Save to database with refresh token and expiration
            await _save_calendly_connection(
                creator_id, access_token, refresh_token, expires_at, calendly_uri
            )

            logger.info(f"Calendly connected for {creator_id}, expires at {expires_at}")
            return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&success=calendly")

    except Exception as e:
        logger.error(f"Calendly OAuth error: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=calendly_failed")


# =============================================================================
# ZOOM
# =============================================================================
ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID", "")
ZOOM_CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET", "")
ZOOM_REDIRECT_URI = os.getenv("ZOOM_REDIRECT_URI", f"{API_URL}/oauth/zoom/callback")


@router.get("/zoom/start")
async def zoom_oauth_start(creator_id: str):
    """Start Zoom OAuth flow"""
    if not ZOOM_CLIENT_ID:
        raise HTTPException(status_code=500, detail="ZOOM_CLIENT_ID not configured")

    state = f"{creator_id}:{secrets.token_urlsafe(16)}"

    params = {
        "client_id": ZOOM_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": ZOOM_REDIRECT_URI,
        "state": state,
    }

    auth_url = f"https://zoom.us/oauth/authorize?{urlencode(params)}"
    return {"auth_url": auth_url, "state": state}


@router.get("/zoom/callback")
async def zoom_oauth_callback(code: str = Query(...), state: str = Query("")):
    """Handle Zoom OAuth callback"""
    import httpx
    import base64
    from datetime import datetime, timezone, timedelta

    if not ZOOM_CLIENT_ID or not ZOOM_CLIENT_SECRET:
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=zoom_not_configured")

    creator_id = state.split(":")[0] if ":" in state else "manel"

    try:
        # Create Basic Auth header
        credentials = base64.b64encode(f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()).decode()

        async with httpx.AsyncClient() as client:
            # Exchange code for access token
            token_response = await client.post(
                "https://zoom.us/oauth/token",
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": ZOOM_REDIRECT_URI,
                }
            )
            token_data = token_response.json()

            if "error" in token_data:
                logger.error(f"Zoom token error: {token_data}")
                return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=zoom_auth_failed")

            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 3600)  # Default 1 hour

            # Calculate expiration time
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            # Get user info
            user_response = await client.get(
                "https://api.zoom.us/v2/users/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_data = user_response.json()
            zoom_email = user_data.get("email", "")

            # Save to database
            await _save_zoom_connection(
                creator_id, access_token, refresh_token, expires_at, zoom_email
            )

            logger.info(f"Zoom connected for {creator_id}, expires at {expires_at}")
            return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&success=zoom")

    except Exception as e:
        logger.error(f"Zoom OAuth error: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=zoom_failed")


# =============================================================================
# GOOGLE (for Google Meet via Calendar API)
# =============================================================================
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", f"{API_URL}/oauth/google/callback").strip()


@router.get("/debug/google-config")
async def debug_google_config():
    """Debug endpoint to verify Google OAuth configuration"""
    client_id = GOOGLE_CLIENT_ID
    client_secret = GOOGLE_CLIENT_SECRET
    redirect_uri = GOOGLE_REDIRECT_URI

    return {
        "client_id_set": bool(client_id),
        "client_id_preview": client_id[:20] + "..." if len(client_id) > 20 else client_id if client_id else "NOT SET",
        "client_id_length": len(client_id),
        "client_secret_set": bool(client_secret),
        "client_secret_length": len(client_secret),
        "client_secret_preview": client_secret[:5] + "..." if len(client_secret) > 5 else "TOO SHORT",
        "redirect_uri": redirect_uri,
        "redirect_uri_matches_api": redirect_uri == f"{API_URL}/oauth/google/callback",
    }


@router.get("/google/start")
async def google_oauth_start(creator_id: str):
    """Start Google OAuth flow for Calendar/Meet access"""
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_ID not configured")

    state = f"{creator_id}:{secrets.token_urlsafe(16)}"

    # Scopes needed for Google Meet links via Calendar API
    scopes = [
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/userinfo.email",
    ]

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "scope": " ".join(scopes),
        "state": state,
        "access_type": "offline",  # Get refresh token
        "prompt": "consent",  # Force consent to always get refresh token
    }

    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return {"auth_url": auth_url, "state": state}


@router.get("/google/callback")
async def google_oauth_callback(code: str = Query(...), state: str = Query("")):
    """Handle Google OAuth callback"""
    import httpx
    from datetime import datetime, timezone, timedelta

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        logger.error(f"Google OAuth not configured: client_id={bool(GOOGLE_CLIENT_ID)}, secret={bool(GOOGLE_CLIENT_SECRET)}")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=google_not_configured")

    creator_id = state.split(":")[0] if ":" in state else "manel"

    # Log what we're sending (without exposing full secret)
    logger.info(f"Google OAuth callback - client_id_len={len(GOOGLE_CLIENT_ID)}, secret_len={len(GOOGLE_CLIENT_SECRET)}, redirect={GOOGLE_REDIRECT_URI}")

    try:
        async with httpx.AsyncClient() as client:
            # Build the request data - use urlencode explicitly for proper form encoding
            token_params = {
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            }

            # Encode as form data explicitly
            encoded_data = urlencode(token_params)
            logger.info(f"Google token request body length: {len(encoded_data)}")

            # Exchange code for access token
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                content=encoded_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )

            logger.info(f"Google token response status: {token_response.status_code}")
            logger.info(f"Google token response body: {token_response.text[:500]}")
            token_data = token_response.json()

            if "error" in token_data:
                logger.error(f"Google token error: {token_data}")
                return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=google_auth_failed")

            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 3600)  # Default 1 hour

            # Calculate expiration time
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            # Get user info
            user_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            user_data = user_response.json()
            google_email = user_data.get("email", "")

            # Save to database
            await _save_google_connection(
                creator_id, access_token, refresh_token, expires_at, google_email
            )

            logger.info(f"Google connected for {creator_id}, expires at {expires_at}")
            return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&success=google")

    except Exception as e:
        logger.error(f"Google OAuth error: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=google_failed")


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
                elif platform == "whatsapp":
                    creator.whatsapp_token = token
                    creator.whatsapp_phone_id = extra_id
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


async def _save_calendly_connection(
    creator_id: str,
    access_token: str,
    refresh_token: str,
    expires_at,
    calendly_uri: str = None
):
    """Save Calendly OAuth connection with refresh token to database"""
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

                creator.calendly_token = access_token
                creator.calendly_refresh_token = refresh_token
                creator.calendly_token_expires_at = expires_at

                session.commit()
                logger.info(f"Saved Calendly connection for {creator_id} with refresh token")
            finally:
                session.close()
    except Exception as e:
        logger.error(f"Error saving Calendly connection: {e}")
        raise


async def refresh_calendly_token(creator_id: str) -> str:
    """
    Refresh Calendly access token using the refresh token.
    Returns the new access token or raises an exception.
    """
    import httpx
    from datetime import datetime, timezone, timedelta

    try:
        from api.database import DATABASE_URL, SessionLocal
        if not DATABASE_URL or not SessionLocal:
            raise Exception("Database not configured")

        session = SessionLocal()
        try:
            from api.models import Creator
            creator = session.query(Creator).filter_by(name=creator_id).first()

            if not creator:
                raise Exception(f"Creator {creator_id} not found")

            if not creator.calendly_refresh_token:
                raise Exception("No refresh token available - user must reconnect")

            # Call Calendly token endpoint
            async with httpx.AsyncClient() as client:
                token_response = await client.post(
                    "https://auth.calendly.com/oauth/token",
                    data={
                        "client_id": CALENDLY_CLIENT_ID,
                        "client_secret": CALENDLY_CLIENT_SECRET,
                        "refresh_token": creator.calendly_refresh_token,
                        "grant_type": "refresh_token",
                    }
                )
                token_data = token_response.json()

                if "error" in token_data:
                    logger.error(f"Calendly refresh error: {token_data}")
                    # Clear tokens so user knows to reconnect
                    creator.calendly_token = None
                    creator.calendly_refresh_token = None
                    creator.calendly_token_expires_at = None
                    session.commit()
                    raise Exception("Refresh token expired - user must reconnect")

                new_access_token = token_data.get("access_token")
                new_refresh_token = token_data.get("refresh_token", creator.calendly_refresh_token)
                expires_in = token_data.get("expires_in", 7200)
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

                # Update tokens in database
                creator.calendly_token = new_access_token
                creator.calendly_refresh_token = new_refresh_token
                creator.calendly_token_expires_at = expires_at
                session.commit()

                logger.info(f"Refreshed Calendly token for {creator_id}, new expiry: {expires_at}")
                return new_access_token

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error refreshing Calendly token: {e}")
        raise


async def get_valid_calendly_token(creator_id: str) -> str:
    """
    Get a valid Calendly access token, refreshing if necessary.
    This should be called before any Calendly API request.
    """
    from datetime import datetime, timezone, timedelta

    try:
        from api.database import DATABASE_URL, SessionLocal
        if not DATABASE_URL or not SessionLocal:
            raise Exception("Database not configured")

        session = SessionLocal()
        try:
            from api.models import Creator
            creator = session.query(Creator).filter_by(name=creator_id).first()

            if not creator:
                raise Exception(f"Creator {creator_id} not found")

            if not creator.calendly_token:
                raise Exception("Calendly not connected")

            # Check if token is expired or about to expire (within 10 minutes)
            if creator.calendly_token_expires_at:
                buffer = timedelta(minutes=10)
                if datetime.now(timezone.utc) + buffer >= creator.calendly_token_expires_at:
                    logger.info(f"Calendly token for {creator_id} expired or expiring soon, refreshing...")
                    session.close()  # Close before async call
                    return await refresh_calendly_token(creator_id)

            return creator.calendly_token

        finally:
            if session:
                session.close()

    except Exception as e:
        logger.error(f"Error getting valid Calendly token: {e}")
        raise


@router.get("/calendly/user-info")
async def get_calendly_user_info(creator_id: str = Query("manel")):
    """Get Calendly user info including scheduling URL"""
    import httpx
    try:
        access_token = await get_valid_calendly_token(creator_id)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.calendly.com/users/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Failed to get Calendly user info")

            data = response.json()
            resource = data.get("resource", {})

            return {
                "status": "ok",
                "creator_id": creator_id,
                "calendly_connected": True,
                "user_uri": resource.get("uri"),
                "scheduling_url": resource.get("scheduling_url"),
                "name": resource.get("name"),
                "email": resource.get("email"),
                "timezone": resource.get("timezone")
            }
    except Exception as e:
        logger.error(f"Error getting Calendly user info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calendly/update-booking-urls/{creator_id}")
async def update_calendly_booking_urls(creator_id: str):
    """Update all Calendly booking links with proper URLs"""
    import httpx
    try:
        access_token = await get_valid_calendly_token(creator_id)

        # Get user's scheduling URL
        async with httpx.AsyncClient() as client:
            user_response = await client.get(
                "https://api.calendly.com/users/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if user_response.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to get Calendly user info")

            user_data = user_response.json()
            resource = user_data.get("resource", {})
            user_uri = resource.get("uri")
            scheduling_url = resource.get("scheduling_url", "")

            if not scheduling_url:
                raise HTTPException(status_code=400, detail="No scheduling URL found in Calendly")

            # Get event types for more specific URLs
            event_types_response = await client.get(
                f"https://api.calendly.com/event_types?user={user_uri}&active=true",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            event_types = {}
            if event_types_response.status_code == 200:
                for et in event_types_response.json().get("collection", []):
                    # Map by duration for matching
                    duration = et.get("duration", 0)
                    event_types[duration] = et.get("scheduling_url", "")

        # Update booking links in database
        from api.database import SessionLocal
        from api.models import BookingLink

        updated_count = 0
        with SessionLocal() as db:
            links = db.query(BookingLink).filter(
                BookingLink.creator_id == creator_id,
                BookingLink.platform == "calendly"
            ).all()

            for link in links:
                if not link.url or link.url == "":
                    # Try to match by duration first
                    new_url = event_types.get(link.duration_minutes, scheduling_url)
                    link.url = new_url
                    updated_count += 1
                    logger.info(f"Updated booking link {link.id} with URL: {new_url}")

            db.commit()

        return {
            "status": "ok",
            "creator_id": creator_id,
            "updated_count": updated_count,
            "scheduling_url": scheduling_url,
            "event_types_found": len(event_types)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating Calendly booking URLs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
                        "message": "Not connected"
                    }

                if not expires_at:
                    return {
                        "connected": True,
                        "status": "unknown_expiry",
                        "has_refresh_token": bool(refresh_token),
                        "message": "Connected (expiry unknown)"
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
                    "message": message
                }

            calendly_status = get_token_status(
                creator.calendly_token,
                creator.calendly_refresh_token,
                creator.calendly_token_expires_at
            )

            zoom_status = get_token_status(
                creator.zoom_access_token,
                creator.zoom_refresh_token,
                creator.zoom_token_expires_at
            )

            google_status = get_token_status(
                creator.google_access_token,
                creator.google_refresh_token,
                creator.google_token_expires_at
            )

            return {
                "status": "ok",
                "creator_id": creator_id,
                "platforms": {
                    "calendly": calendly_status,
                    "zoom": zoom_status,
                    "google": google_status
                },
                "summary": {
                    "total_connected": sum([
                        calendly_status["connected"],
                        zoom_status["connected"],
                        google_status["connected"]
                    ]),
                    "needs_attention": any([
                        calendly_status.get("status") in ["expired", "expiring_soon"],
                        zoom_status.get("status") in ["expired", "expiring_soon"],
                        google_status.get("status") in ["expired", "expiring_soon"]
                    ])
                }
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting OAuth status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh/calendly/{creator_id}")
async def force_refresh_calendly(creator_id: str):
    """Force refresh Calendly token"""
    from datetime import datetime, timezone

    try:
        new_token = await refresh_calendly_token(creator_id)

        # Get updated status
        from api.database import SessionLocal
        from api.models import Creator

        with SessionLocal() as db:
            creator = db.query(Creator).filter_by(name=creator_id).first()
            expires_at = creator.calendly_token_expires_at if creator else None

        return {
            "status": "ok",
            "message": "Calendly token refreshed successfully",
            "token_preview": f"{new_token[:20]}..." if new_token else None,
            "expires_at": expires_at.isoformat() if expires_at else None
        }
    except Exception as e:
        logger.error(f"Error refreshing Calendly token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh/zoom/{creator_id}")
async def force_refresh_zoom(creator_id: str):
    """Force refresh Zoom token"""
    from datetime import datetime, timezone

    try:
        new_token = await refresh_zoom_token(creator_id)

        from api.database import SessionLocal
        from api.models import Creator

        with SessionLocal() as db:
            creator = db.query(Creator).filter_by(name=creator_id).first()
            expires_at = creator.zoom_token_expires_at if creator else None

        return {
            "status": "ok",
            "message": "Zoom token refreshed successfully",
            "token_preview": f"{new_token[:20]}..." if new_token else None,
            "expires_at": expires_at.isoformat() if expires_at else None
        }
    except Exception as e:
        logger.error(f"Error refreshing Zoom token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh/google/{creator_id}")
async def force_refresh_google(creator_id: str):
    """Force refresh Google token"""
    from datetime import datetime, timezone

    try:
        new_token = await refresh_google_token(creator_id)

        from api.database import SessionLocal
        from api.models import Creator

        with SessionLocal() as db:
            creator = db.query(Creator).filter_by(name=creator_id).first()
            expires_at = creator.google_token_expires_at if creator else None

        return {
            "status": "ok",
            "message": "Google token refreshed successfully",
            "token_preview": f"{new_token[:20]}..." if new_token else None,
            "expires_at": expires_at.isoformat() if expires_at else None
        }
    except Exception as e:
        logger.error(f"Error refreshing Google token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _save_zoom_connection(
    creator_id: str,
    access_token: str,
    refresh_token: str,
    expires_at,
    zoom_email: str = None
):
    """Save Zoom OAuth connection with refresh token to database"""
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

                creator.zoom_access_token = access_token
                creator.zoom_refresh_token = refresh_token
                creator.zoom_token_expires_at = expires_at

                session.commit()
                logger.info(f"Saved Zoom connection for {creator_id} ({zoom_email})")
            finally:
                session.close()
    except Exception as e:
        logger.error(f"Error saving Zoom connection: {e}")
        raise


async def _save_google_connection(
    creator_id: str,
    access_token: str,
    refresh_token: str,
    expires_at,
    google_email: str = None
):
    """Save Google OAuth connection with refresh token to database"""
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

                creator.google_access_token = access_token
                creator.google_refresh_token = refresh_token
                creator.google_token_expires_at = expires_at

                session.commit()
                logger.info(f"Saved Google connection for {creator_id} ({google_email})")
            finally:
                session.close()
    except Exception as e:
        logger.error(f"Error saving Google connection: {e}")
        raise


async def refresh_zoom_token(creator_id: str) -> str:
    """
    Refresh Zoom access token using the refresh token.
    Returns the new access token or raises an exception.
    """
    import httpx
    import base64
    from datetime import datetime, timezone, timedelta

    try:
        from api.database import DATABASE_URL, SessionLocal
        if not DATABASE_URL or not SessionLocal:
            raise Exception("Database not configured")

        session = SessionLocal()
        try:
            from api.models import Creator
            creator = session.query(Creator).filter_by(name=creator_id).first()

            if not creator:
                raise Exception(f"Creator {creator_id} not found")

            if not creator.zoom_refresh_token:
                raise Exception("No Zoom refresh token available - user must reconnect")

            # Create Basic Auth header
            credentials = base64.b64encode(f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()).decode()

            # Call Zoom token endpoint
            async with httpx.AsyncClient() as client:
                token_response = await client.post(
                    "https://zoom.us/oauth/token",
                    headers={
                        "Authorization": f"Basic {credentials}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": creator.zoom_refresh_token,
                    }
                )
                token_data = token_response.json()

                if "error" in token_data:
                    logger.error(f"Zoom refresh error: {token_data}")
                    # Clear tokens so user knows to reconnect
                    creator.zoom_access_token = None
                    creator.zoom_refresh_token = None
                    creator.zoom_token_expires_at = None
                    session.commit()
                    raise Exception("Zoom refresh token expired - user must reconnect")

                new_access_token = token_data.get("access_token")
                new_refresh_token = token_data.get("refresh_token", creator.zoom_refresh_token)
                expires_in = token_data.get("expires_in", 3600)
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

                # Update tokens in database
                creator.zoom_access_token = new_access_token
                creator.zoom_refresh_token = new_refresh_token
                creator.zoom_token_expires_at = expires_at
                session.commit()

                logger.info(f"Refreshed Zoom token for {creator_id}, new expiry: {expires_at}")
                return new_access_token

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error refreshing Zoom token: {e}")
        raise


async def get_valid_zoom_token(creator_id: str) -> str:
    """
    Get a valid Zoom access token, refreshing if necessary.
    This should be called before any Zoom API request.
    """
    from datetime import datetime, timezone, timedelta

    try:
        from api.database import DATABASE_URL, SessionLocal
        if not DATABASE_URL or not SessionLocal:
            raise Exception("Database not configured")

        session = SessionLocal()
        try:
            from api.models import Creator
            creator = session.query(Creator).filter_by(name=creator_id).first()

            if not creator:
                raise Exception(f"Creator {creator_id} not found")

            if not creator.zoom_access_token:
                raise Exception("Zoom not connected")

            # Check if token is expired or about to expire (within 10 minutes)
            if creator.zoom_token_expires_at:
                buffer = timedelta(minutes=10)
                if datetime.now(timezone.utc) + buffer >= creator.zoom_token_expires_at:
                    logger.info(f"Zoom token for {creator_id} expired or expiring soon, refreshing...")
                    session.close()  # Close before async call
                    return await refresh_zoom_token(creator_id)

            return creator.zoom_access_token

        finally:
            if session:
                session.close()

    except Exception as e:
        logger.error(f"Error getting valid Zoom token: {e}")
        raise


async def refresh_google_token(creator_id: str) -> str:
    """
    Refresh Google access token using the refresh token.
    Returns the new access token or raises an exception.
    """
    import httpx
    from datetime import datetime, timezone, timedelta

    try:
        from api.database import DATABASE_URL, SessionLocal
        if not DATABASE_URL or not SessionLocal:
            raise Exception("Database not configured")

        session = SessionLocal()
        try:
            from api.models import Creator
            creator = session.query(Creator).filter_by(name=creator_id).first()

            if not creator:
                raise Exception(f"Creator {creator_id} not found")

            if not creator.google_refresh_token:
                raise Exception("No Google refresh token available - user must reconnect")

            # Call Google token endpoint
            async with httpx.AsyncClient() as client:
                token_response = await client.post(
                    "https://oauth2.googleapis.com/token",
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "client_id": GOOGLE_CLIENT_ID,
                        "client_secret": GOOGLE_CLIENT_SECRET,
                        "refresh_token": creator.google_refresh_token,
                        "grant_type": "refresh_token",
                    }
                )
                token_data = token_response.json()

                if "error" in token_data:
                    logger.error(f"Google refresh error: {token_data}")
                    # Clear tokens so user knows to reconnect
                    creator.google_access_token = None
                    creator.google_refresh_token = None
                    creator.google_token_expires_at = None
                    session.commit()
                    raise Exception("Google refresh token expired - user must reconnect")

                new_access_token = token_data.get("access_token")
                # Google doesn't always return a new refresh token
                expires_in = token_data.get("expires_in", 3600)
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

                # Update tokens in database
                creator.google_access_token = new_access_token
                creator.google_token_expires_at = expires_at
                session.commit()

                logger.info(f"Refreshed Google token for {creator_id}, new expiry: {expires_at}")
                return new_access_token

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error refreshing Google token: {e}")
        raise


async def get_valid_google_token(creator_id: str) -> str:
    """
    Get a valid Google access token, refreshing if necessary.
    This should be called before any Google API request.
    """
    from datetime import datetime, timezone, timedelta

    try:
        from api.database import DATABASE_URL, SessionLocal
        if not DATABASE_URL or not SessionLocal:
            raise Exception("Database not configured")

        session = SessionLocal()
        try:
            from api.models import Creator
            creator = session.query(Creator).filter_by(name=creator_id).first()

            if not creator:
                raise Exception(f"Creator {creator_id} not found")

            if not creator.google_access_token:
                raise Exception("Google not connected")

            # Check if token is expired or about to expire (within 10 minutes)
            if creator.google_token_expires_at:
                buffer = timedelta(minutes=10)
                if datetime.now(timezone.utc) + buffer >= creator.google_token_expires_at:
                    logger.info(f"Google token for {creator_id} expired or expiring soon, refreshing...")
                    session.close()  # Close before async call
                    return await refresh_google_token(creator_id)

            return creator.google_access_token

        finally:
            if session:
                session.close()

    except Exception as e:
        logger.error(f"Error getting valid Google token: {e}")
        raise
