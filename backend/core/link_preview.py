"""
Link Preview Service
Extracts Open Graph metadata from URLs for message previews.

Follows Clonnect methodology:
- Exponential backoff for retries
- Background processing (fire-and-forget)
- Graceful degradation on errors
"""

import re
import logging
import httpx
from typing import Optional, Dict, List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Try to import Sentry for error tracking
try:
    import sentry_sdk
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False

# URL regex pattern
URL_PATTERN = re.compile(
    r'https?://[^\s<>"{}|\\^`\[\]]+',
    re.IGNORECASE
)

# Common domains that should be handled specially
INSTAGRAM_DOMAINS = ['instagram.com', 'www.instagram.com', 'instagr.am']
YOUTUBE_DOMAINS = ['youtube.com', 'www.youtube.com', 'youtu.be', 'm.youtube.com']
TIKTOK_DOMAINS = ['tiktok.com', 'www.tiktok.com', 'vm.tiktok.com']


def extract_urls(text: str) -> List[str]:
    """Extract all URLs from text."""
    if not text:
        return []
    return URL_PATTERN.findall(text)


def get_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception as e:
        logger.warning("Failed to parse URL domain: %s", e)
        return ""


def detect_platform(url: str) -> str:
    """Detect which platform a URL belongs to."""
    domain = get_domain(url)

    if any(d in domain for d in INSTAGRAM_DOMAINS):
        return "instagram"
    if any(d in domain for d in YOUTUBE_DOMAINS):
        return "youtube"
    if any(d in domain for d in TIKTOK_DOMAINS):
        return "tiktok"

    return "web"


async def extract_link_preview(url: str, timeout: float = 5.0, max_retries: int = 2) -> Optional[Dict]:
    """
    Extract Open Graph metadata from a URL with exponential backoff.

    Args:
        url: The URL to extract metadata from
        timeout: Request timeout in seconds
        max_retries: Maximum number of retries on failure

    Returns:
        Dict with preview data or None if extraction failed
    """
    import asyncio

    for attempt in range(max_retries + 1):
        try:
            result = await _fetch_og_metadata(url, timeout)
            return result
        except httpx.TimeoutException:
            if attempt < max_retries:
                wait_time = (2 ** attempt) * 0.5  # 0.5s, 1s, 2s...
                logger.debug(f"Link preview timeout for {url}, retrying in {wait_time}s")
                await asyncio.sleep(wait_time)
            else:
                logger.debug(f"Link preview timeout for {url} after {max_retries} retries")
                return None
        except Exception as e:
            logger.debug(f"Link preview error for {url}: {e}")
            return None

    return None


async def _fetch_og_metadata(url: str, timeout: float) -> Optional[Dict]:
    """Internal function to fetch OG metadata from URL."""
    try:
        # Skip Instagram CDN URLs (already media, not pages)
        if 'cdninstagram.com' in url or 'fbcdn.net' in url:
            return None

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; ClonnectBot/1.0; +https://clonnect.com)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
        }

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            verify=False  # Some sites have SSL issues
        ) as client:
            response = await client.get(url, headers=headers)

            if response.status_code != 200:
                logger.debug(f"Link preview failed for {url}: HTTP {response.status_code}")
                return None

            html = response.text

            # Parse Open Graph tags
            preview = {
                "url": str(response.url),  # Use final URL after redirects
                "original_url": url,
                "platform": detect_platform(url),
            }

            # Extract og:title
            title_match = re.search(
                r'<meta[^>]*property=["\']og:title["\'][^>]*content=["\']([^"\']+)["\']',
                html, re.IGNORECASE
            )
            if not title_match:
                title_match = re.search(
                    r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:title["\']',
                    html, re.IGNORECASE
                )
            if title_match:
                preview["title"] = title_match.group(1).strip()[:200]

            # Extract og:description
            desc_match = re.search(
                r'<meta[^>]*property=["\']og:description["\'][^>]*content=["\']([^"\']+)["\']',
                html, re.IGNORECASE
            )
            if not desc_match:
                desc_match = re.search(
                    r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:description["\']',
                    html, re.IGNORECASE
                )
            if desc_match:
                preview["description"] = desc_match.group(1).strip()[:500]

            # Extract og:image
            img_match = re.search(
                r'<meta[^>]*property=["\']og:image["\'][^>]*content=["\']([^"\']+)["\']',
                html, re.IGNORECASE
            )
            if not img_match:
                img_match = re.search(
                    r'<meta[^>]*content=["\']([^"\']+)["\'][^>]*property=["\']og:image["\']',
                    html, re.IGNORECASE
                )
            if img_match:
                preview["image"] = img_match.group(1).strip()

            # Extract og:site_name
            site_match = re.search(
                r'<meta[^>]*property=["\']og:site_name["\'][^>]*content=["\']([^"\']+)["\']',
                html, re.IGNORECASE
            )
            if site_match:
                preview["site_name"] = site_match.group(1).strip()

            # Fallback: try <title> tag if no og:title
            if "title" not in preview:
                title_tag = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
                if title_tag:
                    preview["title"] = title_tag.group(1).strip()[:200]

            # Fallback: use domain as site_name
            if "site_name" not in preview:
                preview["site_name"] = get_domain(url)

            # Only return if we got at least a title or image
            if preview.get("title") or preview.get("image"):
                return preview

            return None

    except httpx.TimeoutException:
        # Re-raise for retry logic in extract_link_preview
        raise
    except Exception as e:
        logger.debug(f"Link preview error for {url}: {e}")
        return None


async def extract_previews_from_text(text: str) -> List[Dict]:
    """
    Extract link previews from all URLs in a text.

    Args:
        text: Text containing URLs

    Returns:
        List of preview dicts for URLs that had valid metadata
    """
    urls = extract_urls(text)
    if not urls:
        return []

    previews = []
    for url in urls[:3]:  # Limit to 3 URLs per message
        preview = await extract_link_preview(url)
        if preview:
            previews.append(preview)

    return previews


def has_link_preview(metadata: Optional[Dict]) -> bool:
    """Check if metadata contains link preview data."""
    if not metadata:
        return False
    return bool(metadata.get("link_preview") or metadata.get("link_previews"))


async def extract_and_save_preview(message_id: str, content: str):
    """
    Background task to extract link preview and update message metadata.

    This runs asynchronously after the message is saved to avoid blocking
    the webhook processing.

    Args:
        message_id: UUID of the message to update
        content: Message content to extract URLs from
    """
    import asyncio

    try:
        urls = extract_urls(content)
        if not urls:
            return

        # Small delay to not overload the system
        await asyncio.sleep(0.5)

        preview = await extract_link_preview(urls[0])
        if not preview:
            return

        # Update message in database
        from api.database import SessionLocal
        from api.models import Message
        import uuid

        session = SessionLocal()
        try:
            msg = session.query(Message).filter_by(id=uuid.UUID(message_id)).first()
            if msg:
                current_metadata = msg.msg_metadata or {}
                if not current_metadata.get("link_preview"):
                    current_metadata["link_preview"] = preview
                    msg.msg_metadata = current_metadata
                    session.commit()
                    logger.info(f"Added link preview for message {message_id}")
        finally:
            session.close()

    except Exception as e:
        logger.warning(f"Background link preview extraction failed: {e}")
        if SENTRY_AVAILABLE:
            sentry_sdk.capture_exception(e)


def schedule_link_preview_extraction(message_id: str, content: str):
    """
    Schedule link preview extraction as a fire-and-forget background task.

    Safe to call from sync code - creates task in current event loop if available,
    otherwise logs and skips (preview can be generated later via admin endpoint).
    """
    import asyncio

    # Check if content has URLs before scheduling
    if not content or 'http' not in content.lower():
        return

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(extract_and_save_preview(message_id, content))
        logger.debug(f"Scheduled link preview extraction for message {message_id}")
    except RuntimeError:
        # No running event loop - that's fine, admin endpoint can fill it in later
        logger.debug(f"No event loop for link preview, message {message_id} will be processed later")
