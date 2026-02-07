"""Audit tests for api/routers/booking.py."""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# 1. Init / Import
# ---------------------------------------------------------------------------
class TestBookingRouterImport:
    """Verify that the booking router can be imported."""

    def test_router_imports_successfully(self):
        """Router object and prefix should be correct."""
        from api.routers.booking import router

        assert router is not None
        assert router.prefix == "/booking"
        assert "booking" in router.tags

    def test_router_has_expected_routes(self):
        """Router should expose availability, slots, reserve, and cancel routes."""
        from api.routers.booking import router

        route_paths = [route.path for route in router.routes]

        # Paths include the router prefix
        assert "/booking/availability/{creator_id}" in route_paths
        assert "/booking/{creator_id}/slots" in route_paths
        assert "/booking/{creator_id}/reserve" in route_paths
        assert "/booking/{creator_id}/cancel/{booking_id}" in route_paths


# ---------------------------------------------------------------------------
# 2. Happy Path -- Booking creation (mocked DB)
# ---------------------------------------------------------------------------
class TestBookingCreationMock:
    """Test the reserve_slot endpoint with a fully mocked DB session."""

    @pytest.mark.asyncio
    async def test_reserve_slot_success(self):
        """reserve_slot should create slot + calendar booking and return confirmation."""
        from api.routers.booking import (
            BookingLink,
            BookingSlot,
            CalendarBooking,
            Creator,
            reserve_slot,
        )

        service_uuid = uuid.uuid4()
        mock_db = MagicMock()

        # Mock service (BookingLink)
        mock_service = MagicMock()
        mock_service.id = service_uuid
        mock_service.title = "Discovery Call"
        mock_service.duration_minutes = 30
        mock_service.meeting_type = "discovery"

        # Build a query mock that returns the right thing depending on the model
        def query_side_effect(model):
            q = MagicMock()
            if model is BookingLink:
                q.filter.return_value.first.return_value = mock_service
            elif model is BookingSlot:
                q.filter.return_value.first.return_value = None  # no existing slot
            elif model is CalendarBooking:
                q.filter.return_value.first.return_value = None  # no conflict
            elif model is Creator:
                # Creator without Google tokens
                mock_creator = MagicMock()
                mock_creator.google_refresh_token = None
                mock_creator.google_access_token = None
                q.filter.return_value.first.return_value = mock_creator
            else:
                q.filter.return_value.first.return_value = None
            return q

        mock_db.query.side_effect = query_side_effect

        data = {
            "service_id": str(service_uuid),
            "date": "2026-06-15",
            "start_time": "10:00",
            "name": "John Doe",
            "email": "john@example.com",
            "phone": "+1234567890",
        }

        result = await reserve_slot("test_creator", data, mock_db)
        assert result["status"] == "ok"
        assert result["message"] == "Booking confirmed!"
        assert result["booking"]["guest_name"] == "John Doe"
        assert result["booking"]["guest_email"] == "john@example.com"
        assert mock_db.add.called
        assert mock_db.commit.called


# ---------------------------------------------------------------------------
# 3. Edge Case -- Time slot validation
# ---------------------------------------------------------------------------
class TestTimeSlotValidation:
    """Test slot validation for past dates and invalid formats."""

    @pytest.mark.asyncio
    async def test_get_slots_returns_empty_for_past_date(self):
        """Requesting slots for a past date should return empty list."""
        from api.routers.booking import get_available_slots

        mock_db = MagicMock()
        service_uuid = uuid.uuid4()

        # Mock service query
        mock_service = MagicMock()
        mock_service.id = service_uuid
        mock_service.duration_minutes = 30
        mock_service.title = "Call"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_service

        # Use a definitely past date
        result = await get_available_slots("test_creator", "2020-01-01", str(service_uuid), mock_db)

        assert result["status"] == "ok"
        assert result["slots"] == []
        assert "past" in result.get("message", "").lower() or len(result["slots"]) == 0

    @pytest.mark.asyncio
    async def test_get_slots_invalid_date_format(self):
        """Invalid date format should return 400."""
        from api.routers.booking import get_available_slots

        mock_db = MagicMock()
        service_uuid = uuid.uuid4()

        mock_service = MagicMock()
        mock_service.id = service_uuid
        mock_service.duration_minutes = 30
        mock_db.query.return_value.filter.return_value.first.return_value = mock_service

        with pytest.raises(HTTPException) as exc_info:
            await get_available_slots("test_creator", "not-a-date", str(service_uuid), mock_db)

        assert exc_info.value.status_code == 400
        assert "Invalid date" in exc_info.value.detail


# ---------------------------------------------------------------------------
# 4. Error Handling -- Cancellation
# ---------------------------------------------------------------------------
class TestCancellationHandling:
    """Test the cancel_booking endpoint."""

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_booking_returns_404(self):
        """Cancelling a booking that does not exist should return 404."""
        from api.routers.booking import cancel_booking

        mock_db = MagicMock()
        # Neither BookingSlot nor CalendarBooking found
        mock_db.query.return_value.filter.return_value.first.return_value = None

        booking_id = str(uuid.uuid4())
        with pytest.raises(HTTPException) as exc_info:
            await cancel_booking("test_creator", booking_id, mock_db)

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_cancel_invalid_uuid_returns_400(self):
        """Cancelling with an invalid UUID format should return 400."""
        from api.routers.booking import cancel_booking

        mock_db = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await cancel_booking("test_creator", "not-a-uuid", mock_db)

        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# 5. Integration Check -- Duplicate booking prevention
# ---------------------------------------------------------------------------
class TestDuplicateBookingCheck:
    """Verify that reserve_slot rejects double-bookings (409 Conflict)."""

    @pytest.mark.asyncio
    async def test_reserve_slot_rejects_duplicate(self):
        """If slot is already booked, reserve_slot should raise 409."""
        from api.routers.booking import BookingLink, BookingSlot, reserve_slot

        service_uuid = uuid.uuid4()
        mock_db = MagicMock()

        # Mock service
        mock_service = MagicMock()
        mock_service.id = service_uuid
        mock_service.title = "Call"
        mock_service.duration_minutes = 30

        # existing_slot is found (already booked)
        existing_slot = MagicMock()
        existing_slot.status = "booked"

        def query_side_effect(model):
            q = MagicMock()
            if model is BookingLink:
                q.filter.return_value.first.return_value = mock_service
            elif model is BookingSlot:
                q.filter.return_value.first.return_value = existing_slot
            else:
                q.filter.return_value.first.return_value = None
            return q

        mock_db.query.side_effect = query_side_effect

        data = {
            "service_id": str(service_uuid),
            "date": "2026-06-15",
            "start_time": "10:00",
            "name": "Jane",
            "email": "jane@example.com",
        }

        with pytest.raises(HTTPException) as exc_info:
            await reserve_slot("test_creator", data, mock_db)

        assert exc_info.value.status_code == 409
        assert "no longer available" in exc_info.value.detail.lower()
