"""
Ingestion V2 API Router - Zero Hallucinations

Endpoint que garantiza:
- Solo productos verificados con 3+ señales
- Precios solo si encontrados via regex (nunca inventados)
- Todos los datos con source_url y source_html como prueba
- Sanity checks que abortan si algo es sospechoso
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingestion/v2", tags=["ingestion-v2"])


# =============================================================================
# Request/Response Models
# =============================================================================

class IngestV2Request(BaseModel):
    """Request para ingestion V2."""
    creator_id: str
    url: str
    max_pages: int = 10
    clean_before: bool = True  # SIEMPRE limpiar datos anteriores
    re_verify: bool = True  # Re-verificar fetching URLs


class InstagramV2Request(BaseModel):
    """Request para ingestion Instagram V2."""
    creator_id: str
    instagram_username: str
    max_posts: int = 20  # Reduced from 50 to avoid rate limits
    clean_before: bool = True  # Limpiar datos anteriores


class InstagramV2Response(BaseModel):
    """Response de ingestion Instagram V2."""
    success: bool
    creator_id: str
    instagram_username: str
    posts_scraped: int
    posts_passed_sanity: int
    posts_rejected: int
    rejection_reasons: list
    posts_saved_db: int
    rag_chunks_created: int
    errors: list


class ProductV2Response(BaseModel):
    """Producto verificado con todas sus pruebas."""
    name: str
    description: str
    price: Optional[float]  # NULL si no encontrado
    currency: str
    source_url: str
    price_source_text: Optional[str]  # Texto literal donde se encontró precio
    signals_matched: list
    confidence: float


class IngestV2Response(BaseModel):
    """Response completa de ingestion V2."""
    success: bool
    status: str  # 'success', 'failed', 'needs_review'
    creator_id: str
    website_url: str

    # Scraping
    pages_scraped: int
    total_chars: int

    # Detection
    products_detected: int
    products_verified: int

    # Products (con pruebas)
    products: list

    # Sanity checks
    sanity_checks: list

    # Storage
    products_saved: int
    rag_docs_saved: int

    # Cleanup
    products_deleted: int

    # Timing
    duration_seconds: float

    # Errors
    errors: list


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

@router.post("/website", response_model=IngestV2Response)
async def ingest_website_v2(request: IngestV2Request, db=Depends(get_db)):
    """
    Ingestion V2 - Zero Hallucinations

    Garantías:
    1. LIMPIA datos anteriores antes de scrapear
    2. Solo detecta productos con 3+ señales
    3. Precios SOLO si encontrados via regex
    4. Aborta si > 20 productos (algo está mal)
    5. Re-verifica cada producto fetching la URL
    6. Solo guarda si todos los sanity checks pasan

    Señales requeridas (mínimo 3):
    - dedicated_page: URL contiene /servicio/, /producto/, etc.
    - cta_present: Tiene "comprar", "reservar", "apúntate"
    - price_visible: Precio encontrado via regex
    - substantial_description: > 100 palabras
    - payment_link: Link a Stripe, Calendly, etc.
    - clear_title: Título < 100 chars

    Retorna:
    - Productos verificados con source_url y source_html
    - Precios con texto literal donde se encontró
    - Detalle de todos los sanity checks
    """
    try:
        from ingestion.v2 import IngestionV2Pipeline

        pipeline = IngestionV2Pipeline(db, request.max_pages)
        result = await pipeline.run(
            creator_id=request.creator_id,
            website_url=request.url,
            clean_before=request.clean_before,
            re_verify=request.re_verify
        )

        return IngestV2Response(
            success=result.success,
            status=result.status,
            creator_id=result.creator_id,
            website_url=result.website_url,
            pages_scraped=result.pages_scraped,
            total_chars=result.total_chars,
            products_detected=result.products_detected,
            products_verified=result.products_verified,
            products=result.products,
            sanity_checks=result.sanity_checks,
            products_saved=result.products_saved,
            rag_docs_saved=result.rag_docs_saved,
            products_deleted=result.products_deleted,
            duration_seconds=result.duration_seconds,
            errors=result.errors
        )

    except Exception as e:
        logger.error(f"Ingestion V2 error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/preview")
async def preview_detection(request: IngestV2Request):
    """
    Preview de detección sin guardar.

    Útil para ver qué productos se detectarían
    antes de ejecutar la ingestion real.
    """
    try:
        from ingestion.v2 import IngestionV2Pipeline

        # Sin DB = no guarda nada
        pipeline = IngestionV2Pipeline(db_session=None, max_pages=request.max_pages)
        result = await pipeline.run(
            creator_id=request.creator_id,
            website_url=request.url,
            clean_before=False,  # No limpiar en preview
            re_verify=request.re_verify
        )

        return {
            "preview": True,
            "would_save": False,
            "status": result.status,
            "pages_scraped": result.pages_scraped,
            "products_detected": result.products_detected,
            "products_verified": result.products_verified,
            "products": result.products,
            "sanity_checks": result.sanity_checks,
            "errors": result.errors
        }

    except Exception as e:
        logger.error(f"Preview error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/verify/{creator_id}")
async def verify_stored_products(creator_id: str, db=Depends(get_db)):
    """
    Verifica productos almacenados para un creator.

    Retorna estadísticas de:
    - Productos con source_url
    - Productos con precio verificado
    - Productos con confidence alta
    """
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        from api.models import Creator, Product
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

        products = db.query(Product).filter(Product.creator_id == creator.id).all()

        total = len(products)
        with_source = len([p for p in products if p.source_url])
        with_price = len([p for p in products if p.price and p.price > 0])
        verified_price = len([p for p in products if p.price_verified])
        high_confidence = len([p for p in products if p.confidence and p.confidence >= 0.5])

        return {
            "creator_id": creator_id,
            "total_products": total,
            "with_source_url": with_source,
            "with_price": with_price,
            "with_verified_price": verified_price,
            "high_confidence": high_confidence,
            "products": [
                {
                    "name": p.name,
                    "price": p.price,
                    "price_verified": p.price_verified,
                    "confidence": p.confidence,
                    "source_url": p.source_url,
                    "has_proof": bool(p.source_url)
                }
                for p in products
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Verify error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Instagram V2 Endpoints
# =============================================================================

@router.post("/instagram", response_model=InstagramV2Response)
async def ingest_instagram_v2_endpoint(request: InstagramV2Request):
    """
    Ingestion V2 para Instagram - Con Sanity Checks

    Garantías:
    1. LIMPIA datos anteriores antes de scrapear (opcional)
    2. Sanity checks para cada post:
       - Caption no vacío (mínimo 10 chars)
       - Fecha válida (no futura, no muy antigua)
       - No duplicados
       - Contenido útil (no solo hashtags)
    3. Persiste en PostgreSQL (instagram_posts + content_chunks)
    4. NO extrae productos - solo contenido RAG

    Request:
    {
        "creator_id": "stefano_auto",
        "instagram_username": "stefanobonanno",
        "max_posts": 50,
        "clean_before": true
    }

    Response:
    {
        "success": true,
        "posts_scraped": 50,
        "posts_passed_sanity": 48,
        "posts_saved_db": 48,
        "rag_chunks_created": 48
    }
    """
    try:
        from ingestion.v2.instagram_ingestion import ingest_instagram_v2

        result = await ingest_instagram_v2(
            creator_id=request.creator_id,
            instagram_username=request.instagram_username,
            max_posts=request.max_posts,
            clean_before=request.clean_before
        )

        return InstagramV2Response(
            success=result.success,
            creator_id=result.creator_id,
            instagram_username=result.instagram_username,
            posts_scraped=result.posts_scraped,
            posts_passed_sanity=result.posts_passed_sanity,
            posts_rejected=result.posts_rejected,
            rejection_reasons=result.rejection_reasons[:10],  # Limit output
            posts_saved_db=result.posts_saved_db,
            rag_chunks_created=result.rag_chunks_created,
            errors=result.errors
        )

    except Exception as e:
        logger.error(f"Instagram V2 ingestion error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/instagram/{creator_id}/status")
async def get_instagram_ingestion_status(creator_id: str):
    """
    Verifica estado de ingestion Instagram para un creator.

    Retorna:
    - Número de posts en DB
    - Número de content chunks
    - Último post indexado
    """
    try:
        from core.tone_profile_db import (
            get_instagram_posts_count_db,
            get_content_chunks_db
        )

        posts_count = get_instagram_posts_count_db(creator_id)
        chunks = await get_content_chunks_db(creator_id)

        # Count only instagram chunks
        instagram_chunks = [
            c for c in chunks
            if c.get('source_type') == 'instagram_post'
        ]

        return {
            "creator_id": creator_id,
            "instagram_posts_in_db": posts_count,
            "instagram_chunks_in_db": len(instagram_chunks),
            "total_chunks_in_db": len(chunks),
            "status": "ready" if posts_count > 0 else "empty"
        }

    except Exception as e:
        logger.error(f"Status check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
