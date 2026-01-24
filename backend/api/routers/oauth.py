"""
OAuth endpoints for platform integrations
Click-and-play authentication for beta testers
"""
import os
import logging
import secrets
from urllib.parse import urlencode
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)


# =============================================================================
# AUTO-ONBOARDING FUNCTION
# =============================================================================

async def _auto_onboard_after_instagram_oauth(
    creator_id: str,
    access_token: str,
    instagram_user_id: str,
    page_id: str = ""
):
    """
    Ejecuta onboarding completo automáticamente después de OAuth.

    Pipeline:
    1. Scrape Instagram posts (últimos 50)
    2. Generar ToneProfile (Magic Slice)
    3. Indexar contenido en RAG
    4. Activar bot automáticamente
    5. Cargar historial de DMs existentes y categorizar leads
    6. Scrapear website de la bio e indexar en RAG
    """
    logger.info(f"[AutoOnboard] Starting automatic onboarding for {creator_id}...")

    try:
        from ingestion import MetaGraphAPIScraper
        from core.onboarding_service import get_onboarding_service, OnboardingRequest
        from core.dm_history_service import get_dm_history_service
        from api.database import SessionLocal
        from api.models import Creator

        # Get page_id from DB if not provided
        if not page_id:
            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if creator:
                    page_id = creator.instagram_page_id or ""
            finally:
                session.close()

        # STEP 1: Scrape Instagram posts
        logger.info(f"[AutoOnboard] Scraping Instagram posts for {creator_id}...")
        scraper = MetaGraphAPIScraper(
            access_token=access_token,
            instagram_business_id=instagram_user_id
        )

        posts = await scraper.get_posts(limit=50)
        logger.info(f"[AutoOnboard] Scraped {len(posts)} posts from Instagram")

        if not posts:
            logger.warning(f"[AutoOnboard] No posts found for {creator_id}, skipping tone analysis")
            # Still activate bot with default config
            _activate_bot_default(creator_id)
        else:
            # Convert InstagramPost objects to dicts for onboarding service
            posts_data = []
            for p in posts:
                if p.caption and len(p.caption.strip()) > 10:
                    posts_data.append({
                        "post_id": p.post_id,
                        "caption": p.caption,
                        "post_type": p.post_type,
                        "timestamp": p.timestamp.isoformat() if p.timestamp else None,
                        "permalink": p.permalink,
                        "media_url": p.media_url,
                        "likes_count": p.likes_count,
                        "comments_count": p.comments_count
                    })

            # STEP 2 & 3: Run onboarding service (tone analysis + RAG indexing)
            logger.info(f"[AutoOnboard] Running onboarding pipeline with {len(posts_data)} posts...")
            service = get_onboarding_service()
            request = OnboardingRequest(
                creator_id=creator_id,
                manual_posts=posts_data,
                scraping_method="manual"  # Already scraped
            )
            result = await service.onboard_creator(request)

            logger.info(f"[AutoOnboard] Onboarding result: posts={result.posts_processed}, tone={result.tone_profile_generated}, indexed={result.content_indexed}")

        # STEP 4: Activate bot
        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if creator:
                creator.bot_active = True
                creator.onboarding_completed = True
                creator.copilot_mode = True  # Enable copilot mode by default
                session.commit()
                logger.info(f"[AutoOnboard] ✅ Bot activated for {creator_id}")
        finally:
            session.close()

        # STEP 4b: Activate default nurturing sequences
        try:
            from core.nurturing import activate_default_sequences
            nurturing_result = activate_default_sequences(creator_id)
            logger.info(f"[AutoOnboard] ✅ Nurturing sequences activated: {list(nurturing_result.keys())}")
        except Exception as nurturing_error:
            logger.warning(f"[AutoOnboard] Could not activate nurturing: {nurturing_error}")

        # STEP 5: Load DM history
        if page_id:
            logger.info(f"[AutoOnboard] Loading DM history for {creator_id}...")
            try:
                dm_service = get_dm_history_service()
                dm_stats = await dm_service.load_dm_history(
                    creator_id=creator_id,
                    access_token=access_token,
                    page_id=page_id,
                    ig_user_id=instagram_user_id,
                    limit=30
                )
                logger.info(f"[AutoOnboard] DM history loaded: {dm_stats}")
            except Exception as dm_error:
                logger.warning(f"[AutoOnboard] Could not load DM history: {dm_error}")
        else:
            logger.warning(f"[AutoOnboard] No page_id, skipping DM history load")

        # STEP 6: Scrape website from Instagram bio (if available)
        try:
            logger.info(f"[AutoOnboard] Checking for website in Instagram bio...")
            import httpx
            from core.website_scraper import extract_url_from_text, scrape_and_index_website

            # Get Instagram profile bio
            async with httpx.AsyncClient(timeout=10.0) as client:
                profile_response = await client.get(
                    f"https://graph.facebook.com/v21.0/{instagram_user_id}",
                    params={
                        "fields": "biography,website",
                        "access_token": access_token
                    }
                )
                if profile_response.status_code == 200:
                    profile_data = profile_response.json()
                    bio = profile_data.get("biography", "")
                    website = profile_data.get("website", "")

                    # Try to extract URL from bio or use website field
                    url_to_scrape = website or extract_url_from_text(bio)

                    if url_to_scrape:
                        logger.info(f"[AutoOnboard] Found website: {url_to_scrape}")
                        web_stats = await scrape_and_index_website(
                            creator_id=creator_id,
                            url=url_to_scrape,
                            max_pages=5
                        )
                        logger.info(f"[AutoOnboard] Website indexed: {web_stats['pages_scraped']} pages, {web_stats['chunks_indexed']} chunks")
                    else:
                        logger.info(f"[AutoOnboard] No website found in bio")
        except Exception as web_error:
            logger.warning(f"[AutoOnboard] Could not scrape website: {web_error}")

        logger.info(f"[AutoOnboard] ✅ Complete! {creator_id} is ready to receive DMs")

    except Exception as e:
        logger.error(f"[AutoOnboard] ❌ Error during auto-onboarding for {creator_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Don't raise - this is a background task


def _activate_bot_default(creator_id: str):
    """Activate bot with default configuration when no posts available."""
    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if creator:
                creator.bot_active = True
                session.commit()
                logger.info(f"[AutoOnboard] Bot activated with defaults for {creator_id}")
        finally:
            session.close()
    except Exception as e:
        logger.error(f"[AutoOnboard] Error activating bot: {e}")


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
    """
    Start Instagram OAuth flow with full messaging permissions.

    Required scopes for Instagram DMs:
    - instagram_manage_messages: Send and receive DMs
    - instagram_basic: Basic Instagram info
    - pages_messaging: Page messaging
    - pages_show_list: List pages
    - pages_read_engagement: Read engagement data
    """
    if not META_APP_ID:
        raise HTTPException(status_code=500, detail="META_APP_ID not configured")

    # Store state for CSRF protection
    state = f"{creator_id}:{secrets.token_urlsafe(16)}"

    # Full scopes for Instagram DM automation
    # Note: These must be approved in Meta App Review first
    scopes = [
        "instagram_manage_messages",  # Required for DMs
        "instagram_basic",            # Basic Instagram account info
        "pages_messaging",            # Page messaging capability
        "pages_show_list",            # List connected pages
        "pages_read_engagement",      # Read engagement data
        "pages_manage_metadata",      # Manage page metadata
    ]

    params = {
        "client_id": META_APP_ID,
        "redirect_uri": META_REDIRECT_URI,
        "scope": ",".join(scopes),
        "response_type": "code",
        "state": state,
    }

    auth_url = f"https://www.facebook.com/v21.0/dialog/oauth?{urlencode(params)}"

    logger.info(f"Instagram OAuth start for {creator_id} with scopes: {scopes}")

    return {
        "auth_url": auth_url,
        "state": state,
        "scopes_requested": scopes,
        "note": "User must have Instagram Business/Creator account connected to a Facebook Page"
    }


@router.get("/instagram/callback")
async def instagram_oauth_callback(
    background_tasks: BackgroundTasks,
    code: str = Query(None),
    state: str = Query(""),
    error_code: str = Query(None),
    error_message: str = Query(None)
):
    """
    Handle Instagram OAuth callback.

    This exchanges the code for a token, finds the Instagram Business account,
    and stores everything needed for DM automation.
    """
    import httpx

    # Handle OAuth errors (like invalid scopes)
    if error_code or error_message:
        logger.error(f"Instagram OAuth error: {error_code} - {error_message}")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=instagram_scope_error&message={error_message}")

    if not code:
        logger.error("Instagram OAuth: No code received")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=instagram_no_code")

    if not META_APP_ID or not META_APP_SECRET:
        logger.error("Instagram OAuth: META_APP_SECRET not configured")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=instagram_not_configured")

    # Extract creator_id from state
    creator_id = state.split(":")[0] if ":" in state else "manel"
    logger.info(f"Instagram OAuth callback for creator: {creator_id}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Exchange code for short-lived access token
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

            short_lived_token = token_data.get("access_token")
            logger.info("Got short-lived token from Meta")

            # Step 2: Exchange for long-lived token (60 days)
            long_token_response = await client.get(
                "https://graph.facebook.com/v21.0/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": META_APP_ID,
                    "client_secret": META_APP_SECRET,
                    "fb_exchange_token": short_lived_token,
                }
            )
            long_token_data = long_token_response.json()

            if "error" in long_token_data:
                logger.warning(f"Could not get long-lived token: {long_token_data}, using short-lived")
                access_token = short_lived_token
            else:
                access_token = long_token_data.get("access_token", short_lived_token)
                logger.info("Got long-lived token (60 days)")

            # Step 3: Get Facebook Pages connected to this user
            # IMPORTANT: Explicitly request access_token field to get Page Access Token
            pages_response = await client.get(
                "https://graph.facebook.com/v21.0/me/accounts",
                params={
                    "access_token": access_token,
                    "fields": "id,name,access_token"  # Explicitly request access_token!
                }
            )
            pages_data = pages_response.json()
            logger.info(f"Pages response: {len(pages_data.get('data', []))} pages found")

            page_id = None
            page_access_token = None
            instagram_user_id = None

            if pages_data.get("data"):
                # Get the first page (most users have one)
                page = pages_data["data"][0]
                page_id = page["id"]
                page_access_token = page.get("access_token")

                # Log token type for debugging
                if page_access_token:
                    token_prefix = page_access_token[:10] if page_access_token else "NONE"
                    logger.info(f"Got Page Access Token: {token_prefix}... (type: {'PAGE' if page_access_token.startswith('EAA') else 'OTHER'})")
                else:
                    logger.warning(f"No access_token in page response! Page data: {page}")
                    page_access_token = access_token  # Fallback

                logger.info(f"Found Facebook Page: {page_id} ({page.get('name', 'unknown')})")

                # Step 4: Get Instagram Business Account linked to this page
                ig_response = await client.get(
                    f"https://graph.facebook.com/v21.0/{page_id}",
                    params={
                        "fields": "instagram_business_account,name",
                        "access_token": page_access_token
                    }
                )
                ig_data = ig_response.json()

                if ig_data.get("instagram_business_account"):
                    instagram_user_id = ig_data["instagram_business_account"]["id"]
                    logger.info(f"Found Instagram Business Account: {instagram_user_id}")

                    # Step 5: Get Instagram username for confirmation
                    ig_info_response = await client.get(
                        f"https://graph.facebook.com/v21.0/{instagram_user_id}",
                        params={
                            "fields": "username,name,profile_picture_url",
                            "access_token": page_access_token
                        }
                    )
                    ig_info = ig_info_response.json()
                    ig_username = ig_info.get("username", "unknown")
                    logger.info(f"Instagram username: @{ig_username}")
                else:
                    logger.warning("No Instagram Business Account linked to this Facebook Page")
            else:
                logger.warning("No Facebook Pages found for this user")

            # Step 6: Save to database
            final_access_token = page_access_token or access_token

            # Log what we're saving for debugging
            token_type = "PAGE (EAA)" if final_access_token.startswith("EAA") else "INSTAGRAM (IGAAT)" if final_access_token.startswith("IGAAT") else "UNKNOWN"
            logger.info(f"Saving token for {creator_id}: {final_access_token[:15]}... (type: {token_type})")
            logger.info(f"  page_id: {page_id}, ig_user_id: {instagram_user_id}")

            if not final_access_token.startswith("EAA"):
                logger.warning(f"⚠️ Token is NOT a Page token! Messaging may not work.")

            await _save_instagram_connection(
                creator_id=creator_id,
                access_token=final_access_token,
                page_id=page_id,
                instagram_user_id=instagram_user_id
            )

            # Step 7: AUTO-ONBOARDING - Trigger scraping, tone analysis, and bot activation
            if instagram_user_id:
                logger.info(f"🚀 Starting auto-onboarding for {creator_id} in background...")
                background_tasks.add_task(
                    _auto_onboard_after_instagram_oauth,
                    creator_id=creator_id,
                    access_token=final_access_token,
                    instagram_user_id=instagram_user_id,
                    page_id=page_id or ""
                )

            success_msg = f"instagram&ig_user_id={instagram_user_id}&onboarding=started" if instagram_user_id else "instagram"
            return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&success={success_msg}")

    except Exception as e:
        logger.error(f"Instagram OAuth error: {e}")
        import traceback
        logger.error(traceback.format_exc())
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

async def _save_instagram_connection(
    creator_id: str,
    access_token: str,
    page_id: str = None,
    instagram_user_id: str = None
):
    """Save Instagram OAuth connection to database"""
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

                creator.instagram_token = access_token
                creator.instagram_page_id = page_id
                # Store Instagram user ID if we have it
                if instagram_user_id:
                    creator.instagram_user_id = instagram_user_id

                session.commit()
                logger.info(f"Saved Instagram connection for {creator_id} (page: {page_id}, ig_user: {instagram_user_id})")
            finally:
                session.close()
    except Exception as e:
        logger.error(f"Error saving Instagram connection: {e}")
        raise


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

            google_status = get_token_status(
                creator.google_access_token,
                creator.google_refresh_token,
                creator.google_token_expires_at
            )

            return {
                "status": "ok",
                "creator_id": creator_id,
                "platforms": {
                    "google": google_status
                },
                "summary": {
                    "total_connected": 1 if google_status["connected"] else 0,
                    "needs_attention": google_status.get("status") in ["expired", "expiring_soon"]
                }
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting OAuth status: {e}")
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


async def create_google_meet_event(
    creator_id: str,
    title: str,
    start_time,
    end_time,
    guest_email: str = None,
    guest_name: str = None,
    description: str = None
) -> dict:
    """
    Create a Google Calendar event with Google Meet link.

    Args:
        creator_id: The creator's ID
        title: Event title
        start_time: Event start datetime (timezone-aware)
        end_time: Event end datetime (timezone-aware)
        guest_email: Optional guest email to invite
        guest_name: Optional guest name
        description: Optional event description

    Returns:
        dict with event_id, meet_link, and calendar_link
    """
    import httpx

    try:
        access_token = await get_valid_google_token(creator_id)

        # Build event data
        event = {
            "summary": title,
            "description": description or f"Booking with {guest_name or 'guest'}",
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": "UTC"
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": "UTC"
            },
            "conferenceData": {
                "createRequest": {
                    "requestId": f"clonnect-{creator_id}-{start_time.timestamp()}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"}
                }
            }
        }

        # Add attendee if email provided
        if guest_email:
            event["attendees"] = [{"email": guest_email, "displayName": guest_name or ""}]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                params={"conferenceDataVersion": 1, "sendUpdates": "all" if guest_email else "none"},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json=event
            )

            if response.status_code != 200:
                logger.error(f"Google Calendar API error: {response.status_code} - {response.text}")
                raise Exception(f"Failed to create calendar event: {response.text}")

            event_data = response.json()

            # Extract Meet link
            meet_link = None
            if "conferenceData" in event_data:
                entry_points = event_data["conferenceData"].get("entryPoints", [])
                for ep in entry_points:
                    if ep.get("entryPointType") == "video":
                        meet_link = ep.get("uri")
                        break

            return {
                "event_id": event_data.get("id"),
                "meet_link": meet_link,
                "calendar_link": event_data.get("htmlLink"),
                "status": "confirmed"
            }

    except Exception as e:
        logger.error(f"Error creating Google Meet event: {e}")
        raise


async def delete_google_calendar_event(creator_id: str, event_id: str) -> bool:
    """
    Delete a Google Calendar event.

    Args:
        creator_id: The creator's ID
        event_id: The Google Calendar event ID to delete

    Returns:
        True if deleted successfully, False otherwise
    """
    import httpx

    try:
        access_token = await get_valid_google_token(creator_id)

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
                params={"sendUpdates": "all"},  # Notify attendees
                headers={
                    "Authorization": f"Bearer {access_token}",
                }
            )

            if response.status_code == 204 or response.status_code == 200:
                logger.info(f"Deleted Google Calendar event {event_id} for {creator_id}")
                return True
            elif response.status_code == 404:
                logger.warning(f"Google Calendar event {event_id} not found - may have been deleted already")
                return True  # Consider it a success if already deleted
            else:
                logger.error(f"Failed to delete Google Calendar event: {response.status_code} - {response.text}")
                return False

    except Exception as e:
        logger.error(f"Error deleting Google Calendar event: {e}")
        return False


async def get_google_freebusy(
    creator_id: str,
    start_time,
    end_time
) -> list:
    """
    Get busy times from Google Calendar using freebusy API.

    Args:
        creator_id: The creator's ID
        start_time: Start of time range (datetime, timezone-aware)
        end_time: End of time range (datetime, timezone-aware)

    Returns:
        List of busy periods: [{"start": datetime, "end": datetime}, ...]
    """
    import httpx
    from datetime import datetime

    try:
        access_token = await get_valid_google_token(creator_id)

        # Build freebusy request
        request_body = {
            "timeMin": start_time.isoformat(),
            "timeMax": end_time.isoformat(),
            "items": [{"id": "primary"}]  # Query primary calendar
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://www.googleapis.com/calendar/v3/freeBusy",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                },
                json=request_body,
                timeout=10.0
            )

            if response.status_code != 200:
                logger.error(f"Google freebusy API error: {response.status_code} - {response.text}")
                return []  # Return empty if error - will show all slots as available

            data = response.json()

            # Extract busy periods
            busy_periods = []
            calendars = data.get("calendars", {})
            primary_cal = calendars.get("primary", {})
            busy_list = primary_cal.get("busy", [])

            for busy in busy_list:
                busy_periods.append({
                    "start": datetime.fromisoformat(busy["start"].replace("Z", "+00:00")),
                    "end": datetime.fromisoformat(busy["end"].replace("Z", "+00:00"))
                })

            logger.info(f"Found {len(busy_periods)} busy periods for {creator_id}")
            return busy_periods

    except Exception as e:
        logger.error(f"Error getting Google freebusy: {e}")
        return []  # Return empty on error - graceful degradation
