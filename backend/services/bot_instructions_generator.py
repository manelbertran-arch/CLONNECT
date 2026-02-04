"""BotInstructionsGenerator service for creating bot instructions.

Generates natural language instructions for the bot based on
relationship DNA, including vocabulary rules and examples.

Part of RELATIONSHIP-DNA feature.
"""

import logging
from typing import Dict, List

from models.relationship_dna import RelationshipType

logger = logging.getLogger(__name__)


# Base instructions per relationship type
BASE_INSTRUCTIONS = {
    RelationshipType.INTIMA.value: (
        "Esta es una relación íntima/romántica. "
        "Usa un tono muy cariñoso, vulnerable y amoroso. "
        "Puedes expresar emociones profundas y mostrar afecto."
    ),
    RelationshipType.AMISTAD_CERCANA.value: (
        "Esta es una amistad cercana. "
        "Usa un tono fraternal, cercano y de confianza. "
        "Puedes ser espiritual y profundo."
    ),
    RelationshipType.AMISTAD_CASUAL.value: (
        "Esta es una amistad casual. "
        "Usa un tono amigable, relajado y divertido. "
        "Mantén la conversación ligera."
    ),
    RelationshipType.COLABORADOR.value: (
        "Esta es una relación de colaboración profesional. "
        "Sé profesional pero cercano. "
        "Muestra respeto y profesionalidad."
    ),
    RelationshipType.CLIENTE.value: (
        "Esta es una relación con un cliente potencial. "
        "Sé profesional, informativo y servicial. "
        "Responde preguntas sobre productos/servicios con claridad."
    ),
    RelationshipType.DESCONOCIDO.value: (
        "Esta es una relación nueva o desconocida. "
        "Usa un tono neutral y amable. "
        "No asumas confianza ni familiaridad."
    ),
}


class BotInstructionsGenerator:
    """Generates bot instructions from relationship DNA."""

    def __init__(self):
        """Initialize the generator."""
        pass

    def generate(self, dna_data: Dict) -> str:
        """Generate bot instructions from DNA data.

        Args:
            dna_data: Dict with relationship_type, vocabulary_uses,
                     vocabulary_avoids, emojis, recurring_topics, golden_examples

        Returns:
            String with natural language instructions
        """
        instructions = []

        # 1. Base instructions for relationship type
        relationship_type = dna_data.get("relationship_type", RelationshipType.DESCONOCIDO.value)
        base = BASE_INSTRUCTIONS.get(relationship_type, BASE_INSTRUCTIONS[RelationshipType.DESCONOCIDO.value])
        instructions.append(base)

        # 2. Vocabulary to use
        vocabulary_uses = dna_data.get("vocabulary_uses", [])
        if vocabulary_uses:
            words = ", ".join(vocabulary_uses[:5])
            instructions.append(f"USA estas palabras: {words}.")

        # 3. Vocabulary to avoid
        vocabulary_avoids = dna_data.get("vocabulary_avoids", [])
        if vocabulary_avoids:
            words = ", ".join(vocabulary_avoids[:5])
            instructions.append(f"EVITA estas palabras: {words}.")

        # 4. Emojis
        emojis = dna_data.get("emojis", [])
        if emojis:
            emoji_str = " ".join(emojis[:5])
            instructions.append(f"Emojis apropiados: {emoji_str}")

        # 5. Recurring topics
        topics = dna_data.get("recurring_topics", [])
        if topics:
            topic_str = ", ".join(topics[:3])
            instructions.append(f"Temas que puedes mencionar: {topic_str}.")

        # 6. Golden examples
        golden_examples = dna_data.get("golden_examples", [])
        if golden_examples:
            examples_section = self._format_examples(golden_examples)
            instructions.append(examples_section)

        return " ".join(instructions)

    def _format_examples(self, examples: List[Dict]) -> str:
        """Format golden examples into instructions.

        Args:
            examples: List of {lead: str, creator: str} dicts

        Returns:
            Formatted string with examples
        """
        if not examples:
            return ""

        lines = ["Ejemplos de cómo responder así:"]
        for i, ex in enumerate(examples[:3], 1):
            lead = ex.get("lead", "")
            creator = ex.get("creator", "")
            if lead and creator:
                lines.append(f"  {i}. Lead: \"{lead}\" → Tú: \"{creator}\"")

        return " ".join(lines)

    def generate_compact(self, dna_data: Dict) -> str:
        """Generate a compact version of instructions for system prompts.

        Args:
            dna_data: Dict with DNA fields

        Returns:
            Compact instruction string
        """
        relationship_type = dna_data.get("relationship_type", RelationshipType.DESCONOCIDO.value)
        vocabulary_uses = dna_data.get("vocabulary_uses", [])
        vocabulary_avoids = dna_data.get("vocabulary_avoids", [])

        parts = []

        # Tone indicator
        tone_map = {
            RelationshipType.INTIMA.value: "TONE:intimate",
            RelationshipType.AMISTAD_CERCANA.value: "TONE:fraternal",
            RelationshipType.AMISTAD_CASUAL.value: "TONE:casual",
            RelationshipType.CLIENTE.value: "TONE:professional",
            RelationshipType.COLABORADOR.value: "TONE:professional-friendly",
            RelationshipType.DESCONOCIDO.value: "TONE:neutral",
        }
        parts.append(tone_map.get(relationship_type, "TONE:neutral"))

        # Vocabulary
        if vocabulary_uses:
            parts.append(f"USE:{','.join(vocabulary_uses[:3])}")
        if vocabulary_avoids:
            parts.append(f"AVOID:{','.join(vocabulary_avoids[:3])}")

        return " | ".join(parts)
