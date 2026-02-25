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

# P1: QUALITY - Question context, query expansion, reflexion
from core.bot_question_analyzer import QuestionType, get_bot_question_analyzer, is_short_affirmation

# FULL INTEGRATION - Citations, message splitting, question removal, self-consistency
from core.citation_service import get_citation_prompt_section
from core.conversation_state import get_state_manager

# DETECTORES - Detect frustration, context, sensitive content
from core.frustration_detector import get_frustration_detector

# VALIDADORES - Output quality
from core.guardrails import get_response_guardrail

# P2: INTELLIGENCE - Lead categorization, conversation state
from core.lead_categorizer import get_lead_categorizer

# Import notification service for escalations
from core.notifications import EscalationNotification, get_notification_service
from core.output_validator import validate_links, validate_prices
from core.query_expansion import get_query_expander

# RAG AVANZADO - Semantic search + Reranking
from core.rag.semantic import get_semantic_rag
from core.rag.reranker import ENABLE_RERANKING

# RAZONAMIENTO - Chain of thought for complex queries
from core.reasoning.chain_of_thought import ChainOfThoughtReasoner
from core.reasoning.self_consistency import get_self_consistency_validator
from core.reflexion_engine import get_reflexion_engine
from core.response_fixes import apply_all_response_fixes

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

# P3: PERSONALIZATION - DNA triggers, relationship detection
from services.dna_update_triggers import get_dna_triggers
from services.edge_case_handler import get_edge_case_handler

# Re-export Intent for backward compatibility
from services.intent_service import Intent

# SERVICIOS DE RESPUESTA - Response quality
from services.length_controller import detect_message_type, enforce_length
from services.message_splitter import get_message_splitter
from services.question_remover import process_questions
from services.relationship_type_detector import RelationshipTypeDetector
from services.response_variator_v2 import get_response_variator_v2

# Decomposed modules
from core.dm.text_utils import (
    _strip_accents,
    _message_mentions_product,
    _truncate_at_boundary,
    _smart_truncate_context,
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
from core.dm.strategy import _determine_response_strategy

# =============================================================================
# COGNITIVE SYSTEMS INTEGRATION (v2.5)
# =============================================================================


# Feature flags for cognitive systems
ENABLE_FRUSTRATION_DETECTION = os.getenv("ENABLE_FRUSTRATION_DETECTION", "true").lower() == "true"
ENABLE_CONVERSATION_MEMORY = os.getenv("ENABLE_CONVERSATION_MEMORY", "true").lower() == "true"
ENABLE_GUARDRAILS = os.getenv("ENABLE_GUARDRAILS", "true").lower() == "true"
ENABLE_OUTPUT_VALIDATION = os.getenv("ENABLE_OUTPUT_VALIDATION", "true").lower() == "true"
ENABLE_RESPONSE_FIXES = os.getenv("ENABLE_RESPONSE_FIXES", "true").lower() == "true"
ENABLE_CHAIN_OF_THOUGHT = os.getenv("ENABLE_CHAIN_OF_THOUGHT", "true").lower() == "true"

# P1: Quality
ENABLE_QUESTION_CONTEXT = os.getenv("ENABLE_QUESTION_CONTEXT", "true").lower() == "true"
ENABLE_QUERY_EXPANSION = os.getenv("ENABLE_QUERY_EXPANSION", "true").lower() == "true"
ENABLE_REFLEXION = os.getenv("ENABLE_REFLEXION", "true").lower() == "true"
# P2: Intelligence
ENABLE_LEAD_CATEGORIZER = os.getenv("ENABLE_LEAD_CATEGORIZER", "true").lower() == "true"
ENABLE_CONVERSATION_STATE = os.getenv("ENABLE_CONVERSATION_STATE", "true").lower() == "true"
ENABLE_FACT_TRACKING = os.getenv("ENABLE_FACT_TRACKING", "true").lower() == "true"
# P3: Personalization
ENABLE_ADVANCED_PROMPTS = os.getenv("ENABLE_ADVANCED_PROMPTS", "true").lower() == "true"
ENABLE_DNA_TRIGGERS = os.getenv("ENABLE_DNA_TRIGGERS", "true").lower() == "true"
ENABLE_DNA_AUTO_CREATE = os.getenv("ENABLE_DNA_AUTO_CREATE", "true").lower() == "true"
ENABLE_RELATIONSHIP_DETECTION = (
    os.getenv("ENABLE_RELATIONSHIP_DETECTION", "true").lower() == "true"
)
# P4: Full integration
ENABLE_CITATIONS = os.getenv("ENABLE_CITATIONS", "true").lower() == "true"
ENABLE_MESSAGE_SPLITTING = os.getenv("ENABLE_MESSAGE_SPLITTING", "true").lower() == "true"
ENABLE_QUESTION_REMOVAL = os.getenv("ENABLE_QUESTION_REMOVAL", "true").lower() == "true"
ENABLE_VOCABULARY_EXTRACTION = os.getenv("ENABLE_VOCABULARY_EXTRACTION", "true").lower() == "true"
ENABLE_SELF_CONSISTENCY = os.getenv("ENABLE_SELF_CONSISTENCY", "false").lower() == "true"
ENABLE_FINETUNED_MODEL = os.getenv("ENABLE_FINETUNED_MODEL", "false").lower() == "true"
ENABLE_LEARNING_RULES = os.getenv("ENABLE_LEARNING_RULES", "false").lower() == "true"
ENABLE_EMAIL_CAPTURE = os.getenv("ENABLE_EMAIL_CAPTURE", "false").lower() == "true"
ENABLE_BEST_OF_N = os.getenv("ENABLE_BEST_OF_N", "false").lower() == "true"
ENABLE_GOLD_EXAMPLES = os.getenv("ENABLE_GOLD_EXAMPLES", "false").lower() == "true"
ENABLE_PREFERENCE_PROFILE = os.getenv("ENABLE_PREFERENCE_PROFILE", "false").lower() == "true"

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
                    # Replace style_prompt entirely — prompt_injection from
                    # real data supersedes Doc D style (avoids 23K→1K bloat)
                    self.style_prompt = (
                        f"=== ESTILO DE ESCRITURA (datos reales) ===\n"
                        f"{data_driven_style}\n"
                        f"=== FIN ESTILO DATOS ==="
                    )
                    logger.info(
                        f"[ECHO] StyleProfile REPLACED style_prompt for {self.creator_id} "
                        f"(confidence={profile.get('confidence', 0)}, "
                        f"style:{len(self.style_prompt)} chars)"
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
            if detection.pool_response:
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
        """Phase 2-3: Intent classification, parallel DB/IO, context assembly."""
        ctx = ContextBundle()
        _t1 = time.monotonic()

        # Step 2: Classify intent
        intent = self.intent_classifier.classify(message)
        intent_value = intent.value if hasattr(intent, "value") else str(intent)
        logger.debug(f"Intent classified: {intent_value}")
        _t1a = time.monotonic()

        # Step 2b: Analyze bot's last question for short affirmation context
        if ENABLE_QUESTION_CONTEXT and is_short_affirmation(message):
            try:
                hist = metadata.get("history", [])
                last_bot = next(
                    (
                        m.get("content", "")
                        for m in reversed(hist)
                        if m.get("role") == "assistant"
                    ),
                    None,
                )
                if last_bot:
                    q_type, q_conf = get_bot_question_analyzer().analyze_with_confidence(
                        last_bot
                    )
                    if q_type != QuestionType.UNKNOWN:
                        cognitive_metadata["question_context"] = q_type.value
            except Exception as e:
                logger.debug(f"Question context failed: {e}")

        # =================================================================
        # PHASE 2-3: PARALLEL DB/IO + CONTEXT LOADING
        # =================================================================
        # Run independent DB/IO operations concurrently to reduce latency.
        # Previously sequential (~3.8s) → now parallel (~1.2s).

        from services.dm_agent_context_integration import build_context_prompt as _build_ctx
        from services.relationship_dna_repository import get_relationship_dna as _get_raw_dna

        async def _load_conv_state():
            if not ENABLE_CONVERSATION_STATE:
                return "", {}
            try:
                state_mgr = get_state_manager()
                conv_state = await asyncio.to_thread(
                    state_mgr.get_state, sender_id, self.creator_id
                )
                state_ctx = state_mgr.build_enhanced_prompt(conv_state)
                return state_ctx, {"conversation_phase": conv_state.phase.value}
            except Exception as e:
                logger.debug(f"Conversation state failed: {e}")
                return "", {}

        # Parallel: memory (file I/O) + DNA+PostCtx (2 DB queries) + conv_state (1 DB query) + raw DNA
        follower, dna_context, (state_context, state_meta), raw_dna = await asyncio.gather(
            self.memory_store.get_or_create(
                creator_id=self.creator_id,
                follower_id=sender_id,
                username=metadata.get("username", sender_id),
            ),
            _build_ctx(self.creator_id, sender_id),
            _load_conv_state(),
            asyncio.to_thread(_get_raw_dna, self.creator_id, sender_id),
        )
        cognitive_metadata.update(state_meta)

        # Memory recall (per-lead context from past conversations)
        memory_context = ""
        if os.getenv("ENABLE_MEMORY_ENGINE", "false").lower() == "true":
            try:
                from services.memory_engine import get_memory_engine
                mem_engine = get_memory_engine()
                memory_context = await mem_engine.recall(self.creator_id, sender_id, message)
                if memory_context:
                    cognitive_metadata["memory_recalled"] = True
                    cognitive_metadata["memory_chars"] = len(memory_context)
            except Exception as e:
                logger.debug(f"[MEMORY] recall failed: {e}")

        # ECHO Engine: Load pending commitments for this lead (Sprint 4)
        commitment_text = ""
        if os.getenv("ENABLE_COMMITMENT_TRACKING", "true").lower() == "true":
            try:
                from services.commitment_tracker import get_commitment_tracker
                tracker = get_commitment_tracker()
                commitment_text = await asyncio.to_thread(
                    tracker.get_pending_text, sender_id
                )
                if commitment_text:
                    cognitive_metadata["commitments_pending"] = True
            except Exception as e:
                logger.debug(f"[COMMITMENT] load failed: {e}")

        _bot_instructions = ""
        if dna_context:
            logger.debug(f"DNA context loaded for {sender_id}")
        if raw_dna:
            _bot_instructions = raw_dna.get("bot_instructions", "") or ""
            metadata["dna_data"] = raw_dna  # Store for trigger check later

        # Auto-create seed DNA if none exists and lead has some history
        if ENABLE_DNA_AUTO_CREATE and not dna_context and follower.total_messages >= 2:
            try:
                hist = metadata.get("history", [])
                if len(hist) >= 2:
                    det_result = RelationshipTypeDetector().detect(hist)
                    detected_type = det_result.get("type", "DESCONOCIDO")
                    det_confidence = det_result.get("confidence", 0)

                    async def _create_seed_dna():
                        try:
                            from services.relationship_dna_repository import (
                                create_relationship_dna,
                                get_relationship_dna as _get_dna,
                            )
                            existing = await asyncio.to_thread(
                                _get_dna, self.creator_id, sender_id
                            )
                            if existing:
                                return  # Already exists, race condition
                            await asyncio.to_thread(
                                create_relationship_dna,
                                creator_id=self.creator_id,
                                follower_id=sender_id,
                                relationship_type=detected_type,
                                trust_score=round(det_confidence * 0.3, 2),
                                depth_level=0,
                            )
                            logger.info(
                                f"[DNA-SEED] Created seed DNA for {sender_id}: "
                                f"type={detected_type} confidence={det_confidence}"
                            )
                        except Exception as e:
                            logger.debug(f"Seed DNA creation failed: {e}")

                    asyncio.create_task(_create_seed_dna())
                    cognitive_metadata["relationship_type"] = detected_type
                    cognitive_metadata["dna_seed_created"] = True
            except Exception as e:
                logger.debug(f"DNA auto-create check failed: {e}")

        _t1b = time.monotonic()
        logger.info(f"[TIMING] Phase 2 sub: intent={int((_t1a - _t1) * 1000)}ms parallel_io={int((_t1b - _t1a) * 1000)}ms")

        # Fast in-memory operations (no parallelization needed)
        # RAG retrieval — skip for simple intents that don't need knowledge
        _SKIP_RAG_INTENTS = {"greeting", "farewell", "thanks", "saludo", "despedida"}
        rag_query = message
        if intent_value in _SKIP_RAG_INTENTS:
            rag_results = []
            cognitive_metadata["rag_skipped"] = intent_value
            logger.info(f"[RAG] Skipped for intent={intent_value} (no knowledge needed)")
        else:
            if ENABLE_QUERY_EXPANSION:
                try:
                    expanded = get_query_expander().expand(message, max_expansions=2)
                    if len(expanded) > 1:
                        rag_query = " ".join(expanded)
                        cognitive_metadata["query_expanded"] = True
                except Exception as e:
                    logger.debug(f"Query expansion failed: {e}")
            rag_results = self.semantic_rag.search(
                rag_query, top_k=self.config.rag_top_k, creator_id=self.creator_id
            )
        if rag_results:
            logger.info(f"[RAG] query='{rag_query[:50]}' results={len(rag_results)}")
        else:
            logger.debug(f"[RAG] query='{rag_query[:50]}' results=0")

        # Note: reranking already happens inside semantic_rag.search()
        # No need for a second reranking pass here
        if ENABLE_RERANKING and rag_results:
            cognitive_metadata["rag_reranked"] = True

        rag_context = self._format_rag_context(rag_results)

        # Relationship type detection (in-memory)
        if ENABLE_RELATIONSHIP_DETECTION:
            try:
                hist = metadata.get("history", [])
                if len(hist) >= 2:
                    rel_result = RelationshipTypeDetector().detect(hist)
                    if rel_result.get("confidence", 0) > 0.5:
                        cognitive_metadata["relationship_type"] = rel_result["type"]
            except Exception as e:
                logger.debug(f"Relationship detection failed: {e}")

        # A1 FIX: Detect friend/family relationship to suppress acquisition behavior
        _rel_type = cognitive_metadata.get("relationship_type", "")
        is_friend = _rel_type in ("amigo", "FAMILIA", "AMISTAD_CERCANA", "INTIMA")

        # Lead stage (depends on follower)
        current_stage = self._get_lead_stage(follower, metadata)

        # Knowledge base lookup (in-memory after first load)
        kb_context = ""
        try:
            from services.knowledge_base import get_knowledge_base
            kb = get_knowledge_base(self.creator_id)
            kb_result = kb.lookup(message)
            if kb_result:
                kb_context = f"Info factual relevante: {kb_result}"
                logger.debug(f"KB hit for message: {message[:50]}")
        except Exception as e:
            logger.debug(f"KB lookup failed: {e}")

        # Step 5: Build prompts - combine style, RAG and DNA context
        # Include system_prompt_override if provided (for V2 prompt)
        # PRIORITY: style_prompt first (defines HOW to write)
        prompt_override = metadata.get("system_prompt_override", "")
        # Include advanced prompt sections if enabled
        advanced_section = ""
        if ENABLE_ADVANCED_PROMPTS:
            try:
                from core.prompt_builder import build_rules_section

                creator_name = self.personality.get("name", "el creador")
                advanced_section = build_rules_section(creator_name)
            except Exception as e:
                logger.debug(f"Advanced prompts failed: {e}")
        # Load citation context
        citation_context = ""
        if ENABLE_CITATIONS:
            try:
                citation_context = get_citation_prompt_section(self.creator_id, message)
            except Exception as e:
                logger.debug(f"Citation loading failed: {e}")

        # A1 FIX: Suppress acquisition/sales for friends/family
        friend_context = ""
        if is_friend:
            if _rel_type == "FAMILIA":
                friend_context = (
                    "IMPORTANTE: Esta persona es FAMILIAR del creador (padre, madre, hijo, etc.). "
                    "NO intentes vender, ofrecer productos, ni hacer preguntas de cualificación. "
                    "Habla con cariño y naturalidad. Si pide ayuda, ayúdale directamente. "
                    "NO uses frases como 'contame qué te trae por acá' ni similares."
                )
                logger.info("[A1] Family member detected — suppressing acquisition behavior")
            else:
                friend_context = (
                    "IMPORTANTE: Esta persona es un AMIGO/A del creador, NO un lead. "
                    "NO intentes vender, ofrecer productos, ni hacer preguntas de cualificación. "
                    "Habla de forma natural, personal y relajada como con un amigo cercano. "
                    "NO uses frases como 'contame qué te trae por acá' ni similares."
                )
                logger.info("[A1] Friend detected — suppressing acquisition behavior")

        # Load few-shot examples from calibration (cap at 2 to reduce prompt size)
        few_shot_section = ""
        if self.calibration:
            try:
                from services.calibration_loader import get_few_shot_section

                few_shot_section = get_few_shot_section(self.calibration, max_examples=2)
            except Exception as e:
                logger.debug(f"Few-shot loading failed: {e}")

        # Build audio context if message comes from audio intelligence
        audio_context = ""
        audio_intel = metadata.get("audio_intel")
        if audio_intel and isinstance(audio_intel, dict):
            parts = []
            if audio_intel.get("intent"):
                parts.append(f"Intención del audio: {audio_intel['intent']}")
            entities = audio_intel.get("entities", {})
            entity_parts = []
            for key, label in [
                ("people", "Personas"), ("places", "Lugares"),
                ("dates", "Fechas"), ("numbers", "Cifras"),
                ("products", "Productos/servicios"),
            ]:
                vals = entities.get(key, [])
                if vals:
                    entity_parts.append(f"{label}: {', '.join(vals)}")
            if entity_parts:
                parts.append("Datos mencionados: " + ". ".join(entity_parts))
            actions = audio_intel.get("action_items", [])
            if actions:
                parts.append("Acciones pendientes: " + "; ".join(actions))
            if audio_intel.get("emotional_tone"):
                parts.append(f"Tono: {audio_intel['emotional_tone']}")
            if parts:
                audio_context = (
                    "CONTEXTO DE AUDIO (mensaje de voz transcrito):\n"
                    + "\n".join(parts)
                )
                cognitive_metadata["audio_enriched"] = True

        # ECHO Engine: Generate relational context (Sprint 4)
        relational_block = ""
        _echo_rel_ctx = None
        if os.getenv("ENABLE_RELATIONSHIP_ADAPTER", "true").lower() == "true":
            try:
                from services.relationship_adapter import (
                    RelationshipAdapter,
                    style_profile_from_analyzer,
                )
                from core.style_analyzer import load_profile_from_db
                from api.database import SessionLocal
                from api.models import Creator

                # Load StyleProfile for modulation
                _sp = None
                session = SessionLocal()
                try:
                    creator = session.query(Creator).filter_by(name=self.creator_id).first()
                    if creator:
                        _raw_profile = load_profile_from_db(str(creator.id))
                        _sp = style_profile_from_analyzer(_raw_profile)
                finally:
                    session.close()

                adapter = RelationshipAdapter()
                _rel_type = "DESCONOCIDO"
                if isinstance(raw_dna, dict):
                    _rel_type = raw_dna.get("relationship_type", "DESCONOCIDO")

                _echo_rel_ctx = adapter.get_relational_context(
                    lead_status=current_stage,
                    style_profile=_sp,
                    commitment_text=commitment_text,
                    lead_memory_summary=memory_context,
                    relationship_type=_rel_type,
                    lead_name=follower.username if hasattr(follower, 'username') else None,
                    message_count=follower.total_messages if hasattr(follower, 'total_messages') else 0,
                )
                relational_block = _echo_rel_ctx.prompt_instructions
                if relational_block:
                    cognitive_metadata["relational_adapted"] = True
                    cognitive_metadata["lead_warmth"] = _echo_rel_ctx.warmth_score
            except Exception as e:
                logger.debug(f"[ECHO] Relationship Adapter failed: {e}")

        # Priority ordering: style first, then knowledge, then context
        combined_context = "\n\n".join(
            filter(
                None,
                [
                    self.style_prompt,       # HOW to write (highest priority)
                    friend_context,          # Friend/family override (critical)
                    relational_block,        # ECHO: Lead-specific behavior (Sprint 4)
                    rag_context,             # Product/knowledge data
                    memory_context,          # Per-lead facts (personalization)
                    few_shot_section,        # Examples of correct responses
                    dna_context,             # Relationship insights
                    state_context,           # Conversation phase
                    audio_context,           # Audio message context
                    kb_context,              # Factual knowledge base
                    citation_context,        # Source attribution
                    advanced_section,        # Anti-hallucination rules
                    prompt_override,         # Manual override (lowest)
                ],
            )
        )
        # A1: Skip products for friends to avoid LLM injecting sales language
        prompt_products = [] if is_friend else self.products
        system_prompt = self.prompt_builder.build_system_prompt(
            products=prompt_products, custom_instructions=combined_context
        )

        # Get conversation history from follower memory
        history = self._get_history_from_follower(follower)
        _t1c = time.monotonic()
        logger.info(f"[TIMING] Phase 3 sub: fast_ops={int((_t1c - _t1b) * 1000)}ms")

        # Build lead_info from follower memory for richer context
        _lead_info = {}
        if follower.interests:
            _lead_info["interests"] = follower.interests[:5]
        if follower.objections_raised:
            _lead_info["objections"] = follower.objections_raised[:5]
        if follower.products_discussed:
            _lead_info["products_discussed"] = follower.products_discussed[:5]
        if follower.purchase_intent_score > 0:
            _lead_info["purchase_score"] = round(follower.purchase_intent_score, 2)
        if follower.is_customer:
            _lead_info["is_customer"] = True
        if follower.conversation_summary:
            _lead_info["summary"] = follower.conversation_summary[:200]

        user_context = self.prompt_builder.build_user_context(
            username=follower.username or sender_id,
            stage=current_stage,
            history=history,
            lead_info=_lead_info if _lead_info else None,
        )

        _t2 = time.monotonic()
        logger.info(f"[TIMING] Phase 2-3 (context+RAG+prompt): {int((_t2 - _t1) * 1000)}ms")

        # Populate context bundle for downstream phases
        ctx.intent = intent
        ctx.intent_value = intent_value
        ctx.follower = follower
        ctx.dna_context = dna_context
        ctx.state_context = state_context
        ctx.raw_dna = raw_dna
        ctx.memory_context = memory_context
        ctx.commitment_text = commitment_text
        ctx.bot_instructions = _bot_instructions
        ctx.rag_results = rag_results
        ctx.rag_context = rag_context
        ctx.is_friend = is_friend
        ctx.rel_type = _rel_type
        ctx.current_stage = current_stage
        ctx.kb_context = kb_context
        ctx.system_prompt = system_prompt
        ctx.history = history
        ctx.user_context = user_context
        ctx.few_shot_section = few_shot_section
        ctx.audio_context = audio_context
        ctx.relational_block = relational_block
        ctx.echo_rel_ctx = _echo_rel_ctx
        ctx.friend_context = friend_context
        ctx.citation_context = citation_context
        ctx.advanced_section = advanced_section
        ctx.prompt_override = prompt_override
        ctx.cognitive_metadata = cognitive_metadata
        return ctx

    def _phase_prompt_construction(
        self, message: str, sender_id: str, metadata: Dict,
        context: ContextBundle, detection: DetectionResult,
        cognitive_metadata: Dict,
    ) -> str:
        """Phase 3b: Strategy, learning rules, gold examples, prompt assembly.

        NOTE: Prompt construction is currently integrated into _phase_llm_generation
        because the learning rules and gold examples require async DB calls.
        This method returns a placeholder; the actual prompt is built in Phase 4.
        """
        return ""  # Actual prompt built in _phase_llm_generation

    async def _phase_llm_generation(
        self, message: str, full_prompt: str, system_prompt: str,
        context: ContextBundle, cognitive_metadata: Dict,
    ) -> "LLMResponse":
        """Phase 4: Prompt finalization + LLM call with fallback chain."""
        _t2 = time.monotonic()
        # Alias context fields for code compatibility
        intent_value = context.intent_value
        _rel_type = context.rel_type
        follower = context.follower
        is_friend = context.is_friend
        current_stage = context.current_stage
        _bot_instructions = context.bot_instructions
        user_context = context.user_context
        relational_block = context.relational_block
        rag_context = context.rag_context
        memory_context = context.memory_context
        few_shot_section = context.few_shot_section
        dna_context = context.dna_context
        state_context = context.state_context
        kb_context = context.kb_context
        advanced_section = context.advanced_section
        _echo_rel_ctx = context.echo_rel_ctx
        history = context.history
        rag_results = context.rag_results
        frustration_level = cognitive_metadata.get("frustration_level", 0) if isinstance(cognitive_metadata, dict) else 0
        sender_id = follower.follower_id if hasattr(follower, 'follower_id') else ""

        # Step 5b: Determine response strategy
        strategy_hint = _determine_response_strategy(
            message=message,
            intent_value=intent_value,
            relationship_type=_rel_type,
            is_first_message=(follower.total_messages <= 1),
            is_friend=is_friend,
            follower_interests=follower.interests,
            lead_stage=current_stage,
        )
        if strategy_hint:
            cognitive_metadata["response_strategy"] = strategy_hint.split(".")[0]
            logger.info(f"[STRATEGY] {strategy_hint.split('.')[0]}")

        # Step 5c: Load learning rules (autolearning feedback loop)
        learning_rules_section = ""
        if ENABLE_LEARNING_RULES:
            try:
                from services.learning_rules_service import get_applicable_rules

                def _load_rules():
                    from api.database import SessionLocal
                    from api.models import Creator
                    _s = SessionLocal()
                    try:
                        _c = _s.query(Creator.id).filter_by(name=self.creator_id).first()
                        if not _c:
                            return []
                        return get_applicable_rules(
                            _c[0], intent=intent_value,
                            relationship_type=_rel_type,
                            lead_stage=current_stage,
                        )
                    finally:
                        _s.close()

                _learning_rules = await asyncio.to_thread(_load_rules)
                if _learning_rules:
                    lines = []
                    for r in _learning_rules:
                        lines.append(f"- {r['rule_text']}")
                        if r.get("example_bad"):
                            lines.append(f'  NO: "{r["example_bad"]}"')
                        if r.get("example_good"):
                            lines.append(f'  SI: "{r["example_good"]}"')
                    learning_rules_section = (
                        "=== REGLAS APRENDIDAS (del propio creador) ===\n"
                        + "\n".join(lines) + "\n"
                        "=== FIN REGLAS ==="
                    )
                    cognitive_metadata["learning_rules_applied"] = len(_learning_rules)
                    logger.info(f"[LEARNING] Injected {len(_learning_rules)} rules for {sender_id}")
            except Exception as lr_err:
                logger.debug(f"[LEARNING] Rule loading failed: {lr_err}")

        # Step 5d: Load preference profile
        preference_profile_section = ""
        if ENABLE_PREFERENCE_PROFILE:
            try:
                from services.preference_profile_service import (
                    compute_preference_profile,
                    format_preference_profile_for_prompt,
                )

                def _load_profile():
                    from api.database import SessionLocal
                    from api.models import Creator
                    _s = SessionLocal()
                    try:
                        _c = _s.query(Creator.id).filter_by(name=self.creator_id).first()
                        if not _c:
                            return None
                        return compute_preference_profile(_c[0])
                    finally:
                        _s.close()

                _profile = await asyncio.to_thread(_load_profile)
                if _profile:
                    preference_profile_section = format_preference_profile_for_prompt(
                        _profile, self.creator_id
                    )
                    cognitive_metadata["preference_profile"] = True
                    logger.info(f"[PREFERENCE] Profile applied for {sender_id}")
            except Exception as pp_err:
                logger.debug(f"[PREFERENCE] Profile loading failed: {pp_err}")

        # Step 5e: Load gold examples (few-shot)
        gold_examples_section = ""
        if ENABLE_GOLD_EXAMPLES:
            try:
                from services.gold_examples_service import get_matching_examples

                def _load_examples():
                    from api.database import SessionLocal
                    from api.models import Creator
                    _s = SessionLocal()
                    try:
                        _c = _s.query(Creator.id).filter_by(name=self.creator_id).first()
                        if not _c:
                            return []
                        return get_matching_examples(
                            _c[0], intent=intent_value,
                            relationship_type=_rel_type,
                            lead_stage=current_stage,
                        )
                    finally:
                        _s.close()

                _gold_examples = await asyncio.to_thread(_load_examples)
                if _gold_examples:
                    ex_lines = []
                    for ex in _gold_examples:
                        ex_lines.append(
                            f"Lead: \"{ex['user_message']}\"\n"
                            f"{self.creator_id}: \"{ex['creator_response']}\""
                        )
                    gold_examples_section = (
                        f"=== EJEMPLOS DE COMO RESPONDE {self.creator_id.upper()} ===\n"
                        + "\n---\n".join(ex_lines) + "\n"
                        "=== FIN EJEMPLOS ==="
                    )
                    cognitive_metadata["gold_examples_injected"] = len(_gold_examples)
                    logger.info(f"[FEWSHOT] Injected {len(_gold_examples)} examples for {sender_id}")
            except Exception as ge_err:
                logger.debug(f"[FEWSHOT] Example loading failed: {ge_err}")

        # Step 6: Build full prompt with bot_instructions + strategy + frustration
        prompt_parts = [user_context]
        if _bot_instructions:
            prompt_parts.append(
                "=== INSTRUCCIONES ESPECÍFICAS PARA ESTE LEAD ===\n"
                f"{_bot_instructions}\n"
                "=== FIN INSTRUCCIONES ==="
            )
        if learning_rules_section:
            prompt_parts.append(learning_rules_section)
        if preference_profile_section:
            prompt_parts.append(preference_profile_section)
        if gold_examples_section:
            prompt_parts.append(gold_examples_section)
        if strategy_hint:
            prompt_parts.append(strategy_hint)
        if frustration_level > 0.5:
            prompt_parts.append(
                f"⚠️ NOTA: El usuario parece frustrado (nivel: {frustration_level:.0%}). "
                f"Responde con empatía y ofrece ayuda concreta."
            )
        prompt_parts.append(f"Mensaje actual:\n<user_message>\n{message}\n</user_message>")
        full_prompt = "\n\n".join(prompt_parts)

        # Cap total context to ~12K tokens to control LLM cost/latency
        _MAX_CONTEXT_CHARS = AGENT_THRESHOLDS.max_context_chars
        if len(system_prompt) > _MAX_CONTEXT_CHARS:
            original_len = len(system_prompt)
            system_prompt = _smart_truncate_context(system_prompt, _MAX_CONTEXT_CHARS)
            cognitive_metadata["prompt_truncated"] = True
            logger.info(f"[PROMPT] Smart-truncated system prompt from {original_len} to {len(system_prompt)} chars")

        # Log prompt size for latency diagnosis
        _est_tokens = len(system_prompt) // 4
        _section_sizes = {
            k: len(v) for k, v in [
                ("style", self.style_prompt or ""),
                ("relational", relational_block),
                ("rag", rag_context), ("memory", memory_context),
                ("fewshot", few_shot_section), ("dna", dna_context),
                ("state", state_context), ("kb", kb_context),
                ("advanced", advanced_section),
            ] if v
        }
        logger.info(
            f"[TIMING] System prompt: {len(system_prompt)} chars (~{_est_tokens} tokens) "
            f"sections={_section_sizes}"
        )

        # LLM generation: Flash-Lite → GPT-4o-mini (2 providers, nothing else)
        # Path: webhook → process_dm() → generate_dm_response() → gemini/openai
        from core.providers.gemini_provider import generate_dm_response

        llm_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_prompt},
        ]

        # Best-of-N: generate 3 candidates at different temperatures (copilot only)
        best_of_n_result = None
        if ENABLE_BEST_OF_N:
            try:
                from core.copilot_service import get_copilot_service
                _is_copilot = get_copilot_service().is_copilot_enabled(self.creator_id)
                if _is_copilot:
                    from core.best_of_n import generate_best_of_n, serialize_candidates
                    best_of_n_result = await generate_best_of_n(
                        llm_messages, 150, intent_value, "llm_generation", self.creator_id
                    )
            except Exception as bon_err:
                logger.debug("[BestOfN] Failed, using single call: %s", bon_err)

        if best_of_n_result:
            llm_result = {
                "content": best_of_n_result.best.content,
                "model": best_of_n_result.best.model,
                "provider": best_of_n_result.best.provider,
                "latency_ms": best_of_n_result.total_latency_ms,
            }
            cognitive_metadata["best_of_n"] = serialize_candidates(best_of_n_result)
        else:
            # A4/A5: generate_dm_response returns dict with model/provider/latency
            # ECHO: Use dynamic max_tokens/temperature from Relationship Adapter
            _llm_max_tokens = 150
            _llm_temperature = 0.7
            if _echo_rel_ctx:
                _llm_max_tokens = _echo_rel_ctx.llm_max_tokens
                _llm_temperature = _echo_rel_ctx.llm_temperature
            llm_result = await generate_dm_response(
                llm_messages,
                max_tokens=_llm_max_tokens,
                temperature=_llm_temperature,
            )

        _t3 = time.monotonic()
        logger.info(f"[TIMING] LLM call: {int((_t3 - _t2) * 1000)}ms")

        if llm_result:
            llm_response = LLMResponse(
                content=llm_result["content"],
                model=llm_result.get("model", "unknown"),
                tokens_used=0,
                metadata={
                    "provider": llm_result.get("provider", "unknown"),
                    "latency_ms": llm_result.get("latency_ms", 0),
                },
            )
        else:
            # Both Flash-Lite and GPT-4o-mini failed — emergency fallback
            logger.error("Primary cascade failed, using llm_service emergency fallback")
            llm_response = await self.llm_service.generate(
                prompt=full_prompt, system_prompt=system_prompt
            )

        # Phase 4b: Self-consistency validation (expensive, default OFF)
        if ENABLE_SELF_CONSISTENCY:
            try:
                validator = get_self_consistency_validator(self.llm_service)
                consistency = await validator.validate_response(
                    query=message,
                    response=llm_response.content,
                    system_prompt=system_prompt,
                )
                if not consistency.is_consistent and consistency.response:
                    logger.info(
                        f"Self-consistency: replaced (conf={consistency.confidence:.2f})"
                    )
                    llm_response.content = consistency.response
                    cognitive_metadata["self_consistency_replaced"] = True
            except Exception as e:
                logger.debug(f"Self-consistency failed: {e}")

        return llm_response

    async def _phase_postprocessing(
        self, message: str, sender_id: str, metadata: Dict,
        llm_response: "LLMResponse", context: ContextBundle,
        detection: DetectionResult, cognitive_metadata: Dict,
    ) -> DMResponse:
        """Phase 5: Guardrails, validation, formatting, scoring."""
        _t3 = time.monotonic()
        # Alias context fields for code compatibility
        intent_value = context.intent_value
        follower = context.follower
        history = context.history
        rag_results = context.rag_results

        response_content = llm_response.content

        # A2 FIX: Detect and break repetitive loops
        try:
            recent_bot_msgs = [
                m["content"] for m in history
                if m.get("role") == "assistant" and m.get("content")
            ][-3:]
            if recent_bot_msgs and response_content:
                resp_norm = response_content.strip().lower()[:50]
                for prev in recent_bot_msgs:
                    prev_norm = prev.strip().lower()[:50]
                    if resp_norm and prev_norm and resp_norm == prev_norm:
                        logger.warning(
                            "[A2] Repetitive loop detected — response matches recent message"
                        )
                        cognitive_metadata["loop_detected"] = True
                        # Break the loop with a short, generic continuation
                        response_content = "Contame más"
                        llm_response.content = response_content
                        break
        except Exception as e:
            logger.debug(f"Loop detection failed: {e}")

        # Step 7a: Output validation (prices, links)
        if ENABLE_OUTPUT_VALIDATION:
            try:
                # Build known prices from products
                known_prices = {
                    p.get("name", ""): p.get("price", 0)
                    for p in self.products
                    if p.get("price")
                }
                price_issues = validate_prices(response_content, known_prices)
                if price_issues:
                    logger.warning(f"Output validation: {len(price_issues)} price issues")
                    cognitive_metadata["output_validation_issues"] = [
                        i.details for i in price_issues
                    ]
                # Build known links from products
                known_links = [p.get("url", "") for p in self.products if p.get("url")]
                link_issues, corrected = validate_links(response_content, known_links)
                if link_issues:
                    logger.warning(f"Output validation: {len(link_issues)} link issues")
                    response_content = corrected  # Apply corrections
            except Exception as e:
                logger.debug(f"Output validation failed: {e}")

        # Step 7a2: Apply response fixes (typos, formatting, patterns)
        if ENABLE_RESPONSE_FIXES:
            try:
                fixed_response = apply_all_response_fixes(
                    response_content, creator_id=self.creator_id,
                )
                if fixed_response and fixed_response != response_content:
                    logger.debug("Response fixes applied")
                    response_content = fixed_response
            except Exception as e:
                logger.debug(f"Response fixes failed: {e}")

        # Step 7a2b: Tone enforcement (emoji/excl/question rates from calibration)
        if self.calibration:
            try:
                from services.tone_enforcer import enforce_tone

                response_content = enforce_tone(
                    response_content, self.calibration,
                    sender_id=sender_id, message=message,
                )
            except Exception as e:
                logger.debug(f"Tone enforcement failed: {e}")

        # Step 7a2c: Question removal
        if ENABLE_QUESTION_REMOVAL:
            try:
                response_content = process_questions(response_content, message)
            except Exception as e:
                logger.debug(f"Question removal failed: {e}")

        # Step 7a3: Reflexion analysis for response quality
        if ENABLE_REFLEXION:
            try:
                prev_bot = [
                    m.get("content", "")
                    for m in metadata.get("history", [])
                    if m.get("role") == "assistant"
                ]
                r_result = get_reflexion_engine().analyze_response(
                    response=response_content,
                    user_message=message,
                    previous_bot_responses=prev_bot[-5:],
                )
                if r_result.needs_revision:
                    cognitive_metadata["reflexion_issues"] = r_result.issues
                    cognitive_metadata["reflexion_severity"] = r_result.severity
            except Exception as e:
                logger.debug(f"Reflexion failed: {e}")

        # Step 7b: Apply guardrails validation
        if ENABLE_GUARDRAILS and hasattr(self, "guardrails"):
            try:
                # Build allowed URLs from creator's products and booking links
                creator_urls = []
                for p in self.products:
                    url = p.get("url", "")
                    if url:
                        creator_urls.append(url)
                # Extract unique domains from product URLs for whitelist
                creator_domains = set()
                for u in creator_urls:
                    # Extract domain: "https://www.example.com/path" -> "example.com"
                    try:
                        domain = u.split("//")[-1].split("/")[0].replace("www.", "")
                        creator_domains.add(domain)
                    except Exception as e:
                        logger.warning(f"Failed to parse URL domain '{u}': {e}")
                guardrail_result = self.guardrails.validate_response(
                    query=message,
                    response=response_content,
                    context={
                        "products": self.products,
                        "allowed_urls": list(creator_domains),
                    },
                )
                if not guardrail_result.get("valid", True):
                    logger.warning(f"Guardrail triggered: {guardrail_result.get('reason')}")
                    if guardrail_result.get("corrected_response"):
                        response_content = guardrail_result["corrected_response"]
                    cognitive_metadata["guardrail_triggered"] = guardrail_result.get("reason")
            except Exception as e:
                logger.debug(f"Guardrails check failed: {e}")

        # Step 7b: Apply soft length guidance based on message type
        try:
            msg_type = detect_message_type(message)
            response_content = enforce_length(response_content, message)
            cognitive_metadata["message_type"] = msg_type
        except Exception as e:
            logger.debug(f"Length control failed: {e}")

        # Step 7c: Format response for Instagram
        formatted_content = self.instagram_service.format_message(response_content)

        # Step 7d: Inject payment link for purchase_intent if missing
        if intent_value.lower() in ("purchase_intent", "want_to_buy") and self.products:
            msg_lower = message.lower()
            resp_lower = formatted_content.lower()
            for p in self.products:
                pname = p.get("name") or ""
                plink = p.get("payment_link") or p.get("url") or ""
                # Match product in user message OR bot response
                mentioned = (
                    _message_mentions_product(pname, msg_lower)
                    or _message_mentions_product(pname, resp_lower)
                )
                if pname and mentioned and plink and plink not in resp_lower:
                    formatted_content = f"{formatted_content}\n\n{plink}"
                    cognitive_metadata["payment_link_injected"] = plink
                    logger.info(f"[Step 7d] Injected payment link for '{pname}': {plink}")
                    break

        _t4 = time.monotonic()
        logger.info(f"[TIMING] Phase 5 (post-processing): {int((_t4 - _t3) * 1000)}ms")

        # CloneScore real-time logging (non-blocking, CPU-only style_fidelity)
        if os.getenv("ENABLE_CLONE_SCORE", "false").lower() == "true":
            try:
                from services.clone_score_engine import CloneScoreEngine
                cs_engine = CloneScoreEngine()
                score_result = await cs_engine.evaluate_single(
                    self.creator_id, message, formatted_content, {}
                )
                cognitive_metadata["clone_score"] = score_result.get("overall_score", 0)
                _style = score_result.get("dimension_scores", {}).get("style_fidelity", 0)
                logger.info(f"[CLONE_SCORE] style={_style:.1f}")
            except Exception as e:
                logger.debug(f"[CLONE_SCORE] eval failed: {e}")

        # Step 9: Update lead score (synchronous - needed for response)
        new_stage = self._update_lead_score(follower, intent_value, metadata)

        # Step 9c: Email capture (non-blocking) — disabled by default
        if ENABLE_EMAIL_CAPTURE:
            try:
                formatted_content = self._step_email_capture(
                    message=message,
                    formatted_content=formatted_content,
                    intent_value=intent_value,
                    sender_id=sender_id,
                    follower=follower,
                    platform=metadata.get("platform", "instagram"),
                    cognitive_metadata=cognitive_metadata,
                )
            except Exception as e:
                logger.warning(f"Email capture step failed (non-blocking): {e}")

        # Steps 8, 8b, 9b: Run in background thread (non-blocking)
        asyncio.create_task(
            self._background_post_response(
                follower=follower,
                message=message,
                formatted_content=formatted_content,
                intent_value=intent_value,
                sender_id=sender_id,
                metadata=metadata,
                cognitive_metadata=cognitive_metadata,
            )
        )

        # Memory extraction (extract facts from conversation — fire-and-forget)
        if os.getenv("ENABLE_MEMORY_ENGINE", "false").lower() == "true":
            try:
                from services.memory_engine import get_memory_engine
                mem_engine = get_memory_engine()
                conversation_msgs = [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": formatted_content},
                ]
                asyncio.create_task(
                    mem_engine.add(self.creator_id, sender_id, conversation_msgs)
                )
            except Exception as e:
                logger.debug(f"[MEMORY] extraction failed: {e}")

        # ECHO Engine: Detect commitments in bot response (Sprint 4 — fire-and-forget)
        if os.getenv("ENABLE_COMMITMENT_TRACKING", "true").lower() == "true":
            try:
                from services.commitment_tracker import get_commitment_tracker

                async def _detect_commitments():
                    try:
                        tracker = get_commitment_tracker()
                        tracker.detect_and_store(
                            response_text=formatted_content,
                            creator_id=self.creator_id,
                            lead_id=sender_id,
                        )
                    except Exception as e:
                        logger.debug(f"[COMMITMENT] detection failed: {e}")

                asyncio.create_task(_detect_commitments())
            except Exception as e:
                logger.debug(f"[COMMITMENT] setup failed: {e}")

        # Step 10: Escalation notification (async, lightweight)
        asyncio.create_task(
            self._check_and_notify_escalation(
                intent_value=intent_value,
                follower=follower,
                sender_id=sender_id,
                message=message,
                metadata=metadata,
            )
        )

        # Step 10b: Message splitting (store in metadata for caller)
        message_parts = None
        if ENABLE_MESSAGE_SPLITTING:
            try:
                splitter = get_message_splitter()
                if splitter.should_split(formatted_content):
                    parts = splitter.split(formatted_content, message)
                    message_parts = [{"text": p.text, "delay": p.delay_before} for p in parts]
                    logger.debug(f"Message split into {len(parts)} parts")
            except Exception as e:
                logger.debug(f"Message splitting failed: {e}")

        _t5 = time.monotonic()
        logger.info(
            f"[TIMING] Phase 5 (post+mem+nurture): {int((_t5 - _t3) * 1000)}ms "
            f"(guardrails={int((_t4 - _t3) * 1000)} async={int((_t5 - _t4) * 1000)})"
        )
        # A4: Include model/provider/latency in metadata for auditing
        llm_meta = llm_response.metadata or {}

        # Confidence scoring (multi-factor)
        try:
            from core.confidence_scorer import calculate_confidence
            scored_confidence = calculate_confidence(
                intent=intent_value,
                response_text=formatted_content,
                response_type="llm_generation",
                creator_id=self.creator_id,
            )
        except Exception:
            scored_confidence = AGENT_THRESHOLDS.default_scored_confidence

        _dm_metadata = {
            "model": llm_response.model,
            "provider": llm_meta.get("provider", "unknown"),
            "latency_ms": llm_meta.get("latency_ms", 0),
            "rag_results": len(rag_results),
            "history_length": len(history),
            "follower_id": sender_id,
            "message_parts": message_parts,
        }
        if cognitive_metadata.get("best_of_n"):
            _dm_metadata["best_of_n"] = cognitive_metadata["best_of_n"]

        return DMResponse(
            content=formatted_content,
            intent=intent_value,
            lead_stage=new_stage.value if hasattr(new_stage, "value") else str(new_stage),
            confidence=scored_confidence,
            tokens_used=llm_response.tokens_used,
            metadata=_dm_metadata,
        )

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

_dm_agent_cache: Dict[str, DMResponderAgentV2] = {}
_dm_agent_cache_timestamp: Dict[str, float] = {}
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
    import time

    cache_key = creator_id
    now = time.time()
    cache_age = now - _dm_agent_cache_timestamp.get(cache_key, 0)

    if cache_age < _DM_AGENT_CACHE_TTL and cache_key in _dm_agent_cache:
        logger.debug(f"get_dm_agent: reusing cached agent for {creator_id}")
        return _dm_agent_cache[cache_key]

    # Create new agent and cache it
    agent = DMResponderAgentV2(creator_id=creator_id)
    _dm_agent_cache[cache_key] = agent
    _dm_agent_cache_timestamp[cache_key] = now
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
        _dm_agent_cache_timestamp.pop(creator_id, None)
        logger.info(f"Invalidated DM agent cache for {creator_id}")
    else:
        _dm_agent_cache.clear()
        _dm_agent_cache_timestamp.clear()
        logger.info("Invalidated all DM agent caches")
