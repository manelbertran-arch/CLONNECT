from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON, ForeignKey, Date, Time, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.sql import func
import uuid

try:
    from api.database import Base
except:
    from database import Base


class User(Base):
    """User accounts for authentication"""
    __tablename__ = "users"
    __table_args__ = {'extend_existing': True}
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
    __table_args__ = {'extend_existing': True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), nullable=False, index=True)
    role = Column(String(50), default="owner")  # owner, admin, viewer
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Creator(Base):
    __tablename__ = "creators"
    __table_args__ = {'extend_existing': True}
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
    instagram_page_id = Column(String(255))
    instagram_user_id = Column(String(255))  # Instagram Business Account ID
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
    clone_progress = Column(JSON, default=dict)  # {"step": "syncing", "percent": 50, "messages_synced": 100}
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

class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = {'extend_existing': True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), index=True)  # FIX P1: Added index
    platform = Column(String(20), nullable=False)
    platform_user_id = Column(String(255), nullable=False, index=True)  # FIX P1: Added index for lookups
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
    __table_args__ = {'extend_existing': True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), nullable=False, index=True)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), index=True)
    activity_type = Column(String(50), nullable=False)  # note, status_change, email, call, meeting, tag_added, task_completed
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
    __table_args__ = {'extend_existing': True}
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
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"), index=True)  # FIX P1: Added index for joins
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    intent = Column(String(50))
    # Copilot mode fields
    status = Column(String(20), default="sent")  # pending_approval, sent, edited, discarded
    suggested_response = Column(Text)  # Original bot suggestion (before edit)
    approved_at = Column(DateTime(timezone=True))
    approved_by = Column(String(50))  # "creator" or "auto"
    platform_message_id = Column(String(255))  # ID del mensaje en Instagram/Telegram
    msg_metadata = Column(JSON, default=dict)  # {type: "story_mention", url: "...", emoji_type: "camera"}
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
    extra_data = Column(JSON, default=dict)  # Additional platform-specific data (renamed from metadata - reserved in SQLAlchemy)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class CalendarBooking(Base):
    """Calendar bookings - stored in PostgreSQL for persistence"""
    __tablename__ = "calendar_bookings"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(String(255), nullable=False, index=True)
    follower_id = Column(String(255), nullable=False)
    meeting_type = Column(String(50), nullable=False)
    platform = Column(String(50), nullable=False)  # calendly, calcom, manual
    status = Column(String(50), default="scheduled")  # scheduled, completed, cancelled, no_show, rescheduled
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
    __table_args__ = {'extend_existing': True}
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
    __table_args__ = {'extend_existing': True}
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
    calendar_booking_id = Column(UUID(as_uuid=True), ForeignKey("calendar_bookings.id"))  # Link to CalendarBooking
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
    __table_args__ = {'extend_existing': True}
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
    __table_args__ = {'extend_existing': True}
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
    __table_args__ = {'extend_existing': True}
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
    __table_args__ = {'extend_existing': True}
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
    extra_data = Column(JSON, default=dict)  # Additional structured data (renamed from metadata - reserved)
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
    __table_args__ = {'extend_existing': True}
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
    __table_args__ = {'extend_existing': True}
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
    __table_args__ = {'extend_existing': True}
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
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(String(100), nullable=False, index=True)
    conversation_id = Column(String(255), nullable=False)
    status = Column(String(20), default="pending")  # pending, processing, done, failed
    attempts = Column(Integer, default=0)
    last_error = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True))

    # Unique constraint para evitar duplicados
    __table_args__ = (
        {'extend_existing': True},
    )


class SyncState(Base):
    """
    Estado global del sync por creator.
    Permite trackear progreso y manejar rate limits.
    """
    __tablename__ = "sync_state"
    __table_args__ = {'extend_existing': True}

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
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(String(100), nullable=False, index=True)
    follower_id = Column(String(255), nullable=False, index=True)

    # State machine position
    phase = Column(String(50), default="inicio")  # inicio, cualificacion, descubrimiento, propuesta, objeciones, cierre, escalar
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
        UniqueConstraint('creator_id', 'follower_id', name='uq_follower_memory_creator_follower'),
        Index('idx_follower_memories_creator_follower', 'creator_id', 'follower_id'),
        {'extend_existing': True},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(String(100), nullable=False, index=True)
    follower_id = Column(String(255), nullable=False, index=True)

    # Basic info
    username = Column(String(255), default="")
    name = Column(String(255), default="")

    # Timestamps
    first_contact = Column(String(50), default="")  # ISO format string
    last_contact = Column(String(50), default="")   # ISO format string

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
        UniqueConstraint('creator_id', 'user_id', name='uq_user_profile_creator_user'),
        Index('idx_user_profiles_creator_user', 'creator_id', 'user_id'),
        {'extend_existing': True},
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
