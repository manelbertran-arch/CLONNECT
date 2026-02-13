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

from fastapi import APIRouter, Depends, HTTPException
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


class YouTubeV2Request(BaseModel):
    """Request para ingestion YouTube V2."""

    creator_id: str
    channel_url: str  # URL del canal (youtube.com/c/... o youtube.com/@...)
    max_videos: int = 20
    clean_before: bool = True
    fallback_to_whisper: bool = True  # Usar Whisper si no hay subtítulos


class YouTubeV2Response(BaseModel):
    """Response de ingestion YouTube V2."""

    success: bool
    creator_id: str
    channel_url: str
    videos_found: int
    videos_with_transcript: int
    videos_without_transcript: int
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

        # CRITICAL: Log db session status for debugging
        logger.info(
            f"[IngestionV2] db_session={db}, type={type(db)}, creator_id={request.creator_id}"
        )
        if db is None:
            logger.warning("[IngestionV2] WARNING: db is None - products will NOT be saved!")

        pipeline = IngestionV2Pipeline(db_session=db, max_pages=request.max_pages)
        result = await pipeline.run(
            creator_id=request.creator_id,
            website_url=request.url,
            clean_before=request.clean_before,
            re_verify=request.re_verify,
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
            errors=result.errors,
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
            re_verify=request.re_verify,
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
            "errors": result.errors,
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
        creator = (
            db.query(Creator)
            .filter(
                or_(
                    Creator.id == creator_id if len(creator_id) > 20 else False,
                    Creator.name == creator_id,
                )
            )
            .first()
        )

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
                    "has_proof": bool(p.source_url),
                }
                for p in products
            ],
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

        # Auto-lookup creator's IG OAuth credentials from DB
        access_token = None
        instagram_business_id = None
        try:
            from api.database import get_db_session
            from api.models import Creator
            from sqlalchemy import or_

            with get_db_session() as db:
                creator = (
                    db.query(Creator)
                    .filter(
                        or_(
                            Creator.name == request.creator_id,
                            (
                                Creator.id == request.creator_id
                                if len(request.creator_id) > 20
                                else False
                            ),
                        )
                    )
                    .first()
                )
                if creator and creator.instagram_token:
                    access_token = creator.instagram_token
                    instagram_business_id = creator.instagram_page_id
                    logger.info(f"Found IG OAuth credentials for {request.creator_id}")
                else:
                    logger.info(
                        f"No IG OAuth credentials for {request.creator_id}, " "will use Instaloader"
                    )
        except Exception as e:
            logger.warning(f"Could not lookup IG credentials: {e}")

        result = await ingest_instagram_v2(
            creator_id=request.creator_id,
            instagram_username=request.instagram_username,
            max_posts=request.max_posts,
            clean_before=request.clean_before,
            access_token=access_token,
            instagram_business_id=instagram_business_id,
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
            errors=result.errors,
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
        from core.tone_profile_db import get_content_chunks_db, get_instagram_posts_count_db

        posts_count = get_instagram_posts_count_db(creator_id)
        chunks = await get_content_chunks_db(creator_id)

        # Count only instagram chunks
        instagram_chunks = [c for c in chunks if c.get("source_type") == "instagram_post"]

        return {
            "creator_id": creator_id,
            "instagram_posts_in_db": posts_count,
            "instagram_chunks_in_db": len(instagram_chunks),
            "total_chunks_in_db": len(chunks),
            "status": "ready" if posts_count > 0 else "empty",
        }

    except Exception as e:
        logger.error(f"Status check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# YouTube V2 Endpoints
# =============================================================================


@router.post("/youtube", response_model=YouTubeV2Response)
async def ingest_youtube_v2_endpoint(request: YouTubeV2Request):
    """
    Ingestion V2 para YouTube - Transcripts + RAG

    Flujo:
    1. Obtiene videos del canal (yt-dlp)
    2. Para cada video, obtiene transcript:
       - Primero intenta subtítulos de YouTube
       - Si no hay, usa Whisper (si fallback_to_whisper=true)
    3. Divide transcripts en chunks (~500 palabras)
    4. Guarda chunks en PostgreSQL para RAG

    Request:
    {
        "creator_id": "stefano_auto",
        "channel_url": "https://www.youtube.com/@stefanobonanno",
        "max_videos": 20,
        "clean_before": true,
        "fallback_to_whisper": true
    }

    Response:
    {
        "success": true,
        "videos_found": 20,
        "videos_with_transcript": 18,
        "rag_chunks_created": 45
    }

    Nota: Whisper tiene costo ($0.006/min) y límite de 25MB por archivo.
    """
    try:
        from ingestion.v2.youtube_ingestion import ingest_youtube_v2

        result = await ingest_youtube_v2(
            creator_id=request.creator_id,
            channel_url=request.channel_url,
            max_videos=request.max_videos,
            clean_before=request.clean_before,
            fallback_to_whisper=request.fallback_to_whisper,
        )

        return YouTubeV2Response(
            success=result.success,
            creator_id=result.creator_id,
            channel_url=result.channel_url,
            videos_found=result.videos_found,
            videos_with_transcript=result.videos_with_transcript,
            videos_without_transcript=result.videos_without_transcript,
            rag_chunks_created=result.rag_chunks_created,
            errors=result.errors,
        )

    except Exception as e:
        logger.error(f"YouTube V2 ingestion error: {e}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/youtube/{creator_id}/status")
async def get_youtube_ingestion_status(creator_id: str):
    """
    Verifica estado de ingestion YouTube para un creator.

    Retorna:
    - Número de chunks de YouTube en DB
    - Estado de ingestion
    """
    try:
        from core.tone_profile_db import get_content_chunks_db

        chunks = await get_content_chunks_db(creator_id)

        # Count only youtube chunks
        youtube_chunks = [c for c in chunks if c.get("source_type") == "youtube"]

        # Get unique videos
        unique_videos = set(c.get("source_id") for c in youtube_chunks if c.get("source_id"))

        return {
            "creator_id": creator_id,
            "youtube_videos_indexed": len(unique_videos),
            "youtube_chunks_in_db": len(youtube_chunks),
            "total_chunks_in_db": len(chunks),
            "status": "ready" if youtube_chunks else "empty",
        }

    except Exception as e:
        logger.error(f"YouTube status check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Debug Endpoints
# =============================================================================


@router.get("/debug/scraper-test")
async def debug_scraper_test(url: str = "https://www.stefanobonanno.com"):
    """
    Diagnóstico paso a paso del scraper.

    Testea cada componente individualmente para identificar
    dónde falla exactamente.
    """
    import os
    import time

    results = {
        "url": url,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "steps": [],
        "config": {},
        "final_status": "unknown",
    }

    # Step 0: Config check
    results["config"] = {
        "SCRAPER_VERIFY_SSL_env": os.getenv("SCRAPER_VERIFY_SSL", "NOT_SET"),
        "SCRAPER_RESPECT_ROBOTS_env": os.getenv("SCRAPER_RESPECT_ROBOTS", "NOT_SET"),
        "PLAYWRIGHT_ENABLED_env": os.getenv("SCRAPER_USE_PLAYWRIGHT", "NOT_SET"),
    }

    # Step 1: Import check
    step1 = {"step": 1, "name": "imports", "status": "pending", "details": {}}
    try:
        from ingestion.deterministic_scraper import (
            RESPECT_ROBOTS_TXT,
            VERIFY_SSL,
            DeterministicScraper,
            get_robots_checker,
            scraper_circuit_breaker,
        )

        step1["status"] = "ok"
        step1["details"] = {
            "VERIFY_SSL_actual": VERIFY_SSL,
            "RESPECT_ROBOTS_TXT_actual": RESPECT_ROBOTS_TXT,
            "circuit_breaker_state": scraper_circuit_breaker.current_state,
            "circuit_breaker_fail_count": scraper_circuit_breaker.fail_counter,
        }
    except Exception as e:
        step1["status"] = "error"
        step1["details"] = {"error": str(e)}
    results["steps"].append(step1)

    if step1["status"] == "error":
        results["final_status"] = "import_error"
        return results

    # Step 2: Robots.txt check
    step2 = {"step": 2, "name": "robots_txt", "status": "pending", "details": {}}
    try:
        robots_checker = get_robots_checker()
        is_allowed = robots_checker.is_allowed(url)
        step2["status"] = "ok" if is_allowed else "blocked"
        step2["details"] = {
            "is_allowed": is_allowed,
            "respect_robots_enabled": RESPECT_ROBOTS_TXT,
        }
    except Exception as e:
        step2["status"] = "error"
        step2["details"] = {"error": str(e)}
    results["steps"].append(step2)

    if step2["status"] == "blocked":
        results["final_status"] = "blocked_by_robots_txt"
        return results

    # Step 3: Direct HTTP fetch (bypass circuit breaker)
    step3 = {"step": 3, "name": "http_fetch", "status": "pending", "details": {}}
    try:
        import httpx

        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            verify=VERIFY_SSL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ClonnectBot/1.0)"},
        ) as client:
            start = time.time()
            response = await client.get(url)
            duration = time.time() - start

            step3["status"] = "ok" if response.status_code == 200 else "http_error"
            step3["details"] = {
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", "unknown"),
                "content_length": len(response.text),
                "final_url": str(response.url),
                "duration_seconds": round(duration, 3),
                "ssl_verify_used": VERIFY_SSL,
            }
    except httpx.ConnectError as e:
        step3["status"] = "connection_error"
        step3["details"] = {"error": str(e), "hint": "Check SSL settings or network"}
    except Exception as e:
        step3["status"] = "error"
        step3["details"] = {"error": str(e), "error_type": type(e).__name__}
    results["steps"].append(step3)

    if step3["status"] != "ok":
        results["final_status"] = f"http_failed_{step3['status']}"
        return results

    # Step 4: Full scrape attempt
    step4 = {"step": 4, "name": "full_scrape", "status": "pending", "details": {}}
    try:
        scraper = DeterministicScraper(max_pages=1)
        start = time.time()
        page = await scraper.scrape_page(url)
        duration = time.time() - start

        if page:
            step4["status"] = "ok"
            step4["details"] = {
                "title": page.title[:100] if page.title else None,
                "content_length": len(page.main_content),
                "has_content": page.has_content,
                "sections_count": len(page.sections),
                "links_count": len(page.links),
                "duration_seconds": round(duration, 3),
            }
        else:
            step4["status"] = "no_content"
            step4["details"] = {"page": None, "duration_seconds": round(duration, 3)}
    except Exception as e:
        step4["status"] = "error"
        step4["details"] = {"error": str(e), "error_type": type(e).__name__}
    results["steps"].append(step4)

    # Step 5: Playwright check
    step5 = {"step": 5, "name": "playwright", "status": "pending", "details": {}}
    try:
        from ingestion.playwright_scraper import get_playwright_scraper, is_playwright_available

        available = is_playwright_available()
        step5["details"]["is_available"] = available

        if available:
            pw_scraper = get_playwright_scraper()
            start = time.time()
            pw_page = await pw_scraper.scrape_page(url)
            duration = time.time() - start

            if pw_page:
                step5["status"] = "ok"
                step5["details"]["content_length"] = len(pw_page.main_content)
                step5["details"]["has_content"] = pw_page.has_content
                step5["details"]["duration_seconds"] = round(duration, 3)
            else:
                step5["status"] = "no_content"
                step5["details"]["duration_seconds"] = round(duration, 3)
        else:
            step5["status"] = "not_available"
    except ImportError as e:
        step5["status"] = "not_installed"
        step5["details"] = {"error": str(e)}
    except Exception as e:
        step5["status"] = "error"
        step5["details"] = {"error": str(e), "error_type": type(e).__name__}
    results["steps"].append(step5)

    # Final status
    if step4["status"] == "ok":
        results["final_status"] = "success_deterministic"
    elif step5["status"] == "ok":
        results["final_status"] = "success_playwright"
    else:
        results["final_status"] = "failed"

    return results
