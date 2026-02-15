"""
Nurturing Database Storage - PostgreSQL backend for follow-ups.

This module provides a PostgreSQL-based storage layer for nurturing followups,
replacing the JSON file storage for better scalability and querying.

Feature Flag:
    NURTURING_USE_DB=true  # Enable PostgreSQL storage
    NURTURING_USE_DB=false # Use JSON files (default)
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from contextlib import contextmanager

from sqlalchemy import Column, String, Integer, Text, DateTime, and_, or_, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import SQLAlchemyError

from api.database import Base, get_db_session, SessionLocal

logger = logging.getLogger(__name__)

# Feature flag for PostgreSQL storage
NURTURING_USE_DB = os.getenv("NURTURING_USE_DB", "true").lower() == "true"


class NurturingFollowupDB(Base):
    """SQLAlchemy model for nurturing_followups table."""
    __tablename__ = "nurturing_followups"

    id = Column(String(255), primary_key=True)
    creator_id = Column(String(100), nullable=False, index=True)
    follower_id = Column(String(100), nullable=False)
    sequence_type = Column(String(50), nullable=False)
    step = Column(Integer, nullable=False, default=0)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    message_template = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)
    extra_data = Column(JSONB, nullable=True, default=dict)  # Renamed from metadata - reserved in SQLAlchemy

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format matching FollowUp dataclass."""
        return {
            "id": self.id,
            "creator_id": self.creator_id,
            "follower_id": self.follower_id,
            "sequence_type": self.sequence_type,
            "step": self.step,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "message_template": self.message_template,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "metadata": self.extra_data or {}
        }

    @classmethod
    def from_followup(cls, followup) -> "NurturingFollowupDB":
        """Create from FollowUp dataclass."""
        scheduled_at = followup.scheduled_at
        if isinstance(scheduled_at, str):
            scheduled_at = datetime.fromisoformat(scheduled_at)

        created_at = followup.created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        sent_at = followup.sent_at
        if isinstance(sent_at, str):
            sent_at = datetime.fromisoformat(sent_at)

        return cls(
            id=followup.id,
            creator_id=followup.creator_id,
            follower_id=followup.follower_id,
            sequence_type=followup.sequence_type,
            step=followup.step,
            scheduled_at=scheduled_at,
            message_template=followup.message_template,
            status=followup.status,
            created_at=created_at,
            sent_at=sent_at,
            extra_data=followup.metadata
        )


class NurturingDBStorage:
    """
    PostgreSQL storage backend for nurturing followups.

    Provides the same interface as the file-based NurturingManager storage,
    allowing seamless switching between backends.
    """

    def __init__(self):
        self._db_available = SessionLocal is not None
        if not self._db_available:
            logger.warning("[NURTURING_DB] Database not configured, falling back to JSON")

    def is_available(self) -> bool:
        """Check if database storage is available."""
        return self._db_available and NURTURING_USE_DB

    @contextmanager
    def _get_session(self):
        """Get a database session with proper error handling."""
        if not self._db_available:
            raise SQLAlchemyError("Database not configured")
        with get_db_session() as session:
            yield session

    def save_followup(self, followup) -> bool:
        """
        Save a single followup to the database.

        Args:
            followup: FollowUp dataclass instance

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            with self._get_session() as session:
                db_followup = NurturingFollowupDB.from_followup(followup)
                session.merge(db_followup)  # Use merge for upsert behavior
                session.commit()
                logger.debug(f"[NURTURING_DB] Saved followup {followup.id}")
                return True
        except SQLAlchemyError as e:
            logger.error(f"[NURTURING_DB] Error saving followup: {e}")
            return False

    def save_followups(self, creator_id: str, followups: list) -> bool:
        """
        Save multiple followups for a creator (replaces all).

        Args:
            creator_id: Creator ID
            followups: List of FollowUp dataclass instances

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            with self._get_session() as session:
                # Convert all followups to DB models
                for followup in followups:
                    db_followup = NurturingFollowupDB.from_followup(followup)
                    session.merge(db_followup)

                session.commit()
                logger.info(f"[NURTURING_DB] Saved {len(followups)} followups for {creator_id}")
                return True
        except SQLAlchemyError as e:
            logger.error(f"[NURTURING_DB] Error saving followups: {e}")
            return False

    def load_followups(self, creator_id: str) -> List[Dict[str, Any]]:
        """
        Load all followups for a creator.

        Args:
            creator_id: Creator ID

        Returns:
            List of followup dictionaries
        """
        try:
            with self._get_session() as session:
                followups = session.query(NurturingFollowupDB).filter(
                    NurturingFollowupDB.creator_id == creator_id
                ).all()
                return [fu.to_dict() for fu in followups]
        except SQLAlchemyError as e:
            logger.error(f"[NURTURING_DB] Error loading followups: {e}")
            return []

    def get_pending_followups(self, creator_id: str = None) -> List[Dict[str, Any]]:
        """
        Get pending followups that are due for sending.

        Args:
            creator_id: Optional creator ID filter

        Returns:
            List of due followup dictionaries, sorted by scheduled_at
        """
        try:
            from datetime import timezone
            now = datetime.now(timezone.utc)
            with self._get_session() as session:
                query = session.query(NurturingFollowupDB).filter(
                    and_(
                        NurturingFollowupDB.status == "pending",
                        NurturingFollowupDB.scheduled_at <= now
                    )
                )

                if creator_id:
                    query = query.filter(NurturingFollowupDB.creator_id == creator_id)

                followups = query.order_by(NurturingFollowupDB.scheduled_at).all()
                logger.info(f"[NURTURING_DB] Found {len(followups)} pending followups")
                return [fu.to_dict() for fu in followups]
        except SQLAlchemyError as e:
            logger.error(f"[NURTURING_DB] Error getting pending followups: {e}")
            return []

    def get_all_followups(self, creator_id: str, status: str = None) -> List[Dict[str, Any]]:
        """
        Get all followups for a creator, optionally filtered by status.

        Args:
            creator_id: Creator ID
            status: Optional status filter (pending, sent, cancelled)

        Returns:
            List of followup dictionaries
        """
        try:
            with self._get_session() as session:
                query = session.query(NurturingFollowupDB).filter(
                    NurturingFollowupDB.creator_id == creator_id
                )

                if status:
                    query = query.filter(NurturingFollowupDB.status == status)

                followups = query.all()
                return [fu.to_dict() for fu in followups]
        except SQLAlchemyError as e:
            logger.error(f"[NURTURING_DB] Error getting followups: {e}")
            return []

    def mark_as_sent(self, followup_id: str, creator_id: str) -> bool:
        """
        Mark a followup as sent.

        Args:
            followup_id: Followup ID
            creator_id: Creator ID

        Returns:
            True if updated successfully, False otherwise
        """
        try:
            with self._get_session() as session:
                followup = session.query(NurturingFollowupDB).filter(
                    NurturingFollowupDB.id == followup_id
                ).first()

                if followup:
                    followup.status = "sent"
                    followup.sent_at = datetime.now()
                    session.commit()
                    logger.info(f"[NURTURING_DB] Marked {followup_id} as sent")
                    return True
                return False
        except SQLAlchemyError as e:
            logger.error(f"[NURTURING_DB] Error marking as sent: {e}")
            return False

    def cancel_followups(
        self,
        creator_id: str,
        follower_id: str,
        sequence_type: str = None
    ) -> int:
        """
        Cancel pending followups for a follower.

        Args:
            creator_id: Creator ID
            follower_id: Follower ID
            sequence_type: Optional sequence type filter

        Returns:
            Number of followups cancelled
        """
        try:
            with self._get_session() as session:
                query = session.query(NurturingFollowupDB).filter(
                    and_(
                        NurturingFollowupDB.creator_id == creator_id,
                        NurturingFollowupDB.follower_id == follower_id,
                        NurturingFollowupDB.status == "pending"
                    )
                )

                if sequence_type:
                    query = query.filter(NurturingFollowupDB.sequence_type == sequence_type)

                followups = query.all()
                cancelled = len(followups)

                for fu in followups:
                    fu.status = "cancelled"

                session.commit()

                if cancelled > 0:
                    logger.info(f"[NURTURING_DB] Cancelled {cancelled} followups for {follower_id}")

                return cancelled
        except SQLAlchemyError as e:
            logger.error(f"[NURTURING_DB] Error cancelling followups: {e}")
            return 0

    def cleanup_old_followups(self, creator_id: str, days: int = 30) -> int:
        """
        Delete old sent/cancelled followups.

        Args:
            creator_id: Creator ID
            days: Keep followups newer than this

        Returns:
            Number of followups deleted
        """
        try:
            cutoff = datetime.now() - timedelta(days=days)
            with self._get_session() as session:
                deleted = session.query(NurturingFollowupDB).filter(
                    and_(
                        NurturingFollowupDB.creator_id == creator_id,
                        NurturingFollowupDB.status != "pending",
                        NurturingFollowupDB.created_at < cutoff
                    )
                ).delete(synchronize_session=False)

                session.commit()

                if deleted > 0:
                    logger.info(f"[NURTURING_DB] Cleaned up {deleted} old followups for {creator_id}")

                return deleted
        except SQLAlchemyError as e:
            logger.error(f"[NURTURING_DB] Error cleaning up followups: {e}")
            return 0

    def get_stats(self, creator_id: str) -> Dict[str, Any]:
        """
        Get nurturing statistics for a creator.

        Args:
            creator_id: Creator ID

        Returns:
            Statistics dictionary
        """
        try:
            with self._get_session() as session:
                followups = session.query(NurturingFollowupDB).filter(
                    NurturingFollowupDB.creator_id == creator_id
                ).all()

                stats = {
                    "total": len(followups),
                    "pending": 0,
                    "sent": 0,
                    "cancelled": 0,
                    "by_sequence": {}
                }

                for fu in followups:
                    # Count by status
                    if fu.status == "pending":
                        stats["pending"] += 1
                    elif fu.status == "sent":
                        stats["sent"] += 1
                    elif fu.status == "cancelled":
                        stats["cancelled"] += 1

                    # Count by sequence type
                    seq = fu.sequence_type
                    if seq not in stats["by_sequence"]:
                        stats["by_sequence"][seq] = {"pending": 0, "sent": 0, "cancelled": 0}
                    stats["by_sequence"][seq][fu.status] = stats["by_sequence"][seq].get(fu.status, 0) + 1

                return stats
        except SQLAlchemyError as e:
            logger.error(f"[NURTURING_DB] Error getting stats: {e}")
            return {"total": 0, "pending": 0, "sent": 0, "cancelled": 0, "by_sequence": {}}

    def get_all_creator_ids(self) -> List[str]:
        """
        Get all unique creator IDs with followups.

        Returns:
            List of creator IDs
        """
        try:
            with self._get_session() as session:
                result = session.query(NurturingFollowupDB.creator_id).distinct().all()
                return [r[0] for r in result]
        except SQLAlchemyError as e:
            logger.error(f"[NURTURING_DB] Error getting creator IDs: {e}")
            return []


# Global instance
_nurturing_db_storage: Optional[NurturingDBStorage] = None


def get_nurturing_db_storage() -> NurturingDBStorage:
    """Get global instance of NurturingDBStorage."""
    global _nurturing_db_storage
    if _nurturing_db_storage is None:
        _nurturing_db_storage = NurturingDBStorage()
    return _nurturing_db_storage


def is_db_storage_enabled() -> bool:
    """Check if database storage is enabled and available."""
    storage = get_nurturing_db_storage()
    return storage.is_available()
