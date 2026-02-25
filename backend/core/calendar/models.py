"""
Calendar models: enums, dataclasses for Clonnect calendar integration.
"""

from typing import Dict, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum


class CalendarPlatform(Enum):
    """Supported calendar platforms"""
    CALENDLY = "calendly"
    CALCOM = "calcom"
    MANUAL = "manual"


class BookingStatus(Enum):
    """Booking status"""
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"
    RESCHEDULED = "rescheduled"


class MeetingType(Enum):
    """Common meeting types"""
    DISCOVERY = "discovery"  # 15-30 min intro call
    CONSULTATION = "consultation"  # 30-60 min detailed call
    COACHING = "coaching"  # 60 min coaching session
    FOLLOWUP = "followup"  # 15 min follow-up
    CUSTOM = "custom"


@dataclass
class BookingLink:
    """Represents a booking link configuration"""
    id: str
    creator_id: str
    meeting_type: str
    title: str
    description: str
    duration_minutes: int
    platform: str
    url: str
    is_active: bool = True
    created_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'BookingLink':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Booking:
    """Represents a calendar booking"""
    booking_id: str
    creator_id: str
    follower_id: str
    meeting_type: str
    platform: str
    status: str
    scheduled_at: str
    duration_minutes: int
    guest_name: str = ""
    guest_email: str = ""
    guest_phone: str = ""
    meeting_url: str = ""
    external_id: str = ""  # Calendly/Cal.com booking ID
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
    cancelled_at: str = ""
    cancel_reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Booking':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class TimeSlot:
    """Represents an available time slot"""
    start: str
    end: str
    duration_minutes: int

    def to_dict(self) -> dict:
        return asdict(self)
