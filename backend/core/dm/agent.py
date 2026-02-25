"""
DM Responder Agent V2 - Slim Orchestrator.

Coordinates all services to process Instagram DMs.
All business logic is delegated to modular phase functions.
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

from core.agent_config import AGENT_THRESHOLDS
from core.dm.models import (
    AgentConfig,
    DMResponse,
    ENABLE_CHAIN_OF_THOUGHT,
    ENABLE_FRUSTRATION_DETECTION,
    ENABLE_GUARDRAILS,
)
from services import (
    InstagramService,
    IntentClassifier,
    LeadService,
    LeadStage,
    LLMService,
    MemoryStore,
    PromptBuilder,
)

logger = logging.getLogger(__name__)


class DMResponderAgentV2:
    """
    DM Responder Agent V2 - Slim Orchestrator.

    Coordinates all services to process Instagram DMs.
    All business logic is delegated to modular services.
    """

    def __init__(
        self,
        creator_id: str,
        config: Optional[AgentConfig] = None,
        personality: Optional[Dict[str, Any]] = None,
        products: Optional[List[Dict]] = None,
    ):
        self.creator_id = creator_id
        self.config = config or AgentConfig()

        if personality is None or products is None:
            self.personality, self.products, self.style_prompt = self._load_creator_data(
                creator_id, personality, products
            )
        else:
            self.personality = personality
            self.products = products
            self.style_prompt = ""

        self._enrich_style_with_profile()

        self.calibration = None
        try:
            from services.calibration_loader import load_calibration

            self.calibration = load_calibration(creator_id)
            if self.calibration:
                logger.info(
                    f"Loaded calibration for {creator_id}: "
                    f"fse={len(self.calibration.get('few_shot_examples', []))}"
                )
        except Exception as e:
            logger.warning(f"Could not load calibration for {creator_id}: {e}")

        self._init_services()

        logger.info(
            f"DMResponderAgentV2 initialized for creator {creator_id} "
            f"(personality: {self.personality.get('name', 'default')}, "
            f"products: {len(self.products)}, "
            f"style: {len(self.style_prompt)} chars)"
        )

    def _load_creator_data(self, creator_id, personality, products) -> tuple:
        """Load creator personality, products, and style from database."""
        loaded_personality = personality or {}
        loaded_products = products or []
        style_prompt = ""

        try:
            from services.creator_style_loader import get_creator_style_prompt

            style_prompt = get_creator_style_prompt(creator_id)
            if style_prompt:
                logger.info(f"Loaded style prompt for {creator_id}: {len(style_prompt)} chars")
        except Exception as e:
            logger.warning(f"Could not load style prompt for {creator_id}: {e}")

        try:
            from core.creator_data_loader import get_creator_data

            creator_data = get_creator_data(creator_id)
            if not creator_data:
                logger.warning(f"No creator data found for {creator_id}")
                return loaded_personality, loaded_products, style_prompt

            if personality is None and creator_data.profile:
                profile = creator_data.profile
                tone = creator_data.tone_profile
                loaded_personality = {
                    "name": profile.clone_name or profile.name or creator_id,
                    "tone": profile.clone_tone or "friendly",
                    "vocabulary": profile.clone_vocabulary or "",
                    "welcome_message": profile.welcome_message or "",
                    "dialect": tone.dialect if tone else "neutral",
                    "formality": tone.formality if tone else "informal",
                    "energy": tone.energy if tone else "medium",
                    "humor": tone.humor if tone else False,
                    "emojis": tone.emojis if tone else "moderate",
                    "signature_phrases": tone.signature_phrases if tone else [],
                    "topics_to_avoid": tone.topics_to_avoid if tone else [],
                    "knowledge_about": profile.knowledge_about or {},
                }
                logger.info(
                    f"Loaded personality for {creator_id}: "
                    f"name={loaded_personality.get('name')}, tone={loaded_personality.get('tone')}"
                )

            if products is None and creator_data.products:
                loaded_products = [
                    {
                        "name": p.name,
                        "description": p.description or p.short_description or "",
                        "price": p.price,
                        "currency": p.currency,
                        "url": p.payment_link or "",
                        "category": p.category,
                        "type": p.product_type,
                    }
                    for p in creator_data.products
                ]
                logger.info(f"Loaded {len(loaded_products)} products for {creator_id}")

            if products is None and creator_data.lead_magnets:
                for lm in creator_data.lead_magnets:
                    loaded_products.append({
                        "name": lm.name,
                        "description": lm.description or lm.short_description or "",
                        "price": 0,
                        "currency": lm.currency,
                        "url": lm.payment_link or "",
                        "category": "lead_magnet",
                        "type": lm.product_type,
                        "is_free": True,
                    })
                logger.info(f"Added {len(creator_data.lead_magnets)} lead magnets for {creator_id}")

        except Exception as e:
            logger.warning(f"Could not load creator data for {creator_id}: {e}")

        return loaded_personality, loaded_products, style_prompt

    def _enrich_style_with_profile(self) -> None:
        """ECHO Engine: Load data-driven StyleProfile to enrich style_prompt."""
        if os.getenv("ENABLE_STYLE_ANALYZER", "true").lower() != "true":
            return
        try:
            from core.style_analyzer import load_profile_from_db
            from api.database import SessionLocal
            from api.models import Creator

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=self.creator_id).first()
                if not creator:
                    return
                profile = load_profile_from_db(str(creator.id))
                if profile and profile.get("prompt_injection"):
                    data_driven_style = profile["prompt_injection"]
                    self.style_prompt = (
                        f"=== ESTILO DE ESCRITURA (datos reales) ===\n"
                        f"{data_driven_style}\n"
                        f"=== FIN ESTILO DATOS ==="
                    )
                    logger.info(
                        f"[ECHO] StyleProfile REPLACED style_prompt for {self.creator_id} "
                        f"(confidence={profile.get('confidence', 0)}, style:{len(self.style_prompt)} chars)"
                    )
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"[ECHO] StyleProfile load failed (using Doc D only): {e}")

    def _init_services(self) -> None:
        """Initialize all required services."""
        from core.rag.semantic import get_semantic_rag
        from core.reasoning.chain_of_thought import ChainOfThoughtReasoner
        from core.frustration_detector import get_frustration_detector
        from core.guardrails import get_response_guardrail
        from services.edge_case_handler import get_edge_case_handler
        from services.response_variator_v2 import get_response_variator_v2
        from models.conversation_memory import ConversationMemory

        self.intent_classifier = IntentClassifier()
        self.prompt_builder = PromptBuilder(personality=self.personality)
        self.memory_store = MemoryStore()

        self.semantic_rag = get_semantic_rag()
        try:
            loaded = self.semantic_rag.load_from_db(self.creator_id)
            logger.info(f"[RAG] SemanticRAG loaded {loaded} docs for {self.creator_id}")
        except Exception as e:
            logger.warning(f"[RAG] Could not hydrate SemanticRAG: {e}")

        self.llm_service = LLMService(
            provider=self.config.llm_provider,
            model=self.config.llm_model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        self.lead_service = LeadService()
        self.instagram_service = InstagramService(access_token=os.getenv("INSTAGRAM_ACCESS_TOKEN"))

        if ENABLE_FRUSTRATION_DETECTION:
            self.frustration_detector = get_frustration_detector()

        self.edge_case_handler = get_edge_case_handler()
        self.response_variator = get_response_variator_v2()

        if ENABLE_GUARDRAILS:
            try:
                self.guardrails = get_response_guardrail()
            except Exception as e:
                logger.warning(f"Could not initialize guardrails: {e}")

        if ENABLE_CHAIN_OF_THOUGHT:
            try:
                self.chain_of_thought = ChainOfThoughtReasoner(self.llm_service)
            except Exception as e:
                logger.warning(f"Could not initialize chain of thought: {e}")

        self._conversation_memories: Dict[str, ConversationMemory] = {}
        logger.debug("All services initialized (including cognitive systems)")

    # =========================================================================
    # MAIN PIPELINE
    # =========================================================================

    async def process_dm(
        self,
        message: str,
        sender_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DMResponse:
        """Process an incoming DM through the 5-phase pipeline."""
        from core.dm.detection import phase_detection
        from core.dm.context import phase_memory_and_context
        from core.dm.generation import phase_llm_generation
        from core.dm.postprocessing import phase_postprocessing

        metadata = metadata or {}
        cognitive_metadata = {}
        _t0 = time.monotonic()

        try:
            # Phase 1: Detection
            detection = await phase_detection(self, message, sender_id, metadata, cognitive_metadata)
            if detection.pool_response:
                return detection.pool_response
            if detection.edge_case_response:
                return detection.edge_case_response

            _t1 = time.monotonic()
            logger.info(f"[TIMING] Phase 1 (detection): {int((_t1 - _t0) * 1000)}ms")

            # Phase 2-3: Memory & Context Loading
            context = await phase_memory_and_context(
                self, message, sender_id, metadata, cognitive_metadata, detection
            )

            _t2 = time.monotonic()
            logger.info(f"[TIMING] Phase 2-3 (context+RAG+prompt): {int((_t2 - _t1) * 1000)}ms")

            # Phase 4: LLM Generation
            llm_response = await phase_llm_generation(
                self, message, "", context.system_prompt, context, cognitive_metadata
            )

            _t3 = time.monotonic()
            logger.info(f"[TIMING] LLM call: {int((_t3 - _t2) * 1000)}ms")

            # Phase 5: Post-processing
            result = await phase_postprocessing(
                self, message, sender_id, metadata, llm_response, context, detection, cognitive_metadata
            )

            _t5 = time.monotonic()
            logger.info(
                f"[TIMING] TOTAL: {int((_t5 - _t0) * 1000)}ms "
                f"(detect={int((_t1 - _t0) * 1000)} ctx+rag={int((_t2 - _t1) * 1000)} "
                f"llm={int((_t3 - _t2) * 1000)} post={int((_t5 - _t3) * 1000)})"
            )
            return result

        except Exception as e:
            logger.error(f"Error processing DM: {e}", exc_info=True)
            return DMResponse(
                content="Lo siento, hubo un error procesando tu mensaje. Por favor intenta de nuevo.",
                intent="ERROR",
                lead_stage=LeadStage.NUEVO.value,
                confidence=0.0,
                metadata={"error": str(e)},
            )

    # =========================================================================
    # PUBLIC API (delegated to public_api module)
    # =========================================================================

    def add_knowledge(self, content: str, metadata: Optional[Dict] = None) -> str:
        from core.dm.public_api import add_knowledge
        return add_knowledge(self, content, metadata)

    def add_knowledge_batch(self, documents: List[Dict[str, Any]]) -> List[str]:
        from core.dm.public_api import add_knowledge_batch
        return add_knowledge_batch(self, documents)

    def clear_knowledge(self) -> None:
        from core.dm.public_api import clear_knowledge
        clear_knowledge(self)

    def get_stats(self) -> Dict[str, Any]:
        from core.dm.public_api import get_stats
        return get_stats(self)

    def health_check(self) -> Dict[str, bool]:
        from core.dm.public_api import health_check
        return health_check(self)

    async def get_follower_detail(self, follower_id: str) -> Optional[Dict[str, Any]]:
        from core.dm.public_api import get_follower_detail
        return await get_follower_detail(self, follower_id)

    async def save_manual_message(self, follower_id: str, message_text: str, sent: bool = True) -> bool:
        from core.dm.public_api import save_manual_message
        return await save_manual_message(self, follower_id, message_text, sent)

    async def update_follower_status(self, follower_id: str, status: str,
                                      purchase_intent: float, is_customer: bool = False) -> bool:
        from core.dm.public_api import update_follower_status
        return await update_follower_status(self, follower_id, status, purchase_intent, is_customer)

    async def _update_follower_memory(self, follower, user_message: str,
                                       assistant_message: str, intent: str) -> None:
        from core.dm.public_api import update_follower_memory
        await update_follower_memory(self, follower, user_message, assistant_message, intent)


# =============================================================================
# BACKWARD COMPATIBILITY
# =============================================================================

DMResponderAgent = DMResponderAgentV2


# =============================================================================
# FACTORY FUNCTIONS (singleton with caching)
# =============================================================================

_dm_agent_cache: Dict[str, DMResponderAgentV2] = {}
_dm_agent_cache_timestamp: Dict[str, float] = {}
_DM_AGENT_CACHE_TTL = AGENT_THRESHOLDS.agent_cache_ttl


def get_dm_agent(creator_id: str) -> DMResponderAgentV2:
    """Factory to get DM agent for a creator - SINGLETON PATTERN."""
    cache_key = creator_id
    now = time.time()
    cache_age = now - _dm_agent_cache_timestamp.get(cache_key, 0)

    if cache_age < _DM_AGENT_CACHE_TTL and cache_key in _dm_agent_cache:
        logger.debug(f"get_dm_agent: reusing cached agent for {creator_id}")
        return _dm_agent_cache[cache_key]

    agent = DMResponderAgentV2(creator_id=creator_id)
    _dm_agent_cache[cache_key] = agent
    _dm_agent_cache_timestamp[cache_key] = now
    logger.info(f"get_dm_agent: created new agent for {creator_id}")
    return agent


def invalidate_dm_agent_cache(creator_id: str = None) -> None:
    """Invalidate DM agent cache."""
    if creator_id:
        _dm_agent_cache.pop(creator_id, None)
        _dm_agent_cache_timestamp.pop(creator_id, None)
        logger.info(f"Invalidated DM agent cache for {creator_id}")
    else:
        _dm_agent_cache.clear()
        _dm_agent_cache_timestamp.clear()
        logger.info("Invalidated all DM agent caches")


# =============================================================================
# ESCALATION NOTIFICATION (moved from postprocessing)
# =============================================================================


async def _check_and_notify_escalation(agent, intent_value, follower, sender_id, message, metadata) -> None:
    """Check if intent warrants escalation notification and send if needed."""
    escalation_intents = {"escalation", "support", "feedback_negative"}
    intent_lower = intent_value.lower() if intent_value else ""

    should_notify = intent_lower in escalation_intents
    is_hot_lead = (
        follower.purchase_intent_score
        and follower.purchase_intent_score >= 0.8
        and intent_lower == "interest_strong"
    )

    if not should_notify and not is_hot_lead:
        return

    try:
        from core.notifications import EscalationNotification, get_notification_service

        notification_service = get_notification_service()

        if intent_lower == "escalation":
            reason = "Usuario solicitó hablar con una persona real"
        elif intent_lower == "support":
            reason = "Usuario reportó un problema o necesita soporte"
        elif intent_lower == "feedback_negative":
            reason = "Usuario expresó insatisfacción o feedback negativo"
        elif is_hot_lead:
            reason = f"🔥 HOT LEAD - Intención de compra: {follower.purchase_intent_score:.0%}"
        else:
            reason = f"Escalación automática por intent: {intent_value}"

        # Build conversation summary
        summary = "Sin historial previo"
        if follower.last_messages:
            recent = follower.last_messages[-6:]
            summary_parts = []
            for msg in recent:
                if isinstance(msg, dict):
                    role = "👤" if msg.get("role") == "user" else "🤖"
                    content = msg.get("content", "")[:100]
                    summary_parts.append(f"{role} {content}")
            if summary_parts:
                summary = "\n".join(summary_parts)

        notification = EscalationNotification(
            creator_id=agent.creator_id,
            follower_id=sender_id,
            follower_username=follower.username or sender_id,
            follower_name=metadata.get("name", ""),
            reason=reason,
            last_message=message[:500],
            conversation_summary=summary,
            purchase_intent_score=follower.purchase_intent_score or 0.0,
            total_messages=follower.total_messages or 0,
            products_discussed=follower.products_discussed or [],
        )

        _t_notif = time.time()
        results = await notification_service.notify_escalation(notification)
        _elapsed = time.time() - _t_notif
        logger.info(f"[A17] DM→Telegram escalation: {_elapsed:.1f}s for {sender_id}: {results}")
    except Exception as e:
        logger.error(f"Failed to send escalation notification: {e}")
