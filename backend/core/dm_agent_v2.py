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

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for the DM Agent."""

    llm_provider: LLMProvider = LLMProvider.GROQ
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

            # Step 4: Get lead stage
            current_stage = self._get_lead_stage(follower, metadata)

            # Step 5: Build prompts
            system_prompt = self.prompt_builder.build_system_prompt(
                products=self.products, custom_instructions=rag_context
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
