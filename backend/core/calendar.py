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

import os
import json
import hmac
import hashlib
import logging
import httpx
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from enum import Enum
import uuid

logger = logging.getLogger("clonnect-calendar")


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


class CalendarManager:
    """
    Manager for calendar integrations.

    Handles Calendly and Cal.com webhooks, manages booking links,
    and tracks bookings.
    """

    def __init__(self, storage_path: str = "data/calendar"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)

        # API keys from environment
        self.calendly_api_key = os.getenv("CALENDLY_API_KEY", "")
        self.calendly_webhook_secret = os.getenv("CALENDLY_WEBHOOK_SECRET", "")
        self.calcom_api_key = os.getenv("CALCOM_API_KEY", "")
        self.calcom_webhook_secret = os.getenv("CALCOM_WEBHOOK_SECRET", "")

        # API base URLs
        self.calendly_base_url = "https://api.calendly.com"
        self.calcom_base_url = os.getenv("CALCOM_BASE_URL", "https://api.cal.com/v1")

        # Cache
        self._links_cache: Dict[str, List[BookingLink]] = {}
        self._bookings_cache: Dict[str, List[Booking]] = {}

        logger.info(f"CalendarManager initialized, storage={storage_path}")

    # ==========================================================================
    # FILE OPERATIONS
    # ==========================================================================

    def _get_links_file(self, creator_id: str) -> str:
        return os.path.join(self.storage_path, f"{creator_id}_links.json")

    def _get_bookings_file(self, creator_id: str) -> str:
        return os.path.join(self.storage_path, f"{creator_id}_bookings.json")

    def _load_links(self, creator_id: str) -> List[BookingLink]:
        """Load booking links for a creator"""
        if creator_id in self._links_cache:
            return self._links_cache[creator_id]

        file_path = self._get_links_file(creator_id)
        links = []

        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    links = [BookingLink.from_dict(l) for l in data]
            except Exception as e:
                logger.error(f"Error loading links: {e}")

        self._links_cache[creator_id] = links
        return links

    def _save_links(self, creator_id: str, links: List[BookingLink]):
        """Save booking links for a creator"""
        file_path = self._get_links_file(creator_id)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump([l.to_dict() for l in links], f, indent=2, ensure_ascii=False)
            self._links_cache[creator_id] = links
        except Exception as e:
            logger.error(f"Error saving links: {e}")

    def _load_bookings(self, creator_id: str) -> List[Booking]:
        """Load bookings for a creator"""
        if creator_id in self._bookings_cache:
            return self._bookings_cache[creator_id]

        file_path = self._get_bookings_file(creator_id)
        bookings = []

        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    bookings = [Booking.from_dict(b) for b in data]
            except Exception as e:
                logger.error(f"Error loading bookings: {e}")

        self._bookings_cache[creator_id] = bookings
        return bookings

    def _save_bookings(self, creator_id: str, bookings: List[Booking]):
        """Save bookings for a creator"""
        file_path = self._get_bookings_file(creator_id)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump([b.to_dict() for b in bookings], f, indent=2, ensure_ascii=False)
            self._bookings_cache[creator_id] = bookings
        except Exception as e:
            logger.error(f"Error saving bookings: {e}")

    # ==========================================================================
    # BOOKING LINKS MANAGEMENT
    # ==========================================================================

    def get_booking_link(
        self,
        creator_id: str,
        meeting_type: str
    ) -> Optional[str]:
        """
        Get booking URL for a specific meeting type.

        Args:
            creator_id: Creator ID
            meeting_type: Type of meeting (discovery, consultation, etc.)

        Returns:
            Booking URL or None
        """
        links = self._load_links(creator_id)

        for link in links:
            if link.meeting_type == meeting_type and link.is_active:
                return link.url

        # Return default link if exists
        for link in links:
            if link.meeting_type == "default" and link.is_active:
                return link.url

        return None

    def get_all_booking_links(self, creator_id: str) -> List[Dict[str, Any]]:
        """Get all booking links for a creator"""
        links = self._load_links(creator_id)
        return [l.to_dict() for l in links if l.is_active]

    def create_booking_link(
        self,
        creator_id: str,
        meeting_type: str,
        duration_minutes: int,
        title: str,
        description: str = "",
        url: str = "",
        platform: str = "manual"
    ) -> BookingLink:
        """
        Create a new booking link.

        Args:
            creator_id: Creator ID
            meeting_type: Type of meeting
            duration_minutes: Duration in minutes
            title: Link title
            description: Link description
            url: Booking URL (manual or from platform)
            platform: Calendar platform

        Returns:
            Created BookingLink
        """
        link = BookingLink(
            id=f"link_{uuid.uuid4().hex[:12]}",
            creator_id=creator_id,
            meeting_type=meeting_type,
            title=title,
            description=description,
            duration_minutes=duration_minutes,
            platform=platform,
            url=url,
            is_active=True
        )

        links = self._load_links(creator_id)
        links.append(link)
        self._save_links(creator_id, links)

        logger.info(f"Created booking link: {link.id} for {creator_id}")
        return link

    def update_booking_link(
        self,
        creator_id: str,
        link_id: str,
        updates: Dict[str, Any]
    ) -> Optional[BookingLink]:
        """Update a booking link"""
        links = self._load_links(creator_id)

        for link in links:
            if link.id == link_id:
                for key, value in updates.items():
                    if hasattr(link, key):
                        setattr(link, key, value)
                self._save_links(creator_id, links)
                return link

        return None

    def delete_booking_link(self, creator_id: str, link_id: str) -> bool:
        """Soft delete a booking link"""
        links = self._load_links(creator_id)

        for link in links:
            if link.id == link_id:
                link.is_active = False
                self._save_links(creator_id, links)
                return True

        return False

    # ==========================================================================
    # AVAILABLE SLOTS
    # ==========================================================================

    async def get_available_slots(
        self,
        creator_id: str,
        start_date: str,
        end_date: str,
        meeting_type: str = "discovery"
    ) -> List[Dict[str, Any]]:
        """
        Get available time slots from calendar platform.

        Args:
            creator_id: Creator ID
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            meeting_type: Meeting type to check availability for

        Returns:
            List of available slots
        """
        links = self._load_links(creator_id)
        link = None

        for l in links:
            if l.meeting_type == meeting_type and l.is_active:
                link = l
                break

        if not link:
            return []

        if link.platform == CalendarPlatform.CALENDLY.value:
            return await self._get_calendly_slots(link, start_date, end_date)
        elif link.platform == CalendarPlatform.CALCOM.value:
            return await self._get_calcom_slots(link, start_date, end_date)
        else:
            # Manual links don't have slot information
            return []

    async def _get_calendly_slots(
        self,
        link: BookingLink,
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        """Get available slots from Calendly"""
        if not self.calendly_api_key:
            logger.warning("Calendly API key not configured")
            return []

        try:
            # Extract event type UUID from link URL
            # URL format: https://calendly.com/username/event-type
            event_type_uri = link.metadata.get("event_type_uri", "")

            if not event_type_uri:
                return []

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.calendly_base_url}/event_type_available_times",
                    headers={
                        "Authorization": f"Bearer {self.calendly_api_key}",
                        "Content-Type": "application/json"
                    },
                    params={
                        "event_type": event_type_uri,
                        "start_time": f"{start_date}T00:00:00Z",
                        "end_time": f"{end_date}T23:59:59Z"
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    slots = []
                    for slot in data.get("collection", []):
                        slots.append({
                            "start": slot.get("start_time"),
                            "status": slot.get("status")
                        })
                    return slots

        except Exception as e:
            logger.error(f"Error getting Calendly slots: {e}")

        return []

    async def _get_calcom_slots(
        self,
        link: BookingLink,
        start_date: str,
        end_date: str
    ) -> List[Dict[str, Any]]:
        """Get available slots from Cal.com"""
        if not self.calcom_api_key:
            logger.warning("Cal.com API key not configured")
            return []

        try:
            event_type_id = link.metadata.get("event_type_id", "")

            if not event_type_id:
                return []

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.calcom_base_url}/slots",
                    headers={
                        "Authorization": f"Bearer {self.calcom_api_key}",
                        "Content-Type": "application/json"
                    },
                    params={
                        "eventTypeId": event_type_id,
                        "startTime": start_date,
                        "endTime": end_date
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get("slots", [])

        except Exception as e:
            logger.error(f"Error getting Cal.com slots: {e}")

        return []

    # ==========================================================================
    # CALENDLY WEBHOOK
    # ==========================================================================

    def verify_calendly_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Calendly webhook signature"""
        if not self.calendly_webhook_secret:
            logger.warning("Calendly webhook secret not configured")
            return True

        try:
            # Calendly uses HMAC-SHA256
            expected = hmac.new(
                self.calendly_webhook_secret.encode(),
                payload,
                hashlib.sha256
            ).hexdigest()

            # Signature format: sha256=<hash>
            if signature.startswith("sha256="):
                signature = signature[7:]

            return hmac.compare_digest(expected, signature)
        except Exception as e:
            logger.error(f"Error verifying Calendly signature: {e}")
            return False

    async def process_calendly_webhook(
        self,
        payload: dict,
        signature: str = "",
        raw_payload: bytes = None
    ) -> Dict[str, Any]:
        """
        Process Calendly webhook event.

        Supported events:
        - invitee.created
        - invitee.canceled

        Args:
            payload: Parsed JSON payload
            signature: Calendly-Webhook-Signature header
            raw_payload: Raw bytes for signature verification

        Returns:
            Processing result
        """
        # Verify signature
        if self.calendly_webhook_secret and raw_payload and signature:
            if not self.verify_calendly_signature(raw_payload, signature):
                logger.warning("Invalid Calendly webhook signature")
                return {"status": "error", "reason": "invalid_signature"}

        event_type = payload.get("event", "")
        event_data = payload.get("payload", {})

        logger.info(f"Processing Calendly event: {event_type}")

        if event_type == "invitee.created":
            return await self._handle_calendly_booking_created(event_data)
        elif event_type == "invitee.canceled":
            return await self._handle_calendly_booking_cancelled(event_data)
        else:
            logger.info(f"Ignoring Calendly event: {event_type}")
            return {"status": "ignored", "event_type": event_type}

    async def _handle_calendly_booking_created(self, data: dict) -> Dict[str, Any]:
        """Handle Calendly invitee.created event"""
        try:
            invitee = data.get("invitee", {})
            event = data.get("event", {})
            tracking = data.get("tracking", {})

            # Extract booking info
            guest_email = invitee.get("email", "")
            guest_name = invitee.get("name", "")

            scheduled_at = event.get("start_time", "")
            end_time = event.get("end_time", "")
            meeting_url = event.get("location", {}).get("join_url", "")

            external_id = invitee.get("uri", "").split("/")[-1]

            # Get creator_id from tracking UTM or default
            creator_id = tracking.get("utm_source", "") or "manel"
            follower_id = tracking.get("utm_campaign", "") or f"calendly_{guest_email}"

            # Calculate duration
            duration = 30  # default
            if scheduled_at and end_time:
                try:
                    start = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                    end = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                    duration = int((end - start).total_seconds() / 60)
                except:
                    pass

            # Get meeting type from event name
            event_name = event.get("name", "").lower()
            meeting_type = "discovery"
            if "consultation" in event_name:
                meeting_type = "consultation"
            elif "coaching" in event_name:
                meeting_type = "coaching"

            # Create booking
            booking = await self.record_booking(
                creator_id=creator_id,
                follower_id=follower_id,
                meeting_type=meeting_type,
                platform=CalendarPlatform.CALENDLY.value,
                scheduled_at=scheduled_at,
                duration_minutes=duration,
                guest_name=guest_name,
                guest_email=guest_email,
                meeting_url=meeting_url,
                external_id=external_id,
                metadata={"calendly_event": data}
            )

            logger.info(f"Calendly booking created: {booking.booking_id}")

            return {
                "status": "ok",
                "booking_id": booking.booking_id,
                "scheduled_at": scheduled_at
            }

        except Exception as e:
            logger.error(f"Error processing Calendly booking: {e}")
            return {"status": "error", "reason": str(e)}

    async def _handle_calendly_booking_cancelled(self, data: dict) -> Dict[str, Any]:
        """Handle Calendly invitee.canceled event"""
        try:
            invitee = data.get("invitee", {})
            cancellation = data.get("cancellation", {})

            external_id = invitee.get("uri", "").split("/")[-1]
            cancel_reason = cancellation.get("reason", "")

            # Find and update booking
            # We need to search all creators' bookings
            for creator_file in os.listdir(self.storage_path):
                if creator_file.endswith("_bookings.json"):
                    creator_id = creator_file.replace("_bookings.json", "")
                    bookings = self._load_bookings(creator_id)

                    for booking in bookings:
                        if booking.external_id == external_id:
                            booking.status = BookingStatus.CANCELLED.value
                            booking.cancelled_at = datetime.now(timezone.utc).isoformat()
                            booking.cancel_reason = cancel_reason
                            booking.updated_at = datetime.now(timezone.utc).isoformat()

                            self._save_bookings(creator_id, bookings)
                            logger.info(f"Calendly booking cancelled: {booking.booking_id}")

                            return {
                                "status": "ok",
                                "action": "cancelled",
                                "booking_id": booking.booking_id
                            }

            return {"status": "ok", "action": "not_found"}

        except Exception as e:
            logger.error(f"Error processing Calendly cancellation: {e}")
            return {"status": "error", "reason": str(e)}

    # ==========================================================================
    # CAL.COM WEBHOOK
    # ==========================================================================

    def verify_calcom_signature(self, payload: bytes, signature: str) -> bool:
        """Verify Cal.com webhook signature"""
        if not self.calcom_webhook_secret:
            logger.warning("Cal.com webhook secret not configured")
            return True

        try:
            expected = hmac.new(
                self.calcom_webhook_secret.encode(),
                payload,
                hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(expected, signature)
        except Exception as e:
            logger.error(f"Error verifying Cal.com signature: {e}")
            return False

    async def process_calcom_webhook(
        self,
        payload: dict,
        signature: str = "",
        raw_payload: bytes = None
    ) -> Dict[str, Any]:
        """
        Process Cal.com webhook event.

        Supported events:
        - BOOKING_CREATED
        - BOOKING_CANCELLED
        - BOOKING_RESCHEDULED

        Args:
            payload: Parsed JSON payload
            signature: X-Cal-Signature-256 header
            raw_payload: Raw bytes for signature verification

        Returns:
            Processing result
        """
        # Verify signature
        if self.calcom_webhook_secret and raw_payload and signature:
            if not self.verify_calcom_signature(raw_payload, signature):
                logger.warning("Invalid Cal.com webhook signature")
                return {"status": "error", "reason": "invalid_signature"}

        trigger_event = payload.get("triggerEvent", "")

        logger.info(f"Processing Cal.com event: {trigger_event}")

        if trigger_event == "BOOKING_CREATED":
            return await self._handle_calcom_booking_created(payload)
        elif trigger_event == "BOOKING_CANCELLED":
            return await self._handle_calcom_booking_cancelled(payload)
        elif trigger_event == "BOOKING_RESCHEDULED":
            return await self._handle_calcom_booking_rescheduled(payload)
        else:
            logger.info(f"Ignoring Cal.com event: {trigger_event}")
            return {"status": "ignored", "event_type": trigger_event}

    async def _handle_calcom_booking_created(self, payload: dict) -> Dict[str, Any]:
        """Handle Cal.com BOOKING_CREATED event"""
        try:
            booking_data = payload.get("payload", {})

            # Extract booking info
            attendees = booking_data.get("attendees", [])
            attendee = attendees[0] if attendees else {}

            guest_email = attendee.get("email", "")
            guest_name = attendee.get("name", "")

            scheduled_at = booking_data.get("startTime", "")
            end_time = booking_data.get("endTime", "")
            meeting_url = booking_data.get("metadata", {}).get("videoCallUrl", "")

            external_id = str(booking_data.get("id", ""))

            # Get creator_id from metadata or default
            metadata = booking_data.get("metadata", {})
            creator_id = metadata.get("creator_id", "") or "manel"
            follower_id = metadata.get("follower_id", "") or f"calcom_{guest_email}"

            # Calculate duration
            duration = booking_data.get("length", 30)

            # Get meeting type from event type
            event_type = booking_data.get("eventType", {})
            event_title = event_type.get("title", "").lower()
            meeting_type = "discovery"
            if "consultation" in event_title:
                meeting_type = "consultation"
            elif "coaching" in event_title:
                meeting_type = "coaching"

            # Create booking
            booking = await self.record_booking(
                creator_id=creator_id,
                follower_id=follower_id,
                meeting_type=meeting_type,
                platform=CalendarPlatform.CALCOM.value,
                scheduled_at=scheduled_at,
                duration_minutes=duration,
                guest_name=guest_name,
                guest_email=guest_email,
                meeting_url=meeting_url,
                external_id=external_id,
                metadata={"calcom_booking": booking_data}
            )

            logger.info(f"Cal.com booking created: {booking.booking_id}")

            return {
                "status": "ok",
                "booking_id": booking.booking_id,
                "scheduled_at": scheduled_at
            }

        except Exception as e:
            logger.error(f"Error processing Cal.com booking: {e}")
            return {"status": "error", "reason": str(e)}

    async def _handle_calcom_booking_cancelled(self, payload: dict) -> Dict[str, Any]:
        """Handle Cal.com BOOKING_CANCELLED event"""
        try:
            booking_data = payload.get("payload", {})
            external_id = str(booking_data.get("id", ""))
            cancel_reason = booking_data.get("cancellationReason", "")

            # Find and update booking
            for creator_file in os.listdir(self.storage_path):
                if creator_file.endswith("_bookings.json"):
                    creator_id = creator_file.replace("_bookings.json", "")
                    bookings = self._load_bookings(creator_id)

                    for booking in bookings:
                        if booking.external_id == external_id:
                            booking.status = BookingStatus.CANCELLED.value
                            booking.cancelled_at = datetime.now(timezone.utc).isoformat()
                            booking.cancel_reason = cancel_reason
                            booking.updated_at = datetime.now(timezone.utc).isoformat()

                            self._save_bookings(creator_id, bookings)
                            logger.info(f"Cal.com booking cancelled: {booking.booking_id}")

                            return {
                                "status": "ok",
                                "action": "cancelled",
                                "booking_id": booking.booking_id
                            }

            return {"status": "ok", "action": "not_found"}

        except Exception as e:
            logger.error(f"Error processing Cal.com cancellation: {e}")
            return {"status": "error", "reason": str(e)}

    async def _handle_calcom_booking_rescheduled(self, payload: dict) -> Dict[str, Any]:
        """Handle Cal.com BOOKING_RESCHEDULED event"""
        try:
            booking_data = payload.get("payload", {})
            external_id = str(booking_data.get("id", ""))
            new_start = booking_data.get("startTime", "")

            # Find and update booking
            for creator_file in os.listdir(self.storage_path):
                if creator_file.endswith("_bookings.json"):
                    creator_id = creator_file.replace("_bookings.json", "")
                    bookings = self._load_bookings(creator_id)

                    for booking in bookings:
                        if booking.external_id == external_id:
                            booking.status = BookingStatus.RESCHEDULED.value
                            booking.scheduled_at = new_start
                            booking.updated_at = datetime.now(timezone.utc).isoformat()

                            self._save_bookings(creator_id, bookings)
                            logger.info(f"Cal.com booking rescheduled: {booking.booking_id}")

                            return {
                                "status": "ok",
                                "action": "rescheduled",
                                "booking_id": booking.booking_id,
                                "new_time": new_start
                            }

            return {"status": "ok", "action": "not_found"}

        except Exception as e:
            logger.error(f"Error processing Cal.com reschedule: {e}")
            return {"status": "error", "reason": str(e)}

    # ==========================================================================
    # BOOKING MANAGEMENT
    # ==========================================================================

    async def record_booking(
        self,
        creator_id: str,
        follower_id: str,
        meeting_type: str,
        platform: str,
        scheduled_at: str,
        duration_minutes: int,
        guest_name: str = "",
        guest_email: str = "",
        guest_phone: str = "",
        meeting_url: str = "",
        external_id: str = "",
        notes: str = "",
        metadata: Dict[str, Any] = None
    ) -> Booking:
        """
        Record a new booking.

        Args:
            creator_id: Creator ID
            follower_id: Follower ID
            meeting_type: Type of meeting
            platform: Calendar platform
            scheduled_at: Scheduled datetime (ISO format)
            duration_minutes: Duration in minutes
            guest_name: Guest name
            guest_email: Guest email
            guest_phone: Guest phone
            meeting_url: Video call URL
            external_id: External booking ID
            notes: Booking notes
            metadata: Additional data

        Returns:
            Created Booking
        """
        booking = Booking(
            booking_id=f"book_{uuid.uuid4().hex[:12]}",
            creator_id=creator_id,
            follower_id=follower_id,
            meeting_type=meeting_type,
            platform=platform,
            status=BookingStatus.SCHEDULED.value,
            scheduled_at=scheduled_at,
            duration_minutes=duration_minutes,
            guest_name=guest_name,
            guest_email=guest_email,
            guest_phone=guest_phone,
            meeting_url=meeting_url,
            external_id=external_id,
            notes=notes,
            metadata=metadata or {}
        )

        # Save booking
        bookings = self._load_bookings(creator_id)
        bookings.append(booking)
        self._save_bookings(creator_id, bookings)

        # Update follower memory
        await self._update_follower_booking(creator_id, follower_id, scheduled_at)

        logger.info(f"Booking recorded: {booking.booking_id} for {scheduled_at}")
        return booking

    async def _update_follower_booking(
        self,
        creator_id: str,
        follower_id: str,
        scheduled_at: str
    ):
        """Update follower memory with booking info"""
        try:
            safe_id = follower_id.replace("/", "_").replace("\\", "_")
            file_path = f"data/followers/{creator_id}/{safe_id}.json"

            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                data["has_booking"] = True
                data["next_booking"] = scheduled_at
                data["booking_count"] = data.get("booking_count", 0) + 1

                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                logger.info(f"Follower {follower_id} booking updated")

        except Exception as e:
            logger.error(f"Error updating follower booking: {e}")

    # ==========================================================================
    # BOOKING QUERIES
    # ==========================================================================

    def get_bookings(
        self,
        creator_id: str,
        status: str = None,
        upcoming_only: bool = False,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get bookings for a creator.

        Args:
            creator_id: Creator ID
            status: Filter by status
            upcoming_only: Only return future bookings
            limit: Maximum results

        Returns:
            List of bookings
        """
        bookings = self._load_bookings(creator_id)

        # Filter by status
        if status:
            bookings = [b for b in bookings if b.status == status]

        # Filter upcoming
        if upcoming_only:
            now = datetime.now(timezone.utc).isoformat()
            bookings = [b for b in bookings if b.scheduled_at >= now]

        # Sort by scheduled time
        bookings.sort(key=lambda x: x.scheduled_at, reverse=True)

        return [b.to_dict() for b in bookings[:limit]]

    def get_follower_bookings(
        self,
        creator_id: str,
        follower_id: str
    ) -> List[Dict[str, Any]]:
        """Get all bookings for a specific follower"""
        bookings = self._load_bookings(creator_id)
        follower_bookings = [b for b in bookings if b.follower_id == follower_id]
        follower_bookings.sort(key=lambda x: x.scheduled_at, reverse=True)
        return [b.to_dict() for b in follower_bookings]

    def get_booking_stats(self, creator_id: str, days: int = 30) -> Dict[str, Any]:
        """Get booking statistics"""
        bookings = self._load_bookings(creator_id)

        # Filter by date
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        recent = [b for b in bookings if b.created_at >= cutoff]

        total = len(recent)
        scheduled = len([b for b in recent if b.status == BookingStatus.SCHEDULED.value])
        completed = len([b for b in recent if b.status == BookingStatus.COMPLETED.value])
        cancelled = len([b for b in recent if b.status == BookingStatus.CANCELLED.value])
        no_show = len([b for b in recent if b.status == BookingStatus.NO_SHOW.value])

        by_type = {}
        for b in recent:
            by_type[b.meeting_type] = by_type.get(b.meeting_type, 0) + 1

        by_platform = {}
        for b in recent:
            by_platform[b.platform] = by_platform.get(b.platform, 0) + 1

        return {
            "period_days": days,
            "total_bookings": total,
            "scheduled": scheduled,
            "completed": completed,
            "cancelled": cancelled,
            "no_show": no_show,
            "show_rate": (completed / (completed + no_show)) if (completed + no_show) > 0 else 0,
            "cancel_rate": (cancelled / total) if total > 0 else 0,
            "by_type": by_type,
            "by_platform": by_platform
        }

    def mark_booking_completed(self, creator_id: str, booking_id: str) -> bool:
        """Mark a booking as completed"""
        bookings = self._load_bookings(creator_id)

        for booking in bookings:
            if booking.booking_id == booking_id:
                booking.status = BookingStatus.COMPLETED.value
                booking.updated_at = datetime.now(timezone.utc).isoformat()
                self._save_bookings(creator_id, bookings)
                return True

        return False

    def mark_booking_no_show(self, creator_id: str, booking_id: str) -> bool:
        """Mark a booking as no-show"""
        bookings = self._load_bookings(creator_id)

        for booking in bookings:
            if booking.booking_id == booking_id:
                booking.status = BookingStatus.NO_SHOW.value
                booking.updated_at = datetime.now(timezone.utc).isoformat()
                self._save_bookings(creator_id, bookings)
                return True

        return False


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_calendar_manager: Optional[CalendarManager] = None


def get_calendar_manager() -> CalendarManager:
    """Get or create calendar manager singleton"""
    global _calendar_manager
    if _calendar_manager is None:
        _calendar_manager = CalendarManager()
    return _calendar_manager
