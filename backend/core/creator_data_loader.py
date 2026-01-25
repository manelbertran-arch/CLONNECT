"""
Creator Data Loader - Unified data loading for LLM context injection.

This module loads ALL creator data in a single optimized call:
- Products with prices
- Booking links
- Payment methods (Stripe, Bizum, Bank, PayPal, etc.)
- Lead magnets (free products)
- FAQs from knowledge base
- Creator profile (name, tone, vocabulary)
- Tone profile from DB

Used for context injection into LLM prompts, replacing multiple fast-paths.

Anti-hallucination methods:
- get_known_prices() -> validates prices mentioned by LLM
- get_known_links() -> validates URLs mentioned by LLM
"""

import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Check if PostgreSQL is available
DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)


@dataclass
class ProductInfo:
    """Product/service information for LLM context."""

    id: str
    name: str
    description: str = ""
    short_description: str = ""
    price: float = 0.0
    currency: str = "EUR"
    payment_link: str = ""
    category: str = "product"  # product, service, resource
    product_type: str = "otro"
    is_active: bool = True
    is_free: bool = False
    source_url: str = ""  # For anti-hallucination verification

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_db_row(cls, row) -> "ProductInfo":
        """Create from SQLAlchemy Product model."""
        return cls(
            id=str(row.id),
            name=row.name or "",
            description=row.description or "",
            short_description=row.short_description or "",
            price=float(row.price or 0),
            currency=row.currency or "EUR",
            payment_link=row.payment_link or "",
            category=row.category or "product",
            product_type=row.product_type or "otro",
            is_active=row.is_active if row.is_active is not None else True,
            is_free=row.is_free if row.is_free is not None else False,
            source_url=row.source_url or "",
        )


@dataclass
class BookingInfo:
    """Booking link information for LLM context."""

    id: str
    meeting_type: str  # discovery, consultation, coaching, custom
    title: str
    description: str = ""
    duration_minutes: int = 30
    platform: str = "manual"  # calendly, zoom, google-meet, etc.
    url: str = ""
    price: int = 0  # Price in euros (0 = free)
    is_active: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_db_row(cls, row) -> "BookingInfo":
        """Create from SQLAlchemy BookingLink model."""
        return cls(
            id=str(row.id),
            meeting_type=row.meeting_type or "discovery",
            title=row.title or "",
            description=row.description or "",
            duration_minutes=row.duration_minutes or 30,
            platform=row.platform or "manual",
            url=row.url or "",
            price=row.price or 0,
            is_active=row.is_active if row.is_active is not None else True,
        )


@dataclass
class FAQInfo:
    """FAQ information for LLM context."""

    id: str
    question: str
    answer: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_db_row(cls, row) -> "FAQInfo":
        """Create from SQLAlchemy KnowledgeBase model."""
        return cls(
            id=str(row.id),
            question=row.question or "",
            answer=row.answer or "",
        )


@dataclass
class PaymentMethods:
    """Alternative payment methods configuration."""

    bizum_enabled: bool = False
    bizum_phone: str = ""
    bank_enabled: bool = False
    bank_iban: str = ""
    bank_holder: str = ""
    revolut_enabled: bool = False
    revolut_link: str = ""
    paypal_enabled: bool = False
    paypal_email: str = ""
    other_enabled: bool = False
    other_instructions: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> "PaymentMethods":
        """Create from JSON stored in creators.other_payment_methods."""
        if not data:
            return cls()

        bizum = data.get("bizum", {}) or {}
        bank = data.get("bank_transfer", {}) or {}
        revolut = data.get("revolut", {}) or {}
        paypal = data.get("paypal", {}) or {}
        other = data.get("other", {}) or {}

        return cls(
            bizum_enabled=bool(bizum.get("enabled")),
            bizum_phone=bizum.get("phone", ""),
            bank_enabled=bool(bank.get("enabled")),
            bank_iban=bank.get("iban", ""),
            bank_holder=bank.get("holder_name", ""),
            revolut_enabled=bool(revolut.get("enabled")),
            revolut_link=revolut.get("link", ""),
            paypal_enabled=bool(paypal.get("enabled")),
            paypal_email=paypal.get("email", ""),
            other_enabled=bool(other.get("enabled")),
            other_instructions=other.get("instructions", ""),
        )

    def get_available_methods(self) -> List[str]:
        """Return list of available payment method names."""
        methods = []
        if self.bizum_enabled and self.bizum_phone:
            methods.append("bizum")
        if self.bank_enabled and self.bank_iban:
            methods.append("bank_transfer")
        if self.revolut_enabled and self.revolut_link:
            methods.append("revolut")
        if self.paypal_enabled and self.paypal_email:
            methods.append("paypal")
        if self.other_enabled and self.other_instructions:
            methods.append("other")
        return methods


@dataclass
class ToneProfileInfo:
    """Creator's tone/personality profile for LLM context."""

    dialect: str = "neutral"  # neutral, rioplatense, mexican, etc.
    formality: str = "informal"  # formal, informal, mixed
    energy: str = "medium"  # low, medium, high
    humor: bool = False
    emojis: str = "moderate"  # none, minimal, moderate, heavy
    signature_phrases: List[str] = field(default_factory=list)
    vocabulary: List[str] = field(default_factory=list)
    topics_to_avoid: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> "ToneProfileInfo":
        """Create from JSON stored in tone_profiles.profile_data."""
        if not data:
            return cls()

        return cls(
            dialect=data.get("dialect", "neutral"),
            formality=data.get("formality", "informal"),
            energy=data.get("energy", "medium"),
            humor=bool(data.get("humor", False)),
            emojis=data.get("emojis", "moderate"),
            signature_phrases=data.get("signature_phrases", []) or [],
            vocabulary=data.get("vocabulary", []) or [],
            topics_to_avoid=data.get("topics_to_avoid", []) or [],
        )


@dataclass
class CreatorProfile:
    """Creator's basic profile information."""

    id: str = ""
    name: str = ""
    clone_name: str = ""
    clone_tone: str = "friendly"
    clone_vocabulary: str = ""
    welcome_message: str = ""
    bot_active: bool = False
    knowledge_about: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CreatorData:
    """
    Complete creator data for LLM context injection.

    This is the main data structure that aggregates ALL creator information
    needed for generating contextual responses.
    """

    creator_id: str
    profile: CreatorProfile = field(default_factory=CreatorProfile)
    products: List[ProductInfo] = field(default_factory=list)
    booking_links: List[BookingInfo] = field(default_factory=list)
    payment_methods: PaymentMethods = field(default_factory=PaymentMethods)
    lead_magnets: List[ProductInfo] = field(default_factory=list)
    faqs: List[FAQInfo] = field(default_factory=list)
    tone_profile: ToneProfileInfo = field(default_factory=ToneProfileInfo)
    loaded_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    # --- Anti-hallucination validation methods ---

    def get_known_prices(self) -> Dict[str, float]:
        """
        Get all known product prices for anti-hallucination validation.

        Returns:
            Dict mapping product name (lowercase) to price.
            Used to validate that prices mentioned by LLM actually exist.
        """
        prices = {}
        for p in self.products:
            if p.price > 0:
                prices[p.name.lower()] = p.price
                # Also add without accents for fuzzy matching
                prices[_remove_accents(p.name.lower())] = p.price
        for p in self.lead_magnets:
            if p.price > 0:
                prices[p.name.lower()] = p.price
        for b in self.booking_links:
            if b.price > 0:
                prices[b.title.lower()] = float(b.price)
        return prices

    def get_known_links(self) -> List[str]:
        """
        Get all known URLs for anti-hallucination validation.

        Returns:
            List of valid URLs that the LLM can mention.
            Used to validate that URLs mentioned by LLM actually exist.
        """
        links = []
        for p in self.products:
            if p.payment_link and p.payment_link.startswith("http"):
                links.append(p.payment_link)
        for p in self.lead_magnets:
            if p.payment_link and p.payment_link.startswith("http"):
                links.append(p.payment_link)
        for b in self.booking_links:
            if b.url and b.url.startswith("http"):
                links.append(b.url)
        if self.payment_methods.revolut_link:
            links.append(self.payment_methods.revolut_link)
        return links

    def get_product_by_name(self, name: str) -> Optional[ProductInfo]:
        """Find product by name (case-insensitive partial match)."""
        name_lower = name.lower()
        for p in self.products + self.lead_magnets:
            if name_lower in p.name.lower() or p.name.lower() in name_lower:
                return p
        return None

    def get_featured_product(self) -> Optional[ProductInfo]:
        """Get the main/featured product (highest price with payment link)."""
        priced = [p for p in self.products if p.price > 0 and p.payment_link]
        if priced:
            return max(priced, key=lambda p: p.price)
        if self.products:
            return self.products[0]
        return None

    def has_payment_options(self) -> bool:
        """Check if creator has any payment option configured."""
        has_product_links = any(p.payment_link for p in self.products)
        has_alt_payments = bool(self.payment_methods.get_available_methods())
        return has_product_links or has_alt_payments

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "creator_id": self.creator_id,
            "profile": self.profile.to_dict(),
            "products": [p.to_dict() for p in self.products],
            "booking_links": [b.to_dict() for b in self.booking_links],
            "payment_methods": self.payment_methods.to_dict(),
            "lead_magnets": [p.to_dict() for p in self.lead_magnets],
            "faqs": [f.to_dict() for f in self.faqs],
            "tone_profile": self.tone_profile.to_dict(),
            "loaded_at": self.loaded_at,
        }


def _remove_accents(text: str) -> str:
    """Remove accents for fuzzy matching."""
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
        "ñ": "n",
        "Á": "A",
        "É": "E",
        "Í": "I",
        "Ó": "O",
        "Ú": "U",
        "Ü": "U",
        "Ñ": "N",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


# =============================================================================
# MAIN LOADER FUNCTION
# =============================================================================


def load_creator_data(creator_id: str) -> CreatorData:
    """
    Load ALL creator data in optimized database queries.

    This is the main entry point for the module. It loads:
    - Creator profile from `creators` table
    - Products from `products` table
    - Booking links from `booking_links` table
    - FAQs from `knowledge_base` table
    - Tone profile from `tone_profiles` table
    - Payment methods from `creators.other_payment_methods` JSON

    Uses JOINs where possible to minimize N+1 queries.

    Args:
        creator_id: Creator name (e.g., 'stefano') or UUID

    Returns:
        CreatorData with all information loaded
    """
    data = CreatorData(creator_id=creator_id)

    if not USE_POSTGRES:
        logger.warning(f"PostgreSQL not configured, returning empty CreatorData for {creator_id}")
        return data

    try:
        from api.database import SessionLocal

        if SessionLocal is None:
            logger.warning("SessionLocal not available")
            return data
    except ImportError:
        logger.warning("Could not import database module")
        return data

    session = SessionLocal()
    try:
        # Import models
        from api.models import BookingLink, Creator, KnowledgeBase, Product, ToneProfile
        from sqlalchemy import text

        # 1. Load creator profile
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            # Try by UUID
            try:
                creator = (
                    session.query(Creator)
                    .filter(text("id::text = :cid"))
                    .params(cid=creator_id)
                    .first()
                )
            except Exception:
                pass

        if not creator:
            logger.warning(f"Creator '{creator_id}' not found in database")
            return data

        creator_uuid = creator.id

        # Fill profile
        data.profile = CreatorProfile(
            id=str(creator_uuid),
            name=creator.name or "",
            clone_name=creator.clone_name or creator.name or "",
            clone_tone=creator.clone_tone or "friendly",
            clone_vocabulary=creator.clone_vocabulary or "",
            welcome_message=creator.welcome_message or "",
            bot_active=bool(creator.bot_active),
            knowledge_about=creator.knowledge_about or {},
        )

        # Fill payment methods from JSON column
        data.payment_methods = PaymentMethods.from_json(creator.other_payment_methods or {})

        # 2. Load products (single query)
        products = session.query(Product).filter_by(creator_id=creator_uuid, is_active=True).all()
        for p in products:
            product_info = ProductInfo.from_db_row(p)
            if product_info.is_free or product_info.price == 0:
                data.lead_magnets.append(product_info)
            else:
                data.products.append(product_info)

        logger.debug(f"Loaded {len(data.products)} products, {len(data.lead_magnets)} lead magnets")

        # 3. Load booking links (single query)
        # Note: BookingLink uses creator_id as string, not UUID
        booking_links = (
            session.query(BookingLink).filter_by(creator_id=creator_id, is_active=True).all()
        )
        # Also try with UUID string
        if not booking_links:
            booking_links = (
                session.query(BookingLink)
                .filter_by(creator_id=str(creator_uuid), is_active=True)
                .all()
            )
        for b in booking_links:
            data.booking_links.append(BookingInfo.from_db_row(b))

        logger.debug(f"Loaded {len(data.booking_links)} booking links")

        # 4. Load FAQs (single query)
        faqs = session.query(KnowledgeBase).filter_by(creator_id=creator_uuid).all()
        for f in faqs:
            data.faqs.append(FAQInfo.from_db_row(f))

        logger.debug(f"Loaded {len(data.faqs)} FAQs")

        # 5. Load tone profile (single query)
        tone = session.query(ToneProfile).filter_by(creator_id=creator_id).first()
        if tone and tone.profile_data:
            data.tone_profile = ToneProfileInfo.from_json(tone.profile_data)

        logger.info(
            f"CreatorData loaded for '{creator_id}': "
            f"{len(data.products)} products, "
            f"{len(data.lead_magnets)} lead magnets, "
            f"{len(data.booking_links)} booking links, "
            f"{len(data.faqs)} FAQs"
        )

        return data

    except Exception as e:
        logger.error(f"Error loading creator data for {creator_id}: {e}")
        import traceback

        traceback.print_exc()
        return data

    finally:
        session.close()


# =============================================================================
# CACHE LAYER (optional, for performance)
# =============================================================================

_creator_data_cache: Dict[str, CreatorData] = {}
_cache_timestamps: Dict[str, float] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


def get_creator_data(creator_id: str, use_cache: bool = True) -> CreatorData:
    """
    Get creator data with optional caching.

    Args:
        creator_id: Creator name or UUID
        use_cache: Whether to use cached data (default True)

    Returns:
        CreatorData instance
    """
    import time

    if use_cache and creator_id in _creator_data_cache:
        cache_age = time.time() - _cache_timestamps.get(creator_id, 0)
        if cache_age < _CACHE_TTL_SECONDS:
            logger.debug(f"Using cached CreatorData for {creator_id} (age: {cache_age:.1f}s)")
            return _creator_data_cache[creator_id]

    # Load fresh data
    data = load_creator_data(creator_id)

    # Cache it
    _creator_data_cache[creator_id] = data
    _cache_timestamps[creator_id] = time.time()

    return data


def invalidate_creator_cache(creator_id: str):
    """Invalidate cached data for a creator."""
    if creator_id in _creator_data_cache:
        del _creator_data_cache[creator_id]
    if creator_id in _cache_timestamps:
        del _cache_timestamps[creator_id]
    logger.debug(f"Cache invalidated for {creator_id}")


def clear_all_cache():
    """Clear all cached creator data."""
    _creator_data_cache.clear()
    _cache_timestamps.clear()
    logger.debug("All creator data cache cleared")


# =============================================================================
# RAG INTEGRATION
# =============================================================================


def get_rag_context(creator_id: str, query: str, top_k: int = 3) -> List[Dict]:
    """
    Get relevant RAG documents for a query.

    Integrates with core/rag/semantic.py for semantic search.

    Args:
        creator_id: Creator name
        query: User's message/query
        top_k: Number of results to return

    Returns:
        List of relevant document dicts with 'text', 'score', 'source_url'
    """
    try:
        from core.rag.semantic import get_semantic_rag

        rag = get_semantic_rag()

        # Ensure RAG is hydrated for this creator
        rag.load_from_db(creator_id)

        # Search
        results = rag.search(query, top_k=top_k, creator_id=creator_id)

        return [
            {
                "text": r.get("text", ""),
                "score": r.get("score", 0.0),
                "source_url": r.get("metadata", {}).get("source_url", ""),
                "title": r.get("metadata", {}).get("title", ""),
            }
            for r in results
        ]

    except Exception as e:
        logger.error(f"Error getting RAG context: {e}")
        return []


# =============================================================================
# PROMPT FORMATTING HELPERS
# =============================================================================


def format_products_for_prompt(data: CreatorData, include_lead_magnets: bool = True) -> str:
    """
    Format products as text for LLM prompt injection.

    Returns a structured text block suitable for system prompts.
    """
    if not data.products and not data.lead_magnets:
        return ""

    lines = ["=== MIS PRODUCTOS/SERVICIOS ==="]

    # Paid products first
    for p in data.products:
        price_text = f"{int(p.price)}€" if p.price > 0 else "Precio a consultar"
        link_text = f" | Link: {p.payment_link}" if p.payment_link else ""
        desc = p.short_description or p.description[:100] if p.description else ""
        lines.append(f"- {p.name}: {price_text}{link_text}")
        if desc:
            lines.append(f"  {desc}")

    # Lead magnets
    if include_lead_magnets and data.lead_magnets:
        lines.append("\n=== RECURSOS GRATUITOS ===")
        for p in data.lead_magnets:
            link_text = f" | Link: {p.payment_link}" if p.payment_link else ""
            lines.append(f"- {p.name} (GRATIS){link_text}")

    return "\n".join(lines)


def format_booking_for_prompt(data: CreatorData) -> str:
    """
    Format booking links as text for LLM prompt injection.
    """
    if not data.booking_links:
        return ""

    lines = ["=== LINKS DE RESERVA ==="]
    for b in data.booking_links:
        price_text = f" ({b.price}€)" if b.price > 0 else " (Gratis)"
        duration = f" - {b.duration_minutes}min" if b.duration_minutes else ""
        lines.append(f"- {b.title}{price_text}{duration}")
        if b.url:
            lines.append(f"  Link: {b.url}")

    return "\n".join(lines)


def format_payment_methods_for_prompt(data: CreatorData) -> str:
    """
    Format payment methods as text for LLM prompt injection.
    """
    methods = data.payment_methods
    available = methods.get_available_methods()

    if not available:
        return ""

    lines = ["=== METODOS DE PAGO ALTERNATIVOS ==="]

    if methods.bizum_enabled and methods.bizum_phone:
        lines.append(f"- Bizum: {methods.bizum_phone}")

    if methods.bank_enabled and methods.bank_iban:
        holder = f" ({methods.bank_holder})" if methods.bank_holder else ""
        lines.append(f"- Transferencia bancaria: {methods.bank_iban}{holder}")

    if methods.revolut_enabled and methods.revolut_link:
        lines.append(f"- Revolut: {methods.revolut_link}")

    if methods.paypal_enabled and methods.paypal_email:
        lines.append(f"- PayPal: {methods.paypal_email}")

    if methods.other_enabled and methods.other_instructions:
        lines.append(f"- Otro: {methods.other_instructions}")

    return "\n".join(lines)


def format_faqs_for_prompt(data: CreatorData, max_faqs: int = 5) -> str:
    """
    Format FAQs as text for LLM prompt injection.
    """
    if not data.faqs:
        return ""

    lines = ["=== PREGUNTAS FRECUENTES ==="]
    for faq in data.faqs[:max_faqs]:
        lines.append(f"P: {faq.question}")
        lines.append(f"R: {faq.answer}")
        lines.append("")

    return "\n".join(lines)


def build_creator_context_prompt(
    creator_id: str,
    include_products: bool = True,
    include_booking: bool = True,
    include_payments: bool = True,
    include_faqs: bool = True,
    max_faqs: int = 5,
) -> str:
    """
    Build complete creator context for LLM prompt injection.

    This is the main function to get a formatted context block
    suitable for adding to system prompts.

    Args:
        creator_id: Creator name
        include_products: Include products section
        include_booking: Include booking links section
        include_payments: Include payment methods section
        include_faqs: Include FAQs section
        max_faqs: Maximum number of FAQs to include

    Returns:
        Formatted context string for prompt injection
    """
    data = get_creator_data(creator_id)

    sections = []

    if include_products:
        products_text = format_products_for_prompt(data)
        if products_text:
            sections.append(products_text)

    if include_booking:
        booking_text = format_booking_for_prompt(data)
        if booking_text:
            sections.append(booking_text)

    if include_payments:
        payments_text = format_payment_methods_for_prompt(data)
        if payments_text:
            sections.append(payments_text)

    if include_faqs:
        faqs_text = format_faqs_for_prompt(data, max_faqs)
        if faqs_text:
            sections.append(faqs_text)

    if not sections:
        return ""

    return "\n\n".join(sections)
