"""Calendar and bookings endpoints"""
from fastapi import APIRouter, Body
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/calendar", tags=["calendar"])

@router.get("/{creator_id}/bookings")
async def get_bookings(creator_id: str, upcoming: bool = True):
    return {"status": "ok", "creator_id": creator_id, "bookings": [], "count": 0}

@router.get("/{creator_id}/stats")
async def get_calendar_stats(creator_id: str, days: int = 30):
    return {"status": "ok", "creator_id": creator_id, "total_bookings": 0, "completed": 0, "cancelled": 0, "no_show": 0, "show_rate": 0.0, "upcoming": 0, "by_type": {}, "by_platform": {}}

@router.get("/{creator_id}/links")
async def get_booking_links(creator_id: str):
    return {"status": "ok", "creator_id": creator_id, "links": [], "count": 0}

@router.post("/{creator_id}/links")
async def create_booking_link(creator_id: str, data: dict = Body(...)):
    return {"status": "ok", "message": "Link created", "link": data}

@router.put("/{creator_id}/links/{link_id}")
async def update_booking_link(creator_id: str, link_id: str, data: dict = Body(...)):
    return {"status": "ok", "message": "Link updated"}

@router.delete("/{creator_id}/links/{link_id}")
async def delete_booking_link(creator_id: str, link_id: str):
    return {"status": "ok", "message": "Link deleted"}
