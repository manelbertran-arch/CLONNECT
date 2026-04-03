"""Learning models: CopilotEvaluation, LearningRule, GoldExample, PatternAnalysisRun, PreferencePair, CloneScoreEvaluation, CloneScoreTestSet, LLMUsageLog, EvaluatorFeedback."""
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

try:
    from api.database import Base
except ImportError:
    from database import Base


class CopilotEvaluation(Base):
    """Autolearning evaluation snapshots (daily/weekly)."""
    __tablename__ = "copilot_evaluations"
    __table_args__ = {"extend_existing": True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False, index=True)
    eval_type = Column(String(20), nullable=False)  # daily, weekly
    eval_date = Column(Date, nullable=False)
    metrics = Column(JSON, nullable=False)
    patterns = Column(JSON)
    recommendations = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LearningRule(Base):
    """Autolearning rules extracted from creator copilot actions.

    Each rule represents a behavioral correction the bot should apply
    when generating responses for similar contexts.
    """
    __tablename__ = "learning_rules"
    __table_args__ = (
        Index("idx_learning_rules_creator_active", "creator_id", "is_active"),
        Index("idx_learning_rules_pattern", "pattern"),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False)
    rule_text = Column(Text, nullable=False)
    pattern = Column(String(50), nullable=False)
    applies_to_relationship_types = Column(JSONB, default=list)
    applies_to_message_types = Column(JSONB, default=list)
    applies_to_lead_stages = Column(JSONB, default=list)
    example_bad = Column(Text, nullable=True)
    example_good = Column(Text, nullable=True)
    confidence = Column(Float, default=0.5)
    times_applied = Column(Integer, default=0)
    times_helped = Column(Integer, default=0)
    source_message_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    superseded_by = Column(UUID(as_uuid=True), ForeignKey("learning_rules.id"), nullable=True)
    version = Column(Integer, default=1)
    source = Column(String(30), default="realtime")


class GoldExample(Base):
    """High-quality creator response examples for few-shot DM prompt injection."""
    __tablename__ = "gold_examples"
    __table_args__ = (
        Index("idx_gold_examples_creator_active", "creator_id", "is_active"),
        Index("idx_gold_examples_creator_intent", "creator_id", "intent", "is_active"),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False)
    user_message = Column(Text, nullable=False)
    creator_response = Column(Text, nullable=False)
    intent = Column(String(50), nullable=True)
    lead_stage = Column(String(30), nullable=True)
    relationship_type = Column(String(30), nullable=True)
    source = Column(String(30), nullable=False)
    source_message_id = Column(UUID(as_uuid=True), nullable=True)
    quality_score = Column(Float, default=0.5)
    times_used = Column(Integer, default=0)
    times_helpful = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    embedding = Column(JSON, nullable=True)  # vector(1536) stored as JSON list; pgvector queries use raw SQL


class PatternAnalysisRun(Base):
    """Audit trail for LLM-as-Judge pattern analysis runs.

    Records when each batch analysis ran, how many preference pairs were
    processed, and how many learning rules were extracted. Allows tracking
    analysis cadence and debugging low rule-generation rates.
    """

    __tablename__ = "pattern_analysis_runs"
    __table_args__ = (
        Index("idx_pattern_runs_creator", "creator_id"),
        Index("idx_pattern_runs_ran_at", "ran_at"),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid.uuid4())
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False)
    ran_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status = Column(String(20), nullable=False)          # done | skipped | error
    pairs_analyzed = Column(Integer, default=0)
    rules_created = Column(Integer, default=0)
    groups_processed = Column(Integer, default=0)
    details = Column(JSONB, default=dict)                # full result dict for debugging


class PreferencePair(Base):
    """Training data pairs (chosen, rejected) from copilot actions and Best-of-N rankings."""
    __tablename__ = "preference_pairs"
    __table_args__ = (
        Index("idx_preference_pairs_creator", "creator_id"),
        Index("idx_preference_pairs_action", "action_type"),
        Index("idx_preference_pairs_created", "created_at"),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False)
    source_message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)
    chosen = Column(Text, nullable=True)
    rejected = Column(Text, nullable=True)
    user_message = Column(Text, nullable=True)
    system_prompt_hash = Column(String(64), nullable=True)
    conversation_context = Column(JSONB, default=list)
    intent = Column(String(50), nullable=True)
    lead_stage = Column(String(50), nullable=True)
    action_type = Column(String(30), nullable=False)
    chosen_temperature = Column(Float, nullable=True)
    rejected_temperature = Column(Float, nullable=True)
    chosen_confidence = Column(Float, nullable=True)
    rejected_confidence = Column(Float, nullable=True)
    confidence_delta = Column(Float, nullable=True)
    edit_diff = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, server_default=text("true"), nullable=False)
    exported_at = Column(DateTime(timezone=True), nullable=True)
    batch_analyzed_at = Column(DateTime(timezone=True), nullable=True)


class CloneScoreEvaluation(Base):
    """CloneScore evaluation snapshots (single/batch/daily)."""

    __tablename__ = "clone_score_evaluations"
    __table_args__ = (
        Index("idx_clone_score_evals_creator", "creator_id"),
        Index("idx_clone_score_evals_creator_type", "creator_id", "eval_type"),
        Index("idx_clone_score_evals_evaluated_at", "evaluated_at"),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False)
    eval_type = Column(String(20), nullable=False)
    evaluated_at = Column(DateTime(timezone=True), server_default=func.now())
    overall_score = Column(Float, nullable=False)
    dimension_scores = Column(JSONB, nullable=False)
    sample_size = Column(Integer, server_default="1")
    eval_metadata = Column(JSONB, server_default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CloneScoreTestSet(Base):
    """Test sets with ground-truth creator response pairs."""

    __tablename__ = "clone_score_test_sets"
    __table_args__ = (
        Index("idx_clone_score_test_sets_creator", "creator_id"),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False)
    name = Column(String(255), nullable=False)
    test_pairs = Column(JSONB, nullable=False, server_default="[]")
    is_active = Column(Boolean, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LLMUsageLog(Base):
    """Per-call LLM token and cost tracking.

    Inserted fire-and-forget after every Gemini / OpenAI call.
    Enables exact cost accounting by provider, model, and call_type.
    """
    __tablename__ = "llm_usage_log"
    __table_args__ = (
        Index("idx_llm_usage_created_at", "created_at"),
        Index("idx_llm_usage_provider_model", "provider", "model"),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider = Column(String(20), nullable=False)       # "gemini" | "openai"
    model = Column(String(100), nullable=False)         # "gemini-2.5-flash-lite" | "gpt-4o-mini"
    call_type = Column(String(50), nullable=False)      # "dm_response" | "background"
    tokens_in = Column(Integer, nullable=False, server_default="0")
    tokens_out = Column(Integer, nullable=False, server_default="0")
    latency_ms = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EvaluatorFeedback(Base):
    """Structured human evaluator feedback on bot responses.

    Captures scores, corrections, and error identifications from human evaluators
    (founder, creator, or manager). Each record with ideal_response auto-generates
    a preference pair and gold example via FeedbackStore.

    Universal: works for any creator_id + evaluator_id combination.
    """
    __tablename__ = "evaluator_feedback"
    __table_args__ = (
        Index("idx_evaluator_feedback_creator", "creator_id"),
        Index("idx_evaluator_feedback_creator_evaluator", "creator_id", "evaluator_id"),
        Index("idx_evaluator_feedback_created", "created_at"),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False)
    evaluator_id = Column(String(50), nullable=False)  # "manel", "iris", etc.

    # Context
    conversation_id = Column(UUID(as_uuid=True), nullable=True)
    source_message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)
    user_message = Column(Text, nullable=False)
    bot_response = Column(Text, nullable=False)
    conversation_history = Column(JSONB, nullable=True)
    intent_detected = Column(String(50), nullable=True)

    # Scores
    coherencia = Column(Integer, nullable=True)       # 1-5
    lo_enviarias = Column(Integer, nullable=True)      # 1-5

    # Corrections (the gold)
    ideal_response = Column(Text, nullable=True)       # What the evaluator would say
    error_tags = Column(JSONB, nullable=True)           # [{type, detail}]
    error_free_text = Column(Text, nullable=True)

    # Metadata for reproducibility
    doc_d_version = Column(String(50), nullable=True)
    model_id = Column(String(100), nullable=True)
    system_prompt_hash = Column(String(64), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
