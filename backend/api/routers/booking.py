"""Internal booking system endpoints - replaces Calendly dependency"""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, date, time, timedelta, timezone
import logging
import uuid
import httpx

try:
    from api.database import get_db
    from api.models import BookingLink, CalendarBooking, CreatorAvailability, BookingSlot, Creator
except:
    from database import get_db
    from models import BookingLink, CalendarBooking, CreatorAvailability, BookingSlot, Creator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/booking", tags=["booking"])


# =============================================================================
# AVAILABILITY ENDPOINTS
# =============================================================================

@router.get("/availability/{creator_id}")
async def get_availability(creator_id: str, db: Session = Depends(get_db)):
    """Get creator's weekly availability schedule"""
    try:
        availability = db.query(CreatorAvailability).filter(
            CreatorAvailability.creator_id == creator_id
        ).order_by(CreatorAvailability.day_of_week).all()

        # Format response
        days = []
        for av in availability:
            days.append({
                "id": str(av.id),
                "day_of_week": av.day_of_week,
                "day_name": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][av.day_of_week],
                "start_time": av.start_time.strftime("%H:%M") if av.start_time else None,
                "end_time": av.end_time.strftime("%H:%M") if av.end_time else None,
                "is_active": av.is_active
            })

        # If no availability set, return default (empty)
        if not days:
            # Return default structure with all days inactive
            days = [
                {"day_of_week": i, "day_name": name, "start_time": "09:00", "end_time": "17:00", "is_active": False}
                for i, name in enumerate(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])
            ]

        return {
            "status": "ok",
            "creator_id": creator_id,
            "availability": days
        }
    except Exception as e:
        logger.error(f"Error getting availability: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/availability/{creator_id}")
async def set_availability(creator_id: str, data: list = Body(...), db: Session = Depends(get_db)):
    """
    Set creator's weekly availability.
    Body: [{ day_of_week: 0, start_time: "09:00", end_time: "17:00", is_active: true }, ...]
    """
    try:
        # Delete existing availability for this creator
        db.query(CreatorAvailability).filter(
            CreatorAvailability.creator_id == creator_id
        ).delete()

        # Create new availability records
        for day_data in data:
            day_of_week = day_data.get("day_of_week")
            if day_of_week is None or day_of_week < 0 or day_of_week > 6:
                continue

            start_str = day_data.get("start_time", "09:00")
            end_str = day_data.get("end_time", "17:00")

            # Parse time strings
            start_time = datetime.strptime(start_str, "%H:%M").time()
            end_time = datetime.strptime(end_str, "%H:%M").time()

            availability = CreatorAvailability(
                id=uuid.uuid4(),
                creator_id=creator_id,
                day_of_week=day_of_week,
                start_time=start_time,
                end_time=end_time,
                is_active=day_data.get("is_active", True)
            )
            db.add(availability)

        db.commit()

        return {
            "status": "ok",
            "message": "Availability updated successfully",
            "days_set": len(data)
        }
    except Exception as e:
        logger.error(f"Error setting availability: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# SLOT ENDPOINTS
# =============================================================================

@router.get("/{creator_id}/slots")
async def get_available_slots(
    creator_id: str,
    date_str: str,  # Format: YYYY-MM-DD
    service_id: str,
    db: Session = Depends(get_db)
):
    """
    Get available slots for a specific date and service.
    Calculates slots based on creator's availability and service duration.
    Excludes already booked slots.
    """
    try:
        # Parse date
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        # Get today's date in UTC for consistency
        today = datetime.now(timezone.utc).date()
        logger.info(f"Slots request: date_str={date_str}, target_date={target_date}, server_today={today}")

        # Don't allow past dates
        if target_date < today:
            return {
                "status": "ok",
                "date": date_str,
                "slots": [],
                "message": f"Cannot book past dates (requested: {target_date}, server today: {today})"
            }

        # Get service info
        try:
            service_uuid = uuid.UUID(service_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid service_id format")

        service = db.query(BookingLink).filter(
            BookingLink.id == service_uuid,
            BookingLink.creator_id == creator_id,
            BookingLink.is_active == True
        ).first()

        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        duration_minutes = service.duration_minutes or 30

        # Get day of week (Python: 0=Monday)
        day_of_week = target_date.weekday()

        # Get creator's availability for this day
        availability = db.query(CreatorAvailability).filter(
            CreatorAvailability.creator_id == creator_id,
            CreatorAvailability.day_of_week == day_of_week,
            CreatorAvailability.is_active == True
        ).first()

        if not availability:
            return {
                "status": "ok",
                "date": date_str,
                "day_of_week": day_of_week,
                "slots": [],
                "message": "No availability for this day"
            }

        # Get already booked slots for this date
        booked_slots = db.query(BookingSlot).filter(
            BookingSlot.creator_id == creator_id,
            BookingSlot.date == target_date,
            BookingSlot.status == "booked"
        ).all()

        booked_times = set()
        for slot in booked_slots:
            booked_times.add(slot.start_time.strftime("%H:%M"))

        # Also check CalendarBooking for external bookings (Calendly, etc.)
        external_bookings = db.query(CalendarBooking).filter(
            CalendarBooking.creator_id == creator_id,
            CalendarBooking.status == "scheduled"
        ).all()

        for booking in external_bookings:
            if booking.scheduled_at and booking.scheduled_at.date() == target_date:
                booked_times.add(booking.scheduled_at.strftime("%H:%M"))

        # Generate available slots
        slots = []
        current_time = datetime.combine(target_date, availability.start_time)
        end_datetime = datetime.combine(target_date, availability.end_time)

        # If it's today, start from current time (rounded up to next slot)
        if target_date == today:
            now = datetime.now(timezone.utc)
            # Add 30 min buffer - use replace to get naive datetime for comparison
            min_start_naive = (now + timedelta(minutes=30)).replace(tzinfo=None)
            if current_time < min_start_naive:
                # Round up to next slot
                minutes = min_start_naive.minute
                if minutes % 15 != 0:
                    minutes = ((minutes // 15) + 1) * 15
                    if minutes >= 60:
                        min_start_naive = min_start_naive.replace(hour=min_start_naive.hour + 1, minute=0)
                    else:
                        min_start_naive = min_start_naive.replace(minute=minutes)
                current_time = min_start_naive

        slot_duration = timedelta(minutes=duration_minutes)

        while current_time + slot_duration <= end_datetime:
            time_str = current_time.strftime("%H:%M")
            end_time_str = (current_time + slot_duration).strftime("%H:%M")

            if time_str not in booked_times:
                slots.append({
                    "start_time": time_str,
                    "end_time": end_time_str,
                    "available": True
                })

            # Move to next slot (use service duration as step)
            current_time += slot_duration

        return {
            "status": "ok",
            "date": date_str,
            "day_of_week": day_of_week,
            "service": {
                "id": str(service.id),
                "title": service.title,
                "duration_minutes": duration_minutes
            },
            "slots": slots,
            "total_available": len(slots)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting slots: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{creator_id}/reserve")
async def reserve_slot(creator_id: str, data: dict = Body(...), db: Session = Depends(get_db)):
    """
    Reserve a booking slot.
    Body: {
        service_id: string,
        date: "YYYY-MM-DD",
        start_time: "HH:MM",
        name: string,
        email: string,
        phone: string (optional)
    }
    """
    try:
        # Validate required fields
        service_id = data.get("service_id")
        date_str = data.get("date")
        start_time_str = data.get("start_time")
        name = data.get("name")
        email = data.get("email")
        phone = data.get("phone", "")

        if not all([service_id, date_str, start_time_str, name, email]):
            raise HTTPException(status_code=400, detail="Missing required fields: service_id, date, start_time, name, email")

        # Parse date and time
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_time = datetime.strptime(start_time_str, "%H:%M").time()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date or time format")

        # Get service
        try:
            service_uuid = uuid.UUID(service_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid service_id format")

        service = db.query(BookingLink).filter(
            BookingLink.id == service_uuid,
            BookingLink.creator_id == creator_id,
            BookingLink.is_active == True
        ).first()

        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        duration_minutes = service.duration_minutes or 30
        end_time = (datetime.combine(target_date, start_time) + timedelta(minutes=duration_minutes)).time()

        # Check if slot is still available
        existing_slot = db.query(BookingSlot).filter(
            BookingSlot.creator_id == creator_id,
            BookingSlot.date == target_date,
            BookingSlot.start_time == start_time,
            BookingSlot.status == "booked"
        ).first()

        if existing_slot:
            raise HTTPException(status_code=409, detail="This slot is no longer available")

        # Check external bookings too
        scheduled_datetime = datetime.combine(target_date, start_time).replace(tzinfo=timezone.utc)
        external_conflict = db.query(CalendarBooking).filter(
            CalendarBooking.creator_id == creator_id,
            CalendarBooking.scheduled_at == scheduled_datetime,
            CalendarBooking.status == "scheduled"
        ).first()

        if external_conflict:
            raise HTTPException(status_code=409, detail="This slot is no longer available")

        # Generate Google Meet URL if Google is connected
        meeting_url = ""
        try:
            creator = db.query(Creator).filter(Creator.name == creator_id).first()
            logger.info(f"Creator {creator_id} found: {bool(creator)}")
            if creator:
                logger.info(f"Creator has google_refresh_token: {bool(creator.google_refresh_token)}")
                logger.info(f"Creator has google_access_token: {bool(creator.google_access_token)}")

            # Check for refresh_token - access_token will be refreshed if needed
            if creator and creator.google_refresh_token:
                logger.info(f"Creating Google Calendar event for booking...")
                try:
                    from api.routers.oauth import create_google_meet_event
                except:
                    from routers.oauth import create_google_meet_event

                # Calculate end time for the event (timedelta already imported at top of file)
                scheduled_datetime = datetime.combine(target_date, start_time).replace(tzinfo=timezone.utc)
                end_datetime = scheduled_datetime + timedelta(minutes=duration_minutes)

                logger.info(f"Calling create_google_meet_event: {service.title}, {scheduled_datetime} - {end_datetime}")
                result = await create_google_meet_event(
                    creator_id=creator_id,
                    title=service.title or "Meeting",
                    start_time=scheduled_datetime,
                    end_time=end_datetime,
                    guest_email=email,
                    guest_name=name,
                    description=f"Booking: {service.title}"
                )
                logger.info(f"Google Meet event result: {result}")
                if result.get("meet_link"):
                    meeting_url = result.get("meet_link", "")
                    logger.info(f"Created Google Meet link for booking: {meeting_url}")
            else:
                logger.info(f"Skipping Google Calendar - no refresh token for creator {creator_id}")
        except Exception as e:
            logger.error(f"Could not create Google Meet event: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")

        # Generate IDs upfront
        slot_id = uuid.uuid4()
        calendar_booking_id = uuid.uuid4()

        # FIRST: Create and save CalendarBooking (must exist before BookingSlot references it)
        calendar_booking = CalendarBooking(
            id=calendar_booking_id,
            creator_id=creator_id,
            follower_id=email,
            meeting_type=service.title or service.meeting_type,
            platform="clonnect",  # Internal booking
            status="scheduled",
            scheduled_at=scheduled_datetime,
            duration_minutes=duration_minutes,
            guest_name=name,
            guest_email=email,
            guest_phone=phone,
            meeting_url=meeting_url,
            external_id=str(slot_id),  # Link to BookingSlot
            extra_data={"source": "internal_booking", "service_id": str(service_uuid)}
        )
        db.add(calendar_booking)
        db.flush()  # Ensure CalendarBooking is inserted before BookingSlot

        # THEN: Create BookingSlot with reference to CalendarBooking
        slot = BookingSlot(
            id=slot_id,
            creator_id=creator_id,
            service_id=service_uuid,
            date=target_date,
            start_time=start_time,
            end_time=end_time,
            status="booked",
            booked_by_name=name,
            booked_by_email=email,
            booked_by_phone=phone,
            meeting_url=meeting_url,
            calendar_booking_id=calendar_booking_id
        )
        db.add(slot)

        db.commit()

        return {
            "status": "ok",
            "message": "Booking confirmed!",
            "booking": {
                "id": str(slot.id),
                "calendar_booking_id": str(calendar_booking.id),
                "service": service.title,
                "date": date_str,
                "start_time": start_time_str,
                "end_time": end_time.strftime("%H:%M"),
                "duration_minutes": duration_minutes,
                "guest_name": name,
                "guest_email": email,
                "meeting_url": meeting_url or "Link will be sent before the call"
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reserving slot: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# PUBLIC ENDPOINTS (for booking page)
# =============================================================================

@router.get("/{creator_id}/public/{service_id}")
async def get_public_service_info(creator_id: str, service_id: str, db: Session = Depends(get_db)):
    """
    Get public information about a service for the booking page.
    No authentication required.
    """
    try:
        # Get service
        try:
            service_uuid = uuid.UUID(service_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid service_id format")

        service = db.query(BookingLink).filter(
            BookingLink.id == service_uuid,
            BookingLink.creator_id == creator_id,
            BookingLink.is_active == True
        ).first()

        if not service:
            raise HTTPException(status_code=404, detail="Service not found")

        # Get creator info
        creator = db.query(Creator).filter(Creator.name == creator_id).first()
        creator_name = creator.clone_name if creator else creator_id

        return {
            "status": "ok",
            "service": {
                "id": str(service.id),
                "title": service.title,
                "description": service.description or "",
                "duration_minutes": service.duration_minutes or 30,
                "price": service.price or 0,
                "platform": service.platform
            },
            "creator": {
                "id": creator_id,
                "name": creator_name
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting public service info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{creator_id}/public/{service_id}/available-dates")
async def get_available_dates(
    creator_id: str,
    service_id: str,
    month: int = None,  # 1-12
    year: int = None,
    db: Session = Depends(get_db)
):
    """
    Get dates with availability for the next 30 days (or specified month).
    Used for calendar display on booking page.
    """
    try:
        # Default to current month if not specified - use UTC for consistency
        today = datetime.now(timezone.utc).date()
        if not month:
            month = today.month
        if not year:
            year = today.year

        # Get creator's availability
        availability = db.query(CreatorAvailability).filter(
            CreatorAvailability.creator_id == creator_id,
            CreatorAvailability.is_active == True
        ).all()

        if not availability:
            return {
                "status": "ok",
                "available_dates": [],
                "message": "No availability set"
            }

        active_days = {av.day_of_week for av in availability}

        # Generate dates for the month
        available_dates = []
        current_date = date(year, month, 1)

        # Go through the month
        while current_date.month == month:
            # Only include future dates and active days
            if current_date >= today and current_date.weekday() in active_days:
                available_dates.append(current_date.isoformat())
            current_date += timedelta(days=1)

        return {
            "status": "ok",
            "month": month,
            "year": year,
            "available_dates": available_dates,
            "active_days_of_week": list(active_days)
        }

    except Exception as e:
        logger.error(f"Error getting available dates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{creator_id}/cancel/{booking_id}")
async def cancel_booking(creator_id: str, booking_id: str, db: Session = Depends(get_db)):
    """Cancel a booking"""
    try:
        try:
            booking_uuid = uuid.UUID(booking_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid booking_id format")

        # Find in BookingSlot
        slot = db.query(BookingSlot).filter(
            BookingSlot.id == booking_uuid,
            BookingSlot.creator_id == creator_id
        ).first()

        if slot:
            slot.status = "cancelled"
            # Also update CalendarBooking
            if slot.calendar_booking_id:
                calendar_booking = db.query(CalendarBooking).filter(
                    CalendarBooking.id == slot.calendar_booking_id
                ).first()
                if calendar_booking:
                    calendar_booking.status = "cancelled"
                    calendar_booking.cancelled_at = datetime.now(timezone.utc)

            db.commit()
            return {"status": "ok", "message": "Booking cancelled"}

        # Try finding by CalendarBooking ID
        calendar_booking = db.query(CalendarBooking).filter(
            CalendarBooking.id == booking_uuid,
            CalendarBooking.creator_id == creator_id
        ).first()

        if calendar_booking:
            calendar_booking.status = "cancelled"
            calendar_booking.cancelled_at = datetime.now(timezone.utc)
            db.commit()
            return {"status": "ok", "message": "Booking cancelled"}

        raise HTTPException(status_code=404, detail="Booking not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling booking: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
