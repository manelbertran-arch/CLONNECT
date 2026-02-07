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
                from services.llm_service import LLMService

                self._llm_service = LLMService()
            except Exception as e:
                logger.error(f"Error creating LLM service: {e}")
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
REGLAS CRÍTICAS (OBLIGATORIAS)
═══════════════════════════════════════════════════════════════════════════════

1. BREVEDAD EXTREMA: Máximo 20-25 caracteres. NUNCA más de 30.
2. NO PREGUNTES: Casi nunca hagas preguntas. Responde, no preguntes.
3. SÉ DIRECTO: No evadas. Si sabes la respuesta, dila corta.
4. TONO: Casual, cálido. Usa "bro", "hermano", "crack".
5. SIN PUNTO FINAL: Termina con ! o emoji o nada.
6. AFECTO: Si te dicen "te quiero", responde cálido "Yo a ti! 💙"

EJEMPLOS DE RESPUESTAS CORRECTAS (OBLIGATORIOS):
- "Cuánto dura?" → "90 min" (DATO EXACTO, no evadas)
- "Te quiero!" → "Yo a ti! 💙" (CÁLIDO, no frío)
- "Estuvo genial!" → "Gracias! 😊" (CORTO)
- Preguntas de duración → Responde con el dato específico

═══════════════════════════════════════════════════════════════════════════════
{creator_context}
═══════════════════════════════════════════════════════════════════════════════
CONTEXTO DE ESTA CONVERSACIÓN
═══════════════════════════════════════════════════════════════════════════════
{conversation_context if conversation_context else "Primera interacción con este lead."}

═══════════════════════════════════════════════════════════════════════════════
INSTRUCCIÓN FINAL
═══════════════════════════════════════════════════════════════════════════════
Responde ULTRA BREVE (máx 25 chars). Sé directo y cálido.
Solo di "déjame revisar" si REALMENTE no tienes la info.
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
            logger.warning("No LLM service available")
            return "Dale! 😊"

        system_prompt = self._build_system_prompt(lead_id, message)

        try:
            response = await llm.generate(
                prompt=message,
                system_prompt=system_prompt,
                max_tokens=100,
                temperature=0.7,
            )

            if response and response.content:
                return response.content.strip()
            return "Dale! 😊"

        except Exception as e:
            logger.error(f"Error en LLM: {e}")
            return "Dale! 😊"

    async def process_message(
        self, message: str, lead_id: str, context: Dict[str, Any] = None
    ) -> OrchestratedResponseV4:
        """Procesa mensaje con contexto completo."""

        # PASO 1: Intentar pool primero (para mensajes simples)
        pool_result = self.variator.try_pool_response(message)

        # Pool con threshold más bajo para affection/praise (respuestas más cálidas)
        if pool_result.matched and pool_result.confidence >= 0.80:
            return OrchestratedResponseV4(
                messages=[pool_result.response], delays=[1.5], used_pool=True
            )

        # PASO 2: Generar con LLM + contexto
        llm_response = await self._generate_with_llm(message, lead_id)

        # PASO 3: Post-procesar
        final_response = self._post_process(llm_response, message)

        # PASO 4: Calcular delay
        msg_type = detect_message_type(message)
        delay = 2.0 if msg_type in ["saludo", "agradecimiento", "casual"] else 3.0

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
