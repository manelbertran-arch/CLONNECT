"""
Messaging webhooks router (Instagram, WhatsApp, Telegram).
Extracted from main.py following TDD methodology.
"""

import asyncio
import json
import logging
import os
from typing import Dict

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response

logger = logging.getLogger(__name__)
router = APIRouter(tags=["messaging-webhooks"])


# =============================================================================
# INSTAGRAM WEBHOOK
# =============================================================================


@router.get("/webhook/instagram")
async def instagram_webhook_verify(request: Request):
    """
    Instagram webhook verification (GET).
    Meta sends GET request to verify the endpoint before activating webhooks.
    """
    from core.instagram_handler import get_instagram_handler

    params = dict(request.query_params)
    mode = params.get("hub.mode", "")
    token = params.get("hub.verify_token", "")
    challenge = params.get("hub.challenge", "")

    handler = get_instagram_handler()
    result = handler.verify_webhook(mode, token, challenge)

    if result:
        logger.info("Instagram webhook verified successfully")
        return Response(content=result, media_type="text/plain")

    logger.warning("Instagram webhook verification failed")
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook/instagram")
async def instagram_webhook_receive(request: Request):
    """
    Receive Instagram webhook events (POST).

    V9: Handles both messaging (DMs) and feed (new posts) events.
    - Messaging: Processed via DMResponderAgent (existing flow)
    - Feed: New post/reel detected → background task for real-time ingestion (SPEC-004B)

    Multi-creator routing with robust ID matching.
    """
    from api.routers.instagram import get_handler_for_creator
    from core.webhook_routing import (
        extract_all_instagram_ids,
        find_creator_for_webhook,
        save_unmatched_webhook,
        update_creator_webhook_stats,
    )

    logger.warning("=" * 60)
    logger.warning("========== INSTAGRAM WEBHOOK HIT V9 (MESSAGING + FEED) ==========")
    logger.warning("=" * 60)

    try:
        raw_body = await request.body()
        payload = await request.json()
        signature = request.headers.get("X-Hub-Signature-256", "")

        # 1. Extract ALL possible Instagram IDs from payload
        instagram_ids = extract_all_instagram_ids(payload)

        if not instagram_ids:
            logger.warning("Could not extract any Instagram IDs from webhook payload")
            return {"status": "ok", "warning": "no_ids_found", "messages_processed": 0}

        logger.info(f"Extracted Instagram IDs: {instagram_ids}")

        # 2. Find creator using any of the extracted IDs
        creator_info, matched_id = find_creator_for_webhook(instagram_ids)

        # 3. If no creator found, save for debugging and return
        if not creator_info:
            logger.warning(f"No creator found for Instagram IDs: {instagram_ids}")
            unmatched_id = save_unmatched_webhook(instagram_ids, payload)
            return {
                "status": "ok",
                "warning": "unknown_creator",
                "instagram_ids": instagram_ids,
                "unmatched_webhook_id": unmatched_id,
                "messages_processed": 0,
            }

        creator_id = creator_info["creator_id"]
        logger.info(f"Found creator: {creator_id} (matched by ID: {matched_id})")

        # 4. Update webhook stats for this creator
        update_creator_webhook_stats(creator_id)

        # 5. Check for feed events (new posts/reels) — SPEC-004B
        #    Process in background so webhook returns 200 instantly
        feed_events_found = 0
        for entry in payload.get("entry", []):
            has_feed = any(
                c.get("field") == "feed"
                for c in entry.get("changes", [])
            )
            if has_feed:
                feed_events_found += 1
                asyncio.create_task(
                    _process_feed_event_safe(creator_info, entry)
                )

        if feed_events_found > 0:
            logger.info(
                f"[FEED-WEBHOOK] Dispatched {feed_events_found} feed event(s) "
                f"for {creator_id} to background processing"
            )

        # 6. Check if bot is active (for DM processing)
        has_messaging = any(
            "messaging" in entry
            for entry in payload.get("entry", [])
        )

        if not has_messaging:
            # Pure feed event — no DM to process
            return {
                "status": "ok",
                "creator_id": creator_id,
                "matched_id": matched_id,
                "messages_processed": 0,
                "feed_events_dispatched": feed_events_found,
            }

        if not creator_info.get("bot_active", False):
            logger.info(f"Bot not active for creator {creator_id}, skipping DM processing")
            return {
                "status": "ok",
                "info": "bot_paused",
                "creator_id": creator_id,
                "matched_id": matched_id,
                "messages_processed": 0,
                "feed_events_dispatched": feed_events_found,
            }

        # 7. Get handler for this creator and process DMs
        handler = get_handler_for_creator(creator_info)
        result = await handler.handle_webhook(payload, signature, raw_body=raw_body)

        logger.info(f"Instagram webhook processed: {result.get('messages_processed', 0)} messages")
        return {
            **result,
            "creator_id": creator_id,
            "matched_id": matched_id,
            "feed_events_dispatched": feed_events_found,
        }

    except Exception as e:
        logger.error(f"Error processing Instagram webhook: {e}")
        import traceback

        logger.error(traceback.format_exc())
        # Return 200 to acknowledge receipt (prevents infinite retries from Meta)
        return {"status": "error", "error": str(e)}


async def _process_feed_event_safe(creator_info: dict, entry: dict):
    """Wrapper to safely run feed webhook processing in background."""
    try:
        from services.feed_webhook_handler import process_feed_webhook

        await process_feed_webhook(creator_info, entry)
    except Exception as e:
        logger.error(
            "[FEED-WEBHOOK] Background processing failed for "
            f"{creator_info.get('creator_id', '?')}: {e}"
        )



@router.get("/instagram/status")
async def instagram_status():
    """Get Instagram handler status"""
    from core.instagram_handler import get_instagram_handler

    handler = get_instagram_handler()
    return {
        "status": "ok",
        "handler": handler.get_status(),
        "recent_messages": handler.get_recent_messages(5),
        "recent_responses": handler.get_recent_responses(5),
    }


@router.post("/webhook/instagram/comments")
async def instagram_comments_webhook(request: Request):
    """
    Webhook for Instagram comments.
    When someone comments on a post with interest keywords, auto-sends a DM.
    Enable with AUTO_DM_ON_COMMENTS=true environment variable.
    """
    from core.instagram_handler import get_instagram_handler

    try:
        payload = await request.json()
        handler = get_instagram_handler()

        results = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") == "comments":
                    comment_data = change.get("value", {})
                    result = await handler.handle_comment(comment_data)
                    if result:
                        results.append(result)

        return {"status": "ok", "comments_processed": len(results), "results": results}

    except Exception as e:
        logger.error(f"Error processing Instagram comments webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal error processing webhook")


# =============================================================================
# WHATSAPP WEBHOOK
# =============================================================================


@router.get("/webhook/whatsapp")
async def whatsapp_webhook_verify(request: Request):
    """
    WhatsApp webhook verification (GET).
    Meta sends GET request to verify the endpoint before activating webhooks.
    """
    mode = request.query_params.get("hub.mode", "")
    token = request.query_params.get("hub.verify_token", "")
    challenge = request.query_params.get("hub.challenge", "")

    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "clonnect_whatsapp_verify_2024")

    if mode == "subscribe" and token == verify_token:
        logger.info("WhatsApp webhook verified successfully")
        return PlainTextResponse(content=challenge)

    logger.warning(f"WhatsApp webhook verification failed: mode={mode}")
    return PlainTextResponse(content="Verification failed", status_code=403)


@router.post("/webhook/whatsapp")
async def whatsapp_webhook_receive(request: Request):
    """
    Receive WhatsApp webhook events (POST).
    Processes incoming messages with DMResponderAgent and sends automatic responses.
    Supports copilot mode (suggested responses) and autopilot mode (auto-send).
    """
    from core.dm_agent_v2 import get_dm_agent
    from core.whatsapp import WhatsAppConnector

    logger.warning("========== WHATSAPP WEBHOOK HIT ==========")

    try:
        body = await request.body()
        payload = json.loads(body)
        signature = request.headers.get("X-Hub-Signature-256", "")

        # Verify webhook signature
        connector = WhatsAppConnector()
        if not connector.verify_webhook_signature(body, signature):
            logger.warning("WhatsApp webhook signature verification failed")
            raise HTTPException(status_code=403, detail="Invalid signature")

        # Parse messages from webhook payload
        messages = await connector.handle_webhook_event(payload)

        if not messages:
            return {"status": "ok", "messages_processed": 0}

        # Multi-tenant: resolve creator from phone_number_id in webhook payload
        creator_id = os.getenv("WHATSAPP_CREATOR_ID", "stefano_bonanno")
        wa_token_db = ""
        wa_phone_id_db = ""
        try:
            # Extract phone_number_id from Meta webhook payload
            webhook_phone_id = ""
            for entry in payload.get("entry", []):
                for change in entry.get("changes", []):
                    metadata = change.get("value", {}).get("metadata", {})
                    if metadata.get("phone_number_id"):
                        webhook_phone_id = metadata["phone_number_id"]
                        break
                if webhook_phone_id:
                    break

            if webhook_phone_id:
                from api.database import SessionLocal
                from api.models import Creator
                session = SessionLocal()
                try:
                    creator_row = session.query(Creator).filter(
                        Creator.whatsapp_phone_id == webhook_phone_id
                    ).first()
                    if creator_row:
                        creator_id = creator_row.name
                        wa_token_db = creator_row.whatsapp_token or ""
                        wa_phone_id_db = creator_row.whatsapp_phone_id or ""
                        logger.info(f"[WA] Multi-tenant: routed to creator '{creator_id}' via phone_number_id={webhook_phone_id}")
                    else:
                        logger.warning(f"[WA] No creator found for phone_number_id={webhook_phone_id}, fallback to env var creator '{creator_id}'")
                finally:
                    session.close()
        except Exception as mt_err:
            logger.warning(f"[WA] Multi-tenant lookup failed, using fallback: {mt_err}")

        # Per-creator credentials with env var fallback
        wa_token = wa_token_db or os.getenv("WHATSAPP_ACCESS_TOKEN", "")
        wa_phone_id = wa_phone_id_db or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")

        results = []
        for message in messages:
            sender_id = f"wa_{message.sender_id}"
            display_name = message.sender_name or message.sender_id
            logger.info(f"[WA:{message.sender_id}] ({display_name}) Input: {message.text[:100]}")

            try:
                agent = get_dm_agent(creator_id)
                response = await agent.process_dm(
                    message=message.text,
                    sender_id=sender_id,
                    metadata={
                        "message_id": message.message_id,
                        "username": display_name,
                        "name": message.sender_name,
                        "platform": "whatsapp",
                    },
                )

                bot_reply = response.content if hasattr(response, "content") else str(response)
                intent = str(response.intent) if hasattr(response, "intent") else "unknown"
                confidence = response.confidence if hasattr(response, "confidence") else 0.0

                logger.info(f"[WA:{message.sender_id}] Intent: {intent} ({confidence:.0%})")

                # Fire-and-forget identity resolution
                try:
                    from core.identity_resolver import resolve_identity
                    from api.services.db_service import get_or_create_lead
                    lead_result = get_or_create_lead(
                        creator_id, sender_id, platform="whatsapp",
                        username=display_name, full_name=message.sender_name,
                    )
                    if lead_result:
                        asyncio.create_task(resolve_identity(creator_id, lead_result["id"], "whatsapp"))
                except Exception as ir_err:
                    logger.debug(f"[WA] Identity resolution skipped: {ir_err}")

                # Check copilot mode
                copilot_enabled = _get_copilot_mode_cached(creator_id)

                if copilot_enabled:
                    logger.info("[WA] COPILOT MODE - creating pending response")
                    try:
                        from core.copilot_service import get_copilot_service
                        copilot = get_copilot_service()
                        # Carry Best-of-N candidates from DM response metadata
                        _wa_msg_meta = {}
                        if hasattr(response, "metadata") and response.metadata and response.metadata.get("best_of_n"):
                            _wa_msg_meta["best_of_n"] = response.metadata["best_of_n"]

                        pending = await copilot.create_pending_response(
                            creator_id=creator_id,
                            lead_id="",
                            follower_id=sender_id,
                            platform="whatsapp",
                            user_message=message.text,
                            user_message_id=message.message_id,
                            suggested_response=bot_reply,
                            intent=intent,
                            confidence=confidence,
                            username=display_name,
                            full_name=message.sender_name or message.sender_id,
                            msg_metadata=_wa_msg_meta if _wa_msg_meta else None,
                        )
                        results.append({
                            "message_id": message.message_id,
                            "sender_id": message.sender_id,
                            "intent": intent,
                            "copilot_mode": True,
                            "pending_response_id": pending.id,
                            "response_sent": False,
                        })
                    except Exception as copilot_err:
                        logger.error(f"[WA] Copilot error: {copilot_err}")
                        results.append({
                            "message_id": message.message_id,
                            "sender_id": message.sender_id,
                            "error": f"copilot: {copilot_err}",
                        })
                else:
                    # AUTOPILOT MODE - send response via WhatsApp
                    logger.info("[WA] AUTOPILOT MODE - sending auto-reply")
                    sent = False

                    if bot_reply and wa_token and wa_phone_id:
                        try:
                            send_connector = WhatsAppConnector(
                                phone_number_id=wa_phone_id,
                                access_token=wa_token,
                            )
                            send_result = await send_connector.send_message(
                                message.sender_id, bot_reply
                            )
                            await send_connector.close()
                            if "error" not in send_result:
                                sent = True
                                logger.info(f"[WA] Response sent to {message.sender_id}")
                            else:
                                logger.error(f"[WA] Send error: {send_result['error']}")
                        except Exception as send_err:
                            logger.error(f"[WA] Send error: {send_err}")

                    # Mark as read
                    if wa_token and wa_phone_id:
                        try:
                            read_connector = WhatsAppConnector(
                                phone_number_id=wa_phone_id,
                                access_token=wa_token,
                            )
                            await read_connector.mark_as_read(message.message_id)
                            await read_connector.close()
                        except Exception as e:
                            logger.warning("Suppressed error in read_connector = WhatsAppConnector(: %s", e)

                    results.append({
                        "message_id": message.message_id,
                        "sender_id": message.sender_id,
                        "response": bot_reply[:100],
                        "intent": intent,
                        "confidence": confidence,
                        "copilot_mode": False,
                        "response_sent": sent,
                    })

            except Exception as e:
                logger.error(f"[WA] Error processing message {message.message_id}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                results.append({
                    "message_id": message.message_id,
                    "sender_id": message.sender_id,
                    "error": str(e),
                })

        logger.info(f"WhatsApp webhook processed: {len(messages)} messages")
        return {
            "status": "ok",
            "messages_processed": len(messages),
            "creator_id": creator_id,
            "results": results,
        }

    except Exception as e:
        logger.error(f"Error processing WhatsApp webhook: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Return 200 to acknowledge receipt (prevents infinite retries from Meta)
        return {"status": "error", "error": str(e)}


@router.get("/whatsapp/status")
async def whatsapp_status():
    """Get WhatsApp handler status"""
    from core.whatsapp import get_whatsapp_handler

    try:
        handler = get_whatsapp_handler()
        return {
            "status": "ok",
            "handler": handler.get_status(),
            "recent_messages": handler.get_recent_messages(5),
            "recent_responses": handler.get_recent_responses(5),
        }
    except Exception as e:
        return {
            "status": "error",
            "phone_number_id_configured": bool(os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")),
            "access_token_configured": bool(os.getenv("WHATSAPP_ACCESS_TOKEN", "")),
            "webhook_url": "/webhook/whatsapp",
            "error": str(e),
        }


# =============================================================================
# WHATSAPP TEST ENDPOINT
# =============================================================================


@router.post("/admin/whatsapp/test-message")
async def whatsapp_test_message(request: Request):
    """
    Simulate a WhatsApp message through the full DM pipeline.

    Use this to test the WhatsApp flow E2E without needing WhatsApp Business API.
    The message goes through DMResponderAgent just like a real webhook,
    but the response is returned in the API response instead of being
    sent to WhatsApp.

    Body: { "creator_id": "stefano_bonanno", "phone": "+34612345678", "text": "Hola" }
    """
    from core.dm_agent_v2 import get_dm_agent

    try:
        body = await request.json()
        creator_id = body.get("creator_id", "stefano_bonanno")
        phone = body.get("phone", "+34600000000")
        text = body.get("text", "Hola, me interesa tu servicio")

        # Strip + and spaces for consistent sender_id
        phone_clean = phone.replace("+", "").replace(" ", "")

        agent = get_dm_agent(creator_id)

        response = await agent.process_dm(
            message=text,
            sender_id=f"wa_{phone_clean}",
            metadata={
                "message_id": "test_wa_0",
                "username": phone,
                "name": phone,
                "platform": "whatsapp",
            },
        )

        response_text = response.content if hasattr(response, "content") else str(response)
        intent = str(response.intent) if hasattr(response, "intent") else "unknown"
        confidence = response.confidence if hasattr(response, "confidence") else None

        return {
            "status": "ok",
            "test_mode": True,
            "creator_id": creator_id,
            "input": {
                "phone": phone,
                "sender_id": f"wa_{phone_clean}",
                "text": text,
            },
            "pipeline_response": {
                "response_text": response_text,
                "intent": intent,
                "confidence": confidence,
            },
            "note": "Response NOT sent to WhatsApp - test mode only",
            "env_check": {
                "WHATSAPP_PHONE_NUMBER_ID": bool(os.getenv("WHATSAPP_PHONE_NUMBER_ID")),
                "WHATSAPP_ACCESS_TOKEN": bool(os.getenv("WHATSAPP_ACCESS_TOKEN")),
                "WHATSAPP_VERIFY_TOKEN": bool(os.getenv("WHATSAPP_VERIFY_TOKEN")),
            },
        }

    except Exception as e:
        logger.error(f"Error in WhatsApp test message: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Internal error processing WhatsApp message")


# =============================================================================
# TELEGRAM WEBHOOK
# =============================================================================

# Telegram configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL", "")
TELEGRAM_PROXY_SECRET = os.getenv("TELEGRAM_PROXY_SECRET", "")

# Deduplication cache for Telegram messages
_telegram_processed_updates: Dict[int, float] = {}
_telegram_dedup_lock = asyncio.Lock()
TELEGRAM_DEDUP_TTL = 60  # seconds

# Copilot mode cache
_copilot_mode_cache: Dict[str, tuple] = {}
_COPILOT_CACHE_TTL = 300  # 5 minutes
_COPILOT_MAX_CACHE_ENTRIES = 500  # Prevent unbounded growth
_COPILOT_EVICTION_TTL = 3600  # Evict entries older than 1 hour


def _evict_stale_copilot_cache(current_time: float):
    """Remove stale copilot cache entries and enforce max size."""
    global _copilot_mode_cache
    if len(_copilot_mode_cache) <= _COPILOT_MAX_CACHE_ENTRIES:
        return
    # Evict entries older than eviction TTL
    stale_keys = [
        k for k, (_, t) in _copilot_mode_cache.items()
        if current_time - t > _COPILOT_EVICTION_TTL
    ]
    for k in stale_keys:
        _copilot_mode_cache.pop(k, None)
    # If still over limit, evict oldest
    if len(_copilot_mode_cache) > _COPILOT_MAX_CACHE_ENTRIES:
        sorted_keys = sorted(_copilot_mode_cache, key=lambda k: _copilot_mode_cache[k][1])
        excess = len(_copilot_mode_cache) - _COPILOT_MAX_CACHE_ENTRIES
        for k in sorted_keys[:excess]:
            _copilot_mode_cache.pop(k, None)


def _get_copilot_mode_cached(creator_id: str) -> bool:
    """Get copilot_mode for a creator with 5-minute cache."""
    import time

    current_time = time.time()

    if creator_id in _copilot_mode_cache:
        cached_value, cached_time = _copilot_mode_cache[creator_id]
        if current_time - cached_time < _COPILOT_CACHE_TTL:
            logger.debug(f"[COPILOT-CACHE] HIT for {creator_id}: copilot_mode={cached_value}")
            return cached_value

    copilot_enabled = True
    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if creator:
                copilot_enabled = getattr(creator, "copilot_mode", True)
                if copilot_enabled is None:
                    copilot_enabled = True
                logger.info(
                    f"[COPILOT-CACHE] MISS for {creator_id}: loaded copilot_mode={copilot_enabled} from DB"
                )
            else:
                logger.warning(
                    f"[COPILOT-CACHE] Creator '{creator_id}' not found, defaulting to copilot_mode=True"
                )
        finally:
            session.close()
    except Exception as e:
        logger.error(f"[COPILOT-CACHE] DB error: {e} - defaulting to copilot_mode=True")

    # Evict stale entries before adding new one
    _evict_stale_copilot_cache(current_time)
    _copilot_mode_cache[creator_id] = (copilot_enabled, current_time)
    return copilot_enabled


async def _check_telegram_duplicate(update_id: int) -> bool:
    """Check if this update was already processed."""
    import time

    current_time = time.time()

    async with _telegram_dedup_lock:
        expired = [
            uid
            for uid, ts in _telegram_processed_updates.items()
            if current_time - ts > TELEGRAM_DEDUP_TTL
        ]
        for uid in expired:
            del _telegram_processed_updates[uid]

        if update_id in _telegram_processed_updates:
            logger.warning(f"Telegram duplicate update_id={update_id} - skipping")
            return True

        _telegram_processed_updates[update_id] = current_time
        return False


async def send_telegram_direct(
    chat_id: int, text: str, bot_token: str, reply_markup: dict = None
) -> dict:
    """Send Telegram message directly."""
    telegram_api = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(telegram_api, json=payload)
        return response.json()


async def send_telegram_via_proxy(
    chat_id: int, text: str, bot_token: str, reply_markup: dict = None
) -> dict:
    """Send Telegram message via Cloudflare Worker proxy."""
    headers = {}
    if TELEGRAM_PROXY_SECRET:
        headers["X-Telegram-Proxy-Secret"] = TELEGRAM_PROXY_SECRET

    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        params["reply_markup"] = reply_markup

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            TELEGRAM_PROXY_URL,
            json={"bot_token": bot_token, "method": "sendMessage", "params": params},
            headers=headers,
        )
        return response.json()


async def send_telegram_message(
    chat_id: int, text: str, bot_token: str, reply_markup: dict = None
) -> dict:
    """Send Telegram message - direct first, proxy as fallback."""
    import time

    _t_start = time.time()

    try:
        logger.info(f"Sending Telegram message directly to chat {chat_id}")
        result = await send_telegram_direct(chat_id, text, bot_token, reply_markup)
        logger.info(f"Telegram direct call took {time.time() - _t_start:.2f}s")

        if result.get("ok"):
            return result
        else:
            logger.warning(f"Direct Telegram failed: {result}, trying proxy...")
    except Exception as e:
        logger.warning(f"Direct Telegram error: {e}, trying proxy...")

    if TELEGRAM_PROXY_URL:
        try:
            logger.info(f"Fallback: sending via proxy to chat {chat_id}")
            result = await send_telegram_via_proxy(chat_id, text, bot_token, reply_markup)
            logger.info(f"Telegram proxy fallback took {time.time() - _t_start:.2f}s")
            return result
        except Exception as e:
            logger.error(f"Proxy also failed: {e}")
            return {"ok": False, "error": str(e)}

    return {"ok": False, "error": "Direct failed and no proxy configured"}


@router.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    Receive Telegram webhook updates (POST).
    Supports multi-bot setup via telegram registry.
    """
    # Verify Telegram webhook secret token if configured
    secret_token = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    if secret_token:
        header_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if header_token != secret_token:
            raise HTTPException(status_code=403, detail="Invalid secret token")

    from core.dm_agent_v2 import get_dm_agent
    from core.telegram_registry import get_telegram_registry

    try:
        payload = await request.json()
        logger.info(f"Telegram webhook received: {payload}")

        update_id = payload.get("update_id")
        if update_id and await _check_telegram_duplicate(update_id):
            return {"status": "ok", "message": "Duplicate update - already processed"}

        # Handle callback_query (button clicks) - simplified, full booking in main.py for now
        callback_query = payload.get("callback_query")
        if callback_query:
            # Import the booking handler from main for now
            try:
                from api.main import handle_telegram_booking_callback

                return await handle_telegram_booking_callback(callback_query)
            except ImportError:
                logger.warning("Booking callback handler not available")
                return {"status": "ok", "message": "Callback not handled"}

        message = payload.get("message", {})
        if not message:
            return {"status": "ok", "message": "No message in update"}

        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")
        sender = message.get("from", {})
        sender_id = str(sender.get("id", "unknown"))
        sender_name = sender.get("first_name", "") + " " + sender.get("last_name", "")
        sender_name = sender_name.strip() or sender.get("username", "Usuario")

        if not chat_id or not text:
            return {"status": "ok", "message": "No chat_id or text"}

        registry = get_telegram_registry()
        bot_id = None
        creator_id = None
        bot_token = None

        bots = registry.list_bots()
        if bots:
            for bot in bots:
                if bot.get("is_active"):
                    bot_id = bot.get("bot_id")
                    creator_id = bot.get("creator_id")
                    bot_token = registry.get_bot_token(bot_id)
                    logger.info(f"Using registered bot {bot_id} for creator {creator_id}")
                    break

        if not creator_id:
            creator_id = os.getenv("DEFAULT_CREATOR_ID", "stefano_auto")
            bot_token = TELEGRAM_BOT_TOKEN
            logger.info(f"Using fallback creator_id={creator_id}")

        try:
            import time

            _t_webhook_start = time.time()

            agent = get_dm_agent(creator_id)
            _t_agent_ready = time.time()
            logger.info(f"Agent ready in {_t_agent_ready - _t_webhook_start:.3f}s")

            first_name = sender.get("first_name", "")
            last_name = sender.get("last_name", "")
            full_name = f"{first_name} {last_name}".strip()

            response = await agent.process_dm(
                message=text,
                sender_id=f"tg_{sender_id}",
                metadata={
                    "message_id": str(message.get("message_id", "")),
                    "username": sender_name,
                    "name": full_name,
                    "platform": "telegram",
                },
            )
            _t_process_done = time.time()
            logger.info(f"process_dm completed in {_t_process_done - _t_agent_ready:.2f}s")

            bot_reply = response.content
            intent = response.intent if response.intent else "unknown"

            logger.info(
                f"Telegram DM from {sender_name} ({sender_id}): '{text[:50]}' -> intent={intent}"
            )

            # Fire-and-forget identity resolution
            try:
                from core.identity_resolver import resolve_identity
                from api.services.db_service import get_or_create_lead
                tg_lead = get_or_create_lead(
                    creator_id, f"tg_{sender_id}", platform="telegram",
                    username=sender_name, full_name=full_name,
                )
                if tg_lead:
                    asyncio.create_task(resolve_identity(creator_id, tg_lead["id"], "telegram"))
            except Exception as ir_err:
                logger.debug(f"[TG] Identity resolution skipped: {ir_err}")

            _t_copilot_start = time.time()
            copilot_enabled = _get_copilot_mode_cached(creator_id)
            logger.info(f"Copilot mode check took {time.time() - _t_copilot_start:.3f}s (cached)")

            if copilot_enabled:
                logger.info(
                    "COPILOT MODE ACTIVE - NOT sending auto-reply, creating pending response"
                )
                from core.copilot_service import get_copilot_service

                copilot = get_copilot_service()
                # Carry Best-of-N candidates from DM response metadata
                _tg_msg_meta = {}
                if hasattr(response, "metadata") and response.metadata and response.metadata.get("best_of_n"):
                    _tg_msg_meta["best_of_n"] = response.metadata["best_of_n"]

                pending = await copilot.create_pending_response(
                    creator_id=creator_id,
                    lead_id="",
                    follower_id=f"tg_{sender_id}",
                    platform="telegram",
                    user_message=text,
                    user_message_id=str(message.get("message_id", "")),
                    suggested_response=bot_reply,
                    intent=intent,
                    confidence=response.confidence if hasattr(response, "confidence") else 0.9,
                    username=sender_name,
                    full_name=full_name,
                    msg_metadata=_tg_msg_meta if _tg_msg_meta else None,
                )
                logger.info(f"[Copilot] Created pending response {pending.id}")

                return {
                    "status": "ok",
                    "chat_id": chat_id,
                    "intent": intent,
                    "creator_id": creator_id,
                    "bot_id": bot_id,
                    "copilot_mode": True,
                    "pending_response_id": pending.id,
                    "response_sent": False,
                }

            # AUTOPILOT MODE
            logger.info("AUTOPILOT MODE - sending auto-reply immediately")
            reply_markup = None
            if response.metadata and "telegram_keyboard" in response.metadata:
                keyboard_data = response.metadata["telegram_keyboard"]
                if keyboard_data:
                    inline_keyboard = []
                    for button in keyboard_data:
                        btn = {"text": button.get("text", "")}
                        if "callback_data" in button:
                            btn["callback_data"] = button["callback_data"]
                        elif "url" in button:
                            btn["url"] = button["url"]
                        inline_keyboard.append([btn])
                    reply_markup = {"inline_keyboard": inline_keyboard}

            telegram_sent = False
            if bot_reply and bot_token:
                try:
                    _t_tg_start = time.time()
                    result = await send_telegram_message(
                        chat_id, bot_reply, bot_token, reply_markup
                    )
                    _t_tg_end = time.time()
                    if result.get("ok"):
                        telegram_sent = True
                        logger.info(
                            f"Telegram sent in {_t_tg_end - _t_tg_start:.2f}s to chat {chat_id}"
                        )
                    else:
                        logger.error(f"Telegram send failed: {result}")
                except Exception as e:
                    logger.error(f"Telegram send error: {e}")

            _t_webhook_end = time.time()
            logger.info(f"TOTAL webhook processing: {_t_webhook_end - _t_webhook_start:.2f}s")

            return {
                "status": "ok",
                "chat_id": chat_id,
                "intent": intent,
                "creator_id": creator_id,
                "bot_id": bot_id,
                "copilot_mode": False,
                "response_sent": telegram_sent,
            }

        except Exception as e:
            logger.error(f"Error processing Telegram message: {type(e).__name__}: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            return {"status": "error", "detail": "Internal error processing message"}

    except Exception as e:
        logger.error(f"Error in Telegram webhook: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="Internal error processing Telegram webhook")


@router.post("/telegram/webhook")
async def telegram_webhook_legacy(request: Request):
    """Legacy endpoint - redirects to /webhook/telegram"""
    return await telegram_webhook(request)


# =============================================================================
# EVOLUTION API WEBHOOK (WhatsApp via Baileys)
# =============================================================================

# Instance name → creator_id mapping
# TODO: Move to DB once multi-creator is needed
EVOLUTION_INSTANCE_MAP: Dict[str, str] = {
    "stefano-fitpack": "stefano_bonanno",
    "iris-bertran": "iris_bertran",
}

# Guard: prevent duplicate WA onboarding pipeline launches
_wa_pipeline_running: set = set()

# Dedup: Evolution/Baileys sends messages.upsert twice per message.
# Track processed message IDs with timestamps to skip duplicates.
_evo_processed_messages: Dict[str, float] = {}
_EVO_DEDUP_TTL = 60  # seconds


def _evo_is_duplicate(message_id: str) -> bool:
    """Return True if this message_id was already processed (dedup)."""
    import time

    now = time.time()

    # Purge expired entries every call (dict is small, O(n) is fine)
    expired = [k for k, t in _evo_processed_messages.items() if now - t > _EVO_DEDUP_TTL]
    for k in expired:
        del _evo_processed_messages[k]

    if message_id in _evo_processed_messages:
        return True

    _evo_processed_messages[message_id] = now
    return False


@router.post("/webhook/whatsapp/evolution")
async def evolution_webhook(request: Request):
    """
    Receive webhook events from Evolution API (WhatsApp via Baileys).

    Events handled:
    - messages.upsert: New incoming message → generate suggestion → save as pending
      (COPILOT mode: does NOT auto-send. Creator approves from dashboard.)
    - connection.update: Instance connected/disconnected
    - qrcode.updated: New QR code generated

    All other events are acknowledged but ignored.
    """
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ok", "ignored": "invalid_json"}

    event = payload.get("event", "")
    instance = payload.get("instance", "")

    # Log non-message events briefly
    if event == "connection.update":
        state = payload.get("data", {}).get("state", "unknown")
        logger.info(f"[EVO:{instance}] Connection update: {state}")

        if state == "open":
            creator_id = EVOLUTION_INSTANCE_MAP.get(instance)
            if creator_id and creator_id not in _wa_pipeline_running:
                _wa_pipeline_running.add(creator_id)

                async def _run_wa_pipeline():
                    try:
                        from services.whatsapp_onboarding_pipeline import (
                            WhatsAppOnboardingPipeline,
                        )

                        pipeline = WhatsAppOnboardingPipeline(creator_id, instance)
                        result = await pipeline.run()
                        logger.info(
                            f"[WA-PIPELINE] Completed for {creator_id}: "
                            f"{result.get('status', 'unknown')}"
                        )
                    except Exception as e:
                        logger.error(f"[WA-PIPELINE] Failed for {creator_id}: {e}")
                    finally:
                        _wa_pipeline_running.discard(creator_id)

                asyncio.create_task(_run_wa_pipeline())
                logger.info(
                    f"[EVO:{instance}] WhatsApp onboarding pipeline started for {creator_id}"
                )

        return {"status": "ok", "event": event, "state": state}

    if event == "qrcode.updated":
        logger.info(f"[EVO:{instance}] QR code updated")
        return {"status": "ok", "event": event}

    # Only process incoming messages
    if event != "messages.upsert":
        return {"status": "ok", "ignored": event}

    data = payload.get("data", {})
    key = data.get("key", {})

    from_me = key.get("fromMe", False)

    # Extract message text (multiple possible locations in Baileys format)
    message_obj = data.get("message", {})
    text = (
        message_obj.get("conversation")
        or (message_obj.get("extendedTextMessage") or {}).get("text")
        or (message_obj.get("imageMessage") or {}).get("caption")
        or (message_obj.get("videoMessage") or {}).get("caption")
        or ""
    )

    # Detect ALL media types from Baileys message object
    audio_obj = message_obj.get("audioMessage") or message_obj.get("pttMessage")
    image_obj = message_obj.get("imageMessage")
    video_obj = message_obj.get("videoMessage")
    sticker_obj = message_obj.get("stickerMessage")
    document_obj = message_obj.get("documentMessage")

    # Determine the primary media type (priority: audio > video > image > sticker > document)
    detected_media_type = None
    if audio_obj:
        detected_media_type = "audio"
    elif video_obj:
        detected_media_type = "video"
    elif image_obj:
        detected_media_type = "image"
    elif sticker_obj:
        detected_media_type = "sticker"
    elif document_obj:
        detected_media_type = "document"

    # Process media: download from WhatsApp CDN → Cloudinary → (transcribe if audio)
    media_result = None
    audio_transcription = None
    if detected_media_type:
        try:
            media_result = await _download_evolution_media(instance, data, detected_media_type)
            if detected_media_type == "audio" and media_result.get("transcription"):
                audio_transcription = media_result["transcription"]
        except Exception as media_err:
            logger.error(f"[EVO:{instance}] Media processing failed ({detected_media_type}): {media_err}")

        # If no text yet, set a descriptive placeholder so the message isn't dropped
        if not text.strip():
            if detected_media_type == "audio":
                # Prefer clean_text from audio intelligence over raw transcription
                ai = media_result.get("audio_intel", {}) if media_result else {}
                display_text = ai.get("clean_text") or ai.get("summary") or audio_transcription
                text = f"[\U0001f3a4 Audio]: {display_text}" if display_text else "[\U0001f3a4 Audio message]"
            else:
                placeholder_map = {
                    "image": "[\U0001f4f7 Photo]",
                    "video": "[\U0001f3ac Video]",
                    "sticker": "[\U0001f3f7\ufe0f Sticker]",
                    "document": "[\U0001f4c4 Document]",
                }
                text = placeholder_map.get(detected_media_type, "[\U0001f4ce Media]")

    if not text.strip():
        return {"status": "ok", "ignored": "no_text"}

    # Extract sender info
    remote_jid = key.get("remoteJid", "")
    sender_number = remote_jid.replace("@s.whatsapp.net", "").replace("@g.us", "").replace("@lid", "")
    push_name = data.get("pushName", "")
    message_id = key.get("id", "")

    # Dedup: Baileys sends messages.upsert twice per message
    if not message_id or _evo_is_duplicate(message_id):
        return {"status": "ok", "ignored": "duplicate"}

    # Resolve creator from instance
    creator_id = EVOLUTION_INSTANCE_MAP.get(instance)
    if not creator_id:
        logger.warning(f"[EVO:{instance}] Unknown instance, no creator mapping")
        return {"status": "ok", "ignored": "unknown_instance"}

    # fromMe=true → Creator's own outgoing message. Save to DB but do NOT
    # generate a DM agent response (it's not an incoming lead message).
    if from_me:
        follower_id = f"wa_{sender_number}"
        logger.info(
            f"[EVO:{instance}] Outgoing (fromMe) to {sender_number}: {text[:80]}"
        )
        # Build outgoing msg_metadata from media_result
        outgoing_meta = None
        if detected_media_type:
            outgoing_meta = {
                "type": detected_media_type,
                "platform": "whatsapp",
                "source": "evolution_outgoing",
            }
            if media_result and media_result.get("url"):
                outgoing_meta["url"] = media_result["url"]
            if audio_transcription:
                outgoing_meta["transcription"] = audio_transcription
            if detected_media_type == "audio":
                if media_result and media_result.get("audio_intel"):
                    outgoing_meta["audio_intel"] = media_result["audio_intel"]
                    for k in ("transcript_raw", "transcript_full", "transcript_summary"):
                        if media_result.get(k):
                            outgoing_meta[k] = media_result[k]
                if isinstance(audio_obj, dict):
                    duration = audio_obj.get("seconds") or audio_obj.get("duration")
                    if duration:
                        outgoing_meta["duration"] = duration

        asyncio.create_task(
            _save_evolution_outgoing_message(
                instance=instance,
                creator_id=creator_id,
                follower_id=follower_id,
                text=text,
                message_id=message_id,
                push_name=push_name,
                msg_metadata=outgoing_meta,
            )
        )
        return {
            "status": "ok",
            "event": event,
            "instance": instance,
            "sender": sender_number,
            "saved_outgoing": True,
        }

    logger.info(
        f"[EVO:{instance}] Message from {push_name} ({sender_number}): {text[:80]}"
    )

    # Build metadata for media messages
    msg_metadata = None
    if detected_media_type:
        msg_metadata = {
            "type": detected_media_type,
            "platform": "whatsapp",
            "source": "evolution",
        }
        # Cloudinary permanent URL (preferred) or WhatsApp CDN URL (expires)
        if media_result and media_result.get("url"):
            msg_metadata["url"] = media_result["url"]
        # Audio-specific fields
        if detected_media_type == "audio":
            if audio_transcription:
                msg_metadata["transcription"] = audio_transcription
            # Audio Intelligence structured data (summary, entities, clean_text)
            if media_result and media_result.get("audio_intel"):
                msg_metadata["audio_intel"] = media_result["audio_intel"]
                # Legacy fields for backward compat
                for k in ("transcript_raw", "transcript_full", "transcript_summary"):
                    if media_result.get(k):
                        msg_metadata[k] = media_result[k]
            if isinstance(audio_obj, dict):
                duration = audio_obj.get("seconds") or audio_obj.get("duration")
                if duration:
                    msg_metadata["duration"] = duration
        # Video duration
        elif detected_media_type == "video" and isinstance(video_obj, dict):
            duration = video_obj.get("seconds") or video_obj.get("duration")
            if duration:
                msg_metadata["duration"] = duration
        # Sticker → render as sticker (smaller display)
        elif detected_media_type == "sticker":
            msg_metadata["render_as_sticker"] = True
        # Document filename
        elif detected_media_type == "document" and isinstance(document_obj, dict):
            filename = document_obj.get("fileName") or document_obj.get("title")
            if filename:
                msg_metadata["filename"] = filename

    # Process with DM agent in background so webhook returns 200 fast
    asyncio.create_task(
        _process_evolution_message_safe(
            instance=instance,
            creator_id=creator_id,
            sender_number=sender_number,
            push_name=push_name,
            text=text,
            message_id=message_id,
            msg_metadata=msg_metadata,
        )
    )

    return {
        "status": "ok",
        "event": event,
        "instance": instance,
        "sender": sender_number,
        "processing": True,
    }


async def _download_evolution_media(instance: str, data: dict, media_type: str) -> dict:
    """
    Download any media type from Evolution API, upload to Cloudinary,
    and optionally transcribe (audio only).

    Uses Evolution's getBase64FromMediaMessage endpoint to fetch media bytes,
    uploads to Cloudinary for permanent storage, then transcribes audio via Whisper.

    Args:
        instance: Evolution API instance name
        data: Full webhook payload (contains message + key)
        media_type: "audio", "image", "video", "sticker", "document"

    Returns dict with keys: url (str|None), mimetype (str), transcription (str, audio only)
    """
    import base64
    import tempfile

    from services.evolution_api import EVOLUTION_API_KEY, EVOLUTION_API_URL

    result = {"transcription": "", "url": None, "mimetype": "application/octet-stream"}

    if not EVOLUTION_API_URL:
        logger.warning(f"[EVO:{instance}] Cannot fetch media: EVOLUTION_API_URL not set")
        return result

    message_obj = data.get("message", {})
    key = data.get("key", {})

    # Build the payload for getBase64FromMediaMessage
    media_payload = {"message": {"key": key, "message": message_obj}}

    url = f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{instance}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=media_payload, headers=headers)

            if resp.status_code >= 400:
                logger.error(
                    f"[EVO:{instance}] getBase64FromMediaMessage failed ({media_type}): "
                    f"HTTP {resp.status_code} {resp.text[:200]}"
                )
                return result

            resp_data = resp.json()
            b64_data = resp_data.get("base64", "")
            mimetype = resp_data.get("mimetype", "application/octet-stream")
            result["mimetype"] = mimetype

            if not b64_data:
                logger.warning(f"[EVO:{instance}] No base64 data in {media_type} response")
                return result

            # Determine file extension from mimetype
            ext_map = {
                # Audio
                "audio/ogg": ".ogg",
                "audio/ogg; codecs=opus": ".ogg",
                "audio/mpeg": ".mp3",
                "audio/mp4": ".m4a",
                "audio/wav": ".wav",
                "audio/webm": ".webm",
                # Image
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/webp": ".webp",
                "image/gif": ".gif",
                # Video
                "video/mp4": ".mp4",
                "video/3gpp": ".3gp",
                "video/webm": ".webm",
                # Document
                "application/pdf": ".pdf",
                "application/msword": ".doc",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            }
            ext = ext_map.get(mimetype.split(";")[0].strip(), ".bin")

            # Decode base64 and write to temp file
            media_bytes = base64.b64decode(b64_data)

            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(media_bytes)
                tmp_path = tmp.name

            try:
                # Upload to Cloudinary for permanent storage
                try:
                    from services.cloudinary_service import get_cloudinary_service

                    cloud = get_cloudinary_service()
                    if cloud.is_configured:
                        sender = key.get("remoteJid", "unknown").replace("@s.whatsapp.net", "")
                        # Cloudinary maps: audio→video, sticker→image, document→raw
                        cloud_media_type = media_type
                        if media_type == "sticker":
                            cloud_media_type = "image"
                        elif media_type == "document":
                            cloud_media_type = "raw"

                        upload = cloud.upload_from_file(
                            file_path=tmp_path,
                            media_type=cloud_media_type,
                            folder=f"clonnect/{instance}/{media_type}",
                            tags=["whatsapp", media_type, sender],
                        )
                        if upload.success and upload.url:
                            result["url"] = upload.url
                            logger.info(
                                f"[EVO:{instance}] {media_type} uploaded to Cloudinary: {upload.url}"
                            )
                        else:
                            logger.warning(
                                f"[EVO:{instance}] Cloudinary upload failed ({media_type}): {upload.error}"
                            )
                except Exception as cloud_err:
                    logger.warning(f"[EVO:{instance}] Cloudinary upload skipped: {cloud_err}")

                # Transcribe audio with cascade (Groq → Gemini → OpenAI) + Audio Intelligence
                if media_type == "audio":
                    try:
                        from ingestion.transcriber import get_transcriber

                        transcriber = get_transcriber()
                        transcript = await transcriber.transcribe_file(tmp_path, language="es")
                        if transcript and transcript.full_text.strip():
                            raw_text = transcript.full_text.strip()
                            result["transcription"] = raw_text

                            # Audio Intelligence Pipeline (4-layer) — same as Instagram
                            try:
                                from services.audio_intelligence import get_audio_intelligence

                                intel = get_audio_intelligence()
                                ai_result = await intel.process(
                                    raw_text=raw_text,
                                    language="es",
                                    role="user",
                                )
                                result["audio_intel"] = ai_result.to_metadata()
                                legacy = ai_result.to_legacy_fields()
                                result.update(legacy)
                            except Exception as intel_err:
                                logger.warning(f"[EVO:{instance}] Audio intelligence failed: {intel_err}")
                    except Exception as whisper_err:
                        logger.error(f"[EVO:{instance}] Whisper transcription failed: {whisper_err}")

                return result
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    except Exception as e:
        logger.error(f"[EVO:{instance}] Media download error ({media_type}): {e}")
        return result


async def _save_evolution_outgoing_message(
    instance: str,
    creator_id: str,
    follower_id: str,
    text: str,
    message_id: str,
    push_name: str,
    msg_metadata: dict = None,
):
    """
    Save a creator's outgoing WhatsApp message (fromMe=true) to the DB.

    This captures messages the creator sends directly from their phone so the
    dashboard shows the complete conversation (incoming + outgoing).
    No DM agent processing — this is not a lead message.
    """
    try:
        from datetime import datetime, timezone

        from api.database import SessionLocal
        from api.models import Creator, Lead, Message

        db = SessionLocal()
        try:
            # Find the creator (Creator.name stores the creator_id string)
            creator = db.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                logger.warning(f"[EVO:{instance}] Outgoing: creator {creator_id} not found")
                return

            # Find or create the lead for this remoteJid
            lead = db.query(Lead).filter(
                Lead.creator_id == creator.id,
                Lead.platform_user_id == follower_id,
            ).first()

            if not lead:
                import uuid

                sender_number = follower_id.removeprefix("wa_")
                # push_name here is the CREATOR's name (fromMe=true), not the contact's.
                # Use phone number as placeholder; inbound handler will set the real name.
                lead = Lead(
                    id=uuid.uuid4(),
                    creator_id=creator.id,
                    platform="whatsapp",
                    platform_user_id=follower_id,
                    username=f"+{sender_number}",
                    full_name=f"+{sender_number}",
                    phone=f"+{sender_number}" if sender_number else None,
                    source="whatsapp_dm",
                    status="nuevo",
                    purchase_intent=0.0,
                )
                db.add(lead)
                db.flush()
                logger.info(f"[EVO:{instance}] Outgoing: created lead {follower_id}")

            # Audio Intelligence Pipeline (outgoing — creator's voice)
            if (
                msg_metadata
                and msg_metadata.get("type") == "audio"
                and msg_metadata.get("transcription")
            ):
                try:
                    from services.audio_intelligence import get_audio_intelligence

                    raw_text = msg_metadata["transcription"]
                    intel = get_audio_intelligence()
                    ai_result = await intel.process(
                        raw_text=raw_text,
                        duration_seconds=msg_metadata.get("duration", 0),
                        language="es",
                        role="assistant",
                    )
                    legacy = ai_result.to_legacy_fields()
                    msg_metadata.update(legacy)
                    msg_metadata["audio_intel"] = ai_result.to_metadata()
                    text = f"[\U0001f3a4 Audio]: {ai_result.clean_text or raw_text}"
                    logger.info(
                        f"[EVO:{instance}] Outgoing AudioIntel: "
                        f"{ai_result.summary[:60]}..."
                    )
                except Exception as e:
                    logger.warning(f"[EVO:{instance}] Outgoing audio intelligence failed: {e}")

            # Save the outgoing message (role=assistant, same as creator manual sends)
            import uuid

            msg_meta = {"source": "evolution_outgoing", "platform": "whatsapp"}
            if msg_metadata:
                msg_meta.update(msg_metadata)

            msg = Message(
                id=uuid.uuid4(),
                lead_id=lead.id,
                role="assistant",
                content=text,
                status="sent",
                approved_by="creator_manual",
                platform_message_id=message_id,
                msg_metadata=msg_meta,
            )
            db.add(msg)

            # Update last_contact_at so the lead appears fresh in the dashboard
            lead.last_contact_at = datetime.now(timezone.utc)

            # Auto-discard pending copilot suggestions for this lead
            # Pass creator_response so resolved_externally learning kicks in
            try:
                from core.copilot_service import get_copilot_service

                get_copilot_service().auto_discard_pending_for_lead(
                    lead.id, session=db,
                    creator_response=text,
                    creator_id=creator_id,
                )
            except Exception as e:
                logger.warning(f"[EVO:{instance}] Auto-discard failed: {e}")

            db.commit()
            logger.info(
                f"[EVO:{instance}] Saved outgoing msg {message_id} for {follower_id}: "
                f"{text[:60]}"
            )
        finally:
            db.close()

    except Exception as e:
        logger.error(f"[EVO:{instance}] Error saving outgoing message: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def _process_evolution_message_safe(
    instance: str,
    creator_id: str,
    sender_number: str,
    push_name: str,
    text: str,
    message_id: str,
    msg_metadata: dict = None,
):
    """
    Process an incoming Evolution API message in COPILOT mode.

    - Generates a suggested response via the DM agent
    - Saves user message + suggestion as pending_approval in DB
    - Does NOT auto-send — creator approves from dashboard
    """
    try:
        from core.copilot_service import get_copilot_service
        from core.dm_agent_v2 import get_dm_agent

        follower_id = f"wa_{sender_number}"

        # Audio Intelligence already ran in _download_evolution_media() (Run 1).
        # Use existing audio_intel for display text if available.
        if (
            msg_metadata
            and msg_metadata.get("type") == "audio"
            and msg_metadata.get("audio_intel")
        ):
            ai = msg_metadata["audio_intel"]
            clean = ai.get("clean_text") or msg_metadata.get("transcription", "")
            text = f"[\U0001f3a4 Audio]: {clean}"

        # Generate suggestion via DM agent
        agent = get_dm_agent(creator_id)
        dm_metadata = {
            "message_id": message_id,
            "username": push_name or "amigo",
            "platform": "whatsapp",
            "source": "evolution",
        }
        # Pass audio intelligence to DM agent for enriched context
        if msg_metadata and msg_metadata.get("audio_intel"):
            dm_metadata["audio_intel"] = msg_metadata["audio_intel"]
        response = await agent.process_dm(
            message=text,
            sender_id=follower_id,
            metadata=dm_metadata,
        )

        response_text = response.content if hasattr(response, "content") else str(response)
        intent = str(response.intent) if hasattr(response, "intent") else "unknown"
        confidence = response.confidence if hasattr(response, "confidence") else 0.0

        # Save as pending response (copilot mode — no auto-send)
        copilot = get_copilot_service()

        # Merge Best-of-N candidates from DM response into existing metadata
        if not msg_metadata:
            msg_metadata = {}
        if hasattr(response, "metadata") and response.metadata and response.metadata.get("best_of_n"):
            msg_metadata["best_of_n"] = response.metadata["best_of_n"]

        pending = await copilot.create_pending_response(
            creator_id=creator_id,
            lead_id="",
            follower_id=follower_id,
            platform="whatsapp",
            user_message=text,
            user_message_id=message_id,
            suggested_response=response_text,
            intent=intent,
            confidence=confidence,
            username=push_name or "",
            full_name=push_name or "",
            msg_metadata=msg_metadata if msg_metadata else None,
        )

        # Fetch and save WhatsApp profile picture (fire-and-forget style)
        try:
            from api.database import SessionLocal
            from api.models import Lead
            from services.evolution_api import fetch_profile_picture

            pic_url = await fetch_profile_picture(instance, sender_number)
            if pic_url:
                db = SessionLocal()
                try:
                    lead = db.query(Lead).filter(
                        Lead.platform_user_id == follower_id
                    ).first()
                    if lead and not lead.profile_pic_url:
                        lead.profile_pic_url = pic_url
                        db.commit()
                        logger.info(f"[EVO:{instance}] Saved profile pic for {sender_number}")
                finally:
                    db.close()
        except Exception as pic_err:
            logger.debug(f"[EVO:{instance}] Profile pic fetch skipped: {pic_err}")

        logger.info(
            f"[EVO:{instance}] Pending response {pending.id} for {sender_number}: "
            f"intent={intent} conf={confidence:.0%} text={response_text[:80]}"
        )

    except Exception as e:
        logger.error(
            f"[EVO:{instance}] Error processing message from {sender_number}: {e}"
        )
        import traceback
        logger.error(traceback.format_exc())
