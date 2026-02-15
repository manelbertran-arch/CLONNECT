"""Instagram API sync endpoint for posts."""

import logging
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# =============================================================================
# INSTAGRAM API SYNC - Sync posts using Instagram Graph API
# =============================================================================


class InstagramAPISyncRequest(BaseModel):
    """Request para sincronizar posts desde Instagram API."""

    creator_id: str
    limit: int = 25


class InstagramAPISyncResponse(BaseModel):
    """Response de sincronizacion de Instagram API."""

    success: bool
    creator_id: str
    posts_fetched: int
    posts_saved: int
    rag_chunks_created: int
    tone_profile_updated: bool
    errors: List[str]


@router.post("/sync-instagram-api", response_model=InstagramAPISyncResponse)
async def sync_instagram_from_api(request: InstagramAPISyncRequest):
    """
    Sincroniza posts de Instagram usando la Graph API.

    Requiere que el creator tenga un token de Instagram valido guardado.

    1. Obtiene posts desde Instagram Graph API
    2. Guarda en DB (instagram_posts + content_chunks)
    3. Actualiza ToneProfile con el nuevo contenido

    Ideal para cargar datos historicos despues de conectar la cuenta.
    """
    import httpx

    errors = []
    posts_fetched = 0
    posts_saved = 0
    rag_chunks_created = 0
    tone_profile_updated = False

    try:
        # Get creator's token from DB
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=request.creator_id).first()

            if not creator:
                raise HTTPException(
                    status_code=404, detail=f"Creator {request.creator_id} not found"
                )

            if not creator.instagram_token:
                raise HTTPException(status_code=400, detail="Creator has no Instagram token")

            access_token = creator.instagram_token

        finally:
            session.close()

        # Fetch posts from Instagram API
        logger.info(f"[InstagramAPISync] Fetching posts for {request.creator_id}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://graph.instagram.com/v21.0/me/media",
                params={
                    "fields": "id,caption,media_type,timestamp,permalink,like_count,comments_count",
                    "limit": request.limit,
                    "access_token": access_token,
                },
            )

            data = response.json()

            if "error" in data:
                error_msg = data["error"].get("message", "Unknown error")
                errors.append(f"Instagram API error: {error_msg}")
                return InstagramAPISyncResponse(
                    success=False,
                    creator_id=request.creator_id,
                    posts_fetched=0,
                    posts_saved=0,
                    rag_chunks_created=0,
                    tone_profile_updated=False,
                    errors=errors,
                )

            posts = data.get("data", [])
            posts_fetched = len(posts)

            logger.info(f"[InstagramAPISync] Fetched {posts_fetched} posts")

        if posts_fetched == 0:
            errors.append("No posts found")
            return InstagramAPISyncResponse(
                success=False,
                creator_id=request.creator_id,
                posts_fetched=0,
                posts_saved=0,
                rag_chunks_created=0,
                tone_profile_updated=False,
                errors=errors,
            )

        # Convert to DB format and save
        import hashlib

        from core.tone_profile_db import save_content_chunks_db, save_instagram_posts_db

        posts_data = []
        chunks_data = []

        for post in posts:
            caption = post.get("caption", "")
            if not caption:
                continue

            post_id = post.get("id", "")

            # Format for instagram_posts table
            posts_data.append(
                {
                    "id": post_id,
                    "post_id": post_id,
                    "caption": caption,
                    "permalink": post.get("permalink", ""),
                    "media_type": post.get("media_type", ""),
                    "timestamp": post.get("timestamp", ""),
                    "like_count": post.get("like_count", 0),
                    "comments_count": post.get("comments_count", 0),
                }
            )

            # Format for content_chunks (RAG)
            chunk_id = hashlib.sha256(f"{request.creator_id}:{post_id}:0".encode()).hexdigest()[:32]
            first_line = caption.split("\n")[0][:100] if caption else ""

            chunks_data.append(
                {
                    "id": chunk_id,
                    "chunk_id": chunk_id,
                    "creator_id": request.creator_id,
                    "content": caption,
                    "source_type": "instagram_post",
                    "source_id": post_id,
                    "source_url": post.get("permalink", ""),
                    "title": first_line,
                    "chunk_index": 0,
                    "total_chunks": 1,
                    "metadata": {
                        "media_type": post.get("media_type"),
                        "likes": post.get("like_count", 0),
                        "comments": post.get("comments_count", 0),
                        "timestamp": post.get("timestamp"),
                    },
                }
            )

        # Save to DB
        if posts_data:
            posts_saved = await save_instagram_posts_db(request.creator_id, posts_data)
            logger.info(f"[InstagramAPISync] Saved {posts_saved} posts to DB")

        if chunks_data:
            rag_chunks_created = await save_content_chunks_db(request.creator_id, chunks_data)
            logger.info(f"[InstagramAPISync] Created {rag_chunks_created} RAG chunks")

        # Update ToneProfile
        try:
            from core.tone_service import save_tone_profile
            from ingestion.tone_analyzer import ToneAnalyzer

            posts_for_tone = [
                {
                    "caption": p.get("caption", ""),
                    "post_id": p.get("post_id"),
                    "post_type": p.get("media_type"),
                    "permalink": p.get("permalink"),
                    "timestamp": p.get("timestamp"),
                    "likes_count": p.get("like_count", 0),
                    "comments_count": p.get("comments_count", 0),
                }
                for p in posts_data
                if p.get("caption")
            ]

            if posts_for_tone:
                analyzer = ToneAnalyzer()
                tone_profile = await analyzer.analyze(request.creator_id, posts_for_tone)
                await save_tone_profile(tone_profile)
                tone_profile_updated = True
                logger.info("[InstagramAPISync] ToneProfile updated")

        except Exception as e:
            errors.append(f"ToneProfile update failed: {str(e)}")
            logger.warning(f"[InstagramAPISync] ToneProfile error: {e}")

        return InstagramAPISyncResponse(
            success=True,
            creator_id=request.creator_id,
            posts_fetched=posts_fetched,
            posts_saved=posts_saved,
            rag_chunks_created=rag_chunks_created,
            tone_profile_updated=tone_profile_updated,
            errors=errors if errors else [],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[InstagramAPISync] Error: {e}")
        import traceback

        traceback.print_exc()
        errors.append(str(e))
        return InstagramAPISyncResponse(
            success=False,
            creator_id=request.creator_id,
            posts_fetched=posts_fetched,
            posts_saved=posts_saved,
            rag_chunks_created=rag_chunks_created,
            tone_profile_updated=tone_profile_updated,
            errors=errors,
        )
