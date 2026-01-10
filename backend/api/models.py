from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON, ForeignKey, Date, Time
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
    name = Column(String(255), nullable=False)
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
    # Copilot mode: if True, bot suggestions require approval before sending
    copilot_mode = Column(Boolean, default=True)
    # Email capture configuration (JSON with messages per level, discount codes, etc.)
    email_capture_config = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Lead(Base):
    __tablename__ = "leads"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"))
    platform = Column(String(20), nullable=False)
    platform_user_id = Column(String(255), nullable=False)
    username = Column(String(255))
    full_name = Column(String(255))
    status = Column(String(50), default="new")
    score = Column(Integer, default=0)
    purchase_intent = Column(Float, default=0.0)
    context = Column(JSON, default=dict)
    first_contact_at = Column(DateTime(timezone=True), server_default=func.now())
    last_contact_at = Column(DateTime(timezone=True), server_default=func.now())

class Message(Base):
    __tablename__ = "messages"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = Column(UUID(as_uuid=True), ForeignKey("leads.id"))
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    intent = Column(String(50))
    # Copilot mode fields
    status = Column(String(20), default="sent")  # pending_approval, sent, edited, discarded
    suggested_response = Column(Text)  # Original bot suggestion (before edit)
    approved_at = Column(DateTime(timezone=True))
    approved_by = Column(String(50))  # "creator" or "auto"
    platform_message_id = Column(String(255))  # ID del mensaje en Instagram/Telegram
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Product(Base):
    __tablename__ = "products"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    price = Column(Float)
    currency = Column(String(3), default="EUR")
    payment_link = Column(String(500), default="")  # Stripe/PayPal payment link
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
    metadata = Column(JSON, default=dict)
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
