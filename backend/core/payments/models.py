"""
Payment data models for Clonnect Creators.

Enums and dataclasses used across the payment system.
"""

from typing import Dict, Any
from dataclasses import dataclass, asdict, field
from enum import Enum


class PaymentPlatform(Enum):
    """Supported payment platforms"""
    STRIPE = "stripe"
    HOTMART = "hotmart"
    PAYPAL = "paypal"
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
