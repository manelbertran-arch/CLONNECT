"""
Content extraction using Readability algorithm.

Readability is the algorithm used by Firefox Reader Mode to extract
the main article content from a web page, removing navigation,
sidebars, footers, and other boilerplate.

This module provides a wrapper with:
- Graceful fallback when Readability fails
- Configurable minimum content threshold
- Integration with existing scraper metrics

Usage:
    title, content, success = extract_with_readability(html, url)
    if success:
        # Use Readability result
    else:
        # Fallback to manual extraction

Configuration (env vars):
    SCRAPER_USE_READABILITY=true    # Enable/disable (default: true)
    READABILITY_MIN_CONTENT=100     # Minimum chars to accept (default: 100)
"""

import os
import re
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================
READABILITY_ENABLED = os.getenv("SCRAPER_USE_READABILITY", "true").lower() in ("true", "1", "yes")
READABILITY_MIN_CONTENT = int(os.getenv("READABILITY_MIN_CONTENT", "100"))

# =============================================================================
# READABILITY AVAILABILITY CHECK
# =============================================================================
_READABILITY_AVAILABLE = False
try:
    from readability import Document
    _READABILITY_AVAILABLE = True
except ImportError:
    logger.warning(
        "readability-lxml not installed. Install with: pip install readability-lxml"
    )


def is_readability_available() -> bool:
    """Check if Readability is available and enabled."""
    return _READABILITY_AVAILABLE and READABILITY_ENABLED


# =============================================================================
# CONTENT EXTRACTION
# =============================================================================
def extract_with_readability(html: str, url: str) -> Tuple[Optional[str], Optional[str], bool]:
    """
    Extract main content using Readability algorithm.

    Readability analyzes the HTML structure to identify the main article
    content, removing navigation, sidebars, ads, and other boilerplate.

    Args:
        html: Raw HTML content
        url: Source URL (used for resolving relative links)

    Returns:
        Tuple of (title, content, success):
        - title: Extracted article title (or None)
        - content: Clean text content (or None)
        - success: True if extraction succeeded and content meets minimum length

    Example:
        >>> title, content, success = extract_with_readability(html, url)
        >>> if success:
        ...     print(f"Extracted: {title}")
        ... else:
        ...     print("Fallback to manual extraction")
    """
    if not is_readability_available():
        logger.debug("Readability not available, skipping")
        return None, None, False

    if not html or len(html.strip()) < 100:
        logger.debug("HTML too short for Readability")
        return None, None, False

    try:
        # Create Readability document
        doc = Document(html, url=url)

        # Extract title
        title = doc.title()
        if title:
            title = _clean_title(title)

        # Extract main content (returns HTML)
        summary_html = doc.summary()

        if not summary_html:
            logger.debug(f"Readability returned empty summary for {url}")
            return title, None, False

        # Convert HTML to clean text
        content = _html_to_text(summary_html)

        if not content:
            logger.debug(f"Readability content conversion failed for {url}")
            return title, None, False

        # Check minimum content length
        if len(content) < READABILITY_MIN_CONTENT:
            logger.debug(
                f"Readability content too short ({len(content)} < {READABILITY_MIN_CONTENT}) for {url}"
            )
            return title, content, False

        logger.info(f"Readability extracted {len(content)} chars from {url}")
        return title, content, True

    except Exception as e:
        logger.warning(f"Readability extraction failed for {url}: {e}")
        return None, None, False


def _clean_title(title: str) -> str:
    """
    Clean extracted title.

    Removes common suffixes like " | Site Name" or " - Company".
    """
    if not title:
        return ""

    # Remove site name suffixes (common patterns)
    # "Article Title | Site Name" -> "Article Title"
    # "Article Title - Company" -> "Article Title"
    patterns = [
        r'\s*\|\s*[^|]+$',  # " | Site Name"
        r'\s*-\s*[^-]+$',   # " - Company" (only last one)
        r'\s*–\s*[^–]+$',   # " – Company" (en-dash)
        r'\s*—\s*[^—]+$',   # " — Company" (em-dash)
    ]

    cleaned = title
    for pattern in patterns:
        # Only apply if it doesn't remove too much
        result = re.sub(pattern, '', cleaned)
        if len(result) > 10:  # Keep at least 10 chars
            cleaned = result
            break

    return cleaned.strip()


def _html_to_text(html: str) -> str:
    """
    Convert HTML to clean plain text.

    Preserves paragraph structure while removing all HTML tags.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("BeautifulSoup not installed")
        return ""

    if not html:
        return ""

    soup = BeautifulSoup(html, 'html.parser')

    # Remove any remaining script/style tags
    for tag in soup.find_all(['script', 'style', 'noscript']):
        tag.decompose()

    # Add markers to preserve list item separation
    for li in soup.find_all('li'):
        li_text = li.get_text(strip=True)
        if li_text:
            li.append(' \u25c6')  # Diamond marker

    # Get text with space separator
    text = soup.get_text(separator=' ', strip=True)

    # Post-process: convert marker to comma before uppercase
    text = re.sub(r' \u25c6(?=\s*[A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1])', ',', text)
    text = re.sub(r' \u25c6', '', text)  # Remove remaining markers

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)

    # Remove common noise phrases
    text = re.sub(r'Cookie\s+Policy.*?Accept', '', text, flags=re.I)
    text = re.sub(r'We use cookies.*?\.', '', text, flags=re.I)

    return text.strip()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================
def get_readability_stats() -> dict:
    """
    Get Readability module status and configuration.

    Useful for debugging and health checks.
    """
    return {
        "available": _READABILITY_AVAILABLE,
        "enabled": READABILITY_ENABLED,
        "active": is_readability_available(),
        "min_content": READABILITY_MIN_CONTENT,
    }
