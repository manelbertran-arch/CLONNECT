"""
Podcast Connector - Importa episodios desde RSS feeds.

Soporta:
- Parsear RSS/Atom feeds de podcasts
- Obtener metadatos de shows y episodios
- Descargar audio de episodios
- Transcribir con Whisper

Dependencias:
- feedparser (para RSS)
- httpx (para descargas)
"""

import asyncio
import logging
import tempfile
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PodcastShow:
    """Metadatos de un podcast."""
    feed_url: str
    title: str
    description: str = ""
    author: str = ""
    image_url: str = ""
    website: str = ""
    language: str = "es"
    categories: List[str] = field(default_factory=list)
    episode_count: int = 0

    @property
    def show_id(self) -> str:
        """Genera ID unico basado en feed URL."""
        return hashlib.md5(self.feed_url.encode()).hexdigest()[:12]

    def to_dict(self) -> Dict:
        return {
            "feed_url": self.feed_url,
            "show_id": self.show_id,
            "title": self.title,
            "description": self.description,
            "author": self.author,
            "image_url": self.image_url,
            "website": self.website,
            "language": self.language,
            "categories": self.categories,
            "episode_count": self.episode_count
        }


@dataclass
class PodcastEpisode:
    """Metadatos de un episodio de podcast."""
    episode_id: str
    title: str
    description: str
    audio_url: str
    published_at: str
    duration_seconds: int = 0
    show_title: str = ""
    show_id: str = ""
    episode_number: Optional[int] = None
    season_number: Optional[int] = None

    @property
    def url(self) -> str:
        return self.audio_url

    def to_dict(self) -> Dict:
        return {
            "episode_id": self.episode_id,
            "title": self.title,
            "description": self.description,
            "audio_url": self.audio_url,
            "published_at": self.published_at,
            "duration_seconds": self.duration_seconds,
            "show_title": self.show_title,
            "show_id": self.show_id,
            "episode_number": self.episode_number,
            "season_number": self.season_number
        }


@dataclass
class PodcastTranscript:
    """Transcripcion de un episodio de podcast."""
    episode_id: str
    episode_title: str
    full_text: str
    segments: List[Dict] = field(default_factory=list)
    language: str = "es"
    source: str = "whisper"

    def to_dict(self) -> Dict:
        return {
            "episode_id": self.episode_id,
            "episode_title": self.episode_title,
            "full_text": self.full_text,
            "segments": self.segments,
            "language": self.language,
            "source": self.source
        }


class PodcastConnector:
    """
    Conector para obtener podcasts desde RSS feeds.

    Uso:
        connector = PodcastConnector()
        show = await connector.get_show_info("https://feed.example.com/podcast.rss")
        episodes = await connector.get_episodes("https://feed.example.com/podcast.rss")
        transcript = await connector.transcribe_episode(episode)
    """

    def __init__(self):
        """Inicializa el conector."""

    async def get_show_info(self, feed_url: str) -> Optional[PodcastShow]:
        """
        Obtiene informacion del podcast desde el feed RSS.

        Args:
            feed_url: URL del feed RSS/Atom

        Returns:
            PodcastShow o None si falla
        """
        try:
            import feedparser
        except ImportError:
            raise ImportError("feedparser required. Install with: pip install feedparser")

        try:
            # Parsear feed (feedparser es sincrono)
            loop = asyncio.get_event_loop()
            feed = await loop.run_in_executor(None, feedparser.parse, feed_url)

            if feed.bozo and not feed.entries:
                logger.error(f"Error parsing feed {feed_url}: {feed.bozo_exception}")
                return None

            # Extraer metadatos del show
            channel = feed.feed

            # Categorias (iTunes)
            categories = []
            if hasattr(channel, 'itunes_category'):
                if isinstance(channel.itunes_category, list):
                    categories = [c.get('text', '') for c in channel.itunes_category if c.get('text')]
                elif hasattr(channel.itunes_category, 'text'):
                    categories = [channel.itunes_category.text]

            show = PodcastShow(
                feed_url=feed_url,
                title=channel.get('title', ''),
                description=channel.get('description', '') or channel.get('subtitle', ''),
                author=channel.get('author', '') or channel.get('itunes_author', ''),
                image_url=self._get_image_url(channel),
                website=channel.get('link', ''),
                language=channel.get('language', 'es')[:2],
                categories=categories,
                episode_count=len(feed.entries)
            )

            logger.info(f"Parsed show: {show.title} with {show.episode_count} episodes")
            return show

        except Exception as e:
            logger.error(f"Error getting show info from {feed_url}: {e}")
            return None

    async def get_episodes(
        self,
        feed_url: str,
        max_episodes: int = 50,
        since_date: Optional[datetime] = None
    ) -> List[PodcastEpisode]:
        """
        Obtiene episodios de un feed RSS.

        Args:
            feed_url: URL del feed RSS/Atom
            max_episodes: Maximo de episodios a obtener
            since_date: Solo episodios despues de esta fecha

        Returns:
            Lista de PodcastEpisode
        """
        try:
            import feedparser
        except ImportError:
            raise ImportError("feedparser required. Install with: pip install feedparser")

        try:
            loop = asyncio.get_event_loop()
            feed = await loop.run_in_executor(None, feedparser.parse, feed_url)

            if feed.bozo and not feed.entries:
                logger.error(f"Error parsing feed: {feed.bozo_exception}")
                return []

            show_title = feed.feed.get('title', '')
            show_id = hashlib.md5(feed_url.encode()).hexdigest()[:12]

            episodes = []

            for entry in feed.entries[:max_episodes]:
                # Buscar URL de audio
                audio_url = self._get_audio_url(entry)
                if not audio_url:
                    continue

                # Parsear fecha
                published = self._parse_date(entry)
                if since_date and published:
                    pub_dt = datetime.fromisoformat(published.replace('Z', '+00:00')) \
                        if isinstance(published, str) else published
                    if isinstance(pub_dt, datetime) and pub_dt < since_date:
                        continue

                # Generar ID del episodio
                episode_id = entry.get('id', '') or hashlib.md5(
                    (entry.get('title', '') + audio_url).encode()
                ).hexdigest()[:12]

                # Duracion (iTunes o enclosure)
                duration = self._parse_duration(entry)

                episode = PodcastEpisode(
                    episode_id=episode_id,
                    title=entry.get('title', ''),
                    description=entry.get('summary', '') or entry.get('description', ''),
                    audio_url=audio_url,
                    published_at=published or '',
                    duration_seconds=duration,
                    show_title=show_title,
                    show_id=show_id,
                    episode_number=self._get_episode_number(entry),
                    season_number=self._get_season_number(entry)
                )
                episodes.append(episode)

            logger.info(f"Fetched {len(episodes)} episodes from {feed_url}")
            return episodes

        except Exception as e:
            logger.error(f"Error getting episodes from {feed_url}: {e}")
            return []

    async def transcribe_episode(
        self,
        episode: PodcastEpisode,
        language: str = "es"
    ) -> Optional[PodcastTranscript]:
        """
        Descarga y transcribe un episodio de podcast.

        Args:
            episode: Episodio a transcribir
            language: Codigo de idioma

        Returns:
            PodcastTranscript o None si falla
        """
        try:
            import httpx
            from .transcriber import get_transcriber
        except ImportError as e:
            logger.error(f"Missing dependency: {e}")
            return None

        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                # Determinar extension del audio
                audio_url = episode.audio_url
                ext = self._get_audio_extension(audio_url)
                audio_path = Path(tmp_dir) / f"episode.{ext}"

                # Descargar audio
                logger.info(f"Downloading episode: {episode.title}")

                async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
                    response = await client.get(audio_url)
                    response.raise_for_status()

                    with open(audio_path, 'wb') as f:
                        f.write(response.content)

                logger.info(f"Downloaded {audio_path.stat().st_size / (1024*1024):.1f}MB")

                # Transcribir
                transcriber = get_transcriber()
                transcript = await transcriber.transcribe_file(
                    str(audio_path),
                    language=language,
                    include_timestamps=True
                )

                return PodcastTranscript(
                    episode_id=episode.episode_id,
                    episode_title=episode.title,
                    full_text=transcript.full_text,
                    segments=[s.to_dict() for s in transcript.segments],
                    language=transcript.language,
                    source="whisper"
                )

            except Exception as e:
                logger.error(f"Error transcribing episode {episode.episode_id}: {e}")
                return None

    def _get_image_url(self, channel) -> str:
        """Extrae URL de imagen del canal."""
        # iTunes image
        if hasattr(channel, 'itunes_image') and channel.itunes_image:
            if isinstance(channel.itunes_image, dict):
                return channel.itunes_image.get('href', '')
            return str(channel.itunes_image)

        # Standard image
        if hasattr(channel, 'image') and channel.image:
            if isinstance(channel.image, dict):
                return channel.image.get('href', '') or channel.image.get('url', '')
            if hasattr(channel.image, 'href'):
                return channel.image.href

        return ""

    def _get_audio_url(self, entry) -> Optional[str]:
        """Extrae URL de audio de un entry."""
        # Buscar en enclosures
        if hasattr(entry, 'enclosures'):
            for enc in entry.enclosures:
                if enc.get('type', '').startswith('audio/'):
                    return enc.get('href') or enc.get('url')

        # Buscar en links
        if hasattr(entry, 'links'):
            for link in entry.links:
                if link.get('type', '').startswith('audio/'):
                    return link.get('href')
                if link.get('rel') == 'enclosure':
                    return link.get('href')

        # Media content
        if hasattr(entry, 'media_content'):
            for media in entry.media_content:
                if media.get('type', '').startswith('audio/'):
                    return media.get('url')

        return None

    def _parse_date(self, entry) -> Optional[str]:
        """Parsea fecha de publicacion."""
        # Intentar varios campos
        date_fields = ['published', 'updated', 'created']

        for field in date_fields:
            if hasattr(entry, f'{field}_parsed') and getattr(entry, f'{field}_parsed'):
                try:
                    from time import mktime
                    dt = datetime.fromtimestamp(mktime(getattr(entry, f'{field}_parsed')))
                    return dt.isoformat()
                except Exception as e:
                    logger.warning("Suppressed error in from time import mktime: %s", e)

            if hasattr(entry, field) and getattr(entry, field):
                return getattr(entry, field)

        return None

    def _parse_duration(self, entry) -> int:
        """Parsea duracion del episodio en segundos."""
        # iTunes duration
        duration_str = entry.get('itunes_duration', '')
        if duration_str:
            return self._duration_to_seconds(str(duration_str))

        # Enclosure length (bytes, no es duracion pero es algo)
        if hasattr(entry, 'enclosures') and entry.enclosures:
            # No hay duracion real disponible
            pass

        return 0

    def _duration_to_seconds(self, duration: str) -> int:
        """Convierte duracion HH:MM:SS a segundos."""
        try:
            # Puede venir como segundos directos
            if duration.isdigit():
                return int(duration)

            # Formato HH:MM:SS o MM:SS
            parts = duration.split(':')
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            else:
                return int(float(duration))
        except Exception:
            return 0

    def _get_episode_number(self, entry) -> Optional[int]:
        """Obtiene numero de episodio."""
        if hasattr(entry, 'itunes_episode'):
            try:
                return int(entry.itunes_episode)
            except (ValueError, TypeError) as e:
                logger.debug("Ignored (ValueError, TypeError) in return int(entry.itunes_episode): %s", e)
        return None

    def _get_season_number(self, entry) -> Optional[int]:
        """Obtiene numero de temporada."""
        if hasattr(entry, 'itunes_season'):
            try:
                return int(entry.itunes_season)
            except (ValueError, TypeError) as e:
                logger.debug("Ignored (ValueError, TypeError) in return int(entry.itunes_season): %s", e)
        return None

    def _get_audio_extension(self, url: str) -> str:
        """Determina extension de audio desde URL."""
        url_lower = url.lower()
        if '.mp3' in url_lower:
            return 'mp3'
        elif '.m4a' in url_lower:
            return 'm4a'
        elif '.ogg' in url_lower:
            return 'ogg'
        elif '.wav' in url_lower:
            return 'wav'
        else:
            return 'mp3'  # Default


# Singleton
_connector: Optional[PodcastConnector] = None


def get_podcast_connector() -> PodcastConnector:
    """Obtiene instancia singleton del conector."""
    global _connector
    if _connector is None:
        _connector = PodcastConnector()
    return _connector
