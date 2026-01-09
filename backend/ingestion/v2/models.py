"""
Data models for Zero-Hallucination Ingestion System V2
Every piece of data must have provenance (source_url + source_html)
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class ProductSignal(str, Enum):
    """Signals that indicate something is a real product"""
    DEDICATED_PAGE = "dedicated_page"      # Has its own URL (/servicio/X)
    CTA_PRESENT = "cta_present"            # Has call-to-action (comprar, reservar)
    PRICE_VISIBLE = "price_visible"        # Has visible price
    SUBSTANTIAL_DESC = "substantial_description"  # >50 words description
    PAYMENT_LINK = "payment_link"          # Links to payment/booking
    CLEAR_TITLE = "clear_title"            # Has clear h1 title
    IN_NAVIGATION = "in_navigation"        # Listed in site navigation


@dataclass
class ScrapedPage:
    """Raw scraped page with full HTML"""
    url: str
    raw_html: str
    extracted_text: str
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    checksum: str = ""


@dataclass
class SignalResult:
    """Result of signal detection on a page"""
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    price_text: Optional[str] = None  # Original text where price was found
    source_html: str = ""
    matched: List[str] = field(default_factory=list)
    count: int = 0


@dataclass
class DetectedProduct:
    """A product detected with provenance proof"""
    name: str
    description: Optional[str]
    price: Optional[float]  # NULL if not found, NEVER invented
    price_text: Optional[str]  # Original text (e.g., "APÚNTATE POR SÓLO €22")
    source_url: str  # REQUIRED - where this was found
    source_html: str  # REQUIRED - HTML proof
    signals_matched: List[str]
    confidence: float  # 0-1 based on signals count
    verified: bool = False
    verification_note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "price": self.price,
            "price_text": self.price_text,
            "source_url": self.source_url,
            "source_html": self.source_html[:500] + "..." if len(self.source_html) > 500 else self.source_html,
            "signals_matched": self.signals_matched,
            "confidence": self.confidence,
            "verified": self.verified,
            "verification_note": self.verification_note
        }


@dataclass
class CheckResult:
    """Result of a single sanity check"""
    name: str
    passed: bool
    message: str


@dataclass
class VerificationResult:
    """Result of sanity verification"""
    passed: bool
    status: str  # 'success', 'needs_review', 'failed'
    checks: List[CheckResult]
    products: List[DetectedProduct]


@dataclass
class IngestionResult:
    """Complete ingestion result"""
    creator_id: str
    website_url: str
    pages_scraped: int
    service_pages_found: int
    products_detected: int
    products_verified: int
    products: List[DetectedProduct]
    sanity_checks: List[CheckResult]
    status: str  # 'success', 'needs_review', 'failed', 'aborted'
    errors: List[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "creator_id": self.creator_id,
            "website_url": self.website_url,
            "pages_scraped": self.pages_scraped,
            "service_pages_found": self.service_pages_found,
            "products_detected": self.products_detected,
            "products_verified": self.products_verified,
            "products": [p.to_dict() for p in self.products],
            "sanity_checks": [{"name": c.name, "passed": c.passed, "message": c.message} for c in self.sanity_checks],
            "status": self.status,
            "errors": self.errors,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }
