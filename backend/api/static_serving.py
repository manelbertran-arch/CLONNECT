"""
Static file serving for frontend SPA.
Extracted from main.py following TDD methodology.

NOTE: This must be registered AFTER all API routes are defined.
The catch-all route will match any path not already matched.
"""
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

# Static directory path
_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")


def register_static_routes(app: "FastAPI"):
    """
    Register static file routes on the FastAPI app.

    IMPORTANT: Call this AFTER all API routes are registered.
    The catch-all route for SPA must be last.
    """
    if not os.path.exists(_static_dir):
        logger.warning(f"Static directory not found: {_static_dir}")
        return

    # Mount assets directory for JS/CSS files
    _assets_dir = os.path.join(_static_dir, "assets")
    if os.path.exists(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="static_assets")
        logger.info(f"Mounted frontend assets from {_assets_dir}")

    @app.get("/clonnect-logo.png")
    async def serve_logo():
        logo_path = os.path.join(_static_dir, "clonnect-logo.png")
        if os.path.exists(logo_path):
            return FileResponse(logo_path)
        raise HTTPException(status_code=404)

    @app.get("/favicon.ico")
    async def serve_favicon():
        favicon_path = os.path.join(_static_dir, "favicon.ico")
        if os.path.exists(favicon_path):
            return FileResponse(favicon_path)
        raise HTTPException(status_code=404)

    @app.get("/placeholder.svg")
    async def serve_placeholder():
        placeholder_path = os.path.join(_static_dir, "placeholder.svg")
        if os.path.exists(placeholder_path):
            return FileResponse(placeholder_path, media_type="image/svg+xml")
        raise HTTPException(status_code=404)

    @app.get("/robots.txt")
    async def serve_robots():
        robots_path = os.path.join(_static_dir, "robots.txt")
        if os.path.exists(robots_path):
            return FileResponse(robots_path, media_type="text/plain")
        raise HTTPException(status_code=404)

    @app.get("/debug.html")
    async def serve_debug_page():
        debug_path = os.path.join(_static_dir, "debug.html")
        if os.path.exists(debug_path):
            return FileResponse(debug_path, media_type="text/html")
        raise HTTPException(status_code=404, detail="Debug page not found")

    @app.get("/debug/status")
    async def debug_status():
        """Comprehensive diagnostic endpoint"""
        static_files = []
        if os.path.exists(_static_dir):
            for f in os.listdir(_static_dir):
                fpath = os.path.join(_static_dir, f)
                static_files.append({
                    "name": f,
                    "size": os.path.getsize(fpath) if os.path.isfile(fpath) else 0,
                    "type": "file" if os.path.isfile(fpath) else "dir",
                })

        assets_dir = os.path.join(_static_dir, "assets")
        assets_files = []
        if os.path.exists(assets_dir):
            for f in os.listdir(assets_dir):
                fpath = os.path.join(assets_dir, f)
                assets_files.append({
                    "name": f,
                    "size": os.path.getsize(fpath) if os.path.isfile(fpath) else 0
                })

        index_path = os.path.join(_static_dir, "index.html")
        index_info = None
        if os.path.exists(index_path):
            with open(index_path, "r") as f:
                content = f.read()
                index_info = {
                    "exists": True,
                    "size": len(content),
                    "has_root_div": 'id="root"' in content,
                    "js_files": [
                        m.split('"')[0] for m in content.split('src="')
                        if ".js" in m.split('"')[0]
                    ][:5],
                    "css_files": [
                        m.split('"')[0] for m in content.split('href="')
                        if ".css" in m.split('"')[0]
                    ][:5],
                }

        db_status = "unknown"
        try:
            from api.services.db_service import db_service
            with db_service._get_session() as session:
                session.execute("SELECT 1")
                db_status = "connected"
        except Exception as e:
            db_status = f"error: {str(e)[:100]}"

        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "static_dir": _static_dir,
            "static_dir_exists": os.path.exists(_static_dir),
            "static_files": static_files,
            "assets_files": assets_files,
            "index_html": index_info,
            "database": db_status,
            "environment": {
                "RAILWAY_ENVIRONMENT": os.environ.get("RAILWAY_ENVIRONMENT", "not set"),
                "PYTHON_VERSION": os.environ.get("PYTHON_VERSION", "unknown"),
            },
        }

    # Catch-all route for frontend SPA - MUST BE LAST
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve frontend for all non-API routes (SPA catch-all)"""
        api_prefixes = (
            "api/", "dm/", "copilot/", "webhook/", "auth/", "debug/",
            "health", "leads/", "products/", "onboarding/", "creator/",
            "messages/", "payments/", "calendar/", "nurturing/", "knowledge/",
            "analytics/", "admin/", "connections/", "oauth/", "booking/",
            "tone/", "citations/", "config/", "telegram/", "instagram/",
            "whatsapp/", "metrics", "docs", "openapi.json", "redoc",
            "ingestion/", "maintenance/", "gdpr/",
        )
        if full_path.startswith(api_prefixes):
            raise HTTPException(status_code=404, detail="API route not found")

        index_path = os.path.join(_static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path, media_type="text/html")

        raise HTTPException(status_code=404, detail="Frontend not found")
