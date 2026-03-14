"""Instagram / Meta OAuth endpoints + helpers."""

import logging
import os
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from services.media_capture_service import capture_media_from_url, is_cdn_url

logger = logging.getLogger(__name__)

router = APIRouter(tags=["oauth"])

# Frontend URL for redirects after OAuth
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://www.clonnectapp.com")
# Backend API URL for OAuth callbacks
API_URL = os.getenv("API_URL", "https://api.clonnectapp.com")

# Facebook App credentials (for Facebook Login API - legacy)
META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_REDIRECT_URI = os.getenv("META_REDIRECT_URI", f"{API_URL}/oauth/instagram/callback")

# Instagram App credentials (for Instagram API with Instagram Login - NEW)
# These are DIFFERENT from the Facebook App credentials!
# In Meta Developer Portal: Your App > App Settings > Basic > Instagram App ID
INSTAGRAM_APP_ID = os.getenv("INSTAGRAM_APP_ID", "")
INSTAGRAM_APP_SECRET = os.getenv("INSTAGRAM_APP_SECRET", "")


# =============================================================================
# AUTO-ONBOARDING FUNCTION
# =============================================================================


async def _auto_onboard_after_instagram_oauth(
    creator_id: str,
    access_token: str,
    instagram_user_id: str,
    page_id: str = "",
    website_url: str = None,
):
    """
    Ejecuta onboarding completo automáticamente después de OAuth.

    Pipeline:
    1. Scrape Instagram posts (últimos 50)
    2. Generar ToneProfile (Magic Slice)
    3. Indexar contenido en RAG
    4. Activar bot automáticamente
    5. Cargar historial de DMs existentes y categorizar leads
    6. Scrapear website (from param or bio) e indexar en RAG
    7. Detectar productos con ProductDetector
    """
    logger.info(f"[AutoOnboard] Starting automatic onboarding for {creator_id}...")

    try:
        from api.database import SessionLocal
        from api.models import Creator
        from core.onboarding_service import OnboardingRequest, get_onboarding_service
        from ingestion import MetaGraphAPIScraper

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
            access_token=access_token, instagram_business_id=instagram_user_id
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
                    posts_data.append(
                        {
                            "post_id": p.post_id,
                            "caption": p.caption,
                            "post_type": p.post_type,
                            "timestamp": p.timestamp.isoformat() if p.timestamp else None,
                            "permalink": p.permalink,
                            "media_url": p.media_url,
                            "likes_count": p.likes_count,
                            "comments_count": p.comments_count,
                        }
                    )

            # STEP 2 & 3: Run onboarding service (tone analysis + RAG indexing)
            logger.info(
                f"[AutoOnboard] Running onboarding pipeline with {len(posts_data)} posts..."
            )
            service = get_onboarding_service()
            request = OnboardingRequest(
                creator_id=creator_id,
                manual_posts=posts_data,
                scraping_method="manual",  # Already scraped
            )
            result = await service.onboard_creator(request)

            logger.info(
                f"[AutoOnboard] Onboarding result: posts={result.posts_processed}, tone={result.tone_profile_generated}, indexed={result.content_indexed}"
            )

        # STEP 4: Pre-configure bot settings (but DON'T mark onboarding_completed!)
        # The /start-clone → _run_clone_creation flow will set onboarding_completed=True
        # after the user explicitly clicks "Crear mi clon" and the progress tracking completes.
        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if creator:
                creator.bot_active = True
                creator.copilot_mode = True  # Enable copilot mode by default
                # NOTE: onboarding_completed is intentionally NOT set here!
                # It will be set by _run_clone_creation after the user clicks "Crear mi clon"
                session.commit()
                logger.info(
                    f"[AutoOnboard] ✅ Bot pre-configured for {creator_id} (awaiting manual clone creation)"
                )
        finally:
            session.close()

        # STEP 4b: Activate default nurturing sequences
        try:
            from core.nurturing import activate_default_sequences

            nurturing_result = activate_default_sequences(creator_id)
            logger.info(
                f"[AutoOnboard] ✅ Nurturing sequences activated: {list(nurturing_result.keys())}"
            )
        except Exception as nurturing_error:
            logger.warning(f"[AutoOnboard] Could not activate nurturing: {nurturing_error}")

        # STEP 5: Load DM history using simple sync (proven to work)
        logger.info(f"[AutoOnboard] Loading DM history for {creator_id}...")
        try:
            dm_stats = await _simple_dm_sync_internal(
                creator_id=creator_id,
                access_token=access_token,
                ig_user_id=instagram_user_id,
                ig_page_id=page_id,
                max_convs=30,
            )
            logger.info(
                f"[AutoOnboard] DM history loaded: {dm_stats.get('messages_saved', 0)} messages, {dm_stats.get('leads_created', 0)} leads"
            )
        except Exception as dm_error:
            logger.warning(f"[AutoOnboard] Could not load DM history: {dm_error}")
            import traceback

            logger.warning(traceback.format_exc())

        # STEP 6: Scrape website (from param or Instagram bio)
        url_to_scrape = website_url  # Use provided URL first
        try:
            if not url_to_scrape:
                logger.info("[AutoOnboard] No website_url provided, checking Instagram bio...")
                import httpx
                from core.website_scraper import extract_url_from_text

                # Get Instagram profile bio
                async with httpx.AsyncClient(timeout=10.0) as client:
                    profile_response = await client.get(
                        f"https://graph.facebook.com/v21.0/{instagram_user_id}",
                        params={"fields": "biography,website", "access_token": access_token},
                    )
                    if profile_response.status_code == 200:
                        profile_data = profile_response.json()
                        bio = profile_data.get("biography", "")
                        website = profile_data.get("website", "")
                        url_to_scrape = website or extract_url_from_text(bio)

            if url_to_scrape:
                logger.info(f"[AutoOnboard] Scraping website: {url_to_scrape}")
                from core.website_scraper import scrape_and_index_website

                web_stats = await scrape_and_index_website(
                    creator_id=creator_id, url=url_to_scrape, max_pages=100
                )
                logger.info(
                    f"[AutoOnboard] Website indexed: {web_stats['pages_scraped']} pages, {web_stats['chunks_indexed']} chunks"
                )

                # Save website_url to creator's knowledge_about
                session = SessionLocal()
                try:
                    creator = session.query(Creator).filter_by(name=creator_id).first()
                    if creator:
                        if not creator.knowledge_about:
                            creator.knowledge_about = {}
                        creator.knowledge_about["website_url"] = url_to_scrape
                        creator.website_url = url_to_scrape  # B10: dedicated column
                        from sqlalchemy.orm.attributes import flag_modified

                        flag_modified(creator, "knowledge_about")
                        session.commit()
                        logger.info(f"[AutoOnboard] Saved website_url to creator: {url_to_scrape}")
                finally:
                    session.close()
            else:
                logger.info("[AutoOnboard] No website found")
        except Exception as web_error:
            logger.warning(f"[AutoOnboard] Could not scrape website: {web_error}")

        # STEP 7: Detect and save products using ProductDetector (IngestionV2Pipeline)
        if url_to_scrape:
            try:
                logger.info(f"[AutoOnboard] Detecting products from {url_to_scrape}...")
                from ingestion.v2.pipeline import IngestionV2Pipeline

                session = SessionLocal()
                try:
                    pipeline = IngestionV2Pipeline(db_session=session, max_pages=100)
                    product_result = await pipeline.run(
                        creator_id=creator_id,
                        website_url=url_to_scrape,
                        clean_before=False,  # Don't clean - keep RAG from previous step
                        re_verify=True,
                    )
                    logger.info(
                        f"[AutoOnboard] Products: detected={product_result.products_detected}, saved={product_result.products_saved}"
                    )
                finally:
                    session.close()
            except Exception as product_error:
                logger.warning(f"[AutoOnboard] Could not detect products: {product_error}")

        # FINAL: Update clone_progress to 100% complete
        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if creator:
                creator.clone_status = "complete"
                creator.clone_progress = {
                    "steps": {
                        "instagram": "completed",
                        "website": "completed",
                        "training": "completed",
                        "activating": "completed",
                    },
                    "percent": 100,
                    "messages_synced": 0,
                    "leads_created": 0,
                }
                creator.onboarding_completed = True
                from sqlalchemy.orm.attributes import flag_modified

                flag_modified(creator, "clone_progress")
                session.commit()
                logger.info("[AutoOnboard] Progress updated to 100%")
        finally:
            session.close()

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


async def _simple_dm_sync_internal(
    creator_id: str, access_token: str, ig_user_id: str, ig_page_id: str = None, max_convs: int = 10
) -> dict:
    """
    Internal DM sync function that works with credentials passed directly.
    Simplified version of admin.simple_dm_sync for use during auto-onboarding.
    Rate limited: 2s delay between conversations to prevent Meta API blocks.
    """
    import asyncio
    from datetime import datetime, timedelta

    import httpx
    from api.database import SessionLocal
    from api.models import Creator, Lead, Message

    # Rate limiting constant
    DELAY_BETWEEN_CONVS = 2.0

    results = {
        "conversations_processed": 0,
        "messages_saved": 0,
        "leads_created": 0,
        "errors": [],
        "rate_limited": False,
    }

    # Build set of creator IDs for identification
    creator_ids = {ig_user_id, ig_page_id} - {None}

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            results["errors"].append(f"Creator {creator_id} not found")
            return results

        # FIX: Check token type FIRST to determine API
        # IGAAT tokens (Instagram Graph API) only work with graph.instagram.com
        # EAA tokens (Page Access) work with graph.facebook.com
        is_igaat_token = access_token.startswith("IGAAT")
        is_page_token = access_token.startswith("EAA")

        if is_igaat_token:
            # IGAAT tokens MUST use Instagram API
            api_base = "https://graph.instagram.com/v21.0"
            conv_id_for_api = ig_user_id or ig_page_id
            conv_extra_params = {}
        elif is_page_token and ig_page_id:
            # Page tokens use Facebook API with page_id
            api_base = "https://graph.facebook.com/v21.0"
            conv_id_for_api = ig_page_id
            conv_extra_params = {"platform": "instagram"}
        else:
            # Fallback to Instagram API
            api_base = "https://graph.instagram.com/v21.0"
            conv_id_for_api = ig_user_id or ig_page_id
            conv_extra_params = {}

        async with httpx.AsyncClient(timeout=60.0) as client:
            # Get conversations
            conv_resp = await client.get(
                f"{api_base}/{conv_id_for_api}/conversations",
                params={
                    **conv_extra_params,
                    "access_token": access_token,
                    "limit": max_convs,
                    "fields": "id,updated_time",
                },
            )

            if conv_resp.status_code != 200:
                results["errors"].append(f"Conversations API error: {conv_resp.status_code}")
                return results

            conversations = conv_resp.json().get("data", [])
            conversations.sort(key=lambda c: c.get("updated_time", ""), reverse=True)

            days_limit_ago = datetime.now().astimezone() - timedelta(days=180)

            for conv_idx, conv in enumerate(conversations):
                conv_id = conv.get("id")
                if not conv_id:
                    continue

                # Rate limiting: delay between conversations
                if conv_idx > 0:
                    logger.info(
                        f"[DMSync] Rate limit delay: {DELAY_BETWEEN_CONVS}s before conv {conv_idx + 1}/{len(conversations)}"
                    )
                    await asyncio.sleep(DELAY_BETWEEN_CONVS)

                try:
                    # Get messages with extended fields for media, stories, etc.
                    msg_resp = await client.get(
                        f"{api_base}/{conv_id}/messages",
                        params={
                            "fields": "id,message,from,to,created_time,attachments,story,share,shares,reactions,sticker",
                            "access_token": access_token,
                            "limit": 50,
                        },
                    )

                    # Check for rate limit error
                    if msg_resp.status_code != 200:
                        error_data = msg_resp.json().get("error", {})
                        if error_data.get("code") in [4, 17]:
                            logger.warning(
                                f"[DMSync] Rate limit hit at conv {conv_idx + 1}, stopping"
                            )
                            results["rate_limited"] = True
                            results["errors"].append(f"Rate limit at conv {conv_idx + 1}")
                            break
                        continue

                    messages = msg_resp.json().get("data", [])
                    if not messages:
                        continue

                    # Find follower (non-creator participant)
                    follower_id = None
                    follower_username = None

                    for msg in messages:
                        from_data = msg.get("from", {})
                        from_id = from_data.get("id")
                        if from_id and from_id not in creator_ids:
                            follower_id = from_id
                            follower_username = from_data.get("username", "unknown")
                            break

                    if not follower_id:
                        for msg in messages:
                            to_data = msg.get("to", {}).get("data", [])
                            for recipient in to_data:
                                if recipient.get("id") not in creator_ids:
                                    follower_id = recipient.get("id")
                                    follower_username = recipient.get("username", "unknown")
                                    break
                            if follower_id:
                                break

                    if not follower_id:
                        continue

                    # Fetch profile picture and verified status for follower
                    follower_profile_pic = None
                    follower_is_verified = False
                    try:
                        profile_resp = await client.get(
                            f"{api_base}/{follower_id}",
                            params={
                                "fields": "id,username,name,profile_pic,is_verified_user",
                                "access_token": access_token,
                            },
                        )
                        if profile_resp.status_code == 200:
                            profile_data = profile_resp.json()
                            follower_profile_pic = profile_data.get("profile_pic")
                            follower_is_verified = profile_data.get("is_verified_user", False)
                            if profile_data.get("username"):
                                follower_username = profile_data.get("username")
                    except Exception as profile_error:
                        logger.debug(f"Could not fetch profile for {follower_id}: {profile_error}")

                    # Parse timestamps
                    all_timestamps = []
                    user_timestamps = []
                    for msg in messages:
                        if msg.get("created_time"):
                            try:
                                ts = datetime.fromisoformat(
                                    msg["created_time"].replace("+0000", "+00:00")
                                )
                                all_timestamps.append(ts)
                                if msg.get("from", {}).get("id") not in creator_ids:
                                    user_timestamps.append(ts)
                            except ValueError as e:
                                logger.debug("Ignored ValueError in ts = datetime.fromisoformat(: %s", e)

                    first_contact = min(all_timestamps) if all_timestamps else None
                    last_contact = max(user_timestamps) if user_timestamps else first_contact

                    # FIX 2026-02-05: Skip conversations with no user messages
                    # These are "dead" outreach attempts (creator sent but got no response)
                    if not user_timestamps:
                        logger.debug(
                            f"[DM Sync] Skipping {follower_username}: no user messages (outbound only)"
                        )
                        continue

                    # Get or create lead - check both with and without ig_ prefix
                    lead = (
                        session.query(Lead)
                        .filter(
                            Lead.creator_id == creator.id,
                            Lead.platform == "instagram",
                            Lead.platform_user_id.in_([follower_id, f"ig_{follower_id}"]),
                        )
                        .first()
                    )

                    if not lead:
                        # Check if this lead is in the dismissed blocklist
                        # If so, skip - creator previously deleted this conversation
                        from api.models import DismissedLead

                        is_dismissed = (
                            session.query(DismissedLead)
                            .filter_by(creator_id=creator.id, platform_user_id=follower_id)
                            .first()
                        )
                        if is_dismissed:
                            logger.debug(
                                f"[DM Sync] Skipping {follower_username}: in dismissed_leads blocklist"
                            )
                            continue

                        # Build initial context with verified status
                        initial_context = {}
                        if follower_is_verified:
                            initial_context["is_verified"] = True
                        lead = Lead(
                            creator_id=creator.id,
                            platform="instagram",
                            platform_user_id=follower_id,
                            username=follower_username,
                            profile_pic_url=follower_profile_pic,
                            status="new",
                            first_contact_at=first_contact,
                            last_contact_at=last_contact,
                            context=initial_context if initial_context else None,
                        )
                        session.add(lead)
                        session.commit()
                        results["leads_created"] += 1
                    else:
                        if first_contact and (
                            not lead.first_contact_at or first_contact < lead.first_contact_at
                        ):
                            lead.first_contact_at = first_contact
                        if last_contact and (
                            not lead.last_contact_at or last_contact > lead.last_contact_at
                        ):
                            lead.last_contact_at = last_contact
                        # Update profile pic if we got one and lead doesn't have it
                        if follower_profile_pic and not lead.profile_pic_url:
                            lead.profile_pic_url = follower_profile_pic
                        # Update verified status if we got it
                        if follower_is_verified:
                            context = lead.context or {}
                            if not context.get("is_verified"):
                                context["is_verified"] = True
                                lead.context = context
                        session.commit()

                    # Save ALL messages (including media, reactions, stories)
                    for msg in messages:
                        msg_id = msg.get("id")
                        if not msg_id:
                            continue

                        # Detect content type and build message text + metadata for frontend rendering
                        # Logic from commit 37ac7a7f that was working correctly
                        msg_text = msg.get("message", "")
                        msg_metadata = {}

                        # STEP 1: Check for story data and reactions FIRST
                        story_data = msg.get("story", {})
                        reactions_data = msg.get("reactions", {}).get("data", [])

                        # Get reaction emoji if exists
                        reaction_emoji = None
                        if reactions_data:
                            reaction_emoji = reactions_data[0].get("emoji", "\u2764\ufe0f")

                        # Get story link if exists (check both reply_to and mention)
                        story_link = None
                        story_type = None
                        if story_data.get("reply_to"):
                            story_link = story_data["reply_to"].get("link", "")
                            story_type = "reply_to"
                        elif story_data.get("mention"):
                            story_link = story_data["mention"].get("link", "")
                            story_type = "mention"

                        # FIX 2026-02-02: Extract CDN URL from attachments for stories
                        # story_link is just a permalink (instagram.com/stories/...)
                        # The actual video/image is in attachments (lookaside.fbsbx.com/...)
                        story_cdn_url = None
                        if story_type:
                            raw_atts = msg.get("attachments", {})
                            story_atts = (
                                raw_atts.get("data", [])
                                if isinstance(raw_atts, dict)
                                else raw_atts if isinstance(raw_atts, list) else []
                            )
                            if story_atts:
                                att = story_atts[0]
                                story_cdn_url = (
                                    att.get("video_data", {}).get("url")
                                    or att.get("image_data", {}).get("url")
                                    or (
                                        att.get("payload", {}).get("url")
                                        if isinstance(att.get("payload"), dict)
                                        else None
                                    )
                                    or att.get("url")
                                )

                        # STEP 2: Build message based on combination (if no text)
                        if not msg_text:
                            if story_type and reaction_emoji:
                                msg_text = f"Reacci\u00f3n {reaction_emoji} a story"
                                msg_metadata = {
                                    "type": "story_reaction",
                                    "url": story_cdn_url
                                    or story_link,  # CDN URL first, fallback to permalink
                                    "link": story_link,  # Keep permalink for "open in Instagram"
                                    "emoji": reaction_emoji,
                                }
                            elif story_type == "reply_to":
                                msg_text = "Respuesta a story"
                                msg_metadata = {
                                    "type": "story_reply",
                                    "url": story_cdn_url or story_link,
                                    "link": story_link,
                                }
                            elif story_type == "mention":
                                msg_text = "Menci\u00f3n en story"
                                msg_metadata = {
                                    "type": "story_mention",
                                    "url": story_cdn_url or story_link,
                                    "link": story_link,
                                }
                            elif reaction_emoji:
                                msg_text = f"Reacci\u00f3n {reaction_emoji}"
                                msg_metadata = {"type": "reaction", "emoji": reaction_emoji}

                        # STEP 3: If still no text, check for share field at message level FIRST
                        if not msg_text:
                            share_data = msg.get("share")
                            if share_data:
                                msg_text = "Post compartido"
                                msg_metadata = {
                                    "type": "shared_post",
                                    "url": share_data.get("link", ""),
                                    "thumbnail_url": share_data.get("image_url", ""),
                                    "name": share_data.get("name", ""),
                                    "description": share_data.get("description", ""),
                                }

                        # STEP 4: Process attachments with structure-based detection
                        # FIX 2026-02-02: Support both Meta formats:
                        # - Old format: image_data.url, video_data.url
                        # - New format: payload.url (Instagram Messaging API)
                        # - Dict format: {"data": [{...}]} vs List format: [{...}]
                        if not msg_text:
                            raw_attachments = msg.get("attachments", {})
                            if isinstance(raw_attachments, dict):
                                attachments = raw_attachments.get("data", [])
                            elif isinstance(raw_attachments, list):
                                attachments = raw_attachments
                            else:
                                attachments = []
                            if attachments:
                                for att in attachments:
                                    att_type = (att.get("type") or "").lower()

                                    # Check for new payload format first (Instagram Messaging API)
                                    payload = att.get("payload", {})
                                    payload_url = (
                                        payload.get("url") if isinstance(payload, dict) else None
                                    )

                                    # Instagram sends structure-based types (no explicit type field)
                                    has_video = att.get("video_data") is not None
                                    has_image = att.get("image_data") is not None
                                    has_audio = att.get("audio_data") is not None
                                    is_sticker = att.get("render_as_sticker", False)
                                    is_animated = att.get("animated_gif_url") is not None

                                    # Get URL: try payload.url first, then legacy formats, then fallbacks
                                    if payload_url:
                                        att_url = payload_url
                                    elif has_video:
                                        att_url = att["video_data"].get("url")
                                    elif has_image:
                                        att_url = att["image_data"].get("url")
                                    elif has_audio:
                                        att_url = att["audio_data"].get("url")
                                    else:
                                        # Try common URL fields as fallbacks
                                        att_url = (
                                            att.get("url")
                                            or att.get("file_url")
                                            or att.get("preview_url")
                                            or att.get("src")
                                            or att.get("source")
                                            or att.get("link")
                                            or att.get("target", {}).get("url")
                                            or att.get("media", {}).get("url")
                                        )

                                    # Detect type by structure or explicit type
                                    if "video" in att_type or has_video:
                                        msg_text = "Video"
                                        msg_metadata = {"type": "video", "url": att_url}
                                    elif "audio" in att_type or has_audio:
                                        msg_text = "Audio"
                                        msg_metadata = {"type": "audio", "url": att_url}
                                    elif is_sticker or is_animated:
                                        # GIFs/Stickers
                                        gif_url = att.get("animated_gif_url") or att_url
                                        msg_text = "GIF"
                                        msg_metadata = {"type": "gif", "url": gif_url}
                                    elif (
                                        "share" in att_type
                                        or "post" in att_type
                                        or "media_share" in att_type
                                    ):
                                        # Shared post (explicit type)
                                        post_url = att.get("target", {}).get("url") or att_url
                                        thumbnail_url = (
                                            att.get("image_data", {}).get("url")
                                            if att.get("image_data")
                                            else att.get("preview_url")
                                        )
                                        msg_text = "Post compartido"
                                        msg_metadata = {
                                            "type": "shared_post",
                                            "url": post_url,
                                            "thumbnail_url": thumbnail_url,
                                        }
                                    elif "image" in att_type or "photo" in att_type or has_image:
                                        msg_text = "Imagen"
                                        msg_metadata = {"type": "image", "url": att_url}
                                    elif "link" in att_type:
                                        msg_text = "Link"
                                        msg_metadata = {"type": "link", "url": att_url}
                                    else:
                                        msg_text = "Archivo"
                                        msg_metadata = {"type": "file", "url": att_url}
                                    break  # Only use first attachment

                        # STEP 5: Check shares field if still no text
                        if not msg_text and msg.get("shares"):
                            shares = msg.get("shares", {}).get("data", [])
                            if shares:
                                share = shares[0]
                                share_link = share.get("link", "")
                                msg_text = "Contenido compartido"
                                msg_metadata = {"type": "share", "url": share_link}

                        # STEP 6: Check sticker if still no text
                        if not msg_text and msg.get("sticker"):
                            msg_text = "Sticker"
                            sticker_url = msg.get("sticker", "")
                            msg_metadata = {
                                "type": "sticker",
                                "url": sticker_url if isinstance(sticker_url, str) else "",
                            }

                        # STEP 7: Default to [Media] for unknown - but still try to extract URL
                        if not msg_text:
                            msg_text = "[Media]"
                            # Try to extract any URL from attachments as last resort
                            fallback_url = None
                            attachments = msg.get("attachments", {}).get("data", [])
                            if attachments:
                                att = attachments[0]
                                # Deep search for any URL-like field
                                for key, value in att.items():
                                    if isinstance(value, str) and value.startswith("http"):
                                        fallback_url = value
                                        break
                                    elif isinstance(value, dict):
                                        for subkey, subvalue in value.items():
                                            if isinstance(subvalue, str) and subvalue.startswith(
                                                "http"
                                            ):
                                                fallback_url = subvalue
                                                break
                                        if fallback_url:
                                            break
                            msg_metadata = {"type": "unknown", "url": fallback_url}

                        # Check timestamp within limit
                        msg_time = None
                        if msg.get("created_time"):
                            try:
                                msg_time = datetime.fromisoformat(
                                    msg["created_time"].replace("+0000", "+00:00")
                                )
                                if msg_time < days_limit_ago:
                                    continue
                            except ValueError as e:
                                logger.debug("Ignored ValueError in msg_time = datetime.fromisoformat(: %s", e)

                        # Check for duplicate
                        existing = (
                            session.query(Message).filter_by(platform_message_id=msg_id).first()
                        )
                        if existing:
                            continue

                        # Determine role (assistant = creator, user = follower)
                        from_id = msg.get("from", {}).get("id")
                        role = "assistant" if from_id in creator_ids else "user"

                        # MEDIA CAPTURE: Capture CDN URLs before they expire
                        # Instagram CDN URLs expire after ~24 hours
                        if msg_metadata:
                            media_url = msg_metadata.get("url") or msg_metadata.get("thumbnail_url")
                            if media_url and is_cdn_url(media_url):
                                try:
                                    media_type = msg_metadata.get("type", "image")
                                    if media_type in ("video", "audio", "shared_video", "reel"):
                                        capture_type = "video"
                                    else:
                                        capture_type = "image"

                                    captured = await capture_media_from_url(
                                        url=media_url,
                                        media_type=capture_type,
                                        creator_id=creator_id,
                                    )
                                    if captured:
                                        # Store captured media
                                        if captured.startswith("data:"):
                                            msg_metadata["thumbnail_base64"] = captured
                                        else:
                                            msg_metadata["permanent_url"] = captured
                                        logger.debug(f"[DM Sync] Captured media for msg {msg_id}")
                                except Exception as capture_err:
                                    logger.warning(f"[DM Sync] Media capture failed: {capture_err}")

                        new_msg = Message(
                            lead_id=lead.id,
                            role=role,
                            content=msg_text,
                            platform_message_id=msg_id,
                            msg_metadata=msg_metadata if msg_metadata else {},
                        )
                        if msg_time:
                            new_msg.created_at = msg_time
                        session.add(new_msg)
                        results["messages_saved"] += 1

                        # AUDIO TRANSCRIPTION: Transcribe audio messages with Whisper
                        if (
                            msg_metadata
                            and msg_metadata.get("type") == "audio"
                            and msg_metadata.get("url")
                        ):
                            try:
                                from ingestion.transcriber import get_transcriber

                                transcriber = get_transcriber()
                                transcript = await transcriber.transcribe_url(
                                    msg_metadata["url"]
                                )
                                if transcript and transcript.full_text.strip():
                                    transcribed_text = transcript.full_text.strip()

                                    # Audio Intelligence Pipeline (4-layer)
                                    try:
                                        from services.audio_intelligence import (
                                            get_audio_intelligence,
                                        )

                                        intel = get_audio_intelligence()
                                        ai_result = await intel.process(
                                            raw_text=transcribed_text,
                                            duration_seconds=int(
                                                new_msg.msg_metadata.get("duration", 0)
                                            ),
                                            language="es",
                                            role="user",
                                        )
                                        legacy = ai_result.to_legacy_fields()
                                        new_msg.msg_metadata.update(legacy)
                                        new_msg.msg_metadata["audio_intel"] = (
                                            ai_result.to_metadata()
                                        )
                                        new_msg.content = (
                                            f"[\U0001f3a4 Audio]: {ai_result.clean_text or transcribed_text}"
                                        )
                                    except Exception as pp_err:
                                        logger.warning(
                                            f"[DM Sync] Audio intelligence failed for {msg_id}: {pp_err}"
                                        )
                                        new_msg.content = (
                                            f"[\U0001f3a4 Audio]: {transcribed_text}"
                                        )
                                        new_msg.msg_metadata["transcription"] = transcribed_text

                                    logger.info(
                                        f"[DM Sync] Audio transcribed for msg {msg_id}: "
                                        f"{transcribed_text[:50]}..."
                                    )
                            except Exception as transcribe_err:
                                logger.error(
                                    f"[DM Sync] Audio transcription failed for msg {msg_id}: "
                                    f"{transcribe_err}"
                                )

                    session.commit()
                    results["conversations_processed"] += 1

                    # Auto-categorize lead after saving messages
                    if results["messages_saved"] > 0:
                        try:
                            from core.lead_categorization import (
                                calcular_categoria,
                                categoria_a_status_legacy,
                            )

                            lead_messages = (
                                session.query(Message)
                                .filter_by(lead_id=lead.id)
                                .order_by(Message.created_at)
                                .all()
                            )
                            mensajes_para_cat = [
                                {"role": m.role, "content": m.content or ""} for m in lead_messages
                            ]

                            cat_result = calcular_categoria(
                                mensajes=mensajes_para_cat,
                                es_cliente=lead.status == "customer",
                                ultimo_mensaje_lead=lead.last_contact_at,
                                lead_created_at=lead.first_contact_at,
                            )

                            new_status = categoria_a_status_legacy(cat_result.categoria)
                            if lead.status != new_status:
                                lead.status = new_status
                                # Recalculate multi-factor score
                                try:
                                    from services.lead_scoring import recalculate_lead_score
                                    recalculate_lead_score(session, str(lead.id))
                                except Exception as se:
                                    logger.warning(f"Scoring failed: {se}")
                                    lead.purchase_intent = cat_result.intent_score
                                    lead.score = max(0, min(100, int(cat_result.intent_score * 100)))
                                session.commit()
                                logger.info(
                                    f"Lead {lead.username} auto-categorizado: {cat_result.categoria}"
                                )
                        except Exception as cat_error:
                            logger.warning(f"Error en auto-categorizaci\u00f3n: {cat_error}")

                except Exception as conv_error:
                    logger.warning(f"[DM Sync] Error processing conversation: {conv_error}")
                    continue

        return results

    except Exception as e:
        logger.error(f"[DM Sync] Error: {e}")
        results["errors"].append(str(e))
        return results
    finally:
        session.close()


async def _save_instagram_connection(
    creator_id: str,
    access_token: str,
    page_id: str = None,
    instagram_user_id: str = None,
    additional_ids: list = None,
    token_expires_at=None,
):
    """
    Save Instagram OAuth connection to database.

    Stores ALL Instagram IDs for robust webhook routing:
    - instagram_user_id: Primary Instagram user ID
    - instagram_page_id: Facebook Page ID (if connected)
    - instagram_additional_ids: All other IDs found during OAuth
    """
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

                creator.instagram_token = access_token
                creator.instagram_page_id = page_id
                if token_expires_at:
                    creator.instagram_token_expires_at = token_expires_at

                # Store Instagram user ID if we have it
                if instagram_user_id:
                    creator.instagram_user_id = instagram_user_id

                # Store ALL additional IDs for webhook routing fallback
                if additional_ids:
                    # Merge with existing additional_ids (don't overwrite)
                    existing_ids = creator.instagram_additional_ids or []
                    all_ids = list(set(existing_ids + additional_ids))
                    creator.instagram_additional_ids = all_ids
                    logger.info(f"Stored {len(all_ids)} additional IDs for webhook routing")

                session.commit()
                logger.info(
                    f"Saved Instagram connection for {creator_id} "
                    f"(page: {page_id}, ig_user: {instagram_user_id}, additional_ids: {additional_ids})"
                )
            finally:
                session.close()
    except Exception as e:
        logger.error(f"Error saving Instagram connection: {e}")
        raise


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
            "secret_key_prefix": (
                stripe_secret[:7] + "..." if len(stripe_secret) > 10 else "NOT_SET"
            ),
        },
        "meta": {
            "app_id_set": bool(os.getenv("META_APP_ID", "")),
        },
        "paypal": {
            "client_id_set": bool(os.getenv("PAYPAL_CLIENT_ID", "")),
        },
        "google": {
            "client_id_set": bool(os.getenv("GOOGLE_CLIENT_ID", "")),
        },
    }


class InjectTokenRequest(BaseModel):
    token: str
    instagram_user_id: str = None  # Optional: will be fetched from /me if not provided
    expires_days: int = 60         # Long-lived tokens last 60 days


@router.post("/instagram/inject-token")
async def instagram_inject_token(
    creator_id: str,
    body: InjectTokenRequest,
    x_api_key: str = Header(None, alias="X-API-Key"),
):
    """
    Admin-only: Manually inject a valid Instagram token for a creator.
    Useful when the Developer Portal generates a token and OAuth isn't available.
    Validates the token against /me before saving.
    """
    import httpx
    from datetime import datetime, timedelta, timezone

    ADMIN_KEY = os.getenv("ADMIN_API_KEY", "clonnect_admin_secret_2024")
    if x_api_key != ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Forbidden")

    token = body.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token is required")

    # Validate token by calling /me
    ig_user_id = body.instagram_user_id
    ig_username = None

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Try graph.instagram.com/me (IGAAT token)
        me_resp = await client.get(
            "https://graph.instagram.com/v21.0/me",
            params={"fields": "id,username,name", "access_token": token},
        )
        me_data = me_resp.json()
        logger.info(f"[InjectToken] /me response for {creator_id}: {me_data}")

        if "error" in me_data:
            # Try graph.facebook.com/me (EAA token)
            me_resp2 = await client.get(
                "https://graph.facebook.com/v21.0/me",
                params={"fields": "id,name", "access_token": token},
            )
            me_data2 = me_resp2.json()
            logger.info(f"[InjectToken] FB /me response: {me_data2}")
            if "error" in me_data2:
                raise HTTPException(
                    status_code=400,
                    detail=f"Token validation failed: {me_data.get('error', {}).get('message', 'unknown error')}",
                )
            ig_user_id = ig_user_id or str(me_data2.get("id", ""))
            ig_username = me_data2.get("name")
        else:
            ig_user_id = ig_user_id or str(me_data.get("id", ""))
            ig_username = me_data.get("username") or me_data.get("name")

        # Try to exchange for long-lived if it looks short-lived
        long_lived_token = token
        if token.startswith("IGAAT") and len(token) < 300:
            for app_secret in [
                os.getenv("INSTAGRAM_APP_SECRET", ""),
                "a6f0db4f7d9ae3b80799fdb8b554e221",  # App 892
            ]:
                if not app_secret:
                    continue
                exchange_resp = await client.get(
                    "https://graph.instagram.com/access_token",
                    params={
                        "grant_type": "ig_exchange_token",
                        "client_secret": app_secret,
                        "access_token": token,
                    },
                )
                exchange_data = exchange_resp.json()
                logger.info(f"[InjectToken] Exchange attempt: {exchange_data}")
                if "access_token" in exchange_data:
                    long_lived_token = exchange_data["access_token"]
                    body.expires_days = exchange_data.get("expires_in", 5183944) // 86400
                    logger.info(f"[InjectToken] Exchanged to long-lived token ({body.expires_days}d)")
                    break

    token_expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_days)

    await _save_instagram_connection(
        creator_id=creator_id,
        access_token=long_lived_token,
        page_id=None,
        instagram_user_id=ig_user_id,
        additional_ids=[ig_user_id] if ig_user_id else [],
        token_expires_at=token_expires_at,
    )

    return {
        "ok": True,
        "creator_id": creator_id,
        "ig_user_id": ig_user_id,
        "ig_username": ig_username,
        "token_prefix": long_lived_token[:20] + "...",
        "token_length": len(long_lived_token),
        "exchanged_to_long_lived": long_lived_token != token,
        "expires_at": token_expires_at.isoformat(),
    }


@router.get("/instagram/start")
async def instagram_oauth_start(creator_id: str, website_url: str = None, redirect_to: str = None):
    """
    Start Instagram OAuth flow using Instagram Business Login.

    Uses Instagram Business Login (instagram.com/oauth/authorize) with INSTAGRAM_APP_ID
    to get IGAAT tokens for Instagram messaging.

    Flow:
    1. User clicks "Connect Instagram"
    2. Redirected to instagram.com/oauth/authorize
    3. User logs into Instagram and grants permissions
    4. Redirected back with authorization code
    5. We exchange code for IGAAT access token (api.instagram.com)
    6. We get instagram_user_id directly from graph.instagram.com/me
    """
    app_id = INSTAGRAM_APP_ID

    if not app_id:
        raise HTTPException(status_code=503, detail="Instagram OAuth is not configured on this server")

    # Store state for CSRF protection - include website_url if provided
    # Format: creator_id:random_token:website_url_base64 (or empty if no website)
    import base64

    website_encoded = ""
    if website_url:
        website_encoded = base64.urlsafe_b64encode(website_url.encode()).decode()
    redirect_encoded = base64.urlsafe_b64encode(redirect_to.encode()).decode() if redirect_to else ""
    state = f"{creator_id}:{secrets.token_urlsafe(16)}:{website_encoded}:{redirect_encoded}"
    logger.info(f"[OAuth] State with website_url: {website_url}, redirect_to: {redirect_to}")

    # Instagram Business Login scopes (produces IGAAT tokens)
    scopes = [
        "instagram_business_basic",
        "instagram_business_manage_messages",
    ]

    params = {
        "client_id": app_id,
        "redirect_uri": META_REDIRECT_URI,
        "scope": ",".join(scopes),
        "response_type": "code",
        "state": state,
    }

    auth_url = f"https://www.instagram.com/oauth/authorize?{urlencode(params)}"

    logger.info(
        f"Instagram OAuth start (IG Business Login) for {creator_id} with app_id={app_id[:6]}... scopes: {scopes}"
    )
    logger.info(f"[DEBUG] OAuth start redirect_uri: {META_REDIRECT_URI}")

    return {
        "auth_url": auth_url,
        "state": state,
        "scopes_requested": scopes,
        "app_id_used": f"{app_id[:6]}...",
        "note": "User will login via Instagram Business Login to grant Instagram permissions",
    }


@router.get("/instagram/callback")
async def instagram_oauth_callback(
    background_tasks: BackgroundTasks,
    code: str = Query(None),
    state: str = Query(""),
    error_code: str = Query(None),
    error_message: str = Query(None),
    error: str = Query(None),
    error_reason: str = Query(None),
    error_description: str = Query(None),
):
    """
    Handle Instagram OAuth callback (Instagram Business Login).

    Exchanges code at api.instagram.com for short-lived IGAAT,
    then upgrades to long-lived IGAAT (60 days) via graph.instagram.com.
    Gets instagram_user_id directly from /me — no Facebook Pages needed.
    """
    import httpx

    logger.info(
        f"[OAuth CALLBACK] Hit! code={'YES' if code else 'NO'}, "
        f"state={state[:20] if state else 'NONE'}..., "
        f"error={error}, error_code={error_code}"
    )

    # Handle OAuth errors from Instagram (user denied, scope rejected, etc.)
    if error or error_code or error_message:
        error_msg = error_description or error_message or error_reason or error or "Unknown error"
        logger.error(
            f"Instagram OAuth DENIED/ERROR: error={error}, error_code={error_code}, "
            f"error_message={error_message}, error_reason={error_reason}, "
            f"error_description={error_description}, state={state}"
        )
        return RedirectResponse(
            f"{FRONTEND_URL}/crear-clon?error=instagram_auth_failed&message={error_msg}"
        )

    if not code:
        logger.error("Instagram OAuth: No code received")
        return RedirectResponse(f"{FRONTEND_URL}/crear-clon?error=instagram_no_code")

    app_id = INSTAGRAM_APP_ID
    app_secret = INSTAGRAM_APP_SECRET

    if not app_id or not app_secret:
        logger.error("Instagram OAuth: INSTAGRAM_APP_ID or INSTAGRAM_APP_SECRET not configured")
        return RedirectResponse(f"{FRONTEND_URL}/crear-clon?error=instagram_not_configured")

    # Extract creator_id and website_url from state
    # Format: creator_id:random_token:website_url_base64
    import base64

    state_parts = state.split(":")
    creator_id = state_parts[0] if len(state_parts) > 0 else "manel"
    website_url = None
    redirect_to = None
    if len(state_parts) >= 3 and state_parts[2]:
        try:
            website_url = base64.urlsafe_b64decode(state_parts[2]).decode()
            logger.info(f"[OAuth] Extracted website_url from state: {website_url}")
        except Exception as e:
            logger.warning(f"[OAuth] Could not decode website_url from state: {e}")
    if len(state_parts) >= 4 and state_parts[3]:
        try:
            redirect_to = base64.urlsafe_b64decode(state_parts[3]).decode()
            logger.info(f"[OAuth] Extracted redirect_to from state: {redirect_to}")
        except Exception as e:
            logger.warning(f"[OAuth] Could not decode redirect_to from state: {e}")
    logger.info(f"Instagram OAuth callback for creator: {creator_id}, website: {website_url}, redirect_to: {redirect_to}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Exchange code for short-lived IGAAT token via Instagram API
            logger.info(f"Exchanging code with app_id={app_id[:6]}... (Instagram Business Login)")
            logger.info(f"[DEBUG] Token exchange redirect_uri: {META_REDIRECT_URI}")
            token_response = await client.post(
                "https://api.instagram.com/oauth/access_token",
                data={
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": META_REDIRECT_URI,
                    "code": code,
                },
            )
            token_data = token_response.json()
            logger.info(f"Instagram token response: {token_response.status_code} {token_data}")

            if "error_type" in token_data or "error" in token_data:
                logger.error(f"Instagram token error: {token_data}")
                return RedirectResponse(f"{FRONTEND_URL}/crear-clon?error=instagram_auth_failed")

            short_lived_token = token_data.get("access_token")
            ig_user_id_from_token = str(token_data.get("user_id", ""))
            logger.info(f"Got short-lived IGAAT: {short_lived_token[:15]}... user_id={ig_user_id_from_token}")

            # Step 2: Exchange for long-lived IGAAT (60 days)
            # Meta docs say GET, but try both POST and GET
            from datetime import datetime, timedelta, timezone as tz
            exchange_params = {
                "grant_type": "ig_exchange_token",
                "client_secret": app_secret,
                "access_token": short_lived_token,
            }

            access_token = short_lived_token
            token_expires_at = None
            exchange_succeeded = False

            # Try GET first (per Meta docs), then POST as fallback
            for method_name, make_request in [
                ("GET", lambda: client.get("https://graph.instagram.com/access_token", params=exchange_params)),
                ("POST", lambda: client.post("https://graph.instagram.com/access_token", data=exchange_params)),
            ]:
                try:
                    long_token_response = await make_request()
                    long_token_data = long_token_response.json()
                    if long_token_response.status_code == 200 and "access_token" in long_token_data:
                        access_token = long_token_data["access_token"]
                        expires_in = long_token_data.get("expires_in", 5184000)
                        token_expires_at = datetime.now(tz.utc) + timedelta(seconds=expires_in)
                        exchange_succeeded = True
                        logger.info(
                            f"Long-lived token exchange succeeded via {method_name} "
                            f"(expires_in={expires_in}s): {access_token[:15]}..."
                        )
                        break
                    else:
                        logger.warning(f"Token exchange {method_name} failed: {long_token_data}")
                except Exception as exc:
                    logger.warning(f"Token exchange {method_name} exception: {exc}")

            if not exchange_succeeded:
                # Save the short-lived token anyway so the user isn't stuck
                # It may actually be long-lived (Meta API behavior varies)
                # Set a conservative 1-hour expiry; the refresh cron will check
                logger.warning(
                    f"Long-lived token exchange failed for {creator_id}. "
                    f"Saving initial token (may be short-lived ~1h). "
                    f"Token: {access_token[:15]}... ({len(access_token)} chars)"
                )
                token_expires_at = datetime.now(tz.utc) + timedelta(hours=1)

            # Step 3: Get Instagram user info directly from graph.instagram.com
            me_response = await client.get(
                "https://graph.instagram.com/v21.0/me",
                params={
                    "fields": "id,username,name",
                    "access_token": access_token,
                },
            )
            me_data = me_response.json()
            logger.info(f"Instagram /me response: {me_data}")

            instagram_user_id = me_data.get("id") or ig_user_id_from_token
            ig_username = me_data.get("username") or me_data.get("name") or "unknown"
            logger.info(f"IG user: id={instagram_user_id}, username={ig_username}")

            # Log what we're saving for debugging
            token_type = "INSTAGRAM (IGAAT)" if access_token.startswith("IGAAT") else "UNKNOWN"
            logger.info(
                f"Saving token for {creator_id}: {access_token[:15]}... (type: {token_type})"
            )
            logger.info(f"  page_id: None (Instagram Business Login — no FB Pages), ig_user_id: {instagram_user_id}")

            # Step 4: Save to database
            # page_id is None with Instagram Business Login (no Facebook Pages involved)
            await _save_instagram_connection(
                creator_id=creator_id,
                access_token=access_token,
                page_id=None,
                instagram_user_id=instagram_user_id,
                additional_ids=[instagram_user_id] if instagram_user_id else [],
                token_expires_at=token_expires_at,
            )

            # P0 FIX: Clone creation runs ONLY from /onboarding/start-clone.
            logger.info(
                "[OAuth] Instagram connected for %s. Clone creation will run from /start-clone.",
                creator_id,
            )

            # Redirect to correct page after OAuth success
            if redirect_to == "settings":
                return RedirectResponse(
                    f"{FRONTEND_URL}/new/ajustes?instagram=connected&ig_user_id={instagram_user_id}&ig_username={ig_username}"
                )
            return RedirectResponse(
                f"{FRONTEND_URL}/crear-clon?instagram=connected&ig_user_id={instagram_user_id}&ig_username={ig_username}"
            )

    except Exception as e:
        logger.error(f"Instagram OAuth error: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return RedirectResponse(f"{FRONTEND_URL}/crear-clon?error=instagram_failed")
