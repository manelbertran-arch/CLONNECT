"""Creator models: Creator, CreatorAvailability, ToneProfile, StyleProfileModel, PersonalityDoc, RelationshipDNAModel."""
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
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

try:
    from api.database import Base
except ImportError:
    from database import Base


class Creator(Base):
    __tablename__ = "creators"
    __table_args__ = {"extend_existing": True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True)
    name = Column(String(255), nullable=False, index=True)  # FIX P1: Added index for faster lookups
    api_key = Column(String(64), unique=True)
    bot_active = Column(Boolean, default=False)  # Start paused by default
    clone_tone = Column(String(50), default="friendly")
    clone_style = Column(Text)
    clone_name = Column(String(255))
    clone_vocabulary = Column(Text)
    welcome_message = Column(Text)
    # Channel connections
    telegram_bot_token = Column(String(255))
    instagram_token = Column(Text)
    instagram_token_expires_at = Column(DateTime(timezone=True))
    instagram_page_id = Column(
        String(255), index=True
    )  # Facebook Page ID (indexed for webhook routing)
    instagram_user_id = Column(
        String(255), index=True
    )  # Instagram Business Account ID (indexed for webhook routing)
    instagram_additional_ids = Column(
        JSONB, default=list
    )  # Additional/legacy IDs for webhook routing ["id1", "id2"]
    # Webhook tracking
    webhook_last_received = Column(DateTime(timezone=True))
    webhook_count = Column(Integer, default=0)
    whatsapp_token = Column(Text)
    whatsapp_phone_id = Column(String(255), index=True)  # Indexed for multi-tenant webhook routing
    # Payment connections
    stripe_api_key = Column(Text)
    paypal_token = Column(Text)
    paypal_email = Column(String(255))
    hotmart_token = Column(Text)
    # Calendar connections
    calendly_token = Column(Text)
    calendly_refresh_token = Column(Text)
    calendly_token_expires_at = Column(DateTime(timezone=True))
    # Zoom connections
    zoom_access_token = Column(Text)
    zoom_refresh_token = Column(Text)
    zoom_token_expires_at = Column(DateTime(timezone=True))
    # Google connections (for Meet via Calendar API)
    google_access_token = Column(Text)
    google_refresh_token = Column(Text)
    google_token_expires_at = Column(DateTime(timezone=True))
    # Alternative payment methods (JSON: bizum, bank_transfer, mercado_pago, revolut, other)
    other_payment_methods = Column(JSON, default=dict)
    # Knowledge base: About Me/Business info (JSON with structured fields)
    knowledge_about = Column(JSON, default=dict)
    # Onboarding status
    onboarding_completed = Column(Boolean, default=False)
    # Clone creation progress (persisted in DB, not in-memory)
    clone_status = Column(String(20), default="pending")  # pending, in_progress, complete, error
    clone_progress = Column(
        JSON, default=dict
    )  # {"step": "syncing", "percent": 50, "messages_synced": 100}
    clone_started_at = Column(DateTime(timezone=True))
    clone_completed_at = Column(DateTime(timezone=True))
    clone_error = Column(Text)  # Error message if clone_status is "error"
    # Copilot mode: if True, bot suggestions require approval before sending
    copilot_mode = Column(Boolean, default=True)
    # Autopilot premium: if True AND copilot_mode=False, bot sends without approval
    autopilot_premium_enabled = Column(Boolean, default=False, nullable=False)
    # Email capture configuration (JSON with messages per level, discount codes, etc.)
    email_capture_config = Column(JSON, default=dict)
    # Product price for lead scoring (default €97)
    product_price = Column(Float, default=97.0)
    # Website URL (promoted from knowledge_about JSON to dedicated column)
    website_url = Column(String(500), nullable=True)
    # Memory consolidation timestamp (CC: lock file mtime, consolidationLock.ts:1,29-36)
    last_consolidated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # ORM relationships
    leads = relationship("Lead", back_populates="creator", lazy="dynamic")
    products = relationship("Product", back_populates="creator", lazy="dynamic")


class CreatorAvailability(Base):
    """Creator's weekly availability schedule"""

    __tablename__ = "creator_availability"
    __table_args__ = {"extend_existing": True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(String(255), nullable=False, index=True)
    day_of_week = Column(Integer, nullable=False)  # 0=Monday, 1=Tuesday, ..., 6=Sunday
    start_time = Column(Time, nullable=False)  # e.g. 09:00
    end_time = Column(Time, nullable=False)  # e.g. 17:00
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ToneProfile(Base):
    """
    Creator's voice/personality profile for AI clone.
    Migrated from data/tone_profiles/{creator_id}.json
    """

    __tablename__ = "tone_profiles"
    __table_args__ = {"extend_existing": True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(String(100), unique=True, nullable=False, index=True)
    profile_data = Column(JSON, nullable=False)  # Full ToneProfile as JSON
    analyzed_posts_count = Column(Integer, default=0)
    confidence_score = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class StyleProfileModel(Base):
    """Data-driven style profile extracted by StyleAnalyzer.

    Stores quantitative metrics + qualitative LLM analysis + generated prompt section.
    One per creator. Updated periodically when new messages accumulate.
    Part of ECHO Engine (E = Extract).
    """

    __tablename__ = "style_profiles"
    __table_args__ = (
        Index("idx_style_profiles_creator", "creator_id", unique=True),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False)
    profile_data = Column(JSONB, nullable=False)  # Full StyleProfile JSON
    version = Column(Integer, default=1)
    confidence = Column(Float, default=0.5)  # 0.0-1.0
    messages_analyzed = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PersonalityDoc(Base):
    """Persistent storage for personality extraction documents (Doc D, Doc E).

    Railway has an ephemeral filesystem — all files written to disk are lost on
    every deploy. This table stores the markdown content of Doc D (bot config)
    and Doc E (copilot rules) so they survive deploys.

    One row per (creator_id, doc_type). Updated on every extraction run.
    """

    __tablename__ = "personality_docs"
    __table_args__ = (
        UniqueConstraint("creator_id", "doc_type", name="uq_personality_docs_creator_type"),
        Index("ix_personality_docs_creator_id", "creator_id"),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid.uuid4())
    creator_id = Column(String(100), nullable=False)  # creator UUID or slug
    doc_type = Column(String(10), nullable=False)      # 'doc_d' or 'doc_e'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RelationshipDNAModel(Base):
    """SQLAlchemy model for relationship-specific communication context.

    Stores personalized vocabulary, tone, and interaction patterns
    for each creator-follower relationship.

    Part of RELATIONSHIP-DNA feature.
    """

    __tablename__ = "relationship_dna"
    __table_args__ = (
        UniqueConstraint("creator_id", "follower_id", name="uq_relationship_dna_creator_follower"),
        Index("idx_relationship_dna_creator_follower", "creator_id", "follower_id"),
        Index("idx_relationship_dna_type", "relationship_type"),
        Index("idx_relationship_dna_creator", "creator_id"),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Foreign keys (stored as strings for flexibility with external IDs)
    creator_id = Column(String(100), nullable=False)
    follower_id = Column(String(255), nullable=False)

    # Relationship classification
    relationship_type = Column(String(50), nullable=False, default="DESCONOCIDO")
    trust_score = Column(Float, default=0.0)
    depth_level = Column(Integer, default=0)

    # Vocabulary specific to this relationship (JSONB for efficient querying)
    vocabulary_uses = Column(JSON, default=list)
    vocabulary_avoids = Column(JSON, default=list)
    emojis = Column(JSON, default=list)

    # Interaction patterns observed from conversation history
    avg_message_length = Column(Integer)
    questions_frequency = Column(Float)
    multi_message_frequency = Column(Float)
    tone_description = Column(Text)

    # Shared context extracted from conversations
    recurring_topics = Column(JSON, default=list)
    private_references = Column(JSON, default=list)

    # Generated instructions for the bot
    bot_instructions = Column(Text)

    # Golden examples for few-shot learning
    golden_examples = Column(JSON, default=list)

    # Metadata for tracking analysis state
    total_messages_analyzed = Column(Integer, default=0)
    last_analyzed_at = Column(DateTime(timezone=True))
    version = Column(Integer, default=1)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
