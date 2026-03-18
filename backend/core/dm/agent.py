"""
DM Responder Agent V2 - Slim Orchestrator.

This is the refactored agent that delegates all business logic
to modular services. Target: <500 lines.

Services used:
- IntentClassifier: Message intent classification
- PromptBuilder: System/user prompt construction
- MemoryStore: Follower memory management
- RAGService: Knowledge retrieval
- LLMService: Response generation
- LeadService: Lead scoring and staging
- InstagramService: Message formatting

Architecture: Orchestrator Pattern
- Agent coordinates services
- Services handle business logic
- Clean separation of concerns
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.agent_config import AGENT_THRESHOLDS


# DETECTORES - Detect frustration, context, sensitive content
from core.frustration_detector import get_frustration_detector

# VALIDADORES - Output quality
from core.guardrails import get_response_guardrail

# RAG AVANZADO - Semantic search + Reranking
from core.rag.semantic import get_semantic_rag

# RAZONAMIENTO - Chain of thought for complex queries
from core.reasoning.chain_of_thought import ChainOfThoughtReasoner

# MEMORIA AVANZADA - Conversation facts tracking
from models.conversation_memory import ConversationMemory

# Import all services
from services import (
    InstagramService,
    IntentClassifier,
    LeadService,
    LeadStage,
    LLMProvider,
    LLMResponse,
    LLMService,
    MemoryStore,
    PromptBuilder,
)

# Import DNA context integration

from services.edge_case_handler import get_edge_case_handler

# Re-export Intent for backward compatibility
from services.intent_service import Intent

# SERVICIOS DE RESPUESTA - Response quality
from services.response_variator_v2 import get_response_variator_v2

# Decomposed modules
from core.dm.text_utils import (
    _strip_accents,
    _truncate_at_boundary,
    apply_voseo,
    NON_CACHEABLE_INTENTS,
    _PRODUCT_STOPWORDS,
)
from core.dm.models import (
    AgentConfig,
    DMResponse,
    DetectionResult,
    ContextBundle,
)

# =============================================================================
# COGNITIVE SYSTEMS INTEGRATION (v2.5)
# =============================================================================


# Feature flags still used in _init_services
ENABLE_FRUSTRATION_DETECTION = os.getenv("ENABLE_FRUSTRATION_DETECTION", "true").lower() == "true"
ENABLE_GUARDRAILS = os.getenv("ENABLE_GUARDRAILS", "true").lower() == "true"
ENABLE_CHAIN_OF_THOUGHT = os.getenv("ENABLE_CHAIN_OF_THOUGHT", "true").lower() == "true"

logger = logging.getLogger(__name__)


class DMResponderAgentV2:
    """
    DM Responder Agent V2 - Slim Orchestrator.

    Coordinates all services to process Instagram DMs.
    All business logic is delegated to modular services.

    Target: <500 lines (orchestration only)
    """

    def __init__(
        self,
        creator_id: str,
        config: Optional[AgentConfig] = None,
        personality: Optional[Dict[str, Any]] = None,
        products: Optional[List[Dict]] = None,
    ):
        """
        Initialize the DM Agent with all services.

        Args:
            creator_id: Creator ID for personalization
            config: Agent configuration
            personality: Bot personality settings (auto-loaded if None)
            products: Products/services to promote (auto-loaded if None)
        """
        self.creator_id = creator_id
        self.config = config or AgentConfig()

        # AUTO-LOAD creator data if not provided
        if personality is None or products is None:
            self.personality, self.products, self.style_prompt = self._load_creator_data(
                creator_id, personality, products
            )
        else:
            self.personality = personality
            self.products = products
            self.style_prompt = ""

        # ECHO Engine: Enrich style_prompt with data-driven StyleProfile (Sprint 1)
        self._enrich_style_with_profile()

        # Load calibration data (few-shot examples, tone targets)
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

        # Initialize all services
        self._init_services()

        logger.info(
            f"DMResponderAgentV2 initialized for creator {creator_id} "
            f"(personality: {self.personality.get('name', 'default')}, "
            f"products: {len(self.products)}, "
            f"style: {len(self.style_prompt)} chars)"
        )

    def _load_creator_data(
        self,
        creator_id: str,
        personality: Optional[Dict[str, Any]],
        products: Optional[List[Dict]],
    ) -> tuple:
        """
        Load creator personality, products, and style from database.

        Returns:
            Tuple of (personality_dict, products_list, style_prompt)
        """
        loaded_personality = personality or {}
        loaded_products = products or []
        style_prompt = ""

        # Load style prompt (writing patterns, DM style, tone profile)
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
                return loaded_personality, loaded_products

            # Load personality from profile and tone_profile
            if personality is None and creator_data.profile:
                profile = creator_data.profile
                tone = creator_data.tone_profile

                loaded_personality = {
                    "name": profile.clone_name or profile.name or creator_id,
                    "tone": profile.clone_tone or "friendly",
                    "vocabulary": profile.clone_vocabulary or "",
                    "welcome_message": profile.welcome_message or "",
                    # From ToneProfile
                    "dialect": tone.dialect if tone else "neutral",
                    "formality": tone.formality if tone else "informal",
                    "energy": tone.energy if tone else "medium",
                    "humor": tone.humor if tone else False,
                    "emojis": tone.emojis if tone else "moderate",
                    "signature_phrases": tone.signature_phrases if tone else [],
                    "topics_to_avoid": tone.topics_to_avoid if tone else [],
                    # Knowledge about creator
                    "knowledge_about": profile.knowledge_about or {},
                }

                logger.info(
                    f"Loaded personality for {creator_id}: "
                    f"name={loaded_personality.get('name')}, "
                    f"tone={loaded_personality.get('tone')}"
                )

            # Load products
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

            # Also add lead magnets as free products
            if products is None and creator_data.lead_magnets:
                for lm in creator_data.lead_magnets:
                    loaded_products.append(
                        {
                            "name": lm.name,
                            "description": lm.description or lm.short_description or "",
                            "price": 0,
                            "currency": lm.currency,
                            "url": lm.payment_link or "",
                            "category": "lead_magnet",
                            "type": lm.product_type,
                            "is_free": True,
                        }
                    )
                logger.info(f"Added {len(creator_data.lead_magnets)} lead magnets for {creator_id}")

        except Exception as e:
            logger.warning(f"Could not load creator data for {creator_id}: {e}")

        return loaded_personality, loaded_products, style_prompt

    def _enrich_style_with_profile(self) -> None:
        """ECHO Engine: Load data-driven StyleProfile to enrich style_prompt.

        Merges quantitative style metrics (from Style Analyzer Sprint 1)
        with existing Doc D personality extraction. Falls back gracefully
        if StyleProfile is not available.
        """
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
                    # APPEND ECHO quantitative data AFTER Doc D personality.
                    # Doc D is the authoritative base (language, tone, bilingual style).
                    # ECHO adds real-data metrics (emoji freq, avg length, etc.).
                    echo_section = (
                        f"\n\n=== ESTILO DE ESCRITURA (datos reales) ===\n"
                        f"{data_driven_style}\n"
                        f"=== FIN ESTILO DATOS ==="
                    )
                    if self.style_prompt:
                        self.style_prompt = self.style_prompt + echo_section
                    else:
                        self.style_prompt = echo_section.lstrip()
                    logger.info(
                        f"[ECHO] StyleProfile APPENDED to style_prompt for {self.creator_id} "
                        f"(confidence={profile.get('confidence', 0)}, "
                        f"total:{len(self.style_prompt)} chars)"
                    )
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"[ECHO] StyleProfile load failed (using Doc D only): {e}")

    def _init_services(self) -> None:
        """Initialize all required services."""
        # Intent classification
        self.intent_classifier = IntentClassifier()

        # Prompt building
        self.prompt_builder = PromptBuilder(personality=self.personality)

        # Memory management (follower-based)
        self.memory_store = MemoryStore()

        # RAG retrieval — use SemanticRAG (OpenAI embeddings + pgvector)
        self.semantic_rag = get_semantic_rag()
        try:
            loaded = self.semantic_rag.load_from_db(self.creator_id)
            logger.info(f"[RAG] SemanticRAG loaded {loaded} docs for {self.creator_id}")
        except Exception as e:
            logger.warning(f"[RAG] Could not hydrate SemanticRAG: {e}")

        # LLM generation
        self.llm_service = LLMService(
            provider=self.config.llm_provider,
            model=self.config.llm_model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

        # Lead scoring
        self.lead_service = LeadService()

        # Instagram API
        self.instagram_service = InstagramService(access_token=os.getenv("INSTAGRAM_ACCESS_TOKEN"))

        # =============================================================================
        # COGNITIVE SYSTEMS (v2.5)
        # =============================================================================

        # Detectores
        if ENABLE_FRUSTRATION_DETECTION:
            self.frustration_detector = get_frustration_detector()

        # Edge case handler
        self.edge_case_handler = get_edge_case_handler()

        # Response variator (pools)
        self.response_variator = get_response_variator_v2()

        # Guardrails
        if ENABLE_GUARDRAILS:
            try:
                self.guardrails = get_response_guardrail()
            except Exception as e:
                logger.warning(f"Could not initialize guardrails: {e}")

        # Chain of thought (disabled by default - expensive)
        if ENABLE_CHAIN_OF_THOUGHT:
            try:
                self.chain_of_thought = ChainOfThoughtReasoner(self.llm_service)
            except Exception as e:
                logger.warning(f"Could not initialize chain of thought: {e}")

        # Conversation memory cache (per follower)
        self._conversation_memories: Dict[str, ConversationMemory] = {}

        logger.debug("All services initialized (including cognitive systems)")

    async def process_dm(
        self,
        message: str,
        sender_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DMResponse:
        """Process an incoming DM through the 5-phase pipeline."""
        metadata = metadata or {}
        cognitive_metadata = {}
        _t0 = time.monotonic()

        try:
            # Phase 1: Detection (sensitive content, frustration, pool response, edge cases)
            detection = await self._phase_detection(message, sender_id, metadata, cognitive_metadata)

            # When Best-of-N is enabled in copilot mode, skip pool/edge-case early return
            # so the full LLM generation pipeline runs and produces 3 ranked candidates.
            from core.dm.phases.generation import ENABLE_BEST_OF_N as _BON_ON
            _skip_early_return = False
            if _BON_ON and detection.pool_response:
                try:
                    from core.copilot_service import get_copilot_service
                    _skip_early_return = get_copilot_service().is_copilot_enabled(self.creator_id)
                except Exception:
                    pass

            if detection.pool_response and not _skip_early_return:
                return detection.pool_response
            if detection.edge_case_response:
                return detection.edge_case_response

            _t1 = time.monotonic()
            logger.info(f"[TIMING] Phase 1 (detection): {int((_t1 - _t0) * 1000)}ms")

            # Phase 2-3: Memory & Context Loading
            context = await self._phase_memory_and_context(
                message, sender_id, metadata, cognitive_metadata, detection
            )

            _t2 = time.monotonic()
            logger.info(f"[TIMING] Phase 2-3 (context+RAG+prompt): {int((_t2 - _t1) * 1000)}ms")

            # Phase 3b: Prompt Construction
            full_prompt = self._phase_prompt_construction(
                message, sender_id, metadata, context, detection, cognitive_metadata
            )

            # Phase 4: LLM Generation
            llm_response = await self._phase_llm_generation(
                message, full_prompt, context.system_prompt, context, cognitive_metadata
            )

            _t3 = time.monotonic()
            logger.info(f"[TIMING] LLM call: {int((_t3 - _t2) * 1000)}ms")

            # Phase 5: Post-processing
            result = await self._phase_postprocessing(
                message, sender_id, metadata, llm_response, context, detection, cognitive_metadata
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
            return self._error_response(str(e))

    # =========================================================================
    # PHASE METHODS (extracted from process_dm for testability)
    # =========================================================================

    async def _phase_detection(
        self, message: str, sender_id: str, metadata: Dict, cognitive_metadata: Dict
    ) -> DetectionResult:
        from core.dm.phases.detection import phase_detection
        return await phase_detection(self, message, sender_id, metadata, cognitive_metadata)


    async def _phase_memory_and_context(
        self, message: str, sender_id: str, metadata: Dict,
        cognitive_metadata: Dict, detection: DetectionResult,
    ) -> ContextBundle:
        from core.dm.phases.context import phase_memory_and_context
        return await phase_memory_and_context(self, message, sender_id, metadata, cognitive_metadata, detection)

    def _phase_prompt_construction(
        self, message: str, sender_id: str, metadata: Dict,
        context: ContextBundle, detection: DetectionResult,
        cognitive_metadata: Dict,
    ) -> str:
        from core.dm.phases.prompt import phase_prompt_construction
        return phase_prompt_construction(self, message, sender_id, metadata, context, detection, cognitive_metadata)

    async def _phase_llm_generation(
        self, message: str, full_prompt: str, system_prompt: str,
        context: ContextBundle, cognitive_metadata: Dict,
    ) -> "LLMResponse":
        from core.dm.phases.generation import phase_llm_generation
        return await phase_llm_generation(self, message, full_prompt, system_prompt, context, cognitive_metadata)

    async def _phase_postprocessing(
        self, message: str, sender_id: str, metadata: Dict,
        llm_response: "LLMResponse", context: ContextBundle,
        detection: DetectionResult, cognitive_metadata: Dict,
    ) -> DMResponse:
        from core.dm.phases.postprocessing import phase_postprocessing
        return await phase_postprocessing(self, message, sender_id, metadata, llm_response, context, detection, cognitive_metadata)

    # =========================================================================
    # THIN WRAPPERS — delegate to extracted modules
    # =========================================================================

    def _format_rag_context(self, rag_results: List[Dict]) -> str:
        from core.dm.helpers import format_rag_context
        return format_rag_context(self, rag_results)

    def _get_lead_stage(self, follower, metadata: Dict) -> str:
        from core.dm.helpers import get_lead_stage
        return get_lead_stage(self, follower, metadata)

    def _get_history_from_follower(self, follower) -> List[Dict[str, str]]:
        from core.dm.helpers import get_history_from_follower
        return get_history_from_follower(self, follower)

    async def _background_post_response(self, follower, message, formatted_content, intent_value, sender_id, metadata, cognitive_metadata):
        from core.dm.post_response import background_post_response
        return await background_post_response(self, follower, message, formatted_content, intent_value, sender_id, metadata, cognitive_metadata)

    def _sync_post_response(self, follower, message, formatted_content, intent_value, sender_id, metadata, cognitive_metadata):
        from core.dm.post_response import sync_post_response
        return sync_post_response(self, follower, message, formatted_content, intent_value, sender_id, metadata, cognitive_metadata)

    async def _update_follower_memory(self, follower, user_message, assistant_message, intent):
        from core.dm.post_response import update_follower_memory
        return await update_follower_memory(self, follower, user_message, assistant_message, intent)

    def _update_lead_score(self, follower, intent, metadata):
        from core.dm.post_response import update_lead_score
        return update_lead_score(self, follower, intent, metadata)

    _EMAIL_SKIP_INTENTS = frozenset({
        "escalation", "support", "sensitive", "crisis",
        "feedback_negative", "spam", "other",
    })

    def _step_email_capture(self, message, formatted_content, intent_value, sender_id, follower, platform, cognitive_metadata):
        from core.dm.post_response import step_email_capture
        return step_email_capture(self, message, formatted_content, intent_value, sender_id, follower, platform, cognitive_metadata)

    async def _check_and_notify_escalation(self, intent_value, follower, sender_id, message, metadata):
        from core.dm.post_response import check_and_notify_escalation
        return await check_and_notify_escalation(self, intent_value, follower, sender_id, message, metadata)

    def _get_conversation_summary(self, follower):
        from core.dm.helpers import get_conversation_summary
        return get_conversation_summary(self, follower)

    def _error_response(self, error):
        from core.dm.helpers import error_response
        return error_response(self, error)

    def _trigger_identity_resolution(self, sender_id, platform):
        from core.dm.post_response import trigger_identity_resolution
        return trigger_identity_resolution(self, sender_id, platform)

    # ═══════════════════════════════════════════════════════════════════════
    # PUBLIC API METHODS
    # ═══════════════════════════════════════════════════════════════════════

    def add_knowledge(self, content, metadata=None):
        from core.dm.knowledge import add_knowledge
        return add_knowledge(self, content, metadata)

    def add_knowledge_batch(self, documents):
        from core.dm.knowledge import add_knowledge_batch
        return add_knowledge_batch(self, documents)

    def clear_knowledge(self):
        from core.dm.knowledge import clear_knowledge
        return clear_knowledge(self)

    def get_stats(self) -> Dict[str, Any]:
        """Get agent statistics."""
        return {
            "creator_id": self.creator_id,
            "config": {
                "llm_provider": self.config.llm_provider.value,
                "llm_model": self.config.llm_model,
                "temperature": self.config.temperature,
            },
            "llm": self.llm_service.get_stats(),
            "rag": {"total_documents": self.semantic_rag.count()},
            "memory": {
                "cache_size": self.memory_store.get_cache_size(),
            },
            "instagram": self.instagram_service.get_stats(),
        }

    def health_check(self) -> Dict[str, bool]:
        """Check health of all services."""
        return {
            "intent_classifier": self.intent_classifier is not None,
            "prompt_builder": self.prompt_builder is not None,
            "memory_store": self.memory_store is not None,
            "rag_service": self.semantic_rag is not None,
            "llm_service": self.llm_service is not None,
            "lead_service": self.lead_service is not None,
            "instagram_service": self.instagram_service is not None,
        }

    async def get_follower_detail(self, follower_id):
        from core.dm.follower_api import get_follower_detail
        return await get_follower_detail(self, follower_id)

    def _detect_platform(self, follower_id):
        from core.dm.helpers import detect_platform
        return detect_platform(self, follower_id)

    async def _enrich_from_database(self, result, follower_id):
        from core.dm.follower_api import enrich_from_database
        return await enrich_from_database(self, result, follower_id)

    async def save_manual_message(self, follower_id, message_text, sent=True):
        from core.dm.follower_api import save_manual_message
        return await save_manual_message(self, follower_id, message_text, sent)

    async def update_follower_status(self, follower_id, status, purchase_intent, is_customer=False):
        from core.dm.follower_api import update_follower_status
        return await update_follower_status(self, follower_id, status, purchase_intent, is_customer)


# =============================================================================
# BACKWARD COMPATIBILITY ALIASES
# =============================================================================

# Alias for backward compatibility with dm_agent.py imports
DMResponderAgent = DMResponderAgentV2


# =============================================================================
# FACTORY FUNCTIONS (singleton pattern with caching)
# =============================================================================

from core.cache import BoundedTTLCache
_dm_agent_cache = BoundedTTLCache(
    max_size=20,  # Max 20 agents in memory (~20-50MB each)
    ttl_seconds=AGENT_THRESHOLDS.agent_cache_ttl,
)
_DM_AGENT_CACHE_TTL = AGENT_THRESHOLDS.agent_cache_ttl


def get_dm_agent(creator_id: str) -> DMResponderAgentV2:
    """
    Factory to get DM agent for a creator - SINGLETON PATTERN.

    Reuses existing agent for same creator to avoid expensive initialization.

    Args:
        creator_id: Creator identifier

    Returns:
        DMResponderAgentV2 instance (cached or new)
    """
    cached = _dm_agent_cache.get(creator_id)
    if cached is not None:
        logger.debug(f"get_dm_agent: reusing cached agent for {creator_id}")
        return cached

    # Create new agent and cache it
    agent = DMResponderAgentV2(creator_id=creator_id)
    _dm_agent_cache.set(creator_id, agent)
    logger.info(f"get_dm_agent: created new agent for {creator_id}")
    return agent


def invalidate_dm_agent_cache(creator_id: str = None) -> None:
    """
    Invalidate DM agent cache.

    Call when creator config changes to force agent recreation.

    Args:
        creator_id: Specific creator to invalidate, or None for all
    """
    if creator_id:
        _dm_agent_cache.pop(creator_id, None)
        logger.info(f"Invalidated DM agent cache for {creator_id}")
    else:
        _dm_agent_cache.clear()
        logger.info("Invalidated all DM agent caches")
