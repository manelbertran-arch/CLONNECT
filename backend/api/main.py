"""
Clonnect Creators API
API simplificada para el clon de IA de creadores de contenido
"""

import asyncio
import json
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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
    get_content_type,
    get_metrics,
    record_message_processed,
    update_health_status,
)
from core.payments import get_payment_manager

# Core imports
from core.products import Product, ProductManager
from core.rag import get_simple_rag
from core.telegram_registry import get_telegram_registry
from core.whatsapp import get_whatsapp_handler

# Optional psutil for memory health checks
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None

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
from api.routers import config, dashboard, health, leads, products

app.include_router(health.router)
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
# PYDANTIC MODELS
# ---------------------------------------------------------
class CreateCreatorRequest(BaseModel):
    id: str
    name: str
    instagram_handle: str
    personality: Optional[Dict[str, Any]] = None
    emoji_style: Optional[str] = "moderate"
    sales_style: Optional[str] = "soft"


class CreateProductRequest(BaseModel):
    id: str
    name: str
    description: str
    price: float
    currency: str = "EUR"
    payment_link: str = ""
    category: str = ""
    features: List[str] = []
    keywords: List[str] = []


# ---------------------------------------------------------
# HEALTH & INFO
# ---------------------------------------------------------
VERSION = "1.0.0"


async def check_llm_health() -> Dict[str, Any]:
    """Verifica conexion con LLM (Groq/OpenAI/Anthropic)"""
    try:
        start = time.time()
        llm_client = get_llm_client()

        # Hacer una llamada simple de prueba
        response = await llm_client.generate(prompt="Responde solo 'ok'", max_tokens=5)

        latency_ms = int((time.time() - start) * 1000)

        return {
            "status": "ok",
            "latency_ms": latency_ms,
            "provider": os.getenv("LLM_PROVIDER", "openai"),
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "provider": os.getenv("LLM_PROVIDER", "openai")}


def check_disk_health() -> Dict[str, Any]:
    """Verifica espacio en disco"""
    try:
        data_path = os.getenv("DATA_PATH", "./data")

        # Obtener info del disco
        total, used, free = shutil.disk_usage(data_path)
        free_gb = round(free / (1024**3), 2)

        # Warning si menos de 1GB, error si menos de 100MB
        if free_gb < 0.1:
            status = "error"
        elif free_gb < 1.0:
            status = "warning"
        else:
            status = "ok"

        return {
            "status": status,
            "free_gb": free_gb,
            "total_gb": round(total / (1024**3), 2),
            "used_percent": round((used / total) * 100, 1),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_memory_health() -> Dict[str, Any]:
    """Verifica memoria RAM disponible"""
    try:
        if not PSUTIL_AVAILABLE:
            return {"status": "unknown", "error": "psutil not installed"}

        mem = psutil.virtual_memory()
        free_mb = round(mem.available / (1024**2), 1)

        # Warning si menos de 256MB, error si menos de 128MB
        if free_mb < 128:
            status = "error"
        elif free_mb < 256:
            status = "warning"
        else:
            status = "ok"

        return {
            "status": status,
            "free_mb": free_mb,
            "total_mb": round(mem.total / (1024**2), 1),
            "used_percent": round(mem.percent, 1),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_data_dir_health() -> Dict[str, Any]:
    """Verifica acceso a directorio de datos"""
    try:
        data_path = os.getenv("DATA_PATH", "./data")

        # Verificar que existe
        if not os.path.exists(data_path):
            return {"status": "error", "error": "data directory does not exist"}

        # Verificar subdirectorios importantes
        subdirs = ["followers", "products", "creators", "analytics"]
        missing = []

        for subdir in subdirs:
            path = os.path.join(data_path, subdir)
            if not os.path.exists(path):
                missing.append(subdir)

        if missing:
            return {"status": "warning", "path": data_path, "missing_subdirs": missing}

        # Verificar que es escribible
        test_file = os.path.join(data_path, ".health_check")
        try:
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            writable = True
        except Exception as e:
            logger.warning(f"Data path not writable: {e}")
            writable = False

        return {"status": "ok" if writable else "error", "path": data_path, "writable": writable}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def determine_overall_status(checks: Dict[str, Dict]) -> str:
    """Determina el status general basado en los checks individuales"""
    statuses = [check.get("status", "unknown") for check in checks.values()]

    if "error" in statuses:
        return "unhealthy"
    elif "warning" in statuses or "unknown" in statuses:
        return "degraded"
    else:
        return "healthy"


@app.get("/health")
async def health():
    """
    Health check completo del sistema.

    Verifica:
    - Estado general del sistema
    - Conexion LLM (Groq/OpenAI)
    - Espacio en disco
    - Memoria RAM
    - Acceso a directorio de datos

    Returns:
        status: healthy | degraded | unhealthy
        checks: Detalles de cada verificacion
    """
    checks = {
        "disk": check_disk_health(),
        "memory": check_memory_health(),
        "data_dir": check_data_dir_health(),
    }

    # LLM check es async
    checks["llm"] = await check_llm_health()

    overall_status = determine_overall_status(checks)

    # Enviar alerta si el status es unhealthy
    if overall_status == "unhealthy":
        try:
            alert_manager = get_alert_manager()
            failed_checks = {k: v for k, v in checks.items() if v.get("status") == "error"}
            await alert_manager.alert_health_check_failed(
                check_name="system", status=overall_status, details=failed_checks
            )
        except Exception as e:
            logger.debug(f"Could not send health alert: {e}")

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "version": VERSION,
        "service": "clonnect-creators",
    }


@app.get("/debug/database")
async def debug_database():
    """
    Debug endpoint to check database connectivity and booking_links table.
    """
    result = {
        "DATABASE_URL_configured": DATABASE_URL is not None and DATABASE_URL != "",
        "SessionLocal_available": SessionLocal is not None,
        "BookingLinkModel_available": BookingLinkModel is not None,
        "tables": [],
        "booking_links_count": 0,
        "booking_links_sample": [],
        "error": None,
    }

    if SessionLocal and BookingLinkModel:
        try:
            from sqlalchemy import text

            db = SessionLocal()
            try:
                # Check tables
                tables_result = db.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                    )
                )
                result["tables"] = [row[0] for row in tables_result.fetchall()]

                # Check booking_links
                if "booking_links" in result["tables"]:
                    count_result = db.execute(text("SELECT COUNT(*) FROM booking_links"))
                    result["booking_links_count"] = count_result.scalar()

                    # Get sample data
                    sample_result = db.execute(
                        text(
                            "SELECT id, creator_id, meeting_type, title, platform FROM booking_links LIMIT 5"
                        )
                    )
                    result["booking_links_sample"] = [
                        {
                            "id": str(row[0]),
                            "creator_id": row[1],
                            "meeting_type": row[2],
                            "title": row[3],
                            "platform": row[4],
                        }
                        for row in sample_result.fetchall()
                    ]
            finally:
                db.close()
        except Exception as e:
            result["error"] = str(e)
            import traceback

            result["traceback"] = traceback.format_exc()
    else:
        result["error"] = "Database not configured - SessionLocal or BookingLinkModel is None"

    return result


@app.get("/debug/products/{creator_name}")
async def debug_products(creator_name: str):
    """Debug endpoint to check products for a creator."""
    result = {"creator_name": creator_name, "creator_found": False, "products": [], "error": None}
    if SessionLocal:
        try:
            from sqlalchemy import text

            db = SessionLocal()
            try:
                # Find creator
                creator_result = db.execute(
                    text("SELECT id, name FROM creators WHERE name = :name"), {"name": creator_name}
                )
                creator_row = creator_result.fetchone()
                if creator_row:
                    result["creator_found"] = True
                    result["creator_id"] = str(creator_row[0])
                    # Get products with new taxonomy fields
                    products_result = db.execute(
                        text(
                            "SELECT id, name, price, currency, category, product_type, is_free, short_description, payment_link, is_active FROM products WHERE creator_id = :cid"
                        ),
                        {"cid": creator_row[0]},
                    )
                    result["products"] = [
                        {
                            "id": str(row[0]),
                            "name": row[1],
                            "price": row[2],
                            "currency": row[3],
                            "category": row[4],
                            "product_type": row[5],
                            "is_free": row[6],
                            "short_description": row[7],
                            "payment_link": row[8],
                            "is_active": row[9],
                        }
                        for row in products_result.fetchall()
                    ]
                    result["count"] = len(result["products"])
            finally:
                db.close()
        except Exception as e:
            result["error"] = str(e)
            import traceback

            result["traceback"] = traceback.format_exc()
    return result


@app.post("/debug/insert-booking-link")
async def debug_insert_booking_link():
    """
    Direct test insert to booking_links - bypasses all conditions.
    This is for debugging only.
    """
    result = {
        "success": False,
        "error": None,
        "link_id": None,
        "SessionLocal": SessionLocal is not None,
        "BookingLinkModel": BookingLinkModel is not None,
    }

    # Try direct SQL insert first
    if SessionLocal:
        try:
            import uuid

            from sqlalchemy import text

            db = SessionLocal()
            try:
                test_id = str(uuid.uuid4())

                # Direct SQL INSERT
                db.execute(
                    text(
                        """
                    INSERT INTO booking_links (id, creator_id, meeting_type, title, duration_minutes, platform, is_active)
                    VALUES (:id, :creator_id, :meeting_type, :title, :duration, :platform, :is_active)
                """
                    ),
                    {
                        "id": test_id,
                        "creator_id": "test_debug",
                        "meeting_type": "debug_test",
                        "title": "Debug Test Link",
                        "duration": 30,
                        "platform": "manual",
                        "is_active": True,
                    },
                )
                db.commit()

                result["success"] = True
                result["link_id"] = test_id
                result["message"] = "Direct SQL INSERT worked!"

                # Verify it was inserted
                verify = db.execute(
                    text("SELECT COUNT(*) FROM booking_links WHERE creator_id = 'test_debug'")
                )
                result["verify_count"] = verify.scalar()

            finally:
                db.close()
        except Exception as e:
            result["error"] = str(e)
            import traceback

            result["traceback"] = traceback.format_exc()
    else:
        result["error"] = "SessionLocal is None - database not configured"

    return result


@app.get("/debug/full-diagnosis")
async def full_diagnosis():
    """
    COMPLETE SYSTEM DIAGNOSIS - Shows everything about the system state.
    Open this URL in browser to see what's happening.
    """
    import subprocess
    from datetime import datetime, timezone

    diagnosis = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server": {},
        "database": {},
        "telegram": {},
        "creator_stefano_auto": {},
        "environment": {},
        "recent_activity": {},
    }

    # === 1. SERVER STATUS ===
    diagnosis["server"] = {
        "status": "running",
        "python_version": os.popen("python --version 2>&1").read().strip(),
        "working_directory": os.getcwd(),
        "uptime_note": "Server is responding to requests",
    }

    # === 2. DATABASE STATUS ===
    db_status = {
        "DATABASE_URL_configured": bool(DATABASE_URL),
        "SessionLocal_available": SessionLocal is not None,
        "connection_test": "not_tested",
    }

    if SessionLocal:
        try:
            from api.models import Creator, Lead, Message
            from sqlalchemy import text

            session = SessionLocal()
            try:
                # Test connection
                session.execute(text("SELECT 1"))
                db_status["connection_test"] = "SUCCESS"

                # Get tables
                tables_result = session.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                    )
                )
                db_status["tables"] = [row[0] for row in tables_result.fetchall()]

                # Count creators
                creator_count = session.query(Creator).count()
                db_status["total_creators"] = creator_count

                # Count pending responses (Messages with status='pending_approval')
                pending_count = (
                    session.query(Message)
                    .filter_by(status="pending_approval", role="assistant")
                    .count()
                )
                db_status["total_pending_responses"] = pending_count

            finally:
                session.close()
        except Exception as e:
            db_status["connection_test"] = f"FAILED: {str(e)}"

    diagnosis["database"] = db_status

    # === 3. STEFANO_AUTO SPECIFIC ===
    stefano_status = {
        "exists": False,
        "copilot_mode": None,
        "bot_active": None,
        "pending_responses_count": 0,
        "last_pending_response": None,
    }

    if SessionLocal:
        try:
            from api.models import Creator, Lead, Message

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name="stefano_auto").first()
                if creator:
                    stefano_status["exists"] = True
                    stefano_status["copilot_mode"] = getattr(creator, "copilot_mode", None)
                    stefano_status["bot_active"] = getattr(creator, "bot_active", None)

                    # Get pending responses for stefano_auto via Lead -> Message
                    pending = (
                        session.query(Message, Lead)
                        .join(Lead, Message.lead_id == Lead.id)
                        .filter(
                            Lead.creator_id == creator.id,
                            Message.status == "pending_approval",
                            Message.role == "assistant",
                        )
                        .order_by(Message.created_at.desc())
                        .all()
                    )

                    stefano_status["pending_responses_count"] = len(pending)

                    if pending:
                        msg, lead = pending[0]
                        # Get user message for context
                        user_msg = (
                            session.query(Message)
                            .filter(Message.lead_id == lead.id, Message.role == "user")
                            .order_by(Message.created_at.desc())
                            .first()
                        )

                        stefano_status["last_pending_response"] = {
                            "id": str(msg.id),
                            "created_at": msg.created_at.isoformat() if msg.created_at else None,
                            "user_message": (
                                user_msg.content[:50] if user_msg and user_msg.content else None
                            ),
                            "suggested_response": msg.content[:50] if msg.content else None,
                            "platform": lead.platform,
                        }
            finally:
                session.close()
        except Exception as e:
            stefano_status["error"] = str(e)

    diagnosis["creator_stefano_auto"] = stefano_status

    # === 4. TELEGRAM STATUS ===
    telegram_status = {
        "bot_token_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
        "registered_bots": [],
        "webhook_status": {},
    }

    try:
        from core.telegram_registry import get_telegram_registry

        registry = get_telegram_registry()
        bots = registry.list_bots()
        telegram_status["registered_bots"] = bots

        # Check webhook for each bot
        for bot in bots:
            bot_id = bot.get("bot_id")
            bot_token = registry.get_bot_token(bot_id)
            if bot_token:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        response = await client.get(
                            f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
                        )
                        webhook_info = response.json()
                        if webhook_info.get("ok"):
                            telegram_status["webhook_status"][bot_id] = {
                                "url": webhook_info.get("result", {}).get("url", "NOT SET"),
                                "pending_updates": webhook_info.get("result", {}).get(
                                    "pending_update_count", 0
                                ),
                                "last_error": webhook_info.get("result", {}).get(
                                    "last_error_message"
                                ),
                            }
                except Exception as e:
                    telegram_status["webhook_status"][bot_id] = {"error": str(e)}
    except Exception as e:
        telegram_status["error"] = str(e)

    diagnosis["telegram"] = telegram_status

    # === 5. ENVIRONMENT (without sensitive values) ===
    env_vars = [
        "DATABASE_URL",
        "GROQ_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "RAILWAY_PUBLIC_URL",
        "RENDER_EXTERNAL_URL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ]

    diagnosis["environment"] = {var: "SET" if os.getenv(var) else "NOT SET" for var in env_vars}

    # === 6. QUICK SUMMARY ===
    diagnosis["summary"] = {
        "database_ok": db_status.get("connection_test") == "SUCCESS",
        "stefano_exists": stefano_status.get("exists", False),
        "copilot_mode": stefano_status.get("copilot_mode"),
        "pending_count": stefano_status.get("pending_responses_count", 0),
        "telegram_bots": len(telegram_status.get("registered_bots", [])),
        "recommendation": "",
    }

    # Build recommendation
    if not stefano_status.get("exists"):
        diagnosis["summary"]["recommendation"] = "Creator stefano_auto doesn't exist in DB!"
    elif stefano_status.get("copilot_mode") == True:
        if stefano_status.get("pending_responses_count", 0) > 0:
            diagnosis["summary"][
                "recommendation"
            ] = f"System working! {stefano_status['pending_responses_count']} messages waiting for approval in Copilot dashboard."
        else:
            diagnosis["summary"][
                "recommendation"
            ] = "Copilot mode ON but no pending messages. Send a test message to the bot."
    elif stefano_status.get("copilot_mode") == False:
        diagnosis["summary"][
            "recommendation"
        ] = "Autopilot mode - bot should respond automatically."
    else:
        diagnosis["summary"][
            "recommendation"
        ] = "copilot_mode is NULL - defaulting to True (Copilot mode)."

    return diagnosis


@app.post("/debug/test-telegram-flow")
async def test_telegram_flow():
    """
    Simulate a Telegram message flow and report each step.
    """
    steps = []

    # Step 1: Check creator exists
    creator_id = "stefano_auto"
    try:
        from api.models import Creator

        session = SessionLocal()
        creator = session.query(Creator).filter_by(name=creator_id).first()
        session.close()

        if creator:
            steps.append(
                {"step": "1. Find creator", "status": "OK", "detail": f"Found {creator_id}"}
            )
            copilot_mode = getattr(creator, "copilot_mode", True)
            steps.append(
                {
                    "step": "2. Check copilot_mode",
                    "status": "OK",
                    "detail": f"copilot_mode = {copilot_mode}",
                }
            )
        else:
            steps.append(
                {
                    "step": "1. Find creator",
                    "status": "FAIL",
                    "detail": f"Creator {creator_id} not found!",
                }
            )
            return {"steps": steps, "conclusion": "FAILED - Creator not found"}
    except Exception as e:
        steps.append({"step": "1. Find creator", "status": "ERROR", "detail": str(e)})
        return {"steps": steps, "conclusion": f"FAILED - {e}"}

    # Step 2: Try to generate a response
    try:
        from core.dm_agent import get_dm_agent

        agent = get_dm_agent(creator_id)
        steps.append(
            {
                "step": "3. Initialize DM Agent",
                "status": "OK",
                "detail": f"Agent ready for {creator_id}",
            }
        )

        # Process a test message
        response = await agent.process_dm(
            sender_id="test_diagnosis",
            message_text="hola, esto es una prueba de diagnóstico",
            message_id="diag_001",
            username="DiagnosticTest",
            name="Test User",
        )

        steps.append(
            {
                "step": "4. Generate response",
                "status": "OK",
                "detail": f"Intent: {response.intent.value if hasattr(response.intent, 'value') else response.intent}, Response: {response.response_text[:80]}...",
            }
        )
    except Exception as e:
        steps.append({"step": "3-4. DM Agent", "status": "ERROR", "detail": str(e)})
        return {"steps": steps, "conclusion": f"FAILED at DM Agent - {e}"}

    # Step 3: Check what would happen based on copilot_mode
    if copilot_mode:
        steps.append(
            {
                "step": "5. Copilot mode action",
                "status": "INFO",
                "detail": "Would save as pending_approval (not send immediately)",
            }
        )

        # Try to create a pending response
        try:
            from core.copilot_service import get_copilot_service

            copilot = get_copilot_service()

            pending = await copilot.create_pending_response(
                creator_id=creator_id,
                lead_id="",
                follower_id="test_diagnosis",
                platform="telegram",
                user_message="TEST - diagnostic message",
                user_message_id="diag_001",
                suggested_response=response.response_text,
                intent=(
                    response.intent.value
                    if hasattr(response.intent, "value")
                    else str(response.intent)
                ),
                confidence=0.95,
                username="DiagnosticTest",
                full_name="Test User",
            )

            steps.append(
                {
                    "step": "6. Create pending response",
                    "status": "OK",
                    "detail": f"Created pending ID: {pending.id}",
                }
            )
        except Exception as e:
            steps.append({"step": "6. Create pending", "status": "ERROR", "detail": str(e)})
    else:
        steps.append(
            {
                "step": "5. Autopilot mode action",
                "status": "INFO",
                "detail": "Would send response immediately via Telegram",
            }
        )

    return {
        "steps": steps,
        "conclusion": "SUCCESS - All steps passed",
        "copilot_mode": copilot_mode,
        "note": "If copilot_mode=True, messages go to dashboard for approval. Check /copilot/stefano_auto/pending",
    }


@app.get("/health/live")
def health_live():
    """
    Liveness probe para Kubernetes.

    Solo verifica que el proceso esta vivo y puede responder.
    Respuesta minima para bajo overhead.

    Returns:
        status: ok | error
    """
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready():
    """
    Readiness probe para Kubernetes.

    Verifica que el servicio puede procesar mensajes:
    - LLM accesible
    - Directorio de datos accesible

    Returns:
        status: ok | error
        ready: boolean
    """
    try:
        # Verificar acceso a datos
        data_check = check_data_dir_health()
        if data_check.get("status") == "error":
            return {"status": "error", "ready": False, "reason": "data_dir_not_accessible"}

        # Verificar LLM
        llm_check = await check_llm_health()
        if llm_check.get("status") == "error":
            return {
                "status": "error",
                "ready": False,
                "reason": "llm_not_accessible",
                "llm_error": llm_check.get("error"),
            }

        return {"status": "ok", "ready": True, "llm_latency_ms": llm_check.get("latency_ms")}

    except Exception as e:
        return {"status": "error", "ready": False, "reason": str(e)}


@app.get("/api")
def api_info():
    """API info - moved to /api to let root serve frontend"""
    return {
        "name": "Clonnect Creators API",
        "version": VERSION,
        "description": "Tu clon de IA para responder DMs de Instagram",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics",
        "privacy": "/privacy",
        "terms": "/terms",
    }


@app.get("/")
async def serve_root():
    """Serve frontend index.html for root"""
    _static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    index_path = os.path.join(_static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return {"error": "Frontend not found"}


# ---------------------------------------------------------
# LEGAL PAGES (Privacy & Terms)
# ---------------------------------------------------------
@app.get("/privacy", response_class=HTMLResponse)
def privacy_policy():
    """Privacy Policy page"""
    return """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Política de Privacidad - Clonnect Creators</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 40px 20px; line-height: 1.6; color: #333; }
        h1 { color: #1a1a2e; border-bottom: 2px solid #4a4e69; padding-bottom: 10px; }
        h2 { color: #4a4e69; margin-top: 30px; }
        .updated { color: #666; font-size: 0.9em; }
        a { color: #4a4e69; }
    </style>
</head>
<body>
    <h1>Política de Privacidad</h1>
    <p class="updated">Última actualización: Diciembre 2024</p>

    <h2>1. Información que Recopilamos</h2>
    <p>Clonnect Creators recopila la siguiente información:</p>
    <ul>
        <li><strong>Datos de conversación:</strong> Mensajes enviados a través de Instagram, Telegram o WhatsApp para proporcionar respuestas automatizadas.</li>
        <li><strong>Identificadores de usuario:</strong> IDs de plataforma para mantener el contexto de la conversación.</li>
        <li><strong>Datos de interacción:</strong> Intenciones detectadas, productos de interés y estado de la conversación.</li>
    </ul>

    <h2>2. Uso de la Información</h2>
    <p>Utilizamos la información recopilada para:</p>
    <ul>
        <li>Proporcionar respuestas automatizadas personalizadas</li>
        <li>Mejorar la calidad de las interacciones</li>
        <li>Generar métricas agregadas para el creador de contenido</li>
        <li>Detectar y prevenir abusos del servicio</li>
    </ul>

    <h2>3. Compartición de Datos</h2>
    <p>No vendemos ni compartimos datos personales con terceros, excepto:</p>
    <ul>
        <li>Con el creador de contenido cuyo bot estás usando</li>
        <li>Proveedores de servicios esenciales (hosting, LLM)</li>
        <li>Cuando sea requerido por ley</li>
    </ul>

    <h2>4. Retención de Datos</h2>
    <p>Los datos de conversación se retienen por un máximo de 90 días para mantener el contexto.
    Puedes solicitar la eliminación de tus datos en cualquier momento.</p>

    <h2>5. Derechos GDPR</h2>
    <p>Si eres residente de la UE, tienes derecho a:</p>
    <ul>
        <li><strong>Acceso:</strong> Solicitar una copia de tus datos</li>
        <li><strong>Rectificación:</strong> Corregir datos inexactos</li>
        <li><strong>Supresión:</strong> Solicitar la eliminación de tus datos</li>
        <li><strong>Portabilidad:</strong> Recibir tus datos en formato estructurado</li>
        <li><strong>Oposición:</strong> Oponerte al procesamiento de tus datos</li>
    </ul>
    <p>Para ejercer estos derechos, contacta al creador de contenido o envía un email con tu solicitud.</p>

    <h2>6. Seguridad</h2>
    <p>Implementamos medidas de seguridad técnicas y organizativas para proteger tus datos,
    incluyendo encriptación en tránsito y almacenamiento seguro.</p>

    <h2>7. Cookies</h2>
    <p>Esta API no utiliza cookies. Las plataformas de mensajería (Instagram, Telegram, WhatsApp)
    tienen sus propias políticas de cookies.</p>

    <h2>8. Cambios a esta Política</h2>
    <p>Podemos actualizar esta política ocasionalmente. Los cambios significativos serán comunicados
    a través de los canales apropiados.</p>

    <h2>9. Contacto</h2>
    <p>Para preguntas sobre esta política de privacidad, contacta al creador de contenido
    que utiliza este servicio.</p>

    <p style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd;">
        <a href="/">← Volver al inicio</a> | <a href="/terms">Términos de Servicio</a>
    </p>
</body>
</html>"""


@app.get("/terms", response_class=HTMLResponse)
def terms_of_service():
    """Terms of Service page"""
    return """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Términos de Servicio - Clonnect Creators</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 40px 20px; line-height: 1.6; color: #333; }
        h1 { color: #1a1a2e; border-bottom: 2px solid #4a4e69; padding-bottom: 10px; }
        h2 { color: #4a4e69; margin-top: 30px; }
        .updated { color: #666; font-size: 0.9em; }
        a { color: #4a4e69; }
    </style>
</head>
<body>
    <h1>Términos de Servicio</h1>
    <p class="updated">Última actualización: Diciembre 2024</p>

    <h2>1. Aceptación de los Términos</h2>
    <p>Al interactuar con un bot de Clonnect Creators, aceptas estos términos de servicio.
    Si no estás de acuerdo, por favor no utilices el servicio.</p>

    <h2>2. Descripción del Servicio</h2>
    <p>Clonnect Creators proporciona respuestas automatizadas mediante inteligencia artificial
    en nombre de creadores de contenido. El servicio:</p>
    <ul>
        <li>Responde mensajes directos de forma automatizada</li>
        <li>Proporciona información sobre productos y servicios del creador</li>
        <li>Facilita la comunicación inicial antes de intervención humana</li>
    </ul>

    <h2>3. Naturaleza del Bot</h2>
    <p><strong>Importante:</strong> Las respuestas son generadas por inteligencia artificial,
    no directamente por el creador de contenido. Aunque el bot está entrenado para representar
    al creador, las respuestas pueden no reflejar exactamente sus opiniones.</p>

    <h2>4. Uso Aceptable</h2>
    <p>Al usar el servicio, te comprometes a NO:</p>
    <ul>
        <li>Enviar contenido ilegal, ofensivo o spam</li>
        <li>Intentar manipular o engañar al sistema de IA</li>
        <li>Usar el servicio para actividades fraudulentas</li>
        <li>Intentar extraer información del sistema o realizar ataques</li>
        <li>Suplantar la identidad de otras personas</li>
    </ul>

    <h2>5. Limitaciones del Servicio</h2>
    <p>El servicio se proporciona "tal cual". No garantizamos:</p>
    <ul>
        <li>Disponibilidad ininterrumpida del servicio</li>
        <li>Precisión completa de las respuestas de IA</li>
        <li>Tiempos de respuesta específicos</li>
    </ul>

    <h2>6. Propiedad Intelectual</h2>
    <p>El contenido generado por el bot pertenece al creador de contenido.
    La tecnología de Clonnect Creators está protegida por derechos de autor.</p>

    <h2>7. Privacidad</h2>
    <p>El uso de tus datos está regido por nuestra <a href="/privacy">Política de Privacidad</a>.
    Al usar el servicio, consientes el procesamiento de datos según dicha política.</p>

    <h2>8. Compras y Transacciones</h2>
    <p>Si realizas compras a través de enlaces proporcionados por el bot:</p>
    <ul>
        <li>Las transacciones se procesan a través de plataformas de terceros (Stripe, Hotmart)</li>
        <li>Los términos de compra del creador y la plataforma de pago aplican</li>
        <li>Clonnect Creators no es responsable de disputas de compra</li>
    </ul>

    <h2>9. Limitación de Responsabilidad</h2>
    <p>En la máxima medida permitida por la ley, Clonnect Creators no será responsable por:</p>
    <ul>
        <li>Daños indirectos, incidentales o consecuentes</li>
        <li>Pérdida de datos o interrupción del servicio</li>
        <li>Acciones tomadas basándose en respuestas del bot</li>
    </ul>

    <h2>10. Modificaciones</h2>
    <p>Nos reservamos el derecho de modificar estos términos en cualquier momento.
    El uso continuado del servicio constituye aceptación de los términos modificados.</p>

    <h2>11. Terminación</h2>
    <p>Podemos suspender o terminar el acceso al servicio si violas estos términos,
    sin previo aviso ni responsabilidad.</p>

    <h2>12. Ley Aplicable</h2>
    <p>Estos términos se rigen por las leyes aplicables en la jurisdicción del creador de contenido.</p>

    <h2>13. Contacto</h2>
    <p>Para preguntas sobre estos términos, contacta al creador de contenido que utiliza este servicio.</p>

    <p style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd;">
        <a href="/">← Volver al inicio</a> | <a href="/privacy">Política de Privacidad</a>
    </p>
</body>
</html>"""


# ---------------------------------------------------------
# PROMETHEUS METRICS
# ---------------------------------------------------------
@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus exposition format.
    Scrape this endpoint with Prometheus server.

    Example prometheus.yml config:
    ```
    scrape_configs:
      - job_name: 'clonnect-creators'
        static_configs:
          - targets: ['localhost:8000']
        metrics_path: '/metrics'
    ```
    """
    return Response(content=get_metrics(), media_type=get_content_type())


# ---------------------------------------------------------
# ---------------------------------------------------------
# INSTAGRAM WEBHOOK
# ---------------------------------------------------------
@app.get("/webhook/instagram")
async def instagram_webhook_verify(request: Request):
    """
    Verificacion de webhook de Meta (GET).
    Meta envia GET para verificar el endpoint antes de activar webhooks.
    """
    params = dict(request.query_params)
    mode = params.get("hub.mode", "")
    token = params.get("hub.verify_token", "")
    challenge = params.get("hub.challenge", "")

    handler = get_instagram_handler()
    result = handler.verify_webhook(mode, token, challenge)

    if result:
        logger.info(f"Instagram webhook verified successfully")
        return Response(content=result, media_type="text/plain")

    logger.warning(f"Instagram webhook verification failed")
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook/instagram")
async def instagram_webhook_receive(request: Request):
    """
    Recibir eventos de Instagram (POST).
    Procesa DMs entrantes con DMResponderAgent y envia respuestas automaticas.
    """
    # V6 MARKER - Log al inicio del endpoint
    logger.warning("=" * 60)
    logger.warning("========== INSTAGRAM WEBHOOK HIT V6 ==========")
    logger.warning("=" * 60)

    try:
        payload = await request.json()
        signature = request.headers.get("X-Hub-Signature-256", "")

        handler = get_instagram_handler()
        result = await handler.handle_webhook(payload, signature)

        logger.info(f"Instagram webhook processed: {result.get('messages_processed', 0)} messages")
        return result

    except Exception as e:
        logger.error(f"Error processing Instagram webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Legacy endpoint (backwards compatibility)
@app.get("/instagram/webhook")
async def instagram_webhook_verify_legacy(request: Request):
    """Legacy endpoint - redirect to /webhook/instagram"""
    return await instagram_webhook_verify(request)


@app.post("/instagram/webhook")
async def instagram_webhook_receive_legacy(request: Request):
    """Legacy endpoint - redirect to /webhook/instagram"""
    return await instagram_webhook_receive(request)


@app.get("/instagram/status")
async def instagram_status():
    """Obtener estado del handler de Instagram"""
    handler = get_instagram_handler()
    return {
        "status": "ok",
        "handler": handler.get_status(),
        "recent_messages": handler.get_recent_messages(5),
        "recent_responses": handler.get_recent_responses(5),
    }


@app.post("/webhook/instagram/comments")
async def instagram_comments_webhook(request: Request):
    """
    Webhook for Instagram comments.
    When someone comments on a post with interest keywords, auto-sends a DM.
    Enable with AUTO_DM_ON_COMMENTS=true environment variable.
    """
    try:
        payload = await request.json()
        handler = get_instagram_handler()

        results = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") == "comments":
                    comment_data = change.get("value", {})
                    result = await handler.handle_comment(comment_data)
                    if result:
                        results.append(result)

        return {"status": "ok", "comments_processed": len(results), "results": results}

    except Exception as e:
        logger.error(f"Error processing Instagram comments webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# WHATSAPP WEBHOOK
# ---------------------------------------------------------


@app.get("/webhook/whatsapp")
async def whatsapp_webhook_verify(request: Request):
    """
    Verificacion de webhook de Meta para WhatsApp (GET).
    Meta envia GET para verificar el endpoint antes de activar webhooks.
    """
    mode = request.query_params.get("hub.mode", "")
    token = request.query_params.get("hub.verify_token", "")
    challenge = request.query_params.get("hub.challenge", "")

    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "clonnect_whatsapp_verify_2024")

    if mode == "subscribe" and token == verify_token:
        logger.info("WhatsApp webhook verified successfully")
        return PlainTextResponse(content=challenge)

    logger.warning(f"WhatsApp webhook verification failed: mode={mode}")
    return PlainTextResponse(content="Verification failed", status_code=403)


@app.post("/webhook/whatsapp")
async def whatsapp_webhook_receive(request: Request):
    """
    Recibir mensajes de WhatsApp via webhook de Meta.
    """
    logger.warning("========== WHATSAPP WEBHOOK HIT ==========")

    try:
        payload = await request.json()
        signature = request.headers.get("X-Hub-Signature-256", "")

        handler = get_whatsapp_handler()
        result = await handler.handle_webhook(payload, signature)

        logger.info(f"WhatsApp webhook processed: {result.get('messages_processed', 0)} messages")
        return result

    except Exception as e:
        logger.error(f"Error processing WhatsApp webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/whatsapp/status")
async def whatsapp_status():
    """Estado del handler de WhatsApp"""
    handler = get_whatsapp_handler()
    return {
        "status": handler.get_status(),
        "recent_messages": handler.get_recent_messages(5),
        "recent_responses": handler.get_recent_responses(5),
    }


# ---------------------------------------------------------
# TELEGRAM WEBHOOK
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL", "")  # Cloudflare Worker URL
TELEGRAM_PROXY_SECRET = os.getenv("TELEGRAM_PROXY_SECRET", "")

# Deduplication cache for Telegram messages (prevents multiple responses)
# Stores {update_id: timestamp} with 60 second TTL
_telegram_processed_updates: Dict[int, float] = {}
_telegram_dedup_lock = asyncio.Lock()
TELEGRAM_DEDUP_TTL = 60  # seconds

# Copilot mode cache - avoid DB query on every message
# Stores {creator_id: (copilot_mode, timestamp)} with 5-minute TTL
_copilot_mode_cache: Dict[str, tuple] = {}
_COPILOT_CACHE_TTL = 300  # 5 minutes


def _get_copilot_mode_cached(creator_id: str) -> bool:
    """
    Get copilot_mode for a creator with 5-minute cache.
    Returns True (copilot mode) by default if not found.
    """
    import time

    current_time = time.time()

    # Check cache first
    if creator_id in _copilot_mode_cache:
        cached_value, cached_time = _copilot_mode_cache[creator_id]
        if current_time - cached_time < _COPILOT_CACHE_TTL:
            logger.debug(f"[COPILOT-CACHE] HIT for {creator_id}: copilot_mode={cached_value}")
            return cached_value

    # Cache miss - query DB
    copilot_enabled = True  # Default to True
    try:
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if creator:
                copilot_enabled = getattr(creator, "copilot_mode", True)
                if copilot_enabled is None:
                    copilot_enabled = True
                logger.info(
                    f"[COPILOT-CACHE] MISS for {creator_id}: loaded copilot_mode={copilot_enabled} from DB"
                )
            else:
                logger.warning(
                    f"[COPILOT-CACHE] Creator '{creator_id}' not found, defaulting to copilot_mode=True"
                )
        finally:
            session.close()
    except Exception as e:
        logger.error(f"[COPILOT-CACHE] DB error: {e} - defaulting to copilot_mode=True")

    # Store in cache
    _copilot_mode_cache[creator_id] = (copilot_enabled, current_time)
    return copilot_enabled


async def _check_telegram_duplicate(update_id: int) -> bool:
    """
    Check if this update was already processed.
    Returns True if duplicate (should skip), False if new.
    Also cleans up old entries.
    """
    import time

    current_time = time.time()

    async with _telegram_dedup_lock:
        # Clean up old entries (older than TTL)
        expired = [
            uid
            for uid, ts in _telegram_processed_updates.items()
            if current_time - ts > TELEGRAM_DEDUP_TTL
        ]
        for uid in expired:
            del _telegram_processed_updates[uid]

        # Check if this update was already processed
        if update_id in _telegram_processed_updates:
            logger.warning(f"Telegram duplicate update_id={update_id} - skipping")
            return True

        # Mark as processed
        _telegram_processed_updates[update_id] = current_time
        return False


async def send_telegram_via_proxy(
    chat_id: int, text: str, bot_token: str, reply_markup: dict = None
) -> dict:
    """Send Telegram message via Cloudflare Worker proxy"""
    headers = {}
    if TELEGRAM_PROXY_SECRET:
        headers["X-Telegram-Proxy-Secret"] = TELEGRAM_PROXY_SECRET

    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        params["reply_markup"] = reply_markup

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            TELEGRAM_PROXY_URL,
            json={"bot_token": bot_token, "method": "sendMessage", "params": params},
            headers=headers,
        )
        return response.json()


async def send_telegram_direct(
    chat_id: int, text: str, bot_token: str, reply_markup: dict = None
) -> dict:
    """Send Telegram message directly (for environments without blocking)"""
    telegram_api = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup

    async with httpx.AsyncClient() as client:
        response = await client.post(telegram_api, json=payload)
        return response.json()


async def send_telegram_message(
    chat_id: int, text: str, bot_token: str, reply_markup: dict = None
) -> dict:
    """
    Send Telegram message - DIRECT FIRST, proxy as fallback.
    Direct is much faster (~0.5s vs 7-8s for proxy).
    """
    import time

    _t_start = time.time()

    # Try direct first (faster) - Railway doesn't block Telegram API
    try:
        logger.info(f"Sending Telegram message directly to chat {chat_id}")
        result = await send_telegram_direct(chat_id, text, bot_token, reply_markup)
        logger.info(f"⏱️ Telegram direct call took {time.time() - _t_start:.2f}s")

        # Check if successful
        if result.get("ok"):
            return result
        else:
            logger.warning(f"Direct Telegram failed: {result}, trying proxy...")
    except Exception as e:
        logger.warning(f"Direct Telegram error: {e}, trying proxy...")

    # Fallback to proxy if direct fails and proxy is configured
    if TELEGRAM_PROXY_URL:
        try:
            logger.info(f"Fallback: sending via proxy to chat {chat_id}")
            result = await send_telegram_via_proxy(chat_id, text, bot_token, reply_markup)
            logger.info(f"⏱️ Telegram proxy fallback took {time.time() - _t_start:.2f}s")
            return result
        except Exception as e:
            logger.error(f"Proxy also failed: {e}")
            return {"ok": False, "error": str(e)}

    return {"ok": False, "error": "Direct failed and no proxy configured"}


async def answer_callback_query(callback_query_id: str, text: str = None) -> dict:
    """Answer a callback query to stop the loading animation"""
    telegram_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text

    if TELEGRAM_PROXY_URL:
        headers = {}
        if TELEGRAM_PROXY_SECRET:
            headers["X-Telegram-Proxy-Secret"] = TELEGRAM_PROXY_SECRET
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                TELEGRAM_PROXY_URL,
                json={
                    "bot_token": TELEGRAM_BOT_TOKEN,
                    "method": "answerCallbackQuery",
                    "params": payload,
                },
                headers=headers,
            )
            return response.json()
    else:
        async with httpx.AsyncClient() as client:
            response = await client.post(telegram_api, json=payload)
            return response.json()


async def edit_telegram_message(
    chat_id: int, message_id: int, text: str, reply_markup: dict = None
) -> dict:
    """Edit an existing Telegram message"""
    telegram_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = reply_markup

    if TELEGRAM_PROXY_URL:
        headers = {}
        if TELEGRAM_PROXY_SECRET:
            headers["X-Telegram-Proxy-Secret"] = TELEGRAM_PROXY_SECRET
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                TELEGRAM_PROXY_URL,
                json={
                    "bot_token": TELEGRAM_BOT_TOKEN,
                    "method": "editMessageText",
                    "params": payload,
                },
                headers=headers,
            )
            return response.json()
    else:
        async with httpx.AsyncClient() as client:
            response = await client.post(telegram_api, json=payload)
            return response.json()


async def handle_telegram_booking_callback(callback_query: dict) -> dict:
    """
    Handle Telegram inline button callbacks for the booking flow.
    Callback data formats:
    - book_svc:{service_id} - User selected a service → show dates
    - book_date:{service_id}:{date} - User selected a date → show time slots
    - book_time:{service_id}:{date}:{time} - User selected a time → confirm booking
    """
    from datetime import datetime, timedelta, timezone

    from api.database import get_db_session
    from api.models import (
        BookingLink,
        BookingSlot,
        CalendarBooking,
        Creator,
        CreatorAvailability,
        Follower,
    )

    callback_id = callback_query.get("id")
    data = callback_query.get("data", "")
    chat_id = callback_query.get("message", {}).get("chat", {}).get("id")
    message_id = callback_query.get("message", {}).get("message_id")
    user = callback_query.get("from", {})
    user_id = str(user.get("id", "unknown"))
    user_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get(
        "username", "Usuario"
    )

    creator_id = os.getenv("DEFAULT_CREATOR_ID", "manel")
    logger.info(f"Telegram callback: {data} from {user_name} (chat {chat_id})")

    try:
        # Answer callback immediately to stop loading animation
        await answer_callback_query(callback_id)

        # Parse callback data
        parts = data.split(":")

        if parts[0] == "book_svc" and len(parts) >= 2:
            # User selected a service → show available dates
            service_id = parts[1]
            return await show_date_picker(chat_id, message_id, service_id, creator_id)

        elif parts[0] == "book_date" and len(parts) >= 3:
            # User selected a date → show available time slots
            service_id = parts[1]
            date_str = parts[2]
            return await show_time_picker(chat_id, message_id, service_id, date_str, creator_id)

        elif parts[0] == "book_time" and len(parts) >= 4:
            # User selected a time → confirm booking
            service_id = parts[1]
            date_str = parts[2]
            time_str = parts[3]
            return await confirm_telegram_booking(
                chat_id, message_id, service_id, date_str, time_str, user_id, user_name, creator_id
            )

        elif parts[0] == "book_back":
            # User wants to go back to service selection
            return await show_service_picker(chat_id, message_id, creator_id)

        else:
            logger.warning(f"Unknown callback data: {data}")
            return {"status": "ok", "message": "Unknown callback"}

    except Exception as e:
        logger.error(f"Error handling booking callback: {e}")
        import traceback

        logger.error(traceback.format_exc())
        await send_telegram_message(
            chat_id,
            f"❌ Error al procesar tu solicitud. Por favor, intenta de nuevo.",
            TELEGRAM_BOT_TOKEN,
        )
        return {"status": "error", "detail": str(e)}


async def show_service_picker(chat_id: int, message_id: int, creator_id: str) -> dict:
    """Show available services as inline buttons"""
    from api.database import get_db_session
    from api.models import BookingLink

    with get_db_session() as db:
        links = (
            db.query(BookingLink)
            .filter(BookingLink.creator_id == creator_id, BookingLink.is_active == True)
            .all()
        )

        if not links:
            await edit_telegram_message(
                chat_id, message_id, "No hay servicios disponibles actualmente."
            )
            return {"status": "ok"}

        keyboard = []
        for link in links:
            price_text = "GRATIS" if (link.price or 0) == 0 else f"{link.price}€"
            btn_text = f"📅 {link.title} ({link.duration_minutes} min) - {price_text}"
            keyboard.append([{"text": btn_text, "callback_data": f"book_svc:{link.id}"}])

        await edit_telegram_message(
            chat_id,
            message_id,
            "📅 ¡Reserva tu llamada conmigo!\n\nElige el servicio que te interese:",
            {"inline_keyboard": keyboard},
        )
        return {"status": "ok"}


async def show_date_picker(chat_id: int, message_id: int, service_id: str, creator_id: str) -> dict:
    """Show available dates as inline buttons (next 7 days with availability)"""
    from datetime import datetime, timedelta, timezone

    from api.database import get_db_session
    from api.models import BookingLink, CreatorAvailability

    with get_db_session() as db:
        # Get service info
        service = db.query(BookingLink).filter(BookingLink.id == service_id).first()
        if not service:
            await edit_telegram_message(chat_id, message_id, "❌ Servicio no encontrado.")
            return {"status": "error"}

        # Get creator availability
        availability = (
            db.query(CreatorAvailability)
            .filter(
                CreatorAvailability.creator_id == creator_id, CreatorAvailability.is_active == True
            )
            .all()
        )

        # Build set of active days (0=Monday, 6=Sunday)
        active_days = {av.day_of_week for av in availability}

        # Generate next 7 available dates
        today = datetime.now(timezone.utc).date()
        available_dates = []
        check_date = today

        for _ in range(14):  # Check next 14 days to find 5-7 available
            weekday = check_date.weekday()  # 0=Monday
            if (
                weekday in active_days or not availability
            ):  # If no availability set, all days available
                available_dates.append(check_date)
                if len(available_dates) >= 5:
                    break
            check_date += timedelta(days=1)

        if not available_dates:
            await edit_telegram_message(
                chat_id, message_id, "❌ No hay fechas disponibles en los próximos días."
            )
            return {"status": "ok"}

        # Build keyboard with dates
        keyboard = []
        day_names_es = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

        # Add dates in rows of 3
        row = []
        for d in available_dates:
            day_name = day_names_es[d.weekday()]
            btn_text = f"{day_name} {d.day}/{d.month}"
            callback = f"book_date:{service_id}:{d.strftime('%Y-%m-%d')}"
            row.append({"text": btn_text, "callback_data": callback})
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        # Add back button
        keyboard.append([{"text": "⬅️ Volver", "callback_data": "book_back"}])

        price_text = "GRATIS" if (service.price or 0) == 0 else f"{service.price}€"
        text = f"📅 <b>{service.title}</b>\n⏱ {service.duration_minutes} min • {price_text}\n\n📆 Elige un día:"

        await edit_telegram_message(chat_id, message_id, text, {"inline_keyboard": keyboard})
        return {"status": "ok"}


async def show_time_picker(
    chat_id: int, message_id: int, service_id: str, date_str: str, creator_id: str
) -> dict:
    """Show available time slots as inline buttons"""
    import uuid as uuid_module
    from datetime import datetime, timedelta, timezone

    from api.database import get_db_session
    from api.models import BookingLink, BookingSlot, CalendarBooking, CreatorAvailability

    with get_db_session() as db:
        # Get service info
        try:
            service_uuid = uuid_module.UUID(service_id)
        except ValueError:
            await edit_telegram_message(chat_id, message_id, "❌ Servicio inválido.")
            return {"status": "error"}

        service = db.query(BookingLink).filter(BookingLink.id == service_uuid).first()
        if not service:
            await edit_telegram_message(chat_id, message_id, "❌ Servicio no encontrado.")
            return {"status": "error"}

        # Parse date
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            await edit_telegram_message(chat_id, message_id, "❌ Fecha inválida.")
            return {"status": "error"}

        # Get availability for this day
        weekday = target_date.weekday()
        availability = (
            db.query(CreatorAvailability)
            .filter(
                CreatorAvailability.creator_id == creator_id,
                CreatorAvailability.day_of_week == weekday,
                CreatorAvailability.is_active == True,
            )
            .first()
        )

        # Default hours if no availability set
        if availability:
            start_hour = availability.start_time.hour
            start_minute = availability.start_time.minute
            end_hour = availability.end_time.hour
            end_minute = availability.end_time.minute
        else:
            start_hour, start_minute = 9, 0
            end_hour, end_minute = 18, 0

        duration = service.duration_minutes or 30

        # Get already booked slots
        booked_times = set()
        booked_slots = (
            db.query(BookingSlot)
            .filter(
                BookingSlot.creator_id == creator_id,
                BookingSlot.date == target_date,
                BookingSlot.status == "booked",
            )
            .all()
        )
        for slot in booked_slots:
            booked_times.add(slot.start_time.strftime("%H:%M"))

        # Also check CalendarBooking
        external_bookings = (
            db.query(CalendarBooking)
            .filter(CalendarBooking.creator_id == creator_id, CalendarBooking.status == "scheduled")
            .all()
        )
        for booking in external_bookings:
            if booking.scheduled_at and booking.scheduled_at.date() == target_date:
                booked_times.add(booking.scheduled_at.strftime("%H:%M"))

        # Generate available slots
        slots = []
        current = datetime.combine(
            target_date, datetime.min.time().replace(hour=start_hour, minute=start_minute)
        )
        end = datetime.combine(
            target_date, datetime.min.time().replace(hour=end_hour, minute=end_minute)
        )
        now = datetime.now(timezone.utc)

        while current + timedelta(minutes=duration) <= end:
            time_str = current.strftime("%H:%M")
            slot_datetime = current.replace(tzinfo=timezone.utc)

            # Skip past slots (for today)
            if target_date == now.date() and slot_datetime <= now:
                current += timedelta(minutes=30)
                continue

            if time_str not in booked_times:
                slots.append(time_str)

            current += timedelta(minutes=30)

        if not slots:
            # No slots available - show message with back button
            keyboard = [[{"text": "⬅️ Elegir otro día", "callback_data": f"book_svc:{service_id}"}]]
            day_names_es = [
                "Lunes",
                "Martes",
                "Miércoles",
                "Jueves",
                "Viernes",
                "Sábado",
                "Domingo",
            ]
            day_name = day_names_es[target_date.weekday()]
            text = f"📅 <b>{service.title}</b>\n📆 {day_name} {target_date.day}/{target_date.month}\n\n❌ No hay horarios disponibles para este día."
            await edit_telegram_message(chat_id, message_id, text, {"inline_keyboard": keyboard})
            return {"status": "ok"}

        # Build keyboard with time slots (4 per row)
        keyboard = []
        row = []
        for time_str in slots[:12]:  # Max 12 slots
            callback = f"book_time:{service_id}:{date_str}:{time_str}"
            row.append({"text": time_str, "callback_data": callback})
            if len(row) == 4:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        # Add back button
        keyboard.append([{"text": "⬅️ Elegir otro día", "callback_data": f"book_svc:{service_id}"}])

        day_names_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        day_name = day_names_es[target_date.weekday()]
        text = f"📅 <b>{service.title}</b>\n📆 {day_name} {target_date.day}/{target_date.month}\n\n⏰ Elige una hora:"

        await edit_telegram_message(chat_id, message_id, text, {"inline_keyboard": keyboard})
        return {"status": "ok"}


async def confirm_telegram_booking(
    chat_id: int,
    message_id: int,
    service_id: str,
    date_str: str,
    time_str: str,
    user_id: str,
    user_name: str,
    creator_id: str,
) -> dict:
    """Confirm the booking and create Google Meet link"""
    import uuid as uuid_module
    from datetime import datetime, timedelta, timezone

    from api.database import get_db_session
    from api.models import BookingLink, BookingSlot, CalendarBooking, Creator, Follower

    with get_db_session() as db:
        # Get service
        try:
            service_uuid = uuid_module.UUID(service_id)
        except ValueError:
            await edit_telegram_message(chat_id, message_id, "❌ Servicio inválido.")
            return {"status": "error"}

        service = db.query(BookingLink).filter(BookingLink.id == service_uuid).first()
        if not service:
            await edit_telegram_message(chat_id, message_id, "❌ Servicio no encontrado.")
            return {"status": "error"}

        # Parse date and time
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_time = datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            await edit_telegram_message(chat_id, message_id, "❌ Fecha u hora inválida.")
            return {"status": "error"}

        duration_minutes = service.duration_minutes or 30
        scheduled_datetime = datetime.combine(target_date, start_time).replace(tzinfo=timezone.utc)
        end_datetime = scheduled_datetime + timedelta(minutes=duration_minutes)
        end_time = end_datetime.time()

        # Check if slot is still available
        existing_slot = (
            db.query(BookingSlot)
            .filter(
                BookingSlot.creator_id == creator_id,
                BookingSlot.date == target_date,
                BookingSlot.start_time == start_time,
                BookingSlot.status == "booked",
            )
            .first()
        )

        if existing_slot:
            keyboard = [
                [
                    {
                        "text": "⬅️ Elegir otro horario",
                        "callback_data": f"book_date:{service_id}:{date_str}",
                    }
                ]
            ]
            await edit_telegram_message(
                chat_id,
                message_id,
                "❌ Este horario ya no está disponible. Por favor, elige otro.",
                {"inline_keyboard": keyboard},
            )
            return {"status": "ok"}

        # Get follower info (email if we have it)
        follower = db.query(Follower).filter(Follower.platform_id == f"tg_{user_id}").first()
        guest_email = follower.email if follower and follower.email else ""
        guest_name = user_name

        # Generate Google Meet URL if Google is connected
        meeting_url = ""
        google_event_id = ""
        try:
            creator = db.query(Creator).filter(Creator.name == creator_id).first()
            if creator and creator.google_refresh_token:
                logger.info(f"Creating Google Calendar event for Telegram booking...")
                try:
                    from api.routers.oauth import create_google_meet_event
                except ImportError:
                    from routers.oauth import create_google_meet_event

                result = await create_google_meet_event(
                    creator_id=creator_id,
                    title=service.title or "Meeting",
                    start_time=scheduled_datetime,
                    end_time=end_datetime,
                    guest_email=guest_email,
                    guest_name=guest_name,
                    description=f"Telegram Booking: {service.title}",
                )
                if result.get("meet_link"):
                    meeting_url = result.get("meet_link", "")
                    google_event_id = result.get("event_id", "")
                    logger.info(f"Created Google Meet link: {meeting_url}")
        except Exception as e:
            logger.error(f"Could not create Google Meet event: {e}")

        # Create booking
        slot_id = uuid_module.uuid4()
        calendar_booking_id = uuid_module.uuid4()

        extra_data = {
            "source": "telegram_booking",
            "service_id": str(service_uuid),
            "telegram_user_id": user_id,
        }
        if google_event_id:
            extra_data["google_event_id"] = google_event_id

        # Create CalendarBooking
        calendar_booking = CalendarBooking(
            id=calendar_booking_id,
            creator_id=creator_id,
            follower_id=f"tg_{user_id}",
            meeting_type=service.title or service.meeting_type,
            platform="clonnect",
            status="scheduled",
            scheduled_at=scheduled_datetime,
            duration_minutes=duration_minutes,
            guest_name=guest_name,
            guest_email=guest_email,
            meeting_url=meeting_url,
            external_id=str(slot_id),
            extra_data=extra_data,
        )
        db.add(calendar_booking)
        db.flush()

        # Create BookingSlot
        slot = BookingSlot(
            id=slot_id,
            creator_id=creator_id,
            service_id=service_uuid,
            date=target_date,
            start_time=start_time,
            end_time=end_time,
            status="booked",
            booked_by_name=guest_name,
            booked_by_email=guest_email,
            meeting_url=meeting_url,
            calendar_booking_id=calendar_booking_id,
        )
        db.add(slot)
        db.commit()

        logger.info(
            f"Telegram booking confirmed: {service.title} on {date_str} at {time_str} for {guest_name}"
        )

        # Format confirmation message
        day_names_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        month_names_es = [
            "",
            "Enero",
            "Febrero",
            "Marzo",
            "Abril",
            "Mayo",
            "Junio",
            "Julio",
            "Agosto",
            "Septiembre",
            "Octubre",
            "Noviembre",
            "Diciembre",
        ]
        day_name = day_names_es[target_date.weekday()]
        month_name = month_names_es[target_date.month]
        end_time_str = end_datetime.strftime("%H:%M")

        text = f"✅ <b>¡Reserva confirmada!</b>\n\n"
        text += f"📅 {day_name} {target_date.day} de {month_name}\n"
        text += f"⏰ {time_str} - {end_time_str}\n"
        text += f"📋 {service.title}\n\n"

        keyboard = []
        if meeting_url:
            text += f"🔗 <a href='{meeting_url}'>Enlace a la videollamada</a>\n\n"
            keyboard.append([{"text": "🎥 Abrir Meet", "url": meeting_url}])

        text += "¡Nos vemos pronto! 👋"

        reply_markup = {"inline_keyboard": keyboard} if keyboard else None
        await edit_telegram_message(chat_id, message_id, text, reply_markup)

        return {"status": "ok", "booking_id": str(calendar_booking_id)}


@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    Recibir updates de Telegram - MULTI-BOT SUPPORT.
    Detecta qué bot recibió el mensaje y usa el creator_id correcto.
    """
    try:
        payload = await request.json()
        logger.info(f"Telegram webhook received: {payload}")

        # === DEDUPLICATION CHECK ===
        update_id = payload.get("update_id")
        if update_id and await _check_telegram_duplicate(update_id):
            return {"status": "ok", "message": "Duplicate update - already processed"}

        # Handle callback_query (button clicks for booking flow)
        callback_query = payload.get("callback_query")
        if callback_query:
            return await handle_telegram_booking_callback(callback_query)

        # Extraer mensaje del update
        message = payload.get("message", {})
        if not message:
            return {"status": "ok", "message": "No message in update"}

        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")
        sender = message.get("from", {})
        sender_id = str(sender.get("id", "unknown"))
        sender_name = sender.get("first_name", "") + " " + sender.get("last_name", "")
        sender_name = sender_name.strip() or sender.get("username", "Usuario")

        if not chat_id or not text:
            return {"status": "ok", "message": "No chat_id or text"}

        # === MULTI-BOT: Detect which bot received this message ===
        # The bot info comes in the "message.via_bot" field for inline results,
        # but for regular messages we need to extract from the update
        # Telegram doesn't send bot_id directly, but we can use the registry
        # to find the bot based on configured bots
        registry = get_telegram_registry()

        # Try to detect bot from message context
        # For now, we'll use a header or query param approach for multi-bot
        # Or fall back to checking all registered bots
        bot_id = None
        creator_id = None
        bot_token = None

        # Check if there's a registered bot - use first active one for now
        # In production, you'd use a bot-specific webhook URL like /webhook/telegram/{bot_id}
        bots = registry.list_bots()
        if bots:
            # Use the first active bot (Stefano's bot)
            for bot in bots:
                if bot.get("is_active"):
                    bot_id = bot.get("bot_id")
                    creator_id = bot.get("creator_id")
                    bot_token = registry.get_bot_token(bot_id)
                    logger.info(f"Using registered bot {bot_id} for creator {creator_id}")
                    break

        # Fallback to env var if no registered bot
        if not creator_id:
            creator_id = os.getenv("DEFAULT_CREATOR_ID", "stefano_auto")
            bot_token = TELEGRAM_BOT_TOKEN
            logger.info(f"Using fallback creator_id={creator_id}")

        try:
            import time

            _t_webhook_start = time.time()

            agent = get_dm_agent(creator_id)
            _t_agent_ready = time.time()
            logger.info(f"⏱️ Agent ready in {_t_agent_ready - _t_webhook_start:.3f}s")

            first_name = sender.get("first_name", "")
            last_name = sender.get("last_name", "")
            full_name = f"{first_name} {last_name}".strip()

            response = await agent.process_dm(
                sender_id=f"tg_{sender_id}",
                message_text=text,
                message_id=str(message.get("message_id", "")),
                username=sender_name,
                name=full_name,
            )
            _t_process_done = time.time()
            logger.info(f"⏱️ process_dm completed in {_t_process_done - _t_agent_ready:.2f}s")

            bot_reply = response.response_text
            intent = response.intent.value if response.intent else "unknown"

            logger.info(
                f"Telegram DM from {sender_name} ({sender_id}): '{text[:50]}' -> intent={intent}, creator={creator_id}"
            )

            # === CHECK COPILOT MODE (CACHED - 5min TTL) ===
            _t_copilot_start = time.time()
            copilot_enabled = _get_copilot_mode_cached(creator_id)
            logger.info(f"⏱️ Copilot mode check took {time.time() - _t_copilot_start:.3f}s (cached)")

            if copilot_enabled:
                # COPILOT MODE: Save as pending approval, don't send
                logger.info(
                    f"🟢🟢🟢 COPILOT MODE ACTIVE - NOT sending auto-reply, creating pending response 🟢🟢🟢"
                )
                from core.copilot_service import get_copilot_service

                copilot = get_copilot_service()

                pending = await copilot.create_pending_response(
                    creator_id=creator_id,
                    lead_id="",
                    follower_id=f"tg_{sender_id}",
                    platform="telegram",
                    user_message=text,
                    user_message_id=str(message.get("message_id", "")),
                    suggested_response=bot_reply,
                    intent=intent,
                    confidence=response.confidence if hasattr(response, "confidence") else 0.9,
                    username=sender_name,
                    full_name=full_name,
                )

                logger.info(
                    f"[Copilot] Created pending response {pending.id} for Telegram user {sender_name}"
                )

                return {
                    "status": "ok",
                    "chat_id": chat_id,
                    "intent": intent,
                    "creator_id": creator_id,
                    "bot_id": bot_id,
                    "copilot_mode": True,
                    "pending_response_id": pending.id,
                    "response_sent": False,
                }

            # AUTOPILOT MODE: Send response immediately
            logger.info(f"🔴🔴🔴 AUTOPILOT MODE - sending auto-reply immediately 🔴🔴🔴")
            # Build inline keyboard if present in metadata
            reply_markup = None
            if response.metadata and "telegram_keyboard" in response.metadata:
                keyboard_data = response.metadata["telegram_keyboard"]
                if keyboard_data:
                    inline_keyboard = []
                    for button in keyboard_data:
                        btn = {"text": button.get("text", "")}
                        if "callback_data" in button:
                            btn["callback_data"] = button["callback_data"]
                        elif "url" in button:
                            btn["url"] = button["url"]
                        inline_keyboard.append([btn])
                    reply_markup = {"inline_keyboard": inline_keyboard}
                    logger.info(f"Sending {len(keyboard_data)} inline buttons for booking")

            # CRITICAL: Send Telegram FIRST, THEN return
            # This is only ~0.3s direct API call - user sees response immediately
            # DB saves happen in background AFTER this
            telegram_sent = False
            if bot_reply and bot_token:
                try:
                    _t_tg_start = time.time()
                    result = await send_telegram_message(
                        chat_id, bot_reply, bot_token, reply_markup
                    )
                    _t_tg_end = time.time()
                    if result.get("ok"):
                        telegram_sent = True
                        logger.info(
                            f"⏱️ Telegram sent in {_t_tg_end - _t_tg_start:.2f}s to chat {chat_id}"
                        )
                    else:
                        logger.error(f"Telegram send failed: {result}")
                except Exception as e:
                    logger.error(f"Telegram send error: {e}")

            _t_webhook_end = time.time()
            logger.info(
                f"⏱️ TOTAL webhook processing: {_t_webhook_end - _t_webhook_start:.2f}s (user perceived)"
            )

            return {
                "status": "ok",
                "chat_id": chat_id,
                "intent": intent,
                "creator_id": creator_id,
                "bot_id": bot_id,
                "copilot_mode": False,
                "response_sent": telegram_sent,
            }

        except Exception as e:
            logger.error(f"Error processing Telegram message: {type(e).__name__}: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            return {"status": "error", "detail": str(e)}

    except Exception as e:
        logger.error(f"Error in Telegram webhook: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Legacy endpoint for Telegram (some setups use /telegram/webhook instead of /webhook/telegram)
@app.post("/telegram/webhook")
async def telegram_webhook_legacy(request: Request):
    """Legacy endpoint - redirects to /webhook/telegram"""
    return await telegram_webhook(request)


# ---------------------------------------------------------
# WHATSAPP WEBHOOK
# ---------------------------------------------------------
# WhatsApp handler singleton
_whatsapp_handler = None


def get_whatsapp_handler():
    """Get or create WhatsApp handler singleton"""
    global _whatsapp_handler
    if _whatsapp_handler is None:
        try:
            from core.whatsapp import WhatsAppHandler

            _whatsapp_handler = WhatsAppHandler()
        except Exception as e:
            logger.error(f"Error initializing WhatsApp handler: {e}")
            raise HTTPException(status_code=500, detail="WhatsApp handler not available")
    return _whatsapp_handler


@app.get("/webhook/whatsapp")
async def whatsapp_webhook_verify(request: Request):
    """
    WhatsApp webhook verification (GET).
    Meta sends GET request to verify the endpoint before activating webhooks.
    """
    params = dict(request.query_params)
    mode = params.get("hub.mode", "")
    token = params.get("hub.verify_token", "")
    challenge = params.get("hub.challenge", "")

    handler = get_whatsapp_handler()
    result = handler.connector.verify_webhook(mode, token, challenge)

    if result:
        logger.info("WhatsApp webhook verified successfully")
        return Response(content=result, media_type="text/plain")

    logger.warning("WhatsApp webhook verification failed")
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook/whatsapp")
async def whatsapp_webhook_receive(request: Request):
    """
    Receive WhatsApp webhook events (POST).
    Processes incoming DMs with DMResponderAgent and sends automatic responses.
    """
    logger.warning("=" * 60)
    logger.warning("========== WHATSAPP WEBHOOK HIT ==========")
    logger.warning("=" * 60)

    try:
        payload = await request.json()
        signature = request.headers.get("X-Hub-Signature-256", "")

        handler = get_whatsapp_handler()
        result = await handler.handle_webhook(payload, signature)

        logger.info(f"WhatsApp webhook processed: {result.get('messages_processed', 0)} messages")
        return result

    except Exception as e:
        logger.error(f"Error processing WhatsApp webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/whatsapp/status")
async def whatsapp_status():
    """Get WhatsApp handler status"""
    try:
        handler = get_whatsapp_handler()
        return {
            "status": "ok",
            "handler": handler.get_status(),
            "recent_messages": handler.get_recent_messages(5),
            "recent_responses": handler.get_recent_responses(5),
        }
    except Exception as e:
        return {
            "status": "error",
            "phone_number_id_configured": bool(os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")),
            "access_token_configured": bool(os.getenv("WHATSAPP_ACCESS_TOKEN", "")),
            "webhook_url": "/webhook/whatsapp",
            "error": str(e),
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
# PAYMENTS
# ---------------------------------------------------------
@app.get("/payments/{creator_id}/purchases")
async def get_purchases(creator_id: str, limit: int = 100, status: Optional[str] = None):
    """
    Get all purchases for a creator.

    Optional filter by status: completed, refunded, cancelled
    """
    try:
        payment_manager = get_payment_manager()
        purchases = payment_manager.get_all_purchases(
            creator_id=creator_id, limit=limit, status=status
        )

        return {
            "status": "ok",
            "creator_id": creator_id,
            "purchases": purchases,
            "count": len(purchases),
        }

    except Exception as e:
        logger.error(f"Error getting purchases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


@app.get("/payments/{creator_id}/revenue")
async def get_revenue_stats(creator_id: str, days: int = 30):
    """
    Get revenue statistics.

    Returns:
    - Total revenue
    - Bot-attributed revenue
    - Revenue by platform (Stripe/Hotmart)
    - Revenue by product
    """
    try:
        payment_manager = get_payment_manager()
        stats = payment_manager.get_revenue_stats(creator_id=creator_id, days=days)

        return {"status": "ok", "creator_id": creator_id, "days": days, **stats.to_dict()}

    except Exception as e:
        logger.error(f"Error getting revenue stats: {e}")
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
# CALENDAR
# ---------------------------------------------------------
@app.get("/calendar/{creator_id}/bookings")
async def get_bookings(
    creator_id: str, status: Optional[str] = None, upcoming: bool = False, limit: int = 100
):
    """
    Get bookings for a creator.

    Optional filters:
    - status: scheduled, completed, cancelled, no_show
    - upcoming: only future bookings
    """
    try:
        calendar_manager = get_calendar_manager()
        bookings = calendar_manager.get_bookings(
            creator_id=creator_id, status=status, upcoming_only=upcoming, limit=limit
        )

        return {
            "status": "ok",
            "creator_id": creator_id,
            "bookings": bookings,
            "count": len(bookings),
        }

    except Exception as e:
        logger.error(f"Error getting bookings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


@app.get("/debug/agent-config/{creator_id}")
async def debug_agent_config(creator_id: str):
    """Debug: ver qué config carga el DMAgent"""
    from core.dm_agent import DMResponderAgent

    agent = DMResponderAgent(creator_id=creator_id)
    vocab = agent.creator_config.get("clone_vocabulary", "")

    # Detect preset like dm_agent does
    vocab_lower = vocab.lower() if vocab else ""
    detected_preset = None
    if "trata de usted" in vocab_lower or "evita emojis" in vocab_lower:
        detected_preset = "profesional"
    elif "ve al grano" in vocab_lower or "llamadas a la acción" in vocab_lower:
        detected_preset = "vendedor"
    elif "posiciónate como experto" in vocab_lower or "da consejos prácticos" in vocab_lower:
        detected_preset = "mentor"
    elif "tutea siempre" in vocab_lower or "amigo de confianza" in vocab_lower:
        detected_preset = "amigo"

    return {
        "clone_tone": agent.creator_config.get("clone_tone"),
        "clone_name": agent.creator_config.get("clone_name"),
        "clone_vocabulary": vocab[:500] if vocab else "(empty)",
        "clone_vocabulary_length": len(vocab) if vocab else 0,
        "detected_preset": detected_preset,
        "name": agent.creator_config.get("name"),
        "config_keys": list(agent.creator_config.keys()),
    }


@app.get("/debug/system-prompt/{creator_id}")
async def debug_system_prompt(creator_id: str):
    """Debug: ver el system prompt que genera el DMAgent"""
    from core.dm_agent import DMResponderAgent

    agent = DMResponderAgent(creator_id=creator_id)
    prompt = agent._build_system_prompt()
    return {"prompt": prompt[:2000]}  # Primeros 2000 chars


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
