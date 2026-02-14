"""Instagram scraping onboarding endpoint."""

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.creator_config import CreatorConfigManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# =============================================================================
# INSTAGRAM SCRAPER ONBOARDING - Auto-setup desde username publico
# =============================================================================


class ScrapeInstagramRequest(BaseModel):
    """Request para scraping automatizado de Instagram."""

    creator_id: str
    instagram_username: str
    max_posts: int = 50


class ScrapeInstagramResponse(BaseModel):
    """Response del scraping de Instagram."""

    success: bool
    creator_id: str
    instagram_username: str
    posts_scraped: int
    tone_profile_generated: bool
    tone_summary: Optional[Dict] = None
    content_indexed: int
    errors: List[str] = []


@router.post("/scrape-instagram", response_model=ScrapeInstagramResponse)
async def scrape_instagram_onboarding(request: ScrapeInstagramRequest):
    """
    Onboarding automatizado desde Instagram publico.

    1. Scrapea los ultimos N posts publicos del username
    2. Genera ToneProfile analizando el contenido
    3. Indexa el contenido para citations

    Args:
        creator_id: ID del creador en Clonnect
        instagram_username: Username de Instagram publico (sin @)
        max_posts: Maximo de posts a scrapear (default 50)

    Returns:
        Resumen del onboarding realizado
    """
    errors = []
    posts_scraped = 0
    tone_generated = False
    tone_summary = None
    content_indexed = 0

    try:
        # Step 1: Scrape Instagram posts
        logger.info(
            f"[ScrapeOnboarding] Starting for {request.creator_id} from @{request.instagram_username}"
        )

        from ingestion.instagram_scraper import InstagramScraperError, InstaloaderScraper

        scraper = InstaloaderScraper()

        try:
            posts = scraper.get_posts(
                target_username=request.instagram_username, limit=request.max_posts
            )
            posts_scraped = len(posts)
            logger.info(
                f"[ScrapeOnboarding] Scraped {posts_scraped} posts from @{request.instagram_username}"
            )
        except InstagramScraperError as e:
            errors.append(f"Scraping error: {str(e)}")
            logger.error(f"[ScrapeOnboarding] Scraping failed: {e}")
            return ScrapeInstagramResponse(
                success=False,
                creator_id=request.creator_id,
                instagram_username=request.instagram_username,
                posts_scraped=0,
                tone_profile_generated=False,
                content_indexed=0,
                errors=errors,
            )

        if posts_scraped == 0:
            errors.append("No posts found or profile is private")
            return ScrapeInstagramResponse(
                success=False,
                creator_id=request.creator_id,
                instagram_username=request.instagram_username,
                posts_scraped=0,
                tone_profile_generated=False,
                content_indexed=0,
                errors=errors,
            )

        # Step 2: Generate ToneProfile
        try:
            from core.tone_service import save_tone_profile
            from ingestion.tone_analyzer import ToneAnalyzer, ToneProfile

            # Convert posts to dict format for analyzer
            posts_data = [
                {
                    "caption": post.caption,
                    "post_id": post.post_id,
                    "post_type": post.post_type,
                    "permalink": post.permalink,
                    "timestamp": post.timestamp.isoformat() if post.timestamp else None,
                    "likes_count": post.likes_count,
                    "comments_count": post.comments_count,
                }
                for post in posts
            ]

            analyzer = ToneAnalyzer()
            tone_profile = await analyzer.analyze(request.creator_id, posts_data)

            # Save the profile
            await save_tone_profile(tone_profile)
            tone_generated = True

            tone_summary = {
                "formality": tone_profile.formality,
                "energy": tone_profile.energy,
                "warmth": tone_profile.warmth,
                "uses_emojis": tone_profile.uses_emojis,
                "emoji_frequency": tone_profile.emoji_frequency,
                "signature_phrases": tone_profile.signature_phrases[:5],
                "analyzed_posts": tone_profile.analyzed_posts_count,
                "primary_language": tone_profile.primary_language,
            }

            logger.info(
                f"[ScrapeOnboarding] ToneProfile generated: {tone_profile.formality}, {tone_profile.energy}, lang={tone_profile.primary_language}"
            )

            # Step 2b: Create basic creator_config if it doesn't exist
            try:
                config_manager = CreatorConfigManager()
                existing_config = config_manager.get_config(request.creator_id)

                if not existing_config or not existing_config.get("name"):
                    # Create basic config from ToneProfile
                    basic_config = {
                        "name": request.instagram_username,
                        "instagram_username": request.instagram_username,
                        "personality": {
                            "formality": tone_profile.formality,
                            "language": tone_profile.primary_language,
                        },
                        "clone_tone": (
                            "friendly"
                            if tone_profile.formality in ["informal", "muy_informal"]
                            else "professional"
                        ),
                        "bot_active": True,
                    }
                    config_manager.save_config(request.creator_id, basic_config)
                    logger.info(
                        f"[ScrapeOnboarding] Created basic creator_config for {request.creator_id}"
                    )
            except Exception as config_error:
                logger.warning(
                    f"[ScrapeOnboarding] Could not create creator_config: {config_error}"
                )

        except Exception as e:
            errors.append(f"ToneProfile generation error: {str(e)}")
            logger.error(f"[ScrapeOnboarding] ToneProfile failed: {e}")

        # Step 3: Index content for citations
        try:
            import json
            from datetime import datetime
            from pathlib import Path

            # Create chunks from posts
            chunks = []
            posts_index = {}  # Dict with post_id as key (matches citation_service format)

            for i, post in enumerate(posts):
                if not post.caption or len(post.caption.strip()) < 20:
                    continue

                # Create a title from first line or truncated caption
                title_candidate = post.caption.split("\n")[0][:100]
                if len(title_candidate) < 10:
                    title_candidate = post.caption[:100]

                # Extract keywords from caption
                keywords = []
                # Add hashtags
                keywords.extend(post.hashtags[:5])
                # Add first few words
                words = post.caption.lower().split()[:10]
                keywords.extend([w for w in words if len(w) > 3])

                chunk = {
                    "id": f"{request.creator_id}_post_{post.post_id}",
                    "creator_id": request.creator_id,
                    "source_type": (
                        "instagram_post" if post.post_type != "reel" else "instagram_reel"
                    ),
                    "source_id": post.post_id,
                    "source_url": post.permalink,
                    "title": title_candidate,
                    "content": post.caption[:1000],  # Limit content length
                    "chunk_index": 0,
                    "total_chunks": 1,
                    "metadata": {
                        "post_type": post.post_type,
                        "likes": post.likes_count,
                        "comments": post.comments_count,
                        "hashtags": post.hashtags,
                        "keywords": list(set(keywords))[:10],
                    },
                    "created_at": (
                        post.timestamp.isoformat()
                        if post.timestamp
                        else datetime.utcnow().isoformat()
                    ),
                }
                chunks.append(chunk)

                posts_index[post.post_id] = {
                    "post_id": post.post_id,
                    "caption": post.caption,
                    "post_type": post.post_type,
                    "url": post.permalink,
                    "published_date": post.timestamp.isoformat() if post.timestamp else None,
                    "chunk_count": 1,
                }

            content_indexed = len(chunks)

            if content_indexed > 0:
                # Save to content_index directory (JSON backup)
                content_dir = Path("data/content_index") / request.creator_id
                content_dir.mkdir(parents=True, exist_ok=True)

                chunks_path = content_dir / "chunks.json"
                posts_path = content_dir / "posts.json"

                with open(chunks_path, "w", encoding="utf-8") as f:
                    json.dump(chunks, f, ensure_ascii=False, indent=2)

                with open(posts_path, "w", encoding="utf-8") as f:
                    json.dump(posts_index, f, ensure_ascii=False, indent=2)

                logger.info(f"[ScrapeOnboarding] Indexed {content_indexed} posts to JSON")

                # Save to PostgreSQL (primary storage)
                try:
                    from core.tone_profile_db import save_content_chunks_db, save_instagram_posts_db

                    # Save chunks to DB
                    chunks_saved = await save_content_chunks_db(request.creator_id, chunks)
                    logger.info(f"[ScrapeOnboarding] Saved {chunks_saved} chunks to PostgreSQL")

                    # Save Instagram posts to DB
                    posts_for_db = [
                        {
                            "id": post.post_id,
                            "caption": post.caption,
                            "permalink": post.permalink,
                            "media_type": post.post_type,
                            "timestamp": post.timestamp.isoformat() if post.timestamp else None,
                            "like_count": post.likes_count,
                            "comments_count": post.comments_count,
                        }
                        for post in posts
                    ]
                    posts_saved = await save_instagram_posts_db(request.creator_id, posts_for_db)
                    logger.info(
                        f"[ScrapeOnboarding] Saved {posts_saved} Instagram posts to PostgreSQL"
                    )

                    # Hydrate RAG with the new chunks (critical for search)
                    try:
                        from api.main import rag

                        loaded = rag.load_from_db(request.creator_id)
                        logger.info(
                            f"[ScrapeOnboarding] Hydrated RAG with {loaded} chunks for {request.creator_id}"
                        )
                    except Exception as rag_error:
                        logger.warning(f"[ScrapeOnboarding] Could not hydrate RAG: {rag_error}")

                except Exception as db_error:
                    logger.warning(
                        f"[ScrapeOnboarding] DB save failed (JSON backup exists): {db_error}"
                    )

                # Reload citation index
                try:
                    from core.citation_service import reload_creator_index

                    reload_creator_index(request.creator_id)
                except Exception as reload_error:
                    logger.warning(f"[ScrapeOnboarding] Could not reload index: {reload_error}")

        except Exception as e:
            errors.append(f"Content indexing error: {str(e)}")
            logger.error(f"[ScrapeOnboarding] Indexing failed: {e}")

        success = posts_scraped > 0 and (tone_generated or content_indexed > 0)

        return ScrapeInstagramResponse(
            success=success,
            creator_id=request.creator_id,
            instagram_username=request.instagram_username,
            posts_scraped=posts_scraped,
            tone_profile_generated=tone_generated,
            tone_summary=tone_summary,
            content_indexed=content_indexed,
            errors=errors,
        )

    except Exception as e:
        logger.error(f"[ScrapeOnboarding] Unexpected error: {e}")
        errors.append(f"Unexpected error: {str(e)}")
        return ScrapeInstagramResponse(
            success=False,
            creator_id=request.creator_id,
            instagram_username=request.instagram_username,
            posts_scraped=posts_scraped,
            tone_profile_generated=tone_generated,
            content_indexed=content_indexed,
            errors=errors,
        )
