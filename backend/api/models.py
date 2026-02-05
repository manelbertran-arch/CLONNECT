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
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

try:
    from api.database import Base
except ImportError:
    from database import Base


class User(Base):
    """User accounts for authentication"""

    __tablename__ = "users"
    __table_args__ = {"extend_existing": True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True))


class UserCreator(Base):
    """Many-to-many relationship between Users and Creators"""

    __tablename__ = "user_creators"
    __table_args__ = {"extend_existing": True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False, index=True)
    role = Column(String(50), default="owner")  # owner, admin, viewer
    created_at = Column(DateTime(timezone=True), server_default=func.now())


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
    whatsapp_phone_id = Column(String(255))
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
    # Email capture configuration (JSON with messages per level, discount codes, etc.)
    email_capture_config = Column(JSON, default=dict)
    # Product price for lead scoring (default €97)
    product_price = Column(Float, default=97.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


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
    resolved_to_creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"))
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
    platform = Column(String(20), nullable=False)
    platform_user_id = Column(
        String(255), nullable=False, index=True
    )  # FIX P1: Added index for lookups
    username = Column(String(255))
    full_name = Column(String(255))
    profile_pic_url = Column(Text)  # Instagram/platform profile picture URL (long CDN URLs)
    status = Column(String(50), default="nuevo")  # nuevo, interesado, caliente, cliente, fantasma
    score = Column(Integer, default=0)
    purchase_intent = Column(Float, default=0.0)
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
    platform_message_id = Column(String(255))  # ID del mensaje en Instagram/Telegram
    msg_metadata = Column(
        JSON, default=dict
    )  # {type: "story_mention", url: "...", emoji_type: "camera"}
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Product(Base):
    __tablename__ = "products"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    short_description = Column(String(300))  # Descripción corta para cards
    # Taxonomía: category + product_type
    category = Column(String(20), default="product")  # product, service, resource
    product_type = Column(String(50), default="otro")  # Depende de category:
    # product: ebook, curso, plantilla, membership, otro
    # service: coaching, mentoria, consultoria, call, sesion, otro
    # resource: podcast, blog, youtube, newsletter, free_guide, otro
    price = Column(Float)
    currency = Column(String(10), default="EUR")
    is_free = Column(Boolean, default=False)  # True para discovery calls gratuitas
    payment_link = Column(String(500), default="")  # Stripe/PayPal/Calendly link
    is_active = Column(Boolean, default=True)
    # Anti-hallucination fields: source tracking
    source_url = Column(Text)  # URL where product info was found
    price_verified = Column(Boolean, default=False)  # True if price was extracted from source
    confidence = Column(Float, default=0.0)  # 0.0-1.0 extraction confidence
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NurturingSequence(Base):
    __tablename__ = "nurturing_sequences"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"))
    type = Column(String(50), nullable=False)
    name = Column(String(255))
    is_active = Column(Boolean, default=True)
    steps = Column(JSON, default=[])
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"))
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BookingLink(Base):
    """Booking links for calendar integration - stored in PostgreSQL for persistence"""

    __tablename__ = "booking_links"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(String(255), nullable=False, index=True)  # String to support "manel" etc.
    meeting_type = Column(String(50), nullable=False)  # discovery, consultation, coaching, custom
    title = Column(String(255), nullable=False)
    description = Column(Text)
    duration_minutes = Column(Integer, default=30)
    platform = Column(String(50), default="manual")  # calendly, zoom, google-meet, etc.
    url = Column(Text)  # Booking URL
    price = Column(Integer, default=0)  # Price in euros (0 = free)
    is_active = Column(Boolean, default=True)
    extra_data = Column(
        JSON, default=dict
    )  # Additional platform-specific data (renamed from metadata - reserved in SQLAlchemy)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CalendarBooking(Base):
    """Calendar bookings - stored in PostgreSQL for persistence"""

    __tablename__ = "calendar_bookings"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(String(255), nullable=False, index=True)
    follower_id = Column(String(255), nullable=False)
    meeting_type = Column(String(50), nullable=False)
    platform = Column(String(50), nullable=False)  # calendly, calcom, manual
    status = Column(
        String(50), default="scheduled"
    )  # scheduled, completed, cancelled, no_show, rescheduled
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    duration_minutes = Column(Integer, default=30)
    guest_name = Column(String(255))
    guest_email = Column(String(255))
    guest_phone = Column(String(50))
    meeting_url = Column(Text)
    external_id = Column(String(255))  # Calendly/Cal.com booking ID
    notes = Column(Text)
    cancel_reason = Column(Text)
    cancelled_at = Column(DateTime(timezone=True))
    extra_data = Column(JSON, default=dict)  # Renamed from metadata - reserved in SQLAlchemy
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


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


class BookingSlot(Base):
    """Individual booking slots for a specific date"""

    __tablename__ = "booking_slots"
    __table_args__ = {"extend_existing": True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(String(255), nullable=False, index=True)
    service_id = Column(UUID(as_uuid=True), ForeignKey("booking_links.id"), nullable=False)
    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    status = Column(String(20), default="available")  # available, booked, cancelled
    booked_by_name = Column(String(255))
    booked_by_email = Column(String(255))
    booked_by_phone = Column(String(50))
    meeting_url = Column(Text)  # Generated when booking is confirmed
    calendar_booking_id = Column(
        UUID(as_uuid=True), ForeignKey("calendar_bookings.id")
    )  # Link to CalendarBooking
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# =============================================================================
# UNIFIED PROFILES - Cross-platform identity & email capture
# =============================================================================


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


class EmailAskTracking(Base):
    """
    Tracks email ask attempts per user to implement progressive asking strategy.
    Levels: 0=never asked, 1=subtle, 2=value offer, 3=irresistible, 4=necessary
    """

    __tablename__ = "email_ask_tracking"
    __table_args__ = {"extend_existing": True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), index=True)
    platform = Column(String(50), nullable=False)
    platform_user_id = Column(String(255), nullable=False, index=True)
    ask_level = Column(Integer, default=0)  # 0-4
    last_asked_at = Column(DateTime(timezone=True))
    declined_count = Column(Integer, default=0)
    captured_email = Column(String(255))  # Email once captured
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# =============================================================================
# RAG DOCUMENTS - Persistent storage for indexed content
# =============================================================================


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


# =============================================================================
# PERSISTENT DATA - Migrated from JSON files to PostgreSQL
# =============================================================================


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


# =============================================================================
# SYNC QUEUE SYSTEM - Para sincronización con rate limiting inteligente
# =============================================================================


class SyncQueue(Base):
    """
    Cola de jobs de sincronización.
    Cada conversación es un job separado para permitir retry granular.
    """

    __tablename__ = "sync_queue"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(String(100), nullable=False, index=True)
    conversation_id = Column(String(255), nullable=False)
    status = Column(String(20), default="pending")  # pending, processing, done, failed
    attempts = Column(Integer, default=0)
    last_error = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True))

    # Unique constraint para evitar duplicados
    __table_args__ = ({"extend_existing": True},)


class SyncState(Base):
    """
    Estado global del sync por creator.
    Permite trackear progreso y manejar rate limits.
    """

    __tablename__ = "sync_state"
    __table_args__ = {"extend_existing": True}

    creator_id = Column(String(100), primary_key=True)
    status = Column(String(20), default="idle")  # idle, running, paused, rate_limited, completed
    last_sync_at = Column(DateTime(timezone=True))
    rate_limit_until = Column(DateTime(timezone=True))  # No intentar hasta esta hora
    conversations_synced = Column(Integer, default=0)
    conversations_total = Column(Integer, default=0)
    messages_saved = Column(Integer, default=0)
    current_conversation = Column(String(255))  # Conversación actual siendo procesada
    error_count = Column(Integer, default=0)
    last_error = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# CONVERSATION STATE - Persistent sales funnel state machine
# =============================================================================


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


# =============================================================================
# FOLLOWER MEMORY - Persistent follower data for DM conversations
# =============================================================================


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


# =============================================================================
# USER PROFILES - Lead behavior and preferences for personalization
# =============================================================================


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


# =============================================================================
# CONVERSATION EMBEDDINGS - Semantic Memory for Long-term Conversation Context
# =============================================================================


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


# =============================================================================
# ANALYTICS - Daily metrics and product analytics
# =============================================================================


class CreatorMetricsDaily(Base):
    """
    Daily aggregated metrics per creator.
    Populated by background jobs analyzing conversations, leads, and sales.
    """

    __tablename__ = "creator_metrics_daily"
    __table_args__ = (
        UniqueConstraint("creator_id", "date", name="uq_metrics_daily_creator_date"),
        Index("idx_metrics_daily_creator_date", "creator_id", "date"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(String(100), nullable=False, index=True)
    date = Column(Date, nullable=False)

    # Conversations
    total_conversations = Column(Integer, default=0)
    total_messages = Column(Integer, default=0)
    unique_users = Column(Integer, default=0)
    returning_users = Column(Integer, default=0)
    avg_response_time_seconds = Column(Float)
    avg_messages_per_conversation = Column(Float)
    avg_conversation_duration_minutes = Column(Float)

    # Intents and sentiment
    intent_distribution = Column(JSON, default=dict)
    sentiment_score = Column(Float)  # -1 to 1
    frustration_rate = Column(Float)
    purchase_intent_avg = Column(Float)

    # Funnel
    new_leads = Column(Integer, default=0)
    leads_engaged = Column(Integer, default=0)
    leads_qualified = Column(Integer, default=0)
    leads_hot = Column(Integer, default=0)
    conversions = Column(Integer, default=0)
    revenue = Column(Float, default=0)

    # Nurturing
    nurturing_sent = Column(Integer, default=0)
    nurturing_opened = Column(Integer, default=0)
    nurturing_responded = Column(Integer, default=0)
    nurturing_converted = Column(Integer, default=0)

    # Bookings
    calls_scheduled = Column(Integer, default=0)
    calls_completed = Column(Integer, default=0)
    calls_no_show = Column(Integer, default=0)
    calls_converted = Column(Integer, default=0)

    # Content
    posts_published = Column(Integer, default=0)
    total_engagement = Column(Integer, default=0)
    avg_engagement_rate = Column(Float)
    dms_from_content = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProductAnalytics(Base):
    """
    Per-product daily analytics.
    Tracks mentions, questions, objections, and conversions per product.
    """

    __tablename__ = "product_analytics"
    __table_args__ = (
        Index("idx_product_analytics_creator_date", "creator_id", "product_id", "date"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(100), nullable=False)
    creator_id = Column(String(100), nullable=False, index=True)
    date = Column(Date, nullable=False)

    mentions = Column(Integer, default=0)
    questions = Column(Integer, default=0)
    objections = Column(Integer, default=0)
    link_clicks = Column(Integer, default=0)
    conversions = Column(Integer, default=0)
    revenue = Column(Float, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


# =============================================================================
# INTELLIGENCE - Predictions, Recommendations, and Insights
# =============================================================================


class Prediction(Base):
    """
    ML predictions for leads and revenue.
    Types: conversion, churn, revenue, engagement, best_time
    """

    __tablename__ = "predictions"
    __table_args__ = (
        Index("idx_predictions_creator_type", "creator_id", "prediction_type", "target_date"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(String(100), nullable=False, index=True)
    prediction_type = Column(
        String(50), nullable=False
    )  # conversion, churn, revenue, engagement, best_time

    target_date = Column(Date)
    target_id = Column(String(100))  # lead_id, content_id, etc.

    predicted_value = Column(Float, nullable=False)
    confidence = Column(Float)
    factors = Column(JSON, default=list)  # Contributing factors

    actual_value = Column(Float)  # For validation
    was_correct = Column(Boolean)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    validated_at = Column(DateTime(timezone=True))


class Recommendation(Base):
    """
    Generated recommendations for creators.
    Categories: content, action, product, pricing, timing
    """

    __tablename__ = "recommendations"
    __table_args__ = (
        Index("idx_recommendations_creator_status", "creator_id", "status", "priority"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(String(100), nullable=False, index=True)
    category = Column(String(50), nullable=False)  # content, action, product, pricing, timing

    priority = Column(String(20), default="medium")  # low, medium, high
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    reasoning = Column(Text)

    data_points = Column(JSON, default=dict)
    expected_impact = Column(JSON, default=dict)

    action_type = Column(String(50))
    action_data = Column(JSON, default=dict)

    status = Column(String(20), default="pending")  # pending, viewed, acted, dismissed
    acted_at = Column(DateTime(timezone=True))
    result = Column(JSON)

    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DetectedTopic(Base):
    """
    Detected topics from conversation analysis.
    Types: question, objection, interest, complaint, suggestion
    """

    __tablename__ = "detected_topics"
    __table_args__ = (
        Index("idx_detected_topics_creator", "creator_id", "period_start"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(String(100), nullable=False, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    topic_label = Column(String(200), nullable=False)
    topic_type = Column(
        String(50), default="general"
    )  # question, objection, interest, complaint, suggestion

    message_count = Column(Integer, default=0)
    unique_users = Column(Integer, default=0)
    growth_rate = Column(Float)

    keywords = Column(JSON, default=list)
    example_messages = Column(JSON, default=list)
    related_products = Column(JSON, default=list)

    avg_sentiment = Column(Float)
    conversion_rate = Column(Float)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


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


class WeeklyReport(Base):
    """
    Weekly intelligence reports with LLM-generated insights.
    Contains metrics, comparisons, predictions, and recommendations.
    """

    __tablename__ = "weekly_reports"
    __table_args__ = (
        UniqueConstraint("creator_id", "week_start", name="uq_weekly_reports_creator_week"),
        Index("idx_weekly_reports_creator", "creator_id", "week_start"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(String(100), nullable=False, index=True)
    week_start = Column(Date, nullable=False)
    week_end = Column(Date, nullable=False)

    # Metrics summary
    metrics_summary = Column(JSON, default=dict)
    funnel_summary = Column(JSON, default=dict)

    # Comparisons
    vs_previous_week = Column(JSON, default=dict)
    vs_previous_month = Column(JSON, default=dict)
    vs_average = Column(JSON, default=dict)

    # Top performers
    top_content = Column(JSON, default=list)
    top_products = Column(JSON, default=list)
    hot_leads = Column(JSON, default=list)

    # Analysis
    topics_trending = Column(JSON, default=list)
    topics_declining = Column(JSON, default=list)
    objections_analysis = Column(JSON, default=dict)
    sentiment_analysis = Column(JSON, default=dict)

    # Predictions
    next_week_forecast = Column(JSON, default=dict)
    conversion_predictions = Column(JSON, default=list)
    churn_risks = Column(JSON, default=list)

    # Recommendations
    content_recommendations = Column(JSON, default=list)
    action_recommendations = Column(JSON, default=list)
    product_recommendations = Column(JSON, default=list)

    # LLM Summary
    executive_summary = Column(Text)
    key_wins = Column(JSON, default=list)
    areas_to_improve = Column(JSON, default=list)
    this_week_focus = Column(JSON, default=list)

    # Alerts
    alerts = Column(JSON, default=list)

    # Meta
    llm_model_used = Column(String(50))
    processing_time_seconds = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True))
    opened_at = Column(DateTime(timezone=True))


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
