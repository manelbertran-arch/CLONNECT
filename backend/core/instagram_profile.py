"""
Instagram Profile Fetcher
Fetches user profile data (name, profile_pic_url) from Instagram API.

Used by:
- sync_instagram_dms.py to create complete leads
- instagram_handler.py webhook to enrich new leads
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# API base for IGAAT tokens
API_BASE = "https://graph.instagram.com/v21.0"

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS = [1, 3, 10]  # Exponential backoff: 1s, 3s, 10s


@dataclass
class ProfileResult:
    """Result of a profile fetch attempt."""

    success: bool
    profile: Optional[Dict] = None
    is_transient: bool = False  # True if error is temporary (should retry)
    error_code: Optional[int] = None
    error_message: Optional[str] = None


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
    result = await fetch_instagram_profile_with_retry(user_id, access_token, client)
    return result.profile if result.success else None


async def fetch_instagram_profile_detailed(
    user_id: str, access_token: str, client: Optional[httpx.AsyncClient] = None
) -> ProfileResult:
    """
    Fetch Instagram user profile data with detailed error info.
    Single attempt, no retry.
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
                "fields": "id,username,name,profile_pic",
                "access_token": access_token,
            },
        )

        if resp.status_code == 200:
            data = resp.json()
            return ProfileResult(
                success=True,
                profile={
                    "id": data.get("id"),
                    "username": data.get("username", ""),
                    "name": data.get("name", ""),
                    "profile_pic": data.get("profile_pic", ""),
                },
            )
        else:
            # Parse error response
            try:
                error_data = resp.json()
                error = error_data.get("error", {})
                error_code = error.get("code", resp.status_code)
                error_message = error.get("message", f"HTTP {resp.status_code}")
                is_transient = error.get("is_transient", False)

                # Also treat 500 errors as transient
                if resp.status_code >= 500:
                    is_transient = True

            except Exception:
                error_code = resp.status_code
                error_message = f"HTTP {resp.status_code}"
                is_transient = resp.status_code >= 500

            logger.debug(
                f"Profile fetch failed for {user_id}: code={error_code}, transient={is_transient}"
            )
            return ProfileResult(
                success=False,
                is_transient=is_transient,
                error_code=error_code,
                error_message=error_message,
            )

    except httpx.TimeoutException:
        logger.debug(f"Profile fetch timeout for {user_id}")
        return ProfileResult(
            success=False,
            is_transient=True,
            error_message="Timeout",
        )
    except Exception as e:
        logger.debug(f"Profile fetch error for {user_id}: {e}")
        return ProfileResult(
            success=False,
            is_transient=True,  # Network errors are usually transient
            error_message=str(e),
        )

    finally:
        if should_close:
            await client.aclose()


async def fetch_instagram_profile_with_retry(
    user_id: str,
    access_token: str,
    client: Optional[httpx.AsyncClient] = None,
    max_retries: int = MAX_RETRIES,
) -> ProfileResult:
    """
    Fetch Instagram profile with automatic retry for transient errors.

    Retries up to max_retries times with exponential backoff.
    Only retries on transient errors (is_transient=True).
    """
    last_result = None

    for attempt in range(max_retries + 1):
        result = await fetch_instagram_profile_detailed(user_id, access_token, client)

        if result.success:
            if attempt > 0:
                logger.info(f"Profile fetch succeeded on retry {attempt} for {user_id}")
            return result

        last_result = result

        # Don't retry non-transient errors
        if not result.is_transient:
            logger.debug(f"Profile fetch failed permanently for {user_id}: {result.error_message}")
            return result

        # Calculate retry delay
        if attempt < max_retries:
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            logger.debug(
                f"Profile fetch transient error for {user_id}, retry {attempt + 1} in {delay}s"
            )
            await asyncio.sleep(delay)

    logger.warning(
        f"Profile fetch failed after {max_retries + 1} attempts for {user_id}: {last_result.error_message}"
    )
    return last_result


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
