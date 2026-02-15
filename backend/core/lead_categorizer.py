"""
Lead Categorization Service - Sistema de Embudo Estándar

Categorías:
- NUEVO: Lead que acaba de llegar, sin señales de intención
- INTERESADO: Muestra curiosidad, hace preguntas, quiere saber más
- CALIENTE: Listo para comprar, pregunta precio o cómo pagar
- CLIENTE: Ya compró
- FANTASMA: Sin respuesta hace +7 días

Prioridad de evaluación (orden importa):
1. Cliente (estado final)
2. Caliente (máxima prioridad comercial)
3. Fantasma (inactivo)
4. Interesado
5. Nuevo (por defecto)
"""

import re
import logging
from enum import Enum
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class LeadCategory(Enum):
    """Categorías del embudo de ventas estándar"""
    NUEVO = "nuevo"
    INTERESADO = "interesado"
    CALIENTE = "caliente"
    CLIENTE = "cliente"
    FANTASMA = "fantasma"


@dataclass
class CategoryInfo:
    """Información de una categoría para UI"""
    value: str
    label: str
    icon: str
    color: str
    description: str
    action_required: bool


# Configuración de categorías para frontend
CATEGORY_CONFIG: Dict[str, CategoryInfo] = {
    "nuevo": CategoryInfo(
        value="nuevo",
        label="Nuevo",
        icon="⚪",
        color="#9CA3AF",  # gris
        description="Acaba de llegar, el bot está saludando",
        action_required=False
    ),
    "interesado": CategoryInfo(
        value="interesado",
        label="Interesado",
        icon="🟡",
        color="#F59E0B",  # amarillo
        description="Hace preguntas, quiere saber más",
        action_required=False
    ),
    "caliente": CategoryInfo(
        value="caliente",
        label="Caliente",
        icon="🔴",
        color="#EF4444",  # rojo
        description="¡Quiere comprar! Contacta personalmente",
        action_required=True
    ),
    "cliente": CategoryInfo(
        value="cliente",
        label="Cliente",
        icon="🟢",
        color="#10B981",  # verde
        description="Ya compró",
        action_required=False
    ),
    "fantasma": CategoryInfo(
        value="fantasma",
        label="Fantasma",
        icon="👻",
        color="#6B7280",  # gris oscuro
        description="No responde hace +7 días",
        action_required=False
    ),
}

# Keywords para detección de interés
KEYWORDS_INTERESADO = [
    r"\binfo\b", r"\binformación\b", r"\bdetalles\b", r"\bcómo funciona\b",
    r"\bqué incluye\b", r"\bcuéntame\b", r"\bexplícame\b", r"\bme interesa\b",
    r"\bquiero saber\b", r"\btienes\b", r"\bofreces\b", r"\bhaces\b",
    r"\bqué es\b", r"\bpara qué sirve\b", r"\bcómo es\b",
]

# Keywords para detección de lead caliente
KEYWORDS_CALIENTE = [
    # Precio
    r"\bprecio\b", r"\bcuesta\b", r"\bcuánto\b", r"\bvale\b", r"\bcost\b",
    r"\btarifa\b", r"\bpagar\b", r"\bforma de pago\b", r"\btarjeta\b",
    r"\btransferencia\b", r"\bcuotas\b",
    # Compra
    r"\bcomprar\b", r"\breservar\b", r"\bcontratar\b", r"\bapúntate\b",
    r"\bempezar\b", r"\binscribirme\b", r"\bquiero el\b", r"\blo quiero\b",
    r"\bme apunto\b",
    # Booking
    r"\blink\b", r"\bcalendario\b", r"\bdisponibilidad\b", r"\bagendar\b",
    r"\bcita\b", r"\bsesión\b", r"\breunión\b",
]


class LeadCategorizer:
    """Categorizador de leads usando sistema de embudo estándar"""

    DAYS_UNTIL_GHOST = 7  # Días sin respuesta para ser fantasma

    def categorize(
        self,
        messages: List[Dict],
        is_customer: bool = False,
        last_user_message_time: Optional[datetime] = None,
        last_bot_message_time: Optional[datetime] = None,
    ) -> Tuple[LeadCategory, float, str]:
        """
        Categoriza un lead basándose en sus mensajes y estado.

        Args:
            messages: Lista de mensajes [{role: "user"|"assistant", content: str, timestamp: datetime}]
            is_customer: Si ya es cliente (desde pago confirmado o manual)
            last_user_message_time: Timestamp del último mensaje del usuario
            last_bot_message_time: Timestamp del último mensaje del bot

        Returns:
            Tuple de (categoría, score 0-1, razón)
        """
        # 1. CLIENTE - Estado final
        if is_customer:
            return LeadCategory.CLIENTE, 1.0, "Es cliente confirmado"

        # Extraer mensajes del usuario
        user_messages = [
            m for m in messages
            if m.get("role") == "user" and m.get("content")
        ]

        # Concatenar todo el texto del usuario para análisis
        all_user_text = " ".join(m.get("content", "") for m in user_messages).lower()
        total_user_messages = len(user_messages)

        # 2. CALIENTE - Máxima prioridad comercial
        is_hot, hot_reason = self._is_caliente(all_user_text, user_messages)
        if is_hot:
            score = self._calculate_hot_score(all_user_text, user_messages)
            return LeadCategory.CALIENTE, score, hot_reason

        # 3. FANTASMA - Inactivo
        is_ghost, ghost_reason = self._is_fantasma(
            last_user_message_time, last_bot_message_time
        )
        if is_ghost:
            return LeadCategory.FANTASMA, 0.1, ghost_reason

        # 4. INTERESADO - Muestra curiosidad
        is_interested, interest_reason = self._is_interesado(all_user_text, total_user_messages)
        if is_interested:
            score = self._calculate_interest_score(all_user_text, total_user_messages)
            return LeadCategory.INTERESADO, score, interest_reason

        # 5. NUEVO - Por defecto
        return LeadCategory.NUEVO, 0.1, "Sin señales de intención detectadas"

    def _is_caliente(self, text: str, messages: List[Dict]) -> Tuple[bool, str]:
        """Detecta si el lead está caliente (listo para comprar)"""
        matches = []

        for pattern in KEYWORDS_CALIENTE:
            if re.search(pattern, text, re.IGNORECASE):
                matches.append(pattern.replace(r"\b", "").replace("\\", ""))

        if matches:
            return True, f"Keywords de compra: {', '.join(matches[:3])}"

        # También verificar intents clasificados en mensajes
        for msg in messages:
            intent = msg.get("intent", "")
            if intent in ["interest_strong", "purchase", "question_product"]:
                return True, f"Intent clasificado: {intent}"

        return False, ""

    def _is_fantasma(
        self,
        last_user_time: Optional[datetime],
        last_bot_time: Optional[datetime]
    ) -> Tuple[bool, str]:
        """Detecta si el lead es un fantasma (sin respuesta hace +7 días)"""
        if not last_user_time:
            return False, ""

        now = datetime.now(timezone.utc)

        # Normalizar timezone
        if last_user_time.tzinfo is None:
            last_user_time = last_user_time.replace(tzinfo=timezone.utc)

        days_since_response = (now - last_user_time).days

        # Es fantasma si no responde hace +7 días Y el último mensaje fue del bot
        if days_since_response >= self.DAYS_UNTIL_GHOST:
            if last_bot_time and last_bot_time > last_user_time:
                return True, f"Sin respuesta hace {days_since_response} días"

        return False, ""

    def _is_interesado(self, text: str, total_messages: int) -> Tuple[bool, str]:
        """Detecta si el lead está interesado"""
        matches = []

        for pattern in KEYWORDS_INTERESADO:
            if re.search(pattern, text, re.IGNORECASE):
                matches.append(pattern.replace(r"\b", "").replace("\\", ""))

        if matches:
            return True, f"Keywords de interés: {', '.join(matches[:3])}"

        # También considerar interesado si tiene 3+ mensajes (conversación activa)
        if total_messages >= 3:
            return True, f"Conversación activa ({total_messages} mensajes)"

        return False, ""

    def _calculate_hot_score(self, text: str, messages: List[Dict]) -> float:
        """Calcula score de lead caliente (0.5-1.0)"""
        base_score = 0.5
        matches = 0

        for pattern in KEYWORDS_CALIENTE:
            if re.search(pattern, text, re.IGNORECASE):
                matches += 1

        # Más keywords = más caliente
        score = base_score + min(0.5, matches * 0.1)
        return min(1.0, score)

    def _calculate_interest_score(self, text: str, total_messages: int) -> float:
        """Calcula score de interés (0.2-0.5)"""
        base_score = 0.2
        matches = 0

        for pattern in KEYWORDS_INTERESADO:
            if re.search(pattern, text, re.IGNORECASE):
                matches += 1

        # Más keywords o más mensajes = más interés
        keyword_bonus = min(0.15, matches * 0.05)
        message_bonus = min(0.15, (total_messages - 2) * 0.05) if total_messages > 2 else 0

        return min(0.5, base_score + keyword_bonus + message_bonus)


def get_category_from_intent_score(intent_score: float, is_customer: bool = False) -> str:
    """
    Mapea un intent_score legacy al nuevo sistema de categorías.

    Args:
        intent_score: Score 0-1 del sistema anterior
        is_customer: Si es cliente

    Returns:
        Categoría string: "nuevo", "interesado", "caliente", "cliente"
    """
    if is_customer:
        return "cliente"
    if intent_score >= 0.5:
        return "caliente"
    if intent_score >= 0.2:
        return "interesado"
    return "nuevo"


def get_intent_score_from_category(category: str) -> float:
    """
    Mapea una categoría a un intent_score para compatibilidad legacy.

    Args:
        category: "nuevo", "interesado", "caliente", "cliente", "fantasma"

    Returns:
        Score 0-1
    """
    scores = {
        "nuevo": 0.1,
        "interesado": 0.35,
        "caliente": 0.7,
        "cliente": 1.0,
        "fantasma": 0.05,
    }
    return scores.get(category, 0.1)


def map_legacy_status_to_category(status: str) -> str:
    """
    Mapea status legacy (new, active, hot) a nuevas categorías.

    Args:
        status: "new", "active", "hot", "customer", "cold", "warm"

    Returns:
        Nueva categoría: "nuevo", "interesado", "caliente", "cliente"
    """
    mapping = {
        "new": "nuevo",
        "cold": "nuevo",
        "active": "interesado",
        "warm": "interesado",
        "hot": "caliente",
        "customer": "cliente",
    }
    return mapping.get(status.lower(), "nuevo")


def map_category_to_legacy_status(category: str) -> str:
    """
    Mapea nueva categoría a status legacy para compatibilidad.

    Args:
        category: "nuevo", "interesado", "caliente", "cliente", "fantasma"

    Returns:
        Status legacy: "new", "active", "hot", "customer"
    """
    mapping = {
        "nuevo": "new",
        "interesado": "active",
        "caliente": "hot",
        "cliente": "customer",
        "fantasma": "new",  # Fantasma vuelve a new para nurturing
    }
    return mapping.get(category.lower(), "new")


# Singleton
_lead_categorizer: Optional[LeadCategorizer] = None


def get_lead_categorizer() -> LeadCategorizer:
    """Obtener instancia singleton del categorizador"""
    global _lead_categorizer
    if _lead_categorizer is None:
        _lead_categorizer = LeadCategorizer()
    return _lead_categorizer
