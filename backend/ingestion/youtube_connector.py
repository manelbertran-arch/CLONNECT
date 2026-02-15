"""
YouTube Connector - Obtiene videos y transcripciones del canal del creador.

Soporta:
- Obtener videos de un canal
- Descargar subtitulos existentes
- Transcribir con Whisper si no hay subtitulos
- Extraer metadatos (titulo, descripcion, fecha)

Dependencias:
- yt-dlp (para descargar)
- youtube-transcript-api (para subtitulos)
"""

import asyncio
import logging
import re
import tempfile
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class YouTubeVideo:
    """Metadatos de un video de YouTube."""
    video_id: str
    title: str
    description: str
    channel_id: str
    channel_name: str
    published_at: str
    duration_seconds: int
    view_count: int = 0
    like_count: int = 0
    thumbnail_url: str = ""

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    def to_dict(self) -> Dict:
        return {
            "video_id": self.video_id,
            "title": self.title,
            "description": self.description,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "published_at": self.published_at,
            "duration_seconds": self.duration_seconds,
            "view_count": self.view_count,
            "like_count": self.like_count,
            "thumbnail_url": self.thumbnail_url,
            "url": self.url
        }


@dataclass
class YouTubeTranscript:
    """Transcripcion de un video de YouTube."""
    video_id: str
    video_title: str
    full_text: str
    segments: List[Dict] = field(default_factory=list)
    language: str = "es"
    is_auto_generated: bool = False
    source: str = "youtube_captions"  # youtube_captions o whisper

    def to_dict(self) -> Dict:
        return {
            "video_id": self.video_id,
            "video_title": self.video_title,
            "full_text": self.full_text,
            "segments": self.segments,
            "language": self.language,
            "is_auto_generated": self.is_auto_generated,
            "source": self.source
        }


class YouTubeConnector:
    """
    Conector para obtener videos y transcripciones de YouTube.

    Uso:
        connector = YouTubeConnector()
        videos = await connector.get_channel_videos("UC...")
        transcript = await connector.get_transcript("dQw4w9WgXcQ")
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Inicializa el conector.

        Args:
            api_key: YouTube Data API key (opcional, para metadatos extendidos)
        """
        import os
        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY")

    async def get_channel_videos(
        self,
        channel_id: Optional[str] = None,
        channel_url: Optional[str] = None,
        max_videos: int = 50
    ) -> List[YouTubeVideo]:
        """
        Obtiene videos de un canal.

        Args:
            channel_id: ID del canal (UC...)
            channel_url: URL del canal (alternativa a channel_id)
            max_videos: Maximo de videos a obtener

        Returns:
            Lista de YouTubeVideo
        """
        try:
            import yt_dlp
        except ImportError:
            raise ImportError("yt-dlp required. Install with: pip install yt-dlp")

        if channel_url:
            url = channel_url
        elif channel_id:
            url = f"https://www.youtube.com/channel/{channel_id}/videos"
        else:
            raise ValueError("Se requiere channel_id o channel_url")

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'playlistend': max_videos,
        }

        videos = []

        def extract_info():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)

        # Ejecutar en thread pool para no bloquear
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, extract_info)

        if not info:
            return videos

        entries = info.get('entries', [])

        for entry in entries[:max_videos]:
            if not entry:
                continue

            video = YouTubeVideo(
                video_id=entry.get('id', ''),
                title=entry.get('title', ''),
                description=entry.get('description', '') or '',
                channel_id=info.get('channel_id', '') or '',
                channel_name=info.get('channel', '') or '',
                published_at=entry.get('upload_date', '') or '',
                duration_seconds=entry.get('duration', 0) or 0,
                view_count=entry.get('view_count', 0) or 0,
                thumbnail_url=entry.get('thumbnail', '') or ''
            )
            videos.append(video)

        logger.info(f"Obtenidos {len(videos)} videos del canal")
        return videos

    async def get_transcript(
        self,
        video_id: str,
        languages: Optional[List[str]] = None,
        fallback_to_whisper: bool = True
    ) -> Optional[YouTubeTranscript]:
        """
        Obtiene transcripcion de un video.

        Intenta primero con subtitulos de YouTube, luego Whisper si no hay.

        Args:
            video_id: ID del video
            languages: Lista de idiomas preferidos (default: ["es", "en"])
            fallback_to_whisper: Si usar Whisper cuando no hay subtitulos

        Returns:
            YouTubeTranscript o None
        """
        languages = languages or ["es", "en"]

        # Primero intentar subtitulos de YouTube
        transcript = await self._get_youtube_captions(video_id, languages)

        if transcript:
            return transcript

        # Fallback a Whisper
        if fallback_to_whisper:
            logger.info(f"No hay subtitulos para {video_id}, usando Whisper...")
            return await self._transcribe_with_whisper(video_id)

        return None

    async def _get_youtube_captions(
        self,
        video_id: str,
        languages: List[str]
    ) -> Optional[YouTubeTranscript]:
        """Obtiene subtitulos de YouTube."""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
        except ImportError:
            logger.warning("youtube-transcript-api no instalado")
            return None

        try:
            # Intentar obtener transcripcion
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            # Buscar en idiomas preferidos
            transcript_data = None
            is_auto = False
            lang = ""

            for lang_code in languages:
                try:
                    transcript = transcript_list.find_transcript([lang_code])
                    transcript_data = transcript.fetch()
                    is_auto = transcript.is_generated
                    lang = lang_code
                    break
                except Exception:
                    continue

            if not transcript_data:
                # Intentar cualquier transcripcion disponible
                try:
                    transcript = transcript_list.find_generated_transcript(languages)
                    transcript_data = transcript.fetch()
                    is_auto = True
                    lang = transcript.language_code
                except Exception:
                    return None

            # Construir transcripcion
            segments = [
                {
                    "text": seg['text'],
                    "start": seg['start'],
                    "duration": seg['duration']
                }
                for seg in transcript_data
            ]

            full_text = " ".join(seg['text'] for seg in transcript_data)

            # Obtener titulo del video
            title = await self._get_video_title(video_id)

            return YouTubeTranscript(
                video_id=video_id,
                video_title=title,
                full_text=full_text,
                segments=segments,
                language=lang,
                is_auto_generated=is_auto,
                source="youtube_captions"
            )

        except Exception as e:
            logger.warning(f"Error obteniendo subtitulos de YouTube: {e}")
            return None

    async def _transcribe_with_whisper(self, video_id: str) -> Optional[YouTubeTranscript]:
        """Descarga audio y transcribe con Whisper."""
        try:
            import yt_dlp
            from .transcriber import get_transcriber
        except ImportError as e:
            logger.error(f"Dependencia faltante: {e}")
            return None

        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path = Path(tmp_dir) / "audio.mp3"

            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': str(audio_path).replace('.mp3', ''),
                'quiet': True,
            }

            try:
                # Descargar audio
                loop = asyncio.get_event_loop()

                def download():
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        return ydl.extract_info(
                            f"https://www.youtube.com/watch?v={video_id}",
                            download=True
                        )

                info = await loop.run_in_executor(None, download)
                title = info.get('title', '')

                # Buscar archivo descargado
                mp3_files = list(Path(tmp_dir).glob("*.mp3"))
                if not mp3_files:
                    logger.error("No se encontro archivo de audio descargado")
                    return None

                actual_audio_path = mp3_files[0]

                # Transcribir
                transcriber = get_transcriber()
                transcript = await transcriber.transcribe_file(str(actual_audio_path))

                return YouTubeTranscript(
                    video_id=video_id,
                    video_title=title,
                    full_text=transcript.full_text,
                    segments=[s.to_dict() for s in transcript.segments],
                    language=transcript.language,
                    is_auto_generated=False,
                    source="whisper"
                )

            except Exception as e:
                logger.error(f"Error transcribiendo video {video_id}: {e}")
                return None

    async def _get_video_title(self, video_id: str) -> str:
        """Obtiene titulo de un video."""
        try:
            import yt_dlp

            def get_info():
                with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                    return ydl.extract_info(
                        f"https://www.youtube.com/watch?v={video_id}",
                        download=False
                    )

            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(None, get_info)
            return info.get('title', '')
        except Exception:
            return ""

    @staticmethod
    def extract_video_id(url: str) -> Optional[str]:
        """Extrae video ID de una URL de YouTube."""
        patterns = [
            r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
            r'(?:embed/)([a-zA-Z0-9_-]{11})',
            r'^([a-zA-Z0-9_-]{11})$'
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None


# Singleton
_connector: Optional[YouTubeConnector] = None


def get_youtube_connector() -> YouTubeConnector:
    """Obtiene instancia singleton del conector."""
    global _connector
    if _connector is None:
        _connector = YouTubeConnector()
    return _connector
