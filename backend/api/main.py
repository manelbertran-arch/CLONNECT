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
from fastapi.responses import Response, HTMLResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)

# PostgreSQL Init
try:
    from api.database import DATABASE_URL
    from api.init_db import init_database
    if DATABASE_URL:
        init_database()
        print("PostgreSQL connected")
    else:
        print("No DATABASE_URL - using JSON fallback")
except Exception as e:
    print(f"PostgreSQL init failed: {e}")

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
from api.routers import knowledge, analytics, onboarding, admin, connections, oauth
app.include_router(knowledge.router)
app.include_router(analytics.router)
app.include_router(onboarding.router)
app.include_router(admin.router)
app.include_router(connections.router)
app.include_router(oauth.router)

logging.info("Routers loaded: health, dashboard, config, leads, products, analytics, connections, oauth")
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
    "/instagram/webhook",  # Legacy
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
# TELEGRAM WEBHOOK
# ---------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    Recibir updates de Telegram.
    Procesa mensajes entrantes con DMResponderAgent y envia respuestas automaticas.
    """
    try:
        payload = await request.json()
        logger.info(f"Telegram webhook received: {payload}")

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

            # Enviar respuesta a Telegram
            if bot_reply and TELEGRAM_BOT_TOKEN:
                telegram_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                async with httpx.AsyncClient() as client:
                    await client.post(telegram_api, json={
                        "chat_id": chat_id,
                        "text": bot_reply,
                        "parse_mode": "HTML"
                    })
                logger.info(f"Telegram response sent to chat {chat_id}")

            return {
                "status": "ok",
                "chat_id": chat_id,
                "intent": intent,
                "response_sent": bool(bot_reply and TELEGRAM_BOT_TOKEN)
            }

        except Exception as e:
            logger.error(f"Error processing Telegram message: {e}")
            return {"status": "error", "detail": str(e)}

    except Exception as e:
        logger.error(f"Error in Telegram webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/telegram/status")
async def telegram_status():
    """Obtener estado de la integración de Telegram"""
    return {
        "status": "ok",
        "bot_token_configured": bool(TELEGRAM_BOT_TOKEN),
        "webhook_url": "/webhook/telegram"
    }


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
    config = config_manager.get_config(creator_id)
    # PostgreSQL first
    if USE_DB:
        config = db_service.get_creator_by_name(creator_id)
        if config:
            return {"status": "ok", "config": config}
    if not config:
        raise HTTPException(status_code=404, detail="Creator not found")
    return {"status": "ok", "config": config.to_dict()}


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
    Get booking link for a specific meeting type.

    Meeting types: discovery, consultation, coaching, followup, custom
    """
    try:
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
    """Get all booking links for a creator"""
    try:
        calendar_manager = get_calendar_manager()
        links = calendar_manager.get_all_booking_links(creator_id)

        return {
            "status": "ok",
            "creator_id": creator_id,
            "links": links,
            "count": len(links)
        }

    except Exception as e:
        logger.error(f"Error getting booking links: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/calendar/{creator_id}/links")
async def create_booking_link(
    creator_id: str,
    data: dict = Body(...)
):
    """
    Create a new booking link.

    Body JSON:
        meeting_type: discovery, consultation, coaching, followup, custom
        duration_minutes: Duration in minutes
        title: Link title
        description: Optional description
        url: Booking URL (from Calendly/Cal.com or custom)
        platform: calendly, calcom, or manual
    """
    try:
        calendar_manager = get_calendar_manager()

        # Extract data from body
        meeting_type = data.get("meeting_type", "custom")
        duration_minutes = data.get("duration_minutes", data.get("duration", 30))
        title = data.get("title", "")
        description = data.get("description", "")
        url = data.get("url", "")
        platform = data.get("platform", "manual")

        link = calendar_manager.create_booking_link(
            creator_id=creator_id,
            meeting_type=meeting_type,
            duration_minutes=duration_minutes,
            title=title,
            description=description,
            url=url,
            platform=platform
        )

        return {
            "status": "ok",
            "link": link.to_dict()
        }

    except Exception as e:
        logger.error(f"Error creating booking link: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
