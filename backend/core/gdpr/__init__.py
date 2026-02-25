"""
GDPR Compliance System for Clonnect Creators.

Provides:
- User data export (Right to Access)
- User data deletion (Right to be Forgotten)
- Data anonymization
- Consent management
- Audit logging

Storage: JSON files in data/gdpr/
"""

from .models import ConsentType, AuditAction, ConsentRecord, AuditLogEntry, DataInventoryItem
from .manager import GDPRManager, get_gdpr_manager

__all__ = [
    "ConsentType",
    "AuditAction",
    "ConsentRecord",
    "AuditLogEntry",
    "DataInventoryItem",
    "GDPRManager",
    "get_gdpr_manager",
]
