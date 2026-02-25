"""Booking models: BookingLink, CalendarBooking, BookingSlot."""
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

try:
    from api.database import Base
except ImportError:
    from database import Base


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
