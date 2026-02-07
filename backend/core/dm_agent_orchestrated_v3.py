"""
DMAgentOrchestrated V3 - Complete integration of all improvements.

Improvements over V2:
- Strict length control (target 20 chars, max 28)
- Question removal post-processor
- Expanded response pools
- Post-processing pipeline: questions -> length -> punctuation
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from prompts.clone_system_prompt_v2 import (
    STEFAN_METRICS,
    CreatorMetrics,
    build_clone_system_prompt,
    build_response_guidelines,
    get_stefan_prompt,
)
from services.bot_orchestrator import BotResponse, get_bot_orchestrator
from services.length_controller import STEFAN_LENGTH_CONFIG, detect_message_type, enforce_length
from services.question_remover import process_questions
from services.response_variator_v2 import get_response_variator_v2

logger = logging.getLogger(__name__)


@dataclass
class OrchestratedResponseV3:
    """V3 orchestrator response."""

    messages: List[str]
    delays: List[float] = field(default_factory=list)
    should_escalate: bool = False
    used_pool: bool = False
    edge_case: Optional[str] = None
    processing_steps: List[str] = field(default_factory=list)
    original_response: Optional[str] = None

    @property
    def primary_response(self) -> str:
        return self.messages[0] if self.messages else ""

    @property
    def total_delay(self) -> float:
        return sum(self.delays)

    @property
    def is_multi_message(self) -> bool:
        return len(self.messages) > 1


class DMAgentOrchestratedV3:
    """DM Agent V3 with all improvements integrated."""

    def __init__(self, creator_id: str, metrics: CreatorMetrics = None):
        self.creator_id = creator_id
        self.metrics = metrics or STEFAN_METRICS
        self.variator = get_response_variator_v2()
        self._dm_agent = None
        self._initialized = False

    def _get_system_prompt(self, relationship_context: str = "") -> str:
        """Generate system prompt with adjusted metrics."""
        # Adjust metrics to be stricter
        adjusted_metrics = CreatorMetrics(
            name=self.metrics.name,
            avg_length=20,  # Shorter than V2
            median_length=18,
            question_rate=0.05,  # Stricter
            emoji_rate=self.metrics.emoji_rate,
            avg_emojis_per_msg=self.metrics.avg_emojis_per_msg,
            uses_period=False,
            period_rate=0.01,
            exclamation_rate=self.metrics.exclamation_rate,
            common_phrases=self.metrics.common_phrases,
            vocabulary=self.metrics.vocabulary,
            tone_words=self.metrics.tone_words,
            elaborates_on_emotion=self.metrics.elaborates_on_emotion,
            elaborates_on_questions=False,
            uses_dry_responses=True,
            dry_response_rate=0.25,
        )

        base = build_clone_system_prompt(adjusted_metrics, relationship_context)
        guidelines = build_response_guidelines(adjusted_metrics)

        # Add brevity emphasis
        brevity_rules = """

═══════════════════════════════════════════════════════════════════════════════
BREVITY RULES (CRITICAL)
═══════════════════════════════════════════════════════════════════════════════

IMPORTANT: Your responses MUST be SHORT. Stefan typically responds with 10-25 characters.

CORRECT LENGTH EXAMPLES:
- "Dale!" (5c) ✅
- "Genial! 😊" (9c) ✅
- "Qué bien hermano!" (17c) ✅
- "Un abrazo!" (10c) ✅

INCORRECT LENGTH EXAMPLES:
- "¡Genial! Me alegra mucho escuchar eso! 😊" (38c) ❌ TOO LONG
- "¡Qué bueno que te fue bien! Espero que sigas así! 💪" (50c) ❌ TOO LONG

RULE: If your response exceeds 28 characters, SHORTEN IT.
"""

        return base + guidelines + brevity_rules

    async def _init_dm_agent(self):
        """Initialize DM agent."""
        if not self._initialized:
            try:
                from core.dm_agent_v2 import DMResponderAgent

                self._dm_agent = DMResponderAgent(creator_id=self.creator_id)
                self._initialized = True
            except Exception as e:
                logger.error(f"Error initializing DM agent: {e}")

    def _post_process(self, response: str, lead_message: str) -> str:
        """
        Post-process response applying all improvements.
        """
        # 1. Remove unnecessary questions
        response = process_questions(
            response, lead_message, question_rate=self.metrics.question_rate
        )

        # 2. Adjust length
        response = enforce_length(response, lead_message)

        # 3. Clean final period if Stefan doesn't use it
        if self.metrics.period_rate < 0.05:
            if response.rstrip().endswith("."):
                response = response.rstrip()[:-1]
                if response and response[-1].isalnum():
                    response += "!"

        return response

    async def _generate_with_llm(self, message: str, **kwargs) -> str:
        """Generate response with LLM."""
        await self._init_dm_agent()

        if not self._dm_agent:
            return "Dale! 😊"

        system_prompt = self._get_system_prompt(kwargs.get("relationship_context", ""))

        try:
            response = await self._dm_agent.process_dm(
                message=message,
                sender_id=kwargs.get("lead_id", "unknown"),
                metadata={"system_prompt_override": system_prompt},
            )

            if hasattr(response, "response_text"):
                return response.response_text
            elif hasattr(response, "content"):
                return response.content
            elif hasattr(response, "text"):
                return response.text
            elif isinstance(response, str):
                return response
            else:
                return str(response)

        except Exception as e:
            logger.error(f"Error in LLM: {e}")
            return "Dale! 😊"

    async def process_message(
        self, message: str, lead_id: str, context: Dict[str, Any] = None
    ) -> OrchestratedResponseV3:
        """Process message with all V3 improvements."""

        context = context or {}
        steps = []

        # STEP 1: Try pool first
        pool_result = self.variator.try_pool_response(message)

        if pool_result.matched and pool_result.confidence >= 0.8:
            steps.append(f"pool_matched:{pool_result.category}")

            return OrchestratedResponseV3(
                messages=[pool_result.response],
                delays=[1.5],
                used_pool=True,
                processing_steps=steps,
            )

        steps.append("llm_generation")

        # STEP 2: Generate with LLM
        llm_response = await self._generate_with_llm(message=message, lead_id=lead_id, **context)

        original_response = llm_response

        # STEP 3: Post-process
        steps.append("post_processing")
        final_response = self._post_process(llm_response, message)

        # STEP 4: Calculate natural delay
        msg_type = detect_message_type(message)
        delay = 2.0 if msg_type in ["saludo", "agradecimiento", "casual"] else 3.0

        return OrchestratedResponseV3(
            messages=[final_response],
            delays=[delay],
            used_pool=False,
            processing_steps=steps,
            original_response=original_response,
        )


# Factory
_agents_v3: Dict[str, DMAgentOrchestratedV3] = {}


async def get_orchestrated_agent_v3(
    creator_id: str, metrics: CreatorMetrics = None
) -> DMAgentOrchestratedV3:
    """Get V3 agent."""
    key = f"{creator_id}_v3"
    if key not in _agents_v3:
        _agents_v3[key] = DMAgentOrchestratedV3(creator_id, metrics)
    return _agents_v3[key]
