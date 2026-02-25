"""
Central Feature Flag Registry for Clonnect.

All feature flags declared in one place. Import `flags` singleton to check values.
New flags should be added here, NOT as inline os.getenv() calls.

Usage:
    from core.feature_flags import flags
    if flags.guardrails:
        ...
"""
import os
import logging
from dataclasses import dataclass, field
from typing import Dict, Any

logger = logging.getLogger(__name__)


def _flag(env_key: str, default: bool = True) -> bool:
    return os.getenv(env_key, str(default).lower()).lower() == "true"


@dataclass
class FeatureFlags:
    """All Clonnect feature flags in one place."""

    # === DM Agent Pipeline (default: enabled) ===
    sensitive_detection: bool = field(default_factory=lambda: _flag("ENABLE_SENSITIVE_DETECTION", True))
    frustration_detection: bool = field(default_factory=lambda: _flag("ENABLE_FRUSTRATION_DETECTION", True))
    context_detection: bool = field(default_factory=lambda: _flag("ENABLE_CONTEXT_DETECTION", True))
    conversation_memory: bool = field(default_factory=lambda: _flag("ENABLE_CONVERSATION_MEMORY", True))
    guardrails: bool = field(default_factory=lambda: _flag("ENABLE_GUARDRAILS", True))
    output_validation: bool = field(default_factory=lambda: _flag("ENABLE_OUTPUT_VALIDATION", True))
    response_fixes: bool = field(default_factory=lambda: _flag("ENABLE_RESPONSE_FIXES", True))
    chain_of_thought: bool = field(default_factory=lambda: _flag("ENABLE_CHAIN_OF_THOUGHT", True))
    question_context: bool = field(default_factory=lambda: _flag("ENABLE_QUESTION_CONTEXT", True))
    query_expansion: bool = field(default_factory=lambda: _flag("ENABLE_QUERY_EXPANSION", True))
    reflexion: bool = field(default_factory=lambda: _flag("ENABLE_REFLEXION", True))
    lead_categorizer: bool = field(default_factory=lambda: _flag("ENABLE_LEAD_CATEGORIZER", True))
    conversation_state: bool = field(default_factory=lambda: _flag("ENABLE_CONVERSATION_STATE", True))
    fact_tracking: bool = field(default_factory=lambda: _flag("ENABLE_FACT_TRACKING", True))
    advanced_prompts: bool = field(default_factory=lambda: _flag("ENABLE_ADVANCED_PROMPTS", True))
    dna_triggers: bool = field(default_factory=lambda: _flag("ENABLE_DNA_TRIGGERS", True))
    dna_auto_create: bool = field(default_factory=lambda: _flag("ENABLE_DNA_AUTO_CREATE", True))
    relationship_detection: bool = field(default_factory=lambda: _flag("ENABLE_RELATIONSHIP_DETECTION", True))
    edge_case_detection: bool = field(default_factory=lambda: _flag("ENABLE_EDGE_CASE_DETECTION", True))
    citations: bool = field(default_factory=lambda: _flag("ENABLE_CITATIONS", True))
    message_splitting: bool = field(default_factory=lambda: _flag("ENABLE_MESSAGE_SPLITTING", True))
    question_removal: bool = field(default_factory=lambda: _flag("ENABLE_QUESTION_REMOVAL", True))
    vocabulary_extraction: bool = field(default_factory=lambda: _flag("ENABLE_VOCABULARY_EXTRACTION", True))

    # === Experimental (default: disabled) ===
    self_consistency: bool = field(default_factory=lambda: _flag("ENABLE_SELF_CONSISTENCY", False))
    finetuned_model: bool = field(default_factory=lambda: _flag("ENABLE_FINETUNED_MODEL", False))
    learning_rules: bool = field(default_factory=lambda: _flag("ENABLE_LEARNING_RULES", False))
    email_capture: bool = field(default_factory=lambda: _flag("ENABLE_EMAIL_CAPTURE", False))
    best_of_n: bool = field(default_factory=lambda: _flag("ENABLE_BEST_OF_N", False))
    gold_examples: bool = field(default_factory=lambda: _flag("ENABLE_GOLD_EXAMPLES", False))
    preference_profile: bool = field(default_factory=lambda: _flag("ENABLE_PREFERENCE_PROFILE", False))

    # === RAG ===
    reranking: bool = field(default_factory=lambda: _flag("ENABLE_RERANKING", True))
    bm25_hybrid: bool = field(default_factory=lambda: _flag("ENABLE_BM25_HYBRID", True))

    # === Services ===
    intelligence: bool = field(default_factory=lambda: _flag("ENABLE_INTELLIGENCE", True))
    style_analyzer: bool = field(default_factory=lambda: _flag("ENABLE_STYLE_ANALYZER", True))

    def to_dict(self) -> Dict[str, Any]:
        """All flags as dict for API/logging."""
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def active_count(self) -> int:
        return sum(1 for v in self.to_dict().values() if v)

    def inactive_count(self) -> int:
        return sum(1 for v in self.to_dict().values() if not v)

    def log_summary(self) -> None:
        """Log flag summary at startup."""
        inactive = [k for k, v in self.to_dict().items() if not v]
        logger.info(f"Feature flags: {self.active_count()} active, {self.inactive_count()} inactive")
        if inactive:
            logger.info(f"Inactive flags: {', '.join(inactive)}")


# Global singleton
flags = FeatureFlags()
