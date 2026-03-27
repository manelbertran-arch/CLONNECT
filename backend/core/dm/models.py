"""
Data models for DM Agent V2.

- AgentConfig: Agent configuration
- DMResponse: Response from the DM Agent
- DetectionResult: Results from Phase 1 (detection)
- ContextBundle: Results from Phases 2-3 (memory & context)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.agent_config import AGENT_THRESHOLDS
from services import LLMProvider


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
    pool_response: Optional["DMResponse"] = None  # Set if fast path hit
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
