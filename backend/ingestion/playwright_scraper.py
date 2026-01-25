"""
Playwright-based scraper for JavaScript-rendered websites.

Falls back from DeterministicScraper when JS rendering is needed.
Uses Chromium in headless mode to render SPAs, Webflow, Wix, etc.

Usage:
    scraper = get_playwright_scraper()
    page = await scraper.scrape_page("https://example.com", "creator_123")
    await scraper.close()  # Cleanup when done

Configuration (env vars):
    SCRAPER_USE_PLAYWRIGHT=true      # Enable/disable (default: true)
    PLAYWRIGHT_TIMEOUT=30000         # Page load timeout in ms (default: 30s)
    PLAYWRIGHT_HEADLESS=true         # Headless mode (default: true)
"""

import os
import re
import time
import logging
import asyncio
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================
PLAYWRIGHT_ENABLED = os.getenv("SCRAPER_USE_PLAYWRIGHT", "true").lower() in ("true", "1", "yes")
PLAYWRIGHT_TIMEOUT = int(os.getenv("PLAYWRIGHT_TIMEOUT", "30000"))  # 30s default
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() in ("true", "1", "yes")

# Import SSL config from deterministic_scraper
VERIFY_SSL = os.getenv("SCRAPER_VERIFY_SSL", "false").lower() in ("true", "1", "yes")


# =============================================================================
# PLAYWRIGHT AVAILABILITY CHECK
# =============================================================================
_PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    logger.warning(
        "Playwright not installed. Install with: pip install playwright && playwright install chromium"
    )


def is_playwright_available() -> bool:
    """Check if Playwright is available and enabled."""
    return _PLAYWRIGHT_AVAILABLE and PLAYWRIGHT_ENABLED


# =============================================================================
# SCRAPER CLASS
# =============================================================================
class PlaywrightScraper:
    """
    Scraper that renders JavaScript using Playwright/Chromium.

    Features:
    - Headless Chromium browser
    - Waits for network idle (JS fully loaded)
    - Reuses browser instance for performance
    - Integrates with existing circuit breaker and metrics
    - Configurable timeout
    """

    # Elements to remove (same as DeterministicScraper)
    NOISE_ELEMENTS = [
        'script', 'style', 'noscript', 'iframe', 'nav', 'footer',
        'header', 'aside', 'form', 'input', 'select',
        '[class*="cookie"]', '[class*="popup"]', '[class*="modal"]',
        '[class*="sidebar"]', '[class*="menu"]', '[class*="nav"]',
        '[id*="cookie"]', '[id*="popup"]', '[id*="modal"]'
    ]

    def __init__(self, timeout: int = PLAYWRIGHT_TIMEOUT, headless: bool = PLAYWRIGHT_HEADLESS):
        """
        Initialize PlaywrightScraper.

        Args:
            timeout: Page load timeout in milliseconds
            headless: Whether to run browser in headless mode
        """
        self.timeout = timeout
        self.headless = headless
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self):
        """Ensure browser is initialized (lazy loading)."""
        if self._browser is None:
            async with self._lock:
                # Double-check after acquiring lock
                if self._browser is None:
                    if not _PLAYWRIGHT_AVAILABLE:
                        raise RuntimeError(
                            "Playwright not available. Install with: "
                            "pip install playwright && playwright install chromium"
                        )

                    self._playwright = await async_playwright().start()
                    self._browser = await self._playwright.chromium.launch(
                        headless=self.headless
                    )
                    logger.info(f"Playwright browser initialized (headless={self.headless})")

    async def scrape_page(self, url: str, creator_id: str = "unknown") -> Optional["ScrapedPage"]:
        """
        Scrape a page with full JavaScript rendering.

        Uses Chromium in headless mode to:
        1. Load the page
        2. Wait for network idle (JS loaded)
        3. Extract rendered HTML
        4. Process with BeautifulSoup

        Args:
            url: URL to scrape
            creator_id: Creator ID for metrics tracking

        Returns:
            ScrapedPage with extracted content, or None if failed
        """
        # Import here to avoid circular imports
        from ingestion.deterministic_scraper import (
            ScrapedPage,
            get_robots_checker,
            scraper_circuit_breaker,
            VERIFY_SSL
        )
        from core.metrics import (
            record_page_scraped,
            record_page_failed,
            observe_scrape_duration,
            record_ingestion_error
        )
        import pybreaker

        if not is_playwright_available():
            logger.debug("Playwright not available, skipping")
            return None

        # Check robots.txt
        robots_checker = get_robots_checker()
        if not robots_checker.is_allowed(url):
            logger.info(f"Playwright: Blocked by robots.txt: {url}")
            return None

        start_time = time.time()

        try:
            # Use circuit breaker for the page load
            html, final_url = await scraper_circuit_breaker.call_async(
                self._fetch_rendered_html,
                url
            )

            if html is None:
                return None

            # Parse with BeautifulSoup
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            # Extract title
            title = ""
            if soup.title:
                title = soup.title.get_text(strip=True)
            elif soup.h1:
                title = soup.h1.get_text(strip=True)

            # Find main content area
            main_soup = soup.find('main') or soup.find('article') or soup.find('body')
            if not main_soup:
                main_soup = soup

            # Extract content
            main_content = self._extract_text_from_soup(main_soup)
            sections = self._extract_sections(main_soup)

            # Extract metadata
            metadata = {"rendered_by": "playwright"}
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                metadata['description'] = meta_desc['content']

            # Record success metrics
            duration = time.time() - start_time
            observe_scrape_duration(duration)
            record_page_scraped(creator_id)

            logger.info(f"Playwright scraped {url}: {len(main_content)} chars in {duration:.2f}s")

            return ScrapedPage(
                url=final_url,
                title=title,
                main_content=main_content,
                sections=sections,
                links=[],  # Don't extract links in fallback mode
                metadata=metadata
            )

        except pybreaker.CircuitBreakerError:
            logger.warning(f"Playwright: Circuit breaker OPEN - skipping {url}")
            record_page_failed(creator_id, "circuit_breaker_open")
            return None
        except PlaywrightTimeout:
            logger.warning(f"Playwright: Timeout loading {url}")
            record_page_failed(creator_id, "playwright_timeout")
            record_ingestion_error("playwright_timeout")
            return None
        except Exception as e:
            logger.error(f"Playwright: Error scraping {url}: {e}")
            record_page_failed(creator_id, "playwright_error")
            record_ingestion_error("playwright_error")
            return None

    async def _fetch_rendered_html(self, url: str) -> tuple:
        """
        Fetch and render page HTML with Playwright.

        Returns:
            Tuple of (html_content, final_url) or (None, None) if failed
        """
        await self._ensure_browser()

        context = await self._browser.new_context(
            ignore_https_errors=not VERIFY_SSL,
            user_agent="Mozilla/5.0 (compatible; ClonnectBot/1.0; +https://clonnect.com)"
        )

        page = None
        try:
            page = await context.new_page()

            # Navigate with network idle wait
            response = await page.goto(
                url,
                wait_until="networkidle",
                timeout=self.timeout
            )

            if response is None:
                logger.warning(f"Playwright: No response for {url}")
                return (None, url)

            if response.status >= 500:
                raise Exception(f"Server error {response.status} for {url}")

            if response.status == 429:
                raise Exception(f"Rate limited (429) for {url}")

            if response.status != 200:
                logger.warning(f"Playwright: Got status {response.status} for {url}")
                return (None, url)

            # Get rendered HTML
            html = await page.content()
            final_url = page.url

            return (html, final_url)

        finally:
            if page:
                await page.close()
            await context.close()

    def _clean_text(self, text: str) -> str:
        """Clean extracted text."""
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'Cookie\s+Policy.*?Accept', '', text, flags=re.I)
        text = re.sub(r'We use cookies.*?\.', '', text, flags=re.I)
        return text.strip()

    def _extract_text_from_soup(self, soup) -> str:
        """Extract clean text from BeautifulSoup object."""
        # Remove noise elements
        for selector in self.NOISE_ELEMENTS:
            for element in soup.select(selector):
                element.decompose()

        # Add markers to list items for separation
        for li in soup.find_all('li'):
            li_text = li.get_text(strip=True)
            if li_text:
                li.append(' \u25c6')

        # Get text
        text = soup.get_text(separator=' ', strip=True)

        # Convert marker to comma before uppercase
        text = re.sub(r' \u25c6(?=\s*[A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1])', ',', text)
        text = re.sub(r' \u25c6', '', text)

        return self._clean_text(text)

    def _extract_sections(self, soup) -> list:
        """Extract sections with headings."""
        sections = []

        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4']):
            heading_text = heading.get_text(strip=True)
            if not heading_text or len(heading_text) < 3:
                continue

            content_parts = []
            for sibling in heading.find_next_siblings():
                if sibling.name in ['h1', 'h2', 'h3', 'h4']:
                    break
                text = sibling.get_text(strip=True)
                if text:
                    content_parts.append(text)

            if content_parts:
                sections.append({
                    'heading': heading_text,
                    'content': ' '.join(content_parts),
                    'level': heading.name
                })

        return sections

    async def close(self):
        """Close browser and cleanup resources."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("Playwright browser closed")


# =============================================================================
# SINGLETON
# =============================================================================
_playwright_scraper: Optional[PlaywrightScraper] = None


def get_playwright_scraper() -> PlaywrightScraper:
    """Get or create PlaywrightScraper instance."""
    global _playwright_scraper
    if _playwright_scraper is None:
        _playwright_scraper = PlaywrightScraper()
    return _playwright_scraper


async def cleanup_playwright():
    """Cleanup Playwright resources. Call on application shutdown."""
    global _playwright_scraper
    if _playwright_scraper:
        await _playwright_scraper.close()
        _playwright_scraper = None
