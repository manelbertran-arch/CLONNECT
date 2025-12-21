"""
Clonnect Creators - Prometheus Metrics
Sistema de metricas para monitoreo con Prometheus
"""

import time
import logging
from typing import Optional, Dict, Any
from functools import wraps
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Intentar importar prometheus_client, pero hacerlo opcional
try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        CollectorRegistry,
        generate_latest,
        CONTENT_TYPE_LATEST,
        multiprocess,
        REGISTRY
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not installed. Metrics will be disabled.")


# Registry global
if PROMETHEUS_AVAILABLE:
    # Usar registry por defecto
    METRICS_REGISTRY = REGISTRY

    # ==========================================================================
    # COUNTERS - Contadores acumulativos
    # ==========================================================================

    # Mensajes procesados
    MESSAGES_PROCESSED = Counter(
        'clonnect_messages_processed_total',
        'Total de mensajes DM procesados',
        ['creator_id', 'platform', 'intent']
    )

    # Errores de LLM
    LLM_ERRORS = Counter(
        'clonnect_llm_errors_total',
        'Total de errores del LLM',
        ['creator_id', 'provider', 'error_type']
    )

    # Escalaciones
    ESCALATIONS = Counter(
        'clonnect_escalations_total',
        'Total de escalaciones a humano',
        ['creator_id', 'reason']
    )

    # Cache hits/misses
    CACHE_HITS = Counter(
        'clonnect_cache_hits_total',
        'Total de cache hits',
        ['creator_id']
    )

    CACHE_MISSES = Counter(
        'clonnect_cache_misses_total',
        'Total de cache misses',
        ['creator_id']
    )

    # Conversiones (ventas)
    CONVERSIONS = Counter(
        'clonnect_conversions_total',
        'Total de conversiones/ventas',
        ['creator_id', 'product_id']
    )

    # API requests
    API_REQUESTS = Counter(
        'clonnect_api_requests_total',
        'Total de requests a la API',
        ['endpoint', 'method', 'status_code']
    )

    # ==========================================================================
    # HISTOGRAMS - Distribuciones de latencia
    # ==========================================================================

    # Latencia de respuesta del LLM
    LLM_RESPONSE_LATENCY = Histogram(
        'clonnect_llm_response_latency_seconds',
        'Latencia de respuesta del LLM en segundos',
        ['creator_id', 'provider'],
        buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0)
    )

    # Tiempo total de procesamiento de DM
    DM_PROCESSING_TIME = Histogram(
        'clonnect_dm_processing_time_seconds',
        'Tiempo total de procesamiento de DM',
        ['creator_id', 'intent'],
        buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0)
    )

    # Latencia de API
    API_REQUEST_LATENCY = Histogram(
        'clonnect_api_request_latency_seconds',
        'Latencia de requests HTTP',
        ['endpoint', 'method'],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
    )

    # ==========================================================================
    # GAUGES - Valores instantaneos
    # ==========================================================================

    # Conversaciones activas
    ACTIVE_CONVERSATIONS = Gauge(
        'clonnect_active_conversations',
        'Numero de conversaciones activas',
        ['creator_id']
    )

    # Leads calientes
    HOT_LEADS = Gauge(
        'clonnect_hot_leads',
        'Numero de leads calientes (score >= 0.7)',
        ['creator_id']
    )

    # Leads totales
    TOTAL_LEADS = Gauge(
        'clonnect_total_leads',
        'Numero total de leads',
        ['creator_id']
    )

    # Bot activo
    BOT_ACTIVE = Gauge(
        'clonnect_bot_active',
        'Estado del bot (1=activo, 0=pausado)',
        ['creator_id']
    )

    # Health status
    HEALTH_STATUS = Gauge(
        'clonnect_health_status',
        'Estado de salud del servicio (1=healthy, 0=unhealthy)',
        ['component']
    )

else:
    # Dummy classes cuando prometheus no esta disponible
    class DummyMetric:
        def labels(self, *args, **kwargs):
            return self
        def inc(self, amount=1):
            pass
        def dec(self, amount=1):
            pass
        def set(self, value):
            pass
        def observe(self, value):
            pass

    METRICS_REGISTRY = None
    MESSAGES_PROCESSED = DummyMetric()
    LLM_ERRORS = DummyMetric()
    ESCALATIONS = DummyMetric()
    CACHE_HITS = DummyMetric()
    CACHE_MISSES = DummyMetric()
    CONVERSIONS = DummyMetric()
    API_REQUESTS = DummyMetric()
    LLM_RESPONSE_LATENCY = DummyMetric()
    DM_PROCESSING_TIME = DummyMetric()
    API_REQUEST_LATENCY = DummyMetric()
    ACTIVE_CONVERSATIONS = DummyMetric()
    HOT_LEADS = DummyMetric()
    TOTAL_LEADS = DummyMetric()
    BOT_ACTIVE = DummyMetric()
    HEALTH_STATUS = DummyMetric()


# ==========================================================================
# FUNCIONES HELPER
# ==========================================================================

def get_metrics() -> bytes:
    """Generar metricas en formato Prometheus"""
    if not PROMETHEUS_AVAILABLE:
        return b"# Prometheus metrics disabled - install prometheus_client\n"
    return generate_latest(METRICS_REGISTRY)


def get_content_type() -> str:
    """Obtener content type para metricas"""
    if PROMETHEUS_AVAILABLE:
        return CONTENT_TYPE_LATEST
    return "text/plain"


@contextmanager
def track_time(histogram, **labels):
    """Context manager para medir tiempo"""
    start = time.time()
    try:
        yield
    finally:
        duration = time.time() - start
        histogram.labels(**labels).observe(duration)


def track_llm_latency(creator_id: str, provider: str):
    """Decorator para medir latencia LLM"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                LLM_RESPONSE_LATENCY.labels(
                    creator_id=creator_id,
                    provider=provider
                ).observe(duration)
        return wrapper
    return decorator


def record_message_processed(
    creator_id: str,
    platform: str = "instagram",
    intent: str = "unknown"
):
    """Registrar mensaje procesado"""
    MESSAGES_PROCESSED.labels(
        creator_id=creator_id,
        platform=platform,
        intent=intent
    ).inc()


def record_llm_error(
    creator_id: str,
    provider: str,
    error_type: str
):
    """Registrar error de LLM"""
    LLM_ERRORS.labels(
        creator_id=creator_id,
        provider=provider,
        error_type=error_type
    ).inc()


def record_escalation(creator_id: str, reason: str):
    """Registrar escalacion"""
    ESCALATIONS.labels(
        creator_id=creator_id,
        reason=reason
    ).inc()


def record_cache_hit(creator_id: str):
    """Registrar cache hit"""
    CACHE_HITS.labels(creator_id=creator_id).inc()


def record_cache_miss(creator_id: str):
    """Registrar cache miss"""
    CACHE_MISSES.labels(creator_id=creator_id).inc()


def record_conversion(creator_id: str, product_id: str):
    """Registrar conversion"""
    CONVERSIONS.labels(
        creator_id=creator_id,
        product_id=product_id
    ).inc()


def record_api_request(
    endpoint: str,
    method: str,
    status_code: int,
    latency: Optional[float] = None
):
    """Registrar request de API"""
    API_REQUESTS.labels(
        endpoint=endpoint,
        method=method,
        status_code=str(status_code)
    ).inc()

    if latency is not None:
        API_REQUEST_LATENCY.labels(
            endpoint=endpoint,
            method=method
        ).observe(latency)


def update_active_conversations(creator_id: str, count: int):
    """Actualizar contador de conversaciones activas"""
    ACTIVE_CONVERSATIONS.labels(creator_id=creator_id).set(count)


def update_hot_leads(creator_id: str, count: int):
    """Actualizar contador de leads calientes"""
    HOT_LEADS.labels(creator_id=creator_id).set(count)


def update_total_leads(creator_id: str, count: int):
    """Actualizar contador de leads totales"""
    TOTAL_LEADS.labels(creator_id=creator_id).set(count)


def update_bot_status(creator_id: str, is_active: bool):
    """Actualizar estado del bot"""
    BOT_ACTIVE.labels(creator_id=creator_id).set(1 if is_active else 0)


def update_health_status(component: str, is_healthy: bool):
    """Actualizar estado de salud"""
    HEALTH_STATUS.labels(component=component).set(1 if is_healthy else 0)


# ==========================================================================
# MIDDLEWARE PARA FASTAPI
# ==========================================================================

class MetricsMiddleware:
    """Middleware para capturar metricas de requests HTTP"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.time()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # Registrar metricas
            duration = time.time() - start_time
            path = scope.get("path", "/")
            method = scope.get("method", "GET")

            # Normalizar paths con IDs dinamicos
            normalized_path = normalize_path(path)

            record_api_request(
                endpoint=normalized_path,
                method=method,
                status_code=status_code,
                latency=duration
            )


def normalize_path(path: str) -> str:
    """Normalizar path reemplazando IDs dinamicos"""
    import re
    # Reemplazar UUIDs
    path = re.sub(
        r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
        '{id}',
        path,
        flags=re.IGNORECASE
    )
    # Reemplazar IDs numericos
    path = re.sub(r'/\d+(?=/|$)', '/{id}', path)
    # Reemplazar creator_ids (alfanumericos con guiones)
    path = re.sub(r'/[a-zA-Z0-9_-]+(?=/|$)', '/{id}', path)
    return path
