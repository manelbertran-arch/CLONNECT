"""Message models: Message, ConversationStateDB, ConversationSummary, ConversationEmbedding, CommitmentModel, PendingMessage."""
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

try:
    from api.database import Base
except ImportError:
    from database import Base


class Message(Base):
    __tablename__ = "messages"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(
        UUID(as_uuid=True), ForeignKey("leads.id"), index=True
    )  # FIX P1: Added index for joins
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    intent = Column(String(50))
    # Copilot mode fields
    status = Column(String(20), default="sent")  # pending_approval, sent, edited, discarded
    suggested_response = Column(Text)  # Original bot suggestion (before edit)
    approved_at = Column(DateTime(timezone=True))
    approved_by = Column(String(50))  # "creator" or "auto"
    platform_message_id = Column(String(255), index=True)  # ID del mensaje en Instagram/Telegram (indexed for dedup checks)
    msg_metadata = Column(
        JSON, default=dict
    )  # {type: "story_mention", url: "...", emoji_type: "camera"}
    # Copilot autolearning tracking (Phase 2)
    copilot_action = Column(String(30))  # approved, edited, discarded, manual_override
    edit_diff = Column(JSON)  # {length_delta, categories: [shortened, removed_question, ...]}
    confidence_score = Column(Float)  # Bot confidence for this suggestion (0.0-1.0)
    response_time_ms = Column(Integer)  # ms between suggestion created and creator action
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # Soft-delete: WhatsApp "Delete for everyone"

    # ORM relationships
    lead = relationship("Lead", back_populates="messages", lazy="joined")


class ConversationStateDB(Base):
    """
    Persistent conversation state for sales funnel.
    Migrated from in-memory dict to PostgreSQL for persistence across restarts.

    Stores the state machine position and accumulated user context
    for each follower-creator pair.
    """

    __tablename__ = "conversation_states"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(String(100), nullable=False, index=True)
    follower_id = Column(String(255), nullable=False, index=True)

    # State machine position
    phase = Column(
        String(50), default="inicio"
    )  # inicio, cualificacion, descubrimiento, propuesta, objeciones, cierre, escalar
    message_count = Column(Integer, default=0)

    # User context (accumulated from conversation)
    context = Column(JSON, default=dict)  # UserContext serialized as JSON

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ConversationSummary(Base):
    """Conversation summaries for lead context."""

    __tablename__ = "conversation_summaries"
    __table_args__ = (
        Index("idx_conv_summaries_creator_lead", "creator_id", "lead_id"),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)
    summary_text = Column(Text, nullable=False)
    key_topics = Column(JSONB, server_default="[]")
    commitments_made = Column(JSONB, server_default="[]")
    sentiment = Column(String(20), server_default="neutral")
    message_count = Column(Integer, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ConversationEmbedding(Base):
    """
    Conversation embeddings for semantic search over message history.
    Enables the bot to remember and recall context from ANY point in conversation.

    Use case: User asks "What did you tell me about my business 2 months ago?"
    -> Semantic search finds relevant messages by meaning, not just recency.

    NOTE: The 'embedding' column (vector(1536)) is NOT in this model because
    SQLAlchemy doesn't natively support pgvector. Vector operations are done
    via raw SQL (same pattern as core/embeddings.py).
    """

    __tablename__ = "conversation_embeddings"
    __table_args__ = (
        Index("idx_conv_emb_creator_follower", "creator_id", "follower_id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(String(100), nullable=False, index=True)
    follower_id = Column(String(255), nullable=False, index=True)

    # Message data
    message_role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)

    # Note: embedding column (vector(1536)) exists in DB but not in model
    # Vector operations handled via raw SQL in semantic_memory_pgvector.py

    # Metadata (intent, products mentioned, etc.)
    msg_metadata = Column(JSON, default=dict)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CommitmentModel(Base):
    """Track promises/commitments made by the clone in conversations.

    Detects when the bot says things like 'te envío el link mañana' and
    ensures follow-up. Part of ECHO Engine (H = Harmonize).
    """

    __tablename__ = "commitments"
    __table_args__ = (
        Index("idx_commitments_creator_lead", "creator_id", "lead_id"),
        Index("idx_commitments_status", "creator_id", "status"),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(String(100), nullable=False)  # creator name string
    lead_id = Column(String(100), nullable=False)  # platform_user_id string
    commitment_text = Column(Text, nullable=False)
    commitment_type = Column(String(30), default="promise")  # delivery, info_request, meeting, follow_up, promise
    due_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default="pending")  # pending, fulfilled, expired, cancelled
    source_message_id = Column(UUID(as_uuid=True), nullable=True)
    detected_by = Column(String(20), default="llm")  # llm, regex, manual
    fulfilled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PendingMessage(Base):
    """Messages that failed to send and are queued for retry."""
    __tablename__ = "pending_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), index=True, nullable=False)
    recipient_id = Column(String(255), nullable=False)  # Instagram user ID
    content = Column(Text, nullable=False)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), index=True, nullable=True)
    attempt_count = Column(Integer, default=0)
    max_attempts = Column(Integer, default=5)
    last_error = Column(Text)
    next_retry_at = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), default="pending")  # pending, sent, failed_permanent
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_pending_messages_retry", "status", "next_retry_at"),
    )
