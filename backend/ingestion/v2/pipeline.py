"""
Ingestion Pipeline V2 - Zero Hallucinations

Pipeline:
1. LIMPIAR datos anteriores del creator
2. Scrapear website
3. Detectar productos con sistema de señales
4. Ejecutar sanity checks
5. Solo guardar si TODO pasa
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import time

logger = logging.getLogger(__name__)


@dataclass
class IngestionV2Result:
    """Resultado de ingestion V2 con todas las pruebas."""
    success: bool
    status: str  # 'success', 'failed', 'needs_review'
    creator_id: str
    website_url: str

    # Scraping
    pages_scraped: int = 0
    total_chars: int = 0
    pages_details: List[Dict] = field(default_factory=list)

    # Detection
    service_pages_found: int = 0
    products_detected: int = 0
    products_verified: int = 0

    # Products (con todas las pruebas)
    products: List[Dict] = field(default_factory=list)

    # Sanity checks
    sanity_checks: List[Dict] = field(default_factory=list)

    # Cleanup
    products_deleted: int = 0
    rag_docs_deleted: int = 0

    # Storage
    products_saved: int = 0
    rag_docs_saved: int = 0

    # Timing
    duration_seconds: float = 0.0

    # Errors
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "status": self.status,
            "creator_id": self.creator_id,
            "website_url": self.website_url,
            "scraping": {
                "pages_scraped": self.pages_scraped,
                "total_chars": self.total_chars,
                "pages": self.pages_details
            },
            "detection": {
                "service_pages_found": self.service_pages_found,
                "products_detected": self.products_detected,
                "products_verified": self.products_verified
            },
            "products": self.products,
            "sanity_checks": self.sanity_checks,
            "cleanup": {
                "products_deleted": self.products_deleted,
                "rag_docs_deleted": self.rag_docs_deleted
            },
            "storage": {
                "products_saved": self.products_saved,
                "rag_docs_saved": self.rag_docs_saved
            },
            "duration_seconds": self.duration_seconds,
            "errors": self.errors
        }


class IngestionV2Pipeline:
    """
    Pipeline de ingestion V2 - Zero Hallucinations.

    1. Limpia datos anteriores
    2. Scrapea website
    3. Detecta productos (sistema de señales)
    4. Verifica (sanity checks)
    5. Guarda solo si todo pasa
    """

    def __init__(self, db_session=None, max_pages: int = 100):
        self.db = db_session
        self.max_pages = max_pages

    async def run(
        self,
        creator_id: str,
        website_url: str,
        clean_before: bool = True,
        re_verify: bool = True
    ) -> IngestionV2Result:
        """
        Ejecuta pipeline completo.

        Args:
            creator_id: ID del creator
            website_url: URL del sitio
            clean_before: Limpiar datos anteriores
            re_verify: Re-verificar productos fetching URLs

        Returns:
            IngestionV2Result con todo el detalle
        """
        start_time = time.time()

        result = IngestionV2Result(
            success=False,
            status='failed',
            creator_id=creator_id,
            website_url=website_url
        )

        try:
            # Import modules
            from ..deterministic_scraper import DeterministicScraper
            from .product_detector import ProductDetector, SuspiciousExtractionError
            from .sanity_checker import SanityChecker

            # PASO 1: LIMPIAR datos anteriores
            if clean_before and self.db:
                logger.info(f"Limpiando datos anteriores de {creator_id}")
                cleanup_stats = self._clean_creator_data(creator_id)
                result.products_deleted = cleanup_stats.get('products_deleted', 0)
                result.rag_docs_deleted = cleanup_stats.get('rag_docs_deleted', 0)
                logger.info(f"Eliminados: {result.products_deleted} productos, {result.rag_docs_deleted} RAG docs")

            # PASO 2: SCRAPEAR website
            logger.info(f"Scrapeando {website_url}")
            scraper = DeterministicScraper(max_pages=self.max_pages)
            pages = await scraper.scrape_website(website_url)

            result.pages_scraped = len(pages)
            result.total_chars = sum(len(p.main_content) for p in pages)
            result.pages_details = [
                {"url": p.url, "title": p.title, "chars": len(p.main_content)}
                for p in pages
            ]

            if not pages:
                result.errors.append("No se pudo scrapear el sitio")
                result.duration_seconds = time.time() - start_time
                return result

            logger.info(f"Scrapeadas {len(pages)} páginas, {result.total_chars} chars")

            # PASO 3: DETECTAR productos con sistema de señales
            logger.info("Detectando productos con sistema de señales...")
            detector = ProductDetector()

            try:
                detected_products = detector.detect_products(pages)
            except SuspiciousExtractionError as e:
                result.errors.append(str(e))
                result.status = 'failed'
                result.duration_seconds = time.time() - start_time
                return result

            result.products_detected = len(detected_products)
            logger.info(f"Productos detectados: {len(detected_products)}")

            # PASO 4: SANITY CHECKS
            logger.info("Ejecutando sanity checks...")
            checker = SanityChecker()
            verification = checker.verify(
                products=detected_products,
                website_url=website_url,
                re_verify_urls=re_verify
            )

            result.sanity_checks = [
                {"name": c.name, "passed": c.passed, "message": c.message}
                for c in verification.checks
            ]
            result.products_verified = verification.products_verified
            result.status = verification.status

            # Filtrar productos que pasaron verificación
            verified_products = [
                p for p in detected_products
                if p.name in [c.details.get('verified', []) for c in verification.checks
                              if c.name == 're_verification'] or verification.passed
            ]

            # Si la verificación pasó, usar todos los productos detectados que pasaron los checks
            if verification.passed:
                verified_products = detected_products[:verification.products_verified] if verification.products_verified else detected_products

            # Preparar productos para resultado
            result.products = [p.to_dict() for p in verified_products]

            # PASO 5: GUARDAR (solo si sanity checks pasaron)
            if verification.status == 'success' and self.db:
                logger.info("Guardando productos verificados...")
                saved = self._save_products(creator_id, verified_products)
                result.products_saved = saved

                # También crear RAG docs básicos para los productos
                rag_saved = self._save_product_rag_docs(creator_id, verified_products, pages)
                result.rag_docs_saved = rag_saved

                result.success = True
            elif not self.db:
                # Sin DB, marcar como éxito si la verificación pasó
                result.success = verification.passed
                logger.warning("No hay conexión a DB - productos no guardados")
            else:
                result.success = False
                result.errors.append(f"Sanity checks fallaron: {verification.status}")

            result.duration_seconds = time.time() - start_time

            logger.info(
                f"Pipeline completado: {result.products_verified} productos verificados, "
                f"{result.products_saved} guardados, status={result.status}"
            )

        except Exception as e:
            logger.error(f"Error en pipeline: {e}")
            import traceback
            traceback.print_exc()
            result.errors.append(str(e))
            result.duration_seconds = time.time() - start_time

        return result

    def _clean_creator_data(self, creator_id: str) -> Dict[str, int]:
        """Limpia TODOS los productos del creator (no solo auto-creados)."""
        stats = {'products_deleted': 0, 'rag_docs_deleted': 0}

        if not self.db:
            return stats

        try:
            from api.models import Creator, Product, RAGDocument
            from sqlalchemy import or_

            # Get creator
            creator = self.db.query(Creator).filter(
                or_(
                    Creator.id == creator_id if len(str(creator_id)) > 20 else False,
                    Creator.name == creator_id
                )
            ).first()

            if not creator:
                return stats

            # DELETE ALL products for this creator
            products_deleted = self.db.query(Product).filter(
                Product.creator_id == creator.id
            ).delete(synchronize_session=False)
            stats['products_deleted'] = products_deleted

            # DELETE ALL RAG documents
            rag_deleted = self.db.query(RAGDocument).filter(
                RAGDocument.creator_id == creator.id
            ).delete(synchronize_session=False)
            stats['rag_docs_deleted'] = rag_deleted

            self.db.commit()
            logger.info(f"Limpieza: {products_deleted} productos, {rag_deleted} RAG docs")

        except Exception as e:
            logger.error(f"Error limpiando datos: {e}")
            self.db.rollback()

        return stats

    def _save_products(
        self,
        creator_id: str,
        products: List['DetectedProduct']
    ) -> int:
        """Guarda productos verificados."""
        from .product_detector import DetectedProduct

        if not self.db or not products:
            return 0

        saved = 0

        try:
            from api.models import Creator, Product
            from sqlalchemy import or_

            # Get creator
            creator = self.db.query(Creator).filter(
                or_(
                    Creator.id == creator_id if len(str(creator_id)) > 20 else False,
                    Creator.name == creator_id
                )
            ).first()

            if not creator:
                return 0

            for product in products:
                new_product = Product(
                    creator_id=creator.id,
                    name=product.name,
                    description=product.description,
                    short_description=product.short_description,
                    category=product.category,
                    product_type=product.product_type,
                    is_free=product.is_free,
                    price=product.price,
                    currency=product.currency,
                    source_url=product.source_url,
                    payment_link=product.payment_link,
                    price_verified=product.price is not None,
                    confidence=product.confidence,
                    is_active=True
                )
                self.db.add(new_product)
                saved += 1
                logger.info(f"Guardado [{product.category.upper()}]: {product.name} (tipo={product.product_type}, gratis={product.is_free})")

            self.db.commit()

        except Exception as e:
            logger.error(f"Error guardando productos: {e}")
            self.db.rollback()

        return saved

    def _save_product_rag_docs(
        self,
        creator_id: str,
        products: List['DetectedProduct'],
        pages: List['ScrapedPage']
    ) -> int:
        """Guarda RAG docs para productos y páginas scrapeadas."""
        from .product_detector import DetectedProduct
        from ..deterministic_scraper import ScrapedPage

        if not self.db:
            return 0

        saved = 0

        try:
            from api.models import Creator, RAGDocument
            from sqlalchemy import or_
            import hashlib

            # Get creator
            creator = self.db.query(Creator).filter(
                or_(
                    Creator.id == creator_id if len(str(creator_id)) > 20 else False,
                    Creator.name == creator_id
                )
            ).first()

            if not creator:
                return 0

            # Save product descriptions as RAG docs
            for product in products:
                doc_id = hashlib.sha256(
                    f"{product.source_url}:{product.name}".encode()
                ).hexdigest()[:32]

                content = f"{product.name}\n\n{product.description}"
                if product.price:
                    content += f"\n\nPrecio: €{product.price}"

                rag_doc = RAGDocument(
                    creator_id=creator.id,
                    doc_id=doc_id,
                    content=content,
                    source_url=product.source_url,
                    source_type='website',
                    content_type='product',
                    title=product.name
                )
                self.db.add(rag_doc)
                saved += 1

            # Save main page content as RAG docs (chunked)
            for page in pages:
                # Chunk content
                content = page.main_content
                chunk_size = 500
                for i in range(0, len(content), chunk_size - 50):
                    chunk = content[i:i + chunk_size]
                    if len(chunk.strip()) < 50:
                        continue

                    doc_id = hashlib.sha256(
                        f"{page.url}:{i}".encode()
                    ).hexdigest()[:32]

                    rag_doc = RAGDocument(
                        creator_id=creator.id,
                        doc_id=doc_id,
                        content=chunk,
                        source_url=page.url,
                        source_type='website',
                        content_type='page_content',
                        title=page.title,
                        chunk_index=i // chunk_size
                    )
                    self.db.add(rag_doc)
                    saved += 1

            self.db.commit()

        except Exception as e:
            logger.error(f"Error guardando RAG docs: {e}")
            self.db.rollback()

        return saved


async def ingest_website_v2(
    creator_id: str,
    website_url: str,
    db_session=None,
    max_pages: int = 100,
    clean_before: bool = True,
    re_verify: bool = True
) -> IngestionV2Result:
    """
    Función de conveniencia para ejecutar ingestion V2.
    """
    pipeline = IngestionV2Pipeline(db_session, max_pages)
    return await pipeline.run(creator_id, website_url, clean_before, re_verify)
