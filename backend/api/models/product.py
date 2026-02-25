"""Product models: Product, ProductAnalytics."""
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

try:
    from api.database import Base
except ImportError:
    from database import Base


class Product(Base):
    __tablename__ = "products"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), index=True)  # Indexed: filtered in every product endpoint
    name = Column(String(255), nullable=False)
    description = Column(Text)
    short_description = Column(String(300))  # Descripción corta para cards
    # Taxonomía: category + product_type
    category = Column(String(20), default="product")  # product, service, resource
    product_type = Column(String(50), default="otro")  # Depende de category:
    # product: ebook, curso, plantilla, membership, otro
    # service: coaching, mentoria, consultoria, call, sesion, otro
    # resource: podcast, blog, youtube, newsletter, free_guide, otro
    price = Column(Float)
    currency = Column(String(10), default="EUR")
    is_free = Column(Boolean, default=False)  # True para discovery calls gratuitas
    payment_link = Column(String(500), default="")  # Stripe/PayPal/Calendly link
    is_active = Column(Boolean, default=True)
    # Anti-hallucination fields: source tracking
    source_url = Column(Text)  # URL where product info was found
    price_verified = Column(Boolean, default=False)  # True if price was extracted from source
    confidence = Column(Float, default=0.0)  # 0.0-1.0 extraction confidence
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # ORM relationships
    creator = relationship("Creator", back_populates="products", lazy="joined")


class ProductAnalytics(Base):
    """
    Per-product daily analytics.
    Tracks mentions, questions, objections, and conversions per product.
    """

    __tablename__ = "product_analytics"
    __table_args__ = (
        Index("idx_product_analytics_creator_date", "creator_id", "product_id", "date"),
        {"extend_existing": True},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(100), nullable=False)
    creator_id = Column(String(100), nullable=False, index=True)
    date = Column(Date, nullable=False)

    mentions = Column(Integer, default=0)
    questions = Column(Integer, default=0)
    objections = Column(Integer, default=0)
    link_clicks = Column(Integer, default=0)
    conversions = Column(Integer, default=0)
    revenue = Column(Float, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
