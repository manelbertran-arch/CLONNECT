"""Calendar and bookings endpoints"""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import logging
import uuid
import httpx

try:
    from api.database import get_db
    from api.models import BookingLink, CalendarBooking, Creator
except:
    from database import get_db
    from models import BookingLink, CalendarBooking, Creator

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


async def create_zoom_meeting(access_token: str, name: str, duration: int) -> dict:
    """
    Create a Zoom meeting and return the join URL.
    Uses Zoom's meeting creation API.
    """
    async with httpx.AsyncClient() as client:
        # Create a scheduled meeting (type 2) that can be reused
        meeting_response = await client.post(
            "https://api.zoom.us/v2/users/me/meetings",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json={
                "topic": name,
                "type": 2,  # Scheduled meeting
                "duration": duration,
                "settings": {
                    "join_before_host": True,
                    "waiting_room": False,
                    "use_pmi": False,  # Don't use personal meeting ID
                }
            }
        )

        if meeting_response.status_code in [200, 201]:
            meeting_data = meeting_response.json()
            return {
                "success": True,
                "join_url": meeting_data.get("join_url", ""),
                "meeting_id": meeting_data.get("id", ""),
                "start_url": meeting_data.get("start_url", "")
            }
        else:
            logger.warning(f"Zoom meeting creation failed: {meeting_response.status_code} - {meeting_response.text}")
            return {
                "success": False,
                "join_url": "",
                "error": f"Could not create Zoom meeting. Status: {meeting_response.status_code}"
            }


async def create_google_calendar_event(access_token: str, name: str, duration: int) -> dict:
    """
    Create a Google Calendar event with automatic Google Meet link.
    Returns the Meet join URL.
    """
    from datetime import datetime, timedelta, timezone
    import uuid

    async with httpx.AsyncClient() as client:
        # Create a calendar event for tomorrow (as a template)
        # The user can then use the Meet link for their bookings
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        start_time = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(minutes=duration)

        event_data = {
            "summary": name,
            "description": f"Booking: {name} ({duration} min)",
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": "UTC"
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": "UTC"
            },
            "conferenceData": {
                "createRequest": {
                    "requestId": str(uuid.uuid4()),
                    "conferenceSolutionKey": {
                        "type": "hangoutsMeet"
                    }
                }
            }
        }

        event_response = await client.post(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            params={
                "conferenceDataVersion": 1  # Required for Meet link creation
            },
            json=event_data
        )

        if event_response.status_code in [200, 201]:
            response_data = event_response.json()
            conference_data = response_data.get("conferenceData", {})
            entry_points = conference_data.get("entryPoints", [])

            # Find the video entry point (Google Meet link)
            meet_link = ""
            for entry in entry_points:
                if entry.get("entryPointType") == "video":
                    meet_link = entry.get("uri", "")
                    break

            if meet_link:
                # Delete the template event (we just wanted the Meet link)
                event_id = response_data.get("id")
                if event_id:
                    await client.delete(
                        f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
                        headers={"Authorization": f"Bearer {access_token}"}
                    )

                return {
                    "success": True,
                    "meet_link": meet_link,
                    "event_id": event_id
                }
            else:
                return {
                    "success": False,
                    "meet_link": "",
                    "error": "Event created but no Meet link generated"
                }
        else:
            logger.warning(f"Google Calendar event creation failed: {event_response.status_code} - {event_response.text}")
            return {
                "success": False,
                "meet_link": "",
                "error": f"Could not create Google Calendar event. Status: {event_response.status_code}"
            }


async def create_calendly_event_type(access_token: str, name: str, duration: int) -> dict:
    """
    Create an event type in Calendly and return the scheduling URL.
    Uses the one_off_event_types endpoint for simple event creation.
    """
    async with httpx.AsyncClient() as client:
        # First, get user URI
        user_response = await client.get(
            "https://api.calendly.com/users/me",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        if user_response.status_code != 200:
            raise Exception("Failed to get Calendly user info")

        user_data = user_response.json()
        user_uri = user_data.get("resource", {}).get("uri")
        scheduling_url_base = user_data.get("resource", {}).get("scheduling_url", "")

        if not user_uri:
            raise Exception("Could not get Calendly user URI")

        # Try to create a one-off event type
        # Calculate date range (next 90 days)
        from datetime import date, timedelta
        start_date = date.today().isoformat()
        end_date = (date.today() + timedelta(days=90)).isoformat()

        event_response = await client.post(
            "https://api.calendly.com/one_off_event_types",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json={
                "name": name,
                "host": user_uri,
                "duration": duration,
                "date_setting": {
                    "type": "date_range",
                    "start_date": start_date,
                    "end_date": end_date
                },
                "location": {
                    "kind": "ask_invitee"
                }
            }
        )

        if event_response.status_code in [200, 201]:
            event_data = event_response.json()
            resource = event_data.get("resource", {})
            scheduling_url = resource.get("scheduling_url", "")
            return {
                "success": True,
                "scheduling_url": scheduling_url,
                "event_uri": resource.get("uri", "")
            }
        else:
            # Log the error but don't fail - fall back to manual URL
            logger.warning(f"Calendly event creation failed: {event_response.status_code} - {event_response.text}")

            # Generate a reasonable default URL based on user's scheduling URL
            slug = name.lower().replace(" ", "-").replace("'", "")[:20]
            fallback_url = f"{scheduling_url_base}/{slug}" if scheduling_url_base else ""

            return {
                "success": False,
                "scheduling_url": fallback_url,
                "error": f"Could not auto-create event type. Status: {event_response.status_code}"
            }


@router.post("/{creator_id}/links")
async def create_booking_link(creator_id: str, data: dict = Body(...), db: Session = Depends(get_db)):
    """
    Create a new booking link in PostgreSQL.
    Auto-creates links in connected platforms (Calendly, Zoom, Google Meet).
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

        platform = data.get("platform", "manual")
        url = data.get("url")
        auto_created = False
        auto_create_error = None

        # Import token helpers
        try:
            from api.routers.oauth import get_valid_calendly_token, get_valid_zoom_token, get_valid_google_token
        except:
            from routers.oauth import get_valid_calendly_token, get_valid_zoom_token, get_valid_google_token

        # If platform is Calendly and no URL provided, try to auto-create
        if platform == "calendly" and not url:
            try:
                access_token = await get_valid_calendly_token(creator_id)
                result = await create_calendly_event_type(
                    access_token=access_token,
                    name=data.get("title", "Meeting"),
                    duration=data.get("duration_minutes", 30)
                )
                if result["success"]:
                    url = result["scheduling_url"]
                    auto_created = True
                    logger.info(f"Auto-created Calendly event for {creator_id}: {url}")
                else:
                    auto_create_error = result.get("error")
                    url = result.get("scheduling_url", "")
                    logger.warning(f"Calendly auto-create partial: {auto_create_error}")
            except Exception as e:
                auto_create_error = str(e)
                logger.warning(f"Calendly auto-create failed for {creator_id}: {e}")

        # If platform is Zoom and no URL provided, try to auto-create
        elif platform == "zoom" and not url:
            try:
                access_token = await get_valid_zoom_token(creator_id)
                result = await create_zoom_meeting(
                    access_token=access_token,
                    name=data.get("title", "Meeting"),
                    duration=data.get("duration_minutes", 30)
                )
                if result["success"]:
                    url = result["join_url"]
                    auto_created = True
                    logger.info(f"Auto-created Zoom meeting for {creator_id}: {url}")
                else:
                    auto_create_error = result.get("error")
                    logger.warning(f"Zoom auto-create failed: {auto_create_error}")
            except Exception as e:
                auto_create_error = str(e)
                logger.warning(f"Zoom auto-create failed for {creator_id}: {e}")

        # If platform is Google Meet and no URL provided, try to auto-create
        elif platform == "google-meet" and not url:
            try:
                access_token = await get_valid_google_token(creator_id)
                result = await create_google_calendar_event(
                    access_token=access_token,
                    name=data.get("title", "Meeting"),
                    duration=data.get("duration_minutes", 30)
                )
                if result["success"]:
                    url = result["meet_link"]
                    auto_created = True
                    logger.info(f"Auto-created Google Meet for {creator_id}: {url}")
                else:
                    auto_create_error = result.get("error")
                    logger.warning(f"Google Meet auto-create failed: {auto_create_error}")
            except Exception as e:
                auto_create_error = str(e)
                logger.warning(f"Google Meet auto-create failed for {creator_id}: {e}")

        # Require URL if auto-create failed and platform supports it
        auto_create_platforms = ["calendly", "zoom", "google-meet"]
        if not url and platform not in auto_create_platforms:
            raise HTTPException(status_code=400, detail="URL is required")

        # Create new BookingLink with the URL (auto-generated or provided)
        new_link = BookingLink(
            id=uuid.uuid4(),
            creator_id=creator_id,
            meeting_type=data.get("meeting_type", "custom"),
            title=data.get("title", "Booking"),
            description=data.get("description"),
            duration_minutes=data.get("duration_minutes", 30),
            platform=platform,
            url=url or "",  # Use empty string if no URL
            price=data.get("price", 0),
            is_active=data.get("is_active", True),
            extra_data={
                **(data.get("extra_data", {})),
                "auto_created": auto_created
            }
        )

        db.add(new_link)
        db.commit()
        db.refresh(new_link)

        logger.info(f"POST /calendar/{creator_id}/links - Created link {new_link.id} (auto_created={auto_created})")

        platform_names = {"calendly": "Calendly", "zoom": "Zoom", "google-meet": "Google Meet"}
        platform_name = platform_names.get(platform, platform)

        response = {
            "status": "ok",
            "message": f"Service created" + (f" with {platform_name} link" if auto_created else ""),
            "auto_created": auto_created,
            "calendly_auto_created": auto_created and platform == "calendly",  # For backwards compatibility
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

        # If it's a Calendly booking, try to cancel in Calendly too
        if booking.platform == "calendly" and booking.external_id:
            try:
                from api.routers.oauth import get_valid_calendly_token
            except:
                from routers.oauth import get_valid_calendly_token

            try:
                access_token = await get_valid_calendly_token(creator_id)
                async with httpx.AsyncClient() as client:
                    # Cancel the event in Calendly
                    cancel_response = await client.post(
                        f"https://api.calendly.com/scheduled_events/{booking.external_id}/cancellation",
                        headers={
                            "Authorization": f"Bearer {access_token}",
                            "Content-Type": "application/json"
                        },
                        json={"reason": "Cancelled by creator"}
                    )
                    if cancel_response.status_code in [200, 201, 204]:
                        logger.info(f"Cancelled Calendly event {booking.external_id}")
                    else:
                        logger.warning(f"Failed to cancel Calendly event: {cancel_response.status_code}")
            except Exception as e:
                logger.warning(f"Could not cancel in Calendly: {e}")
                # Continue with local deletion anyway

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
# CALENDLY SYNC
# =============================================================================

@router.post("/{creator_id}/sync/calendly")
async def sync_calendly_events(creator_id: str, db: Session = Depends(get_db)):
    """
    Sync scheduled events from Calendly API.
    Automatically refreshes token if expired.
    """
    try:
        # Import the token helper from oauth module
        try:
            from api.routers.oauth import get_valid_calendly_token
        except:
            from routers.oauth import get_valid_calendly_token

        # Get valid token (auto-refreshes if needed)
        try:
            access_token = await get_valid_calendly_token(creator_id)
        except Exception as e:
            error_msg = str(e)
            if "not connected" in error_msg.lower():
                raise HTTPException(
                    status_code=400,
                    detail="Calendly not connected. Go to Settings to connect."
                )
            elif "reconnect" in error_msg.lower():
                raise HTTPException(
                    status_code=401,
                    detail="Calendly session expired. Please reconnect in Settings."
                )
            raise HTTPException(status_code=400, detail=error_msg)

        synced = 0
        errors = []

        async with httpx.AsyncClient() as client:
            # First, get user URI
            user_response = await client.get(
                "https://api.calendly.com/users/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )

            if user_response.status_code == 401:
                # Token invalid even after refresh - user must reconnect
                raise HTTPException(
                    status_code=401,
                    detail="Calendly session expired. Please reconnect in Settings."
                )

            user_data = user_response.json()
            user_uri = user_data.get("resource", {}).get("uri")

            if not user_uri:
                raise HTTPException(status_code=400, detail="Could not get Calendly user")

            # Get scheduled events (upcoming)
            now = datetime.now(timezone.utc).isoformat()
            events_response = await client.get(
                "https://api.calendly.com/scheduled_events",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "user": user_uri,
                    "min_start_time": now,
                    "status": "active",
                    "count": 50
                }
            )

            if events_response.status_code != 200:
                logger.error(f"Calendly events error: {events_response.text}")
                raise HTTPException(status_code=400, detail="Failed to fetch Calendly events")

            events_data = events_response.json()
            events = events_data.get("collection", [])

            for event in events:
                try:
                    event_uri = event.get("uri", "")
                    external_id = event_uri.split("/")[-1] if event_uri else None

                    # Check if already synced
                    existing = db.query(CalendarBooking).filter(
                        CalendarBooking.external_id == external_id,
                        CalendarBooking.creator_id == creator_id
                    ).first()

                    if existing:
                        continue  # Skip already synced

                    # Get invitee info
                    invitees_response = await client.get(
                        f"{event_uri}/invitees",
                        headers={"Authorization": f"Bearer {access_token}"}
                    )
                    invitee_data = {}
                    if invitees_response.status_code == 200:
                        invitees = invitees_response.json().get("collection", [])
                        if invitees:
                            invitee_data = invitees[0]

                    # Parse event data
                    start_time = event.get("start_time")
                    end_time = event.get("end_time")
                    duration = 30  # default
                    if start_time and end_time:
                        start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                        end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                        duration = int((end_dt - start_dt).total_seconds() / 60)

                    # Create booking
                    booking = CalendarBooking(
                        id=uuid.uuid4(),
                        creator_id=creator_id,
                        follower_id=invitee_data.get("email", "unknown"),
                        meeting_type=event.get("event_type_name", event.get("name", "Meeting")),
                        platform="calendly",
                        status="scheduled",
                        scheduled_at=datetime.fromisoformat(start_time.replace("Z", "+00:00")) if start_time else None,
                        duration_minutes=duration,
                        guest_name=invitee_data.get("name", ""),
                        guest_email=invitee_data.get("email", ""),
                        meeting_url=event.get("location", {}).get("join_url", ""),
                        external_id=external_id,
                        extra_data={"calendly_event": event}
                    )
                    db.add(booking)
                    synced += 1

                except Exception as e:
                    errors.append(str(e))
                    logger.error(f"Error syncing event: {e}")

            db.commit()

        return {
            "status": "ok",
            "synced": synced,
            "total_events": len(events),
            "errors": errors if errors else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing Calendly: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{creator_id}/sync/status")
async def get_sync_status(creator_id: str, db: Session = Depends(get_db)):
    """Check if Calendly is connected and return sync status"""
    try:
        creator = db.query(Creator).filter(Creator.name == creator_id).first()

        calendly_connected = bool(creator and creator.calendly_token)
        has_refresh_token = bool(creator and creator.calendly_refresh_token)
        token_expires_at = None

        if creator and creator.calendly_token_expires_at:
            token_expires_at = creator.calendly_token_expires_at.isoformat()

        # Count existing bookings
        bookings_count = db.query(CalendarBooking).filter(
            CalendarBooking.creator_id == creator_id
        ).count()

        return {
            "status": "ok",
            "calendly_connected": calendly_connected,
            "has_refresh_token": has_refresh_token,
            "token_expires_at": token_expires_at,
            "bookings_synced": bookings_count,
            "auto_refresh_enabled": has_refresh_token
        }
    except Exception as e:
        logger.error(f"Error getting sync status: {e}")
        return {
            "status": "ok",
            "calendly_connected": False,
            "has_refresh_token": False,
            "token_expires_at": None,
            "bookings_synced": 0,
            "auto_refresh_enabled": False
        }
