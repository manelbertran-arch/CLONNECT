"""Calendar and bookings endpoints"""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import logging
import uuid
import httpx

try:
    from api.database import get_db
    from api.models import BookingLink, CalendarBooking, Creator, BookingSlot
except:
    from database import get_db
    from models import BookingLink, CalendarBooking, Creator, BookingSlot

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/calendar", tags=["calendar"])

@router.get("/{creator_id}/bookings")
async def get_bookings(creator_id: str, upcoming: bool = True, db: Session = Depends(get_db)):
    """Get all bookings for a creator."""
    try:
        # Update status of past bookings
        now = datetime.now(timezone.utc)
        past_scheduled = db.query(CalendarBooking).filter(
            CalendarBooking.creator_id == creator_id,
            CalendarBooking.status == "scheduled",
            CalendarBooking.scheduled_at < now
        ).all()
        for booking in past_scheduled:
            booking.status = "completed"
        if past_scheduled:
            db.commit()
            logger.info(f"Marked {len(past_scheduled)} past bookings as completed for {creator_id}")

        # Get all bookings
        bookings = db.query(CalendarBooking).filter(
            CalendarBooking.creator_id == creator_id
        ).order_by(CalendarBooking.scheduled_at.desc()).all()

        return {
            "status": "ok",
            "creator_id": creator_id,
            "bookings": [
                {
                    "id": str(b.id),
                    "meeting_type": b.meeting_type,
                    "title": b.meeting_type,  # Alias for frontend
                    "platform": b.platform,
                    "status": b.status,
                    "scheduled_at": b.scheduled_at.isoformat() if b.scheduled_at else None,
                    "duration_minutes": b.duration_minutes,
                    "guest_name": b.guest_name,
                    "guest_email": b.guest_email,
                    "meeting_url": b.meeting_url or "",
                    "follower_name": b.guest_name,  # Alias for frontend
                }
                for b in bookings
            ],
            "count": len(bookings)
        }
    except Exception as e:
        logger.error(f"Error getting bookings: {e}")
        return {"status": "ok", "creator_id": creator_id, "bookings": [], "count": 0}

@router.get("/{creator_id}/stats")
async def get_calendar_stats(creator_id: str, days: int = 30, db: Session = Depends(get_db)):
    """Get calendar statistics for a creator"""
    try:
        bookings = db.query(CalendarBooking).filter(
            CalendarBooking.creator_id == creator_id
        ).all()

        completed = sum(1 for b in bookings if b.status == "completed")
        cancelled = sum(1 for b in bookings if b.status == "cancelled")
        no_show = sum(1 for b in bookings if b.status == "no_show")
        upcoming = sum(1 for b in bookings if b.status == "scheduled")
        total = len(bookings)

        return {
            "status": "ok",
            "creator_id": creator_id,
            "total_bookings": total,
            "completed": completed,
            "cancelled": cancelled,
            "no_show": no_show,
            "show_rate": (completed / total * 100) if total > 0 else 0.0,
            "upcoming": upcoming,
            "by_type": {},
            "by_platform": {}
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return {"status": "ok", "creator_id": creator_id, "total_bookings": 0, "completed": 0, "cancelled": 0, "no_show": 0, "show_rate": 0.0, "upcoming": 0, "by_type": {}, "by_platform": {}}

@router.get("/{creator_id}/links")
async def get_booking_links(creator_id: str, db: Session = Depends(get_db)):
    """Get all booking links for a creator from PostgreSQL"""
    try:
        links = db.query(BookingLink).filter(
            BookingLink.creator_id == creator_id
        ).all()

        logger.info(f"GET /calendar/{creator_id}/links - Found {len(links)} links")

        return {
            "status": "ok",
            "creator_id": creator_id,
            "links": [
                {
                    "id": str(link.id),
                    "meeting_type": link.meeting_type,
                    "title": link.title,
                    "description": link.description,
                    "duration_minutes": link.duration_minutes,
                    "platform": link.platform,
                    "url": link.url,
                    "price": getattr(link, 'price', 0) or 0,
                    "is_active": link.is_active,
                    "created_at": link.created_at.isoformat() if link.created_at else None,
                }
                for link in links
            ],
            "count": len(links)
        }
    except Exception as e:
        logger.error(f"Error getting booking links: {e}")
        return {"status": "ok", "creator_id": creator_id, "links": [], "count": 0}

MAX_BOOKING_LINKS = 5


@router.post("/{creator_id}/links")
async def create_booking_link(creator_id: str, data: dict = Body(...), db: Session = Depends(get_db)):
    """
    Create a new booking link in PostgreSQL.
    Supports Google Meet (auto-creates links) and manual platforms.
    """
    try:
        # Check limit of booking links per creator
        existing_count = db.query(BookingLink).filter(
            BookingLink.creator_id == creator_id
        ).count()
        if existing_count >= MAX_BOOKING_LINKS:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum {MAX_BOOKING_LINKS} booking links allowed per creator"
            )

        platform = data.get("platform", "clonnect")  # Default to internal Clonnect system
        url = data.get("url", "")
        auto_create_error = None

        # For google-meet platform, we don't pre-create links
        # Meet links are generated when a booking is confirmed
        if platform == "google-meet":
            # Verify Google is connected
            try:
                from api.routers.oauth import get_valid_google_token
            except:
                from routers.oauth import get_valid_google_token

            try:
                await get_valid_google_token(creator_id)
                logger.info(f"Google connected for {creator_id} - Meet links will be generated on booking")
            except Exception as e:
                auto_create_error = f"Google not connected: {e}"
                logger.warning(f"Google Meet service created but Google not connected: {e}")

        # Create new BookingLink
        new_link = BookingLink(
            id=uuid.uuid4(),
            creator_id=creator_id,
            meeting_type=data.get("meeting_type", "custom"),
            title=data.get("title", "Booking"),
            description=data.get("description"),
            duration_minutes=data.get("duration_minutes", 30),
            platform=platform,
            url=url,  # May be empty for google-meet (generated on booking)
            price=data.get("price", 0),
            is_active=data.get("is_active", True),
            extra_data=data.get("extra_data", {})
        )

        db.add(new_link)
        db.commit()
        db.refresh(new_link)

        logger.info(f"POST /calendar/{creator_id}/links - Created link {new_link.id}")

        platform_names = {"google-meet": "Google Meet", "clonnect": "Clonnect"}
        platform_name = platform_names.get(platform, platform)

        response = {
            "status": "ok",
            "message": f"Service created ({platform_name})",
            "link": {
                "id": str(new_link.id),
                "creator_id": new_link.creator_id,
                "meeting_type": new_link.meeting_type,
                "title": new_link.title,
                "description": new_link.description,
                "duration_minutes": new_link.duration_minutes,
                "platform": new_link.platform,
                "url": new_link.url,
                "price": getattr(new_link, 'price', 0) or 0,
                "is_active": new_link.is_active,
                "created_at": new_link.created_at.isoformat() if new_link.created_at else None,
            }
        }

        if auto_create_error:
            response["warning"] = auto_create_error

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating booking link: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create link: {str(e)}")

@router.put("/{creator_id}/links/{link_id}")
async def update_booking_link(creator_id: str, link_id: str, data: dict = Body(...), db: Session = Depends(get_db)):
    """Update a booking link"""
    try:
        link = db.query(BookingLink).filter(
            BookingLink.id == link_id,
            BookingLink.creator_id == creator_id
        ).first()

        if not link:
            raise HTTPException(status_code=404, detail="Link not found")

        # Update fields
        for key, value in data.items():
            if hasattr(link, key) and key not in ["id", "creator_id", "created_at"]:
                setattr(link, key, value)

        db.commit()
        logger.info(f"PUT /calendar/{creator_id}/links/{link_id} - Updated")

        return {"status": "ok", "message": "Link updated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating booking link: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update link: {str(e)}")

@router.delete("/{creator_id}/links/{link_id}")
async def delete_booking_link(creator_id: str, link_id: str, db: Session = Depends(get_db)):
    """Delete a booking link and all associated booking slots"""
    try:
        # Convert to UUID
        try:
            link_uuid = uuid.UUID(link_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid link_id format")

        link = db.query(BookingLink).filter(
            BookingLink.id == link_uuid,
            BookingLink.creator_id == creator_id
        ).first()

        if not link:
            raise HTTPException(status_code=404, detail="Link not found")

        # FIRST: Delete all booking_slots that reference this service
        deleted_slots = db.query(BookingSlot).filter(
            BookingSlot.service_id == link_uuid
        ).delete()

        # THEN: Delete the booking link
        db.delete(link)
        db.commit()

        logger.info(f"DELETE /calendar/{creator_id}/links/{link_id} - Deleted (with {deleted_slots} slots)")

        return {
            "status": "ok",
            "message": "Link deleted",
            "deleted_slots": deleted_slots
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting booking link: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete link: {str(e)}")


@router.delete("/{creator_id}/bookings/reset")
async def reset_bookings(creator_id: str, db: Session = Depends(get_db)):
    """Delete all bookings for a creator (for testing/reset purposes)"""
    try:
        # Delete all bookings for this creator
        deleted_count = db.query(CalendarBooking).filter(
            CalendarBooking.creator_id == creator_id
        ).delete()

        db.commit()

        logger.info(f"DELETE /calendar/{creator_id}/bookings/reset - Deleted {deleted_count} bookings")

        return {
            "status": "ok",
            "message": f"Deleted {deleted_count} bookings for {creator_id}",
            "deleted_count": deleted_count
        }
    except Exception as e:
        logger.error(f"Error resetting bookings: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to reset bookings: {str(e)}")


@router.delete("/{creator_id}/bookings/{booking_id}")
async def cancel_booking(creator_id: str, booking_id: str, db: Session = Depends(get_db)):
    """Cancel/delete a scheduled booking"""
    try:
        booking = db.query(CalendarBooking).filter(
            CalendarBooking.id == booking_id,
            CalendarBooking.creator_id == creator_id
        ).first()

        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        # Update status to cancelled instead of deleting (for history)
        booking.status = "cancelled"
        db.commit()
        logger.info(f"DELETE /calendar/{creator_id}/bookings/{booking_id} - Cancelled")

        return {"status": "ok", "message": "Booking cancelled"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling booking: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to cancel booking: {str(e)}")


# =============================================================================
# GOOGLE CALENDAR SYNC STATUS
# =============================================================================

@router.get("/{creator_id}/sync/status")
async def get_sync_status(creator_id: str, db: Session = Depends(get_db)):
    """Check if Google Calendar is connected and return sync status"""
    try:
        creator = db.query(Creator).filter(Creator.name == creator_id).first()

        google_connected = bool(creator and creator.google_access_token)
        has_refresh_token = bool(creator and creator.google_refresh_token)
        token_expires_at = None

        if creator and creator.google_token_expires_at:
            token_expires_at = creator.google_token_expires_at.isoformat()

        # Count existing bookings
        bookings_count = db.query(CalendarBooking).filter(
            CalendarBooking.creator_id == creator_id
        ).count()

        return {
            "status": "ok",
            "google_connected": google_connected,
            "has_refresh_token": has_refresh_token,
            "token_expires_at": token_expires_at,
            "bookings_synced": bookings_count,
            "auto_refresh_enabled": has_refresh_token
        }
    except Exception as e:
        logger.error(f"Error getting sync status: {e}")
        return {
            "status": "ok",
            "google_connected": False,
            "has_refresh_token": False,
            "token_expires_at": None,
            "bookings_synced": 0,
            "auto_refresh_enabled": False
        }


@router.post("/{creator_id}/update-status")
async def update_booking_status(creator_id: str, db: Session = Depends(get_db)):
    """
    Update status of past bookings:
    - scheduled -> completed (if scheduled_at < now)
    """
    try:
        now = datetime.now(timezone.utc)

        # Find all scheduled bookings that are in the past
        past_scheduled = db.query(CalendarBooking).filter(
            CalendarBooking.creator_id == creator_id,
            CalendarBooking.status == "scheduled",
            CalendarBooking.scheduled_at < now
        ).all()

        updated_count = 0
        for booking in past_scheduled:
            booking.status = "completed"
            updated_count += 1
            logger.info(f"Marked booking {booking.id} as completed (was scheduled for {booking.scheduled_at})")

        db.commit()

        return {
            "status": "ok",
            "message": f"Updated {updated_count} bookings to completed",
            "updated": updated_count
        }
    except Exception as e:
        logger.error(f"Error updating booking status: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


