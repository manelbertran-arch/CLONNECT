"""
Clonnect Creators API
API simplificada para el clon de IA de creadores de contenido
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api.schemas import CreateCreatorRequest, CreateProductRequest

logging.basicConfig(level=logging.INFO)

# =============================================================================
# SENTRY ERROR TRACKING
# =============================================================================
SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            profiles_sample_rate=0.1,
            release=os.getenv("RAILWAY_GIT_COMMIT_SHA", "unknown"),
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
            ],
            send_default_pii=False,
        )
        logging.info("Sentry initialized: %s...", SENTRY_DSN[:40])
    except ImportError:
        logging.warning("sentry-sdk not installed, error tracking disabled")
    except Exception as e:
        logging.error("Sentry init failed: %s", e)

# PostgreSQL Init - define defaults first
SessionLocal = None
BookingLinkModel = None
CalendarBookingModel = None
DATABASE_URL = None

try:
    from api.database import DATABASE_URL, SessionLocal, get_db
    from api.init_db import init_database
    from api.models import BookingLink as BookingLinkModel
    from api.models import CalendarBooking as CalendarBookingModel

    if DATABASE_URL:
        # NOTE: init_database() moved to startup_event to not block healthcheck
        # Tables are created lazily on first request or during startup background task
        logging.info("PostgreSQL configured - SessionLocal=%s", SessionLocal is not None)
        logging.info("Database initialization deferred to startup event")
    else:
        logging.warning("No DATABASE_URL - using JSON fallback")
except Exception as e:
    logging.error("PostgreSQL init failed: %s", e)
    import traceback

    traceback.print_exc()

# Database service
try:
    from api import db_service

    USE_DB = True
    logging.info("Database service loaded")
except Exception as e:
    USE_DB = False
    logging.warning("Database service not available: %s", e)

logging.warning("=" * 60)
logging.warning("========== API MAIN V7 LOADED ==========")

from core.alerts import get_alert_manager
from core.calendar import get_calendar_manager
from core.creator_config import CreatorConfig, CreatorConfigManager
from core.dm_agent import DMResponderAgent
from core.gdpr import ConsentType, get_gdpr_manager
from core.instagram_handler import InstagramHandler, get_instagram_handler
from core.llm import get_llm_client
from core.memory import MemoryStore
from core.metrics import (
    PROMETHEUS_AVAILABLE,
    MetricsMiddleware,
    record_message_processed,
    update_health_status,
)
from core.payments import get_payment_manager

# Core imports
from core.products import Product, ProductManager
from core.rag import get_simple_rag
from core.telegram_registry import get_telegram_registry
from core.whatsapp import get_whatsapp_handler

logging.warning("=" * 60)

logger = logging.getLogger(__name__)

# Instancias globales
product_manager = ProductManager()
config_manager = CreatorConfigManager()
memory_store = MemoryStore()
rag = get_simple_rag()

# FastAPI
app = FastAPI(
    title="Clonnect Creators",
    description="API para el clon de IA de creadores de contenido",
    version="1.0.0",
)

# =============================================================================
# CORS CONFIGURATION
# =============================================================================
# Always allow Vercel frontend + localhost + any additional origins from env
DEFAULT_CORS_ORIGINS = [
    "https://clonnect.vercel.app",
    "https://www.clonnect.vercel.app",
    "https://clonnect-production.up.railway.app",
    "https://frontend-wine-ten-57.vercel.app",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
    "http://localhost:8081",
]

CORS_ORIGINS_ENV = os.getenv("CORS_ORIGINS", "")
if CORS_ORIGINS_ENV:
    # Add env origins to defaults
    env_origins = [origin.strip() for origin in CORS_ORIGINS_ENV.split(",") if origin.strip()]
    CORS_ORIGINS = list(set(DEFAULT_CORS_ORIGINS + env_origins))
else:
    CORS_ORIGINS = DEFAULT_CORS_ORIGINS
logging.info("CORS: Allowing origins: %s", CORS_ORIGINS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Rate Limiting Middleware
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
if RATE_LIMIT_ENABLED:
    try:
        from api.middleware.rate_limit import RateLimitMiddleware

        app.add_middleware(
            RateLimitMiddleware,
            requests_per_minute=60,
            requests_per_hour=1000,
            webhook_rpm=200,
        )
        logging.info("Rate limiting middleware enabled")
    except ImportError as e:
        logging.warning(f"Rate limiting middleware not available: {e}")

# Add exception handler to log 422 validation errors
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger = logging.getLogger("api.validation")
    logger.error(f"=== VALIDATION ERROR 422 ===")
    logger.error(f"URL: {request.url}")
    logger.error(f"Method: {request.method}")
    logger.error(f"Errors: {exc.errors()}")
    # Note: Don't try to read request.body() here - it may already be consumed
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


# Metrics middleware
if PROMETHEUS_AVAILABLE:
    app.add_middleware(MetricsMiddleware)


# ---------------------------------------------------------

# ---------------------------------------------------------
# ROUTERS (modularized endpoints)
# ---------------------------------------------------------
from api.routers import config, dashboard, health, leads, products, static

app.include_router(health.router)
app.include_router(static.router)
app.include_router(dashboard.router)
app.include_router(config.router)
app.include_router(leads.router)
app.include_router(products.router)

# Additional routers
from api.routers import calendar, messages, nurturing, payments

app.include_router(messages.router)
app.include_router(payments.router)
app.include_router(calendar.router)
app.include_router(nurturing.router)
from api.routers import (
    admin,
    analytics,
    booking,
    citations,
    connections,
    copilot,
    ingestion_v2,
    intelligence,
    knowledge,
    oauth,
    onboarding,
    tone,
)

app.include_router(knowledge.router)
app.include_router(analytics.router)
app.include_router(intelligence.router)
app.include_router(onboarding.router)
app.include_router(admin.router)
app.include_router(connections.router)
app.include_router(oauth.router)
app.include_router(booking.router)
app.include_router(tone.router)
app.include_router(citations.router)
app.include_router(copilot.router)
app.include_router(ingestion_v2.router)

# Ingestion router (anti-hallucination pipeline)
from api.routers import ingestion

app.include_router(ingestion.router)

# Ingestion V2 router (zero-hallucination pipeline)
from api.routers import ingestion_v2

app.include_router(ingestion_v2.router)

# Instagram router (multi-creator support)
from api.routers import instagram as instagram_router

app.include_router(instagram_router.router)

# Preview router (link previews with screenshots)
from api.routers import preview as preview_router

app.include_router(preview_router.router)

# DM router (direct message management)
from api.routers import dm as dm_router

app.include_router(dm_router.router)

# Webhooks router (payment and calendar webhooks)
from api.routers import webhooks as webhooks_router

app.include_router(webhooks_router.router)

# GDPR router
from api.routers import gdpr as gdpr_router

app.include_router(gdpr_router.router)

# Telegram router (bot management and status)
from api.routers import telegram as telegram_router

app.include_router(telegram_router.router)

# Content router (RAG management)
from api.routers import content as content_router

app.include_router(content_router.router)

# Creator router (config management)
from api.routers import creator as creator_router

app.include_router(creator_router.router)

# Bot router (pause/resume/status)
from api.routers import bot as bot_router

app.include_router(bot_router.router)

# AI router (Grok API endpoints)
from api.routers import ai as ai_router

app.include_router(ai_router.router)

# Debug router (diagnostic endpoints)
from api.routers import debug as debug_router

app.include_router(debug_router.router)

# Messaging webhooks router (Instagram, WhatsApp, Telegram)
from api.routers import messaging_webhooks as messaging_webhooks_router

app.include_router(messaging_webhooks_router.router)

# Authentication router
from api.auth import (
    router as auth_router,
    get_current_creator,
    get_optional_creator,
    require_admin,
    require_creator_or_admin,
)

app.include_router(auth_router)

logging.info(
    "Routers loaded: health, dashboard, config, leads, products, analytics, connections, oauth, booking, tone, citations, copilot, ingestion, instagram, auth"
)
# AUTHENTICATION
# ---------------------------------------------------------
# Endpoints publicos (no requieren autenticacion)
PUBLIC_ENDPOINTS = {
    "/",
    "/health",
    "/health/live",
    "/health/ready",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/privacy",
    "/terms",
    # OAuth callbacks (need to be public for redirects)
    "/oauth/instagram/callback",
    "/oauth/whatsapp/callback",
    "/oauth/stripe/callback",
    "/oauth/paypal/callback",
    "/oauth/calendly/callback",
}

# Endpoints de webhook (usan su propia autenticacion via firma)
WEBHOOK_ENDPOINTS = {
    "/webhook/instagram",
    "/webhook/whatsapp",
    "/webhook/stripe",
    "/webhook/hotmart",
    "/webhook/paypal",
    "/webhook/calendly",
    "/webhook/calcom",
    "/webhook/telegram",
    "/instagram/webhook",  # Legacy
    "/telegram/webhook",  # Legacy
}


@app.get("/citations/debug/{creator_id}")
async def debug_citations(creator_id: str, query: str = "test"):
    """Debug endpoint to check citation content index"""
    import os
    from pathlib import Path

    from core.citation_service import get_citation_prompt_section, get_content_index

    debug_info = {
        "creator_id": creator_id,
        "query": query,
        "cwd": os.getcwd(),
        "data_dir_exists": os.path.exists("data"),
        "content_index_dir_exists": os.path.exists("data/content_index"),
        "creator_dir_exists": os.path.exists(f"data/content_index/{creator_id}"),
        "chunks_file_exists": os.path.exists(f"data/content_index/{creator_id}/chunks.json"),
        "initial_data_exists": os.path.exists("/app/initial_data"),
        "files_in_content_index": [],
        "chunks_count": 0,
        "search_results": [],
        "citation_prompt": "",
    }

    # List files in content_index
    try:
        if os.path.exists("data/content_index"):
            debug_info["files_in_content_index"] = os.listdir("data/content_index")
        if os.path.exists(f"data/content_index/{creator_id}"):
            debug_info["creator_files"] = os.listdir(f"data/content_index/{creator_id}")
    except Exception as e:
        debug_info["list_error"] = str(e)

    # Load index and check
    try:
        index = get_content_index(creator_id)
        debug_info["chunks_count"] = len(index.chunks)
        debug_info["index_loaded"] = index._loaded
        debug_info["posts_count"] = len(index.posts_metadata)

        # Search test
        if query:
            results = index.search(query, max_results=3)
            debug_info["search_results"] = [
                {"id": r["chunk_id"], "title": r.get("title"), "relevance": r["relevance_score"]}
                for r in results
            ]

            # Get citation prompt
            citation_prompt = get_citation_prompt_section(creator_id, query)
            debug_info["citation_prompt_length"] = len(citation_prompt)
            debug_info["citation_prompt_preview"] = citation_prompt[:500] if citation_prompt else ""

    except Exception as e:
        debug_info["index_error"] = str(e)

    return {"status": "ok", "debug": debug_info}


# ---------------------------------------------------------
# PAYMENTS (unique endpoints - purchases/revenue in payments.py)
# ---------------------------------------------------------
@app.get("/payments/{creator_id}/customer/{follower_id}")
async def get_customer_purchases(creator_id: str, follower_id: str):
    """Get purchase history for a specific customer"""
    try:
        payment_manager = get_payment_manager()
        purchases = payment_manager.get_customer_purchases(
            creator_id=creator_id, follower_id=follower_id
        )

        total_spent = sum(p.get("amount", 0) for p in purchases if p.get("status") == "completed")

        return {
            "status": "ok",
            "creator_id": creator_id,
            "follower_id": follower_id,
            "purchases": purchases,
            "total_spent": total_spent,
            "count": len(purchases),
        }

    except Exception as e:
        logger.error(f"Error getting customer purchases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/payments/{creator_id}/attribute")
async def attribute_sale(creator_id: str, purchase_id: str, follower_id: str):
    """
    Manually attribute a sale to the bot.

    Use when a purchase wasn't automatically linked to a conversation.
    """
    try:
        payment_manager = get_payment_manager()
        success = payment_manager.attribute_sale_to_bot(
            creator_id=creator_id, follower_id=follower_id, purchase_id=purchase_id
        )

        if not success:
            raise HTTPException(status_code=404, detail="Purchase not found")

        return {
            "status": "ok",
            "attributed": True,
            "purchase_id": purchase_id,
            "follower_id": follower_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error attributing sale: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# CALENDAR (unique endpoints - bookings/stats/links in calendar.py)
# ---------------------------------------------------------
@app.get("/calendar/{creator_id}/link/{meeting_type}")
async def get_booking_link(creator_id: str, meeting_type: str):
    """
    Get booking link for a specific meeting type - uses PostgreSQL for persistence.

    Meeting types: discovery, consultation, coaching, followup, custom
    """
    try:
        # Use database instead of file storage
        if SessionLocal:
            db = SessionLocal()
            try:
                # First try to find exact meeting type
                db_link = (
                    db.query(BookingLinkModel)
                    .filter(
                        BookingLinkModel.creator_id == creator_id,
                        BookingLinkModel.meeting_type == meeting_type,
                        BookingLinkModel.is_active == True,
                    )
                    .first()
                )

                # If not found, try default
                if not db_link:
                    db_link = (
                        db.query(BookingLinkModel)
                        .filter(
                            BookingLinkModel.creator_id == creator_id,
                            BookingLinkModel.meeting_type == "default",
                            BookingLinkModel.is_active == True,
                        )
                        .first()
                    )

                if not db_link:
                    raise HTTPException(
                        status_code=404, detail=f"No booking link found for type: {meeting_type}"
                    )

                return {
                    "status": "ok",
                    "creator_id": creator_id,
                    "meeting_type": meeting_type,
                    "url": db_link.url,
                }
            finally:
                db.close()
        else:
            # Fallback to file-based storage
            calendar_manager = get_calendar_manager()
            url = calendar_manager.get_booking_link(creator_id, meeting_type)

            if not url:
                raise HTTPException(
                    status_code=404, detail=f"No booking link found for type: {meeting_type}"
                )

            return {
                "status": "ok",
                "creator_id": creator_id,
                "meeting_type": meeting_type,
                "url": url,
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting booking link: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/calendar/{creator_id}/links")
async def get_all_booking_links(creator_id: str):
    """Get all booking links for a creator - uses PostgreSQL with direct SQL"""
    logger.info(f"GET /calendar/{creator_id}/links - SessionLocal={SessionLocal is not None}")
    try:
        # Use database with direct SQL (proven to work)
        if SessionLocal:
            logger.info(f"GET - Using PostgreSQL with direct SQL")
            from sqlalchemy import text

            db = SessionLocal()
            try:
                # Direct SQL SELECT - same approach as debug endpoint
                result = db.execute(
                    text(
                        """
                    SELECT id, creator_id, meeting_type, title, description,
                           duration_minutes, platform, url, is_active, created_at
                    FROM booking_links
                    WHERE creator_id = :creator_id AND is_active = true
                    ORDER BY created_at DESC
                """
                    ),
                    {"creator_id": creator_id},
                )

                rows = result.fetchall()
                logger.info(f"GET - Found {len(rows)} links in PostgreSQL for {creator_id}")

                links = []
                for row in rows:
                    links.append(
                        {
                            "id": str(row[0]),
                            "creator_id": row[1],
                            "meeting_type": row[2],
                            "title": row[3],
                            "description": row[4] or "",
                            "duration_minutes": row[5],
                            "platform": row[6],
                            "url": row[7] or "",
                            "is_active": row[8],
                            "metadata": {},
                            "created_at": row[9].isoformat() if row[9] else "",
                        }
                    )

                return {
                    "status": "ok",
                    "storage": "postgresql",
                    "creator_id": creator_id,
                    "links": links,
                    "count": len(links),
                }
            finally:
                db.close()
        else:
            # Fallback to file-based storage
            logger.warning(
                f"GET /calendar/{creator_id}/links - USING FILE FALLBACK (SessionLocal={SessionLocal}, BookingLinkModel={BookingLinkModel})"
            )
            calendar_manager = get_calendar_manager()
            links = calendar_manager.get_all_booking_links(creator_id)
            return {
                "status": "ok",
                "creator_id": creator_id,
                "links": links,
                "count": len(links),
                "storage": "file",  # Indicator for debugging
            }

    except Exception as e:
        logger.error(f"Error getting booking links: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/booking-links/{creator_name}")
async def get_booking_links_public(creator_name: str):
    """Get all booking links/services for a creator (public endpoint)"""
    try:
        if not SessionLocal:
            raise HTTPException(status_code=500, detail="Database not configured")

        from sqlalchemy import text

        db = SessionLocal()
        try:
            result = db.execute(
                text(
                    """
                SELECT id, title, description, duration_minutes, platform, url,
                       COALESCE(price, 0) as price, meeting_type
                FROM booking_links
                WHERE creator_id = :creator_id AND is_active = true
                ORDER BY created_at DESC
            """
                ),
                {"creator_id": creator_name},
            )

            rows = result.fetchall()
            logger.info(f"GET /booking-links/{creator_name} - Found {len(rows)} links")

            return {
                "status": "ok",
                "creator": creator_name,
                "booking_links": [
                    {
                        "id": str(row[0]),
                        "name": row[1],
                        "description": row[2] or "",
                        "duration": row[3],
                        "platform": row[4],
                        "url": row[5] or "",
                        "price": float(row[6]) if row[6] else 0,
                        "meeting_type": row[7],
                    }
                    for row in rows
                ],
                "count": len(rows),
            }
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting booking links: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/calendar/{creator_id}/links")
async def create_booking_link(creator_id: str, data: dict = Body(...)):
    """
    Create a new booking link - uses PostgreSQL for persistence.
    REWRITTEN to match debug endpoint exactly.
    """
    import uuid

    from sqlalchemy import text

    logger.debug("BOOKING LINK CREATE - creator_id: %s, data: %s, SessionLocal: %s",
                 creator_id, data, SessionLocal is not None)

    # Extract data from body
    meeting_type = data.get("meeting_type", "custom")
    duration_minutes = data.get("duration_minutes", data.get("duration", 30))
    title = data.get("title", "")
    platform = data.get("platform", "manual")

    result = {"success": False, "error": None, "link_id": None}

    if SessionLocal:
        db = SessionLocal()
        try:
            link_id = str(uuid.uuid4())
            logger.debug("Inserting link_id: %s", link_id)

            # EXACT same SQL as debug endpoint
            db.execute(
                text(
                    """
                INSERT INTO booking_links (id, creator_id, meeting_type, title, duration_minutes, platform, is_active)
                VALUES (:id, :creator_id, :meeting_type, :title, :duration, :platform, :is_active)
            """
                ),
                {
                    "id": link_id,
                    "creator_id": creator_id,
                    "meeting_type": meeting_type,
                    "title": title,
                    "duration": duration_minutes,
                    "platform": platform,
                    "is_active": True,
                },
            )
            db.commit()
            logger.debug("INSERT + COMMIT done for %s", link_id)

            # Verify
            verify = db.execute(
                text("SELECT COUNT(*) FROM booking_links WHERE id = :id"), {"id": link_id}
            )
            verify_count = verify.scalar()
            logger.debug("verify_count: %s", verify_count)

            result["success"] = True
            result["link_id"] = link_id
            result["verify_count"] = verify_count

            return {
                "status": "ok",
                "storage": "postgresql",
                "link": {
                    "id": link_id,
                    "creator_id": creator_id,
                    "meeting_type": meeting_type,
                    "title": title,
                    "duration_minutes": duration_minutes,
                    "platform": platform,
                    "is_active": True,
                },
                "debug": result,
            }
        except Exception as e:
            logger.error("Booking link create failed: %s", e, exc_info=True)
            result["error"] = str(e)
            return {"status": "error", "error": str(e), "debug": result}
        finally:
            db.close()
    else:
        logger.error("SessionLocal is None - database not configured")
        return {"status": "error", "error": "Database not configured"}


@app.get("/calendar/{creator_id}/stats")
async def get_calendar_stats(creator_id: str, days: int = 30):
    """
    Get booking statistics.

    Returns:
    - Total bookings
    - Show rate
    - Cancel rate
    - Bookings by type
    - Bookings by platform
    """
    try:
        calendar_manager = get_calendar_manager()
        stats = calendar_manager.get_booking_stats(creator_id, days)

        return {"status": "ok", "creator_id": creator_id, **stats}

    except Exception as e:
        logger.error(f"Error getting calendar stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/calendar/{creator_id}/bookings/{booking_id}/complete")
async def mark_booking_completed(creator_id: str, booking_id: str):
    """Mark a booking as completed"""
    try:
        calendar_manager = get_calendar_manager()
        success = calendar_manager.mark_booking_completed(creator_id, booking_id)

        if not success:
            raise HTTPException(status_code=404, detail="Booking not found")

        return {"status": "ok", "booking_id": booking_id, "new_status": "completed"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking booking complete: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/calendar/{creator_id}/bookings/{booking_id}/no-show")
async def mark_booking_no_show(creator_id: str, booking_id: str):
    """Mark a booking as no-show"""
    try:
        calendar_manager = get_calendar_manager()
        success = calendar_manager.mark_booking_no_show(creator_id, booking_id)

        if not success:
            raise HTTPException(status_code=404, detail="Booking not found")

        return {"status": "ok", "booking_id": booking_id, "new_status": "no_show"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking booking no-show: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# STARTUP
# ---------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    """Inicializacion al arrancar"""
    logger.info("Clonnect Creators API starting...")
    logger.info(f"LLM Provider: {os.getenv('LLM_PROVIDER', 'openai')}")

    # Log database configuration
    db_url = os.getenv("DATABASE_URL")
    json_fallback = os.getenv("ENABLE_JSON_FALLBACK", "false").lower() == "true"
    if db_url:
        logger.info("Database: PostgreSQL configured")
        if json_fallback:
            logger.warning("JSON Fallback: ENABLED - DB errors will fall back to JSON files")
        else:
            logger.info("JSON Fallback: DISABLED - DB errors will raise exceptions")
    else:
        logger.warning("Database: No DATABASE_URL - using JSON files only")

    # Initialize database in background to not block healthcheck
    # Tables/migrations can take 30-60s on cold start
    async def init_db_background():
        await asyncio.sleep(1)  # Let healthcheck pass first
        try:
            if db_url:
                logger.info("Starting database initialization (background)...")
                init_database()
                logger.info("Database initialization complete")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")

    asyncio.create_task(init_db_background())
    logger.info("Database initialization scheduled (background task)")

    # Start nurturing scheduler
    try:
        from api.routers.nurturing import start_scheduler

        start_scheduler()
        logger.info("Nurturing scheduler started")
    except Exception as e:
        logger.error(f"Failed to start nurturing scheduler: {e}")

    # Hydrate RAG from PostgreSQL - DO IT IN BACKGROUND to not block health check
    # Railway gives only 30s for health check, but FAISS encoding can take 60s+
    async def hydrate_rag_background():
        await asyncio.sleep(5)  # Wait for app to be fully ready
        try:
            loaded = rag.load_from_db()
            logger.info(f"RAG hydrated with {loaded} documents from database")
        except Exception as e:
            logger.error(f"Failed to hydrate RAG from database: {e}")

    asyncio.create_task(hydrate_rag_background())
    logger.info("RAG hydration scheduled (background task)")

    # PRE-WARM: Load ToneProfile and CitationIndex for active creators
    # This reduces first-request latency from ~4s to ~0.5s
    # Added 10s timeout to prevent blocking if DB is slow
    async def prewarm_creator_caches():
        await asyncio.sleep(2)  # Wait a bit for app to be ready
        try:
            # Wrap in timeout to prevent blocking on slow DB
            await asyncio.wait_for(_do_prewarm(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning("Pre-warming timeout after 10s, continuing anyway")
        except Exception as e:
            logger.error(f"Failed to pre-warm caches: {e}")

    async def _do_prewarm():
        try:
            import time

            _t_start = time.time()

            # Get active creators from database AND Telegram registry
            active_creators = set()

            # 1. Get from database
            if SessionLocal:
                try:
                    from api.models import Creator

                    session = SessionLocal()
                    try:
                        creators = session.query(Creator).filter_by(bot_active=True).all()
                        for c in creators:
                            if c.name:
                                active_creators.add(c.name)
                    finally:
                        session.close()
                except Exception as e:
                    logger.warning(f"Could not get creators from DB: {e}")

            # 2. Get from Telegram registry (may not be in DB)
            try:
                from core.telegram_registry import get_telegram_registry

                registry = get_telegram_registry()
                for bot in registry.list_bots():
                    if bot.get("is_active") and bot.get("creator_id"):
                        active_creators.add(bot["creator_id"])
            except Exception:
                pass

            # Fallback: at minimum, pre-warm stefano_auto
            if not active_creators:
                active_creators = {"stefano_auto"}

            active_creators = list(active_creators)

            logger.info(
                f"Pre-warming caches for {len(active_creators)} creators: {active_creators}"
            )

            # Pre-load embedding model for semantic memory (takes 2-10s on first load)
            try:
                from core.semantic_memory import ENABLE_SEMANTIC_MEMORY, _get_embeddings

                if ENABLE_SEMANTIC_MEMORY:
                    _t_emb = time.time()
                    _get_embeddings()  # Force load the model
                    logger.info(f"⏱️ Pre-loaded embedding model in {time.time() - _t_emb:.2f}s")
            except Exception as e:
                logger.warning(f"Could not pre-load embedding model: {e}")

            # Pre-load ToneProfile cache
            from core.tone_service import get_tone_prompt_section

            for creator_id in active_creators:
                try:
                    get_tone_prompt_section(creator_id)
                except Exception as e:
                    logger.debug(f"ToneProfile not found for {creator_id}: {e}")

            # Pre-load CitationIndex cache
            from core.citation_service import get_content_index

            for creator_id in active_creators:
                try:
                    get_content_index(creator_id)
                except Exception as e:
                    logger.debug(f"CitationIndex not found for {creator_id}: {e}")

            _t_end = time.time()
            logger.info(f"⏱️ Pre-warmed caches in {_t_end - _t_start:.2f}s for {active_creators}")

        except Exception as e:
            logger.warning(f"Pre-warm inner error: {e}")

    asyncio.create_task(prewarm_creator_caches())
    logger.info("Cache pre-warming scheduled (background task)")

    # KEEP-ALIVE: Ping every 4 minutes to prevent cold starts and keep caches warm
    # Railway puts containers to sleep after extended inactivity
    # CRITICAL: 4 min interval keeps all caches warm (config TTL=5min, agent TTL=10min)
    async def keep_alive_task():
        import time

        KEEP_ALIVE_INTERVAL = 240  # 4 minutes - keeps all caches warm

        # Wait briefly for startup to complete
        await asyncio.sleep(3)
        logger.warning(
            f"[KEEP-ALIVE] ===== STARTED - will ping every {KEEP_ALIVE_INTERVAL}s (4 min) ====="
        )

        while True:
            try:
                _t_start = time.time()

                # Get ALL active creators to warm up
                active_creators = set(["stefano_auto", "stefano_bonanno"])  # Defaults

                # 1. Get creators from database with bot_active=True
                if SessionLocal:
                    try:
                        from api.models import Creator

                        session = SessionLocal()
                        try:
                            creators = session.query(Creator).filter_by(bot_active=True).all()
                            if creators:
                                for c in creators:
                                    if c.name:
                                        active_creators.add(c.name)
                        finally:
                            session.close()
                    except Exception:
                        pass

                # 2. Get creators from Telegram registry (may not be in DB)
                try:
                    from core.telegram_registry import get_telegram_registry

                    registry = get_telegram_registry()
                    for bot in registry.list_bots():
                        if bot.get("is_active") and bot.get("creator_id"):
                            active_creators.add(bot["creator_id"])
                except Exception:
                    pass

                active_creators = list(active_creators)

                # 1. Pre-load DM agents for ALL active creators
                # This keeps config/products cache warm (5-min TTL) and agent cache warm (10-min TTL)
                from core.dm_agent import _dm_agent_cache_timestamp

                for creator_id in active_creators:
                    try:
                        agent = get_dm_agent(creator_id)
                        cache_age = time.time() - _dm_agent_cache_timestamp.get(creator_id, 0)
                        # Touch the system prompt cache to keep it warm
                        if hasattr(agent, "_build_system_prompt"):
                            _ = agent._build_system_prompt("")
                        logger.info(
                            f"[KEEP-ALIVE] Agent for {creator_id} kept warm (cache age: {cache_age:.1f}s)"
                        )
                    except Exception as e:
                        logger.warning(f"[KEEP-ALIVE] DM agent warm failed for {creator_id}: {e}")

                # 2. Keep embedding model warm (for semantic memory)
                try:
                    from core.semantic_memory import ENABLE_SEMANTIC_MEMORY, _get_embeddings

                    if ENABLE_SEMANTIC_MEMORY:
                        _get_embeddings()  # Just touch it to keep in memory
                        logger.debug("[KEEP-ALIVE] Embedding model kept warm")
                except Exception:
                    pass

                # 3. Refresh ToneProfile and CitationIndex cache for all creators
                try:
                    from core.citation_service import get_content_index
                    from core.tone_service import get_tone_prompt_section

                    for creator_id in active_creators:
                        try:
                            get_tone_prompt_section(creator_id)
                            get_content_index(creator_id)
                        except Exception:
                            pass
                except Exception:
                    pass

                # 5. Light DB ping to keep connection pool alive
                if SessionLocal:
                    try:
                        from sqlalchemy import text

                        session = SessionLocal()
                        session.execute(text("SELECT 1"))
                        session.close()
                    except Exception:
                        pass

                _t_end = time.time()
                logger.warning(
                    f"[KEEP-ALIVE] ===== Ping completed in {_t_end - _t_start:.2f}s ====="
                )

            except Exception as e:
                logger.error(f"[KEEP-ALIVE] Error: {e}", exc_info=True)

            await asyncio.sleep(KEEP_ALIVE_INTERVAL)

    asyncio.create_task(keep_alive_task())
    logger.info("Keep-alive task scheduled (every 4 minutes)")

    logger.info("Ready to receive requests!")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


# =============================================================================
# SERVE FRONTEND STATIC FILES
# =============================================================================
# This must be at the VERY END after all API routes are defined

_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")

if os.path.exists(_static_dir):
    # Mount assets directory for JS/CSS files
    _assets_dir = os.path.join(_static_dir, "assets")
    if os.path.exists(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="static_assets")
        logger.info(f"Mounted frontend assets from {_assets_dir}")

    # Serve static files (images, favicon, etc.)
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
        import glob as _glob

        # Check static files
        static_files = []
        if os.path.exists(_static_dir):
            for f in os.listdir(_static_dir):
                fpath = os.path.join(_static_dir, f)
                static_files.append(
                    {
                        "name": f,
                        "size": os.path.getsize(fpath) if os.path.isfile(fpath) else 0,
                        "type": "file" if os.path.isfile(fpath) else "dir",
                    }
                )

        # Check assets folder
        assets_dir = os.path.join(_static_dir, "assets")
        assets_files = []
        if os.path.exists(assets_dir):
            for f in os.listdir(assets_dir):
                fpath = os.path.join(assets_dir, f)
                assets_files.append(
                    {"name": f, "size": os.path.getsize(fpath) if os.path.isfile(fpath) else 0}
                )

        # Check index.html
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
                        m.split('"')[0] for m in content.split('src="') if ".js" in m.split('"')[0]
                    ][:5],
                    "css_files": [
                        m.split('"')[0]
                        for m in content.split('href="')
                        if ".css" in m.split('"')[0]
                    ][:5],
                }

        # Database check
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
            "timestamp": datetime.now().isoformat(),
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

    # Catch-all route for frontend SPA - must be LAST
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve frontend for all non-API routes (SPA catch-all)"""
        # Don't catch API routes - they're already handled above
        # NOTE: "dashboard/" removed from prefixes - frontend uses /dashboard/{id} route
        # The actual API endpoints /dashboard/{id}/overview and /dashboard/{id}/toggle
        # are defined before this catch-all, so they'll match first
        api_prefixes = (
            "api/",
            "dm/",
            "copilot/",
            "webhook/",
            "auth/",
            "debug/",
            "health",
            "leads/",
            "products/",
            "onboarding/",
            "creator/",
            "messages/",
            "payments/",
            "calendar/",
            "nurturing/",
            "knowledge/",
            "analytics/",
            "admin/",
            "connections/",
            "oauth/",
            "booking/",
            "tone/",
            "citations/",
            "config/",
            "telegram/",
            "instagram/",
            "whatsapp/",
            "metrics",
            "docs",
            "openapi.json",
            "redoc",
        )
        if full_path.startswith(api_prefixes):
            raise HTTPException(status_code=404, detail="API route not found")

        index_path = os.path.join(_static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path, media_type="text/html")

        raise HTTPException(status_code=404, detail="Frontend not found")

else:
    logger.warning(f"Static directory not found: {_static_dir}")
