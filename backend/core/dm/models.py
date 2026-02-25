"""
DM Agent data models and feature flags.

Contains all dataclasses used across the DM pipeline
and environment-based feature toggles.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.agent_config import AGENT_THRESHOLDS
from services import LLMProvider

# =============================================================================
# FEATURE FLAGS (environment-based toggles)
# =============================================================================

# Cognitive systems
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
ENABLE_DNA_AUTO_CREATE = os.getenv("ENABLE_DNA_AUTO_CREATE", "true").lower() == "true"
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
ENABLE_LEARNING_RULES = os.getenv("ENABLE_LEARNING_RULES", "false").lower() == "true"
ENABLE_EMAIL_CAPTURE = os.getenv("ENABLE_EMAIL_CAPTURE", "false").lower() == "true"
ENABLE_BEST_OF_N = os.getenv("ENABLE_BEST_OF_N", "false").lower() == "true"
ENABLE_GOLD_EXAMPLES = os.getenv("ENABLE_GOLD_EXAMPLES", "false").lower() == "true"
ENABLE_PREFERENCE_PROFILE = os.getenv("ENABLE_PREFERENCE_PROFILE", "false").lower() == "true"


# =============================================================================
# DATACLASSES
# =============================================================================


@dataclass
class AgentConfig:
    """Configuration for the DM Agent."""

    llm_provider: LLMProvider = LLMProvider.OPENAI
    llm_model: Optional[str] = None
    temperature: float = AGENT_THRESHOLDS.temperature
    max_tokens: int = AGENT_THRESHOLDS.max_tokens
    rag_similarity_threshold: float = AGENT_THRESHOLDS.rag_similarity_threshold
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


@dataclass
class DetectionResult:
    """Results from Phase 1: Detection."""
    frustration_level: float = 0.0
    frustration_signals: Any = None
    context_signals: Any = None
    pool_response: Optional[DMResponse] = None
    edge_case_response: Optional[DMResponse] = None
    cognitive_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextBundle:
    """Results from Phase 2-3: Memory & Context."""
    intent: Any = None
    intent_value: str = ""
    follower: Any = None
    dna_context: str = ""
    state_context: str = ""
    raw_dna: Any = None
    memory_context: str = ""
    commitment_text: str = ""
    bot_instructions: str = ""
    rag_results: list = field(default_factory=list)
    rag_context: str = ""
    is_friend: bool = False
    rel_type: str = ""
    current_stage: str = ""
    kb_context: str = ""
    system_prompt: str = ""
    history: list = field(default_factory=list)
    user_context: str = ""
    few_shot_section: str = ""
    audio_context: str = ""
    relational_block: str = ""
    echo_rel_ctx: Any = None
    friend_context: str = ""
    citation_context: str = ""
    advanced_section: str = ""
    prompt_override: str = ""
    cognitive_metadata: Dict[str, Any] = field(default_factory=dict)
