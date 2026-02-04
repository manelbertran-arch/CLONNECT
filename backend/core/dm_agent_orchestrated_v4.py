"""
DMAgentOrchestrated V4 - Con memoria contextual y conocimiento del creador.

V4 añade sobre V3:
- Memoria de conversación (últimos 20 mensajes)
- Conocimiento del creador (perfil, servicios, etc.)
- Contexto inyectado en cada respuesta
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from prompts.clone_system_prompt_v2 import STEFAN_METRICS, CreatorMetrics
from services.context_memory_service import get_context_memory_service
from services.creator_knowledge_service import get_creator_knowledge_service
from services.length_controller import STEFAN_LENGTH_CONFIG, detect_message_type, enforce_length
from services.question_remover import process_questions
from services.response_variator_v2 import get_response_variator_v2

logger = logging.getLogger(__name__)


@dataclass
class OrchestratedResponseV4:
    """Respuesta del orquestador V4."""

    messages: List[str]
    delays: List[float] = field(default_factory=list)
    should_escalate: bool = False
    used_pool: bool = False
    edge_case: Optional[str] = None
    context_used: bool = False
    knowledge_used: bool = False

    @property
    def primary_response(self) -> str:
        return self.messages[0] if self.messages else ""

    @property
    def total_delay(self) -> float:
        return sum(self.delays)

    @property
    def is_multi_message(self) -> bool:
        return len(self.messages) > 1


class DMAgentOrchestratedV4:
    """DM Agent V4 con contexto y conocimiento."""

    def __init__(self, creator_id: str, metrics: CreatorMetrics = None):
        self.creator_id = creator_id
        self.metrics = metrics or STEFAN_METRICS
        self.variator = get_response_variator_v2()
        self.context_service = get_context_memory_service()
        self.knowledge_service = get_creator_knowledge_service()
        self._llm_service = None
        self._initialized = False

    def _get_llm_service(self):
        """Get LLM service lazily."""
        if self._llm_service is None:
            try:
                from services.llm_service import get_llm_service

                self._llm_service = get_llm_service()
            except Exception as e:
                logger.error(f"Error getting LLM service: {e}")
        return self._llm_service

    def _build_system_prompt(self, lead_id: str, message: str) -> str:
        """Construye el system prompt con contexto y conocimiento."""

        # Cargar contexto de conversación
        context = self.context_service.load_conversation_context(
            lead_id=lead_id, creator_id=self.creator_id, max_messages=15
        )
        conversation_context = context.to_prompt_context()

        # Cargar conocimiento del creador
        creator_context = self.knowledge_service.get_context_for_message(
            creator_id=self.creator_id, message=message
        )

        prompt = f"""Eres Stefan (Stefano Bonanno). Responde EXACTAMENTE como Stefan en Instagram DM.

═══════════════════════════════════════════════════════════════════════════════
REGLAS CRÍTICAS
═══════════════════════════════════════════════════════════════════════════════

1. BREVEDAD: Respuestas de 10-25 caracteres típicamente. MÁXIMO 30.
2. NO PREGUNTES: Casi nunca hagas preguntas. Solo si es NECESARIO.
3. TONO: Casual, amigable. Usa "bro", "hermano", "crack", "dale".
4. EMOJIS: Moderado. No en cada mensaje.
5. SIN PUNTO FINAL: Usa ! o emoji o nada.

═══════════════════════════════════════════════════════════════════════════════
{creator_context}
═══════════════════════════════════════════════════════════════════════════════
CONTEXTO DE ESTA CONVERSACIÓN
═══════════════════════════════════════════════════════════════════════════════
{conversation_context if conversation_context else "Primera interacción con este lead."}

═══════════════════════════════════════════════════════════════════════════════
INSTRUCCIÓN FINAL
═══════════════════════════════════════════════════════════════════════════════
Responde al mensaje del lead de forma BREVE y NATURAL.
Si no sabes algo, di "déjame revisar y te confirmo".
NO inventes información.
"""

        return prompt

    def _post_process(self, response: str, lead_message: str) -> str:
        """Post-procesa la respuesta."""
        # Eliminar preguntas innecesarias
        response = process_questions(response, lead_message, question_rate=0.10)

        # Ajustar longitud
        response = enforce_length(response, lead_message)

        # Limpiar punto final
        if response.rstrip().endswith("."):
            response = response.rstrip()[:-1]
            if response and response[-1].isalnum():
                response += "!"

        return response

    async def _generate_with_llm(self, message: str, lead_id: str) -> str:
        """Genera respuesta con LLM + contexto."""
        llm = self._get_llm_service()

        if not llm:
            return "Dale! 😊"

        system_prompt = self._build_system_prompt(lead_id, message)

        try:
            response = await llm.generate(
                system_prompt=system_prompt,
                user_message=message,
                max_tokens=100,
                temperature=0.7,
            )

            return response.strip() if response else "Dale! 😊"

        except Exception as e:
            logger.error(f"Error en LLM: {e}")
            return "Dale! 😊"

    async def process_message(
        self, message: str, lead_id: str, context: Dict[str, Any] = None
    ) -> OrchestratedResponseV4:
        """Procesa mensaje con contexto completo."""

        # PASO 1: Intentar pool primero (para mensajes simples)
        pool_result = self.variator.try_pool_response(message)

        if pool_result.matched and pool_result.confidence >= 0.85:
            return OrchestratedResponseV4(
                messages=[pool_result.response], delays=[1.5], used_pool=True
            )

        # PASO 2: Generar con LLM + contexto
        llm_response = await self._generate_with_llm(message, lead_id)

        # PASO 3: Post-procesar
        final_response = self._post_process(llm_response, message)

        # PASO 4: Calcular delay
        msg_type = detect_message_type(message)
        delay = 2.0 if msg_type in ["greeting", "confirmation"] else 3.0

        return OrchestratedResponseV4(
            messages=[final_response],
            delays=[delay],
            used_pool=False,
            context_used=True,
            knowledge_used=True,
        )


# Factory
_agents_v4: Dict[str, DMAgentOrchestratedV4] = {}


async def get_orchestrated_agent_v4(creator_id: str) -> DMAgentOrchestratedV4:
    """Obtiene agente V4."""
    key = f"{creator_id}_v4"
    if key not in _agents_v4:
        _agents_v4[key] = DMAgentOrchestratedV4(creator_id)
    return _agents_v4[key]
