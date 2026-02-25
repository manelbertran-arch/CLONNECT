"""WhatsApp Business OAuth endpoints."""

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

WHATSAPP_REDIRECT_URI = os.getenv("WHATSAPP_REDIRECT_URI", f"{API_URL}/oauth/whatsapp/callback")

# Facebook App credentials (for Facebook Login API - legacy)
META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")


@router.get("/whatsapp/start")
async def whatsapp_oauth_start(creator_id: str):
    """
    Start WhatsApp Business OAuth flow.

    WhatsApp Business uses Facebook Login with specific scopes for
    WhatsApp Business Management API access.
    """
    whatsapp_app_id = os.getenv("WHATSAPP_META_APP_ID", META_APP_ID)
    if not whatsapp_app_id:
        raise HTTPException(status_code=503, detail="WhatsApp OAuth is not configured on this server")

    # Store state for CSRF protection
    state = f"{creator_id}:{secrets.token_urlsafe(16)}"

    # WhatsApp Business scopes - requires approved Meta Business app
    # business_management needed for me/businesses API to discover WABA + phone_number_id
    # Reference: https://developers.facebook.com/docs/whatsapp/embedded-signup/
    params = {
        "client_id": whatsapp_app_id,
        "redirect_uri": WHATSAPP_REDIRECT_URI,
        "scope": "business_management,whatsapp_business_management,whatsapp_business_messaging",
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
    error_message: str = Query(None),
):
    """Handle WhatsApp Business OAuth callback"""
    import httpx

    # Handle OAuth errors
    if error_code or error_message:
        logger.error(f"WhatsApp OAuth error: {error_code} - {error_message}")
        return RedirectResponse(
            f"{FRONTEND_URL}/settings?tab=connections&error=whatsapp_scope_error"
        )

    if not code:
        logger.error("WhatsApp OAuth: No code received")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=whatsapp_no_code")

    whatsapp_app_id = os.getenv("WHATSAPP_META_APP_ID", META_APP_ID)
    whatsapp_app_secret = os.getenv("WHATSAPP_APP_SECRET", META_APP_SECRET)
    if not whatsapp_app_id or not whatsapp_app_secret:
        return RedirectResponse(
            f"{FRONTEND_URL}/settings?tab=connections&error=whatsapp_not_configured"
        )

    # Extract creator_id from state
    creator_id = state.split(":")[0] if ":" in state else "manel"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Exchange code for access token
            token_response = await client.get(
                "https://graph.facebook.com/v21.0/oauth/access_token",
                params={
                    "client_id": whatsapp_app_id,
                    "client_secret": whatsapp_app_secret,
                    "redirect_uri": WHATSAPP_REDIRECT_URI,
                    "code": code,
                },
            )
            token_data = token_response.json()

            if "error" in token_data:
                logger.error(f"WhatsApp token error: {token_data}")
                return RedirectResponse(
                    f"{FRONTEND_URL}/settings?tab=connections&error=whatsapp_auth_failed"
                )

            access_token = token_data.get("access_token")

            # Exchange short-lived token (1h) for long-lived token (60 days)
            try:
                ll_response = await client.get(
                    "https://graph.facebook.com/v21.0/oauth/access_token",
                    params={
                        "grant_type": "fb_exchange_token",
                        "client_id": whatsapp_app_id,
                        "client_secret": whatsapp_app_secret,
                        "fb_exchange_token": access_token,
                    },
                )
                ll_data = ll_response.json()
                if ll_data.get("access_token"):
                    access_token = ll_data["access_token"]
                    logger.info(f"WhatsApp: exchanged for long-lived token ({len(access_token)} chars)")
                else:
                    logger.warning(f"WhatsApp long-lived token exchange failed: {ll_data}")
            except Exception as e:
                logger.warning(f"WhatsApp long-lived token exchange error: {e}")

            # Discover WhatsApp Business Account and Phone Number ID
            phone_number_id = None
            waba_id = None

            # Strategy 1: debug_token → granular_scopes → WABA ID → phone_numbers
            # Uses app token (app_id|app_secret) — works without business_management scope
            try:
                app_token = f"{whatsapp_app_id}|{whatsapp_app_secret}"
                debug_response = await client.get(
                    "https://graph.facebook.com/v21.0/debug_token",
                    params={"input_token": access_token, "access_token": app_token},
                )
                debug_data = debug_response.json()

                if debug_data.get("data", {}).get("granular_scopes"):
                    for scope in debug_data["data"]["granular_scopes"]:
                        if scope.get("scope") == "whatsapp_business_management" and scope.get("target_ids"):
                            waba_id = scope["target_ids"][0]
                            logger.info(f"Found WABA ID via debug_token: {waba_id}")
                            break

                if waba_id:
                    phones_response = await client.get(
                        f"https://graph.facebook.com/v21.0/{waba_id}/phone_numbers",
                        params={"access_token": access_token},
                    )
                    phones_data = phones_response.json()

                    if phones_data.get("data"):
                        phone_number_id = phones_data["data"][0]["id"]
                        logger.info(f"Found WhatsApp phone number ID: {phone_number_id}")
                    elif phones_data.get("error"):
                        logger.warning(f"WhatsApp phone_numbers failed: {phones_data['error']}")
                else:
                    logger.warning(f"WhatsApp: no WABA ID in debug_token granular_scopes: {debug_data}")
            except Exception as e:
                logger.warning(f"WhatsApp debug_token discovery failed: {e}")

            # Strategy 2 (fallback): me/businesses → owned_whatsapp_business_accounts
            # Requires business_management scope (may not be approved)
            if not phone_number_id:
                try:
                    waba_response = await client.get(
                        "https://graph.facebook.com/v21.0/me/businesses",
                        params={"access_token": access_token},
                    )
                    waba_data = waba_response.json()

                    if waba_data.get("data"):
                        business_id = waba_data["data"][0]["id"]
                        owned_wabas = await client.get(
                            f"https://graph.facebook.com/v21.0/{business_id}/owned_whatsapp_business_accounts",
                            params={"access_token": access_token},
                        )
                        owned_data = owned_wabas.json()

                        if owned_data.get("data"):
                            waba_id = owned_data["data"][0]["id"]
                            phones_response = await client.get(
                                f"https://graph.facebook.com/v21.0/{waba_id}/phone_numbers",
                                params={"access_token": access_token},
                            )
                            phones_data = phones_response.json()
                            if phones_data.get("data"):
                                phone_number_id = phones_data["data"][0]["id"]
                                logger.info(f"Found phone number ID via me/businesses: {phone_number_id}")
                except Exception as e:
                    logger.warning(f"WhatsApp me/businesses fallback failed: {e}")

            # Save token (even without phone_number_id — user can add it manually)
            await _save_connection(creator_id, "whatsapp", access_token, phone_number_id)

            if phone_number_id:
                return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&success=whatsapp")
            else:
                # Token saved but phone_number_id missing — tell user to add it manually
                logger.warning(
                    f"WhatsApp OAuth for {creator_id}: token saved but phone_number_id not found. "
                    "User must enter phone_number_id manually in Conexiones settings."
                )
                return RedirectResponse(
                    f"{FRONTEND_URL}/settings?tab=connections&error=whatsapp_missing_phone_id"
                )

    except Exception as e:
        logger.error(f"WhatsApp OAuth error: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=whatsapp_failed")


@router.get("/whatsapp/config")
async def whatsapp_get_config():
    """
    Return WhatsApp Embedded Signup configuration for the frontend.

    Returns app_id and config_id needed to initialize FB.login().
    """
    app_id = os.getenv("WHATSAPP_META_APP_ID", META_APP_ID)
    config_id = os.getenv("WHATSAPP_CONFIG_ID", "")
    return {"app_id": app_id or "", "config_id": config_id}


@router.post("/whatsapp/embedded-signup")
async def whatsapp_embedded_signup(payload: dict):
    """
    Handle WhatsApp Embedded Signup exchange.

    Receives code (+ optional waba_id, phone_number_id) from frontend
    after FB.login() popup completes.

    Flow:
      1. Exchange code -> access_token (short -> long-lived)
      2. If waba_id/phone_number_id not provided, discover via debug_token
      3. Register phone number on Cloud API
      4. Subscribe WABA to webhooks
      5. Save token + phone_number_id to Creator model
    """
    import httpx

    code = payload.get("code")
    waba_id = payload.get("waba_id", "")
    phone_number_id = payload.get("phone_number_id", "")
    creator_id = payload.get("creator_id", "manel")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    whatsapp_app_id = os.getenv("WHATSAPP_META_APP_ID", META_APP_ID)
    whatsapp_app_secret = os.getenv("WHATSAPP_APP_SECRET", META_APP_SECRET)
    if not whatsapp_app_id or not whatsapp_app_secret:
        raise HTTPException(status_code=503, detail="WhatsApp OAuth is not configured on this server")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Exchange code for access token
            token_response = await client.get(
                "https://graph.facebook.com/v21.0/oauth/access_token",
                params={
                    "client_id": whatsapp_app_id,
                    "client_secret": whatsapp_app_secret,
                    "code": code,
                },
            )
            token_data = token_response.json()

            if "error" in token_data:
                logger.error(f"WhatsApp Embedded Signup token error: {token_data}")
                raise HTTPException(status_code=400, detail=f"Token exchange failed: {token_data['error'].get('message', 'Unknown error')}")

            access_token = token_data.get("access_token")

            # Exchange for long-lived token (60 days)
            try:
                ll_response = await client.get(
                    "https://graph.facebook.com/v21.0/oauth/access_token",
                    params={
                        "grant_type": "fb_exchange_token",
                        "client_id": whatsapp_app_id,
                        "client_secret": whatsapp_app_secret,
                        "fb_exchange_token": access_token,
                    },
                )
                ll_data = ll_response.json()
                if ll_data.get("access_token"):
                    access_token = ll_data["access_token"]
                    logger.info(f"WhatsApp ES: long-lived token obtained ({len(access_token)} chars)")
            except Exception as e:
                logger.warning(f"WhatsApp ES: long-lived token exchange failed: {e}")

            # Step 2: Discover WABA + phone_number_id if not provided
            if not waba_id or not phone_number_id:
                logger.info("WhatsApp ES: waba_id/phone_number_id not in payload, discovering via debug_token...")

                try:
                    app_token = f"{whatsapp_app_id}|{whatsapp_app_secret}"
                    debug_response = await client.get(
                        "https://graph.facebook.com/v21.0/debug_token",
                        params={"input_token": access_token, "access_token": app_token},
                    )
                    debug_data = debug_response.json()

                    if debug_data.get("data", {}).get("granular_scopes"):
                        for scope in debug_data["data"]["granular_scopes"]:
                            if scope.get("scope") == "whatsapp_business_management" and scope.get("target_ids"):
                                waba_id = scope["target_ids"][0]
                                logger.info(f"WhatsApp ES: found WABA ID via debug_token: {waba_id}")
                                break

                    if waba_id and not phone_number_id:
                        phones_response = await client.get(
                            f"https://graph.facebook.com/v21.0/{waba_id}/phone_numbers",
                            params={"access_token": access_token},
                        )
                        phones_data = phones_response.json()
                        if phones_data.get("data"):
                            phone_number_id = phones_data["data"][0]["id"]
                            logger.info(f"WhatsApp ES: found phone_number_id: {phone_number_id}")
                except Exception as e:
                    logger.warning(f"WhatsApp ES: discovery failed: {e}")

            # Step 3: Register phone number (if we have it)
            if phone_number_id:
                try:
                    from core.whatsapp import register_phone_number
                    reg_result = await register_phone_number(phone_number_id, access_token)
                    if "error" in reg_result:
                        logger.warning(f"WhatsApp ES: phone registration returned error (may already be registered): {reg_result['error']}")
                except Exception as e:
                    logger.warning(f"WhatsApp ES: phone registration failed: {e}")

            # Step 4: Subscribe WABA to webhooks (if we have it)
            if waba_id:
                try:
                    from core.whatsapp import subscribe_waba_webhooks
                    sub_result = await subscribe_waba_webhooks(waba_id, access_token)
                    if "error" in sub_result:
                        logger.warning(f"WhatsApp ES: webhook subscription error: {sub_result['error']}")
                except Exception as e:
                    logger.warning(f"WhatsApp ES: webhook subscription failed: {e}")

            # Step 5: Save to database
            await _save_connection(creator_id, "whatsapp", access_token, phone_number_id)

            logger.info(
                f"WhatsApp Embedded Signup complete for {creator_id}: "
                f"waba_id={waba_id}, phone_number_id={phone_number_id}"
            )

            return {
                "success": True,
                "phone_number_id": phone_number_id or "",
                "waba_id": waba_id or "",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WhatsApp Embedded Signup error: {e}")
        raise HTTPException(status_code=502, detail="WhatsApp signup failed due to an unexpected error")
