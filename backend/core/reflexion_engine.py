"""
Reflexion Engine v1.7.0 - Self-improvement for bot responses.

Implements a lightweight reflexion pattern:
1. Analyze the proposed response
2. Check for common issues
3. Suggest improvements or flag for revision

This is NOT a full LLM reflexion loop - it's rule-based for speed.
"""

import logging
import re
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ReflexionResult:
    """Result of reflexion analysis."""
    needs_revision: bool = False
    issues: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    severity: str = "none"  # none, low, medium, high

    def to_prompt_context(self) -> str:
        """Generate context for re-prompting if needed."""
        if not self.needs_revision:
            return ""

        parts = ["=== REVISION NECESARIA ==="]
        parts.append(f"Severidad: {self.severity.upper()}")

        if self.issues:
            parts.append("\nProblemas detectados:")
            for issue in self.issues:
                parts.append(f"- {issue}")

        if self.suggestions:
            parts.append("\nSugerencias:")
            for suggestion in self.suggestions:
                parts.append(f"- {suggestion}")

        return "\n".join(parts)


class ReflexionEngine:
    """
    Analyzes bot responses for quality issues.

    Checks for:
    - Response too long (> 300 chars for simple questions)
    - Response too short (< 20 chars)
    - Missing call to action when appropriate
    - Repetition of information already given
    - Unanswered user question
    - Tone mismatch
    """

    # Maximum response length guidelines
    MAX_RESPONSE_LENGTH = 300  # Shorter for simple questions
    MIN_RESPONSE_LENGTH = 2  # Iris writes "Ok", "Va", "Sí" (2-3 chars)
    IDEAL_RESPONSE_LENGTH = 150

    # Patterns indicating questions
    QUESTION_PATTERNS = [
        r'\?$',
        r'\bcuanto\s+(?:cuesta|vale|es)\b',
        r'\bque\s+(?:es|son|incluye)\b',
        r'\bcomo\s+(?:funciona|puedo)\b',
        r'\bdonde\s+(?:esta|puedo)\b',
        r'\bhow\s+(?:much|does|can)\b',
        r'\bwhat\s+(?:is|are|does)\b',
    ]

    # Patterns for pricing questions
    PRICE_QUESTION_PATTERNS = [
        r'\bcuanto\s+(?:cuesta|vale|es)\b',
        r'\bcu[aá]nto\s+(?:cuesta|vale|es)\b',  # BUG-04: also match with tilde
        r'\bprecio\b',
        r'\bcoste?\b',
        r'\bhow\s+much\b',
        r'\bprice\b',
        r'\bcost\b',
    ]

    # CTA indicators
    CTA_PATTERNS = [
        r'\blink\b',
        r'\bcomprar\b',
        r'\binscribir\b',
        r'\breservar\b',
        r'\bapuntar\b',
        r'\bbuy\b',
        r'\bsign\s+up\b',
        r'\bregister\b',
    ]

    def __init__(self):
        self._question_compiled = [re.compile(p, re.IGNORECASE) for p in self.QUESTION_PATTERNS]
        self._price_compiled = [re.compile(p, re.IGNORECASE) for p in self.PRICE_QUESTION_PATTERNS]
        self._cta_compiled = [re.compile(p, re.IGNORECASE) for p in self.CTA_PATTERNS]

    def analyze_response(
        self,
        response: str,
        user_message: str,
        conversation_phase: str = None,
        previous_bot_responses: List[str] = None,
        user_context: Dict = None
    ) -> ReflexionResult:
        """
        Analyze a proposed response for quality issues.

        Args:
            response: The bot's proposed response
            user_message: The user's message being responded to
            conversation_phase: Current phase (inicio, propuesta, etc.)
            previous_bot_responses: List of previous bot responses
            user_context: Context about the user (goal, situation, etc.)

        Returns:
            ReflexionResult with analysis
        """
        result = ReflexionResult()

        # Check 1: Response length
        self._check_length(response, user_message, result)

        # Check 2: Unanswered question
        self._check_unanswered_question(response, user_message, result)

        # Check 3: Repetition
        if previous_bot_responses:
            self._check_repetition(response, previous_bot_responses, result)

        # Check 4: Phase-appropriate response
        if conversation_phase:
            self._check_phase_appropriateness(response, conversation_phase, result)

        # Check 5: Missing price when asked
        self._check_price_response(response, user_message, result)

        # Determine overall severity
        if result.issues:
            result.needs_revision = True
            if len(result.issues) >= 3:
                result.severity = "high"
            elif len(result.issues) >= 2:
                result.severity = "medium"
            else:
                result.severity = "low"

        if result.needs_revision:
            logger.info(f"[REFLEXION] Issues found ({result.severity}): {result.issues}")

        return result

    def _check_length(self, response: str, user_message: str, result: ReflexionResult) -> None:
        """Check if response length is appropriate."""
        response_len = len(response)
        msg_len = len(user_message)

        # Very short responses might be incomplete
        if response_len < self.MIN_RESPONSE_LENGTH:
            result.issues.append("Respuesta demasiado corta")
            result.suggestions.append("Elabora un poco mas la respuesta")

        # Very long responses for short questions
        elif response_len > self.MAX_RESPONSE_LENGTH and msg_len < 50:
            result.issues.append("Respuesta muy larga para pregunta simple")
            result.suggestions.append("Acorta la respuesta, se mas directo")

    def _check_unanswered_question(self, response: str, user_message: str, result: ReflexionResult) -> None:
        """Check if user's question was addressed."""
        # Check if user asked a question
        user_asked_question = any(p.search(user_message) for p in self._question_compiled)

        if not user_asked_question:
            return

        # Check if response contains a question mark (might be deflecting with another question)
        response_questions = response.count('?')

        # If user asked and response only has questions, might be deflecting
        if response_questions >= 2 and '!' not in response:
            result.issues.append("Posible evasion - respondiendo con multiples preguntas")
            result.suggestions.append("Responde primero la pregunta del usuario")

    def _check_repetition(self, response: str, previous_responses: List[str], result: ReflexionResult) -> None:
        """Check for repetition of previous responses."""
        response_lower = response.lower()
        response_words = set(re.findall(r'\b\w{4,}\b', response_lower))  # Words 4+ chars

        for prev in previous_responses[-5:]:  # Check last 5 responses
            prev_lower = prev.lower()
            prev_words = set(re.findall(r'\b\w{4,}\b', prev_lower))

            if not prev_words:
                continue

            overlap = len(response_words & prev_words) / max(len(prev_words), 1)
            if overlap > 0.6:  # More than 60% word overlap
                result.issues.append("Alta repeticion con respuesta anterior")
                result.suggestions.append("Varia el contenido, no repitas lo mismo")
                break

    def _check_phase_appropriateness(self, response: str, phase: str, result: ReflexionResult) -> None:
        """Check if response is appropriate for conversation phase."""
        response_lower = response.lower()

        # In INICIO phase, shouldn't mention prices
        if phase == "inicio":
            if re.search(r'\d+\s*€|\beuros?\b|\bprecio\b', response_lower):
                result.issues.append("Menciona precio en fase INICIO")
                result.suggestions.append("En fase INICIO, no menciones precios aun")

        # In PROPUESTA phase, should include price if discussing product
        elif phase == "propuesta":
            if not re.search(r'\d+\s*€|\beuros?\b', response_lower):
                # Only flag if response is about products
                if re.search(r'\bprograma\b|\bcurso\b|\bmentoria\b|\bebook\b', response_lower):
                    result.issues.append("Falta precio en fase PROPUESTA")
                    result.suggestions.append("Incluye el precio del producto")

        # In CIERRE phase, should have CTA or link
        elif phase == "cierre":
            has_cta = any(p.search(response_lower) for p in self._cta_compiled)
            has_link = 'http' in response_lower or '.com' in response_lower

            if not has_cta and not has_link:
                result.issues.append("Falta CTA o link en fase CIERRE")
                result.suggestions.append("Incluye el link de compra o invitacion a actuar")

    def _check_price_response(self, response: str, user_message: str, result: ReflexionResult) -> None:
        """Check if price question was answered with actual price."""
        # Check if user asked about price
        asked_price = any(p.search(user_message) for p in self._price_compiled)

        if not asked_price:
            return

        # Check if response contains a price
        has_price = bool(re.search(r'\d+\s*€|\d+\s*euros?|\$\d+', response, re.IGNORECASE))

        if not has_price:
            result.issues.append("Usuario pregunto precio pero no se incluyo")
            result.suggestions.append("Incluye el precio especifico del producto")

    def build_revision_prompt(self, result: ReflexionResult, original_response: str) -> str:
        """
        Build a prompt for revising the response.

        Only called if needs_revision is True.
        """
        if not result.needs_revision:
            return ""

        parts = [
            "Tu respuesta anterior tenia algunos problemas. Por favor, genera una nueva respuesta.",
            "",
            "RESPUESTA ANTERIOR:",
            original_response,
            "",
            result.to_prompt_context(),
            "",
            "Genera una respuesta mejorada que corrija estos problemas.",
        ]

        return "\n".join(parts)


# Singleton instance
_reflexion_engine: Optional[ReflexionEngine] = None


def get_reflexion_engine() -> ReflexionEngine:
    """Get singleton ReflexionEngine instance."""
    global _reflexion_engine
    if _reflexion_engine is None:
        _reflexion_engine = ReflexionEngine()
    return _reflexion_engine
