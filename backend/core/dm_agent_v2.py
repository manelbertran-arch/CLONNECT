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
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# Import all services
from services import (
    InstagramService,
    IntentClassifier,
    LeadService,
    LeadStage,
    LLMProvider,
    LLMService,
    MemoryStore,
    PromptBuilder,
    RAGService,
)

# Re-export Intent for backward compatibility
from services.intent_service import Intent

# Import DNA context integration
from services.dm_agent_context_integration import get_context_for_dm_agent

logger = logging.getLogger(__name__)


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
    created_at: datetime = field(default_factory=datetime.utcnow)

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
            personality: Bot personality settings
            products: Products/services to promote
        """
        self.creator_id = creator_id
        self.config = config or AgentConfig()
        self.personality = personality or {}
        self.products = products or []

        # Initialize all services
        self._init_services()

        logger.info(f"DMResponderAgentV2 initialized for creator {creator_id}")

    def _init_services(self) -> None:
        """Initialize all required services."""
        # Intent classification
        self.intent_classifier = IntentClassifier()

        # Prompt building
        self.prompt_builder = PromptBuilder(personality=self.personality)

        # Memory management (follower-based)
        self.memory_store = MemoryStore()

        # RAG retrieval
        self.rag_service = RAGService(
            similarity_threshold=self.config.rag_similarity_threshold
        )

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
        self.instagram_service = InstagramService(
            access_token=os.getenv("INSTAGRAM_ACCESS_TOKEN")
        )

        logger.debug("All services initialized")

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

        try:
            # Step 1: Classify intent
            intent = self.intent_classifier.classify(message)
            intent_value = intent.value if hasattr(intent, "value") else str(intent)
            logger.debug(f"Intent classified: {intent_value}")

            # Step 2: Get or create follower memory
            follower = await self.memory_store.get_or_create(
                creator_id=self.creator_id,
                follower_id=sender_id,
                username=metadata.get("username", sender_id),
            )

            # Step 3: Retrieve relevant context (RAG)
            rag_results = self.rag_service.retrieve(
                message, top_k=self.config.rag_top_k
            )
            rag_context = self._format_rag_context(rag_results)

            # Step 3b: Get RelationshipDNA context (personalization per lead)
            dna_context = get_context_for_dm_agent(self.creator_id, sender_id)
            if dna_context:
                logger.debug(f"DNA context loaded for {sender_id}")

            # Step 4: Get lead stage
            current_stage = self._get_lead_stage(follower, metadata)

            # Step 5: Build prompts - combine RAG and DNA context
            # Include system_prompt_override if provided (for V2 prompt)
            prompt_override = metadata.get("system_prompt_override", "")
            combined_context = "\n\n".join(filter(None, [rag_context, dna_context, prompt_override]))
            system_prompt = self.prompt_builder.build_system_prompt(
                products=self.products, custom_instructions=combined_context
            )

            # Get conversation history from follower memory
            history = self._get_history_from_follower(follower)

            user_context = self.prompt_builder.build_user_context(
                username=follower.username or sender_id,
                stage=current_stage,
                history=history,
            )

            # Step 6: Generate response via LLM
            full_prompt = f"{user_context}\n\nMensaje actual: {message}"
            llm_response = await self.llm_service.generate(
                prompt=full_prompt, system_prompt=system_prompt
            )

            # Step 7: Format response for Instagram
            formatted_content = self.instagram_service.format_message(
                llm_response.content
            )

            # Step 8: Update follower memory
            await self._update_follower_memory(
                follower, message, formatted_content, intent_value
            )

            # Step 9: Update lead score
            new_stage = self._update_lead_score(follower, intent_value, metadata)

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
                history.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                })
        return history

    async def _update_follower_memory(
        self,
        follower,
        user_message: str,
        assistant_message: str,
        intent: str,
    ) -> None:
        """Update follower memory with new messages."""
        # Add messages to history
        now = datetime.now().isoformat()

        follower.last_messages.append({
            "role": "user",
            "content": user_message,
            "timestamp": now,
        })
        follower.last_messages.append({
            "role": "assistant",
            "content": assistant_message,
            "timestamp": now,
        })

        # Keep only last 20 messages
        follower.last_messages = follower.last_messages[-20:]

        # Update metadata
        follower.total_messages += 1
        follower.last_contact = now

        # Save to storage
        await self.memory_store.save(follower)

    def _update_lead_score(
        self, follower, intent: str, metadata: Dict
    ) -> LeadStage:
        """Update and return lead stage based on interaction."""
        # Use LeadService for intent-based scoring
        new_score = self.lead_service.calculate_intent_score(
            current_score=follower.purchase_intent_score or 0.0,
            intent=intent.upper() if intent else "OTHER",
            has_direct_purchase_keywords=(
                intent in ["purchase_intent", "PURCHASE_INTENT"]
            ),
        )
        follower.purchase_intent_score = new_score

        # Determine stage
        return self.lead_service.determine_stage(
            score=int(new_score * 100),
            days_since_contact=metadata.get("days_since_contact", 0),
            is_customer=follower.is_customer,
        )

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

    def add_knowledge(
        self, content: str, metadata: Optional[Dict] = None
    ) -> str:
        """
        Add knowledge to RAG index.

        Args:
            content: Document content
            metadata: Optional metadata

        Returns:
            Document ID
        """
        return self.rag_service.add_document(content, metadata)

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
            doc_id = self.rag_service.add_document(
                doc.get("content", ""), doc.get("metadata", {})
            )
            doc_ids.append(doc_id)
        return doc_ids

    def clear_knowledge(self) -> None:
        """Clear all knowledge from RAG index."""
        self.rag_service.clear_index()

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
            "rag": self.rag_service.get_stats(),
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
            "rag_service": self.rag_service is not None,
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
                lead = (
                    session.query(Lead)
                    .filter(Lead.platform_user_id == follower_id)
                    .first()
                )
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
            timestamp = datetime.now().isoformat()
            follower.last_messages.append({
                "role": "assistant",
                "content": message_text,
                "timestamp": timestamp,
                "manual": True,
                "sent": sent,
            })

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
