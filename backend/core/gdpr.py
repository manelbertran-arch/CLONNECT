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

import os
import json
import logging
import hashlib
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
import uuid

logger = logging.getLogger("clonnect-gdpr")


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


class GDPRManager:
    """
    Manager for GDPR compliance operations.

    Handles data export, deletion, anonymization, consent, and audit logging.
    """

    def __init__(self, storage_path: str = "data/gdpr"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        self._consent_cache: Dict[str, List[ConsentRecord]] = {}
        self._audit_cache: Dict[str, List[AuditLogEntry]] = {}

    # ==========================================================================
    # FILE PATHS
    # ==========================================================================

    def _get_consents_file(self, creator_id: str) -> str:
        return os.path.join(self.storage_path, f"{creator_id}_consents.json")

    def _get_audit_file(self, creator_id: str) -> str:
        return os.path.join(self.storage_path, f"{creator_id}_audit_log.json")

    def _get_deletion_log_file(self, creator_id: str) -> str:
        return os.path.join(self.storage_path, f"{creator_id}_deletions.json")

    # ==========================================================================
    # CONSENT MANAGEMENT
    # ==========================================================================

    def _load_consents(self, creator_id: str) -> List[ConsentRecord]:
        """Load consents for a creator"""
        if creator_id in self._consent_cache:
            return self._consent_cache[creator_id]

        file_path = self._get_consents_file(creator_id)
        consents = []

        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    consents = [ConsentRecord.from_dict(c) for c in data]
            except Exception as e:
                logger.error(f"Error loading consents: {e}")

        self._consent_cache[creator_id] = consents
        return consents

    def _save_consents(self, creator_id: str, consents: List[ConsentRecord]):
        """Save consents for a creator"""
        file_path = self._get_consents_file(creator_id)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump([c.to_dict() for c in consents], f, indent=2, ensure_ascii=False)
            self._consent_cache[creator_id] = consents
        except Exception as e:
            logger.error(f"Error saving consents: {e}")

    def record_consent(
        self,
        creator_id: str,
        follower_id: str,
        consent_type: str,
        granted: bool,
        ip_address: str = "",
        user_agent: str = "",
        source: str = "dm"
    ) -> ConsentRecord:
        """
        Record a consent decision.

        Args:
            creator_id: Creator ID
            follower_id: Follower ID
            consent_type: Type of consent (from ConsentType enum)
            granted: Whether consent was granted
            ip_address: User's IP address (optional)
            user_agent: User's browser/app info (optional)
            source: Where consent was given

        Returns:
            ConsentRecord
        """
        consent = ConsentRecord(
            consent_id=f"cns_{uuid.uuid4().hex[:12]}",
            follower_id=follower_id,
            creator_id=creator_id,
            consent_type=consent_type,
            granted=granted,
            timestamp=datetime.now(timezone.utc).isoformat(),
            ip_address=ip_address,
            user_agent=user_agent,
            source=source
        )

        consents = self._load_consents(creator_id)
        consents.append(consent)
        self._save_consents(creator_id, consents)

        # Log audit
        action = AuditAction.CONSENT_GRANTED.value if granted else AuditAction.CONSENT_REVOKED.value
        self.log_access(
            creator_id=creator_id,
            follower_id=follower_id,
            action=action,
            actor="user",
            details={"consent_type": consent_type, "granted": granted}
        )

        logger.info(f"Consent recorded: {follower_id} {'granted' if granted else 'revoked'} {consent_type}")
        return consent

    def get_consent_status(
        self,
        creator_id: str,
        follower_id: str
    ) -> Dict[str, Any]:
        """
        Get current consent status for a user.

        Args:
            creator_id: Creator ID
            follower_id: Follower ID

        Returns:
            Dict with consent status for each type
        """
        consents = self._load_consents(creator_id)

        # Filter consents for this follower
        follower_consents = [c for c in consents if c.follower_id == follower_id]

        # Get latest consent for each type
        status = {}
        for consent_type in ConsentType:
            type_consents = [c for c in follower_consents if c.consent_type == consent_type.value]
            if type_consents:
                # Get most recent
                latest = max(type_consents, key=lambda x: x.timestamp)
                status[consent_type.value] = {
                    "granted": latest.granted,
                    "timestamp": latest.timestamp,
                    "source": latest.source
                }
            else:
                status[consent_type.value] = {
                    "granted": False,
                    "timestamp": None,
                    "source": None
                }

        return {
            "follower_id": follower_id,
            "creator_id": creator_id,
            "consents": status,
            "has_any_consent": any(s["granted"] for s in status.values())
        }

    def has_consent(
        self,
        creator_id: str,
        follower_id: str,
        consent_type: str = None
    ) -> bool:
        """
        Check if user has granted consent.

        Args:
            creator_id: Creator ID
            follower_id: Follower ID
            consent_type: Specific consent type to check (optional)

        Returns:
            True if consent granted
        """
        status = self.get_consent_status(creator_id, follower_id)

        if consent_type:
            return status["consents"].get(consent_type, {}).get("granted", False)

        # Check for basic data processing consent
        return status["consents"].get(ConsentType.DATA_PROCESSING.value, {}).get("granted", False)

    # ==========================================================================
    # DATA EXPORT
    # ==========================================================================

    def export_user_data(
        self,
        creator_id: str,
        follower_id: str,
        include_analytics: bool = True,
        include_messages: bool = True
    ) -> Dict[str, Any]:
        """
        Export all user data (GDPR Right to Access).

        Args:
            creator_id: Creator ID
            follower_id: Follower ID
            include_analytics: Include analytics data
            include_messages: Include message history

        Returns:
            Dict with all user data
        """
        export_data = {
            "export_id": f"exp_{uuid.uuid4().hex[:12]}",
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "follower_id": follower_id,
            "creator_id": creator_id,
            "data": {}
        }

        # 1. Follower memory data
        follower_data = self._get_follower_data(creator_id, follower_id)
        if follower_data:
            export_data["data"]["profile"] = follower_data

        # 2. Consent records
        consents = self._load_consents(creator_id)
        follower_consents = [c.to_dict() for c in consents if c.follower_id == follower_id]
        export_data["data"]["consents"] = follower_consents

        # 3. Analytics events (if requested)
        if include_analytics:
            analytics_data = self._get_analytics_data(creator_id, follower_id)
            export_data["data"]["analytics"] = analytics_data

        # 4. Message history (if requested and available)
        if include_messages and follower_data:
            export_data["data"]["messages"] = follower_data.get("last_messages", [])

        # 5. Nurturing data
        nurturing_data = self._get_nurturing_data(creator_id, follower_id)
        if nurturing_data:
            export_data["data"]["nurturing"] = nurturing_data

        # Log audit
        self.log_access(
            creator_id=creator_id,
            follower_id=follower_id,
            action=AuditAction.DATA_EXPORT.value,
            actor="system",
            details={"export_id": export_data["export_id"]}
        )

        logger.info(f"Data exported for {follower_id}")
        return export_data

    def _get_follower_data(self, creator_id: str, follower_id: str) -> Optional[dict]:
        """Get follower data from memory store"""
        # Sanitize follower_id for filename
        safe_id = follower_id.replace("/", "_").replace("\\", "_")
        file_path = f"data/followers/{creator_id}/{safe_id}.json"

        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading follower data: {e}")
        return None

    def _get_analytics_data(self, creator_id: str, follower_id: str) -> List[dict]:
        """Get analytics events for follower"""
        file_path = f"data/analytics/{creator_id}_events.json"

        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    events = json.load(f)
                    return [e for e in events if e.get("follower_id") == follower_id]
            except Exception as e:
                logger.error(f"Error loading analytics data: {e}")
        return []

    def _get_nurturing_data(self, creator_id: str, follower_id: str) -> List[dict]:
        """Get nurturing followups for follower"""
        file_path = f"data/nurturing/{creator_id}_followups.json"

        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    followups = json.load(f)
                    return [f for f in followups if f.get("follower_id") == follower_id]
            except Exception as e:
                logger.error(f"Error loading nurturing data: {e}")
        return []

    # ==========================================================================
    # DATA DELETION
    # ==========================================================================

    def delete_user_data(
        self,
        creator_id: str,
        follower_id: str,
        reason: str = "user_request"
    ) -> Dict[str, Any]:
        """
        Delete all user data (GDPR Right to be Forgotten).

        Args:
            creator_id: Creator ID
            follower_id: Follower ID
            reason: Reason for deletion

        Returns:
            Dict with deletion result
        """
        deleted_items = []
        errors = []

        # 1. Delete follower memory
        safe_id = follower_id.replace("/", "_").replace("\\", "_")
        follower_file = f"data/followers/{creator_id}/{safe_id}.json"
        if os.path.exists(follower_file):
            try:
                os.remove(follower_file)
                deleted_items.append("follower_profile")
            except Exception as e:
                errors.append(f"follower_profile: {e}")

        # 2. Delete from analytics
        analytics_file = f"data/analytics/{creator_id}_events.json"
        if os.path.exists(analytics_file):
            try:
                with open(analytics_file, 'r', encoding='utf-8') as f:
                    events = json.load(f)
                original_count = len(events)
                events = [e for e in events if e.get("follower_id") != follower_id]
                with open(analytics_file, 'w', encoding='utf-8') as f:
                    json.dump(events, f, indent=2, ensure_ascii=False)
                if original_count > len(events):
                    deleted_items.append("analytics_events")
            except Exception as e:
                errors.append(f"analytics: {e}")

        # 3. Delete from nurturing
        nurturing_file = f"data/nurturing/{creator_id}_followups.json"
        if os.path.exists(nurturing_file):
            try:
                with open(nurturing_file, 'r', encoding='utf-8') as f:
                    followups = json.load(f)
                original_count = len(followups)
                followups = [f for f in followups if f.get("follower_id") != follower_id]
                with open(nurturing_file, 'w', encoding='utf-8') as f:
                    json.dump(followups, f, indent=2, ensure_ascii=False)
                if original_count > len(followups):
                    deleted_items.append("nurturing_followups")
            except Exception as e:
                errors.append(f"nurturing: {e}")

        # 4. Keep consent records but mark as deleted (required for audit)
        # Don't delete consents - they serve as proof of previous consent

        # Log the deletion
        deletion_record = {
            "deletion_id": f"del_{uuid.uuid4().hex[:12]}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "follower_id": follower_id,
            "creator_id": creator_id,
            "reason": reason,
            "deleted_items": deleted_items,
            "errors": errors
        }

        self._save_deletion_record(creator_id, deletion_record)

        # Log audit
        self.log_access(
            creator_id=creator_id,
            follower_id=follower_id,
            action=AuditAction.DATA_DELETE.value,
            actor="system",
            details={"deletion_id": deletion_record["deletion_id"], "items": deleted_items}
        )

        logger.info(f"Data deleted for {follower_id}: {deleted_items}")

        return {
            "success": len(errors) == 0,
            "deletion_id": deletion_record["deletion_id"],
            "deleted_items": deleted_items,
            "errors": errors
        }

    def _save_deletion_record(self, creator_id: str, record: dict):
        """Save deletion record for audit trail"""
        file_path = self._get_deletion_log_file(creator_id)
        records = []

        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    records = json.load(f)
            except:
                pass

        records.append(record)

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(records, f, indent=2, ensure_ascii=False)

    # ==========================================================================
    # DATA ANONYMIZATION
    # ==========================================================================

    def anonymize_user_data(
        self,
        creator_id: str,
        follower_id: str
    ) -> Dict[str, Any]:
        """
        Anonymize user data instead of deleting.

        Keeps aggregated/anonymized data for analytics while removing PII.

        Args:
            creator_id: Creator ID
            follower_id: Follower ID

        Returns:
            Dict with anonymization result
        """
        anonymized_items = []
        errors = []

        # Generate anonymous ID
        anon_id = f"anon_{hashlib.sha256(follower_id.encode()).hexdigest()[:12]}"

        # 1. Anonymize follower memory
        safe_id = follower_id.replace("/", "_").replace("\\", "_")
        follower_file = f"data/followers/{creator_id}/{safe_id}.json"

        if os.path.exists(follower_file):
            try:
                with open(follower_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Anonymize PII fields
                data["follower_id"] = anon_id
                data["username"] = "anonymized"
                data["name"] = "anonymized"
                data["last_messages"] = []  # Remove message content

                # Keep non-PII for analytics
                # interests, products_discussed, scores, etc.

                # Save with anonymized ID
                anon_file = f"data/followers/{creator_id}/{anon_id}.json"
                with open(anon_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                # Remove original file
                os.remove(follower_file)
                anonymized_items.append("follower_profile")

            except Exception as e:
                errors.append(f"follower_profile: {e}")

        # 2. Anonymize analytics events
        analytics_file = f"data/analytics/{creator_id}_events.json"
        if os.path.exists(analytics_file):
            try:
                with open(analytics_file, 'r', encoding='utf-8') as f:
                    events = json.load(f)

                for event in events:
                    if event.get("follower_id") == follower_id:
                        event["follower_id"] = anon_id

                with open(analytics_file, 'w', encoding='utf-8') as f:
                    json.dump(events, f, indent=2, ensure_ascii=False)
                anonymized_items.append("analytics_events")

            except Exception as e:
                errors.append(f"analytics: {e}")

        # Log audit
        self.log_access(
            creator_id=creator_id,
            follower_id=follower_id,
            action=AuditAction.DATA_ANONYMIZE.value,
            actor="system",
            details={"anonymized_id": anon_id, "items": anonymized_items}
        )

        logger.info(f"Data anonymized for {follower_id} -> {anon_id}")

        return {
            "success": len(errors) == 0,
            "original_id": follower_id,
            "anonymized_id": anon_id,
            "anonymized_items": anonymized_items,
            "errors": errors
        }

    # ==========================================================================
    # DATA INVENTORY
    # ==========================================================================

    def get_data_inventory(
        self,
        creator_id: str,
        follower_id: str
    ) -> Dict[str, Any]:
        """
        Get inventory of what data we hold for a user.

        Args:
            creator_id: Creator ID
            follower_id: Follower ID

        Returns:
            Dict with data inventory
        """
        inventory = []

        # 1. Follower profile
        safe_id = follower_id.replace("/", "_").replace("\\", "_")
        follower_file = f"data/followers/{creator_id}/{safe_id}.json"
        has_profile = os.path.exists(follower_file)

        inventory.append(DataInventoryItem(
            data_type="profile",
            description="User profile including name, username, interests, purchase intent",
            location="data/followers/",
            retention_period="Until deletion request or 2 years inactivity",
            legal_basis="Legitimate interest / Consent",
            has_data=has_profile
        ))

        # 2. Message history
        inventory.append(DataInventoryItem(
            data_type="messages",
            description="Conversation history (last 20 messages)",
            location="data/followers/ (embedded)",
            retention_period="Until deletion request or 2 years inactivity",
            legal_basis="Contract performance",
            has_data=has_profile
        ))

        # 3. Analytics
        analytics_file = f"data/analytics/{creator_id}_events.json"
        has_analytics = False
        if os.path.exists(analytics_file):
            try:
                with open(analytics_file, 'r', encoding='utf-8') as f:
                    events = json.load(f)
                    has_analytics = any(e.get("follower_id") == follower_id for e in events)
            except:
                pass

        inventory.append(DataInventoryItem(
            data_type="analytics",
            description="Message events, intent classification, engagement metrics",
            location="data/analytics/",
            retention_period="2 years",
            legal_basis="Legitimate interest / Consent",
            has_data=has_analytics
        ))

        # 4. Consent records
        consents = self._load_consents(creator_id)
        has_consents = any(c.follower_id == follower_id for c in consents)

        inventory.append(DataInventoryItem(
            data_type="consents",
            description="Records of consent given or revoked",
            location="data/gdpr/",
            retention_period="5 years (legal requirement)",
            legal_basis="Legal obligation",
            has_data=has_consents
        ))

        # 5. Nurturing data
        nurturing_file = f"data/nurturing/{creator_id}_followups.json"
        has_nurturing = False
        if os.path.exists(nurturing_file):
            try:
                with open(nurturing_file, 'r', encoding='utf-8') as f:
                    followups = json.load(f)
                    has_nurturing = any(f.get("follower_id") == follower_id for f in followups)
            except:
                pass

        inventory.append(DataInventoryItem(
            data_type="nurturing",
            description="Scheduled follow-up messages",
            location="data/nurturing/",
            retention_period="Until sent or cancelled",
            legal_basis="Legitimate interest / Consent",
            has_data=has_nurturing
        ))

        return {
            "follower_id": follower_id,
            "creator_id": creator_id,
            "inventory": [asdict(item) for item in inventory],
            "total_data_types": len(inventory),
            "data_types_with_data": sum(1 for item in inventory if item.has_data)
        }

    # ==========================================================================
    # AUDIT LOGGING
    # ==========================================================================

    def _load_audit_log(self, creator_id: str) -> List[AuditLogEntry]:
        """Load audit log for a creator"""
        if creator_id in self._audit_cache:
            return self._audit_cache[creator_id]

        file_path = self._get_audit_file(creator_id)
        entries = []

        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    entries = [AuditLogEntry.from_dict(e) for e in data]
            except Exception as e:
                logger.error(f"Error loading audit log: {e}")

        self._audit_cache[creator_id] = entries
        return entries

    def _save_audit_log(self, creator_id: str, entries: List[AuditLogEntry]):
        """Save audit log for a creator"""
        file_path = self._get_audit_file(creator_id)
        try:
            # Keep last 10000 entries max
            if len(entries) > 10000:
                entries = entries[-10000:]

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump([e.to_dict() for e in entries], f, indent=2, ensure_ascii=False)
            self._audit_cache[creator_id] = entries
        except Exception as e:
            logger.error(f"Error saving audit log: {e}")

    def log_access(
        self,
        creator_id: str,
        follower_id: str,
        action: str,
        actor: str,
        details: Dict[str, Any] = None,
        ip_address: str = ""
    ):
        """
        Log a data access or modification.

        Args:
            creator_id: Creator ID
            follower_id: Follower ID
            action: Action performed (from AuditAction)
            actor: Who performed the action
            details: Additional details
            ip_address: IP address (optional)
        """
        entry = AuditLogEntry(
            log_id=f"log_{uuid.uuid4().hex[:12]}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            creator_id=creator_id,
            follower_id=follower_id,
            action=action,
            actor=actor,
            details=details or {},
            ip_address=ip_address
        )

        entries = self._load_audit_log(creator_id)
        entries.append(entry)
        self._save_audit_log(creator_id, entries)

    def log_modification(
        self,
        creator_id: str,
        follower_id: str,
        action: str,
        old_value: Any,
        new_value: Any,
        actor: str = "system"
    ):
        """
        Log a data modification with before/after values.

        Args:
            creator_id: Creator ID
            follower_id: Follower ID
            action: What was modified
            old_value: Value before change
            new_value: Value after change
            actor: Who made the change
        """
        self.log_access(
            creator_id=creator_id,
            follower_id=follower_id,
            action=AuditAction.DATA_MODIFY.value,
            actor=actor,
            details={
                "field": action,
                "old_value": str(old_value)[:200],  # Truncate for storage
                "new_value": str(new_value)[:200]
            }
        )

    def get_audit_log(
        self,
        creator_id: str,
        follower_id: str = None,
        action: str = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get audit log entries.

        Args:
            creator_id: Creator ID
            follower_id: Filter by follower (optional)
            action: Filter by action (optional)
            limit: Maximum entries to return

        Returns:
            List of audit log entries
        """
        entries = self._load_audit_log(creator_id)

        # Filter
        if follower_id:
            entries = [e for e in entries if e.follower_id == follower_id]
        if action:
            entries = [e for e in entries if e.action == action]

        # Sort by timestamp descending (most recent first)
        entries.sort(key=lambda x: x.timestamp, reverse=True)

        # Limit
        entries = entries[:limit]

        return [e.to_dict() for e in entries]


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_gdpr_manager: Optional[GDPRManager] = None


def get_gdpr_manager() -> GDPRManager:
    """Get or create GDPR manager singleton"""
    global _gdpr_manager
    if _gdpr_manager is None:
        _gdpr_manager = GDPRManager()
    return _gdpr_manager
