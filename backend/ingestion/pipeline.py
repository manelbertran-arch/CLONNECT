"""
Content Ingestion Pipeline - Orchestrates the full ingestion process.

Pipeline steps:
1. Scrape website deterministically (no LLM)
2. Extract structured content (regex patterns)
3. Store products with source tracking
4. Store RAG documents with source_url
5. Return comprehensive results

Anti-hallucination guarantees:
- Every extracted item has a source_url
- Prices are regex-verified (price_verified=True)
- Confidence scores indicate extraction reliability
- No LLM interpretation in extraction
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Result of a content ingestion pipeline run."""
    success: bool
    creator_id: str
    source_url: str
    # Scraping stats
    pages_scraped: int = 0
    total_content_chars: int = 0
    # Extraction stats
    products_found: int = 0
    products_with_price: int = 0
    testimonials_found: int = 0
    faqs_found: int = 0
    about_sections_found: int = 0
    # Storage stats
    products_created: int = 0
    products_updated: int = 0
    rag_documents_indexed: int = 0
    rag_documents_persisted: int = 0
    # Timing
    duration_seconds: float = 0.0
    # Errors
    errors: list = field(default_factory=list)
    # Metadata
    completed_at: datetime = field(default_factory=datetime.utcnow)


class IngestionPipeline:
    """
    Orchestrates the content ingestion pipeline.

    Usage:
        pipeline = IngestionPipeline(db_session)
        result = await pipeline.run(creator_id, "https://example.com")
    """

    def __init__(self, db_session=None, max_pages: int = 10):
        self.db = db_session
        self.max_pages = max_pages

    async def run(
        self,
        creator_id: str,
        website_url: str,
        clear_existing: bool = False
    ) -> IngestionResult:
        """
        Run the full ingestion pipeline.

        Args:
            creator_id: Creator ID (name or UUID)
            website_url: Website URL to ingest
            clear_existing: If True, clear existing data first

        Returns:
            IngestionResult with all stats
        """
        import time
        start_time = time.time()

        result = IngestionResult(
            success=False,
            creator_id=creator_id,
            source_url=website_url
        )

        try:
            # Import modules
            from .deterministic_scraper import get_deterministic_scraper
            from .structured_extractor import get_structured_extractor
            from .content_store import get_content_store

            # Initialize components
            scraper = get_deterministic_scraper(max_pages=self.max_pages)
            extractor = get_structured_extractor()
            store = get_content_store(self.db)

            # Step 0: Clear existing data if requested
            if clear_existing:
                logger.info(f"Clearing existing data for {creator_id}")
                store.clear_creator_data(creator_id)

            # Step 1: Scrape website
            logger.info(f"Starting scrape of {website_url}")
            pages = await scraper.scrape_website(website_url)
            result.pages_scraped = len(pages)
            result.total_content_chars = sum(len(p.main_content) for p in pages)

            if not pages:
                result.errors.append("No content found on website")
                result.duration_seconds = time.time() - start_time
                return result

            logger.info(f"Scraped {len(pages)} pages, {result.total_content_chars} chars total")

            # Step 2: Extract structured content
            logger.info("Extracting structured content")
            extracted = extractor.extract_all(pages)

            result.products_found = len(extracted.products)
            result.products_with_price = len([p for p in extracted.products if p.price_verified])
            result.testimonials_found = len(extracted.testimonials)
            result.faqs_found = len(extracted.faqs)
            result.about_sections_found = len(extracted.about_sections)

            logger.info(
                f"Extracted: {result.products_found} products "
                f"({result.products_with_price} with verified price), "
                f"{result.testimonials_found} testimonials, "
                f"{result.faqs_found} FAQs"
            )

            # Step 3: Store products
            if extracted.products:
                logger.info("Storing products")
                product_stats = store.store_products(creator_id, extracted.products)
                result.products_created = product_stats.get("created", 0)
                result.products_updated = product_stats.get("updated", 0)

            # Step 4: Store RAG documents (main content)
            if extracted.raw_chunks:
                logger.info(f"Storing {len(extracted.raw_chunks)} RAG chunks")
                rag_stats = store.store_rag_documents(creator_id, extracted.raw_chunks)
                result.rag_documents_indexed = rag_stats.get("indexed", 0)
                result.rag_documents_persisted = rag_stats.get("persisted", 0)

            # Step 5: Store testimonials as RAG
            if extracted.testimonials:
                testimonial_count = store.store_testimonials_as_rag(creator_id, extracted.testimonials)
                result.rag_documents_indexed += testimonial_count

            # Step 6: Store FAQs as RAG
            if extracted.faqs:
                faq_count = store.store_faqs_as_rag(creator_id, extracted.faqs)
                result.rag_documents_indexed += faq_count

            # Step 7: Store about sections as RAG
            if extracted.about_sections:
                about_count = store.store_about_sections_as_rag(creator_id, extracted.about_sections)
                result.rag_documents_indexed += about_count

            result.success = True
            result.duration_seconds = time.time() - start_time

            logger.info(
                f"Ingestion complete: {result.pages_scraped} pages, "
                f"{result.products_created} products created, "
                f"{result.rag_documents_indexed} docs indexed, "
                f"duration: {result.duration_seconds:.2f}s"
            )

        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            import traceback
            traceback.print_exc()
            result.errors.append(str(e))
            result.duration_seconds = time.time() - start_time

        return result

    async def run_quick_scrape(
        self,
        website_url: str
    ) -> Dict[str, Any]:
        """
        Quick scrape without storage - for preview/testing.

        Returns extracted content without persisting.
        """
        from .deterministic_scraper import get_deterministic_scraper
        from .structured_extractor import get_structured_extractor

        scraper = get_deterministic_scraper(max_pages=5)
        extractor = get_structured_extractor()

        pages = await scraper.scrape_website(website_url)

        if not pages:
            return {"error": "No content found", "pages": 0}

        extracted = extractor.extract_all(pages)

        return {
            "pages_scraped": len(pages),
            "pages": [
                {
                    "url": p.url,
                    "title": p.title,
                    "content_length": len(p.main_content),
                    "sections": len(p.sections)
                }
                for p in pages
            ],
            "products": [
                {
                    "name": p.name,
                    "description": p.description[:200] if p.description else "",
                    "price": p.price,
                    "currency": p.currency,
                    "price_verified": p.price_verified,
                    "confidence": p.confidence,
                    "source_url": p.source_url
                }
                for p in extracted.products
            ],
            "testimonials": [
                {
                    "content": t.content[:200],
                    "author": t.author,
                    "source_url": t.source_url
                }
                for t in extracted.testimonials
            ],
            "faqs": [
                {
                    "question": f.question,
                    "answer": f.answer[:200],
                    "source_url": f.source_url
                }
                for f in extracted.faqs
            ],
            "contact_info": extracted.contact_info,
            "rag_chunks_count": len(extracted.raw_chunks)
        }


def get_ingestion_pipeline(db_session=None, max_pages: int = 10) -> IngestionPipeline:
    """Get pipeline instance."""
    return IngestionPipeline(db_session, max_pages)


async def ingest_website(
    creator_id: str,
    website_url: str,
    db_session=None,
    max_pages: int = 10,
    clear_existing: bool = False
) -> IngestionResult:
    """
    Convenience function to run ingestion.

    Args:
        creator_id: Creator ID
        website_url: URL to ingest
        db_session: Database session
        max_pages: Max pages to scrape
        clear_existing: Clear existing data first

    Returns:
        IngestionResult
    """
    pipeline = get_ingestion_pipeline(db_session, max_pages)
    return await pipeline.run(creator_id, website_url, clear_existing)
