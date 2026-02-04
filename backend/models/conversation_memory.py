"""
ConversationMemory - Memoria persistente de conversaciones.

Permite al bot:
- Recordar información ya dada (no repetir precios)
- Detectar "ya te lo dije"
- Continuar conversaciones después de días
- Rastrear temas pendientes
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class FactType(Enum):
    """Tipos de hechos que el bot puede recordar."""

    PRICE_GIVEN = "price_given"  # Se dio un precio
    LINK_SHARED = "link_shared"  # Se compartió un link
    PRODUCT_EXPLAINED = "product_explained"  # Se explicó un producto
    QUESTION_ASKED = "question_asked"  # Bot hizo una pregunta
    QUESTION_ANSWERED = "question_answered"  # Lead respondió pregunta
    APPOINTMENT_MENTIONED = "appointment"  # Se mencionó una cita
    NAME_USED = "name_used"  # Se usó el nombre del lead
    OBJECTION_RAISED = "objection"  # Lead puso una objeción
    INTEREST_EXPRESSED = "interest"  # Lead expresó interés


@dataclass
class ConversationFact:
    """Un hecho extraído de la conversación."""

    fact_type: FactType
    content: str  # "Precio coaching: 150€"
    message_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    confidence: float = 0.9

    def to_dict(self) -> dict:
        return {
            "fact_type": self.fact_type.value,
            "content": self.content,
            "message_id": self.message_id,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationFact":
        return cls(
            fact_type=FactType(data["fact_type"]),
            content=data["content"],
            message_id=data.get("message_id"),
            timestamp=(
                datetime.fromisoformat(data["timestamp"])
                if data.get("timestamp")
                else datetime.now()
            ),
            confidence=data.get("confidence", 0.9),
        )


@dataclass
class ConversationMemory:
    """Memoria persistente de una conversación."""

    lead_id: str
    creator_id: str

    # Facts extraídos
    facts: List[ConversationFact] = field(default_factory=list)

    # Información ya dada (para no repetir)
    info_given: Dict[str, str] = field(default_factory=dict)
    # Ejemplo: {"precio_coaching": "150€", "link_pago": "https://..."}

    # Estado conversacional
    last_topic: Optional[str] = None
    pending_questions: List[str] = field(default_factory=list)
    unanswered_lead_questions: List[str] = field(default_factory=list)

    # Metadata
    last_interaction: Optional[datetime] = None
    total_messages: int = 0
    conversation_started: Optional[datetime] = None

    def has_given_info(self, info_type: str) -> bool:
        """Verifica si ya se dio cierta información."""
        return info_type in self.info_given

    def get_info(self, info_type: str) -> Optional[str]:
        """Obtiene información previamente dada."""
        return self.info_given.get(info_type)

    def add_fact(self, fact: ConversationFact):
        """Añade un hecho a la memoria."""
        self.facts.append(fact)

        # Actualizar info_given si corresponde
        if fact.fact_type == FactType.PRICE_GIVEN:
            self.info_given["precio"] = fact.content
        elif fact.fact_type == FactType.LINK_SHARED:
            self.info_given["link"] = fact.content
        elif fact.fact_type == FactType.PRODUCT_EXPLAINED:
            key = f"explicado_{fact.content.lower().replace(' ', '_')}"
            self.info_given[key] = "sí"

    def get_days_since_last_interaction(self) -> Optional[int]:
        """Días desde última interacción."""
        if not self.last_interaction:
            return None
        delta = datetime.now() - self.last_interaction
        return delta.days

    def get_context_summary(self) -> str:
        """Genera resumen de contexto para el LLM."""
        lines = []

        # Tiempo desde última interacción
        days = self.get_days_since_last_interaction()
        if days and days > 0:
            lines.append(f"⏰ Última interacción hace {days} días")

        # Información ya dada
        if self.info_given:
            lines.append("📋 Ya le diste esta información (NO REPETIR):")
            for key, value in self.info_given.items():
                lines.append(f"  • {key}: {value}")

        # Último tema
        if self.last_topic:
            lines.append(f"💬 Último tema: {self.last_topic}")

        # Preguntas pendientes del lead
        if self.unanswered_lead_questions:
            lines.append("❓ Preguntas del lead sin responder:")
            for q in self.unanswered_lead_questions[-3:]:
                lines.append(f"  • {q}")

        return "\n".join(lines) if lines else ""

    def to_dict(self) -> dict:
        return {
            "lead_id": self.lead_id,
            "creator_id": self.creator_id,
            "facts": [f.to_dict() for f in self.facts],
            "info_given": self.info_given,
            "last_topic": self.last_topic,
            "pending_questions": self.pending_questions,
            "unanswered_lead_questions": self.unanswered_lead_questions,
            "last_interaction": (
                self.last_interaction.isoformat() if self.last_interaction else None
            ),
            "total_messages": self.total_messages,
            "conversation_started": (
                self.conversation_started.isoformat()
                if self.conversation_started
                else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConversationMemory":
        memory = cls(
            lead_id=data["lead_id"],
            creator_id=data["creator_id"],
        )
        memory.facts = [ConversationFact.from_dict(f) for f in data.get("facts", [])]
        memory.info_given = data.get("info_given", {})
        memory.last_topic = data.get("last_topic")
        memory.pending_questions = data.get("pending_questions", [])
        memory.unanswered_lead_questions = data.get("unanswered_lead_questions", [])
        memory.last_interaction = (
            datetime.fromisoformat(data["last_interaction"])
            if data.get("last_interaction")
            else None
        )
        memory.total_messages = data.get("total_messages", 0)
        memory.conversation_started = (
            datetime.fromisoformat(data["conversation_started"])
            if data.get("conversation_started")
            else None
        )
        return memory
