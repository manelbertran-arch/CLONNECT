"""
Context Memory Service - Proporciona contexto de conversación al bot.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConversationContext:
    """Contexto de una conversación."""

    lead_id: str
    lead_name: Optional[str] = None
    recent_messages: List[Dict[str, str]] = field(default_factory=list)
    extracted_facts: Dict[str, Any] = field(default_factory=dict)
    relationship_type: Optional[str] = None
    last_interaction: Optional[datetime] = None
    topics_discussed: List[str] = field(default_factory=list)

    def to_prompt_context(self) -> str:
        """Convierte el contexto a texto para el prompt."""
        lines = []

        if self.lead_name:
            lines.append(f"Estás hablando con: {self.lead_name}")

        if self.relationship_type:
            lines.append(f"Relación: {self.relationship_type}")

        if self.extracted_facts:
            lines.append("Datos del lead:")
            for key, value in self.extracted_facts.items():
                lines.append(f"  - {key}: {value}")

        if self.recent_messages:
            lines.append("\nÚltimos mensajes de la conversación:")
            for msg in self.recent_messages[-10:]:
                direction = "Lead" if msg.get("role") == "user" else "Tú"
                lines.append(f"  {direction}: {msg.get('content', '')}")

        if self.topics_discussed:
            lines.append(f"\nTemas discutidos: {', '.join(self.topics_discussed)}")

        return "\n".join(lines)


class ContextMemoryService:
    """Servicio de memoria contextual."""

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or os.environ.get("DATABASE_URL")
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            from api.database import engine as shared_engine
            if shared_engine is not None:
                self._engine = shared_engine
            else:
                from sqlalchemy import create_engine
                self._engine = create_engine(self.db_url)
        return self._engine

    def load_conversation_context(
        self, lead_id: str, creator_id: str, max_messages: int = 20
    ) -> ConversationContext:
        """
        Carga el contexto de una conversación.

        Args:
            lead_id: ID del lead
            creator_id: ID del creador
            max_messages: Máximo de mensajes a cargar

        Returns:
            ConversationContext con toda la información disponible
        """
        from sqlalchemy import text

        context = ConversationContext(lead_id=lead_id)

        try:
            engine = self._get_engine()

            with engine.connect() as conn:
                # Obtener info del lead
                lead_info = conn.execute(
                    text(
                        """
                    SELECT username, full_name
                    FROM leads
                    WHERE id = :lid
                """
                    ),
                    {"lid": lead_id},
                ).fetchone()

                if lead_info:
                    context.lead_name = lead_info[1] or lead_info[0]

                # Obtener mensajes recientes
                messages = conn.execute(
                    text(
                        """
                    SELECT content, role, created_at
                    FROM messages
                    WHERE lead_id = :lid
                    AND content IS NOT NULL
                    AND content != ''
                    ORDER BY created_at DESC
                    LIMIT :limit
                """
                    ),
                    {"lid": lead_id, "limit": max_messages},
                ).fetchall()

                context.recent_messages = [
                    {"content": m[0], "role": m[1], "timestamp": str(m[2])}
                    for m in reversed(messages)
                ]

                if messages:
                    context.last_interaction = messages[0][2]

                # Extraer hechos de los mensajes
                if not context.extracted_facts:
                    context.extracted_facts = self._extract_facts_from_messages(
                        context.recent_messages
                    )

        except Exception as e:
            logger.error(f"Error loading context: {e}")

        return context

    def _extract_facts_from_messages(self, messages: List[Dict]) -> Dict[str, Any]:
        """Extrae hechos importantes de los mensajes."""
        facts = {}

        patterns = {
            "location_mentioned": [
                "barcelona",
                "madrid",
                "argentina",
                "españa",
                "brazil",
                "italia",
            ],
            "activity_mentioned": [
                "yoga",
                "gym",
                "entrenar",
                "clase",
                "sesión",
                "evento",
                "retiro",
            ],
            "time_reference": [
                "ayer",
                "mañana",
                "semana",
                "mes",
                "lunes",
                "martes",
                "miércoles",
            ],
        }

        all_text = " ".join(
            m["content"].lower() for m in messages if m.get("role") == "user"
        )

        for fact_type, keywords in patterns.items():
            matches = [kw for kw in keywords if kw in all_text]
            if matches:
                facts[fact_type] = matches

        return facts

    def get_recent_summary(self, lead_id: str, creator_id: str) -> str:
        """Obtiene un resumen breve de la conversación reciente."""
        context = self.load_conversation_context(lead_id, creator_id, max_messages=5)

        if not context.recent_messages:
            return "Primera conversación con este lead."

        summary_parts = []

        if context.lead_name:
            summary_parts.append(f"Hablando con {context.lead_name}")

        if context.relationship_type:
            summary_parts.append(f"({context.relationship_type})")

        for msg in reversed(context.recent_messages):
            if msg.get("role") == "user":
                summary_parts.append(f"Último mensaje: \"{msg['content'][:50]}...\"")
                break

        return " | ".join(summary_parts) if summary_parts else "Contexto no disponible"


# Singleton
_context_service: Optional[ContextMemoryService] = None


def get_context_memory_service() -> ContextMemoryService:
    """Obtiene instancia del servicio de contexto."""
    global _context_service
    if _context_service is None:
        _context_service = ContextMemoryService()
    return _context_service
