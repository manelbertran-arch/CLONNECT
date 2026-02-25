"""Stripe Connect OAuth endpoints."""

import logging
import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from .status import _save_connection

logger = logging.getLogger(__name__)

router = APIRouter(tags=["oauth"])

# Frontend URL for redirects after OAuth
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://www.clonnectapp.com")
# Backend API URL for OAuth callbacks
API_URL = os.getenv("API_URL", "https://api.clonnectapp.com")


@router.get("/stripe/start")
async def stripe_oauth_start(creator_id: str):
    """Start Stripe Connect onboarding using Account Links API"""
    import httpx

    stripe_secret_key = os.getenv("STRIPE_SECRET_KEY", "").strip()

    if not stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured on this server")

    logger.info(f"Starting Stripe Connect for creator: {creator_id}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Create a Stripe Express connected account
            account_response = await client.post(
                "https://api.stripe.com/v1/accounts",
                headers={"Authorization": f"Bearer {stripe_secret_key}"},
                data={
                    "type": "express",
                    "metadata[creator_id]": creator_id,
                },
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
                },
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
        raise HTTPException(status_code=502, detail="Failed to connect to Stripe")


@router.get("/stripe/callback")
async def stripe_oauth_callback(creator_id: str = Query("manel"), account_id: str = Query(...)):
    """Handle Stripe Connect onboarding completion"""
    import httpx

    stripe_secret_key = os.getenv("STRIPE_SECRET_KEY", "").strip()

    if not stripe_secret_key:
        return RedirectResponse(
            f"{FRONTEND_URL}/settings?tab=connections&error=stripe_not_configured"
        )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Verify the account status
            account_response = await client.get(
                f"https://api.stripe.com/v1/accounts/{account_id}",
                headers={"Authorization": f"Bearer {stripe_secret_key}"},
            )
            account_data = account_response.json()

            if "error" in account_data:
                logger.error(f"Stripe account fetch error: {account_data}")
                return RedirectResponse(
                    f"{FRONTEND_URL}/settings?tab=connections&error=stripe_auth_failed"
                )

            # Check if onboarding is complete
            charges_enabled = account_data.get("charges_enabled", False)
            payouts_enabled = account_data.get("payouts_enabled", False)

            logger.info(
                f"Stripe account {account_id} - charges: {charges_enabled}, payouts: {payouts_enabled}"
            )

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
        return RedirectResponse(
            f"{FRONTEND_URL}/settings?tab=connections&error=stripe_not_configured"
        )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Create a new Account Link
            link_response = await client.post(
                "https://api.stripe.com/v1/account_links",
                headers={"Authorization": f"Bearer {stripe_secret_key}"},
                data={
                    "account": account_id,
                    "refresh_url": f"{API_URL}/oauth/stripe/refresh?creator_id={creator_id}&account_id={account_id}",
                    "return_url": f"{API_URL}/oauth/stripe/callback?creator_id={creator_id}&account_id={account_id}",
                    "type": "account_onboarding",
                },
            )
            link_data = link_response.json()

            if "error" in link_data:
                logger.error(f"Stripe refresh link error: {link_data}")
                return RedirectResponse(
                    f"{FRONTEND_URL}/settings?tab=connections&error=stripe_refresh_failed"
                )

            return RedirectResponse(link_data["url"])

    except Exception as e:
        logger.error(f"Stripe refresh error: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=stripe_failed")
