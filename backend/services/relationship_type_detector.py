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
    RelationshipType.FAMILIA.value: {
        "words": {
            # ES
            "hijo": 5, "hija": 5, "hola hijo": 6, "hola hija": 6,
            "papá": 5, "papa": 4, "mamá": 5, "mama": 4,
            "padre": 4, "madre": 4, "viejo": 3, "vieja": 3,
            "nene": 3, "nena": 3, "abuelo": 4, "abuela": 4,
            "sobrino": 3, "sobrina": 3,
            "familia": 3, "familiar": 2, "pariente": 2,
            "papi": 4, "mami": 4,
            # IT
            "figlio": 5, "figlia": 5, "mamma": 5, "papà": 5,
            "nonno": 4, "nonna": 4, "nipote": 3, "fratello": 4,
            "sorella": 4, "famiglia": 3, "babbo": 4,
            # CA
            "fill": 5, "filla": 5, "mare": 4, "pare": 4,
            "avi": 4, "àvia": 4, "nebot": 3, "germà": 4,
            "germana": 4, "família": 3,
            # EN
            "son": 4, "daughter": 4, "mom": 4, "dad": 4,
            "mother": 4, "father": 4, "grandpa": 4, "grandma": 4,
            "brother": 4, "sister": 4, "family": 3,
        },
        "emojis": {"👨‍👩‍👧": 3, "👪": 3, "🏠": 1, "💛": 1},
        "threshold": 8,
    },
    RelationshipType.INTIMA.value: {
        "words": {
            # ES
            "amor": 5, "te amo": 5, "te quiero": 4, "mi vida": 4,
            "cariño": 4, "preciosa": 4, "precioso": 4, "bebe": 3,
            "te extraño": 4, "extraño": 2,
            # IT
            "ti amo": 5, "amore": 5, "tesoro": 4, "amore mio": 5,
            "mi manchi": 4, "ti voglio bene": 4,
            # CA
            "t'estimo": 5, "amor meu": 5, "vida meva": 4,
            # EN
            "i love you": 5, "love you": 4, "my love": 4,
            "darling": 3, "sweetheart": 3, "miss you": 4,
        },
        "emojis": {"💙": 3, "❤️": 3, "😘": 2, "💋": 2, "🥰": 2, "💕": 2},
        "threshold": 10,
    },
    RelationshipType.AMISTAD_CERCANA.value: {
        "words": {
            # ES
            "hermano": 3, "bro": 3, "compa": 2,
            "circulo": 2, "retiro": 2, "meditacion": 2, "vipassana": 2,
            "transformador": 2, "espiritual": 2,
            # IT
            "fratello": 3, "amico mio": 3, "compagno": 2,
            # CA
            "germà": 3, "amic meu": 3, "company": 2,
            # EN
            "brother": 3, "mate": 2, "buddy": 2, "dude": 2,
        },
        "emojis": {"🙏🏽": 2, "🙏": 2, "💪🏽": 2, "💪": 2, "🫂": 2, "🔥": 1},
        "threshold": 6,
    },
    RelationshipType.AMISTAD_CASUAL.value: {
        "words": {
            # ES
            "crack": 3, "tio": 2, "maquina": 2, "genial": 1,
            "guay": 1, "mola": 1, "flipante": 1,
            # IT
            "grande": 2, "mitico": 2, "forte": 1,
            # CA
            "crack": 3, "tio": 2, "bèstia": 2, "brutal": 1,
            # EN
            "cool": 1, "awesome": 1, "dude": 1, "nice": 1,
        },
        "emojis": {"😄": 1, "👍": 1, "🙌": 1, "💯": 1},
        "threshold": 4,
    },
    RelationshipType.CLIENTE.value: {
        "words": {
            # ES
            "precio": 3, "cuesta": 3, "cuanto cuesta": 4, "pagar": 3,
            "comprar": 2, "programa": 2, "curso": 2, "incluye": 2,
            "que incluye": 3, "factura": 2, "descuento": 2, "euros": 1,
            # IT
            "prezzo": 3, "costa": 3, "quanto costa": 4, "pagare": 3,
            "comprare": 2, "programma": 2, "corso": 2, "sconto": 2,
            # CA
            "preu": 3, "costa": 3, "quant costa": 4, "pagar": 3,
            "comprar": 2, "curs": 2, "descompte": 2,
            # EN
            "price": 3, "cost": 3, "how much": 4, "pay": 3,
            "buy": 2, "program": 2, "course": 2, "discount": 2,
        },
        "emojis": {},
        "threshold": 6,
    },
    RelationshipType.COLABORADOR.value: {
        "words": {
            # ES
            "colaboracion": 4, "colaborar": 3, "partnership": 3,
            "proponer": 2, "audiencia": 2, "directo": 2, "live": 2,
            "juntos": 2, "marca": 2, "patrocinio": 3,
            # IT
            "collaborazione": 4, "collaborare": 3, "proporre": 2,
            # CA
            "col·laboració": 4, "col·laborar": 3, "proposar": 2,
            # EN
            "collaboration": 4, "collaborate": 3, "partnership": 3,
            "sponsor": 3, "audience": 2, "together": 2,
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
