"""VocabularyExtractor service for extracting vocabulary patterns.

Extracts:
- Common words used in messages
- Emojis
- Muletillas (filler words)
- Forbidden words based on relationship type

Part of RELATIONSHIP-DNA feature.
"""

import re
from collections import Counter
from typing import Dict, List

from models.relationship_dna import RelationshipType


# Stop words to exclude from common words
SPANISH_STOP_WORDS = {
    "de", "la", "que", "el", "en", "y", "a", "los", "del", "se", "las",
    "por", "un", "para", "con", "no", "una", "su", "al", "lo", "como",
    "más", "pero", "sus", "le", "ya", "o", "este", "ha", "me", "si",
    "porque", "esta", "cuando", "muy", "sin", "sobre", "también", "ser",
    "es", "yo", "eso", "entre", "era", "hay", "soy", "estoy", "tengo",
    "va", "voy", "te", "ti", "tu", "mi", "nos", "esa", "ese", "esto",
    "todo", "bien", "así", "ahora", "aquí", "cada", "donde", "hacer",
    "hola", "gracias", "mensaje", "hoy", "ayer", "mañana",
}

# Common muletillas (filler words) in Spanish
MULETILLAS = {
    "bueno", "pues", "entonces", "mira", "oye", "vale", "ósea", "osea",
    "tipo", "como", "digamos", "sabes", "nada", "total", "básicamente",
}

# Forbidden words per relationship type
FORBIDDEN_WORDS = {
    RelationshipType.FAMILIA.value: ["bro", "crack", "tio", "colega", "compa"],
    RelationshipType.INTIMA.value: ["hermano", "bro", "crack", "tio", "colega", "compa"],
    RelationshipType.AMISTAD_CERCANA.value: ["amor", "cariño", "mi vida", "bebe", "preciosa"],
    RelationshipType.AMISTAD_CASUAL.value: ["amor", "cariño", "mi vida"],
    RelationshipType.CLIENTE.value: ["hermano", "bro", "tio", "crack", "compa"],
    RelationshipType.COLABORADOR.value: ["hermano", "bro", "tio", "amor"],
    RelationshipType.DESCONOCIDO.value: ["hermano", "bro", "amor", "cariño"],
}


class VocabularyExtractor:
    """Extracts vocabulary patterns from conversation messages."""

    def __init__(self):
        """Initialize the extractor."""
        self._word_pattern = re.compile(r"\b[a-záéíóúñü]+\b", re.IGNORECASE)
        self._emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "\U0001F900-\U0001F9FF"  # supplemental symbols
            "\U0001FA00-\U0001FA6F"  # chess symbols
            "\U0001FA70-\U0001FAFF"  # symbols extended
            "]+",
            flags=re.UNICODE,
        )

    def extract_common_words(self, messages: List[str], limit: int = 10) -> List[str]:
        """Extract commonly used words from messages.

        Args:
            messages: List of message strings
            limit: Maximum number of words to return

        Returns:
            List of common words, ordered by frequency
        """
        if not messages:
            return []

        # Combine all messages
        all_text = " ".join(messages).lower()

        # Extract words
        words = self._word_pattern.findall(all_text)

        # Filter out stop words and short words
        filtered_words = [
            w for w in words
            if w not in SPANISH_STOP_WORDS
            and len(w) > 2
            and not w.isdigit()
        ]

        # Count frequencies
        counter = Counter(filtered_words)

        # Get most common (require at least 2 occurrences)
        common = [word for word, count in counter.most_common(limit * 2) if count >= 2]

        return common[:limit]

    def extract_emojis(self, messages: List[str], limit: int = 5) -> List[str]:
        """Extract emojis from messages.

        Args:
            messages: List of message strings
            limit: Maximum number of emojis to return

        Returns:
            List of emojis, ordered by frequency
        """
        if not messages:
            return []

        all_text = " ".join(messages)

        # Find all emojis
        emojis = self._emoji_pattern.findall(all_text)

        # Count frequencies
        counter = Counter(emojis)

        # Return most common
        return [emoji for emoji, _ in counter.most_common(limit)]

    def get_forbidden_words(self, relationship_type: str) -> List[str]:
        """Get words that should be avoided for a relationship type.

        Args:
            relationship_type: The relationship type

        Returns:
            List of words to avoid
        """
        return FORBIDDEN_WORDS.get(relationship_type, [])

    def extract_muletillas(self, messages: List[str]) -> List[str]:
        """Extract filler words (muletillas) from messages.

        Args:
            messages: List of message strings

        Returns:
            List of muletillas found
        """
        if not messages:
            return []

        all_text = " ".join(messages).lower()

        found = []
        for muletilla in MULETILLAS:
            if muletilla in all_text:
                # Count occurrences
                count = all_text.count(muletilla)
                if count >= 2:  # Only if used multiple times
                    found.append(muletilla)

        return found

    def extract_all(self, messages: List[str], relationship_type: str = None) -> Dict:
        """Extract all vocabulary patterns.

        Args:
            messages: List of message strings
            relationship_type: Optional relationship type for forbidden words

        Returns:
            Dict with common_words, emojis, muletillas, forbidden_words
        """
        return {
            "common_words": self.extract_common_words(messages),
            "emojis": self.extract_emojis(messages),
            "muletillas": self.extract_muletillas(messages),
            "forbidden_words": (
                self.get_forbidden_words(relationship_type) if relationship_type else []
            ),
        }
