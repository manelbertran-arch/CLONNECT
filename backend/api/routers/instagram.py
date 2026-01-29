"""
Instagram Router - Multi-Creator Support

BLOQUE 1+2: Multi-Creator Routing for Instagram Webhooks.
Routes incoming webhooks to the correct creator based on page_id.

Features:
- page_id → creator_id mapping via database lookup
- Dynamic handler creation per creator
- Ice Breakers support
- Stories Reply handling
- Persistent Menu configuration
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import PlainTextResponse

logger = logging.getLogger("clonnect-instagram")

router = APIRouter(prefix="/instagram", tags=["instagram"])

# Cache for Instagram handlers per creator
_creator_handlers: Dict[str, Any] = {}

# Cache for creator lookups by page_id (5-minute TTL for performance)
_creator_by_page_id_cache: Dict[str, tuple] = {}  # {page_id: (creator_info, timestamp)}
_CREATOR_LOOKUP_CACHE_TTL = 300  # 5 minutes


# =============================================================================
# MULTI-CREATOR ROUTING: page_id → creator_id
# =============================================================================


def get_creator_by_page_id(page_id: str) -> Optional[Dict[str, Any]]:
    """
    BLOQUE 1: Lookup creator by Instagram page_id.
    CACHED with 5-minute TTL for performance.

    Returns creator info including:
    - creator_id (name)
    - instagram_token
    - instagram_page_id
    - instagram_user_id
    - bot_active
    - copilot_mode

    Returns None if no creator found with this page_id.
    """
    import time

    current_time = time.time()

    # Check cache first
    if page_id in _creator_by_page_id_cache:
        cached_info, cached_time = _creator_by_page_id_cache[page_id]
        if current_time - cached_time < _CREATOR_LOOKUP_CACHE_TTL:
            if cached_info:
                logger.debug(
                    f"[CREATOR-CACHE] HIT for page_id {page_id}: {cached_info.get('creator_id')}"
                )
            return cached_info

    # Cache miss - query DB
    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            # Try by instagram_page_id first
            creator = session.query(Creator).filter_by(instagram_page_id=page_id).first()

            # If not found, also try by instagram_user_id (for new Instagram API without Facebook Page)
            if not creator:
                creator = session.query(Creator).filter_by(instagram_user_id=page_id).first()

            if not creator:
                logger.warning(f"No creator found for page_id: {page_id}")
                _creator_by_page_id_cache[page_id] = (None, current_time)
                return None

            result = {
                "creator_id": creator.name,
                "creator_uuid": str(creator.id),
                "instagram_token": creator.instagram_token,
                "instagram_page_id": creator.instagram_page_id,
                "instagram_user_id": creator.instagram_user_id,
                "bot_active": creator.bot_active,
                "copilot_mode": creator.copilot_mode,
            }
            logger.info(
                f"[CREATOR-CACHE] MISS for page_id {page_id}: loaded {result.get('creator_id')} from DB"
            )
            _creator_by_page_id_cache[page_id] = (result, current_time)
            return result
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error looking up creator by page_id {page_id}: {e}")
        return None


def get_creator_by_ig_user_id(ig_user_id: str) -> Optional[Dict[str, Any]]:
    """
    Alternative lookup: Find creator by instagram_user_id.
    Used when page_id is not available in webhook payload.
    CACHED with 5-minute TTL for performance.
    """
    import time

    current_time = time.time()

    # Use same cache (ig_user_id is just another type of page_id)
    cache_key = f"ig_user:{ig_user_id}"
    if cache_key in _creator_by_page_id_cache:
        cached_info, cached_time = _creator_by_page_id_cache[cache_key]
        if current_time - cached_time < _CREATOR_LOOKUP_CACHE_TTL:
            if cached_info:
                logger.debug(
                    f"[CREATOR-CACHE] HIT for ig_user_id {ig_user_id}: {cached_info.get('creator_id')}"
                )
            return cached_info

    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(instagram_user_id=ig_user_id).first()

            if not creator:
                _creator_by_page_id_cache[cache_key] = (None, current_time)
                return None

            result = {
                "creator_id": creator.name,
                "creator_uuid": str(creator.id),
                "instagram_token": creator.instagram_token,
                "instagram_page_id": creator.instagram_page_id,
                "instagram_user_id": creator.instagram_user_id,
                "bot_active": creator.bot_active,
                "copilot_mode": creator.copilot_mode,
            }
            logger.info(
                f"[CREATOR-CACHE] MISS for ig_user_id {ig_user_id}: loaded {result.get('creator_id')} from DB"
            )
            _creator_by_page_id_cache[cache_key] = (result, current_time)
            return result
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error looking up creator by ig_user_id {ig_user_id}: {e}")
        return None


def get_handler_for_creator(creator_info: Dict[str, Any]):
    """
    Get or create Instagram handler for a specific creator.
    Handlers are cached for performance.
    """
    from core.instagram_handler import InstagramHandler

    creator_id = creator_info["creator_id"]

    # Check cache
    if creator_id in _creator_handlers:
        handler = _creator_handlers[creator_id]
        # Update token if changed
        if handler.access_token != creator_info.get("instagram_token"):
            handler.access_token = creator_info.get("instagram_token")
            handler._init_connector()
        return handler

    # Create new handler
    handler = InstagramHandler(
        access_token=creator_info.get("instagram_token"),
        page_id=creator_info.get("instagram_page_id"),
        ig_user_id=creator_info.get("instagram_user_id"),
        creator_id=creator_id,
    )

    _creator_handlers[creator_id] = handler
    logger.info(f"Created Instagram handler for creator: {creator_id}")

    return handler


def extract_page_id_from_payload(payload: Dict[str, Any]) -> Optional[str]:
    """
    Extract page_id from Instagram webhook payload.
    The recipient.id in messaging events is the page_id.
    """
    try:
        for entry in payload.get("entry", []):
            # Entry ID is usually the page_id
            page_id = entry.get("id")
            if page_id:
                return page_id

            # Also check messaging events
            for messaging in entry.get("messaging", []):
                recipient_id = messaging.get("recipient", {}).get("id")
                if recipient_id:
                    return recipient_id

        return None
    except Exception as e:
        logger.error(f"Error extracting page_id: {e}")
        return None


# =============================================================================
# DEBUG/CACHE ENDPOINTS
# =============================================================================

@router.get("/clear-cache")
async def clear_instagram_cache():
    """Clear handler and lookup caches - useful for debugging"""
    global _creator_handlers, _creator_by_page_id_cache
    handlers_cleared = len(_creator_handlers)
    lookups_cleared = len(_creator_by_page_id_cache)
    _creator_handlers.clear()
    _creator_by_page_id_cache.clear()
    return {
        "status": "ok",
        "handlers_cleared": handlers_cleared,
        "lookups_cleared": lookups_cleared,
        "code_version": "V2_FIX_2026-01-29"
    }


# =============================================================================
# WEBHOOK ENDPOINTS
# =============================================================================

VERIFY_TOKEN = os.getenv("INSTAGRAM_VERIFY_TOKEN", "clonnect_verify_2024")


@router.get("/webhook")
async def instagram_webhook_verify(request: Request):
    """
    Webhook verification (GET) - Required by Meta.
    This is called when setting up the webhook in Meta App Dashboard.
    """
    params = dict(request.query_params)
    mode = params.get("hub.mode", "")
    token = params.get("hub.verify_token", "")
    challenge = params.get("hub.challenge", "")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Instagram webhook verified successfully")
        return PlainTextResponse(content=challenge)

    logger.warning(
        f"Instagram webhook verification failed: mode={mode}, token_match={token == VERIFY_TOKEN}"
    )
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def instagram_webhook_receive(request: Request):
    """
    BLOQUE 1+2: Multi-creator webhook receiver.

    Routes messages to the correct creator based on page_id in payload.
    Supports:
    - Direct messages (messaging events)
    - Story replies (story_mention events)
    - Comments (changes events)
    """
    logger.info("=" * 60)
    logger.info("========== INSTAGRAM WEBHOOK (MULTI-CREATOR) ==========")
    logger.info("=" * 60)

    try:
        payload = await request.json()
        signature = request.headers.get("X-Hub-Signature-256", "")

        # Log payload structure for debugging
        logger.info(f"Webhook object: {payload.get('object')}")

        # Extract page_id to route to correct creator
        page_id = extract_page_id_from_payload(payload)

        if not page_id:
            logger.warning("Could not extract page_id from webhook payload")
            # Return 200 to acknowledge receipt (don't retry)
            return {"status": "ok", "warning": "no_page_id", "messages_processed": 0}

        logger.info(f"Routing webhook for page_id: {page_id}")

        # Lookup creator by page_id
        creator_info = get_creator_by_page_id(page_id)

        if not creator_info:
            # Try alternative lookup by recipient in messaging
            for entry in payload.get("entry", []):
                for messaging in entry.get("messaging", []):
                    ig_user_id = messaging.get("recipient", {}).get("id")
                    if ig_user_id:
                        creator_info = get_creator_by_ig_user_id(ig_user_id)
                        if creator_info:
                            break
                if creator_info:
                    break

        if not creator_info:
            logger.warning(f"No creator found for page_id: {page_id}")
            # Return 200 to acknowledge (prevents retries for unknown pages)
            return {"status": "ok", "warning": "unknown_creator", "page_id": page_id}

        creator_id = creator_info["creator_id"]
        logger.info(f"Found creator: {creator_id} for page_id: {page_id}")

        # Check if bot is active
        if not creator_info.get("bot_active", False):
            logger.info(f"Bot not active for creator {creator_id}, skipping")
            return {"status": "ok", "info": "bot_paused", "creator_id": creator_id}

        # Get handler for this creator
        handler = get_handler_for_creator(creator_info)

        # Process the webhook
        result = await handler.handle_webhook(payload, signature)

        logger.info(
            f"Processed webhook for {creator_id}: {result.get('messages_processed', 0)} messages"
        )

        return {**result, "creator_id": creator_id, "page_id": page_id}

    except Exception as e:
        logger.error(f"Error processing Instagram webhook: {e}")
        import traceback

        logger.error(traceback.format_exc())
        # Return 200 to acknowledge receipt (prevents infinite retries)
        return {"status": "error", "error": str(e)}


# =============================================================================
# BLOQUE 3: ICE BREAKERS + PERSISTENT MENU
# =============================================================================


@router.post("/icebreakers/{creator_id}")
async def set_ice_breakers(creator_id: str, ice_breakers: List[Dict[str, str]]):
    """
    Set Ice Breakers for a creator's Instagram.

    Ice Breakers are conversation starters shown to users when they open
    a new conversation. Meta allows up to 4 ice breakers.

    Request body:
    [
        {"question": "¿Cuánto cuestan tus servicios?", "payload": "PRICING"},
        {"question": "¿Qué incluye el programa?", "payload": "FEATURES"},
        {"question": "¿Cómo puedo reservar?", "payload": "BOOKING"},
        {"question": "Quiero más información", "payload": "INFO"}
    ]
    """
    try:
        import httpx
        from api.database import SessionLocal
        from api.models import Creator

        # Get creator's token
        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

            if not creator.instagram_token or not creator.instagram_page_id:
                raise HTTPException(status_code=400, detail="Creator has no Instagram connection")

            access_token = creator.instagram_token
            page_id = creator.instagram_page_id
        finally:
            session.close()

        # Validate ice breakers (max 4)
        if len(ice_breakers) > 4:
            raise HTTPException(status_code=400, detail="Maximum 4 ice breakers allowed")

        # Format for Meta API
        formatted_icebreakers = [
            {"question": ib["question"], "payload": ib.get("payload", ib["question"][:20])}
            for ib in ice_breakers
        ]

        # Set ice breakers via Meta API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://graph.facebook.com/v21.0/{page_id}/messenger_profile",
                params={"access_token": access_token},
                json={"ice_breakers": formatted_icebreakers},
            )

            result = response.json()

            if "error" in result:
                logger.error(f"Failed to set ice breakers: {result['error']}")
                raise HTTPException(
                    status_code=400, detail=result["error"].get("message", "Unknown error")
                )

            logger.info(f"Set {len(ice_breakers)} ice breakers for {creator_id}")

            return {
                "status": "ok",
                "creator_id": creator_id,
                "ice_breakers_set": len(ice_breakers),
                "ice_breakers": formatted_icebreakers,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting ice breakers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/icebreakers/{creator_id}")
async def get_ice_breakers(creator_id: str):
    """
    Get current Ice Breakers for a creator.
    """
    try:
        import httpx
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

            if not creator.instagram_token or not creator.instagram_page_id:
                return {"status": "ok", "ice_breakers": [], "info": "No Instagram connection"}

            access_token = creator.instagram_token
            page_id = creator.instagram_page_id
        finally:
            session.close()

        # Get ice breakers via Meta API
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://graph.facebook.com/v21.0/{page_id}/messenger_profile",
                params={"access_token": access_token, "fields": "ice_breakers"},
            )

            result = response.json()
            ice_breakers = result.get("data", [{}])[0].get("ice_breakers", [])

            return {"status": "ok", "creator_id": creator_id, "ice_breakers": ice_breakers}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ice breakers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/icebreakers/{creator_id}")
async def delete_ice_breakers(creator_id: str):
    """
    Delete all Ice Breakers for a creator.
    """
    try:
        import httpx
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

            access_token = creator.instagram_token
            page_id = creator.instagram_page_id
        finally:
            session.close()

        if not access_token or not page_id:
            return {"status": "ok", "info": "No Instagram connection"}

        async with httpx.AsyncClient() as client:
            response = await client.delete(
                f"https://graph.facebook.com/v21.0/{page_id}/messenger_profile",
                params={"access_token": access_token},
                json={"fields": ["ice_breakers"]},
            )

            result = response.json()

            if result.get("success"):
                logger.info(f"Deleted ice breakers for {creator_id}")
                return {"status": "ok", "deleted": True}
            else:
                return {"status": "ok", "deleted": False, "result": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting ice breakers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/persistent-menu/{creator_id}")
async def set_persistent_menu(creator_id: str, menu_items: List[Dict[str, Any]]):
    """
    Set Persistent Menu for a creator's Instagram.

    The persistent menu appears as a hamburger menu in the chat.

    Request body example:
    [
        {
            "type": "postback",
            "title": "Ver servicios",
            "payload": "SERVICES"
        },
        {
            "type": "postback",
            "title": "Reservar cita",
            "payload": "BOOKING"
        },
        {
            "type": "web_url",
            "title": "Visitar web",
            "url": "https://example.com"
        }
    ]
    """
    try:
        import httpx
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

            access_token = creator.instagram_token
            page_id = creator.instagram_page_id
        finally:
            session.close()

        if not access_token or not page_id:
            raise HTTPException(status_code=400, detail="No Instagram connection")

        # Format persistent menu
        persistent_menu = [
            {"locale": "default", "composer_input_disabled": False, "call_to_actions": menu_items}
        ]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://graph.facebook.com/v21.0/{page_id}/messenger_profile",
                params={"access_token": access_token},
                json={"persistent_menu": persistent_menu},
            )

            result = response.json()

            if "error" in result:
                logger.error(f"Failed to set persistent menu: {result['error']}")
                raise HTTPException(
                    status_code=400, detail=result["error"].get("message", "Unknown error")
                )

            logger.info(f"Set persistent menu for {creator_id} with {len(menu_items)} items")

            return {"status": "ok", "creator_id": creator_id, "menu_items_set": len(menu_items)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting persistent menu: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# BLOQUE 4: STORIES REPLY HANDLER
# =============================================================================


@router.post("/webhook/stories")
async def instagram_stories_webhook(request: Request):
    """
    BLOQUE 4: Handle Instagram Story replies/mentions.

    When someone replies to a story or mentions the creator in their story,
    this webhook is triggered. The bot can auto-respond to story interactions.
    """
    logger.info("========== INSTAGRAM STORIES WEBHOOK ==========")

    try:
        payload = await request.json()

        results = []

        for entry in payload.get("entry", []):
            page_id = entry.get("id")

            # Get creator for this page
            creator_info = get_creator_by_page_id(page_id) if page_id else None

            if not creator_info:
                continue

            creator_id = creator_info["creator_id"]

            for messaging in entry.get("messaging", []):
                # Check for story mentions
                if "message" in messaging:
                    message = messaging["message"]
                    attachments = message.get("attachments", [])

                    for attachment in attachments:
                        # Story mention type
                        if attachment.get("type") == "story_mention":
                            story_url = attachment.get("payload", {}).get("url")
                            sender_id = messaging.get("sender", {}).get("id")

                            logger.info(f"Story mention from {sender_id} for {creator_id}")

                            # Process as regular message with story context
                            result = await _handle_story_mention(
                                creator_info=creator_info,
                                sender_id=sender_id,
                                story_url=story_url,
                                message_text=message.get("text", ""),
                            )
                            results.append(result)

                        # Story reply type
                        elif attachment.get("type") == "share" and attachment.get(
                            "payload", {}
                        ).get("is_story_reply"):
                            sender_id = messaging.get("sender", {}).get("id")
                            reply_text = message.get("text", "")

                            logger.info(
                                f"Story reply from {sender_id} for {creator_id}: {reply_text[:50]}..."
                            )

                            result = await _handle_story_reply(
                                creator_info=creator_info,
                                sender_id=sender_id,
                                reply_text=reply_text,
                            )
                            results.append(result)

        return {"status": "ok", "stories_processed": len(results), "results": results}

    except Exception as e:
        logger.error(f"Error processing stories webhook: {e}")
        return {"status": "error", "error": str(e)}


async def _handle_story_mention(
    creator_info: Dict[str, Any], sender_id: str, story_url: str, message_text: str = ""
) -> Dict[str, Any]:
    """
    Handle when someone mentions the creator in their story.
    Auto-sends a thank you DM and saves story thumbnail before it expires.
    """
    creator_id = creator_info["creator_id"]

    # Get handler
    handler = get_handler_for_creator(creator_info)

    # CRITICAL: Download story thumbnail IMMEDIATELY before it expires (24h)
    saved_thumbnail = None
    try:
        from core.story_thumbnail import download_story_thumbnail

        saved_thumbnail = await download_story_thumbnail(story_url)
        if saved_thumbnail:
            logger.info(f"Saved story thumbnail for mention from {sender_id}")
    except Exception as e:
        logger.warning(f"Could not save story thumbnail: {e}")

    # Default thank you message for story mentions
    thank_you_message = os.getenv(
        "STORY_MENTION_RESPONSE",
        "¡Gracias por compartir! 🙌 Me encanta que te haya gustado. ¿En qué puedo ayudarte?",
    )

    try:
        # Send response
        success = await handler.send_response(sender_id, thank_you_message)

        # Register interaction with saved thumbnail
        await _register_story_interaction(
            creator_id=creator_id,
            sender_id=sender_id,
            interaction_type="mention",
            story_url=story_url,
            saved_thumbnail=saved_thumbnail,
        )

        return {
            "type": "story_mention",
            "sender_id": sender_id,
            "response_sent": success,
            "creator_id": creator_id,
            "thumbnail_saved": bool(saved_thumbnail),
        }

    except Exception as e:
        logger.error(f"Error handling story mention: {e}")
        return {"type": "story_mention", "error": str(e)}


async def _handle_story_reply(
    creator_info: Dict[str, Any], sender_id: str, reply_text: str
) -> Dict[str, Any]:
    """
    Handle when someone replies to a creator's story.
    Process the reply through the DM agent like a regular message.
    """
    creator_id = creator_info["creator_id"]

    # Get handler
    handler = get_handler_for_creator(creator_info)

    try:
        # Import here to avoid circular imports
        from core.instagram import InstagramMessage

        # Create message object
        message = InstagramMessage(
            message_id=f"story_reply_{datetime.now().timestamp()}",
            sender_id=sender_id,
            recipient_id=creator_info.get("instagram_page_id", ""),
            text=reply_text,
            timestamp=datetime.now(timezone.utc),
        )

        # Process through DM agent
        response = await handler.process_message(message)

        # Check copilot mode
        copilot_enabled = creator_info.get("copilot_mode", True)

        if copilot_enabled:
            # Save as pending approval
            from core.copilot_service import get_copilot_service

            copilot = get_copilot_service()

            pending = await copilot.create_pending_response(
                creator_id=creator_id,
                lead_id="",
                follower_id=sender_id,
                platform="instagram",
                user_message=reply_text,
                user_message_id=message.message_id,
                suggested_response=response.response_text,
                intent=(
                    response.intent.value
                    if hasattr(response.intent, "value")
                    else str(response.intent)
                ),
                confidence=response.confidence,
                source="story_reply",
            )

            return {
                "type": "story_reply",
                "sender_id": sender_id,
                "copilot_mode": True,
                "pending_id": pending.id,
                "status": "pending_approval",
            }
        else:
            # Send immediately
            await handler.send_response(sender_id, response.response_text)

            return {
                "type": "story_reply",
                "sender_id": sender_id,
                "copilot_mode": False,
                "response": response.response_text[:50] + "...",
                "status": "sent",
            }

    except Exception as e:
        logger.error(f"Error handling story reply: {e}")
        return {"type": "story_reply", "error": str(e)}


async def _register_story_interaction(
    creator_id: str,
    sender_id: str,
    interaction_type: str,
    story_url: str = "",
    saved_thumbnail: str = None,
):
    """
    Register a story interaction as a lead touchpoint.
    Saves the story thumbnail if provided (before Instagram CDN URL expires).
    """
    try:
        from core.memory import FollowerMemory, MemoryStore

        memory_store = MemoryStore()
        follower_id = f"ig_{sender_id}"

        follower = await memory_store.load(creator_id, follower_id)
        if not follower:
            follower = FollowerMemory(
                follower_id=follower_id, creator_id=creator_id, platform="instagram"
            )

        follower.is_lead = True
        follower.source = f"story_{interaction_type}"

        # Add to notes
        if not hasattr(follower, "notes") or not follower.notes:
            follower.notes = []
        follower.notes.append(
            {
                "type": f"story_{interaction_type}",
                "story_url": story_url,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        await memory_store.save(follower)

        # Save message with story metadata to database
        try:
            from api.services import db_service

            # Get or create lead
            lead = db_service.get_or_create_lead(creator_id, follower_id, "instagram")
            if lead:
                # Build metadata with saved thumbnail
                msg_metadata = {
                    "type": f"story_{interaction_type}",
                    "url": story_url,
                }
                # Use saved thumbnail (base64) if available, otherwise use CDN URL
                if saved_thumbnail:
                    msg_metadata["thumbnail_base64"] = saved_thumbnail
                else:
                    msg_metadata["thumbnail_url"] = story_url

                # Save message
                await db_service.save_message(
                    lead_id=str(lead["id"]),
                    role="user",
                    content=f"Story {interaction_type}",
                    metadata=msg_metadata,
                )
                logger.info(f"Saved story {interaction_type} message for {follower_id}")
        except Exception as e:
            logger.warning(f"Could not save story message to DB: {e}")

        logger.info(f"Registered story {interaction_type} from {sender_id}")

    except Exception as e:
        logger.error(f"Failed to register story interaction: {e}")


# =============================================================================
# CONNECT ENDPOINT: Register page_id for a creator
# =============================================================================


@router.post("/connect")
async def connect_instagram_page(
    creator_id: str = Query(..., description="Creator name/ID"),
    page_id: str = Query(..., description="Instagram/Facebook Page ID"),
    access_token: str = Query(None, description="Page access token (optional if already stored)"),
    ig_user_id: str = Query(None, description="Instagram User ID (optional, defaults to page_id)"),
):
    """
    Connect/register an Instagram page to a creator.

    This endpoint allows manual registration of a page_id when OAuth flow
    doesn't capture it automatically, or for testing purposes.
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()

            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

            # Update page_id
            creator.instagram_page_id = page_id

            # Update instagram_user_id (use page_id as default if not provided)
            creator.instagram_user_id = ig_user_id or page_id

            # Update token if provided
            if access_token:
                creator.instagram_token = access_token

            session.commit()

            logger.info(f"Connected Instagram page {page_id} to creator {creator_id}")

            return {
                "status": "ok",
                "creator_id": creator_id,
                "instagram_page_id": page_id,
                "instagram_user_id": creator.instagram_user_id,
                "token_updated": bool(access_token),
            }

        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error connecting Instagram page: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{creator_id}")
async def get_instagram_status(creator_id: str):
    """
    Get Instagram connection status for a creator.
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()

            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator {creator_id} not found")

            connected = bool(creator.instagram_token and creator.instagram_page_id)

            # Get handler stats if connected
            handler_stats = {}
            if creator_id in _creator_handlers:
                handler = _creator_handlers[creator_id]
                handler_stats = handler.get_status()

            return {
                "status": "ok",
                "creator_id": creator_id,
                "connected": connected,
                "instagram_page_id": creator.instagram_page_id,
                "instagram_user_id": creator.instagram_user_id,
                "bot_active": creator.bot_active,
                "copilot_mode": creator.copilot_mode,
                "handler_stats": handler_stats,
            }

        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting Instagram status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/creators")
async def list_instagram_creators():
    """
    List all creators with Instagram connections.
    Useful for debugging multi-creator setup.
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creators = session.query(Creator).filter(Creator.instagram_page_id.isnot(None)).all()

            return {
                "status": "ok",
                "count": len(creators),
                "creators": [
                    {
                        "creator_id": c.name,
                        "instagram_page_id": c.instagram_page_id,
                        "instagram_user_id": c.instagram_user_id,
                        "bot_active": c.bot_active,
                        "copilot_mode": c.copilot_mode,
                        "has_token": bool(c.instagram_token),
                    }
                    for c in creators
                ],
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error listing Instagram creators: {e}")
        raise HTTPException(status_code=500, detail=str(e))
