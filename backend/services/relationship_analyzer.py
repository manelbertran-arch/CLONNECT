"""RelationshipAnalyzer service for extracting relationship DNA from conversations.

Analyzes conversation history to determine:
- Relationship type (INTIMA, AMISTAD_CERCANA, etc.)
- Trust score and depth level
- Vocabulary patterns (uses, avoids, emojis)
- Interaction patterns
- Bot instructions

Part of RELATIONSHIP-DNA feature.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from models.relationship_dna import RelationshipType

logger = logging.getLogger(__name__)


# Vocabulary indicators for relationship detection
INTIMA_INDICATORS = {
    "words": ["amor", "te amo", "te quiero", "mi vida", "cariño", "bebe", "preciosa", "precioso"],
    "emojis": ["💙", "❤️", "😘", "💋", "🥰", "💕"],
}

AMISTAD_CERCANA_INDICATORS = {
    "words": ["hermano", "bro", "crack", "tio", "compa", "brother"],
    "topics": ["circulo", "retiro", "meditacion", "vipassana", "terapia", "crecimiento"],
    "emojis": ["🙏🏽", "🙏", "💪🏽", "💪", "🫂", "🔥"],
}

AMISTAD_CASUAL_INDICATORS = {
    "words": ["crack", "tio", "maquina", "genial"],
    "emojis": ["😄", "👍", "🙌", "💯"],
}

CLIENTE_INDICATORS = {
    "words": ["precio", "cuesta", "pagar", "comprar", "programa", "curso", "incluye", "factura"],
    "patterns": ["cuanto cuesta", "como puedo pagar", "que incluye", "hay descuento"],
}


class RelationshipAnalyzer:
    """Analyzes conversations to extract relationship DNA."""

    # Thresholds for relationship detection
    MIN_MESSAGES_FOR_ANALYSIS = 5
    STALE_DAYS = 30
    MESSAGE_INCREASE_THRESHOLD = 10  # Re-analyze if 10+ new messages

    def __init__(self):
        """Initialize the analyzer."""
        self._cache = {}  # Simple in-memory cache

    def analyze(
        self, creator_id: str, follower_id: str, messages: List[Dict]
    ) -> Dict:
        """Analyze conversation and return relationship DNA.

        Args:
            creator_id: Creator identifier
            follower_id: Follower/lead identifier
            messages: List of message dicts with 'role' and 'content'

        Returns:
            Dict with relationship DNA fields
        """
        total_messages = len(messages)

        # Default values for insufficient data
        if total_messages < self.MIN_MESSAGES_FOR_ANALYSIS:
            return {
                "creator_id": creator_id,
                "follower_id": follower_id,
                "relationship_type": RelationshipType.DESCONOCIDO.value,
                "trust_score": 0.0,
                "depth_level": 0,
                "vocabulary_uses": [],
                "vocabulary_avoids": [],
                "emojis": [],
                "bot_instructions": None,
                "golden_examples": [],
                "total_messages_analyzed": total_messages,
            }

        # Extract text for analysis
        all_text = " ".join([m.get("content", "") for m in messages]).lower()
        creator_messages = [
            m.get("content", "") for m in messages if m.get("role") == "assistant"
        ]
        user_messages = [
            m.get("content", "") for m in messages if m.get("role") == "user"
        ]

        # Detect relationship type
        relationship_type = self._detect_relationship_type(all_text, messages)

        # Calculate trust score
        trust_score = self._calculate_trust_score(
            relationship_type, total_messages, all_text
        )

        # Calculate depth level
        depth_level = self._calculate_depth_level(total_messages)

        # Extract vocabulary
        vocabulary_uses = self._extract_vocabulary_uses(creator_messages, relationship_type)
        vocabulary_avoids = self._get_vocabulary_avoids(relationship_type)
        emojis = self._extract_emojis(creator_messages, relationship_type)

        # Extract patterns
        patterns = self.extract_patterns(messages)

        # Generate bot instructions
        dna_data = {
            "relationship_type": relationship_type,
            "vocabulary_uses": vocabulary_uses,
            "vocabulary_avoids": vocabulary_avoids,
            "emojis": emojis,
            "recurring_topics": self._extract_topics(all_text),
        }
        bot_instructions = self.generate_instructions(dna_data)

        # Extract golden examples
        golden_examples = self._extract_golden_examples(messages)

        return {
            "creator_id": creator_id,
            "follower_id": follower_id,
            "relationship_type": relationship_type,
            "trust_score": trust_score,
            "depth_level": depth_level,
            "vocabulary_uses": vocabulary_uses,
            "vocabulary_avoids": vocabulary_avoids,
            "emojis": emojis,
            "avg_message_length": patterns.get("avg_message_length"),
            "questions_frequency": patterns.get("questions_frequency"),
            "multi_message_frequency": patterns.get("multi_message_frequency"),
            "tone_description": self._describe_tone(relationship_type),
            "recurring_topics": dna_data["recurring_topics"],
            "private_references": [],
            "bot_instructions": bot_instructions,
            "golden_examples": golden_examples,
            "total_messages_analyzed": total_messages,
        }

    def _detect_relationship_type(self, text: str, messages: List[Dict]) -> str:
        """Detect relationship type from conversation content."""
        text_lower = text.lower()

        # Check for INTIMA indicators (highest priority)
        intima_score = 0
        for word in INTIMA_INDICATORS["words"]:
            if word in text_lower:
                intima_score += 2
        for emoji in INTIMA_INDICATORS["emojis"]:
            if emoji in text:
                intima_score += 1

        if intima_score >= 3:
            return RelationshipType.INTIMA.value

        # Check for CLIENTE indicators
        cliente_score = 0
        for word in CLIENTE_INDICATORS["words"]:
            if word in text_lower:
                cliente_score += 1
        for pattern in CLIENTE_INDICATORS["patterns"]:
            if pattern in text_lower:
                cliente_score += 2

        if cliente_score >= 3:
            return RelationshipType.CLIENTE.value

        # Check for AMISTAD_CERCANA indicators
        cercana_score = 0
        for word in AMISTAD_CERCANA_INDICATORS["words"]:
            if word in text_lower:
                cercana_score += 2
        for topic in AMISTAD_CERCANA_INDICATORS["topics"]:
            if topic in text_lower:
                cercana_score += 1
        for emoji in AMISTAD_CERCANA_INDICATORS["emojis"]:
            if emoji in text:
                cercana_score += 1

        if cercana_score >= 3:
            return RelationshipType.AMISTAD_CERCANA.value

        # Check for AMISTAD_CASUAL
        casual_score = 0
        for word in AMISTAD_CASUAL_INDICATORS["words"]:
            if word in text_lower:
                casual_score += 1
        for emoji in AMISTAD_CASUAL_INDICATORS["emojis"]:
            if emoji in text:
                casual_score += 1

        if casual_score >= 2:
            return RelationshipType.AMISTAD_CASUAL.value

        # Default
        return RelationshipType.DESCONOCIDO.value

    def _calculate_trust_score(
        self, relationship_type: str, message_count: int, text: str
    ) -> float:
        """Calculate trust score based on relationship type and interaction depth."""
        base_scores = {
            RelationshipType.INTIMA.value: 0.9,
            RelationshipType.AMISTAD_CERCANA.value: 0.75,
            RelationshipType.AMISTAD_CASUAL.value: 0.5,
            RelationshipType.COLABORADOR.value: 0.6,
            RelationshipType.CLIENTE.value: 0.3,
            RelationshipType.DESCONOCIDO.value: 0.1,
        }

        base = base_scores.get(relationship_type, 0.1)

        # Adjust based on message count (more messages = more trust)
        message_bonus = min(0.1, message_count * 0.002)

        return min(1.0, base + message_bonus)

    def _calculate_depth_level(self, message_count: int) -> int:
        """Calculate depth level based on message count."""
        if message_count < 10:
            return 0
        elif message_count < 25:
            return 1
        elif message_count < 50:
            return 2
        elif message_count < 100:
            return 3
        else:
            return 4

    def _extract_vocabulary_uses(
        self, creator_messages: List[str], relationship_type: str
    ) -> List[str]:
        """Extract vocabulary patterns from creator messages."""
        uses = []
        all_text = " ".join(creator_messages).lower()

        # Check for relationship-specific vocabulary
        if relationship_type == RelationshipType.AMISTAD_CERCANA.value:
            for word in ["hermano", "bro", "crack", "tio"]:
                if word in all_text:
                    uses.append(word)
        elif relationship_type == RelationshipType.INTIMA.value:
            for word in ["amor", "cariño", "preciosa", "precioso"]:
                if word in all_text:
                    uses.append(word)

        return list(set(uses))

    def _get_vocabulary_avoids(self, relationship_type: str) -> List[str]:
        """Get vocabulary to avoid based on relationship type."""
        avoids = {
            RelationshipType.INTIMA.value: ["hermano", "bro", "colega"],
            RelationshipType.AMISTAD_CERCANA.value: ["amor", "cariño", "mi vida"],
            RelationshipType.CLIENTE.value: ["hermano", "bro", "tio"],
        }
        return avoids.get(relationship_type, [])

    def _extract_emojis(
        self, creator_messages: List[str], relationship_type: str
    ) -> List[str]:
        """Extract commonly used emojis from creator messages."""
        all_text = " ".join(creator_messages)

        # Emoji regex pattern
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE,
        )

        emojis = emoji_pattern.findall(all_text)

        # Return unique emojis, prioritizing relationship-specific ones
        unique_emojis = list(set(emojis))

        # Add relationship-specific emojis if found
        if relationship_type == RelationshipType.INTIMA.value:
            for e in INTIMA_INDICATORS["emojis"]:
                if e in all_text and e not in unique_emojis:
                    unique_emojis.append(e)
        elif relationship_type == RelationshipType.AMISTAD_CERCANA.value:
            for e in AMISTAD_CERCANA_INDICATORS["emojis"]:
                if e in all_text and e not in unique_emojis:
                    unique_emojis.append(e)

        return unique_emojis[:5]  # Limit to 5 most relevant

    def _extract_topics(self, text: str) -> List[str]:
        """Extract recurring topics from conversation."""
        topics = []
        topic_keywords = {
            "circulos de hombres": ["circulo", "circulos", "hombres"],
            "meditacion": ["meditacion", "meditar", "vipassana"],
            "terapia": ["terapia", "terapeuta", "sesion"],
            "negocios": ["negocio", "empresa", "ventas", "cliente"],
            "fitness": ["entreno", "gimnasio", "dieta", "musculo"],
        }

        text_lower = text.lower()
        for topic, keywords in topic_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    topics.append(topic)
                    break

        return list(set(topics))

    def _describe_tone(self, relationship_type: str) -> str:
        """Generate tone description based on relationship type."""
        tones = {
            RelationshipType.INTIMA.value: "Íntimo, cariñoso, vulnerable, con mucho amor",
            RelationshipType.AMISTAD_CERCANA.value: "Cercano, fraternal, espiritual, de confianza",
            RelationshipType.AMISTAD_CASUAL.value: "Amigable, relajado, divertido",
            RelationshipType.COLABORADOR.value: "Profesional pero cercano, respetuoso",
            RelationshipType.CLIENTE.value: "Profesional, informativo, servicial",
            RelationshipType.DESCONOCIDO.value: "Neutral, amable, sin asumir confianza",
        }
        return tones.get(relationship_type, "Neutral")

    def extract_patterns(self, messages: List[Dict]) -> Dict:
        """Extract interaction patterns from messages.

        Returns:
            Dict with avg_message_length, questions_frequency, multi_message_frequency
        """
        if not messages:
            return {
                "avg_message_length": 0,
                "questions_frequency": 0.0,
                "multi_message_frequency": 0.0,
            }

        creator_messages = [
            m.get("content", "") for m in messages if m.get("role") == "assistant"
        ]

        if not creator_messages:
            return {
                "avg_message_length": 0,
                "questions_frequency": 0.0,
                "multi_message_frequency": 0.0,
            }

        # Average message length
        total_length = sum(len(m) for m in creator_messages)
        avg_length = total_length // len(creator_messages) if creator_messages else 0

        # Questions frequency
        questions = sum(1 for m in creator_messages if "?" in m)
        questions_freq = questions / len(creator_messages) if creator_messages else 0.0

        # Multi-message frequency (consecutive assistant messages)
        multi_count = 0
        prev_role = None
        for m in messages:
            if m.get("role") == "assistant" and prev_role == "assistant":
                multi_count += 1
            prev_role = m.get("role")

        multi_freq = multi_count / len(creator_messages) if creator_messages else 0.0

        return {
            "avg_message_length": avg_length,
            "questions_frequency": round(questions_freq, 2),
            "multi_message_frequency": round(multi_freq, 2),
        }

    def generate_instructions(self, dna_data: Dict) -> str:
        """Generate bot instructions based on relationship DNA.

        Args:
            dna_data: Dict with relationship_type, vocabulary_uses, etc.

        Returns:
            String with natural language instructions for the bot
        """
        relationship_type = dna_data.get("relationship_type", "DESCONOCIDO")
        vocabulary_uses = dna_data.get("vocabulary_uses", [])
        vocabulary_avoids = dna_data.get("vocabulary_avoids", [])
        emojis = dna_data.get("emojis", [])
        topics = dna_data.get("recurring_topics", [])

        instructions = []

        # Relationship-specific base instructions
        if relationship_type == RelationshipType.INTIMA.value:
            instructions.append(
                "Esta es una relación íntima. Usa un tono muy cariñoso y vulnerable."
            )
        elif relationship_type == RelationshipType.AMISTAD_CERCANA.value:
            instructions.append(
                "Esta es una amistad cercana. Usa un tono fraternal y de confianza."
            )
        elif relationship_type == RelationshipType.CLIENTE.value:
            instructions.append(
                "Esta es una relación de cliente. Sé profesional pero cálido."
            )

        # Vocabulary instructions
        if vocabulary_uses:
            instructions.append(f"USA estas palabras: {', '.join(vocabulary_uses)}")
        if vocabulary_avoids:
            instructions.append(f"EVITA estas palabras: {', '.join(vocabulary_avoids)}")

        # Emoji instructions
        if emojis:
            instructions.append(f"Puedes usar estos emojis: {' '.join(emojis)}")

        # Topic instructions
        if topics:
            instructions.append(
                f"Temas recurrentes que puedes mencionar: {', '.join(topics)}"
            )

        return " ".join(instructions) if instructions else "Usa un tono neutral y amable."

    def should_update_dna(self, existing_dna: Dict, current_message_count: int) -> bool:
        """Determine if DNA needs to be re-analyzed.

        Args:
            existing_dna: Current DNA data
            current_message_count: Current total message count

        Returns:
            True if DNA should be updated
        """
        if not existing_dna:
            return True

        # Check if stale (>30 days)
        last_analyzed = existing_dna.get("last_analyzed_at")
        if last_analyzed:
            if isinstance(last_analyzed, str):
                last_analyzed = datetime.fromisoformat(last_analyzed.replace("Z", "+00:00"))
            age = datetime.now(timezone.utc) - last_analyzed
            if age > timedelta(days=self.STALE_DAYS):
                return True

        # Check if significant new messages
        prev_count = existing_dna.get("total_messages_analyzed", 0)
        if current_message_count - prev_count >= self.MESSAGE_INCREASE_THRESHOLD:
            return True

        return False

    def update_incremental(self, existing_dna: Dict, new_messages: List[Dict]) -> Dict:
        """Incrementally update DNA with new messages while preserving curated data.

        Args:
            existing_dna: Current DNA data
            new_messages: New messages to incorporate

        Returns:
            Updated DNA data
        """
        # Preserve manually curated fields
        preserved_golden = existing_dna.get("golden_examples", [])

        # Re-analyze with all context
        # In a real implementation, we'd merge old + new analysis
        updated = existing_dna.copy()

        # Extract new vocabulary from new messages
        creator_messages = [
            m.get("content", "") for m in new_messages if m.get("role") == "assistant"
        ]
        new_uses = self._extract_vocabulary_uses(
            creator_messages, existing_dna.get("relationship_type", "DESCONOCIDO")
        )

        # Merge vocabulary
        current_uses = existing_dna.get("vocabulary_uses", [])
        updated["vocabulary_uses"] = list(set(current_uses + new_uses))

        # Preserve golden examples
        updated["golden_examples"] = preserved_golden

        # Update message count
        updated["total_messages_analyzed"] = (
            existing_dna.get("total_messages_analyzed", 0) + len(new_messages)
        )

        return updated

    def _extract_golden_examples(self, messages: List[Dict]) -> List[Dict]:
        """Extract representative examples from conversation.

        Returns list of {lead: str, creator: str} pairs.
        """
        examples = []

        for i, msg in enumerate(messages):
            if msg.get("role") == "user" and i + 1 < len(messages):
                next_msg = messages[i + 1]
                if next_msg.get("role") == "assistant":
                    # Good exchange found
                    user_content = msg.get("content", "")
                    creator_content = next_msg.get("content", "")

                    # Only include short, representative exchanges
                    if len(user_content) < 100 and len(creator_content) < 150:
                        examples.append({
                            "lead": user_content,
                            "creator": creator_content,
                        })

                    if len(examples) >= 3:  # Limit to 3 examples
                        break

        return examples
