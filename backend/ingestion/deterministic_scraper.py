"""
Deterministic Website Scraper - NO LLM, NO HALLUCINATIONS.

This scraper uses BeautifulSoup to extract raw content from websites.
It does NOT interpret or summarize content - just extracts what's there.

Anti-hallucination principles:
1. Extract text exactly as it appears on the page
2. Track source_url for every piece of content
3. No creative interpretation - just structured extraction
"""

import os
import re
import ssl
import time
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from datetime import datetime

import httpx
import pybreaker

from core.metrics import (
    record_page_scraped,
    record_page_failed,
    observe_scrape_duration,
    record_ingestion_error
)

logger = logging.getLogger(__name__)

# =============================================================================
# SSL CONFIGURATION
# =============================================================================
# SSL verification is ENABLED by default for security.
# Set SCRAPER_VERIFY_SSL=false only for development/testing with self-signed certs.
VERIFY_SSL = os.getenv("SCRAPER_VERIFY_SSL", "true").lower() in ("true", "1", "yes")

# =============================================================================
# ROBOTS.TXT CONFIGURATION (BUG-003 FIX)
# =============================================================================
# Respect robots.txt is ENABLED by default for legal/ethical compliance.
# Set SCRAPER_RESPECT_ROBOTS=false to disable (not recommended for production).
RESPECT_ROBOTS_TXT = os.getenv("SCRAPER_RESPECT_ROBOTS", "true").lower() in ("true", "1", "yes")

# Cache TTL for robots.txt (in seconds) - default 1 hour
ROBOTS_TXT_CACHE_TTL = int(os.getenv("SCRAPER_ROBOTS_CACHE_TTL", "3600"))

# User agent to identify as when checking robots.txt
SCRAPER_USER_AGENT = "ClonnectBot"


class RobotsTxtChecker:
    """
    Checks robots.txt compliance with domain-level caching.

    Features:
    - Caches parsed robots.txt per domain
    - TTL-based cache expiration
    - Graceful handling of fetch failures (allow by default)
    - Async-compatible synchronous fetching
    """

    def __init__(self, user_agent: str = SCRAPER_USER_AGENT, cache_ttl: int = ROBOTS_TXT_CACHE_TTL):
        self.user_agent = user_agent
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple] = {}  # domain -> (parser, timestamp)

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _is_cache_valid(self, domain: str) -> bool:
        """Check if cached robots.txt is still valid."""
        if domain not in self._cache:
            return False
        _, timestamp = self._cache[domain]
        return (time.time() - timestamp) < self.cache_ttl

    def _fetch_robots_txt(self, domain: str) -> Optional[RobotFileParser]:
        """
        Fetch and parse robots.txt for a domain.

        Returns None if fetch fails (we'll allow access by default).
        """
        robots_url = f"{domain}/robots.txt"
        parser = RobotFileParser()
        parser.set_url(robots_url)

        try:
            # Use httpx for consistency (sync version for robotparser compatibility)
            import httpx
            response = httpx.get(
                robots_url,
                timeout=5.0,
                follow_redirects=True,
                verify=VERIFY_SSL,
                headers={"User-Agent": f"Mozilla/5.0 (compatible; {self.user_agent}/1.0)"}
            )

            if response.status_code == 200:
                # Parse the robots.txt content
                parser.parse(response.text.splitlines())
                return parser
            elif response.status_code in (404, 410):
                # No robots.txt = allow all
                logger.debug(f"No robots.txt found at {robots_url} (status {response.status_code})")
                return None
            else:
                logger.warning(f"Unexpected status {response.status_code} fetching {robots_url}")
                return None

        except httpx.TimeoutException:
            logger.warning(f"Timeout fetching robots.txt from {domain}")
            return None
        except Exception as e:
            logger.warning(f"Error fetching robots.txt from {domain}: {e}")
            return None

    def is_allowed(self, url: str) -> bool:
        """
        Check if scraping this URL is allowed by robots.txt.

        Returns True if:
        - robots.txt allows the URL
        - robots.txt doesn't exist (404)
        - robots.txt fetch failed (fail-open for availability)

        Returns False if:
        - robots.txt explicitly disallows the URL
        """
        if not RESPECT_ROBOTS_TXT:
            return True

        domain = self._get_domain(url)

        # Check cache first
        if not self._is_cache_valid(domain):
            parser = self._fetch_robots_txt(domain)
            self._cache[domain] = (parser, time.time())
        else:
            parser, _ = self._cache[domain]

        # No parser = no robots.txt = allow all
        if parser is None:
            return True

        # Check if our user agent is allowed
        path = urlparse(url).path or "/"
        allowed = parser.can_fetch(self.user_agent, path)

        if not allowed:
            logger.info(f"robots.txt disallows {url} for {self.user_agent}")

        return allowed

    def clear_cache(self):
        """Clear the robots.txt cache."""
        self._cache.clear()


# Global robots.txt checker instance
_robots_checker: Optional[RobotsTxtChecker] = None


def get_robots_checker() -> RobotsTxtChecker:
    """Get or create the global robots.txt checker."""
    global _robots_checker
    if _robots_checker is None:
        _robots_checker = RobotsTxtChecker()
    return _robots_checker


# =============================================================================
# CIRCUIT BREAKER CONFIGURATION
# =============================================================================
# Circuit breaker protects the system when websites are consistently failing.
# After FAILURE_THRESHOLD consecutive failures for a domain, the circuit "opens"
# and rejects requests for RECOVERY_TIMEOUT seconds before testing again.

SCRAPER_CIRCUIT_FAILURE_THRESHOLD = int(os.getenv("SCRAPER_CIRCUIT_FAILURE_THRESHOLD", "5"))
SCRAPER_CIRCUIT_RECOVERY_TIMEOUT = int(os.getenv("SCRAPER_CIRCUIT_RECOVERY_TIMEOUT", "30"))


class ScraperCircuitBreakerListener(pybreaker.CircuitBreakerListener):
    """Listener to log circuit breaker state changes for website scraper."""

    def __init__(self, name: str):
        self.name = name

    def state_change(self, cb, old_state, new_state):
        """Log when circuit state changes."""
        logger.warning(
            f"Circuit breaker [{self.name}] state changed: {old_state.name} -> {new_state.name}"
        )
        if new_state == pybreaker.STATE_OPEN:
            logger.error(
                f"Circuit [{self.name}] OPENED - Too many scraping failures. "
                f"Requests will be rejected for {cb.reset_timeout} seconds."
            )
        elif new_state == pybreaker.STATE_HALF_OPEN:
            logger.info(f"Circuit [{self.name}] HALF-OPEN - Testing if scraping works again.")
        elif new_state == pybreaker.STATE_CLOSED:
            logger.info(f"Circuit [{self.name}] CLOSED - Scraping resumed normally.")

    def failure(self, cb, exc):
        """Log failures tracked by circuit breaker."""
        logger.debug(f"Circuit [{self.name}] recorded failure ({cb.fail_counter}/{cb.fail_max}): {exc}")


# Circuit breaker for web scraping
scraper_circuit_breaker = pybreaker.CircuitBreaker(
    fail_max=SCRAPER_CIRCUIT_FAILURE_THRESHOLD,
    reset_timeout=SCRAPER_CIRCUIT_RECOVERY_TIMEOUT,
    listeners=[ScraperCircuitBreakerListener("web_scraper")],
    name="web_scraper"
)


class ScraperCircuitBreakerOpenError(Exception):
    """Raised when scraper circuit breaker is open."""
    pass


@dataclass
class ScrapedPage:
    """Represents a scraped page with its raw content."""
    url: str
    title: str
    main_content: str
    sections: List[Dict[str, str]] = field(default_factory=list)  # [{heading, content}]
    links: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    scraped_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def has_content(self) -> bool:
        """Check if page has meaningful content."""
        return len(self.main_content.strip()) > 100


class DeterministicScraper:
    """
    Deterministic web scraper using BeautifulSoup.
    No LLM, no AI, no hallucinations - just parsing HTML.
    """

    # URLs/patterns to skip
    SKIP_PATTERNS = [
        r'/login', r'/signin', r'/signup', r'/register',
        r'/cart', r'/checkout', r'/account', r'/admin',
        r'/privacy', r'/terms', r'/legal', r'/cookie',
        r'facebook\.com', r'twitter\.com', r'instagram\.com',
        r'youtube\.com', r'linkedin\.com', r'tiktok\.com',
        r'\.pdf$', r'\.zip$', r'\.exe$', r'\.dmg$', r'\.mp4$', r'\.mp3$'
    ]

    # Elements to remove (noise)
    # NOTE: Don't remove 'button' - accordion FAQs often use buttons for titles
    NOISE_ELEMENTS = [
        'script', 'style', 'noscript', 'iframe', 'nav', 'footer',
        'header', 'aside', 'form', 'input', 'select',
        '[class*="cookie"]', '[class*="popup"]', '[class*="modal"]',
        '[class*="sidebar"]', '[class*="menu"]', '[class*="nav"]',
        '[id*="cookie"]', '[id*="popup"]', '[id*="modal"]'
    ]

    def __init__(self, timeout: float = 15.0, max_pages: int = 100):
        self.timeout = timeout
        self.max_pages = max_pages
        self._visited: set = set()

    def _should_skip_url(self, url: str) -> bool:
        """Check if URL should be skipped."""
        return any(re.search(p, url, re.I) for p in self.SKIP_PATTERNS)

    def _clean_text(self, text: str) -> str:
        """Clean extracted text."""
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove common noise
        text = re.sub(r'Cookie\s+Policy.*?Accept', '', text, flags=re.I)
        text = re.sub(r'We use cookies.*?\.', '', text, flags=re.I)
        return text.strip()

    def _extract_text_from_soup(self, soup) -> str:
        """Extract clean text from BeautifulSoup object."""
        # Remove noise elements
        for selector in self.NOISE_ELEMENTS:
            for element in soup.select(selector):
                element.decompose()

        # PRE-PROCESO: Añadir marcador a elementos de lista para preservar separación
        for li in soup.find_all('li'):
            li_text = li.get_text(strip=True)
            if li_text:
                # Añadir marcador temporal al final
                li.append(' ◆')

        # Get text
        text = soup.get_text(separator=' ', strip=True)

        # POST-PROCESO: Convertir marcador a coma antes de mayúscula
        text = re.sub(r' ◆(?=\s*[A-ZÁÉÍÓÚÑ])', ',', text)
        # Limpiar marcadores residuales (al final o antes de minúscula)
        text = re.sub(r' ◆', '', text)

        return self._clean_text(text)

    def _extract_sections(self, soup) -> List[Dict[str, str]]:
        """Extract sections with headings."""
        sections = []

        # Find all heading elements
        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4']):
            heading_text = heading.get_text(strip=True)
            if not heading_text or len(heading_text) < 3:
                continue

            # Get content after heading until next heading
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

    def _extract_links(self, soup, base_url: str) -> List[str]:
        """Extract internal links from page."""
        links = []
        parsed_base = urlparse(base_url)

        for a in soup.find_all('a', href=True):
            href = a['href']

            # Skip anchors and javascript
            if href.startswith('#') or href.startswith('javascript:'):
                continue

            # Convert to absolute URL
            absolute_url = urljoin(base_url, href)
            parsed = urlparse(absolute_url)

            # Only include same domain
            if parsed.netloc != parsed_base.netloc:
                continue

            # Clean URL (remove fragment and query)
            clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            clean_url = clean_url.rstrip('/')

            if clean_url and clean_url not in links and not self._should_skip_url(clean_url):
                links.append(clean_url)

        return links[:30]  # Limit

    async def scrape_page(self, url: str, creator_id: str = "unknown") -> Optional[ScrapedPage]:
        """
        Scrape a single page deterministically.

        Args:
            url: URL to scrape
            creator_id: Creator ID for metrics tracking

        Returns:
            ScrapedPage with extracted content, or None if failed

        Note:
            Uses circuit breaker to prevent cascading failures when
            websites are down or returning errors consistently.
        """
        start_time = time.time()

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("BeautifulSoup not installed. Run: pip install beautifulsoup4")
            record_page_failed(creator_id, "import_error")
            return None

        if self._should_skip_url(url):
            logger.debug(f"Skipping URL: {url}")
            return None

        # BUG-003 FIX: Check robots.txt compliance
        robots_checker = get_robots_checker()
        if not robots_checker.is_allowed(url):
            logger.info(f"Blocked by robots.txt: {url}")
            return None

        try:
            # Circuit breaker wraps the HTTP fetch
            html, response_url = await self._fetch_page_with_circuit_breaker(url)
            if html is None:
                return None

            soup = BeautifulSoup(html, 'html.parser')

            # Extract title (will be overridden by Readability if successful)
            title = ""
            if soup.title:
                title = soup.title.get_text(strip=True)
            elif soup.h1:
                title = soup.h1.get_text(strip=True)

            # IMPORTANTE: Extraer links ANTES de modificar el soup
            # (decompose() destruye elementos permanentemente)
            links = self._extract_links(soup, response_url)

            # Try Readability first for better content extraction
            main_content = None
            sections = []
            readability_used = False

            try:
                from ingestion.content_extractor import extract_with_readability, is_readability_available
                if is_readability_available():
                    r_title, r_content, r_success = extract_with_readability(html, response_url)
                    if r_success and r_content:
                        main_content = r_content
                        if r_title:
                            title = r_title
                        readability_used = True
                        logger.debug(f"Readability extracted {len(main_content)} chars from {url}")
            except ImportError:
                logger.debug("Readability not available")
            except Exception as e:
                logger.warning(f"Readability failed for {url}: {e}")

            # Fallback to manual extraction if Readability didn't work
            if not readability_used:
                # Find main content area
                main_soup = soup.find('main') or soup.find('article') or soup.find('body')
                if not main_soup:
                    main_soup = soup

                # Extract content (esto modifica el soup con decompose())
                main_content = self._extract_text_from_soup(main_soup)
                sections = self._extract_sections(main_soup)

            # Extract metadata
            metadata = {}
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            if meta_desc and meta_desc.get('content'):
                metadata['description'] = meta_desc['content']

            og_image = soup.find('meta', attrs={'property': 'og:image'})
            if og_image and og_image.get('content'):
                metadata['og_image'] = og_image['content']

            # Track extraction method used
            if readability_used:
                metadata['extracted_by'] = 'readability'

            # Check if content is too short - might need JavaScript rendering
            logger.info(f"Content check: main_content={len(main_content) if main_content else 0} chars, threshold=100")
            if not main_content or len(main_content) < 100:
                logger.info(f"Content too short ({len(main_content) if main_content else 0} chars), trying Playwright for {url}")
                try:
                    from ingestion.playwright_scraper import get_playwright_scraper, is_playwright_available
                    if is_playwright_available():
                        playwright_scraper = get_playwright_scraper()
                        # Use _fetch_rendered_html directly to avoid redundant checks
                        # and potential circular import issues with scrape_page
                        pw_html, pw_final_url = await playwright_scraper._fetch_rendered_html(url)
                        if pw_html and len(pw_html) > 500:
                            # Parse the rendered HTML
                            pw_soup = BeautifulSoup(pw_html, 'html.parser')
                            pw_title = ""
                            if pw_soup.title:
                                pw_title = pw_soup.title.get_text(strip=True)
                            elif pw_soup.h1:
                                pw_title = pw_soup.h1.get_text(strip=True)

                            pw_main_soup = pw_soup.find('main') or pw_soup.find('article') or pw_soup.find('body')
                            if not pw_main_soup:
                                pw_main_soup = pw_soup

                            pw_content = self._extract_text_from_soup(pw_main_soup)

                            if pw_content and len(pw_content) > 100:
                                logger.info(f"Playwright fallback successful for {url}: {len(pw_content)} chars")
                                return ScrapedPage(
                                    url=pw_final_url,
                                    title=pw_title or title,
                                    main_content=pw_content,
                                    sections=self._extract_sections(pw_main_soup),
                                    links=links,  # Reuse links already extracted
                                    metadata={**metadata, "rendered_by": "playwright_fallback"}
                                )
                            else:
                                logger.warning(f"Playwright rendered HTML but content still too short: {len(pw_content) if pw_content else 0} chars")
                except ImportError:
                    logger.debug("Playwright not available for fallback")
                except Exception as e:
                    logger.warning(f"Playwright fallback failed for {url}: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())

            # Record success metrics
            duration = time.time() - start_time
            observe_scrape_duration(duration)
            record_page_scraped(creator_id)

            return ScrapedPage(
                url=response_url,
                title=title,
                main_content=main_content,
                sections=sections,
                links=links,
                metadata=metadata
            )

        except pybreaker.CircuitBreakerError:
            logger.warning(
                f"Circuit breaker OPEN - skipping {url}. "
                f"Too many consecutive scraping failures."
            )
            record_page_failed(creator_id, "circuit_breaker_open")
            return None
        except httpx.TimeoutException:
            logger.warning(f"Timeout scraping {url}")
            record_page_failed(creator_id, "timeout")
            record_ingestion_error("scrape_timeout")
            return None
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            record_page_failed(creator_id, "exception")
            record_ingestion_error("scrape_error")
            return None

    async def _fetch_page_with_circuit_breaker(self, url: str) -> tuple:
        """
        Fetch page HTML with circuit breaker protection.

        Returns:
            Tuple of (html_content, final_url) or (None, None) if failed
        """
        return await scraper_circuit_breaker.call_async(
            self._fetch_page_html,
            url
        )

    async def _fetch_page_html(self, url: str) -> tuple:
        """
        Actual HTTP request to fetch page HTML.

        Separated for circuit breaker wrapping.
        Raises exceptions on failure so circuit breaker can track them.
        """
        import httpx

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            verify=VERIFY_SSL,  # Use global SSL config (BUG-004 FIX)
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; ClonnectBot/1.0; +https://clonnect.com)"
            }
        ) as client:
            response = await client.get(url)

            if response.status_code >= 500:
                # Server errors should trip the circuit breaker
                raise Exception(f"Server error {response.status_code} for {url}")

            if response.status_code == 429:
                # Rate limit - trip the circuit breaker
                raise Exception(f"Rate limited (429) for {url}")

            if response.status_code != 200:
                logger.warning(f"Got status {response.status_code} for {url}")
                return (None, url)

            content_type = response.headers.get('content-type', '')
            if 'text/html' not in content_type:
                return (None, url)

            return (response.text, str(response.url))

    async def scrape_website(self, start_url: str) -> List[ScrapedPage]:
        """
        Scrape a website starting from a URL.

        Args:
            start_url: Starting URL

        Returns:
            List of ScrapedPage objects
        """
        pages = []
        to_visit = [start_url]
        self._visited = set()

        while to_visit and len(pages) < self.max_pages:
            current_url = to_visit.pop(0)

            if current_url in self._visited:
                continue

            self._visited.add(current_url)

            page = await self.scrape_page(current_url)
            if page and page.has_content:
                pages.append(page)
                logger.info(f"Scraped {current_url}: {len(page.main_content)} chars, {len(page.sections)} sections")

                # Add discovered links to queue (check robots.txt first)
                robots_checker = get_robots_checker()
                for link in page.links:
                    if link not in self._visited and link not in to_visit:
                        # Pre-check robots.txt to avoid queueing blocked URLs
                        if robots_checker.is_allowed(link):
                            to_visit.append(link)
                        else:
                            logger.debug(f"Not queueing {link} - blocked by robots.txt")

        logger.info(f"Total pages scraped: {len(pages)}")
        return pages


# Singleton
_scraper: Optional[DeterministicScraper] = None

def get_deterministic_scraper(max_pages: int = 100) -> DeterministicScraper:
    """Get or create scraper instance."""
    global _scraper
    if _scraper is None:
        _scraper = DeterministicScraper(max_pages=max_pages)
    return _scraper
