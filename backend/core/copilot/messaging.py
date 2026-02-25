"""
Copilot messaging — platform sends and debounced regeneration.

Handles sending messages via Instagram, Telegram, and WhatsApp,
plus the debounce logic for regenerating stale suggestions.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from core.copilot.models import DEBOUNCE_SECONDS

logger = logging.getLogger(__name__)


async def send_message_impl(
    service, creator, lead, text: str, copilot_action: str = None
) -> Dict[str, Any]:
    """Send message via platform — GUARDED by send_guard."""
    from core.send_guard import SendBlocked, check_send_permission

    try:
        approved = copilot_action in ("approved", "edited")
        check_send_permission(creator.name, approved=approved, caller="copilot_service")
    except SendBlocked as e:
        return {"success": False, "error": str(e), "blocked": True}

    try:
        if lead.platform == "instagram":
            return await _send_instagram_message(service, creator, lead, text)
        elif lead.platform == "telegram":
            return await _send_telegram_message(service, creator, lead, text)
        elif lead.platform == "whatsapp":
            return await _send_whatsapp_message(service, creator, lead, text)
        else:
            return {"success": False, "error": f"Unknown platform: {lead.platform}"}
    except Exception as e:
        logger.error(f"[Copilot] Error sending message: {e}")
        return {"success": False, "error": str(e)}


async def _send_instagram_message(service, creator, lead, text: str) -> Dict[str, Any]:
    """Enviar mensaje via Instagram API"""
    import os

    from core.instagram import InstagramConnector

    # Use DB values with fallback to env vars (same as InstagramHandler)
    access_token = creator.instagram_token or os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    page_id = creator.instagram_page_id or os.getenv("INSTAGRAM_PAGE_ID", "")
    ig_user_id = creator.instagram_user_id or os.getenv("INSTAGRAM_USER_ID", "")

    # DEBUG: Log all values to identify 'auto' issue
    logger.info("[Copilot] _send_instagram_message DEBUG:")
    logger.info(f"[Copilot]   creator.name = {creator.name}")
    logger.info(f"[Copilot]   creator.instagram_page_id = {creator.instagram_page_id}")
    logger.info(f"[Copilot]   creator.instagram_user_id = {creator.instagram_user_id}")
    logger.info(f"[Copilot]   lead.platform_user_id = {lead.platform_user_id}")
    logger.info(f"[Copilot]   page_id (final) = {page_id}")
    logger.info(f"[Copilot]   ig_user_id (final) = {ig_user_id}")

    if not access_token or not page_id:
        return {"success": False, "error": "Instagram not connected"}

    # Validate page_id is not garbage value
    if page_id == "auto" or len(page_id) < 5:
        logger.error(
            f"[Copilot] Invalid page_id: '{page_id}' - creator may not have Instagram connected"
        )
        return {"success": False, "error": f"Invalid Instagram page_id: '{page_id}'"}

    connector = InstagramConnector(
        access_token=access_token, page_id=page_id, ig_user_id=ig_user_id
    )

    try:
        # Strip "ig_" prefix - platform_user_id format is "ig_123456" but API needs just "123456"
        recipient_id = lead.platform_user_id
        if recipient_id.startswith("ig_"):
            recipient_id = recipient_id[3:]  # Remove "ig_" prefix

        # Validate recipient_id is not garbage
        if recipient_id == "auto" or not recipient_id or len(recipient_id) < 5:
            logger.error(f"[Copilot] Invalid recipient_id: '{recipient_id}'")
            return {"success": False, "error": f"Invalid recipient_id: '{recipient_id}'"}

        logger.info(f"[Copilot] Sending Instagram message to {recipient_id} via connector")
        result = await connector.send_message(recipient_id=recipient_id, text=text)
        logger.info(f"[Copilot] Instagram API response: {result}")

        if "error" in result:
            # Instagram API returns error as dict: {"message": "...", "code": X}
            error_info = result["error"]
            if isinstance(error_info, dict):
                error_msg = f"{error_info.get('message', 'Unknown error')} (code: {error_info.get('code', 'N/A')})"
            else:
                error_msg = str(error_info)
            logger.error(f"[Copilot] Instagram send error: {error_msg}")
            return {"success": False, "error": error_msg}

        return {"success": True, "message_id": result.get("message_id", "")}
    finally:
        await connector.close()


async def _send_telegram_message(service, creator, lead, text: str) -> Dict[str, Any]:
    """Enviar mensaje via Telegram API"""
    import httpx
    from core.telegram_registry import get_telegram_registry

    # Try registry first (bots.json), fallback to creator.telegram_bot_token
    registry = get_telegram_registry()
    bot_token = registry.get_token_for_creator(creator.name)

    if not bot_token:
        # Fallback to creator table
        bot_token = creator.telegram_bot_token

    if not bot_token:
        return {"success": False, "error": "Telegram not connected"}

    # Extract chat_id from follower_id (format: tg_123456)
    chat_id = lead.platform_user_id.replace("tg_", "")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json={"chat_id": chat_id, "text": text})
        result = response.json()

        if not result.get("ok"):
            return {"success": False, "error": result.get("description", "Failed")}

        return {
            "success": True,
            "message_id": str(result.get("result", {}).get("message_id", "")),
        }


async def _send_whatsapp_message(service, creator, lead, text: str) -> Dict[str, Any]:
    """Enviar mensaje via Evolution API (Baileys) or WhatsApp Cloud API fallback."""
    import os

    # Extract phone number from follower_id (format: wa_34612345678)
    recipient = lead.platform_user_id
    if recipient.startswith("wa_"):
        recipient = recipient[3:]

    if not recipient or len(recipient) < 5:
        return {"success": False, "error": f"Invalid WhatsApp recipient: '{recipient}'"}

    # Try Evolution API first (Baileys)
    try:
        from api.routers.messaging_webhooks import EVOLUTION_INSTANCE_MAP
        from services.evolution_api import send_evolution_message

        evo_instance = None
        for inst_name, cid in EVOLUTION_INSTANCE_MAP.items():
            if cid == creator.name:
                evo_instance = inst_name
                break

        if evo_instance:
            logger.info(f"[Copilot] Sending WhatsApp via Evolution [{evo_instance}] to {recipient}")
            result = await send_evolution_message(evo_instance, recipient, text, approved=True)
            msg_id = result.get("key", {}).get("id", "")
            logger.info(f"[Copilot] Evolution API response: {result}")
            return {"success": True, "message_id": msg_id}
    except Exception as evo_err:
        logger.warning(f"[Copilot] Evolution API send failed, trying Cloud API: {evo_err}")

    # Fallback to official WhatsApp Cloud API
    from core.whatsapp import WhatsAppConnector

    wa_token = creator.whatsapp_token or os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    wa_phone_id = creator.whatsapp_phone_id or os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")

    if not wa_token or not wa_phone_id:
        return {"success": False, "error": "WhatsApp not connected (no Evolution instance or Cloud API)"}

    connector = WhatsAppConnector(
        phone_number_id=wa_phone_id,
        access_token=wa_token,
    )

    try:
        logger.info(f"[Copilot] Sending WhatsApp message to {recipient} via Cloud API")
        result = await connector.send_message(recipient, text)
        logger.info(f"[Copilot] WhatsApp API response: {result}")

        if "error" in result:
            error_info = result["error"]
            if isinstance(error_info, dict):
                error_msg = f"{error_info.get('message', 'Unknown error')} (code: {error_info.get('code', 'N/A')})"
            else:
                error_msg = str(error_info)
            logger.error(f"[Copilot] WhatsApp send error: {error_msg}")
            return {"success": False, "error": error_msg}

        msg_id = ""
        if "messages" in result and result["messages"]:
            msg_id = result["messages"][0].get("id", "")

        return {"success": True, "message_id": msg_id}
    finally:
        await connector.close()


# ── Debounce regeneration ──────────────────────────────────────────────


def schedule_debounced_regen_impl(
    service,
    creator_id: str,
    follower_id: str,
    platform: str,
    pending_message_id: str,
    lead_id: str,
    username: str = "",
):
    """Schedule (or reschedule) a debounced regeneration for a lead."""
    lead_key = lead_id

    # Cancel any existing debounce task for this lead
    existing_task = service._debounce_tasks.get(lead_key)
    if existing_task and not existing_task.done():
        existing_task.cancel()
        logger.info(f"[Copilot:Debounce] Cancelled previous regen timer for lead {lead_key}")

    # Store metadata for the regeneration
    service._debounce_metadata[lead_key] = {
        "creator_id": creator_id,
        "follower_id": follower_id,
        "platform": platform,
        "pending_message_id": pending_message_id,
        "username": username,
    }

    # Schedule new delayed regeneration
    task = asyncio.create_task(_debounced_regeneration_impl(service, lead_key))
    service._debounce_tasks[lead_key] = task
    logger.info(
        f"[Copilot:Debounce] Scheduled regen in {DEBOUNCE_SECONDS}s for lead {lead_key}"
    )


async def _debounced_regeneration_impl(service, lead_key: str):
    """Wait for silence, then regenerate the pending suggestion with full context."""
    try:
        await asyncio.sleep(DEBOUNCE_SECONDS)
    except asyncio.CancelledError:
        logger.info(f"[Copilot:Debounce] Regen cancelled for lead {lead_key}")
        return

    meta = service._debounce_metadata.pop(lead_key, None)
    service._debounce_tasks.pop(lead_key, None)

    if not meta:
        logger.warning(f"[Copilot:Debounce] No metadata for lead {lead_key} — skipping")
        return

    from api.database import SessionLocal
    from api.models import Lead, Message

    session = SessionLocal()
    try:
        # Verify pending message still exists and is pending
        pending_msg = (
            session.query(Message)
            .filter_by(id=meta["pending_message_id"])
            .first()
        )
        if not pending_msg or pending_msg.status != "pending_approval":
            logger.info(
                f"[Copilot:Debounce] Pending msg {meta['pending_message_id']} "
                f"no longer pending (status={getattr(pending_msg, 'status', 'gone')}) — skipping regen"
            )
            return

        # Get the latest user message for this lead
        latest_user_msg = (
            session.query(Message)
            .filter(
                Message.lead_id == pending_msg.lead_id,
                Message.role == "user",
            )
            .order_by(Message.created_at.desc())
            .first()
        )
        if not latest_user_msg:
            logger.warning(f"[Copilot:Debounce] No user messages for lead {lead_key}")
            return

        # Call process_dm to generate a new response with full context
        from core.dm_agent_v2 import get_dm_agent

        agent = get_dm_agent(meta["creator_id"])
        dm_response = await agent.process_dm(
            message=latest_user_msg.content,
            sender_id=meta["follower_id"],
            metadata={"platform": meta["platform"]},
        )

        response_text = dm_response.content if hasattr(dm_response, "content") else str(dm_response)
        if not response_text or not response_text.strip():
            logger.warning(f"[Copilot:Debounce] Empty regen response for lead {lead_key}")
            return

        # Re-fetch pending msg in case status changed during LLM call
        session.refresh(pending_msg)
        if pending_msg.status != "pending_approval":
            logger.info(
                f"[Copilot:Debounce] Pending msg changed to {pending_msg.status} during regen — skipping"
            )
            return

        # Update the pending suggestion with the regenerated response
        now = datetime.now(timezone.utc)
        pending_msg.content = response_text
        pending_msg.suggested_response = response_text
        pending_msg.created_at = now

        # Carry Best-of-N candidates from DM response metadata
        if hasattr(dm_response, "metadata") and dm_response.metadata and dm_response.metadata.get("best_of_n"):
            existing_meta = pending_msg.msg_metadata or {}
            existing_meta["best_of_n"] = dm_response.metadata["best_of_n"]
            pending_msg.msg_metadata = existing_meta

        session.commit()

        logger.info(
            f"[Copilot:Debounce] Regenerated pending suggestion for lead {lead_key} "
            f"(msg {meta['pending_message_id']})"
        )

        # Invalidate caches
        try:
            from api.cache import api_cache

            api_cache.invalidate(f"conversations:{meta['creator_id']}")
            api_cache.invalidate(
                f"follower_detail:{meta['creator_id']}:{meta['follower_id']}"
            )
        except Exception:
            pass

        # Notify frontend of updated suggestion
        try:
            from api.routers.events import notify_creator

            await notify_creator(
                meta["creator_id"],
                "new_message",
                {"follower_id": meta["follower_id"], "role": "assistant"},
            )
        except Exception:
            pass

    except Exception as e:
        logger.error(f"[Copilot:Debounce] Regen failed for lead {lead_key}: {e}")
        session.rollback()
    finally:
        session.close()
