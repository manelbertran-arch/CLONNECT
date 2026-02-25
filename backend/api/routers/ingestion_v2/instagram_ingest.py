"""
Instagram ingestion endpoints for Ingestion V2 API.

Endpoints:
- POST /instagram — Instagram content ingestion with sanity checks
- GET /instagram/{creator_id}/status — Check Instagram ingestion status
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


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


# =============================================================================
# Endpoints
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
        raise HTTPException(status_code=503, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")
