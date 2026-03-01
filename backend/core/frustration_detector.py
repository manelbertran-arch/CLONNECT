"""
Frustration Detector v1.7.0 - Detects user frustration patterns.

Analyzes messages to detect signs of frustration like:
- Repeated questions (user asked same thing multiple times)
- Negative sentiment markers
- Explicit frustration expressions
- Message length decrease (giving up)
- ALL CAPS usage
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FrustrationSignals:
    """Collected frustration signals from a conversation."""
    repeated_questions: int = 0
    negative_markers: int = 0
    caps_ratio: float = 0.0
    explicit_frustration: bool = False
    short_responses: int = 0
    question_marks_excess: int = 0

    def get_score(self) -> float:
        """Calculate overall frustration score (0-1)."""
        score = 0.0

        # Repeated questions are strong signal
        score += min(self.repeated_questions * 0.2, 0.4)

        # Negative markers
        score += min(self.negative_markers * 0.1, 0.3)

        # CAPS usage
        if self.caps_ratio > 0.3:
            score += 0.15

        # Explicit frustration is very strong (BUG-08: increased from 0.3 to 0.5)
        if self.explicit_frustration:
            score += 0.5

        # Multiple question marks
        score += min(self.question_marks_excess * 0.05, 0.15)

        return min(score, 1.0)


class FrustrationDetector:
    """Detects user frustration in conversations."""

    # Explicit frustration expressions
    FRUSTRATION_PATTERNS = [
        r'\b(?:no\s+(?:entiendes?|me\s+entiendes?))\b',
        r'\b(?:ya\s+te\s+(?:dije|pregunte|pregunt[eé]))\b',
        r'\b(?:ya\s+(?:te\s+)?(?:lo\s+)?pregunt[eé])\b',
        r'\b(?:te\s+pregunt[eé]\s+\d+\s+veces?)\b',
        r'\b(?:otra\s+vez|de\s+nuevo)\b',
        r'\b(?:esto\s+no\s+(?:funciona|sirve|ayuda))\b',
        r'\b(?:no\s+funciona)\b',  # BUG-08: also match without "esto"
        r'\b(?:no\s+(?:me\s+)?(?:ayudas?|sirves?))\b',
        r'\b(?:que\s+(?:pesado|molesto|frustrante))\b',
        r'\b(?:me\s+(?:cansas?|hartas?))\b',
        r'\b(?:dejalo|olvidalo|paso)\b',
        r'\b(?:inutil|tonto|estupido)\b',
        r'\b(?:no\s+(?:vale|sirve)\s+(?:la\s+)?pena)\b',
        r'\b(?:es\s+imposible)\b',
        r'\b(?:sin\s+historias?)\b',
        # BUG-08: profanity and strong frustration markers
        r'\b(?:mierda|hostia|joder|coño|puto|puta)\b',
        r'\b(?:estoy\s+(?:harto|cansado|harta|cansada))\b',
        r'\b(?:harto\s+de\s+(?:esperar|esto|todo))\b',
        r'\b(?:nadie\s+me\s+responde)\b',
        r'\b(?:me\s+ignoran|me\s+ignoráis)\b',
        r'\b(?:llevas?\s+(?:\d+\s+)?(?:horas?|d[ií]as?)\s+sin\s+responder)\b',
        r'\b(?:dios\s+m[ií]o|por\s+favor\s+responde)\b',
        # English patterns
        r'\b(?:you\s+don\'?t\s+understand)\b',
        r'\b(?:i\s+(?:already|just)\s+(?:said|asked|told))\b',
        r'\b(?:this\s+(?:doesn\'?t|does\s+not)\s+(?:work|help))\b',
        r'\b(?:useless|stupid|annoying)\b',
        r'\b(?:forget\s+it|never\s*mind)\b',
    ]

    # Negative sentiment markers
    NEGATIVE_MARKERS = [
        r'\bno\b', r'\bnunca\b', r'\bnada\b', r'\bmal\b', r'\bpeor\b',
        r'\bproblema\b', r'\berror\b', r'\bfallo\b', r'\bimpossible\b',
        r'\bdificil\b', r'\bcomplicado\b', r'\bconfuso\b',
        r'\bdon\'?t\b', r'\bcan\'?t\b', r'\bwon\'?t\b', r'\bnot\b',
        r'\bbad\b', r'\bworse\b', r'\bproblem\b', r'\bwrong\b',
    ]

    def __init__(self):
        self._conversation_history: Dict[str, List[str]] = {}
        self._frustration_compiled = [re.compile(p, re.IGNORECASE) for p in self.FRUSTRATION_PATTERNS]
        self._negative_compiled = [re.compile(p, re.IGNORECASE) for p in self.NEGATIVE_MARKERS]

    def analyze_message(
        self,
        message: str,
        conversation_id: str,
        previous_messages: List[str] = None
    ) -> Tuple[FrustrationSignals, float]:
        """
        Analyze a message for frustration signals.

        Args:
            message: The current user message
            conversation_id: Unique conversation identifier
            previous_messages: List of previous user messages in conversation

        Returns:
            Tuple of (FrustrationSignals, frustration_score)
        """
        # DEFENSIVE: Ensure message is a string
        if not isinstance(message, str):
            if isinstance(message, dict):
                message = message.get('text', '') or message.get('content', '') or str(message)
            else:
                message = str(message) if message else ""

        signals = FrustrationSignals()

        # Store message history
        if conversation_id not in self._conversation_history:
            self._conversation_history[conversation_id] = []

        history = self._conversation_history[conversation_id]
        if previous_messages:
            history = previous_messages

        # Check for repeated questions
        signals.repeated_questions = self._count_repeated_questions(message, history)

        # Check for negative markers
        signals.negative_markers = self._count_negative_markers(message)

        # Check CAPS ratio
        signals.caps_ratio = self._calculate_caps_ratio(message)

        # Check for explicit frustration
        signals.explicit_frustration = self._has_explicit_frustration(message)

        # Check for excessive question marks
        signals.question_marks_excess = message.count('?') - 1 if message.count('?') > 1 else 0

        # Store current message
        self._conversation_history[conversation_id].append(message.lower().strip())

        # Limit history size
        if len(self._conversation_history[conversation_id]) > 20:
            self._conversation_history[conversation_id] = self._conversation_history[conversation_id][-20:]

        score = signals.get_score()

        if score > 0.3:
            logger.info(f"[FRUSTRATION] Detected frustration (score={score:.2f}): {signals}")

        return signals, score

    def _count_repeated_questions(self, message: str, history: List[str]) -> int:
        """Count how many times similar content was asked before."""
        if not history:
            return 0

        msg_lower = message.lower().strip()
        msg_words = set(re.findall(r'\b\w+\b', msg_lower))

        # Remove common words
        stopwords = {'el', 'la', 'los', 'las', 'un', 'una', 'de', 'en', 'que', 'y', 'a', 'the', 'is', 'it', 'to', 'and'}
        msg_words -= stopwords

        # Also check for semantic similarity on key topics
        price_keywords = {'precio', 'cuesta', 'coste', 'vale', 'euros', 'dinero', 'price', 'cost'}
        msg_about_price = bool(msg_words & price_keywords)

        if len(msg_words) < 2:
            return 0

        repetitions = 0
        for prev_msg in history[-10:]:  # Check last 10 messages
            prev_words = set(re.findall(r'\b\w+\b', prev_msg.lower()))
            prev_words -= stopwords

            if len(prev_words) < 2:
                continue

            # Check semantic similarity for price topic
            prev_about_price = bool(prev_words & price_keywords)
            if msg_about_price and prev_about_price:
                repetitions += 1
                continue

            # Calculate word overlap
            overlap = len(msg_words & prev_words) / max(len(msg_words), 1)
            if overlap > 0.4:  # More than 40% word overlap (lowered threshold)
                repetitions += 1

        return repetitions

    def _count_negative_markers(self, message: str) -> int:
        """Count negative sentiment markers in message."""
        count = 0
        for pattern in self._negative_compiled:
            count += len(pattern.findall(message))
        return count

    def _calculate_caps_ratio(self, message: str) -> float:
        """Calculate ratio of uppercase letters."""
        letters = [c for c in message if c.isalpha()]
        if not letters:
            return 0.0
        uppercase = sum(1 for c in letters if c.isupper())
        return uppercase / len(letters)

    def _has_explicit_frustration(self, message: str) -> bool:
        """Check for explicit frustration expressions."""
        for pattern in self._frustration_compiled:
            if pattern.search(message):
                return True
        return False

    def get_frustration_context(self, score: float, signals: FrustrationSignals) -> str:
        """
        Generate context for the LLM based on frustration level.

        Returns instructions for the LLM on how to respond to frustrated user.
        """
        if score < 0.2:
            return ""

        context_parts = ["=== ALERTA DE FRUSTRACION ==="]

        if score >= 0.6:
            context_parts.append("NIVEL: ALTO - El usuario esta MUY frustrado")
            context_parts.append("ACCION REQUERIDA:")
            context_parts.append("- Disculpate brevemente y reconoce la frustracion")
            context_parts.append("- Responde de forma DIRECTA y CONCRETA")
            context_parts.append("- Ofrece hablar con el creador si no puedes resolver")
            context_parts.append("- NO hagas mas preguntas, da soluciones")
        elif score >= 0.4:
            context_parts.append("NIVEL: MEDIO - El usuario muestra signos de frustracion")
            context_parts.append("ACCION REQUERIDA:")
            context_parts.append("- Se mas directo en tus respuestas")
            context_parts.append("- Evita respuestas largas o evasivas")
            context_parts.append("- Si ya preguntaste algo, no lo repitas")
        else:
            context_parts.append("NIVEL: BAJO - Posible frustracion incipiente")
            context_parts.append("SUGERENCIA: Mantén respuestas claras y concisas")

        # Add specific signals
        if signals.repeated_questions > 0:
            context_parts.append(f"\nNOTA: El usuario ha repetido su pregunta {signals.repeated_questions} vez(ces). Responde directamente.")

        if signals.explicit_frustration:
            context_parts.append("\nNOTA: El usuario ha expresado frustracion explicita. Muestra empatia.")

        return "\n".join(context_parts)

    def clear_conversation(self, conversation_id: str) -> None:
        """Clear history for a conversation."""
        if conversation_id in self._conversation_history:
            del self._conversation_history[conversation_id]


# Singleton instance
_frustration_detector: Optional[FrustrationDetector] = None


def get_frustration_detector() -> FrustrationDetector:
    """Get singleton FrustrationDetector instance."""
    global _frustration_detector
    if _frustration_detector is None:
        _frustration_detector = FrustrationDetector()
    return _frustration_detector
