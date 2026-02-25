"""
Payment Manager — orchestrator that delegates to sub-modules.

Sub-modules:
- stripe_handler.py: Stripe webhook processing
- webhook_handler.py: Hotmart and PayPal webhook processing
- subscription_manager.py: Purchase recording, queries, and customer management
"""

import os
import json
import logging
from typing import Optional, List, Dict, Any

from core.payments.models import Purchase, RevenueStats

logger = logging.getLogger("clonnect-payments")


class PaymentManager:
    """
    Manager for payment processing and tracking.

    Handles webhooks from Stripe, Hotmart, and PayPal, records purchases,
    and attributes sales to the bot.
    """

    def __init__(self, storage_path: str = "data/payments"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        self._cache: Dict[str, List[Purchase]] = {}

        # Webhook secrets from environment
        self.stripe_webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
        self.hotmart_webhook_token = os.getenv("HOTMART_WEBHOOK_TOKEN", "")
        self.paypal_webhook_id = os.getenv("PAYPAL_WEBHOOK_ID", "")
        self.paypal_client_id = os.getenv("PAYPAL_CLIENT_ID", "")
        self.paypal_client_secret = os.getenv("PAYPAL_CLIENT_SECRET", "")
        self.paypal_mode = os.getenv("PAYPAL_MODE", "sandbox")

    # ==========================================================================
    # FILE OPERATIONS (shared by all sub-modules)
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
    # STRIPE — delegated to stripe_handler
    # ==========================================================================

    def verify_stripe_signature(self, payload: bytes, signature: str) -> bool:
        from .stripe_handler import verify_stripe_signature
        return verify_stripe_signature(self.stripe_webhook_secret, payload, signature)

    async def process_stripe_webhook(
        self, payload: dict, signature: str = "", raw_payload: bytes = None
    ) -> Dict[str, Any]:
        from .stripe_handler import process_stripe_webhook
        return await process_stripe_webhook(self, payload, signature, raw_payload)

    # ==========================================================================
    # HOTMART — delegated to webhook_handler
    # ==========================================================================

    def verify_hotmart_token(self, token: str) -> bool:
        from .webhook_handler import verify_hotmart_token
        return verify_hotmart_token(self.hotmart_webhook_token, token)

    async def process_hotmart_webhook(
        self, payload: dict, token: str = ""
    ) -> Dict[str, Any]:
        from .webhook_handler import process_hotmart_webhook
        return await process_hotmart_webhook(self, payload, token)

    # ==========================================================================
    # PAYPAL — delegated to webhook_handler
    # ==========================================================================

    async def verify_paypal_webhook(
        self, payload: bytes, headers: Dict[str, str]
    ) -> bool:
        from .webhook_handler import verify_paypal_webhook
        paypal_config = {
            "webhook_id": self.paypal_webhook_id,
            "client_id": self.paypal_client_id,
            "client_secret": self.paypal_client_secret,
            "mode": self.paypal_mode,
        }
        return await verify_paypal_webhook(paypal_config, payload, headers)

    async def process_paypal_webhook(
        self, payload: dict, headers: Dict[str, str] = None, raw_payload: bytes = None
    ) -> Dict[str, Any]:
        from .webhook_handler import process_paypal_webhook
        return await process_paypal_webhook(self, payload, headers, raw_payload)

    # ==========================================================================
    # PURCHASE RECORDING — delegated to subscription_manager
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
        from .subscription_manager import record_purchase
        return await record_purchase(
            self,
            creator_id=creator_id,
            follower_id=follower_id,
            product_id=product_id,
            product_name=product_name,
            amount=amount,
            currency=currency,
            platform=platform,
            external_id=external_id,
            customer_email=customer_email,
            customer_name=customer_name,
            metadata=metadata,
        )

    # ==========================================================================
    # PURCHASE QUERIES — delegated to subscription_manager
    # ==========================================================================

    def get_customer_purchases(
        self, creator_id: str, follower_id: str
    ) -> List[Dict[str, Any]]:
        from .subscription_manager import get_customer_purchases
        return get_customer_purchases(self, creator_id, follower_id)

    def get_all_purchases(
        self, creator_id: str, limit: int = 100, status: str = None
    ) -> List[Dict[str, Any]]:
        from .subscription_manager import get_all_purchases
        return get_all_purchases(self, creator_id, limit, status)

    def attribute_sale_to_bot(
        self,
        creator_id: str,
        follower_id: str,
        purchase_id: str,
        attribution_data: Dict[str, Any] = None
    ) -> bool:
        from .subscription_manager import attribute_sale_to_bot
        return attribute_sale_to_bot(self, creator_id, follower_id, purchase_id, attribution_data)

    def get_revenue_stats(self, creator_id: str, days: int = 30) -> RevenueStats:
        from .subscription_manager import get_revenue_stats
        return get_revenue_stats(self, creator_id, days)

    async def _find_follower_by_email(self, creator_id: str, email: str) -> str:
        from .subscription_manager import find_follower_by_email
        return await find_follower_by_email(creator_id, email)


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
