"""Lead models: Lead, UnifiedLead, UnmatchedWebhook, LeadActivity, LeadTask, DismissedLead, LeadIntelligence, LeadMemory."""
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


class UnifiedLead(Base):
    """
    Cross-platform identity: groups leads from different channels (IG, WA, TG)
    that belong to the same real person.
    """

    __tablename__ = "unified_leads"
    __table_args__ = (
        Index("idx_unified_creator", "creator_id"),
        Index("idx_unified_email", "creator_id", "email"),
        Index("idx_unified_phone", "creator_id", "phone"),
        {"extend_existing": True},
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False)
    display_name = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    profile_pic_url = Column(Text)
    unified_score = Column(Float, default=0)
    status = Column(String(50), default="nuevo")
    first_contact_at = Column(DateTime(timezone=True))
    last_contact_at = Column(DateTime(timezone=True))
    merge_history = Column(JSON, default=list)  # Audit log of merges
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UnmatchedWebhook(Base):
    """
    Store webhooks that couldn't be matched to a creator.
    Used for debugging and manual resolution of routing issues.
    """

    __tablename__ = "unmatched_webhooks"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    instagram_ids = Column(JSONB, nullable=False)  # All IDs extracted from payload
    payload_summary = Column(JSONB)  # Summary of payload (no sensitive data)
    resolved = Column(Boolean, default=False, nullable=False)
    resolved_to_creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), index=True)
    resolved_at = Column(DateTime(timezone=True))
    notes = Column(Text)


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("creator_id", "platform_user_id", name="uq_lead_creator_platform"),
        Index("idx_lead_creator_platform", "creator_id", "platform_user_id"),
        {"extend_existing": True},
    )
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(
        UUID(as_uuid=True), ForeignKey("creators.id"), index=True
    )  # FIX P1: Added index
    unified_lead_id = Column(UUID(as_uuid=True), ForeignKey("unified_leads.id"), nullable=True, index=True)
    platform = Column(String(20), nullable=False)
    platform_user_id = Column(
        String(255), nullable=False, index=True
    )  # FIX P1: Added index for lookups
    username = Column(String(255))
    full_name = Column(String(255))
    profile_pic_url = Column(Text)  # Instagram/platform profile picture URL (long CDN URLs)
    status = Column(String(50), default="nuevo")  # V3: cliente, caliente, colaborador, amigo, nuevo, frío
    score = Column(Integer, default=0)
    purchase_intent = Column(Float, default=0.0)
    relationship_type = Column(String(30), default="nuevo")  # DEPRECATED: mirrors status
    score_updated_at = Column(DateTime(timezone=True))  # Last time score was recalculated
    context = Column(JSON, default=dict)
    first_contact_at = Column(DateTime(timezone=True), server_default=func.now())
    last_contact_at = Column(DateTime(timezone=True), server_default=func.now())
    # CRM fields
    notes = Column(Text)  # Free-form notes about the lead
    tags = Column(JSON, default=list)  # Array of tags: ["vip", "interested", "price_sensitive"]
    email = Column(String(255))  # Captured email
    phone = Column(String(50))  # Captured phone
    deal_value = Column(Float)  # Potential deal value in euros
    source = Column(String(100))  # Where they came from: "instagram_dm", "story_reply", "ad_click"
    assigned_to = Column(String(255))  # Team member assignment
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # ORM relationships
    creator = relationship("Creator", back_populates="leads", lazy="joined")
    messages = relationship("Message", back_populates="lead", lazy="dynamic", order_by="Message.created_at")
    activities = relationship("LeadActivity", back_populates="lead", lazy="dynamic")
    tasks = relationship("LeadTask", back_populates="lead", lazy="dynamic")


class LeadActivity(Base):
    """
    Activity log for leads - tracks all interactions and changes.
    Creates a timeline of the relationship with each lead.
    """

    __tablename__ = "lead_activities"
    __table_args__ = {"extend_existing": True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), index=True)
    activity_type = Column(
        String(50), nullable=False
    )  # note, status_change, email, call, meeting, tag_added, task_completed
    description = Column(Text)  # Human readable description
    old_value = Column(String(255))  # For status_change: previous status
    new_value = Column(String(255))  # For status_change: new status
    extra_data = Column(JSON, default=dict)  # Extra data: {tag: "vip"}, {meeting_type: "discovery"}
    created_by = Column(String(255))  # "system", "creator", user email
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # ORM relationships
    lead = relationship("Lead", back_populates="activities", lazy="joined")


class LeadTask(Base):
    """
    Tasks and reminders for leads - follow-ups, calls, etc.
    """

    __tablename__ = "lead_tasks"
    __table_args__ = {"extend_existing": True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    task_type = Column(String(50), default="follow_up")  # follow_up, call, email, meeting, other
    priority = Column(String(20), default="medium")  # low, medium, high, urgent
    status = Column(String(20), default="pending")  # pending, in_progress, completed, cancelled
    due_date = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    assigned_to = Column(String(255))  # User email or name
    created_by = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # ORM relationships
    lead = relationship("Lead", back_populates="tasks", lazy="joined")


class DismissedLead(Base):
    """
    Blocklist for leads that were manually deleted by creator.
    Prevents sync from re-importing deleted conversations.

    When a creator deletes a conversation, we add the lead's platform_user_id
    to this table. The sync process checks this table before creating new leads.
    """

    __tablename__ = "dismissed_leads"
    __table_args__ = (
        UniqueConstraint(
            "creator_id", "platform_user_id", name="ix_dismissed_leads_creator_platform"
        ),
        Index("ix_dismissed_leads_platform_user_id", "platform_user_id"),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(
        UUID(as_uuid=True), ForeignKey("creators.id", ondelete="CASCADE"), nullable=False
    )
    platform_user_id = Column(String(255), nullable=False)
    username = Column(String(255))  # For debug/reference
    dismissed_at = Column(DateTime(timezone=True), server_default=func.now())
    reason = Column(String(50), default="manual_delete")  # manual_delete, spam, blocked


class LeadIntelligence(Base):
    """
    Detailed lead intelligence and scoring.
    Provides predictions and recommendations per lead.
    """

    __tablename__ = "lead_intelligence"
    __table_args__ = (
        Index("idx_lead_intel_creator", "creator_id", "overall_score"),
        UniqueConstraint("creator_id", "lead_id", name="uq_lead_intel_lead"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(String(100), nullable=False, index=True)
    lead_id = Column(String(100), nullable=False)

    # Scores
    engagement_score = Column(Float, default=0)
    intent_score = Column(Float, default=0)
    fit_score = Column(Float, default=0)
    urgency_score = Column(Float, default=0)
    overall_score = Column(Float, default=0)

    # Predictions
    conversion_probability = Column(Float)
    predicted_value = Column(Float)
    churn_risk = Column(Float)
    best_contact_time = Column(Time)
    best_contact_day = Column(String(10))

    # Insights
    interests = Column(JSON, default=list)
    objections = Column(JSON, default=list)
    products_interested = Column(JSON, default=list)
    content_engaged = Column(JSON, default=list)

    # Recommendations
    recommended_action = Column(String(100))
    recommended_product = Column(String(100))
    talking_points = Column(JSON, default=list)

    last_calculated = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LeadMemory(Base):
    """Per-lead extracted facts with pgvector embeddings."""

    __tablename__ = "lead_memories"
    __table_args__ = (
        Index("idx_lead_memories_creator_lead", "creator_id", "lead_id"),
        Index("idx_lead_memories_active", "creator_id", "lead_id", "is_active"),
        Index("idx_lead_memories_type", "creator_id", "lead_id", "fact_type"),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False)
    fact_type = Column(String(30), nullable=False)
    fact_text = Column(Text, nullable=False)
    confidence = Column(Float, server_default="0.7")
    source_message_id = Column(UUID(as_uuid=True), nullable=True)
    source_type = Column(String(30), server_default="extracted")
    is_active = Column(Boolean, server_default="true")
    superseded_by = Column(UUID(as_uuid=True), nullable=True)
    times_accessed = Column(Integer, server_default="0")
    last_accessed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
