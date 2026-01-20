"""
Tone Detector - Detects communication tone from website content.

Analyzes website text to determine the creator's communication style.
Complements tone_analyzer.py which analyzes Instagram posts.
"""

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from ..deterministic_scraper import ScrapedPage
    from .bio_extractor import ExtractedBio

logger = logging.getLogger(__name__)


@dataclass
class DetectedTone:
    """Detected tone profile from website."""

    style: str  # "amigo", "mentor", "vendedor", "profesional"
    formality: str  # "formal", "informal", "neutral"
    energy: str  # "alta", "media", "baja"
    confidence: float
    indicators: List[str]  # Phrases/patterns that led to detection


# Tone indicators
TONE_INDICATORS = {
    "amigo": {
        "patterns": [
            r"(?:hey|hola)[!,]",
            r"(?:amig[oa]s?|colega|compa)",
            r"(?:genial|increible|super|wow)",
            r"(?:vamos|dale|va)",
            r"[!]{2,}",  # Multiple exclamations
        ],
        "words": ["crack", "mola", "guay", "brutal", "pasada", "currar", "curro"],
        "formality": "informal",
        "energy": "alta",
    },
    "mentor": {
        "patterns": [
            r"(?:te ense[ñn]o|aprende|descubre)",
            r"(?:paso a paso|te guio|te muestro)",
            r"(?:mi experiencia|aprendido|errores)",
            r"(?:consejos?|tips?|estrategia)",
        ],
        "words": ["transformar", "crecer", "potencial", "metodologia", "sistema"],
        "formality": "neutral",
        "energy": "media",
    },
    "vendedor": {
        "patterns": [
            r"(?:oferta|descuento|promocion)",
            r"(?:compra|adquiere|consigue) (?:ahora|ya|hoy)",
            r"(?:limitad[oa]|exclusiv[oa]|unic[oa])",
            r"(?:garantia|devolucion)",
            r"(?:\d+%|€\d+|\$\d+)",  # Prices and percentages
        ],
        "words": ["invertir", "valor", "resultados", "garantizado", "bonus"],
        "formality": "neutral",
        "energy": "alta",
    },
    "profesional": {
        "patterns": [
            r"(?:servicio|consultoria|asesoria)",
            r"(?:empresa|profesional|corporativ)",
            r"(?:experiencia|trayectoria|especializad)",
            r"(?:contacte|solicite|agende)",
        ],
        "words": ["soluciones", "optimizar", "implementar", "analisis", "estrategia"],
        "formality": "formal",
        "energy": "baja",
    },
}

# Formality indicators
FORMALITY_INDICATORS = {
    "formal": [
        r"(?:usted|ustedes)",
        r"(?:atentamente|cordialmente)",
        r"(?:le invitamos|le ofrecemos)",
        r"(?:nuestra empresa|nuestros servicios)",
    ],
    "informal": [
        r"(?:tu |tus |te )",
        r"(?:oye|mira|fijate)",
        r"(?:curro|currar|mola)",
        r"[!]{2,}",
    ],
}


class ToneDetector:
    """Detects communication tone from website content."""

    def __init__(self):
        self.min_text_length = 200

    async def detect(
        self,
        pages: List["ScrapedPage"],
        bio: Optional["ExtractedBio"] = None,
    ) -> Optional[DetectedTone]:
        """
        Detect tone from website pages.

        Args:
            pages: Scraped website pages
            bio: Extracted bio for additional context

        Returns:
            DetectedTone or None if not enough content
        """
        # Combine all text for analysis
        all_text = ""
        for page in pages:
            all_text += " " + page.main_content

        if bio:
            all_text += " " + bio.description

        all_text = all_text.lower()

        if len(all_text) < self.min_text_length:
            logger.warning("Not enough text for tone detection")
            return None

        # Count indicators for each style
        style_scores = {}
        style_indicators = {}

        for style, data in TONE_INDICATORS.items():
            score = 0
            indicators = []

            # Check patterns
            for pattern in data["patterns"]:
                matches = re.findall(pattern, all_text, re.IGNORECASE)
                if matches:
                    score += len(matches)
                    indicators.extend(matches[:3])  # Keep first 3 as examples

            # Check words
            for word in data["words"]:
                count = all_text.count(word.lower())
                if count:
                    score += count
                    indicators.append(word)

            style_scores[style] = score
            style_indicators[style] = indicators

        # Determine dominant style
        if not any(style_scores.values()):
            # Default to profesional if no strong indicators
            dominant_style = "profesional"
            confidence = 0.3
            indicators = []
        else:
            dominant_style = max(style_scores, key=style_scores.get)
            max_score = style_scores[dominant_style]
            total_score = sum(style_scores.values()) or 1
            confidence = min(0.95, 0.5 + (max_score / total_score) * 0.5)
            indicators = style_indicators[dominant_style][:5]

        # Detect formality
        formality = self._detect_formality(all_text)

        # Use default from style if formality unclear
        if not formality:
            formality = TONE_INDICATORS[dominant_style].get("formality", "neutral")

        # Detect energy level
        energy = self._detect_energy(all_text)
        if not energy:
            energy = TONE_INDICATORS[dominant_style].get("energy", "media")

        logger.info(
            f"Detected tone: {dominant_style} (formality={formality}, energy={energy}, confidence={confidence:.2f})"
        )

        return DetectedTone(
            style=dominant_style,
            formality=formality,
            energy=energy,
            confidence=confidence,
            indicators=indicators,
        )

    def _detect_formality(self, text: str) -> Optional[str]:
        """Detect formality level from text."""
        formal_count = 0
        informal_count = 0

        for pattern in FORMALITY_INDICATORS["formal"]:
            formal_count += len(re.findall(pattern, text, re.IGNORECASE))

        for pattern in FORMALITY_INDICATORS["informal"]:
            informal_count += len(re.findall(pattern, text, re.IGNORECASE))

        if formal_count > informal_count * 2:
            return "formal"
        elif informal_count > formal_count * 2:
            return "informal"
        elif formal_count > 0 or informal_count > 0:
            return "neutral"

        return None

    def _detect_energy(self, text: str) -> Optional[str]:
        """Detect energy level from text."""
        # Count exclamation marks
        exclamations = text.count("!")

        # Count energy words
        high_energy_words = ["increible", "genial", "wow", "brutal", "amazing", "super"]
        low_energy_words = ["tranquilo", "calma", "serenidad", "pausado"]

        high_count = sum(text.count(word) for word in high_energy_words)
        low_count = sum(text.count(word) for word in low_energy_words)

        # Normalize by text length
        text_factor = len(text) / 1000

        if exclamations > text_factor * 5 or high_count > text_factor * 3:
            return "alta"
        elif low_count > high_count or exclamations < text_factor:
            return "baja"

        return "media"

    def to_dict(self, tone: DetectedTone) -> dict:
        """Convert DetectedTone to dictionary."""
        return {
            "style": tone.style,
            "formality": tone.formality,
            "energy": tone.energy,
            "confidence": tone.confidence,
            "indicators": tone.indicators,
        }
