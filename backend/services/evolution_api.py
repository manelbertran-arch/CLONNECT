"""
Evolution API client for WhatsApp integration via Baileys.

Connects to a self-hosted Evolution API instance to send/receive
WhatsApp messages without the official Cloud API.

Env vars:
- EVOLUTION_API_URL: Base URL of the Evolution API instance
- EVOLUTION_API_KEY: Global API key for authentication
"""

import logging
import os
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")


def _headers() -> Dict[str, str]:
    return {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }


def _resolve_creator_from_instance(instance: str) -> str:
    """Resolve creator_id from Evolution API instance name."""
    try:
        from api.routers.messaging_webhooks import EVOLUTION_INSTANCE_MAP

        return EVOLUTION_INSTANCE_MAP.get(instance, "unknown")
    except ImportError:
        return "unknown"


async def send_evolution_message(
    instance: str, to_number: str, text: str, approved: bool = False
) -> Dict[str, Any]:
    """
    Send a text message via Evolution API — GUARDED by send_guard.

    Args:
        instance: Instance name (e.g. "stefano-fitpack")
        to_number: Phone number with country code, no + (e.g. "34612345678")
        text: Message text
        approved: True if message was explicitly approved by creator

    Returns:
        API response dict
    """
    from core.send_guard import SendBlocked, check_send_permission

    creator_id = _resolve_creator_from_instance(instance)
    try:
        check_send_permission(creator_id, approved=approved, caller="evolution_api")
    except SendBlocked:
        return {"error": "Message blocked — not approved by creator", "blocked": True}

    url = f"{EVOLUTION_API_URL}/message/sendText/{instance}"
    payload = {
        "number": to_number,
        "text": text,
        "options": {
            "delay": 1200,
            "presence": "composing",
        },
    }

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        async with session.post(url, json=payload, headers=_headers()) as resp:
            result = await resp.json()
            if resp.status >= 400:
                logger.error(
                    "Evolution send failed [%s -> %s]: %s",
                    instance, to_number, result,
                )
            else:
                logger.info(
                    "Evolution message sent [%s -> %s]: %d chars",
                    instance, to_number, len(text),
                )
            return result


async def get_instance_status(instance: str) -> Dict[str, Any]:
    """
    Get connection state of an Evolution instance.

    Returns dict like: {"instance": {"instanceName": "...", "state": "open"}}
    """
    url = f"{EVOLUTION_API_URL}/instance/connectionState/{instance}"

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        async with session.get(url, headers=_headers()) as resp:
            return await resp.json()


async def get_qr_code(instance: str) -> Dict[str, Any]:
    """
    Get QR code for an instance (used for initial pairing).

    Returns dict with base64 QR or pairingCode.
    """
    url = f"{EVOLUTION_API_URL}/instance/connect/{instance}"

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        async with session.get(url, headers=_headers()) as resp:
            return await resp.json()


async def fetch_profile_picture(instance: str, number: str) -> Optional[str]:
    """
    Fetch a WhatsApp contact's profile picture URL via Evolution API.

    Args:
        instance: Instance name (e.g. "manel-test")
        number: Phone number with country code, no + (e.g. "34612345678")

    Returns:
        Profile picture URL string, or None if not available.
    """
    if not EVOLUTION_API_URL or not number:
        return None

    url = f"{EVOLUTION_API_URL}/chat/fetchProfilePictureUrl/{instance}"
    payload = {"number": number}

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, json=payload, headers=_headers()) as resp:
                if resp.status >= 400:
                    logger.warning(
                        "Evolution profile pic failed [%s, %s]: HTTP %d",
                        instance, number, resp.status,
                    )
                    return None
                result = await resp.json()
                pic_url = result.get("profilePictureUrl") or result.get("url") or None
                if pic_url:
                    logger.info("Evolution profile pic fetched [%s, %s]", instance, number)
                return pic_url
    except Exception as e:
        logger.warning("Evolution profile pic error [%s, %s]: %s", instance, number, e)
        return None


async def send_evolution_media(
    instance: str,
    to_number: str,
    media_url: str,
    media_type: str = "image",
    caption: str = "",
    approved: bool = False,
) -> Dict[str, Any]:
    """
    Send a media message via Evolution API — GUARDED by send_guard.

    Args:
        instance: Instance name (e.g. "stefano-fitpack")
        to_number: Phone number with country code, no + (e.g. "34612345678")
        media_url: Public URL of the media (Cloudinary)
        media_type: "image", "video", "audio", "document"
        caption: Optional caption text
        approved: True if message was explicitly approved by creator

    Returns:
        API response dict
    """
    from core.send_guard import SendBlocked, check_send_permission

    creator_id = _resolve_creator_from_instance(instance)
    try:
        check_send_permission(creator_id, approved=approved, caller="evolution_api.send_media")
    except SendBlocked:
        return {"error": "Message blocked — not approved by creator", "blocked": True}

    url = f"{EVOLUTION_API_URL}/message/sendMedia/{instance}"
    payload = {
        "number": to_number,
        "mediatype": media_type,
        "media": media_url,
        "caption": caption,
    }

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        async with session.post(url, json=payload, headers=_headers()) as resp:
            result = await resp.json()
            if resp.status >= 400:
                logger.error(
                    "Evolution media send failed [%s -> %s]: %s",
                    instance, to_number, result,
                )
            else:
                logger.info(
                    "Evolution media sent [%s -> %s]: %s (%s)",
                    instance, to_number, media_type, media_url[:60],
                )
            return result


async def fetch_instances() -> list:
    """List all Evolution API instances."""
    url = f"{EVOLUTION_API_URL}/instance/fetchInstances"

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        async with session.get(url, headers=_headers()) as resp:
            return await resp.json()
