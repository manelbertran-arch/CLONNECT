"""Link Preview Service - Obtiene thumbnails de posts/reels compartidos"""
import logging
import httpx
import asyncio
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class LinkPreviewService:
    """Servicio para obtener previews de links usando Microlink API"""

    MICROLINK_API = "https://api.microlink.io"

    @staticmethod
    async def get_preview(url: str) -> Optional[Dict]:
        """
        Obtiene preview de un link (thumbnail, título, descripción)
        Microlink es gratis hasta 50 req/día, suficiente para imports
        """
        if not url:
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    LinkPreviewService.MICROLINK_API,
                    params={"url": url}
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "success":
                        result = data.get("data", {})
                        return {
                            "title": result.get("title"),
                            "description": result.get("description"),
                            "image": result.get("image", {}).get("url"),
                            "logo": result.get("logo", {}).get("url"),
                            "publisher": result.get("publisher"),
                            "url": result.get("url")
                        }
        except Exception as e:
            logger.warning("Link preview error for %s: %s", url, e)

        return None

    @staticmethod
    async def get_instagram_post_preview(url: str) -> Optional[Dict]:
        """Preview específico para posts de Instagram"""
        preview = await LinkPreviewService.get_preview(url)
        if preview:
            return {
                "thumbnail_url": preview.get("image"),
                "title": preview.get("title"),
                "author": preview.get("publisher", "Instagram"),
                "permalink": url
            }
        return None


# Singleton
_preview_service = LinkPreviewService()

async def get_link_preview(url: str) -> Optional[Dict]:
    return await _preview_service.get_preview(url)

async def get_instagram_preview(url: str) -> Optional[Dict]:
    return await _preview_service.get_instagram_post_preview(url)
