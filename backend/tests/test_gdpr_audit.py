"""Audit tests for core/gdpr.py."""

import json
import os
import shutil
import tempfile

import pytest
from core.gdpr import AuditAction, AuditLogEntry, ConsentRecord, ConsentType, GDPRManager


@pytest.fixture
def gdpr_tmpdir():
    """Create a temp directory for GDPR storage, clean up after test."""
    tmpdir = tempfile.mkdtemp(prefix="gdpr_test_")
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


class TestGDPRServiceInit:
    """Test 1: Initialization and imports."""

    def test_gdpr_manager_creates_storage_dir(self, gdpr_tmpdir):
        """GDPRManager creates the storage directory on init."""
        path = os.path.join(gdpr_tmpdir, "subdir")
        manager = GDPRManager(storage_path=path)
        assert os.path.isdir(path)
        assert manager._consent_cache == {}
        assert manager._audit_cache == {}

    def test_consent_type_enum_values(self):
        """ConsentType enum has all expected values."""
        expected = {"data_processing", "marketing", "analytics", "third_party", "profiling"}
        actual = {ct.value for ct in ConsentType}
        assert actual == expected

    def test_audit_action_enum_values(self):
        """AuditAction enum has all expected values."""
        expected = {
            "data_access",
            "data_export",
            "data_delete",
            "data_anonymize",
            "data_modify",
            "consent_granted",
            "consent_revoked",
            "message_processed",
        }
        actual = {aa.value for aa in AuditAction}
        assert actual == expected

    def test_consent_record_from_dict(self):
        """ConsentRecord.from_dict creates instance from dict."""
        data = {
            "consent_id": "cns_abc",
            "follower_id": "f1",
            "creator_id": "c1",
            "consent_type": "marketing",
            "granted": True,
            "timestamp": "2026-01-01T00:00:00",
        }
        record = ConsentRecord.from_dict(data)
        assert record.consent_id == "cns_abc"
        assert record.granted is True

    def test_audit_log_entry_to_dict(self):
        """AuditLogEntry.to_dict produces serializable dict."""
        entry = AuditLogEntry(
            log_id="log_1",
            timestamp="2026-01-01T00:00:00",
            creator_id="c1",
            follower_id="f1",
            action="data_access",
            actor="system",
        )
        d = entry.to_dict()
        assert d["log_id"] == "log_1"
        assert d["details"] == {}


class TestGDPRDataExportFormat:
    """Test 2: Happy path - data export format."""

    def test_export_user_data_has_required_fields(self, gdpr_tmpdir):
        """export_user_data returns dict with export_id, timestamp, data keys."""
        manager = GDPRManager(storage_path=gdpr_tmpdir)
        result = manager.export_user_data("creator1", "follower1")
        assert "export_id" in result
        assert result["export_id"].startswith("exp_")
        assert "export_timestamp" in result
        assert "data" in result
        assert "consents" in result["data"]

    def test_export_includes_consent_records(self, gdpr_tmpdir):
        """Exported data includes previously recorded consents."""
        manager = GDPRManager(storage_path=gdpr_tmpdir)
        manager.record_consent("creator1", "follower1", "marketing", True)

        result = manager.export_user_data("creator1", "follower1")
        assert len(result["data"]["consents"]) == 1
        assert result["data"]["consents"][0]["consent_type"] == "marketing"

    def test_export_without_analytics_excludes_analytics(self, gdpr_tmpdir):
        """export_user_data with include_analytics=False omits analytics key."""
        manager = GDPRManager(storage_path=gdpr_tmpdir)
        result = manager.export_user_data("creator1", "follower1", include_analytics=False)
        assert "analytics" not in result["data"]

    def test_export_logs_audit_entry(self, gdpr_tmpdir):
        """export_user_data creates an audit log entry."""
        manager = GDPRManager(storage_path=gdpr_tmpdir)
        manager.export_user_data("creator1", "follower1")
        audit = manager.get_audit_log("creator1", follower_id="follower1")
        actions = [e["action"] for e in audit]
        assert AuditAction.DATA_EXPORT.value in actions


class TestGDPRDataDeletion:
    """Test 3: Edge case - data deletion mock."""

    def test_delete_nonexistent_user_returns_success(self, gdpr_tmpdir):
        """Deleting a user with no data succeeds with empty deleted_items."""
        manager = GDPRManager(storage_path=gdpr_tmpdir)
        result = manager.delete_user_data("creator1", "follower_ghost")
        assert result["success"] is True
        assert result["deleted_items"] == []
        assert result["deletion_id"].startswith("del_")

    def test_delete_records_audit_trail(self, gdpr_tmpdir):
        """Deletion creates an audit log entry with DATA_DELETE action."""
        manager = GDPRManager(storage_path=gdpr_tmpdir)
        manager.delete_user_data("creator1", "follower1", reason="user_request")
        audit = manager.get_audit_log("creator1", follower_id="follower1")
        actions = [e["action"] for e in audit]
        assert AuditAction.DATA_DELETE.value in actions

    def test_delete_saves_deletion_record(self, gdpr_tmpdir):
        """Deletion persists to the deletion log file."""
        manager = GDPRManager(storage_path=gdpr_tmpdir)
        manager.delete_user_data("creator1", "follower1")
        log_file = manager._get_deletion_log_file("creator1")
        assert os.path.exists(log_file)
        with open(log_file, "r") as f:
            records = json.load(f)
        assert len(records) == 1
        assert records[0]["follower_id"] == "follower1"


class TestGDPREmptyUserHandling:
    """Test 4: Error handling - empty user and edge cases."""

    def test_consent_status_for_unknown_user(self, gdpr_tmpdir):
        """get_consent_status for unknown user shows all consents as not granted."""
        manager = GDPRManager(storage_path=gdpr_tmpdir)
        status = manager.get_consent_status("creator1", "nobody")
        assert status["has_any_consent"] is False
        for ct_status in status["consents"].values():
            assert ct_status["granted"] is False
            assert ct_status["timestamp"] is None

    def test_has_consent_returns_false_for_unknown_user(self, gdpr_tmpdir):
        """has_consent returns False for user without any consent records."""
        manager = GDPRManager(storage_path=gdpr_tmpdir)
        assert manager.has_consent("creator1", "nobody") is False

    def test_has_consent_specific_type_not_granted(self, gdpr_tmpdir):
        """has_consent for specific type returns False when only other types granted."""
        manager = GDPRManager(storage_path=gdpr_tmpdir)
        manager.record_consent("creator1", "f1", ConsentType.MARKETING.value, True)
        assert manager.has_consent("creator1", "f1", ConsentType.ANALYTICS.value) is False

    def test_data_inventory_no_data(self, gdpr_tmpdir):
        """get_data_inventory for new user shows has_data=False everywhere."""
        manager = GDPRManager(storage_path=gdpr_tmpdir)
        result = manager.get_data_inventory("creator1", "nobody")
        assert result["data_types_with_data"] == 0
        assert result["total_data_types"] == 5


class TestGDPRConsentCheck:
    """Test 5: Integration check - consent record and revoke cycle."""

    def test_record_and_check_consent(self, gdpr_tmpdir):
        """Record consent then verify has_consent returns True."""
        manager = GDPRManager(storage_path=gdpr_tmpdir)
        record = manager.record_consent("creator1", "f1", ConsentType.DATA_PROCESSING.value, True)
        assert record.granted is True
        assert record.consent_id.startswith("cns_")
        assert manager.has_consent("creator1", "f1") is True

    def test_revoke_consent_overrides_grant(self, gdpr_tmpdir):
        """Revoking consent after granting makes has_consent return False."""
        manager = GDPRManager(storage_path=gdpr_tmpdir)
        manager.record_consent("creator1", "f1", ConsentType.DATA_PROCESSING.value, True)
        manager.record_consent("creator1", "f1", ConsentType.DATA_PROCESSING.value, False)
        assert manager.has_consent("creator1", "f1") is False

    def test_consent_persists_to_file(self, gdpr_tmpdir):
        """Consent records survive cache eviction and reload from file."""
        manager = GDPRManager(storage_path=gdpr_tmpdir)
        manager.record_consent("creator1", "f1", ConsentType.MARKETING.value, True)
        # Evict cache, force reload
        manager._consent_cache.clear()
        assert manager.has_consent("creator1", "f1", ConsentType.MARKETING.value) is True

    def test_audit_log_filters_by_action(self, gdpr_tmpdir):
        """get_audit_log filters entries by action type."""
        manager = GDPRManager(storage_path=gdpr_tmpdir)
        manager.record_consent("creator1", "f1", ConsentType.DATA_PROCESSING.value, True)
        manager.export_user_data("creator1", "f1")
        grants = manager.get_audit_log("creator1", action=AuditAction.CONSENT_GRANTED.value)
        exports = manager.get_audit_log("creator1", action=AuditAction.DATA_EXPORT.value)
        assert len(grants) >= 1
        assert len(exports) >= 1
        assert all(e["action"] == AuditAction.CONSENT_GRANTED.value for e in grants)

    def test_log_modification_records_old_and_new(self, gdpr_tmpdir):
        """log_modification stores old_value and new_value in details."""
        manager = GDPRManager(storage_path=gdpr_tmpdir)
        manager.log_modification("creator1", "f1", "status", "new", "active", actor="system")
        audit = manager.get_audit_log("creator1", follower_id="f1")
        assert len(audit) >= 1
        entry = audit[0]
        assert entry["action"] == AuditAction.DATA_MODIFY.value
        assert entry["details"]["old_value"] == "new"
        assert entry["details"]["new_value"] == "active"
