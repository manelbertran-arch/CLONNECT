"""
Creator Knowledge Service - Base de conocimiento del creador.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CreatorKnowledge:
    """Conocimiento sobre un creador."""

    creator_id: str
    name: str
    nickname: str
    location: str
    profession: List[str]
    services: List[str]
    communication_style: Dict[str, Any]
    values: List[str]
    content_themes: List[str]
    faqs: Dict[str, str]

    def get_relevant_info(self, query: str) -> str:
        """Obtiene información relevante para una consulta."""
        query_lower = query.lower()
        info_parts = []

        if any(w in query_lower for w in ["precio", "cuesta", "coste", "valor"]):
            info_parts.append(
                "NOTA: No tengo los precios actualizados. Sugiere contactar directamente."
            )

        if any(w in query_lower for w in ["donde", "ubicación", "dirección", "lugar"]):
            info_parts.append(f"Ubicación: {self.location}")

        if any(w in query_lower for w in ["servicio", "ofrece", "programa", "sesión"]):
            info_parts.append(f"Servicios: {', '.join(self.services)}")

        if any(w in query_lower for w in ["quién", "quien", "eres", "haces"]):
            info_parts.append(f"Profesión: {', '.join(self.profession)}")

        if any(w in query_lower for w in ["dura", "duración", "tiempo", "cuánto dura", "cuanto dura"]):
            if "cuanto_dura" in self.faqs:
                info_parts.append(f"RESPONDE EXACTAMENTE: {self.faqs['cuanto_dura']}")

        for question, answer in self.faqs.items():
            if any(word in query_lower for word in question.lower().split()):
                info_parts.append(f"FAQ: {answer}")
                break

        return "\n".join(info_parts) if info_parts else ""

    def to_system_context(self) -> str:
        """Genera contexto para el system prompt."""
        return f"""
INFORMACIÓN SOBRE TI ({self.name}):
- Nombre: {self.name} (te llaman {self.nickname})
- Ubicación: {self.location}
- Profesión: {', '.join(self.profession)}
- Servicios que ofreces: {', '.join(self.services)}
- Valores: {', '.join(self.values)}
- Temas de contenido: {', '.join(self.content_themes)}

REGLAS DE CONOCIMIENTO:
- Si te preguntan precios específicos, di que les pasas la info por privado o que consulten la web
- Si te preguntan algo que no sabes, di "déjame revisarlo y te confirmo"
- Nunca inventes información sobre eventos, fechas o precios
"""


class CreatorKnowledgeService:
    """Servicio de conocimiento del creador."""

    def __init__(self, knowledge_dir: str = "data/stefan_knowledge"):
        self.knowledge_dir = knowledge_dir
        self._knowledge_cache: Dict[str, CreatorKnowledge] = {}

    def load_knowledge(self, creator_id: str) -> Optional[CreatorKnowledge]:
        """Carga el conocimiento de un creador."""

        if creator_id in self._knowledge_cache:
            return self._knowledge_cache[creator_id]

        profile_path = os.path.join(self.knowledge_dir, "stefan_profile.json")

        try:
            with open(profile_path, "r") as f:
                profile = json.load(f)

            knowledge = CreatorKnowledge(
                creator_id=creator_id,
                name=profile.get("name", "Creator"),
                nickname=profile.get("nickname", "Creator"),
                location=profile.get("location", "Unknown"),
                profession=profile.get("profession", []),
                services=profile.get("services", []),
                communication_style=profile.get("communication_style", {}),
                values=profile.get("values", []),
                content_themes=profile.get("content_themes", []),
                faqs=profile.get("faqs", {}),
            )

            self._knowledge_cache[creator_id] = knowledge
            return knowledge

        except Exception as e:
            logger.error(f"Error loading knowledge: {e}")
            return None

    def get_context_for_message(self, creator_id: str, message: str) -> str:
        """Obtiene contexto relevante para un mensaje."""

        knowledge = self.load_knowledge(creator_id)
        if not knowledge:
            return ""

        base_context = knowledge.to_system_context()
        relevant_info = knowledge.get_relevant_info(message)

        if relevant_info:
            return (
                f"{base_context}\n\nINFORMACIÓN RELEVANTE PARA ESTA CONSULTA:\n{relevant_info}"
            )

        return base_context


# Singleton
_knowledge_service: Optional[CreatorKnowledgeService] = None


def get_creator_knowledge_service() -> CreatorKnowledgeService:
    """Obtiene instancia del servicio."""
    global _knowledge_service
    if _knowledge_service is None:
        _knowledge_service = CreatorKnowledgeService()
    return _knowledge_service
