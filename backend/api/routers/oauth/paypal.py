"""PayPal OAuth endpoints."""

import logging
import os
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from .status import _save_connection

logger = logging.getLogger(__name__)

router = APIRouter(tags=["oauth"])

# Frontend URL for redirects after OAuth
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://www.clonnectapp.com")
# Backend API URL for OAuth callbacks
API_URL = os.getenv("API_URL", "https://api.clonnectapp.com")

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_REDIRECT_URI = os.getenv("PAYPAL_REDIRECT_URI", f"{API_URL}/oauth/paypal/callback")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")  # sandbox or live


@router.get("/paypal/start")
async def paypal_oauth_start(creator_id: str):
    """Start PayPal OAuth flow"""
    if not PAYPAL_CLIENT_ID:
        raise HTTPException(status_code=503, detail="PayPal OAuth is not configured on this server")

    state = f"{creator_id}:{secrets.token_urlsafe(16)}"

    base_url = (
        "https://www.sandbox.paypal.com" if PAYPAL_MODE == "sandbox" else "https://www.paypal.com"
    )

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
    import base64

    import httpx

    if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
        raise HTTPException(status_code=503, detail="PayPal OAuth is not configured on this server")

    creator_id = state.split(":")[0] if ":" in state else "manel"

    try:
        base_url = (
            "https://api-m.sandbox.paypal.com"
            if PAYPAL_MODE == "sandbox"
            else "https://api-m.paypal.com"
        )

        # Create Basic Auth header
        credentials = base64.b64encode(
            f"{PAYPAL_CLIENT_ID}:{PAYPAL_CLIENT_SECRET}".encode()
        ).decode()

        async with httpx.AsyncClient(timeout=30.0) as client:
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
                },
            )
            token_data = token_response.json()

            if "error" in token_data:
                logger.error(f"PayPal token error: {token_data}")
                return RedirectResponse(
                    f"{FRONTEND_URL}/settings?tab=connections&error=paypal_auth_failed"
                )

            access_token = token_data.get("access_token")

            # Get user info
            user_response = await client.get(
                f"{base_url}/v1/identity/oauth2/userinfo?schema=paypalv1.1",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_data = user_response.json()
            paypal_email = user_data.get("emails", [{}])[0].get("value", "")

            # Save to database
            await _save_connection(creator_id, "paypal", access_token, paypal_email)

            return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&success=paypal")

    except Exception as e:
        logger.error(f"PayPal OAuth error: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=paypal_failed")
