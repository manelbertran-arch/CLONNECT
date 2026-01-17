"""
Story Thumbnail Service
Downloads and saves Instagram story thumbnails before they expire.

Instagram CDN URLs expire after ~24 hours, so we must save immediately.
"""

import logging
import base64
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

# Max size for base64 storage (500KB after encoding)
MAX_THUMBNAIL_SIZE = 500 * 1024


async def download_story_thumbnail(cdn_url: str, timeout: float = 10.0) -> Optional[str]:
    """
    Download a story thumbnail from Instagram CDN and convert to base64.

    Args:
        cdn_url: Instagram CDN URL (expires after ~24h)
        timeout: Request timeout in seconds

    Returns:
        Base64 data URL (data:image/jpeg;base64,...) or None if failed
    """
    if not cdn_url:
        return None

    # Skip if already a data URL
    if cdn_url.startswith("data:"):
        return cdn_url

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ClonnectBot/1.0)",
            "Accept": "image/*",
        }

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(cdn_url, headers=headers)

            if response.status_code != 200:
                logger.warning(f"Story thumbnail download failed: HTTP {response.status_code}")
                return None

            content = response.content

            # Check size
            if len(content) > MAX_THUMBNAIL_SIZE:
                logger.warning(f"Story thumbnail too large: {len(content)} bytes")
                # Could resize here in the future
                return None

            # Detect content type
            content_type = response.headers.get("content-type", "image/jpeg")
            if ";" in content_type:
                content_type = content_type.split(";")[0].strip()

            # Convert to base64
            b64_content = base64.b64encode(content).decode("utf-8")
            data_url = f"data:{content_type};base64,{b64_content}"

            logger.info(f"Saved story thumbnail: {len(content)} bytes -> base64")
            return data_url

    except httpx.TimeoutException:
        logger.warning(f"Story thumbnail download timeout: {cdn_url[:50]}...")
        return None
    except Exception as e:
        logger.warning(f"Story thumbnail download error: {e}")
        return None


def is_story_url_expired(url: str) -> bool:
    """
    Check if an Instagram CDN URL has likely expired.

    Instagram CDN URLs contain expiration timestamps in query params.
    """
    if not url:
        return True

    # Data URLs never expire
    if url.startswith("data:"):
        return False

    # Check for common Instagram CDN patterns
    if "cdninstagram.com" in url or "fbcdn.net" in url:
        # These URLs typically have oe= (expiration) parameter
        # After 24h they return 403
        return False  # Can't know for sure without checking

    return False


async def ensure_story_thumbnail(cdn_url: str, existing_thumbnail: Optional[str] = None) -> Optional[str]:
    """
    Ensure we have a permanent thumbnail for a story.

    If existing_thumbnail is already a data URL, returns it.
    Otherwise downloads and converts the CDN URL.

    Args:
        cdn_url: Original Instagram CDN URL
        existing_thumbnail: Previously saved thumbnail (if any)

    Returns:
        Permanent thumbnail (data URL) or None
    """
    # Already have a permanent thumbnail
    if existing_thumbnail and existing_thumbnail.startswith("data:"):
        return existing_thumbnail

    # Try to download and save
    return await download_story_thumbnail(cdn_url)
