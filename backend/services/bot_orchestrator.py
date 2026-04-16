"""
BotOrchestrator - Orchestrates all bot autopilot services.

Complete flow:
1. Timing Service → Check active hours
2. Response Variator → Try quick pool response
3. Conversation Memory → Load context
4. LLM Generation → If no quick response
5. Memory Update → Save facts (regex extractor + LLM extractor)
6. Message Splitter → Split if too long
7. Calculate Delays → Natural timing

Part of Bot Autopilot Integration.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional

# CC-faithful feature flag: mirrors ENABLE_MEMORY_ENGINE in memory_engine.py.
# Checked at call site so postprocessing stays zero-latency (fire-and-forget).
_ENABLE_MEMORY_ENGINE = os.getenv("ENABLE_MEMORY_ENGINE", "false").lower() == "true"

from services.memory_service import (
    ConversationMemory,
    ConversationMemoryService,
    get_conversation_memory_service,
)
from services.message_splitter import (
    MessageSplitter,
    get_message_splitter,
)
from services.response_variator_v2 import ResponseVariatorV2, get_response_variator_v2
from services.timing_service import TimingService, get_timing_service

logger = logging.getLogger(__name__)


@dataclass
class BotResponse:
    """Response from the bot with metadata."""

    messages: List[str] = field(default_factory=list)
    delays: List[float] = field(default_factory=list)
    used_pool: bool = False
    should_escalate: bool = False
    total_delay: float = 0.0
    memory_updated: bool = False

    @property
    def single_message(self) -> str:
        """First message (for backwards compatibility)."""
        return self.messages[0] if self.messages else ""

    @property
    def is_multi_message(self) -> bool:
        """Check if response has multiple messages."""
        return len(self.messages) > 1

    @property
    def has_response(self) -> bool:
        """Check if there's at least one message."""
        return len(self.messages) > 0


class BotOrchestrator:
    """Main orchestrator for the bot autopilot."""

    def __init__(
        self,
        variator: ResponseVariatorV2 = None,
        memory_service: ConversationMemoryService = None,
        splitter: MessageSplitter = None,
        timing: TimingService = None,
    ):
        self.variator = variator or get_response_variator_v2()
        self.memory_service = memory_service or get_conversation_memory_service()
        self.splitter = splitter or get_message_splitter()
        self.timing = timing or get_timing_service()

    async def process_message(
        self,
        message: str,
        lead_id: str,
        creator_id: str,
        generate_with_llm: Callable = None,
        context: dict = None,
    ) -> BotResponse:
        """
        Process a message and generate response(s).

        Args:
            message: Message from the lead.
            lead_id: Lead identifier.
            creator_id: Creator identifier.
            generate_with_llm: Async function to generate with LLM.
            context: Additional context.

        Returns:
            BotResponse with message(s), delays, and metadata.
        """
        context = context or {}

        # ═══════════════════════════════════════════════════════════════════
        # STEP 1: Check active hours
        # ═══════════════════════════════════════════════════════════════════
        if not self.timing.is_active_hours():
            if not self.timing.should_respond_off_hours():
                logger.debug(f"Off hours, not responding to {lead_id}")
                return BotResponse(
                    messages=[],
                    delays=[],
                    used_pool=False,
                    should_escalate=False,
                    total_delay=0,
                )

        # ═══════════════════════════════════════════════════════════════════
        # STEP 2: Try quick pool response
        # ═══════════════════════════════════════════════════════════════════
        pool_match = self.variator.try_pool_response(
            lead_message=message,
            conv_id=lead_id,
            creator_id=creator_id,
        )

        if pool_match.matched and pool_match.response:
            delay = self.timing.calculate_delay(len(pool_match.response), len(message))
            logger.debug(f"Pool response for {lead_id}: {pool_match.category}")
            return BotResponse(
                messages=[pool_match.response],
                delays=[delay],
                used_pool=True,
                should_escalate=False,
                total_delay=delay,
            )

        # ═══════════════════════════════════════════════════════════════════
        # STEP 4: Load conversation memory
        # ═══════════════════════════════════════════════════════════════════
        memory = await self.memory_service.load(lead_id, creator_id)

        # Detect if user references past conversation
        references_past = self.memory_service.detect_past_reference(message)

        # Build memory context for LLM
        memory_context = self._build_memory_context(memory)

        # ═══════════════════════════════════════════════════════════════════
        # STEP 5: Generate with LLM
        # ═══════════════════════════════════════════════════════════════════
        if generate_with_llm:
            try:
                response_text = await generate_with_llm(
                    message=message,
                    memory_context=memory_context,
                    references_past=references_past,
                    **context,
                )
            except Exception as e:
                logger.error(f"LLM generation failed for {lead_id}: {e}")
                response_text = "Hola! 😊"
        else:
            # Fallback if no LLM function provided
            response_text = "Hola! 😊"

        # ═══════════════════════════════════════════════════════════════════
        # STEP 6: Update memory with facts
        # ═══════════════════════════════════════════════════════════════════
        try:
            # Extract facts from exchange
            facts = self.memory_service.extract_facts(message, response_text, True)
            for fact in facts:
                memory.add_fact(fact)

            # Update message count
            memory.total_messages += 1

            # Save memory
            await self.memory_service.save(memory)
            memory_updated = True
        except Exception as e:
            logger.error(f"Memory update failed for {lead_id}: {e}")
            memory_updated = False

        # ═══════════════════════════════════════════════════════════════════
        # STEP 6b: LLM semantic extraction (CC pattern — fire-and-forget)
        #
        # CC equivalent: stopHooks.ts:149
        #   void extractMemoriesModule!.executeExtractMemories(stopHookContext, ...)
        #
        # Invoked AFTER the regex extractor (STEP 6) — both run in parallel:
        #   - Regex extractor (ConversationMemoryService.extract_facts): handles
        #     PRICE_GIVEN / LINK_SHARED / PRODUCT_EXPLAINED — structural signals
        #     that have no CC equivalent (CC has no product catalog). Kept as-is.
        #   - LLM extractor (MemoryExtractor.extract_and_store): handles semantic
        #     facts — preferences, commitments, objections, personal_info, topics.
        #     This is the CC-equivalent path.
        #
        # Guards: ENABLE_MEMORY_ENGINE feature flag (same as postprocessing.py:431).
        # Fire-and-forget: asyncio.create_task() — never blocks the DM response.
        # ═══════════════════════════════════════════════════════════════════
        if _ENABLE_MEMORY_ENGINE:
            try:
                from services.memory_extraction import get_memory_extractor
                from services.memory_engine import get_memory_engine

                # Build conversation window: recent history + current exchange.
                # CC: stopHookContext.messages (all messages in current session).
                # Clonnect: last 3 turns from memory.last_messages + current turn.
                # memory.last_messages: List[{"role": str, "content": str, ...}]
                recent_history = [
                    {"role": m.get("role", "user"), "content": m.get("content", "")}
                    for m in (memory.last_messages[-6:] if memory.last_messages else [])
                    if m.get("content")
                ]
                conversation_msgs = recent_history + [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": response_text},
                ]

                extractor = get_memory_extractor(get_memory_engine())
                task = asyncio.create_task(
                    extractor.extract_and_store(
                        creator_id=creator_id,
                        lead_id=lead_id,
                        conversation_messages=conversation_msgs,
                    )
                )
                extractor.track_task(task)
                logger.debug(
                    "[MEMORY] LLM extraction scheduled fire-and-forget for lead=%s",
                    lead_id,
                )
            except Exception as e:
                logger.debug("[MEMORY] LLM extraction setup failed: %s", e)

        # ═══════════════════════════════════════════════════════════════════
        # STEP 7: Split message if too long
        # ═══════════════════════════════════════════════════════════════════
        message_parts = self.splitter.split(response_text, message)

        messages = [part.text for part in message_parts]
        delays = [part.delay_before for part in message_parts]

        return BotResponse(
            messages=messages,
            delays=delays,
            used_pool=False,
            should_escalate=False,
            total_delay=sum(delays),
            memory_updated=memory_updated,
        )

    def _build_memory_context(self, memory: ConversationMemory) -> str:
        """Build memory context string for LLM prompt."""
        if not memory or memory.total_messages == 0:
            return ""

        lines = []

        # Info already given
        if memory.info_given:
            lines.append("Info ya compartida:")
            for info_type, value in memory.info_given.items():
                lines.append(f"  - {info_type}: {value}")

        # Recent facts
        recent_facts = memory.facts[-5:] if memory.facts else []
        if recent_facts:
            lines.append("Datos recientes:")
            for fact in recent_facts:
                lines.append(f"  - {fact.fact_type.value}: {fact.content}")

        return "\n".join(lines) if lines else ""

    async def send_responses(
        self,
        bot_response: BotResponse,
        send_func: Callable,
    ):
        """
        Send responses with calculated delays.

        Args:
            bot_response: Response from process_message.
            send_func: Async function to send a single message.
        """
        for message, delay in zip(bot_response.messages, bot_response.delays):
            await asyncio.sleep(delay)
            await send_func(message)


# Singleton
_orchestrator: Optional[BotOrchestrator] = None


def get_bot_orchestrator() -> BotOrchestrator:
    """Get global BotOrchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = BotOrchestrator()
    return _orchestrator
