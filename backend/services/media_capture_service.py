"""
Media Capture Service.

Captures Instagram/WhatsApp media from temporary CDN URLs and stores permanently.
Instagram media URLs expire after ~24 hours, so we need to capture immediately.

Strategies (in order of preference):
1. Cloudinary upload (if configured) - returns permanent URL
2. Base64 encoding - stores directly in database

Usage:
    from services.media_capture_service import capture_media_from_url

    result = await capture_media_from_url(cdn_url, media_type="image")
    if result:
        msg_metadata['thumbnail_base64'] = result  # or permanent_url
"""

import base64
import logging
from typing import Optional

import httpx

from services.cloudinary_service import get_cloudinary_service

logger = logging.getLogger(__name__)

# Configuration
MAX_MEDIA_SIZE_BYTES = 5 * 1024 * 1024  # 5MB max for base64 storage
DOWNLOAD_TIMEOUT_SECONDS = 15
CDN_DOMAINS = [
    "lookaside.fbsbx.com",
    "scontent.cdninstagram.com",
    "scontent-",  # scontent-*.cdninstagram.com
    "video.cdninstagram.com",
    "instagram.f",  # instagram.fXXX-X.fna.fbcdn.net
]


def is_cdn_url(url: str) -> bool:
    """
    Check if URL is a temporary CDN URL that will expire.

    Args:
        url: Media URL to check

    Returns:
        True if URL is from a known expiring CDN
    """
    if not url:
        return False
    url_lower = url.lower()
    return any(domain in url_lower for domain in CDN_DOMAINS)


async def download_media(url: str, timeout: float = DOWNLOAD_TIMEOUT_SECONDS) -> Optional[bytes]:
    """
    Download media content from URL.

    Args:
        url: Media URL
        timeout: Request timeout in seconds

    Returns:
        Media bytes or None if failed
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                timeout=timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ClonnectBot/1.0)"
                }
            )

            if response.status_code == 200:
                content = response.content

                # Check size limit
                if len(content) > MAX_MEDIA_SIZE_BYTES:
                    logger.warning(
                        f"[MediaCapture] Media too large: {len(content)} bytes "
                        f"(max {MAX_MEDIA_SIZE_BYTES})"
                    )
                    return None

                return content
            else:
                logger.warning(
                    f"[MediaCapture] Download failed: HTTP {response.status_code}"
                )
                return None

    except httpx.TimeoutException:
        logger.warning(f"[MediaCapture] Download timeout after {timeout}s")
        return None
    except Exception as e:
        logger.error(f"[MediaCapture] Download error: {e}")
        return None


def get_content_type_from_headers(headers: dict) -> str:
    """Extract content type from response headers."""
    content_type = headers.get("content-type", "image/jpeg")
    # Strip charset and other parameters
    return content_type.split(";")[0].strip()


async def capture_media_from_url(
    url: str,
    media_type: str = "image",
    creator_id: Optional[str] = None,
    use_cloudinary: bool = True,
) -> Optional[str]:
    """
    Capture media from a CDN URL and store permanently.

    Tries Cloudinary first (if configured), falls back to base64.

    Args:
        url: Media URL to capture
        media_type: Type of media (image, video, audio)
        creator_id: Creator ID for Cloudinary folder organization
        use_cloudinary: Whether to try Cloudinary first

    Returns:
        - Cloudinary URL (permanent) if Cloudinary succeeded
        - data:URI base64 string if base64 fallback used
        - None if capture failed
    """
    if not url:
        return None

    # Only capture from CDN URLs (temporary URLs)
    if not is_cdn_url(url):
        logger.debug(f"[MediaCapture] Skipping non-CDN URL: {url[:50]}...")
        return None

    logger.info(f"[MediaCapture] Capturing {media_type} from CDN URL")

    # Strategy 1: Try Cloudinary if configured
    if use_cloudinary:
        cloudinary = get_cloudinary_service()
        if cloudinary.is_configured:
            folder = f"clonnect/{creator_id}" if creator_id else "clonnect/media"
            result = cloudinary.upload_from_url(
                url=url,
                media_type=media_type,
                folder=folder,
                tags=["dm_media", "auto_captured"],
            )

            if result.success and result.url:
                logger.info(
                    f"[MediaCapture] Cloudinary upload success: {result.url[:50]}..."
                )
                return result.url
            else:
                logger.warning(
                    f"[MediaCapture] Cloudinary failed: {result.error}, "
                    "falling back to base64"
                )

    # Strategy 2: Base64 encoding
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                timeout=DOWNLOAD_TIMEOUT_SECONDS,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ClonnectBot/1.0)"
                }
            )

            if response.status_code != 200:
                logger.warning(
                    f"[MediaCapture] Download failed: HTTP {response.status_code}"
                )
                return None

            content = response.content

            # Check size limit
            if len(content) > MAX_MEDIA_SIZE_BYTES:
                logger.warning(
                    f"[MediaCapture] Media too large for base64: {len(content)} bytes"
                )
                return None

            # Get content type
            content_type = get_content_type_from_headers(dict(response.headers))

            # Encode to base64 data URI
            b64_content = base64.b64encode(content).decode("utf-8")
            data_uri = f"data:{content_type};base64,{b64_content}"

            logger.info(
                f"[MediaCapture] Base64 capture success: {len(content)} bytes, "
                f"type={content_type}"
            )

            return data_uri

    except httpx.TimeoutException:
        logger.warning(
            f"[MediaCapture] Base64 download timeout after {DOWNLOAD_TIMEOUT_SECONDS}s"
        )
        return None
    except Exception as e:
        logger.error(f"[MediaCapture] Base64 capture error: {e}")
        return None


async def capture_story_thumbnail(
    story_url: str,
    creator_id: Optional[str] = None,
) -> Optional[str]:
    """
    Capture a thumbnail from an Instagram story URL.

    Stories are videos/images that expire after 24h. This captures them
    for permanent display.

    Args:
        story_url: Instagram story URL
        creator_id: Creator ID for organization

    Returns:
        Permanent URL or base64 data URI, or None if failed
    """
    # Stories are typically videos, try to capture thumbnail
    return await capture_media_from_url(
        url=story_url,
        media_type="video",
        creator_id=creator_id,
    )


# Convenience function for sync context (wraps async)
def capture_media_sync(url: str, media_type: str = "image") -> Optional[str]:
    """
    Synchronous wrapper for capture_media_from_url.

    For use in non-async contexts.
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're in an async context, create a new task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    capture_media_from_url(url, media_type)
                )
                return future.result(timeout=DOWNLOAD_TIMEOUT_SECONDS + 5)
        else:
            return loop.run_until_complete(
                capture_media_from_url(url, media_type)
            )
    except Exception as e:
        logger.error(f"[MediaCapture] Sync wrapper error: {e}")
        return None
