"""
OAuth endpoints for platform integrations
Click-and-play authentication for beta testers
"""

import logging
import os
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import RedirectResponse
from services.media_capture_service import capture_media_from_url, is_cdn_url

logger = logging.getLogger(__name__)


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
                            reaction_emoji = reactions_data[0].get("emoji", "❤️")

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
                                msg_text = f"Reacción {reaction_emoji} a story"
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
                                msg_text = "Mención en story"
                                msg_metadata = {
                                    "type": "story_mention",
                                    "url": story_cdn_url or story_link,
                                    "link": story_link,
                                }
                            elif reaction_emoji:
                                msg_text = f"Reacción {reaction_emoji}"
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
                            logger.warning(f"Error en auto-categorización: {cat_error}")

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


router = APIRouter(prefix="/oauth", tags=["oauth"])

# Frontend URL for redirects after OAuth
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://www.clonnectapp.com")
# Backend API URL for OAuth callbacks
API_URL = os.getenv("API_URL", "https://api.clonnectapp.com")


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


# =============================================================================
# INSTAGRAM / META
# =============================================================================
# Facebook App credentials (for Facebook Login API - legacy)
META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_REDIRECT_URI = os.getenv("META_REDIRECT_URI", f"{API_URL}/oauth/instagram/callback")

# Instagram App credentials (for Instagram API with Instagram Login - NEW)
# These are DIFFERENT from the Facebook App credentials!
# In Meta Developer Portal: Your App > App Settings > Basic > Instagram App ID
INSTAGRAM_APP_ID = os.getenv("INSTAGRAM_APP_ID", "")
INSTAGRAM_APP_SECRET = os.getenv("INSTAGRAM_APP_SECRET", "")


@router.get("/instagram/start")
async def instagram_oauth_start(creator_id: str, website_url: str = None):
    """
    Start Instagram OAuth flow using Facebook Login.

    Uses Facebook Login (facebook.com/dialog/oauth) with META_APP_ID to get
    EAA tokens that have full page access for messaging.

    Flow:
    1. User clicks "Connect Instagram"
    2. Redirected to Facebook Login
    3. User logs into Facebook and grants permissions
    4. Redirected back with authorization code
    5. We exchange code for EAA access token
    6. We discover their Facebook Page and Instagram Business Account
    """
    app_id = META_APP_ID

    if not app_id:
        raise HTTPException(status_code=500, detail="META_APP_ID not configured")

    # Store state for CSRF protection - include website_url if provided
    # Format: creator_id:random_token:website_url_base64 (or empty if no website)
    import base64

    website_encoded = ""
    if website_url:
        website_encoded = base64.urlsafe_b64encode(website_url.encode()).decode()
    state = f"{creator_id}:{secrets.token_urlsafe(16)}:{website_encoded}"
    logger.info(f"[OAuth] State with website_url: {website_url}")

    # Facebook Login scopes for Instagram messaging via Pages
    scopes = [
        "instagram_basic",
        "instagram_manage_messages",
        "pages_show_list",
        "pages_manage_metadata",
        "pages_messaging",
    ]

    params = {
        "client_id": app_id,
        "redirect_uri": META_REDIRECT_URI,
        "scope": ",".join(scopes),
        "response_type": "code",
        "state": state,
    }

    auth_url = f"https://www.facebook.com/v21.0/dialog/oauth?{urlencode(params)}"

    logger.info(
        f"Instagram OAuth start (FB Login) for {creator_id} with app_id={app_id[:6]}... scopes: {scopes}"
    )
    logger.info(f"[DEBUG] OAuth start redirect_uri: {META_REDIRECT_URI}")

    return {
        "auth_url": auth_url,
        "state": state,
        "scopes_requested": scopes,
        "app_id_used": f"{app_id[:6]}...",
        "note": "User will login via Facebook Login to grant Instagram + Page permissions",
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
    Handle Instagram OAuth callback.

    Uses Facebook Login flow: exchanges code at graph.facebook.com for EAA tokens.
    Then discovers Facebook Pages and Instagram Business Account.
    """
    import httpx

    # Handle OAuth errors
    if error or error_code or error_message:
        error_msg = error_description or error_message or error_reason or error or "Unknown error"
        logger.error(f"Instagram OAuth error: {error_code or error} - {error_msg}")
        return RedirectResponse(
            f"{FRONTEND_URL}/crear-clon?error=instagram_scope_error&message={error_msg}"
        )

    if not code:
        logger.error("Instagram OAuth: No code received")
        return RedirectResponse(f"{FRONTEND_URL}/crear-clon?error=instagram_no_code")

    app_id = META_APP_ID
    app_secret = META_APP_SECRET

    if not app_id or not app_secret:
        logger.error("Instagram OAuth: META_APP_ID or META_APP_SECRET not configured")
        return RedirectResponse(f"{FRONTEND_URL}/crear-clon?error=instagram_not_configured")

    # Extract creator_id and website_url from state
    # Format: creator_id:random_token:website_url_base64
    import base64

    state_parts = state.split(":")
    creator_id = state_parts[0] if len(state_parts) > 0 else "manel"
    website_url = None
    if len(state_parts) >= 3 and state_parts[2]:
        try:
            website_url = base64.urlsafe_b64decode(state_parts[2]).decode()
            logger.info(f"[OAuth] Extracted website_url from state: {website_url}")
        except Exception as e:
            logger.warning(f"[OAuth] Could not decode website_url from state: {e}")
    logger.info(f"Instagram OAuth callback for creator: {creator_id}, website: {website_url}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Exchange code for short-lived access token via Facebook Graph API
            logger.info(f"Exchanging code with app_id={app_id[:6]}... (Facebook Login)")
            logger.info(f"[DEBUG] Token exchange redirect_uri: {META_REDIRECT_URI}")
            token_response = await client.get(
                "https://graph.facebook.com/v21.0/oauth/access_token",
                params={
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "redirect_uri": META_REDIRECT_URI,
                    "code": code,
                },
            )
            token_data = token_response.json()
            logger.info(f"Facebook token response: {token_response.status_code}")

            if "error" in token_data:
                logger.error(f"Facebook token error: {token_data}")
                return RedirectResponse(f"{FRONTEND_URL}/crear-clon?error=instagram_auth_failed")

            short_lived_token = token_data.get("access_token")
            logger.info(f"Got short-lived FB user token: {short_lived_token[:15]}...")

            # Track ALL Instagram IDs for webhook routing
            all_instagram_ids = set()

            # Step 2: Exchange for long-lived FB user token (60 days)
            long_token_response = await client.get(
                "https://graph.facebook.com/v21.0/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "fb_exchange_token": short_lived_token,
                },
            )
            long_token_data = long_token_response.json()

            if "error" in long_token_data:
                logger.warning(
                    f"Could not get long-lived token: {long_token_data}, using short-lived"
                )
                access_token = short_lived_token
            else:
                access_token = long_token_data.get("access_token", short_lived_token)
                logger.info(f"Got long-lived FB user token (60 days): {access_token[:15]}...")

            # Step 3: Get Facebook user info (IG username will come from business account discovery)
            user_response = await client.get(
                "https://graph.facebook.com/v21.0/me",
                params={
                    "fields": "id,name",
                    "access_token": access_token,
                },
            )
            user_data = user_response.json()
            logger.info(f"Facebook user info: {user_data}")

            ig_username = "unknown"  # Will be updated from IG business account
            instagram_user_id = ""

            # Step 4: Try to get Page Access Token (needed for messaging)
            # IMPORTANT: Explicitly request access_token field to get Page Access Token
            page_id = None
            page_access_token = None

            try:
                pages_response = await client.get(
                    "https://graph.facebook.com/v21.0/me/accounts",
                    params={
                        "access_token": access_token,
                        "fields": "id,name,access_token",  # Explicitly request access_token!
                    },
                )
                pages_data = pages_response.json()
                logger.info(f"Pages response: {len(pages_data.get('data', []))} pages found")

                if pages_data.get("data"):
                    # Get the first page (most users have one)
                    page = pages_data["data"][0]
                    page_id = page["id"]
                    page_access_token = page.get("access_token")

                    # Add ALL page IDs to additional_ids for webhook routing
                    for p in pages_data["data"]:
                        if p.get("id"):
                            all_instagram_ids.add(str(p["id"]))

                    # Log token type for debugging
                    if page_access_token:
                        token_prefix = page_access_token[:10] if page_access_token else "NONE"
                        logger.info(
                            f"Got Page Access Token: {token_prefix}... (type: {'PAGE' if page_access_token.startswith('EAA') else 'OTHER'})"
                        )
                    else:
                        logger.warning(f"No access_token in page response! Page data: {page}")

                    logger.info(f"Found Facebook Page: {page_id} ({page.get('name', 'unknown')})")

                    # Try to get Instagram Business Account linked to this page
                    ig_response = await client.get(
                        f"https://graph.facebook.com/v21.0/{page_id}",
                        params={
                            "fields": "instagram_business_account,name",
                            "access_token": page_access_token or access_token,
                        },
                    )
                    ig_data = ig_response.json()

                    if ig_data.get("instagram_business_account"):
                        ig_business_id = ig_data["instagram_business_account"]["id"]
                        all_instagram_ids.add(str(ig_business_id))
                        instagram_user_id = ig_business_id
                        logger.info(f"Found Instagram Business Account: {instagram_user_id}")

                        # Fetch IG username from the business account
                        try:
                            ig_user_response = await client.get(
                                f"https://graph.facebook.com/v21.0/{ig_business_id}",
                                params={
                                    "fields": "username",
                                    "access_token": page_access_token or access_token,
                                },
                            )
                            ig_user_data = ig_user_response.json()
                            if ig_user_data.get("username"):
                                ig_username = ig_user_data["username"]
                                logger.info(f"Got IG username: {ig_username}")
                        except Exception as username_err:
                            logger.warning(f"Could not fetch IG username: {username_err}")
                else:
                    logger.warning("No Facebook Pages found - using Instagram token directly")
            except Exception as page_err:
                logger.warning(f"Could not get Page token: {page_err} - using Instagram token")

            # Determine which token to save
            # Prefer Page token (EAA) for messaging, fall back to Instagram token (IGAAT)
            final_access_token = page_access_token or access_token

            # Log what we're saving for debugging
            token_type = (
                "PAGE (EAA)"
                if final_access_token.startswith("EAA")
                else "INSTAGRAM (IGAAT)" if final_access_token.startswith("IGAAT") else "UNKNOWN"
            )
            logger.info(
                f"Saving token for {creator_id}: {final_access_token[:15]}... (type: {token_type})"
            )
            logger.info(f"  page_id: {page_id}, ig_user_id: {instagram_user_id}")

            if not final_access_token.startswith("EAA"):
                logger.warning(
                    "⚠️ Token is NOT a Page token! Using Instagram token - messaging endpoint will use graph.instagram.com"
                )

            # Step 5: Save to database with ALL collected IDs
            # Convert set to list for JSON storage
            additional_ids_list = list(all_instagram_ids)
            logger.info(
                f"Collected {len(additional_ids_list)} Instagram IDs: {additional_ids_list}"
            )

            await _save_instagram_connection(
                creator_id=creator_id,
                access_token=final_access_token,
                page_id=page_id,
                instagram_user_id=instagram_user_id,
                additional_ids=additional_ids_list,
            )

            # NOTE: DO NOT set onboarding_completed=True here!
            # The /onboarding/start-clone endpoint and _run_clone_creation will handle that
            # after the user clicks "Crear mi clon" and the actual clone creation completes.
            # Setting it here causes a race condition where the progress endpoint
            # returns "complete" immediately before the clone creation even starts.

            # P0 FIX: Auto-onboarding removed. The clone creation pipeline now runs
            # ONLY from /onboarding/start-clone when the user clicks "Crear mi clon".
            # This eliminates the race condition where OAuth auto-onboard and clone creation
            # would both run simultaneously, overwriting each other's progress/status.
            logger.info(
                "[OAuth] Instagram connected for %s. Clone creation will run from /start-clone.",
                creator_id,
            )

            # Redirect to crear-clon page with success
            return RedirectResponse(
                f"{FRONTEND_URL}/crear-clon?instagram=connected&ig_user_id={instagram_user_id}&ig_username={ig_username}"
            )

    except Exception as e:
        logger.error(f"Instagram OAuth error: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return RedirectResponse(f"{FRONTEND_URL}/crear-clon?error=instagram_failed")


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
    whatsapp_app_id = os.getenv("WHATSAPP_META_APP_ID", META_APP_ID)
    if not whatsapp_app_id:
        raise HTTPException(status_code=500, detail="WHATSAPP_META_APP_ID not configured")

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
        raise HTTPException(status_code=500, detail="WhatsApp not configured on server")

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
        raise HTTPException(status_code=500, detail=f"WhatsApp signup failed: {str(e)}")


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
        raise HTTPException(status_code=500, detail="Failed to connect to Stripe")


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
        raise HTTPException(status_code=500, detail="PayPal credentials not configured")

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
        "client_id_preview": (
            client_id[:20] + "..." if len(client_id) > 20 else client_id if client_id else "NOT SET"
        ),
        "client_id_length": len(client_id),
        "client_secret_set": bool(client_secret),
        "client_secret_length": len(client_secret),
        "client_secret_preview": (
            client_secret[:5] + "..." if len(client_secret) > 5 else "TOO SHORT"
        ),
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
    from datetime import datetime, timedelta, timezone

    import httpx

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        logger.error(
            f"Google OAuth not configured: client_id={bool(GOOGLE_CLIENT_ID)}, secret={bool(GOOGLE_CLIENT_SECRET)}"
        )
        return RedirectResponse(
            f"{FRONTEND_URL}/settings?tab=connections&error=google_not_configured"
        )

    creator_id = state.split(":")[0] if ":" in state else "manel"

    # Log what we're sending (without exposing full secret)
    logger.info(
        f"Google OAuth callback - client_id_len={len(GOOGLE_CLIENT_ID)}, secret_len={len(GOOGLE_CLIENT_SECRET)}, redirect={GOOGLE_REDIRECT_URI}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
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
                return RedirectResponse(
                    f"{FRONTEND_URL}/settings?tab=connections&error=google_auth_failed"
                )

            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 3600)  # Default 1 hour

            # Calculate expiration time
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            # Get user info
            user_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
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
    instagram_user_id: str = None,
    additional_ids: list = None,
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
                    creator = Creator(name=creator_id, email=f"{creator_id}@clonnect.com")
                    session.add(creator)

                creator.instagram_token = access_token
                creator.instagram_page_id = page_id

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


@router.post("/refresh/google/{creator_id}")
async def force_refresh_google(creator_id: str):
    """Force refresh Google token"""

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
            "expires_at": expires_at.isoformat() if expires_at else None,
        }
    except Exception as e:
        from api.utils.error_helpers import safe_error_detail

        raise HTTPException(status_code=500, detail=safe_error_detail(e, "Google token refresh"))


async def _save_google_connection(
    creator_id: str, access_token: str, refresh_token: str, expires_at, google_email: str = None
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
    from datetime import datetime, timedelta, timezone

    import httpx

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
            async with httpx.AsyncClient(timeout=30.0) as client:
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
                    },
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
    from datetime import datetime, timedelta, timezone

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
                    logger.info(
                        f"Google token for {creator_id} expired or expiring soon, refreshing..."
                    )
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
    description: str = None,
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
            "start": {"dateTime": start_time.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end_time.isoformat(), "timeZone": "UTC"},
            "conferenceData": {
                "createRequest": {
                    "requestId": f"clonnect-{creator_id}-{start_time.timestamp()}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }

        # Add attendee if email provided
        if guest_email:
            event["attendees"] = [{"email": guest_email, "displayName": guest_name or ""}]

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                params={
                    "conferenceDataVersion": 1,
                    "sendUpdates": "all" if guest_email else "none",
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=event,
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
                "status": "confirmed",
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

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
                params={"sendUpdates": "all"},  # Notify attendees
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
            )

            if response.status_code == 204 or response.status_code == 200:
                logger.info(f"Deleted Google Calendar event {event_id} for {creator_id}")
                return True
            elif response.status_code == 404:
                logger.warning(
                    f"Google Calendar event {event_id} not found - may have been deleted already"
                )
                return True  # Consider it a success if already deleted
            else:
                logger.error(
                    f"Failed to delete Google Calendar event: {response.status_code} - {response.text}"
                )
                return False

    except Exception as e:
        logger.error(f"Error deleting Google Calendar event: {e}")
        return False


async def get_google_freebusy(creator_id: str, start_time, end_time) -> list:
    """
    Get busy times from Google Calendar using freebusy API.

    Args:
        creator_id: The creator's ID
        start_time: Start of time range (datetime, timezone-aware)
        end_time: End of time range (datetime, timezone-aware)

    Returns:
        List of busy periods: [{"start": datetime, "end": datetime}, ...]
    """
    from datetime import datetime

    import httpx

    try:
        access_token = await get_valid_google_token(creator_id)

        # Build freebusy request
        request_body = {
            "timeMin": start_time.isoformat(),
            "timeMax": end_time.isoformat(),
            "items": [{"id": "primary"}],  # Query primary calendar
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://www.googleapis.com/calendar/v3/freeBusy",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=request_body,
                timeout=10.0,
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
                busy_periods.append(
                    {
                        "start": datetime.fromisoformat(busy["start"].replace("Z", "+00:00")),
                        "end": datetime.fromisoformat(busy["end"].replace("Z", "+00:00")),
                    }
                )

            logger.info(f"Found {len(busy_periods)} busy periods for {creator_id}")
            return busy_periods

    except Exception as e:
        logger.error(f"Error getting Google freebusy: {e}")
        return []  # Return empty on error - graceful degradation
