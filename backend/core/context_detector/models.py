"""
Context Detector Models — Universal, language-agnostic dataclasses.

Redesigned: removed frustration (handled by FrustrationDetector v2)
and sarcasm (LLM handles natively). Kept B2B, interest, meta, correction,
name, objection — all as factual signals, no behavior instructions.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class B2BResult:
    """Result of B2B context detection."""
    is_b2b: bool = False
    company_context: str = ""
    contact_name: str = ""
    collaboration_type: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_b2b": self.is_b2b,
            "company_context": self.company_context,
            "contact_name": self.contact_name,
            "collaboration_type": self.collaboration_type,
        }


@dataclass
class DetectedContext:
    """Complete detected context from a message.

    All fields are factual observations, not behavior instructions.
    The creator's Doc D defines HOW the clone reacts — this module
    only provides WHAT was detected in the lead's message.
    """
    # Sentiment (positive/neutral only — frustration handled externally)
    sentiment: str = "neutral"  # positive, neutral

    # B2B context
    is_b2b: bool = False
    company_context: str = ""
    b2b_contact_name: str = ""

    # Interest level (from intent classifier, not duplicated)
    interest_level: str = "none"  # strong, soft, none
    objection_type: str = ""  # price, time, trust, need, ""

    # User name
    user_name: str = ""

    # Conversational signals
    is_meta_message: bool = False  # lead references earlier messages
    is_correction: bool = False  # lead correcting a misunderstanding

    # Generated factual notes for Recalling block
    context_notes: List[str] = field(default_factory=list)

    # Backward compat — kept so detection.py .alerts access doesn't crash
    alerts: List[str] = field(default_factory=list)
    frustration_level: str = "none"
    frustration_reason: str = ""
    is_first_message: bool = True
    intent: Any = None
    intent_confidence: float = 0.0
    intent_sub: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sentiment": self.sentiment,
            "is_b2b": self.is_b2b,
            "company_context": self.company_context,
            "b2b_contact_name": self.b2b_contact_name,
            "interest_level": self.interest_level,
            "objection_type": self.objection_type,
            "user_name": self.user_name,
            "is_meta_message": self.is_meta_message,
            "is_correction": self.is_correction,
            "context_notes": self.context_notes,
        }

    def build_context_notes(self) -> List[str]:
        """Build factual notes for injection into Recalling block.

        Notes are factual observations, NOT behavior instructions.
        The Doc D / personality prompt defines how the clone reacts.
        """
        notes = []
        if self.is_b2b:
            note = "Este lead parece representar una empresa/marca"
            if self.company_context:
                note += f" ({self.company_context})"
            note += "."
            notes.append(note)
        if self.user_name:
            notes.append(f"El lead se llama {self.user_name}.")
        if self.is_meta_message:
            notes.append("El lead hace referencia a mensajes anteriores.")
        if self.is_correction:
            notes.append("El lead está corrigiendo algo que dijiste.")
        if self.objection_type:
            objection_labels = {
                "price": "precio",
                "time": "tiempo",
                "trust": "confianza",
                "need": "necesidad",
            }
            label = objection_labels.get(self.objection_type, self.objection_type)
            notes.append(f"El lead tiene una objeción de {label}.")
        self.context_notes = notes
        # Backward compat: also populate alerts
        self.alerts = notes
        return notes

    # Backward compat alias
    def build_alerts(self) -> List[str]:
        return self.build_context_notes()


# Backward compat re-exports (tests import these)
@dataclass
class FrustrationResult:
    is_frustrated: bool = False
    level: str = "none"
    reason: str = ""
    matched_pattern: str = ""
    def to_dict(self) -> Dict[str, Any]:
        return {"is_frustrated": self.is_frustrated, "level": self.level,
                "reason": self.reason, "matched_pattern": self.matched_pattern}


@dataclass
class SarcasmResult:
    is_sarcastic: bool = False
    confidence: float = 0.0
    matched_pattern: str = ""
    def to_dict(self) -> Dict[str, Any]:
        return {"is_sarcastic": self.is_sarcastic, "confidence": self.confidence,
                "matched_pattern": self.matched_pattern}
