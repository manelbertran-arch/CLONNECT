"""Analytics endpoints for sales tracking and conversion metrics"""
from fastapi import APIRouter
import logging

from core.sales_tracker import get_sales_tracker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/{creator_id}/sales")
async def get_sales_stats(creator_id: str, days: int = 30):
    """Get sales and conversion statistics"""
    tracker = get_sales_tracker()
    stats = tracker.get_stats(creator_id, days)
    return {"status": "ok", "creator_id": creator_id, "stats": stats}


@router.get("/{creator_id}/sales/activity")
async def get_recent_activity(creator_id: str, limit: int = 20):
    """Get recent clicks and sales activity"""
    tracker = get_sales_tracker()
    activity = tracker.get_recent_activity(creator_id, limit)
    return {"status": "ok", "creator_id": creator_id, "activity": activity, "count": len(activity)}


@router.get("/{creator_id}/sales/follower/{follower_id}")
async def get_follower_journey(creator_id: str, follower_id: str):
    """Get purchase journey for a specific follower"""
    tracker = get_sales_tracker()
    journey = tracker.get_follower_journey(creator_id, follower_id)
    return {"status": "ok", "follower_id": follower_id, "journey": journey}


@router.post("/{creator_id}/sales/click")
async def record_click(creator_id: str, product_id: str, follower_id: str, product_name: str = "", link_url: str = ""):
    """Manually record a product link click"""
    tracker = get_sales_tracker()
    tracker.record_click(creator_id, product_id, follower_id, product_name, link_url)
    return {"status": "ok", "message": "Click recorded"}
