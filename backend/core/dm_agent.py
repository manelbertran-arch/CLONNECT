"""
DMResponderAgent - Agent simplificado para responder DMs
Carga configuración y productos directamente de JSON
Genera respuestas personalizadas usando Groq/LLM
"""

import json
import os
import time
import logging
import random
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from core.llm import get_llm_client
from core.nurturing import get_nurturing_manager, should_schedule_nurturing
from core.i18n import (
    detect_language,
    get_i18n_manager,
    translate_response,
    DEFAULT_LANGUAGE
)
from core.analytics import get_analytics_manager, detect_platform
from core.gdpr import get_gdpr_manager, ConsentType
from core.rate_limiter import get_rate_limiter
from core.notifications import get_notification_service, EscalationNotification
from core.cache import get_response_cache
from core.alerts import get_alert_manager
from core.creator_config import CreatorConfigManager
from core.sales_tracker import get_sales_tracker
from core.guardrails import get_response_guardrail
from core.reasoning import get_self_consistency_validator, get_chain_of_thought_reasoner
from core.tone_service import get_tone_prompt_section, get_tone_language, get_tone_dialect
from core.citation_service import get_citation_prompt_section
from core.bot_question_analyzer import get_bot_question_analyzer, QuestionType, is_short_affirmation
from core.metrics import (
    record_message_processed,
    record_llm_error,
    record_escalation,
    record_cache_hit,
    record_cache_miss,
    DM_PROCESSING_TIME
)

# =============================================================================
# Personalization Modules (Memory Engine Migration)
# =============================================================================
from core.rag.reranker import rerank, ENABLE_RERANKING
from core.user_profiles import get_user_profile
from core.personalized_ranking import personalize_results, adapt_system_prompt
from core.semantic_memory import get_conversation_memory, ENABLE_SEMANTIC_MEMORY


# PostgreSQL integration
USE_POSTGRES = bool(os.getenv("DATABASE_URL"))
db_service = None
if USE_POSTGRES:
    try:
        from api.services import db_service
    except ImportError:
        try:
            from api import db_service
        except ImportError:
            USE_POSTGRES = False

logger = logging.getLogger(__name__)


# =============================================================================
# P0 FIX: Retry decorator for DB operations
# =============================================================================

def retry_db_operation(max_retries: int = 3, delay: float = 0.5, operation_name: str = "DB"):
    """
    Decorator to retry database operations with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries (doubles each attempt)
        operation_name: Name for logging purposes
    """
    import asyncio
    from functools import wraps

    def decorator(func):
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    wait_time = delay * (2 ** attempt)
                    logger.warning(
                        f"[P0-RETRY] {operation_name} failed (attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {wait_time:.1f}s..."
                    )
                    if attempt < max_retries - 1:
                        time.sleep(wait_time)
            logger.error(f"[P0-RETRY] {operation_name} FAILED after {max_retries} attempts: {last_error}")
            return None

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    wait_time = delay * (2 ** attempt)
                    logger.warning(
                        f"[P0-RETRY] {operation_name} failed (attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {wait_time:.1f}s..."
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
            logger.error(f"[P0-RETRY] {operation_name} FAILED after {max_retries} attempts: {last_error}")
            return None

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Configuration: Set to True to require consent before processing
REQUIRE_CONSENT = os.getenv("REQUIRE_GDPR_CONSENT", "false").lower() == "true"


def get_valid_payment_url(product: Dict[str, Any]) -> str:
    """
    Get a valid payment URL from a product.
    Checks payment_link first, falls back to url if payment_link is not a valid URL.
    """
    payment_link = product.get('payment_link', '')
    url = product.get('url', '')

    # Check if payment_link is a valid URL
    if payment_link and isinstance(payment_link, str) and payment_link.startswith('http'):
        return payment_link

    # Fall back to url
    if url and isinstance(url, str) and url.startswith('http'):
        return url

    return ''


# =============================================================================
# PROTECTED BLOCK: Category-Based Item Formatting
# Modified: 2026-01-16
# Reason: Taxonomía de catálogo (product/service/resource) con respuestas diferenciadas
# Do not modify without testing bot responses for each category type
# =============================================================================

def format_item_by_category(item: Dict[str, Any]) -> str:
    """
    Formatea un item según su categoría para el system prompt.
    """
    category = item.get('category', 'product')
    name = item.get('name', 'Item')
    description = item.get('short_description') or item.get('description', '')
    price = item.get('price', 0)
    currency = item.get('currency', '€')
    is_free = item.get('is_free', False)
    product_type = item.get('product_type', 'otro')
    url = get_valid_payment_url(item)

    if category == 'resource':
        # RECURSO: contenido gratuito
        tipo_texto = {
            'podcast': '🎙️ Podcast',
            'blog': '✍️ Blog',
            'youtube': '📺 YouTube',
            'newsletter': '📧 Newsletter',
            'free_guide': '📚 Guía gratuita'
        }.get(product_type, '📚 Recurso')
        return f"""- {tipo_texto}: {name}
  Descripción: {description[:150] if description else 'Sin descripción'}
  Link: {url or 'No configurado'}
  (GRATUITO - solo mencionar si es relevante, NO vender)"""

    elif category == 'service':
        # SERVICIO: sesiones, coaching, etc.
        tipo_texto = {
            'coaching': '🎯 Coaching',
            'mentoria': '🧭 Mentoría',
            'consultoria': '💼 Consultoría',
            'call': '📞 Llamada',
            'sesion': '🗓️ Sesión'
        }.get(product_type, '🤝 Servicio')

        if is_free or price == 0:
            price_text = "GRATIS"
            action = "Invitar a reservar sin presión"
        else:
            price_text = f"{price}{currency}"
            action = "Mencionar precio y ofrecer agendar"

        return f"""- {tipo_texto}: {name} - {price_text}
  Descripción: {description[:150] if description else 'Sin descripción'}
  Link de reserva: {url or 'No configurado'}
  (Acción: {action})"""

    else:
        # PRODUCTO: algo que se vende
        tipo_texto = {
            'ebook': '📖 Ebook',
            'curso': '🎓 Curso',
            'plantilla': '📄 Plantilla',
            'membership': '👥 Membresía'
        }.get(product_type, '🛒 Producto')

        if is_free or price == 0:
            price_text = "GRATIS"
        else:
            price_text = f"{price}{currency}"

        return f"""- {tipo_texto}: {name} - {price_text}
  Descripción: {description[:150] if description else 'Sin descripción'}
  Link de compra: {url or 'No configurado'}
  (Acción: Dar precio y link de compra)"""


def get_category_instructions() -> str:
    """
    Retorna instrucciones para el bot sobre cómo manejar cada categoría.
    """
    return """
=== CÓMO RESPONDER SEGÚN CATEGORÍA ===

🛒 PRODUCTOS (category: product)
- Menciona el PRECIO directamente cuando pregunten
- Comparte el LINK DE COMPRA
- Usa frases como: "cuesta X€", "puedes comprarlo aquí"
- Objetivo: VENDER

🤝 SERVICIOS (category: service)
- Si es GRATUITO: invita a reservar sin presión ("puedes reservar gratis aquí")
- Si tiene PRECIO: menciona el precio y ofrece agendar
- Usa frases como: "puedes reservar", "¿agendamos una sesión?"
- El link típicamente es Calendly o similar
- Objetivo: AGENDAR

📚 RECURSOS (category: resource)
- NO intentes venderlos (son gratuitos)
- SOLO menciona si es RELEVANTE a la conversación
- Usa frases como: "tengo un podcast donde hablo de esto"
- NO ofrezcas activamente, solo si encaja naturalmente
- Objetivo: DAR VALOR, no vender

=== FIN INSTRUCCIONES DE CATEGORÍA ===
"""


class Intent(Enum):
    """Intenciones posibles del mensaje"""
    GREETING = "greeting"
    INTEREST_SOFT = "interest_soft"
    INTEREST_STRONG = "interest_strong"
    ACKNOWLEDGMENT = "acknowledgment"  # User just confirms/acknowledges (ok, vale, entendido)
    CORRECTION = "correction"  # User corrects a misunderstanding (no te he dicho que...)
    OBJECTION_PRICE = "objection_price"
    OBJECTION_TIME = "objection_time"
    OBJECTION_DOUBT = "objection_doubt"
    OBJECTION_LATER = "objection_later"
    OBJECTION_WORKS = "objection_works"
    OBJECTION_NOT_FOR_ME = "objection_not_for_me"
    OBJECTION_COMPLICATED = "objection_complicated"
    OBJECTION_ALREADY_HAVE = "objection_already_have"
    QUESTION_PRODUCT = "question_product"
    QUESTION_GENERAL = "question_general"
    LEAD_MAGNET = "lead_magnet"
    BOOKING = "booking"  # Quiere agendar una llamada/reunión
    THANKS = "thanks"
    GOODBYE = "goodbye"
    SUPPORT = "support"
    ESCALATION = "escalation"
    OTHER = "other"


# Inicializar intents que no deben cachearse
NON_CACHEABLE_INTENTS = {
    Intent.OBJECTION_PRICE,
    Intent.OBJECTION_TIME,
    Intent.OBJECTION_DOUBT,
    Intent.OBJECTION_LATER,
    Intent.OBJECTION_WORKS,
    Intent.OBJECTION_NOT_FOR_ME,
    Intent.INTEREST_STRONG,  # Conversiones activas
    Intent.ESCALATION,
    Intent.SUPPORT,  # Soporte necesita respuestas personalizadas
    Intent.OTHER,  # Fallback - siempre regenerar para evitar respuestas genéricas
}

# === ANTI-ALUCINACIÓN: Intents que REQUIEREN contenido RAG ===
# Si el RAG no encuentra contenido relevante para estos intents → Escalar al creador
# Intents genéricos (GREETING, THANKS, GOODBYE, OTHER) pueden responder sin RAG
INTENTS_REQUIRING_RAG = {
    Intent.INTEREST_SOFT,
    Intent.INTEREST_STRONG,
    Intent.QUESTION_PRODUCT,
    Intent.QUESTION_GENERAL,
    Intent.OBJECTION_PRICE,
    Intent.OBJECTION_TIME,
    Intent.OBJECTION_DOUBT,
    Intent.OBJECTION_LATER,
    Intent.OBJECTION_WORKS,
    Intent.OBJECTION_NOT_FOR_ME,
    Intent.OBJECTION_COMPLICATED,
    Intent.OBJECTION_ALREADY_HAVE,
    Intent.SUPPORT,
    Intent.LEAD_MAGNET,
}


# === CONVERSION OPTIMIZATION PROMPTS ===
# These prompts are injected dynamically based on user intent and purchase score

PROACTIVE_CLOSE_INSTRUCTION = """
=== CIERRE PROACTIVO (USUARIO CON ALTO INTERÉS) ===
El usuario muestra INTERÉS FUERTE. En tu respuesta:
1. Responde su pregunta de forma concisa
2. Ofrece NATURALMENTE el siguiente paso con el LINK REAL
3. Usa frases como: "Si quieres reservar...", "Puedes apuntarte aquí...", "Te dejo el link..."
4. NUNCA uses [link] o placeholders - usa el URL COMPLETO real
5. No presiones, pero facilita la compra

Ejemplo BUENO: "Son 297€ y tienes garantía de 30 días. Aquí puedes apuntarte: https://pay.ejemplo.com/curso"
Ejemplo MALO: "Son 297€. Si te interesa, [aquí tienes el link]"
=== FIN CIERRE PROACTIVO ===
"""

NO_REPETITION_INSTRUCTION = """
=== REGLA CRÍTICA - NO REPETIR ===
Revisa el HISTORIAL antes de responder:
- NUNCA repitas un saludo si ya saludaste en esta conversación
- NUNCA uses la misma frase dos veces (varía expresiones)
- NUNCA repitas la misma estructura de respuesta
- Si dijiste "genial", "perfecto", "claro" → usa otra palabra diferente
- Si el usuario repite una pregunta, responde DIFERENTE pero con la misma info
- Si ya diste un link, NO lo repitas a menos que lo pidan
=== FIN NO REPETIR ===
"""

COHERENCE_INSTRUCTION = """
=== REGLA CRÍTICA - COHERENCIA ===
Mantén CONSISTENCIA con todo lo dicho:
- Si diste un precio, NO lo cambies
- Si dijiste que algo está disponible, NO digas luego que no
- Si el usuario dio información (nombre, situación), ÚSALA
- Recuerda el contexto: si hablaban de un producto, SIGUE en ese tema
- NO cambies de tema sin razón
- Si no sabes algo, admítelo - NO inventes
- USA la información del follower para personalizar
=== FIN COHERENCIA ===
"""

CONVERSION_INSTRUCTION = """
=== OBJETIVO - CONVERSIÓN ===
Cada respuesta debe ACERCAR al usuario a la acción (compra/reserva):

- Si pregunta info general → responde + menciona UN beneficio del producto
- Si muestra interés → responde + ofrece siguiente paso concreto
- Si tiene objeción → maneja objeción + reafirma valor
- Si está listo → facilita la compra con LINK DIRECTO (no placeholder)
- Si está frío → genera curiosidad sin presionar

NUNCA termines una respuesta sin:
1. Responder lo que preguntó
2. Añadir valor (tip, beneficio, insight breve)
3. Invitar sutilmente al siguiente paso

Ejemplos de CTAs suaves:
- "¿Te cuento más sobre cómo funciona?"
- "¿Quieres que te pase el link?"
- "¿Reservamos una llamada para verlo juntos?"
=== FIN CONVERSIÓN ===
"""

# Keywords that indicate strong interest (for proactive close detection)
STRONG_INTEREST_KEYWORDS = [
    "me interesa", "cuánto cuesta", "cuanto cuesta", "cómo me apunto", "como me apunto",
    "quiero saber más", "quiero saber mas", "cómo funciona", "como funciona",
    "qué incluye", "que incluye", "dónde compro", "donde compro", "cómo pago", "como pago",
    "precio", "comprar", "apuntarme", "inscribirme", "reservar"
]


def apply_voseo(text: str) -> str:
    """
    Convierte texto de tuteo español a voseo argentino.
    Transforma: tú->vos, tienes->tenés, puedes->podés, etc.
    """
    import re

    # Diccionario de conversiones tuteo -> voseo
    conversions = [
        # Pronombres
        (r'\btú\b', 'vos'),
        (r'\bTú\b', 'Vos'),

        # Verbos comunes en presente (2da persona singular)
        (r'\btienes\b', 'tenés'),
        (r'\bTienes\b', 'Tenés'),
        (r'\bpuedes\b', 'podés'),
        (r'\bPuedes\b', 'Podés'),
        (r'\bquieres\b', 'querés'),
        (r'\bQuieres\b', 'Querés'),
        (r'\bsabes\b', 'sabés'),
        (r'\bSabes\b', 'Sabés'),
        (r'\beres\b', 'sos'),
        (r'\bEres\b', 'Sos'),
        (r'\bvienes\b', 'venís'),
        (r'\bpiensas\b', 'pensás'),
        (r'\bsientes\b', 'sentís'),
        (r'\bprefieres\b', 'preferís'),
        (r'\bnecesitas\b', 'necesitás'),
        (r'\bestás\b', 'estás'),  # igual en voseo
        (r'\bvas\b', 'vas'),  # igual en voseo

        # Imperativos
        (r'\bcuéntame\b', 'contame'),
        (r'\bCuéntame\b', 'Contame'),
        (r'\bescríbeme\b', 'escribime'),
        (r'\bEscríbeme\b', 'Escribime'),
        (r'\bdime\b', 'decime'),
        (r'\bDime\b', 'Decime'),
        (r'\bmira\b', 'mirá'),
        (r'\bMira\b', 'Mirá'),
        (r'\bpiensa\b', 'pensá'),
        (r'\bPiensa\b', 'Pensá'),
        (r'\bespera\b', 'esperá'),
        (r'\bEspera\b', 'Esperá'),
        (r'\bescucha\b', 'escuchá'),
        (r'\bEscucha\b', 'Escuchá'),
        (r'\bfíjate\b', 'fijate'),
        (r'\bFíjate\b', 'Fijate'),
        (r'\bpregunta\b', 'preguntá'),

        # Frases comunes
        (r'\bte respondo\b', 'te respondo'),  # igual
        (r'\bte cuento\b', 'te cuento'),  # igual
        (r'\bte paso\b', 'te paso'),  # igual
        (r'\bte gustaría\b', 'te gustaría'),  # igual
    ]

    result = text
    for pattern, replacement in conversions:
        result = re.sub(pattern, replacement, result)

    return result


def truncate_response(response: str, max_sentences: int = 2) -> str:
    """Trunca respuestas largas a máximo N frases - AGRESIVO"""
    if not response:
        return response

    import re

    # Clean up the response first
    response = response.strip()

    # Split by sentence endings (. ! ? followed by space or end)
    # Also handle cases like "297€." or "30 días."
    sentences = re.split(r'(?<=[.!?])\s+', response)
    sentences = [s.strip() for s in sentences if s.strip()]

    original_count = len(sentences)

    if original_count > max_sentences:
        truncated = ' '.join(sentences[:max_sentences])
        # Ensure it ends with punctuation
        if truncated and truncated[-1] not in '.!?':
            truncated += '.'
        logger.info(f"TRUNCATED response from {original_count} to {max_sentences} sentences")
        return truncated

    return response


def _contains_alternative_payment(response: str) -> bool:
    """Check if response already contains alternative payment info (Bizum, IBAN, Revolut, PayPal)"""
    response_lower = response.lower()
    # Check for specific indicators of alternative payment methods
    indicators = [
        'bizum', 'transferencia', 'iban', 'revolut', 'wise', 'paypal',
        '639', '6[0-9]{8}',  # Spanish mobile numbers
        'es[0-9]{2}',  # IBAN prefix
        '@'  # Revolut handle
    ]
    import re
    for ind in indicators:
        if ind.startswith('[') or ind.startswith('('):
            # It's a regex pattern
            if re.search(ind, response_lower):
                return True
        elif ind in response_lower:
            return True
    return False


def truncate_payment_response(response: str) -> str:
    """If response contains alternative payment info, keep only first sentence + CTA.

    This is an AGGRESSIVE truncation because LLMs ignore prompt instructions
    and keep adding product info after payment details.
    """
    if not response or not _contains_alternative_payment(response):
        return response

    logger.info(f"Payment response detected, truncating aggressively")

    # Split by sentence-ending punctuation
    import re
    # Match period, exclamation, or question mark followed by space or end
    sentences = re.split(r'(?<=[.!?])\s+', response)

    if not sentences:
        return response

    # Keep only the first sentence
    first_sentence = sentences[0].strip()

    # Ensure it ends with punctuation
    if first_sentence and first_sentence[-1] not in '.!?':
        first_sentence += '.'

    # Add friendly CTA if not present
    cta_indicators = ['avísame', 'avisame', 'confirma', 'cuando lo hagas', 'me avisas', 'házmelo saber']
    if not any(cta in first_sentence.lower() for cta in cta_indicators):
        first_sentence += " Avísame cuando lo hagas 👍"

    logger.info(f"Truncated payment response: '{response[:50]}...' -> '{first_sentence}'")
    return first_sentence


def clean_response_placeholders(response: str, payment_links: list) -> str:
    """Reemplaza placeholders de links con links reales y añade link si falta"""
    if not response:
        return response

    import re

    # Get first available payment link
    real_link = ""
    for link in payment_links:
        if link and isinstance(link, str) and link.startswith("http"):
            real_link = link
            break

    logger.info(f"Payment links available: {payment_links}, using: {real_link}")

    # Check if response already has alternative payment method
    has_alternative_payment = _contains_alternative_payment(response)
    if has_alternative_payment:
        logger.info("Response contains alternative payment method - NOT appending Stripe link")

    # Replace common placeholders (payment + booking links)
    placeholders = [
        "[LINK_REAL]", "[link de pago]", "[link]", "[LINK]",
        "(link de pago)", "(link)", "[payment link]", "[pago]",
        "[tu enlace de reserva]", "[enlace de reserva]", "[booking link]",
        "[enlace]", "[tu enlace]", "[link de reserva]", "(enlace de reserva)"
    ]

    for placeholder in placeholders:
        if placeholder in response:
            # Don't replace with Stripe link if alternative payment is mentioned
            if real_link and not has_alternative_payment:
                response = response.replace(placeholder, real_link)
            else:
                # Remove placeholder
                response = response.replace(placeholder, "")

    # If response mentions giving a link but no URL present, add it
    # BUT ONLY if not using alternative payment method
    link_phrases = ['aquí tienes', 'here you go', 'aquí está', 'here is', 'este enlace', 'this link']
    has_link_phrase = any(phrase in response.lower() for phrase in link_phrases)
    has_url = 'http' in response.lower()

    if has_link_phrase and not has_url and real_link and not has_alternative_payment:
        logger.info(f"Response mentions link but has no URL, appending: {real_link}")
        response = f"{response} {real_link}"

    # Clean up empty link patterns like "enlace: ." or "link: ."
    # Remove patterns like "siguiente enlace: ." or "aquí: ." when link was empty
    response = re.sub(r'(enlace|link|aquí|here):\s*\.', '', response, flags=re.IGNORECASE)
    # Remove double spaces
    response = re.sub(r'\s+', ' ', response)
    # Remove orphaned punctuation
    response = re.sub(r'\s+([.!?])', r'\1', response)

    return response.strip()


# === VARIEDAD EN SALUDOS ===
GREETING_VARIANTS = {
    "es": [
        "¡Hola {name}!",
        "¡Hey {name}!",
        "¡Qué tal {name}!",
        "¡Buenas {name}!",
        "¡Hola! 👋",
        "¡Hey! ¿Cómo estás?",
        "{name}! Qué bueno verte por aquí",
        "¡Ey {name}! ¿Qué tal todo?",
    ],
    "en": [
        "Hey {name}!",
        "Hi {name}!",
        "Hello {name}!",
        "What's up {name}!",
        "Hi there! 👋",
        "Hey! How are you?",
    ],
    "pt": [
        "Oi {name}!",
        "Olá {name}!",
        "E aí {name}!",
        "Opa {name}!",
        "Oi! 👋",
        "Hey! Tudo bem?",
    ],
}

# === VARIEDAD EN EMOJIS ===
EMOJI_POOLS = {
    "positive": ["🙌", "💪", "🔥", "✨", "🚀", "👏", "💯", "⚡"],
    "friendly": ["😊", "😄", "🤗", "☺️", "😉", "🙂", "👍"],
    "thinking": ["🤔", "💭", "🧐", "💡"],
    "celebration": ["🎉", "🎊", "🥳", "🏆"],
}

# === KEYWORDS PARA DETECCIÓN DE IDIOMA ROBUSTA ===
LANG_KEYWORDS = {
    "es": ['hola', 'qué', 'cómo', 'tengo', 'quiero', 'puedo', 'gracias', 'precio',
           'caro', 'tiempo', 'buenas', 'vale', 'claro', 'genial', 'estoy', 'soy',
           'necesito', 'dudas', 'funciona', 'cuánto', 'dónde', 'cuándo', 'ahora'],
    "en": ['hello', 'hi', 'how', 'what', 'want', 'can', 'thanks', 'price',
           'expensive', 'time', 'okay', 'sure', 'great', "i'm", "i am", 'need',
           'doubt', 'works', 'much', 'where', 'when', 'now', 'please', 'the'],
    "pt": ['olá', 'oi', 'como', 'quero', 'posso', 'obrigado', 'obrigada', 'preço',
           'caro', 'tempo', 'tudo', 'bem', 'você', 'voce', 'muito', 'também',
           'preciso', 'dúvida', 'funciona', 'quanto', 'onde', 'quando', 'agora'],
}


def detect_language_robust(text: str, current_language: str = None) -> str:
    """
    Detecta idioma del texto de forma robusta.
    Si ya hay un idioma establecido, solo cambia si hay evidencia FUERTE.

    Args:
        text: Texto a analizar
        current_language: Idioma actual del usuario (si existe)

    Returns:
        Código de idioma ("es", "en", "pt")
    """
    if not text or len(text.strip()) < 2:
        return current_language or "es"

    text_lower = text.lower()

    # Contar coincidencias por idioma
    scores = {}
    for lang, keywords in LANG_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        scores[lang] = count

    max_score = max(scores.values()) if scores else 0

    # Si ya hay idioma establecido, necesita evidencia FUERTE para cambiar
    if current_language and current_language in scores:
        current_score = scores.get(current_language, 0)

        # Solo cambiar si:
        # 1. El nuevo idioma tiene al menos 3 coincidencias más
        # 2. Y el score actual es bajo (< 2)
        best_lang = max(scores, key=scores.get)
        if best_lang != current_language:
            diff = scores[best_lang] - current_score
            if diff < 3 or current_score >= 2:
                # No hay suficiente evidencia, mantener idioma actual
                return current_language

    # Detectar nuevo idioma
    if max_score == 0:
        return current_language or "es"

    # Resolver empates favoreciendo español > inglés > portugués
    best_lang = "es"
    best_score = scores.get("es", 0)

    for lang in ["en", "pt"]:
        if scores.get(lang, 0) > best_score:
            best_lang = lang
            best_score = scores[lang]

    return best_lang


def get_random_greeting(language: str, name: str, variant_index: int = 0) -> str:
    """
    Obtiene un saludo variado basado en el idioma y un índice rotativo.

    Args:
        language: Código de idioma
        name: Nombre del usuario
        variant_index: Índice para rotar saludos

    Returns:
        Saludo formateado
    """
    greetings = GREETING_VARIANTS.get(language, GREETING_VARIANTS["es"])
    # Usar índice rotativo para variar
    idx = variant_index % len(greetings)
    greeting = greetings[idx]
    return greeting.format(name=name)


def get_random_emoji(category: str = "positive") -> str:
    """
    Obtiene un emoji aleatorio de una categoría.

    Args:
        category: Categoría de emoji (positive, friendly, thinking, celebration)

    Returns:
        Emoji aleatorio
    """
    pool = EMOJI_POOLS.get(category, EMOJI_POOLS["positive"])
    return random.choice(pool)


def get_first_name(full_name: str) -> str:
    """
    Extrae solo el PRIMER nombre de un nombre completo.

    Args:
        full_name: Nombre completo (ej: "James Hawk")

    Returns:
        Solo el primer nombre (ej: "James")
    """
    if not full_name or not full_name.strip():
        return "amigo"

    # Limpiar y dividir por espacios
    parts = full_name.strip().split()
    first_name = parts[0] if parts else "amigo"

    # Si el primer nombre es muy corto o parece un username, usar completo
    if len(first_name) < 2 or first_name.startswith('@'):
        return full_name.strip()

    return first_name


import re

def extract_name_from_message(message: str) -> Optional[str]:
    """
    Extrae el nombre del usuario si se presenta en el mensaje.

    Detecta patrones como:
    - "soy [nombre]"
    - "me llamo [nombre]"
    - "mi nombre es [nombre]"
    - "I'm [name]"
    - "my name is [name]"
    - "call me [name]"

    Args:
        message: El mensaje del usuario

    Returns:
        El nombre extraído o None si no se detecta
    """
    if not message:
        return None

    # Normalizar mensaje
    text = message.strip()

    # Patrones en español e inglés
    patterns = [
        # Español
        r"(?:^|\s)(?:soy|me llamo|mi nombre es)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)",
        r"(?:^|\s)(?:hola[,!]?\s*)?soy\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)",
        # Inglés
        r"(?:^|\s)(?:i'?m|my name is|call me|i am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"(?:^|\s)(?:hey[,!]?\s*)?i'?m\s+([A-Z][a-z]+)",
        # Caso insensitivo para detectar más
        r"(?i)(?:^|\s)(?:soy|me llamo)\s+(\w+)",
        r"(?i)(?:^|\s)(?:i'?m|my name is)\s+(\w+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip()
            # Validar que parece un nombre real (no una palabra común)
            common_words = {'el', 'la', 'un', 'una', 'de', 'que', 'a', 'the', 'an', 'of',
                          'interested', 'looking', 'here', 'nuevo', 'nueva', 'good', 'fine',
                          'ok', 'okay', 'bien', 'mal', 'not', 'no', 'yes', 'si', 'tu', 'your'}
            if name.lower() not in common_words and len(name) >= 2:
                # Capitalizar correctamente
                return name.title()

    return None


# Keywords that indicate DIRECT purchase intent (user wants to pay NOW)
DIRECT_PURCHASE_KEYWORDS = [
    "quiero comprar",
    "como pago",
    "cómo pago",
    "dame el link",
    "me apunto",
    "lo quiero",
    "donde pago",
    "dónde pago",
    "link de pago",
    "quiero el curso",
    "lo compro",
    "donde compro",
    "dónde compro",
    "pasame el link",
    "pásame el link",
    "quiero pagar",
    "como lo compro",
    "cómo lo compro",
    "envíame el link",
    "enviame el link",
    "manda el link",
    "quiero comprarlo",
    "lo voy a comprar",
    "voy a comprarlo",
    # Affirmative responses (after bot asks "¿quieres el link?")
    "sí",
    "si",
    "yes",
    "ok",
    "vale",
    "claro",
    "por supuesto",
    "adelante",
    "proceder",
    "venga",
    "dale",
    "vamos",
    "perfecto",
    "porfa",
    "por favor",
    "ahora",
    "ya",
    # Explicit link requests
    "por aqui",
    "por aquí",
    "aquí",
    "aqui",
    "mandalo",
    "mándalo",
    "envialo",
    "envíalo",
]


def is_direct_purchase_intent(message: str) -> bool:
    """
    Detecta si el mensaje indica intención de compra DIRECTA.

    Cuando el usuario dice explícitamente que quiere comprar/pagar,
    no hay que volver a venderle - solo dar el link.

    Args:
        message: El mensaje del usuario

    Returns:
        True si es compra directa, False si no
    """
    if not message:
        return False

    msg_lower = message.lower()

    # EXCLUSIÓN: Si contiene frases de objeción/duda, NO es compra directa
    # Esto evita que "no sé si es para mí" active el link por contener "si"
    objection_phrases = [
        'no sé si', 'no se si', 'no estoy seguro', 'no estoy segura',
        'no es para mi', 'no es para mí', 'tengo dudas', 'no creo',
        'me lo pienso', 'lo pienso', 'lo tengo que pensar',
        'es muy caro', 'es caro', 'no tengo', 'no puedo',
        'más adelante', 'mas adelante', 'luego', 'después', 'despues',
        'ya veré', 'ya vere', 'ya te digo', 'no sé', 'no se'
    ]
    for phrase in objection_phrases:
        if phrase in msg_lower:
            return False  # Es una objeción, no compra directa

    # FIX: "si", "sí", "ok", "ya" solos son CONFIRMACIONES, no compra directa
    # Solo deben activar compra si hay contexto adicional
    # Ejemplo: "sí, quiero comprarlo" = compra directa
    # Ejemplo: "sí" (solo) = confirmación genérica, NO compra directa
    ambiguous_confirmations = {'sí', 'si', 'ok', 'ya', 'vale', 'dale', 'claro', 'bueno'}

    words = msg_lower.split()

    # Si el mensaje es SOLO una confirmación simple (1-2 palabras), NO es compra directa
    # Estas confirmaciones deben pasar por el LLM para que use el contexto
    if len(words) <= 2:
        is_only_confirmation = all(w.rstrip('!.?') in ambiguous_confirmations for w in words)
        if is_only_confirmation:
            return False  # No es compra directa, dejar que el LLM use el contexto

    # Check direct purchase keywords (solo los explícitos)
    for keyword in DIRECT_PURCHASE_KEYWORDS:
        if keyword in ambiguous_confirmations:
            # Para confirmaciones ambiguas, solo activar si hay más contexto
            # "sí, lo quiero" = compra, pero "sí" solo = no compra
            if keyword in words and len(words) > 2:
                return True
        else:
            # Para keywords largos/explícitos, búsqueda normal
            if keyword in msg_lower:
                return True

    return False


def get_transparency_disclosure(creator_name: str, language: str = "es") -> str:
    """
    Get AI transparency disclosure message for first interaction.

    Args:
        creator_name: Name of the creator
        language: User's preferred language

    Returns:
        Disclosure message string
    """
    disclosures = {
        "es": f"👋 Soy el asistente de IA de {creator_name}. Estoy aquí para ayudarte.",
        "en": f"👋 I'm {creator_name}'s AI assistant. I'm here to help you.",
        "ca": f"👋 Sóc l'assistent d'IA de {creator_name}. Estic aquí per ajudar-te.",
        "pt": f"👋 Sou o assistente de IA de {creator_name}. Estou aqui para ajudá-lo.",
        "fr": f"👋 Je suis l'assistant IA de {creator_name}. Je suis là pour vous aider.",
    }
    return disclosures.get(language, disclosures["es"])


@dataclass
class DMResponse:
    """Respuesta generada por el agent"""
    response_text: str
    intent: Intent
    action_taken: str = ""
    product_mentioned: Optional[str] = None
    follow_up_needed: bool = False
    escalate_to_human: bool = False
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FollowerMemory:
    """Memoria simplificada del seguidor"""
    follower_id: str
    creator_id: str
    username: str = ""
    name: str = ""
    first_contact: str = ""
    last_contact: str = ""
    total_messages: int = 0
    interests: List[str] = field(default_factory=list)
    products_discussed: List[str] = field(default_factory=list)
    objections_raised: List[str] = field(default_factory=list)
    purchase_intent_score: float = 0.0
    is_lead: bool = False
    is_customer: bool = False
    # Pipeline status: new, active, hot, customer
    status: str = "new"
    preferred_language: str = "es"  # Idioma preferido del seguidor
    last_messages: List[Dict] = field(default_factory=list)
    # Campos para control de links y objeciones
    links_sent_count: int = 0  # Contador de links enviados en conversación
    last_link_message_num: int = 0  # Número de mensaje cuando se envió último link
    objections_handled: List[str] = field(default_factory=list)  # Objeciones ya manejadas
    arguments_used: List[str] = field(default_factory=list)  # Argumentos ya usados
    greeting_variant_index: int = 0  # Para variar saludos
    # Campos para naturalidad - evitar repetición
    last_greeting_style: str = ""  # Último estilo de saludo usado
    last_emojis_used: List[str] = field(default_factory=list)  # Últimos emojis usados
    messages_since_name_used: int = 0  # Mensajes desde que se usó el nombre
    # Campos para contacto alternativo (WhatsApp/Telegram)
    alternative_contact: str = ""  # Número o usuario de WhatsApp/Telegram
    alternative_contact_type: str = ""  # "whatsapp", "telegram", u otro
    contact_requested: bool = False  # Si ya pedimos el contacto

    def __post_init__(self):
        """Sanitize None values that may come from JSON/DB loading."""
        # Int fields - replace None with 0
        if self.total_messages is None:
            self.total_messages = 0
        if self.links_sent_count is None:
            self.links_sent_count = 0
        if self.last_link_message_num is None:
            self.last_link_message_num = 0
        if self.greeting_variant_index is None:
            self.greeting_variant_index = 0
        if self.messages_since_name_used is None:
            self.messages_since_name_used = 0
        # Float fields - replace None with 0.0
        if self.purchase_intent_score is None:
            self.purchase_intent_score = 0.0
        # String fields - replace None with ""
        if self.username is None:
            self.username = ""
        if self.name is None:
            self.name = ""
        if self.first_contact is None:
            self.first_contact = ""
        if self.last_contact is None:
            self.last_contact = ""
        if self.status is None:
            self.status = "new"
        if self.preferred_language is None:
            self.preferred_language = "es"
        if self.last_greeting_style is None:
            self.last_greeting_style = ""
        if self.alternative_contact is None:
            self.alternative_contact = ""
        if self.alternative_contact_type is None:
            self.alternative_contact_type = ""
        # Bool fields - replace None with False
        if self.is_lead is None:
            self.is_lead = False
        if self.is_customer is None:
            self.is_customer = False
        if self.contact_requested is None:
            self.contact_requested = False
        # List fields - replace None with []
        if self.interests is None:
            self.interests = []
        if self.products_discussed is None:
            self.products_discussed = []
        if self.objections_raised is None:
            self.objections_raised = []
        if self.last_messages is None:
            self.last_messages = []
        if self.objections_handled is None:
            self.objections_handled = []
        if self.arguments_used is None:
            self.arguments_used = []
        if self.last_emojis_used is None:
            self.last_emojis_used = []


class MemoryStore:
    """Almacén simplificado de memoria"""

    def __init__(self, storage_path: str = "data/followers"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        self._cache: Dict[str, FollowerMemory] = {}

    def _get_file_path(self, creator_id: str, follower_id: str) -> str:
        creator_dir = os.path.join(self.storage_path, creator_id)
        os.makedirs(creator_dir, exist_ok=True)
        # Sanitize follower_id for filename
        safe_id = follower_id.replace("/", "_").replace("\\", "_")
        return os.path.join(creator_dir, f"{safe_id}.json")

    async def get(self, creator_id: str, follower_id: str) -> Optional[FollowerMemory]:
        cache_key = f"{creator_id}:{follower_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        file_path = self._get_file_path(creator_id, follower_id)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    memory = FollowerMemory(**{k: v for k, v in data.items() if k in FollowerMemory.__dataclass_fields__})
                    self._cache[cache_key] = memory
                    return memory
            except Exception as e:
                logger.error(f"Error loading memory: {e}")
        return None

    async def save(self, memory: FollowerMemory):
        cache_key = f"{memory.creator_id}:{memory.follower_id}"
        self._cache[cache_key] = memory

        file_path = self._get_file_path(memory.creator_id, memory.follower_id)
        try:
            data = {
                "follower_id": memory.follower_id,
                "creator_id": memory.creator_id,
                "username": memory.username,
                "name": memory.name,
                "first_contact": memory.first_contact,
                "last_contact": memory.last_contact,
                "total_messages": memory.total_messages,
                "interests": memory.interests,
                "products_discussed": memory.products_discussed,
                "objections_raised": memory.objections_raised,
                "purchase_intent_score": memory.purchase_intent_score,
                "is_lead": memory.is_lead,
                "is_customer": memory.is_customer,
                "status": memory.status,  # Pipeline status: new, active, hot, customer
                "preferred_language": memory.preferred_language,
                "last_messages": memory.last_messages[-20:],  # Keep last 20
                # Campos para control de links y objeciones
                "links_sent_count": memory.links_sent_count,
                "last_link_message_num": memory.last_link_message_num,
                "objections_handled": memory.objections_handled,
                "arguments_used": memory.arguments_used,
                "greeting_variant_index": memory.greeting_variant_index,
                # Campos para naturalidad
                "last_greeting_style": memory.last_greeting_style,
                "last_emojis_used": memory.last_emojis_used[-5:],  # Últimos 5
                "messages_since_name_used": memory.messages_since_name_used,
                # Campos para contacto alternativo
                "alternative_contact": memory.alternative_contact,
                "alternative_contact_type": memory.alternative_contact_type,
                "contact_requested": memory.contact_requested
            }
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving memory: {e}")

    async def get_or_create(
        self,
        creator_id: str,
        follower_id: str,
        name: str = "",
        username: str = ""
    ) -> FollowerMemory:
        memory = await self.get(creator_id, follower_id)
        if memory is None:
            memory = FollowerMemory(
                follower_id=follower_id,
                creator_id=creator_id,
                name=name,
                username=username,
                first_contact=datetime.now().isoformat(),
                last_contact=datetime.now().isoformat()
            )
            await self.save(memory)
            logger.info(f"Created new follower: {follower_id} (name={name}, username={username})")
        return memory


class DMResponderAgent:
    """Agent principal que procesa DMs y genera respuestas personalizadas"""

    async def _save_message_to_db(self, follower_id: str, role: str, content: str, intent: str = None):
        """Save message to PostgreSQL if available - with timing"""
        import time
        _t_start = time.time()

        if not USE_POSTGRES or not db_service:
            logger.debug(f"PostgreSQL disabled: USE_POSTGRES={USE_POSTGRES}, db_service={db_service}")
            return
        try:
            lead = await db_service.get_lead_by_platform_id(self.creator_id, follower_id)
            if not lead:
                logger.info(f"Creating new lead for {follower_id}")
                lead = await db_service.create_lead_async(self.creator_id, {"platform_user_id": follower_id, "platform": "telegram" if follower_id.startswith("tg_") else "instagram", "username": follower_id})
            if lead and "id" in lead:
                result = await db_service.save_message(lead["id"], role, content, intent)
                logger.info(f"⏱️ DB save ({role}) took {time.time() - _t_start:.2f}s - lead={lead['id']}")
            else:
                logger.warning(f"Could not get/create lead for {follower_id}: lead={lead}")
        except Exception as e:
            logger.error(f"PostgreSQL save failed for {follower_id}: {e}", exc_info=True)

    def _save_message_to_db_fire_and_forget(self, follower_id: str, role: str, content: str, intent: str = None):
        """
        Fire-and-forget DB save - uses thread pool to truly not block.
        asyncio.create_task runs during next await, blocking the response.
        Threading ensures DB saves happen completely in background.
        FIX P0: Added retry logic and proper error logging.
        """
        import threading
        import asyncio
        import time

        MAX_RETRIES = 3
        RETRY_DELAYS = [1, 2, 4]  # Exponential backoff: 1s, 2s, 4s

        def run_in_thread():
            last_error = None
            for attempt in range(MAX_RETRIES):
                try:
                    # Create new event loop for this thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(self._save_message_to_db(follower_id, role, content, intent))
                        if attempt > 0:
                            logger.info(f"DB save succeeded on retry {attempt + 1} for {follower_id}/{role}")
                        return  # Success - exit
                    finally:
                        loop.close()
                except Exception as e:
                    last_error = e
                    if attempt < MAX_RETRIES - 1:
                        delay = RETRY_DELAYS[attempt]
                        logger.warning(f"DB save attempt {attempt + 1} failed for {follower_id}/{role}, retrying in {delay}s: {e}")
                        time.sleep(delay)
                    else:
                        logger.error(f"DB save FAILED after {MAX_RETRIES} attempts for {follower_id}/{role}: {e}", exc_info=True)

        # Start in background thread - truly non-blocking
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
        logger.debug(f"DB save started in background thread for {role}")

    def _sync_lead_to_postgres_fire_and_forget(self, creator_id: str, follower_id: str, purchase_intent_score: float = 0.0, status: str = None):
        """
        Fire-and-forget lead sync - uses thread pool to truly not block.
        P0 FIX: Now includes retry logic and direct DB update as backup.
        """
        import threading
        import time

        MAX_RETRIES = 3
        RETRY_DELAY = 0.5

        def run_in_thread():
            from api.services.data_sync import sync_json_to_postgres, update_lead_score_direct

            for attempt in range(MAX_RETRIES):
                try:
                    _t_start = time.time()

                    # Method 1: Sync from JSON (includes all data)
                    result = sync_json_to_postgres(creator_id, follower_id)

                    # Method 2 (P0 FIX): Also do direct update to ensure score persists
                    if purchase_intent_score > 0:
                        update_lead_score_direct(creator_id, follower_id, purchase_intent_score, status)

                    _t_end = time.time()
                    if result:
                        logger.info(f"⏱️ [P0-SYNC] Lead sync completed in {_t_end - _t_start:.2f}s: {follower_id} (score={purchase_intent_score:.2f}, status={status})")
                    else:
                        logger.debug(f"[P0-SYNC] Lead sync returned None for {follower_id} ({_t_end - _t_start:.2f}s)")

                    # Success - exit retry loop
                    return

                except Exception as e:
                    wait_time = RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"[P0-RETRY] Lead sync failed (attempt {attempt + 1}/{MAX_RETRIES}): {follower_id} - {e}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(wait_time)
                    else:
                        logger.error(f"[P0-RETRY] Lead sync FAILED after {MAX_RETRIES} attempts for {follower_id}: {e}", exc_info=True)

        # Start in background thread - truly non-blocking
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
        logger.debug(f"[P0-SYNC] Lead sync started in background thread for {follower_id}")

    # Class-level cache for system prompts and configs (shared across instances)
    _system_prompt_cache: Dict[str, str] = {}
    _config_cache: Dict[str, dict] = {}
    _products_cache: Dict[str, list] = {}
    _cache_timestamp: Dict[str, float] = {}
    _CACHE_TTL = 0  # NO CACHE - siempre leer productos frescos de DB

    def __init__(self, creator_id: str = "manel"):
        import time
        self.creator_id = creator_id

        # Use cached config/products if available and fresh
        cache_key = creator_id
        now = time.time()
        cache_age = now - self._cache_timestamp.get(cache_key, 0)

        if cache_age < self._CACHE_TTL and cache_key in self._config_cache:
            self.creator_config = self._config_cache[cache_key]
            self.products = self._products_cache.get(cache_key, [])
            logger.info(f"Using cached config/products for {creator_id} (age: {cache_age:.1f}s)")
        else:
            self.creator_config = self._load_creator_config()
            self.products = self._load_products()
            # Cache them
            self._config_cache[cache_key] = self.creator_config
            self._products_cache[cache_key] = self.products
            self._cache_timestamp[cache_key] = now
            logger.info(f"Loaded and cached config/products for {creator_id}")

        self.llm = get_llm_client()
        self.memory_store = MemoryStore()
        self.config_manager = CreatorConfigManager()
        self._follower_cache: Dict[str, FollowerMemory] = {}

        logger.info(f"DM Agent initialized for creator: {creator_id}")
        logger.info(f"Creator: {self.creator_config.get('name', 'Unknown')}")
        logger.info(f"Loaded {len(self.products)} products")

    def _load_creator_config(self) -> dict:
        """Cargar configuración del creador desde PostgreSQL (primero) o JSON (fallback)"""
        # Try PostgreSQL first (where Settings page saves)
        if USE_POSTGRES and db_service:
            try:
                creator = db_service.get_creator_by_name(self.creator_id)
                if creator:
                    logger.info(f"Loaded creator config from DB: {creator.get('name')}, tone={creator.get('clone_tone')}")
                    # Map DB fields to config format expected by _build_system_prompt
                    return {
                        "name": creator.get("name", "Asistente"),
                        "clone_name": creator.get("clone_name") or creator.get("name", "Asistente"),
                        "clone_tone": creator.get("clone_tone", "friendly"),
                        "clone_vocabulary": creator.get("clone_vocabulary", ""),
                        "welcome_message": creator.get("welcome_message", ""),
                        "bot_active": creator.get("bot_active", True),
                        "clone_active": creator.get("bot_active", True),
                        # Alternative payment methods from DB (bizum, bank_transfer, revolut, etc)
                        "other_payment_methods": creator.get("other_payment_methods", {}),
                        # Keep these for compatibility
                        "personality": "amable y profesional",
                        "language": "Español",
                        "greeting_style": "Hola! Que tal?",
                        "emoji_usage": "moderado",
                        "response_length": "conciso, maximo 2-3 frases",
                        "escalation_keywords": ["urgente", "reembolso", "hablar con humano"]
                    }
            except Exception as e:
                logger.warning(f"Failed to load config from PostgreSQL: {e}")

        # Fallback to JSON file
        config_path = Path(f"data/creators/{self.creator_id}_config.json")
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    logger.info(f"Loaded creator config from JSON: {config.get('name')}")
                    return config
            except Exception as e:
                logger.error(f"Error loading creator config from JSON: {e}")

        logger.warning(f"Creator config not found in DB or JSON")
        return self._default_config()

    def _load_products(self) -> list:
        """Cargar productos desde PostgreSQL (primero) o JSON (fallback)

        Solo carga productos activos (is_active=True) para que el bot
        no mencione productos pausados.
        """
        # Try PostgreSQL first
        if USE_POSTGRES and db_service:
            try:
                all_products = db_service.get_products(self.creator_id)
                if all_products:
                    # Filter only active products
                    products = [p for p in all_products if p.get('is_active', True)]
                    logger.info(f"Loaded {len(products)} active products from PostgreSQL (filtered from {len(all_products)} total)")
                    return products
            except Exception as e:
                logger.warning(f"Error loading products from DB: {e}")

        # Fallback to JSON
        products_path = Path(f"data/products/{self.creator_id}_products.json")
        if products_path.exists():
            try:
                with open(products_path, 'r', encoding='utf-8') as f:
                    all_products = json.load(f)
                    # Handle both list and dict with 'products' key
                    if isinstance(all_products, dict):
                        all_products = all_products.get('products', [])
                    # Filter only active products
                    products = [p for p in all_products if p.get('is_active', True)]
                    logger.info(f"Loaded {len(products)} active products from JSON (filtered from {len(all_products)} total)")
                    return products
            except Exception as e:
                logger.error(f"Error loading products from JSON: {e}")

        logger.warning(f"No products found for {self.creator_id}")
        return []

    def _default_config(self) -> dict:
        """Configuración por defecto"""
        return {
            "name": "Asistente",
            "personality": "amable y profesional",
            "tone": "cercano pero profesional",
            "language": "Español",
            "greeting_style": "Hola! Que tal?",
            "emoji_usage": "moderado",
            "response_length": "conciso, maximo 2-3 frases",
            "escalation_keywords": ["urgente", "reembolso", "hablar con humano"]
        }

    def _load_booking_links(self) -> list:
        """Load booking links from database"""
        try:
            from api.database import SessionLocal
            from api.models import BookingLink

            if not SessionLocal:
                logger.warning("SessionLocal not available, cannot load booking links")
                return []

            with SessionLocal() as db:
                links = db.query(BookingLink).filter(
                    BookingLink.creator_id == self.creator_id,
                    BookingLink.is_active == True
                ).all()

                return [
                    {
                        "id": str(link.id),
                        "title": link.title,
                        "description": link.description,
                        "duration_minutes": link.duration_minutes,
                        "platform": link.platform,
                        "url": link.url,
                        "price": getattr(link, 'price', 0) or 0,
                        "meeting_type": link.meeting_type
                    }
                    for link in links
                ]
        except Exception as e:
            logger.error(f"Error loading booking links: {e}")
            return []

    def _get_service_emoji(self, meeting_type: str) -> str:
        """Get emoji for service type"""
        emoji_map = {
            "discovery": "🔍",
            "coaching": "🎯",
            "consultation": "💼",
            "consultoria": "💼",
            "mentoring": "🧠",
            "mentoria": "🧠",
            "strategy": "📊",
        }
        if "qa" in meeting_type.lower() or "q&a" in meeting_type.lower():
            return "❓"
        return emoji_map.get(meeting_type, "📞")

    def _format_booking_response(self, links: list, language: str = "es", platform: str = "instagram") -> dict:
        """
        Format booking links as a friendly message with internal Clonnect URLs.
        Returns dict with 'text' and optionally 'telegram_keyboard' for inline buttons.
        For Telegram, uses URL buttons that open the booking page directly.
        """
        if not links:
            # No booking links - give natural response asking to continue in DM
            if language == "es":
                dialect = get_tone_dialect(self.creator_id)
                if dialect == "rioplatense":
                    text = "¡Claro! Para agendar una sesión, escribime por acá y coordinamos 📲"
                else:
                    text = "¡Claro! Para agendar una sesión, escríbeme por aquí y coordinamos 📲"
            else:
                text = "Sure! To schedule a session, just message me here and we'll coordinate 📲"
            return {"text": text}

        # Frontend URL for internal booking system
        frontend_url = os.getenv("FRONTEND_URL", "https://clonnect.vercel.app")

        # Build keyboard for Telegram (list of button rows)
        telegram_keyboard = []
        formatted_links = []

        for link in links:
            service_id = link.get('id', '')
            duration = link.get('duration_minutes', 30)
            price = link.get('price') or 0
            title = link.get('title', 'Llamada')
            meeting_type = link.get('meeting_type', 'call')

            emoji = self._get_service_emoji(meeting_type)

            # Price text (shorter format)
            if price == 0:
                price_text = "Gratis" if language == "es" else "Free"
            else:
                price_text = f"{price}€"

            # Generate internal Clonnect booking URL
            booking_url = f"{frontend_url}/book/{self.creator_id}/{service_id}"

            # Shorten title if too long (Telegram buttons have limited width)
            short_title = title[:15] + "..." if len(title) > 18 else title

            # For Telegram: create URL button with shortened text
            # Format: "🎯 Coaching (60m) Gratis" - much shorter to avoid truncation
            button_text = f"{emoji} {short_title} ({duration}m) {price_text}"
            telegram_keyboard.append({
                "text": button_text,
                "url": booking_url  # Direct URL to booking page
            })

            # For Instagram/other: text with URL
            formatted_links.append(f"{emoji} {title} - {duration} min - {price_text}\n   ➜ {booking_url}")

        # Build response based on platform
        if platform == "telegram":
            # Telegram gets short intro + inline buttons
            if language == "es":
                text = "📅 ¡Reserva tu llamada conmigo!\n\nElige el servicio:"
            else:
                text = "📅 Book a call with me!\n\nChoose a service:"

            return {
                "text": text,
                "telegram_keyboard": telegram_keyboard
            }
        else:
            # Instagram/other gets full text with URLs
            if language == "es":
                intro = "¡Genial! Estos son mis servicios disponibles:\n\n"
                outro = "\n\nHaz clic en el que te interese para elegir tu horario."
            else:
                intro = "Great! Here are my available services:\n\n"
                outro = "\n\nClick on the one you're interested in to choose your time slot."

            return {"text": intro + "\n\n".join(formatted_links) + outro}

    def _get_last_bot_message(self, conversation_history: List[dict]) -> Optional[str]:
        """Obtiene el último mensaje del bot (assistant) del historial.

        Args:
            conversation_history: Lista de mensajes [{role: 'user'|'assistant', content: '...'}]

        Returns:
            El contenido del último mensaje del assistant, o None si no hay.
        """
        if not conversation_history:
            return None

        # Buscar desde el final hacia atrás
        for msg in reversed(conversation_history):
            if msg.get("role") == "assistant":
                return msg.get("content", "")

        return None

    def _extract_known_info(self, history: List[dict]) -> List[str]:
        """Extrae información que el usuario ya proporcionó en la conversación.

        Returns:
            Lista de strings con la información conocida
        """
        import re
        known = []
        seen = set()  # Evitar duplicados

        for msg in history:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "").lower()

            # Detectar nombre
            match = re.search(r'(?:soy|me llamo|mi nombre es)\s+(\w+)', content)
            if match and "nombre" not in seen:
                known.append(f"Nombre: {match.group(1).title()}")
                seen.add("nombre")

            # Detectar profesión
            match = re.search(r'(?:trabajo como|soy|trabajo de)\s+([\w\s]+?)(?:\.|,|$)', content)
            if match and "profesion" not in seen:
                prof = match.group(1).strip()
                if len(prof) > 2 and len(prof) < 30:
                    known.append(f"Profesión: {prof}")
                    seen.add("profesion")

            # Detectar presupuesto
            match = re.search(r'(?:presupuesto|gastar|pagar)[^0-9]*(\d+)\s*[€$]?', content)
            if match and "presupuesto" not in seen:
                known.append(f"Presupuesto: {match.group(1)}€")
                seen.add("presupuesto")

            # Detectar interés específico
            interests = ['ansiedad', 'estrés', 'meditación', 'yoga', 'coaching', 'curso']
            for interest in interests:
                if interest in content and f"interes_{interest}" not in seen:
                    known.append(f"Interés: {interest}")
                    seen.add(f"interes_{interest}")

            # Detectar objeción de precio
            if any(kw in content for kw in ['caro', 'muy caro', 'precio alto', 'no puedo pagar']):
                if "objecion_precio" not in seen:
                    known.append("Objeción mencionada: precio")
                    seen.add("objecion_precio")

            # Detectar objeción de tiempo
            if any(kw in content for kw in ['no tengo tiempo', 'ocupado', 'sin tiempo']):
                if "objecion_tiempo" not in seen:
                    known.append("Objeción mencionada: tiempo")
                    seen.add("objecion_tiempo")

            # Detectar situación personal
            if 'hijo' in content and "hijos" not in seen:
                known.append("Situación: tiene hijos")
                seen.add("hijos")

        return known

    def _extract_conversation_topic(self, history: List[dict]) -> Optional[str]:
        """Extrae el tema principal de la conversación.

        Returns:
            El tema principal o None si no se detecta
        """
        topics_mentioned = []

        topic_keywords = {
            'ansiedad': ['ansiedad', 'ansioso', 'nervios', 'estrés', 'estres'],
            'meditación': ['meditación', 'meditacion', 'meditar', 'mindfulness', 'respiración'],
            'coaching': ['coaching', 'coach', 'sesión', 'sesion', 'acompañamiento'],
            'curso': ['curso', 'programa', 'formación', 'formacion', 'módulos', 'modulos'],
            'yoga': ['yoga', 'posturas', 'asanas'],
            'precio': ['precio', 'cuesta', 'vale', 'pagar', 'euros', '€'],
            'llamada': ['llamada', 'agendar', 'videollamada', 'reunión', 'reunion'],
        }

        for msg in history:
            content = msg.get("content", "").lower()
            for topic, keywords in topic_keywords.items():
                if any(kw in content for kw in keywords):
                    topics_mentioned.append(topic)

        if topics_mentioned:
            # Retornar el tema más frecuente (excluir 'precio' si hay otro)
            from collections import Counter
            counts = Counter(topics_mentioned)
            # Si el tema más común es 'precio' y hay otros, preferir los otros
            most_common = counts.most_common()
            if most_common[0][0] == 'precio' and len(most_common) > 1:
                return most_common[1][0]
            return most_common[0][0]

        return None

    def _detect_meta_message(self, message: str, history: List[dict]) -> Optional[Dict[str, Any]]:
        """Detecta cuando el usuario hace referencia a la conversación misma.

        Detecta patrones como:
        - "ya te lo dije" → Usuario quiere que recordemos algo
        - "revisa el chat" → Usuario frustrado porque repetimos
        - "no me entiendes" → Usuario frustrado

        Args:
            message: Mensaje actual del usuario
            history: Historial de conversación

        Returns:
            Dict con {action: str, context: str} o None si no es meta-mensaje
        """
        msg_lower = message.lower().strip()

        # === PATRONES: "Revisa lo que dije" ===
        review_patterns = [
            "ya te lo dije", "te lo dije", "ya te dije",
            "revisa el chat", "lee el chat", "mira el chat",
            "te lo acabo de decir", "lo acabo de decir",
            "ya te lo he dicho", "te lo he dicho",
            "lee arriba", "mira arriba", "scroll up",
            "ya lo mencioné", "ya lo mencione", "te lo comenté",
            "como te dije antes", "como ya te dije"
        ]

        if any(p in msg_lower for p in review_patterns):
            # Buscar el último mensaje relevante del usuario (no el actual)
            user_messages = [m for m in history if m.get("role") == "user"]
            if len(user_messages) >= 1:
                # Retornar el penúltimo mensaje del usuario si existe
                previous_msg = user_messages[-1].get("content", "") if len(user_messages) >= 1 else ""
                return {
                    "action": "REVIEW_HISTORY",
                    "context": previous_msg,
                    "instruction": f"El usuario me pide que recuerde lo que dijo antes: '{previous_msg[:100]}'"
                }

        # === PATRONES: Frustración ===
        frustration_patterns = [
            "no me entiendes", "no entiendes", "no me escuchas",
            "eres un bot", "habla con alguien", "persona real",
            "no sirves", "inútil", "no ayudas", "qué malo"
        ]

        if any(p in msg_lower for p in frustration_patterns):
            return {
                "action": "USER_FRUSTRATED",
                "context": message,
                "instruction": "Usuario frustrado - responder con empatía y ofrecer ayuda clara"
            }

        # === PATRONES: Repetición pedida ===
        repeat_patterns = [
            "repite", "otra vez", "no entendí", "no entendi",
            "puedes repetir", "me lo repites", "dilo de nuevo"
        ]

        if any(p in msg_lower for p in repeat_patterns):
            # Buscar última respuesta del bot
            bot_messages = [m for m in history if m.get("role") == "assistant"]
            if bot_messages:
                last_bot = bot_messages[-1].get("content", "")
                return {
                    "action": "REPEAT_REQUESTED",
                    "context": last_bot,
                    "instruction": f"Usuario pide repetición. Mi último mensaje fue: '{last_bot[:100]}'"
                }

        # === FIX MEMORIA: Referencias implícitas al contexto ===
        # "Por eso necesito flexibilidad" → conectar con lo que dijo antes
        import re
        implicit_patterns = [
            r'^por eso\b', r'^por esa raz[oó]n', r'^debido a eso',
            r'^entonces\b', r'^es por eso', r'^por lo que te',
            r'^como te dec[íi]a', r'^lo que pasa es',
            r'^el tema es', r'^la cosa es', r'^el problema es',
        ]

        for pattern in implicit_patterns:
            if re.match(pattern, msg_lower):
                # Buscar contexto relevante de mensajes anteriores
                user_messages = [m for m in history if m.get("role") == "user"]
                if len(user_messages) >= 1:
                    # Buscar el mensaje anterior que da contexto
                    previous_context = user_messages[-1].get("content", "")
                    return {
                        "action": "IMPLICIT_REFERENCE",
                        "context": previous_context,
                        "instruction": f"Usuario hace referencia implícita a lo que dijo antes: '{previous_context[:100]}'"
                    }

        # === FIX FRUSTRACIÓN: Detección de sarcasmo ===
        sarcasm_patterns = [
            r'como si', r'seguro que s[íi]', r'ya ver[áa]s',
            r'aj[áa]', r'ya ya', r'qu[ée] gracioso',
            r's[íi].*(?:claro|seguro).*no', r'claro.*como si',
            r'obvio.*que no', r'seguro.*(?:vas|puedes|sabes)',
            r'otra vez.*(?:igual|lo mismo)',
        ]

        for pattern in sarcasm_patterns:
            if re.search(pattern, msg_lower):
                return {
                    "action": "SARCASM_DETECTED",
                    "context": message,
                    "instruction": "Usuario usando sarcasmo/ironía - responder con empatía, no literal"
                }

        return None

    def _classify_intent(self, message: str, conversation_history: Optional[List[dict]] = None) -> tuple:
        """Clasificar intención del mensaje por keywords.

        Args:
            message: Mensaje del usuario
            conversation_history: Historial de conversación (opcional) para context-aware classification
        """
        msg = message.lower()

        # === CORRECTION - MÁXIMA PRIORIDAD ===
        # Cuando el usuario corrige un malentendido O pide que revise el historial
        correction_patterns = [
            # Correcciones de malentendido
            'no te he dicho', 'no he dicho', 'no quiero comprar', 'no quiero pagar',
            'me has entendido mal', 'no es eso', 'no me refiero', 'no era eso',
            'no te estoy diciendo', 'no estoy diciendo', 'malentendido',
            'no he pedido', 'no te pedi', 'no te pedí', 'yo no dije',
            'no dije eso', 'no es lo que dije', 'no quise decir',
            # Meta-mensajes: usuario pide que revise el historial
            'ya te lo dije', 'te lo dije', 'ya te dije', 'te lo acabo de decir',
            'ya te lo he dicho', 'te lo he dicho', 'como te dije', 'como te comenté',
            'revisa el chat', 'mira el chat', 'lee el chat', 'lee arriba',
            'mira arriba', 'scroll up', 'lo que te dije', 'ya lo dije',
            'ya te expliqué', 'ya te explique', 'te acabo de decir',
            'no me escuchas', 'no lees', 'no prestas atención'
        ]
        if any(p in msg for p in correction_patterns):
            return Intent.CORRECTION, 0.95

        # === CONTEXT-AWARE ACKNOWLEDGMENT ===
        # Cuando el usuario responde con "Si", "Vale", "Ok", etc., analizamos
        # el contexto de la conversación para clasificar mejor la intención.
        #
        # ANTES: "Si" → ACKNOWLEDGMENT → respuesta genérica "¿En qué más puedo ayudarte?"
        # AHORA: "Si" después de "¿Quieres saber más?" → INTEREST_SOFT → continúa conversación
        #
        if is_short_affirmation(message):
            # Si tenemos historial, analizar qué preguntó el bot
            if conversation_history:
                last_bot_msg = self._get_last_bot_message(conversation_history)
                if last_bot_msg:
                    analyzer = get_bot_question_analyzer()
                    question_type, q_confidence = analyzer.analyze_with_confidence(last_bot_msg)

                    logger.info(f"Context-aware: '{message}' after bot question type={question_type.value}")

                    # Mapear tipo de pregunta del bot → intent del usuario
                    if question_type == QuestionType.INTEREST:
                        logger.info(f"→ Context: Bot asked about interest → INTEREST_SOFT")
                        return Intent.INTEREST_SOFT, 0.88

                    elif question_type == QuestionType.PURCHASE:
                        logger.info(f"→ Context: Bot asked about purchase → INTEREST_STRONG")
                        return Intent.INTEREST_STRONG, 0.90

                    elif question_type == QuestionType.BOOKING:
                        logger.info(f"→ Context: Bot asked about booking → BOOKING")
                        return Intent.BOOKING, 0.88

                    elif question_type == QuestionType.PAYMENT_METHOD:
                        logger.info(f"→ Context: Bot asked about payment → INTEREST_STRONG")
                        return Intent.INTEREST_STRONG, 0.88

                    elif question_type == QuestionType.INFORMATION:
                        # Bot hizo pregunta abierta, usuario confirma → continuar flujo
                        logger.info(f"→ Context: Bot asked open question → INTEREST_SOFT")
                        return Intent.INTEREST_SOFT, 0.80

                    elif question_type == QuestionType.CONFIRMATION:
                        # Bot preguntó si quedó claro → usuario confirma → ACKNOWLEDGMENT (OK aquí)
                        logger.info(f"→ Context: Bot asked for confirmation → ACKNOWLEDGMENT")
                        return Intent.ACKNOWLEDGMENT, 0.85

            # Sin contexto o tipo desconocido → ACKNOWLEDGMENT original
            logger.info(f"→ No context or unknown question type → ACKNOWLEDGMENT")
            return Intent.ACKNOWLEDGMENT, 0.85

        # Escalación (prioridad máxima después de corrections)
        # Patrones por defecto para detectar solicitud de humano
        default_escalation = [
            "hablar con persona", "hablar con humano", "persona real",
            "agente humano", "agente real", "quiero hablar con alguien",
            "pasame con", "pásame con", "hablar con un humano",
            "contactar persona", "necesito hablar con", "prefiero hablar con",
            "quiero un humano", "eres un bot", "eres robot", "no eres real",
            "hablar con soporte", "hablar con atención", "operador",
            "quiero hablar con una persona", "conectame con", "conéctame con"
        ]
        escalation_kw = self.creator_config.get('escalation_keywords', []) + default_escalation
        if any(kw.lower() in msg for kw in escalation_kw):
            return Intent.ESCALATION, 0.95

        # === INTERÉS SE DETECTA PRIMERO (prioridad sobre saludos) ===
        # Esto permite que "Hola, me interesa el curso" se clasifique como INTEREST, no GREETING

        # Interés fuerte (quiere comprar)
        # NOTA: "pagar" solo si es positivo (quiero pagar), no negativo (no puedo pagar)
        interest_strong_kw = ['comprar', 'quiero comprar', 'adquirir', 'donde compro', 'link de pago',
                              'apuntarme', 'me apunto', 'lo quiero', 'lo compro', 'quiero pagar']
        if any(w in msg for w in interest_strong_kw):
            # Excluir si contiene negación
            if not any(neg in msg for neg in ['no puedo', 'no tengo', 'no quiero']):
                return Intent.INTEREST_STRONG, 0.90

        # Interés soft - ANTES de saludos para que "hola, me interesa" sea INTEREST_SOFT
        if any(w in msg for w in ['interesa', 'cuentame', 'cuéntame', 'info', 'información', 'saber mas', 'saber más', 'como funciona', 'cómo funciona']):
            return Intent.INTEREST_SOFT, 0.85

        # PRECIO - ANTES de booking para que "cuanto cuesta la mentoria" sea QUESTION_PRODUCT
        price_keywords = ['cuanto cuesta', 'cuánto cuesta', 'precio', 'cuanto vale', 'cuánto vale',
                          'que cuesta', 'qué cuesta', 'cuanto es', 'cuánto es', 'inversion', 'inversión',
                          'cuanto sale', 'cuánto sale', 'que precio', 'qué precio']
        if any(w in msg for w in price_keywords):
            logger.info(f"=== PRICE QUESTION detected === msg='{msg}'")
            return Intent.QUESTION_PRODUCT, 0.95  # Alta prioridad

        # PREGUNTAS SOBRE CONTENIDO/METODOLOGÍA - ANTES de booking
        # Para que "cual es tu filosofia de coaching" sea QUESTION_PRODUCT, no BOOKING
        content_question_kw = [
            'que es', 'qué es', 'en que consiste', 'en qué consiste',
            'como trabajas', 'cómo trabajas', 'tu metodologia', 'tu metodología',
            'filosofia', 'filosofía', 'enfoque', 'tu programa', 'tus programas',
            'de que trata', 'de qué trata', 'como funciona tu', 'cómo funciona tu',
            'sintoma', 'síntoma', 'plenitud', 'sanacion', 'sanación',
            'transformacion', 'transformación', 'autoconocimiento',
            'programa de', 'acompañamiento', 'acompanamiento',
            'resultados de tus', 'testimonios de', 'clientes han'
        ]
        if any(w in msg for w in content_question_kw):
            logger.info(f"=== QUESTION_PRODUCT (content) detected === msg='{msg}'")
            return Intent.QUESTION_PRODUCT, 0.92

        # Booking / Agendar llamada - DESPUÉS de preguntas sobre contenido
        # NOTA: "coaching" solo si quiere AGENDAR, no si pregunta sobre él
        if any(w in msg for w in [
            'agendar', 'reservar', 'llamada', 'reunion', 'reunión', 'cita',
            'agenda', 'book', 'booking', 'appointment', 'schedule',
            'videollamada', 'zoom', 'meet', 'calendly', 'hablar contigo',
            'cuando podemos hablar', 'podemos hablar', 'disponibilidad',
            'sesion de coaching', 'sesión de coaching', 'consulta', 'consultoria', 'consultoría',
            'quiero coaching', 'contratar coaching', 'discovery',
            'call', 'una call', 'quiero call', 'hacer call', 'tener call'
        ]):
            return Intent.BOOKING, 0.90

        # Saludos (solo si NO hay interés ni booking)
        # Incluye ES + EN básico
        if any(w in msg for w in ['hola', 'hey', 'ey', 'buenas', 'buenos dias', 'que tal', 'hi', 'hello']):
            return Intent.GREETING, 0.90

        # Objeción precio
        if any(w in msg for w in ['caro', 'costoso', 'mucho dinero', 'no puedo pagar', 'precio alto', 'barato', 'no tengo dinero', 'no tengo plata']):
            return Intent.OBJECTION_PRICE, 0.90

        # Objeción tiempo - incluye "ahora no puedo" (específico)
        if any(w in msg for w in ['no tengo tiempo', 'ocupado', 'sin tiempo', 'no puedo ahora', 'ahora no puedo']):
            return Intent.OBJECTION_TIME, 0.90

        # Objeción duda
        if any(w in msg for w in ['pensarlo', 'pensar', 'no se', 'no estoy seguro', 'dudas']):
            return Intent.OBJECTION_DOUBT, 0.85

        # Despedida - ANTES de OBJECTION_LATER para que "hasta luego" no matchee "luego"
        if any(w in msg for w in ['adios', 'adiós', 'hasta luego', 'chao', 'nos vemos', 'bye', 'goodbye']):
            return Intent.GOODBYE, 0.85

        # Objeción "luego" / "después" - DESPUÉS de GOODBYE
        # Excluye "hasta luego" que ya fue capturado arriba
        if any(w in msg for w in ['luego', 'despues', 'después', 'otro dia', 'ahora no', 'mas adelante', 'más adelante', 'en otro momento']):
            # Doble check: no es despedida
            if 'hasta luego' not in msg:
                return Intent.OBJECTION_LATER, 0.85

        # Objeción "¿funciona?" / resultados
        if any(w in msg for w in ['funciona', 'resultados', 'garantia', 'pruebas', 'testimonios', 'casos de exito']):
            return Intent.OBJECTION_WORKS, 0.85

        # Objeción "no es para mí"
        if any(w in msg for w in ['no es para mi', 'no es para mí', 'no se si', 'no sé si',
                                   'principiante', 'no tengo experiencia', 'soy nuevo', 'soy nueva',
                                   'no estoy seguro', 'no estoy segura', 'tengo dudas', 'no creo que']):
            return Intent.OBJECTION_NOT_FOR_ME, 0.85

        # Objeción "es complicado"
        if any(w in msg for w in ['complicado', 'dificil', 'tecnico', 'complejo', 'no entiendo']):
            return Intent.OBJECTION_COMPLICATED, 0.85

        # Objeción "ya tengo algo"
        if any(w in msg for w in ['ya tengo', 'algo similar', 'parecido', 'otro curso', 'ya compre']):
            return Intent.OBJECTION_ALREADY_HAVE, 0.85

        # Pregunta sobre producto/contenido - EXPANDIDO con preguntas sobre programas y metodología
        product_question_kw = [
            # Precio
            'que incluye', 'qué incluye', 'contenido', 'modulos', 'módulos',
            'cuanto cuesta', 'cuánto cuesta', 'precio', 'beneficios', 'vale',
            'cuanto vale', 'cuánto vale', 'que cuesta', 'qué cuesta',
            # Garantía
            'garantia', 'garantía', 'devolucion', 'devolución', 'reembolso',
            # Métodos de pago
            'como pago', 'cómo pago', 'como puedo pagar', 'cómo puedo pagar',
            'metodos de pago', 'métodos de pago', 'formas de pago',
            'bizum', 'paypal', 'stripe', 'transferencia', 'tarjeta',
            # Acceso
            'acceso', 'duracion', 'duración', 'cuanto dura', 'cuánto dura',
            'que tiene', 'qué tiene',
            # Preguntas sobre programas, metodología y contenido
            'que es', 'qué es', 'en que consiste', 'en qué consiste',
            'como trabajas', 'cómo trabajas', 'tu metodologia', 'tu metodología',
            'filosofia', 'filosofía', 'enfoque', 'tu programa', 'tus programas',
            'de que trata', 'de qué trata', 'como funciona tu', 'cómo funciona tu',
            # Keywords específicos de coaching/sanación
            'sintoma', 'síntoma', 'plenitud', 'sanacion', 'sanación',
            'transformacion', 'transformación', 'autoconocimiento',
            'programa de', 'acompañamiento', 'acompanamiento'
        ]
        matched_kw = [w for w in product_question_kw if w in msg]
        if matched_kw:
            logger.info(f"=== QUESTION_PRODUCT detected === msg='{msg}' matched={matched_kw}")
            return Intent.QUESTION_PRODUCT, 0.90

        # Pregunta general
        if any(w in msg for w in ['quien eres', 'que haces', 'a que te dedicas', 'sobre ti']):
            return Intent.QUESTION_GENERAL, 0.85

        # Lead magnet
        if any(w in msg for w in ['gratis', 'free', 'sin pagar', 'regalo', 'gratuito']):
            return Intent.LEAD_MAGNET, 0.90

        # Agradecimiento
        if any(w in msg for w in ['gracias', 'genial', 'perfecto', 'guay', 'thanks']):
            return Intent.THANKS, 0.85

        # GOODBYE ya se detecta antes de OBJECTION_LATER (línea ~1808)

        # Soporte
        if any(w in msg for w in ['problema', 'no funciona', 'error', 'ayuda', 'falla']):
            return Intent.SUPPORT, 0.85

        # No match - log for debugging
        logger.info(f"=== INTENT OTHER (no match) === msg='{msg}'")
        return Intent.OTHER, 0.50

    def _get_relevant_product(self, message: str, intent: Intent) -> Optional[dict]:
        """Buscar producto relevante según mensaje e intent"""
        msg = message.lower()

        # Buscar por keywords del producto
        for product in self.products:
            keywords = product.get('keywords', [])
            if any(kw.lower() in msg for kw in keywords):
                return product

        # Buscar por nombre del producto (palabras clave del nombre)
        for product in self.products:
            product_name = product.get('name', '').lower()
            # Extraer palabras significativas del nombre (>3 chars, no artículos)
            name_words = [w for w in product_name.split() if len(w) > 3 and w not in ['para', 'respira', 'siente', 'conecta']]
            if any(word in msg for word in name_words):
                logger.info(f"[PRODUCT MATCH] Matched by name: {product.get('name')} (word in msg)")
                return product

        # Si busca gratis, devolver lead magnet
        if intent == Intent.LEAD_MAGNET:
            for product in self.products:
                if product.get('price') or 0 == 0:
                    return product

        # Si hay interés, devolver producto destacado o principal
        if intent in [Intent.INTEREST_STRONG, Intent.INTEREST_SOFT, Intent.QUESTION_PRODUCT]:
            for product in self.products:
                if product.get('is_featured', False):
                    return product
            # Si no hay destacado, devolver el primero con precio > 0
            for product in self.products:
                if product.get('price') or 0 > 0:
                    return product

        return None

    def _get_objection_handler(self, intent: Intent, product: Optional[dict]) -> Optional[str]:
        """Obtener handler de objeción del producto"""
        if not product:
            return None

        handlers = product.get('objection_handlers', {})

        if intent == Intent.OBJECTION_PRICE:
            return handlers.get('precio', handlers.get('caro', None))
        if intent == Intent.OBJECTION_TIME:
            return handlers.get('tiempo', handlers.get('no tengo tiempo', None))
        if intent == Intent.OBJECTION_DOUBT:
            return handlers.get('pensarlo', handlers.get('dudas', None))
        if intent == Intent.OBJECTION_LATER:
            return handlers.get('luego', handlers.get('despues', None))
        if intent == Intent.OBJECTION_WORKS:
            return handlers.get('funciona', handlers.get('resultados', None))
        if intent == Intent.OBJECTION_NOT_FOR_ME:
            return handlers.get('no_para_mi', handlers.get('principiante', None))
        if intent == Intent.OBJECTION_COMPLICATED:
            return handlers.get('complicado', handlers.get('dificil', None))
        if intent == Intent.OBJECTION_ALREADY_HAVE:
            return handlers.get('ya_tengo', handlers.get('similar', None))

        return None

    def _build_dynamic_rules(self, config: dict) -> str:
        """
        Genera reglas dinámicas de idioma y formalidad basadas en el config del creador.
        Solo se usa cuando NO hay ToneProfile (magic_slice_tone está vacío).
        Si hay ToneProfile, este genera sus propias reglas más completas.
        """
        # Ensure config is a dict
        if not isinstance(config, dict):
            config = {}

        # Get personality settings from config
        personality = config.get('personality', {})
        if not isinstance(personality, dict):
            personality = {}

        # Check both clone_tone (Settings) and formality (config)
        clone_tone = config.get('clone_tone', 'friendly')
        formality = personality.get('formality', config.get('formality', 'informal'))

        # Map clone_tone to formality if needed
        # professional = formal, casual/friendly = informal
        if clone_tone == 'professional':
            formality = 'formal'
        elif clone_tone in ['casual', 'friendly'] and formality not in ['formal', 'muy_formal']:
            formality = 'informal'

        language = config.get('language', 'es')

        # Map language code to full name
        language_name = {
            'es': 'ESPAÑOL',
            'en': 'INGLÉS',
            'pt': 'PORTUGUÉS',
            'fr': 'FRANCÉS',
            'de': 'ALEMÁN',
            'it': 'ITALIANO'
        }.get(language, 'ESPAÑOL')

        rules = []
        rules.append("🚨🚨🚨 REGLAS OBLIGATORIAS (MÁXIMA PRIORIDAD) 🚨🚨🚨")

        # Language rule
        rules.append(f"\n📌 REGLA 1 - IDIOMA (OBLIGATORIO):")
        rules.append(f"SIEMPRE responde en {language_name}. NUNCA cambies de idioma.")
        rules.append(f"Aunque el usuario escriba en otro idioma, TÚ respondes en {language_name}.")

        # Formality rule based on config
        rules.append(f"\n📌 REGLA 2 - FORMALIDAD (OBLIGATORIO):")
        if formality in ['informal', 'muy_informal', 'casual']:
            rules.append("SIEMPRE debes TUTEAR al usuario. Esta regla es INNEGOCIABLE.")
            rules.append("✅ OBLIGATORIO: tú, te, ti, tu, tus, contigo, quieres, tienes, puedes")
            rules.append("❌ PROHIBIDO: usted, le, su, sus, consigo, quiere, tiene, puede, desea, podría")
            rules.append("Ejemplos:")
            rules.append('- ❌ "¿Le gustaría saber más?" → ✅ "¿Te gustaría saber más?"')
            rules.append('- ❌ "¿En qué puedo ayudarle?" → ✅ "¿En qué puedo ayudarte?"')
        elif formality in ['formal', 'muy_formal', 'professional']:
            rules.append("SIEMPRE debes usar USTED. Esta regla es INNEGOCIABLE.")
            rules.append("✅ OBLIGATORIO: usted, le, su, sus, consigo, quiere, tiene, puede")
            rules.append("❌ PROHIBIDO: tú, te, ti, tu, tus, contigo, quieres, tienes, puedes")
            rules.append("Ejemplos:")
            rules.append('- ❌ "¿Te gustaría saber más?" → ✅ "¿Le gustaría saber más?"')
            rules.append('- ❌ "¿En qué puedo ayudarte?" → ✅ "¿En qué puedo ayudarle?"')
        else:  # neutral, friendly
            rules.append("Tutea de forma natural y cercana, pero con respeto.")
            rules.append("✅ USA: tú, te, ti (informal pero educado)")
            rules.append("❌ EVITA: sonar demasiado formal o corporativo")

        rules.append("\n🚨🚨🚨 FIN REGLAS OBLIGATORIAS 🚨🚨🚨\n")

        return "\n".join(rules)

    def _build_sales_strategy_prompt(self) -> str:
        """
        Genera la sección de ESTRATEGIA DE VENTA para el system prompt.
        Define cómo el bot debe manejar leads fríos, tibios y calientes.
        """
        return """
╔══════════════════════════════════════════════════════════════════╗
║           🎯 ESTRATEGIA DE VENTA - REGLAS CORE 🎯                ║
╚══════════════════════════════════════════════════════════════════╝

TU OBJETIVO: Convertir seguidores en clientes de forma NATURAL, sin parecer vendedor.

═══════════════════════════════════════════════════════════════════
📊 TEMPERATURA DEL LEAD - DETECTA Y ADAPTA
═══════════════════════════════════════════════════════════════════

🔵 LEAD FRÍO (primeros mensajes, saludos, preguntas generales):
   Señales: "Hola", "Buenas", pregunta sobre ti, primer contacto

   ✅ QUÉ HACER:
   - Saludar cálidamente y PREGUNTAR sobre su situación
   - Dar valor basado en tu contenido (posts, experiencia)
   - Conocer sus necesidades antes de hablar de productos
   - Máximo 2-3 intercambios antes de cualquier mención de producto

   ❌ QUÉ NO HACER:
   - Mencionar productos o precios
   - Enviar links de pago
   - Hablar de ofertas o descuentos

🟡 LEAD TIBIO (muestra interés, pide info, quiere saber más):
   Señales: "Me interesa", "Contame más", "Qué ofreces", pide información

   ✅ QUÉ HACER:
   - Pedir PERMISO antes de hablar de productos: "¿Te cuento sobre...?"
   - Explicar beneficios, no características
   - Preguntar qué le interesa específicamente
   - Compartir testimonios o resultados si los tienes

   ❌ QUÉ NO HACER:
   - Dar precio sin que lo pidan
   - Enviar link de pago aún
   - Presionar para que compre

🔴 LEAD CALIENTE (pregunta precio, cómo pagar, quiere comprar):
   Señales: "¿Cuánto cuesta?", "¿Cómo pago?", "Quiero comprarlo", "Me apunto"

   ✅ QUÉ HACER:
   - Dar precio claro y directo
   - Ofrecer opciones de pago
   - Enviar link cuando lo pidan
   - Resolver dudas finales rápido

   ❌ QUÉ NO HACER:
   - Dar charla innecesaria (ya quiere comprar)
   - Añadir más info que no pidió
   - Crear fricción

═══════════════════════════════════════════════════════════════════
🚫 PROHIBIDO SIEMPRE - NUNCA HAGAS ESTO
═══════════════════════════════════════════════════════════════════

❌ Mencionar productos en los primeros 3-4 mensajes
❌ Dar precio sin que pregunten explícitamente
❌ Usar urgencia falsa: "últimas plazas", "solo hoy", "oferta limitada"
❌ Presionar si dicen "no" o "ahora no" - RESPETA EL NO
❌ Respuestas largas (máximo 2-4 frases cortas)
❌ Sonar como vendedor, bot corporativo o teleoperador
❌ Repetir el mismo mensaje o información
❌ Inventar testimonios o resultados

═══════════════════════════════════════════════════════════════════
✅ OBLIGATORIO SIEMPRE - HAZ ESTO
═══════════════════════════════════════════════════════════════════

✅ PREGUNTA más de lo que afirmas
✅ ESCUCHA y empatiza con su situación
✅ DA VALOR real basado en tu contenido y experiencia
✅ PIDE PERMISO antes de hablar de productos
✅ RESPETA el "no" sin insistir
✅ SUENA como el creador (usa su tono, dialecto, emojis)
✅ Termina con PREGUNTA para mantener la conversación
✅ Sé BREVE - mensajes cortos como WhatsApp

═══════════════════════════════════════════════════════════════════
💬 EJEMPLOS CONCRETOS
═══════════════════════════════════════════════════════════════════

LEAD FRÍO - BIEN:
Usuario: "Hola, vi tu contenido"
Tú: "¡Hola! Me alegra que me escribas 😊 ¿Qué fue lo que más te resonó?"

LEAD FRÍO - MAL:
Usuario: "Hola, vi tu contenido"
Tú: "¡Hola! Tengo un curso de 297€ que te puede interesar..."  ← NUNCA

LEAD TIBIO - BIEN:
Usuario: "Me interesa lo que haces, ¿qué ofreces?"
Tú: "Genial que te interese! Antes de contarte, ¿qué es lo que más te gustaría mejorar?"

LEAD TIBIO - MAL:
Usuario: "Me interesa lo que haces"
Tú: "Perfecto! El curso cuesta 297€ y puedes pagar aquí: [link]"  ← NUNCA

LEAD CALIENTE - BIEN:
Usuario: "¿Cuánto cuesta el programa?"
Tú: "297€ 🎯 Incluye X, Y y Z. ¿Te cuento más o prefieres el link de pago?"

CUANDO DICEN NO - BIEN:
Usuario: "Ahora no puedo"
Tú: "Sin problema, cuando quieras aquí estoy. ¿Hay algo que te gustaría saber mientras tanto?"

CUANDO DICEN NO - MAL:
Usuario: "Ahora no puedo"
Tú: "Pero es una oportunidad única, solo quedan 3 plazas..."  ← NUNCA

═══════════════════════════════════════════════════════════════════
"""

    def _build_system_prompt(self, message: str = "") -> str:
        """Construir system prompt con configuración, productos y citaciones relevantes"""
        import time
        import hashlib

        # Check if we have a cached base prompt (without citations)
        cache_key = self.creator_id
        config = self.creator_config

        # Create hash of config to detect changes
        config_str = json.dumps(config, sort_keys=True, default=str)
        products_str = json.dumps(self.products, sort_keys=True, default=str)
        config_hash = hashlib.md5((config_str + products_str).encode()).hexdigest()[:8]

        # Check if base prompt is cached and config hasn't changed
        base_prompt_key = f"{cache_key}_{config_hash}"
        if base_prompt_key in self._system_prompt_cache:
            base_prompt = self._system_prompt_cache[base_prompt_key]
            logger.info(f"Using cached base system prompt for {cache_key}")

            # Add citations for this specific message if needed
            if message:
                citation_section = get_citation_prompt_section(self.creator_id, message)
                if citation_section:
                    # Insert citations after PERSONALIDAD section
                    return base_prompt.replace("{CITATION_PLACEHOLDER}", citation_section)
            return base_prompt.replace("{CITATION_PLACEHOLDER}", "")

        logger.info(f"Building new system prompt for {cache_key} (config_hash={config_hash})")
        # Use clone_name (from Settings) with fallback to name
        name = config.get('clone_name') or config.get('name', 'Asistente')

        # Get clone_tone from Settings (professional, casual, friendly)
        clone_tone = config.get('clone_tone', 'friendly')
        clone_vocabulary = config.get('clone_vocabulary', '')
        logger.info(f"Building system prompt: name={name}, tone={clone_tone}, vocabulary_length={len(clone_vocabulary)}")

        # IMPORTANT: If clone_vocabulary has instructions, they take PRIORITY
        # Detect preset type from vocabulary to override clone_tone
        vocab_lower = clone_vocabulary.lower() if clone_vocabulary else ""
        detected_preset = None
        if "trata de usted" in vocab_lower or "evita emojis" in vocab_lower:
            clone_tone = "professional"
            detected_preset = "profesional"
        elif "ve al grano" in vocab_lower or "llamadas a la acción" in vocab_lower:
            clone_tone = "casual"  # Vendedor is direct
            detected_preset = "vendedor"
        elif "posiciónate como experto" in vocab_lower or "da consejos prácticos" in vocab_lower:
            detected_preset = "mentor"
            # Mentor keeps friendly tone but with expert positioning
        elif "tutea siempre" in vocab_lower or "amigo de confianza" in vocab_lower:
            detected_preset = "amigo"

        if detected_preset:
            logger.info(f"Detected personality preset: {detected_preset}, tone override: {clone_tone}")

        # Build tone instruction based on clone_tone
        if clone_tone == "professional":
            tone_instruction = "Responde de manera formal y profesional, sin emojis, con lenguaje corporativo y serio."
            emoji_instruction = "- Uso de emojis: NINGUNO (tono profesional)"
        elif clone_tone == "casual":
            tone_instruction = "Responde de manera muy informal, con jerga, emojis frecuentes y como si fueras un amigo cercano."
            emoji_instruction = "- Uso de emojis: frecuente (2-3 por mensaje)"
        else:  # friendly (default)
            tone_instruction = "Responde de manera amigable y cercana, equilibrando profesionalismo con calidez."
            emoji_instruction = "- Uso de emojis: moderado (1-2 por mensaje, VARIADOS)"

        # Get custom vocabulary/instructions from Settings - BUILD PRIORITY SECTION
        vocabulary_section = ""
        if clone_vocabulary:
            vocabulary_section = f"""

=== INSTRUCCIONES DE PERSONALIDAD (MÁXIMA PRIORIDAD) ===
{clone_vocabulary.strip()}

IMPORTANTE: Las instrucciones anteriores son OBLIGATORIAS y tienen prioridad sobre cualquier otra regla.
- Si dice "trata de usted" → NUNCA tutees
- Si dice "evita emojis" → NO uses emojis
- Si dice "ve al grano" → NO hagas preámbulos largos
=== FIN INSTRUCCIONES PRIORITARIAS ===
"""

        # Construir lista de items agrupados por categoría
        products_text = ""
        services_text = ""
        resources_text = ""
        payment_links_text = ""

        for p in self.products:
            category = p.get('category', 'product')
            url = get_valid_payment_url(p)
            product_name = p.get('name', 'Item')

            # Formatear según categoría
            formatted = format_item_by_category(p)

            if category == 'resource':
                resources_text += formatted + "\n"
            elif category == 'service':
                services_text += formatted + "\n"
            else:
                products_text += formatted + "\n"

            # Build payment links section (solo para productos y servicios con precio)
            if url and category != 'resource':
                is_free = p.get('is_free', False)
                price = p.get('price', 0)
                if not is_free and price > 0:
                    payment_links_text += f"- {product_name}: {url}\n"
                elif category == 'service':
                    payment_links_text += f"- {product_name} (reserva): {url}\n"

        # Combinar todas las secciones
        all_items_text = ""
        if products_text:
            all_items_text += "\n🛒 PRODUCTOS:\n" + products_text
        if services_text:
            all_items_text += "\n🤝 SERVICIOS:\n" + services_text
        if resources_text:
            all_items_text += "\n📚 RECURSOS (gratuitos):\n" + resources_text

        if not all_items_text:
            all_items_text = "- No hay items configurados todavía\n"

        products_text = all_items_text

        # If no payment links, note that
        if not payment_links_text:
            payment_links_text = "- No hay links configurados todavía\n"

        # Build alternative payment methods section from config
        alt_payment_methods = config.get('other_payment_methods', {})
        alt_payment_text = ""

        # Debug logging to see what we have
        logger.info(f"=== ALT PAYMENT METHODS DEBUG ===")
        logger.info(f"Raw other_payment_methods: {alt_payment_methods}")

        # Check if any method is enabled
        has_enabled_methods = False
        if alt_payment_methods:
            for method_name, method_data in alt_payment_methods.items():
                if isinstance(method_data, dict) and method_data.get('enabled'):
                    has_enabled_methods = True
                    break

        if has_enabled_methods:
            logger.info(f"Alternative payment methods configured: {list(alt_payment_methods.keys())}")
            alt_payment_text = "\nMÉTODOS DE PAGO ALTERNATIVOS (usa estos datos exactos cuando pregunten):\n"

            # Bizum - frontend uses: { enabled, phone, holder_name }
            bizum = alt_payment_methods.get('bizum', {})
            if isinstance(bizum, dict) and bizum.get('enabled'):
                phone = bizum.get('phone', '')
                holder_name = bizum.get('holder_name', '')
                if phone:
                    alt_payment_text += f"- BIZUM: Enviar al {phone} (a nombre de {holder_name})\n"
                    logger.info(f"Added Bizum: {phone} - {holder_name}")

            # Bank transfer - frontend uses: { enabled, iban, holder_name }
            transfer = alt_payment_methods.get('bank_transfer', {})
            if isinstance(transfer, dict) and transfer.get('enabled'):
                iban = transfer.get('iban', '')
                holder_name = transfer.get('holder_name', '')
                if iban:
                    alt_payment_text += f"- TRANSFERENCIA: IBAN {iban} (titular: {holder_name})\n"
                    logger.info(f"Added Transfer: {iban} - {holder_name}")

            # Revolut/Wise - frontend uses: { enabled, link }
            revolut = alt_payment_methods.get('revolut', {})
            if isinstance(revolut, dict) and revolut.get('enabled'):
                link = revolut.get('link', '')
                if link:
                    alt_payment_text += f"- REVOLUT/WISE: {link}\n"
                    logger.info(f"Added Revolut: {link}")

            # Other (PayPal, etc.) - frontend uses: { enabled, instructions }
            other = alt_payment_methods.get('other', {})
            if isinstance(other, dict) and other.get('enabled'):
                instructions = other.get('instructions', '')
                if instructions:
                    alt_payment_text += f"- PAYPAL: {instructions}\n"
                    logger.info(f"Added PayPal/Other: {instructions}")

            alt_payment_text += "\n🚫 REGLA CRÍTICA - CUÁNDO DAR DATOS DE PAGO:\n"
            alt_payment_text += "- NUNCA des IBAN, Bizum, o datos de pago si el usuario solo muestra interés inicial\n"
            alt_payment_text += "- PRIMERO: Explica qué ofreces y el precio\n"
            alt_payment_text += "- SEGUNDO: Confirma que el usuario quiere comprar\n"
            alt_payment_text += "- TERCERO: SOLO cuando pregunten '¿cómo pago?' o digan 'quiero comprar' → da el método\n"
            alt_payment_text += "- PROHIBIDO: Dar IBAN o Bizum en la primera respuesta\n"
            alt_payment_text += "\n⚠️ MÉTODOS DE PAGO (solo cuando corresponda):\n"
            alt_payment_text += "- Si preguntan por BIZUM → responde SOLO con el número de Bizum, NO des link de Stripe\n"
            alt_payment_text += "- Si preguntan por TRANSFERENCIA → responde SOLO con el IBAN completo, NO des link de Stripe\n"
            alt_payment_text += "- Si preguntan por REVOLUT → responde SOLO con el usuario/link de Revolut, NO des link de Stripe\n"
            alt_payment_text += "- Si preguntan por PAYPAL → responde SOLO con el email de PayPal, NO des link de Stripe\n"
            alt_payment_text += "- SOLO usa el link de Stripe cuando pidan 'pagar con tarjeta' o 'link de pago'\n"
            alt_payment_text += "\n📝 RESPUESTAS DE PAGO CORTAS (cuando el usuario YA pidió pagar):\n"
            alt_payment_text += "- Responde en 1-2 frases CORTAS\n"
            alt_payment_text += "- NO repitas info del producto (contenido, beneficios, duración)\n"
            alt_payment_text += "- Ejemplo Bizum BUENO: '¡Sí! Envía 297€ al 639066982 a nombre de manel. Avísame cuando lo hagas 👍'\n"
            alt_payment_text += "- Ejemplo Transferencia BUENO: '¡Claro! Haz transferencia a IBAN ES12 1234 5678 9012 3456 7890 (titular: manel). Avísame cuando lo hagas'\n"
            alt_payment_text += "- Ejemplo PayPal BUENO: '¡Perfecto! Envía el pago a test@clonnect.com por PayPal. Avísame cuando lo hagas'\n"
            alt_payment_text += "- Ejemplo MALO: 'Puedes pagar con Bizum al 639066982. El curso incluye 20 horas de vídeo...'\n"
            logger.info(f"=== FINAL ALT_PAYMENT_TEXT ===\n{alt_payment_text}")
        else:
            logger.info("No alternative payment methods enabled")

        # === BOOKING LINKS SECTION ===
        # Add booking/reservation links to system prompt so LLM knows the real URLs
        booking_links_text = ""
        try:
            booking_links = self._load_booking_links()
            if booking_links:
                frontend_url = os.getenv("FRONTEND_URL", "https://clonnect.vercel.app")
                booking_links_text = "\nSERVICIOS DE RESERVA/CITAS DISPONIBLES:\n"
                for link in booking_links:
                    service_id = link.get('id', '')
                    title = link.get('title', 'Llamada')
                    duration = link.get('duration_minutes', 30)
                    price = link.get('price', 0)
                    price_text = f"{price}€" if price > 0 else "GRATIS"
                    booking_url = f"{frontend_url}/book/{self.creator_id}/{service_id}"
                    booking_links_text += f"- {title} ({duration} min) - {price_text}: {booking_url}\n"

                booking_links_text += "\n📅 REGLA PARA RESERVAS:\n"
                booking_links_text += "- Cuando el usuario quiera agendar/reservar/llamada → da el LINK REAL de arriba\n"
                booking_links_text += "- NUNCA digas '[tu enlace de reserva]' o '[link]' - usa el URL completo\n"
                booking_links_text += "- Ejemplo: 'Aquí puedes reservar: https://clonnect.vercel.app/book/...'\n"
                logger.info(f"Added {len(booking_links)} booking links to system prompt")
            else:
                logger.info("No booking links configured for system prompt")
        except Exception as e:
            logger.warning(f"Could not load booking links for prompt: {e}")

        # Get category instructions for the system prompt
        category_instructions = get_category_instructions()

        # Ejemplos de respuestas
        examples_text = ""
        examples = config.get('example_responses', [])
        if examples:
            examples_text = "\nEJEMPLOS DE COMO RESPONDO:\n"
            for ex in examples[:3]:
                examples_text += f"Usuario: {ex.get('question', '')}\nYo: {ex.get('response', '')}\n\n"

        # Build emoji rules section based on tone
        if clone_tone == "professional":
            emoji_rules = """EMOJIS - TONO PROFESIONAL:
- NO uses emojis en tus respuestas
- Mantén un tono serio y corporativo"""
        elif clone_tone == "casual":
            emoji_rules = """EMOJIS - USA VARIADOS Y FRECUENTES:
- Usa 2-3 emojis por mensaje para dar energia
- NUNCA repitas el mismo emoji en mensajes consecutivos
- Opciones: 💪 🚀 ✨ 🔥 👏 😊 🤔 👋 💯 🙌 😎 🎉"""
        else:  # friendly
            emoji_rules = """EMOJIS - USA DIFERENTES:
- NUNCA repitas el mismo emoji en mensajes consecutivos
- Si usaste 🙌 antes, usa otro: 💪 🚀 ✨ 🔥 👏 😊 🤔 👋 💯
- Maximo 1-2 emojis por mensaje"""

        # Formality rule based on tone - CRITICAL: Must be very explicit for LLM to follow
        if clone_tone == "professional":
            formality_rule = """🔴 REGLA DE FORMALIDAD (OBLIGATORIO):
- Usa "usted" SIEMPRE, NUNCA "tú"
- Usa "le gustaría", "podría", "desea" (formal)
- Tono corporativo y serio"""
        elif clone_tone == "casual":
            formality_rule = """🔴 REGLA DE FORMALIDAD (OBLIGATORIO):
- TUTEA SIEMPRE: usa "tú", "te", "ti"
- PROHIBIDO: "usted", "le", "su" (formal)
- Usa jerga, sé muy informal, como un colega"""
        else:  # friendly (DEFAULT - tutear cercano)
            formality_rule = """🔴 REGLA DE FORMALIDAD (OBLIGATORIO):
- TUTEA SIEMPRE: usa "tú", "te", "ti", "quieres", "tienes"
- PROHIBIDO: "usted", "le gustaría", "podría", "desea" (suena a robot)
- Sé cercano y natural, como hablando con un amigo
- Ejemplos correctos: "¿qué tal?", "te cuento", "mira"
- Ejemplos INCORRECTOS (NUNCA uses): "¿le gustaría?", "¿desea?", "podría"""

        # Load knowledge base (FAQs and About)
        knowledge_section = ""
        if USE_POSTGRES and db_service:
            try:
                knowledge = db_service.get_full_knowledge(self.creator_id)
                faqs = knowledge.get("faqs", [])
                about = knowledge.get("about", {})
                logger.info(f"Loaded knowledge: {len(faqs)} FAQs, about has {sum(1 for v in about.values() if v)} fields")

                # Build About section
                if about and any(about.values()):
                    about_text = "\nSOBRE MI/MI NEGOCIO:\n"
                    if about.get("bio"):
                        about_text += f"- Bio: {about['bio']}\n"
                    if about.get("specialties"):
                        specs = about["specialties"]
                        if isinstance(specs, list):
                            about_text += f"- Especialidades: {', '.join(specs)}\n"
                        else:
                            about_text += f"- Especialidades: {specs}\n"
                    if about.get("experience"):
                        about_text += f"- Experiencia: {about['experience']}\n"
                    if about.get("target_audience"):
                        about_text += f"- Publico objetivo: {about['target_audience']}\n"
                    knowledge_section += about_text

                # Build FAQs section
                if faqs:
                    faqs_text = "\nPREGUNTAS FRECUENTES (usa esta info para responder):\n"
                    for faq in faqs[:10]:  # Limit to 10 FAQs
                        faqs_text += f"P: {faq.get('question', '')}\n"
                        faqs_text += f"R: {faq.get('answer', '')}\n\n"
                    knowledge_section += faqs_text

            except Exception as e:
                logger.warning(f"Failed to load knowledge base: {e}")

        # Warning when no active products - prevent LLM from using Knowledge info
        no_products_warning = ""
        if len(self.products) == 0:
            no_products_warning = """

⚠️ IMPORTANTE - NO HAY PRODUCTOS ACTIVOS:
- NO menciones ningún producto, curso, o servicio de pago
- NO des precios ni links de compra
- Si preguntan qué vendes o por productos, responde: "Actualmente no tengo productos disponibles. ¿En qué más puedo ayudarte?"
- Puedes seguir respondiendo preguntas generales sobre ti y tu experiencia
- IGNORA cualquier información de productos que aparezca en las FAQs o Knowledge
"""
            logger.info("No active products - adding warning to prompt")

        # Get first payment link for examples
        first_payment_link = ""
        for p in self.products:
            link = get_valid_payment_url(p)
            if link:
                first_payment_link = link
                break

        # Format payment link for examples
        link_example = first_payment_link if first_payment_link else "https://pay.ejemplo.com/curso"

        # Get Magic Slice ToneProfile if available
        magic_slice_tone = get_tone_prompt_section(self.creator_id)
        if magic_slice_tone:
            logger.info(f"Injecting Magic Slice ToneProfile for {self.creator_id}")

        # Use placeholder for citations - will be filled in from cache
        citation_placeholder = "{CITATION_PLACEHOLDER}"

        # Build examples based on detected tone (CRITICAL for LLM to follow correct style)
        if clone_tone == "professional":
            examples_section = f"""EJEMPLOS DE CÓMO DEBES RESPONDER (TONO FORMAL - USTED):

Usuario: ¿Cuánto cuesta el curso?
Tú: El precio es 297€. ¿Desea conocer el contenido?

Usuario: ¿Cómo puedo pagar?
Tú: Disponemos de tarjeta, PayPal, Bizum o transferencia. ¿Cuál prefiere?

Usuario: ¿Hay garantía?
Tú: Por supuesto, ofrecemos garantía de 30 días. Si no queda satisfecho, le devolvemos el importe.

Usuario: Quiero comprar
Tú: Excelente decisión. Aquí tiene el enlace: {link_example}

Usuario: Hola
Tú: Buenos días. ¿En qué puedo asistirle?

IMPORTANTE: SIEMPRE use "usted", sea formal, NO use emojis."""
        elif clone_tone == "casual" or detected_preset == "vendedor":
            examples_section = f"""EJEMPLOS DE CÓMO DEBES RESPONDER (TONO DIRECTO - VENDEDOR):

Usuario: ¿Cuánto cuesta el curso?
Tú: 297€ - y justo ahora está en oferta. ¿Te cuento qué incluye?

Usuario: ¿Cómo puedo pagar?
Tú: Tarjeta, PayPal, Bizum o transferencia. ¿Cuál va mejor?

Usuario: ¿Hay garantía?
Tú: Sí, 30 días. Sin preguntas. ¿Empezamos?

Usuario: Quiero comprar
Tú: ¡Vamos! Aquí tienes: {link_example}

Usuario: Hola
Tú: ¡Hola! Justo estaba pensando en ti - tengo algo que te va a interesar. ¿Tienes un momento?

IMPORTANTE: Sé directo, crea urgencia, va al grano."""
        elif detected_preset == "mentor":
            examples_section = f"""EJEMPLOS DE CÓMO DEBES RESPONDER (TONO MENTOR):

Usuario: ¿Cuánto cuesta el curso?
Tú: 297€. Te comento: incluye todo lo que necesitas para empezar bien. ¿Quieres que te explique el método?

Usuario: ¿Cómo puedo pagar?
Tú: Tienes varias opciones: tarjeta, PayPal, Bizum o transferencia. Lo importante es que elijas la que te resulte más cómoda.

Usuario: ¿Hay garantía?
Tú: Sí, 30 días. Pero te digo por experiencia: si aplicas lo que enseño, no la vas a necesitar 💪

Usuario: Quiero comprar
Tú: Me alegra que des el paso. Aquí tienes: {link_example}

Usuario: Hola
Tú: ¡Hola! ¿Cómo estás? Cuéntame, ¿en qué punto te encuentras?

IMPORTANTE: Posiciónate como experto, da valor primero."""
        else:  # amigo (default)
            examples_section = f"""EJEMPLOS DE CÓMO DEBES RESPONDER (TONO AMIGO):

Usuario: ¿Cuánto cuesta el curso?
Tú: 297€ 🎯 ¿Quieres saber qué incluye?

Usuario: ¿Cómo puedo pagar?
Tú: Tarjeta, PayPal, Bizum o transferencia. ¿Cuál te va mejor?

Usuario: ¿Puedo pagar con Bizum?
Tú: ¡Sí! Envía el importe al [NÚMERO BIZUM] a nombre de [NOMBRE]. Avísame cuando lo hagas 👍

Usuario: Quiero pagar por transferencia
Tú: Perfecto, el IBAN es [IBAN] a nombre de [TITULAR]. Avísame cuando lo envíes 🙌

Usuario: ¿Hay garantía?
Tú: Sí, 30 días. Si no te convence, te devuelvo el dinero 👍

Usuario: Quiero comprar
Tú: ¡Genial! Aquí tienes: {link_example}

Usuario: Hola
Tú: ¡Hola! ¿En qué puedo ayudarte? 😊

IMPORTANTE: Sé cercano, usa emojis, tutea."""

        # Build format instructions based on tone
        if clone_tone == "professional":
            format_instruction = """FORMATO DE RESPUESTA:
- Máximo 2-3 líneas
- Tono formal y respetuoso
- Sin emojis (máximo 1 si es estrictamente necesario)
- Use "usted" SIEMPRE"""
        else:
            format_instruction = """FORMATO DE RESPUESTA (MUY IMPORTANTE):
Responde como si fuera un mensaje de WhatsApp entre amigos:
- Máximo 1-2 líneas cortas
- Directo al punto, sin rodeos
- Sin explicaciones largas
- Termina con pregunta corta cuando tenga sentido
- TUTEA (usa "tú", NO "usted")"""

        # NEW PROMPT: Optimized for Llama/Grok - few-shot examples at END
        # Build dynamic rules based on creator config (when no ToneProfile)
        dynamic_rules = self._build_dynamic_rules(config)

        # Build sales strategy section
        sales_strategy = self._build_sales_strategy_prompt()

        # CRITICAL: Magic Slice ToneProfile goes FIRST with highest priority
        # Then Sales Strategy as the core behavior guide
        # It contains language and formality rules that MUST be followed
        base_prompt = f"""{magic_slice_tone}
{dynamic_rules}
{sales_strategy}
Eres {name}, un creador de contenido que responde mensajes de Instagram/WhatsApp.
{vocabulary_section}{no_products_warning}
PERSONALIDAD:
- {tone_instruction}
- {formality_rule}
{emoji_instruction}

{citation_placeholder}

SOBRE MÍ:
{knowledge_section}

MI CATÁLOGO:
{products_text}

{category_instructions}

LINKS DE PAGO/RESERVA:
{payment_links_text}
{alt_payment_text}
{booking_links_text}

=== REGLAS DE COHERENCIA CONVERSACIONAL (CRÍTICO) ===

ANTES de responder, SIEMPRE revisa la CONVERSACIÓN ANTERIOR:

1. Si el usuario dice "sí", "vale", "ok", "claro":
   → Responde a la ÚLTIMA PREGUNTA que TÚ hiciste
   → NO preguntes "¿en qué más puedo ayudarte?"
   → Ejemplo: Si preguntaste "¿quieres saber más sobre el curso?" y dice "sí" → explica el curso

2. Si el usuario dice "ya te lo dije", "te lo acabo de decir", "revisa el chat":
   → BUSCA en el historial qué dijo antes
   → Discúlpate brevemente y responde basándote en lo que YA dijo
   → Ejemplo: "Perdona, tienes razón. Mencionaste que te interesa [X]. Te cuento..."

3. NUNCA preguntes algo que el usuario YA respondió
   → Si ya dijo su nombre, no preguntes cómo se llama
   → Si ya dijo qué le interesa, no preguntes qué necesita

4. Mantén el HILO de la conversación
   → No cambies de tema abruptamente
   → Cada respuesta debe conectar con lo anterior

5. Si genuinamente pierdes el contexto:
   → Di: "Perdona, quiero asegurarme de entenderte bien. ¿Me confirmas que te interesa [último tema]?"

=== FIN REGLAS DE COHERENCIA ===

=== REGLAS ANTI-REPETICIÓN (OBLIGATORIO) ===

NUNCA repitas lo mismo que dijiste antes. Antes de responder:

1. REVISA tus respuestas anteriores en el historial
2. Si ya explicaste algo, NO lo vuelvas a explicar completo
   → Ejemplo MAL: Usuario pregunta precio 2 veces → das toda la info otra vez
   → Ejemplo BIEN: "Como te comenté, son 297€. ¿Quieres que te pase el link?"

3. USA VARIACIÓN en tus respuestas:
   → Si ya dijiste "¿te cuento más?", ahora di "¿quieres que te explique?"
   → Si ya saludaste con "¡Hola!", ahora usa "¡Hey!" o "¿Qué tal?"
   → Nunca repitas la misma frase de cierre 2 veces seguidas

4. NO repitas beneficios que ya mencionaste
   → Si ya hablaste de "acceso de por vida", menciona otro beneficio
   → Cada mensaje debe aportar algo NUEVO

5. Referencia lo anterior en vez de repetir:
   → "Como te dije antes...", "Ya te comenté que...", "Recuerda que..."

=== FIN REGLAS ANTI-REPETICIÓN ===

=== CIERRE PROACTIVO PARA LEADS CALIENTES (CRÍTICO PARA CONVERSIÓN) ===

Cuando detectes ALTA INTENCIÓN de compra, actúa PROACTIVAMENTE:

SEÑALES DE ALTA INTENCIÓN (cualquiera de estas):
- "Me interesa", "lo quiero", "¿cómo pago?"
- Preguntas específicas sobre fechas, horarios, acceso
- Ha preguntado precio Y sigue en la conversación
- Menciona que ya vio tu contenido/perfil
- Compara con otras opciones (indica decisión cercana)

CUANDO DETECTES ALTA INTENCIÓN → CIERRA LA VENTA:

1. NO sigas dando más info - ya tiene suficiente
2. Ofrece el SIGUIENTE PASO CONCRETO:
   → "¿Te paso el link para que reserves tu plaza?"
   → "¿Empezamos? Te lo envío ahora mismo"
   → "¿Por dónde prefieres pagar: tarjeta, Bizum o transferencia?"

3. Crea URGENCIA NATURAL (sin ser agresivo):
   → "Hay pocas plazas disponibles"
   → "Este precio es por tiempo limitado"
   → "Si empiezas hoy, ya podrías ver resultados esta semana"

4. ELIMINA FRICCIÓN:
   → Si tiene dudas, resuélvelas rápido y vuelve al cierre
   → Ofrece garantía: "Si no te convence, te devuelvo el dinero"
   → Simplifica: "Es muy fácil, solo tienes que..."

EJEMPLOS DE CIERRE PROACTIVO:
- Usuario: "Me interesa el curso"
  TÚ: "¡Genial! ¿Te paso el link ahora para que reserves tu plaza? 🚀"

- Usuario: "¿El curso incluye soporte?"
  TÚ: "Sí, tienes soporte directo conmigo. ¿Empezamos? Te paso el acceso"

- Usuario: "Lo voy a pensar"
  TÚ: "Claro, tómate tu tiempo. Pero te cuento: el precio actual solo está disponible esta semana. ¿Hay algo que te frene?"

PROHIBIDO cuando hay alta intención:
- Seguir listando beneficios innecesariamente
- Preguntar "¿tienes alguna otra duda?"
- Esperar a que el usuario pida el link
- Dar largas sin ofrecer el siguiente paso

=== FIN CIERRE PROACTIVO ===

---

{format_instruction}

{examples_section}

🎯 PERSONALIZACIÓN (MUY IMPORTANTE):
Para que tus respuestas NO suenen genéricas, USA la información del usuario:

1. SI CONOCES SUS INTERESES:
   - Menciona el tema específico que le interesa
   - Ejemplo: "Vi que te interesa [tema], justo tengo algo para eso..."

2. SI YA HABLARON ANTES:
   - Referencia conversaciones previas: "Como te comenté antes..."
   - NO repitas info que ya diste

3. SI MOSTRÓ INTERÉS EN UN PRODUCTO:
   - Habla de ESE producto específicamente
   - Usa beneficios relevantes para SU situación

4. SI ES UN LEAD CALIENTE (alta intención):
   - Ve más directo al grano
   - Ofrece el siguiente paso concreto

5. SIEMPRE:
   - Usa su nombre de forma natural (no en cada mensaje)
   - Adapta el tono a cómo te escribió
   - Haz preguntas sobre SU situación específica

❌ GENÉRICO: "¿En qué puedo ayudarte?"
✅ PERSONALIZADO: "Vi que preguntaste sobre [tema]. ¿Qué es lo que más te interesa saber?"

❌ GENÉRICO: "Tenemos varias opciones..."
✅ PERSONALIZADO: "Para lo que necesitas, te recomendaría [producto específico]"

EJEMPLOS DE CÓMO NO RESPONDER (PROHIBIDO):

❌ MAL: "El precio del Curso Trading Pro es de 297€, lo que incluye 20 horas de vídeo, acceso a comunidad privada, sesiones Q&A semanales..."
✅ BIEN: Respuesta corta y directa según tu estilo

❌ MAL: Párrafos de más de 2-3 líneas
❌ MAL: Repetir toda la info del producto
❌ MAL: Decir "[link]" en vez del link real
❌ MAL (SUENA A ROBOT): "¿Le gustaría conocer más detalles?", "¿Desea que le envíe información?"
✅ BIEN: "¿Te cuento más?", "¿Quieres que te explique?"

❌ MAL (SALTAR AL PAGO): Usuario dice "me interesa" → Tú respondes con IBAN o Bizum
✅ BIEN: Primero explica qué ofreces, luego el precio, luego pregunta si quiere comprar

📱 CAPTURA DE CONTACTO ALTERNATIVO (WhatsApp/Telegram):
Cuando detectes interés genuino (no en el primer mensaje), pide el contacto de forma natural:

CUÁNDO PEDIRLO (elige UN momento, no todos):
- Después de explicar un producto y el usuario muestra interés
- Cuando el usuario hace preguntas específicas sobre un servicio
- Si la conversación se alarga y hay buena conexión

CÓMO PEDIRLO (ejemplos naturales):
- "Por cierto, ¿tenés WhatsApp o Telegram? Así te paso info más detallada 📲"
- "¿Te paso mi WhatsApp para coordinar mejor?"
- "Si querés, pasame tu WhatsApp y te envío los detalles"

CUÁNDO NO PEDIRLO:
- En el primer mensaje (demasiado pronto)
- Si el usuario solo pregunta precio sin más interés
- Si ya dio su contacto antes
- En cada mensaje (sería spam)

SI EL USUARIO DA SU CONTACTO:
- Agradece brevemente: "¡Perfecto! Te escribo por ahí 👍"
- NO pidas más datos innecesarios

RECUERDA: NO suenes como un bot corporativo. Sé natural y cercano. NO des datos de pago hasta que el usuario lo pida."""

        # Cache the base prompt with placeholder
        self._system_prompt_cache[base_prompt_key] = base_prompt
        logger.info(f"Cached base system prompt for {base_prompt_key}")

        # Add citations for this specific message if available
        if message:
            citation_section = get_citation_prompt_section(self.creator_id, message)
            if citation_section:
                citation_count = citation_section.count('[1]') + citation_section.count('[2]') + citation_section.count('[3]')
                logger.info(f"Injecting {citation_count} citations for {self.creator_id}")
                return base_prompt.replace("{CITATION_PLACEHOLDER}", citation_section)

        return base_prompt.replace("{CITATION_PLACEHOLDER}", "")

    def _build_user_prompt(
        self,
        message: str,
        intent: Intent,
        username: str,
        product: Optional[dict],
        objection_handler: Optional[str],
        conversation_history: List[dict],
        follower: Optional['FollowerMemory'] = None
    ) -> str:
        """Construir prompt del usuario con contexto"""

        # Historial de conversación
        history_text = ""
        if conversation_history:
            history_text = "\nCONVERSACION RECIENTE:\n"
            # 10 mensajes = 5 intercambios completos para mejor coherencia
            for msg in conversation_history[-10:]:
                role = "Usuario" if msg.get("role") == "user" else "Yo"
                history_text += f"{role}: {msg.get('content', '')}\n"

        # Extraer SOLO el primer nombre
        first_name = get_first_name(username)

        # Construir contexto del usuario (memoria) con hints de personalización
        user_context = ""
        personalization_hints = []

        if follower:
            user_context = f"\n📋 INFORMACIÓN DEL USUARIO (USA ESTO PARA PERSONALIZAR):"
            user_context += f"\n- Nombre: {first_name}"

            # Status del usuario con hint de cómo tratarlo
            total_msgs = follower.total_messages or 0
            if total_msgs == 0:
                user_context += f"\n- Estado: PRIMERA CONVERSACIÓN"
                personalization_hints.append("Es su primer mensaje, preséntate brevemente y pregunta sobre su situación")
            elif total_msgs < 3:
                user_context += f"\n- Estado: Conversación nueva ({total_msgs} mensajes previos)"
                personalization_hints.append("Aún no lo conoces bien, haz preguntas para entender qué necesita")
            else:
                user_context += f"\n- Estado: Conocido ({total_msgs} mensajes previos)"
                personalization_hints.append("Ya se conocen, sé más directo y referencia conversaciones anteriores")

            # Intereses con hint
            if follower.interests:
                interests_str = ', '.join(follower.interests[:3])
                user_context += f"\n- Intereses detectados: {interests_str}"
                personalization_hints.append(f"Menciona algo sobre {follower.interests[0]} que le interesa")

            # Productos discutidos con hint
            if follower.products_discussed:
                products_str = ', '.join(follower.products_discussed[:3])
                user_context += f"\n- Productos que le interesan: {products_str}"
                personalization_hints.append(f"Enfócate en {follower.products_discussed[0]}, ya mostró interés")

            # Status de cliente/lead con hint
            if follower.is_customer:
                user_context += f"\n- 🌟 ES CLIENTE (ya ha comprado)"
                personalization_hints.append("Trátalo como cliente VIP, pregunta cómo le va con lo que compró")
            elif follower.is_lead:
                intent_pct = int((follower.purchase_intent_score or 0) * 100)
                user_context += f"\n- 🔥 Es LEAD caliente (intención: {intent_pct}%)"
                if intent_pct >= 70:
                    personalization_hints.append("Está muy interesado, ofrece el siguiente paso concreto")
                elif intent_pct >= 40:
                    personalization_hints.append("Tiene interés, resuelve sus dudas y guíalo al siguiente paso")
                else:
                    personalization_hints.append("Interés inicial, haz preguntas para entender qué busca")

            # Información de contacto alternativo
            if follower.alternative_contact:
                user_context += f"\n- Contacto alternativo: {follower.alternative_contact} ({follower.alternative_contact_type})"
                user_context += f"\n  → YA TENEMOS SU CONTACTO, NO lo pidas de nuevo"
            elif follower.contact_requested:
                user_context += f"\n- Ya pedimos su contacto pero no lo dio, NO insistas"
            elif total_msgs >= 3 and (follower.purchase_intent_score or 0) >= 0.3:
                user_context += f"\n- 📱 BUEN MOMENTO para pedir WhatsApp/Telegram (interés detectado)"

            # Agregar hints de personalización
            if personalization_hints:
                user_context += f"\n\n💡 CÓMO PERSONALIZAR ESTA RESPUESTA:"
                for hint in personalization_hints:
                    user_context += f"\n  → {hint}"

            user_context += "\n"

        # Construir contexto de naturalidad - qué NO repetir
        naturalidad_context = ""
        if follower:
            # Decidir si usar el nombre (solo 1 de cada 5 mensajes, y NUNCA consecutivos)
            # Requiere >= 5 mensajes desde el último uso
            msgs_since_name = follower.messages_since_name_used or 0
            if msgs_since_name >= 5:
                naturalidad_context += f"\n✓ PUEDES usar '{first_name}' (solo primer nombre, NO '{username}')"
            else:
                msgs_restantes = 5 - msgs_since_name
                naturalidad_context += f"\n⚠️ PROHIBIDO usar el nombre (faltan {msgs_restantes} mensajes)"

            # Evitar repetir emojis
            if follower.last_emojis_used:
                emojis_to_avoid = ", ".join(follower.last_emojis_used[-3:])
                naturalidad_context += f"\n⚠️ NO uses estos emojis (ya los usaste): {emojis_to_avoid}"

            # Evitar repetir estilo de saludo
            if follower.last_greeting_style:
                naturalidad_context += f"\n⚠️ NO empieces con '{follower.last_greeting_style}' (ya lo usaste)"

        prompt = f"""CONTEXTO:
- Usuario: {first_name} (usar SOLO este nombre, no el completo)
- Intent detectado: {intent.value}
{user_context}{history_text}
MENSAJE DEL USUARIO: "{message}"
{naturalidad_context}
"""

        # Control de links - no repetir demasiado
        include_link = True
        link_note = ""
        if follower:
            # Safe access to potentially None values
            total_msgs = follower.total_messages or 0
            last_link_num = follower.last_link_message_num or 0
            links_sent = follower.links_sent_count or 0
            messages_since_last_link = total_msgs - last_link_num
            # Solo incluir link si:
            # 1. Es la primera vez, O
            # 2. Han pasado 3+ mensajes desde el ultimo link, O
            # 3. El usuario pregunta explicitamente "como pago", "donde compro", etc.
            asking_for_link = any(kw in message.lower() for kw in ['pagar', 'compro', 'comprar', 'link', 'donde', 'how to pay', 'buy'])

            if links_sent > 0 and messages_since_last_link < 3 and not asking_for_link:
                include_link = False
                link_note = "\n⚠️ NOTA: Ya enviaste el link recientemente. NO lo repitas a menos que el usuario pregunte."

        # Añadir producto relevante
        if product:
            price = product.get('price') or 0
            price_text = f"{price}€" if price > 0 else "GRATIS"
            benefits = product.get('features', product.get('benefits', []))[:3]

            if include_link:
                prompt += f"""
PRODUCTO RELEVANTE PARA MENCIONAR:
- Nombre: {product.get('name')}
- Precio: {price_text}
- Link: {get_valid_payment_url(product)}
- Beneficios: {', '.join(benefits)}
"""
            else:
                prompt += f"""
PRODUCTO RELEVANTE (sin link, ya lo enviaste):
- Nombre: {product.get('name')}
- Precio: {price_text}
- Beneficios: {', '.join(benefits)}
{link_note}
"""

        # Control de argumentos - no repetir los mismos
        if follower and follower.objections_handled:
            prompt += f"\nOBJECIONES YA MANEJADAS (usa argumentos DIFERENTES): {', '.join(follower.objections_handled[-3:])}"
            if follower.arguments_used:
                prompt += f"\nARGUMENTOS YA USADOS (NO repitas estos): {', '.join(follower.arguments_used[-5:])}"

        # Añadir handler de objeción
        if objection_handler:
            prompt += f"""
USA ESTA RESPUESTA PARA LA OBJECION (adaptala a tu tono):
"{objection_handler}"
"""

        # Instrucciones según intent - con hints de personalización y CIERRE PROACTIVO
        instructions = {
            Intent.GREETING: "Saluda de forma cercana y VARIADA. Si ya conoces al usuario, pregunta sobre algo específico que discutieron. Si es nuevo, pregunta sobre SU situación/necesidad específica.",
            Intent.INTEREST_STRONG: "🔥 EL USUARIO QUIERE COMPRAR - CIERRA AHORA: (1) Confirma brevemente el valor, (2) Da el link de pago INMEDIATAMENTE, (3) Crea urgencia: '¿Te paso el acceso ahora?' NO sigas explicando beneficios - ¡CIERRA!",
            Intent.INTEREST_SOFT: "Hay interés. AVANZA hacia la venta: Responde su duda en 1 frase, luego pregunta '¿Te cuento más o prefieres que te pase el acceso directo?'. Siempre ofrece el siguiente paso.",
            Intent.ACKNOWLEDGMENT: "El usuario confirma. Si confirmó interés → OFRECE el siguiente paso hacia la compra. NO hagas preguntas abiertas genéricas.",
            Intent.CORRECTION: "El usuario corrige. Discúlpate brevemente y pregunta específicamente qué es lo que busca.",
            Intent.OBJECTION_PRICE: "Maneja precio CERRANDO: (1) Justifica el valor en 1 frase, (2) Ofrece garantía, (3) Pregunta '¿Empezamos?' o '¿Te paso el link?'. NO te quedes en la objeción.",
            Intent.OBJECTION_TIME: "Maneja tiempo: (1) Muestra flexibilidad en 1 frase, (2) Ofrece empezar: '¿Quieres que te pase el acceso y empiezas cuando puedas?'",
            Intent.OBJECTION_DOUBT: "Resuelve la duda en 1-2 frases cortas, luego CIERRA: '¿Te queda más claro? ¿Empezamos?'",
            Intent.OBJECTION_LATER: "Maneja 'luego' creando urgencia natural: 'El precio actual es por tiempo limitado. ¿Hay algo que te frene para empezar hoy?'",
            Intent.OBJECTION_WORKS: "Comparte 1 resultado específico, luego CIERRA: 'Y podrías tener resultados similares. ¿Empezamos?'",
            Intent.OBJECTION_NOT_FOR_ME: "Pregunta QUÉ lo hace pensar eso, escucha, y reconecta con valor específico para SU caso.",
            Intent.OBJECTION_COMPLICATED: "Simplifica en 1 frase, luego: 'Es más fácil de lo que parece. ¿Te paso el acceso y te guío?'",
            Intent.OBJECTION_ALREADY_HAVE: "Diferencia en 1 frase, pregunta resultados de lo que tiene, y muestra por qué esto es mejor.",
            Intent.QUESTION_PRODUCT: "Responde en 2 frases máximo, luego AVANZA: '¿Quieres que te pase el acceso?' o '¿Te cuento algo más?'",
            Intent.QUESTION_GENERAL: "Responde brevemente y conecta con el producto: 'Por cierto, esto lo enseño en detalle en el curso...'",
            Intent.LEAD_MAGNET: "Ofrece el recurso GRATIS e incluye CTA hacia el producto de pago.",
            Intent.THANKS: "Agradece brevemente y ofrece el siguiente paso: '¿Hay algo más en lo que pueda ayudarte o empezamos?'",
            Intent.GOODBYE: "Despídete, crea apertura futura: 'Si decides avanzar, aquí estoy. ¡Éxitos!'",
            Intent.SUPPORT: "Muestra empatía breve y resuelve. Si es sobre el producto, aprovecha para cerrar.",
            Intent.OTHER: "Responde de forma útil y siempre ofrece el siguiente paso hacia la conversión."
        }

        # High-intent boost - add conversion pressure when purchase intent is high
        conversion_boost = ""
        if follower:
            intent_score = follower.purchase_intent_score or 0
            if intent_score >= 0.7:
                conversion_boost = "\n\n🔥 ALERTA - LEAD MUY CALIENTE: Tiene {:.0%} de intención de compra. CIERRA LA VENTA AHORA. Ofrece el link de pago directamente.".format(intent_score)
            elif intent_score >= 0.4:
                conversion_boost = "\n\n⚡ LEAD CON INTERÉS: Tiene {:.0%} de intención. Avanza hacia el cierre - no hagas preguntas abiertas, ofrece el siguiente paso concreto.".format(intent_score)

        prompt += f"\nINSTRUCCION: {instructions.get(intent, instructions[Intent.OTHER])}{conversion_boost}"
        prompt += "\n\n⚠️ RECUERDA: Usa la INFORMACIÓN DEL USUARIO de arriba para personalizar. NO des respuestas genéricas. SIEMPRE ofrece el siguiente paso."

        return prompt

    def _build_language_instruction(self, language: str) -> str:
        """Construir instruccion de idioma para el prompt - MUY EXPLICITA"""
        if language == "es":
            return """

⚠️ IDIOMA OBLIGATORIO: ESPAÑOL
- Responde ÚNICAMENTE en ESPAÑOL
- NO uses palabras en inglés como "I", "don't", "you've", "they"
- Respuesta en español (máximo 2-3 frases):"""
        elif language == "en":
            return """

⚠️ MANDATORY LANGUAGE: ENGLISH
- Reply ONLY in ENGLISH
- Do NOT use Spanish words
- Response in English (max 2-3 sentences):"""
        elif language == "pt":
            return """

⚠️ IDIOMA OBRIGATÓRIO: PORTUGUÊS
- Responda SOMENTE em PORTUGUÊS
- NÃO use palavras em espanhol ou inglês
- Resposta em português (máximo 2-3 frases):"""
        else:
            return f"\n\nResponde en español (máximo 2-3 frases):"

    def _handle_direct_payment_question(self, message: str, other_payment_methods: dict, language: str = "es") -> Optional[str]:
        """Handle payment method questions directly without LLM.

        Returns a response string if the message is a specific payment method question,
        or None if the LLM should handle it.
        """
        if not other_payment_methods:
            return None

        msg_lower = message.lower()

        # Check for GENERIC payment questions first - "¿cómo pago?", "formas de pago", etc.
        generic_payment_triggers = [
            'cómo pago', 'como pago', 'cómo puedo pagar', 'como puedo pagar',
            'formas de pago', 'métodos de pago', 'metodos de pago',
            'qué opciones', 'que opciones', 'opciones de pago',
            'cómo te pago', 'como te pago', 'cómo lo pago', 'como lo pago',
            'manera de pagar', 'maneras de pagar', 'how do i pay', 'how can i pay',
            'quiero pagar', 'puedo pagar', 'para pagar'
        ]

        is_generic_payment_question = any(trigger in msg_lower for trigger in generic_payment_triggers)

        if is_generic_payment_question:
            # Build list of ALL available payment methods
            available_methods = []

            bizum = other_payment_methods.get('bizum', {})
            if isinstance(bizum, dict) and bizum.get('enabled') and bizum.get('phone'):
                available_methods.append(f"Bizum al {bizum['phone']}")

            bank = other_payment_methods.get('bank_transfer', {})
            if isinstance(bank, dict) and bank.get('enabled') and bank.get('iban'):
                holder = bank.get('holder_name', '')
                holder_text = f" ({holder})" if holder else ""
                available_methods.append(f"Transferencia a {bank['iban']}{holder_text}")

            revolut = other_payment_methods.get('revolut', {})
            if isinstance(revolut, dict) and revolut.get('enabled') and revolut.get('link'):
                available_methods.append(f"Revolut: {revolut['link']}")

            other = other_payment_methods.get('other', {})
            if isinstance(other, dict) and other.get('enabled') and other.get('instructions'):
                available_methods.append(f"PayPal: {other['instructions']}")

            # Also mention card payment if there are product payment links
            if self.products:
                has_payment_link = any(get_valid_payment_url(p) for p in self.products)
                if has_payment_link:
                    available_methods.append("Tarjeta (te paso el link)")

            if available_methods:
                methods_text = "\n- ".join(available_methods)
                logger.info(f"Direct payment response: Listing all methods -> {available_methods}")
                return f"¡Genial! Puedes pagar por:\n- {methods_text}\n\n¿Cuál prefieres? 😊"

        # Bizum
        if 'bizum' in msg_lower:
            bizum = other_payment_methods.get('bizum', {})
            if isinstance(bizum, dict) and bizum.get('enabled') and bizum.get('phone'):
                holder = bizum.get('holder_name', '')
                holder_text = f" a nombre de {holder}" if holder else ""
                logger.info(f"Direct payment response: Bizum -> {bizum['phone']}")
                return f"¡Sí! Envía el importe al {bizum['phone']}{holder_text}. Avísame cuando lo hagas 👍"

        # Transferencia / IBAN
        if 'transferencia' in msg_lower or 'iban' in msg_lower or 'cuenta' in msg_lower:
            bank = other_payment_methods.get('bank_transfer', {})
            if isinstance(bank, dict) and bank.get('enabled') and bank.get('iban'):
                holder = bank.get('holder_name', '')
                holder_text = f" (titular: {holder})" if holder else ""
                logger.info(f"Direct payment response: Bank Transfer -> {bank['iban']}")
                return f"¡Claro! Haz transferencia a IBAN {bank['iban']}{holder_text}. Avísame cuando lo hagas 👍"

        # Revolut / Wise
        if 'revolut' in msg_lower or 'wise' in msg_lower:
            revolut = other_payment_methods.get('revolut', {})
            if isinstance(revolut, dict) and revolut.get('enabled') and revolut.get('link'):
                logger.info(f"Direct payment response: Revolut -> {revolut['link']}")
                return f"¡Sí! Envía el pago a {revolut['link']} por Revolut. Avísame cuando lo hagas 👍"

        # PayPal
        if 'paypal' in msg_lower:
            other = other_payment_methods.get('other', {})
            if isinstance(other, dict) and other.get('enabled') and other.get('instructions'):
                logger.info(f"Direct payment response: PayPal -> {other['instructions']}")
                return f"¡Sí! Envía el pago a {other['instructions']} por PayPal. Avísame cuando lo hagas 👍"

        return None  # Not a specific payment question, use LLM

    async def process_dm(
        self,
        sender_id: str,
        message_text: str,
        message_id: str = "",
        username: str = "amigo",
        name: str = ""
    ) -> DMResponse:
        """Procesar DM y generar respuesta personalizada"""
        import time
        _process_start = time.time()

        logger.info(f"Processing DM from {sender_id}: {message_text}")

        # Verificar si el bot esta activo (PostgreSQL primero, luego JSON config)
        bot_is_active = True  # Default to active
        if USE_POSTGRES and db_service:
            try:
                creator = db_service.get_creator_by_name(self.creator_id)
                if creator:
                    bot_is_active = creator.get("bot_active", True)
                    logger.debug(f"Bot status from PostgreSQL: {bot_is_active}")
            except Exception as e:
                logger.warning(f"Failed to get bot status from PostgreSQL: {e}")
                # Fallback to config manager
                bot_is_active = self.config_manager.is_bot_active(self.creator_id)
        else:
            bot_is_active = self.config_manager.is_bot_active(self.creator_id)

        if not bot_is_active:
            logger.info(f"Bot paused for creator {self.creator_id}")
            return DMResponse(
                response_text="",  # No enviar respuesta cuando esta pausado
                intent=Intent.OTHER,
                action_taken="bot_paused",
                confidence=1.0,
                metadata={"status": "paused", "message": "Bot pausado por el creador"}
            )

        # Products cached in __init__ with 5-minute TTL
        logger.info(f"Using {len(self.products)} cached products")

        # Rate limiting para prevenir abuse y controlar costes
        rate_limiter = get_rate_limiter()
        rate_key = f"{self.creator_id}:{sender_id}"
        allowed, reason = rate_limiter.check_limit(rate_key)
        if not allowed:
            logger.warning(f"Rate limited: {rate_key} - {reason}")
            # Check dialect for voseo
            dialect = get_tone_dialect(self.creator_id)
            if dialect == "rioplatense":
                rate_msg = "Dame un momento, estoy procesando varios mensajes. Te respondo enseguida!"
            else:
                rate_msg = "Dame un momento, estoy procesando varios mensajes. Te respondo enseguida!"
            return DMResponse(
                response_text=rate_msg,
                intent=Intent.OTHER,
                action_taken="rate_limited",
                confidence=1.0,
                metadata={"rate_limit_reason": reason}
            )

        # Obtener/crear memoria del seguidor (with name/username if available)
        _t_mem = time.time()
        follower = await self.memory_store.get_or_create(
            self.creator_id,
            sender_id,
            name=name,
            username=username if username != "amigo" else ""
        )
        logger.info(f"⏱️ memory_store.get_or_create took {time.time() - _t_mem:.2f}s")

        # =============================================================================
        # PERSONALIZATION: User Profile + Semantic Memory (Memory Engine Migration)
        # =============================================================================
        user_profile = None
        semantic_memory = None
        semantic_context = ""
        try:
            user_profile = get_user_profile(sender_id, self.creator_id)
            if ENABLE_SEMANTIC_MEMORY:
                semantic_memory = get_conversation_memory(sender_id, self.creator_id)
                semantic_context = semantic_memory.get_context_for_query(message_text, recent_n=3, semantic_k=2)
                if semantic_context:
                    logger.debug(f"Semantic memory context retrieved ({len(semantic_context)} chars)")
        except Exception as e:
            logger.warning(f"Personalization modules failed to load: {e}")

        # Extraer nombre del mensaje si el usuario se presenta
        # Patrones: "soy [nombre]", "me llamo [nombre]", "I'm [name]", etc.
        extracted_name = extract_name_from_message(message_text)
        if extracted_name:
            # SIEMPRE actualizar cuando el usuario dice explícitamente su nombre
            # Esto sobreescribe el nombre de Telegram/Instagram
            old_name = follower.name
            follower.name = extracted_name
            logger.info(f"Name extracted from message: '{extracted_name}' (was: '{old_name}')")
            # Guardar inmediatamente en memoria
            await self.memory_store.save(follower)

        # Verificar consentimiento GDPR (si esta habilitado)
        if REQUIRE_CONSENT:
            consent_response = await self._check_gdpr_consent(sender_id, message_text, follower)
            if consent_response:
                return consent_response

        # Detectar idioma del mensaje usando detección ROBUSTA
        # Solo cambia el idioma si hay evidencia fuerte (3+ keywords)
        total_msgs = follower.total_messages or 0
        current_lang = follower.preferred_language if total_msgs > 0 else None
        detected_lang = detect_language_robust(message_text, current_lang)

        # Actualizar idioma preferido solo si:
        # 1. Es el primer mensaje, O
        # 2. La detección robusta cambió el idioma (evidencia fuerte)
        if total_msgs == 0:
            follower.preferred_language = detected_lang
            logger.info(f"Language set on first message: {detected_lang}")
        elif detected_lang != follower.preferred_language:
            # detect_language_robust ya verifica evidencia fuerte
            old_lang = follower.preferred_language
            follower.preferred_language = detected_lang
            logger.info(f"Language changed from {old_lang} to {detected_lang} (strong evidence)")

        # === META-MESSAGE DETECTION ===
        # Detectar cuando el usuario hace referencia a la conversación misma
        # ("ya te lo dije", "revisa el chat", "no me entiendes")
        meta_result = self._detect_meta_message(message_text, follower.last_messages or [])

        if meta_result:
            action = meta_result.get("action")
            context = meta_result.get("context", "")
            instruction = meta_result.get("instruction", "")

            logger.info(f"Meta-message detected: {action} - {instruction[:50]}...")

            if action == "USER_FRUSTRATED":
                # Respuesta de recuperación empática
                response_text = "Perdona si no te he entendido bien. Cuéntame de nuevo qué necesitas y te ayudo ahora mismo."
                await self._update_memory(follower, message_text, response_text, Intent.OTHER)
                return DMResponse(
                    response_text=response_text,
                    intent=Intent.OTHER,
                    confidence=0.95,
                    metadata={"meta_action": "frustrated_recovery"}
                )

            elif action == "REVIEW_HISTORY":
                # Inyectar contexto en el mensaje para que el LLM lo vea
                # El LLM verá esto como parte del mensaje y responderá apropiadamente
                message_text = f"[CONTEXTO: El usuario me pide que recuerde que antes dijo: '{context[:150]}']\n\nUsuario: {message_text}"
                logger.info(f"Injected review context into message")

            elif action == "REPEAT_REQUESTED":
                # Inyectar contexto de repetición
                message_text = f"[CONTEXTO: El usuario pide que repita. Mi último mensaje fue: '{context[:150]}']\n\nUsuario: {message_text}"
                logger.info(f"Injected repeat context into message")

            elif action == "IMPLICIT_REFERENCE":
                # Inyectar contexto de referencia implícita
                message_text = f"[CONTEXTO PREVIO: El usuario mencionó antes: '{context[:150]}'. Su mensaje actual hace referencia a eso.]\n\nUsuario: {message_text}"
                logger.info(f"Injected implicit reference context")

            elif action == "SARCASM_DETECTED":
                # Respuesta empática para sarcasmo
                response_text = "Entiendo que estás frustrado. Perdona si no te he ayudado bien. ¿Qué puedo hacer para ayudarte de verdad?"
                await self._update_memory(follower, message_text, response_text, Intent.OTHER)
                return DMResponse(
                    response_text=response_text,
                    intent=Intent.OTHER,
                    confidence=0.90,
                    metadata={"meta_action": "sarcasm_recovery"}
                )

        # Clasificar intent con contexto conversacional
        _t_intent = time.time()
        intent, confidence = self._classify_intent(message_text, follower.last_messages)
        logger.info(f"⏱️ _classify_intent took {time.time() - _t_intent:.2f}s")
        logger.info(f"Intent: {intent.value} ({confidence:.0%})")

        # Verificar escalación
        if intent == Intent.ESCALATION:
            response_text = self._get_escalation_response()
            await self._update_memory(follower, message_text, response_text, intent)

            # Registrar escalacion en metricas
            record_escalation(self.creator_id, reason="user_requested")

            # Notificar al creador de la escalación
            try:
                notification_service = get_notification_service()
                escalation = EscalationNotification(
                    creator_id=self.creator_id,
                    follower_id=sender_id,
                    follower_username=username,
                    follower_name=follower.name or username,
                    reason="Usuario solicita hablar con humano",
                    last_message=message_text,
                    conversation_summary=f"Último tema: {follower.products_discussed[-1] if follower.products_discussed else 'General'}",
                    purchase_intent_score=follower.purchase_intent_score,
                    total_messages=follower.total_messages,
                    products_discussed=follower.products_discussed
                )
                await notification_service.notify_escalation(escalation)
                logger.info(f"Escalation notification sent for {sender_id}")
            except Exception as e:
                logger.error(f"Failed to send escalation notification: {e}")

            return DMResponse(
                response_text=response_text,
                intent=intent,
                action_taken="escalate",
                escalate_to_human=True,
                confidence=confidence
            )

        # Verificar si quiere agendar una llamada
        if intent == Intent.BOOKING:
            booking_links = self._load_booking_links()
            user_language = follower.preferred_language or "es"

            # Detect platform from sender_id
            platform = "telegram" if sender_id.startswith("tg_") else "instagram"

            # Get formatted response (returns dict with 'text' and optionally 'telegram_keyboard')
            booking_response = self._format_booking_response(booking_links, user_language, platform)
            response_text = booking_response.get("text", "")

            await self._update_memory(follower, message_text, response_text, intent)

            logger.info(f"Booking intent detected - found {len(booking_links)} links (platform: {platform})")

            # Include telegram keyboard in metadata if present
            metadata = {}
            if "telegram_keyboard" in booking_response:
                metadata["telegram_keyboard"] = booking_response["telegram_keyboard"]

            return DMResponse(
                response_text=response_text,
                intent=intent,
                action_taken="show_booking_links",
                confidence=confidence,
                metadata=metadata
            )

        # === ACKNOWLEDGMENT: Ahora pasa por flujo normal con LLM ===
        # ANTES: Fast path con respuesta hardcoded "¿En qué más puedo ayudarte?"
        # AHORA: El LLM verá el historial y responderá según el contexto
        # Ejemplo: "Si" después de "¿quieres saber más?" → el LLM explicará el producto
        if intent == Intent.ACKNOWLEDGMENT:
            logger.info(f"=== ACKNOWLEDGMENT - procesando con contexto conversacional ===")
            # NO retornar aquí - continuar al flujo normal del LLM

        # === CORRECTION: Ahora pasa por flujo normal con LLM ===
        # ANTES: Fast path con respuesta hardcoded "Disculpa la confusión!"
        # AHORA: El LLM verá el historial y responderá según el contexto
        # Ejemplo: "ya te lo dije" → el LLM buscará en el historial qué dijo
        if intent == Intent.CORRECTION:
            logger.info(f"=== CORRECTION - procesando con contexto conversacional ===")
            # NO retornar aquí - continuar al flujo normal del LLM

        # Buscar producto relevante
        product = self._get_relevant_product(message_text, intent)
        if product:
            logger.info(f"Relevant product: {product.get('name')}, payment_link={get_valid_payment_url(product) or 'NONE'}")
            if product.get('id') and product.get('id') not in follower.products_discussed:
                follower.products_discussed.append(product.get('id'))

        # === FAST PATH: Pregunta específica de método de pago ===
        # Bypass LLM when user asks specifically about Bizum, Transferencia, Revolut, PayPal
        # Use cached config (5-minute TTL)
        other_payment_methods = self.creator_config.get('other_payment_methods', {})
        logger.info(f"Payment methods for direct handler: {list(other_payment_methods.keys()) if other_payment_methods else 'None'}")
        direct_payment_response = self._handle_direct_payment_question(
            message_text, other_payment_methods, follower.preferred_language
        )
        if direct_payment_response:
            logger.info(f"=== DIRECT PAYMENT RESPONSE (NO LLM) ===")
            logger.info(f"Message: {message_text}")
            logger.info(f"Response: {direct_payment_response}")

            # Update lead status - high purchase intent
            follower.purchase_intent_score = max(follower.purchase_intent_score or 0.0, 0.85)
            follower.is_lead = True

            await self._update_memory(follower, message_text, direct_payment_response, Intent.INTEREST_STRONG)

            return DMResponse(
                response_text=direct_payment_response,
                intent=Intent.INTEREST_STRONG,
                action_taken="direct_payment_method",
                confidence=1.0,
                metadata={
                    "direct_payment": True,
                    "method_type": "alternative",
                    "purchase_intent_score": follower.purchase_intent_score
                }
            )

        # === FAST PATH: Pregunta de precio específica ===
        # Cuando usuario pregunta "cuánto cuesta X" y tenemos el producto, responder directamente
        if intent == Intent.QUESTION_PRODUCT and product:
            msg_lower = message_text.lower()
            price_keywords = ['cuanto cuesta', 'cuánto cuesta', 'precio', 'cuanto vale', 'cuánto vale',
                              'que cuesta', 'qué cuesta', 'cuanto es', 'cuánto es', 'cual es el precio',
                              'cuál es el precio', 'cuanto sale', 'cuánto sale']
            is_price_question = any(kw in msg_lower for kw in price_keywords)

            if is_price_question:
                logger.info(f"=== FAST PATH: Price question for {product.get('name')} ===")
                price = product.get('price') or 0
                product_name = product.get('name', 'el servicio')
                description = product.get('description', '')[:100]

                if price > 0:
                    price_response = f"¡{product_name} tiene un precio de {int(price)}€! 🎯"
                    if description:
                        price_response += f" {description}"
                else:
                    price_response = f"¡{product_name} es GRATIS! 🎉"
                    if description:
                        price_response += f" {description}"

                await self._update_memory(follower, message_text, price_response, intent)

                return DMResponse(
                    response_text=price_response,
                    intent=intent,
                    action_taken="direct_price_response",
                    product_mentioned=product_name,
                    confidence=1.0,
                    metadata={
                        "fast_path": True,
                        "product_price": price,
                        "product_id": product.get('id')
                    }
                )

        # === FAST PATH: Compra directa ===
        # Cuando usuario QUIERE COMPRAR, solo dar el link - NO volver a vender
        if is_direct_purchase_intent(message_text):
            logger.info(f"=== DIRECT PURCHASE INTENT DETECTED ===")
            logger.info(f"Message: {message_text}")
            logger.info(f"All products: {[(p.get('name'), get_valid_payment_url(p) or 'NONE') for p in self.products]}")

            # Try to find a product with a payment link
            product_url = ""
            product_name = "el producto"

            # Helper to check if link is valid (not placeholder)
            def is_valid_link(link: str) -> bool:
                if not link:
                    return False
                if link.startswith('PENDIENTE'):
                    return False
                if not link.startswith('http'):
                    return False
                return True

            # First try the relevant product
            if product:
                potential_url = get_valid_payment_url(product)
                if is_valid_link(potential_url):
                    product_url = potential_url
                product_name = product.get('name', 'el producto')

            # If no link, try to find ANY product with a payment link
            if not product_url:
                for p in self.products:
                    link = get_valid_payment_url(p)
                    if is_valid_link(link):
                        product_url = link
                        product_name = p.get('name', 'el producto')
                        logger.info(f"Found fallback payment link from product: {product_name}")
                        break

            logger.info(f"DIRECT PURCHASE: product={product_name}, payment_link={product_url}")

            # Subir purchase_intent a 85%+ inmediatamente
            follower.purchase_intent_score = max(follower.purchase_intent_score or 0.0, 0.85)
            follower.is_lead = True

            logger.info(f"DIRECT PURCHASE detected - giving link only, score set to {follower.purchase_intent_score}")

            # Elegir emoji basado en idioma
            emoji = "🚀" if follower.preferred_language == "es" else "🎉"

            # Respuesta CORTA - solo el link (si hay link)
            if product_url:
                if follower.preferred_language == "es":
                    response_text = f"¡Perfecto! {emoji} Aquí tienes: {product_url}"
                else:
                    response_text = f"Perfect! {emoji} Here you go: {product_url}"
            else:
                # No hay link configurado - TRY ALTERNATIVE PAYMENT METHODS FIRST
                logger.warning(f"NO PAYMENT LINK FOUND for any product! Checking alternative methods...")

                # Build list of available alternative payment methods
                available_methods = []

                bizum = other_payment_methods.get('bizum', {})
                if isinstance(bizum, dict) and bizum.get('enabled') and bizum.get('phone'):
                    available_methods.append(f"Bizum al {bizum['phone']}")

                bank = other_payment_methods.get('bank_transfer', {})
                if isinstance(bank, dict) and bank.get('enabled') and bank.get('iban'):
                    holder = bank.get('holder_name', '')
                    holder_text = f" ({holder})" if holder else ""
                    available_methods.append(f"Transferencia a {bank['iban']}{holder_text}")

                revolut = other_payment_methods.get('revolut', {})
                if isinstance(revolut, dict) and revolut.get('enabled') and revolut.get('link'):
                    available_methods.append(f"Revolut: {revolut['link']}")

                other = other_payment_methods.get('other', {})
                if isinstance(other, dict) and other.get('enabled') and other.get('instructions'):
                    available_methods.append(f"PayPal: {other['instructions']}")

                if available_methods:
                    # Show alternative payment methods
                    methods_text = "\n- ".join(available_methods)
                    logger.info(f"Found alternative payment methods: {available_methods}")
                    if follower.preferred_language == "es":
                        # Check dialect for voseo
                        dialect = get_tone_dialect(self.creator_id)
                        if dialect == "rioplatense":
                            response_text = f"¡Genial! {emoji} Podés pagar por:\n- {methods_text}\n\n¿Cuál preferís?"
                        else:
                            response_text = f"¡Genial! {emoji} Puedes pagar por:\n- {methods_text}\n\n¿Cuál prefieres?"
                    else:
                        response_text = f"Great! {emoji} You can pay via:\n- {methods_text}\n\nWhich do you prefer?"
                else:
                    # No alternative methods either - natural response asking to continue DM
                    logger.warning(f"NO ALTERNATIVE PAYMENT METHODS FOUND either - using natural DM response")
                    if follower.preferred_language == "es":
                        # Check dialect for voseo
                        dialect = get_tone_dialect(self.creator_id)
                        if dialect == "rioplatense":
                            response_text = f"¡Genial que te interese! {emoji} Para pagos y reservas, escribime por acá y te paso los datos. ¿Qué producto te interesa?"
                        else:
                            response_text = f"¡Genial que te interese! {emoji} Para pagos y reservas, escríbeme por aquí y te paso los datos. ¿Qué producto te interesa?"
                    else:
                        response_text = f"Great that you're interested! {emoji} For payments and bookings, just message me here and I'll send you the details. Which product interests you?"

            # Guardar en historial
            follower.last_messages.append({
                "role": "user",
                "content": message_text,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            follower.last_messages.append({
                "role": "assistant",
                "content": response_text,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            follower.total_messages += 1
            follower.last_contact = datetime.now(timezone.utc).isoformat()

            # Limitar historial
            if len(follower.last_messages) > 20:
                follower.last_messages = follower.last_messages[-20:]

            await self.memory_store.save(follower)
            # Save BOTH messages to PostgreSQL (fire-and-forget - don't block response)
            self._save_message_to_db_fire_and_forget(follower.follower_id, 'user', message_text, str(intent))
            self._save_message_to_db_fire_and_forget(follower.follower_id, 'assistant', response_text, None)

            # Track product link click
            try:
                sales_tracker = get_sales_tracker()
                sales_tracker.record_click(
                    creator_id=self.creator_id,
                    product_id=product.get('id', ''),
                    follower_id=follower.follower_id,
                    product_name=product_name,
                    link_url=product_url
                )
            except Exception as e:
                logger.warning(f"Failed to track click: {e}")

            return DMResponse(
                response_text=response_text,
                intent=intent,
                action_taken="direct_purchase_link",
                product_mentioned=product_name,
                confidence=0.95,
                metadata={
                    "direct_purchase": True,
                    "product_url": product_url,
                    "purchase_intent_score": follower.purchase_intent_score
                }
            )

        # =============================================================================
        # ANTI-ALUCINACIÓN: Verificar si el intent requiere contenido RAG
        # Si requiere RAG y no hay contenido relevante → Escalar al creador
        # =============================================================================
        if intent in INTENTS_REQUIRING_RAG:
            from core.citation_service import get_citation_prompt_section

            # Buscar contenido relevante en RAG
            citation_section = get_citation_prompt_section(self.creator_id, message_text, min_relevance=0.25)

            if not citation_section:
                # NO hay contenido relevante en RAG → Escalar al creador
                logger.warning(f"[ANTI-HALLUCINATION] Intent {intent.value} requires RAG but NO content found. Escalating.")

                # Obtener nombre del creador para el mensaje
                creator_name = self.creator_config.get('clone_name') or self.creator_config.get('name', 'el creador')

                # Mensaje de escalado personalizado
                dialect = get_tone_dialect(self.creator_id)
                if dialect == "rioplatense":
                    escalation_response = f"Me encantaría ayudarte con eso 🙌 Te paso con {creator_name} directamente para que pueda darte toda la info que necesitás. ¡Te escribe pronto!"
                else:
                    escalation_response = f"Me encantaría ayudarte con eso 🙌 Te paso con {creator_name} directamente para que pueda darte toda la info que necesitas. ¡Te escribe pronto!"

                # Actualizar memoria con la escalación
                await self._update_memory(follower, message_text, escalation_response, intent)

                # Marcar lead como needs_human en PostgreSQL
                try:
                    if USE_POSTGRES and db_service:
                        db_service.update_lead(
                            creator_name=self.creator_id,
                            lead_id=sender_id,  # platform_user_id
                            data={"status": "needs_human"}
                        )
                        logger.info(f"[ANTI-HALLUCINATION] Lead {sender_id} marked as needs_human")
                except Exception as e:
                    logger.warning(f"[ANTI-HALLUCINATION] Failed to update lead status: {e}")

                # Registrar escalación en métricas
                record_escalation(self.creator_id, reason="no_rag_content")

                return DMResponse(
                    response_text=escalation_response,
                    intent=intent,
                    action_taken="escalate_no_rag",
                    escalate_to_human=True,
                    confidence=0.95,
                    metadata={
                        "anti_hallucination": True,
                        "reason": "no_relevant_rag_content",
                        "original_intent": intent.value
                    }
                )
            else:
                logger.info(f"[ANTI-HALLUCINATION] Intent {intent.value} - RAG content found, proceeding with LLM")

        # Obtener handler de objeción
        objection_handler = self._get_objection_handler(intent, product)

        # Usar el nombre guardado del follower si existe, sino el username del mensaje
        display_name = follower.name or username

        # Construir prompts (pass message for citation lookup)
        import time
        _t0 = time.time()
        system_prompt = self._build_system_prompt(message=message_text)
        logger.info(f"⏱️ _build_system_prompt took {time.time() - _t0:.2f}s")

        # =============================================================================
        # PERSONALIZATION: Adapt system prompt based on user profile
        # =============================================================================
        if user_profile:
            try:
                system_prompt = adapt_system_prompt(system_prompt, user_profile)
                logger.debug("System prompt personalized based on user profile")
            except Exception as e:
                logger.warning(f"Failed to personalize system prompt: {e}")

        # Add semantic memory context if available
        if semantic_context:
            system_prompt += f"\n\n{semantic_context}"
            logger.debug("Added semantic memory context to prompt")
        _t1 = time.time()
        user_prompt = self._build_user_prompt(
            message=message_text,
            intent=intent,
            username=display_name,  # Usar nombre guardado del follower
            product=product,
            objection_handler=objection_handler,
            conversation_history=follower.last_messages,
            follower=follower  # Para control de links y objeciones
        )

        logger.info(f"⏱️ _build_user_prompt took {time.time() - _t1:.2f}s")

        # Agregar instruccion de idioma al prompt
        # PRIORIDAD: ToneProfile.primary_language > follower.preferred_language
        # Esto asegura que el bot responde en el idioma del creador, no del usuario
        tone_language = get_tone_language(self.creator_id)
        if tone_language:
            user_language = tone_language
            logger.info(f"Using ToneProfile language: {tone_language} (overrides follower preferred: {follower.preferred_language})")
        else:
            user_language = follower.preferred_language
        user_prompt += self._build_language_instruction(user_language)

        # Check cache para respuestas frecuentes (solo intents cacheables)
        response_cache = get_response_cache()
        # Include clone_tone and clone_vocabulary hash in cache key so config changes invalidate cache
        clone_tone = self.creator_config.get('clone_tone', 'friendly')
        clone_vocabulary = self.creator_config.get('clone_vocabulary', '')
        # Use hash of vocabulary to avoid long cache keys
        vocab_hash = hash(clone_vocabulary) if clone_vocabulary else 0
        cache_key_params = {
            "creator_id": self.creator_id,
            "intent": intent.value,
            "language": user_language,
            "tone": clone_tone,
            "vocab": vocab_hash
        }

        # Solo cachear intents que lo permiten
        is_cacheable = intent not in NON_CACHEABLE_INTENTS
        cached_response = None

        # Response cache enabled for faster responses
        bypass_cache = False

        if is_cacheable and not bypass_cache:
            # Normalizar mensaje para cache (sin puntuacion, minusculas)
            normalized_msg = message_text.lower().strip()
            cached_response = response_cache.get(normalized_msg, **cache_key_params)

            if cached_response:
                logger.info(f"Cache HIT for intent {intent.value}: {cached_response[:50]}")
                response_text = cached_response
                record_cache_hit(self.creator_id)
            else:
                logger.debug(f"Cache MISS for intent {intent.value}")
                record_cache_miss(self.creator_id)
        else:
            logger.info(f"Cache BYPASSED for debugging")

        # Generar respuesta con LLM solo si no hay cache
        if not cached_response:
            try:
                # === CHAIN OF THOUGHT FOR COMPLEX QUERIES ===
                # Use CoT reasoning for complex/health-related queries
                cot_used = False
                try:
                    cot_reasoner = get_chain_of_thought_reasoner(self.llm)
                    if cot_reasoner.is_complex_query(message_text):
                        logger.info("Using Chain of Thought for complex query")
                        cot_context = {
                            "creator_name": self.creator_config.get("name", "el creador"),
                            "products": self.products
                        }
                        cot_result = await cot_reasoner.generate(message_text, cot_context)

                        if cot_result.is_complex and cot_result.answer:
                            response_text = cot_result.answer
                            cot_used = True
                            logger.info(f"CoT response: type={cot_result.query_type}, steps={len(cot_result.reasoning_steps)}")
                except Exception as cot_error:
                    logger.warning(f"Chain of Thought failed: {cot_error}")

                # Standard LLM response if CoT not used
                if not cot_used:
                    # === FIX NO_REPETIR: Extraer info conocida del usuario ===
                    known_info = self._extract_known_info(follower.last_messages or [])
                    if known_info:
                        known_section = "\n=== INFORMACIÓN YA CONOCIDA DEL USUARIO ===\n"
                        known_section += "\n".join(f"• {info}" for info in known_info)
                        known_section += "\n\n⚠️ NO preguntes nada de lo anterior, ya lo sabes.\n"
                        system_prompt += known_section
                        logger.info(f"Added known info to prompt: {known_info}")

                    # === FIX COHERENCIA: Extraer tema de conversación ===
                    topic = self._extract_conversation_topic(follower.last_messages or [])
                    if topic:
                        topic_section = f"\n=== TEMA ACTUAL DE LA CONVERSACIÓN ===\n"
                        topic_section += f"Estamos hablando de: {topic.upper()}\n"
                        topic_section += f"⚠️ MANTÉN el foco en este tema. No cambies de tema sin razón.\n"
                        system_prompt += topic_section
                        logger.info(f"Conversation topic detected: {topic}")

                    # === FIX CONVERSIÓN: Auto-CTA después de varios mensajes ===
                    total_msgs = follower.total_messages or 0
                    if total_msgs > 0 and total_msgs % 4 == 0:
                        cta_section = "\n=== MOMENTO DE AVANZAR ===\n"
                        cta_section += "Llevamos varios mensajes. Propón una ACCIÓN CONCRETA:\n"
                        cta_section += "- Si hay interés: ofrece el link de pago o agendar llamada\n"
                        cta_section += "- Si hay dudas: resuelve la duda más importante\n"
                        cta_section += "⚠️ NO hagas otra pregunta abierta. PROPÓN algo concreto.\n"
                        system_prompt += cta_section
                        logger.info(f"Added auto-CTA prompt (message #{total_msgs})")

                    # === CONVERSION OPTIMIZATION: Inject dynamic prompts ===
                    # Always add base conversion optimization
                    system_prompt += NO_REPETITION_INSTRUCTION
                    system_prompt += COHERENCE_INSTRUCTION
                    system_prompt += CONVERSION_INSTRUCTION

                    # Proactive close for high-intent users
                    purchase_score = follower.purchase_intent_score or 0.0
                    has_strong_interest_keywords = any(kw in message_text.lower() for kw in STRONG_INTEREST_KEYWORDS)
                    high_intent_intents = {Intent.INTEREST_STRONG, Intent.INTEREST_SOFT, Intent.QUESTION_PRODUCT}

                    if purchase_score >= 0.70 or intent in high_intent_intents or has_strong_interest_keywords:
                        system_prompt += PROACTIVE_CLOSE_INSTRUCTION
                        logger.info(f"Added PROACTIVE_CLOSE (score={purchase_score:.0%}, intent={intent.value}, keywords={has_strong_interest_keywords})")

                    logger.info(f"Conversion optimization injected: NO_REPEAT + COHERENCE + CONVERSION" +
                               (f" + PROACTIVE_CLOSE" if purchase_score >= 0.70 or intent in high_intent_intents or has_strong_interest_keywords else ""))

                    # === MULTI-TURN: Construir conversación real ===
                    # ANTES: Solo system + user_prompt (historial como texto)
                    # AHORA: system + historial como mensajes reales + mensaje actual
                    messages = [{"role": "system", "content": system_prompt}]

                    # Añadir historial como mensajes reales (últimos 10 = 5 intercambios para mejor coherencia)
                    if follower.last_messages:
                        for msg in follower.last_messages[-10:]:
                            role = msg.get("role", "user")
                            content = msg.get("content", "")
                            if content and role in ("user", "assistant"):
                                messages.append({"role": role, "content": content})

                    # Mensaje actual del usuario (si no está ya en el historial)
                    if not follower.last_messages or follower.last_messages[-1].get("content") != message_text:
                        messages.append({"role": "user", "content": message_text})

                    logger.info(f"Multi-turn LLM call: {len(messages)} messages ({len(messages)-1} history + system)")
                    logger.info(f"=== DEBUG: Calling LLM ===")
                    logger.info(f"Message: {message_text[:100]}")
                    logger.info(f"Intent: {intent.value} ({confidence:.2f})")
                    logger.info(f"Products loaded: {len(self.products)}")

                    _t_llm = time.time()
                    response_text = await self.llm.chat(
                        messages,
                        max_tokens=80,  # CORTO - 1-2 frases máximo
                        temperature=0.8  # Más natural, menos robótico
                    )
                    response_text = response_text.strip()
                    logger.info(f"⏱️ LLM call took {time.time() - _t_llm:.2f}s")
                    logger.info(f"LLM Response: {response_text[:150] if response_text else 'EMPTY'}")

                # Validate response with guardrails
                try:
                    guardrail = get_response_guardrail()
                    product_prices = [p.get("price") for p in self.products if p.get("price")]
                    logger.debug(f"Guardrail context: {len(self.products)} products, prices: {product_prices}")
                    guardrail_context = {
                        "products": self.products,
                        "allowed_urls": [p.get("payment_link", "") for p in self.products if p.get("payment_link")],
                        "creator_config": self.creator_config,
                        "language": user_language
                    }
                    response_text = guardrail.get_safe_response(
                        query=message_text,
                        response=response_text,
                        context=guardrail_context
                    )
                except Exception as ge:
                    logger.warning(f"Guardrail check failed: {ge}")

                # === POST-PROCESSING: BREVEDAD Y LINKS ===
                # 1. Truncar a máximo 2 frases (AGRESIVO - el LLM ignora instrucciones)
                response_text = truncate_response(response_text, max_sentences=2)

                # 2. Reemplazar placeholders de links con links reales
                payment_links = [get_valid_payment_url(p) for p in self.products]
                response_text = clean_response_placeholders(response_text, payment_links)

                # 3. EXTRA AGRESIVO: Si es respuesta de pago alternativo, solo primera frase + CTA
                response_text = truncate_payment_response(response_text)

                # === SELF-CONSISTENCY CHECK ===
                # Validate response confidence before sending
                # If confidence < 0.6 -> use safe fallback response
                # SKIP for most intents - only validate objections and escalations
                intents_needing_validation = {
                    Intent.ESCALATION,
                    # Intent.SUPPORT removido - preguntas generales no necesitan validación extra
                    # El self-consistency penaliza respuestas válidas pero textuamente diferentes
                }
                # Skip consistency for most intents (trust the LLM with good prompt)
                skip_consistency = intent not in intents_needing_validation

                if skip_consistency:
                    logger.info(f"Skipping self-consistency for simple intent {intent.value} (confidence={confidence:.2f})")
                else:
                    try:
                        consistency_validator = get_self_consistency_validator(self.llm)
                        consistency_result = await consistency_validator.validate_response(
                            query=message_text,
                            response=response_text,
                            system_prompt=system_prompt,
                            max_tokens=200
                        )

                        # Log confidence for monitoring
                        logger.info(
                            f"Self-consistency: confidence={consistency_result.confidence:.2f}, "
                            f"consistent={consistency_result.is_consistent}"
                        )

                        if not consistency_result.is_consistent:
                            # Low confidence -> safe fallback
                            creator_name = self.creator_config.get('clone_name') or self.creator_config.get('name', 'el creador')
                            if user_language == "es":
                                # Check dialect for voseo
                                dialect = get_tone_dialect(self.creator_id)
                                if dialect == "rioplatense":
                                    response_text = f"Dejame confirmarlo con {creator_name} y te respondo enseguida."
                                else:
                                    response_text = f"Déjame confirmarlo con {creator_name} y te respondo enseguida."
                            elif user_language == "en":
                                response_text = f"Let me confirm this with {creator_name} and I'll get back to you shortly."
                            elif user_language == "pt":
                                response_text = f"Deixe-me confirmar isso com {creator_name} e já te respondo."
                            else:
                                response_text = f"Déjame confirmarlo con {creator_name} y te respondo enseguida."

                            logger.info(f"Low confidence ({consistency_result.confidence:.2f}) - using safe fallback")

                            # Record for analytics (optional: track escalations due to low confidence)
                            try:
                                record_escalation(self.creator_id, reason="low_confidence")
                            except Exception:
                                pass
                        else:
                            # Use validated response (may be refined by consistency check)
                            response_text = consistency_result.response

                    except Exception as sc_error:
                        logger.warning(f"Self-consistency check failed: {sc_error}")
                        # Continue with original response on error

                # Si el idioma no es espanol y la respuesta parece en espanol, traducir
                if user_language != DEFAULT_LANGUAGE:
                    # Verificar si necesitamos traducir (el LLM a veces ignora la instruccion)
                    response_lang = detect_language(response_text)
                    if response_lang != user_language:
                        logger.info(f"Translating response from {response_lang} to {user_language}")
                        response_text = await translate_response(
                            response_text,
                            user_language,
                            response_lang,
                            self.llm
                        )

                # Cachear respuesta si es cacheable
                if is_cacheable and response_text:
                    normalized_msg = message_text.lower().strip()
                    response_cache.set(normalized_msg, response_text, **cache_key_params)
                    logger.debug(f"Cached response for intent {intent.value}")

            except Exception as e:
                import traceback
                logger.error(f"=== ERROR generating response ===")
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Error message: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                response_text = self._get_fallback_response(intent)
                logger.info(f"Using fallback response: {response_text[:100]}")

                # Registrar error en metricas
                provider = os.getenv("LLM_PROVIDER", "unknown")
                record_llm_error(
                    creator_id=self.creator_id,
                    provider=provider,
                    error_type=type(e).__name__
                )

                # Enviar alerta de error LLM
                try:
                    alert_manager = get_alert_manager()
                    await alert_manager.alert_llm_error(
                        error=str(e),
                        creator_id=self.creator_id,
                        provider=provider
                    )
                except Exception as alert_error:
                    logger.debug(f"Could not send alert: {alert_error}")

        # Actualizar memoria
        await self._update_memory(follower, message_text, response_text, intent)

        # =============================================================================
        # PERSONALIZATION: Update user profile and semantic memory
        # =============================================================================
        try:
            if user_profile:
                user_profile.record_interaction()
                # Auto-detect interests from message (simple keyword matching)
                interest_keywords = {
                    "fitness": ["fitness", "ejercicio", "gym", "entrenamiento", "workout"],
                    "nutricion": ["nutrición", "dieta", "alimentación", "comida", "nutrition"],
                    "salud": ["salud", "health", "bienestar", "wellness"],
                    "negocio": ["negocio", "business", "emprender", "ventas", "marketing"],
                    "finanzas": ["dinero", "inversión", "finanzas", "ahorro", "money"],
                }
                msg_lower = message_text.lower()
                for interest, keywords in interest_keywords.items():
                    if any(kw in msg_lower for kw in keywords):
                        user_profile.add_interest(interest, weight=1.0)

                # Track product interest if applicable
                if product and product.get("id"):
                    user_profile.add_interested_product(product["id"], product.get("name"))

            if semantic_memory and ENABLE_SEMANTIC_MEMORY:
                semantic_memory.add_message("user", message_text)
                semantic_memory.add_message("assistant", response_text)
                logger.debug("Messages saved to semantic memory")
        except Exception as e:
            logger.warning(f"Failed to update personalization data: {e}")

        # Programar nurturing si aplica
        nurturing_scheduled = await self._schedule_nurturing_if_needed(
            follower_id=sender_id,
            intent=intent,
            product=product,
            is_customer=follower.is_customer
        )

        # Add AI transparency disclosure for first message if enabled
        transparency_enabled = os.getenv("TRANSPARENCY_ENABLED", "false").lower() == "true"
        is_first_message = (follower.total_messages or 0) <= 1
        if transparency_enabled and is_first_message:
            creator_name = self.config.get("name", self.creator_id)
            disclosure = get_transparency_disclosure(creator_name, user_language)
            response_text = f"{disclosure}\n\n{response_text}"
            logger.info(f"Added transparency disclosure for first message")

        logger.info(f"Response: {response_text[:100]}...")

        # Track product link click if response contains a link and product was mentioned
        if product and ('http' in response_text.lower() or '.com' in response_text.lower() or 'hotmart' in response_text.lower()):
            try:
                sales_tracker = get_sales_tracker()
                product_url = get_valid_payment_url(product)
                sales_tracker.record_click(
                    creator_id=self.creator_id,
                    product_id=product.get('id', ''),
                    follower_id=sender_id,
                    product_name=product.get('name', ''),
                    link_url=product_url
                )
                logger.info(f"Click tracked for product {product.get('name')} -> follower {sender_id}")
            except Exception as e:
                logger.warning(f"Failed to track click: {e}")

        # Track analytics
        await self._track_analytics(
            sender_id=sender_id,
            intent=intent,
            is_lead=follower.is_lead,
            score=follower.purchase_intent_score
        )

        # Registrar mensaje procesado en metricas Prometheus
        record_message_processed(
            creator_id=self.creator_id,
            platform="instagram",
            intent=intent.value
        )

        # === EMAIL CAPTURE SYSTEM ===
        email_captured = False
        try:
            from core.unified_profile_service import (
                extract_email,
                should_ask_email,
                process_email_capture,
                record_email_ask
            )

            # 1. Check if message contains an email
            detected_email = extract_email(message_text)
            if detected_email:
                # Capture the email!
                result = process_email_capture(
                    email=detected_email,
                    platform="instagram",
                    platform_user_id=sender_id,
                    creator_id=self.creator_id,
                    name=follower.name
                )
                if not result.get("error"):
                    email_captured = True
                    # Use the response generated by the service
                    response_text = result.get("response", response_text)
                    is_returning = not result.get("is_new", True)
                    logger.info(f"Email captured: {detected_email} for {sender_id} (returning={is_returning})")

            # 2. If no email captured, check if we should ask for one
            if not email_captured:
                ask_decision = should_ask_email(
                    platform="instagram",
                    platform_user_id=sender_id,
                    creator_id=self.creator_id,
                    intent=intent.value,
                    message_count=follower.total_messages
                )
                if ask_decision.should_ask:
                    # Append email ask to response
                    response_text = response_text + "\n\n" + ask_decision.message
                    record_email_ask("instagram", sender_id, self.creator_id)
                    logger.info(f"Added email ask: {ask_decision.reason}")

        except Exception as email_error:
            logger.warning(f"Email capture error (non-fatal): {email_error}")

        logger.info(f"⏱️ TOTAL process_dm took {time.time() - _process_start:.2f}s")
        return DMResponse(
            response_text=response_text,
            intent=intent,
            action_taken=intent.value,
            product_mentioned=product.get('name') if product else None,
            follow_up_needed=intent in [Intent.INTEREST_SOFT, Intent.OBJECTION_PRICE, Intent.OBJECTION_TIME],
            escalate_to_human=False,
            confidence=confidence,
            metadata={
                "product_id": product.get('id') if product else None,
                "follower_messages": follower.total_messages,
                "nurturing_scheduled": nurturing_scheduled,
                "language": user_language,
                "email_captured": email_captured
            }
        )

    async def _update_memory(
        self,
        follower: FollowerMemory,
        message: str,
        response: str,
        intent: Intent
    ):
        """Actualizar memoria del seguidor"""
        follower.total_messages += 1
        timestamp = datetime.now(timezone.utc).isoformat()
        follower.last_contact = timestamp

        # Añadir al historial con timestamps
        follower.last_messages.append({
            "role": "user",
            "content": message,
            "timestamp": timestamp
        })
        follower.last_messages.append({
            "role": "assistant",
            "content": response,
            "timestamp": timestamp
        })

        # Limitar historial
        if len(follower.last_messages) > 20:
            follower.last_messages = follower.last_messages[-20:]

        # Trackear links enviados (detectar si la respuesta contiene un link)
        if 'http' in response.lower() or '.com' in response.lower() or 'hotmart' in response.lower():
            follower.links_sent_count += 1
            follower.last_link_message_num = follower.total_messages
            logger.debug(f"Link detected in response. Total links sent: {follower.links_sent_count}")

        # Trackear objeciones manejadas y argumentos usados
        if intent.value.startswith('objection_'):
            objection_type = intent.value.replace('objection_', '')
            if objection_type not in follower.objections_handled:
                follower.objections_handled.append(objection_type)

            # Detectar argumentos usados en la respuesta
            argument_keywords = {
                'garantia': ['garantía', 'garantia', '30 días', '30 dias', 'devolucion'],
                'roi': ['recuperas', 'rentabiliza', 'primera semana', 'roi'],
                'tiempo_corto': ['15 minutos', 'poco tiempo', 'rápido', 'flexible'],
                'testimonios': ['alumnos', 'casos', 'testimonios', 'resultados'],
                'soporte': ['soporte', 'ayuda', 'acompaño', 'comunidad'],
                'niveles': ['todos los niveles', 'desde cero', 'principiante'],
                'facil': ['fácil', 'sencillo', 'paso a paso'],
                'unico': ['único', 'diferente', 'exclusivo'],
            }
            for arg_name, keywords in argument_keywords.items():
                if any(kw in response.lower() for kw in keywords):
                    if arg_name not in follower.arguments_used:
                        follower.arguments_used.append(arg_name)

        # Incrementar índice de saludo para variar
        if intent == Intent.GREETING:
            follower.greeting_variant_index += 1

        # === TRACKING DE NATURALIDAD ===

        # Detectar y trackear emojis usados en la respuesta
        emoji_pattern = ['🙌', '💪', '🔥', '✨', '🚀', '👏', '💯', '⚡', '😊', '😄',
                        '🤗', '☺️', '😉', '🙂', '👍', '🤔', '💭', '🧐', '💡', '🎉',
                        '🎊', '🥳', '🏆', '👋', '🎯', '📈']
        for emoji in emoji_pattern:
            if emoji in response:
                if emoji not in follower.last_emojis_used:
                    follower.last_emojis_used.append(emoji)
                # Limitar a últimos 5
                if len(follower.last_emojis_used) > 5:
                    follower.last_emojis_used = follower.last_emojis_used[-5:]

        # Detectar estilo de inicio del mensaje para no repetir
        response_start = response[:20].lower() if response else ""
        greeting_styles = ['ey ', 'hey ', 'hola', 'buenas', 'genial', 'claro', 'entiendo', 'mira']
        for style in greeting_styles:
            if response_start.startswith(style) or f'¡{style}' in response_start:
                follower.last_greeting_style = style.strip()
                break

        # Trackear uso del nombre del usuario
        # Buscar el PRIMER nombre del follower en la respuesta
        full_name = follower.name or follower.username
        first_name = get_first_name(full_name)
        if first_name and len(first_name) > 2 and first_name != "amigo":
            # Verificar si se usó el primer nombre en la respuesta
            if first_name.lower() in response.lower():
                # Se usó el nombre, resetear contador
                follower.messages_since_name_used = 0
                logger.debug(f"Name '{first_name}' used in response, counter reset")
            else:
                # No se usó el nombre, incrementar contador
                follower.messages_since_name_used += 1
        else:
            follower.messages_since_name_used += 1

        # === TRACKING DE CONTACTO ALTERNATIVO ===
        # Detectar si el bot pidió el contacto
        contact_request_phrases = ['whatsapp', 'telegram', 'te paso mi', 'pasame tu', 'tu número', 'tu numero']
        if any(phrase in response.lower() for phrase in contact_request_phrases):
            if not follower.alternative_contact:  # Solo marcar si no tenemos el contacto ya
                follower.contact_requested = True
                logger.info(f"Contact requested from follower {follower.follower_id}")

        # Detectar si el usuario dio su contacto (número de teléfono o username)
        if not follower.alternative_contact:
            import re
            # Patrones para detectar contacto
            # Número de teléfono (varios formatos)
            phone_patterns = [
                r'\+?\d{1,3}[-.\s]?\d{2,4}[-.\s]?\d{2,4}[-.\s]?\d{2,4}',  # +34 612 345 678
                r'\d{9,12}',  # 612345678
            ]
            # Username de Telegram (@username)
            telegram_pattern = r'@[\w]{4,32}'

            message_lower = message.lower()

            # Buscar número de teléfono
            for pattern in phone_patterns:
                match = re.search(pattern, message)
                if match:
                    phone = match.group()
                    # Verificar que parece un teléfono válido (no cualquier número)
                    digits_only = re.sub(r'\D', '', phone)
                    if len(digits_only) >= 9:
                        follower.alternative_contact = phone
                        follower.alternative_contact_type = "whatsapp"
                        logger.info(f"Phone captured: {phone} for follower {follower.follower_id}")
                        break

            # Buscar username de Telegram
            if not follower.alternative_contact:
                telegram_match = re.search(telegram_pattern, message)
                if telegram_match:
                    username = telegram_match.group()
                    follower.alternative_contact = username
                    follower.alternative_contact_type = "telegram"
                    logger.info(f"Telegram captured: {username} for follower {follower.follower_id}")

        # Actualizar score de intención
        # Usamos MÍNIMOS para intenciones positivas (el score no baja de ese valor)
        # y DECREMENTOS para objeciones

        # === SCORE RANGES: 25% / 50% / 75% / 100% ===
        # New Leads: 0-25% | Warm: 25-50% | Hot: 50-75% | Customer: 75%+

        # BOOST: Si hay keywords de compra directa, subir a 75% (Hot)
        if is_direct_purchase_intent(message):
            follower.purchase_intent_score = max(follower.purchase_intent_score or 0.0, 0.75)
            logger.info(f"Direct purchase keywords detected - score boosted to {follower.purchase_intent_score}")
        elif intent == Intent.INTEREST_STRONG:
            # Interés fuerte ("quiero comprar"): 75% → Hot
            follower.purchase_intent_score = max(follower.purchase_intent_score or 0.0, 0.75)
            logger.info(f"INTEREST_STRONG detected - score set to 75% (Hot)")
        elif intent == Intent.INTEREST_SOFT:
            # Interés suave ("me interesa"): 50% → Warm
            follower.purchase_intent_score = max(follower.purchase_intent_score or 0.0, 0.50)
            logger.info(f"INTEREST_SOFT detected - score set to 50% (Warm)")
        elif intent == Intent.QUESTION_PRODUCT:
            # Pregunta sobre producto: 25% → sale de New Leads
            follower.purchase_intent_score = max(follower.purchase_intent_score or 0.0, 0.25)
        else:
            # Para objeciones y otros, aplicar decrementos
            objection_decrements = {
                Intent.OBJECTION_PRICE: -0.05,
                Intent.OBJECTION_TIME: -0.05,
                Intent.OBJECTION_DOUBT: -0.05,
                Intent.OBJECTION_LATER: -0.03,
                Intent.OBJECTION_WORKS: 0.05,  # Pide pruebas = interés real
                Intent.OBJECTION_NOT_FOR_ME: -0.05,
                Intent.OBJECTION_COMPLICATED: -0.03,
                Intent.OBJECTION_ALREADY_HAVE: -0.1,
            }
            change = objection_decrements.get(intent, 0)
            if change != 0:
                current_score = follower.purchase_intent_score or 0.0
                follower.purchase_intent_score = max(0.0, min(1.0, current_score + change))

        # Marcar como lead (score > 25% = sale de New Leads)
        if (follower.purchase_intent_score or 0) > 0.25 or intent == Intent.INTEREST_STRONG:
            follower.is_lead = True

        # ============================================================
        # AUTO-TRANSITION: Update pipeline status based on rules
        # ============================================================
        # NEVER downgrade status: customer > hot > active > new
        # Each transition only moves UP, never down

        # Constants for thresholds
        HOT_INTENT_THRESHOLD = 0.60  # 60% intent = hot

        # Intents that indicate buying intent (→ hot)
        hot_intents = {Intent.INTEREST_STRONG}

        # Intents that indicate active engagement (→ active)
        active_intents = {
            Intent.INTEREST_SOFT,
            Intent.QUESTION_PRODUCT,
            Intent.OBJECTION_PRICE,  # Asking about price = engaged
            Intent.OBJECTION_TIME,
            Intent.OBJECTION_DOUBT,
            Intent.OBJECTION_LATER,
            Intent.OBJECTION_WORKS,
        }

        old_status = follower.status
        current_status = follower.status or "new"
        intent_score = follower.purchase_intent_score or 0.0
        follower_msgs = follower.total_messages or 0

        # Rule: Customer status is permanent (set via payment webhooks)
        if current_status == "customer" or follower.is_customer:
            follower.status = "customer"
        # Rule: NEW → HOT (direct purchase intent or high AI score)
        elif current_status in ["new", "active", ""] and (
            intent in hot_intents or
            is_direct_purchase_intent(message) or
            intent_score >= HOT_INTENT_THRESHOLD
        ):
            follower.status = "hot"
            logger.info(f"Pipeline transition: {old_status} → hot (intent={intent.value}, score={intent_score:.0%})")
        # Rule: NEW → ACTIVE (engagement without clear buy intent)
        elif current_status in ["new", ""] and (
            intent in active_intents or
            follower_msgs >= 2  # At least one back-and-forth
        ):
            follower.status = "active"
            logger.info(f"Pipeline transition: {old_status} → active (intent={intent.value}, messages={follower_msgs})")
        # Keep current status if no transition rule applies
        elif not follower.status:
            follower.status = "new"

        await self.memory_store.save(follower)
        # Save BOTH messages to PostgreSQL for dashboard stats (fire-and-forget)
        self._save_message_to_db_fire_and_forget(follower.follower_id, 'user', message, str(intent))
        self._save_message_to_db_fire_and_forget(follower.follower_id, 'assistant', response, None)
        # Sync lead data (including purchase_intent_score) to PostgreSQL (fire-and-forget)
        # P0 FIX: Now includes status and uses direct DB update as backup
        if USE_POSTGRES and db_service:
            self._sync_lead_to_postgres_fire_and_forget(
                self.creator_id,
                follower.follower_id,
                follower.purchase_intent_score,
                follower.status
            )

    async def _schedule_nurturing_if_needed(
        self,
        follower_id: str,
        intent: Intent,
        product: Optional[dict],
        is_customer: bool
    ) -> bool:
        """
        Programar nurturing automático si aplica.

        Args:
            follower_id: ID del seguidor
            intent: Intent detectado
            product: Producto relevante
            is_customer: Si ya es cliente

        Returns:
            True si se programó nurturing
        """
        try:
            sequence_type = should_schedule_nurturing(
                intent=intent.value,
                has_purchased=is_customer,
                creator_id=self.creator_id
            )

            if not sequence_type:
                return False

            nurturing = get_nurturing_manager()
            product_name = product.get('name', 'mi producto') if product else 'mi producto'

            # Cancelar nurturing existente del mismo tipo antes de programar nuevo
            nurturing.cancel_followups(self.creator_id, follower_id, sequence_type)

            # Programar nueva secuencia
            followups = nurturing.schedule_followup(
                creator_id=self.creator_id,
                follower_id=follower_id,
                sequence_type=sequence_type,
                product_name=product_name
            )

            if followups:
                logger.info(f"Scheduled {len(followups)} nurturing followups for {follower_id} ({sequence_type})")
                return True

        except Exception as e:
            logger.error(f"Error scheduling nurturing: {e}")

        return False

    async def _track_analytics(
        self,
        sender_id: str,
        intent: Intent,
        is_lead: bool,
        score: float
    ):
        """
        Track analytics for the processed message.

        Args:
            sender_id: Follower ID
            intent: Detected intent
            is_lead: Whether follower is a lead
            score: Purchase intent score
        """
        try:
            analytics = get_analytics_manager()
            platform = detect_platform(sender_id)

            # Track received message
            analytics.track_message(
                creator_id=self.creator_id,
                follower_id=sender_id,
                direction="received",
                intent=intent.value,
                platform=platform
            )

            # Track sent message (response)
            analytics.track_message(
                creator_id=self.creator_id,
                follower_id=sender_id,
                direction="sent",
                platform=platform
            )

            # Track lead if applicable
            if is_lead and score > 0.3:
                analytics.track_lead(
                    creator_id=self.creator_id,
                    follower_id=sender_id,
                    score=score,
                    source="dm",
                    platform=platform
                )

            # Track objection if applicable
            if intent.value.startswith("objection_"):
                analytics.track_objection(
                    creator_id=self.creator_id,
                    follower_id=sender_id,
                    objection_type=intent.value,
                    platform=platform
                )

            # Track escalation if applicable
            if intent == Intent.ESCALATION:
                analytics.track_escalation(
                    creator_id=self.creator_id,
                    follower_id=sender_id,
                    platform=platform
                )

        except Exception as e:
            logger.error(f"Error tracking analytics: {e}")

    async def _check_gdpr_consent(
        self,
        sender_id: str,
        message_text: str,
        follower
    ) -> Optional[DMResponse]:
        """
        Check GDPR consent and handle consent flow if needed.

        Args:
            sender_id: Follower ID
            message_text: User's message
            follower: Follower memory object

        Returns:
            DMResponse if consent flow is triggered, None otherwise
        """
        try:
            gdpr = get_gdpr_manager()

            # Check if user has data processing consent
            has_consent = gdpr.has_consent(
                self.creator_id,
                sender_id,
                ConsentType.DATA_PROCESSING.value
            )

            if has_consent:
                return None  # Continue normal processing

            # Check if user is giving consent in this message
            msg_lower = message_text.lower()
            consent_keywords = ['acepto', 'si acepto', 'de acuerdo', 'ok', 'vale', 'accept', 'i agree', 'yes']
            decline_keywords = ['no acepto', 'no quiero', 'rechazar', 'decline', 'no thanks']

            if any(kw in msg_lower for kw in consent_keywords):
                # Record consent
                gdpr.record_consent(
                    creator_id=self.creator_id,
                    follower_id=sender_id,
                    consent_type=ConsentType.DATA_PROCESSING.value,
                    granted=True,
                    source="dm"
                )
                logger.info(f"Consent granted by {sender_id}")
                return None  # Continue with normal processing

            if any(kw in msg_lower for kw in decline_keywords):
                # Record declined consent
                gdpr.record_consent(
                    creator_id=self.creator_id,
                    follower_id=sender_id,
                    consent_type=ConsentType.DATA_PROCESSING.value,
                    granted=False,
                    source="dm"
                )
                response_text = (
                    "Entendido, respeto tu decision. Si cambias de opinion, "
                    "solo escribe 'acepto' y podre ayudarte. Hasta pronto!"
                )
                return DMResponse(
                    response_text=response_text,
                    intent=Intent.OTHER,
                    action_taken="consent_declined",
                    confidence=1.0
                )

            # First message without consent - ask for consent
            if follower.total_messages == 0:
                response_text = (
                    "Hola! Antes de continuar, necesito tu consentimiento para procesar "
                    "tus mensajes y poder ayudarte mejor. "
                    "Tus datos se usaran solo para responder tus consultas. "
                    "Responde 'acepto' para continuar o 'no acepto' si prefieres no hacerlo."
                )
                return DMResponse(
                    response_text=response_text,
                    intent=Intent.OTHER,
                    action_taken="consent_request",
                    confidence=1.0
                )

            # Subsequent message without consent - remind
            response_text = (
                "Recuerda que necesito tu consentimiento para procesar tus mensajes. "
                "Responde 'acepto' para que pueda ayudarte!"
            )
            return DMResponse(
                response_text=response_text,
                intent=Intent.OTHER,
                action_taken="consent_reminder",
                confidence=1.0
            )

        except Exception as e:
            logger.error(f"Error checking GDPR consent: {e}")
            return None  # On error, continue normal processing

    def _get_escalation_response(self) -> str:
        """Respuesta de escalación cuando el usuario pide hablar con humano"""
        name = self.creator_config.get('clone_name') or self.creator_config.get('name', 'el equipo')
        email = self.creator_config.get('escalation_email', '')

        # Check dialect for voseo
        dialect = get_tone_dialect(self.creator_id)

        if dialect == "rioplatense":
            # Variantes con voseo argentino
            responses = [
                f"Entendido, le paso tu mensaje a {name} y te contacta pronto. 🙌",
                f"Perfecto, le paso tu mensaje a {name} y se pone en contacto con vos lo antes posible.",
                f"Sin problema, {name} te responde personalmente en breve.",
                f"Claro, tomé nota y {name} te contacta pronto para ayudarte mejor."
            ]
            response = random.choice(responses)
            if email:
                response += f" Si es urgente, podés escribir a {email}."
        else:
            # Variantes con tuteo español
            responses = [
                f"Entendido, paso tu mensaje a {name} y te contactará pronto. 🙌",
                f"Perfecto, le paso tu mensaje a {name} y se pondrá en contacto contigo lo antes posible.",
                f"Sin problema, {name} te responderá personalmente en breve.",
                f"Claro, he tomado nota y {name} te contactará pronto para ayudarte mejor."
            ]
            response = random.choice(responses)
            if email:
                response += f" Si es urgente, puedes escribir a {email}."
        return response

    def _get_fallback_response(self, intent: Intent, language: str = "es") -> str:
        """
        Respuesta de fallback cuando LLM falla.
        Uses varied responses to seem more natural.
        """
        # Use clone_name (display name) with fallback to name
        name = self.creator_config.get('clone_name') or self.creator_config.get('name', 'yo')

        # Check dialect for voseo
        dialect = get_tone_dialect(self.creator_id)

        # Spanish fallbacks with voseo (rioplatense)
        fallbacks_es_voseo = {
            Intent.GREETING: [
                f"Ey! Qué tal? Soy {name}. ¿En qué puedo ayudarte?",
                f"Hola! Soy {name}, encantado de saludarte. ¿Qué necesitás?",
            ],
            Intent.INTEREST_STRONG: [
                "Genial que te interese! Te paso toda la info ahora mismo.",
                "Me encanta tu interés! Dejame contarte todo.",
            ],
            Intent.INTEREST_SOFT: [
                "Me alegra que te interese! Contame, ¿qué necesitás exactamente?",
                "Qué bien! ¿Qué te gustaría saber más?",
            ],
            Intent.ACKNOWLEDGMENT: [
                "Perfecto! ¿Te gustaría saber más sobre algo?",
                "Genial! ¿En qué más puedo ayudarte?",
                "Ok! ¿Hay algo más que quieras saber?",
            ],
            Intent.CORRECTION: [
                "Disculpa la confusión! ¿En qué puedo ayudarte entonces?",
                "Perdona, te entendí mal. ¿Qué necesitás?",
                "Ups, disculpa! Contame, ¿qué te gustaría saber?",
            ],
            Intent.OBJECTION_PRICE: [
                "Entiendo que es una inversión. ¿Qué es lo que más te preocupa?",
                "Comprendo. Es normal pensarlo. ¿Qué te gustaría saber sobre el valor?",
            ],
            Intent.OBJECTION_TIME: [
                "Lo entiendo, el tiempo es oro. Precisamente esto te ayuda a ganar tiempo.",
                "Claro, el tiempo es importante. Por eso está diseñado para ser rápido.",
            ],
            Intent.OBJECTION_DOUBT: [
                "Normal tener dudas. ¿Qué te gustaría saber?",
                "Entiendo tus dudas. Contame, ¿qué te preocupa?",
            ],
            Intent.OBJECTION_LATER: [
                "Claro, sin apuro. Aunque te digo que el mejor momento es ahora.",
                "Entiendo! Cuando estés listo, acá estoy.",
            ],
            Intent.OTHER: [
                "Gracias por tu mensaje! Dame un momento para responder.",
                "Recibido! En un momento te cuento más.",
                "Gracias por escribir! ¿En qué puedo ayudarte?",
            ],
        }

        # Spanish fallbacks with tuteo (standard)
        fallbacks_es = {
            Intent.GREETING: [
                f"Ey! Qué tal? Soy {name}. ¿En qué puedo ayudarte?",
                f"Hola! Soy {name}, encantado de saludarte. ¿Qué necesitas?",
            ],
            Intent.INTEREST_STRONG: [
                "Genial que te interese! Te paso toda la info ahora mismo.",
                "Me encanta tu interés! Déjame contarte todo.",
            ],
            Intent.INTEREST_SOFT: [
                "Me alegra que te interese! Cuéntame, ¿qué necesitas exactamente?",
                "Qué bien! ¿Qué te gustaría saber más?",
            ],
            Intent.ACKNOWLEDGMENT: [
                "Perfecto! ¿Te gustaría saber más sobre algo?",
                "Genial! ¿En qué más puedo ayudarte?",
                "Ok! ¿Hay algo más que quieras saber?",
            ],
            Intent.CORRECTION: [
                "Disculpa la confusión! ¿En qué puedo ayudarte entonces?",
                "Perdona, te entendí mal. ¿Qué necesitas?",
                "Ups, disculpa! Cuéntame, ¿qué te gustaría saber?",
            ],
            Intent.OBJECTION_PRICE: [
                "Entiendo que es una inversión. ¿Qué es lo que más te preocupa?",
                "Comprendo. Es normal pensárselo. ¿Qué te gustaría saber sobre el valor?",
            ],
            Intent.OBJECTION_TIME: [
                "Lo entiendo, el tiempo es oro. Precisamente esto te ayuda a ganar tiempo.",
                "Claro, el tiempo es importante. Por eso está diseñado para ser rápido.",
            ],
            Intent.OBJECTION_DOUBT: [
                "Normal tener dudas. ¿Qué te gustaría saber?",
                "Entiendo tus dudas. Cuéntame, ¿qué te preocupa?",
            ],
            Intent.OBJECTION_LATER: [
                "Claro, sin prisa. Aunque te digo que el mejor momento es ahora.",
                "Entiendo! Cuando estés listo, aquí estoy.",
            ],
            Intent.OTHER: [
                "Gracias por tu mensaje! Dame un momento para responder.",
                "Recibido! En un momento te cuento más.",
                "Gracias por escribir! ¿En qué puedo ayudarte?",
            ],
        }

        # English fallbacks
        fallbacks_en = {
            Intent.GREETING: [
                f"Hey! I'm {name}. How can I help you?",
                f"Hi there! {name} here. What can I do for you?",
            ],
            Intent.OTHER: [
                "Thanks for your message! I'll get back to you shortly.",
                "Got it! Give me a moment to respond.",
            ],
        }

        # Select appropriate fallbacks based on language and dialect
        if language == "es":
            if dialect == "rioplatense":
                fallbacks = fallbacks_es_voseo
            else:
                fallbacks = fallbacks_es
        else:
            fallbacks = fallbacks_en

        options = fallbacks.get(intent, fallbacks.get(Intent.OTHER, ["Gracias por escribir!"]))
        return random.choice(options)

    async def get_all_conversations(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Obtener todas las conversaciones del creador"""
        conversations = []
        storage_path = os.path.join(self.memory_store.storage_path, self.creator_id)

        if not os.path.exists(storage_path):
            return conversations

        try:
            files = sorted(
                [f for f in os.listdir(storage_path) if f.endswith('.json')],
                key=lambda x: os.path.getmtime(os.path.join(storage_path, x)),
                reverse=True
            )[:limit]

            for file in files:
                file_path = os.path.join(storage_path, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # Count actual user messages in last_messages (more accurate than stored counter)
                        last_messages = data.get("last_messages", [])
                        user_msg_count = len([m for m in last_messages if m.get("role") == "user"])
                        # Use the higher of stored counter or actual count
                        total_msgs = max(data.get("total_messages", 0), user_msg_count)
                        conversations.append({
                            "follower_id": data.get("follower_id", ""),
                            "username": data.get("username", ""),
                            "name": data.get("name", ""),
                            "platform": data.get("platform", "instagram"),
                            "total_messages": total_msgs,
                            "last_contact": data.get("last_contact", ""),
                            "first_contact": data.get("first_contact", ""),
                            "is_lead": data.get("is_lead", False),
                            "is_customer": data.get("is_customer", False),
                            "purchase_intent": data.get("purchase_intent_score", 0),
                            "interests": data.get("interests", []),
                            "products_discussed": data.get("products_discussed", []),
                            "preferred_language": data.get("preferred_language", "es"),
                            # Contact fields from JSON storage
                            "email": data.get("email", ""),
                            "phone": data.get("phone", ""),
                            "notes": data.get("notes", ""),
                            "last_messages": last_messages[-5:] if last_messages else [],
                        })
                except Exception as e:
                    logger.error(f"Error reading conversation file {file}: {e}")

        except Exception as e:
            logger.error(f"Error listing conversations: {e}")

        return conversations

    async def get_leads(self) -> List[Dict[str, Any]]:
        """Obtener todos los leads del creador"""
        conversations = await self.get_all_conversations(limit=500)
        leads = [c for c in conversations if c.get("is_lead", False)]
        # Ordenar por intención de compra
        leads.sort(key=lambda x: x.get("purchase_intent", 0), reverse=True)
        return leads

    async def get_metrics(self) -> Dict[str, Any]:
        """Obtener métricas del agente"""
        conversations = await self.get_all_conversations(limit=1000)

        total_messages = sum(c.get("total_messages", 0) for c in conversations)
        total_followers = len(conversations)
        leads = [c for c in conversations if c.get("is_lead", False)]
        customers = [c for c in conversations if c.get("is_customer", False)]
        high_intent = [c for c in conversations if c.get("purchase_intent", 0) > 0.5]

        return {
            "total_messages": total_messages,
            "total_followers": total_followers,
            "leads": len(leads),
            "customers": len(customers),
            "high_intent_followers": len(high_intent),
            "conversion_rate": len(customers) / total_followers if total_followers > 0 else 0,
            "lead_rate": len(leads) / total_followers if total_followers > 0 else 0
        }

    async def get_follower_detail(self, follower_id: str) -> Optional[Dict[str, Any]]:
        """Obtener detalle de un seguidor específico"""
        follower = await self.memory_store.get(self.creator_id, follower_id)

        if not follower:
            return None

        return {
            "follower_id": follower.follower_id,
            "username": follower.username,
            "name": follower.name,
            "first_contact": follower.first_contact,
            "last_contact": follower.last_contact,
            "total_messages": follower.total_messages,
            "interests": follower.interests,
            "products_discussed": follower.products_discussed,
            "objections_raised": follower.objections_raised,
            "purchase_intent_score": follower.purchase_intent_score,
            "is_lead": follower.is_lead,
            "is_customer": follower.is_customer,
            "preferred_language": follower.preferred_language,
            "last_messages": follower.last_messages[-10:]  # Últimos 10 mensajes
        }

    async def save_manual_message(
        self,
        follower_id: str,
        message_text: str,
        sent: bool = True
    ) -> bool:
        """
        Save a manually sent message in the conversation history.

        Args:
            follower_id: The follower's ID
            message_text: The message text that was sent
            sent: Whether the message was successfully sent

        Returns:
            True if saved successfully
        """
        try:
            follower = await self.memory_store.get(self.creator_id, follower_id)

            if not follower:
                logger.warning(f"Follower {follower_id} not found for saving manual message")
                return False

            # Add the message to history
            timestamp = datetime.now(timezone.utc).isoformat()
            follower.last_messages.append({
                "role": "assistant",
                "content": message_text,
                "timestamp": timestamp,
                "manual": True,  # Mark as manually sent
                "sent": sent
            })

            # Keep only last 50 messages
            if len(follower.last_messages) > 50:
                follower.last_messages = follower.last_messages[-50:]

            # Update last contact time
            follower.last_contact = timestamp

            # Save to memory store
            await self.memory_store.save(follower)
            # Save to PostgreSQL (manual message from assistant) - fire-and-forget
            self._save_message_to_db_fire_and_forget(follower.follower_id, 'assistant', message_text, None)

            logger.info(f"Saved manual message for {follower_id}")
            return True

        except Exception as e:
            logger.error(f"Error saving manual message: {e}")
            return False

    async def update_follower_status(
        self,
        follower_id: str,
        status: str,
        purchase_intent: float,
        is_customer: bool = False
    ) -> bool:
        """
        Update the lead status for a follower.

        Args:
            follower_id: The follower's ID
            status: The new status (cold, warm, hot, customer)
            purchase_intent: The purchase intent score (0.0 to 1.0)
            is_customer: Whether the follower is now a customer

        Returns:
            True if updated successfully
        """
        try:
            follower = await self.memory_store.get(self.creator_id, follower_id)

            if not follower:
                logger.warning(f"Follower {follower_id} not found for status update")
                return False

            # Update the follower's status
            old_score = follower.purchase_intent_score
            follower.purchase_intent_score = purchase_intent

            # Update is_lead based on score
            if purchase_intent >= 0.3:
                follower.is_lead = True

            # Update is_customer
            if is_customer:
                follower.is_customer = True

            # Save to memory store (no message added to history)
            await self.memory_store.save(follower)

            logger.info(f"Updated status for {follower_id}: {status} (intent: {old_score:.0%} → {purchase_intent:.0%})")
            return True

        except Exception as e:
            logger.error(f"Error updating follower status: {e}")
            return False

# ============================================================
# POSTGRESQL INTEGRATION (saves messages to DB for dashboard)
# ============================================================

# Singleton cache for DM agents (one per creator, reused across requests)
_dm_agent_cache: Dict[str, DMResponderAgent] = {}
_dm_agent_cache_timestamp: Dict[str, float] = {}
_DM_AGENT_CACHE_TTL = 600  # 10 minutes - agents are reused for this long


def get_dm_agent(creator_id: str) -> DMResponderAgent:
    """
    Factory to get DM agent for a creator - SINGLETON PATTERN.
    Reuses existing agent for same creator to avoid expensive initialization.
    """
    import time
    _t_start = time.time()

    cache_key = creator_id
    now = time.time()
    cache_age = now - _dm_agent_cache_timestamp.get(cache_key, 0)

    if cache_age < _DM_AGENT_CACHE_TTL and cache_key in _dm_agent_cache:
        agent = _dm_agent_cache[cache_key]
        logger.info(f"⏱️ get_dm_agent: reusing cached agent for {creator_id} (age: {cache_age:.1f}s) took {time.time() - _t_start:.3f}s")
        return agent

    # Create new agent and cache it
    agent = DMResponderAgent(creator_id=creator_id)
    _dm_agent_cache[cache_key] = agent
    _dm_agent_cache_timestamp[cache_key] = now
    logger.info(f"⏱️ get_dm_agent: created new agent for {creator_id} took {time.time() - _t_start:.2f}s")
    return agent


def invalidate_dm_agent_cache(creator_id: str = None):
    """Invalidate DM agent cache - call when creator config changes."""
    if creator_id:
        _dm_agent_cache.pop(creator_id, None)
        _dm_agent_cache_timestamp.pop(creator_id, None)
        logger.info(f"Invalidated DM agent cache for {creator_id}")
    else:
        _dm_agent_cache.clear()
        _dm_agent_cache_timestamp.clear()
        logger.info("Invalidated all DM agent caches")

