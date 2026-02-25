"""
Messaging webhooks router — Telegram platform.
Extracted from messaging_webhooks.py following TDD methodology.
"""

import asyncio
import json
import logging
import os
from typing import Dict

import httpx
from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)
router = APIRouter(tags=["messaging-webhooks"])


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
