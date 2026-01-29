"""
Telegram Router - Telegram bot management and status endpoints
Extracted from main.py as part of refactoring
"""
import logging
import os
import socket
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Core imports
from core.telegram_registry import get_telegram_registry

# Environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL", "")
TELEGRAM_PROXY_SECRET = os.getenv("TELEGRAM_PROXY_SECRET", "")

router = APIRouter(prefix="/telegram", tags=["telegram"])


# ---------------------------------------------------------
# PYDANTIC MODELS
# ---------------------------------------------------------
class RegisterBotRequest(BaseModel):
    """Request to register a new Telegram bot."""

    creator_id: str
    bot_token: str
    bot_username: Optional[str] = None
    set_webhook: bool = True


# ---------------------------------------------------------
# TELEGRAM STATUS ENDPOINTS
# ---------------------------------------------------------
@router.get("/status")
async def telegram_status():
    """Obtener estado de la integración de Telegram"""
    token_configured = bool(TELEGRAM_BOT_TOKEN)
    token_preview = (
        f"{TELEGRAM_BOT_TOKEN[:10]}...{TELEGRAM_BOT_TOKEN[-5:]}"
        if token_configured and len(TELEGRAM_BOT_TOKEN) > 15
        else "NOT SET"
    )

    # Proxy configuration check - proxy is used if URL is set (secret is optional but recommended)
    proxy_url_set = bool(TELEGRAM_PROXY_URL)
    proxy_secret_set = bool(TELEGRAM_PROXY_SECRET)
    proxy_will_be_used = proxy_url_set  # Proxy is used if URL is configured

    # Build status response
    status_response = {
        "status": "ok" if token_configured else "warning",
        "bot_token_configured": token_configured,
        "bot_token_preview": token_preview,
        "proxy_url_configured": proxy_url_set,
        "proxy_secret_configured": proxy_secret_set,
        "proxy_configured": proxy_url_set,  # Now only requires URL
        "proxy_url": TELEGRAM_PROXY_URL or "NOT SET",
        "send_mode": "proxy" if proxy_will_be_used else "direct",
        "webhook_url": "/webhook/telegram",
        "legacy_webhook_url": "/telegram/webhook",
    }

    # Add info about secret status
    if proxy_url_set and not proxy_secret_set:
        status_response["proxy_note"] = (
            "Proxy URL configured. Secret not set - will work if Worker allows unauthenticated requests."
        )

    return status_response


@router.get("/diagnose")
async def telegram_diagnose():
    """
    DIAGNOSTIC ENDPOINT - Check webhook status for ALL registered bots.
    Use this to verify that webhooks are correctly pointing to Railway.
    """
    from api.db_service import SessionLocal

    results = {"bots": [], "expected_webhook_url": ""}

    # Expected webhook URL
    base_url = (
        os.getenv("RAILWAY_PUBLIC_URL")
        or os.getenv("RENDER_EXTERNAL_URL")
        or "https://www.clonnectapp.com"
    )
    expected_webhook = f"{base_url}/webhook/telegram"
    results["expected_webhook_url"] = expected_webhook

    registry = get_telegram_registry()
    bots = registry.list_bots()

    for bot in bots:
        bot_id = bot.get("bot_id")
        bot_token = registry.get_bot_token(bot_id)

        if not bot_token:
            results["bots"].append(
                {"bot_id": bot_id, "creator_id": bot.get("creator_id"), "error": "No token found"}
            )
            continue

        # Call Telegram API to get current webhook info
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
                )
                webhook_info = response.json()

                if webhook_info.get("ok"):
                    current_webhook = webhook_info.get("result", {}).get("url", "")
                    is_correct = current_webhook == expected_webhook

                    results["bots"].append(
                        {
                            "bot_id": bot_id,
                            "bot_username": bot.get("bot_username"),
                            "creator_id": bot.get("creator_id"),
                            "current_webhook": current_webhook or "NOT SET",
                            "webhook_correct": is_correct,
                            "pending_update_count": webhook_info.get("result", {}).get(
                                "pending_update_count", 0
                            ),
                            "last_error": webhook_info.get("result", {}).get("last_error_message"),
                            "last_error_date": webhook_info.get("result", {}).get(
                                "last_error_date"
                            ),
                        }
                    )
                else:
                    results["bots"].append(
                        {
                            "bot_id": bot_id,
                            "error": webhook_info.get("description", "Unknown error"),
                        }
                    )
        except Exception as e:
            results["bots"].append({"bot_id": bot_id, "error": f"Failed to check: {str(e)}"})

    # Also check creators in DB for copilot_mode
    try:
        from api.models import Creator

        session = SessionLocal()
        try:
            creators = session.query(Creator).all()
            results["creators_copilot_status"] = [
                {"name": c.name, "copilot_mode": c.copilot_mode, "bot_active": c.bot_active}
                for c in creators
            ]
        finally:
            session.close()
    except Exception as e:
        results["creators_error"] = str(e)

    return results


@router.post("/fix-webhook/{bot_id}")
async def fix_telegram_webhook(bot_id: str):
    """
    Re-configure webhook for a specific bot to point to Railway.
    Use this if the webhook is pointing to the wrong URL.
    """
    registry = get_telegram_registry()
    bot_token = registry.get_bot_token(bot_id)

    if not bot_token:
        raise HTTPException(status_code=404, detail=f"Bot {bot_id} not found")

    # Build webhook URL
    base_url = (
        os.getenv("RAILWAY_PUBLIC_URL")
        or os.getenv("RENDER_EXTERNAL_URL")
        or "https://www.clonnectapp.com"
    )
    webhook_url = f"{base_url}/webhook/telegram"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # First delete any existing webhook
            await client.post(f"https://api.telegram.org/bot{bot_token}/deleteWebhook")

            # Then set the new webhook
            response = await client.post(
                f"https://api.telegram.org/bot{bot_token}/setWebhook", json={"url": webhook_url}
            )
            result = response.json()

            if result.get("ok"):
                logger.info(f"Webhook fixed for bot {bot_id}: {webhook_url}")
                return {
                    "status": "success",
                    "bot_id": bot_id,
                    "webhook_url": webhook_url,
                    "telegram_response": result,
                }
            else:
                logger.error(f"Failed to set webhook for bot {bot_id}: {result}")
                return {
                    "status": "error",
                    "bot_id": bot_id,
                    "error": result.get("description"),
                    "telegram_response": result,
                }
    except Exception as e:
        logger.error(f"Error fixing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# TELEGRAM MULTI-BOT MANAGEMENT
# ---------------------------------------------------------
@router.get("/bots")
async def list_telegram_bots():
    """List all registered Telegram bots."""
    registry = get_telegram_registry()
    bots = registry.list_bots()
    return {"status": "ok", "bots": bots, "count": len(bots)}


@router.post("/register-bot")
async def register_telegram_bot(request: RegisterBotRequest):
    """
    Register a new Telegram bot for a creator.

    This will:
    1. Verify the bot token with Telegram
    2. Store the bot configuration
    3. Optionally set the webhook to point to this server
    """
    registry = get_telegram_registry()

    result = await registry.register_bot(
        creator_id=request.creator_id,
        bot_token=request.bot_token,
        bot_username=request.bot_username,
        set_webhook=request.set_webhook,
    )

    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("error"))

    return result


@router.put("/bots/{bot_id}/creator")
async def update_telegram_bot_creator(bot_id: str, creator_id: str):
    """Update the creator_id for an existing Telegram bot."""
    registry = get_telegram_registry()
    result = registry.update_bot_creator(bot_id, creator_id)

    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("error"))

    return result


@router.delete("/bots/{bot_id}")
async def unregister_telegram_bot(bot_id: str, delete_webhook: bool = True):
    """Unregister a Telegram bot."""
    registry = get_telegram_registry()
    result = await registry.unregister_bot(bot_id, delete_webhook=delete_webhook)

    if result.get("status") == "error":
        raise HTTPException(status_code=404, detail=result.get("error"))

    return result


@router.post("/bots/reload")
async def reload_telegram_bots():
    """Reload bot configuration from file."""
    registry = get_telegram_registry()
    registry.reload()
    return {
        "status": "ok",
        "message": "Bot configuration reloaded",
        "bots_count": len(registry.list_bots()),
    }


@router.get("/test-connection")
async def telegram_test_connection():
    """Test if we can connect to Telegram API"""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not bot_token:
        return {"status": "error", "error": "TELEGRAM_BOT_TOKEN not configured"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
            return {
                "status": "ok",
                "telegram_response": response.json(),
                "connection": "successful",
            }
    except httpx.ConnectTimeout:
        return {"status": "error", "error": "ConnectTimeout - cannot reach api.telegram.org"}
    except httpx.ConnectError as e:
        return {"status": "error", "error": f"ConnectError: {str(e)}"}
    except Exception as e:
        return {"status": "error", "error": str(e), "type": type(e).__name__}


@router.get("/network-test")
async def telegram_network_test():
    """Test network connectivity to various endpoints"""
    results = {}

    # Test 1: DNS resolution
    try:
        ip = socket.gethostbyname("api.telegram.org")
        results["dns_resolution"] = {"status": "ok", "ip": ip}
    except Exception as e:
        results["dns_resolution"] = {"status": "error", "error": str(e)}

    # Test 2: Try different Telegram endpoints
    endpoints = [
        "https://api.telegram.org",
        "https://core.telegram.org",
        "https://telegram.org",
    ]

    for endpoint in endpoints:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(endpoint, follow_redirects=True)
                results[endpoint] = {"status": "ok", "code": response.status_code}
        except httpx.ConnectTimeout:
            results[endpoint] = {"status": "timeout"}
        except Exception as e:
            results[endpoint] = {"status": "error", "error": str(e)}

    # Test 3: Compare with working endpoint (groq)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://api.groq.com")
            results["api.groq.com"] = {"status": "ok", "code": response.status_code}
    except Exception as e:
        results["api.groq.com"] = {"status": "error", "error": str(e)}

    return results


# Note: /telegram/webhook legacy endpoint is kept in main.py since it references
# the telegram_webhook function which has complex dependencies
