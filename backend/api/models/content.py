"""Content models: ContentChunk, InstagramPost, PostContextModel, ContentPerformance, RAGDocument, KnowledgeBase."""
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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

try:
    from api.database import Base
except ImportError:
    from database import Base


class ContentChunk(Base):
    """
    Content chunks for RAG/citation system.
    Migrated from data/content_index/{creator_id}/chunks.json
    """

    __tablename__ = "content_chunks"
    __table_args__ = {"extend_existing": True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(String(100), nullable=False, index=True)
    chunk_id = Column(String(255), nullable=False)  # Original chunk ID
    content = Column(Text, nullable=False)
    source_type = Column(String(50))  # instagram_post, web_page, etc.
    source_id = Column(String(255))  # Post ID, page slug, etc.
    source_url = Column(Text)
    title = Column(String(500))
    chunk_index = Column(Integer, default=0)
    total_chunks = Column(Integer, default=1)
    extra_data = Column(JSON, default=dict)  # Renamed from metadata - reserved in SQLAlchemy
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class InstagramPost(Base):
    """
    Instagram posts scraped during onboarding.
    Used for ToneProfile analysis and RAG indexing.
    """

    __tablename__ = "instagram_posts"
    __table_args__ = {"extend_existing": True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(String(100), nullable=False, index=True)
    post_id = Column(String(100), nullable=False)  # Instagram post ID
    caption = Column(Text)
    permalink = Column(Text)
    media_type = Column(String(50))  # IMAGE, VIDEO, CAROUSEL_ALBUM
    media_url = Column(Text)
    thumbnail_url = Column(Text)
    post_timestamp = Column(DateTime(timezone=True))
    likes_count = Column(Integer, default=0)
    comments_count = Column(Integer, default=0)
    hashtags = Column(JSON, default=list)  # Extracted hashtags
    mentions = Column(JSON, default=list)  # Extracted mentions
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PostContextModel(Base):
    """SQLAlchemy model for temporal context from Instagram posts.

    Stores analyzed context from creator's recent posts including
    promotions, topics, and availability hints.

    Part of POST-CONTEXT-DETECTION feature (Layer 4).
    """

    __tablename__ = "post_contexts"
    __table_args__ = (
        UniqueConstraint("creator_id", name="unique_post_context_creator"),
        Index("idx_post_contexts_creator", "creator_id"),
        Index("idx_post_contexts_expires", "expires_at"),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Creator reference
    creator_id = Column(String(100), nullable=False)

    # Promotion fields
    active_promotion = Column(Text)
    promotion_deadline = Column(DateTime(timezone=True))
    promotion_urgency = Column(Text)

    # Topics and products (JSON arrays)
    recent_topics = Column(JSON, default=list)
    recent_products = Column(JSON, default=list)

    # Availability
    availability_hint = Column(Text)

    # Generated instructions for bot
    context_instructions = Column(Text, nullable=False)

    # Metadata
    posts_analyzed = Column(Integer, default=0)
    analyzed_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    source_posts = Column(JSON, default=list)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ContentPerformance(Base):
    """
    Content performance metrics for Instagram/social.
    Includes engagement metrics and business correlation.
    """

    __tablename__ = "content_performance"
    __table_args__ = (
        Index("idx_content_perf_creator", "creator_id", "platform", "posted_at"),
        UniqueConstraint("creator_id", "content_id", name="uq_content_perf_content_id"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(String(100), nullable=False, index=True)
    content_id = Column(String(100), nullable=False)
    platform = Column(String(20), default="instagram")

    # Metadata
    content_type = Column(String(50))
    posted_at = Column(DateTime(timezone=True))
    caption = Column(Text)
    hashtags = Column(JSON, default=list)
    mentions = Column(JSON, default=list)
    topics_detected = Column(JSON, default=list)

    # Engagement metrics
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    saves = Column(Integer, default=0)
    reach = Column(Integer, default=0)
    impressions = Column(Integer, default=0)
    video_views = Column(Integer, default=0)
    avg_watch_time_seconds = Column(Float)

    # Calculated metrics
    engagement_rate = Column(Float)
    virality_score = Column(Float)
    save_rate = Column(Float)

    # Comment analysis
    comment_sentiment_avg = Column(Float)
    comment_topics = Column(JSON, default=list)
    questions_in_comments = Column(Integer, default=0)

    # Business correlation
    dms_generated_24h = Column(Integer, default=0)
    dms_generated_48h = Column(Integer, default=0)
    dms_generated_7d = Column(Integer, default=0)
    leads_generated = Column(Integer, default=0)
    conversions_attributed = Column(Integer, default=0)
    revenue_attributed = Column(Float, default=0)

    # Predictions
    predicted_engagement = Column(Float)
    performance_vs_predicted = Column(Float)

    last_updated = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RAGDocument(Base):
    """
    Persistent storage for RAG documents with source tracking.
    Anti-hallucination: Every piece of content has a verifiable source_url.
    """

    __tablename__ = "rag_documents"
    __table_args__ = {"extend_existing": True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False, index=True)
    doc_id = Column(String(64), nullable=False, index=True)  # Hash-based unique ID
    content = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)  # REQUIRED: Original source for verification
    source_type = Column(String(50), nullable=False)  # website, instagram, pdf, youtube, etc.
    content_type = Column(String(50))  # service, testimonial, faq, about, product, etc.
    title = Column(String(500))
    chunk_index = Column(Integer, default=0)
    total_chunks = Column(Integer, default=1)
    embedding_model = Column(String(100), default="all-MiniLM-L6-v2")
    extra_data = Column(
        JSON, default=dict
    )  # Additional structured data (renamed from metadata - reserved)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), index=True)  # Indexed: filtered in knowledge endpoints
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
