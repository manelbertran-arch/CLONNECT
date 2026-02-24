"""
DMAgentOrchestrated - Wrapper that integrates BotOrchestrator with DM Agent.

This module connects the complete orchestration system (memory, variations,
timing, edge cases, multi-message) with the existing dm_agent_v2 flow.

Part of Bot Autopilot Integration.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from services.bot_orchestrator import get_bot_orchestrator

logger = logging.getLogger(__name__)


@dataclass
class OrchestratedResponse:
    """Orchestrated response with all metadata."""

    messages: List[str]
    delays: List[float]
    should_escalate: bool
    used_pool: bool
    edge_case: Optional[str]
    raw_llm_response: Optional[str] = None

    @property
    def primary_response(self) -> str:
        """Primary response (first or only message)."""
        return self.messages[0] if self.messages else ""

    @property
    def is_multi_message(self) -> bool:
        """Check if response has multiple messages."""
        return len(self.messages) > 1

    @property
    def total_delay(self) -> float:
        """Total delay for all messages."""
        return sum(self.delays)


class DMAgentOrchestrated:
    """
    DM Agent with full orchestration.

    Flow:
    1. Orchestrator processes the message
    2. If LLM is needed, uses dm_agent_v2 to generate
    3. Orchestrator post-processes (split, timing, etc.)
    """

    def __init__(self, creator_id: str):
        self.creator_id = creator_id
        self.orchestrator = get_bot_orchestrator()
        self._dm_agent = None
        self._dm_agent_initialized = False

    async def _get_dm_agent(self):
        """Lazy load the original dm_agent."""
        if not self._dm_agent_initialized:
            try:
                from core.dm_agent_v2 import DMResponderAgent

                self._dm_agent = DMResponderAgent(creator_id=self.creator_id)
                self._dm_agent_initialized = True
                logger.info(f"DM Agent initialized for {self.creator_id}")
            except Exception as e:
                logger.error(f"Failed to initialize DM Agent: {e}")
                self._dm_agent = None

        return self._dm_agent

    async def _generate_with_llm(
        self,
        message: str,
        memory_context: str = "",
        references_past: bool = False,
        **kwargs,
    ) -> str:
        """
        Generate response using LLM through dm_agent_v2.

        This method is passed to the orchestrator as a callback.
        """
        agent = await self._get_dm_agent()

        if agent is None:
            logger.warning("DM Agent not available, using fallback")
            return "Hola! Déjame revisar y te respondo 😊"

        try:
            # Build additional context
            additional_context = ""

            if memory_context:
                additional_context += f"\n{memory_context}\n"

            if references_past:
                additional_context += (
                    "\n⚠️ El usuario hace referencia a una conversación pasada. "
                    "Revisa el contexto previo.\n"
                )

            # Get lead_id from kwargs
            lead_id = kwargs.get("lead_id", "unknown")

            # Call the original agent
            response = await agent.process_dm(
                message=message,
                sender_id=lead_id,
                metadata={"additional_context": additional_context, **kwargs},
            )

            # Extract text from response
            if hasattr(response, "response_text"):
                return response.response_text
            elif hasattr(response, "text"):
                return response.text
            elif hasattr(response, "content"):
                return response.content
            elif isinstance(response, str):
                return response
            else:
                # Try to get the first attribute that looks like text
                for attr in ["message", "reply", "answer"]:
                    if hasattr(response, attr):
                        return getattr(response, attr)
                return str(response)

        except Exception as e:
            logger.error(f"Error in LLM generation: {e}")
            return "Hola! Déjame revisar y te respondo 😊"

    async def process_message(
        self,
        message: str,
        lead_id: str,
        context: Dict[str, Any] = None,
    ) -> OrchestratedResponse:
        """
        Process a message with full orchestration.

        Args:
            message: Message from the lead
            lead_id: Lead identifier
            context: Additional context

        Returns:
            OrchestratedResponse with messages, delays, and metadata
        """
        context = context or {}
        context["lead_id"] = lead_id

        # Use orchestrator with our LLM callback
        bot_response = await self.orchestrator.process_message(
            message=message,
            lead_id=lead_id,
            creator_id=self.creator_id,
            generate_with_llm=self._generate_with_llm,
            context=context,
        )

        return OrchestratedResponse(
            messages=bot_response.messages,
            delays=bot_response.delays,
            should_escalate=bot_response.should_escalate,
            used_pool=bot_response.used_pool,
            edge_case=bot_response.edge_case,
        )

    async def send_response(
        self,
        response: OrchestratedResponse,
        send_func: callable,
    ):
        """
        Send the response with natural delays.

        Args:
            response: Orchestrated response
            send_func: Async function to send a single message
        """
        for msg, delay in zip(response.messages, response.delays):
            await asyncio.sleep(delay)
            await send_func(msg)


# Factory function with caching
_agents: Dict[str, DMAgentOrchestrated] = {}


async def get_orchestrated_agent(creator_id: str) -> DMAgentOrchestrated:
    """Get or create an orchestrated agent for a creator."""
    if creator_id not in _agents:
        _agents[creator_id] = DMAgentOrchestrated(creator_id)
    return _agents[creator_id]


def clear_agent_cache():
    """Clear the agent cache (useful for testing)."""
    global _agents
    _agents = {}
