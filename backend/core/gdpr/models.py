"""
GDPR Compliance System - Models.

Enums and dataclasses for GDPR compliance.
"""

from typing import Dict, Any
from dataclasses import dataclass, asdict, field
from enum import Enum


class ConsentType(Enum):
    """Types of consent"""
    DATA_PROCESSING = "data_processing"  # Basic data processing for service
    MARKETING = "marketing"  # Marketing communications
    ANALYTICS = "analytics"  # Analytics and tracking
    THIRD_PARTY = "third_party"  # Sharing with third parties
    PROFILING = "profiling"  # Automated profiling/scoring


class AuditAction(Enum):
    """Types of audit actions"""
    DATA_ACCESS = "data_access"
    DATA_EXPORT = "data_export"
    DATA_DELETE = "data_delete"
    DATA_ANONYMIZE = "data_anonymize"
    DATA_MODIFY = "data_modify"
    CONSENT_GRANTED = "consent_granted"
    CONSENT_REVOKED = "consent_revoked"
    MESSAGE_PROCESSED = "message_processed"


@dataclass
class ConsentRecord:
    """Record of user consent"""
    consent_id: str
    follower_id: str
    creator_id: str
    consent_type: str
    granted: bool
    timestamp: str
    ip_address: str = ""
    user_agent: str = ""
    source: str = "dm"  # dm, web, api, etc.
    version: str = "1.0"  # Consent policy version

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'ConsentRecord':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AuditLogEntry:
    """Single audit log entry"""
    log_id: str
    timestamp: str
    creator_id: str
    follower_id: str
    action: str
    actor: str  # Who performed the action (system, creator, user, admin)
    details: Dict[str, Any] = field(default_factory=dict)
    ip_address: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'AuditLogEntry':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class DataInventoryItem:
    """Item in data inventory"""
    data_type: str
    description: str
    location: str
    retention_period: str
    legal_basis: str
    has_data: bool = False
