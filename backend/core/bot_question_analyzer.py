"""
Bot Question Analyzer — contexto conversacional para turn-taking.

Resuelve el *affirmation collapse*: cuando el lead responde con un mensaje corto
("Si", "Vale", "Ok", 👍, "clar") el LLM base sin contexto genera un ACK genérico
en vez de avanzar sobre lo que el bot preguntó.

Principio arquitectural (zero hardcoding):
    Las afirmaciones son descubiertas per-creator del content mining
    (vocab_meta DB). El módulo NUNCA contiene listas preasignadas por idioma.
    Si vocab_meta está vacío o no hay creator_id, el fallback es mínimo y
    universal: sólo emojis Unicode con semántica convencional cross-cultural.

    Consistente con los demás sistemas data-derived:
        - negation reducer          (vocab_meta.blacklist_phrases / negation)
        - pool auto-extraction      (pools per creator)
        - code-switching universal  (langdetect runtime)
        - intent-stratified few-shot (mined per creator/intent)

Entry points (stable API):
    get_bot_question_analyzer() -> BotQuestionAnalyzer
    is_short_affirmation(message: str, creator_id: str | None = None) -> bool
    QuestionType  (Enum de 7 valores: INTEREST, PURCHASE, INFORMATION,
                   CONFIRMATION, BOOKING, PAYMENT_METHOD, UNKNOWN)

Callsites productivos (gated por ENABLE_QUESTION_CONTEXT env, default true):
    core/dm/phases/context.py:803  — detection (escribe cognitive_metadata)
    core/dm/phases/context.py:1396 — injection (adds note if conf ≥ 0.7)

Dependencia (bloqueador para activación del flag en medición):
    `personality_docs.vocab_meta` DEBE contener la key `"affirmations"` con
    lista de tokens mined para el creator. El worker de onboarding
    (scripts/bootstrap_vocab_metadata.py o un nuevo extractor) es responsable
    de poblar esta key a partir de DMs + posts + comentarios del creator.
"""

from __future__ import annotations

import logging
import re
import threading
from collections import Counter
from enum import Enum
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
    interpretación de respuestas cortas del lead.

    Los patrones regex del bot son semánticos (no identity-dependent): no
    dependen del vocab del creator sino de la gramática de ventas. Por tanto
    NO se migran a vocab_meta — son patrones universales de la tarea."""

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


# ── Singleton thread-safe + métricas in-memory ────────────────────────────────

_analyzer_instance: Optional[BotQuestionAnalyzer] = None
_analyzer_lock = threading.Lock()
_METRICS: Counter = Counter()


def get_bot_question_analyzer() -> BotQuestionAnalyzer:
    """Singleton thread-safe. Compila los regex semánticos una única vez."""
    global _analyzer_instance
    if _analyzer_instance is None:
        with _analyzer_lock:
            if _analyzer_instance is None:
                _analyzer_instance = BotQuestionAnalyzer()
    return _analyzer_instance


def get_metrics() -> dict:
    """Exporta el Counter in-memory. Keys relevantes Prometheus-style:

        analyze.{purchase,payment,booking,interest,information,confirmation,
                 unknown,information_fallback,statement_interest}
        affirmation.{mined,fallback_emoji,empty,punct_only,too_long,whitespace,null}
        vocab_source.{mined,fallback,empty}

    Scrape target: Prometheus label
        bot_question_analyzer_vocab_source{source="mined"}   ← vocab_source.mined
        bot_question_analyzer_vocab_source{source="fallback"} ← vocab_source.fallback
        bot_question_analyzer_vocab_source{source="empty"}    ← vocab_source.empty
            (no creator_id o vocab_meta.affirmations vacío)
    """
    return dict(_METRICS)


def reset_metrics() -> None:
    """Helper para tests — reset del Counter global."""
    _METRICS.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# AFIRMACIONES — vocab descubierto runtime desde vocab_meta DB por creator
# ═══════════════════════════════════════════════════════════════════════════════

# FALLBACK UNIVERSAL — glifos Unicode con semántica convencional cross-cultural.
# NO son "lista por idioma": son caracteres Unicode convencionalmente afirmativos
# en la mayoría de culturas (thumbs-up, OK hand, check, applause, etc.). Se
# mantiene como único backstop cuando (a) no hay creator_id o (b) vocab_meta
# no contiene la key "affirmations". Observable via Prometheus source=fallback.
_UNIVERSAL_AFFIRMATION_EMOJI: frozenset = frozenset({
    "👍", "👌", "🙌", "✅", "💪", "💯", "👏", "🙏", "🤙",
})

_PUNCT_CHARS = "!.,?¡¿"
_PUNCT_ONLY_RE = re.compile(r'^[\s!.,?¡¿]+$')
_REPEAT_CHAR_RE = re.compile(r'(.)\1+')


def _normalize_elongation(word: str) -> str:
    """Colapsa repeticiones consecutivas del mismo carácter a 1 para tolerar
    alargamientos expresivos cuando el vocab mined incluye la forma base.
    Zero per-language: es una regla morfológica pura."""
    return _REPEAT_CHAR_RE.sub(r'\1', word)


def _load_affirmation_vocab(creator_id: Optional[str]) -> Optional[frozenset]:
    """Carga afirmaciones descubiertas de vocab_meta DB por creator.

    Devuelve:
        frozenset(str) — si hay afirmaciones mined para el creator.
        None           — si no hay creator_id, lookup falla, o key vacía.

    Reusa `services.calibration_loader._load_creator_vocab` que ya implementa
    DB → on-disk fallback con cache. El shape del vocab JSON es:
        {"blacklist_words": [...], "approved_terms": [...], ...,
         "affirmations": ["si","vale","ok","clar",...]}  ← esta PR introduce
                                                           el consumo de esta key.

    El worker de onboarding (scripts/bootstrap_vocab_metadata.py o el
    extractor dedicado de afirmaciones) es responsable de poblar la key
    "affirmations" mediante mining del corpus del creator (DMs + posts +
    comentarios) extrayendo tokens ≤15 chars de alta frecuencia en contexto
    post-pregunta. No es parte de este PR.
    """
    if not creator_id:
        return None
    try:
        from services.calibration_loader import _load_creator_vocab
    except ImportError as e:
        logger.debug("[BQA] calibration_loader unavailable (%s)", e)
        return None
    try:
        vocab = _load_creator_vocab(creator_id) or {}
    except Exception as e:
        logger.debug("[BQA] _load_creator_vocab(%s) failed: %s", creator_id, e)
        return None
    affirmations = vocab.get("affirmations")
    if not affirmations or not isinstance(affirmations, list):
        return None
    normalized = frozenset(
        str(a).lower().strip()
        for a in affirmations
        if a and isinstance(a, str)
    )
    return normalized or None


def is_short_affirmation(message: str, creator_id: Optional[str] = None) -> bool:
    """True si el mensaje es una afirmación corta del lead.

    Args:
        message: texto del lead (puede ser None, "", "   ", emoji, etc.)
        creator_id: slug del creator. Si se provee, se consulta vocab_meta
                    para obtener las afirmaciones descubiertas. Si es None o
                    el vocab no tiene afirmaciones, cae a fallback universal
                    (solo emojis Unicode convencionales).

    Observabilidad:
        Cada llamada incrementa `vocab_source.{mined,fallback,empty}` del
        Counter global para monitoreo Prometheus.

    Guards estructurales (independientes de idioma):
        * None / "" / "   " → False
        * Puntuación sola ("?", "..", "!!!") → False
        * >30 chars normalizados → False
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

    mined_vocab = _load_affirmation_vocab(creator_id)

    if mined_vocab:
        _METRICS["vocab_source.mined"] += 1
        if _match_against(msg, mined_vocab):
            _METRICS["affirmation.mined"] += 1
            return True
        # Descubierto pero no matched: caer a fallback universal (emojis).
        if msg in _UNIVERSAL_AFFIRMATION_EMOJI:
            _METRICS["affirmation.fallback_emoji"] += 1
            return True
        return False

    # No creator_id o vocab_meta sin "affirmations" → fallback universal.
    _METRICS["vocab_source.fallback" if creator_id is None else "vocab_source.empty"] += 1
    if msg in _UNIVERSAL_AFFIRMATION_EMOJI:
        _METRICS["affirmation.fallback_emoji"] += 1
        return True
    return False


def _match_against(msg: str, vocab: frozenset) -> bool:
    """Match de `msg` contra un vocab dado. Aplica lookup directo,
    normalización de elongación, y tolerancia multi-token (≤3 palabras
    todas afirmaciones). Es agnóstico al idioma del vocab."""
    if msg in vocab or _normalize_elongation(msg) in vocab:
        return True
    words = msg.split()
    if 0 < len(words) <= 3:
        cleaned = [w.strip(_PUNCT_CHARS) for w in words]
        non_empty = [w for w in cleaned if w]
        if not non_empty:
            return False
        if all((w in vocab) or (_normalize_elongation(w) in vocab) for w in non_empty):
            return True
    return False
