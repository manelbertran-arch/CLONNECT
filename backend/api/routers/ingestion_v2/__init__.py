"""
Ingestion V2 API Router - Zero Hallucinations

Endpoint que garantiza:
- Solo productos verificados con 3+ señales
- Precios solo si encontrados via regex (nunca inventados)
- Todos los datos con source_url y source_html como prueba
- Sanity checks que abortan si algo es sospechoso

This package combines sub-routers for website, Instagram, YouTube, and debug endpoints.
"""

from fastapi import APIRouter

from api.routers.ingestion_v2.debug import FullRefreshRequest
from api.routers.ingestion_v2.debug import router as debug_router
from api.routers.ingestion_v2.instagram_ingest import InstagramV2Request, InstagramV2Response
from api.routers.ingestion_v2.instagram_ingest import router as instagram_router
from api.routers.ingestion_v2.website import (
    IngestV2Request,
    IngestV2Response,
    ProductV2Response,
    get_db,
)
from api.routers.ingestion_v2.website import router as website_router
from api.routers.ingestion_v2.youtube import YouTubeV2Request, YouTubeV2Response
from api.routers.ingestion_v2.youtube import router as youtube_router

# Re-export endpoint functions for external test imports
from api.routers.ingestion_v2.website import (
    ingest_website_v2,
    preview_detection,
    verify_stored_products,
)
from api.routers.ingestion_v2.instagram_ingest import (
    ingest_instagram_v2_endpoint,
    get_instagram_ingestion_status,
)
from api.routers.ingestion_v2.youtube import (
    ingest_youtube_v2_endpoint,
    get_youtube_ingestion_status,
)
from api.routers.ingestion_v2.debug import (
    debug_scraper_test,
    full_refresh,
    get_data_status,
)

# Combined router with original prefix and tags
router = APIRouter(prefix="/ingestion/v2", tags=["ingestion-v2"])
router.include_router(website_router)
router.include_router(instagram_router)
router.include_router(youtube_router)
router.include_router(debug_router)

__all__ = [
    "router",
    # Models
    "IngestV2Request",
    "IngestV2Response",
    "ProductV2Response",
    "InstagramV2Request",
    "InstagramV2Response",
    "YouTubeV2Request",
    "YouTubeV2Response",
    "FullRefreshRequest",
    # Dependencies
    "get_db",
    # Endpoint functions
    "ingest_website_v2",
    "preview_detection",
    "verify_stored_products",
    "ingest_instagram_v2_endpoint",
    "get_instagram_ingestion_status",
    "ingest_youtube_v2_endpoint",
    "get_youtube_ingestion_status",
    "debug_scraper_test",
    "full_refresh",
    "get_data_status",
]
