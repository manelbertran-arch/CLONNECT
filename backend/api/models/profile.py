"""Profile models: UnifiedProfile, PlatformIdentity, FollowerMemoryDB, UserProfileDB."""
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


class UnifiedProfile(Base):
    """
    Unified profile linking users across platforms via email.
    Enables cross-platform conversation continuity.
    """

    __tablename__ = "unified_profiles"
    __table_args__ = {"extend_existing": True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255))
    phone = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PlatformIdentity(Base):
    """
    Links platform-specific identities to unified profiles.
    One unified profile can have multiple platform identities.
    """

    __tablename__ = "platform_identities"
    __table_args__ = {"extend_existing": True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    unified_profile_id = Column(UUID(as_uuid=True), ForeignKey("unified_profiles.id"), index=True)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), index=True)
    platform = Column(String(50), nullable=False)  # instagram, telegram, whatsapp
    platform_user_id = Column(String(255), nullable=False)
    username = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class FollowerMemoryDB(Base):
    """
    Persistent follower memory for DM agent.
    Migrated from JSON files (data/followers/) to PostgreSQL.

    Contains 27 fields matching the FollowerMemory dataclass in dm_agent.py.
    """

    __tablename__ = "follower_memories"
    __table_args__ = (
        UniqueConstraint("creator_id", "follower_id", name="uq_follower_memory_creator_follower"),
        Index("idx_follower_memories_creator_follower", "creator_id", "follower_id"),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(String(100), nullable=False, index=True)
    follower_id = Column(String(255), nullable=False, index=True)

    # Basic info
    username = Column(String(255), default="")
    name = Column(String(255), default="")

    # Timestamps
    first_contact = Column(String(50), default="")  # ISO format string
    last_contact = Column(String(50), default="")  # ISO format string

    # Interaction stats
    total_messages = Column(Integer, default=0)

    # Profile data (lists stored as JSON)
    interests = Column(JSON, default=list)
    products_discussed = Column(JSON, default=list)
    objections_raised = Column(JSON, default=list)

    # Scoring
    purchase_intent_score = Column(Float, default=0.0)

    # Status flags
    is_lead = Column(Boolean, default=False)
    is_customer = Column(Boolean, default=False)
    status = Column(String(20), default="new")  # new, active, hot, customer

    # Preferences
    preferred_language = Column(String(10), default="es")

    # Conversation history (last 20 messages)
    last_messages = Column(JSON, default=list)

    # Link and objection control
    links_sent_count = Column(Integer, default=0)
    last_link_message_num = Column(Integer, default=0)
    objections_handled = Column(JSON, default=list)
    arguments_used = Column(JSON, default=list)

    # Greeting variation
    greeting_variant_index = Column(Integer, default=0)

    # Naturalness fields
    last_greeting_style = Column(String(100), default="")
    last_emojis_used = Column(JSON, default=list)
    messages_since_name_used = Column(Integer, default=0)

    # Alternative contact
    alternative_contact = Column(String(255), default="")
    alternative_contact_type = Column(String(50), default="")  # whatsapp, telegram
    contact_requested = Column(Boolean, default=False)

    # DB timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserProfileDB(Base):
    """
    User/Lead profile with preferences and behavior tracking.
    Migrated from JSON files (data/profiles/) to PostgreSQL.

    Different from UnifiedProfile:
    - UnifiedProfile = identity (email, name, phone) for cross-platform linking
    - UserProfileDB = behavior (interests, preferences, objections) for personalization
    """

    __tablename__ = "user_profiles"
    __table_args__ = (
        UniqueConstraint("creator_id", "user_id", name="uq_user_profile_creator_user"),
        Index("idx_user_profiles_creator_user", "creator_id", "user_id"),
        {"extend_existing": True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(String(100), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)

    # Preferences (language, response_style, communication_tone)
    preferences = Column(JSON, default=dict)

    # Interests with weights (topic -> weight)
    interests = Column(JSON, default=dict)

    # Objections raised (list of {type, context, timestamp})
    objections = Column(JSON, default=list)

    # Products of interest (list of {id, name, first_interest, interest_count})
    interested_products = Column(JSON, default=list)

    # Content scores for personalized ranking (content_id -> score)
    content_scores = Column(JSON, default=dict)

    # Interaction stats
    interaction_count = Column(Integer, default=0)
    last_interaction = Column(DateTime(timezone=True))

    # DB timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
