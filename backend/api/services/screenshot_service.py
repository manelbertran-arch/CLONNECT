"""
Screenshot Service - Captura screenshots de URLs con Playwright
Para generar previews de links compartidos (Instagram, YouTube, webs)

Fallback a Microlink API cuando Playwright no está disponible.
"""
import asyncio
import base64
import re
import httpx
from typing import Optional, Dict
from contextlib import asynccontextmanager

# Playwright import con fallback
try:
    from playwright.async_api import async_playwright, Browser, BrowserContext
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("INFO: Playwright not installed. Using Microlink API fallback.")

# Microlink API for fallback
MICROLINK_API = "https://api.microlink.io"


async def get_microlink_preview(url: str) -> Optional[Dict]:
    """
    Get preview using Microlink API (free tier: 50 req/day).
    Returns thumbnail_url and metadata.
    """
    if not url:
        return None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Microlink with screenshot option for better thumbnails
            response = await client.get(
                MICROLINK_API,
                params={
                    "url": url,
                    "screenshot": "true",  # Get screenshot if available
                    "meta": "true"
                }
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    result = data.get("data", {})

                    # Prefer screenshot, fallback to image
                    screenshot = result.get("screenshot", {})
                    image = result.get("image", {})

                    thumbnail_url = screenshot.get("url") or image.get("url")

                    if thumbnail_url:
                        return {
                            "thumbnail_url": thumbnail_url,
                            "title": result.get("title"),
                            "description": result.get("description"),
                            "author": result.get("author") or result.get("publisher"),
                            "url": url
                        }
    except Exception as e:
        print(f"Microlink preview error for {url}: {e}")

    return None


# URL patterns para detectar tipo de contenido
INSTAGRAM_POST_REGEX = re.compile(r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)')
INSTAGRAM_PROFILE_REGEX = re.compile(r'https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)/?$')
YOUTUBE_VIDEO_REGEX = re.compile(r'https?://(?:www\.|m\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]+)')
TIKTOK_VIDEO_REGEX = re.compile(r'https?://(?:www\.|vm\.)?tiktok\.com/')


class ScreenshotService:
    """Servicio para capturar screenshots de URLs usando Playwright"""

    @classmethod
    async def close(cls):
        """No-op for compatibility. Each capture manages its own browser."""
        pass

    @staticmethod
    async def capture(
        url: str,
        width: int = 400,
        height: int = 400,
        wait_for_selector: Optional[str] = None,
        timeout: int = 20000,
        mobile: bool = False,
        full_page: bool = False
    ) -> Optional[str]:
        """
        Captura screenshot de una URL y devuelve base64.
        Cada captura crea su propia instancia del browser (más estable).

        Args:
            url: URL a capturar
            width: Ancho del viewport
            height: Alto del viewport
            wait_for_selector: Selector CSS para esperar antes de capturar
            timeout: Timeout en ms
            mobile: Si usar viewport de móvil
            full_page: Si capturar toda la página

        Returns:
            Screenshot en base64 o None si falla
        """
        if not PLAYWRIGHT_AVAILABLE:
            print("Playwright not available, skipping screenshot")
            return None

        playwright = None
        browser = None
        context = None

        try:
            # Create new playwright instance for this capture
            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                ]
            )

            # Configurar contexto
            context_options = {
                "viewport": {"width": width, "height": height},
                "user_agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
                    "Mobile/15E148 Safari/604.1"
                ) if mobile else (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "locale": "es-ES",
                "timezone_id": "Europe/Madrid",
            }

            if mobile:
                context_options["is_mobile"] = True
                context_options["has_touch"] = True

            context = await browser.new_context(**context_options)
            page = await context.new_page()

            # Navegar a la URL
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            except Exception as e:
                print(f"Navigation error for {url}: {e}")
                # Intentar con timeout más largo
                await page.goto(url, wait_until="load", timeout=timeout * 1.5)

            # Esperar selector específico si se proporciona
            if wait_for_selector:
                try:
                    await page.wait_for_selector(wait_for_selector, timeout=5000)
                except:
                    pass  # Continuar aunque no encuentre el selector

            # Esperar un poco para contenido dinámico
            await asyncio.sleep(1.5)

            # Cerrar popups/cookies si existen
            for selector in ['[aria-label="Close"]', '[data-testid="cookie-close"]', '.cookie-banner button']:
                try:
                    await page.click(selector, timeout=1000)
                except:
                    pass

            # Capturar screenshot
            screenshot = await page.screenshot(
                type="jpeg",
                quality=80,
                full_page=full_page
            )

            return base64.b64encode(screenshot).decode()

        except Exception as e:
            print(f"Screenshot error for {url}: {e}")
            return None
        finally:
            # Clean up in reverse order
            if context:
                try:
                    await context.close()
                except:
                    pass
            if browser:
                try:
                    await browser.close()
                except:
                    pass
            if playwright:
                try:
                    await playwright.stop()
                except:
                    pass

    @staticmethod
    async def capture_instagram_post(url: str) -> Optional[Dict]:
        """
        Captura específica para posts/reels de Instagram.
        Intenta Playwright primero, fallback a Microlink API.
        Returns dict con thumbnail y metadata.
        """
        post_type = "shared_post" if "/p/" in url else "shared_reel"

        # Try Playwright first if available
        if PLAYWRIGHT_AVAILABLE:
            screenshot = await ScreenshotService.capture(
                url,
                width=400,
                height=500,
                mobile=True,
                wait_for_selector='article',
                timeout=25000
            )
            if screenshot:
                return {
                    "thumbnail_base64": screenshot,
                    "type": post_type,
                    "url": url,
                    "platform": "instagram"
                }

        # Fallback to Microlink API (free, no browser needed)
        microlink_result = await get_microlink_preview(url)
        if microlink_result and microlink_result.get("thumbnail_url"):
            return {
                "thumbnail_url": microlink_result["thumbnail_url"],
                "type": post_type,
                "url": url,
                "platform": "instagram",
                "title": microlink_result.get("title"),
                "author": microlink_result.get("author")
            }

        return None

    @staticmethod
    async def capture_youtube_video(url: str) -> Optional[Dict]:
        """
        Captura específica para videos de YouTube
        Returns dict con thumbnail_base64 y metadata
        """
        # Extraer video ID para usar thumbnail oficial de YouTube (más rápido)
        match = YOUTUBE_VIDEO_REGEX.search(url)
        if match:
            video_id = match.group(1)
            # YouTube provee thumbnails oficiales - usar maxresdefault
            thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
            return {
                "thumbnail_url": thumbnail_url,
                "type": "shared_video",
                "url": url,
                "platform": "youtube",
                "video_id": video_id
            }

        # Fallback a screenshot si no se puede extraer ID
        screenshot = await ScreenshotService.capture(
            url,
            width=640,
            height=360,
            wait_for_selector='#player',
            timeout=20000
        )

        if screenshot:
            return {
                "thumbnail_base64": screenshot,
                "type": "shared_video",
                "url": url,
                "platform": "youtube"
            }
        return None

    @staticmethod
    async def capture_generic(url: str) -> Optional[Dict]:
        """
        Captura genérica para cualquier URL.
        Intenta Playwright primero, fallback a Microlink API.
        """
        # Try Playwright first if available
        if PLAYWRIGHT_AVAILABLE:
            screenshot = await ScreenshotService.capture(
                url,
                width=600,
                height=400,
                timeout=15000
            )
            if screenshot:
                return {
                    "thumbnail_base64": screenshot,
                    "type": "link_preview",
                    "url": url,
                    "platform": "web"
                }

        # Fallback to Microlink API
        microlink_result = await get_microlink_preview(url)
        if microlink_result and microlink_result.get("thumbnail_url"):
            return {
                "thumbnail_url": microlink_result["thumbnail_url"],
                "type": "link_preview",
                "url": url,
                "platform": "web",
                "title": microlink_result.get("title"),
                "description": microlink_result.get("description")
            }

        return None

    @staticmethod
    async def get_preview(url: str) -> Optional[Dict]:
        """
        Auto-detecta el tipo de URL y captura el preview apropiado.
        Uses Playwright when available, otherwise Microlink API.
        """
        if not url:
            return None

        # Instagram post/reel
        if INSTAGRAM_POST_REGEX.search(url):
            return await ScreenshotService.capture_instagram_post(url)

        # YouTube video (uses official thumbnail API, no browser needed)
        if YOUTUBE_VIDEO_REGEX.search(url):
            return await ScreenshotService.capture_youtube_video(url)

        # TikTok (try Playwright, fallback to Microlink)
        if TIKTOK_VIDEO_REGEX.search(url):
            if PLAYWRIGHT_AVAILABLE:
                screenshot = await ScreenshotService.capture(
                    url, width=400, height=700, mobile=True
                )
                if screenshot:
                    return {
                        "thumbnail_base64": screenshot,
                        "type": "shared_video",
                        "url": url,
                        "platform": "tiktok"
                    }

            # Fallback to Microlink for TikTok
            microlink_result = await get_microlink_preview(url)
            if microlink_result and microlink_result.get("thumbnail_url"):
                return {
                    "thumbnail_url": microlink_result["thumbnail_url"],
                    "type": "shared_video",
                    "url": url,
                    "platform": "tiktok",
                    "title": microlink_result.get("title")
                }

        # URL genérica
        return await ScreenshotService.capture_generic(url)


# Instancia singleton
screenshot_service = ScreenshotService()


# Funciones helper para uso simple
async def get_screenshot(url: str) -> Optional[str]:
    """Obtiene screenshot base64 de una URL"""
    result = await screenshot_service.get_preview(url)
    return result.get("thumbnail_base64") if result else None


async def get_link_preview(url: str) -> Optional[Dict]:
    """Obtiene preview completo de una URL (auto-detecta tipo)"""
    return await screenshot_service.get_preview(url)


async def get_instagram_screenshot(url: str) -> Optional[str]:
    """Obtiene screenshot base64 de un post de Instagram"""
    result = await screenshot_service.capture_instagram_post(url)
    return result.get("thumbnail_base64") if result else None


def extract_urls(text: str) -> list[str]:
    """Extrae URLs de un texto"""
    url_pattern = re.compile(
        r'https?://[^\s<>"{}|\\^`\[\]]+'
    )
    return url_pattern.findall(text)


def detect_instagram_url(text: str) -> Optional[str]:
    """Detecta y extrae URL de Instagram de un texto"""
    match = INSTAGRAM_POST_REGEX.search(text)
    return match.group(0) if match else None


def detect_youtube_url(text: str) -> Optional[str]:
    """Detecta y extrae URL de YouTube de un texto"""
    match = YOUTUBE_VIDEO_REGEX.search(text)
    return match.group(0) if match else None
