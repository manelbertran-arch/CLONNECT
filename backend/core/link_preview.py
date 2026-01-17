"""
Link Preview Service
Extracts Open Graph metadata from URLs for message previews.
"""

import re
import logging
import httpx
from typing import Optional, Dict, List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

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
    except:
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


async def extract_link_preview(url: str, timeout: float = 5.0) -> Optional[Dict]:
    """
    Extract Open Graph metadata from a URL.

    Args:
        url: The URL to extract metadata from
        timeout: Request timeout in seconds

    Returns:
        Dict with preview data or None if extraction failed
    """
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
        logger.debug(f"Link preview timeout for {url}")
        return None
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
