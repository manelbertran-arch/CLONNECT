"""
Instagram Profile Fetcher
Fetches user profile data (name, profile_pic_url) from Instagram API.

Used by:
- sync_instagram_dms.py to create complete leads
- instagram_handler.py webhook to enrich new leads
"""

import logging
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# API base for IGAAT tokens
API_BASE = "https://graph.instagram.com/v21.0"


async def fetch_instagram_profile(
    user_id: str, access_token: str, client: Optional[httpx.AsyncClient] = None
) -> Optional[Dict]:
    """
    Fetch Instagram user profile data.

    Args:
        user_id: Instagram user ID (IGSID)
        access_token: Instagram access token (IGAAT or EAA)
        client: Optional httpx client to reuse

    Returns:
        Dict with profile data:
        {
            "id": "123456789",
            "username": "johndoe",
            "name": "John Doe",
            "profile_picture_url": "https://..."
        }
        Or None if fetch failed
    """
    should_close = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=10.0)

    try:
        # Use correct API base based on token type
        api_base = API_BASE
        if access_token and access_token.startswith("EAA"):
            api_base = "https://graph.facebook.com/v21.0"

        resp = await client.get(
            f"{api_base}/{user_id}",
            params={
                "fields": "id,username,name,profile_pic",  # Note: field is profile_pic, not profile_picture_url
                "access_token": access_token,
            },
        )

        if resp.status_code == 200:
            data = resp.json()
            return {
                "id": data.get("id"),
                "username": data.get("username", ""),
                "name": data.get("name", ""),
                "profile_picture_url": data.get("profile_pic", ""),  # API returns profile_pic
            }
        else:
            logger.debug(f"Profile fetch failed for {user_id}: HTTP {resp.status_code}")
            return None

    except Exception as e:
        logger.debug(f"Profile fetch error for {user_id}: {e}")
        return None

    finally:
        if should_close:
            await client.aclose()


async def fetch_profiles_batch(
    user_ids: list, access_token: str, delay_seconds: float = 0.3
) -> Dict[str, Dict]:
    """
    Fetch profiles for multiple users with rate limiting.

    Args:
        user_ids: List of Instagram user IDs
        access_token: Instagram access token
        delay_seconds: Delay between requests (default 0.3s = ~200/min)

    Returns:
        Dict mapping user_id to profile data
    """
    import asyncio

    results = {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        for user_id in user_ids:
            profile = await fetch_instagram_profile(user_id, access_token, client)
            if profile:
                results[user_id] = profile
            await asyncio.sleep(delay_seconds)

    return results
