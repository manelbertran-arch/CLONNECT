"""
Lead Categorization Service - Sistema de Embudo Estándar

Categorías:
- nuevo: Acaba de llegar, sin señales de intención
- interesado: Muestra curiosidad, hace preguntas
- caliente: Listo para comprar, pregunta precio
- cliente: Ya compró
- fantasma: Sin respuesta 7+ días
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# Keywords que indican interés (pero no compra)
KEYWORDS_INTERESADO = [
    # Español
    "info", "información", "detalles", "cómo funciona", "como funciona",
    "qué incluye", "que incluye", "cuéntame", "cuentame", "explícame", "explicame",
    "me interesa", "quiero saber", "tienes", "ofreces", "haces",
    "servicios", "productos", "programas", "opciones",
    # English
    "info", "information", "details", "how does it work",
    "what's included", "tell me", "explain", "interested",
    "want to know", "do you have", "offer", "services"
]

# Keywords que indican intención de compra (CALIENTE)
KEYWORDS_CALIENTE = [
    # Precio
    "precio", "cuesta", "cuánto", "cuanto", "vale", "cost", "price", "how much",
    # Compra
    "comprar", "pagar", "reservar", "contratar", "empezar", "comenzar",
    "buy", "pay", "book", "hire", "start",
    # Intención clara
    "quiero", "lo quiero", "me apunto", "me anoto", "lo tomo",
    "i want", "sign me up", "i'll take it",
    # Acción
    "dónde pago", "donde pago", "link de pago", "link pago",
    "calendario", "disponibilidad", "agendar", "cita",
    "where do i pay", "payment link", "calendar", "availability", "schedule"
]


@dataclass
class CategorizationResult:
    """Resultado de la categorización de un lead."""
    categoria: str  # nuevo, interesado, caliente, cliente, fantasma
    intent_score: float  # 0.0 - 1.0
    razones: List[str]  # Por qué se asignó esta categoría
    keywords_detectados: List[str]


def detectar_keywords(texto: str, keywords: List[str]) -> List[str]:
    """Detecta qué keywords están presentes en el texto."""
    texto_lower = texto.lower()
    encontrados = []
    for kw in keywords:
        if kw.lower() in texto_lower:
            encontrados.append(kw)
    return encontrados


def calcular_categoria(
    mensajes: List[Dict],
    es_cliente: bool = False,
    ultimo_mensaje_lead: Optional[datetime] = None,
    dias_fantasma: int = 7,
    lead_created_at: Optional[datetime] = None,
    ultima_interaccion: Optional[datetime] = None
) -> CategorizationResult:
    """
    Calcula la categoría de un lead basándose en sus mensajes.

    Args:
        mensajes: Lista de mensajes con 'role' y 'content'
        es_cliente: Si ya tiene compra confirmada
        ultimo_mensaje_lead: Fecha del último mensaje del lead
        dias_fantasma: Días sin respuesta para considerar fantasma
        lead_created_at: Fecha de creación del lead (para fantasma sin mensajes)
        ultima_interaccion: Última interacción (cualquier tipo) del lead

    Returns:
        CategorizationResult con categoría, score y razones
    """
    razones = []
    keywords_detectados = []

    # 1. CLIENTE - Estado final, máxima prioridad
    if es_cliente:
        return CategorizationResult(
            categoria="cliente",
            intent_score=1.0,
            razones=["Compra confirmada"],
            keywords_detectados=[]
        )

    # Extraer solo mensajes del usuario (no del bot)
    mensajes_usuario = [m for m in mensajes if m.get("role") == "user"]
    total_mensajes = len(mensajes_usuario)

    # Concatenar todo el texto del usuario para análisis
    texto_completo = " ".join([m.get("content", "") for m in mensajes_usuario])

    # Detectar keywords
    kw_caliente = detectar_keywords(texto_completo, KEYWORDS_CALIENTE)
    kw_interesado = detectar_keywords(texto_completo, KEYWORDS_INTERESADO)

    keywords_detectados = kw_caliente + kw_interesado

    # 2. CALIENTE - Pregunta precio o quiere comprar
    if kw_caliente:
        razones.append(f"Keywords de compra detectados: {', '.join(kw_caliente[:3])}")

        # Calcular score basado en intensidad de señales
        intent_score = 0.5
        if any(kw in texto_completo.lower() for kw in ["precio", "cuesta", "cuánto", "cuanto", "cost", "price"]):
            intent_score += 0.2
            razones.append("Preguntó por precio")
        if any(kw in texto_completo.lower() for kw in ["comprar", "pagar", "reservar", "quiero", "buy", "pay"]):
            intent_score += 0.2
            razones.append("Expresó intención de compra")
        if any(kw in texto_completo.lower() for kw in ["link", "calendario", "agendar", "calendar"]):
            intent_score += 0.1
            razones.append("Pidió link o calendario")

        return CategorizationResult(
            categoria="caliente",
            intent_score=min(intent_score, 1.0),
            razones=razones,
            keywords_detectados=keywords_detectados
        )

    # 3. FANTASMA - Sin respuesta del lead por X días
    ahora = datetime.now(timezone.utc)

    # Caso A: Lead con mensajes pero sin respuesta después de mensaje del bot
    if ultimo_mensaje_lead:
        if ultimo_mensaje_lead.tzinfo is None:
            ultimo_mensaje_lead = ultimo_mensaje_lead.replace(tzinfo=timezone.utc)

        dias_sin_respuesta = (ahora - ultimo_mensaje_lead).days

        # Verificar si el último mensaje fue del bot
        if mensajes:
            ultimo_rol = mensajes[-1].get("role") if mensajes else None
            if ultimo_rol == "assistant" and dias_sin_respuesta >= dias_fantasma:
                return CategorizationResult(
                    categoria="fantasma",
                    intent_score=0.1,
                    razones=[f"Sin respuesta hace {dias_sin_respuesta} días"],
                    keywords_detectados=[]
                )

    # Caso B: Lead sin mensajes de texto, usar última interacción o fecha de creación
    elif total_mensajes == 0:
        fecha_referencia = ultima_interaccion or lead_created_at
        if fecha_referencia:
            if fecha_referencia.tzinfo is None:
                fecha_referencia = fecha_referencia.replace(tzinfo=timezone.utc)

            dias_desde_creacion = (ahora - fecha_referencia).days

            if dias_desde_creacion >= dias_fantasma:
                return CategorizationResult(
                    categoria="fantasma",
                    intent_score=0.05,
                    razones=[f"Sin interacción hace {dias_desde_creacion} días (sin mensajes)"],
                    keywords_detectados=[]
                )

    # 4. INTERESADO - Muestra curiosidad, hace preguntas
    if kw_interesado or total_mensajes >= 3:
        razones_interesado = []

        if kw_interesado:
            razones_interesado.append(f"Keywords de interés: {', '.join(kw_interesado[:3])}")

        if total_mensajes >= 3:
            razones_interesado.append(f"Conversación activa ({total_mensajes} mensajes)")

        # Calcular score
        intent_score = 0.2
        if kw_interesado:
            intent_score += 0.1 * min(len(kw_interesado), 3)
        if total_mensajes >= 5:
            intent_score += 0.1

        return CategorizationResult(
            categoria="interesado",
            intent_score=min(intent_score, 0.49),  # Max 0.49 para no ser caliente
            razones=razones_interesado,
            keywords_detectados=kw_interesado
        )

    # 5. NUEVO - Por defecto
    razones_nuevo = []
    if total_mensajes == 0:
        razones_nuevo.append("Sin mensajes del usuario")
    elif total_mensajes <= 2:
        razones_nuevo.append(f"Pocos mensajes ({total_mensajes})")
    else:
        razones_nuevo.append("Sin señales de interés detectadas")

    return CategorizationResult(
        categoria="nuevo",
        intent_score=0.1,
        razones=razones_nuevo,
        keywords_detectados=[]
    )


def categoria_a_status_legacy(categoria: str) -> str:
    """
    Convierte categoría nueva a status legacy para compatibilidad.

    nuevo -> new
    interesado -> active
    caliente -> hot
    cliente -> hot (o nuevo campo)
    fantasma -> new
    """
    mapping = {
        "nuevo": "new",
        "interesado": "active",
        "caliente": "hot",
        "cliente": "hot",
        "fantasma": "new"
    }
    return mapping.get(categoria, "new")


def status_legacy_a_categoria(status: str) -> str:
    """
    Convierte status legacy a categoría nueva.

    new -> nuevo
    active -> interesado
    hot -> caliente
    """
    mapping = {
        "new": "nuevo",
        "active": "interesado",
        "hot": "caliente"
    }
    return mapping.get(status, "nuevo")


# Colores y metadata para frontend
CATEGORIAS_CONFIG = {
    "nuevo": {
        "color": "#9CA3AF",  # gris
        "icon": "⚪",
        "label": "Nuevo",
        "label_en": "New",
        "description": "Acaba de llegar, el bot está saludando",
        "description_en": "Just arrived, bot is greeting",
        "priority": 5
    },
    "interesado": {
        "color": "#F59E0B",  # amarillo
        "icon": "🟡",
        "label": "Interesado",
        "label_en": "Interested",
        "description": "Hace preguntas, quiere saber más",
        "description_en": "Asking questions, wants to know more",
        "priority": 3
    },
    "caliente": {
        "color": "#EF4444",  # rojo
        "icon": "🔴",
        "label": "Caliente",
        "label_en": "Hot",
        "description": "¡Quiere comprar! Contacta personalmente",
        "description_en": "Wants to buy! Contact personally",
        "priority": 1  # Máxima prioridad
    },
    "cliente": {
        "color": "#10B981",  # verde
        "icon": "🟢",
        "label": "Cliente",
        "label_en": "Customer",
        "description": "Ya compró",
        "description_en": "Already purchased",
        "priority": 4
    },
    "fantasma": {
        "color": "#6B7280",  # gris oscuro
        "icon": "👻",
        "label": "Fantasma",
        "label_en": "Ghost",
        "description": "No responde hace +7 días",
        "description_en": "No response for 7+ days",
        "priority": 6
    }
}


def get_categoria_config(categoria: str) -> Dict:
    """Obtiene la configuración de una categoría."""
    return CATEGORIAS_CONFIG.get(categoria, CATEGORIAS_CONFIG["nuevo"])
