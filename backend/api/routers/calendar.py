"""Calendar and bookings endpoints"""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session
import logging
import uuid

try:
    from api.database import get_db
    from api.models import BookingLink, CalendarBooking
except:
    from database import get_db
    from models import BookingLink, CalendarBooking

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/calendar", tags=["calendar"])

@router.get("/{creator_id}/bookings")
async def get_bookings(creator_id: str, upcoming: bool = True, db: Session = Depends(get_db)):
    """Get all bookings for a creator"""
    try:
        bookings = db.query(CalendarBooking).filter(
            CalendarBooking.creator_id == creator_id
        ).all()

        return {
            "status": "ok",
            "creator_id": creator_id,
            "bookings": [
                {
                    "id": str(b.id),
                    "meeting_type": b.meeting_type,
                    "platform": b.platform,
                    "status": b.status,
                    "scheduled_at": b.scheduled_at.isoformat() if b.scheduled_at else None,
                    "duration_minutes": b.duration_minutes,
                    "guest_name": b.guest_name,
                    "guest_email": b.guest_email,
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

@router.post("/{creator_id}/links")
async def create_booking_link(creator_id: str, data: dict = Body(...), db: Session = Depends(get_db)):
    """Create a new booking link in PostgreSQL - uses creator_id from URL"""
    try:
        # Create new BookingLink with creator_id from URL path
        new_link = BookingLink(
            id=uuid.uuid4(),
            creator_id=creator_id,  # Use creator_id from URL, not from data
            meeting_type=data.get("meeting_type", "custom"),
            title=data.get("title", "Booking"),
            description=data.get("description"),
            duration_minutes=data.get("duration_minutes", 30),
            platform=data.get("platform", "manual"),
            url=data.get("url"),
            is_active=data.get("is_active", True),
            extra_data=data.get("extra_data", {})
        )

        db.add(new_link)
        db.commit()
        db.refresh(new_link)

        logger.info(f"POST /calendar/{creator_id}/links - Created link {new_link.id} with creator_id={creator_id}")

        return {
            "status": "ok",
            "message": "Link created",
            "link": {
                "id": str(new_link.id),
                "creator_id": new_link.creator_id,
                "meeting_type": new_link.meeting_type,
                "title": new_link.title,
                "description": new_link.description,
                "duration_minutes": new_link.duration_minutes,
                "platform": new_link.platform,
                "url": new_link.url,
                "is_active": new_link.is_active,
                "created_at": new_link.created_at.isoformat() if new_link.created_at else None,
            }
        }
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
    """Delete a booking link"""
    try:
        link = db.query(BookingLink).filter(
            BookingLink.id == link_id,
            BookingLink.creator_id == creator_id
        ).first()

        if not link:
            raise HTTPException(status_code=404, detail="Link not found")

        db.delete(link)
        db.commit()
        logger.info(f"DELETE /calendar/{creator_id}/links/{link_id} - Deleted")

        return {"status": "ok", "message": "Link deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting booking link: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete link: {str(e)}")
