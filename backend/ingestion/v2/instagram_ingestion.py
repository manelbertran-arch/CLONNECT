"""
Instagram Ingestion V2 - Sanity Checks + PostgreSQL Persistence

Reutiliza InstaloaderScraper existente, añadiendo:
1. Sanity checks (caption, fecha, duplicados)
2. Persistencia en PostgreSQL
3. Conversión a content chunks para RAG

NO extrae productos - solo contenido RAG.
"""

import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class InstagramSanityResult:
    """Resultado de sanity checks para un post."""
    post_id: str
    passed: bool
    checks: Dict[str, bool] = field(default_factory=dict)
    rejection_reason: Optional[str] = None


@dataclass
class InstagramIngestionResult:
    """Resultado completo de ingestion de Instagram."""
    success: bool
    creator_id: str
    instagram_username: str

    # Scraping
    posts_scraped: int = 0

    # Sanity checks
    posts_passed_sanity: int = 0
    posts_rejected: int = 0
    rejection_reasons: List[str] = field(default_factory=list)

    # Persistence
    posts_saved_db: int = 0
    rag_chunks_created: int = 0

    # Errors
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "creator_id": self.creator_id,
            "instagram_username": self.instagram_username,
            "posts_scraped": self.posts_scraped,
            "posts_passed_sanity": self.posts_passed_sanity,
            "posts_rejected": self.posts_rejected,
            "rejection_reasons": self.rejection_reasons[:10],  # Limit
            "posts_saved_db": self.posts_saved_db,
            "rag_chunks_created": self.rag_chunks_created,
            "errors": self.errors
        }


class InstagramPostSanityChecker:
    """
    Sanity checks para posts de Instagram.

    Checks:
    1. Caption no vacío (mínimo 10 chars útiles)
    2. Fecha válida (no futura, no muy antigua)
    3. No duplicados (por post_id)
    4. Contenido útil (no solo hashtags/mentions)
    """

    MIN_CAPTION_LENGTH = 10
    MAX_POST_AGE_DAYS = 365 * 3  # 3 años máximo
    MIN_USEFUL_WORDS = 3  # Al menos 3 palabras útiles

    def __init__(self):
        self._seen_post_ids: set = set()

    def check_post(self, post) -> InstagramSanityResult:
        """
        Ejecuta todos los sanity checks para un post.

        Args:
            post: InstagramPost object del scraper

        Returns:
            InstagramSanityResult con resultado de checks
        """
        checks = {}
        rejection_reason = None

        # Check 1: Caption no vacío
        checks['caption_not_empty'] = self._check_caption_not_empty(post.caption)
        if not checks['caption_not_empty']:
            rejection_reason = f"Caption vacío o muy corto (<{self.MIN_CAPTION_LENGTH} chars)"

        # Check 2: Fecha válida
        checks['valid_date'] = self._check_valid_date(post.timestamp)
        if not checks['valid_date'] and not rejection_reason:
            rejection_reason = "Fecha inválida (futura o muy antigua)"

        # Check 3: No duplicado
        checks['not_duplicate'] = self._check_not_duplicate(post.post_id)
        if not checks['not_duplicate'] and not rejection_reason:
            rejection_reason = f"Post duplicado: {post.post_id}"

        # Check 4: Contenido útil
        checks['useful_content'] = self._check_useful_content(post.caption)
        if not checks['useful_content'] and not rejection_reason:
            rejection_reason = "Contenido no útil (solo hashtags/mentions)"

        passed = all(checks.values())

        return InstagramSanityResult(
            post_id=post.post_id,
            passed=passed,
            checks=checks,
            rejection_reason=rejection_reason if not passed else None
        )

    def _check_caption_not_empty(self, caption: str) -> bool:
        """Caption debe tener contenido mínimo."""
        if not caption:
            return False
        clean = caption.strip()
        return len(clean) >= self.MIN_CAPTION_LENGTH

    def _check_valid_date(self, timestamp: datetime) -> bool:
        """Fecha no debe ser futura ni muy antigua."""
        if not timestamp:
            return False

        now = datetime.now(timezone.utc)

        # Normalizar timestamp a UTC si no tiene timezone
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        # No futuro
        if timestamp > now:
            return False

        # No muy antiguo
        age_days = (now - timestamp).days
        if age_days > self.MAX_POST_AGE_DAYS:
            return False

        return True

    def _check_not_duplicate(self, post_id: str) -> bool:
        """Post no debe estar duplicado."""
        if post_id in self._seen_post_ids:
            return False
        self._seen_post_ids.add(post_id)
        return True

    def _check_useful_content(self, caption: str) -> bool:
        """Caption debe tener contenido útil, no solo hashtags/mentions."""
        if not caption:
            return False

        # Remover hashtags y mentions
        words = caption.split()
        useful_words = [
            w for w in words
            if not w.startswith('#')
            and not w.startswith('@')
            and len(w) > 2
        ]

        return len(useful_words) >= self.MIN_USEFUL_WORDS

    def reset(self):
        """Reset seen posts for new ingestion."""
        self._seen_post_ids.clear()


class InstagramIngestionV2:
    """
    Pipeline de ingestion V2 para Instagram.

    1. Usa InstaloaderScraper existente
    2. Aplica sanity checks
    3. Persiste en PostgreSQL (instagram_posts + content_chunks)
    """

    def __init__(self):
        self.sanity_checker = InstagramPostSanityChecker()

    async def ingest(
        self,
        creator_id: str,
        instagram_username: str,
        max_posts: int = 50,
        clean_before: bool = True
    ) -> InstagramIngestionResult:
        """
        Ejecuta ingestion completa de Instagram.

        Args:
            creator_id: ID del creator
            instagram_username: Username de Instagram a scrapear
            max_posts: Máximo de posts a obtener
            clean_before: Limpiar datos anteriores antes de ingestar

        Returns:
            InstagramIngestionResult con estadísticas
        """
        result = InstagramIngestionResult(
            success=False,
            creator_id=creator_id,
            instagram_username=instagram_username
        )

        try:
            # Reset sanity checker
            self.sanity_checker.reset()

            # PASO 1: Limpiar datos anteriores si se solicita
            if clean_before:
                await self._clean_previous_data(creator_id)

            # PASO 2: Scrapear Instagram
            logger.info(f"Scrapeando Instagram @{instagram_username} (max {max_posts} posts)")
            posts = self._scrape_instagram(instagram_username, max_posts)
            result.posts_scraped = len(posts)

            if not posts:
                result.errors.append(f"No se obtuvieron posts de @{instagram_username}")
                return result

            logger.info(f"Scrapeados {len(posts)} posts de @{instagram_username}")

            # PASO 3: Aplicar sanity checks
            valid_posts = []
            for post in posts:
                sanity_result = self.sanity_checker.check_post(post)
                if sanity_result.passed:
                    valid_posts.append(post)
                else:
                    result.rejection_reasons.append(
                        f"{post.post_id}: {sanity_result.rejection_reason}"
                    )

            result.posts_passed_sanity = len(valid_posts)
            result.posts_rejected = result.posts_scraped - result.posts_passed_sanity

            logger.info(
                f"Sanity checks: {result.posts_passed_sanity} pasaron, "
                f"{result.posts_rejected} rechazados"
            )

            if not valid_posts:
                result.errors.append("Ningún post pasó los sanity checks")
                return result

            # PASO 4: Convertir a formato DB y guardar instagram_posts
            posts_data = self._convert_posts_to_db_format(valid_posts)
            saved_posts = await self._save_posts_to_db(creator_id, posts_data)
            result.posts_saved_db = saved_posts

            # PASO 5: Crear content chunks para RAG
            chunks = self._create_content_chunks(creator_id, valid_posts)
            saved_chunks = await self._save_chunks_to_db(creator_id, chunks)
            result.rag_chunks_created = saved_chunks

            result.success = True
            logger.info(
                f"Ingestion completada: {result.posts_saved_db} posts, "
                f"{result.rag_chunks_created} chunks guardados"
            )

        except Exception as e:
            logger.error(f"Error en ingestion Instagram: {e}")
            import traceback
            traceback.print_exc()
            result.errors.append(str(e))

        return result

    def _scrape_instagram(self, username: str, max_posts: int) -> List:
        """Usa InstaloaderScraper existente."""
        try:
            from ingestion.instagram_scraper import InstaloaderScraper

            scraper = InstaloaderScraper()
            posts = scraper.get_posts(username, limit=max_posts)
            return posts

        except Exception as e:
            logger.error(f"Error scrapeando Instagram: {e}")
            raise

    async def _clean_previous_data(self, creator_id: str):
        """Limpia datos anteriores del creator."""
        try:
            from core.tone_profile_db import (
                delete_instagram_posts_db,
                delete_content_chunks_db
            )

            deleted_posts = await delete_instagram_posts_db(creator_id)
            deleted_chunks = await delete_content_chunks_db(creator_id)

            logger.info(
                f"Limpieza: {deleted_posts} posts, {deleted_chunks} chunks eliminados"
            )

        except Exception as e:
            logger.warning(f"Error limpiando datos anteriores: {e}")

    def _convert_posts_to_db_format(self, posts: List) -> List[dict]:
        """Convierte InstagramPost a formato para DB."""
        return [
            {
                'id': post.post_id,
                'post_id': post.post_id,
                'caption': post.caption,
                'permalink': post.permalink,
                'media_type': post.post_type,
                'media_url': post.media_url,
                'thumbnail_url': post.thumbnail_url,
                'timestamp': post.timestamp.isoformat() if post.timestamp else None,
                'like_count': post.likes_count or 0,
                'comments_count': post.comments_count or 0,
                'hashtags': post.hashtags,
                'mentions': post.mentions
            }
            for post in posts
        ]

    async def _save_posts_to_db(self, creator_id: str, posts: List[dict]) -> int:
        """Guarda posts en PostgreSQL."""
        try:
            from core.tone_profile_db import save_instagram_posts_db

            saved = await save_instagram_posts_db(creator_id, posts)
            return saved

        except Exception as e:
            logger.error(f"Error guardando posts: {e}")
            return 0

    def _create_content_chunks(self, creator_id: str, posts: List) -> List[dict]:
        """Crea content chunks para RAG desde posts."""
        chunks = []

        for post in posts:
            # Generar ID único para el chunk
            chunk_id = hashlib.sha256(
                f"{creator_id}:{post.post_id}:0".encode()
            ).hexdigest()[:32]

            # Construir título desde primera línea del caption
            first_line = post.caption.split('\n')[0][:100] if post.caption else ""

            chunk = {
                'id': chunk_id,
                'chunk_id': chunk_id,
                'creator_id': creator_id,
                'content': post.caption,
                'source_type': 'instagram_post',
                'source_id': post.post_id,
                'source_url': post.permalink,
                'title': first_line,
                'chunk_index': 0,
                'total_chunks': 1,
                'metadata': {
                    'post_type': post.post_type,
                    'likes': post.likes_count,
                    'comments': post.comments_count,
                    'hashtags': post.hashtags,
                    'mentions': post.mentions,
                    'timestamp': post.timestamp.isoformat() if post.timestamp else None
                }
            }
            chunks.append(chunk)

        return chunks

    async def _save_chunks_to_db(self, creator_id: str, chunks: List[dict]) -> int:
        """Guarda content chunks en PostgreSQL."""
        try:
            from core.tone_profile_db import save_content_chunks_db

            saved = await save_content_chunks_db(creator_id, chunks)
            return saved

        except Exception as e:
            logger.error(f"Error guardando chunks: {e}")
            return 0


async def ingest_instagram_v2(
    creator_id: str,
    instagram_username: str,
    max_posts: int = 50,
    clean_before: bool = True
) -> InstagramIngestionResult:
    """
    Función de conveniencia para ejecutar ingestion Instagram V2.

    Args:
        creator_id: ID del creator
        instagram_username: Username de Instagram
        max_posts: Máximo de posts
        clean_before: Limpiar datos antes

    Returns:
        InstagramIngestionResult
    """
    pipeline = InstagramIngestionV2()
    return await pipeline.ingest(
        creator_id=creator_id,
        instagram_username=instagram_username,
        max_posts=max_posts,
        clean_before=clean_before
    )
