"""
Context Detector Models

Dataclasses for context detection results.

Part of refactor/context-injection-v2
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from core.intent_classifier import Intent


@dataclass
class FrustrationResult:
    """Result of frustration detection."""

    is_frustrated: bool = False
    level: str = "none"  # none, mild, moderate, severe
    reason: str = ""
    matched_pattern: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_frustrated": self.is_frustrated,
            "level": self.level,
            "reason": self.reason,
            "matched_pattern": self.matched_pattern,
        }


@dataclass
class SarcasmResult:
    """Result of sarcasm detection."""

    is_sarcastic: bool = False
    confidence: float = 0.0
    matched_pattern: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_sarcastic": self.is_sarcastic,
            "confidence": self.confidence,
            "matched_pattern": self.matched_pattern,
        }


@dataclass
class B2BResult:
    """Result of B2B context detection."""

    is_b2b: bool = False
    company_context: str = ""
    contact_name: str = ""
    collaboration_type: str = ""  # partnership, previous_work, proposal, etc.

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_b2b": self.is_b2b,
            "company_context": self.company_context,
            "contact_name": self.contact_name,
            "collaboration_type": self.collaboration_type,
        }


@dataclass
class DetectedContext:
    """Complete detected context from a message."""

    # Emotional state
    sentiment: str = "neutral"  # frustrated, sarcastic, positive, neutral
    frustration_level: str = "none"  # none, mild, moderate, severe
    frustration_reason: str = ""

    # B2B context
    is_b2b: bool = False
    company_context: str = ""
    b2b_contact_name: str = ""

    # Intent (from existing classifier)
    intent: Intent = Intent.OTHER
    intent_confidence: float = 0.0
    intent_sub: str = ""
    objection_type: str = ""

    # Interest level
    interest_level: str = "none"  # strong, soft, none

    # User name
    user_name: str = ""

    # Flags
    is_first_message: bool = True
    is_meta_message: bool = False  # "ya te dije", "revisa el chat", etc.
    is_correction: bool = False  # "no quise decir eso", etc.

    # Generated alerts for LLM prompt
    alerts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sentiment": self.sentiment,
            "frustration_level": self.frustration_level,
            "frustration_reason": self.frustration_reason,
            "is_b2b": self.is_b2b,
            "company_context": self.company_context,
            "b2b_contact_name": self.b2b_contact_name,
            "intent": self.intent.value if self.intent else "other",
            "intent_confidence": self.intent_confidence,
            "intent_sub": self.intent_sub,
            "objection_type": self.objection_type,
            "interest_level": self.interest_level,
            "user_name": self.user_name,
            "is_first_message": self.is_first_message,
            "is_meta_message": self.is_meta_message,
            "is_correction": self.is_correction,
            "alerts": self.alerts,
        }

    def build_alerts(self) -> List[str]:
        """Generate list of alerts to inject into LLM prompt."""
        alerts = []

        # Frustration alerts (highest priority)
        if self.frustration_level == "severe":
            alerts.append(
                "\u26a0\ufe0f USUARIO MUY FRUSTRADO - Responde con m\u00e1xima empat\u00eda, "
                "reconoce el problema y ofrece soluci\u00f3n clara"
            )
        elif self.frustration_level == "moderate":
            alerts.append(
                "\u26a0\ufe0f Usuario frustrado - Muestra empat\u00eda y resuelve directamente"
            )
        elif self.frustration_level == "mild":
            alerts.append("\u2139\ufe0f Usuario algo impaciente - S\u00e9 conciso y directo")

        # Sarcasm alert
        if self.sentiment == "sarcastic":
            alerts.append(
                "\u2139\ufe0f Posible sarcasmo/iron\u00eda detectado - No interpretar literalmente"
            )

        # B2B alerts (high priority)
        if self.is_b2b:
            if self.company_context:
                alerts.append(
                    f"\U0001f3e2 CONTEXTO B2B: {self.company_context} - "
                    "Tratar como colaboraci\u00f3n profesional, NO como venta individual"
                )
            else:
                alerts.append(
                    "\U0001f3e2 Contexto B2B detectado - Tratar como colaboraci\u00f3n profesional"
                )

        # Meta-message alerts
        if self.is_meta_message:
            alerts.append(
                "\U0001f4dd Usuario hace referencia al historial - Revisar mensajes anteriores"
            )

        # Correction alerts
        if self.is_correction:
            alerts.append(
                "\U0001f504 Usuario corrigiendo malentendido - "
                "Reconocer error y ajustar respuesta"
            )

        # Interest level alerts
        if self.interest_level == "strong":
            alerts.append(
                "\U0001f525 Alta intenci\u00f3n de compra - Facilitar proceso de pago/reserva"
            )
        elif self.interest_level == "soft":
            alerts.append("\U0001f4a1 Inter\u00e9s detectado - Nutrir y cualificar")

        # Objection alerts
        if self.objection_type:
            objection_messages = {
                "price": "\U0001f4b0 Objeci\u00f3n de precio - Enfatizar valor, ofrecer alternativas",
                "time": "\u23f0 Objeci\u00f3n de tiempo - Mostrar flexibilidad y facilidad",
                "trust": "\U0001f914 Objeci\u00f3n de confianza - Ofrecer garant\u00edas y testimonios",
                "need": "\u2753 Objeci\u00f3n de necesidad - Conectar con sus problemas espec\u00edficos",
            }
            if self.objection_type in objection_messages:
                alerts.append(objection_messages[self.objection_type])

        # User name alert
        if self.user_name:
            alerts.append(f"\U0001f464 Nombre del usuario: {self.user_name}")

        # First message alert
        if self.is_first_message:
            alerts.append("\U0001f195 Primer mensaje - Dar bienvenida c\u00e1lida")

        self.alerts = alerts
        return alerts
