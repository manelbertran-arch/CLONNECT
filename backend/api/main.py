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
from core.dm_agent_v2 import DMResponderAgent
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

# Audience router (audience intelligence endpoints)
from api.routers import audience as audience_router

app.include_router(audience_router.router)

# Insights router (daily mission and weekly insights)
from api.routers import insights as insights_router

app.include_router(insights_router.router)

# Audiencia router (aggregated audience data for Tu Audiencia page)
from api.routers import audiencia as audiencia_router

app.include_router(audiencia_router.router)

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


# ---------------------------------------------------------
# PUBLIC BOOKING LINKS (standalone, not part of /calendar/ prefix)
# ---------------------------------------------------------
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


# ---------------------------------------------------------
# STARTUP (handlers in api/startup.py)
# ---------------------------------------------------------
from api.startup import register_startup_handlers

register_startup_handlers(app)


# =============================================================================
# STATIC FILE SERVING (SPA catch-all - MUST BE LAST)
# =============================================================================
from api.static_serving import register_static_routes

register_static_routes(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
