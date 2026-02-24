"""Nurturing models: NurturingSequence, EmailAskTracking."""
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

try:
    from api.database import Base
except ImportError:
    from database import Base


class NurturingSequence(Base):
    __tablename__ = "nurturing_sequences"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), index=True)  # Indexed: filtered in nurturing queries
    type = Column(String(50), nullable=False)
    name = Column(String(255))
    is_active = Column(Boolean, default=True)
    steps = Column(JSON, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EmailAskTracking(Base):
    """
    Tracks email ask attempts per user to implement progressive asking strategy.
    Levels: 0=never asked, 1=subtle, 2=value offer, 3=irresistible, 4=necessary
    """

    __tablename__ = "email_ask_tracking"
    __table_args__ = {"extend_existing": True}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    creator_id = Column(UUID(as_uuid=True), ForeignKey("creators.id"), index=True)
    platform = Column(String(50), nullable=False)
    platform_user_id = Column(String(255), nullable=False, index=True)
    ask_level = Column(Integer, default=0)  # 0-4
    last_asked_at = Column(DateTime(timezone=True))
    declined_count = Column(Integer, default=0)
    captured_email = Column(String(255))  # Email once captured
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
