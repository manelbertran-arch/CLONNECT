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

from core.payments.models import (  # noqa: F401
    PaymentPlatform,
    PurchaseStatus,
    Purchase,
    RevenueStats,
)
from core.payments.manager import (  # noqa: F401
    PaymentManager,
    get_payment_manager,
)

__all__ = [
    "PaymentPlatform",
    "PurchaseStatus",
    "Purchase",
    "RevenueStats",
    "PaymentManager",
    "get_payment_manager",
]
