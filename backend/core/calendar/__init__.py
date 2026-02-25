"""
Calendar Integration System for Clonnect Creators.

Supports:
- Calendly (invitee.created, invitee.canceled)
- Cal.com (BOOKING_CREATED, BOOKING_CANCELLED)

Provides:
- Booking link management
- Available slots query
- Webhook processing
- Booking tracking

Storage: JSON files in data/calendar/

Environment Variables:
- CALENDLY_API_KEY: Calendly API key
- CALENDLY_WEBHOOK_SECRET: Calendly webhook signing secret
- CALCOM_API_KEY: Cal.com API key
- CALCOM_WEBHOOK_SECRET: Cal.com webhook secret
"""

from .models import (
    CalendarPlatform,
    BookingStatus,
    MeetingType,
    BookingLink,
    Booking,
    TimeSlot,
)
from .manager import (
    CalendarManager,
    get_calendar_manager,
)

__all__ = [
    "CalendarPlatform",
    "BookingStatus",
    "MeetingType",
    "BookingLink",
    "Booking",
    "TimeSlot",
    "CalendarManager",
    "get_calendar_manager",
]
