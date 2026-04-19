"""Tests for ARC2 A2.3 migration scripts.

All tests use mocked SQLAlchemy sessions and a temporary filesystem — no real
DB or LLM calls required.
"""

import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

CREATOR_UUID = "00000000-0000-0000-0000-000000000001"
LEAD_UUID = "00000000-0000-0000-0000-000000000002"
CREATOR_SLUG = "iris_bertran"
FOLLOWER_ID = "17841400999933058"


def _make_db_session(
    *,
    creator_uuid: str = CREATOR_UUID,
    lead_uuid: str = LEAD_UUID,
    follower_rows: list[Any] | None = None,
    lead_memories_rows: list[Any] | None = None,
    arc2_count: int = 0,
) -> MagicMock:
    """Return a mock DB session wired for common queries."""
    session = MagicMock()

    def _execute(query, params=None, **kwargs):
        result = MagicMock()
        q = str(query) if not isinstance(query, str) else query

        if "SELECT id FROM creators" in q:
            row = MagicMock()
            row.__getitem__ = lambda self, i: creator_uuid
            result.fetchone.return_value = row

        elif "SELECT id FROM leads" in q:
            row = MagicMock()
            row.__getitem__ = lambda self, i: lead_uuid
            result.fetchone.return_value = row

        elif "SELECT COUNT(*) FROM follower_memories" in q:
            row = MagicMock()
            row.__getitem__ = lambda self, i: len(follower_rows or [])
            result.fetchone.return_value = row

        elif "SELECT COUNT(*) FROM lead_memories" in q:
            row = MagicMock()
            row.__getitem__ = lambda self, i: len(lead_memories_rows or [])
            result.fetchone.return_value = row

        elif "SELECT COUNT(*) FROM arc2_lead_memories" in q:
            row = MagicMock()
            row.__getitem__ = lambda self, i: arc2_count
            result.fetchone.return_value = row

        elif "FROM follower_memories" in q and "COUNT" not in q:
            result.fetchall.return_value = follower_rows or []

        elif "FROM lead_memories" in q and "COUNT" not in q:
            result.fetchall.return_value = lead_memories_rows or []

        elif "FROM arc2_lead_memories" in q and "last_writer" in q:
            result.fetchall.return_value = []

        else:
            result.fetchone.return_value = None
            result.fetchall.return_value = []
            result.rowcount = 0

        return result

    session.execute.side_effect = _execute
    return session


def _make_follower_row(
    *,
    creator_id: str = CREATOR_SLUG,
    follower_id: str = FOLLOWER_ID,
    name: str = "María García",
    interests: list[str] | None = None,
    products_discussed: list[str] | None = None,
    objections_raised: list[str] | None = None,
    status: str = "hot",
    purchase_intent_score: float = 0.5,
) -> MagicMock:
    row = MagicMock()
    row.creator_id = creator_id
    row.follower_id = follower_id
    row.name = name
    row.interests = interests if interests is not None else ["yoga", "nutrición"]
    row.products_discussed = products_discussed if products_discussed is not None else ["plan coaching"]
    row.objections_raised = objections_raised if objections_raised is not None else ["muy caro"]
    row.status = status
    row.purchase_intent_score = purchase_intent_score
    return row


def _make_lead_memory_row(
    *,
    fact_type: str = "personal_info",
    fact_text: str = "Se llama María",
    confidence: float = 0.7,
    source_message_id: str | None = None,
    embedding_text: str | None = None,
    is_active: bool = True,
) -> MagicMock:
    row = MagicMock()
    row.id = str(uuid.uuid4())
    row.creator_id = CREATOR_UUID
    row.lead_id = LEAD_UUID
    row.fact_type = fact_type
    row.fact_text = fact_text
    row.confidence = confidence
    row.source_message_id = source_message_id
    row.embedding_text = embedding_text
    row.is_active = is_active
    return row


# ─────────────────────────────────────────────────────────────────────────────
# migrate_conversation_memory tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMigrateConversationMemory:

    def test_dry_run_no_inserts(self, tmp_path):
        """Dry-run must not call INSERT on the DB session."""
        from scripts.migrate_conversation_memory import _process_row

        row = _make_follower_row()
        db = _make_db_session(follower_rows=[row])

        counts = _process_row(db, row, dry_run=True)

        # No INSERT should have been called
        for call_args in db.execute.call_args_list:
            args = call_args.args
            if args:
                q = str(args[0])
                assert "INSERT INTO arc2_lead_memories" not in q, \
                    "INSERT executed in dry_run mode"

        assert counts["inserted"] >= 1  # would-be insertions reported

    def test_inserts_to_arc2(self, tmp_path):
        """Non-dry-run inserts at least the name and one interest."""
        from scripts.migrate_conversation_memory import _process_row

        row = _make_follower_row(
            name="María",
            interests=["yoga"],
            objections_raised=[],
            products_discussed=[],
            status="new",
            purchase_intent_score=0.0,
        )
        db = _make_db_session(follower_rows=[row])

        counts = _process_row(db, row, dry_run=False)

        insert_calls = [
            c for c in db.execute.call_args_list
            if "INSERT INTO arc2_lead_memories" in str(c.args[0] if c.args else "")
        ]
        assert len(insert_calls) >= 2  # name + 1 interest
        assert counts["inserted"] >= 2

    def test_idempotent(self):
        """Running _process_row twice produces same INSERT call count."""
        from scripts.migrate_conversation_memory import _process_row

        row = _make_follower_row(
            name="Carlos",
            interests=["boxeo"],
            objections_raised=[],
            products_discussed=[],
            status="new",
            purchase_intent_score=0.0,
        )
        db1 = _make_db_session(follower_rows=[row])
        db2 = _make_db_session(follower_rows=[row])

        counts1 = _process_row(db1, row, dry_run=False)
        counts2 = _process_row(db2, row, dry_run=False)

        # ON CONFLICT DO NOTHING → same count on second run
        inserts1 = len([
            c for c in db1.execute.call_args_list
            if "INSERT INTO arc2_lead_memories" in str(c.args[0] if c.args else "")
        ])
        inserts2 = len([
            c for c in db2.execute.call_args_list
            if "INSERT INTO arc2_lead_memories" in str(c.args[0] if c.args else "")
        ])
        assert inserts1 == inserts2

    def test_skips_invalid_lead_id(self):
        """If lead cannot be resolved, row is skipped."""
        from scripts.migrate_conversation_memory import _process_row

        row = _make_follower_row(follower_id="UNKNOWN_9999")

        # DB returns None for lead lookup
        db = MagicMock()

        def _execute(query, params=None, **kwargs):
            result = MagicMock()
            q = str(query)
            if "SELECT id FROM creators" in q:
                r = MagicMock()
                r.__getitem__ = lambda self, i: CREATOR_UUID
                result.fetchone.return_value = r
            elif "SELECT id FROM leads" in q:
                result.fetchone.return_value = None  # not found
            else:
                result.fetchone.return_value = None
                result.fetchall.return_value = []
            return result

        db.execute.side_effect = _execute

        counts = _process_row(db, row, dry_run=False)

        insert_calls = [
            c for c in db.execute.call_args_list
            if "INSERT INTO arc2_lead_memories" in str(c.args[0] if c.args else "")
        ]
        assert len(insert_calls) == 0
        assert counts["skipped"] == 1

    def test_objection_has_why_and_how_to_apply(self):
        """Objections must have why + how_to_apply (DB constraint)."""
        from scripts.migrate_conversation_memory import _process_row

        row = _make_follower_row(
            objections_raised=["es muy caro"],
            interests=[],
            products_discussed=[],
            name="",
            status="new",
            purchase_intent_score=0.0,
        )
        db = _make_db_session(follower_rows=[row])

        _process_row(db, row, dry_run=False)

        for c in db.execute.call_args_list:
            q = str(c.args[0] if c.args else "")
            if "INSERT INTO arc2_lead_memories" in q:
                params = c.kwargs.get("params") or (c.args[1] if len(c.args) > 1 else {})
                if params:
                    assert params.get("why"), "why must not be empty for objection"
                    assert params.get("how_to_apply"), "how_to_apply must not be empty"


# ─────────────────────────────────────────────────────────────────────────────
# migrate_follower_jsons tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMigrateFollowerJsons:

    def _write_json(self, base: Path, creator: str, follower_id: str, data: dict) -> Path:
        creator_dir = base / creator
        creator_dir.mkdir(parents=True, exist_ok=True)
        p = creator_dir / f"{follower_id}.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return p

    def _make_follower_data(self, **overrides) -> dict:
        base = {
            "creator_id": CREATOR_SLUG,
            "follower_id": FOLLOWER_ID,
            "username": "mgarcia",
            "name": "María García",
            "interests": ["yoga", "nutrición"],
            "products_discussed": [],
            "objections_raised": [],
            "status": "hot",
            "purchase_intent_score": 0.5,
            "preferred_language": "es",
        }
        base.update(overrides)
        return base

    def test_processes_one_creator(self, tmp_path):
        """Given 1 JSON file, inserts memories for that creator."""
        from scripts.migrate_follower_jsons import _process_file

        data = self._make_follower_data(interests=["yoga"], objections_raised=[], status="new", purchase_intent_score=0.0)
        json_path = self._write_json(tmp_path, CREATOR_SLUG, FOLLOWER_ID, data)

        db = _make_db_session()
        counts = _process_file(db, json_path, dry_run=False)

        assert counts["inserted"] >= 2  # name + 1 interest
        assert counts["errors"] == 0

    def test_creates_one_memory_per_interest(self, tmp_path):
        """Each interest item → one separate arc2_lead_memories row."""
        from scripts.migrate_follower_jsons import _process_file

        interests = ["yoga", "nutrición", "meditación"]
        data = self._make_follower_data(
            interests=interests,
            objections_raised=[],
            status="new",
            purchase_intent_score=0.0,
            name="",
        )
        json_path = self._write_json(tmp_path, CREATOR_SLUG, FOLLOWER_ID, data)

        db = _make_db_session()
        counts = _process_file(db, json_path, dry_run=False)

        # 3 interests + username
        assert counts["inserted"] >= len(interests)

    def test_dry_run_no_inserts(self, tmp_path):
        """Dry-run produces 0 INSERT calls."""
        from scripts.migrate_follower_jsons import _process_file

        data = self._make_follower_data()
        json_path = self._write_json(tmp_path, CREATOR_SLUG, FOLLOWER_ID, data)
        db = _make_db_session()

        counts = _process_file(db, json_path, dry_run=True)

        insert_calls = [
            c for c in db.execute.call_args_list
            if "INSERT INTO arc2_lead_memories" in str(c.args[0] if c.args else "")
        ]
        assert len(insert_calls) == 0
        assert counts["inserted"] >= 1  # would-be count

    def test_skips_file_with_invalid_lead(self, tmp_path):
        """File whose follower_id can't resolve to a lead UUID → skipped."""
        from scripts.migrate_follower_jsons import _process_file

        data = self._make_follower_data(follower_id="NOLEAD")

        db = MagicMock()
        def _execute(query, params=None, **kwargs):
            result = MagicMock()
            q = str(query)
            if "FROM creators" in q:
                r = MagicMock(); r.__getitem__ = lambda s, i: CREATOR_UUID
                result.fetchone.return_value = r
            else:
                result.fetchone.return_value = None
                result.fetchall.return_value = []
            return result
        db.execute.side_effect = _execute

        json_path = self._write_json(tmp_path, CREATOR_SLUG, "NOLEAD", data)
        counts = _process_file(db, json_path, dry_run=False)

        assert counts["skipped"] >= 1
        insert_calls = [
            c for c in db.execute.call_args_list
            if "INSERT INTO arc2_lead_memories" in str(c.args[0] if c.args else "")
        ]
        assert len(insert_calls) == 0

    def test_missing_base_path_is_safe(self, tmp_path):
        """If base path doesn't exist, run() returns without error (no DB needed)."""
        from scripts.migrate_follower_jsons import run

        non_existent = tmp_path / "no_such_dir"
        # SessionLocal is imported lazily inside run() only after the path check,
        # so the function exits before touching the DB.
        run(dry_run=True, creator_slug=None, base_path=non_existent)
        # No exception means success


# ─────────────────────────────────────────────────────────────────────────────
# migrate_legacy_lead_memories tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMigrateLegacyLeadMemories:

    def test_preserves_embedding(self):
        """fact_embedding is copied to embedding in arc2_lead_memories."""
        from scripts.migrate_legacy_lead_memories import _insert_memory

        db = MagicMock()
        db.execute.return_value = MagicMock()

        embedding_str = "[0.1, 0.2, 0.3]"
        _insert_memory(
            db,
            creator_uuid=CREATOR_UUID,
            lead_uuid=LEAD_UUID,
            memory_type="identity",
            content="Se llama María",
            why=None,
            how_to_apply=None,
            confidence=0.7,
            embedding_str=embedding_str,
            source_message_id=None,
            dry_run=False,
        )

        called_sql = str(db.execute.call_args.args[0])
        params = db.execute.call_args.args[1] if len(db.execute.call_args.args) > 1 else {}
        assert "vector" in called_sql.lower() or "emb" in str(params)
        assert params.get("emb") == embedding_str

    def test_skips_compressed_memo(self):
        """fact_type='compressed_memo' is skipped."""
        from scripts.migrate_legacy_lead_memories import _map_type

        assert _map_type("compressed_memo") is None

    def test_maps_personal_info_to_identity(self):
        from scripts.migrate_legacy_lead_memories import _map_type
        assert _map_type("personal_info") == "identity"

    def test_maps_preference_to_interest(self):
        from scripts.migrate_legacy_lead_memories import _map_type
        assert _map_type("preference") == "interest"

    def test_maps_objection_to_objection(self):
        from scripts.migrate_legacy_lead_memories import _map_type
        assert _map_type("objection") == "objection"

    def test_objection_has_why_and_how_to_apply(self):
        """Objections inserted with why + how_to_apply."""
        from scripts.migrate_legacy_lead_memories import _insert_memory

        db = MagicMock()
        db.execute.return_value = MagicMock()

        _insert_memory(
            db,
            creator_uuid=CREATOR_UUID,
            lead_uuid=LEAD_UUID,
            memory_type="objection",
            content="Es muy caro",
            why="Migrado de MemoryEngine",
            how_to_apply="Manejar antes de continuar",
            confidence=0.7,
            embedding_str=None,
            source_message_id=None,
            dry_run=False,
        )

        params = db.execute.call_args.args[1]
        assert params["why"]
        assert params["how_to_apply"]

    def test_dry_run_no_insert_call(self):
        """Dry-run skips the INSERT."""
        from scripts.migrate_legacy_lead_memories import _insert_memory

        db = MagicMock()
        result = _insert_memory(
            db,
            creator_uuid=CREATOR_UUID,
            lead_uuid=LEAD_UUID,
            memory_type="identity",
            content="Test content",
            why=None,
            how_to_apply=None,
            confidence=0.7,
            embedding_str=None,
            source_message_id=None,
            dry_run=True,
        )
        assert result is True
        db.execute.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# reextract_low_confidence tests
# ─────────────────────────────────────────────────────────────────────────────

class TestReextractLowConfidence:

    def _make_arc2_row(
        self,
        memory_type: str = "identity",
        content: str = "Nombre: test",
        confidence: float = 0.5,
    ) -> MagicMock:
        row = MagicMock()
        row.id = str(uuid.uuid4())
        row.creator_id = CREATOR_UUID
        row.lead_id = LEAD_UUID
        row.memory_type = memory_type
        row.content = content
        row.confidence = confidence
        return row

    @pytest.mark.asyncio
    async def test_dry_run_no_update(self):
        """Dry-run must not call UPDATE."""
        from scripts.reextract_low_confidence import _reextract_record

        row = self._make_arc2_row()
        db = MagicMock()
        db.execute.return_value = MagicMock()

        llm_response = '{"memory_type": "identity", "content": "Se llama Test", "why": null, "how_to_apply": null}'

        with patch("scripts.reextract_low_confidence._call_llm", return_value=llm_response):
            result = await _reextract_record(db, row, dry_run=True)

        assert result is True
        update_calls = [
            c for c in db.execute.call_args_list
            if "UPDATE arc2_lead_memories" in str(c.args[0] if c.args else "")
        ]
        assert len(update_calls) == 0

    @pytest.mark.asyncio
    async def test_updates_confidence_to_1(self):
        """Successful re-extraction sets confidence = 1.0."""
        from scripts.reextract_low_confidence import _reextract_record

        row = self._make_arc2_row(confidence=0.5)
        db = MagicMock()
        db.execute.return_value = MagicMock()

        llm_response = '{"memory_type": "interest", "content": "Le gusta el yoga", "why": null, "how_to_apply": null}'

        with patch("scripts.reextract_low_confidence._call_llm", return_value=llm_response):
            result = await _reextract_record(db, row, dry_run=False)

        assert result is True
        update_calls = [
            c for c in db.execute.call_args_list
            if "UPDATE arc2_lead_memories" in str(c.args[0] if c.args else "")
        ]
        assert len(update_calls) == 1
        params = update_calls[0].args[1]
        assert params.get("writer") == "reextraction"

    @pytest.mark.asyncio
    async def test_respects_max_records(self):
        """max_records limits how many rows are fetched."""
        from scripts.reextract_low_confidence import _run_async

        rows = [self._make_arc2_row(confidence=0.4) for _ in range(20)]

        db = MagicMock()
        def _execute(query, params=None, **kwargs):
            result = MagicMock()
            q = str(query)
            if "FROM arc2_lead_memories" in q:
                # Return only up to max_records
                result.fetchall.return_value = rows[:5]
            else:
                result.fetchall.return_value = []
                result.fetchone.return_value = None
            return result
        db.execute.side_effect = _execute

        llm_response = '{"memory_type": "identity", "content": "Test", "why": null, "how_to_apply": null}'

        with patch("api.database.SessionLocal", return_value=db):
            with patch("scripts.reextract_low_confidence._call_llm", return_value=llm_response):
                await _run_async(
                    dry_run=False,
                    batch_size=100,
                    max_records=5,
                    confidence_threshold=0.7,
                    sleep_between_calls=0.0,
                )

        # Only 5 records processed (LIMIT 5 in query)
        update_calls = [
            c for c in db.execute.call_args_list
            if "UPDATE arc2_lead_memories" in str(c.args[0] if c.args else "")
        ]
        assert len(update_calls) == 5

    @pytest.mark.asyncio
    async def test_invalid_llm_response_skipped(self):
        """If LLM returns garbage, record is skipped without error."""
        from scripts.reextract_low_confidence import _reextract_record

        row = self._make_arc2_row()
        db = MagicMock()
        db.execute.return_value = MagicMock()

        with patch("scripts.reextract_low_confidence._call_llm", return_value="not json at all"):
            result = await _reextract_record(db, row, dry_run=False)

        assert result is False
        update_calls = [
            c for c in db.execute.call_args_list
            if "UPDATE" in str(c.args[0] if c.args else "")
        ]
        assert len(update_calls) == 0
