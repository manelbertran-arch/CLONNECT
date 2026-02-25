"""Purchase recording, customer management, and revenue queries."""
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

from core.payments.models import PaymentPlatform, PurchaseStatus, Purchase, RevenueStats

logger = logging.getLogger("clonnect-payments")


# ==========================================================================
# PURCHASE RECORDING
# ==========================================================================

async def record_purchase(
    manager,
    creator_id: str,
    follower_id: str,
    product_id: str,
    product_name: str,
    amount: float,
    currency: str = "EUR",
    platform: str = "manual",
    external_id: str = "",
    customer_email: str = "",
    customer_name: str = "",
    metadata: Dict[str, Any] = None
) -> Purchase:
    """
    Record a purchase.

    Args:
        manager: PaymentManager instance (for file operations)
        creator_id: Creator ID
        follower_id: Follower ID (if known)
        product_id: Product ID
        product_name: Product name
        amount: Purchase amount
        currency: Currency code
        platform: Payment platform
        external_id: External transaction ID
        customer_email: Customer email
        customer_name: Customer name
        metadata: Additional data

    Returns:
        Purchase object
    """
    purchase = Purchase(
        purchase_id=f"pur_{uuid.uuid4().hex[:12]}",
        creator_id=creator_id,
        follower_id=follower_id,
        product_id=product_id,
        product_name=product_name,
        amount=amount,
        currency=currency,
        platform=platform,
        status=PurchaseStatus.COMPLETED.value,
        timestamp=datetime.now(timezone.utc).isoformat(),
        external_id=external_id,
        customer_email=customer_email,
        customer_name=customer_name,
        attributed_to_bot=False,
        metadata=metadata or {}
    )

    # Save purchase
    purchases = manager._load_purchases(creator_id)
    purchases.append(purchase)
    manager._save_purchases(creator_id, purchases)

    # Update follower memory
    if follower_id:
        await _update_follower_as_customer(creator_id, follower_id, product_id)

        # Try to attribute to bot
        if await _check_bot_attribution(creator_id, follower_id):
            purchase.attributed_to_bot = True
            manager._save_purchases(creator_id, purchases)

    # Track analytics
    await _track_purchase_analytics(creator_id, follower_id, product_id, amount, platform)

    # Track sale in SalesTracker for conversion analytics
    try:
        from core.sales_tracker import get_sales_tracker
        sales_tracker = get_sales_tracker()
        sales_tracker.record_sale(
            creator_id=creator_id,
            product_id=product_id,
            follower_id=follower_id or "",
            amount=amount,
            currency=currency,
            product_name=product_name,
            external_id=external_id,
            platform=platform
        )
        logger.info(f"Sale tracked in SalesTracker: {product_id}")
    except Exception as st_error:
        logger.warning(f"Failed to track sale in SalesTracker: {st_error}")

    logger.info(f"Purchase recorded: {purchase.purchase_id} - {amount} {currency}")
    return purchase


async def _update_follower_as_customer(
    creator_id: str,
    follower_id: str,
    product_id: str
):
    """Update follower memory to mark as customer"""
    try:
        # Load follower memory
        safe_id = follower_id.replace("/", "_").replace("\\", "_")
        file_path = f"data/followers/{creator_id}/{safe_id}.json"

        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Update customer status
            data["is_customer"] = True

            # Add product to purchased products
            if "products_purchased" not in data:
                data["products_purchased"] = []
            if product_id and product_id not in data["products_purchased"]:
                data["products_purchased"].append(product_id)

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"Follower {follower_id} marked as customer")

        # Update lead status to 'cliente' in PostgreSQL
        await _update_lead_status_to_cliente(creator_id, follower_id)

        # Cancel nurturing sequences
        await _cancel_nurturing_for_customer(creator_id, follower_id)

    except Exception as e:
        logger.error(f"Error updating follower as customer: {e}")


async def _cancel_nurturing_for_customer(creator_id: str, follower_id: str):
    """Cancel nurturing sequences when user becomes a customer"""
    try:
        nurturing_file = f"data/nurturing/{creator_id}_followups.json"

        if os.path.exists(nurturing_file):
            with open(nurturing_file, 'r', encoding='utf-8') as f:
                followups = json.load(f)

            # Remove pending followups for this follower
            original_count = len(followups)
            followups = [
                f for f in followups
                if f.get("follower_id") != follower_id or f.get("status") != "pending"
            ]

            if len(followups) < original_count:
                with open(nurturing_file, 'w', encoding='utf-8') as f:
                    json.dump(followups, f, indent=2, ensure_ascii=False)
                logger.info(f"Cancelled nurturing for new customer {follower_id}")

    except Exception as e:
        logger.error(f"Error cancelling nurturing: {e}")


async def _update_lead_status_to_cliente(creator_id: str, follower_id: str):
    """Update lead status to 'cliente' in PostgreSQL after payment."""
    try:
        from sqlalchemy import text

        from api.database import get_db_session

        with get_db_session() as db:
            result = db.execute(
                text("""
                    UPDATE leads SET status = 'cliente', updated_at = NOW()
                    WHERE follower_id = :follower_id
                      AND creator_id IN (
                        SELECT id FROM creators WHERE id::text = :cid OR name = :cid
                      )
                      AND status != 'cliente'
                """),
                {"follower_id": follower_id, "cid": creator_id},
            )
            db.commit()

            if result.rowcount > 0:
                logger.info(f"Lead {follower_id} status updated to 'cliente'")

    except Exception as e:
        logger.error(f"Error updating lead status to cliente: {e}")


async def _check_bot_attribution(creator_id: str, follower_id: str) -> bool:
    """Check if purchase should be attributed to bot"""
    try:
        safe_id = follower_id.replace("/", "_").replace("\\", "_")
        file_path = f"data/followers/{creator_id}/{safe_id}.json"

        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Attribute if:
            # 1. User had interaction with bot
            # 2. User was marked as lead
            # 3. User had high purchase intent
            if data.get("total_messages", 0) > 0:
                return True
            if data.get("is_lead", False):
                return True
            if data.get("purchase_intent_score", 0) > 0.3:
                return True

        return False

    except Exception as e:
        logger.error(f"Error checking bot attribution: {e}")
        return False


async def _track_purchase_analytics(
    creator_id: str,
    follower_id: str,
    product_id: str,
    amount: float,
    platform: str
):
    """Track purchase in analytics"""
    try:
        from core.analytics import get_analytics_manager
        analytics = get_analytics_manager()
        analytics.track_conversion(
            creator_id=creator_id,
            follower_id=follower_id or "unknown",
            product_id=product_id,
            amount=amount,
            platform=platform
        )
    except Exception as e:
        logger.error(f"Error tracking purchase analytics: {e}")


async def find_follower_by_email(creator_id: str, email: str) -> str:
    """Try to find follower ID by email"""
    return ""


# ==========================================================================
# PURCHASE QUERIES
# ==========================================================================

def get_customer_purchases(
    manager,
    creator_id: str,
    follower_id: str
) -> List[Dict[str, Any]]:
    """
    Get all purchases for a customer.

    Args:
        manager: PaymentManager instance
        creator_id: Creator ID
        follower_id: Follower ID

    Returns:
        List of purchases
    """
    purchases = manager._load_purchases(creator_id)
    customer_purchases = [
        p.to_dict() for p in purchases
        if p.follower_id == follower_id
    ]
    return sorted(customer_purchases, key=lambda x: x["timestamp"], reverse=True)


def get_all_purchases(
    manager,
    creator_id: str,
    limit: int = 100,
    status: str = None
) -> List[Dict[str, Any]]:
    """
    Get all purchases for a creator.

    Args:
        manager: PaymentManager instance
        creator_id: Creator ID
        limit: Maximum number to return
        status: Filter by status

    Returns:
        List of purchases
    """
    purchases = manager._load_purchases(creator_id)

    if status:
        purchases = [p for p in purchases if p.status == status]

    # Sort by timestamp descending
    purchases.sort(key=lambda x: x.timestamp, reverse=True)

    return [p.to_dict() for p in purchases[:limit]]


def attribute_sale_to_bot(
    manager,
    creator_id: str,
    follower_id: str,
    purchase_id: str,
    attribution_data: Dict[str, Any] = None
) -> bool:
    """
    Manually attribute a sale to the bot.

    Args:
        manager: PaymentManager instance
        creator_id: Creator ID
        follower_id: Follower ID
        purchase_id: Purchase ID
        attribution_data: Additional attribution info

    Returns:
        True if successful
    """
    purchases = manager._load_purchases(creator_id)

    for purchase in purchases:
        if purchase.purchase_id == purchase_id:
            purchase.attributed_to_bot = True
            purchase.follower_id = follower_id
            purchase.attribution_data = attribution_data or {}
            manager._save_purchases(creator_id, purchases)
            logger.info(f"Purchase {purchase_id} attributed to bot")
            return True

    return False


def get_revenue_stats(
    manager,
    creator_id: str,
    days: int = 30
) -> RevenueStats:
    """
    Get revenue statistics.

    Args:
        manager: PaymentManager instance
        creator_id: Creator ID
        days: Number of days to include

    Returns:
        RevenueStats object
    """
    purchases = manager._load_purchases(creator_id)

    # Filter by date if needed
    _cutoff = datetime.now(timezone.utc).isoformat()[:10]  # Just use all for now

    stats = RevenueStats()
    stats.by_platform = {}
    stats.by_product = {}

    for purchase in purchases:
        if purchase.status != PurchaseStatus.COMPLETED.value:
            continue

        stats.total_revenue += purchase.amount
        stats.total_purchases += 1

        if purchase.attributed_to_bot:
            stats.attributed_to_bot += purchase.amount
            stats.attributed_purchases += 1

        # By platform
        platform = purchase.platform
        stats.by_platform[platform] = stats.by_platform.get(platform, 0) + purchase.amount

        # By product
        product = purchase.product_name
        stats.by_product[product] = stats.by_product.get(product, 0) + purchase.amount

    return stats
