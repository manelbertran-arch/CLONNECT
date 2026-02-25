"""
core.dm — Modular DM Agent package.

Re-exports all public symbols for backward compatibility
with `from core.dm import ...` style imports.
"""

from core.dm.agent import (
    DMResponderAgent,
    DMResponderAgentV2,
    get_dm_agent,
    invalidate_dm_agent_cache,
)
from core.dm.helpers import (
    NON_CACHEABLE_INTENTS,
    _determine_response_strategy,
    _message_mentions_product,
    _smart_truncate_context,
    _strip_accents,
    _truncate_at_boundary,
    apply_voseo,
)
from core.dm.models import (
    AgentConfig,
    ContextBundle,
    DMResponse,
    DetectionResult,
    # Feature flags
    ENABLE_ADVANCED_PROMPTS,
    ENABLE_BEST_OF_N,
    ENABLE_CHAIN_OF_THOUGHT,
    ENABLE_CITATIONS,
    ENABLE_CONTEXT_DETECTION,
    ENABLE_CONVERSATION_MEMORY,
    ENABLE_CONVERSATION_STATE,
    ENABLE_DNA_AUTO_CREATE,
    ENABLE_DNA_TRIGGERS,
    ENABLE_EDGE_CASE_DETECTION,
    ENABLE_EMAIL_CAPTURE,
    ENABLE_FACT_TRACKING,
    ENABLE_FINETUNED_MODEL,
    ENABLE_FRUSTRATION_DETECTION,
    ENABLE_GOLD_EXAMPLES,
    ENABLE_GUARDRAILS,
    ENABLE_LEAD_CATEGORIZER,
    ENABLE_LEARNING_RULES,
    ENABLE_MESSAGE_SPLITTING,
    ENABLE_OUTPUT_VALIDATION,
    ENABLE_PREFERENCE_PROFILE,
    ENABLE_QUERY_EXPANSION,
    ENABLE_QUESTION_CONTEXT,
    ENABLE_QUESTION_REMOVAL,
    ENABLE_REFLEXION,
    ENABLE_RELATIONSHIP_DETECTION,
    ENABLE_RESPONSE_FIXES,
    ENABLE_SELF_CONSISTENCY,
    ENABLE_SENSITIVE_DETECTION,
    ENABLE_VOCABULARY_EXTRACTION,
)

# Re-export Intent for backward compatibility
from services.intent_service import Intent

__all__ = [
    "AgentConfig",
    "ContextBundle",
    "DMResponse",
    "DMResponderAgent",
    "DMResponderAgentV2",
    "DetectionResult",
    "Intent",
    "NON_CACHEABLE_INTENTS",
    "apply_voseo",
    "get_dm_agent",
    "invalidate_dm_agent_cache",
    "_determine_response_strategy",
    "_message_mentions_product",
    "_smart_truncate_context",
    "_strip_accents",
    "_truncate_at_boundary",
]
