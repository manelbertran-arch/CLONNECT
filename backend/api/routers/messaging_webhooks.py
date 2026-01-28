"""
Messaging webhooks router (Instagram, WhatsApp, Telegram).
Extracted from main.py following TDD methodology.
"""
import asyncio
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
    Processes incoming DMs with DMResponderAgent and sends automatic responses.
    """
    from core.instagram_handler import get_instagram_handler

    logger.warning("=" * 60)
    logger.warning("========== INSTAGRAM WEBHOOK HIT V6 ==========")
    logger.warning("=" * 60)

    try:
        payload = await request.json()
        signature = request.headers.get("X-Hub-Signature-256", "")

        handler = get_instagram_handler()
        result = await handler.handle_webhook(payload, signature)

        logger.info(f"Instagram webhook processed: {result.get('messages_processed', 0)} messages")
        return result

    except Exception as e:
        logger.error(f"Error processing Instagram webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Legacy endpoint (backwards compatibility)
@router.get("/instagram/webhook")
async def instagram_webhook_verify_legacy(request: Request):
    """Legacy endpoint - redirect to /webhook/instagram"""
    return await instagram_webhook_verify(request)


@router.post("/instagram/webhook")
async def instagram_webhook_receive_legacy(request: Request):
    """Legacy endpoint - redirect to /webhook/instagram"""
    return await instagram_webhook_receive(request)


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
        raise HTTPException(status_code=500, detail=str(e))


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
    """
    from core.whatsapp import get_whatsapp_handler

    logger.warning("========== WHATSAPP WEBHOOK HIT ==========")

    try:
        payload = await request.json()
        signature = request.headers.get("X-Hub-Signature-256", "")

        handler = get_whatsapp_handler()
        result = await handler.handle_webhook(payload, signature)

        logger.info(f"WhatsApp webhook processed: {result.get('messages_processed', 0)} messages")
        return result

    except Exception as e:
        logger.error(f"Error processing WhatsApp webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
                logger.info(f"[COPILOT-CACHE] MISS for {creator_id}: loaded copilot_mode={copilot_enabled} from DB")
            else:
                logger.warning(f"[COPILOT-CACHE] Creator '{creator_id}' not found, defaulting to copilot_mode=True")
        finally:
            session.close()
    except Exception as e:
        logger.error(f"[COPILOT-CACHE] DB error: {e} - defaulting to copilot_mode=True")

    _copilot_mode_cache[creator_id] = (copilot_enabled, current_time)
    return copilot_enabled


async def _check_telegram_duplicate(update_id: int) -> bool:
    """Check if this update was already processed."""
    import time

    current_time = time.time()

    async with _telegram_dedup_lock:
        expired = [uid for uid, ts in _telegram_processed_updates.items() if current_time - ts > TELEGRAM_DEDUP_TTL]
        for uid in expired:
            del _telegram_processed_updates[uid]

        if update_id in _telegram_processed_updates:
            logger.warning(f"Telegram duplicate update_id={update_id} - skipping")
            return True

        _telegram_processed_updates[update_id] = current_time
        return False


async def send_telegram_direct(chat_id: int, text: str, bot_token: str, reply_markup: dict = None) -> dict:
    """Send Telegram message directly."""
    telegram_api = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup

    async with httpx.AsyncClient() as client:
        response = await client.post(telegram_api, json=payload)
        return response.json()


async def send_telegram_via_proxy(chat_id: int, text: str, bot_token: str, reply_markup: dict = None) -> dict:
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


async def send_telegram_message(chat_id: int, text: str, bot_token: str, reply_markup: dict = None) -> dict:
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
    from core.dm_agent import get_dm_agent
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
                sender_id=f"tg_{sender_id}",
                message_text=text,
                message_id=str(message.get("message_id", "")),
                username=sender_name,
                name=full_name,
            )
            _t_process_done = time.time()
            logger.info(f"process_dm completed in {_t_process_done - _t_agent_ready:.2f}s")

            bot_reply = response.response_text
            intent = response.intent.value if response.intent else "unknown"

            logger.info(f"Telegram DM from {sender_name} ({sender_id}): '{text[:50]}' -> intent={intent}")

            _t_copilot_start = time.time()
            copilot_enabled = _get_copilot_mode_cached(creator_id)
            logger.info(f"Copilot mode check took {time.time() - _t_copilot_start:.3f}s (cached)")

            if copilot_enabled:
                logger.info("COPILOT MODE ACTIVE - NOT sending auto-reply, creating pending response")
                from core.copilot_service import get_copilot_service

                copilot = get_copilot_service()
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
                    result = await send_telegram_message(chat_id, bot_reply, bot_token, reply_markup)
                    _t_tg_end = time.time()
                    if result.get("ok"):
                        telegram_sent = True
                        logger.info(f"Telegram sent in {_t_tg_end - _t_tg_start:.2f}s to chat {chat_id}")
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
            return {"status": "error", "detail": str(e)}

    except Exception as e:
        logger.error(f"Error in Telegram webhook: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/telegram/webhook")
async def telegram_webhook_legacy(request: Request):
    """Legacy endpoint - redirects to /webhook/telegram"""
    return await telegram_webhook(request)
