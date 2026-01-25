"""
Deterministic Website Scraper - NO LLM, NO HALLUCINATIONS.

This scraper uses BeautifulSoup to extract raw content from websites.
It does NOT interpret or summarize content - just extracts what's there.

Anti-hallucination principles:
1. Extract text exactly as it appears on the page
2. Track source_url for every piece of content
3. No creative interpretation - just structured extraction
"""

import re
import time
import logging
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from datetime import datetime

from core.metrics import (
    record_page_scraped,
    record_page_failed,
    observe_scrape_duration,
    record_ingestion_error
)

logger = logging.getLogger(__name__)


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
        """
        import httpx
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

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                verify=False,  # Some sites have SSL cert issues
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ClonnectBot/1.0; +https://clonnect.com)"
                }
            ) as client:
                response = await client.get(url)

                if response.status_code != 200:
                    logger.warning(f"Got status {response.status_code} for {url}")
                    return None

                content_type = response.headers.get('content-type', '')
                if 'text/html' not in content_type:
                    return None

                html = response.text
                soup = BeautifulSoup(html, 'html.parser')

                # Extract title
                title = ""
                if soup.title:
                    title = soup.title.get_text(strip=True)
                elif soup.h1:
                    title = soup.h1.get_text(strip=True)

                # IMPORTANTE: Extraer links ANTES de modificar el soup
                # (decompose() destruye elementos permanentemente)
                links = self._extract_links(soup, url)

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

                # Record success metrics
                duration = time.time() - start_time
                observe_scrape_duration(duration)
                record_page_scraped(creator_id)

                return ScrapedPage(
                    url=url,
                    title=title,
                    main_content=main_content,
                    sections=sections,
                    links=links,
                    metadata=metadata
                )

        except httpx.TimeoutException:
            logger.warning(f"Timeout scraping {url}")
            record_page_failed(creator_id, "timeout")
            record_ingestion_error("scrape_timeout")
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            record_page_failed(creator_id, "exception")
            record_ingestion_error("scrape_error")

        return None

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

                # Add discovered links to queue
                for link in page.links:
                    if link not in self._visited and link not in to_visit:
                        to_visit.append(link)

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
