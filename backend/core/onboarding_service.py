"""
Onboarding Service - Pipeline completo para nuevos creadores.

Combina:
- Instagram scraping (o JSON manual)
- Tone analysis -> ToneProfile
- Content indexing -> CitationIndex
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from ingestion import (
    InstagramPost,
    ToneProfile,
    ToneAnalyzer
)
from core.tone_service import save_tone_profile, get_tone_profile
from core.citation_service import index_creator_posts, get_content_index

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
        start_time = datetime.now()
        errors: List[str] = []
        posts: List[Dict] = []
        tone_profile: Optional[ToneProfile] = None
        citation_stats: Optional[Dict] = None

        try:
            # PASO 1: Obtener posts
            logger.info(f"[Onboarding] Starting for creator_id={request.creator_id}")

            if request.manual_posts:
                # Posts proporcionados manualmente
                posts = self._parse_manual_posts(request.manual_posts)
                logger.info(f"[Onboarding] {len(posts)} manual posts received")
            elif request.instagram_username:
                # Scraping de Instagram
                posts = await self._scrape_instagram(request)
                logger.info(f"[Onboarding] {len(posts)} posts scraped from Instagram")
            else:
                errors.append("Se requiere instagram_username o manual_posts")
                return self._build_result(request, False, 0, errors, start_time)

            if not posts:
                errors.append("No se obtuvieron posts para procesar")
                return self._build_result(request, False, 0, errors, start_time)

            # PASO 2: Analizar tono
            logger.info(f"[Onboarding] Analyzing tone from {len(posts)} posts...")
            tone_profile = await self._analyze_tone(request.creator_id, posts)

            if tone_profile:
                # Guardar ToneProfile
                await save_tone_profile(tone_profile)
                logger.info(f"[Onboarding] ToneProfile saved for {request.creator_id}")
            else:
                errors.append("No se pudo generar ToneProfile")

            # PASO 3: Indexar contenido para citaciones
            logger.info(f"[Onboarding] Indexing content for citations...")
            citation_stats = await self._index_content(request.creator_id, posts)

            # Construir resultado
            return self._build_result(
                request=request,
                success=True,
                posts_count=len(posts),
                errors=errors,
                start_time=start_time,
                tone_profile=tone_profile,
                citation_stats=citation_stats
            )

        except Exception as e:
            logger.error(f"[Onboarding] Error: {e}")
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
                    "timestamp": post.get("timestamp", datetime.now().isoformat()),
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
                MetaGraphAPIScraper,
                ManualJSONScraper,
                get_instagram_scraper
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
        try:
            if not posts:
                return None

            # Analizar con ToneAnalyzer
            profile = await self.tone_analyzer.analyze(
                creator_id=creator_id,
                posts=posts,
                max_posts=30
            )
            return profile
        except Exception as e:
            logger.error(f"[Onboarding] Error in tone analysis: {e}")
            return None

    async def _index_content(
        self,
        creator_id: str,
        posts: List[Dict]
    ) -> Dict:
        """Indexa posts para el sistema de citaciones."""
        try:
            # Indexar usando citation_service
            result = await index_creator_posts(
                creator_id=creator_id,
                posts=posts,
                save=True
            )

            return {
                "posts_indexed": result.get("posts_indexed", 0),
                "total_chunks": result.get("total_chunks", 0),
                "indexed_at": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"[Onboarding] Error indexing content: {e}")
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
        duration = (datetime.now() - start_time).total_seconds()

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
