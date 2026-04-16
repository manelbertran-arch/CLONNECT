"""Security event model — QW3 alerting log.

Persists `prompt_injection` and `sensitive_content` detections from
`core/dm/phases/detection.py`. See DECISIONS.md 2026-04-16 entry.

GDPR: never stores raw message content — only SHA256 hex fingerprint.
"""

from sqlalchemy import Column, DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

try:
    from api.database import Base
except ImportError:
    from database import Base


class SecurityEvent(Base):
    """Append-only log of security flag events.

    creator_id is a slug (e.g. "iris_bertran"), matching the rest of the
    Clonnect codebase — NOT a UUID.
    sender_id is the Instagram platform_user_id (raw numeric, no "ig_" prefix).
    """

    __tablename__ = "security_events"
    __table_args__ = (
        Index(
            "idx_security_events_creator_sender_type_time",
            "creator_id", "sender_id", "event_type", "created_at",
        ),
        Index("idx_security_events_created_at", "created_at"),
        {"extend_existing": True},
    )

    # Single-column indexes on creator_id / sender_id / event_type are omitted
    # deliberately: the composite `idx_security_events_creator_sender_type_time`
    # already satisfies the leading-column access patterns we need.
    id = Column(Integer, primary_key=True, autoincrement=True)
    creator_id = Column(String(100), nullable=False)
    sender_id = Column(String(100), nullable=True)
    event_type = Column(String(40), nullable=False)
    severity = Column(String(20), nullable=False)
    content_hash = Column(String(64), nullable=True)
    message_length = Column(Integer, nullable=True)
    event_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<SecurityEvent id={self.id} creator={self.creator_id} "
            f"type={self.event_type} severity={self.severity} at={self.created_at}>"
        )
