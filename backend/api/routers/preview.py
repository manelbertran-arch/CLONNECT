"""Link Preview endpoints - Screenshot service for link previews"""
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
import logging

from api.services.screenshot_service import (
    ScreenshotService,
    get_link_preview,
    detect_instagram_url,
    detect_youtube_url,
    PLAYWRIGHT_AVAILABLE
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/preview", tags=["preview"])


@router.get("/status")
async def preview_status():
    """Check if screenshot service is available"""
    return {
        "playwright_available": PLAYWRIGHT_AVAILABLE,
        "service": "screenshot_service",
        "supported_platforms": ["instagram", "youtube", "tiktok", "web"]
    }


@router.get("/screenshot")
async def get_screenshot(
    url: str = Query(..., description="URL to capture screenshot from"),
    width: int = Query(400, ge=100, le=1920, description="Viewport width"),
    height: int = Query(400, ge=100, le=1080, description="Viewport height"),
    mobile: bool = Query(False, description="Use mobile viewport")
):
    """
    Capture a screenshot of any URL.
    Uses Playwright if available, otherwise Microlink API.

    - **url**: Full URL to capture (https://...)
    - **width**: Viewport width (100-1920) - only used with Playwright
    - **height**: Viewport height (100-1080) - only used with Playwright
    - **mobile**: Use mobile user agent and viewport - only used with Playwright

    Returns thumbnail_base64 (JPEG) or thumbnail_url (Microlink).
    """
    if not url.startswith(('http://', 'https://')):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    try:
        # Try Playwright first
        if PLAYWRIGHT_AVAILABLE:
            result = await ScreenshotService.capture(
                url=url,
                width=width,
                height=height,
                mobile=mobile
            )
            if result:
                return {
                    "success": True,
                    "url": url,
                    "thumbnail_base64": result,
                    "width": width,
                    "height": height
                }

        # Fallback to Microlink
        from api.services.screenshot_service import get_microlink_preview
        microlink_result = await get_microlink_preview(url)
        if microlink_result and microlink_result.get("thumbnail_url"):
            return {
                "success": True,
                "url": url,
                "thumbnail_url": microlink_result["thumbnail_url"],
                "title": microlink_result.get("title"),
                "source": "microlink"
            }

        return JSONResponse(
            status_code=500,
            content={"success": False, "error": "Failed to capture screenshot", "url": url}
            )
    except Exception as e:
        logger.error(f"Screenshot error for {url}: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e), "url": url}
        )


@router.get("/link")
async def get_link_preview_endpoint(
    url: str = Query(..., description="URL to get preview for")
):
    """
    Get a smart preview of a URL (auto-detects platform).

    Supports:
    - Instagram posts/reels
    - YouTube videos (uses official thumbnails)
    - TikTok videos
    - Any web page

    Returns metadata including thumbnail (base64 or URL).
    """
    if not url.startswith(('http://', 'https://')):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    try:
        result = await get_link_preview(url)

        if result:
            return {
                "success": True,
                **result
            }
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Failed to get preview", "url": url}
            )
    except Exception as e:
        logger.error(f"Link preview error for {url}: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e), "url": url}
        )


@router.get("/instagram")
async def get_instagram_preview(
    url: str = Query(..., description="Instagram post/reel URL")
):
    """
    Get preview of an Instagram post or reel.
    Uses Playwright if available, otherwise Microlink API.
    """
    # Validate Instagram URL
    if not detect_instagram_url(url):
        raise HTTPException(
            status_code=400,
            detail="Invalid Instagram URL. Expected format: instagram.com/p/... or instagram.com/reel/..."
        )

    try:
        # capture_instagram_post now uses Microlink as fallback
        result = await ScreenshotService.capture_instagram_post(url)

        if result:
            return {
                "success": True,
                **result
            }
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Failed to capture Instagram preview", "url": url}
            )
    except Exception as e:
        logger.error(f"Instagram preview error for {url}: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e), "url": url}
        )


@router.get("/youtube")
async def get_youtube_preview(
    url: str = Query(..., description="YouTube video URL")
):
    """
    Get preview of a YouTube video.

    Uses official YouTube thumbnail API (fast, no browser needed).
    """
    # Validate YouTube URL
    if not detect_youtube_url(url):
        raise HTTPException(
            status_code=400,
            detail="Invalid YouTube URL. Expected format: youtube.com/watch?v=... or youtu.be/..."
        )

    try:
        result = await ScreenshotService.capture_youtube_video(url)

        if result:
            return {
                "success": True,
                **result
            }
        else:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": "Failed to get YouTube preview", "url": url}
            )
    except Exception as e:
        logger.error(f"YouTube preview error for {url}: {e}")
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e), "url": url}
        )
