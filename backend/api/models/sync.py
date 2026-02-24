"""Sync models: SyncQueue, SyncState."""
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

try:
    from api.database import Base
except ImportError:
    from database import Base


class SyncQueue(Base):
    """
    Cola de jobs de sincronización.
    Cada conversación es un job separado para permitir retry granular.
    """

    __tablename__ = "sync_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(String(100), nullable=False, index=True)
    conversation_id = Column(String(255), nullable=False)
    status = Column(String(20), default="pending")  # pending, processing, done, failed
    attempts = Column(Integer, default=0)
    last_error = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("creator_id", "conversation_id", name="uq_sync_queue_creator_conversation"),
        {"extend_existing": True},
    )


class SyncState(Base):
    """
    Estado global del sync por creator.
    Permite trackear progreso y manejar rate limits.
    """

    __tablename__ = "sync_state"
    __table_args__ = {"extend_existing": True}

    creator_id = Column(String(100), primary_key=True)
    status = Column(String(20), default="idle")  # idle, running, paused, rate_limited, completed
    last_sync_at = Column(DateTime(timezone=True))
    rate_limit_until = Column(DateTime(timezone=True))  # No intentar hasta esta hora
    conversations_synced = Column(Integer, default=0)
    conversations_total = Column(Integer, default=0)
    messages_saved = Column(Integer, default=0)
    current_conversation = Column(String(255))  # Conversación actual siendo procesada
    error_count = Column(Integer, default=0)
    last_error = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
