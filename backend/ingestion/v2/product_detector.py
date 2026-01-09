"""
ProductDetector - Conservative signal-based product detection
Principle: Better to miss a product than to invent one
"""

import re
import logging
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from .models import ScrapedPage, SignalResult, DetectedProduct, ProductSignal

logger = logging.getLogger(__name__)


class SuspiciousExtractionError(Exception):
    """Raised when extraction results are suspicious (e.g., too many products)"""
    pass


class ProductDetector:
    """
    Detects REAL products using multiple signals.
    Conservative: requires minimum 3 signals to consider something a product.
    """

    REQUIRED_SIGNALS = 3  # Minimum signals to consider something a product
    MAX_PRODUCTS = 20     # If more than this, something is wrong

    # URL patterns that indicate service/product pages
    SERVICE_URL_PATTERNS = [
        r'/servicio', r'/service', r'/producto', r'/product',
        r'/curso', r'/course', r'/programa', r'/program',
        r'/coaching', r'/mentoria', r'/taller', r'/workshop',
        r'/sesion', r'/session', r'/challenge', r'/pack',
        r'/pricing', r'/precio', r'/oferta', r'/offer',
        r'/membership', r'/membresia', r'/suscripcion',
        r'/formacion', r'/training', r'/masterclass',
        r'/retiro', r'/retreat', r'/evento', r'/event'
    ]

    # CTA patterns (call-to-action words)
    CTA_PATTERNS = [
        r'\bcomprar\b', r'\bcompra\b', r'\breservar\b', r'\breserva\b',
        r'\bcontratar\b', r'\bcontrata\b', r'\bapúntate\b', r'\bapuntate\b',
        r'\binscríbete\b', r'\binscribete\b', r'\bquiero\b', r'\bempezar\b',
        r'\bacceder\b', r'\búnete\b', r'\bunete\b', r'\bregistrar\b',
        r'\bbuy\b', r'\bbook\b', r'\bjoin\b', r'\benroll\b', r'\bget\s+started\b',
        r'\bsign\s+up\b', r'\bstart\s+now\b', r'\bagendar\b', r'\bagenda\b'
    ]

    # Payment platform domains
    PAYMENT_DOMAINS = [
        'stripe.com', 'paypal.com', 'paypal.me', 'calendly.com',
        'gumroad.com', 'hotmart.com', 'thinkific.com', 'teachable.com',
        'kajabi.com', 'podia.com', 'checkout.', 'pay.', 'booking.',
        'typeform.com', 'tally.so'
    ]

    # Price patterns (EUR focused, can extend)
    PRICE_PATTERNS = [
        r'€\s*(\d+(?:[.,]\d{2})?)',           # €22, €22.00, €22,00
        r'(\d+(?:[.,]\d{2})?)\s*€',           # 22€, 22.00€
        r'(\d+(?:[.,]\d{2})?)\s*EUR',         # 22 EUR
        r'EUR\s*(\d+(?:[.,]\d{2})?)',         # EUR 22
        r'(\d+(?:[.,]\d{2})?)\s*euros?',      # 22 euros
        r'\$\s*(\d+(?:[.,]\d{2})?)',          # $22
        r'(\d+(?:[.,]\d{2})?)\s*USD',         # 22 USD
    ]

    def detect_products(self, pages: List[ScrapedPage], base_domain: str) -> List[DetectedProduct]:
        """
        Main entry point: detect products from scraped pages.
        Returns only products with 3+ signals.
        Raises SuspiciousExtractionError if > MAX_PRODUCTS found.
        """
        candidates = []

        # 1. Identify service pages (not blogs, not about, not contact)
        service_pages = self._identify_service_pages(pages)
        logger.info(f"[ProductDetector] Found {len(service_pages)} potential service pages out of {len(pages)} total")

        # 2. Extract navigation links to know what's promoted as service
        nav_links = self._extract_navigation_links(pages)

        for page in service_pages:
            signals = self._count_signals(page, nav_links)

            if signals.count >= self.REQUIRED_SIGNALS:
                # Only create product if we have enough signals
                product = DetectedProduct(
                    name=signals.name or self._extract_page_title(page),
                    description=signals.description,
                    price=signals.price,
                    price_text=signals.price_text,
                    source_url=page.url,
                    source_html=signals.source_html,
                    signals_matched=signals.matched,
                    confidence=min(signals.count / 6, 1.0)  # Max 6 signals
                )
                candidates.append(product)
                logger.info(f"[ProductDetector] Detected: {product.name} ({signals.count} signals: {signals.matched})")
            else:
                logger.debug(f"[ProductDetector] Rejected {page.url}: only {signals.count} signals ({signals.matched})")

        # SANITY CHECK: If too many products, something is wrong
        if len(candidates) > self.MAX_PRODUCTS:
            raise SuspiciousExtractionError(
                f"Detected {len(candidates)} products, which exceeds maximum of {self.MAX_PRODUCTS}. "
                "This suggests the extraction is too liberal. Aborting."
            )

        return candidates

    def _identify_service_pages(self, pages: List[ScrapedPage]) -> List[ScrapedPage]:
        """
        Identify pages that are likely service/product pages.
        Filter out blogs, about, contact, legal pages.
        """
        service_pages = []

        # Patterns to EXCLUDE (not service pages)
        exclude_patterns = [
            r'/blog', r'/post', r'/article', r'/noticias', r'/news',
            r'/about', r'/sobre', r'/quienes-somos', r'/acerca',
            r'/contact', r'/contacto', r'/contacta',
            r'/privacy', r'/privacidad', r'/legal', r'/terms', r'/terminos',
            r'/faq', r'/preguntas', r'/ayuda', r'/help',
            r'/login', r'/register', r'/cuenta', r'/account',
            r'/cart', r'/carrito', r'/checkout',
            r'/tag/', r'/category/', r'/categoria/'
        ]

        for page in pages:
            url_lower = page.url.lower()

            # Skip excluded pages
            if any(re.search(pat, url_lower) for pat in exclude_patterns):
                continue

            # Include if URL matches service patterns
            if any(re.search(pat, url_lower) for pat in self.SERVICE_URL_PATTERNS):
                service_pages.append(page)
                continue

            # Include homepage (might list services)
            parsed = urlparse(page.url)
            if parsed.path in ['', '/', '/index.html', '/index.php']:
                # Homepage - check if it has service CTAs
                if self._has_service_indicators(page):
                    service_pages.append(page)
                continue

            # Include if page has strong service indicators
            if self._has_strong_service_indicators(page):
                service_pages.append(page)

        return service_pages

    def _has_service_indicators(self, page: ScrapedPage) -> bool:
        """Check if page has basic service indicators"""
        text_lower = page.extracted_text.lower()
        return any(re.search(pat, text_lower, re.IGNORECASE) for pat in self.CTA_PATTERNS[:5])

    def _has_strong_service_indicators(self, page: ScrapedPage) -> bool:
        """Check if page has strong service indicators (price + CTA)"""
        text_lower = page.extracted_text.lower()
        has_cta = any(re.search(pat, text_lower, re.IGNORECASE) for pat in self.CTA_PATTERNS)
        has_price = any(re.search(pat, page.extracted_text, re.IGNORECASE) for pat in self.PRICE_PATTERNS)
        return has_cta and has_price

    def _extract_navigation_links(self, pages: List[ScrapedPage]) -> List[str]:
        """Extract links from navigation menus to identify promoted services"""
        nav_links = []

        for page in pages:
            soup = BeautifulSoup(page.raw_html, 'html.parser')

            # Look for nav elements
            navs = soup.find_all(['nav', 'header'])
            for nav in navs:
                links = nav.find_all('a', href=True)
                for link in links:
                    href = link['href']
                    if href.startswith('/') or href.startswith('http'):
                        nav_links.append(href.lower())

        return list(set(nav_links))

    def _count_signals(self, page: ScrapedPage, nav_links: List[str]) -> SignalResult:
        """Count product signals on a page"""
        signals = []
        soup = BeautifulSoup(page.raw_html, 'html.parser')
        text_lower = page.extracted_text.lower()

        # Extract basic info
        name = None
        description = None
        price = None
        price_text = None

        # SIGNAL 1: Dedicated page (has service URL pattern)
        if self._is_dedicated_page(page.url):
            signals.append(ProductSignal.DEDICATED_PAGE.value)

        # SIGNAL 2: CTA present
        if any(re.search(pat, text_lower, re.IGNORECASE) for pat in self.CTA_PATTERNS):
            signals.append(ProductSignal.CTA_PRESENT.value)

        # SIGNAL 3: Price visible
        price_result = self._extract_price(page.extracted_text)
        if price_result:
            price, price_text = price_result
            signals.append(ProductSignal.PRICE_VISIBLE.value)

        # SIGNAL 4: Substantial description (>50 words in main content)
        main_content = self._get_main_content(soup)
        if main_content and len(main_content.split()) > 50:
            signals.append(ProductSignal.SUBSTANTIAL_DESC.value)
            description = main_content[:1000]  # First 1000 chars

        # SIGNAL 5: Payment link present
        if self._has_payment_link(soup):
            signals.append(ProductSignal.PAYMENT_LINK.value)

        # SIGNAL 6: Clear title (h1)
        h1 = soup.find('h1')
        if h1:
            title_text = h1.get_text(strip=True)
            if title_text and 3 < len(title_text) < 150:
                name = title_text
                signals.append(ProductSignal.CLEAR_TITLE.value)

        # SIGNAL 7: In navigation
        url_lower = page.url.lower()
        if any(url_lower in nav or nav in url_lower for nav in nav_links if len(nav) > 5):
            signals.append(ProductSignal.IN_NAVIGATION.value)

        # Get source HTML (relevant section)
        source_html = self._extract_relevant_html(soup)

        return SignalResult(
            name=name,
            description=description,
            price=price,
            price_text=price_text,
            source_html=source_html,
            matched=signals,
            count=len(signals)
        )

    def _is_dedicated_page(self, url: str) -> bool:
        """Check if URL is a dedicated service page (not homepage)"""
        parsed = urlparse(url)
        path = parsed.path.lower()

        # Not homepage
        if path in ['', '/', '/index.html', '/index.php']:
            return False

        # Has meaningful path
        return len(path) > 3

    def _extract_price(self, text: str) -> Optional[Tuple[float, str]]:
        """Extract price from text, return (value, original_text) or None"""
        for pattern in self.PRICE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    # Get the full match context
                    start = max(0, match.start() - 20)
                    end = min(len(text), match.end() + 20)
                    context = text[start:end].strip()

                    # Parse price value
                    price_str = match.group(1)
                    price_str = price_str.replace(',', '.')
                    price = float(price_str)

                    # Sanity check: price between 1 and 50000
                    if 1 <= price <= 50000:
                        return (price, context)
                except (ValueError, IndexError):
                    continue

        return None

    def _get_main_content(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract main content text from page"""
        # Try common main content containers
        main_selectors = [
            'main', 'article', '[role="main"]',
            '.content', '.main-content', '#content', '#main',
            '.entry-content', '.post-content', '.page-content'
        ]

        for selector in main_selectors:
            main = soup.select_one(selector)
            if main:
                # Remove script and style
                for tag in main.find_all(['script', 'style', 'nav', 'footer', 'header']):
                    tag.decompose()
                text = main.get_text(separator=' ', strip=True)
                if len(text) > 100:
                    return text

        # Fallback: body content
        body = soup.find('body')
        if body:
            for tag in body.find_all(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()
            return body.get_text(separator=' ', strip=True)

        return None

    def _has_payment_link(self, soup: BeautifulSoup) -> bool:
        """Check if page has links to payment platforms"""
        links = soup.find_all('a', href=True)

        for link in links:
            href = link['href'].lower()
            if any(domain in href for domain in self.PAYMENT_DOMAINS):
                return True

        # Also check for forms that might be payment
        forms = soup.find_all('form')
        for form in forms:
            action = form.get('action', '').lower()
            if any(domain in action for domain in self.PAYMENT_DOMAINS):
                return True

        return False

    def _extract_relevant_html(self, soup: BeautifulSoup) -> str:
        """Extract relevant HTML section as proof"""
        # Try to get the main content area
        main = soup.find('main') or soup.find('article') or soup.find('body')
        if main:
            # Get first 2000 chars of HTML
            html = str(main)
            return html[:2000] if len(html) > 2000 else html
        return ""

    def _extract_page_title(self, page: ScrapedPage) -> str:
        """Extract page title as fallback"""
        soup = BeautifulSoup(page.raw_html, 'html.parser')

        # Try h1 first
        h1 = soup.find('h1')
        if h1:
            return h1.get_text(strip=True)

        # Try title tag
        title = soup.find('title')
        if title:
            text = title.get_text(strip=True)
            # Remove site name if present
            if ' | ' in text:
                return text.split(' | ')[0]
            if ' - ' in text:
                return text.split(' - ')[0]
            return text

        # Fallback to URL
        parsed = urlparse(page.url)
        return parsed.path.strip('/').replace('-', ' ').title()
