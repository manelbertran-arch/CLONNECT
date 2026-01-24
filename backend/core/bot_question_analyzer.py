"""
Bot Question Analyzer - Analiza el contexto de la última pregunta del bot.

Este módulo permite clasificar mejor los mensajes cortos del usuario
("Si", "Vale", "Ok") basándose en qué tipo de pregunta hizo el bot.

Ejemplo:
    Bot: "¿Te gustaría saber más sobre el curso?"
    User: "Si"
    → Sin contexto: ACKNOWLEDGMENT (genérico)
    → Con contexto: INTEREST_SOFT (quiere saber más)
"""

import logging
import re
from typing import Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class QuestionType(Enum):
    """Tipos de pregunta que puede hacer el bot."""
    INTEREST = "interest"           # ¿Quieres saber más?
    PURCHASE = "purchase"           # ¿Quieres comprarlo?
    INFORMATION = "information"     # ¿Qué te gustaría saber?
    CONFIRMATION = "confirmation"   # ¿Te quedó claro?
    BOOKING = "booking"             # ¿Quieres agendar una llamada?
    PAYMENT_METHOD = "payment"      # ¿Cómo prefieres pagar?
    UNKNOWN = "unknown"             # No se detectó tipo de pregunta


class BotQuestionAnalyzer:
    """
    Analiza el último mensaje del bot para entender qué tipo de
    respuesta espera y clasificar mejor los mensajes cortos del usuario.
    """

    # Patrones que indican pregunta de INTERÉS (quiere saber más)
    INTEREST_PATTERNS = [
        r'te gustar[íi]a saber m[áa]s',
        r'quer[ée]s saber m[áa]s',
        r'te interesa',
        r'quieres que te cuente',
        r'te paso info',
        r'te explico',
        r'te cuento m[áa]s',
        r'quieres m[áa]s info',
        r'te interesar[íi]a',
        r'te gustar[íi]a conocer',
        r'quieres conocer',
        r'te muestro',
        r'te ense[ñn]o',
        r'saber m[áa]s sobre',
        r'conocer m[áa]s',
        r'te cuento sobre',
        r'te hablo de',
        r'te comento',
        r'pod[ée]s contarme m[áa]s',  # voseo
        r'quer[ée]s que te cuente',
    ]

    # Patrones que indican pregunta de COMPRA
    PURCHASE_PATTERNS = [
        r'te paso el link',
        r'quieres comprarlo',
        r'lo quieres',
        r'te lo reservo',
        r'procedemos',
        r'te mando el link',
        r'hacemos el pago',
        r'confirmamos',
        r'lo compramos',
        r'te apuntas',
        r'te apunt[áa]s',  # voseo
        r'te interesa comprarlo',
        r'quieres el link',
        r'te env[íi]o el link',
        r'empezamos',
        r'comenzamos',
        r'cerramos',
    ]

    # Patrones que indican pregunta de INFORMACIÓN (abierta)
    INFORMATION_PATTERNS = [
        r'qu[ée] aspecto',
        r'qu[ée] te gustar[íi]a',
        r'cu[ée]ntame m[áa]s',
        r'contame',  # voseo
        r'qu[ée] necesitas',
        r'qu[ée] necesit[áa]s',  # voseo
        r'en qu[ée] puedo',
        r'qu[ée] buscas',
        r'qu[ée] busc[áa]s',  # voseo
        r'c[óo]mo puedo ayudarte',
        r'qu[ée] te interesa',
        r'qu[ée] te trae',
        r'd[íi]me m[áa]s',
        r'decime',  # voseo
        r'qu[ée] problema',
        r'qu[ée] objetivo',
        r'qu[ée] meta',
    ]

    # Patrones de CONFIRMACIÓN
    CONFIRMATION_PATTERNS = [
        r'te qued[óo] claro',
        r'entendiste',
        r'entendido',
        r'alguna duda',
        r'alguna pregunta',
        r'todo bien',
        r'est[áa] claro',
        r'comprend[ée]s',
    ]

    # Patrones de BOOKING/AGENDAR
    BOOKING_PATTERNS = [
        r'quieres agendar',
        r'quer[ée]s agendar',  # voseo
        r'agendamos',
        r'reservamos',
        r'programamos',
        r'te va bien',
        r'cu[áa]ndo puedes',
        r'cu[áa]ndo pod[ée]s',  # voseo
        r'hacemos una llamada',
        r'una videollamada',
    ]

    # Patrones de MÉTODO DE PAGO
    PAYMENT_PATTERNS = [
        r'c[óo]mo prefieres pagar',
        r'c[óo]mo prefer[íi]s pagar',  # voseo
        r'qu[ée] m[ée]todo',
        r'tarjeta o',
        r'bizum o',
        r'transferencia o',
        r'cu[áa]l prefieres',
        r'cu[áa]l prefer[íi]s',  # voseo
    ]

    # === FIX CONTINUIDAD: Statements que esperan respuesta (no tienen ?) ===
    # Cuando el bot hace una oferta o explicación, "Ok" significa interés
    STATEMENT_EXPECTING_RESPONSE = [
        # Ofertas / Descuentos
        r'te (?:hago|ofrezco|puedo hacer).*descuento',
        r'(?:tienes|ten[ée]s).*descuento',
        r'son solo \d+',
        r'cuesta (?:solo )?\d+',
        r'el precio es',
        r'vale \d+',
        r'\d+\s*[€$]',
        # Explicaciones que esperan feedback
        r'el (?:programa|curso|taller) (?:incluye|tiene|consiste)',
        r'(?:incluye|tiene|consiste en)',
        r'funciona as[íi]',
        r'lo que hacemos es',
        r'b[áa]sicamente',
        r'en resumen',
        # Propuestas
        r'(?:podemos|podr[íi]amos)',
        r'te parece si',
        r'qu[ée] tal si',
        r'si quieres',
        r'si quer[ée]s',  # voseo
        # Afirmaciones que esperan reacción
        r'es perfecto para',
        r'te va a (?:encantar|servir|ayudar)',
        r'vas a (?:aprender|lograr|conseguir)',
    ]

    def __init__(self):
        # Compilar patrones para eficiencia
        self._compiled_patterns = {
            QuestionType.INTEREST: [re.compile(p, re.IGNORECASE) for p in self.INTEREST_PATTERNS],
            QuestionType.PURCHASE: [re.compile(p, re.IGNORECASE) for p in self.PURCHASE_PATTERNS],
            QuestionType.INFORMATION: [re.compile(p, re.IGNORECASE) for p in self.INFORMATION_PATTERNS],
            QuestionType.CONFIRMATION: [re.compile(p, re.IGNORECASE) for p in self.CONFIRMATION_PATTERNS],
            QuestionType.BOOKING: [re.compile(p, re.IGNORECASE) for p in self.BOOKING_PATTERNS],
            QuestionType.PAYMENT_METHOD: [re.compile(p, re.IGNORECASE) for p in self.PAYMENT_PATTERNS],
        }
        # Patrones de statements que esperan respuesta (→ INTEREST)
        self._statement_patterns = [re.compile(p, re.IGNORECASE) for p in self.STATEMENT_EXPECTING_RESPONSE]

    def analyze(self, bot_message: str) -> QuestionType:
        """
        Analiza el mensaje del bot y retorna el tipo de pregunta.

        Args:
            bot_message: El último mensaje enviado por el bot

        Returns:
            QuestionType indicando qué tipo de respuesta espera el bot
        """
        if not bot_message:
            return QuestionType.UNKNOWN

        # Verificar si el mensaje contiene una pregunta
        has_question = '?' in bot_message

        # Buscar patrones en orden de prioridad
        # PURCHASE tiene prioridad sobre INTEREST (si hay link = compra)
        for question_type in [
            QuestionType.PURCHASE,
            QuestionType.PAYMENT_METHOD,
            QuestionType.BOOKING,
            QuestionType.INTEREST,
            QuestionType.INFORMATION,
            QuestionType.CONFIRMATION,
        ]:
            patterns = self._compiled_patterns.get(question_type, [])
            for pattern in patterns:
                if pattern.search(bot_message):
                    logger.debug(f"BotQuestionAnalyzer: '{bot_message[:50]}...' → {question_type.value}")
                    return question_type

        # Si tiene signo de pregunta pero no matchea patrones, es pregunta genérica
        if has_question:
            return QuestionType.INFORMATION

        # === FIX CONTINUIDAD: Buscar statements que esperan respuesta ===
        # Si no hay pregunta (?) pero hay statement que espera feedback → INTEREST
        for pattern in self._statement_patterns:
            if pattern.search(bot_message):
                logger.debug(f"BotQuestionAnalyzer: Statement expecting response detected → INTEREST")
                return QuestionType.INTEREST

        return QuestionType.UNKNOWN

    def analyze_with_confidence(self, bot_message: str) -> Tuple[QuestionType, float]:
        """
        Analiza el mensaje y retorna tipo + confianza.

        Args:
            bot_message: El último mensaje enviado por el bot

        Returns:
            Tuple de (QuestionType, confidence)
        """
        question_type = self.analyze(bot_message)

        # Asignar confianza basada en el tipo
        confidence_map = {
            QuestionType.PURCHASE: 0.92,
            QuestionType.PAYMENT_METHOD: 0.90,
            QuestionType.BOOKING: 0.88,
            QuestionType.INTEREST: 0.85,
            QuestionType.INFORMATION: 0.75,
            QuestionType.CONFIRMATION: 0.70,
            QuestionType.UNKNOWN: 0.50,
        }

        return question_type, confidence_map.get(question_type, 0.50)


# Singleton para evitar recompilar patrones
_analyzer_instance = None


def get_bot_question_analyzer() -> BotQuestionAnalyzer:
    """Obtiene instancia singleton del analizador."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = BotQuestionAnalyzer()
    return _analyzer_instance


# ═══════════════════════════════════════════════════════════════════════════════
# UTILIDADES PARA AFIRMACIONES
# ═══════════════════════════════════════════════════════════════════════════════

# Palabras que son afirmaciones simples
AFFIRMATION_WORDS = {
    'si', 'sí', 'ok', 'okay', 'okey', 'vale', 'dale', 'claro',
    'bueno', 'bien', 'perfecto', 'genial', 'venga', 'va',
    'de acuerdo', 'por supuesto', 'obvio', 'seguro', 'ya',
    'eso', 'exacto', 'correcto', 'así es', 'afirmativo',
    'entendido', 'entiendo', 'comprendo', 'listo', 'hecho',
    # Variantes con signos
    'si!', 'sí!', 'ok!', 'vale!', 'dale!', 'claro!',
    'si.', 'sí.', 'ok.', 'vale.', 'claro.', 'entendido.',
}


def is_short_affirmation(message: str) -> bool:
    """
    Verifica si un mensaje es una afirmación corta.

    Args:
        message: El mensaje del usuario

    Returns:
        True si es una afirmación corta como "Si", "Vale", "Ok"
    """
    if not message:
        return False

    # Normalizar
    msg = message.lower().strip()

    # Muy largo no puede ser afirmación simple
    if len(msg) > 30:
        return False

    # Verificar si es exactamente una afirmación
    if msg in AFFIRMATION_WORDS:
        return True

    # Verificar si son 1-3 palabras que son todas afirmaciones
    words = msg.split()
    if len(words) <= 3:
        # Limpiar puntuación de cada palabra
        cleaned_words = [w.rstrip('!.,?') for w in words]
        if all(w in AFFIRMATION_WORDS or w == '' for w in cleaned_words):
            return True

    return False
