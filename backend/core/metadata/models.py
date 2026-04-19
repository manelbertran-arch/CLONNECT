"""Typed metadata models for Clonnect message pipeline (ARC5 Phase 1).

Mirrors docs/sprint5_planning/ARC5_observability.md §2.2.1 literally.
DB stays JSONB; typing is enforced at the write/read boundary via
`core.metadata.serdes`.
"""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class DetectionMetadata(BaseModel):
    """Metadata emitted by core/dm/phases/detection.py."""

    detection_ts: datetime
    detection_duration_ms: int
    detected_intent: Literal["greeting", "question", "objection", "purchase", "other"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    lang_detected: str
    matched_rules: list[str] = Field(default_factory=list)

    # Security (populated by QW3)
    security_flags: list[str] = Field(default_factory=list)
    security_severity: Optional[Literal["low", "medium", "high", "critical"]] = None


class ScoringMetadata(BaseModel):
    """Metadata emitted by services/lead_scoring.py."""

    scoring_ts: datetime
    scoring_duration_ms: int
    scoring_model: str
    score_before: float
    score_after: float
    score_delta: float

    # Sub-scores
    interest_score: float
    intent_score: float
    objection_score: float

    # Batch metadata
    batch_id: Optional[UUID] = None
    batch_position: Optional[int] = None


class GenerationMetadata(BaseModel):
    """Metadata emitted by services/generation.py."""

    generation_ts: datetime
    generation_duration_ms: int
    generation_model: str
    temperature: float

    # Tokens
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    # Context assembly (populated by ARC1/ARC3)
    compaction_applied: bool = False
    distill_cache_hit: bool = False
    sections_truncated: list[str] = Field(default_factory=list)
    context_budget_used_pct: float

    # Retries
    retry_count: int = 0
    circuit_breaker_tripped: bool = False


class PostGenMetadata(BaseModel):
    """Metadata emitted by services/safety_filter.py + post-processing."""

    post_gen_ts: datetime
    safety_status: Literal["OK", "BLOCK", "REGEN"]
    safety_reason: Optional[str] = None
    pii_redacted_types: list[str] = Field(default_factory=list)

    # Rule violations (ARC4 metrics)
    rule_violations: list[str] = Field(default_factory=list)
    length_regen_triggered: bool = False


class MessageMetadata(BaseModel):
    """Top-level container for all phase metadata."""

    detection: Optional[DetectionMetadata] = None
    scoring: Optional[ScoringMetadata] = None
    generation: Optional[GenerationMetadata] = None
    post_gen: Optional[PostGenMetadata] = None

    # Versioning (for migrations)
    schema_version: int = 1
