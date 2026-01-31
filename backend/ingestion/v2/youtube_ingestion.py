"""
YouTube Ingestion V2 - Transcripts + RAG Chunks

Soporta:
1. Obtener videos de un canal (yt-dlp)
2. Obtener transcripts (YouTube API o Whisper fallback)
3. Crear content chunks para RAG
4. Persistencia en PostgreSQL

NO extrae productos - solo contenido RAG.
"""

import logging
import hashlib
from typing import List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class YouTubeIngestionResult:
    """Resultado completo de ingestion de YouTube."""
    success: bool
    creator_id: str
    channel_url: str

    # Scraping
    videos_found: int = 0
    videos_with_transcript: int = 0
    videos_without_transcript: int = 0

    # Persistence
    rag_chunks_created: int = 0

    # Errors
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "creator_id": self.creator_id,
            "channel_url": self.channel_url,
            "videos_found": self.videos_found,
            "videos_with_transcript": self.videos_with_transcript,
            "videos_without_transcript": self.videos_without_transcript,
            "rag_chunks_created": self.rag_chunks_created,
            "errors": self.errors
        }


class YouTubeIngestionPipeline:
    """
    Pipeline de ingestion para YouTube.

    Flujo:
    1. Obtener videos del canal
    2. Para cada video, obtener transcript
    3. Crear content chunks
    4. Guardar en PostgreSQL
    """

    def __init__(self, max_videos: int = 20, fallback_to_whisper: bool = True):
        """
        Inicializa el pipeline.

        Args:
            max_videos: Máximo de videos a procesar
            fallback_to_whisper: Usar Whisper si no hay subtítulos
        """
        self.max_videos = max_videos
        self.fallback_to_whisper = fallback_to_whisper

    async def run(
        self,
        creator_id: str,
        channel_url: str,
        clean_before: bool = True
    ) -> YouTubeIngestionResult:
        """
        Ejecuta el pipeline completo.

        Args:
            creator_id: ID del creator
            channel_url: URL del canal de YouTube
            clean_before: Limpiar datos anteriores

        Returns:
            YouTubeIngestionResult
        """
        result = YouTubeIngestionResult(
            success=False,
            creator_id=creator_id,
            channel_url=channel_url
        )

        try:
            # Step 1: Clean if needed
            if clean_before:
                await self._clean_previous_data(creator_id)

            # Step 2: Get videos
            logger.info(f"[YouTube] Getting videos from {channel_url}")
            videos = await self._get_channel_videos(channel_url)
            result.videos_found = len(videos)

            if not videos:
                result.errors.append("No videos found in channel")
                return result

            logger.info(f"[YouTube] Found {len(videos)} videos")

            # Step 3: Get transcripts
            transcripts = []
            for video in videos:
                transcript = await self._get_transcript(video)
                if transcript:
                    transcripts.append({
                        'video': video,
                        'transcript': transcript
                    })
                    result.videos_with_transcript += 1
                else:
                    result.videos_without_transcript += 1

            logger.info(
                f"[YouTube] Got transcripts for {result.videos_with_transcript}/{len(videos)} videos"
            )

            if not transcripts:
                result.errors.append("No transcripts obtained")
                return result

            # Step 4: Create chunks
            chunks = self._create_content_chunks(creator_id, transcripts)
            logger.info(f"[YouTube] Created {len(chunks)} content chunks")

            # Step 5: Save to DB
            saved = await self._save_chunks_to_db(creator_id, chunks)
            result.rag_chunks_created = saved

            result.success = True
            logger.info(
                f"[YouTube] Ingestion complete: {result.videos_with_transcript} videos, "
                f"{result.rag_chunks_created} chunks saved"
            )

        except Exception as e:
            logger.error(f"[YouTube] Ingestion error: {e}")
            import traceback
            traceback.print_exc()
            result.errors.append(str(e))

        return result

    async def _clean_previous_data(self, creator_id: str) -> int:
        """Limpia datos anteriores de YouTube para el creator."""
        try:
            from core.tone_profile_db import delete_content_chunks_db

            # Delete only youtube chunks
            deleted = await delete_content_chunks_db(
                creator_id,
                source_type='youtube'
            )
            logger.info(f"[YouTube] Deleted {deleted} previous YouTube chunks")
            return deleted

        except Exception as e:
            logger.warning(f"[YouTube] Could not clean previous data: {e}")
            return 0

    async def _get_channel_videos(self, channel_url: str) -> List:
        """Obtiene videos del canal."""
        try:
            from ingestion.youtube_connector import get_youtube_connector

            connector = get_youtube_connector()
            videos = await connector.get_channel_videos(
                channel_url=channel_url,
                max_videos=self.max_videos
            )
            return videos

        except Exception as e:
            logger.error(f"[YouTube] Error getting videos: {e}")
            return []

    async def _get_transcript(self, video) -> Optional[dict]:
        """Obtiene transcript de un video."""
        try:
            from ingestion.youtube_connector import get_youtube_connector

            connector = get_youtube_connector()
            transcript = await connector.get_transcript(
                video.video_id,
                fallback_to_whisper=self.fallback_to_whisper
            )

            if transcript:
                return transcript.to_dict()
            return None

        except Exception as e:
            logger.warning(f"[YouTube] Error getting transcript for {video.video_id}: {e}")
            return None

    def _create_content_chunks(
        self,
        creator_id: str,
        transcripts: List[dict]
    ) -> List[dict]:
        """
        Crea content chunks para RAG desde transcripts.

        Cada video se divide en chunks de ~500 palabras con overlap.
        """
        chunks = []
        chunk_size = 500  # palabras
        overlap = 50  # palabras de overlap

        for item in transcripts:
            video = item['video']
            transcript = item['transcript']

            full_text = transcript.get('full_text', '')
            if not full_text:
                continue

            # Dividir en palabras
            words = full_text.split()
            total_words = len(words)

            if total_words <= chunk_size:
                # Un solo chunk
                chunk_id = hashlib.sha256(
                    f"{creator_id}:{video.video_id}:0".encode()
                ).hexdigest()[:32]

                chunks.append({
                    'id': chunk_id,
                    'chunk_id': chunk_id,
                    'creator_id': creator_id,
                    'content': full_text,
                    'source_type': 'youtube',
                    'source_id': video.video_id,
                    'source_url': video.url,
                    'title': video.title[:100] if video.title else '',
                    'chunk_index': 0,
                    'total_chunks': 1,
                    'metadata': {
                        'video_id': video.video_id,
                        'channel_name': video.channel_name,
                        'duration_seconds': video.duration_seconds,
                        'view_count': video.view_count,
                        'published_at': video.published_at,
                        'transcript_source': transcript.get('source', 'unknown'),
                        'is_auto_generated': transcript.get('is_auto_generated', False)
                    }
                })
            else:
                # Múltiples chunks con overlap
                chunk_index = 0
                start = 0
                total_chunks = (total_words // (chunk_size - overlap)) + 1

                while start < total_words:
                    end = min(start + chunk_size, total_words)
                    chunk_words = words[start:end]
                    chunk_text = ' '.join(chunk_words)

                    chunk_id = hashlib.sha256(
                        f"{creator_id}:{video.video_id}:{chunk_index}".encode()
                    ).hexdigest()[:32]

                    chunks.append({
                        'id': chunk_id,
                        'chunk_id': chunk_id,
                        'creator_id': creator_id,
                        'content': chunk_text,
                        'source_type': 'youtube',
                        'source_id': video.video_id,
                        'source_url': video.url,
                        'title': f"{video.title[:80]} (part {chunk_index + 1})" if video.title else '',
                        'chunk_index': chunk_index,
                        'total_chunks': total_chunks,
                        'metadata': {
                            'video_id': video.video_id,
                            'channel_name': video.channel_name,
                            'duration_seconds': video.duration_seconds,
                            'view_count': video.view_count,
                            'published_at': video.published_at,
                            'transcript_source': transcript.get('source', 'unknown'),
                            'is_auto_generated': transcript.get('is_auto_generated', False)
                        }
                    })

                    chunk_index += 1
                    start = end - overlap

        return chunks

    async def _save_chunks_to_db(self, creator_id: str, chunks: List[dict]) -> int:
        """Guarda content chunks en PostgreSQL."""
        try:
            from core.tone_profile_db import save_content_chunks_db

            saved = await save_content_chunks_db(creator_id, chunks)
            return saved

        except Exception as e:
            logger.error(f"[YouTube] Error saving chunks: {e}")
            return 0


async def ingest_youtube_v2(
    creator_id: str,
    channel_url: str,
    max_videos: int = 20,
    clean_before: bool = True,
    fallback_to_whisper: bool = True
) -> YouTubeIngestionResult:
    """
    Función de conveniencia para ejecutar ingestion YouTube V2.

    Args:
        creator_id: ID del creator
        channel_url: URL del canal de YouTube
        max_videos: Máximo de videos a procesar
        clean_before: Limpiar datos antes
        fallback_to_whisper: Usar Whisper si no hay subtítulos

    Returns:
        YouTubeIngestionResult
    """
    pipeline = YouTubeIngestionPipeline(
        max_videos=max_videos,
        fallback_to_whisper=fallback_to_whisper
    )

    return await pipeline.run(
        creator_id=creator_id,
        channel_url=channel_url,
        clean_before=clean_before
    )
