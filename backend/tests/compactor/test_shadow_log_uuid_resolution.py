"""Tests for _log_shadow_compactor_sync UUID resolution fix (bug ref: audit 52986d00).

Bug: UUID(slug) always raised ValueError, silently discarding every shadow log row.
Fix: resolve slug→UUID via DB lookup when UUID parse fails.
"""
import json
import logging
import os
from unittest.mock import MagicMock, patch, call
from uuid import UUID, uuid4

import pytest

os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("TESTING", "true")

# Import the function under test
from core.dm.phases.context import _log_shadow_compactor_sync


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_CREATOR_UUID = str(uuid4())
_CREATOR_SLUG = "iris_bertran"

_DEFAULT_KWARGS = dict(
    creator_id_str=_CREATOR_SLUG,
    sender_id="123456",
    total_budget=8000,
    actual_chars=5000,
    shadow_chars=3200,
    compaction_applied=True,
    reason="OVER_BUDGET",
    sections_truncated=["lead_memories"],
    distill_applied=False,
    model="google/gemma-4-31b-it",
)


def _make_db_mock(uuid_row=None, insert_ok=True):
    """Build a mock DB session with configurable query results."""
    db = MagicMock()
    slug_result = MagicMock()
    slug_result.fetchone.return_value = (UUID(_CREATOR_UUID),) if uuid_row else None
    insert_result = MagicMock()
    db.execute.side_effect = [slug_result, insert_result]
    if not insert_ok:
        db.execute.side_effect = [slug_result, Exception("DB error")]
    return db


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestShadowLogUUIDResolution:

    @patch("api.database.SessionLocal")
    def test_slug_resolves_to_uuid_and_inserts(self, mock_session_local):
        """Valid slug in creators table → UUID resolved → INSERT executed."""
        db = _make_db_mock(uuid_row=True)
        mock_session_local.return_value = db

        _log_shadow_compactor_sync(**_DEFAULT_KWARGS)

        # DB session opened once
        mock_session_local.assert_called_once()
        # Two execute calls: slug lookup + INSERT
        assert db.execute.call_count == 2
        # First call is the slug lookup
        first_call_sql = str(db.execute.call_args_list[0][0][0])
        assert "creators" in first_call_sql
        assert "name" in first_call_sql
        # INSERT committed
        db.commit.assert_called_once()
        # Session closed (finally block)
        db.close.assert_called_once()

    @patch("api.database.SessionLocal")
    def test_slug_not_found_logs_warning_no_insert(self, mock_session_local, caplog):
        """Slug not in creators table → WARNING logged → no INSERT → no crash."""
        db = _make_db_mock(uuid_row=False)
        # Only the slug lookup is called (returns None), no INSERT call
        db.execute.side_effect = [MagicMock(fetchone=lambda: None)]
        mock_session_local.return_value = db

        with caplog.at_level(logging.WARNING):
            _log_shadow_compactor_sync(**_DEFAULT_KWARGS)

        assert "not found in DB" in caplog.text or "iris_bertran" in caplog.text
        # Only slug lookup executed, no INSERT
        assert db.execute.call_count == 1
        db.commit.assert_not_called()
        # Session still closed properly
        db.close.assert_called_once()

    @patch("api.database.SessionLocal")
    def test_valid_uuid_bypasses_db_lookup(self, mock_session_local):
        """creator_id_str that IS a valid UUID → no DB slug lookup → direct INSERT."""
        db = MagicMock()
        mock_session_local.return_value = db

        kwargs = dict(_DEFAULT_KWARGS)
        kwargs["creator_id_str"] = _CREATOR_UUID

        _log_shadow_compactor_sync(**kwargs)

        # Only one execute call — the INSERT (no slug lookup needed)
        assert db.execute.call_count == 1
        insert_sql = str(db.execute.call_args_list[0][0][0])
        assert "context_compactor_shadow_log" in insert_sql
        db.commit.assert_called_once()

    @patch("api.database.SessionLocal")
    def test_empty_creator_id_does_not_crash(self, mock_session_local, caplog):
        """Empty string as creator_id → handled gracefully, no crash."""
        db = MagicMock()
        # Empty string: UUID parse fails, DB lookup returns None
        lookup_result = MagicMock()
        lookup_result.fetchone.return_value = None
        db.execute.side_effect = [lookup_result]
        mock_session_local.return_value = db

        kwargs = dict(_DEFAULT_KWARGS)
        kwargs["creator_id_str"] = ""

        # Must not raise
        _log_shadow_compactor_sync(**kwargs)

        db.commit.assert_not_called()
        db.close.assert_called_once()

    @patch("api.database.SessionLocal")
    def test_db_insert_failure_is_non_fatal(self, mock_session_local):
        """DB error during INSERT → caught by outer except → no crash."""
        db = MagicMock()
        slug_result = MagicMock()
        slug_result.fetchone.return_value = (UUID(_CREATOR_UUID),)
        db.execute.side_effect = [slug_result, Exception("connection reset")]
        mock_session_local.return_value = db

        # Must not raise
        _log_shadow_compactor_sync(**_DEFAULT_KWARGS)

        db.close.assert_called_once()

    @patch("api.database.SessionLocal")
    def test_insert_payload_contains_resolved_uuid(self, mock_session_local):
        """The resolved UUID (not the slug) is passed to the INSERT."""
        db = _make_db_mock(uuid_row=True)
        mock_session_local.return_value = db

        _log_shadow_compactor_sync(**_DEFAULT_KWARGS)

        insert_params = db.execute.call_args_list[1][0][1]
        assert insert_params["creator_id"] == _CREATOR_UUID
        assert insert_params["compaction_applied"] is True
        assert insert_params["actual_chars"] == 5000
        assert insert_params["shadow_chars"] == 3200
        assert json.loads(insert_params["sections"]) == ["lead_memories"]
