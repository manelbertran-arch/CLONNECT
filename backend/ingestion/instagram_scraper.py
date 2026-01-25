"""
Instagram Scraper - Obtiene posts y captions del creador.
Fase 1 - Magic Slice

Soporta 3 metodos:
1. Meta Graph API (oficial, requiere token de Business/Creator)
2. Instaloader (no oficial, puede ser bloqueado)
3. Manual JSON (el creador exporta y sube sus datos)
"""

import json
import logging
import os
import re
from typing import List, Dict, Optional, Literal
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pybreaker

logger = logging.getLogger(__name__)


# =============================================================================
# EXCEPTION CLASSES (defined first for circuit breaker configuration)
# =============================================================================

class InstagramScraperError(Exception):
    """Error base para el scraper."""
    pass


class RateLimitError(InstagramScraperError):
    """Error de rate limit."""
    pass


class AuthenticationError(InstagramScraperError):
    """Error de autenticacion."""
    pass


class CircuitBreakerOpenError(InstagramScraperError):
    """Raised when circuit breaker is open and rejecting requests."""
    pass


# =============================================================================
# CIRCUIT BREAKER CONFIGURATION
# =============================================================================
# Circuit breaker protects the system when external APIs are failing.
# After FAILURE_THRESHOLD consecutive failures, the circuit "opens" and
# rejects requests for RECOVERY_TIMEOUT seconds before testing again.

CIRCUIT_FAILURE_THRESHOLD = int(os.getenv("CIRCUIT_FAILURE_THRESHOLD", "5"))
CIRCUIT_RECOVERY_TIMEOUT = int(os.getenv("CIRCUIT_RECOVERY_TIMEOUT", "60"))


class CircuitBreakerListener(pybreaker.CircuitBreakerListener):
    """Listener to log circuit breaker state changes."""

    def __init__(self, name: str):
        self.name = name

    def state_change(self, cb, old_state, new_state):
        """Log when circuit state changes."""
        logger.warning(
            f"Circuit breaker [{self.name}] state changed: {old_state.name} -> {new_state.name}"
        )
        if new_state == pybreaker.STATE_OPEN:
            logger.error(
                f"Circuit [{self.name}] OPENED - Too many failures. "
                f"Requests will be rejected for {cb.reset_timeout} seconds."
            )
        elif new_state == pybreaker.STATE_HALF_OPEN:
            logger.info(
                f"Circuit [{self.name}] HALF-OPEN - Testing if service recovered."
            )
        elif new_state == pybreaker.STATE_CLOSED:
            logger.info(
                f"Circuit [{self.name}] CLOSED - Service recovered, normal operation resumed."
            )

    def failure(self, cb, exc):
        """Log failures tracked by circuit breaker."""
        logger.debug(
            f"Circuit [{self.name}] recorded failure ({cb.fail_counter}/{cb.fail_max}): {exc}"
        )

    def success(self, cb):
        """Log successful calls (resets failure count)."""
        if cb.fail_counter > 0:
            logger.debug(f"Circuit [{self.name}] recorded success, resetting failure counter")


# Circuit breaker for Instagram/Meta Graph API
instagram_circuit_breaker = pybreaker.CircuitBreaker(
    fail_max=CIRCUIT_FAILURE_THRESHOLD,
    reset_timeout=CIRCUIT_RECOVERY_TIMEOUT,
    exclude=[AuthenticationError],  # Don't count auth errors - they won't fix themselves
    listeners=[CircuitBreakerListener("instagram_api")],
    name="instagram_api"
)

# Circuit breaker for Instaloader
instaloader_circuit_breaker = pybreaker.CircuitBreaker(
    fail_max=CIRCUIT_FAILURE_THRESHOLD,
    reset_timeout=CIRCUIT_RECOVERY_TIMEOUT * 2,  # Longer recovery for Instaloader (stricter rate limits)
    exclude=[AuthenticationError],
    listeners=[CircuitBreakerListener("instaloader")],
    name="instaloader"
)


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class InstagramPost:
    """Representa un post de Instagram."""
    post_id: str
    post_type: Literal['image', 'video', 'carousel', 'reel']
    caption: str
    permalink: str
    timestamp: datetime
    likes_count: Optional[int] = None
    comments_count: Optional[int] = None
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    hashtags: List[str] = field(default_factory=list)
    mentions: List[str] = field(default_factory=list)

    @property
    def has_content(self) -> bool:
        """Verifica si el post tiene contenido util para indexar."""
        return bool(self.caption and len(self.caption.strip()) > 10)


# =============================================================================
# METODO 1: META GRAPH API (Oficial)
# =============================================================================

class MetaGraphAPIScraper:
    """
    Scraper usando Meta Graph API oficial.
    Requiere: Instagram Business/Creator Account + Facebook Page + Access Token

    Docs: https://developers.facebook.com/docs/instagram-api/
    """

    BASE_URL = "https://graph.instagram.com/v21.0"

    def __init__(self, access_token: str, instagram_business_id: str):
        """
        Args:
            access_token: Token de acceso de Meta (largo plazo preferido)
            instagram_business_id: ID de la cuenta de Instagram Business
        """
        self.access_token = access_token
        self.instagram_business_id = instagram_business_id

    async def get_posts(
        self,
        limit: int = 50,
        since: Optional[datetime] = None
    ) -> List[InstagramPost]:
        """
        Obtiene posts usando la Graph API.

        Args:
            limit: Numero maximo de posts
            since: Solo posts despues de esta fecha

        Returns:
            Lista de InstagramPost

        Raises:
            CircuitBreakerOpenError: If circuit is open due to too many failures
            RateLimitError: If API returns 429
            AuthenticationError: If token is invalid
        """
        try:
            # Circuit breaker wraps the actual API call
            data = await self._fetch_posts_with_circuit_breaker(limit)
        except pybreaker.CircuitBreakerError:
            raise CircuitBreakerOpenError(
                f"Circuit breaker OPEN for Instagram API. "
                f"Too many consecutive failures. Try again in {CIRCUIT_RECOVERY_TIMEOUT} seconds."
            )

        posts = []
        for item in data.get("data", []):
            post = self._parse_post(item)
            if post.has_content:
                if since and post.timestamp < since:
                    continue
                posts.append(post)

                if len(posts) >= limit:
                    break

        logger.info(f"Obtenidos {len(posts)} posts via Meta Graph API")
        return posts

    async def _fetch_posts_with_circuit_breaker(self, limit: int) -> Dict:
        """
        Fetch posts from Meta Graph API with circuit breaker protection.

        This method is wrapped by the circuit breaker to track failures
        and prevent cascading failures when the API is down.
        """
        import httpx

        # Use circuit breaker's call method for async functions
        return await instagram_circuit_breaker.call_async(
            self._fetch_media_page,
            limit
        )

    async def _fetch_media_page(self, limit: int) -> Dict:
        """
        Actual HTTP request to fetch media from Instagram API.

        Separated for circuit breaker wrapping.
        """
        import httpx

        url = f"{self.BASE_URL}/{self.instagram_business_id}/media"
        params = {
            "access_token": self.access_token,
            "fields": "id,caption,permalink,timestamp,media_type,like_count,comments_count,media_url,thumbnail_url",
            "limit": min(limit, 100)  # API max es 100 por request
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params)

                if response.status_code == 429:
                    raise RateLimitError("Meta API rate limit alcanzado")

                if response.status_code == 401:
                    raise AuthenticationError("Token de Meta invalido o expirado")

                if response.status_code >= 500:
                    # Server errors should trip the circuit breaker
                    raise InstagramScraperError(f"Server error {response.status_code}")

                if response.status_code >= 400:
                    # Client errors (except 429/401 handled above) - don't retry
                    raise InstagramScraperError(
                        f"Client error {response.status_code}: {response.text[:200]}"
                    )

                return response.json()

        except httpx.TimeoutException as e:
            raise InstagramScraperError(f"Timeout conectando a Meta API: {e}")
        except httpx.HTTPError as e:
            logger.error(f"Error HTTP en Meta Graph API: {e}")
            raise InstagramScraperError(f"Error de conexion: {e}")

    def _parse_post(self, data: Dict) -> InstagramPost:
        """Parsea respuesta de la API a InstagramPost."""
        caption = data.get("caption", "")

        return InstagramPost(
            post_id=data["id"],
            post_type=self._map_media_type(data.get("media_type", "IMAGE")),
            caption=caption,
            permalink=data.get("permalink", ""),
            timestamp=datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00")),
            likes_count=data.get("like_count"),
            comments_count=data.get("comments_count"),
            media_url=data.get("media_url"),
            thumbnail_url=data.get("thumbnail_url"),
            hashtags=self._extract_hashtags(caption),
            mentions=self._extract_mentions(caption)
        )

    @staticmethod
    def _map_media_type(media_type: str) -> str:
        mapping = {
            "IMAGE": "image",
            "VIDEO": "video",
            "CAROUSEL_ALBUM": "carousel",
            "REELS": "reel"
        }
        return mapping.get(media_type, "image")

    @staticmethod
    def _extract_hashtags(text: str) -> List[str]:
        return re.findall(r'#(\w+)', text) if text else []

    @staticmethod
    def _extract_mentions(text: str) -> List[str]:
        return re.findall(r'@(\w+)', text) if text else []


# =============================================================================
# METODO 2: INSTALOADER (No oficial)
# =============================================================================

class InstaloaderScraper:
    """
    Scraper usando Instaloader (no oficial).

    ADVERTENCIA: Puede ser bloqueado por Instagram.
    Usar con moderacion y con cuenta propia del creador.

    Docs: https://instaloader.github.io/
    """

    def __init__(self, username: Optional[str] = None, password: Optional[str] = None):
        """
        Args:
            username: Usuario de Instagram (opcional, mejora limites)
            password: Contrasena (opcional)
        """
        self.username = username
        self.password = password
        self._loader = None

    def _get_loader(self):
        """Inicializa Instaloader de forma lazy con configuración anti-rate-limit."""
        if self._loader is None:
            try:
                import instaloader
                self._loader = instaloader.Instaloader(
                    download_pictures=False,
                    download_videos=False,
                    download_video_thumbnails=False,
                    download_geotags=False,
                    download_comments=False,
                    save_metadata=False,
                    compress_json=False,
                    max_connection_attempts=3,
                    request_timeout=30,
                    quiet=True  # Less verbose output
                )

                # Set slower rate to avoid rate limits
                self._loader.context.sleep = True
                self._loader.context.max_connection_attempts = 3

                if self.username and self.password:
                    try:
                        self._loader.login(self.username, self.password)
                        logger.info(f"Logged in as {self.username}")
                    except Exception as e:
                        logger.warning(f"Login failed: {e}. Continuing without auth.")

            except ImportError:
                raise InstagramScraperError(
                    "Instaloader no instalado. Ejecuta: pip install instaloader"
                )

        return self._loader

    def get_posts(
        self,
        target_username: str,
        limit: int = 50,
        since: Optional[datetime] = None,
        delay_between_posts: float = 1.5
    ) -> List[InstagramPost]:
        """
        Obtiene posts de un perfil usando Instaloader.

        Args:
            target_username: Username del creador a scrapear
            limit: Numero maximo de posts
            since: Solo posts despues de esta fecha
            delay_between_posts: Segundos a esperar entre cada post (anti-rate-limit)

        Returns:
            Lista de InstagramPost

        Raises:
            CircuitBreakerOpenError: If circuit is open due to too many failures
            RateLimitError: If Instagram rate limit hit
        """
        try:
            # Circuit breaker wraps the profile fetch
            return instaloader_circuit_breaker.call(
                self._fetch_posts_internal,
                target_username,
                limit,
                since,
                delay_between_posts
            )
        except pybreaker.CircuitBreakerError:
            raise CircuitBreakerOpenError(
                f"Circuit breaker OPEN for Instaloader. "
                f"Too many consecutive failures. Try again in {CIRCUIT_RECOVERY_TIMEOUT * 2} seconds."
            )

    def _fetch_posts_internal(
        self,
        target_username: str,
        limit: int,
        since: Optional[datetime],
        delay_between_posts: float
    ) -> List[InstagramPost]:
        """
        Internal method to fetch posts - wrapped by circuit breaker.
        """
        import instaloader
        import time
        import random

        loader = self._get_loader()
        posts = []

        try:
            # Initial delay before fetching profile
            time.sleep(random.uniform(1.0, 2.0))

            profile = instaloader.Profile.from_username(loader.context, target_username)
            logger.info(f"Fetching posts from @{target_username} (limit={limit})")

            for post in profile.get_posts():
                if len(posts) >= limit:
                    break

                if since and post.date_utc < since:
                    break  # Posts estan ordenados por fecha desc

                caption = post.caption or ""

                ig_post = InstagramPost(
                    post_id=post.shortcode,
                    post_type=self._get_post_type(post),
                    caption=caption,
                    permalink=f"https://instagram.com/p/{post.shortcode}/",
                    timestamp=post.date_utc,
                    likes_count=post.likes,
                    comments_count=post.comments,
                    media_url=post.url,
                    thumbnail_url=post.url if post.is_video else None,
                    hashtags=list(post.caption_hashtags) if post.caption_hashtags else [],
                    mentions=list(post.caption_mentions) if post.caption_mentions else []
                )

                if ig_post.has_content:
                    posts.append(ig_post)
                    # Add delay between posts to avoid rate limiting
                    if len(posts) < limit:
                        time.sleep(random.uniform(delay_between_posts * 0.8, delay_between_posts * 1.2))

            logger.info(f"Obtenidos {len(posts)} posts via Instaloader")
            return posts

        except instaloader.exceptions.ProfileNotExistsException:
            raise InstagramScraperError(f"Perfil '{target_username}' no existe")
        except instaloader.exceptions.ConnectionException as e:
            if "429" in str(e) or "401" in str(e) or "wait" in str(e).lower():
                raise RateLimitError("Instagram rate limit. Espera unos minutos.")
            raise InstagramScraperError(f"Error de conexion: {e}")
        except Exception as e:
            logger.error(f"Error en Instaloader: {e}")
            raise InstagramScraperError(f"Error obteniendo posts: {e}")

    @staticmethod
    def _get_post_type(post) -> str:
        if post.typename == "GraphReel":
            return "reel"
        elif post.is_video:
            return "video"
        elif post.typename == "GraphSidecar":
            return "carousel"
        return "image"


# =============================================================================
# METODO 3: MANUAL JSON (El creador sube sus datos)
# =============================================================================

class ManualJSONScraper:
    """
    Procesa datos exportados manualmente por el creador.

    El creador puede:
    1. Exportar datos desde Instagram (Settings > Your Activity > Download Your Information)
    2. Subir el JSON resultante
    3. Este scraper lo procesa

    Esto es el metodo mas confiable y no tiene riesgo de bloqueo.
    """

    def parse_instagram_export(self, json_path: str) -> List[InstagramPost]:
        """
        Parsea el archivo JSON de exportacion de Instagram.

        Args:
            json_path: Ruta al archivo JSON exportado

        Returns:
            Lista de InstagramPost
        """
        path = Path(json_path)
        if not path.exists():
            raise InstagramScraperError(f"Archivo no encontrado: {json_path}")

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise InstagramScraperError(f"JSON invalido: {e}")

        posts = []

        # Instagram export tiene varias estructuras posibles
        media_items = (
            data.get("media", []) or
            data.get("posts", []) or
            data.get("content", {}).get("posts", [])
        )

        for item in media_items:
            post = self._parse_export_item(item)
            if post and post.has_content:
                posts.append(post)

        logger.info(f"Parseados {len(posts)} posts desde exportacion manual")
        return posts

    def parse_simple_json(self, json_data: List[Dict]) -> List[InstagramPost]:
        """
        Parsea un JSON simple con estructura basica.

        Formato esperado:
        [
            {
                "id": "abc123",
                "caption": "Texto del post...",
                "timestamp": "2024-01-15T10:30:00",
                "type": "image",
                "url": "https://instagram.com/p/abc123/"
            },
            ...
        ]
        """
        posts = []

        for item in json_data:
            try:
                caption = item.get("caption", "")
                post = InstagramPost(
                    post_id=item.get("id", str(hash(caption))[:10]),
                    post_type=item.get("type", "image"),
                    caption=caption,
                    permalink=item.get("url", ""),
                    timestamp=datetime.fromisoformat(item.get("timestamp", datetime.now().isoformat())),
                    likes_count=item.get("likes"),
                    comments_count=item.get("comments"),
                    hashtags=self._extract_hashtags(caption),
                    mentions=self._extract_mentions(caption)
                )

                if post.has_content:
                    posts.append(post)

            except Exception as e:
                logger.warning(f"Error parseando item: {e}")
                continue

        return posts

    def _parse_export_item(self, item: Dict) -> Optional[InstagramPost]:
        """Parsea un item del export oficial de Instagram."""
        try:
            # El formato de Instagram export varia, intentamos varios
            caption = (
                item.get("caption", "") or
                item.get("title", "") or
                item.get("media", [{}])[0].get("title", "") if item.get("media") else ""
            )

            timestamp_str = (
                item.get("creation_timestamp") or
                item.get("taken_at_timestamp") or
                item.get("timestamp")
            )

            if isinstance(timestamp_str, (int, float)):
                timestamp = datetime.fromtimestamp(timestamp_str)
            elif isinstance(timestamp_str, str):
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            else:
                timestamp = datetime.now()

            return InstagramPost(
                post_id=str(item.get("id", hash(caption)))[:20],
                post_type=self._guess_type(item),
                caption=caption,
                permalink=item.get("permalink", ""),
                timestamp=timestamp,
                hashtags=self._extract_hashtags(caption),
                mentions=self._extract_mentions(caption)
            )

        except Exception as e:
            logger.warning(f"Error parseando export item: {e}")
            return None

    @staticmethod
    def _guess_type(item: Dict) -> str:
        if "video" in str(item).lower():
            return "video"
        if "reel" in str(item).lower():
            return "reel"
        if "carousel" in str(item).lower() or "sidecar" in str(item).lower():
            return "carousel"
        return "image"

    @staticmethod
    def _extract_hashtags(text: str) -> List[str]:
        return re.findall(r'#(\w+)', text) if text else []

    @staticmethod
    def _extract_mentions(text: str) -> List[str]:
        return re.findall(r'@(\w+)', text) if text else []


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_instagram_scraper(
    method: Literal['meta_api', 'instaloader', 'manual'] = 'manual',
    **kwargs
):
    """
    Factory para obtener el scraper apropiado.

    Args:
        method: Metodo a usar
        **kwargs: Argumentos especificos del metodo

    Returns:
        Instancia del scraper

    Examples:
        # Meta Graph API
        scraper = get_instagram_scraper(
            'meta_api',
            access_token='xxx',
            instagram_business_id='123'
        )

        # Instaloader
        scraper = get_instagram_scraper(
            'instaloader',
            username='mi_cuenta',
            password='xxx'
        )

        # Manual
        scraper = get_instagram_scraper('manual')
    """
    if method == 'meta_api':
        return MetaGraphAPIScraper(
            access_token=kwargs['access_token'],
            instagram_business_id=kwargs['instagram_business_id']
        )
    elif method == 'instaloader':
        return InstaloaderScraper(
            username=kwargs.get('username'),
            password=kwargs.get('password')
        )
    elif method == 'manual':
        return ManualJSONScraper()
    else:
        raise ValueError(f"Metodo desconocido: {method}")
