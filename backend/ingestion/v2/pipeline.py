"""
IngestionPipeline - Main orchestrator for Zero-Hallucination Ingestion
Handles: scraping, detection, verification, and database persistence
"""

import hashlib
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse, urljoin
import httpx
from bs4 import BeautifulSoup

from .models import ScrapedPage, DetectedProduct, IngestionResult, CheckResult
from .product_detector import ProductDetector, SuspiciousExtractionError
from .sanity_checker import SanityChecker

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """
    Main pipeline for website ingestion.
    1. Scrapes website
    2. Detects products (conservative)
    3. Verifies with sanity checks
    4. Persists to database (after clearing old data)
    """

    MAX_PAGES = 50  # Maximum pages to scrape
    SCRAPE_TIMEOUT = 15  # Seconds per page

    def __init__(self, db_session=None):
        self.db = db_session
        self.detector = ProductDetector()
        self.checker = SanityChecker()

    async def run(self, creator_id: str, website_url: str) -> IngestionResult:
        """
        Run the full ingestion pipeline.
        Returns IngestionResult with all details.
        """
        started_at = datetime.utcnow()
        errors = []

        # Normalize URL
        website_url = self._normalize_url(website_url)
        base_domain = urlparse(website_url).netloc

        logger.info(f"[Pipeline] Starting ingestion for {creator_id} from {website_url}")

        # Step 1: Scrape website
        try:
            pages = await self._scrape_website(website_url)
            logger.info(f"[Pipeline] Scraped {len(pages)} pages")
        except Exception as e:
            logger.error(f"[Pipeline] Scraping failed: {e}")
            return IngestionResult(
                creator_id=creator_id,
                website_url=website_url,
                pages_scraped=0,
                service_pages_found=0,
                products_detected=0,
                products_verified=0,
                products=[],
                sanity_checks=[],
                status='failed',
                errors=[f"Scraping failed: {str(e)}"],
                started_at=started_at,
                completed_at=datetime.utcnow()
            )

        # Step 2: Detect products (conservative)
        try:
            products = self.detector.detect_products(pages, base_domain)
            logger.info(f"[Pipeline] Detected {len(products)} products")
        except SuspiciousExtractionError as e:
            logger.error(f"[Pipeline] Suspicious extraction: {e}")
            return IngestionResult(
                creator_id=creator_id,
                website_url=website_url,
                pages_scraped=len(pages),
                service_pages_found=0,
                products_detected=0,
                products_verified=0,
                products=[],
                sanity_checks=[
                    CheckResult(
                        name='extraction_sanity',
                        passed=False,
                        message=str(e)
                    )
                ],
                status='aborted',
                errors=[str(e)],
                started_at=started_at,
                completed_at=datetime.utcnow()
            )
        except Exception as e:
            logger.error(f"[Pipeline] Detection failed: {e}")
            errors.append(f"Detection failed: {str(e)}")
            products = []

        # Step 3: Verify with sanity checks
        verification = self.checker.verify(products, website_url)
        verified_products = verification.products

        # Step 4: Clear old data and persist (if we have a DB session)
        if self.db and verified_products:
            try:
                await self._persist_products(creator_id, verified_products)
                logger.info(f"[Pipeline] Persisted {len(verified_products)} products")
            except Exception as e:
                logger.error(f"[Pipeline] Persistence failed: {e}")
                errors.append(f"Persistence failed: {str(e)}")

        return IngestionResult(
            creator_id=creator_id,
            website_url=website_url,
            pages_scraped=len(pages),
            service_pages_found=len([p for p in pages if self._is_service_url(p.url)]),
            products_detected=len(products),
            products_verified=len([p for p in verified_products if p.verified]),
            products=verified_products,
            sanity_checks=verification.checks,
            status=verification.status,
            errors=errors,
            started_at=started_at,
            completed_at=datetime.utcnow()
        )

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for consistent handling"""
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        return url.rstrip('/')

    def _is_service_url(self, url: str) -> bool:
        """Check if URL looks like a service page"""
        url_lower = url.lower()
        service_indicators = [
            '/servicio', '/service', '/producto', '/product',
            '/curso', '/program', '/coaching', '/taller'
        ]
        return any(ind in url_lower for ind in service_indicators)

    async def _scrape_website(self, start_url: str) -> List[ScrapedPage]:
        """
        Scrape website starting from URL.
        Uses breadth-first crawling with depth limit.
        """
        pages = []
        visited = set()
        to_visit = [start_url]
        base_domain = urlparse(start_url).netloc

        async with httpx.AsyncClient(
            timeout=self.SCRAPE_TIMEOUT,
            follow_redirects=True,
            headers={'User-Agent': 'Clonnect Bot 1.0'}
        ) as client:

            while to_visit and len(pages) < self.MAX_PAGES:
                url = to_visit.pop(0)

                # Normalize URL
                url = url.split('#')[0].rstrip('/')

                # Skip if visited
                if url in visited:
                    continue
                visited.add(url)

                # Skip non-HTML resources
                if any(url.lower().endswith(ext) for ext in ['.pdf', '.jpg', '.png', '.gif', '.css', '.js']):
                    continue

                try:
                    response = await client.get(url)

                    if response.status_code != 200:
                        continue

                    content_type = response.headers.get('content-type', '')
                    if 'text/html' not in content_type:
                        continue

                    html = response.text
                    soup = BeautifulSoup(html, 'html.parser')

                    # Extract text
                    for tag in soup.find_all(['script', 'style']):
                        tag.decompose()
                    text = soup.get_text(separator=' ', strip=True)

                    # Create page object
                    page = ScrapedPage(
                        url=url,
                        raw_html=html,
                        extracted_text=text,
                        checksum=hashlib.md5(html.encode()).hexdigest()
                    )
                    pages.append(page)

                    # Find links to other pages on same domain
                    for link in soup.find_all('a', href=True):
                        href = link['href']

                        # Resolve relative URLs
                        if href.startswith('/'):
                            href = urljoin(url, href)
                        elif not href.startswith('http'):
                            continue

                        # Only same domain
                        link_domain = urlparse(href).netloc
                        if link_domain == base_domain:
                            href_clean = href.split('#')[0].rstrip('/')
                            if href_clean not in visited:
                                to_visit.append(href_clean)

                except Exception as e:
                    logger.debug(f"[Pipeline] Failed to scrape {url}: {e}")
                    continue

        return pages

    async def _persist_products(self, creator_id: str, products: List[DetectedProduct]):
        """
        Clear old products and persist new ones.
        IMPORTANT: Clears existing data first to avoid contamination.
        """
        if not self.db:
            logger.warning("[Pipeline] No DB session, skipping persistence")
            return

        try:
            # Import here to avoid circular imports
            from api.models import Product

            # STEP 1: Delete existing products for this creator
            logger.info(f"[Pipeline] Clearing existing products for {creator_id}")
            self.db.query(Product).filter(Product.creator_id == creator_id).delete()
            self.db.commit()

            # STEP 2: Insert new verified products
            for p in products:
                product = Product(
                    creator_id=creator_id,
                    name=p.name,
                    description=p.description,
                    price=p.price,
                    # Store provenance in metadata or separate columns
                    source_url=p.source_url if hasattr(Product, 'source_url') else None,
                    is_active=True
                )
                self.db.add(product)

            self.db.commit()
            logger.info(f"[Pipeline] Saved {len(products)} products for {creator_id}")

        except Exception as e:
            self.db.rollback()
            logger.error(f"[Pipeline] Persistence error: {e}")
            raise


# Convenience function for API use
async def ingest_website(creator_id: str, website_url: str, db_session=None) -> Dict[str, Any]:
    """
    Convenience function to run ingestion and return dict result.
    """
    pipeline = IngestionPipeline(db_session=db_session)
    result = await pipeline.run(creator_id, website_url)
    return result.to_dict()
