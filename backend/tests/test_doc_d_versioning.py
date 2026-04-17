"""
Tests for Doc D automatic versioning + CCEE traceability.

Coverage:
1. _snapshot_doc_d writes to doc_d_versions with content_hash + metadata
2. _snapshot_doc_d dedup: second call with same content in <24h is skipped
3. _snapshot_doc_d with metadata param persists metadata JSON
4. get_active_doc_d_version_id returns latest version ID for creator
5. compile_persona (weekly_compilation) calls _snapshot_doc_d BEFORE _set_current_doc_d
6. run_ccee output includes doc_d_version_id + doc_d_snapshot_at + doc_d_char_length
7. _snapshot_doc_d with custom tag stored in metadata
"""

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# 1. _snapshot_doc_d writes content_hash + metadata to doc_d_versions
# ---------------------------------------------------------------------------

class TestSnapshotDocDWrite:
    def test_inserts_with_content_hash_and_metadata(self):
        """_snapshot_doc_d inserts row with content_hash SHA256 and metadata JSONB."""
        from services.persona_compiler import _snapshot_doc_d

        session = MagicMock()
        # No existing hash in last 24h (dedup query returns None)
        session.execute.return_value.fetchone.return_value = None

        creator_id = uuid.uuid4()
        doc_text = "Doc D content for testing"
        expected_hash = hashlib.sha256(doc_text.encode()).hexdigest()

        version_id = _snapshot_doc_d(
            session,
            creator_id,
            doc_text,
            "weekly_compilation",
            ["tone", "length"],
            metadata={"trigger": "weekly_compilation_autosave"},
        )

        assert version_id is not None
        assert uuid.UUID(version_id)  # valid UUID

        # Must have called execute at least twice: dedup check + INSERT
        assert session.execute.call_count >= 2

        # Find the INSERT call
        all_calls = [str(c[0][0]) for c in session.execute.call_args_list]
        insert_calls = [s for s in all_calls if "INSERT" in s.upper()]
        assert len(insert_calls) >= 1
        assert "doc_d_versions" in insert_calls[0]

        # Check that content_hash was passed in params
        insert_params = [
            c[0][1] for c in session.execute.call_args_list
            if "INSERT" in str(c[0][0]).upper()
        ]
        assert len(insert_params) >= 1
        assert insert_params[0].get("content_hash") == expected_hash

    def test_insert_sql_includes_metadata_column(self):
        """INSERT SQL must reference metadata column."""
        from services.persona_compiler import _snapshot_doc_d

        session = MagicMock()
        session.execute.return_value.fetchone.return_value = None

        version_id = _snapshot_doc_d(
            session,
            uuid.uuid4(),
            "some doc d text",
            "weekly_compilation",
            metadata={"tag": "pre_arc1_experiment"},
        )

        all_sqls = [str(c[0][0]) for c in session.execute.call_args_list]
        insert_sqls = [s for s in all_sqls if "INSERT" in s.upper()]
        assert any("metadata" in s for s in insert_sqls)


# ---------------------------------------------------------------------------
# 2. SHA256 dedup: same content in <24h is skipped
# ---------------------------------------------------------------------------

class TestSnapshotDocDDedup:
    def test_dedup_skips_when_same_hash_within_24h(self):
        """If identical content_hash exists in last 24h, skip INSERT and return existing ID."""
        from services.persona_compiler import _snapshot_doc_d

        session = MagicMock()
        existing_id = str(uuid.uuid4())
        # Dedup query returns existing row
        session.execute.return_value.fetchone.return_value = (existing_id,)

        doc_text = "Unchanged Doc D content"

        version_id = _snapshot_doc_d(
            session,
            uuid.uuid4(),
            doc_text,
            "weekly_compilation",
        )

        # Must return the existing ID, not a new one
        assert version_id == existing_id

        # Must NOT have issued an INSERT
        all_sqls = [str(c[0][0]) for c in session.execute.call_args_list]
        insert_sqls = [s for s in all_sqls if "INSERT INTO doc_d_versions" in s.upper() or "insert into doc_d_versions" in s]
        assert len(insert_sqls) == 0

    def test_no_dedup_when_content_differs(self):
        """Different content bypasses dedup and issues a fresh INSERT."""
        from services.persona_compiler import _snapshot_doc_d

        session = MagicMock()
        # Dedup query finds no match
        session.execute.return_value.fetchone.return_value = None

        version_id = _snapshot_doc_d(
            session,
            uuid.uuid4(),
            "Updated Doc D with new content",
            "weekly_compilation",
        )

        all_sqls = [str(c[0][0]) for c in session.execute.call_args_list]
        insert_sqls = [s for s in all_sqls if "INSERT" in s.upper() and "doc_d_versions" in s]
        assert len(insert_sqls) >= 1
        assert uuid.UUID(version_id)


# ---------------------------------------------------------------------------
# 3. get_active_doc_d_version_id returns latest snapshot ID
# ---------------------------------------------------------------------------

class TestGetActiveDocDVersionId:
    def test_returns_latest_version_id(self):
        """get_active_doc_d_version_id resolves creator slug → returns latest snapshot ID."""
        from services.persona_compiler import get_active_doc_d_version_id

        expected_version_id = str(uuid.uuid4())
        session = MagicMock()
        # Simulates: creator lookup returns UUID row, version lookup returns version_id row
        session.execute.side_effect = [
            MagicMock(fetchone=MagicMock(return_value=(str(uuid.uuid4()),))),  # creator UUID
            MagicMock(fetchone=MagicMock(return_value=(expected_version_id,))),  # latest version
        ]

        result = get_active_doc_d_version_id(session, "iris_bertran")

        assert result == expected_version_id

    def test_returns_none_when_no_versions(self):
        """Returns None when no snapshots exist for creator."""
        from services.persona_compiler import get_active_doc_d_version_id

        session = MagicMock()
        session.execute.side_effect = [
            MagicMock(fetchone=MagicMock(return_value=(str(uuid.uuid4()),))),  # creator exists
            MagicMock(fetchone=MagicMock(return_value=None)),                  # no versions
        ]

        result = get_active_doc_d_version_id(session, "iris_bertran")
        assert result is None

    def test_returns_none_when_creator_not_found(self):
        """Returns None when creator slug not in DB."""
        from services.persona_compiler import get_active_doc_d_version_id

        session = MagicMock()
        session.execute.return_value.fetchone.return_value = None

        result = get_active_doc_d_version_id(session, "nonexistent_creator")
        assert result is None


# ---------------------------------------------------------------------------
# 4. compile_persona snapshots BEFORE overwriting (ordering guarantee)
# ---------------------------------------------------------------------------

class TestCompilePersonaSnapshotOrder:
    @pytest.mark.asyncio
    @patch("services.persona_compiler._compile_section")
    @patch("api.database.SessionLocal")
    async def test_snapshot_called_before_set(self, mock_session_cls, mock_compile):
        """compile_persona must call _snapshot_doc_d BEFORE _set_current_doc_d."""
        from services.persona_compiler import compile_persona

        session = MagicMock()
        mock_session_cls.return_value = session
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        mock_creator = MagicMock()
        mock_creator.id = uuid.uuid4()
        session.query.return_value.filter_by.return_value.first.return_value = mock_creator

        mock_compile.return_value = "Compiled section text"

        call_order = []

        def record_snapshot(*a, **kw):
            call_order.append("snapshot")
            return str(uuid.uuid4())

        def record_set(*a, **kw):
            call_order.append("set")

        with patch("services.persona_compiler._collect_signals") as mock_collect, \
             patch("services.persona_compiler._get_current_doc_d", return_value="old doc d"), \
             patch("services.persona_compiler._snapshot_doc_d", side_effect=record_snapshot), \
             patch("services.persona_compiler._set_current_doc_d", side_effect=record_set), \
             patch("services.persona_compiler._persist_run"):

            mock_pairs = [MagicMock(id=uuid.uuid4(), action_type="edited",
                                    edit_diff={"categories": ["tone"]}, chosen="ok",
                                    rejected="long") for _ in range(5)]
            mock_collect.return_value = {"pairs": mock_pairs, "feedback": [], "evaluations": []}
            session.query.return_value.filter.return_value.update.return_value = 5

            result = await compile_persona("iris_bertran", uuid.uuid4())

        assert result["status"] == "done"
        assert call_order.index("snapshot") < call_order.index("set"), \
            "snapshot must happen BEFORE set"

    @pytest.mark.asyncio
    @patch("services.persona_compiler._compile_section")
    @patch("api.database.SessionLocal")
    async def test_compile_returns_doc_d_version_id(self, mock_session_cls, mock_compile):
        """compile_persona result includes doc_d_version_id key."""
        from services.persona_compiler import compile_persona

        session = MagicMock()
        mock_session_cls.return_value = session
        session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        mock_creator = MagicMock()
        mock_creator.id = uuid.uuid4()
        session.query.return_value.filter_by.return_value.first.return_value = mock_creator

        mock_compile.return_value = "Compiled section text"
        fake_version_id = str(uuid.uuid4())

        with patch("services.persona_compiler._collect_signals") as mock_collect, \
             patch("services.persona_compiler._get_current_doc_d", return_value="old doc d"), \
             patch("services.persona_compiler._snapshot_doc_d", return_value=fake_version_id), \
             patch("services.persona_compiler._set_current_doc_d"), \
             patch("services.persona_compiler._persist_run"):

            mock_pairs = [MagicMock(id=uuid.uuid4(), action_type="edited",
                                    edit_diff={"categories": ["tone"]}, chosen="ok",
                                    rejected="long") for _ in range(5)]
            mock_collect.return_value = {"pairs": mock_pairs, "feedback": [], "evaluations": []}
            session.query.return_value.filter.return_value.update.return_value = 5

            result = await compile_persona("iris_bertran", uuid.uuid4())

        assert "doc_d_version_id" in result
        assert result["doc_d_version_id"] == fake_version_id


# ---------------------------------------------------------------------------
# 5. run_ccee metadata includes doc_d traceability fields
# ---------------------------------------------------------------------------

class TestCCEEDocDTraceability:
    def test_build_metadata_includes_doc_d_fields(self):
        """_build_metadata must include doc_d_version_id, doc_d_snapshot_at, doc_d_char_length."""
        from scripts.run_ccee import _build_metadata

        args = MagicMock()
        args.v5 = False
        args.v41_metrics = False
        args.cases = 10
        args.runs = 1
        args.mt_conversations = None
        args.mt_turns = None
        args.generate_only = False
        args.multi_turn = False
        args.v4_composite = False
        args.doc_d_version_id = "abc-123"
        args.doc_d_snapshot_at = "2026-04-17T12:00:00"
        args.doc_d_char_length = 47000

        meta = _build_metadata(args)
        assert "doc_d_version_id" in meta
        assert "doc_d_snapshot_at" in meta
        assert "doc_d_char_length" in meta
        assert meta["doc_d_version_id"] == "abc-123"
        assert meta["doc_d_char_length"] == 47000

    def test_build_metadata_doc_d_fields_none_when_not_provided(self):
        """When doc_d args not set, fields are None (graceful degradation)."""
        from scripts.run_ccee import _build_metadata

        args = MagicMock(spec=[
            "v5", "v41_metrics", "cases", "runs", "mt_conversations",
            "mt_turns", "generate_only", "multi_turn", "v4_composite", "v41_metrics",
        ])
        args.v5 = False
        args.v41_metrics = False
        args.cases = 5
        args.runs = 1
        args.mt_conversations = None
        args.mt_turns = None
        args.generate_only = False
        args.multi_turn = False
        args.v4_composite = False

        meta = _build_metadata(args)
        # Fields must exist (None is acceptable, missing is not)
        assert "doc_d_version_id" in meta
        assert "doc_d_snapshot_at" in meta
        assert "doc_d_char_length" in meta


# ---------------------------------------------------------------------------
# 6. _snapshot_doc_d with custom tag stored in metadata
# ---------------------------------------------------------------------------

class TestSnapshotWithCustomTag:
    def test_custom_tag_in_metadata(self):
        """Custom tag is stored in metadata JSON."""
        from services.persona_compiler import _snapshot_doc_d

        session = MagicMock()
        session.execute.return_value.fetchone.return_value = None  # no dedup match

        version_id = _snapshot_doc_d(
            session,
            uuid.uuid4(),
            "doc d content",
            "manual_snapshot",
            metadata={"tag": "pre_arc1_experiment", "trigger": "manual"},
        )

        # Find the INSERT params
        insert_params = [
            c[0][1] for c in session.execute.call_args_list
            if "INSERT" in str(c[0][0]).upper()
        ]
        assert len(insert_params) >= 1
        stored_meta = insert_params[0].get("metadata")
        if isinstance(stored_meta, str):
            stored_meta = json.loads(stored_meta)
        assert stored_meta.get("tag") == "pre_arc1_experiment"
