"""
Onboarding Service - Pipeline completo para nuevos creadores.

Combina:
- Instagram scraping (o JSON manual)
- Tone analysis -> ToneProfile
- Content indexing -> CitationIndex
"""

import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict
from dataclasses import dataclass, field

from ingestion import (
    InstagramPost,
    ToneProfile,
    ToneAnalyzer
)
from core.tone_service import save_tone_profile
from core.citation_service import index_creator_posts

logger = logging.getLogger(__name__)


@dataclass
class OnboardingRequest:
    """Request para onboarding de creador."""
    creator_id: str
    instagram_username: Optional[str] = None
    instagram_access_token: Optional[str] = None
    manual_posts: Optional[List[Dict]] = None  # Alternativa al scraping
    scraping_method: str = "manual"  # "meta_api", "instaloader", "manual"
    max_posts: int = 50


@dataclass
class OnboardingResult:
    """Resultado del onboarding."""
    creator_id: str
    success: bool
    posts_processed: int
    tone_profile_generated: bool
    content_indexed: bool
    tone_summary: Optional[Dict] = None
    citation_stats: Optional[Dict] = None
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    def to_dict(self) -> Dict:
        """Convierte a diccionario para respuesta API."""
        return {
            "creator_id": self.creator_id,
            "success": self.success,
            "posts_processed": self.posts_processed,
            "tone_profile_generated": self.tone_profile_generated,
            "content_indexed": self.content_indexed,
            "tone_summary": self.tone_summary,
            "citation_stats": self.citation_stats,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds
        }


class OnboardingService:
    """
    Servicio de onboarding que orquesta todo el pipeline.

    Uso:
        service = OnboardingService()
        result = await service.onboard_creator(request)
    """

    def __init__(self):
        self.tone_analyzer = ToneAnalyzer()

    async def onboard_creator(self, request: OnboardingRequest) -> OnboardingResult:
        """
        Pipeline completo de onboarding.

        1. Obtener posts (scraping o manual)
        2. Analizar tono -> ToneProfile
        3. Indexar contenido -> CitationIndex
        """
        logger.info("[OnboardCreator] ENTERING onboard_creator - creator_id=%s, manual_posts=%d, instagram_username=%s",
                    request.creator_id,
                    len(request.manual_posts) if request.manual_posts else 0,
                    request.instagram_username)

        start_time = datetime.now(timezone.utc)
        errors: List[str] = []
        posts: List[Dict] = []
        tone_profile: Optional[ToneProfile] = None
        citation_stats: Optional[Dict] = None

        try:
            # PASO 1: Obtener posts
            logger.debug("[OnboardCreator] STEP 1: Getting posts...")

            if request.manual_posts:
                # Posts proporcionados manualmente
                logger.debug("[OnboardCreator] Parsing %d manual posts...", len(request.manual_posts))
                posts = self._parse_manual_posts(request.manual_posts)
                logger.info("[Onboarding] %d manual posts received", len(posts))
            elif request.instagram_username:
                # Scraping de Instagram
                logger.debug("[OnboardCreator] Scraping Instagram for %s...", request.instagram_username)
                posts = await self._scrape_instagram(request)
                logger.info("[Onboarding] %d posts scraped from Instagram", len(posts))
            else:
                logger.error("[OnboardCreator] No posts source provided!")
                errors.append("Se requiere instagram_username o manual_posts")
                return self._build_result(request, False, 0, errors, start_time)

            if not posts:
                logger.error("[OnboardCreator] No posts to process!")
                errors.append("No se obtuvieron posts para procesar")
                return self._build_result(request, False, 0, errors, start_time)

            # PASO 2: Analizar tono
            logger.info("[Onboarding] Analyzing tone from %d posts...", len(posts))
            tone_profile = await self._analyze_tone(request.creator_id, posts)
            logger.debug("[OnboardCreator] Tone analysis complete. Profile generated: %s", tone_profile is not None)

            if tone_profile:
                # Guardar ToneProfile
                logger.debug("[OnboardCreator] Saving ToneProfile...")
                await save_tone_profile(tone_profile)
                logger.info("[Onboarding] ToneProfile saved for %s", request.creator_id)
            else:
                logger.warning("[OnboardCreator] No ToneProfile generated")
                errors.append("No se pudo generar ToneProfile")

            # PASO 3: Indexar contenido para citaciones
            logger.info("[Onboarding] Indexing content for citations...")
            citation_stats = await self._index_content(request.creator_id, posts)
            logger.debug("[OnboardCreator] Content indexing complete: %s", citation_stats)

            # Construir resultado
            logger.debug("[OnboardCreator] Building final result...")
            result = self._build_result(
                request=request,
                success=True,
                posts_count=len(posts),
                errors=errors,
                start_time=start_time,
                tone_profile=tone_profile,
                citation_stats=citation_stats
            )
            logger.info("[OnboardCreator] EXITING onboard_creator SUCCESS")
            return result

        except Exception as e:
            logger.error("[OnboardCreator] EXCEPTION in onboard_creator: %s", e, exc_info=True)
            errors.append(str(e))
            return self._build_result(request, False, len(posts), errors, start_time)

    def _parse_manual_posts(self, manual_posts: List[Dict]) -> List[Dict]:
        """Convierte posts manuales a formato estandar."""
        result = []
        for i, post in enumerate(manual_posts):
            caption = post.get("caption", "")
            if caption and len(caption.strip()) > 10:
                parsed = {
                    "post_id": post.get("post_id", f"manual_{i}"),
                    "caption": caption,
                    "post_type": post.get("post_type", post.get("media_type", "image")),
                    "timestamp": post.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    "permalink": post.get("permalink", post.get("url", "")),
                    "media_url": post.get("media_url"),
                    "likes_count": post.get("likes_count", 0),
                    "comments_count": post.get("comments_count", 0)
                }
                result.append(parsed)
        return result

    async def _scrape_instagram(self, request: OnboardingRequest) -> List[Dict]:
        """Scraping de Instagram segun metodo configurado."""
        try:
            from ingestion import (
                MetaGraphAPIScraper
            )

            if request.scraping_method == "meta_api" and request.instagram_access_token:
                # TODO: Obtener instagram_business_id del token
                scraper = MetaGraphAPIScraper(
                    access_token=request.instagram_access_token,
                    instagram_business_id=""  # Necesita configuracion adicional
                )
                posts = await scraper.get_posts(limit=request.max_posts)
                return [self._instagram_post_to_dict(p) for p in posts]
            else:
                # Fallback a manual - requiere que el usuario proporcione posts
                logger.warning("[Onboarding] Instagram scraping not configured, use manual_posts")
                return []

        except Exception as e:
            logger.error(f"[Onboarding] Error scraping Instagram: {e}")
            return []

    def _instagram_post_to_dict(self, post: InstagramPost) -> Dict:
        """Convierte InstagramPost a diccionario."""
        return {
            "post_id": post.post_id,
            "caption": post.caption,
            "post_type": post.post_type,
            "timestamp": post.timestamp.isoformat() if post.timestamp else None,
            "permalink": post.permalink,
            "media_url": post.media_url,
            "likes_count": post.likes_count,
            "comments_count": post.comments_count
        }

    async def _analyze_tone(
        self,
        creator_id: str,
        posts: List[Dict]
    ) -> Optional[ToneProfile]:
        """Analiza el tono de los posts y genera ToneProfile."""
        logger.debug("[_analyze_tone] Entering with %d posts for %s", len(posts), creator_id)
        try:
            if not posts:
                logger.debug("[_analyze_tone] No posts provided, returning None")
                return None

            # Analizar con ToneAnalyzer
            logger.debug("[_analyze_tone] Calling ToneAnalyzer.analyze()...")
            profile = await self.tone_analyzer.analyze(
                creator_id=creator_id,
                posts=posts,
                max_posts=30
            )
            logger.debug("[_analyze_tone] ToneAnalyzer.analyze() returned: %s", profile is not None)
            return profile
        except Exception as e:
            logger.error("[Onboarding] Error in tone analysis: %s", e, exc_info=True)
            return None

    async def _index_content(
        self,
        creator_id: str,
        posts: List[Dict]
    ) -> Dict:
        """Indexa posts para el sistema de citaciones."""
        logger.debug("[_index_content] Entering with %d posts for %s", len(posts), creator_id)
        try:
            # Indexar usando citation_service
            logger.debug("[_index_content] Calling index_creator_posts()...")
            result = await index_creator_posts(
                creator_id=creator_id,
                posts=posts,
                save=True
            )
            logger.debug("[_index_content] index_creator_posts() returned: %s", result)

            return {
                "posts_indexed": result.get("posts_indexed", 0),
                "total_chunks": result.get("total_chunks", 0),
                "indexed_at": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            logger.error("[Onboarding] Error indexing content: %s", e, exc_info=True)
            return {"error": str(e)}

    def _build_result(
        self,
        request: OnboardingRequest,
        success: bool,
        posts_count: int,
        errors: List[str],
        start_time: datetime,
        tone_profile: Optional[ToneProfile] = None,
        citation_stats: Optional[Dict] = None
    ) -> OnboardingResult:
        """Construye el resultado del onboarding."""
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        tone_summary = None
        if tone_profile:
            tone_summary = {
                "formality": tone_profile.formality,
                "energy": tone_profile.energy,
                "warmth": tone_profile.warmth,
                "emoji_frequency": tone_profile.emoji_frequency,
                "main_topics": tone_profile.main_topics[:5] if tone_profile.main_topics else [],
                "signature_phrases": tone_profile.signature_phrases[:3] if tone_profile.signature_phrases else [],
                "confidence_score": tone_profile.confidence_score
            }

        return OnboardingResult(
            creator_id=request.creator_id,
            success=success,
            posts_processed=posts_count,
            tone_profile_generated=tone_profile is not None,
            content_indexed=citation_stats is not None and "error" not in citation_stats,
            tone_summary=tone_summary,
            citation_stats=citation_stats,
            errors=errors,
            duration_seconds=duration
        )


# Singleton para uso global
_onboarding_service: Optional[OnboardingService] = None


def get_onboarding_service() -> OnboardingService:
    """Obtiene instancia singleton del servicio."""
    global _onboarding_service
    if _onboarding_service is None:
        _onboarding_service = OnboardingService()
    return _onboarding_service
