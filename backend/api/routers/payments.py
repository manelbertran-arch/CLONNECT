"""Payments and revenue endpoints"""
from fastapi import APIRouter, Body
from datetime import datetime, timedelta
from typing import Optional
import logging

from core.payments import get_payment_manager
from core.sales_tracker import get_sales_tracker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("/{creator_id}/revenue")
async def get_revenue_stats(creator_id: str, days: int = 30):
    """Get revenue statistics combining payment manager and sales tracker"""
    payment_manager = get_payment_manager()
    sales_tracker = get_sales_tracker()

    # Get stats from both sources
    pm_stats = payment_manager.get_revenue_stats(creator_id, days)
    st_stats = sales_tracker.get_stats(creator_id, days)

    # Generate daily revenue placeholder
    daily_revenue = [
        {"date": (datetime.now() - timedelta(days=days-i-1)).strftime("%Y-%m-%d"), "revenue": 0, "purchases": 0}
        for i in range(days)
    ]

    return {
        "status": "ok",
        "creator_id": creator_id,
        "total_revenue": pm_stats.total_revenue + st_stats.get("total_revenue", 0),
        "total_purchases": pm_stats.total_purchases + st_stats.get("total_sales", 0),
        "avg_order_value": pm_stats.total_revenue / pm_stats.total_purchases if pm_stats.total_purchases > 0 else st_stats.get("avg_order_value", 0),
        "bot_attributed_revenue": pm_stats.attributed_to_bot,
        "bot_attributed_purchases": pm_stats.attributed_purchases,
        "total_clicks": st_stats.get("total_clicks", 0),
        "conversion_rate": st_stats.get("conversion_rate", 0),
        "revenue_by_platform": pm_stats.by_platform,
        "revenue_by_product": {**pm_stats.by_product, **st_stats.get("revenue_by_product", {})},
        "daily_revenue": daily_revenue
    }


@router.get("/{creator_id}/purchases")
async def get_purchases(creator_id: str, limit: int = 50, offset: int = 0):
    """Get all purchases"""
    payment_manager = get_payment_manager()
    purchases = payment_manager.get_all_purchases(creator_id, limit)
    return {"status": "ok", "creator_id": creator_id, "purchases": purchases, "count": len(purchases)}


@router.post("/{creator_id}/purchases")
async def record_purchase(
    creator_id: str,
    data: dict = Body(...)
):
    """Record a new purchase manually or from webhook"""
    payment_manager = get_payment_manager()
    sales_tracker = get_sales_tracker()

    # Extract data
    product_id = data.get("product_id", "")
    product_name = data.get("product_name", "Unknown")
    amount = float(data.get("amount", 0))
    currency = data.get("currency", "EUR")
    platform = data.get("platform", "manual")
    follower_id = data.get("follower_id", "")
    external_id = data.get("external_id", "")

    # Record in payment manager
    purchase = await payment_manager.record_purchase(
        creator_id=creator_id,
        follower_id=follower_id,
        product_id=product_id,
        product_name=product_name,
        amount=amount,
        currency=currency,
        platform=platform,
        external_id=external_id
    )

    # Also record in sales tracker for conversion analytics
    sales_tracker.record_sale(
        creator_id=creator_id,
        product_id=product_id,
        follower_id=follower_id,
        amount=amount,
        currency=currency,
        product_name=product_name,
        external_id=external_id,
        platform=platform
    )

    return {"status": "ok", "message": "Purchase recorded", "purchase_id": purchase.purchase_id}
