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


async def send_evolution_message(
    instance: str, to_number: str, text: str
) -> Dict[str, Any]:
    """
    Send a text message via Evolution API.

    Args:
        instance: Instance name (e.g. "stefano-fitpack")
        to_number: Phone number with country code, no + (e.g. "34612345678")
        text: Message text

    Returns:
        API response dict
    """
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


async def fetch_instances() -> list:
    """List all Evolution API instances."""
    url = f"{EVOLUTION_API_URL}/instance/fetchInstances"

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
        async with session.get(url, headers=_headers()) as resp:
            return await resp.json()
