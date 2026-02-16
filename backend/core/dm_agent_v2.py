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
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# P1: QUALITY - Question context, query expansion, reflexion
from core.bot_question_analyzer import QuestionType, get_bot_question_analyzer, is_short_affirmation

# FULL INTEGRATION - Citations, message splitting, question removal, self-consistency
from core.citation_service import get_citation_prompt_section
from core.context_detector import detect_all as detect_context
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
from core.sensitive_detector import detect_sensitive_content, get_crisis_resources

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

# =============================================================================
# COGNITIVE SYSTEMS INTEGRATION (v2.5)
# =============================================================================


# Feature flags for cognitive systems
ENABLE_SENSITIVE_DETECTION = os.getenv("ENABLE_SENSITIVE_DETECTION", "true").lower() == "true"
ENABLE_FRUSTRATION_DETECTION = os.getenv("ENABLE_FRUSTRATION_DETECTION", "true").lower() == "true"
ENABLE_CONTEXT_DETECTION = os.getenv("ENABLE_CONTEXT_DETECTION", "true").lower() == "true"
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
ENABLE_RELATIONSHIP_DETECTION = (
    os.getenv("ENABLE_RELATIONSHIP_DETECTION", "true").lower() == "true"
)
# P4: Full integration
ENABLE_EDGE_CASE_DETECTION = os.getenv("ENABLE_EDGE_CASE_DETECTION", "true").lower() == "true"
ENABLE_CITATIONS = os.getenv("ENABLE_CITATIONS", "true").lower() == "true"
ENABLE_MESSAGE_SPLITTING = os.getenv("ENABLE_MESSAGE_SPLITTING", "true").lower() == "true"
ENABLE_QUESTION_REMOVAL = os.getenv("ENABLE_QUESTION_REMOVAL", "true").lower() == "true"
ENABLE_VOCABULARY_EXTRACTION = os.getenv("ENABLE_VOCABULARY_EXTRACTION", "true").lower() == "true"
ENABLE_SELF_CONSISTENCY = os.getenv("ENABLE_SELF_CONSISTENCY", "false").lower() == "true"
ENABLE_FINETUNED_MODEL = os.getenv("ENABLE_FINETUNED_MODEL", "false").lower() == "true"
USE_SCOUT_MODEL = os.getenv("USE_SCOUT_MODEL", "true").lower() == "true"

logger = logging.getLogger(__name__)


# =============================================================================
# PRODUCT NAME MATCHING (fuzzy, accent-insensitive)
# =============================================================================

_PRODUCT_STOPWORDS = frozenset({
    "para", "como", "hacia", "entre", "sobre", "desde", "hasta",
    "este", "esta", "estos", "estas", "todo", "toda", "todos",
    "cada", "otro", "otra", "otros", "dias", "donde", "bien",
    "mejor", "mucho", "poco", "mas", "menos", "muy", "que",
    "con", "del", "los", "las", "una", "uno",
})


def _strip_accents(text: str) -> str:
    """Remove accents/diacritics for fuzzy matching."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _message_mentions_product(product_name: str, msg_lower: str) -> bool:
    """Check if a message mentions a product using fuzzy matching.

    Handles long DB names like 'Fitpack Challenge de 11 días: Transforma...'
    by matching on the short-name segment or >=2 significant brand words.
    """
    pname = _strip_accents(product_name.lower().strip())
    msg = _strip_accents(msg_lower)

    if not pname or len(pname) <= 3:
        return False

    # 1. Exact substring (works for short names like "Círculo de Hombres")
    if pname in msg:
        return True

    # 2. First segment before ':' or '—' delimiter
    for sep in [":", "\u2014", " - "]:
        if sep in pname:
            short = pname.split(sep)[0].strip()
            if short and len(short) > 3 and short in msg:
                return True
            break

    # 3. Brand-word matching: >=2 significant words found in message
    words = [w for w in pname.split() if len(w) >= 4 and w not in _PRODUCT_STOPWORDS]
    if len(words) >= 2:
        matches = sum(1 for w in words if w in msg)
        if matches >= 2:
            return True

    return False


# =============================================================================
# NON-CACHEABLE INTENTS (backward compatibility)
# =============================================================================
# Intents that should NOT be cached (require fresh responses)
NON_CACHEABLE_INTENTS = {
    Intent.OBJECTION_PRICE,
    Intent.OBJECTION_TIME,
    Intent.OBJECTION_DOUBT,
    Intent.OBJECTION_LATER,
    Intent.OBJECTION_WORKS,
    Intent.OBJECTION_NOT_FOR_ME,
    Intent.INTEREST_STRONG,  # Active conversions
    Intent.ESCALATION,
    Intent.SUPPORT,  # Support needs personalized responses
    Intent.OTHER,  # Fallback - always regenerate
}


# =============================================================================
# VOSEO CONVERSION (backward compatibility)
# =============================================================================
def apply_voseo(text: str) -> str:
    """
    Convert Spanish tuteo to Argentine voseo.
    Transforms: tu->vos, tienes->tenes, puedes->podes, etc.
    """
    import re

    # Conversion patterns tuteo -> voseo
    conversions = [
        # Pronouns
        (r"\btú\b", "vos"),
        (r"\bTú\b", "Vos"),
        # Common present tense verbs (2nd person singular)
        (r"\btienes\b", "tenés"),
        (r"\bTienes\b", "Tenés"),
        (r"\bpuedes\b", "podés"),
        (r"\bPuedes\b", "Podés"),
        (r"\bquieres\b", "querés"),
        (r"\bQuieres\b", "Querés"),
        (r"\bsabes\b", "sabés"),
        (r"\bSabes\b", "Sabés"),
        (r"\beres\b", "sos"),
        (r"\bEres\b", "Sos"),
        (r"\bvienes\b", "venís"),
        (r"\bpiensas\b", "pensás"),
        (r"\bsientes\b", "sentís"),
        (r"\bprefieres\b", "preferís"),
        (r"\bnecesitas\b", "necesitás"),
        (r"\bestás\b", "estás"),  # Same in voseo
        (r"\bvas\b", "vas"),  # Same in voseo
        # Imperatives
        (r"\bcuéntame\b", "contame"),
        (r"\bCuéntame\b", "Contame"),
        (r"\bescríbeme\b", "escribime"),
        (r"\bEscríbeme\b", "Escribime"),
        (r"\bdime\b", "decime"),
        (r"\bDime\b", "Decime"),
        (r"\bmira\b", "mirá"),
        (r"\bMira\b", "Mirá"),
        (r"\bpiensa\b", "pensá"),
        (r"\bPiensa\b", "Pensá"),
        (r"\bespera\b", "esperá"),
        (r"\bEspera\b", "Esperá"),
        (r"\bescucha\b", "escuchá"),
        (r"\bEscucha\b", "Escuchá"),
        (r"\bfíjate\b", "fijate"),
        (r"\bFíjate\b", "Fijate"),
        (r"\bpregunta\b", "preguntá"),
        # Common phrases (same in voseo)
        (r"\bte respondo\b", "te respondo"),
        (r"\bte cuento\b", "te cuento"),
        (r"\bte paso\b", "te paso"),
        (r"\bte gustaría\b", "te gustaría"),
    ]

    result = text
    for pattern, replacement in conversions:
        result = re.sub(pattern, replacement, result)

    return result


@dataclass
class AgentConfig:
    """Configuration for the DM Agent."""

    llm_provider: LLMProvider = LLMProvider.OPENAI
    llm_model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 1024
    rag_similarity_threshold: float = 0.3
    rag_top_k: int = 3


@dataclass
class DMResponse:
    """Response from the DM Agent."""

    content: str
    intent: str
    lead_stage: str
    confidence: float
    tokens_used: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "intent": self.intent,
            "lead_stage": self.lead_stage,
            "confidence": self.confidence,
            "tokens_used": self.tokens_used,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


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
        """
        Process an incoming DM and generate a response.

        This is the main orchestration method that coordinates
        all services to produce a response.

        Args:
            message: The incoming message text
            sender_id: Instagram user ID of sender
            metadata: Additional message metadata

        Returns:
            DMResponse with generated content and metadata
        """
        metadata = metadata or {}
        cognitive_metadata = {}  # Track cognitive system outputs
        _t0 = time.monotonic()  # Pipeline timing

        try:
            # =================================================================
            # PRE-PIPELINE: SENSITIVE CONTENT DETECTION (Security)
            # =================================================================
            if ENABLE_SENSITIVE_DETECTION:
                try:
                    sensitive_result = detect_sensitive_content(message)
                    if sensitive_result and sensitive_result.confidence >= 0.7:
                        logger.warning(f"Sensitive content detected: {sensitive_result.category}")
                        cognitive_metadata["sensitive_detected"] = True
                        cognitive_metadata["sensitive_category"] = sensitive_result.category
                        # Return crisis resources for high-confidence sensitive content
                        if sensitive_result.confidence >= 0.85:
                            crisis_response = get_crisis_resources(language="es")
                            return DMResponse(
                                content=crisis_response,
                                intent="sensitive_content",
                                lead_stage="unknown",
                                confidence=sensitive_result.confidence,
                                tokens_used=0,
                                metadata={"sensitive_category": sensitive_result.category},
                            )
                except Exception as e:
                    logger.debug(f"Sensitive detection failed: {e}")

            # =================================================================
            # PHASE 1: DETECTION (Frustration, Context, Edge Cases)
            # =================================================================

            # Step 1a: Detect frustration level
            frustration_level = 0.0
            frustration_signals = None
            if ENABLE_FRUSTRATION_DETECTION and hasattr(self, "frustration_detector"):
                try:
                    history = metadata.get("history", [])
                    prev_messages = [
                        m.get("content", "") for m in history if m.get("role") == "user"
                    ]
                    frustration_signals, frustration_level = (
                        self.frustration_detector.analyze_message(message, sender_id, prev_messages)
                    )
                    if frustration_level > 0.3:
                        logger.info(f"Frustration detected: {frustration_level:.2f}")
                        cognitive_metadata["frustration_level"] = frustration_level
                except Exception as e:
                    logger.debug(f"Frustration detection failed: {e}")

            # Step 1b: Detect context signals (sarcasm, B2B, etc.)
            context_signals = None
            if ENABLE_CONTEXT_DETECTION:
                try:
                    history = metadata.get("history", [])
                    context_signals = detect_context(message, history)
                    if context_signals and context_signals.alerts:
                        cognitive_metadata["context_signals"] = context_signals.to_dict()
                except Exception as e:
                    logger.debug(f"Context detection failed: {e}")

            # Step 1c: Try pool response for simple messages (fast path)
            if hasattr(self, "response_variator"):
                # Skip pool if message mentions a product name (needs LLM)
                msg_lower = message.lower()
                mentions_product = False
                if self.products:
                    for p in self.products:
                        pname = p.get("name") or ""
                        if pname and _message_mentions_product(pname, msg_lower):
                            mentions_product = True
                            break

                if not mentions_product and len(message.strip()) <= 80:
                    # Classify context for pool routing (v10.2)
                    # Skip pool for messages > 80 chars — they need LLM context
                    from services.length_controller import classify_lead_context
                    pool_context = classify_lead_context(message)

                    # Pass conv_id for dedup (v10.3) and context for routing (v10.2)
                    conv_id = metadata.get("conversation_id", sender_id)
                    pool_result = self.response_variator.try_pool_response(
                        message,
                        conv_id=conv_id,
                        turn_index=metadata.get("turn_index", 0),
                        context=pool_context,
                    )
                    if pool_result.matched and pool_result.confidence >= 0.8:
                        logger.debug(f"Pool response matched: {pool_result.category}")
                        return DMResponse(
                            content=pool_result.response,
                            intent="pool_response",
                            lead_stage="unknown",
                            confidence=pool_result.confidence,
                            tokens_used=0,
                            metadata={"pool_category": pool_result.category, "used_pool": True},
                        )

            # Step 1d: Edge case detection
            if ENABLE_EDGE_CASE_DETECTION and hasattr(self, "edge_case_handler"):
                try:
                    edge_result = self.edge_case_handler.detect(message)
                    if edge_result.should_escalate:
                        logger.info(f"Edge case escalation: {edge_result.edge_type}")
                        return DMResponse(
                            content=edge_result.suggested_response
                            or "Entiendo, déjame consultarlo y te respondo.",
                            intent="edge_case_escalation",
                            lead_stage="unknown",
                            confidence=edge_result.confidence,
                            metadata={
                                "edge_type": str(edge_result.edge_type),
                                "escalated": True,
                            },
                        )
                except Exception as e:
                    logger.debug(f"Edge case detection failed: {e}")

            # =================================================================
            # PHASE 2: MEMORY & CONTEXT LOADING
            # =================================================================
            _t1 = time.monotonic()
            logger.info(f"[TIMING] Phase 1 (detection): {int((_t1 - _t0) * 1000)}ms")

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

            import asyncio
            from services.dm_agent_context_integration import build_context_prompt as _build_ctx

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

            # Parallel: memory (file I/O) + DNA+PostCtx (2 DB queries) + conv_state (1 DB query)
            follower, dna_context, (state_context, state_meta) = await asyncio.gather(
                self.memory_store.get_or_create(
                    creator_id=self.creator_id,
                    follower_id=sender_id,
                    username=metadata.get("username", sender_id),
                ),
                _build_ctx(self.creator_id, sender_id),
                _load_conv_state(),
            )
            cognitive_metadata.update(state_meta)
            if dna_context:
                logger.debug(f"DNA context loaded for {sender_id}")

            _t1b = time.monotonic()
            logger.info(f"[TIMING] Phase 2 sub: intent={int((_t1a - _t1) * 1000)}ms parallel_io={int((_t1b - _t1a) * 1000)}ms")

            # Fast in-memory operations (no parallelization needed)
            # RAG retrieval
            rag_query = message
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

            combined_context = "\n\n".join(
                filter(
                    None,
                    [
                        self.style_prompt,
                        rag_context,
                        dna_context,
                        state_context,
                        advanced_section,
                        citation_context,
                        kb_context,
                        prompt_override,
                    ],
                )
            )
            system_prompt = self.prompt_builder.build_system_prompt(
                products=self.products, custom_instructions=combined_context
            )

            # Get conversation history from follower memory
            history = self._get_history_from_follower(follower)
            _t1c = time.monotonic()
            logger.info(f"[TIMING] Phase 3 sub: fast_ops={int((_t1c - _t1b) * 1000)}ms")

            user_context = self.prompt_builder.build_user_context(
                username=follower.username or sender_id,
                stage=current_stage,
                history=history,
            )

            # =================================================================
            # PHASE 4: LLM GENERATION
            # =================================================================
            _t2 = time.monotonic()
            logger.info(f"[TIMING] Phase 2-3 (context+RAG+prompt): {int((_t2 - _t1) * 1000)}ms")

            # Step 6: Inject frustration context if detected
            if frustration_level > 0.5:
                full_prompt = (
                    f"{user_context}\n\n"
                    f"⚠️ NOTA: El usuario parece frustrado (nivel: {frustration_level:.0%}). "
                    f"Responde con empatía y ofrece ayuda concreta.\n\n"
                    f"Mensaje actual: {message}"
                )
            else:
                full_prompt = f"{user_context}\n\nMensaje actual: {message}"

            # Log prompt size for latency diagnosis
            logger.info(f"[TIMING] System prompt: {len(system_prompt)} chars (~{len(system_prompt) // 4} tokens)")

            # LLM generation: Flash-Lite → GPT-4o-mini (2 providers, nothing else)
            # Path: webhook → process_dm() → generate_dm_response() → gemini/openai
            from core.providers.gemini_provider import generate_dm_response

            llm_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt},
            ]
            llm_content = await generate_dm_response(llm_messages, max_tokens=150)

            _t3 = time.monotonic()
            logger.info(f"[TIMING] LLM call: {int((_t3 - _t2) * 1000)}ms")

            if llm_content:
                llm_response = LLMResponse(
                    content=llm_content,
                    model="gemini-flash-lite",
                    tokens_used=0,
                    metadata={"provider": "gemini-cascade"},
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

            # =================================================================
            # PHASE 5: POST-PROCESSING (Guardrails, Length Control)
            # =================================================================

            response_content = llm_response.content

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
                    fixed_response = apply_all_response_fixes(response_content)
                    if fixed_response and fixed_response != response_content:
                        logger.debug("Response fixes applied")
                        response_content = fixed_response
                except Exception as e:
                    logger.debug(f"Response fixes failed: {e}")

            # Step 7a2b: Question removal
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

            # Step 9: Update lead score (synchronous - needed for response)
            new_stage = self._update_lead_score(follower, intent_value, metadata)

            # Step 9c: Email capture (non-blocking)
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
                f"[TIMING] TOTAL: {int((_t5 - _t0) * 1000)}ms "
                f"(detect={int((_t1 - _t0) * 1000)} ctx+rag={int((_t2 - _t1) * 1000)} "
                f"llm={int((_t3 - _t2) * 1000)} post={int((_t4 - _t3) * 1000)} "
                f"mem+nurture={int((_t5 - _t4) * 1000)})"
            )
            return DMResponse(
                content=formatted_content,
                intent=intent_value,
                lead_stage=new_stage.value if hasattr(new_stage, "value") else str(new_stage),
                confidence=0.9,  # Default confidence
                tokens_used=llm_response.tokens_used,
                metadata={
                    "model": llm_response.model,
                    "rag_results": len(rag_results),
                    "history_length": len(history),
                    "follower_id": sender_id,
                    "message_parts": message_parts,
                },
            )

        except Exception as e:
            logger.error(f"Error processing DM: {e}", exc_info=True)
            return self._error_response(str(e))

    def _format_rag_context(self, rag_results: List[Dict]) -> str:
        """Format RAG results as context for the prompt."""
        if not rag_results:
            return ""

        context_parts = ["Informacion relevante:"]
        for result in rag_results[:3]:
            content = result.get("content", "")[:200]
            score = result.get("score", 0)
            context_parts.append(f"- [{score:.2f}] {content}")

        return "\n".join(context_parts)

    def _get_lead_stage(self, follower, metadata: Dict) -> str:
        """Get current lead stage for user."""
        if metadata.get("lead_stage"):
            return metadata["lead_stage"]
        # Try advanced categorizer first
        if ENABLE_LEAD_CATEGORIZER:
            try:
                messages = follower.last_messages[-20:] if follower.last_messages else []
                category, score, reason = get_lead_categorizer().categorize(
                    messages=messages,
                    is_customer=follower.is_customer,
                )
                logger.debug(f"Lead categorizer: {category.value} ({reason})")
                return category.value
            except Exception as e:
                logger.debug(f"Lead categorizer failed: {e}")
        # Fallback to simple score-based logic
        if follower.is_customer:
            return LeadStage.CLIENTE.value
        if follower.purchase_intent_score >= 0.7:
            return LeadStage.CALIENTE.value
        if follower.purchase_intent_score >= 0.4:
            return LeadStage.INTERESADO.value
        return LeadStage.NUEVO.value

    def _get_history_from_follower(self, follower) -> List[Dict[str, str]]:
        """Extract conversation history from follower memory."""
        history = []
        for msg in follower.last_messages[-10:]:
            if isinstance(msg, dict):
                history.append(
                    {
                        "role": msg.get("role", "user"),
                        "content": msg.get("content", ""),
                    }
                )
        return history

    async def _background_post_response(
        self,
        follower,
        message: str,
        formatted_content: str,
        intent_value: str,
        sender_id: str,
        metadata: Dict,
        cognitive_metadata: Dict,
    ) -> None:
        """Run memory save, nurturing, DNA triggers, and escalation in background thread."""
        try:
            # Run all sync-heavy operations in thread pool to avoid blocking event loop
            await asyncio.to_thread(
                self._sync_post_response,
                follower, message, formatted_content, intent_value,
                sender_id, metadata, cognitive_metadata,
            )
            logger.debug(f"[BACKGROUND] Post-response tasks completed for {sender_id}")
        except Exception as e:
            logger.error(f"[BACKGROUND] Post-response tasks failed: {e}", exc_info=True)

    def _sync_post_response(
        self,
        follower,
        message: str,
        formatted_content: str,
        intent_value: str,
        sender_id: str,
        metadata: Dict,
        cognitive_metadata: Dict,
    ) -> None:
        """Synchronous post-response tasks (runs in thread pool)."""
        # Step 8: Update follower memory (in-memory + JSON file save)
        now = datetime.now(timezone.utc).isoformat()
        follower.last_messages.append(
            {"role": "user", "content": message, "timestamp": now}
        )
        follower.last_messages.append(
            {"role": "assistant", "content": formatted_content, "timestamp": now}
        )
        follower.last_messages = follower.last_messages[-20:]
        follower.total_messages += 1
        follower.last_contact = now

        # Fact tracking
        if ENABLE_FACT_TRACKING:
            try:
                import re
                facts = []
                if re.search(r"\d+\s*€|\d+\s*euros?|\$\d+", formatted_content, re.IGNORECASE):
                    facts.append("PRICE_GIVEN")
                if "https://" in formatted_content or "http://" in formatted_content:
                    facts.append("LINK_SHARED")
                if self.products:
                    for prod in self.products:
                        prod_name = prod.get("name", "").lower()
                        if prod_name and len(prod_name) > 3 and prod_name in formatted_content.lower():
                            facts.append("PRODUCT_EXPLAINED")
                            break
                if re.search(r"entiendo tu (duda|preocupación)|es normal|no te preocupes|garantía|devolución", formatted_content, re.IGNORECASE):
                    facts.append("OBJECTION_RAISED")
                if re.search(r"me interesa|quiero saber|cuéntame|suena bien|me gusta", message, re.IGNORECASE):
                    facts.append("INTEREST_EXPRESSED")
                if re.search(r"reserva|agenda|cita|llamada|reunión|calendly|cal\.com", formatted_content, re.IGNORECASE):
                    facts.append("APPOINTMENT_MENTIONED")
                if re.search(r"@\w{3,}|[\w.-]+@[\w.-]+\.\w+|\+?\d{9,}|wa\.me|whatsapp", formatted_content, re.IGNORECASE):
                    facts.append("CONTACT_SHARED")
                if "?" in formatted_content:
                    facts.append("QUESTION_ASKED")
                if follower.name and len(follower.name) > 2 and follower.name.lower() in formatted_content.lower():
                    facts.append("NAME_USED")
                if facts:
                    follower.last_messages[-1]["facts"] = facts
            except Exception as e:
                logger.debug(f"Fact tracking failed: {e}")

        # Save to JSON storage (sync file I/O)
        try:
            self.memory_store._save_to_json(follower)
        except Exception as e:
            logger.debug(f"Memory save failed: {e}")

        # Step 8b: Check DNA update triggers
        if ENABLE_DNA_TRIGGERS:
            try:
                triggers = get_dna_triggers()
                existing_dna = metadata.get("dna_data")
                if triggers.should_update(existing_dna, follower.total_messages):
                    msgs = follower.last_messages[-20:]
                    triggers.schedule_async_update(self.creator_id, sender_id, msgs)
                    cognitive_metadata["dna_update_scheduled"] = True
            except Exception as e:
                logger.debug(f"DNA trigger check failed: {e}")

        # Step 9b: Auto-schedule nurturing based on intent (sync DB operations)
        try:
            from core.nurturing import should_schedule_nurturing, get_nurturing_manager

            sequence_type = should_schedule_nurturing(
                intent=intent_value,
                has_purchased=follower.is_customer,
                creator_id=self.creator_id,
            )
            if sequence_type:
                manager = get_nurturing_manager()
                followups = manager.schedule_followup(
                    creator_id=self.creator_id,
                    follower_id=sender_id,
                    sequence_type=sequence_type,
                    product_name="",
                )
                if followups:
                    logger.info(
                        f"[NURTURING] Auto-scheduled {len(followups)} followups "
                        f"(type={sequence_type}) for {sender_id}"
                    )
                    cognitive_metadata["nurturing_scheduled"] = sequence_type
        except Exception as e:
            logger.error(f"[NURTURING] Auto-trigger failed: {e}")

    async def _update_follower_memory(
        self,
        follower,
        user_message: str,
        assistant_message: str,
        intent: str,
    ) -> None:
        """Update follower memory with new messages."""
        # Add messages to history
        now = datetime.now(timezone.utc).isoformat()

        follower.last_messages.append(
            {
                "role": "user",
                "content": user_message,
                "timestamp": now,
            }
        )
        follower.last_messages.append(
            {
                "role": "assistant",
                "content": assistant_message,
                "timestamp": now,
            }
        )

        # Keep only last 20 messages
        follower.last_messages = follower.last_messages[-20:]

        # Track facts in assistant response (9 types)
        if ENABLE_FACT_TRACKING:
            try:
                import re

                facts = []
                # Price given
                if re.search(r"\d+\s*€|\d+\s*euros?|\$\d+", assistant_message, re.IGNORECASE):
                    facts.append("PRICE_GIVEN")
                # Link shared
                if "https://" in assistant_message or "http://" in assistant_message:
                    facts.append("LINK_SHARED")
                # Product explained (match against known products)
                if self.products:
                    for prod in self.products:
                        prod_name = prod.get("name", "").lower()
                        if (
                            prod_name
                            and len(prod_name) > 3
                            and prod_name in assistant_message.lower()
                        ):
                            facts.append("PRODUCT_EXPLAINED")
                            break
                # Objection handling
                if re.search(
                    r"entiendo tu (duda|preocupación)|es normal|no te preocupes|garantía|devolución",
                    assistant_message,
                    re.IGNORECASE,
                ):
                    facts.append("OBJECTION_RAISED")
                # Interest expressed (from user message)
                if re.search(
                    r"me interesa|quiero saber|cuéntame|suena bien|me gusta",
                    user_message,
                    re.IGNORECASE,
                ):
                    facts.append("INTEREST_EXPRESSED")
                # Appointment/scheduling mentioned
                if re.search(
                    r"reserva|agenda|cita|llamada|reunión|calendly|cal\.com",
                    assistant_message,
                    re.IGNORECASE,
                ):
                    facts.append("APPOINTMENT_MENTIONED")
                # Contact info shared
                if re.search(
                    r"@\w{3,}|[\w.-]+@[\w.-]+\.\w+|\+?\d{9,}|wa\.me|whatsapp",
                    assistant_message,
                    re.IGNORECASE,
                ):
                    facts.append("CONTACT_SHARED")
                # Question asked by bot
                if "?" in assistant_message:
                    facts.append("QUESTION_ASKED")
                # Name used (personalization)
                if (
                    follower.name
                    and len(follower.name) > 2
                    and follower.name.lower() in assistant_message.lower()
                ):
                    facts.append("NAME_USED")
                if facts:
                    follower.last_messages[-1]["facts"] = facts
                    logger.debug(f"Facts tracked: {facts}")
            except Exception as e:
                logger.debug(f"Fact tracking failed: {e}")

        # Update metadata
        follower.total_messages += 1
        follower.last_contact = now

        # Save to storage
        await self.memory_store.save(follower)

    def _update_lead_score(self, follower, intent: str, metadata: Dict) -> LeadStage:
        """Update and return lead stage based on interaction."""
        # Use LeadService for intent-based scoring
        new_score = self.lead_service.calculate_intent_score(
            current_score=follower.purchase_intent_score or 0.0,
            intent=intent.upper() if intent else "OTHER",
            has_direct_purchase_keywords=(intent in ["purchase_intent", "PURCHASE_INTENT"]),
        )
        follower.purchase_intent_score = new_score

        # Determine stage
        return self.lead_service.determine_stage(
            score=int(new_score * 100),
            days_since_contact=metadata.get("days_since_contact", 0),
            is_customer=follower.is_customer,
        )

    # Intents where we should NOT ask for email
    _EMAIL_SKIP_INTENTS = frozenset({
        "escalation", "support", "sensitive", "crisis",
        "feedback_negative", "spam", "other",
    })

    def _step_email_capture(
        self,
        message: str,
        formatted_content: str,
        intent_value: str,
        sender_id: str,
        follower,
        platform: str,
        cognitive_metadata: dict,
    ) -> str:
        """
        Step 9c: Email capture logic.

        1. Check if incoming message contains an email → capture it
        2. If no email found, check if we should ask for one → append CTA
        3. Non-blocking: caller wraps in try/except

        Returns formatted_content (possibly with email ask appended).
        """
        from core.unified_profile_service import (
            extract_email,
            process_email_capture,
            should_ask_email,
            record_email_ask,
        )

        # 1. Try to detect email in user message
        detected_email = extract_email(message)
        if detected_email:
            result = process_email_capture(
                email=detected_email,
                platform=platform,
                platform_user_id=sender_id,
                creator_id=self.creator_id,
                name=follower.name,
            )
            if not result.get("error"):
                # Update lead.email in DB
                try:
                    from api.services.db_service import update_lead
                    update_lead(self.creator_id, sender_id, {"email": detected_email})
                except Exception as e:
                    logger.debug(f"Failed to update lead email: {e}")

                cognitive_metadata["email_captured"] = detected_email
                logger.info(f"[EMAIL] Captured {detected_email} for {sender_id}")
                # Replace response with capture confirmation
                capture_response = result.get("response")
                if capture_response:
                    return self.instagram_service.format_message(capture_response)
            return formatted_content

        # 2. Skip asking on sensitive intents
        if intent_value.lower() in self._EMAIL_SKIP_INTENTS:
            return formatted_content

        # 3. Check if we should ask for email
        decision = should_ask_email(
            platform=platform,
            platform_user_id=sender_id,
            creator_id=self.creator_id,
            intent=intent_value,
            message_count=follower.total_messages,
        )

        if decision.should_ask and decision.message:
            # Append email ask CTA to the response
            formatted_content = f"{formatted_content}\n\n{decision.message}"
            record_email_ask(
                platform=platform,
                platform_user_id=sender_id,
                creator_id=self.creator_id,
            )
            cognitive_metadata["email_asked"] = decision.reason
            logger.info(f"[EMAIL] Ask appended for {sender_id} (reason={decision.reason})")

        return formatted_content

    async def _check_and_notify_escalation(
        self,
        intent_value: str,
        follower,
        sender_id: str,
        message: str,
        metadata: Dict,
    ) -> None:
        """
        Check if intent warrants escalation notification and send if needed.

        Triggers notification for:
        - ESCALATION: User explicitly wants to talk to human
        - SUPPORT: User has a problem/complaint
        - FEEDBACK_NEGATIVE: Negative feedback
        - High purchase intent (>0.8) as hot lead alert
        """
        # Intents that trigger escalation notification
        escalation_intents = {"escalation", "support", "feedback_negative"}
        intent_lower = intent_value.lower() if intent_value else ""

        # Check if should notify
        should_notify = intent_lower in escalation_intents
        is_hot_lead = (
            follower.purchase_intent_score
            and follower.purchase_intent_score >= 0.8  # noqa: W503
            and intent_lower == "interest_strong"  # noqa: W503
        )

        if not should_notify and not is_hot_lead:
            return

        try:
            notification_service = get_notification_service()

            # Determine escalation reason
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

            # Build notification
            notification = EscalationNotification(
                creator_id=self.creator_id,
                follower_id=sender_id,
                follower_username=follower.username or sender_id,
                follower_name=metadata.get("name", ""),
                reason=reason,
                last_message=message[:500],  # Truncate for notification
                conversation_summary=self._get_conversation_summary(follower),
                purchase_intent_score=follower.purchase_intent_score or 0.0,
                total_messages=follower.total_messages or 0,
                products_discussed=follower.products_discussed or [],
            )

            # Send notification (async, non-blocking)
            results = await notification_service.notify_escalation(notification)
            logger.info(f"Escalation notification sent for {sender_id}: {results}")

        except Exception as e:
            # Don't fail the main flow if notification fails
            logger.error(f"Failed to send escalation notification: {e}")

    def _get_conversation_summary(self, follower) -> str:
        """Get a brief summary of recent conversation for notification."""
        if not follower.last_messages:
            return "Sin historial previo"

        # Get last 3 exchanges
        recent = follower.last_messages[-6:]
        summary_parts = []
        for msg in recent:
            if isinstance(msg, dict):
                role = "👤" if msg.get("role") == "user" else "🤖"
                content = msg.get("content", "")[:100]
                summary_parts.append(f"{role} {content}")

        return "\n".join(summary_parts) if summary_parts else "Sin historial"

    def _error_response(self, error: str) -> DMResponse:
        """Generate error response."""
        return DMResponse(
            content="Lo siento, hubo un error procesando tu mensaje. Por favor intenta de nuevo.",
            intent="ERROR",
            lead_stage=LeadStage.NUEVO.value,
            confidence=0.0,
            metadata={"error": error},
        )

    # ═══════════════════════════════════════════════════════════════════════
    # PUBLIC API METHODS
    # ═══════════════════════════════════════════════════════════════════════

    def add_knowledge(self, content: str, metadata: Optional[Dict] = None) -> str:
        """
        Add knowledge to RAG index.

        Args:
            content: Document content
            metadata: Optional metadata

        Returns:
            Document ID
        """
        self.semantic_rag.add_document(
            doc_id=f"manual_{len(self.semantic_rag._documents)}",
            text=content,
            metadata=metadata or {},
        )
        return f"manual_{len(self.semantic_rag._documents) - 1}"

    def add_knowledge_batch(self, documents: List[Dict[str, Any]]) -> List[str]:
        """
        Add multiple documents to RAG index.

        Args:
            documents: List of dicts with 'content' and optional 'metadata'

        Returns:
            List of document IDs
        """
        doc_ids = []
        for doc in documents:
            self.semantic_rag.add_document(
                doc_id=f"batch_{len(self.semantic_rag._documents)}",
                text=doc.get("content", ""),
                metadata=doc.get("metadata", {}),
            )
            doc_id = f"batch_{len(self.semantic_rag._documents) - 1}"
            doc_ids.append(doc_id)
        return doc_ids

    def clear_knowledge(self) -> None:
        """Clear all knowledge from RAG index."""
        self.semantic_rag._documents.clear()
        self.semantic_rag._doc_list.clear()

    def get_stats(self) -> Dict[str, Any]:
        """
        Get agent statistics.

        Returns:
            Dictionary with agent and service stats
        """
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
        """
        Check health of all services.

        Returns:
            Dictionary with service health status
        """
        return {
            "intent_classifier": self.intent_classifier is not None,
            "prompt_builder": self.prompt_builder is not None,
            "memory_store": self.memory_store is not None,
            "rag_service": self.semantic_rag is not None,
            "llm_service": self.llm_service is not None,
            "lead_service": self.lead_service is not None,
            "instagram_service": self.instagram_service is not None,
        }

    async def get_follower_detail(self, follower_id: str) -> Optional[Dict[str, Any]]:
        """
        Get unified follower profile from multiple data sources.

        SPRINT1-T1.1: Extended to unify data from:
        - follower_memories (basic data)
        - leads (CRM fields: email, phone, notes, deal_value)
        - conversation_states (funnel phase, context)
        - user_profiles (weighted interests, preferences)

        Args:
            follower_id: Platform-prefixed follower ID (e.g., ig_123)

        Returns:
            Unified profile dict or None if not found
        """
        # Step 1: Get base follower memory
        follower = await self.memory_store.get(self.creator_id, follower_id)

        if not follower:
            return None

        # Build base response from follower_memory
        result = {
            "follower_id": follower.follower_id,
            "username": follower.username,
            "name": follower.name,
            "platform": self._detect_platform(follower_id),
            "profile_pic_url": None,  # Will be enriched from leads
            "first_contact": follower.first_contact,
            "last_contact": follower.last_contact,
            "total_messages": follower.total_messages,
            "interests": follower.interests or [],
            "products_discussed": follower.products_discussed or [],
            "objections_raised": follower.objections_raised or [],
            "purchase_intent_score": follower.purchase_intent_score or 0.0,
            "is_lead": follower.is_lead,
            "is_customer": follower.is_customer,
            "status": getattr(follower, "status", None),
            "preferred_language": follower.preferred_language or "es",
            "last_messages": follower.last_messages[-10:] if follower.last_messages else [],
            # CRM fields (from leads) - defaults
            "email": None,
            "phone": None,
            "notes": None,
            "deal_value": None,
            "tags": [],
            "source": None,
            "assigned_to": None,
            # Funnel fields (from conversation_states) - defaults
            "funnel_phase": None,
            "funnel_context": {},
            # Behavior profile (from user_profiles) - defaults
            "weighted_interests": {},
            "preferences": {},
            "interested_products": [],
        }

        # Step 2: Enrich from PostgreSQL if available
        try:
            result = await self._enrich_from_database(result, follower_id)
        except Exception as e:
            logger.warning(f"Could not enrich follower data from DB: {e}")
            # Continue with base data

        return result

    def _detect_platform(self, follower_id: str) -> str:
        """Detect platform from follower_id prefix."""
        if follower_id.startswith("ig_"):
            return "instagram"
        if follower_id.startswith("tg_"):
            return "telegram"
        if follower_id.startswith("wa_"):
            return "whatsapp"
        return "instagram"  # Default

    async def _enrich_from_database(
        self, result: Dict[str, Any], follower_id: str
    ) -> Dict[str, Any]:
        """
        Enrich follower data from PostgreSQL tables using JOINs.

        Uses LEFT JOINs so missing records don't break the query.
        """
        import os

        if not os.getenv("DATABASE_URL"):
            return result

        try:
            from api.models import ConversationStateDB, Lead, UserProfileDB
            from api.services.db_service import get_session

            session = get_session()
            if not session:
                return result

            try:
                # Query leads table for CRM data
                lead = session.query(Lead).filter(Lead.platform_user_id == follower_id).first()
                if lead:
                    result["email"] = lead.email
                    result["phone"] = lead.phone
                    result["notes"] = lead.notes
                    result["deal_value"] = lead.deal_value
                    result["tags"] = lead.tags or []
                    result["source"] = lead.source
                    result["assigned_to"] = lead.assigned_to
                    result["profile_pic_url"] = lead.profile_pic_url
                    # Override status from leads if available
                    if lead.status:
                        result["status"] = lead.status

                # Query conversation_states for funnel data
                conv_state = (
                    session.query(ConversationStateDB)
                    .filter(
                        ConversationStateDB.creator_id == self.creator_id,
                        ConversationStateDB.follower_id == follower_id,
                    )
                    .first()
                )
                if conv_state:
                    result["funnel_phase"] = conv_state.phase
                    result["funnel_context"] = conv_state.context or {}

                # Query user_profiles for behavior data
                user_profile = (
                    session.query(UserProfileDB)
                    .filter(
                        UserProfileDB.creator_id == self.creator_id,
                        UserProfileDB.user_id == follower_id,
                    )
                    .first()
                )
                if user_profile:
                    result["weighted_interests"] = user_profile.interests or {}
                    result["preferences"] = user_profile.preferences or {}
                    result["interested_products"] = user_profile.interested_products or []

            finally:
                session.close()

        except ImportError:
            logger.debug("Database models not available for enrichment")
        except Exception as e:
            logger.warning(f"Database enrichment failed: {e}")

        return result

    async def save_manual_message(
        self, follower_id: str, message_text: str, sent: bool = True
    ) -> bool:
        """
        Save a manually sent message in the conversation history.

        Args:
            follower_id: The follower's ID
            message_text: The message text that was sent
            sent: Whether the message was successfully sent

        Returns:
            True if saved successfully
        """
        try:
            follower = await self.memory_store.get(self.creator_id, follower_id)

            if not follower:
                logger.warning(f"Follower {follower_id} not found for saving manual message")
                return False

            # Add the message to history
            timestamp = datetime.now(timezone.utc).isoformat()
            follower.last_messages.append(
                {
                    "role": "assistant",
                    "content": message_text,
                    "timestamp": timestamp,
                    "manual": True,
                    "sent": sent,
                }
            )

            # Keep only last 50 messages
            if len(follower.last_messages) > 50:
                follower.last_messages = follower.last_messages[-50:]

            # Update last contact time
            follower.last_contact = timestamp

            # Save to memory store
            await self.memory_store.save(follower)

            logger.info(f"Saved manual message for {follower_id}")
            return True

        except Exception as e:
            logger.error(f"Error saving manual message: {e}")
            return False

    async def update_follower_status(
        self, follower_id: str, status: str, purchase_intent: float, is_customer: bool = False
    ) -> bool:
        """
        Update the lead status for a follower.

        Args:
            follower_id: The follower's ID
            status: The new status (cold, warm, hot, customer)
            purchase_intent: The purchase intent score (0.0 to 1.0)
            is_customer: Whether the follower is now a customer

        Returns:
            True if updated successfully
        """
        try:
            follower = await self.memory_store.get(self.creator_id, follower_id)

            if not follower:
                logger.warning(f"Follower {follower_id} not found for status update")
                return False

            # Update the follower's status
            old_score = follower.purchase_intent_score
            follower.purchase_intent_score = purchase_intent

            # Update is_lead based on score
            if purchase_intent >= 0.3:
                follower.is_lead = True

            # Update is_customer
            if is_customer:
                follower.is_customer = True

            # Save to memory store
            await self.memory_store.save(follower)

            logger.info(
                f"Updated status for {follower_id}: {status} (intent: {old_score:.0%} -> {purchase_intent:.0%})"
            )
            return True

        except Exception as e:
            logger.error(f"Error updating follower status: {e}")
            return False


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
_DM_AGENT_CACHE_TTL = 600  # 10 minutes


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
