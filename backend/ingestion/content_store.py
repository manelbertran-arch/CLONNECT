"""
Content Store - Persist extracted content to PostgreSQL and RAG index.

Anti-hallucination principles:
1. Every document has a source_url
2. Every product has price_verified and confidence fields
3. RAG documents are persisted to PostgreSQL for recovery
"""

import hashlib
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime
from uuid import UUID

logger = logging.getLogger(__name__)


def generate_doc_id(content: str, source_url: str) -> str:
    """Generate a unique document ID based on content and source."""
    raw = f"{source_url}:{content[:100]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class ContentStore:
    """
    Persist content to PostgreSQL (products, RAG docs) and in-memory RAG index.
    """

    def __init__(self, db_session=None):
        self.db = db_session
        self._rag = None

    def _get_rag(self):
        """Lazy load RAG instance."""
        if self._rag is None:
            try:
                from core.rag import get_hybrid_rag
                self._rag = get_hybrid_rag()
            except ImportError:
                logger.warning("RAG module not available")
        return self._rag

    def store_products(
        self,
        creator_id: str,
        products: List['ExtractedProduct']
    ) -> Dict[str, int]:
        """
        Store extracted products to PostgreSQL.

        Args:
            creator_id: Creator ID
            products: List of ExtractedProduct

        Returns:
            Stats dict with counts
        """
        from .structured_extractor import ExtractedProduct

        stats = {"created": 0, "updated": 0, "skipped": 0}

        if not self.db:
            logger.warning("No database session, skipping product storage")
            return stats

        try:
            from api.models import Product, Creator
            from sqlalchemy import or_

            # Get creator UUID
            creator = self.db.query(Creator).filter(
                or_(
                    Creator.id == creator_id if len(creator_id) > 20 else False,
                    Creator.name == creator_id
                )
            ).first()

            if not creator:
                logger.error(f"Creator not found: {creator_id}")
                return stats

            for product in products:
                # ANTI-HALLUCINATION: Only store products with verified prices
                # This prevents testimonials, about sections, etc. from being stored as products
                if not product.price_verified:
                    logger.debug(f"Skipping product without verified price: {product.name[:50]}")
                    stats["skipped"] += 1
                    continue

                # Check if product exists by name
                existing = self.db.query(Product).filter(
                    Product.creator_id == creator.id,
                    Product.name == product.name
                ).first()

                if existing:
                    # Update if we have better data
                    if product.price_verified and not existing.price_verified:
                        existing.price = product.price
                        existing.price_verified = True
                        existing.source_url = product.source_url
                        existing.confidence = product.confidence
                        stats["updated"] += 1
                    else:
                        stats["skipped"] += 1
                else:
                    # Create new product
                    new_product = Product(
                        creator_id=creator.id,
                        name=product.name,
                        description=product.description,
                        price=product.price,
                        currency=product.currency,
                        source_url=product.source_url,
                        price_verified=product.price_verified,
                        confidence=product.confidence,
                        is_active=True
                    )
                    self.db.add(new_product)
                    stats["created"] += 1

            self.db.commit()
            logger.info(f"Stored products: {stats}")

        except Exception as e:
            logger.error(f"Error storing products: {e}")
            self.db.rollback()

        return stats

    def store_rag_documents(
        self,
        creator_id: str,
        chunks: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Store RAG documents to PostgreSQL and add to in-memory index.

        Args:
            creator_id: Creator ID
            chunks: List of chunk dicts with content, source_url, etc.

        Returns:
            Stats dict
        """
        stats = {"indexed": 0, "persisted": 0, "errors": 0}

        if not chunks:
            return stats

        try:
            from api.models import Creator, RAGDocument
            from sqlalchemy import or_

            # Get creator UUID
            creator = None
            creator_uuid = None
            if self.db:
                creator = self.db.query(Creator).filter(
                    or_(
                        Creator.id == creator_id if len(creator_id) > 20 else False,
                        Creator.name == creator_id
                    )
                ).first()
                if creator:
                    creator_uuid = creator.id

            rag = self._get_rag()

            for chunk in chunks:
                try:
                    doc_id = generate_doc_id(chunk['content'], chunk['source_url'])

                    # Add to in-memory RAG
                    if rag:
                        rag.add_document(
                            doc_id=doc_id,
                            text=chunk['content'],
                            metadata={
                                'creator_id': str(creator_uuid) if creator_uuid else creator_id,
                                'source_url': chunk['source_url'],
                                'source_type': chunk.get('source_type', 'website'),
                                'content_type': chunk.get('content_type', 'general'),
                                'title': chunk.get('title', '')
                            }
                        )
                        stats["indexed"] += 1

                    # Persist to PostgreSQL
                    if self.db and creator_uuid:
                        # Check if document exists
                        existing = self.db.query(RAGDocument).filter(
                            RAGDocument.doc_id == doc_id
                        ).first()

                        if not existing:
                            rag_doc = RAGDocument(
                                creator_id=creator_uuid,
                                doc_id=doc_id,
                                content=chunk['content'],
                                source_url=chunk['source_url'],
                                source_type=chunk.get('source_type', 'website'),
                                content_type=chunk.get('content_type', 'general'),
                                title=chunk.get('title'),
                                chunk_index=chunk.get('chunk_index', 0),
                                extra_data=chunk.get('metadata', {})
                            )
                            self.db.add(rag_doc)
                            stats["persisted"] += 1

                except Exception as e:
                    logger.error(f"Error storing chunk: {e}")
                    stats["errors"] += 1

            if self.db:
                self.db.commit()

            logger.info(f"Stored RAG documents: {stats}")

        except Exception as e:
            logger.error(f"Error storing RAG documents: {e}")
            if self.db:
                self.db.rollback()

        return stats

    def store_testimonials_as_rag(
        self,
        creator_id: str,
        testimonials: List['ExtractedTestimonial']
    ) -> int:
        """
        Store testimonials as RAG documents for retrieval.
        """
        from .structured_extractor import ExtractedTestimonial

        chunks = []
        for t in testimonials:
            content = f"Testimonial from {t.author}: \"{t.content}\""
            if t.role:
                content += f" ({t.role})"

            chunks.append({
                'content': content,
                'source_url': t.source_url,
                'source_type': 'website',
                'content_type': 'testimonial',
                'title': f"Testimonial - {t.author}",
            })

        result = self.store_rag_documents(creator_id, chunks)
        return result.get("indexed", 0)

    def store_faqs_as_rag(
        self,
        creator_id: str,
        faqs: List['ExtractedFAQ']
    ) -> int:
        """
        Store FAQs as RAG documents for retrieval.
        """
        from .structured_extractor import ExtractedFAQ

        chunks = []
        for faq in faqs:
            content = f"Question: {faq.question}\nAnswer: {faq.answer}"

            chunks.append({
                'content': content,
                'source_url': faq.source_url,
                'source_type': 'website',
                'content_type': 'faq',
                'title': faq.question,
            })

        result = self.store_rag_documents(creator_id, chunks)
        return result.get("indexed", 0)

    def store_about_sections_as_rag(
        self,
        creator_id: str,
        sections: List[Dict[str, str]]
    ) -> int:
        """
        Store about/bio sections as RAG documents.
        """
        chunks = []
        for section in sections:
            chunks.append({
                'content': section.get('content', ''),
                'source_url': section.get('source_url', ''),
                'source_type': 'website',
                'content_type': 'about',
                'title': section.get('title', 'About'),
            })

        result = self.store_rag_documents(creator_id, chunks)
        return result.get("indexed", 0)

    def load_rag_from_db(self, creator_id: str) -> int:
        """
        Load persisted RAG documents from PostgreSQL into in-memory index.
        Call this on startup to restore RAG index.

        Returns:
            Number of documents loaded
        """
        if not self.db:
            logger.warning("No database session, cannot load RAG docs")
            return 0

        try:
            from api.models import Creator, RAGDocument
            from sqlalchemy import or_

            # Get creator
            creator = self.db.query(Creator).filter(
                or_(
                    Creator.id == creator_id if len(creator_id) > 20 else False,
                    Creator.name == creator_id
                )
            ).first()

            if not creator:
                return 0

            # Load documents
            docs = self.db.query(RAGDocument).filter(
                RAGDocument.creator_id == creator.id
            ).all()

            rag = self._get_rag()
            if not rag:
                return 0

            loaded = 0
            for doc in docs:
                try:
                    rag.add_document(
                        doc_id=doc.doc_id,
                        text=doc.content,
                        metadata={
                            'creator_id': str(doc.creator_id),
                            'source_url': doc.source_url,
                            'source_type': doc.source_type,
                            'content_type': doc.content_type,
                            'title': doc.title
                        }
                    )
                    loaded += 1
                except Exception as e:
                    logger.error(f"Error loading doc {doc.doc_id}: {e}")

            logger.info(f"Loaded {loaded} RAG documents for {creator_id}")
            return loaded

        except Exception as e:
            logger.error(f"Error loading RAG from DB: {e}")
            return 0

    def clear_creator_data(self, creator_id: str) -> Dict[str, int]:
        """
        Clear all ingested data for a creator (for re-ingestion).
        """
        stats = {"products_deleted": 0, "rag_docs_deleted": 0}

        if not self.db:
            return stats

        try:
            from api.models import Creator, Product, RAGDocument
            from sqlalchemy import or_

            creator = self.db.query(Creator).filter(
                or_(
                    Creator.id == creator_id if len(creator_id) > 20 else False,
                    Creator.name == creator_id
                )
            ).first()

            if not creator:
                return stats

            # Delete products (only auto-created ones)
            products_deleted = self.db.query(Product).filter(
                Product.creator_id == creator.id,
                Product.source_url.isnot(None)  # Only auto-created
            ).delete(synchronize_session=False)
            stats["products_deleted"] = products_deleted

            # Delete RAG documents
            rag_deleted = self.db.query(RAGDocument).filter(
                RAGDocument.creator_id == creator.id
            ).delete(synchronize_session=False)
            stats["rag_docs_deleted"] = rag_deleted

            self.db.commit()

            # Clear from in-memory RAG
            rag = self._get_rag()
            if rag:
                rag.delete_by_creator(str(creator.id))

            logger.info(f"Cleared data for {creator_id}: {stats}")

        except Exception as e:
            logger.error(f"Error clearing data: {e}")
            self.db.rollback()

        return stats


def get_content_store(db_session=None) -> ContentStore:
    """Get content store instance."""
    return ContentStore(db_session)
