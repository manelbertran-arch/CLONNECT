"""
YouTube ingestion endpoints for Ingestion V2 API.

Endpoints:
- POST /youtube — YouTube channel ingestion with transcript extraction
- GET /youtube/{creator_id}/status — Check YouTube ingestion status
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


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


# =============================================================================
# Endpoints
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
        raise HTTPException(status_code=503, detail="Internal server error")


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
        raise HTTPException(status_code=500, detail="Internal server error")
