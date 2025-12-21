"""
Payment Integration System for Clonnect Creators.

Supports:
- Stripe (checkout.session.completed, payment_intent.succeeded)
- Hotmart (PURCHASE_COMPLETE, PURCHASE_APPROVED)

Provides:
- Webhook processing
- Purchase recording
- Customer attribution
- Revenue tracking

Storage: JSON files in data/payments/
"""

import os
import json
import hmac
import hashlib
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
import uuid

logger = logging.getLogger("clonnect-payments")


class PaymentPlatform(Enum):
    """Supported payment platforms"""
    STRIPE = "stripe"
    HOTMART = "hotmart"
    MANUAL = "manual"


class PurchaseStatus(Enum):
    """Purchase status"""
    PENDING = "pending"
    COMPLETED = "completed"
    REFUNDED = "refunded"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"


@dataclass
class Purchase:
    """Represents a purchase"""
    purchase_id: str
    creator_id: str
    follower_id: str
    product_id: str
    product_name: str
    amount: float
    currency: str
    platform: str  # stripe, hotmart, manual
    status: str
    timestamp: str
    external_id: str = ""  # Stripe/Hotmart transaction ID
    customer_email: str = ""
    customer_name: str = ""
    attributed_to_bot: bool = False
    attribution_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Purchase':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class RevenueStats:
    """Revenue statistics"""
    total_revenue: float = 0.0
    total_purchases: int = 0
    attributed_to_bot: float = 0.0
    attributed_purchases: int = 0
    by_platform: Dict[str, float] = field(default_factory=dict)
    by_product: Dict[str, float] = field(default_factory=dict)
    currency: str = "EUR"

    def to_dict(self) -> dict:
        return asdict(self)


class PaymentManager:
    """
    Manager for payment processing and tracking.

    Handles webhooks from Stripe and Hotmart, records purchases,
    and attributes sales to the bot.
    """

    def __init__(self, storage_path: str = "data/payments"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        self._cache: Dict[str, List[Purchase]] = {}

        # Webhook secrets from environment
        self.stripe_webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        self.hotmart_webhook_token = os.getenv("HOTMART_WEBHOOK_TOKEN", "")

    # ==========================================================================
    # FILE OPERATIONS
    # ==========================================================================

    def _get_purchases_file(self, creator_id: str) -> str:
        return os.path.join(self.storage_path, f"{creator_id}_purchases.json")

    def _load_purchases(self, creator_id: str) -> List[Purchase]:
        """Load purchases for a creator"""
        if creator_id in self._cache:
            return self._cache[creator_id]

        file_path = self._get_purchases_file(creator_id)
        purchases = []

        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    purchases = [Purchase.from_dict(p) for p in data]
            except Exception as e:
                logger.error(f"Error loading purchases: {e}")

        self._cache[creator_id] = purchases
        return purchases

    def _save_purchases(self, creator_id: str, purchases: List[Purchase]):
        """Save purchases for a creator"""
        file_path = self._get_purchases_file(creator_id)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump([p.to_dict() for p in purchases], f, indent=2, ensure_ascii=False)
            self._cache[creator_id] = purchases
        except Exception as e:
            logger.error(f"Error saving purchases: {e}")

    # ==========================================================================
    # STRIPE WEBHOOK
    # ==========================================================================

    def verify_stripe_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify Stripe webhook signature.

        Args:
            payload: Raw request body
            signature: Stripe-Signature header

        Returns:
            True if valid
        """
        if not self.stripe_webhook_secret:
            logger.warning("Stripe webhook secret not configured, skipping verification")
            return True

        try:
            # Parse signature header
            elements = dict(item.split("=") for item in signature.split(","))
            timestamp = elements.get("t", "")
            v1_signature = elements.get("v1", "")

            # Compute expected signature
            signed_payload = f"{timestamp}.{payload.decode()}"
            expected = hmac.new(
                self.stripe_webhook_secret.encode(),
                signed_payload.encode(),
                hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(expected, v1_signature)
        except Exception as e:
            logger.error(f"Error verifying Stripe signature: {e}")
            return False

    async def process_stripe_webhook(
        self,
        payload: dict,
        signature: str = "",
        raw_payload: bytes = None
    ) -> Dict[str, Any]:
        """
        Process Stripe webhook event.

        Supported events:
        - checkout.session.completed
        - payment_intent.succeeded

        Args:
            payload: Parsed JSON payload
            signature: Stripe-Signature header
            raw_payload: Raw bytes for signature verification

        Returns:
            Processing result
        """
        # Verify signature if secret is configured
        if self.stripe_webhook_secret and raw_payload and signature:
            if not self.verify_stripe_signature(raw_payload, signature):
                logger.warning("Invalid Stripe webhook signature")
                return {"status": "error", "reason": "invalid_signature"}

        event_type = payload.get("type", "")
        event_data = payload.get("data", {}).get("object", {})

        logger.info(f"Processing Stripe event: {event_type}")

        if event_type == "checkout.session.completed":
            return await self._handle_stripe_checkout_completed(event_data)
        elif event_type == "payment_intent.succeeded":
            return await self._handle_stripe_payment_succeeded(event_data)
        elif event_type == "charge.refunded":
            return await self._handle_stripe_refund(event_data)
        else:
            logger.info(f"Ignoring Stripe event: {event_type}")
            return {"status": "ignored", "event_type": event_type}

    async def _handle_stripe_checkout_completed(self, session: dict) -> Dict[str, Any]:
        """Handle Stripe checkout.session.completed event"""
        try:
            # Extract data
            customer_email = session.get("customer_details", {}).get("email", "")
            customer_name = session.get("customer_details", {}).get("name", "")
            amount = session.get("amount_total", 0) / 100  # Convert from cents
            currency = session.get("currency", "eur").upper()
            external_id = session.get("id", "")

            # Get metadata
            metadata = session.get("metadata", {})
            creator_id = metadata.get("creator_id", "manel")
            product_id = metadata.get("product_id", "")
            product_name = metadata.get("product_name", "Unknown Product")
            follower_id = metadata.get("follower_id", "")

            # If no follower_id, try to find by email
            if not follower_id and customer_email:
                follower_id = await self._find_follower_by_email(creator_id, customer_email)

            # Record purchase
            purchase = await self.record_purchase(
                creator_id=creator_id,
                follower_id=follower_id,
                product_id=product_id,
                product_name=product_name,
                amount=amount,
                currency=currency,
                platform=PaymentPlatform.STRIPE.value,
                external_id=external_id,
                customer_email=customer_email,
                customer_name=customer_name,
                metadata=metadata
            )

            logger.info(f"Stripe purchase recorded: {purchase.purchase_id}")

            return {
                "status": "ok",
                "purchase_id": purchase.purchase_id,
                "amount": amount,
                "currency": currency
            }

        except Exception as e:
            logger.error(f"Error processing Stripe checkout: {e}")
            return {"status": "error", "reason": str(e)}

    async def _handle_stripe_payment_succeeded(self, payment_intent: dict) -> Dict[str, Any]:
        """Handle Stripe payment_intent.succeeded event"""
        try:
            amount = payment_intent.get("amount", 0) / 100
            currency = payment_intent.get("currency", "eur").upper()
            external_id = payment_intent.get("id", "")

            metadata = payment_intent.get("metadata", {})
            creator_id = metadata.get("creator_id", "manel")
            product_id = metadata.get("product_id", "")
            product_name = metadata.get("product_name", "Unknown Product")
            follower_id = metadata.get("follower_id", "")

            # Check if already processed (avoid duplicates)
            purchases = self._load_purchases(creator_id)
            if any(p.external_id == external_id for p in purchases):
                logger.info(f"Payment {external_id} already processed")
                return {"status": "already_processed", "external_id": external_id}

            purchase = await self.record_purchase(
                creator_id=creator_id,
                follower_id=follower_id,
                product_id=product_id,
                product_name=product_name,
                amount=amount,
                currency=currency,
                platform=PaymentPlatform.STRIPE.value,
                external_id=external_id,
                metadata=metadata
            )

            return {
                "status": "ok",
                "purchase_id": purchase.purchase_id,
                "amount": amount
            }

        except Exception as e:
            logger.error(f"Error processing Stripe payment: {e}")
            return {"status": "error", "reason": str(e)}

    async def _handle_stripe_refund(self, charge: dict) -> Dict[str, Any]:
        """Handle Stripe charge.refunded event"""
        try:
            external_id = charge.get("payment_intent", "")
            creator_id = charge.get("metadata", {}).get("creator_id", "manel")

            purchases = self._load_purchases(creator_id)
            for purchase in purchases:
                if purchase.external_id == external_id:
                    purchase.status = PurchaseStatus.REFUNDED.value
                    break

            self._save_purchases(creator_id, purchases)

            return {"status": "ok", "action": "refund_recorded"}

        except Exception as e:
            logger.error(f"Error processing Stripe refund: {e}")
            return {"status": "error", "reason": str(e)}

    # ==========================================================================
    # HOTMART WEBHOOK
    # ==========================================================================

    def verify_hotmart_token(self, token: str) -> bool:
        """Verify Hotmart webhook token"""
        if not self.hotmart_webhook_token:
            logger.warning("Hotmart webhook token not configured, skipping verification")
            return True
        return hmac.compare_digest(token, self.hotmart_webhook_token)

    async def process_hotmart_webhook(
        self,
        payload: dict,
        token: str = ""
    ) -> Dict[str, Any]:
        """
        Process Hotmart webhook event.

        Supported events:
        - PURCHASE_COMPLETE
        - PURCHASE_APPROVED
        - PURCHASE_REFUNDED
        - PURCHASE_CANCELED

        Args:
            payload: Webhook payload
            token: X-Hotmart-Hottok header

        Returns:
            Processing result
        """
        # Verify token
        if self.hotmart_webhook_token and token:
            if not self.verify_hotmart_token(token):
                logger.warning("Invalid Hotmart webhook token")
                return {"status": "error", "reason": "invalid_token"}

        event_type = payload.get("event", "")
        data = payload.get("data", {})

        logger.info(f"Processing Hotmart event: {event_type}")

        if event_type in ["PURCHASE_COMPLETE", "PURCHASE_APPROVED"]:
            return await self._handle_hotmart_purchase(data)
        elif event_type in ["PURCHASE_REFUNDED", "PURCHASE_CANCELED"]:
            return await self._handle_hotmart_refund(data, event_type)
        else:
            logger.info(f"Ignoring Hotmart event: {event_type}")
            return {"status": "ignored", "event_type": event_type}

    async def _handle_hotmart_purchase(self, data: dict) -> Dict[str, Any]:
        """Handle Hotmart purchase event"""
        try:
            # Extract buyer info
            buyer = data.get("buyer", {})
            customer_email = buyer.get("email", "")
            customer_name = buyer.get("name", "")

            # Extract product info
            product = data.get("product", {})
            product_id = str(product.get("id", ""))
            product_name = product.get("name", "Unknown Product")

            # Extract purchase info
            purchase_data = data.get("purchase", {})
            external_id = purchase_data.get("transaction", "")
            amount = float(purchase_data.get("price", {}).get("value", 0))
            currency = purchase_data.get("price", {}).get("currency_code", "BRL")

            # Get creator_id from product name or metadata
            creator_id = data.get("creator_id", "manel")

            # Try to find follower
            follower_id = await self._find_follower_by_email(creator_id, customer_email)

            # Check for duplicates
            purchases = self._load_purchases(creator_id)
            if any(p.external_id == external_id for p in purchases):
                logger.info(f"Hotmart purchase {external_id} already processed")
                return {"status": "already_processed", "external_id": external_id}

            # Record purchase
            purchase = await self.record_purchase(
                creator_id=creator_id,
                follower_id=follower_id,
                product_id=product_id,
                product_name=product_name,
                amount=amount,
                currency=currency,
                platform=PaymentPlatform.HOTMART.value,
                external_id=external_id,
                customer_email=customer_email,
                customer_name=customer_name,
                metadata=data
            )

            logger.info(f"Hotmart purchase recorded: {purchase.purchase_id}")

            return {
                "status": "ok",
                "purchase_id": purchase.purchase_id,
                "amount": amount,
                "currency": currency
            }

        except Exception as e:
            logger.error(f"Error processing Hotmart purchase: {e}")
            return {"status": "error", "reason": str(e)}

    async def _handle_hotmart_refund(self, data: dict, event_type: str) -> Dict[str, Any]:
        """Handle Hotmart refund/cancel event"""
        try:
            purchase_data = data.get("purchase", {})
            external_id = purchase_data.get("transaction", "")
            creator_id = data.get("creator_id", "manel")

            purchases = self._load_purchases(creator_id)
            for purchase in purchases:
                if purchase.external_id == external_id:
                    if event_type == "PURCHASE_REFUNDED":
                        purchase.status = PurchaseStatus.REFUNDED.value
                    else:
                        purchase.status = PurchaseStatus.CANCELLED.value
                    break

            self._save_purchases(creator_id, purchases)

            return {"status": "ok", "action": f"{event_type.lower()}_recorded"}

        except Exception as e:
            logger.error(f"Error processing Hotmart {event_type}: {e}")
            return {"status": "error", "reason": str(e)}

    # ==========================================================================
    # PURCHASE RECORDING
    # ==========================================================================

    async def record_purchase(
        self,
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
        purchases = self._load_purchases(creator_id)
        purchases.append(purchase)
        self._save_purchases(creator_id, purchases)

        # Update follower memory
        if follower_id:
            await self._update_follower_as_customer(creator_id, follower_id, product_id)

            # Try to attribute to bot
            if await self._check_bot_attribution(creator_id, follower_id):
                purchase.attributed_to_bot = True
                self._save_purchases(creator_id, purchases)

        # Track analytics
        await self._track_purchase_analytics(creator_id, follower_id, product_id, amount, platform)

        logger.info(f"Purchase recorded: {purchase.purchase_id} - {amount} {currency}")
        return purchase

    async def _update_follower_as_customer(
        self,
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

            # Cancel nurturing sequences
            await self._cancel_nurturing_for_customer(creator_id, follower_id)

        except Exception as e:
            logger.error(f"Error updating follower as customer: {e}")

    async def _cancel_nurturing_for_customer(self, creator_id: str, follower_id: str):
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

    async def _check_bot_attribution(self, creator_id: str, follower_id: str) -> bool:
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
        self,
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

    async def _find_follower_by_email(self, creator_id: str, email: str) -> str:
        """Try to find follower ID by email"""
        # This would require storing email in follower data
        # For now, return empty string
        return ""

    # ==========================================================================
    # PURCHASE QUERIES
    # ==========================================================================

    def get_customer_purchases(
        self,
        creator_id: str,
        follower_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all purchases for a customer.

        Args:
            creator_id: Creator ID
            follower_id: Follower ID

        Returns:
            List of purchases
        """
        purchases = self._load_purchases(creator_id)
        customer_purchases = [
            p.to_dict() for p in purchases
            if p.follower_id == follower_id
        ]
        return sorted(customer_purchases, key=lambda x: x["timestamp"], reverse=True)

    def get_all_purchases(
        self,
        creator_id: str,
        limit: int = 100,
        status: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get all purchases for a creator.

        Args:
            creator_id: Creator ID
            limit: Maximum number to return
            status: Filter by status

        Returns:
            List of purchases
        """
        purchases = self._load_purchases(creator_id)

        if status:
            purchases = [p for p in purchases if p.status == status]

        # Sort by timestamp descending
        purchases.sort(key=lambda x: x.timestamp, reverse=True)

        return [p.to_dict() for p in purchases[:limit]]

    def attribute_sale_to_bot(
        self,
        creator_id: str,
        follower_id: str,
        purchase_id: str,
        attribution_data: Dict[str, Any] = None
    ) -> bool:
        """
        Manually attribute a sale to the bot.

        Args:
            creator_id: Creator ID
            follower_id: Follower ID
            purchase_id: Purchase ID
            attribution_data: Additional attribution info

        Returns:
            True if successful
        """
        purchases = self._load_purchases(creator_id)

        for purchase in purchases:
            if purchase.purchase_id == purchase_id:
                purchase.attributed_to_bot = True
                purchase.follower_id = follower_id
                purchase.attribution_data = attribution_data or {}
                self._save_purchases(creator_id, purchases)
                logger.info(f"Purchase {purchase_id} attributed to bot")
                return True

        return False

    def get_revenue_stats(
        self,
        creator_id: str,
        days: int = 30
    ) -> RevenueStats:
        """
        Get revenue statistics.

        Args:
            creator_id: Creator ID
            days: Number of days to include

        Returns:
            RevenueStats object
        """
        purchases = self._load_purchases(creator_id)

        # Filter by date if needed
        cutoff = datetime.now(timezone.utc).isoformat()[:10]  # Just use all for now

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


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_payment_manager: Optional[PaymentManager] = None


def get_payment_manager() -> PaymentManager:
    """Get or create payment manager singleton"""
    global _payment_manager
    if _payment_manager is None:
        _payment_manager = PaymentManager()
    return _payment_manager
