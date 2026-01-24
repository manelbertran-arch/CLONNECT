"""
Auto Configurator - Orquesta la creación automática de clones.

Combina:
- Instagram scraping (50 posts)
- Video transcription (Whisper)
- Website scraping + Product detection (V2)
- ToneProfile generation
- RAG indexing
- Dashboard auto-fill

Diseñado para zero-hallucination y contenido citable.
"""

import asyncio
import logging
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class AutoConfigResult:
    """Resultado completo de auto-configuración."""
    success: bool
    creator_id: str
    status: str  # 'success', 'partial', 'failed'

    # Steps completed
    steps_completed: List[str] = field(default_factory=list)

    # Instagram
    instagram_posts_scraped: int = 0
    instagram_posts_indexed: int = 0
    instagram_sanity_passed: int = 0

    # Transcription
    videos_found: int = 0
    videos_transcribed: int = 0
    transcription_errors: List[str] = field(default_factory=list)

    # Website
    website_pages_scraped: int = 0
    products_detected: int = 0
    products_verified: int = 0

    # ToneProfile
    tone_profile_generated: bool = False
    tone_confidence: float = 0.0

    # RAG
    content_chunks_created: int = 0

    # DMs (NEW)
    dms_conversations_found: int = 0
    dms_messages_imported: int = 0
    dms_leads_created: int = 0

    # Bio (NEW)
    bio_loaded: bool = False

    # FAQs (NEW)
    faqs_generated: int = 0

    # Errors
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Timing
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "creator_id": self.creator_id,
            "status": self.status,
            "steps_completed": self.steps_completed,
            "instagram": {
                "posts_scraped": self.instagram_posts_scraped,
                "posts_indexed": self.instagram_posts_indexed,
                "sanity_passed": self.instagram_sanity_passed
            },
            "transcription": {
                "videos_found": self.videos_found,
                "videos_transcribed": self.videos_transcribed,
                "errors": self.transcription_errors[:5]
            },
            "website": {
                "pages_scraped": self.website_pages_scraped,
                "products_detected": self.products_detected,
                "products_verified": self.products_verified
            },
            "tone_profile": {
                "generated": self.tone_profile_generated,
                "confidence": self.tone_confidence
            },
            "rag": {
                "chunks_created": self.content_chunks_created
            },
            "dms": {
                "conversations_found": self.dms_conversations_found,
                "messages_imported": self.dms_messages_imported,
                "leads_created": self.dms_leads_created
            },
            "bio": {
                "loaded": self.bio_loaded
            },
            "faqs": {
                "generated": self.faqs_generated
            },
            "errors": self.errors[:10],
            "warnings": self.warnings[:10],
            "duration_seconds": self.duration_seconds
        }


class AutoConfigurator:
    """
    Orquestador de auto-configuración de clones.

    Pipeline:
    1. Scrapear Instagram (50 posts)
    2. Transcribir videos/reels
    3. Scrapear website + detectar productos
    4. Generar ToneProfile
    5. Cargar historial de DMs (últimos 50) + calcular scoring
    6. Extraer bio del perfil de Instagram
    7. Generar FAQs automáticas desde contenido
    8. Indexar contenido para RAG
    9. Actualizar Creator en DB
    """

    def __init__(self, db_session=None):
        self.db = db_session

    async def run(
        self,
        creator_id: str,
        instagram_username: str,
        website_url: Optional[str] = None,
        max_posts: int = 50,
        transcribe_videos: bool = True
    ) -> AutoConfigResult:
        """
        Ejecuta pipeline completo de auto-configuración.

        Args:
            creator_id: ID/nombre del creator
            instagram_username: Username de Instagram
            website_url: URL del website (opcional)
            max_posts: Máximo de posts a scrapear
            transcribe_videos: Si transcribir videos con Whisper

        Returns:
            AutoConfigResult con estadísticas completas
        """
        import time
        start_time = time.time()

        result = AutoConfigResult(
            success=False,
            creator_id=creator_id,
            status='failed'
        )

        try:
            # PASO 1: Scrapear Instagram
            logger.info(f"[AutoConfig] Step 1: Scraping Instagram @{instagram_username}")
            ig_result = await self._scrape_instagram(
                creator_id=creator_id,
                instagram_username=instagram_username,
                max_posts=max_posts
            )
            result.instagram_posts_scraped = ig_result.get('posts_scraped', 0)
            result.instagram_posts_indexed = ig_result.get('posts_saved_db', 0)
            result.instagram_sanity_passed = ig_result.get('posts_passed_sanity', 0)
            result.content_chunks_created += ig_result.get('rag_chunks_created', 0)

            if ig_result.get('success'):
                result.steps_completed.append('instagram_scraping')
            else:
                result.errors.extend(ig_result.get('errors', []))

            # PASO 2: Transcribir videos (opcional)
            if transcribe_videos:
                logger.info("[AutoConfig] Step 2: Transcribing videos")
                try:
                    trans_result = await self._transcribe_videos(creator_id)
                    result.videos_found = trans_result.get('videos_found', 0)
                    result.videos_transcribed = trans_result.get('videos_transcribed', 0)
                    result.transcription_errors = trans_result.get('errors', [])
                    result.content_chunks_created += trans_result.get('chunks_created', 0)

                    if trans_result.get('videos_transcribed', 0) > 0:
                        result.steps_completed.append('video_transcription')
                except Exception as e:
                    logger.warning(f"Video transcription failed: {e}")
                    result.warnings.append(f"Video transcription skipped: {str(e)}")

            # PASO 3: Scrapear website + detectar productos
            if website_url:
                logger.info(f"[AutoConfig] Step 3: Scraping website {website_url}")
                try:
                    web_result = await self._scrape_website(
                        creator_id=creator_id,
                        website_url=website_url
                    )
                    result.website_pages_scraped = web_result.get('pages_scraped', 0)
                    result.products_detected = web_result.get('products_detected', 0)
                    result.products_verified = web_result.get('products_verified', 0)
                    result.content_chunks_created += web_result.get('rag_docs_saved', 0)

                    if web_result.get('success'):
                        result.steps_completed.append('website_scraping')
                        result.steps_completed.append('product_detection')
                    else:
                        result.warnings.extend(web_result.get('errors', []))
                except Exception as e:
                    logger.warning(f"Website scraping failed: {e}")
                    result.warnings.append(f"Website scraping failed: {str(e)}")

            # PASO 4: Generar ToneProfile
            logger.info("[AutoConfig] Step 4: Generating ToneProfile")
            try:
                tone_result = await self._generate_tone_profile(creator_id)
                result.tone_profile_generated = tone_result.get('success', False)
                result.tone_confidence = tone_result.get('confidence', 0.0)

                if result.tone_profile_generated:
                    result.steps_completed.append('tone_profile')
            except Exception as e:
                logger.warning(f"ToneProfile generation failed: {e}")
                result.warnings.append(f"ToneProfile generation failed: {str(e)}")

            # PASO 5: Cargar historial de DMs (incluye scoring de leads)
            logger.info("[AutoConfig] Step 5: Loading DM History")
            try:
                dm_result = await self._load_dm_history(creator_id)
                result.dms_conversations_found = dm_result.get('conversations_found', 0)
                result.dms_messages_imported = dm_result.get('messages_imported', 0)
                result.dms_leads_created = dm_result.get('leads_created', 0)

                if dm_result.get('success'):
                    result.steps_completed.append('dm_history')
                else:
                    if dm_result.get('reason'):
                        result.warnings.append(f"DM history: {dm_result.get('reason')}")
            except Exception as e:
                logger.warning(f"DM history loading failed: {e}")
                result.warnings.append(f"DM history skipped: {str(e)}")

            # PASO 6: Extraer bio del perfil de Instagram
            logger.info("[AutoConfig] Step 6: Extracting Bio")
            try:
                bio_result = await self._extract_bio(creator_id, instagram_username)
                result.bio_loaded = bio_result.get('success', False)

                if result.bio_loaded:
                    result.steps_completed.append('bio_extracted')
            except Exception as e:
                logger.warning(f"Bio extraction failed: {e}")
                result.warnings.append(f"Bio extraction skipped: {str(e)}")

            # PASO 7: Generar FAQs automáticas
            logger.info("[AutoConfig] Step 7: Generating FAQs")
            try:
                faq_result = await self._generate_faqs(creator_id)
                result.faqs_generated = faq_result.get('faqs_created', 0)

                if result.faqs_generated > 0:
                    result.steps_completed.append('faqs_generated')
            except Exception as e:
                logger.warning(f"FAQ generation failed: {e}")
                result.warnings.append(f"FAQ generation skipped: {str(e)}")

            # PASO 8: Actualizar Creator
            logger.info("[AutoConfig] Step 8: Updating Creator")
            try:
                await self._update_creator(
                    creator_id=creator_id,
                    instagram_username=instagram_username,
                    website_url=website_url,
                    tone_confidence=result.tone_confidence
                )
                result.steps_completed.append('creator_updated')
            except Exception as e:
                logger.warning(f"Creator update failed: {e}")
                result.warnings.append(f"Creator update failed: {str(e)}")

            # Determinar status final
            if len(result.steps_completed) >= 3:
                result.success = True
                result.status = 'success' if len(result.errors) == 0 else 'partial'
            elif len(result.steps_completed) >= 1:
                result.status = 'partial'
            else:
                result.status = 'failed'

        except Exception as e:
            logger.error(f"AutoConfig failed: {e}")
            import traceback
            traceback.print_exc()
            result.errors.append(str(e))
            result.status = 'failed'

        result.duration_seconds = time.time() - start_time
        logger.info(
            f"[AutoConfig] Completed in {result.duration_seconds:.1f}s - "
            f"Status: {result.status}, Steps: {result.steps_completed}"
        )

        return result

    async def _scrape_instagram(
        self,
        creator_id: str,
        instagram_username: str,
        max_posts: int
    ) -> dict:
        """
        Scrapea posts de Instagram con V2 sanity checks.

        Prioridad:
        1. Meta Graph API (si el Creator tiene token OAuth guardado)
        2. Instaloader (fallback, scraping público)
        """
        # Intentar obtener credenciales OAuth del Creator
        access_token = None
        instagram_business_id = None

        try:
            from api.database import get_db_session
            from api.models import Creator
            from sqlalchemy import or_

            with get_db_session() as db:
                creator = db.query(Creator).filter(
                    or_(
                        Creator.id == creator_id if len(str(creator_id)) > 20 else False,
                        Creator.name == creator_id
                    )
                ).first()

                if creator:
                    access_token = creator.instagram_token
                    # instagram_business_id puede ser instagram_user_id o instagram_page_id
                    instagram_business_id = creator.instagram_user_id or creator.instagram_page_id

                    if access_token and instagram_business_id:
                        logger.info(
                            f"[AutoConfig] Credenciales OAuth encontradas para {creator_id}, "
                            f"usando Meta Graph API"
                        )
                    else:
                        logger.info(
                            f"[AutoConfig] No hay credenciales OAuth completas para {creator_id}, "
                            f"usando Instaloader"
                        )

        except Exception as e:
            logger.warning(f"[AutoConfig] Error obteniendo credenciales OAuth: {e}")

        # Ejecutar ingestion con o sin credenciales OAuth
        try:
            from ingestion.v2.instagram_ingestion import ingest_instagram_v2

            result = await ingest_instagram_v2(
                creator_id=creator_id,
                instagram_username=instagram_username,
                max_posts=max_posts,
                clean_before=True,
                access_token=access_token,
                instagram_business_id=instagram_business_id
            )
            return result.to_dict()

        except Exception as e:
            logger.error(f"Instagram scraping error: {e}")
            return {
                'success': False,
                'posts_scraped': 0,
                'errors': [str(e)]
            }

    async def _transcribe_videos(self, creator_id: str) -> dict:
        """Transcribe videos de posts de Instagram."""
        result = {
            'videos_found': 0,
            'videos_transcribed': 0,
            'chunks_created': 0,
            'errors': []
        }

        try:
            from core.tone_profile_db import get_instagram_posts_db
            from ingestion.transcriber import get_transcriber
            from core.citation_service import get_content_index

            # Obtener posts con video
            posts = await get_instagram_posts_db(creator_id)
            video_posts = [
                p for p in posts
                if p.get('media_type') in ['VIDEO', 'REELS', 'video', 'reel']
                and p.get('media_url')
            ]

            result['videos_found'] = len(video_posts)

            if not video_posts:
                logger.info("No video posts found to transcribe")
                return result

            transcriber = get_transcriber()
            index = get_content_index(creator_id)

            for post in video_posts[:10]:  # Limit to 10 videos
                try:
                    media_url = post.get('media_url')
                    if not media_url:
                        continue

                    transcript = await transcriber.transcribe_url(
                        url=media_url,
                        language="es",
                        include_timestamps=True
                    )

                    if transcript and transcript.full_text:
                        # Agregar como chunk RAG
                        chunks = index.add_post(
                            post_id=f"{post['id']}_transcript",
                            caption=transcript.full_text,
                            post_type='instagram_reel_transcript',
                            url=post.get('permalink'),
                            published_date=None
                        )
                        result['chunks_created'] += len(chunks)
                        result['videos_transcribed'] += 1

                except Exception as e:
                    logger.warning(f"Failed to transcribe video {post.get('id')}: {e}")
                    result['errors'].append(f"{post.get('id')}: {str(e)}")

            # Guardar índice
            if result['chunks_created'] > 0:
                index.save()

        except ImportError as e:
            logger.warning(f"Transcription dependencies not available: {e}")
            result['errors'].append(f"Dependencies missing: {str(e)}")
        except Exception as e:
            logger.error(f"Video transcription error: {e}")
            result['errors'].append(str(e))

        return result

    async def _scrape_website(self, creator_id: str, website_url: str) -> dict:
        """Scrapea website con V2 product detection."""
        try:
            from ingestion.v2.pipeline import ingest_website_v2

            result = await ingest_website_v2(
                creator_id=creator_id,
                website_url=website_url,
                db_session=self.db,
                max_pages=10,
                clean_before=False,  # Don't clean Instagram data
                re_verify=True
            )
            return result.to_dict()

        except Exception as e:
            logger.error(f"Website scraping error: {e}")
            return {
                'success': False,
                'pages_scraped': 0,
                'errors': [str(e)]
            }

    async def _generate_tone_profile(self, creator_id: str) -> dict:
        """Genera ToneProfile desde posts indexados."""
        result = {
            'success': False,
            'confidence': 0.0
        }

        try:
            from core.tone_profile_db import (
                get_instagram_posts_db,
                save_tone_profile_db
            )

            # Obtener posts
            posts = await get_instagram_posts_db(creator_id)
            if not posts:
                logger.warning("No posts found for ToneProfile generation")
                return result

            # Extraer captions
            captions = [
                p.get('caption', '')
                for p in posts
                if len(p.get('caption', '')) > 20
            ]

            if len(captions) < 5:
                logger.warning(f"Not enough captions ({len(captions)}) for reliable ToneProfile")
                return result

            # Análisis simple del tono
            profile_data = self._analyze_tone(captions)
            profile_data['analyzed_posts_count'] = len(captions)
            profile_data['generated_at'] = datetime.utcnow().isoformat()

            # Guardar en DB
            saved = await save_tone_profile_db(creator_id, profile_data)

            result['success'] = saved
            result['confidence'] = profile_data.get('confidence_score', 0.0)

        except Exception as e:
            logger.error(f"ToneProfile generation error: {e}")

        return result

    def _analyze_tone(self, captions: List[str]) -> dict:
        """Análisis básico de tono desde captions."""
        import re
        from collections import Counter

        all_text = ' '.join(captions)

        # Extraer emojis
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "\U00002702-\U000027B0"
            "\U0001F900-\U0001F9FF"
            "]+",
            flags=re.UNICODE
        )
        emojis = emoji_pattern.findall(all_text)
        emoji_counts = Counter(emojis)
        top_emojis = [e for e, _ in emoji_counts.most_common(10)]

        # Calcular longitud promedio
        avg_length = sum(len(c) for c in captions) / len(captions)

        # Detectar formalidad (simple heuristic)
        formal_indicators = ['usted', 'estimado', 'cordialmente', 'atentamente']
        informal_indicators = ['tú', 'tu', 'hey', 'hola', '!', '😊', '🙌']

        formal_count = sum(1 for w in formal_indicators if w in all_text.lower())
        informal_count = sum(1 for w in informal_indicators if w in all_text.lower())

        formality = formal_count / (formal_count + informal_count + 1)

        # Extraer palabras frecuentes (excluir stopwords)
        stopwords = {
            'de', 'la', 'que', 'el', 'en', 'y', 'a', 'los', 'del', 'se',
            'las', 'por', 'un', 'para', 'con', 'no', 'una', 'su', 'al',
            'es', 'lo', 'como', 'más', 'pero', 'sus', 'le', 'ya', 'o',
            'este', 'si', 'porque', 'esta', 'son', 'entre', 'cuando',
            'muy', 'sin', 'sobre', 'también', 'me', 'hasta', 'hay',
            'donde', 'quien', 'desde', 'todo', 'nos', 'durante', 'te'
        }

        words = re.findall(r'\b[a-záéíóúñü]+\b', all_text.lower())
        words = [w for w in words if w not in stopwords and len(w) > 3]
        word_counts = Counter(words)
        top_words = [w for w, _ in word_counts.most_common(20)]

        # Detectar temas
        fitness_words = ['fitness', 'entreno', 'ejercicio', 'gym', 'deporte', 'fuerza']
        mindset_words = ['mente', 'mindset', 'mentalidad', 'propósito', 'energía']
        nutrition_words = ['nutrición', 'dieta', 'comida', 'alimentación', 'proteína']

        topics = []
        if any(w in all_text.lower() for w in fitness_words):
            topics.append('fitness')
        if any(w in all_text.lower() for w in mindset_words):
            topics.append('mindset')
        if any(w in all_text.lower() for w in nutrition_words):
            topics.append('nutrition')

        # Confidence basado en cantidad de datos
        confidence = min(1.0, len(captions) / 30)

        return {
            'emoji_style': top_emojis,
            'avg_message_length': round(avg_length),
            'formality': round(formality, 2),
            'frequent_words': top_words,
            'topics': topics,
            'confidence_score': round(confidence, 2)
        }

    async def _update_creator(
        self,
        creator_id: str,
        instagram_username: str,
        website_url: Optional[str],
        tone_confidence: float
    ):
        """Actualiza Creator en DB con datos extraídos."""
        try:
            from api.database import get_db_session
            from api.models import Creator
            from sqlalchemy import or_

            with get_db_session() as db:
                creator = db.query(Creator).filter(
                    or_(
                        Creator.id == creator_id if len(str(creator_id)) > 20 else False,
                        Creator.name == creator_id
                    )
                ).first()

                if not creator:
                    logger.warning(f"Creator not found: {creator_id}")
                    return

                # Actualizar campos
                creator.instagram_username = instagram_username
                if website_url:
                    creator.website_url = website_url

                # Marcar onboarding como completado
                creator.onboarding_completed = True

                # Activar bot si hay suficiente confianza
                if tone_confidence >= 0.5:
                    creator.bot_active = True

                db.commit()
                logger.info(f"Updated creator {creator_id}")

        except Exception as e:
            logger.error(f"Error updating creator: {e}")
            raise

    async def _load_dm_history(self, creator_id: str) -> dict:
        """
        Carga historial de DMs desde Instagram API.
        Requiere que el creator tenga instagram_token configurado.
        También calcula scoring de leads basado en intent de mensajes.
        """
        result = {
            'success': False,
            'conversations_found': 0,
            'messages_imported': 0,
            'leads_created': 0,
            'reason': None
        }

        try:
            from api.database import get_db_session
            from api.models import Creator
            from core.dm_history_service import get_dm_history_service
            from sqlalchemy import or_

            # Obtener credenciales del creator
            with get_db_session() as db:
                creator = db.query(Creator).filter(
                    or_(
                        Creator.id == creator_id if len(str(creator_id)) > 20 else False,
                        Creator.name == creator_id
                    )
                ).first()

                if not creator:
                    result['reason'] = 'Creator not found'
                    return result

                access_token = creator.instagram_token
                page_id = creator.instagram_page_id
                ig_user_id = creator.instagram_user_id

            # Solo necesitamos access_token y al menos uno de page_id o ig_user_id
            # Instagram Login API solo proporciona ig_user_id, no page_id
            if not access_token or (not page_id and not ig_user_id):
                result['reason'] = 'Instagram OAuth credentials not configured'
                logger.info(f"[AutoConfig] DM history skipped: no OAuth credentials for {creator_id}")
                return result

            # Cargar historial de DMs
            dm_service = get_dm_history_service()
            stats = await dm_service.load_dm_history(
                creator_id=creator_id,
                access_token=access_token,
                page_id=page_id,  # Puede ser None si usamos Instagram Login API
                ig_user_id=ig_user_id,
                limit=50  # Últimos 50 DMs
            )

            result['conversations_found'] = stats.get('conversations_found', 0)
            result['messages_imported'] = stats.get('messages_imported', 0)
            result['leads_created'] = stats.get('leads_created', 0)
            result['success'] = result['messages_imported'] > 0 or result['conversations_found'] > 0

            logger.info(
                f"[AutoConfig] DM history loaded: {result['conversations_found']} conversations, "
                f"{result['messages_imported']} messages, {result['leads_created']} new leads"
            )

        except ImportError as e:
            result['reason'] = f'Missing dependencies: {str(e)}'
            logger.warning(f"[AutoConfig] DM history dependencies missing: {e}")
        except Exception as e:
            result['reason'] = str(e)
            logger.error(f"[AutoConfig] DM history error: {e}")

        return result

    async def _extract_bio(self, creator_id: str, instagram_username: str) -> dict:
        """
        Extrae bio del perfil de Instagram y la guarda en knowledge_about.
        Usa instaloader para scraping público si no hay OAuth.
        """
        result = {
            'success': False,
            'bio': None
        }

        try:
            from api.database import get_db_session
            from api.models import Creator
            from sqlalchemy import or_

            bio_data = {}

            # Intentar obtener bio via scraping público
            try:
                import instaloader
                L = instaloader.Instaloader()
                profile = instaloader.Profile.from_username(L.context, instagram_username)

                bio_data = {
                    'name': profile.full_name or instagram_username,
                    'bio': profile.biography or '',
                    'followers': profile.followers,
                    'following': profile.followees,
                    'posts_count': profile.mediacount,
                    'external_url': profile.external_url or '',
                    'is_verified': profile.is_verified,
                    'instagram_username': instagram_username
                }

                logger.info(f"[AutoConfig] Extracted bio for @{instagram_username}: {bio_data.get('name')}")

            except Exception as e:
                logger.warning(f"[AutoConfig] Instaloader bio extraction failed: {e}")
                # Fallback: crear bio básica
                bio_data = {
                    'name': instagram_username,
                    'bio': '',
                    'instagram_username': instagram_username
                }

            # Guardar en knowledge_about del creator
            with get_db_session() as db:
                creator = db.query(Creator).filter(
                    or_(
                        Creator.id == creator_id if len(str(creator_id)) > 20 else False,
                        Creator.name == creator_id
                    )
                ).first()

                if creator:
                    # Merge con datos existentes
                    existing_about = creator.knowledge_about or {}
                    existing_about.update(bio_data)
                    creator.knowledge_about = existing_about

                    # También actualizar clone_name si está vacío
                    if not creator.clone_name and bio_data.get('name'):
                        creator.clone_name = bio_data.get('name')

                    db.commit()
                    result['success'] = True
                    result['bio'] = bio_data
                    logger.info(f"[AutoConfig] Bio saved to knowledge_about for {creator_id}")

        except Exception as e:
            logger.error(f"[AutoConfig] Bio extraction error: {e}")

        return result

    async def _generate_faqs(self, creator_id: str) -> dict:
        """
        Genera FAQs automáticas basadas en el contenido scrapeado.

        IMPORTANTE: Si ya existen FAQs en KnowledgeBase (del V2 pipeline),
        NO genera nuevas para evitar duplicados/parafraseados.
        """
        result = {
            'faqs_created': 0,
            'source': []
        }

        try:
            from api.database import get_db_session
            from api.models import Creator, KnowledgeBase, Product, ContentChunk
            from sqlalchemy import or_

            faqs_to_create = []

            with get_db_session() as db:
                creator = db.query(Creator).filter(
                    or_(
                        Creator.id == creator_id if len(str(creator_id)) > 20 else False,
                        Creator.name == creator_id
                    )
                ).first()

                if not creator:
                    return result

                # SKIP if FAQs already exist from V2 pipeline (literal extraction)
                existing_faq_count = db.query(KnowledgeBase).filter(
                    KnowledgeBase.creator_id == creator.id
                ).count()

                if existing_faq_count >= 10:
                    logger.info(
                        f"[AutoConfig] Skipping FAQ generation - {existing_faq_count} FAQs already exist from V2 pipeline"
                    )
                    result['faqs_created'] = existing_faq_count
                    result['source'] = ['v2_pipeline_existing']
                    return result

                creator_uuid = creator.id

                # 1. Buscar FAQs ya extraídas del website (source_type='faq')
                existing_faqs = db.query(ContentChunk).filter(
                    ContentChunk.creator_id == str(creator_uuid),
                    ContentChunk.source_type == 'faq'
                ).all()

                for chunk in existing_faqs:
                    # El contenido debería tener formato "Q: ... A: ..."
                    content = chunk.content or ''
                    if 'Q:' in content or '?' in content:
                        parts = content.split('\n', 1)
                        if len(parts) >= 2:
                            question = parts[0].replace('Q:', '').strip()
                            answer = parts[1].replace('A:', '').strip()
                            if question and answer and len(answer) > 10:
                                faqs_to_create.append({
                                    'question': question if question.endswith('?') else f"{question}?",
                                    'answer': answer,
                                    'source': 'website'
                                })

                # 2. Generar FAQs basadas en productos
                products = db.query(Product).filter(
                    Product.creator_id == creator_uuid,
                    Product.is_active == True
                ).all()

                for product in products:
                    if product.price and product.name:
                        # FAQ sobre precio
                        faqs_to_create.append({
                            'question': f"¿Cuánto cuesta {product.name}?",
                            'answer': f"{product.name} tiene un precio de {product.price:.0f} {product.currency}. {product.description[:200] if product.description else ''}".strip(),
                            'source': 'products'
                        })

                        # FAQ sobre qué incluye
                        if product.description and len(product.description) > 50:
                            faqs_to_create.append({
                                'question': f"¿Qué incluye {product.name}?",
                                'answer': product.description[:500],
                                'source': 'products'
                            })

                # 3. Generar FAQs genéricas basadas en knowledge_about
                about = creator.knowledge_about or {}
                if about.get('bio'):
                    faqs_to_create.append({
                        'question': f"¿Quién es {about.get('name', creator.name)}?",
                        'answer': about.get('bio', ''),
                        'source': 'bio'
                    })

                # 4. Eliminar duplicados y guardar
                seen_questions = set()
                for faq in faqs_to_create:
                    question_key = faq['question'].lower()
                    if question_key in seen_questions:
                        continue
                    seen_questions.add(question_key)

                    # Verificar si ya existe
                    existing = db.query(KnowledgeBase).filter(
                        KnowledgeBase.creator_id == creator_uuid,
                        KnowledgeBase.question.ilike(f"%{faq['question'][:50]}%")
                    ).first()

                    if not existing:
                        new_faq = KnowledgeBase(
                            creator_id=creator_uuid,
                            question=faq['question'],
                            answer=faq['answer']
                        )
                        db.add(new_faq)
                        result['faqs_created'] += 1
                        if faq['source'] not in result['source']:
                            result['source'].append(faq['source'])

                db.commit()

            logger.info(f"[AutoConfig] Generated {result['faqs_created']} FAQs from sources: {result['source']}")

        except Exception as e:
            logger.error(f"[AutoConfig] FAQ generation error: {e}")
            import traceback
            traceback.print_exc()

        return result


async def auto_configure_clone(
    creator_id: str,
    instagram_username: str,
    website_url: Optional[str] = None,
    max_posts: int = 50,
    transcribe_videos: bool = True,
    db_session=None
) -> AutoConfigResult:
    """
    Función de conveniencia para ejecutar auto-configuración.

    Args:
        creator_id: ID/nombre del creator
        instagram_username: Username de Instagram
        website_url: URL del website (opcional)
        max_posts: Máximo posts a scrapear
        transcribe_videos: Si transcribir videos
        db_session: Sesión de DB (opcional)

    Returns:
        AutoConfigResult con estadísticas
    """
    configurator = AutoConfigurator(db_session)
    return await configurator.run(
        creator_id=creator_id,
        instagram_username=instagram_username,
        website_url=website_url,
        max_posts=max_posts,
        transcribe_videos=transcribe_videos
    )
