"""
DMAgentOrchestrated V2 - Con prompt universal mejorado.
"""
import asyncio
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import logging

from services.bot_orchestrator import get_bot_orchestrator, BotResponse
from prompts.clone_system_prompt_v2 import (
    get_stefan_prompt, 
    build_clone_system_prompt,
    build_response_guidelines,
    STEFAN_METRICS,
    CreatorMetrics
)

logger = logging.getLogger(__name__)


@dataclass
class OrchestratedResponseV2:
    messages: List[str]
    delays: List[float]
    should_escalate: bool
    used_pool: bool
    edge_case: Optional[str]
    
    @property
    def primary_response(self) -> str:
        return self.messages[0] if self.messages else ""
    
    @property
    def is_multi_message(self) -> bool:
        return len(self.messages) > 1
    
    @property
    def total_delay(self) -> float:
        return sum(self.delays)


class DMAgentOrchestratedV2:
    """DM Agent con prompt universal V2."""
    
    def __init__(self, creator_id: str, metrics: CreatorMetrics = None):
        self.creator_id = creator_id
        self.metrics = metrics or STEFAN_METRICS
        self.orchestrator = get_bot_orchestrator()
        self._system_prompt = None
        self._dm_agent = None
        self._initialized = False
    
    def _get_system_prompt(self, relationship_context: str = "") -> str:
        """Genera el system prompt con las métricas del creador."""
        base = build_clone_system_prompt(self.metrics, relationship_context)
        guidelines = build_response_guidelines(self.metrics)
        return base + guidelines
    
    async def _init_dm_agent(self):
        """Inicializa el DM agent original."""
        if not self._initialized:
            try:
                from core.dm_agent_v2 import DMResponderAgent
                self._dm_agent = DMResponderAgent(creator_id=self.creator_id)
                self._initialized = True
            except Exception as e:
                logger.error(f"Error initializing DM agent: {e}")
    
    async def _generate_with_llm(
        self,
        message: str,
        memory_context: str = "",
        references_past: bool = False,
        edge_guidance: str = "",
        relationship_context: str = "",
        **kwargs
    ) -> str:
        """Genera respuesta con el LLM usando el prompt V2."""
        
        await self._init_dm_agent()
        
        if not self._dm_agent:
            return "Hola! 😊"
        
        # Construir prompt mejorado
        system_prompt = self._get_system_prompt(relationship_context)
        
        # Añadir contexto adicional
        additional_context = f"""
{system_prompt}

═══════════════════════════════════════════════════════════════════════════════
CONTEXTO DE ESTA CONVERSACIÓN
═══════════════════════════════════════════════════════════════════════════════
{memory_context if memory_context else "Primera interacción con este lead."}

{f"⚠️ El lead hace referencia a conversación pasada." if references_past else ""}
{edge_guidance if edge_guidance else ""}
═══════════════════════════════════════════════════════════════════════════════
MENSAJE DEL LEAD
═══════════════════════════════════════════════════════════════════════════════
"{message}"

═══════════════════════════════════════════════════════════════════════════════
TU RESPUESTA (recuerda: CORTA, sin preguntas innecesarias, como {self.metrics.name})
═══════════════════════════════════════════════════════════════════════════════
"""
        
        try:
            response = await self._dm_agent.process_dm(
                message=message,
                sender_id=kwargs.get('lead_id', 'unknown'),
                metadata={
                    'system_prompt_override': additional_context,
                    **kwargs
                }
            )
            
            if hasattr(response, 'content'):
                return response.content
            elif hasattr(response, 'response_text'):
                return response.response_text
            elif hasattr(response, 'text'):
                return response.text
            elif isinstance(response, str):
                return response
            else:
                return str(response)
                
        except Exception as e:
            logger.error(f"Error en LLM: {e}")
            return "Dale! 😊"
    
    async def process_message(
        self,
        message: str,
        lead_id: str,
        context: Dict[str, Any] = None
    ) -> OrchestratedResponseV2:
        """Procesa mensaje con orquestación V2."""
        
        context = context or {}
        context['lead_id'] = lead_id
        
        bot_response = await self.orchestrator.process_message(
            message=message,
            lead_id=lead_id,
            creator_id=self.creator_id,
            generate_with_llm=self._generate_with_llm,
            context=context
        )
        
        return OrchestratedResponseV2(
            messages=bot_response.messages,
            delays=bot_response.delays,
            should_escalate=bot_response.should_escalate,
            used_pool=bot_response.used_pool,
            edge_case=bot_response.edge_case
        )


# Factory
_agents_v2: Dict[str, DMAgentOrchestratedV2] = {}

async def get_orchestrated_agent_v2(creator_id: str, metrics: CreatorMetrics = None) -> DMAgentOrchestratedV2:
    """Obtiene agente V2."""
    key = f"{creator_id}_v2"
    if key not in _agents_v2:
        _agents_v2[key] = DMAgentOrchestratedV2(creator_id, metrics)
    return _agents_v2[key]
