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
        generate_latest,
        CONTENT_TYPE_LATEST,
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

    # ==========================================================================
    # INGESTION PIPELINE METRICS
    # ==========================================================================

    # Counters
    INGESTION_PAGES_SCRAPED = Counter(
        'ingestion_pages_scraped_total',
        'Total pages successfully scraped',
        ['creator_id']
    )

    INGESTION_PAGES_FAILED = Counter(
        'ingestion_pages_failed_total',
        'Total pages that failed to scrape',
        ['creator_id', 'error_type']
    )

    INGESTION_PRODUCTS_DETECTED = Counter(
        'ingestion_products_detected_total',
        'Total products detected by product detector',
        ['creator_id']
    )

    INGESTION_FAQS_EXTRACTED = Counter(
        'ingestion_faqs_extracted_total',
        'Total FAQs extracted by FAQ extractor',
        ['creator_id']
    )

    INGESTION_POSTS_INDEXED = Counter(
        'ingestion_posts_indexed_total',
        'Total Instagram posts indexed',
        ['creator_id']
    )

    INGESTION_CHUNKS_SAVED = Counter(
        'ingestion_chunks_saved_total',
        'Total content chunks saved to database',
        ['creator_id', 'source_type']
    )

    INGESTION_ERRORS = Counter(
        'ingestion_errors_total',
        'Total ingestion errors by type',
        ['error_type']
    )

    # Histograms
    INGESTION_SCRAPE_DURATION = Histogram(
        'ingestion_scrape_duration_seconds',
        'Time spent scraping a single page',
        buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60)
    )

    INGESTION_EXTRACT_DURATION = Histogram(
        'ingestion_extract_duration_seconds',
        'Time spent extracting content',
        ['phase'],  # products, faqs, text
        buckets=(0.01, 0.05, 0.1, 0.5, 1, 5)
    )

    INGESTION_TOTAL_DURATION = Histogram(
        'ingestion_total_duration_seconds',
        'Total ingestion pipeline duration per creator',
        buckets=(1, 5, 10, 30, 60, 120, 300, 600)
    )

    INGESTION_CHUNKS_PER_CREATOR = Histogram(
        'ingestion_chunks_per_creator',
        'Number of chunks created per creator ingestion',
        buckets=(10, 50, 100, 500, 1000, 5000)
    )

    # Gauges
    INGESTION_ACTIVE_SCRAPES = Gauge(
        'ingestion_active_scrapes',
        'Number of currently active scrape operations'
    )

    INGESTION_CIRCUIT_BREAKER_STATE = Gauge(
        'ingestion_circuit_breaker_state',
        'Circuit breaker state (0=closed, 1=half-open, 2=open)',
        ['name']
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
    # Ingestion metrics
    INGESTION_PAGES_SCRAPED = DummyMetric()
    INGESTION_PAGES_FAILED = DummyMetric()
    INGESTION_PRODUCTS_DETECTED = DummyMetric()
    INGESTION_FAQS_EXTRACTED = DummyMetric()
    INGESTION_POSTS_INDEXED = DummyMetric()
    INGESTION_CHUNKS_SAVED = DummyMetric()
    INGESTION_ERRORS = DummyMetric()
    INGESTION_SCRAPE_DURATION = DummyMetric()
    INGESTION_EXTRACT_DURATION = DummyMetric()
    INGESTION_TOTAL_DURATION = DummyMetric()
    INGESTION_CHUNKS_PER_CREATOR = DummyMetric()
    INGESTION_ACTIVE_SCRAPES = DummyMetric()
    INGESTION_CIRCUIT_BREAKER_STATE = DummyMetric()


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


# ==========================================================================
# INGESTION PIPELINE HELPER FUNCTIONS
# ==========================================================================

# Track ingestion start time per creator
_ingestion_start_times: Dict[str, float] = {}


def record_page_scraped(creator_id: str):
    """Record a successfully scraped page."""
    INGESTION_PAGES_SCRAPED.labels(creator_id=creator_id).inc()


def record_page_failed(creator_id: str, error_type: str):
    """Record a failed page scrape."""
    INGESTION_PAGES_FAILED.labels(creator_id=creator_id, error_type=error_type).inc()


def record_products_detected(creator_id: str, count: int = 1):
    """Record products detected."""
    for _ in range(count):
        INGESTION_PRODUCTS_DETECTED.labels(creator_id=creator_id).inc()


def record_faqs_extracted(creator_id: str, count: int = 1):
    """Record FAQs extracted."""
    for _ in range(count):
        INGESTION_FAQS_EXTRACTED.labels(creator_id=creator_id).inc()


def record_posts_indexed(creator_id: str, count: int = 1):
    """Record Instagram posts indexed."""
    for _ in range(count):
        INGESTION_POSTS_INDEXED.labels(creator_id=creator_id).inc()


def record_chunks_saved(creator_id: str, count: int, source_type: str = "mixed"):
    """Record chunks saved to database."""
    for _ in range(count):
        INGESTION_CHUNKS_SAVED.labels(creator_id=creator_id, source_type=source_type).inc()


def record_ingestion_error(error_type: str):
    """Record an ingestion error."""
    INGESTION_ERRORS.labels(error_type=error_type).inc()


def observe_scrape_duration(duration_seconds: float):
    """Record scrape duration."""
    INGESTION_SCRAPE_DURATION.observe(duration_seconds)


def observe_extract_duration(phase: str, duration_seconds: float):
    """Record extraction duration by phase."""
    INGESTION_EXTRACT_DURATION.labels(phase=phase).observe(duration_seconds)


def start_ingestion(creator_id: str):
    """Mark start of ingestion for a creator."""
    _ingestion_start_times[creator_id] = time.time()
    INGESTION_ACTIVE_SCRAPES.inc()
    logger.info(f"[metrics] Starting ingestion for {creator_id}")


def end_ingestion(creator_id: str, chunks_count: int = 0):
    """Mark end of ingestion and record duration."""
    if creator_id in _ingestion_start_times:
        duration = time.time() - _ingestion_start_times[creator_id]
        INGESTION_TOTAL_DURATION.observe(duration)
        del _ingestion_start_times[creator_id]
        logger.info(f"[metrics] Completed ingestion for {creator_id} in {duration:.2f}s")
    else:
        duration = 0

    if chunks_count > 0:
        INGESTION_CHUNKS_PER_CREATOR.observe(chunks_count)

    INGESTION_ACTIVE_SCRAPES.dec()

    return duration


def set_circuit_breaker_state(name: str, state: int):
    """
    Set circuit breaker state metric.

    Args:
        name: Circuit breaker name (e.g., 'instagram_api', 'web_scraper')
        state: 0=closed, 1=half-open, 2=open
    """
    INGESTION_CIRCUIT_BREAKER_STATE.labels(name=name).set(state)


@contextmanager
def track_scrape_time():
    """Context manager to track scrape duration."""
    start = time.time()
    yield
    INGESTION_SCRAPE_DURATION.observe(time.time() - start)


@contextmanager
def track_extract_time(phase: str):
    """Context manager to track extraction duration."""
    start = time.time()
    yield
    INGESTION_EXTRACT_DURATION.labels(phase=phase).observe(time.time() - start)


def get_ingestion_summary(creator_id: str) -> Dict[str, Any]:
    """
    Get a summary of ingestion metrics for logging.

    Note: This returns approximations as Prometheus metrics are designed
    for scraping, not direct querying. Use for logging purposes only.
    """
    return {
        "creator_id": creator_id,
        "prometheus_available": PROMETHEUS_AVAILABLE,
        "metrics_note": "Query Prometheus directly for accurate values"
    }


def log_ingestion_complete(
    creator_id: str,
    pages_scraped: int = 0,
    pages_failed: int = 0,
    products_detected: int = 0,
    faqs_extracted: int = 0,
    posts_indexed: int = 0,
    chunks_saved: int = 0,
    duration_seconds: float = 0
):
    """
    Log structured summary at end of ingestion.

    Use this for structured logging even when Prometheus is available.
    """
    logger.info(
        "ingestion_complete",
        extra={
            "creator_id": creator_id,
            "pages_scraped": pages_scraped,
            "pages_failed": pages_failed,
            "products_detected": products_detected,
            "faqs_extracted": faqs_extracted,
            "posts_indexed": posts_indexed,
            "chunks_saved": chunks_saved,
            "duration_seconds": round(duration_seconds, 2)
        }
    )

    # Also log human-readable summary
    logger.info(
        f"[Ingestion Complete] creator={creator_id} "
        f"pages={pages_scraped} failed={pages_failed} "
        f"products={products_detected} faqs={faqs_extracted} "
        f"posts={posts_indexed} chunks={chunks_saved} "
        f"duration={duration_seconds:.2f}s"
    )
