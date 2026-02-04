"""
EdgeCaseHandler - Handles difficult conversation situations.

Detects and responds appropriately to:
- Sarcasm and irony
- Questions the bot can't answer
- Situations requiring "dry" responses

Part of PHASE-6: Edge Cases.
"""

import random
import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple


class EdgeCaseType(Enum):
    """Types of edge cases the bot can detect."""

    SARCASM = "sarcasm"
    IRONY = "irony"
    UNKNOWN_QUESTION = "unknown_question"
    PERSONAL_QUESTION = "personal_question"
    OFF_TOPIC = "off_topic"
    COMPLAINT = "complaint"
    AGGRESSIVE = "aggressive"
    NONE = "none"


@dataclass
class EdgeCaseConfig:
    """Configuration for edge case handling."""

    # Probability of admitting "no sé" when uncertain
    admit_unknown_chance: float = 0.3

    # Probability of dry response in ambiguous situations
    dry_response_chance: float = 0.15

    # Minimum confidence to NOT trigger edge case
    confidence_threshold: float = 0.7


@dataclass
class EdgeCaseResult:
    """Result of edge case detection."""

    edge_type: EdgeCaseType
    confidence: float
    suggested_response: Optional[str] = None
    should_escalate: bool = False
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class EdgeCaseHandler:
    """Service for handling edge cases in conversations."""

    # Sarcasm indicators
    SARCASM_PATTERNS = [
        r"claro que sí",
        r"sí,? claro",
        r"obvio",
        r"no me digas",
        r"qué sorpresa",
        r"quién lo diría",
        r"ah,? bueno",
        r"qué novedad",
        r"wow,? increíble",
        r"genial\.{3,}",
        r"perfecto\.{3,}",
        r"súper\.{3,}",
    ]

    # Irony indicators (often with excessive punctuation/emoji)
    IRONY_PATTERNS = [
        r"😂{2,}",
        r"🤣{2,}",
        r"ja(ja){3,}",  # jajajaja or longer
        r"\.{4,}",
        r"\?{3,}",
        r"!{3,}",
    ]

    # Questions about things the bot shouldn't know
    UNKNOWN_PATTERNS = [
        r"qué piensas (de verdad|realmente)",
        r"cuál es tu opinión (real|personal)",
        r"qué harías (tú|vos)",
        r"cómo te sientes",
        r"qué sentiste cuando",
        r"te acuerdas cuando",
        r"recuerdas la vez que",
    ]

    # Personal questions the bot can't answer
    PERSONAL_PATTERNS = [
        r"tienes (novi[oa]|pareja|esposa)",
        r"estás casado",
        r"dónde vives (ahora|actualmente)",
        r"cuántos años tienes",
        r"cuál es tu número",
        r"dame tu (whatsapp|teléfono|número)",
    ]

    # Off-topic indicators
    OFF_TOPIC_PATTERNS = [
        r"qué opinas de (política|fútbol|trump|gobierno)",
        r"(votaste|votas) (por|a)",
        r"por quién (votaste|votas)",
        r"eres de (derecha|izquierda)",
        r"qué piensas de (bitcoin|crypto)",
    ]

    # Complaint/negative patterns
    COMPLAINT_PATTERNS = [
        r"no me (sirve|funciona|ayuda)",
        r"esto es (una mierda|basura|inútil)",
        r"perdí mi (tiempo|dinero)",
        r"me siento (estafado|engañado)",
        r"quiero (mi )?(devolución|reembolso)",
        r"voy a (denunciar|reportar)",
    ]

    # Aggressive patterns
    AGGRESSIVE_PATTERNS = [
        r"eres (idiota|estúpido|tonto)",
        r"vete (a la mierda|al carajo)",
        r"me cago en",
        r"hijo de",
        r"la puta madre",
    ]

    # "No sé" responses (Stefan style)
    NO_SE_RESPONSES = [
        "Mmm no sabría decirte la verdad 🤔",
        "Eso no lo sé la verdad",
        "No tengo ni idea jaja",
        "Pues no lo sé 🤷‍♂️",
        "Buena pregunta! No lo sé",
        "Ni idea la verdad 😅",
    ]

    # Deflection responses (for personal/off-topic)
    DEFLECTION_RESPONSES = [
        "Jaja mejor hablemos de otra cosa",
        "Prefiero no meterme en eso 😅",
        "Eso es tema aparte jaja",
        "Mejor dejemos eso para otro momento",
    ]

    # Empathy responses (for complaints)
    EMPATHY_RESPONSES = [
        "Entiendo que estés frustrado",
        "Lamento que te sientas así",
        "Te entiendo perfectamente",
        "Es normal sentirse así",
    ]

    def __init__(self, config: EdgeCaseConfig = None):
        self.config = config or EdgeCaseConfig()

        # Compile patterns for efficiency
        self._sarcasm_re = self._compile_patterns(self.SARCASM_PATTERNS)
        self._irony_re = self._compile_patterns(self.IRONY_PATTERNS)
        self._unknown_re = self._compile_patterns(self.UNKNOWN_PATTERNS)
        self._personal_re = self._compile_patterns(self.PERSONAL_PATTERNS)
        self._off_topic_re = self._compile_patterns(self.OFF_TOPIC_PATTERNS)
        self._complaint_re = self._compile_patterns(self.COMPLAINT_PATTERNS)
        self._aggressive_re = self._compile_patterns(self.AGGRESSIVE_PATTERNS)

    def _compile_patterns(self, patterns: List[str]) -> re.Pattern:
        """Compile a list of patterns into a single regex."""
        combined = "|".join(f"({p})" for p in patterns)
        return re.compile(combined, re.IGNORECASE)

    def detect(self, message: str, context: dict = None) -> EdgeCaseResult:
        """
        Detect if a message is an edge case.

        Args:
            message: The user's message.
            context: Optional conversation context.

        Returns:
            EdgeCaseResult with detection details.
        """
        message_lower = message.lower().strip()
        context = context or {}

        # Check in priority order

        # 1. Aggressive - highest priority, needs escalation
        if self._aggressive_re.search(message_lower):
            return EdgeCaseResult(
                edge_type=EdgeCaseType.AGGRESSIVE,
                confidence=0.9,
                suggested_response=None,  # Should be handled specially
                should_escalate=True,
                metadata={"reason": "aggressive_language"},
            )

        # 2. Complaints - high priority
        if self._complaint_re.search(message_lower):
            return EdgeCaseResult(
                edge_type=EdgeCaseType.COMPLAINT,
                confidence=0.85,
                suggested_response=random.choice(self.EMPATHY_RESPONSES),
                should_escalate=True,
                metadata={"reason": "complaint_detected"},
            )

        # 3. Personal questions
        if self._personal_re.search(message_lower):
            return EdgeCaseResult(
                edge_type=EdgeCaseType.PERSONAL_QUESTION,
                confidence=0.8,
                suggested_response=random.choice(self.DEFLECTION_RESPONSES),
                should_escalate=False,
            )

        # 4. Off-topic
        if self._off_topic_re.search(message_lower):
            return EdgeCaseResult(
                edge_type=EdgeCaseType.OFF_TOPIC,
                confidence=0.75,
                suggested_response=random.choice(self.DEFLECTION_RESPONSES),
                should_escalate=False,
            )

        # 5. Sarcasm detection
        if self._sarcasm_re.search(message_lower):
            return EdgeCaseResult(
                edge_type=EdgeCaseType.SARCASM,
                confidence=0.7,
                suggested_response=self._get_sarcasm_response(),
                should_escalate=False,
            )

        # 6. Irony detection
        if self._irony_re.search(message_lower):
            return EdgeCaseResult(
                edge_type=EdgeCaseType.IRONY,
                confidence=0.6,
                suggested_response=None,  # Let LLM handle with caution
                should_escalate=False,
                metadata={"tone": "potentially_ironic"},
            )

        # 7. Unknown questions
        if self._unknown_re.search(message_lower):
            if random.random() < self.config.admit_unknown_chance:
                return EdgeCaseResult(
                    edge_type=EdgeCaseType.UNKNOWN_QUESTION,
                    confidence=0.65,
                    suggested_response=random.choice(self.NO_SE_RESPONSES),
                    should_escalate=False,
                )

        # No edge case detected
        return EdgeCaseResult(
            edge_type=EdgeCaseType.NONE,
            confidence=0.0,
            suggested_response=None,
            should_escalate=False,
        )

    def _get_sarcasm_response(self) -> str:
        """Get an appropriate response to sarcasm."""
        responses = [
            "Jaja ya, entiendo 😅",
            "Me lo merezco jaja",
            "Vale, vale, pillado 😂",
            "Touché 😅",
            "Jaja ok ok",
        ]
        return random.choice(responses)

    def should_admit_unknown(self, confidence: float) -> Tuple[bool, Optional[str]]:
        """
        Decide if the bot should admit it doesn't know.

        Args:
            confidence: The LLM's confidence in its response.

        Returns:
            (should_admit, suggested_response)
        """
        if confidence < self.config.confidence_threshold:
            if random.random() < self.config.admit_unknown_chance:
                return True, random.choice(self.NO_SE_RESPONSES)

        return False, None

    def get_dry_response_if_appropriate(
        self,
        message_type: str,
        context: dict = None,
    ) -> Optional[str]:
        """
        Return a dry response if appropriate for the situation.

        This adds naturalness - not everything deserves enthusiasm.

        Args:
            message_type: Type of message detected.
            context: Conversation context.

        Returns:
            Dry response or None.
        """
        # Situations where dry responses are more appropriate
        dry_situations = ["confirmation", "repetitive", "obvious"]

        if message_type in dry_situations:
            if random.random() < self.config.dry_response_chance:
                dry_responses = ["Ok", "Vale", "👍", "Sí", "Claro"]
                return random.choice(dry_responses)

        return None

    def process_with_context(
        self,
        message: str,
        llm_response: str,
        llm_confidence: float = 1.0,
        context: dict = None,
    ) -> Tuple[str, bool]:
        """
        Process a message and LLM response, applying edge case handling.

        Args:
            message: User's message.
            llm_response: The LLM's generated response.
            llm_confidence: LLM's confidence (0-1).
            context: Conversation context.

        Returns:
            (final_response, should_escalate)
        """
        # First, detect edge cases in the user's message
        result = self.detect(message, context)

        # If edge case with suggested response, use it
        if result.edge_type != EdgeCaseType.NONE and result.suggested_response:
            return result.suggested_response, result.should_escalate

        # Check if we should admit unknown
        should_admit, admit_response = self.should_admit_unknown(llm_confidence)
        if should_admit and admit_response:
            return admit_response, False

        # Default: use LLM response
        return llm_response, result.should_escalate


# Singleton
_handler: Optional[EdgeCaseHandler] = None


def get_edge_case_handler() -> EdgeCaseHandler:
    """Get global EdgeCaseHandler instance."""
    global _handler
    if _handler is None:
        _handler = EdgeCaseHandler()
    return _handler
