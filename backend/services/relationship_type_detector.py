"""RelationshipTypeDetector service for classifying relationships.

Analyzes conversation content to determine relationship type with confidence score.

Part of RELATIONSHIP-DNA feature.
"""

import logging
from typing import Dict, List

from models.relationship_dna import RelationshipType

logger = logging.getLogger(__name__)


# Scoring weights for different indicators
INDICATORS = {
    RelationshipType.INTIMA.value: {
        "words": {
            "amor": 5, "te amo": 5, "te quiero": 4, "mi vida": 4,
            "cariño": 4, "preciosa": 4, "precioso": 4, "bebe": 3,
            "te extraño": 4, "extraño": 2,
        },
        "emojis": {"💙": 3, "❤️": 3, "😘": 2, "💋": 2, "🥰": 2, "💕": 2},
        "threshold": 10,
    },
    RelationshipType.AMISTAD_CERCANA.value: {
        "words": {
            "hermano": 3, "bro": 3, "brother": 3, "compa": 2,
            "circulo": 2, "retiro": 2, "meditacion": 2, "vipassana": 2,
            "transformador": 2, "espiritual": 2,
        },
        "emojis": {"🙏🏽": 2, "🙏": 2, "💪🏽": 2, "💪": 2, "🫂": 2, "🔥": 1},
        "threshold": 6,
    },
    RelationshipType.AMISTAD_CASUAL.value: {
        "words": {
            "crack": 3, "tio": 2, "maquina": 2, "genial": 1,
            "guay": 1, "mola": 1, "flipante": 1,
        },
        "emojis": {"😄": 1, "👍": 1, "🙌": 1, "💯": 1},
        "threshold": 4,
    },
    RelationshipType.CLIENTE.value: {
        "words": {
            "precio": 3, "cuesta": 3, "cuanto cuesta": 4, "pagar": 3,
            "comprar": 2, "programa": 2, "curso": 2, "incluye": 2,
            "que incluye": 3, "factura": 2, "descuento": 2, "euros": 1,
        },
        "emojis": {},
        "threshold": 6,
    },
    RelationshipType.COLABORADOR.value: {
        "words": {
            "colaboracion": 4, "colaborar": 3, "partnership": 3,
            "proponer": 2, "audiencia": 2, "directo": 2, "live": 2,
            "juntos": 2, "marca": 2, "patrocinio": 3,
        },
        "emojis": {},
        "threshold": 5,
    },
}


class RelationshipTypeDetector:
    """Detects relationship type from conversation messages."""

    def __init__(self):
        """Initialize the detector."""

    def detect(self, messages: List[Dict]) -> Dict:
        """Detect relationship type from messages.

        Args:
            messages: List of message dicts with 'role' and 'content'

        Returns:
            Dict with 'type' and 'confidence' keys
        """
        if not messages or len(messages) < 2:
            return {
                "type": RelationshipType.DESCONOCIDO.value,
                "confidence": 0.3,
                "scores": {},
            }

        # Combine all text
        all_text = " ".join([m.get("content", "") for m in messages]).lower()

        # Calculate scores for each relationship type
        scores = {}
        for rel_type, indicators in INDICATORS.items():
            score = self._calculate_score(all_text, indicators)
            scores[rel_type] = score

        # Find highest scoring type
        max_type = max(scores, key=scores.get)
        max_score = scores[max_type]

        # Calculate confidence
        threshold = INDICATORS.get(max_type, {}).get("threshold", 5)

        if max_score >= threshold:
            # Calculate confidence based on how much above threshold
            confidence = min(0.95, 0.6 + (max_score - threshold) * 0.05)
            return {
                "type": max_type,
                "confidence": round(confidence, 2),
                "scores": scores,
            }

        # Default to DESCONOCIDO
        return {
            "type": RelationshipType.DESCONOCIDO.value,
            "confidence": min(0.5, 0.3 + max_score * 0.02),
            "scores": scores,
        }

    def _calculate_score(self, text: str, indicators: Dict) -> float:
        """Calculate score for a relationship type.

        Args:
            text: Combined message text (lowercase)
            indicators: Dict with words, emojis, threshold

        Returns:
            Numeric score
        """
        score = 0.0

        # Score words
        for word, weight in indicators.get("words", {}).items():
            if word in text:
                # Count occurrences (capped at 3)
                count = min(3, text.count(word))
                score += weight * count

        # Score emojis
        for emoji, weight in indicators.get("emojis", {}).items():
            if emoji in text:
                count = min(3, text.count(emoji))
                score += weight * count

        return score

    def detect_with_history(
        self, messages: List[Dict], previous_type: str = None
    ) -> Dict:
        """Detect type considering previous classification.

        Args:
            messages: List of message dicts
            previous_type: Previously detected type

        Returns:
            Dict with type and confidence
        """
        result = self.detect(messages)

        # If we had a previous type and new detection is uncertain,
        # keep the previous type with reduced confidence
        if (
            previous_type
            and previous_type != RelationshipType.DESCONOCIDO.value
            and result["type"] == RelationshipType.DESCONOCIDO.value
            and result["confidence"] < 0.5
        ):
            return {
                "type": previous_type,
                "confidence": 0.5,  # Reduced confidence
                "scores": result["scores"],
            }

        return result
