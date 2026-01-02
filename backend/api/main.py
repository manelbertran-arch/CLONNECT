"""
Clonnect Creators API
API simplificada para el clon de IA de creadores de contenido
"""

import os
import json
import logging
import time
import shutil
import httpx
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Request, Depends, Header, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, HTMLResponse, PlainTextResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)

# PostgreSQL Init - define defaults first
SessionLocal = None
BookingLinkModel = None
CalendarBookingModel = None
DATABASE_URL = None

try:
    from api.database import DATABASE_URL, get_db, SessionLocal
    from api.init_db import init_database
    from api.models import BookingLink as BookingLinkModel, CalendarBooking as CalendarBookingModel
    if DATABASE_URL:
        init_database()
        print(f"PostgreSQL connected - SessionLocal={SessionLocal is not None}")
    else:
        print("No DATABASE_URL - using JSON fallback")
except Exception as e:
    print(f"PostgreSQL init failed: {e}")
    import traceback
    traceback.print_exc()

# Database service
try:
    from api import db_service
    USE_DB = True
    print("Database service loaded")
except Exception as e:
    USE_DB = False
    print(f"Database service not available: {e}")

logging.warning("=" * 60)
logging.warning("========== API MAIN V7 LOADED ==========")

# Core imports
from core.products import ProductManager, Product
from core.creator_config import CreatorConfigManager, CreatorConfig
from core.dm_agent import DMResponderAgent
from core.rag import SimpleRAG
from core.llm import get_llm_client
from core.memory import MemoryStore
from core.instagram_handler import InstagramHandler, get_instagram_handler
from core.whatsapp import get_whatsapp_handler
from core.gdpr import get_gdpr_manager, ConsentType
from core.payments import get_payment_manager
from core.calendar import get_calendar_manager
from core.auth import get_auth_manager, validate_api_key, is_admin_key
from core.alerts import get_alert_manager
from core.metrics import get_metrics, get_content_type, MetricsMiddleware, record_message_processed, update_health_status, PROMETHEUS_AVAILABLE
logging.warning("=" * 60)

logger = logging.getLogger(__name__)

# Instancias globales
product_manager = ProductManager()
config_manager = CreatorConfigManager()
memory_store = MemoryStore()
rag = SimpleRAG()

# FastAPI
app = FastAPI(
    title="Clonnect Creators",
    description="API para el clon de IA de creadores de contenido",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Metrics middleware
if PROMETHEUS_AVAILABLE:
    app.add_middleware(MetricsMiddleware)


# ---------------------------------------------------------

# ---------------------------------------------------------
# ROUTERS (modularized endpoints)
# ---------------------------------------------------------
from api.routers import health, dashboard, config, leads, products

app.include_router(health.router)
app.include_router(dashboard.router)
app.include_router(config.router)
app.include_router(leads.router)
app.include_router(products.router)

# Additional routers
from api.routers import messages, payments, calendar, nurturing
app.include_router(messages.router)
app.include_router(payments.router)
app.include_router(calendar.router)
app.include_router(nurturing.router)
from api.routers import knowledge, analytics, onboarding, admin, connections, oauth, booking
app.include_router(knowledge.router)
app.include_router(analytics.router)
app.include_router(onboarding.router)
app.include_router(admin.router)
app.include_router(connections.router)
app.include_router(oauth.router)
app.include_router(booking.router)

logging.info("Routers loaded: health, dashboard, config, leads, products, analytics, connections, oauth, booking")
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
    "/telegram/webhook",   # Legacy
}


async def get_current_creator(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> str:
    """
    Dependency para obtener el creator_id del API key.
    Lanza HTTPException 401 si no hay key o es invalida.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Include X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    creator_id = validate_api_key(x_api_key)

    if not creator_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired API key.",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    return creator_id


async def get_optional_creator(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> Optional[str]:
    """
    Dependency opcional - retorna creator_id o None.
    No lanza excepcion si no hay key.
    """
    if not x_api_key:
        return None

    return validate_api_key(x_api_key)


async def require_admin(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> str:
    """
    Dependency que requiere admin key.
    Lanza HTTPException 403 si no es admin.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required.",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    if is_admin_key(x_api_key):
        return "__admin__"

    raise HTTPException(
        status_code=403,
        detail="Admin privileges required for this operation."
    )


async def require_creator_or_admin(
    creator_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> str:
    """
    Verifica que el API key pertenece al creator_id o es admin.
    """
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required.",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    if is_admin_key(x_api_key):
        return "__admin__"

    key_creator_id = validate_api_key(x_api_key)

    if not key_creator_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key."
        )

    if key_creator_id != creator_id:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to access this creator's data."
        )

    return key_creator_id


# ---------------------------------------------------------
# PYDANTIC MODELS
# ---------------------------------------------------------
class ProcessDMRequest(BaseModel):
    creator_id: str
    sender_id: str
    message: str
    message_id: str = ""


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


class SendMessageRequest(BaseModel):
    """Request to send a manual message to a follower"""
    follower_id: str
    message: str


class UpdateLeadStatusRequest(BaseModel):
    """Request to update lead status in pipeline"""
    status: str  # cold, warm, hot, customer


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
        response = await llm_client.generate(
            prompt="Responde solo 'ok'",
            max_tokens=5
        )

        latency_ms = int((time.time() - start) * 1000)

        return {
            "status": "ok",
            "latency_ms": latency_ms,
            "provider": os.getenv("LLM_PROVIDER", "openai")
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "provider": os.getenv("LLM_PROVIDER", "openai")
        }


def check_disk_health() -> Dict[str, Any]:
    """Verifica espacio en disco"""
    try:
        data_path = os.getenv("DATA_PATH", "./data")

        # Obtener info del disco
        total, used, free = shutil.disk_usage(data_path)
        free_gb = round(free / (1024 ** 3), 2)

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
            "total_gb": round(total / (1024 ** 3), 2),
            "used_percent": round((used / total) * 100, 1)
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_memory_health() -> Dict[str, Any]:
    """Verifica memoria RAM disponible"""
    try:
        if not PSUTIL_AVAILABLE:
            return {"status": "unknown", "error": "psutil not installed"}

        mem = psutil.virtual_memory()
        free_mb = round(mem.available / (1024 ** 2), 1)

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
            "total_mb": round(mem.total / (1024 ** 2), 1),
            "used_percent": round(mem.percent, 1)
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
            return {
                "status": "warning",
                "path": data_path,
                "missing_subdirs": missing
            }

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

        return {
            "status": "ok" if writable else "error",
            "path": data_path,
            "writable": writable
        }
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
        "data_dir": check_data_dir_health()
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
                check_name="system",
                status=overall_status,
                details=failed_checks
            )
        except Exception as e:
            logger.debug(f"Could not send health alert: {e}")

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "version": VERSION,
        "service": "clonnect-creators"
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
        "error": None
    }

    if SessionLocal and BookingLinkModel:
        try:
            from sqlalchemy import text
            db = SessionLocal()
            try:
                # Check tables
                tables_result = db.execute(text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                ))
                result["tables"] = [row[0] for row in tables_result.fetchall()]

                # Check booking_links
                if "booking_links" in result["tables"]:
                    count_result = db.execute(text("SELECT COUNT(*) FROM booking_links"))
                    result["booking_links_count"] = count_result.scalar()

                    # Get sample data
                    sample_result = db.execute(text(
                        "SELECT id, creator_id, meeting_type, title, platform FROM booking_links LIMIT 5"
                    ))
                    result["booking_links_sample"] = [
                        {"id": str(row[0]), "creator_id": row[1], "meeting_type": row[2], "title": row[3], "platform": row[4]}
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
        "BookingLinkModel": BookingLinkModel is not None
    }

    # Try direct SQL insert first
    if SessionLocal:
        try:
            from sqlalchemy import text
            import uuid

            db = SessionLocal()
            try:
                test_id = str(uuid.uuid4())

                # Direct SQL INSERT
                db.execute(text("""
                    INSERT INTO booking_links (id, creator_id, meeting_type, title, duration_minutes, platform, is_active)
                    VALUES (:id, :creator_id, :meeting_type, :title, :duration, :platform, :is_active)
                """), {
                    "id": test_id,
                    "creator_id": "test_debug",
                    "meeting_type": "debug_test",
                    "title": "Debug Test Link",
                    "duration": 30,
                    "platform": "manual",
                    "is_active": True
                })
                db.commit()

                result["success"] = True
                result["link_id"] = test_id
                result["message"] = "Direct SQL INSERT worked!"

                # Verify it was inserted
                verify = db.execute(text("SELECT COUNT(*) FROM booking_links WHERE creator_id = 'test_debug'"))
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
            return {
                "status": "error",
                "ready": False,
                "reason": "data_dir_not_accessible"
            }

        # Verificar LLM
        llm_check = await check_llm_health()
        if llm_check.get("status") == "error":
            return {
                "status": "error",
                "ready": False,
                "reason": "llm_not_accessible",
                "llm_error": llm_check.get("error")
            }

        return {
            "status": "ok",
            "ready": True,
            "llm_latency_ms": llm_check.get("latency_ms")
        }

    except Exception as e:
        return {
            "status": "error",
            "ready": False,
            "reason": str(e)
        }


@app.get("/")
def root():
    """API info"""
    return {
        "name": "Clonnect Creators API",
        "version": VERSION,
        "description": "Tu clon de IA para responder DMs de Instagram",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics",
        "privacy": "/privacy",
        "terms": "/terms"
    }


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
    return Response(
        content=get_metrics(),
        media_type=get_content_type()
    )


# ---------------------------------------------------------
# AUTHENTICATION ENDPOINTS
# ---------------------------------------------------------
class CreateAPIKeyRequest(BaseModel):
    creator_id: str
    name: Optional[str] = None


@app.post("/auth/keys")
async def create_api_key(
    request: CreateAPIKeyRequest,
    admin: str = Depends(require_admin)
):
    """
    Crear una nueva API key para un creador.
    Requiere admin key.

    La API key completa solo se muestra una vez.
    Guardala de forma segura.
    """
    auth_manager = get_auth_manager()
    api_key = auth_manager.generate_api_key(
        creator_id=request.creator_id,
        name=request.name
    )

    return {
        "status": "ok",
        "api_key": api_key,
        "creator_id": request.creator_id,
        "warning": "Save this key securely. It will not be shown again."
    }


@app.get("/auth/keys")
async def list_all_api_keys(
    admin: str = Depends(require_admin)
):
    """
    Listar todas las API keys (solo admin).
    No muestra las keys completas, solo prefijos.
    """
    auth_manager = get_auth_manager()
    keys = auth_manager.list_all_keys()

    return {
        "status": "ok",
        "keys": keys,
        "count": len(keys)
    }


@app.get("/auth/keys/{creator_id}")
async def list_creator_api_keys(
    creator_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """
    Listar API keys de un creador.
    Requiere ser el creador o admin.
    """
    # Verificar permisos
    await require_creator_or_admin(creator_id, x_api_key)

    auth_manager = get_auth_manager()
    keys = auth_manager.list_api_keys(creator_id)

    return {
        "status": "ok",
        "creator_id": creator_id,
        "keys": keys,
        "count": len(keys)
    }


@app.delete("/auth/keys/{key_prefix}")
async def revoke_api_key(
    key_prefix: str,
    admin: str = Depends(require_admin)
):
    """
    Revocar una API key.
    Requiere admin key.

    Usa el prefijo de la key (ej: clk_abc12345)
    """
    auth_manager = get_auth_manager()

    # Obtener info de la key para verificar que existe
    key_info = auth_manager.get_key_info(key_prefix)
    if not key_info:
        raise HTTPException(status_code=404, detail="API key not found")

    success = auth_manager.revoke_api_key(key_prefix)

    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    return {
        "status": "ok",
        "revoked": True,
        "key_prefix": key_prefix,
        "creator_id": key_info.get("creator_id")
    }


@app.get("/auth/verify")
async def verify_api_key(
    current_creator: str = Depends(get_current_creator)
):
    """
    Verificar que una API key es valida.
    Retorna el creator_id asociado.
    """
    return {
        "status": "ok",
        "valid": True,
        "creator_id": current_creator,
        "is_admin": current_creator == "__admin__"
    }


# ---------------------------------------------------------
# BOT CONTROL (Pause/Resume)
# ---------------------------------------------------------
class PauseBotRequest(BaseModel):
    reason: Optional[str] = None


@app.post("/bot/{creator_id}/pause")
async def pause_bot(
    creator_id: str,
    request: PauseBotRequest = PauseBotRequest(),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """
    Pausar el bot para un creador.
    Los mensajes entrantes no seran respondidos.
    """
    await require_creator_or_admin(creator_id, x_api_key)

    success = config_manager.set_active(creator_id, False, request.reason or "Pausado manualmente")

    if not success:
        raise HTTPException(status_code=404, detail="Creator not found")

    logger.info(f"Bot paused for creator {creator_id}")

    return {
        "status": "ok",
        "creator_id": creator_id,
        "bot_active": False,
        "reason": request.reason or "Pausado manualmente"
    }


@app.post("/bot/{creator_id}/resume")
async def resume_bot(
    creator_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """
    Reanudar el bot para un creador.
    El bot volvera a responder mensajes.
    """
    await require_creator_or_admin(creator_id, x_api_key)

    success = config_manager.set_active(creator_id, True)

    if not success:
        raise HTTPException(status_code=404, detail="Creator not found")

    logger.info(f"Bot resumed for creator {creator_id}")

    return {
        "status": "ok",
        "creator_id": creator_id,
        "bot_active": True
    }


@app.get("/bot/{creator_id}/status")
async def get_bot_status(
    creator_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """
    Obtener estado del bot para un creador.
    """
    await require_creator_or_admin(creator_id, x_api_key)

    status = config_manager.get_bot_status(creator_id)

    if not status.get("exists"):
        raise HTTPException(status_code=404, detail="Creator not found")

    return {
        "status": "ok",
        "creator_id": creator_id,
        **status
    }


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
        "recent_responses": handler.get_recent_responses(5)
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

        return {
            "status": "ok",
            "comments_processed": len(results),
            "results": results
        }

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
        "recent_responses": handler.get_recent_responses(5)
    }

# ---------------------------------------------------------
# TELEGRAM WEBHOOK
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL", "")  # Cloudflare Worker URL
TELEGRAM_PROXY_SECRET = os.getenv("TELEGRAM_PROXY_SECRET", "")


async def send_telegram_via_proxy(chat_id: int, text: str, bot_token: str, reply_markup: dict = None) -> dict:
    """Send Telegram message via Cloudflare Worker proxy"""
    headers = {}
    if TELEGRAM_PROXY_SECRET:
        headers["X-Telegram-Proxy-Secret"] = TELEGRAM_PROXY_SECRET

    params = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        params["reply_markup"] = reply_markup

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            TELEGRAM_PROXY_URL,
            json={
                "bot_token": bot_token,
                "method": "sendMessage",
                "params": params
            },
            headers=headers
        )
        return response.json()


async def send_telegram_direct(chat_id: int, text: str, bot_token: str, reply_markup: dict = None) -> dict:
    """Send Telegram message directly (for environments without blocking)"""
    telegram_api = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    async with httpx.AsyncClient() as client:
        response = await client.post(telegram_api, json=payload)
        return response.json()


async def send_telegram_message(chat_id: int, text: str, bot_token: str, reply_markup: dict = None) -> dict:
    """Send Telegram message - uses proxy if configured, otherwise direct"""
    if TELEGRAM_PROXY_URL:
        logger.info(f"Sending Telegram message via proxy to chat {chat_id}")
        if not TELEGRAM_PROXY_SECRET:
            logger.warning("TELEGRAM_PROXY_SECRET not set - proxy may reject request if it requires auth")
        return await send_telegram_via_proxy(chat_id, text, bot_token, reply_markup)
    else:
        logger.info(f"Sending Telegram message directly to chat {chat_id}")
        return await send_telegram_direct(chat_id, text, bot_token, reply_markup)


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
                json={"bot_token": TELEGRAM_BOT_TOKEN, "method": "answerCallbackQuery", "params": payload},
                headers=headers
            )
            return response.json()
    else:
        async with httpx.AsyncClient() as client:
            response = await client.post(telegram_api, json=payload)
            return response.json()


async def edit_telegram_message(chat_id: int, message_id: int, text: str, reply_markup: dict = None) -> dict:
    """Edit an existing Telegram message"""
    telegram_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    if TELEGRAM_PROXY_URL:
        headers = {}
        if TELEGRAM_PROXY_SECRET:
            headers["X-Telegram-Proxy-Secret"] = TELEGRAM_PROXY_SECRET
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                TELEGRAM_PROXY_URL,
                json={"bot_token": TELEGRAM_BOT_TOKEN, "method": "editMessageText", "params": payload},
                headers=headers
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
    from api.models import BookingLink, CalendarBooking, CreatorAvailability, BookingSlot, Creator, Follower

    callback_id = callback_query.get("id")
    data = callback_query.get("data", "")
    chat_id = callback_query.get("message", {}).get("chat", {}).get("id")
    message_id = callback_query.get("message", {}).get("message_id")
    user = callback_query.get("from", {})
    user_id = str(user.get("id", "unknown"))
    user_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip() or user.get('username', 'Usuario')

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
            return await confirm_telegram_booking(chat_id, message_id, service_id, date_str, time_str, user_id, user_name, creator_id)

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
        await send_telegram_message(chat_id, f"❌ Error al procesar tu solicitud. Por favor, intenta de nuevo.", TELEGRAM_BOT_TOKEN)
        return {"status": "error", "detail": str(e)}


async def show_service_picker(chat_id: int, message_id: int, creator_id: str) -> dict:
    """Show available services as inline buttons"""
    from api.database import get_db_session
    from api.models import BookingLink

    with get_db_session() as db:
        links = db.query(BookingLink).filter(
            BookingLink.creator_id == creator_id,
            BookingLink.is_active == True
        ).all()

        if not links:
            await edit_telegram_message(chat_id, message_id, "No hay servicios disponibles actualmente.")
            return {"status": "ok"}

        keyboard = []
        for link in links:
            price_text = "GRATIS" if (link.price or 0) == 0 else f"{link.price}€"
            btn_text = f"📅 {link.title} ({link.duration_minutes} min) - {price_text}"
            keyboard.append([{"text": btn_text, "callback_data": f"book_svc:{link.id}"}])

        await edit_telegram_message(
            chat_id, message_id,
            "📅 ¡Reserva tu llamada conmigo!\n\nElige el servicio que te interese:",
            {"inline_keyboard": keyboard}
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
        availability = db.query(CreatorAvailability).filter(
            CreatorAvailability.creator_id == creator_id,
            CreatorAvailability.is_active == True
        ).all()

        # Build set of active days (0=Monday, 6=Sunday)
        active_days = {av.day_of_week for av in availability}

        # Generate next 7 available dates
        today = datetime.now(timezone.utc).date()
        available_dates = []
        check_date = today

        for _ in range(14):  # Check next 14 days to find 5-7 available
            weekday = check_date.weekday()  # 0=Monday
            if weekday in active_days or not availability:  # If no availability set, all days available
                available_dates.append(check_date)
                if len(available_dates) >= 5:
                    break
            check_date += timedelta(days=1)

        if not available_dates:
            await edit_telegram_message(chat_id, message_id, "❌ No hay fechas disponibles en los próximos días.")
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


async def show_time_picker(chat_id: int, message_id: int, service_id: str, date_str: str, creator_id: str) -> dict:
    """Show available time slots as inline buttons"""
    from datetime import datetime, timedelta, timezone
    from api.database import get_db_session
    from api.models import BookingLink, CreatorAvailability, BookingSlot, CalendarBooking
    import uuid as uuid_module

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
        availability = db.query(CreatorAvailability).filter(
            CreatorAvailability.creator_id == creator_id,
            CreatorAvailability.day_of_week == weekday,
            CreatorAvailability.is_active == True
        ).first()

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
        booked_slots = db.query(BookingSlot).filter(
            BookingSlot.creator_id == creator_id,
            BookingSlot.date == target_date,
            BookingSlot.status == "booked"
        ).all()
        for slot in booked_slots:
            booked_times.add(slot.start_time.strftime("%H:%M"))

        # Also check CalendarBooking
        external_bookings = db.query(CalendarBooking).filter(
            CalendarBooking.creator_id == creator_id,
            CalendarBooking.status == "scheduled"
        ).all()
        for booking in external_bookings:
            if booking.scheduled_at and booking.scheduled_at.date() == target_date:
                booked_times.add(booking.scheduled_at.strftime("%H:%M"))

        # Generate available slots
        slots = []
        current = datetime.combine(target_date, datetime.min.time().replace(hour=start_hour, minute=start_minute))
        end = datetime.combine(target_date, datetime.min.time().replace(hour=end_hour, minute=end_minute))
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
            day_names_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
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


async def confirm_telegram_booking(chat_id: int, message_id: int, service_id: str, date_str: str, time_str: str, user_id: str, user_name: str, creator_id: str) -> dict:
    """Confirm the booking and create Google Meet link"""
    from datetime import datetime, timedelta, timezone
    from api.database import get_db_session
    from api.models import BookingLink, CalendarBooking, BookingSlot, Creator, Follower
    import uuid as uuid_module

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
        existing_slot = db.query(BookingSlot).filter(
            BookingSlot.creator_id == creator_id,
            BookingSlot.date == target_date,
            BookingSlot.start_time == start_time,
            BookingSlot.status == "booked"
        ).first()

        if existing_slot:
            keyboard = [[{"text": "⬅️ Elegir otro horario", "callback_data": f"book_date:{service_id}:{date_str}"}]]
            await edit_telegram_message(chat_id, message_id, "❌ Este horario ya no está disponible. Por favor, elige otro.", {"inline_keyboard": keyboard})
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
                except:
                    from routers.oauth import create_google_meet_event

                result = await create_google_meet_event(
                    creator_id=creator_id,
                    title=service.title or "Meeting",
                    start_time=scheduled_datetime,
                    end_time=end_datetime,
                    guest_email=guest_email,
                    guest_name=guest_name,
                    description=f"Telegram Booking: {service.title}"
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
            "telegram_user_id": user_id
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
            extra_data=extra_data
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
            calendar_booking_id=calendar_booking_id
        )
        db.add(slot)
        db.commit()

        logger.info(f"Telegram booking confirmed: {service.title} on {date_str} at {time_str} for {guest_name}")

        # Format confirmation message
        day_names_es = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
        month_names_es = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
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
    Recibir updates de Telegram.
    Procesa mensajes entrantes con DMResponderAgent y envia respuestas automaticas.
    Tambien maneja callback_query para el flujo de reservas in-Telegram.
    """
    try:
        payload = await request.json()
        logger.info(f"Telegram webhook received: {payload}")

        # Handle callback_query (button clicks for booking flow)
        callback_query = payload.get("callback_query")
        if callback_query:
            return await handle_telegram_booking_callback(callback_query)

        # Extraer mensaje del update
        message = payload.get("message", {})
        if not message:
            # Puede ser un callback_query u otro tipo de update
            return {"status": "ok", "message": "No message in update"}

        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")
        sender = message.get("from", {})
        sender_id = str(sender.get("id", "unknown"))
        sender_name = sender.get("first_name", "") + " " + sender.get("last_name", "")
        sender_name = sender_name.strip() or sender.get("username", "Usuario")

        if not chat_id or not text:
            return {"status": "ok", "message": "No chat_id or text"}

        # Procesar con DMResponderAgent
        # Por ahora usamos "manel" como creator_id, luego se puede mapear por chat
        creator_id = os.getenv("DEFAULT_CREATOR_ID", "manel")

        try:
            agent = get_dm_agent(creator_id)
            # Extraer nombre completo para guardar en el follower
            first_name = sender.get("first_name", "")
            last_name = sender.get("last_name", "")
            full_name = f"{first_name} {last_name}".strip()

            response = await agent.process_dm(
                sender_id=f"tg_{sender_id}",
                message_text=text,
                message_id=str(message.get("message_id", "")),
                username=sender_name,
                name=full_name  # Guardar nombre en el follower
            )

            # DMResponse es un dataclass, no un dict
            bot_reply = response.response_text
            intent = response.intent.value if response.intent else "unknown"

            logger.info(f"Telegram DM from {sender_name} ({sender_id}): '{text[:50]}' -> intent={intent}")

            # Build inline keyboard if present in metadata
            reply_markup = None
            if response.metadata and "telegram_keyboard" in response.metadata:
                keyboard_data = response.metadata["telegram_keyboard"]
                if keyboard_data:
                    # Convert to Telegram API format: {"inline_keyboard": [[{button}], ...]}
                    inline_keyboard = []
                    for button in keyboard_data:
                        btn = {"text": button.get("text", "")}
                        # Support both callback_data and url buttons
                        if "callback_data" in button:
                            btn["callback_data"] = button["callback_data"]
                        elif "url" in button:
                            btn["url"] = button["url"]
                        inline_keyboard.append([btn])
                    reply_markup = {"inline_keyboard": inline_keyboard}
                    logger.info(f"Sending {len(keyboard_data)} inline buttons for booking")

            # Enviar respuesta a Telegram (via proxy si está configurado)
            if bot_reply and TELEGRAM_BOT_TOKEN:
                result = await send_telegram_message(chat_id, bot_reply, TELEGRAM_BOT_TOKEN, reply_markup)
                if result.get("ok"):
                    logger.info(f"Telegram response sent to chat {chat_id}")
                else:
                    logger.error(f"Telegram send failed: {result}")

            return {
                "status": "ok",
                "chat_id": chat_id,
                "intent": intent,
                "response_sent": bool(bot_reply and TELEGRAM_BOT_TOKEN)
            }

        except Exception as e:
            logger.error(f"Error processing Telegram message: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {"status": "error", "detail": str(e)}

    except Exception as e:
        logger.error(f"Error in Telegram webhook: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/telegram/status")
async def telegram_status():
    """Obtener estado de la integración de Telegram"""
    token_configured = bool(TELEGRAM_BOT_TOKEN)
    token_preview = f"{TELEGRAM_BOT_TOKEN[:10]}...{TELEGRAM_BOT_TOKEN[-5:]}" if token_configured and len(TELEGRAM_BOT_TOKEN) > 15 else "NOT SET"

    # Proxy configuration check - proxy is used if URL is set (secret is optional but recommended)
    proxy_url_set = bool(TELEGRAM_PROXY_URL)
    proxy_secret_set = bool(TELEGRAM_PROXY_SECRET)
    proxy_will_be_used = proxy_url_set  # Proxy is used if URL is configured

    # Build status response
    status_response = {
        "status": "ok" if token_configured else "warning",
        "bot_token_configured": token_configured,
        "bot_token_preview": token_preview,
        "proxy_url_configured": proxy_url_set,
        "proxy_secret_configured": proxy_secret_set,
        "proxy_configured": proxy_url_set,  # Now only requires URL
        "proxy_url": TELEGRAM_PROXY_URL or "NOT SET",
        "send_mode": "proxy" if proxy_will_be_used else "direct",
        "webhook_url": "/webhook/telegram",
        "legacy_webhook_url": "/telegram/webhook"
    }

    # Add info about secret status
    if proxy_url_set and not proxy_secret_set:
        status_response["proxy_note"] = "Proxy URL configured. Secret not set - will work if Worker allows unauthenticated requests."

    return status_response


@app.get("/telegram/test-connection")
async def telegram_test_connection():
    """Test if we can connect to Telegram API"""
    import httpx
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not bot_token:
        return {"status": "error", "error": "TELEGRAM_BOT_TOKEN not configured"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"https://api.telegram.org/bot{bot_token}/getMe"
            )
            return {
                "status": "ok",
                "telegram_response": response.json(),
                "connection": "successful"
            }
    except httpx.ConnectTimeout:
        return {"status": "error", "error": "ConnectTimeout - cannot reach api.telegram.org"}
    except httpx.ConnectError as e:
        return {"status": "error", "error": f"ConnectError: {str(e)}"}
    except Exception as e:
        return {"status": "error", "error": str(e), "type": type(e).__name__}


@app.get("/telegram/network-test")
async def telegram_network_test():
    """Test network connectivity to various endpoints"""
    import httpx
    import socket

    results = {}

    # Test 1: DNS resolution
    try:
        ip = socket.gethostbyname("api.telegram.org")
        results["dns_resolution"] = {"status": "ok", "ip": ip}
    except Exception as e:
        results["dns_resolution"] = {"status": "error", "error": str(e)}

    # Test 2: Try different Telegram endpoints
    endpoints = [
        "https://api.telegram.org",
        "https://core.telegram.org",
        "https://telegram.org",
    ]

    for endpoint in endpoints:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(endpoint, follow_redirects=True)
                results[endpoint] = {"status": "ok", "code": response.status_code}
        except httpx.ConnectTimeout:
            results[endpoint] = {"status": "timeout"}
        except Exception as e:
            results[endpoint] = {"status": "error", "error": str(e)}

    # Test 3: Compare with working endpoint (groq)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://api.groq.com")
            results["api.groq.com"] = {"status": "ok", "code": response.status_code}
    except Exception as e:
        results["api.groq.com"] = {"status": "error", "error": str(e)}

    return results


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
            "recent_responses": handler.get_recent_responses(5)
        }
    except Exception as e:
        return {
            "status": "error",
            "phone_number_id_configured": bool(os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")),
            "access_token_configured": bool(os.getenv("WHATSAPP_ACCESS_TOKEN", "")),
            "webhook_url": "/webhook/whatsapp",
            "error": str(e)
        }


# ---------------------------------------------------------
# CREATOR CONFIG
# ---------------------------------------------------------
@app.post("/creator/config")
async def create_creator_config(config_data: dict):
    """Crear configuracion de creador"""
    try:
        config = CreatorConfig(**config_data)
        config_id = config_manager.create_config(config)
        return {"status": "ok", "creator_id": config_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/creator/config/{creator_id}")
async def get_creator_config(creator_id: str):
    """Obtener configuracion de creador"""
    # PostgreSQL first - auto-create if doesn't exist
    if USE_DB:
        try:
            config = db_service.get_or_create_creator(creator_id)
            if config:
                return {"status": "ok", "config": config}
            logger.warning(f"get_or_create_creator returned None for {creator_id}")
        except Exception as e:
            logger.error(f"Error getting creator config from DB: {e}")

    # Fallback to JSON config manager
    config = config_manager.get_config(creator_id)
    if config:
        return {"status": "ok", "config": config.to_dict()}

    # Ultimate fallback - return default config instead of 404
    logger.warning(f"Returning default config for creator '{creator_id}'")
    return {
        "status": "ok",
        "config": {
            "id": creator_id,
            "name": creator_id,
            "email": None,
            "bot_active": True,
            "clone_tone": "friendly",
            "clone_style": "",
            "clone_name": creator_id,
            "clone_vocabulary": "",
            "welcome_message": "",
            "other_payment_methods": {},
            "knowledge_about": {},
        }
    }


# ---------------------------------------------------------
# AI PERSONALITY GENERATION
# ---------------------------------------------------------
@app.post("/api/ai/generate-rules")
async def generate_ai_rules(request: dict = Body(...)):
    """Generate bot personality rules using AI (Grok)"""
    prompt = request.get("prompt", "")

    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt required")

    xai_api_key = (os.getenv("XAI_API_KEY") or "").strip()

    if not xai_api_key:
        # Fallback: generate basic rules locally
        rules = f"- {prompt}"
        return {"rules": rules, "source": "fallback"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {xai_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "grok-beta",
                    "messages": [
                        {
                            "role": "system",
                            "content": "Genera 5-7 reglas claras y concisas para un chatbot de ventas. Cada regla empieza con '- '. Solo devuelve las reglas, sin explicaciones adicionales. Las reglas deben ser en español."
                        },
                        {
                            "role": "user",
                            "content": f"El usuario quiere un bot con esta personalidad: {prompt}"
                        }
                    ],
                    "max_tokens": 300,
                    "temperature": 0.7
                }
            )

            if response.status_code == 200:
                data = response.json()
                rules = data["choices"][0]["message"]["content"]
                return {"rules": rules, "source": "grok"}
            else:
                logger.warning(f"Grok API error: {response.status_code}")
                # Fallback
                rules = f"- {prompt}"
                return {"rules": rules, "source": "fallback"}

    except Exception as e:
        logger.error(f"Error calling Grok API: {e}")
        # Fallback
        rules = f"- {prompt}"
        return {"rules": rules, "source": "fallback"}


@app.post("/api/ai/generate-knowledge-full")
async def generate_knowledge_full(request: dict = Body(...)):
    """Generate FAQs + extract 'About' info from content"""
    content = request.get("content", "") or request.get("prompt", "")

    if not content:
        raise HTTPException(status_code=400, detail="Content required")

    logger.info(f"Generating full knowledge for: {content[:100]}...")

    xai_api_key = (os.getenv("XAI_API_KEY") or "").strip()

    if not xai_api_key:
        logger.warning("XAI_API_KEY not configured, using fallback")
        fallback_faqs = generate_fallback_faqs(content)
        fallback_about = generate_fallback_about(content)
        return {"faqs": fallback_faqs, "about": fallback_about, "source": "fallback"}

    try:
        import re
        import json

        async with httpx.AsyncClient(timeout=60.0) as client:
            system_prompt = """Genera FAQs PERFECTAS. Eres un experto en redacción comercial.

## REGLAS CRÍTICAS:

1. PRECIOS: Menciona TODOS los productos con nombre y precio exacto
   MAL: "Los precios varían según el producto"
   BIEN: "Curso Trading Pro: 297€. Mentoría 1:1: 500€/mes."

2. NO MEZCLAR PRODUCTOS: Cada producto tiene su propia descripción
   MAL: "Incluye 20h de vídeo... La mentoría cuesta 500€"
   BIEN: "El Curso Trading Pro incluye 20h de vídeo, comunidad y plantillas."

3. REDACCIÓN LIMPIA - EVITA ESTOS ERRORES:
   MAL: "Atendemos de atención:"
   BIEN: "Atendemos de lunes a viernes de 9:00 a 18:00"
   MAL: "El precio es Curso Trading"
   BIEN: "El Curso Trading Pro cuesta 297€"

4. RESPUESTAS COMPLETAS: 20-60 palabras cada una, datos específicos

5. GARANTÍA: Siempre el número exacto de días
   MAL: "Hay garantía de satisfacción"
   BIEN: "Garantía de 30 días con devolución completa"

## GENERA:

1. ABOUT (perfil):
   - bio: 1-2 frases sobre quién es
   - specialties: lista separada por comas
   - experience: años concretos
   - audience: público objetivo

2. FAQS (6-8): precios, qué incluye, garantía, pagos, horario, cómo empezar

## FORMATO JSON (solo esto):
{
  "about": {"bio": "...", "specialties": "...", "experience": "...", "audience": "..."},
  "faqs": [{"question": "?", "answer": "respuesta específica con datos"}]
}"""

            user_message = f"""Extrae la información de este negocio:

{content}

Genera el JSON con about + faqs:"""

            logger.info("Calling Grok API for full knowledge generation...")
            response = await client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {xai_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "grok-beta",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "max_tokens": 2500,
                    "temperature": 0.05
                }
            )

            if response.status_code == 200:
                data = response.json()
                result = data["choices"][0]["message"]["content"]
                logger.info(f"Grok full knowledge response: {result[:500]}...")

                # Clean up
                result = re.sub(r'```json\s*', '', result)
                result = re.sub(r'```\s*', '', result)
                result = result.strip()

                json_match = re.search(r'\{[\s\S]*\}', result)
                if json_match:
                    result = json_match.group()

                parsed = json.loads(result)

                # Validate and clean FAQs
                validated_faqs = []
                for faq in parsed.get("faqs", []):
                    answer = faq.get("answer", "")
                    question = faq.get("question", "")

                    # Skip too short answers
                    if len(answer) < 20:
                        continue

                    # Post-process: fix common redundancies
                    answer = answer.replace("Atendemos de atención:", "Atendemos")
                    answer = answer.replace("Atendemos de Atención:", "Atendemos")
                    answer = answer.replace("El precio es Curso", "El Curso")
                    answer = answer.replace("El precio es curso", "El curso")
                    answer = re.sub(r'\s+', ' ', answer).strip()  # Fix double spaces

                    # Skip generic answers
                    generic_phrases = ["contacta para más", "contáctanos para", "escríbenos para"]
                    if any(phrase in answer.lower() for phrase in generic_phrases):
                        continue

                    validated_faqs.append({"question": question, "answer": answer})

                logger.info(f"Generated {len(validated_faqs)} FAQs + about info")
                return {
                    "about": parsed.get("about", {}),
                    "faqs": validated_faqs,
                    "source": "grok"
                }
            else:
                logger.warning(f"Grok API error: {response.status_code}")

    except Exception as e:
        logger.error(f"Error generating full knowledge: {e}")
        import traceback
        logger.error(traceback.format_exc())

    # Fallback
    fallback_faqs = generate_fallback_faqs(content)
    fallback_about = generate_fallback_about(content)
    return {"faqs": fallback_faqs, "about": fallback_about, "source": "fallback"}


def generate_fallback_about(content: str) -> dict:
    """Extract about info from content when API is unavailable"""
    import re
    content_lower = content.lower()

    about = {
        "bio": "",
        "specialties": "",
        "experience": "",
        "audience": ""
    }

    # Extract bio - first sentence or "Soy..." pattern
    soy_match = re.search(r'[Ss]oy\s+([^.]+)', content)
    if soy_match:
        about["bio"] = f"Soy {soy_match.group(1).strip()}."

    # Extract experience - "desde 2018" or "X años"
    exp_match = re.search(r'desde\s+(\d{4})', content_lower)
    if exp_match:
        year = int(exp_match.group(1))
        years = 2024 - year
        about["experience"] = f"{years} años"
    else:
        years_match = re.search(r'(\d+)\s*años', content_lower)
        if years_match:
            about["experience"] = f"{years_match.group(1)} años"

    # Extract specialties
    specialties = []
    keywords = ["trading", "criptomonedas", "crypto", "fitness", "coaching", "marketing", "diseño", "programación"]
    for kw in keywords:
        if kw in content_lower:
            specialties.append(kw.capitalize())
    if specialties:
        about["specialties"] = ", ".join(specialties[:3])

    return about


@app.post("/api/ai/generate-knowledge")
async def generate_ai_knowledge(request: dict = Body(...)):
    """Generate knowledge base content using AI (Grok)"""
    prompt = request.get("prompt", "")
    content_type = request.get("type", "faqs")  # "faqs" or "about"

    if not prompt:
        raise HTTPException(status_code=400, detail="Prompt required")

    logger.info(f"Generating {content_type} for content: {prompt[:100]}...")

    xai_api_key = (os.getenv("XAI_API_KEY") or "").strip()

    if not xai_api_key:
        logger.warning("XAI_API_KEY not configured, using smart fallback")
        # Smart fallback: generate FAQs based on keywords in the content
        if content_type == "faqs":
            fallback_faqs = generate_fallback_faqs(prompt)
            return {"faqs": fallback_faqs, "source": "fallback"}
        else:
            return {"about": {"bio": prompt}, "source": "fallback"}

    try:
        import re
        import json

        async with httpx.AsyncClient(timeout=60.0) as client:
            if content_type == "faqs":
                system_prompt = """Genera FAQs PERFECTAS para un negocio.

REGLAS ESTRICTAS:

1. PRECIOS: Si hay múltiples productos, lista TODOS con nombre y precio exacto
   MAL: "El precio es 297€"
   BIEN: "El Curso Trading Pro cuesta 297€. La Mentoría 1:1 cuesta 500€/mes."

2. CONTENIDO: Si un producto incluye varias cosas, lista TODO
   MAL: "Incluye videos y comunidad"
   BIEN: "Incluye 20 horas de vídeo, comunidad privada en Telegram, sesiones Q&A semanales, plantillas y acceso de por vida."

3. NO MEZCLAR PRODUCTOS: Cada producto debe tener su propia descripción
   MAL: "Incluye videos... Mentoría 500€/mes..." (mezclado)
   BIEN: Separar en FAQs diferentes

4. REDACCIÓN LIMPIA: Sin redundancias ni errores
   MAL: "Atendemos de atención: Lunes..."
   BIEN: "Atendemos de lunes a viernes de 9:00 a 18:00."

5. RESPUESTAS COMPLETAS: Mínimo 15 palabras, máximo 60

FORMATO (solo JSON, sin explicaciones):
{"faqs":[{"question":"?","answer":"respuesta completa"}]}

EJEMPLO:
Texto: "Curso A: 100€ (videos, comunidad). Mentoría: 200€/mes. Garantía 30 días."
{"faqs":[
{"question":"¿Cuánto cuestan tus productos?","answer":"El Curso A cuesta 100€. La Mentoría cuesta 200€/mes."},
{"question":"¿Qué incluye el Curso A?","answer":"Incluye videos y acceso a comunidad."},
{"question":"¿Qué es la Mentoría?","answer":"Es acompañamiento personalizado por 200€/mes."},
{"question":"¿Tienen garantía?","answer":"Sí, 30 días de garantía de devolución."}
]}"""
            else:
                system_prompt = """Extrae informacion clave sobre el negocio/creador.
Devuelve SOLO un JSON valido:
{"bio": "descripcion breve", "specialties": ["especialidad1"], "experience": "experiencia", "target_audience": "publico"}"""

            user_message = f"""Genera 6-8 FAQs para este negocio:

{prompt}

CHECKLIST antes de responder:
- ¿Mencioné TODOS los productos con sus precios exactos?
- ¿Cada respuesta es completa y específica?
- ¿No hay frases redundantes como "Atendemos de atención"?
- ¿No mezclé información de diferentes productos en la misma respuesta?
- ¿Listó TODO lo que incluye cada producto?

JSON:"""

            logger.info("Calling Grok API with perfected prompt...")
            response = await client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {xai_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "grok-beta",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "max_tokens": 2000,
                    "temperature": 0.05
                }
            )

            logger.info(f"Grok API response status: {response.status_code}")

            if response.status_code == 200:
                data = response.json()

                if "choices" not in data or len(data["choices"]) == 0:
                    logger.error(f"Grok response missing choices: {data}")
                    raise Exception("Invalid Grok response")

                content = data["choices"][0]["message"]["content"]
                logger.info(f"Grok raw response: {content[:500]}...")

                # Clean up response - remove markdown code blocks
                content = re.sub(r'```json\s*', '', content)
                content = re.sub(r'```\s*', '', content)
                content = content.strip()

                # Try to extract JSON if there's extra text
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    content = json_match.group()

                # Try to parse as JSON
                try:
                    parsed = json.loads(content)

                    if content_type == "faqs":
                        # Handle both {"faqs": [...]} and [...] formats
                        faqs_list = parsed.get("faqs", parsed) if isinstance(parsed, dict) else parsed

                        if not isinstance(faqs_list, list):
                            faqs_list = [faqs_list]

                        # POST-GENERATION VALIDATION & CLEANUP
                        validated_faqs = []
                        seen_answers = set()

                        for faq in faqs_list:
                            answer = faq.get("answer", "").strip()
                            question = faq.get("question", "").strip()

                            # Fix common redundancies
                            answer = answer.replace("Atendemos de atención:", "Atendemos")
                            answer = answer.replace("Atendemos de atención", "Atendemos")
                            answer = answer.replace("El precio es Curso", "El Curso")
                            answer = answer.replace("El precio es el Curso", "El Curso")
                            answer = re.sub(r'\s+', ' ', answer)  # Fix double spaces

                            # Skip empty or very short answers
                            if len(answer) < 15:
                                logger.warning(f"Skipping short answer: '{answer}'")
                                continue

                            # Skip absurd answers
                            absurd_answers = ["tarjeta", "incluye: tarjeta", "tarjeta.", "stripe", "paypal"]
                            if answer.lower().strip().rstrip('.') in absurd_answers:
                                logger.warning(f"Skipping absurd answer: '{answer}'")
                                continue

                            # Skip duplicates
                            answer_normalized = answer.lower()[:50]
                            if answer_normalized in seen_answers:
                                logger.warning(f"Skipping duplicate answer: '{answer[:50]}...'")
                                continue
                            seen_answers.add(answer_normalized)

                            validated_faqs.append({"question": question, "answer": answer})

                        logger.info(f"Validated {len(validated_faqs)} FAQs from Grok (filtered from {len(faqs_list)})")
                        return {"faqs": validated_faqs, "source": "grok"}
                    else:
                        return {"about": parsed, "source": "grok"}

                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse Grok response as JSON: {e}")
                    logger.warning(f"Content was: {content}")
                    # Try to extract FAQs from text
                    if content_type == "faqs":
                        extracted = extract_faqs_from_text(content)
                        if extracted:
                            return {"faqs": extracted, "source": "grok-extracted"}
                        return {"faqs": [{"question": "FAQ generado", "answer": content}], "source": "grok-text"}
                    else:
                        return {"about": {"bio": content}, "source": "grok-text"}
            else:
                logger.warning(f"Grok API error: {response.status_code} - {response.text}")

    except Exception as e:
        logger.error(f"Error calling Grok API for knowledge: {e}")
        import traceback
        logger.error(traceback.format_exc())

    # Smart fallback
    logger.info("Using smart fallback for FAQ generation")
    if content_type == "faqs":
        fallback_faqs = generate_fallback_faqs(prompt)
        return {"faqs": fallback_faqs, "source": "fallback"}
    else:
        return {"about": {"bio": prompt}, "source": "fallback"}


def generate_fallback_faqs(content: str) -> list:
    """Generate FAQs locally when API is not available - extracts EXACT SPECIFIC data"""
    import re
    faqs = []
    content_lower = content.lower()

    # Extract product names with prices (e.g., "Curso Trading Pro: 297€" or "Mentoría 1:1: 500€/mes")
    product_price_patterns = [
        r'[-•]\s*([^:]+?):\s*(\d+)[€$](?:/(\w+))?',  # "- Curso X: 297€" or "- Mentoría: 500€/mes"
        r'([Cc]urso[^:]+?):\s*(\d+)[€$]',  # "Curso Trading Pro: 297€"
        r'([Mm]entoría[^:]+?):\s*(\d+)[€$](?:/(\w+))?',  # "Mentoría 1:1: 500€/mes"
    ]

    products = []
    seen_prices = set()  # Track prices to avoid duplicates

    for pattern in product_price_patterns:
        matches = re.findall(pattern, content)
        for match in matches:
            if len(match) >= 2:
                name = match[0].strip()
                price = match[1]
                period = match[2] if len(match) > 2 and match[2] else None

                # Skip if we've already seen this price (avoid duplicates)
                price_key = f"{price}-{period or ''}"
                if price_key in seen_prices:
                    continue
                seen_prices.add(price_key)

                if period:
                    products.append(f"{name}: {price}€/{period}")
                else:
                    products.append(f"{name}: {price}€")

    # If no structured products found, try simple price extraction
    if not products:
        simple_prices = re.findall(r'(\d+)\s*[€$]', content)
        if simple_prices:
            products = [f"{p}€" for p in simple_prices]

    # Build price FAQ
    if products:
        if len(products) == 1:
            faqs.append({
                "question": "¿Cuánto cuesta?",
                "answer": f"El precio es {products[0]}."
            })
        else:
            faqs.append({
                "question": "¿Cuánto cuesta?",
                "answer": f"Tenemos varias opciones: {'. '.join(products)}."
            })

    # Extract what's included - look for parentheses after price OR after "incluye"
    # IMPORTANT: Skip small parentheses with payment words like "(tarjeta)"
    included_text = None

    # First, try to find parentheses that come after a price (e.g., "297€ (20h vídeo, comunidad...)")
    price_paren_match = re.search(r'\d+[€$]\s*\(([^)]{15,})\)', content)  # Min 15 chars to avoid "(tarjeta)"
    if price_paren_match:
        included_text = price_paren_match.group(1)
    else:
        # Try any parentheses with substantial content (not payment-related)
        all_parens = re.findall(r'\(([^)]+)\)', content)
        for paren_content in all_parens:
            paren_lower = paren_content.lower()
            # Skip payment-related parentheses
            if any(word in paren_lower for word in ["tarjeta", "card", "visa", "mastercard"]):
                continue
            # Skip very short content
            if len(paren_content) < 15:
                continue
            included_text = paren_content
            break

    if included_text:
        faqs.append({
            "question": "¿Qué incluye?",
            "answer": f"Incluye: {included_text}."
        })
    else:
        # Try "incluye:" pattern
        incluye_match = re.search(r'[Ii]ncluye[:\s]+([^.]+)', content)
        if incluye_match:
            faqs.append({
                "question": "¿Qué incluye?",
                "answer": f"Incluye: {incluye_match.group(1).strip()}."
            })

    # Extract guarantee - multiple patterns
    guarantee_patterns = [
        r'[Gg]arantía[:\s]+(\d+)\s*(días?|semanas?|meses?)',
        r'(\d+)\s*(días?|semanas?|meses?)\s*(?:de\s*)?(?:garantía|devolución)',
        r'[Gg]arantía\s*(?:de\s*)?(\d+)\s*(días?|semanas?|meses?)',
    ]

    guarantee = None
    for pattern in guarantee_patterns:
        match = re.search(pattern, content)
        if match:
            guarantee = f"{match.group(1)} {match.group(2)}"
            break

    if guarantee:
        faqs.append({
            "question": "¿Tienen garantía de devolución?",
            "answer": f"Sí, {guarantee} de garantía. Si no estás satisfecho, te devolvemos el dinero."
        })

    # Extract payment methods - be specific
    payment_methods = []
    if "stripe" in content_lower:
        payment_methods.append("Stripe (tarjeta)")
    elif "tarjeta" in content_lower:
        payment_methods.append("tarjeta")
    if "paypal" in content_lower:
        payment_methods.append("PayPal")
    if "bizum" in content_lower:
        payment_methods.append("Bizum")
    if "transferencia" in content_lower:
        payment_methods.append("transferencia bancaria")

    if payment_methods:
        faqs.append({
            "question": "¿Cuáles son los métodos de pago?",
            "answer": f"Puedes pagar con {', '.join(payment_methods)}."
        })

    # Extract schedule/hours
    horario_match = re.search(r'[Hh]orario[:\s]+([^\n.]+)', content)
    if horario_match:
        faqs.append({
            "question": "¿Cuál es el horario de atención?",
            "answer": f"Atendemos {horario_match.group(1).strip()}."
        })

    # Access duration
    if "de por vida" in content_lower or "acceso de por vida" in content_lower:
        faqs.append({
            "question": "¿Por cuánto tiempo tengo acceso?",
            "answer": "Tienes acceso de por vida al contenido."
        })
    elif "vida" in content_lower:
        faqs.append({
            "question": "¿Por cuánto tiempo tengo acceso?",
            "answer": "El acceso es de por vida."
        })

    # Extract hours of content
    hours_match = re.search(r'(\d+)\s*h(?:oras?)?\s*(?:de\s*)?(?:vídeo|video|contenido)', content_lower)
    if hours_match:
        faqs.append({
            "question": "¿Cuánto contenido incluye?",
            "answer": f"Incluye {hours_match.group(1)} horas de vídeo."
        })

    # How to start - only if we have some FAQs
    if faqs:
        faqs.append({
            "question": "¿Cómo puedo empezar?",
            "answer": "Escríbeme y te cuento los pasos para comenzar."
        })

    return faqs[:8]  # Return max 8 FAQs


def extract_faqs_from_text(text: str) -> list:
    """Try to extract Q&A pairs from unstructured text"""
    faqs = []
    import re

    # Try to find Q: A: patterns
    qa_pattern = r'[¿?]([^?¿]+)\?[:\s]*([^¿?]+?)(?=[¿?]|$)'
    matches = re.findall(qa_pattern, text, re.DOTALL)

    for q, a in matches:
        q = q.strip()
        a = a.strip()
        if len(q) > 5 and len(a) > 5:
            faqs.append({"question": f"¿{q}?", "answer": a})

    return faqs if faqs else None


@app.put("/creator/config/{creator_id}")
async def update_creator_config(creator_id: str, updates: dict = Body(...)):
    """Actualizar configuracion de creador"""
    config = config_manager.update_config(creator_id, updates)
    # PostgreSQL first
    if USE_DB:
        success = db_service.update_creator(creator_id, updates)
        if success:
            return {"status": "ok", "message": "Config updated"}
    if not config:
        raise HTTPException(status_code=404, detail="Creator not found")
    return {"status": "ok", "config": config.to_dict()}


@app.delete("/creator/config/{creator_id}")
async def delete_creator_config(creator_id: str):
    """Eliminar configuracion de creador"""
    success = config_manager.delete_config(creator_id)
    if not success:
        raise HTTPException(status_code=404, detail="Creator not found")
    return {"status": "ok"}


@app.get("/creator/list")
async def list_creators():
    """Listar todos los creadores"""
    creators = config_manager.list_creators()
    return {"status": "ok", "creators": creators, "count": len(creators)}


# ---------------------------------------------------------
# PRODUCTS
# ---------------------------------------------------------
@app.post("/creator/{creator_id}/products")
async def create_product(creator_id: str, product_data: dict = Body(...)):
    """Crear producto"""
    try:
        # Auto-generate id if not provided
        if 'id' not in product_data or not product_data['id']:
            product_data['id'] = product_data['name'].lower().replace(' ', '-').replace('/', '-')
        # Default description if not provided
        if 'description' not in product_data:
            product_data['description'] = ''
        product = Product(**product_data)
        product_id = product_manager.add_product(creator_id, product)
        # Get the created product to return full data
        created_product = product_manager.get_product_by_id(creator_id, product_id)
        return {"status": "ok", "product": created_product.to_dict() if created_product else {"id": product_id, **product_data}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/creator/{creator_id}/products")
async def get_products(creator_id: str, active_only: bool = True):
    """Listar productos del creador"""
    # PostgreSQL first
    if USE_DB:
        products = db_service.get_products(creator_id)
        if products is not None:
            return {"status": "ok", "products": products, "count": len(products)}
    products = product_manager.get_products(creator_id, active_only)
    return {"status": "ok", "products": [p.to_dict() for p in products], "count": len(products)}


@app.get("/creator/{creator_id}/products/{product_id}")
async def get_product(creator_id: str, product_id: str):
    """Obtener producto especifico"""
    product = product_manager.get_product_by_id(creator_id, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product.to_dict()


@app.put("/creator/{creator_id}/products/{product_id}")
async def update_product(creator_id: str, product_id: str, updates: dict = Body(...)):
    """Actualizar producto"""
    product = product_manager.update_product(creator_id, product_id, updates)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product.to_dict()


@app.delete("/creator/{creator_id}/products/{product_id}")
async def delete_product(creator_id: str, product_id: str):
    """Eliminar producto"""
    success = product_manager.delete_product(creator_id, product_id)
    if not success:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"status": "ok"}


# ---------------------------------------------------------
# DM AGENT
# ---------------------------------------------------------
def get_dm_agent(creator_id: str) -> DMResponderAgent:
    """Factory para crear DM agent"""
    return DMResponderAgent(creator_id=creator_id)


@app.post("/dm/process")
async def process_dm(payload: ProcessDMRequest):
    """Procesar un DM manualmente (para testing)"""
    try:
        agent = get_dm_agent(payload.creator_id)

        result = await agent.process_dm(
            sender_id=payload.sender_id,
            message_text=payload.message,
            message_id=payload.message_id
        )

        return {
            "status": "ok",
            "response": result.response_text,
            "intent": result.intent.value,
            "action": result.action_taken,
            "product_mentioned": result.product_mentioned,
            "escalate": result.escalate_to_human,
            "confidence": result.confidence
        }

    except Exception as e:
        logger.error(f"Error processing DM: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dm/conversations/{creator_id}")
async def get_conversations(creator_id: str, limit: int = 50):
    """Listar conversaciones del creador"""
    try:
        # Use PostgreSQL for conversations with message counts
        # Messages ARE being saved to PostgreSQL (confirmed in logs)
        if USE_DB:
            from api.services.db_service import get_session
            from api.models import Creator, Lead, Message
            from sqlalchemy import func, not_

            session = get_session()
            if session:
                try:
                    creator = session.query(Creator).filter_by(name=creator_id).first()
                    logger.info(f"[CONV] creator_id={creator_id}, found={creator is not None}")
                    if creator:
                        logger.info(f"[CONV] creator.id={creator.id}")

                        # Count user messages per lead
                        msg_count_subq = session.query(
                            Message.lead_id,
                            func.count(Message.id).label('msg_count')
                        ).filter(Message.role == 'user').group_by(Message.lead_id).subquery()

                        # Get leads with message counts, excluding archived/spam
                        results = session.query(
                            Lead,
                            func.coalesce(msg_count_subq.c.msg_count, 0).label('total_messages')
                        ).outerjoin(
                            msg_count_subq, Lead.id == msg_count_subq.c.lead_id
                        ).filter(
                            Lead.creator_id == creator.id,
                            not_(Lead.status.in_(["archived", "spam"]))
                        ).order_by(Lead.last_contact_at.desc()).limit(limit).all()

                        logger.info(f"[CONV] Found {len(results)} leads")

                        conversations = []
                        for lead, msg_count in results:
                            # Count from PostgreSQL
                            direct_count = session.query(Message).filter_by(lead_id=lead.id, role='user').count()

                            # If PostgreSQL has 0, try to get count from JSON
                            final_count = direct_count
                            if direct_count == 0 and lead.platform_user_id:
                                try:
                                    from api.services.data_sync import _load_json
                                    json_data = _load_json(creator_id, lead.platform_user_id)
                                    if json_data:
                                        last_messages = json_data.get("last_messages", [])
                                        final_count = len([m for m in last_messages if m.get("role") == "user"])
                                        if final_count > 0:
                                            logger.info(f"[CONV] Lead {lead.platform_user_id}: PG=0, JSON={final_count}")
                                except Exception as json_err:
                                    logger.debug(f"JSON fallback failed for {lead.platform_user_id}: {json_err}")

                            logger.info(f"[CONV] Lead {lead.platform_user_id}: subq={msg_count}, direct={direct_count}, final={final_count}")

                            # Get last_messages from JSON for preview
                            last_messages = []
                            if lead.platform_user_id:
                                try:
                                    from api.services.data_sync import _load_json
                                    json_data = _load_json(creator_id, lead.platform_user_id)
                                    if json_data:
                                        last_messages = json_data.get("last_messages", [])[-5:]  # Last 5 for preview
                                except:
                                    pass

                            # Extract email/phone/notes from context JSON
                            ctx = lead.context or {}

                            conversations.append({
                                "follower_id": lead.platform_user_id,
                                "id": str(lead.id),
                                "username": lead.username or lead.platform_user_id,
                                "name": lead.full_name or lead.username or "",
                                "platform": lead.platform or "instagram",
                                "total_messages": final_count,
                                "purchase_intent_score": lead.purchase_intent or 0.0,
                                "is_lead": True,
                                "last_contact": lead.last_contact_at.isoformat() if lead.last_contact_at else None,
                                "last_messages": last_messages,
                                "email": ctx.get("email") or "",
                                "phone": ctx.get("phone") or "",
                                "notes": ctx.get("notes") or "",
                            })

                        return {"status": "ok", "conversations": conversations, "count": len(conversations)}
                finally:
                    session.close()

        # Fallback to JSON if PostgreSQL not available
        agent = get_dm_agent(creator_id)
        conversations = await agent.get_all_conversations(limit)
        filtered = [c for c in conversations if not c.get("archived") and not c.get("spam")]
        return {"status": "ok", "conversations": filtered, "count": len(filtered)}

    except Exception as e:
        logger.error(f"get_conversations error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dm/debug/{creator_id}")
async def debug_messages(creator_id: str):
    """Debug endpoint to diagnose message count issue"""
    debug_info = {
        "creator_id": creator_id,
        "use_db": USE_DB,
        "creator_found": False,
        "total_leads": 0,
        "total_messages_all": 0,
        "total_messages_user": 0,
        "leads_with_messages": [],
        "sample_messages": [],
    }

    if not USE_DB:
        return {"status": "error", "message": "Database not available", "debug": debug_info}

    try:
        from api.services.db_service import get_session
        from api.models import Creator, Lead, Message
        from sqlalchemy import func

        session = get_session()
        if not session:
            return {"status": "error", "message": "No session", "debug": debug_info}

        try:
            # Check if creator exists
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                debug_info["error"] = f"Creator '{creator_id}' not found"
                # List all creators
                all_creators = session.query(Creator).all()
                debug_info["available_creators"] = [c.name for c in all_creators]
                return {"status": "error", "message": "Creator not found", "debug": debug_info}

            debug_info["creator_found"] = True
            debug_info["creator_uuid"] = str(creator.id)

            # Count leads for this creator
            leads = session.query(Lead).filter_by(creator_id=creator.id).all()
            debug_info["total_leads"] = len(leads)

            # Get lead UUIDs
            lead_ids = [lead.id for lead in leads]
            debug_info["lead_uuids"] = [str(lid) for lid in lead_ids[:5]]  # First 5

            # Count ALL messages for these leads
            if lead_ids:
                all_msg_count = session.query(Message).filter(Message.lead_id.in_(lead_ids)).count()
                debug_info["total_messages_all"] = all_msg_count

                # Count only user messages
                user_msg_count = session.query(Message).filter(
                    Message.lead_id.in_(lead_ids),
                    Message.role == 'user'
                ).count()
                debug_info["total_messages_user"] = user_msg_count

                # Get message counts per lead
                for lead in leads[:5]:  # First 5 leads
                    lead_all = session.query(Message).filter_by(lead_id=lead.id).count()
                    lead_user = session.query(Message).filter_by(lead_id=lead.id, role='user').count()
                    debug_info["leads_with_messages"].append({
                        "lead_id": str(lead.id),
                        "platform_user_id": lead.platform_user_id,
                        "username": lead.username,
                        "all_messages": lead_all,
                        "user_messages": lead_user,
                    })

                # Get sample messages
                sample_msgs = session.query(Message).filter(Message.lead_id.in_(lead_ids)).limit(5).all()
                for msg in sample_msgs:
                    debug_info["sample_messages"].append({
                        "id": str(msg.id),
                        "lead_id": str(msg.lead_id),
                        "role": msg.role,
                        "content_preview": msg.content[:50] if msg.content else "",
                    })

                # Check for orphan messages (messages not associated with any of this creator's leads)
                all_msgs_in_db = session.query(Message).count()
                msgs_for_creator = session.query(Message).filter(Message.lead_id.in_(lead_ids)).count() if lead_ids else 0
                orphan_msgs = all_msgs_in_db - msgs_for_creator
                debug_info["orphan_messages"] = orphan_msgs
                debug_info["all_messages_in_db"] = all_msgs_in_db
                debug_info["messages_for_this_creator"] = msgs_for_creator

                # Get sample orphan messages if any
                if orphan_msgs > 0 and lead_ids:
                    orphan_sample = session.query(Message).filter(~Message.lead_id.in_(lead_ids)).limit(5).all()
                    debug_info["orphan_sample"] = [{
                        "id": str(msg.id),
                        "lead_id": str(msg.lead_id),
                        "role": msg.role,
                        "content_preview": msg.content[:50] if msg.content else "",
                    } for msg in orphan_sample]

            return {"status": "ok", "debug": debug_info}

        finally:
            session.close()

    except Exception as e:
        debug_info["exception"] = str(e)
        logger.error(f"debug_messages error: {e}")
        return {"status": "error", "message": str(e), "debug": debug_info}


@app.get("/dm/metrics/{creator_id}")
async def get_dm_metrics(creator_id: str):
    """Obtener metricas del agent"""
    try:
        agent = get_dm_agent(creator_id)
        metrics = await agent.get_metrics()
        return {"status": "ok", **metrics}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/dm/follower/{creator_id}/{follower_id}")
async def get_follower_detail(creator_id: str, follower_id: str):
    """Obtener detalle de un seguidor"""
    try:
        agent = get_dm_agent(creator_id)
        detail = await agent.get_follower_detail(follower_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Follower not found")

        return {"status": "ok", **detail}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/dm/send/{creator_id}")
async def send_manual_message(creator_id: str, request: SendMessageRequest):
    """
    Send a manual message to a follower.

    The message will be sent via the appropriate platform (Telegram, Instagram, WhatsApp)
    based on the follower_id prefix:
    - tg_* -> Telegram
    - ig_* -> Instagram
    - wa_* -> WhatsApp

    The message is also saved in the conversation history.
    """
    try:
        follower_id = request.follower_id
        message_text = request.message

        if not message_text.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        # Detect platform from follower_id prefix
        if follower_id.startswith("tg_"):
            platform = "telegram"
            chat_id = follower_id.replace("tg_", "")
        elif follower_id.startswith("ig_"):
            platform = "instagram"
            recipient_id = follower_id.replace("ig_", "")
        elif follower_id.startswith("wa_"):
            platform = "whatsapp"
            phone = follower_id.replace("wa_", "")
        else:
            # Assume Instagram for legacy IDs without prefix
            platform = "instagram"
            recipient_id = follower_id

        sent = False

        # Send via appropriate platform
        if platform == "telegram" and TELEGRAM_BOT_TOKEN:
            try:
                telegram_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                async with httpx.AsyncClient() as client:
                    resp = await client.post(telegram_api, json={
                        "chat_id": int(chat_id),
                        "text": message_text,
                        "parse_mode": "HTML"
                    })
                    if resp.status_code == 200:
                        sent = True
                        logger.info(f"Manual message sent to Telegram chat {chat_id}")
            except Exception as e:
                logger.error(f"Error sending Telegram message: {e}")

        elif platform == "instagram":
            try:
                handler = get_instagram_handler()
                if handler.connector:
                    sent = await handler.send_response(recipient_id, message_text)
                    if sent:
                        logger.info(f"Manual message sent to Instagram {recipient_id}")
            except Exception as e:
                logger.error(f"Error sending Instagram message: {e}")

        elif platform == "whatsapp":
            try:
                wa_handler = get_whatsapp_handler()
                if wa_handler and wa_handler.connector:
                    result = await wa_handler.connector.send_message(phone, message_text)
                    sent = "error" not in result
                    if sent:
                        logger.info(f"Manual message sent to WhatsApp {phone}")
            except Exception as e:
                logger.error(f"Error sending WhatsApp message: {e}")

        # Save the message in conversation history
        agent = get_dm_agent(creator_id)
        await agent.save_manual_message(follower_id, message_text, sent)

        return {
            "status": "ok",
            "sent": sent,
            "platform": platform,
            "follower_id": follower_id,
            "message_preview": message_text[:100] + "..." if len(message_text) > 100 else message_text
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending manual message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/dm/follower/{creator_id}/{follower_id}/status")
async def update_follower_status(
    creator_id: str,
    follower_id: str,
    request: UpdateLeadStatusRequest
):
    """
    Update the lead status for a follower (for drag & drop in pipeline).

    IMPORTANT: This does NOT change the purchase_intent_score!
    The score reflects actual user behavior and should not be modified by manual categorization.

    Valid status values:
    - cold: New follower, low intent
    - warm: Engaged follower, medium intent
    - hot: High purchase intent
    - customer: Has made a purchase
    """
    try:
        valid_statuses = ["cold", "warm", "hot", "customer"]
        status = request.status.lower()

        if status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {valid_statuses}"
            )

        agent = get_dm_agent(creator_id)

        # Get current follower data to preserve the real score
        follower = await agent.memory_store.get(creator_id, follower_id)
        if not follower:
            raise HTTPException(status_code=404, detail="Follower not found")

        # Preserve the existing purchase_intent_score - DON'T CHANGE IT
        current_score = follower.purchase_intent_score

        # Only set is_customer if status is "customer"
        is_customer = (status == "customer") or follower.is_customer

        # Update status WITHOUT changing the score
        success = await agent.update_follower_status(
            follower_id=follower_id,
            status=status,
            purchase_intent=current_score,  # Keep the real score!
            is_customer=is_customer
        )

        if not success:
            raise HTTPException(status_code=404, detail="Follower not found")

        logger.info(f"Updated status for {follower_id} to {status} (score preserved: {current_score:.0%})")

        return {
            "status": "ok",
            "follower_id": follower_id,
            "new_status": status,
            "purchase_intent": current_score  # Return the real score
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating follower status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------
@app.get("/dashboard/{creator_id}/overview")
async def dashboard_overview(creator_id: str):
    """Datos para dashboard principal"""
    try:
        # PostgreSQL first
        if USE_DB:
            metrics = db_service.get_dashboard_metrics(creator_id)
            if metrics:
                return metrics
        agent = get_dm_agent(creator_id)

        metrics = await agent.get_metrics()
        conversations = await agent.get_all_conversations(10)
        leads = await agent.get_leads()
        config = config_manager.get_config(creator_id)
        products = product_manager.get_products(creator_id)

        return {
            "status": "ok",
            "metrics": metrics,
            "recent_conversations": conversations,
            "leads": leads[:10],
            "config": config.to_dict() if config else None,
            "products_count": len(products),
            "clone_active": config.is_active if config else False
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/dashboard/{creator_id}/toggle")
async def toggle_clone(creator_id: str, active: bool, reason: str = ""):
    """Activar/desactivar el clon"""
    try:
        # PostgreSQL first
        if USE_DB:
            result = db_service.toggle_bot(creator_id, active)
            if result is not None:
                return {"status": "ok", "active": result}
        success = config_manager.set_active(creator_id, active, reason)
        if not success:
            raise HTTPException(status_code=404, detail="Creator not found")

        return {
            "status": "ok",
            "active": active,
            "reason": reason if not active else None
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# RAG CONTENT (optional)
# ---------------------------------------------------------
class AddContentRequest(BaseModel):
    creator_id: str
    text: str
    doc_type: str = "faq"


@app.post("/content/add")
async def add_content(request: AddContentRequest):
    """Anadir contenido al RAG del creador"""
    try:
        import hashlib
        doc_id = f"{request.creator_id}_{request.doc_type}_{hashlib.md5(request.text.encode()).hexdigest()[:8]}"

        rag.add_document(
            doc_id=doc_id,
            text=request.text,
            metadata={
                "creator_id": request.creator_id,
                "type": request.doc_type
            }
        )

        return {"status": "ok", "doc_id": doc_id}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/content/search")
async def search_content(creator_id: str, query: str, top_k: int = 3):
    """Buscar en el contenido del creador"""
    try:
        results = rag.search(query, top_k=top_k, creator_id=creator_id)
        return {"status": "ok", "results": results, "count": len(results)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# GDPR COMPLIANCE
# ---------------------------------------------------------
@app.get("/gdpr/{creator_id}/export/{follower_id}")
async def gdpr_export_data(creator_id: str, follower_id: str):
    """
    Export all user data (GDPR Right to Access).
    Returns JSON with all data we hold for this user.
    """
    try:
        gdpr = get_gdpr_manager()
        export_data = gdpr.export_user_data(creator_id, follower_id)
        return {"status": "ok", **export_data}

    except Exception as e:
        logger.error(f"Error exporting GDPR data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/gdpr/{creator_id}/delete/{follower_id}")
async def gdpr_delete_data(creator_id: str, follower_id: str, reason: str = "user_request"):
    """
    Delete all user data (GDPR Right to be Forgotten).
    Permanently removes all data for this user.
    """
    try:
        gdpr = get_gdpr_manager()
        result = gdpr.delete_user_data(creator_id, follower_id, reason)

        if not result["success"]:
            raise HTTPException(status_code=500, detail=f"Deletion errors: {result['errors']}")

        return {"status": "ok", **result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting GDPR data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/gdpr/{creator_id}/anonymize/{follower_id}")
async def gdpr_anonymize_data(creator_id: str, follower_id: str):
    """
    Anonymize user data instead of deleting.
    Keeps aggregated data for analytics while removing PII.
    """
    try:
        gdpr = get_gdpr_manager()
        result = gdpr.anonymize_user_data(creator_id, follower_id)

        if not result["success"]:
            raise HTTPException(status_code=500, detail=f"Anonymization errors: {result['errors']}")

        return {"status": "ok", **result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error anonymizing GDPR data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gdpr/{creator_id}/consent/{follower_id}")
async def gdpr_get_consent(creator_id: str, follower_id: str):
    """Get consent status for a user"""
    try:
        gdpr = get_gdpr_manager()
        status = gdpr.get_consent_status(creator_id, follower_id)
        return {"status": "ok", **status}

    except Exception as e:
        logger.error(f"Error getting consent status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/gdpr/{creator_id}/consent/{follower_id}")
async def gdpr_record_consent(
    creator_id: str,
    follower_id: str,
    consent_type: str,
    granted: bool,
    source: str = "api"
):
    """
    Record a consent decision.

    consent_type options: data_processing, marketing, analytics, third_party, profiling
    """
    try:
        # Validate consent type
        valid_types = [ct.value for ct in ConsentType]
        if consent_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid consent_type. Must be one of: {valid_types}"
            )

        gdpr = get_gdpr_manager()
        consent = gdpr.record_consent(
            creator_id=creator_id,
            follower_id=follower_id,
            consent_type=consent_type,
            granted=granted,
            source=source
        )
        return {"status": "ok", "consent": consent.to_dict()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording consent: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gdpr/{creator_id}/inventory/{follower_id}")
async def gdpr_data_inventory(creator_id: str, follower_id: str):
    """Get inventory of what data we hold for a user"""
    try:
        gdpr = get_gdpr_manager()
        inventory = gdpr.get_data_inventory(creator_id, follower_id)
        return {"status": "ok", **inventory}

    except Exception as e:
        logger.error(f"Error getting data inventory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gdpr/{creator_id}/audit/{follower_id}")
async def gdpr_audit_log(creator_id: str, follower_id: str, limit: int = 50):
    """Get audit log for a user"""
    try:
        gdpr = get_gdpr_manager()
        logs = gdpr.get_audit_log(creator_id, follower_id, limit=limit)
        return {"status": "ok", "logs": logs, "count": len(logs)}

    except Exception as e:
        logger.error(f"Error getting audit log: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# PAYMENTS (Stripe + Hotmart)
# ---------------------------------------------------------
@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """
    Stripe webhook endpoint.

    Processes:
    - checkout.session.completed
    - payment_intent.succeeded
    - charge.refunded

    Include metadata in Stripe checkout:
    - creator_id
    - follower_id
    - product_id
    - product_name
    """
    try:
        raw_payload = await request.body()
        payload = await request.json()
        signature = request.headers.get("Stripe-Signature", "")

        payment_manager = get_payment_manager()
        result = await payment_manager.process_stripe_webhook(
            payload=payload,
            signature=signature,
            raw_payload=raw_payload
        )

        logger.info(f"Stripe webhook processed: {result}")
        return result

    except Exception as e:
        logger.error(f"Stripe webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/hotmart")
async def hotmart_webhook(request: Request):
    """
    Hotmart webhook (postback) endpoint.

    Processes:
    - PURCHASE_COMPLETE
    - PURCHASE_APPROVED
    - PURCHASE_REFUNDED
    - PURCHASE_CANCELED
    """
    try:
        payload = await request.json()
        token = request.headers.get("X-Hotmart-Hottok", "")

        payment_manager = get_payment_manager()
        result = await payment_manager.process_hotmart_webhook(
            payload=payload,
            token=token
        )

        logger.info(f"Hotmart webhook processed: {result}")
        return result

    except Exception as e:
        logger.error(f"Hotmart webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/paypal")
async def paypal_webhook(request: Request):
    """
    PayPal webhook endpoint.

    Processes:
    - PAYMENT.SALE.COMPLETED
    - PAYMENT.CAPTURE.COMPLETED
    - CHECKOUT.ORDER.APPROVED
    - PAYMENT.SALE.REFUNDED

    Include custom_id in PayPal checkout with JSON:
    - creator_id
    - follower_id
    - product_id
    - product_name
    """
    try:
        raw_payload = await request.body()
        payload = await request.json()

        # Get PayPal verification headers
        headers = {
            "paypal-transmission-id": request.headers.get("paypal-transmission-id", ""),
            "paypal-transmission-time": request.headers.get("paypal-transmission-time", ""),
            "paypal-transmission-sig": request.headers.get("paypal-transmission-sig", ""),
            "paypal-cert-url": request.headers.get("paypal-cert-url", ""),
            "paypal-auth-algo": request.headers.get("paypal-auth-algo", ""),
        }

        payment_manager = get_payment_manager()
        result = await payment_manager.process_paypal_webhook(
            payload=payload,
            headers=headers,
            raw_payload=raw_payload
        )

        logger.info(f"PayPal webhook processed: {result}")
        return result

    except Exception as e:
        logger.error(f"PayPal webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/payments/{creator_id}/purchases")
async def get_purchases(
    creator_id: str,
    limit: int = 100,
    status: Optional[str] = None
):
    """
    Get all purchases for a creator.

    Optional filter by status: completed, refunded, cancelled
    """
    try:
        payment_manager = get_payment_manager()
        purchases = payment_manager.get_all_purchases(
            creator_id=creator_id,
            limit=limit,
            status=status
        )

        return {
            "status": "ok",
            "creator_id": creator_id,
            "purchases": purchases,
            "count": len(purchases)
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
            creator_id=creator_id,
            follower_id=follower_id
        )

        total_spent = sum(
            p.get("amount", 0) for p in purchases
            if p.get("status") == "completed"
        )

        return {
            "status": "ok",
            "creator_id": creator_id,
            "follower_id": follower_id,
            "purchases": purchases,
            "total_spent": total_spent,
            "count": len(purchases)
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
        stats = payment_manager.get_revenue_stats(
            creator_id=creator_id,
            days=days
        )

        return {
            "status": "ok",
            "creator_id": creator_id,
            "days": days,
            **stats.to_dict()
        }

    except Exception as e:
        logger.error(f"Error getting revenue stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/payments/{creator_id}/attribute")
async def attribute_sale(
    creator_id: str,
    purchase_id: str,
    follower_id: str
):
    """
    Manually attribute a sale to the bot.

    Use when a purchase wasn't automatically linked to a conversation.
    """
    try:
        payment_manager = get_payment_manager()
        success = payment_manager.attribute_sale_to_bot(
            creator_id=creator_id,
            follower_id=follower_id,
            purchase_id=purchase_id
        )

        if not success:
            raise HTTPException(status_code=404, detail="Purchase not found")

        return {
            "status": "ok",
            "attributed": True,
            "purchase_id": purchase_id,
            "follower_id": follower_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error attributing sale: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# CALENDAR (Calendly + Cal.com)
# ---------------------------------------------------------
@app.post("/webhook/calendly")
async def calendly_webhook(request: Request):
    """
    Calendly webhook endpoint.

    Processes:
    - invitee.created (new booking)
    - invitee.canceled (booking cancelled)

    Use UTM parameters in Calendly link:
    - utm_source: creator_id
    - utm_campaign: follower_id
    """
    try:
        raw_payload = await request.body()
        payload = await request.json()
        signature = request.headers.get("Calendly-Webhook-Signature", "")

        calendar_manager = get_calendar_manager()
        result = await calendar_manager.process_calendly_webhook(
            payload=payload,
            signature=signature,
            raw_payload=raw_payload
        )

        logger.info(f"Calendly webhook processed: {result}")
        return result

    except Exception as e:
        logger.error(f"Calendly webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/calcom")
async def calcom_webhook(request: Request):
    """
    Cal.com webhook endpoint.

    Processes:
    - BOOKING_CREATED
    - BOOKING_CANCELLED
    - BOOKING_RESCHEDULED

    Include in booking metadata:
    - creator_id
    - follower_id
    """
    try:
        raw_payload = await request.body()
        payload = await request.json()
        signature = request.headers.get("X-Cal-Signature-256", "")

        calendar_manager = get_calendar_manager()
        result = await calendar_manager.process_calcom_webhook(
            payload=payload,
            signature=signature,
            raw_payload=raw_payload
        )

        logger.info(f"Cal.com webhook processed: {result}")
        return result

    except Exception as e:
        logger.error(f"Cal.com webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/calendar/{creator_id}/bookings")
async def get_bookings(
    creator_id: str,
    status: Optional[str] = None,
    upcoming: bool = False,
    limit: int = 100
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
            creator_id=creator_id,
            status=status,
            upcoming_only=upcoming,
            limit=limit
        )

        return {
            "status": "ok",
            "creator_id": creator_id,
            "bookings": bookings,
            "count": len(bookings)
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
                db_link = db.query(BookingLinkModel).filter(
                    BookingLinkModel.creator_id == creator_id,
                    BookingLinkModel.meeting_type == meeting_type,
                    BookingLinkModel.is_active == True
                ).first()

                # If not found, try default
                if not db_link:
                    db_link = db.query(BookingLinkModel).filter(
                        BookingLinkModel.creator_id == creator_id,
                        BookingLinkModel.meeting_type == "default",
                        BookingLinkModel.is_active == True
                    ).first()

                if not db_link:
                    raise HTTPException(
                        status_code=404,
                        detail=f"No booking link found for type: {meeting_type}"
                    )

                return {
                    "status": "ok",
                    "creator_id": creator_id,
                    "meeting_type": meeting_type,
                    "url": db_link.url
                }
            finally:
                db.close()
        else:
            # Fallback to file-based storage
            calendar_manager = get_calendar_manager()
            url = calendar_manager.get_booking_link(creator_id, meeting_type)

            if not url:
                raise HTTPException(
                    status_code=404,
                    detail=f"No booking link found for type: {meeting_type}"
                )

            return {
                "status": "ok",
                "creator_id": creator_id,
                "meeting_type": meeting_type,
                "url": url
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
                result = db.execute(text("""
                    SELECT id, creator_id, meeting_type, title, description,
                           duration_minutes, platform, url, is_active, created_at
                    FROM booking_links
                    WHERE creator_id = :creator_id AND is_active = true
                    ORDER BY created_at DESC
                """), {"creator_id": creator_id})

                rows = result.fetchall()
                logger.info(f"GET - Found {len(rows)} links in PostgreSQL for {creator_id}")

                links = []
                for row in rows:
                    links.append({
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
                        "created_at": row[9].isoformat() if row[9] else ""
                    })

                return {
                    "status": "ok",
                    "storage": "postgresql",
                    "creator_id": creator_id,
                    "links": links,
                    "count": len(links)
                }
            finally:
                db.close()
        else:
            # Fallback to file-based storage
            logger.warning(f"GET /calendar/{creator_id}/links - USING FILE FALLBACK (SessionLocal={SessionLocal}, BookingLinkModel={BookingLinkModel})")
            calendar_manager = get_calendar_manager()
            links = calendar_manager.get_all_booking_links(creator_id)
            return {
                "status": "ok",
                "creator_id": creator_id,
                "links": links,
                "count": len(links),
                "storage": "file"  # Indicator for debugging
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
            result = db.execute(text("""
                SELECT id, title, description, duration_minutes, platform, url,
                       COALESCE(price, 0) as price, meeting_type
                FROM booking_links
                WHERE creator_id = :creator_id AND is_active = true
                ORDER BY created_at DESC
            """), {"creator_id": creator_name})

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
                        "meeting_type": row[7]
                    }
                    for row in rows
                ],
                "count": len(rows)
            }
        finally:
            db.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting booking links: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/calendar/{creator_id}/links")
async def create_booking_link(
    creator_id: str,
    data: dict = Body(...)
):
    """
    Create a new booking link - uses PostgreSQL for persistence.
    REWRITTEN to match debug endpoint exactly.
    """
    from sqlalchemy import text
    import uuid

    print("=== BOOKING LINK CREATE ===")
    print(f"creator_id: {creator_id}")
    print(f"data: {data}")
    print(f"SessionLocal: {SessionLocal}")

    # Extract data from body
    meeting_type = data.get("meeting_type", "custom")
    duration_minutes = data.get("duration_minutes", data.get("duration", 30))
    title = data.get("title", "")
    platform = data.get("platform", "manual")

    result = {
        "success": False,
        "error": None,
        "link_id": None
    }

    if SessionLocal:
        db = SessionLocal()
        try:
            link_id = str(uuid.uuid4())
            print(f"Inserting link_id: {link_id}")

            # EXACT same SQL as debug endpoint
            db.execute(text("""
                INSERT INTO booking_links (id, creator_id, meeting_type, title, duration_minutes, platform, is_active)
                VALUES (:id, :creator_id, :meeting_type, :title, :duration, :platform, :is_active)
            """), {
                "id": link_id,
                "creator_id": creator_id,
                "meeting_type": meeting_type,
                "title": title,
                "duration": duration_minutes,
                "platform": platform,
                "is_active": True
            })
            db.commit()
            print(f"INSERT + COMMIT done for {link_id}")

            # Verify
            verify = db.execute(text("SELECT COUNT(*) FROM booking_links WHERE id = :id"), {"id": link_id})
            verify_count = verify.scalar()
            print(f"verify_count: {verify_count}")

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
                    "is_active": True
                },
                "debug": result
            }
        except Exception as e:
            import traceback
            print(f"ERROR: {e}")
            print(traceback.format_exc())
            result["error"] = str(e)
            return {"status": "error", "error": str(e), "debug": result}
        finally:
            db.close()
    else:
        print("SessionLocal is None!")
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

        return {
            "status": "ok",
            "creator_id": creator_id,
            **stats
        }

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
# ADMIN PANEL ENDPOINTS
# ---------------------------------------------------------
@app.get("/admin/creators")
async def admin_list_creators(
    admin: str = Depends(require_admin)
):
    """
    [ADMIN] Listar todos los creadores con estadísticas básicas.
    Requiere CLONNECT_ADMIN_KEY.
    """
    try:
        creators = config_manager.list_creators()
        creator_stats = []

        for creator_id in creators:
            config = config_manager.get_config(creator_id)
            if not config:
                continue

            # Obtener métricas básicas
            try:
                agent = get_dm_agent(creator_id)
                metrics = await agent.get_metrics()
                leads = await agent.get_leads()
            except Exception as e:
                metrics = {}
                logger.warning(f"Failed to get metrics for {creator_id}: {e}")
                leads = []

            creator_stats.append({
                "creator_id": creator_id,
                "name": config.name,
                "instagram_handle": config.instagram_handle,
                "is_active": config.is_active,
                "pause_reason": config.pause_reason if not config.is_active else None,
                "total_messages": metrics.get("total_messages", 0),
                "total_leads": len(leads),
                "hot_leads": len([l for l in leads if l.get("score", 0) >= 0.7]),
                "updated_at": config.updated_at
            })

        return {
            "status": "ok",
            "creators": creator_stats,
            "total": len(creator_stats)
        }

    except Exception as e:
        logger.error(f"Error listing creators: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/stats")
async def admin_global_stats(
    admin: str = Depends(require_admin)
):
    """
    [ADMIN] Estadísticas globales de la plataforma.
    Requiere CLONNECT_ADMIN_KEY.
    """
    try:
        creators = config_manager.list_creators()

        total_messages = 0
        total_leads = 0
        total_hot_leads = 0
        total_conversations = 0
        active_bots = 0
        paused_bots = 0

        for creator_id in creators:
            config = config_manager.get_config(creator_id)
            if config:
                if config.is_active:
                    active_bots += 1
                else:
                    paused_bots += 1

            try:
                agent = get_dm_agent(creator_id)
                metrics = await agent.get_metrics()
                leads = await agent.get_leads()
                conversations = await agent.get_all_conversations(1000)

                total_messages += metrics.get("total_messages", 0)
                total_leads += len(leads)
                total_hot_leads += len([l for l in leads if l.get("score", 0) >= 0.7])
                total_conversations += len(conversations)
            except Exception as e:
                logger.warning(f"Failed to aggregate stats: {e}")

        return {
            "status": "ok",
            "stats": {
                "total_creators": len(creators),
                "active_bots": active_bots,
                "paused_bots": paused_bots,
                "total_messages": total_messages,
                "total_conversations": total_conversations,
                "total_leads": total_leads,
                "hot_leads": total_hot_leads
            }
        }

    except Exception as e:
        logger.error(f"Error getting global stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/conversations")
async def admin_all_conversations(
    admin: str = Depends(require_admin),
    creator_id: Optional[str] = None,
    limit: int = 100
):
    """
    [ADMIN] Listar todas las conversaciones de todos los creadores.
    Opcionalmente filtrar por creator_id.
    Requiere CLONNECT_ADMIN_KEY.
    """
    try:
        if creator_id:
            creators = [creator_id]
        else:
            creators = config_manager.list_creators()

        all_conversations = []

        for cid in creators:
            try:
                agent = get_dm_agent(cid)
                conversations = await agent.get_all_conversations(limit)

                for conv in conversations:
                    conv["creator_id"] = cid
                    all_conversations.append(conv)
            except Exception as e:
                logger.warning(f"Failed to get conversations: {e}")

        # Ordenar por última actividad
        all_conversations.sort(
            key=lambda x: x.get("last_contact", ""),
            reverse=True
        )

        return {
            "status": "ok",
            "conversations": all_conversations[:limit],
            "total": len(all_conversations)
        }

    except Exception as e:
        logger.error(f"Error getting conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/alerts")
async def admin_recent_alerts(
    admin: str = Depends(require_admin),
    limit: int = 50
):
    """
    [ADMIN] Obtener alertas recientes del sistema.
    Requiere CLONNECT_ADMIN_KEY.

    Nota: Las alertas se envían a Telegram, este endpoint
    es para consultar un historial local si está habilitado.
    """
    try:
        # Leer alertas del log si existe
        alerts = []
        log_file = os.path.join(os.getenv("DATA_PATH", "./data"), "alerts.log")

        if os.path.exists(log_file):
            with open(log_file, "r") as f:
                lines = f.readlines()[-limit:]
                for line in lines:
                    try:
                        import json
                        alert = json.loads(line.strip())
                        alerts.append(alert)
                    except Exception as e:
                        logger.debug(f"Skipping malformed alert line: {e}")

        return {
            "status": "ok",
            "alerts": alerts,
            "total": len(alerts),
            "telegram_enabled": os.getenv("TELEGRAM_ALERTS_ENABLED", "false").lower() == "true"
        }

    except Exception as e:
        logger.error(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/creators/{creator_id}/pause")
async def admin_pause_creator(
    creator_id: str,
    reason: str = "Pausado por admin",
    admin: str = Depends(require_admin)
):
    """
    [ADMIN] Pausar el bot de cualquier creador.
    Requiere CLONNECT_ADMIN_KEY.
    """
    try:
        success = config_manager.set_active(creator_id, False, reason)

        if not success:
            raise HTTPException(status_code=404, detail="Creator not found")

        logger.warning(f"Admin paused bot for creator {creator_id}: {reason}")

        return {
            "status": "ok",
            "creator_id": creator_id,
            "is_active": False,
            "reason": reason
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing creator: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/creators/{creator_id}/resume")
async def admin_resume_creator(
    creator_id: str,
    admin: str = Depends(require_admin)
):
    """
    [ADMIN] Reanudar el bot de cualquier creador.
    Requiere CLONNECT_ADMIN_KEY.
    """
    try:
        success = config_manager.set_active(creator_id, True)

        if not success:
            raise HTTPException(status_code=404, detail="Creator not found")

        logger.info(f"Admin resumed bot for creator {creator_id}")

        return {
            "status": "ok",
            "creator_id": creator_id,
            "is_active": True
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming creator: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/creator/{creator_id}/reset")
async def reset_creator_data(
    creator_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
):
    """
    Reset all test/follower data for a creator.

    Deletes:
    - All followers (data/followers/{creator_id}/)
    - All analytics (data/analytics/{creator_id}/)

    Keeps:
    - Creator config (data/creators/{creator_id}.json)
    - Products (data/products/{creator_id}/)

    Requires creator API key or admin key.
    """
    await require_creator_or_admin(creator_id, x_api_key)

    data_path = os.getenv("DATA_PATH", "./data")
    deleted = {
        "followers": 0,
        "analytics": 0
    }
    errors = []

    # Delete followers directory
    followers_path = os.path.join(data_path, "followers", creator_id)
    if os.path.exists(followers_path):
        try:
            for file in os.listdir(followers_path):
                file_path = os.path.join(followers_path, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    deleted["followers"] += 1
            logger.info(f"Deleted {deleted['followers']} follower files for {creator_id}")
        except Exception as e:
            errors.append(f"Error deleting followers: {e}")
            logger.error(f"Error deleting followers for {creator_id}: {e}")

    # Delete analytics directory
    analytics_path = os.path.join(data_path, "analytics", creator_id)
    if os.path.exists(analytics_path):
        try:
            for file in os.listdir(analytics_path):
                file_path = os.path.join(analytics_path, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    deleted["analytics"] += 1
            logger.info(f"Deleted {deleted['analytics']} analytics files for {creator_id}")
        except Exception as e:
            errors.append(f"Error deleting analytics: {e}")
            logger.error(f"Error deleting analytics for {creator_id}: {e}")

    # Clear memory store cache if exists
    try:
        memory_store.clear_creator_cache(creator_id)
    except Exception as e:
        logger.debug(f"Memory store cache clear skipped: {e}")

    return {
        "status": "ok" if not errors else "partial",
        "creator_id": creator_id,
        "deleted": deleted,
        "errors": errors if errors else None,
        "note": "Config and products were preserved"
    }


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

    # Start nurturing scheduler
    try:
        from api.routers.nurturing import start_scheduler
        start_scheduler()
        logger.info("Nurturing scheduler started")
    except Exception as e:
        logger.error(f"Failed to start nurturing scheduler: {e}")

    logger.info("Ready to receive requests!")


# ============ CONVERSATION ACTIONS ============

@app.post("/dm/conversations/{creator_id}/{conversation_id}/archive")
async def archive_conversation_endpoint(creator_id: str, conversation_id: str):
    # Try PostgreSQL first
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services import db_service
            success = db_service.archive_conversation(creator_id, conversation_id)
            if success:
                return {"status": "ok", "archived": True}
        except Exception as e:
            logger.warning(f"PostgreSQL archive failed: {e}")
    # Fallback to JSON files
    try:
        file_path = f"data/followers/{creator_id}/{conversation_id}.json"
        if not os.path.exists(file_path):
            return {"status": "error", "message": "Conversation not found"}
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["archived"] = True
        data["is_lead"] = False
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return {"status": "ok", "archived": True}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/dm/conversations/{creator_id}/{conversation_id}/spam")
async def mark_conversation_spam_endpoint(creator_id: str, conversation_id: str):
    # Try PostgreSQL first
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services import db_service
            success = db_service.mark_conversation_spam(creator_id, conversation_id)
            if success:
                return {"status": "ok", "spam": True}
        except Exception as e:
            logger.warning(f"PostgreSQL spam failed: {e}")
    # Fallback to JSON files
    try:
        file_path = f"data/followers/{creator_id}/{conversation_id}.json"
        if not os.path.exists(file_path):
            return {"status": "error", "message": "Conversation not found"}
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["spam"] = True
        data["is_lead"] = False
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # Invalidate cache
        agent = get_dm_agent(creator_id)
        cache_key = f"{creator_id}:{conversation_id}"
        if cache_key in agent.memory_store._cache:
            del agent.memory_store._cache[cache_key]
        return {"status": "ok", "spam": True}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.delete("/dm/conversations/{creator_id}/{conversation_id}")
async def delete_conversation_endpoint(creator_id: str, conversation_id: str):
    # Try PostgreSQL first
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services import db_service
            success = db_service.delete_conversation(creator_id, conversation_id)
            if success:
                return {"status": "ok", "deleted": conversation_id}
        except Exception as e:
            logger.warning(f"PostgreSQL delete failed: {e}")
    # Fallback to JSON files
    try:
        file_path = f"data/followers/{creator_id}/{conversation_id}.json"
        if not os.path.exists(file_path):
            return {"status": "error", "message": "Conversation not found"}
        os.remove(file_path)
        return {"status": "ok", "deleted": conversation_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ============ ARCHIVED/SPAM MANAGEMENT ============

@app.get("/dm/conversations/{creator_id}/archived")
async def get_archived_conversations(creator_id: str):
    """Get all archived and spam conversations"""
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services import db_service
            from api.services.db_service import get_session
            from api.models import Creator, Lead, Message

            session = get_session()
            if not session:
                return {"status": "error", "conversations": []}

            try:
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    return {"status": "ok", "conversations": []}

                leads = session.query(Lead).filter_by(creator_id=creator.id).filter(
                    Lead.status.in_(["archived", "spam"])
                ).order_by(Lead.last_contact_at.desc()).all()

                conversations = []
                for lead in leads:
                    # Only count user messages, not bot responses
                    msg_count = session.query(Message).filter_by(lead_id=lead.id, role='user').count()
                    conversations.append({
                        "id": str(lead.id),
                        "follower_id": lead.platform_user_id or str(lead.id),
                        "username": lead.username,
                        "name": lead.full_name,
                        "platform": lead.platform or "instagram",
                        "status": lead.status,
                        "total_messages": msg_count,
                        "purchase_intent": lead.purchase_intent or 0.0,
                        "last_contact": lead.last_contact_at.isoformat() if lead.last_contact_at else None,
                    })

                return {"status": "ok", "conversations": conversations}
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Get archived failed: {e}")
            return {"status": "error", "message": str(e), "conversations": []}
    return {"status": "ok", "conversations": []}


@app.post("/dm/conversations/{creator_id}/{conversation_id}/restore")
async def restore_conversation(creator_id: str, conversation_id: str):
    """Restore an archived/spam conversation back to 'new' status"""
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services import db_service
            count = db_service.reset_conversation_status(creator_id, conversation_id)
            if count > 0:
                return {"status": "ok", "restored": True}
            return {"status": "error", "message": "Conversation not found or not archived/spam"}
        except Exception as e:
            logger.warning(f"Restore failed: {e}")
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "Database not configured"}


@app.post("/dm/conversations/{creator_id}/reset")
async def reset_conversations(creator_id: str):
    """Reset all archived/spam conversations back to 'new' status"""
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services import db_service
            count = db_service.reset_conversation_status(creator_id)
            return {"status": "ok", "reset_count": count}
        except Exception as e:
            logger.warning(f"Reset failed: {e}")
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "Database not configured"}


@app.post("/dm/conversations/{creator_id}/sync-messages")
async def sync_messages_from_json_endpoint(creator_id: str):
    """Sync all messages from JSON files to PostgreSQL (one-time migration)"""
    USE_DB = bool(os.getenv("DATABASE_URL"))
    if USE_DB:
        try:
            from api.services.data_sync import sync_messages_from_json
            stats = sync_messages_from_json(creator_id)
            return {"status": "ok", **stats}
        except Exception as e:
            logger.warning(f"Message sync failed: {e}")
            return {"status": "error", "message": str(e)}
    return {"status": "error", "message": "Database not configured"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

@app.get("/debug/agent-config/{creator_id}")
async def debug_agent_config(creator_id: str):
    """Debug: ver qué config carga el DMAgent"""
    from core.dm_agent import DMResponderAgent
    agent = DMResponderAgent(creator_id=creator_id)
    return {
        "clone_tone": agent.creator_config.get("clone_tone"),
        "clone_name": agent.creator_config.get("clone_name"),
        "name": agent.creator_config.get("name"),
        "config_keys": list(agent.creator_config.keys())
    }

@app.get("/debug/system-prompt/{creator_id}")
async def debug_system_prompt(creator_id: str):
    """Debug: ver el system prompt que genera el DMAgent"""
    from core.dm_agent import DMResponderAgent
    agent = DMResponderAgent(creator_id=creator_id)
    prompt = agent._build_system_prompt()
    return {"prompt": prompt[:2000]}  # Primeros 2000 chars
