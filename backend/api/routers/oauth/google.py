"""Google OAuth + Calendar/Meet endpoints and helpers."""

import logging
import os
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["oauth"])

# Frontend URL for redirects after OAuth
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://www.clonnectapp.com")
# Backend API URL for OAuth callbacks
API_URL = os.getenv("API_URL", "https://api.clonnectapp.com")

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", f"{API_URL}/oauth/google/callback").strip()


@router.get("/debug/google-config")
async def debug_google_config():
    """Debug endpoint to verify Google OAuth configuration"""
    client_id = GOOGLE_CLIENT_ID
    client_secret = GOOGLE_CLIENT_SECRET
    redirect_uri = GOOGLE_REDIRECT_URI

    return {
        "client_id_set": bool(client_id),
        "client_id_preview": (
            client_id[:20] + "..." if len(client_id) > 20 else client_id if client_id else "NOT SET"
        ),
        "client_id_length": len(client_id),
        "client_secret_set": bool(client_secret),
        "client_secret_length": len(client_secret),
        "client_secret_preview": (
            client_secret[:5] + "..." if len(client_secret) > 5 else "TOO SHORT"
        ),
        "redirect_uri": redirect_uri,
        "redirect_uri_matches_api": redirect_uri == f"{API_URL}/oauth/google/callback",
    }


@router.get("/google/start")
async def google_oauth_start(creator_id: str):
    """Start Google OAuth flow for Calendar/Meet access"""
    import secrets

    if not GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured on this server")

    state = f"{creator_id}:{secrets.token_urlsafe(16)}"

    # Scopes needed for Google Meet links via Calendar API
    scopes = [
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/userinfo.email",
    ]

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "scope": " ".join(scopes),
        "state": state,
        "access_type": "offline",  # Get refresh token
        "prompt": "consent",  # Force consent to always get refresh token
    }

    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return {"auth_url": auth_url, "state": state}


@router.get("/google/callback")
async def google_oauth_callback(code: str = Query(...), state: str = Query("")):
    """Handle Google OAuth callback"""
    from datetime import datetime, timedelta, timezone

    import httpx

    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        logger.error(
            f"Google OAuth not configured: client_id={bool(GOOGLE_CLIENT_ID)}, secret={bool(GOOGLE_CLIENT_SECRET)}"
        )
        return RedirectResponse(
            f"{FRONTEND_URL}/settings?tab=connections&error=google_not_configured"
        )

    creator_id = state.split(":")[0] if ":" in state else "manel"

    # Log what we're sending (without exposing full secret)
    logger.info(
        f"Google OAuth callback - client_id_len={len(GOOGLE_CLIENT_ID)}, secret_len={len(GOOGLE_CLIENT_SECRET)}, redirect={GOOGLE_REDIRECT_URI}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Build the request data - use urlencode explicitly for proper form encoding
            token_params = {
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            }

            # Encode as form data explicitly
            encoded_data = urlencode(token_params)
            logger.info(f"Google token request body length: {len(encoded_data)}")

            # Exchange code for access token
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                content=encoded_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )

            logger.info(f"Google token response status: {token_response.status_code}")
            logger.info(f"Google token response body: {token_response.text[:500]}")
            token_data = token_response.json()

            if "error" in token_data:
                logger.error(f"Google token error: {token_data}")
                return RedirectResponse(
                    f"{FRONTEND_URL}/settings?tab=connections&error=google_auth_failed"
                )

            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in", 3600)  # Default 1 hour

            # Calculate expiration time
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

            # Get user info
            user_response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_data = user_response.json()
            google_email = user_data.get("email", "")

            # Save to database
            await _save_google_connection(
                creator_id, access_token, refresh_token, expires_at, google_email
            )

            logger.info(f"Google connected for {creator_id}, expires at {expires_at}")
            return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&success=google")

    except Exception as e:
        logger.error(f"Google OAuth error: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/settings?tab=connections&error=google_failed")


@router.post("/refresh/google/{creator_id}")
async def force_refresh_google(creator_id: str):
    """Force refresh Google token"""

    try:
        new_token = await refresh_google_token(creator_id)

        from api.database import SessionLocal
        from api.models import Creator

        with SessionLocal() as db:
            creator = db.query(Creator).filter_by(name=creator_id).first()
            expires_at = creator.google_token_expires_at if creator else None

        return {
            "status": "ok",
            "message": "Google token refreshed successfully",
            "token_preview": f"{new_token[:20]}..." if new_token else None,
            "expires_at": expires_at.isoformat() if expires_at else None,
        }
    except Exception as e:
        from api.utils.error_helpers import safe_error_detail

        raise HTTPException(status_code=502, detail=safe_error_detail(e, "Google token refresh"))


async def _save_google_connection(
    creator_id: str, access_token: str, refresh_token: str, expires_at, google_email: str = None
):
    """Save Google OAuth connection with refresh token to database"""
    try:
        from api.database import DATABASE_URL, SessionLocal

        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                from api.models import Creator

                creator = session.query(Creator).filter_by(name=creator_id).first()

                if not creator:
                    logger.warning(f"Creator {creator_id} not found, creating...")
                    try:
                        creator = Creator(name=creator_id, email=f"{creator_id}@clonnect.com")
                        session.add(creator)
                        session.flush()
                    except Exception:
                        session.rollback()
                        creator = session.query(Creator).filter_by(name=creator_id).first()
                        if not creator:
                            raise

                creator.google_access_token = access_token
                creator.google_refresh_token = refresh_token
                creator.google_token_expires_at = expires_at

                session.commit()
                logger.info(f"Saved Google connection for {creator_id} ({google_email})")
            finally:
                session.close()
    except Exception as e:
        logger.error(f"Error saving Google connection: {e}")
        raise


async def refresh_google_token(creator_id: str) -> str:
    """
    Refresh Google access token using the refresh token.
    Returns the new access token or raises an exception.
    """
    from datetime import datetime, timedelta, timezone

    import httpx

    try:
        from api.database import DATABASE_URL, SessionLocal

        if not DATABASE_URL or not SessionLocal:
            raise Exception("Database not configured")

        session = SessionLocal()
        try:
            from api.models import Creator

            creator = session.query(Creator).filter_by(name=creator_id).first()

            if not creator:
                raise Exception(f"Creator {creator_id} not found")

            if not creator.google_refresh_token:
                raise Exception("No Google refresh token available - user must reconnect")

            # Call Google token endpoint
            async with httpx.AsyncClient(timeout=30.0) as client:
                token_response = await client.post(
                    "https://oauth2.googleapis.com/token",
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    data={
                        "client_id": GOOGLE_CLIENT_ID,
                        "client_secret": GOOGLE_CLIENT_SECRET,
                        "refresh_token": creator.google_refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
                token_data = token_response.json()

                if "error" in token_data:
                    logger.error(f"Google refresh error: {token_data}")
                    # Clear tokens so user knows to reconnect
                    creator.google_access_token = None
                    creator.google_refresh_token = None
                    creator.google_token_expires_at = None
                    session.commit()
                    raise Exception("Google refresh token expired - user must reconnect")

                new_access_token = token_data.get("access_token")
                # Google doesn't always return a new refresh token
                expires_in = token_data.get("expires_in", 3600)
                expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

                # Update tokens in database
                creator.google_access_token = new_access_token
                creator.google_token_expires_at = expires_at
                session.commit()

                logger.info(f"Refreshed Google token for {creator_id}, new expiry: {expires_at}")
                return new_access_token

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Error refreshing Google token: {e}")
        raise


async def get_valid_google_token(creator_id: str) -> str:
    """
    Get a valid Google access token, refreshing if necessary.
    This should be called before any Google API request.
    """
    from datetime import datetime, timedelta, timezone

    try:
        from api.database import DATABASE_URL, SessionLocal

        if not DATABASE_URL or not SessionLocal:
            raise Exception("Database not configured")

        session = SessionLocal()
        try:
            from api.models import Creator

            creator = session.query(Creator).filter_by(name=creator_id).first()

            if not creator:
                raise Exception(f"Creator {creator_id} not found")

            if not creator.google_access_token:
                raise Exception("Google not connected")

            # Check if token is expired or about to expire (within 10 minutes)
            if creator.google_token_expires_at:
                buffer = timedelta(minutes=10)
                if datetime.now(timezone.utc) + buffer >= creator.google_token_expires_at:
                    logger.info(
                        f"Google token for {creator_id} expired or expiring soon, refreshing..."
                    )
                    session.close()  # Close before async call
                    return await refresh_google_token(creator_id)

            return creator.google_access_token

        finally:
            if session:
                session.close()

    except Exception as e:
        logger.error(f"Error getting valid Google token: {e}")
        raise


async def create_google_meet_event(
    creator_id: str,
    title: str,
    start_time,
    end_time,
    guest_email: str = None,
    guest_name: str = None,
    description: str = None,
) -> dict:
    """
    Create a Google Calendar event with Google Meet link.

    Args:
        creator_id: The creator's ID
        title: Event title
        start_time: Event start datetime (timezone-aware)
        end_time: Event end datetime (timezone-aware)
        guest_email: Optional guest email to invite
        guest_name: Optional guest name
        description: Optional event description

    Returns:
        dict with event_id, meet_link, and calendar_link
    """
    import httpx

    try:
        access_token = await get_valid_google_token(creator_id)

        # Build event data
        event = {
            "summary": title,
            "description": description or f"Booking with {guest_name or 'guest'}",
            "start": {"dateTime": start_time.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end_time.isoformat(), "timeZone": "UTC"},
            "conferenceData": {
                "createRequest": {
                    "requestId": f"clonnect-{creator_id}-{start_time.timestamp()}",
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }

        # Add attendee if email provided
        if guest_email:
            event["attendees"] = [{"email": guest_email, "displayName": guest_name or ""}]

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                params={
                    "conferenceDataVersion": 1,
                    "sendUpdates": "all" if guest_email else "none",
                },
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=event,
            )

            if response.status_code != 200:
                logger.error(f"Google Calendar API error: {response.status_code} - {response.text}")
                raise Exception(f"Failed to create calendar event: {response.text}")

            event_data = response.json()

            # Extract Meet link
            meet_link = None
            if "conferenceData" in event_data:
                entry_points = event_data["conferenceData"].get("entryPoints", [])
                for ep in entry_points:
                    if ep.get("entryPointType") == "video":
                        meet_link = ep.get("uri")
                        break

            return {
                "event_id": event_data.get("id"),
                "meet_link": meet_link,
                "calendar_link": event_data.get("htmlLink"),
                "status": "confirmed",
            }

    except Exception as e:
        logger.error(f"Error creating Google Meet event: {e}")
        raise


async def delete_google_calendar_event(creator_id: str, event_id: str) -> bool:
    """
    Delete a Google Calendar event.

    Args:
        creator_id: The creator's ID
        event_id: The Google Calendar event ID to delete

    Returns:
        True if deleted successfully, False otherwise
    """
    import httpx

    try:
        access_token = await get_valid_google_token(creator_id)

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}",
                params={"sendUpdates": "all"},  # Notify attendees
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
            )

            if response.status_code == 204 or response.status_code == 200:
                logger.info(f"Deleted Google Calendar event {event_id} for {creator_id}")
                return True
            elif response.status_code == 404:
                logger.warning(
                    f"Google Calendar event {event_id} not found - may have been deleted already"
                )
                return True  # Consider it a success if already deleted
            else:
                logger.error(
                    f"Failed to delete Google Calendar event: {response.status_code} - {response.text}"
                )
                return False

    except Exception as e:
        logger.error(f"Error deleting Google Calendar event: {e}")
        return False


async def get_google_freebusy(creator_id: str, start_time, end_time) -> list:
    """
    Get busy times from Google Calendar using freebusy API.

    Args:
        creator_id: The creator's ID
        start_time: Start of time range (datetime, timezone-aware)
        end_time: End of time range (datetime, timezone-aware)

    Returns:
        List of busy periods: [{"start": datetime, "end": datetime}, ...]
    """
    from datetime import datetime

    import httpx

    try:
        access_token = await get_valid_google_token(creator_id)

        # Build freebusy request
        request_body = {
            "timeMin": start_time.isoformat(),
            "timeMax": end_time.isoformat(),
            "items": [{"id": "primary"}],  # Query primary calendar
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://www.googleapis.com/calendar/v3/freeBusy",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=request_body,
                timeout=10.0,
            )

            if response.status_code != 200:
                logger.error(f"Google freebusy API error: {response.status_code} - {response.text}")
                return []  # Return empty if error - will show all slots as available

            data = response.json()

            # Extract busy periods
            busy_periods = []
            calendars = data.get("calendars", {})
            primary_cal = calendars.get("primary", {})
            busy_list = primary_cal.get("busy", [])

            for busy in busy_list:
                busy_periods.append(
                    {
                        "start": datetime.fromisoformat(busy["start"].replace("Z", "+00:00")),
                        "end": datetime.fromisoformat(busy["end"].replace("Z", "+00:00")),
                    }
                )

            logger.info(f"Found {len(busy_periods)} busy periods for {creator_id}")
            return busy_periods

    except Exception as e:
        logger.error(f"Error getting Google freebusy: {e}")
        return []  # Return empty on error - graceful degradation
