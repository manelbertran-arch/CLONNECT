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
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from ..deterministic_scraper import ScrapedPage
    from .bio_extractor import ExtractedBio
    from .faq_extractor import ExtractedFAQ
    from .product_detector import DetectedProduct
    from .tone_detector import DetectedTone

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

    # Creator knowledge (bio, FAQs, tone) - extracted from website
    bio: Optional[Dict] = None
    faqs: List[Dict] = field(default_factory=list)
    tone: Optional[Dict] = None
    knowledge_saved: bool = False

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
                "pages": self.pages_details,
            },
            "detection": {
                "service_pages_found": self.service_pages_found,
                "products_detected": self.products_detected,
                "products_verified": self.products_verified,
            },
            "products": self.products,
            "sanity_checks": self.sanity_checks,
            "cleanup": {
                "products_deleted": self.products_deleted,
                "rag_docs_deleted": self.rag_docs_deleted,
            },
            "storage": {
                "products_saved": self.products_saved,
                "rag_docs_saved": self.rag_docs_saved,
            },
            "creator_knowledge": {
                "bio": self.bio,
                "faqs": self.faqs,
                "tone": self.tone,
                "saved": self.knowledge_saved,
            },
            "duration_seconds": self.duration_seconds,
            "errors": self.errors,
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
        self, creator_id: str, website_url: str, clean_before: bool = True, re_verify: bool = True
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
            success=False, status="failed", creator_id=creator_id, website_url=website_url
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
                result.products_deleted = cleanup_stats.get("products_deleted", 0)
                result.rag_docs_deleted = cleanup_stats.get("rag_docs_deleted", 0)
                logger.info(
                    f"Eliminados: {result.products_deleted} productos, {result.rag_docs_deleted} RAG docs"
                )

            # PASO 2: SCRAPEAR website
            logger.info(f"Scrapeando {website_url}")
            scraper = DeterministicScraper(max_pages=self.max_pages)
            pages = await scraper.scrape_website(website_url)

            result.pages_scraped = len(pages)
            result.total_chars = sum(len(p.main_content) for p in pages)
            result.pages_details = [
                {"url": p.url, "title": p.title, "chars": len(p.main_content)} for p in pages
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
                result.status = "failed"
                result.duration_seconds = time.time() - start_time
                return result

            result.products_detected = len(detected_products)
            logger.info(f"Productos detectados: {len(detected_products)}")

            # PASO 4: SANITY CHECKS
            logger.info("Ejecutando sanity checks...")
            checker = SanityChecker()
            verification = checker.verify(
                products=detected_products, website_url=website_url, re_verify_urls=re_verify
            )

            result.sanity_checks = [
                {"name": c.name, "passed": c.passed, "message": c.message}
                for c in verification.checks
            ]
            result.products_verified = verification.products_verified
            result.status = verification.status

            # Filtrar productos que pasaron verificación
            verified_products = [
                p
                for p in detected_products
                if p.name
                in [
                    c.details.get("verified", [])
                    for c in verification.checks
                    if c.name == "re_verification"
                ]
                or verification.passed
            ]

            # Si la verificación pasó, usar todos los productos detectados que pasaron los checks
            if verification.passed:
                verified_products = (
                    detected_products[: verification.products_verified]
                    if verification.products_verified
                    else detected_products
                )

            # Preparar productos para resultado
            result.products = [p.to_dict() for p in verified_products]

            # PASO 4.5: EXTRAER conocimiento del creador (bio, FAQs, tono)
            logger.info("Extrayendo conocimiento del creador (bio, FAQs, tono)...")
            bio = None
            faqs_result = None
            tone = None

            try:
                from .bio_extractor import BioExtractor
                from .faq_extractor import FAQExtractor
                from .tone_detector import ToneDetector

                # Extract bio
                bio_extractor = BioExtractor()
                bio = await bio_extractor.extract(pages)
                if bio:
                    result.bio = bio_extractor.to_dict(bio)
                    logger.info(
                        f"Bio extraído: {len(bio.description)} chars, confidence={bio.confidence:.2f}"
                    )

                # Extract FAQs
                faq_extractor = FAQExtractor()
                faqs_result = await faq_extractor.extract(pages, verified_products, bio)
                if faqs_result and faqs_result.faqs:
                    result.faqs = [faq_extractor.to_dict(f) for f in faqs_result.faqs]
                    logger.info(f"FAQs extraídos: {len(faqs_result.faqs)}")

                # Detect tone
                tone_detector = ToneDetector()
                tone = await tone_detector.detect(pages, bio)
                if tone:
                    result.tone = tone_detector.to_dict(tone)
                    logger.info(f"Tono detectado: {tone.style} (formality={tone.formality})")

            except Exception as e:
                logger.warning(f"Error extrayendo conocimiento del creador: {e}")
                import traceback

                traceback.print_exc()

            # PASO 5: GUARDAR (solo si sanity checks pasaron)
            if verification.status == "success" and self.db:
                logger.info("Guardando productos verificados...")
                saved = self._save_products(creator_id, verified_products)
                result.products_saved = saved

                # También crear RAG docs básicos para los productos
                rag_saved = self._save_product_rag_docs(creator_id, verified_products, pages)
                result.rag_docs_saved = rag_saved

                # DUAL-SAVE: Guardar conocimiento del creador en RAG + tablas UI
                if bio or (faqs_result and faqs_result.faqs) or tone:
                    knowledge_saved = self._save_creator_knowledge(
                        creator_id=creator_id,
                        bio=bio,
                        faqs=faqs_result.faqs if faqs_result else [],
                        tone=tone,
                    )
                    result.knowledge_saved = knowledge_saved
                    logger.info(f"Conocimiento del creador guardado: {knowledge_saved}")

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
        stats = {"products_deleted": 0, "rag_docs_deleted": 0}

        if not self.db:
            return stats

        try:
            from api.models import Creator, Product, RAGDocument
            from sqlalchemy import or_

            # Get creator
            creator = (
                self.db.query(Creator)
                .filter(
                    or_(
                        Creator.id == creator_id if len(str(creator_id)) > 20 else False,
                        Creator.name == creator_id,
                    )
                )
                .first()
            )

            if not creator:
                return stats

            # DELETE ALL products for this creator
            products_deleted = (
                self.db.query(Product)
                .filter(Product.creator_id == creator.id)
                .delete(synchronize_session=False)
            )
            stats["products_deleted"] = products_deleted

            # DELETE ALL RAG documents
            rag_deleted = (
                self.db.query(RAGDocument)
                .filter(RAGDocument.creator_id == creator.id)
                .delete(synchronize_session=False)
            )
            stats["rag_docs_deleted"] = rag_deleted

            self.db.commit()
            logger.info(f"Limpieza: {products_deleted} productos, {rag_deleted} RAG docs")

        except Exception as e:
            logger.error(f"Error limpiando datos: {e}")
            self.db.rollback()

        return stats

    def _save_products(self, creator_id: str, products: List["DetectedProduct"]) -> int:
        """Guarda productos verificados."""
        # CRITICAL: Log why we might not save
        logger.info(
            f"[_save_products] db={self.db}, products_count={len(products) if products else 0}, creator_id={creator_id}"
        )

        if not self.db:
            logger.warning("[_save_products] SKIPPING: db is None!")
            return 0

        if not products:
            logger.warning("[_save_products] SKIPPING: No products to save!")
            return 0

        saved = 0

        try:
            from api.models import Creator, Product
            from sqlalchemy import or_

            # Get creator
            logger.info(f"[_save_products] Querying for creator: {creator_id}")
            creator = (
                self.db.query(Creator)
                .filter(
                    or_(
                        Creator.id == creator_id if len(str(creator_id)) > 20 else False,
                        Creator.name == creator_id,
                    )
                )
                .first()
            )

            if not creator:
                logger.warning(
                    f"[_save_products] SKIPPING: Creator '{creator_id}' NOT FOUND in database!"
                )
                return 0

            logger.info(f"[_save_products] Found creator: id={creator.id}, name={creator.name}")

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
                    is_active=True,
                )
                self.db.add(new_product)
                saved += 1
                logger.info(
                    f"Guardado [{product.category.upper()}]: {product.name} (tipo={product.product_type}, gratis={product.is_free})"
                )

            self.db.commit()

        except Exception as e:
            logger.error(f"Error guardando productos: {e}")
            self.db.rollback()

        return saved

    def _save_product_rag_docs(
        self, creator_id: str, products: List["DetectedProduct"], pages: List["ScrapedPage"]
    ) -> int:
        """Guarda RAG docs para productos y páginas scrapeadas."""
        if not self.db:
            return 0

        saved = 0

        try:
            import hashlib

            from api.models import Creator, RAGDocument
            from sqlalchemy import or_

            # Get creator
            creator = (
                self.db.query(Creator)
                .filter(
                    or_(
                        Creator.id == creator_id if len(str(creator_id)) > 20 else False,
                        Creator.name == creator_id,
                    )
                )
                .first()
            )

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
                    source_type="website",
                    content_type="product",
                    title=product.name,
                )
                self.db.add(rag_doc)
                saved += 1

            # Save main page content as RAG docs (chunked)
            for page in pages:
                # Chunk content
                content = page.main_content
                chunk_size = 500
                for i in range(0, len(content), chunk_size - 50):
                    chunk = content[i : i + chunk_size]
                    if len(chunk.strip()) < 50:
                        continue

                    doc_id = hashlib.sha256(f"{page.url}:{i}".encode()).hexdigest()[:32]

                    rag_doc = RAGDocument(
                        creator_id=creator.id,
                        doc_id=doc_id,
                        content=chunk,
                        source_url=page.url,
                        source_type="website",
                        content_type="page_content",
                        title=page.title,
                        chunk_index=i // chunk_size,
                    )
                    self.db.add(rag_doc)
                    saved += 1

            self.db.commit()

        except Exception as e:
            logger.error(f"Error guardando RAG docs: {e}")
            self.db.rollback()

        return saved

    def _auto_configure_clone(
        self,
        creator,
        bio: Optional["ExtractedBio"],
        tone: Optional["DetectedTone"],
    ) -> None:
        """
        Auto-configura la personalidad del bot con datos extraídos del website.

        1. clone_name = nombre del creador (de bio)
        2. clone_tone = preset UI mapeado desde tone.style
        3. bot_instructions = suggested_bot_tone (para instrucciones del bot)
        """
        changes = []

        # 1. Nombre del bot = nombre del creador
        if bio and bio.name:
            creator.clone_name = bio.name
            changes.append(f"clone_name={bio.name}")

        # 2. Mapear tone.style → preset UI
        TONE_TO_PRESET = {
            "inspirador": "mentor",
            "cercano": "amigo",
            "directo": "vendedor",
            "motivacional": "mentor",
            "técnico": "profesional",
            "empático": "amigo",
            "formal": "profesional",
            "informal": "amigo",
            "transformador": "mentor",
            "reflexivo": "mentor",
            "enérgico": "vendedor",
            "serio": "profesional",
        }

        if tone and hasattr(tone, "style") and tone.style:
            style_lower = tone.style.lower()
            preset = TONE_TO_PRESET.get(style_lower, "amigo")
            creator.clone_tone = preset
            changes.append(f"clone_tone={preset} (from style={tone.style})")

        # 3. Guardar suggested_bot_tone como clone_vocabulary (instrucciones del bot)
        if tone and hasattr(tone, "suggested_bot_tone") and tone.suggested_bot_tone:
            creator.clone_vocabulary = tone.suggested_bot_tone
            changes.append(f"clone_vocabulary={tone.suggested_bot_tone[:50]}...")

        if changes:
            logger.info(f"[_auto_configure_clone] {', '.join(changes)}")

    def _save_creator_knowledge(
        self,
        creator_id: str,
        bio: Optional["ExtractedBio"],
        faqs: List["ExtractedFAQ"],
        tone: Optional["DetectedTone"],
    ) -> bool:
        """
        DUAL-SAVE: Guarda conocimiento del creador en AMBOS lugares:
        1. RAG documents (para el chatbot)
        2. Tablas UI (KnowledgeBase para FAQs, knowledge_about para bio)

        Esto asegura que tanto el chatbot como el Settings UI muestren los datos.
        """
        if not self.db:
            logger.warning("[_save_creator_knowledge] No DB session, skipping")
            return False

        try:
            import hashlib

            from api.models import Creator, KnowledgeBase, RAGDocument
            from sqlalchemy import or_
            from sqlalchemy.orm.attributes import flag_modified

            # Get creator
            creator = (
                self.db.query(Creator)
                .filter(
                    or_(
                        Creator.id == creator_id if len(str(creator_id)) > 20 else False,
                        Creator.name == creator_id,
                    )
                )
                .first()
            )

            if not creator:
                logger.warning(f"[_save_creator_knowledge] Creator not found: {creator_id}")
                return False

            logger.info(f"[_save_creator_knowledge] Saving knowledge for creator: {creator.name}")

            # ============================================================
            # SAVE BIO to knowledge_about (UI) + RAG
            # ============================================================
            if bio:
                # 1. Save to creator.knowledge_about (for Settings UI)
                about_data = creator.knowledge_about or {}

                # Bio básica (existente)
                about_data["bio"] = bio.description
                about_data["bio_source_url"] = bio.source_url
                about_data["bio_confidence"] = bio.confidence

                # AUTO-COMPLETAR: Campos adicionales extraídos del website
                if bio.name:
                    about_data["creator_name"] = bio.name
                if bio.specialties:
                    about_data["specialties"] = bio.specialties
                if bio.years_experience:
                    # Frontend expects "experience" as string "X años", not "years_experience" as int
                    about_data["experience"] = f"{bio.years_experience} años"
                if bio.target_audience:
                    about_data["target_audience"] = bio.target_audience

                creator.knowledge_about = about_data

                # CRITICAL: flag_modified tells SQLAlchemy the JSON field changed
                flag_modified(creator, "knowledge_about")

                # Log con detalle de campos guardados
                saved_fields = ["bio"]
                if bio.name:
                    saved_fields.append("creator_name")
                if bio.specialties:
                    saved_fields.append(f"specialties({len(bio.specialties)})")
                if bio.years_experience:
                    saved_fields.append(f"experience({bio.years_experience} años)")
                if bio.target_audience:
                    saved_fields.append("target_audience")
                logger.info(
                    f"[_save_creator_knowledge] Bio saved to knowledge_about: {', '.join(saved_fields)}"
                )

                # 2. Save to RAG documents (for chatbot)
                bio_doc_id = hashlib.sha256(f"bio:{creator.id}".encode()).hexdigest()[:32]
                bio_rag = RAGDocument(
                    creator_id=creator.id,
                    doc_id=bio_doc_id,
                    content=f"Sobre mí:\n\n{bio.description}",
                    source_url=bio.source_url,
                    source_type="website",
                    content_type="bio",
                    title="Bio del creador",
                )
                self.db.merge(bio_rag)  # merge to update if exists

            # ============================================================
            # SAVE FAQs to KnowledgeBase (UI) + RAG
            # ============================================================
            if faqs:
                # First, clear existing FAQs from KnowledgeBase for this creator
                self.db.query(KnowledgeBase).filter(KnowledgeBase.creator_id == creator.id).delete(
                    synchronize_session=False
                )

                for faq in faqs:
                    # 1. Save to KnowledgeBase table (for Settings UI)
                    kb_item = KnowledgeBase(
                        creator_id=creator.id,
                        question=faq.question,
                        answer=faq.answer,
                    )
                    self.db.add(kb_item)

                    # 2. Save to RAG documents (for chatbot)
                    faq_doc_id = hashlib.sha256(
                        f"faq:{creator.id}:{faq.question}".encode()
                    ).hexdigest()[:32]
                    faq_rag = RAGDocument(
                        creator_id=creator.id,
                        doc_id=faq_doc_id,
                        content=f"Pregunta: {faq.question}\n\nRespuesta: {faq.answer}",
                        source_url=faq.source_url,
                        source_type="website",
                        content_type="faq",
                        title=faq.question[:100],
                    )
                    self.db.merge(faq_rag)

                logger.info(
                    f"[_save_creator_knowledge] {len(faqs)} FAQs saved to KnowledgeBase + RAG"
                )

            # ============================================================
            # SAVE TONE to knowledge_about (UI)
            # ============================================================
            if tone:
                about_data = creator.knowledge_about or {}
                about_data["tone"] = {
                    "style": tone.style,
                    "formality": tone.formality,
                    "language": getattr(tone, "language", "es"),
                    "emoji_usage": getattr(tone, "emoji_usage", "none"),
                    "personality_traits": getattr(tone, "personality_traits", []),
                    "communication_summary": getattr(tone, "communication_summary", ""),
                    "suggested_bot_tone": getattr(tone, "suggested_bot_tone", ""),
                    "confidence": tone.confidence,
                }
                creator.knowledge_about = about_data
                flag_modified(creator, "knowledge_about")
                logger.info(f"[_save_creator_knowledge] Tone saved: {tone.style}")

            # AUTO-CONFIGURAR personalidad del bot con datos extraídos
            self._auto_configure_clone(creator, bio, tone)

            self.db.commit()
            logger.info("[_save_creator_knowledge] All knowledge saved successfully")
            return True

        except Exception as e:
            logger.error(f"[_save_creator_knowledge] Error: {e}")
            import traceback

            traceback.print_exc()
            self.db.rollback()
            return False


async def ingest_website_v2(
    creator_id: str,
    website_url: str,
    db_session=None,
    max_pages: int = 100,
    clean_before: bool = True,
    re_verify: bool = True,
) -> IngestionV2Result:
    """
    Función de conveniencia para ejecutar ingestion V2.
    """
    pipeline = IngestionV2Pipeline(db_session, max_pages)
    return await pipeline.run(creator_id, website_url, clean_before, re_verify)
