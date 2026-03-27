"""
Frustration Detector v2.0 — Science-based, multilingual, gradated.

Design principles:
- Profanity alone is NOT frustration (filler word in es/ca informal speech)
- Profanity AMPLIFIES an existing frustration signal (×1.3)
- Multilingual: es / ca / en with extensible structure
- History analysis: escalation across last 3 messages adds +0.2
- Gradated output: level 0–3 (nothing / soft / moderate / escalate)
- Injection: factual note in Recalling block — NOT behavior instruction in user prompt
- Deduplication: working-string approach prevents substring and cross-lang double-counts
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Escalation patterns — always level 3 regardless of score
# ---------------------------------------------------------------------------

ESCALATION_PATTERNS = [
    # es
    "quiero hablar con una persona", "quiero hablar con alguien real",
    "ponme con un humano", "ponme con el creador",
    "hablar con una persona real",
    # ca
    "vull parlar amb una persona", "vull parlar amb algú real",
    "posa'm amb el creador",
    # en
    "let me talk to a real person", "i want a human",
    "put me through to a human",
]

# ---------------------------------------------------------------------------
# Signal catalogue — grouped by language and signal type
# Kept in order of specificity (longer/more-specific patterns FIRST within each list)
# so the dedup working-string approach eliminates sub-patterns correctly.
# ---------------------------------------------------------------------------

FRUSTRATION_SIGNALS: Dict[str, Dict[str, List[str]]] = {
    "es": {
        "explicit": [
            "estoy harto de", "estoy harta de",
            "estoy harto", "estoy harta",
            "estoy cansado de", "estoy cansada de",
            "eres un inútil", "eres inútil", "eres inutil",  # accented + unaccented
            "no sirves para nada", "no sirves",
            "harto de esperar", "harta de esperar",
            "nadie me responde", "me ignoran",
        ],
        "repetition": [
            "ya te lo he dicho", "ya te lo dije",  # longer first
            "te lo he dicho",
            "cuántas veces", "cuantas veces",
            "otra vez lo mismo", "de nuevo lo mismo",
            "te pregunté", "ya pregunté",
            "llevo días esperando", "llevo horas esperando",
            "días sin respuesta",
        ],
        "failure": [
            "no me entiendes", "no entiendes",
            "no me funciona", "no funciona",
            "no me estás ayudando", "no me ayudas",
            "no resuelves", "no puedes resolver",
            "es imposible contigo", "imposible hablar contigo",
        ],
    },
    "ca": {
        "explicit": [
            "estic fart de", "estic farta de",
            "estic fart", "estic farta",
            "ets inútil", "ets inutil",
            "no serveixes per res", "no serveixes",
            "porto dies esperant", "porto hores esperant",
        ],
        "repetition": [
            "ja t'ho he dit", "ja t'ho vaig dir",  # longer first — prevents "t'ho he dit" double
            "t'ho he dit",
            "quantes vegades",
            "una altra vegada el mateix",
            "ja vaig preguntar",
        ],
        "failure": [
            "no m'entens", "no entens",
            "no m'ajudes",
            "és impossible amb tu", "impossible parlar amb tu",
        ],
    },
    "en": {
        "explicit": [
            "i'm fed up with", "i am fed up with",
            "i'm fed up", "i am fed up",
            "you're useless", "you are useless",
            "this is ridiculous", "this is absurd",
            "i've been waiting for days", "been waiting for hours",
        ],
        "repetition": [
            "i already told you", "i already said",
            "told you multiple times",
            "how many times",
            "i said this before",
        ],
        "failure": [
            "you don't understand", "you do not understand",
            "this doesn't work", "this does not work",
            "no one is helping",
            "you can't help me", "you cannot help me",
        ],
    },
}

# Profanity words — AMPLIFY existing signal (×1.3), do NOT trigger alone
PROFANITY_AMPLIFIERS = [
    "joder", "hostia", "ostia", "coño", "cono", "puto", "puta", "mierda", "cojones", "leches",
    "collons", "merda", "cony",
    "fuck", "shit", "damn", "crap",
]

# Score weights by signal type
_WEIGHTS = {"explicit": 0.5, "repetition": 0.3, "failure": 0.2}

# "N veces / vegades / times" — explicit repetition count → strong signal
_COUNT_RE = re.compile(r"\b\d+\s+(?:veces|vegades|times)\b", re.IGNORECASE)


@dataclass
class FrustrationSignals:
    """Collected frustration signals from a conversation."""
    repeated_questions: int = 0
    negative_markers: int = 0
    caps_ratio: float = 0.0
    explicit_frustration: bool = False
    short_responses: int = 0
    question_marks_excess: int = 0
    # v2 additions
    level: int = 0                          # 0=none, 1=soft, 2=moderate, 3=escalate
    reasons: List[str] = field(default_factory=list)

    def get_score(self) -> float:
        """Calculate overall frustration score (0–1) — legacy compat."""
        score = 0.0
        score += min(self.repeated_questions * 0.2, 0.4)
        score += min(self.negative_markers * 0.1, 0.3)
        if self.caps_ratio > 0.5:
            score += 0.15
        if self.explicit_frustration:
            score += 0.5
        score += min(self.question_marks_excess * 0.05, 0.15)
        return min(score, 1.0)


class FrustrationDetector:
    """Detects user frustration in conversations — v2.0."""

    NEGATIVE_MARKERS = [
        r'\bno\b', r'\bnunca\b', r'\bnada\b', r'\bmal\b', r'\bpeor\b',
        r'\bproblema\b', r'\berror\b', r'\bfallo\b',
        r'\bdon\'?t\b', r'\bcan\'?t\b', r'\bwon\'?t\b', r'\bnot\b',
        r'\bbad\b', r'\bworse\b', r'\bproblem\b', r'\bwrong\b',
    ]

    def __init__(self):
        self._conversation_history: Dict[str, List[str]] = {}
        self._negative_compiled = [
            re.compile(p, re.IGNORECASE) for p in self.NEGATIVE_MARKERS
        ]

    def analyze_message(
        self,
        message: str,
        conversation_id: str,
        previous_messages: List[str] = None,
    ) -> Tuple[FrustrationSignals, float]:
        """
        Analyze a message for frustration signals.

        Returns (FrustrationSignals, score) — backward-compatible.
        signals.level (int 0–3) and signals.reasons carry v2 data.
        """
        if not isinstance(message, str):
            if isinstance(message, dict):
                message = message.get("text", "") or message.get("content", "") or str(message)
            else:
                message = str(message) if message else ""

        msg_lower = message.lower()
        signals = FrustrationSignals()
        score = 0.0
        reasons: List[str] = []

        # ── 1. Escalation check — always level 3 ──────────────────────────
        for pattern in ESCALATION_PATTERNS:
            if pattern in msg_lower:
                signals.explicit_frustration = True
                signals.level = 3
                signals.reasons = [f"escalation:{pattern}"]
                # Store history and return
                self._store_history(conversation_id, msg_lower)
                logger.info(f"[FRUSTRATION] level=3 escalation detected: {pattern}")
                return signals, 1.0

        # ── 2. Multilingual signal matching (dedup via working string) ─────
        # Processing order within each list: longer patterns first (they're defined that way)
        # so substring patterns don't double-fire on the same text.
        working = msg_lower  # consumed as patterns match
        for lang, categories in FRUSTRATION_SIGNALS.items():
            for sig_type, patterns in categories.items():
                weight = _WEIGHTS[sig_type]
                for pattern in patterns:
                    if pattern in working:
                        score += weight
                        reasons.append(f"{sig_type}:{pattern}")
                        if sig_type == "explicit":
                            signals.explicit_frustration = True
                        # Blank out matched span to prevent sub/cross-lang double-count
                        working = working.replace(pattern, " " * len(pattern), 1)

        # ── 3. Explicit repetition count ("3 veces", "4 times") ───────────
        if _COUNT_RE.search(msg_lower):
            score += 0.3
            reasons.append("explicit_count_N_times")

        # ── 4. Profanity amplifier (×1.3 only when other signals exist) ───
        has_profanity = any(
            re.search(r"\b" + re.escape(w) + r"\b", msg_lower)
            for w in PROFANITY_AMPLIFIERS
        )
        if has_profanity and score > 0:
            score *= 1.3
            reasons.append("profanity_amplifier")
        # profanity alone → score stays 0 → level 0

        # ── 5. History escalation (last 3 user messages) ───────────────────
        history: List[str] = []
        if conversation_id in self._conversation_history:
            history = self._conversation_history[conversation_id]
        if previous_messages:
            history = previous_messages

        if history and len(history) >= 2:
            recent = history[-3:]
            neg_count = 0
            for hist_msg in recent:
                hist_lower = hist_msg.lower()
                for lang_cats in FRUSTRATION_SIGNALS.values():
                    for patterns in lang_cats.values():
                        for p in patterns:
                            if p in hist_lower:
                                neg_count += 1
            if neg_count >= 2:
                score += 0.2
                reasons.append(f"escalating_{neg_count}_signals_in_history")

        # ── 6. Repeated questions in history ──────────────────────────────
        repeated = self._count_repeated_questions(message, history)
        signals.repeated_questions = repeated
        score += min(repeated * 0.2, 0.4)
        if repeated > 0:
            reasons.append(f"repeated_question_{repeated}x")

        # ── 7. CAPS detection (threshold 0.5 — short/decorative caps ignored) ──
        letters = [c for c in message if c.isalpha()]
        if len(letters) > 10:
            caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
            signals.caps_ratio = caps_ratio
            if caps_ratio > 0.5:
                score += 0.15
                reasons.append("CAPS")

        # ── 8. Repeated question marks ─────────────────────────────────────
        q_excess = message.count("?") - 1 if message.count("?") > 1 else 0
        signals.question_marks_excess = q_excess
        score += min(q_excess * 0.05, 0.15)
        if q_excess > 0:
            reasons.append(f"multi_qmarks_{q_excess}")

        # ── 9. Negative markers (reduced legacy weight) ───────────────────
        neg_markers = self._count_negative_markers(message)
        signals.negative_markers = neg_markers
        score += min(neg_markers * 0.05, 0.10)  # capped, halved vs v1

        score = min(score, 1.0)

        # ── 10. Determine level ────────────────────────────────────────────
        if score < 0.3:
            level = 0
        elif score < 0.6:
            level = 1
        elif score < 0.8:
            level = 2
        else:
            level = 3

        signals.level = level
        signals.reasons = reasons

        self._store_history(conversation_id, msg_lower)

        if level > 0:
            logger.info(
                f"[FRUSTRATION] level={level} score={score:.2f} reasons={reasons[:4]}"
            )

        return signals, score

    def _store_history(self, conversation_id: str, msg_lower: str) -> None:
        if conversation_id not in self._conversation_history:
            self._conversation_history[conversation_id] = []
        self._conversation_history[conversation_id].append(msg_lower.strip())
        if len(self._conversation_history[conversation_id]) > 20:
            self._conversation_history[conversation_id] = (
                self._conversation_history[conversation_id][-20:]
            )

    def _count_repeated_questions(self, message: str, history: List[str]) -> int:
        if not history:
            return 0
        msg_lower = message.lower().strip()
        msg_words = set(re.findall(r"\b\w+\b", msg_lower))
        stopwords = {
            "el", "la", "los", "las", "un", "una", "de", "en", "que", "y", "a",
            "the", "is", "it", "to", "and", "i",
        }
        msg_words -= stopwords
        price_keywords = {"precio", "cuesta", "coste", "vale", "euros", "dinero", "price", "cost"}
        msg_about_price = bool(msg_words & price_keywords)
        if len(msg_words) < 2:
            return 0
        repetitions = 0
        for prev_msg in history[-10:]:
            prev_words = set(re.findall(r"\b\w+\b", prev_msg.lower())) - stopwords
            if len(prev_words) < 2:
                continue
            if msg_about_price and bool(prev_words & price_keywords):
                repetitions += 1
                continue
            overlap = len(msg_words & prev_words) / max(len(msg_words), 1)
            if overlap > 0.4:
                repetitions += 1
        return repetitions

    def _count_negative_markers(self, message: str) -> int:
        count = 0
        for pattern in self._negative_compiled:
            count += len(pattern.findall(message))
        return count

    def clear_conversation(self, conversation_id: str) -> None:
        if conversation_id in self._conversation_history:
            del self._conversation_history[conversation_id]


# Singleton
_frustration_detector: Optional[FrustrationDetector] = None


def get_frustration_detector() -> FrustrationDetector:
    global _frustration_detector
    if _frustration_detector is None:
        _frustration_detector = FrustrationDetector()
    return _frustration_detector
