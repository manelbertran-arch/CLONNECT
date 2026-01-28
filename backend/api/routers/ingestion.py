"""
Ingestion API Router - Endpoints for content ingestion pipeline.

Provides endpoints for:
- Full website ingestion (scrape + extract + store)
- Quick preview (scrape + extract without storage)
- RAG document management
- Ingestion status/stats
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, HttpUrl

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


# =============================================================================
# Request/Response Models
# =============================================================================

class IngestWebsiteRequest(BaseModel):
    """Request to ingest a website."""
    creator_id: str
    url: str  # Website URL
    max_pages: int = 10
    clear_existing: bool = False


class QuickScrapeRequest(BaseModel):
    """Request for quick scrape preview."""
    url: str
    max_pages: int = 5


class IngestWebsiteResponse(BaseModel):
    """Response from website ingestion."""
    success: bool
    creator_id: str
    source_url: str
    # Stats
    pages_scraped: int
    total_content_chars: int
    products_found: int
    products_with_price: int
    testimonials_found: int
    faqs_found: int
    products_created: int
    products_updated: int
    rag_documents_indexed: int
    rag_documents_persisted: int
    duration_seconds: float
    errors: list


class LoadRAGRequest(BaseModel):
    """Request to load RAG from database."""
    creator_id: str


class ClearDataRequest(BaseModel):
    """Request to clear ingested data."""
    creator_id: str


# =============================================================================
# Database Dependency
# =============================================================================

def get_db():
    """Get database session."""
    try:
        from api.database import SessionLocal
        if SessionLocal is None:
            return None
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Database not available: {e}")
        yield None


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/website", response_model=IngestWebsiteResponse)
async def ingest_website(request: IngestWebsiteRequest, db=Depends(get_db)):
    """
    Ingest content from a website.

    This endpoint:
    1. Scrapes the website deterministically (no LLM)
    2. Extracts products, testimonials, FAQs using regex patterns
    3. Stores products to PostgreSQL with source tracking
    4. Indexes content in RAG with source_url

    Anti-hallucination guarantees:
    - Every item has source_url for verification
    - Prices are regex-verified (price_verified field)
    - Confidence scores indicate extraction reliability
    """
    try:
        from ingestion.pipeline import get_ingestion_pipeline

        pipeline = get_ingestion_pipeline(db, request.max_pages)
        result = await pipeline.run(
            creator_id=request.creator_id,
            website_url=request.url,
            clear_existing=request.clear_existing
        )

        return IngestWebsiteResponse(
            success=result.success,
            creator_id=result.creator_id,
            source_url=result.source_url,
            pages_scraped=result.pages_scraped,
            total_content_chars=result.total_content_chars,
            products_found=result.products_found,
            products_with_price=result.products_with_price,
            testimonials_found=result.testimonials_found,
            faqs_found=result.faqs_found,
            products_created=result.products_created,
            products_updated=result.products_updated,
            rag_documents_indexed=result.rag_documents_indexed,
            rag_documents_persisted=result.rag_documents_persisted,
            duration_seconds=result.duration_seconds,
            errors=result.errors
        )

    except Exception as e:
        logger.error(f"Ingestion error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preview")
async def preview_website(request: QuickScrapeRequest):
    """
    Quick preview of what would be extracted from a website.

    Does NOT store anything - just scrapes and extracts for review.
    Use this to test before running full ingestion.
    """
    try:
        from ingestion.pipeline import get_ingestion_pipeline

        pipeline = get_ingestion_pipeline(max_pages=request.max_pages)
        result = await pipeline.run_quick_scrape(request.url)

        return result

    except Exception as e:
        logger.error(f"Preview error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/load-rag")
async def load_rag_from_db(request: LoadRAGRequest, db=Depends(get_db)):
    """
    Load persisted RAG documents from PostgreSQL into memory.

    Call this on startup or after server restart to restore
    the in-memory RAG index from persisted data.
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        from ingestion.content_store import get_content_store

        store = get_content_store(db)
        count = store.load_rag_from_db(request.creator_id)

        return {
            "success": True,
            "creator_id": request.creator_id,
            "documents_loaded": count
        }

    except Exception as e:
        logger.error(f"Load RAG error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear")
async def clear_ingested_data(request: ClearDataRequest, db=Depends(get_db)):
    """
    Clear all ingested data for a creator.

    This removes:
    - Auto-created products (with source_url)
    - All RAG documents for this creator

    Does NOT remove manually created products.
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        from ingestion.content_store import get_content_store

        store = get_content_store(db)
        stats = store.clear_creator_data(request.creator_id)

        return {
            "success": True,
            "creator_id": request.creator_id,
            "products_deleted": stats.get("products_deleted", 0),
            "rag_documents_deleted": stats.get("rag_docs_deleted", 0)
        }

    except Exception as e:
        logger.error(f"Clear data error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/{creator_id}")
async def get_ingestion_stats(creator_id: str, db=Depends(get_db)):
    """
    Get ingestion stats for a creator.

    Returns counts of indexed products, RAG documents, etc.
    """
    if not db:
        return {
            "creator_id": creator_id,
            "database_available": False,
            "products": 0,
            "rag_documents": 0
        }

    try:
        from api.models import Creator, Product, RAGDocument
        from sqlalchemy import or_

        # Get creator
        creator = db.query(Creator).filter(
            or_(
                Creator.id == creator_id if len(creator_id) > 20 else False,
                Creator.name == creator_id
            )
        ).first()

        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        # Count products
        product_count = db.query(Product).filter(
            Product.creator_id == creator.id
        ).count()

        auto_products = db.query(Product).filter(
            Product.creator_id == creator.id,
            Product.source_url.isnot(None)
        ).count()

        verified_prices = db.query(Product).filter(
            Product.creator_id == creator.id,
            Product.price_verified == True
        ).count()

        # Count RAG documents
        rag_count = db.query(RAGDocument).filter(
            RAGDocument.creator_id == creator.id
        ).count()

        # Get RAG in-memory count
        rag_in_memory = 0
        try:
            from core.rag import get_hybrid_rag
            rag = get_hybrid_rag()
            if rag:
                # Count docs for this creator
                for doc in rag.semantic_rag._documents.values():
                    if doc.metadata and doc.metadata.get('creator_id') == str(creator.id):
                        rag_in_memory += 1
        except Exception as e:
            logger.warning("Failed to count RAG documents: %s", e)

        return {
            "creator_id": creator_id,
            "creator_uuid": str(creator.id),
            "database_available": True,
            "products": {
                "total": product_count,
                "auto_created": auto_products,
                "verified_prices": verified_prices
            },
            "rag_documents": {
                "persisted": rag_count,
                "in_memory": rag_in_memory
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rag-docs/{creator_id}")
async def list_rag_documents(
    creator_id: str,
    limit: int = 20,
    offset: int = 0,
    content_type: Optional[str] = None,
    db=Depends(get_db)
):
    """
    List RAG documents for a creator.

    Useful for debugging and verification.
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        from api.models import Creator, RAGDocument
        from sqlalchemy import or_

        # Get creator
        creator = db.query(Creator).filter(
            or_(
                Creator.id == creator_id if len(creator_id) > 20 else False,
                Creator.name == creator_id
            )
        ).first()

        if not creator:
            raise HTTPException(status_code=404, detail="Creator not found")

        # Query documents
        query = db.query(RAGDocument).filter(
            RAGDocument.creator_id == creator.id
        )

        if content_type:
            query = query.filter(RAGDocument.content_type == content_type)

        total = query.count()
        docs = query.offset(offset).limit(limit).all()

        return {
            "creator_id": creator_id,
            "total": total,
            "limit": limit,
            "offset": offset,
            "documents": [
                {
                    "doc_id": doc.doc_id,
                    "title": doc.title,
                    "content_preview": doc.content[:200] + "..." if len(doc.content) > 200 else doc.content,
                    "source_url": doc.source_url,
                    "source_type": doc.source_type,
                    "content_type": doc.content_type,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None
                }
                for doc in docs
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List RAG docs error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
