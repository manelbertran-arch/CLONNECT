"""
Bot Question Analyzer — contexto conversacional para turn-taking.

Resuelve el *affirmation collapse*: cuando el lead responde con un mensaje corto
("Si", "Vale", "Ok", 👍, "clar") el LLM base sin contexto genera un ACK genérico
en vez de avanzar sobre lo que el bot preguntó.

Entry points (stable API):
    get_bot_question_analyzer() -> BotQuestionAnalyzer
    is_short_affirmation(message: str, creator_id: str | None = None) -> bool
    QuestionType  (Enum de 7 valores: INTEREST, PURCHASE, INFORMATION,
                   CONFIRMATION, BOOKING, PAYMENT_METHOD, UNKNOWN)

Ejemplo:
    Bot: "¿Te gustaría saber más sobre el curso?"
    Lead: "si"
      └─ is_short_affirmation("si") → True
      └─ analyze_with_confidence(bot_msg) → (INTEREST, 0.85)
      └─ callsite injecta "El lead confirma interés en tus servicios." al prompt.

Callsites productivos (gated por ENABLE_QUESTION_CONTEXT env, default true):
    core/dm/phases/context.py:803  — detection (escribe cognitive_metadata)
    core/dm/phases/context.py:1396 — injection (adds note if conf ≥ 0.7)

Mejoras 2026-04-23 (forensic audit PR, flag OFF en Railway pendiente de medición):
    * Fix whitespace-only y puntuación-only devolviendo False (BUG-1/BUG-2).
    * Vocab data-derived desde backend/data/vocab/affirmation_vocab.json con
      cascada default + creator overrides + fallback a literal embedded.
    * Soporte emoji afirmaciones (👍, 👌, 🙌, ✅, ...) (BUG-3).
    * Normalización de alargamientos expresivos ("siiiii" → "si") (BUG-4).
    * Structured logging con prefijo [BQA] para observabilidad.
    * Counter in-memory por tipo (exportable vía get_metrics()).
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections import Counter
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple

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
    """Clasifica el último mensaje del bot en 7 tipos para anclar la
    interpretación de respuestas cortas del lead."""

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
        r'pod[ée]s contarme m[áa]s',
        r'quer[ée]s que te cuente',
    ]

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
        r'te apunt[áa]s',
        r'te interesa comprarlo',
        r'quieres el link',
        r'te env[íi]o el link',
        r'empezamos',
        r'comenzamos',
        r'cerramos',
    ]

    INFORMATION_PATTERNS = [
        r'qu[ée] aspecto',
        r'qu[ée] te gustar[íi]a',
        r'cu[ée]ntame m[áa]s',
        r'contame',
        r'qu[ée] necesitas',
        r'qu[ée] necesit[áa]s',
        r'en qu[ée] puedo',
        r'qu[ée] buscas',
        r'qu[ée] busc[áa]s',
        r'c[óo]mo puedo ayudarte',
        r'qu[ée] te interesa',
        r'qu[ée] te trae',
        r'd[íi]me m[áa]s',
        r'decime',
        r'qu[ée] problema',
        r'qu[ée] objetivo',
        r'qu[ée] meta',
    ]

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

    BOOKING_PATTERNS = [
        r'quieres agendar',
        r'quer[ée]s agendar',
        r'agendamos',
        r'reservamos',
        r'programamos',
        r'te va bien',
        r'cu[áa]ndo puedes',
        r'cu[áa]ndo pod[ée]s',
        r'hacemos una llamada',
        r'una videollamada',
    ]

    PAYMENT_PATTERNS = [
        r'c[óo]mo prefieres pagar',
        r'c[óo]mo prefer[íi]s pagar',
        r'qu[ée] m[ée]todo',
        r'tarjeta o',
        r'bizum o',
        r'transferencia o',
        r'cu[áa]l prefieres',
        r'cu[áa]l prefer[íi]s',
    ]

    # Statements sin `?` que esperan respuesta — "Ok" tras una oferta = INTEREST
    STATEMENT_EXPECTING_RESPONSE = [
        r'te (?:hago|ofrezco|puedo hacer).*descuento',
        r'(?:tienes|ten[ée]s).*descuento',
        r'son solo \d+',
        r'cuesta (?:solo )?\d+',
        r'el precio es',
        r'vale \d+',
        r'\d+\s*[€$]',
        r'el (?:programa|curso|taller) (?:incluye|tiene|consiste)',
        r'(?:incluye|tiene|consiste en)',
        r'funciona as[íi]',
        r'lo que hacemos es',
        r'b[áa]sicamente',
        r'en resumen',
        r'(?:podemos|podr[íi]amos)',
        r'te parece si',
        r'qu[ée] tal si',
        r'si quieres',
        r'si quer[ée]s',
        r'es perfecto para',
        r'te va a (?:encantar|servir|ayudar)',
        r'vas a (?:aprender|lograr|conseguir)',
    ]

    def __init__(self):
        self._compiled_patterns = {
            QuestionType.INTEREST: [re.compile(p, re.IGNORECASE) for p in self.INTEREST_PATTERNS],
            QuestionType.PURCHASE: [re.compile(p, re.IGNORECASE) for p in self.PURCHASE_PATTERNS],
            QuestionType.INFORMATION: [re.compile(p, re.IGNORECASE) for p in self.INFORMATION_PATTERNS],
            QuestionType.CONFIRMATION: [re.compile(p, re.IGNORECASE) for p in self.CONFIRMATION_PATTERNS],
            QuestionType.BOOKING: [re.compile(p, re.IGNORECASE) for p in self.BOOKING_PATTERNS],
            QuestionType.PAYMENT_METHOD: [re.compile(p, re.IGNORECASE) for p in self.PAYMENT_PATTERNS],
        }
        self._statement_patterns = [re.compile(p, re.IGNORECASE) for p in self.STATEMENT_EXPECTING_RESPONSE]

    def analyze(self, bot_message: str) -> QuestionType:
        if not bot_message:
            return QuestionType.UNKNOWN
        has_question = '?' in bot_message
        for question_type in [
            QuestionType.PURCHASE,
            QuestionType.PAYMENT_METHOD,
            QuestionType.BOOKING,
            QuestionType.INTEREST,
            QuestionType.INFORMATION,
            QuestionType.CONFIRMATION,
        ]:
            for pattern in self._compiled_patterns.get(question_type, []):
                if pattern.search(bot_message):
                    _METRICS["analyze." + question_type.value] += 1
                    logger.debug("[BQA] '%s...' → %s", bot_message[:50], question_type.value)
                    return question_type
        if has_question:
            _METRICS["analyze.information_fallback"] += 1
            return QuestionType.INFORMATION
        for pattern in self._statement_patterns:
            if pattern.search(bot_message):
                _METRICS["analyze.statement_interest"] += 1
                logger.debug("[BQA] statement expecting response → INTEREST")
                return QuestionType.INTEREST
        _METRICS["analyze.unknown"] += 1
        return QuestionType.UNKNOWN

    def analyze_with_confidence(self, bot_message: str) -> Tuple[QuestionType, float]:
        question_type = self.analyze(bot_message)
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


# ── Singleton (thread-safe) ────────────────────────────────────────────────────

_analyzer_instance: Optional[BotQuestionAnalyzer] = None
_analyzer_lock = threading.Lock()
_METRICS: Counter = Counter()


def get_bot_question_analyzer() -> BotQuestionAnalyzer:
    """Singleton thread-safe. Compila los 98 regex una única vez."""
    global _analyzer_instance
    if _analyzer_instance is None:
        with _analyzer_lock:
            if _analyzer_instance is None:
                _analyzer_instance = BotQuestionAnalyzer()
    return _analyzer_instance


def get_metrics() -> dict:
    """Exporta el counter in-memory (para /metrics endpoint o logs)."""
    return dict(_METRICS)


# ═══════════════════════════════════════════════════════════════════════════════
# AFIRMACIONES — vocab data-derived con cascada (DB / JSON / embedded default)
# ═══════════════════════════════════════════════════════════════════════════════

# Embedded fallback — idéntico al literal histórico (backward compat garantizado
# si el JSON no existe o falla la carga). NO editar aquí: editar el JSON.
_EMBEDDED_AFFIRMATION_WORDS = frozenset({
    # Español
    'si', 'sí', 'ok', 'okay', 'okey', 'vale', 'dale', 'claro',
    'bueno', 'bien', 'perfecto', 'genial', 'venga', 'va',
    'de acuerdo', 'por supuesto', 'obvio', 'seguro', 'ya',
    'eso', 'exacto', 'correcto', 'así es', 'afirmativo',
    'entendido', 'entiendo', 'comprendo', 'listo', 'hecho',
    # Catalán
    'clar', 'fet', 'entesos', 'perfecte', 'bé', 'molt bé', 'moltbé',
    'sip', 'oka', 'okaaa', 'okaa', "d'acord", 'endavant', 'vinga',
    'siii', 'siiii', 'top', 'va bé', 'entenc',
    # Italiano
    'sì', 'certo', 'perfetto', 'va bene', "d'accordo", 'capito',
    'esatto', 'giusto', 'benissimo', 'fatto',
    # English
    'yes', 'sure', 'alright', 'right', 'yep', 'yup', 'cool', 'fine',
    'got it', 'sounds good', 'perfect', 'done',
    # Emojis
    '👍', '👌', '🙌', '✅', '💪', '🙏', '🤙', '💯', '👏',
})

# Backward-compat export — código legacy que importe AFFIRMATION_WORDS sigue
# funcionando (con el set embedded, sin overrides de JSON).
AFFIRMATION_WORDS = _EMBEDDED_AFFIRMATION_WORDS


_VOCAB_PATH = Path(__file__).resolve().parent.parent / "data" / "vocab" / "affirmation_vocab.json"
_vocab_cache: dict = {}


def _load_vocab(creator_id: Optional[str] = None) -> frozenset:
    """Carga el vocab desde JSON con fallback al embedded.

    Cascada:
        1. Cache por creator_id (o "__default__").
        2. JSON en backend/data/vocab/affirmation_vocab.json.
           * `default` siempre se incluye.
           * `creators[creator_id].extras` extiende por idioma (opcional).
        3. Fallback: _EMBEDDED_AFFIRMATION_WORDS (vocab original literal).
    """
    key = creator_id or "__default__"
    if key in _vocab_cache:
        return _vocab_cache[key]

    try:
        if _VOCAB_PATH.is_file():
            with _VOCAB_PATH.open(encoding="utf-8") as f:
                data = json.load(f)
            words = set()
            default_section = data.get("default", {})
            for lang, items in default_section.items():
                if isinstance(items, list):
                    words.update(items)
            if creator_id:
                creator_section = data.get("creators", {}).get(creator_id, {})
                extras = creator_section.get("extras", {})
                for lang, items in extras.items():
                    if isinstance(items, list):
                        words.update(items)
            if words:
                result = frozenset(w.lower() for w in words)
                _vocab_cache[key] = result
                return result
    except (OSError, ValueError, TypeError) as e:
        logger.warning("[BQA] vocab JSON load failed (%s), falling back to embedded", e)

    _vocab_cache[key] = _EMBEDDED_AFFIRMATION_WORDS
    return _EMBEDDED_AFFIRMATION_WORDS


_PUNCT_CHARS = "!.,?¡¿"
_PUNCT_ONLY_RE = re.compile(r'^[\s!.,?¡¿]+$')
_REPEAT_CHAR_RE = re.compile(r'(.)\1+')


def _normalize_elongation(word: str) -> str:
    """Colapsa repeticiones consecutivas del mismo carácter a 1
    ('sii'/'siiiii' → 'si', 'okkk' → 'ok', 'perfeeecto' → 'perfecto').

    La lookup directa `msg in vocab` se hace ANTES que esta función, así que
    palabras legítimas con letras dobles (p.ej. 'cool') se matchean sin
    normalizar y no se ven afectadas. Sólo se usa como fallback."""
    return _REPEAT_CHAR_RE.sub(r'\1', word)


def is_short_affirmation(message: str, creator_id: Optional[str] = None) -> bool:
    """True si el mensaje es una afirmación corta.

    Args:
        message: texto del lead (puede ser None, "", "   ", emoji, etc.)
        creator_id: opcional, para usar vocab con overrides per-creator.

    Reglas:
        * None/""/"   "/"?"/"..."/"!!!" → False (punct-only/whitespace-only).
        * Mensajes >30 chars normalizados → False.
        * Mensaje completo normalizado o elongado-normalizado en vocab → True.
        * 1-3 palabras, cada una normalizada y elongada, en vocab → True.
        * Resto → False.
    """
    if not message:
        _METRICS["affirmation.null"] += 1
        return False

    msg = message.lower().strip()
    if not msg:
        _METRICS["affirmation.whitespace"] += 1
        return False
    if _PUNCT_ONLY_RE.match(msg):
        _METRICS["affirmation.punct_only"] += 1
        return False
    if len(msg) > 30:
        _METRICS["affirmation.too_long"] += 1
        return False

    vocab = _load_vocab(creator_id)

    # Match directo (incluye emojis y multi-word como "va bene", "got it").
    if msg in vocab or _normalize_elongation(msg) in vocab:
        _METRICS["affirmation.direct"] += 1
        return True

    # Split por espacio y tolerar hasta 3 tokens no-vacíos que sean todos afirmación.
    words = msg.split()
    if 0 < len(words) <= 3:
        cleaned = [w.strip(_PUNCT_CHARS) for w in words]
        non_empty = [w for w in cleaned if w]
        if not non_empty:
            _METRICS["affirmation.punct_only"] += 1
            return False
        # Cada token debe resolver a afirmación (directo o tras normalizar elongación).
        if all((w in vocab) or (_normalize_elongation(w) in vocab) for w in non_empty):
            _METRICS["affirmation.multi_token"] += 1
            return True

    return False
