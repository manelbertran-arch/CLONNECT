"""Payments and revenue endpoints"""
from fastapi import APIRouter, Body, HTTPException
from datetime import datetime, timedelta, timezone
import logging

from api.schemas.payments import PurchaseRecord
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
        {"date": (datetime.now(timezone.utc) - timedelta(days=days-i-1)).strftime("%Y-%m-%d"), "revenue": 0, "purchases": 0}
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
    data: PurchaseRecord,
):
    """Record a new purchase manually or from webhook"""
    payment_manager = get_payment_manager()
    sales_tracker = get_sales_tracker()

    # Extract data
    product_id = data.product_id or ""
    product_name = data.product_name or "Unknown"
    amount = float(data.amount or 0)
    currency = data.currency or "EUR"
    platform = data.platform or "manual"
    follower_id = data.follower_id or ""
    external_id = data.external_id or ""

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


@router.get("/{creator_id}/customer/{follower_id}")
async def get_customer_purchases(creator_id: str, follower_id: str):
    """Get purchase history for a specific customer"""
    try:
        payment_manager = get_payment_manager()
        purchases = payment_manager.get_customer_purchases(
            creator_id=creator_id, follower_id=follower_id
        )

        total_spent = sum(p.get("amount", 0) for p in purchases if p.get("status") == "completed")

        return {
            "status": "ok",
            "creator_id": creator_id,
            "follower_id": follower_id,
            "purchases": purchases,
            "total_spent": total_spent,
            "count": len(purchases),
        }

    except Exception as e:
        logger.error(f"Error getting customer purchases: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{creator_id}/attribute")
async def attribute_sale(creator_id: str, purchase_id: str, follower_id: str):
    """
    Manually attribute a sale to the bot.

    Use when a purchase wasn't automatically linked to a conversation.
    """
    try:
        payment_manager = get_payment_manager()
        success = payment_manager.attribute_sale_to_bot(
            creator_id=creator_id, follower_id=follower_id, purchase_id=purchase_id
        )

        if not success:
            raise HTTPException(status_code=404, detail="Purchase not found")

        return {
            "status": "ok",
            "attributed": True,
            "purchase_id": purchase_id,
            "follower_id": follower_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error attributing sale: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
