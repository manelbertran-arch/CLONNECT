"""
DM Agent configuration — all tunable parameters in one place.
Override any value via environment variables prefixed with AGENT_.
"""
import os
from dataclasses import dataclass, field


def _env_float(key: str, default: float) -> float:
    return float(os.getenv(f"AGENT_{key}", str(default)))


def _env_int(key: str, default: int) -> int:
    return int(os.getenv(f"AGENT_{key}", str(default)))


@dataclass(frozen=True)
class AgentThresholds:
    """All tunable thresholds for the DM agent pipeline."""
    temperature: float = field(default_factory=lambda: _env_float("TEMPERATURE", 0.7))
    max_tokens: int = field(default_factory=lambda: _env_int("MAX_TOKENS", 1024))
    max_context_chars: int = field(default_factory=lambda: _env_int("MAX_CONTEXT_CHARS", 48000))
    rag_similarity_threshold: float = field(default_factory=lambda: _env_float("RAG_SIMILARITY_THRESHOLD", 0.3))
    sensitive_confidence: float = field(default_factory=lambda: _env_float("SENSITIVE_CONFIDENCE", 0.7))
    sensitive_escalation: float = field(default_factory=lambda: _env_float("SENSITIVE_ESCALATION", 0.85))
    pool_confidence: float = field(default_factory=lambda: _env_float("POOL_CONFIDENCE", 0.8))
    purchase_intent_high: float = field(default_factory=lambda: _env_float("PURCHASE_INTENT_HIGH", 0.7))
    purchase_intent_medium: float = field(default_factory=lambda: _env_float("PURCHASE_INTENT_MEDIUM", 0.4))
    purchase_intent_escalation: float = field(default_factory=lambda: _env_float("PURCHASE_INTENT_ESCALATION", 0.8))
    purchase_intent_low: float = field(default_factory=lambda: _env_float("PURCHASE_INTENT_LOW", 0.3))
    default_scored_confidence: float = field(default_factory=lambda: _env_float("DEFAULT_SCORED_CONFIDENCE", 0.7))
    agent_cache_ttl: int = field(default_factory=lambda: _env_int("CACHE_TTL", 600))


AGENT_THRESHOLDS = AgentThresholds()
