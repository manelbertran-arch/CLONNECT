"""
Clonnect Creators API
API simplificada para el clon de IA de creadores de contenido
"""

import logging
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

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
    from api.database import DATABASE_URL, SessionLocal

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
    pass

    USE_DB = True
    logging.info("Database service loaded")
except Exception as e:
    USE_DB = False
    logging.warning("Database service not available: %s", e)

logging.warning("=" * 60)
logging.warning("========== API MAIN V7 LOADED ==========")

from core.creator_config import CreatorConfigManager
from core.memory import MemoryStore
from core.metrics import (
    PROMETHEUS_AVAILABLE,
    MetricsMiddleware,
)

# Core imports
from core.products import ProductManager
from core.rag import get_simple_rag

logging.warning("=" * 60)

logger = logging.getLogger(__name__)

# LLM model config — log at startup so it's visible in Railway logs
try:
    from core.config.llm_models import log_model_config
    log_model_config()
except Exception as _e:
    logging.error("[LLM CONFIG] Failed to log model config: %s", _e)

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
# Production origins only; localhost added conditionally below
DEFAULT_CORS_ORIGINS = [
    "https://www.clonnectapp.com",
    "https://clonnectapp.com",
    "https://api.clonnectapp.com",
]
# Only include localhost origins in non-production environments
if os.getenv("ENVIRONMENT", "production") != "production":
    DEFAULT_CORS_ORIGINS.extend([
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://localhost:8081",
    ])

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
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Requested-With", "Accept", "Origin"],
    allow_credentials=True,
)

# Security Headers Middleware (after CORS so headers are added to all responses)
from api.middleware.security_headers import SecurityHeadersMiddleware

app.add_middleware(SecurityHeadersMiddleware)

# Rate Limiting Middleware
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
if RATE_LIMIT_ENABLED:
    try:
        from api.middleware.rate_limit import RateLimitMiddleware

        app.add_middleware(
            RateLimitMiddleware,
            requests_per_minute=120,   # Was 60 — too low for dashboard polling
            requests_per_hour=3000,    # Was 1000
            webhook_rpm=300,           # Was 200
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
    logger.error("=== VALIDATION ERROR 422 ===")
    logger.error(f"URL: {request.url}")
    logger.error(f"Method: {request.method}")
    logger.error(f"Errors: {exc.errors()}")
    # Note: Don't try to read request.body() here - it may already be consumed
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


# Metrics middleware
if PROMETHEUS_AVAILABLE:
    app.add_middleware(MetricsMiddleware)

# ARC5 Phase 3 — creator context middleware (auto-injects creator_id/lead_id into emit_metric)
try:
    from core.observability.middleware import CreatorContextMiddleware
    app.add_middleware(CreatorContextMiddleware)
    logging.info("[ARC5] CreatorContextMiddleware registered")
except Exception as _e:
    logging.warning("[ARC5] CreatorContextMiddleware not loaded: %s", _e)


# ---------------------------------------------------------
# ROUTERS
# ---------------------------------------------------------
from api.routers import (
    admin,
    ai,
    analytics,
    audience,
    audiencia,
    audio,
    booking,
    bot,
    calendar,
    citations,
    clone_score,
    config,
    connections,
    content,
    copilot,
    creator,
    dashboard,
    debug,
    dm,
    events,
    feedback,
    gdpr,
    health,
    ingestion_v2,
    insights,
    instagram,
    intelligence,
    knowledge,
    leads,
    maintenance,
    memory,
    messaging_webhooks,
    metrics,
    nurturing,
    oauth,
    onboarding,
    payments,
    preview,
    products,
    static,
    telegram,
    tone,
    unified_leads,
    webhooks,
)
from api import autolearning_api
from api.auth import router as auth_router

# Register all routers
# NOTE: messages.router removed — all its endpoints are duplicated in dm.router
app.include_router(health.router)
app.include_router(static.router)
app.include_router(dashboard.router)
app.include_router(config.router)
app.include_router(leads.router)
app.include_router(products.router)
app.include_router(payments.router)
app.include_router(calendar.router)
app.include_router(nurturing.router)
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
app.include_router(autolearning_api.router)
app.include_router(instagram.router)
app.include_router(preview.router)
app.include_router(dm.router)
app.include_router(webhooks.router)
app.include_router(gdpr.router)
app.include_router(telegram.router)
app.include_router(content.router)
app.include_router(creator.router)
app.include_router(bot.router)
app.include_router(ai.router)
app.include_router(audio.router)
app.include_router(debug.router)
app.include_router(audience.router)
app.include_router(insights.router)
app.include_router(audiencia.router)
app.include_router(messaging_webhooks.router)
app.include_router(maintenance.router)
app.include_router(metrics.router)
app.include_router(events.router)
app.include_router(unified_leads.router)
app.include_router(clone_score.router)
app.include_router(feedback.router)
app.include_router(memory.router)
app.include_router(auth_router)
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
        from api.utils.error_helpers import safe_error_detail

        raise HTTPException(status_code=500, detail=safe_error_detail(e, "fetching booking links"))


# =============================================================================
# DEBUG: MEMORY PROFILING ENDPOINT (temporary — remove after diagnosis)
# =============================================================================
@app.get("/debug/memory")
async def debug_memory():
    import asyncio
    import gc
    import sys

    import psutil

    gc.collect()
    # Force arenas back to OS before reading RSS so we see the true minimum
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass
    process = psutil.Process()
    mem = process.memory_info()

    # Asyncio task count (fire-and-forget leak indicator)
    all_tasks = asyncio.all_tasks()
    task_names = {}
    for t in all_tasks:
        name = t.get_name() or "unnamed"
        # Group by first segment (e.g. "scheduler:reconciliation")
        key = name.split(":")[0] if ":" in name else name[:40]
        task_names[key] = task_names.get(key, 0) + 1

    # SSE connection counts
    try:
        from api.routers.events import _active_connections
        sse_connections = {k: len(v) for k, v in _active_connections.items()}
        sse_total = sum(sse_connections.values())
    except Exception:
        sse_connections = {}
        sse_total = 0

    # User profiles cache size
    try:
        from core.user_profiles import _profiles
        profiles_cache_size = len(_profiles)
    except Exception:
        profiles_cache_size = -1

    # API cache stats
    try:
        from api.cache import api_cache
        api_cache_stats = api_cache.stats()
    except Exception:
        api_cache_stats = {}

    # DM agent cache size
    try:
        from core.dm.agent import _dm_agent_cache
        dm_agent_cache_size = len(_dm_agent_cache)
    except Exception:
        dm_agent_cache_size = -1

    # BM25 retrievers
    try:
        from core.rag.bm25 import _retrievers
        bm25_cache_size = len(_retrievers)
    except Exception:
        bm25_cache_size = -1

    # Evolution dedup dict sizes
    try:
        from api.routers.messaging_webhooks.evolution_webhook import (
            _evo_content_dedup,
            _evo_processed_messages,
        )
        evo_dedup_size = len(_evo_processed_messages)
        evo_content_dedup_size = len(_evo_content_dedup)
    except Exception:
        evo_dedup_size = -1
        evo_content_dedup_size = -1

    # Top object counts (GC-visible)
    try:
        from collections import Counter
        obj_counts = Counter(type(o).__name__ for o in gc.get_objects())
        top_objects = dict(obj_counts.most_common(20))
    except Exception:
        top_objects = {}

    # Reranker/PyTorch status
    try:
        from core.rag.reranker import ENABLE_RERANKING, _reranker
        reranker_loaded = _reranker is not None
    except Exception:
        ENABLE_RERANKING = None
        reranker_loaded = False

    return {
        "rss_mb": round(mem.rss / 1024 / 1024, 1),
        "vms_mb": round(mem.vms / 1024 / 1024, 1),
        "gc_objects": len(gc.get_objects()),
        "gc_garbage": len(gc.garbage),
        "asyncio_tasks_total": len(all_tasks),
        "asyncio_tasks_by_type": task_names,
        "sse_connections": sse_connections,
        "sse_total_queues": sse_total,
        "profiles_cache_size": profiles_cache_size,
        "dm_agent_cache_size": dm_agent_cache_size,
        "bm25_cache_size": bm25_cache_size,
        "evo_dedup_size": evo_dedup_size,
        "evo_content_dedup_size": evo_content_dedup_size,
        "api_cache": api_cache_stats,
        "reranker_enabled": ENABLE_RERANKING,
        "reranker_loaded": reranker_loaded,
        "top_gc_objects": top_objects,
    }


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
