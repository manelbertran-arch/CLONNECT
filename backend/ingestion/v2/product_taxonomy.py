"""
Product Taxonomy - Signal-Based Classification

Taxonomía de contenido: product, service, resource.
Incluye enums, dataclasses, constantes de taxonomía y funciones de clasificación.
"""

import re
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ProductSignal(Enum):
    """Señales que indican que algo es un producto real."""
    DEDICATED_PAGE = "dedicated_page"
    CTA_PRESENT = "cta_present"
    PRICE_VISIBLE = "price_visible"
    SUBSTANTIAL_DESCRIPTION = "substantial_description"
    PAYMENT_LINK = "payment_link"
    CLEAR_TITLE = "clear_title"


@dataclass
class DetectedProduct:
    """
    Producto/Servicio/Recurso detectado con todas sus pruebas.

    Taxonomía:
    - category: 'product' | 'service' | 'resource'
    - product_type: depende de category
    """
    name: str
    description: str
    price: Optional[float]  # NULL si no encontrado, NUNCA inventado
    currency: str = "EUR"
    source_url: str = ""
    source_html: str = ""  # Prueba del origen
    price_source_text: Optional[str] = None  # Texto literal donde se encontró el precio
    signals_matched: List[str] = field(default_factory=list)
    confidence: float = 0.0
    # Taxonomía
    category: str = "product"  # product, service, resource
    product_type: str = "otro"  # Depende de category
    is_free: bool = False  # True para discovery calls gratuitas
    short_description: str = ""  # Descripción corta (max 150 chars)
    payment_link: str = ""  # URL de compra/pago/reserva

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "short_description": self.short_description,
            "category": self.category,
            "product_type": self.product_type,
            "is_free": self.is_free,
            "price": self.price,
            "currency": self.currency,
            "source_url": self.source_url,
            "payment_link": self.payment_link,
            "price_source_text": self.price_source_text,
            "signals_matched": self.signals_matched,
            "confidence": self.confidence,
        }


# =============================================================================
# TAXONOMÍA: PRODUCTO vs SERVICIO vs RECURSO
# =============================================================================

# Keywords para detectar RECURSO (contenido gratuito)
RESOURCE_KEYWORDS = [
    'podcast', 'spotify', 'apple podcast', 'youtube', 'canal',
    'blog', 'artículo', 'article', 'newsletter', 'semanal'
]

# Keywords para detectar SERVICIO (requiere interacción humana)
SERVICE_KEYWORDS = [
    'coaching', 'sesión', 'session', 'consultoría', 'consultoria',
    'mentoría', 'mentoring', '1:1', 'one-on-one', 'call',
    'llamada', 'discovery', 'agendar', 'reservar', 'calendly',
    'booking', 'acompañamiento', 'asesoría', 'asesoria'
]

# Subtipos para cada categoría
PRODUCT_TYPES = {
    'ebook': ['ebook', 'guía', 'guia', 'pdf', 'descargable', 'download', 'libro'],
    'curso': ['curso', 'course', 'programa', 'formación', 'training', 'masterclass',
              'workshop', 'taller', 'challenge', 'reto', 'días', 'dias', 'semanas',
              'módulo', 'lecciones'],
    'plantilla': ['plantilla', 'template', 'notion', 'spreadsheet', 'excel', 'canva', 'figma'],
    'membership': ['membresía', 'membership', 'suscripción', 'subscription', 'mensual',
                   'anual', 'comunidad', 'community', 'club']
}

SERVICE_TYPES = {
    'coaching': ['coaching', 'coach'],
    'mentoria': ['mentoría', 'mentoring', 'mentor'],
    'consultoria': ['consultoría', 'consultoria', 'consulting', 'asesoría', 'asesoria'],
    'call': ['call', 'llamada', 'discovery'],
    'sesion': ['sesión', 'session', '1:1', 'one-on-one', 'acompañamiento']
}

RESOURCE_TYPES = {
    'podcast': ['podcast', 'spotify', 'apple podcast'],
    'blog': ['blog', 'artículo', 'article', 'post'],
    'youtube': ['youtube', 'canal', 'video'],
    'newsletter': ['newsletter', 'semanal', 'boletín'],
    'free_guide': ['guía gratuita', 'recurso gratuito', 'descarga gratis']
}


def es_recurso(text: str, url: str) -> bool:
    """Detecta si es un RECURSO (podcast, blog, youtube, etc.)"""
    combined = f"{text} {url}".lower()
    return any(kw in combined for kw in RESOURCE_KEYWORDS)


def es_servicio(text: str, url: str) -> bool:
    """Detecta si es un SERVICIO (coaching, sesión, call, etc.)"""
    combined = f"{text} {url}".lower()
    return any(kw in combined for kw in SERVICE_KEYWORDS)


def detectar_tipo_recurso(text: str, url: str) -> str:
    """Detecta el subtipo de recurso."""
    combined = f"{text} {url}".lower()
    for tipo, keywords in RESOURCE_TYPES.items():
        if any(kw in combined for kw in keywords):
            return tipo
    return 'otro'


def detectar_tipo_servicio(text: str, url: str) -> str:
    """Detecta el subtipo de servicio."""
    combined = f"{text} {url}".lower()
    for tipo, keywords in SERVICE_TYPES.items():
        if any(kw in combined for kw in keywords):
            return tipo
    return 'otro'


def detectar_tipo_producto(name: str, description: str, url: str) -> str:
    """Detecta el subtipo de producto."""
    combined = f"{name} {description} {url}".lower()
    for tipo, keywords in PRODUCT_TYPES.items():
        if any(kw in combined for kw in keywords):
            return tipo
    return 'otro'


# =============================================================================
# PROTECTED BLOCK: Content Taxonomy Classification
# Modified: 2026-01-16
# Reason: Sistema de taxonomía (product/service/resource) para catálogo
# Do not modify without running full test suite and verifying bot responses
# =============================================================================
def clasificar_contenido(name: str, description: str, url: str, tiene_precio: bool, es_gratis: bool) -> Dict:
    """
    Clasifica contenido en la taxonomía: product, service, resource.

    Returns:
        {
            'category': 'product' | 'service' | 'resource',
            'type': subtipo específico,
            'is_free': bool
        }
    """
    text = f"{name} {description}".lower()

    # 1. RECURSO (podcast, blog, youtube - sin precio, no gratis explícito)
    if es_recurso(text, url) and not tiene_precio and not es_gratis:
        return {
            'category': 'resource',
            'type': detectar_tipo_recurso(text, url),
            'is_free': True  # Recursos son siempre gratuitos
        }

    # 2. SERVICIO (coaching, sesión, call - con o sin precio)
    if es_servicio(text, url):
        return {
            'category': 'service',
            'type': detectar_tipo_servicio(text, url),
            'is_free': es_gratis and not tiene_precio
        }

    # 3. PRODUCTO (tiene precio, es vendible)
    if tiene_precio or es_gratis:
        return {
            'category': 'product',
            'type': detectar_tipo_producto(name, description, url),
            'is_free': es_gratis and not tiene_precio
        }

    # 4. No clasificable
    return None


def detectar_moneda(text: str, price_text: str = "") -> str:
    """
    Detecta la moneda basándose en símbolos/keywords.

    Returns: EUR, USD, GBP, MXN, etc.
    """
    combined = f"{text} {price_text}"

    # USD
    if '$' in combined and '€' not in combined:
        if any(kw in combined.lower() for kw in ['usd', 'dólar', 'dollar', 'us$']):
            return 'USD'
        # Si hay $ pero no hay contexto de EUR, probablemente USD
        if '€' not in combined and 'eur' not in combined.lower():
            return 'USD'

    # GBP
    if '£' in combined or 'GBP' in combined or 'libra' in combined.lower():
        return 'GBP'

    # MXN
    if 'MXN' in combined or 'peso' in combined.lower():
        return 'MXN'

    # EUR (default para España/LATAM)
    return 'EUR'


def extraer_descripcion_corta(description: str, max_chars: int = 150) -> str:
    """
    Extrae una descripción corta del producto.
    """
    if not description:
        return ""

    # Limpiar y truncar
    desc = description.strip()
    desc = re.sub(r'\s+', ' ', desc)  # Normalizar espacios

    if len(desc) <= max_chars:
        return desc

    # Truncar en límite de palabra
    truncated = desc[:max_chars].rsplit(' ', 1)[0]
    return truncated + '...'


def extraer_payment_link(page_url: str, page_content: str) -> str:
    """
    Extrae el enlace de compra/pago.

    Prioridad:
    1. Link externo a plataforma de pago (Gumroad, Stripe, Calendly, etc.)
    2. URL de la página del producto
    """
    # Buscar links a plataformas de pago en el contenido
    payment_platforms = [
        r'https?://[^\s"\'<>]*gumroad\.com[^\s"\'<>]*',
        r'https?://[^\s"\'<>]*hotmart\.com[^\s"\'<>]*',
        r'https?://[^\s"\'<>]*calendly\.com[^\s"\'<>]*',
        r'https?://[^\s"\'<>]*stripe\.com[^\s"\'<>]*',
        r'https?://[^\s"\'<>]*paypal\.com[^\s"\'<>]*',
        r'https?://[^\s"\'<>]*checkout\.stripe\.com[^\s"\'<>]*',
        r'https?://[^\s"\'<>]*buy\.stripe\.com[^\s"\'<>]*',
        r'https?://[^\s"\'<>]*thrivecart\.com[^\s"\'<>]*',
        r'https?://[^\s"\'<>]*teachable\.com[^\s"\'<>]*',
    ]

    for pattern in payment_platforms:
        match = re.search(pattern, page_content, re.IGNORECASE)
        if match:
            return match.group(0)

    # Si no hay link externo, usar la URL de la página
    return page_url


class SuspiciousExtractionError(Exception):
    """Se lanza cuando la extracción parece sospechosa."""
