"""Tests for LeadMemoryService (ARC2 A2.1).

Uses a mock SQLAlchemy session — no real DB required for unit tests.
DB-level CHECK constraint tests are marked with @pytest.mark.db and
skipped unless a real DB is available (integration tests via CCEE).
"""

import logging
import uuid
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from services.lead_memory_service import (
    MEMORY_TYPES,
    LeadMemory,
    LeadMemoryService,
    validate_body_structure,
    validate_confidence,
    validate_memory_type,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

CREATOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
LEAD_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _make_row(**kwargs: Any) -> MagicMock:
    """Build a row mock that mimics a SQLAlchemy Row."""
    defaults = {
        "id": uuid.uuid4(),
        "creator_id": CREATOR_ID,
        "lead_id": LEAD_ID,
        "memory_type": "identity",
        "content": "Se llama Manel",
        "why": None,
        "how_to_apply": None,
        "body_extras": {},
        "embedding": None,
        "source_message_id": None,
        "confidence": 1.0,
        "last_writer": "dm_extractor",
        "created_at": None,
        "updated_at": None,
        "deleted_at": None,
        "superseded_by": None,
    }
    defaults.update(kwargs)
    row = MagicMock()
    for k, v in defaults.items():
        setattr(row, k, v)
    return row


def _make_service(fetchone=None, fetchall=None, rowcount=0):
    """Return (service, mock_session) pair."""
    session = MagicMock()
    # execute().fetchone() / fetchall()
    exec_result = MagicMock()
    exec_result.fetchone.return_value = fetchone
    exec_result.fetchall.return_value = fetchall or []
    exec_result.rowcount = rowcount
    session.execute.return_value = exec_result
    return LeadMemoryService(session), session


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_memory_type_valid():
    for t in MEMORY_TYPES:
        validate_memory_type(t)  # must not raise


def test_validate_memory_type_invalid():
    with pytest.raises(ValueError, match="Invalid memory_type"):
        validate_memory_type("unknown_type")


def test_validate_body_structure_missing_why_for_objection():
    with pytest.raises(ValueError, match="requires 'why'"):
        validate_body_structure("objection", why=None, how_to_apply="do X")


def test_validate_body_structure_missing_how_to_apply_for_objection():
    with pytest.raises(ValueError, match="requires 'how_to_apply'"):
        validate_body_structure("objection", why="lead said too expensive", how_to_apply=None)


def test_validate_body_structure_missing_why_for_relationship_state():
    with pytest.raises(ValueError, match="requires 'why'"):
        validate_body_structure("relationship_state", why=None, how_to_apply="send reactivation")


def test_validate_body_structure_missing_how_to_apply_for_relationship_state():
    with pytest.raises(ValueError, match="requires 'how_to_apply'"):
        validate_body_structure("relationship_state", why="went cold", how_to_apply=None)


def test_validate_body_structure_identity_no_why_required():
    # identity does NOT require why/how_to_apply
    validate_body_structure("identity", why=None, how_to_apply=None)  # must not raise


def test_validate_body_structure_interest_no_why_required():
    validate_body_structure("interest", why=None, how_to_apply=None)  # must not raise


def test_validate_confidence_valid():
    validate_confidence(0.0)
    validate_confidence(0.5)
    validate_confidence(1.0)  # must not raise


def test_validate_confidence_out_of_range_above():
    with pytest.raises(ValueError, match="confidence must be in"):
        validate_confidence(1.1)


def test_validate_confidence_out_of_range_below():
    with pytest.raises(ValueError, match="confidence must be in"):
        validate_confidence(-0.1)


# ─────────────────────────────────────────────────────────────────────────────
# upsert — happy path
# ─────────────────────────────────────────────────────────────────────────────

def test_upsert_creates_new_memory():
    row = _make_row(memory_type="identity", content="nombre: Manel")
    svc, session = _make_service(fetchone=row)
    # First fetchone (existing check) → None, second (RETURNING) → row
    results = [None, row]
    session.execute.return_value.fetchone.side_effect = results

    mem = svc.upsert(
        creator_id=CREATOR_ID,
        lead_id=LEAD_ID,
        memory_type="identity",
        content="nombre: Manel",
        last_writer="dm_extractor",
    )

    assert mem.memory_type == "identity"
    assert mem.content == "nombre: Manel"
    session.commit.assert_called_once()


def test_upsert_updates_existing_memory_same_writer():
    existing = _make_row(last_writer="dm_extractor")
    updated = _make_row(last_writer="dm_extractor", confidence=0.9)
    session = MagicMock()
    calls = [existing, updated]
    session.execute.return_value.fetchone.side_effect = calls
    svc = LeadMemoryService(session)

    mem = svc.upsert(
        creator_id=CREATOR_ID,
        lead_id=LEAD_ID,
        memory_type="identity",
        content="nombre: Manel",
        last_writer="dm_extractor",
        confidence=0.9,
    )

    assert mem.confidence == 0.9
    session.commit.assert_called_once()


def test_upsert_with_different_last_writer_logs_warning(caplog):
    existing = _make_row(last_writer="copilot")
    updated = _make_row(last_writer="dm_extractor")
    session = MagicMock()
    session.execute.return_value.fetchone.side_effect = [existing, updated]
    svc = LeadMemoryService(session)

    with caplog.at_level(logging.WARNING, logger="services.lead_memory_service"):
        svc.upsert(
            creator_id=CREATOR_ID,
            lead_id=LEAD_ID,
            memory_type="identity",
            content="nombre: Manel",
            last_writer="dm_extractor",
        )

    assert "writer conflict" in caplog.text
    assert "copilot" in caplog.text
    assert "dm_extractor" in caplog.text


def test_upsert_objection_with_required_fields():
    row = _make_row(
        memory_type="objection",
        content="Es muy caro",
        why="dijo que no puede pagarlo",
        how_to_apply="ofrecer plan de pago",
    )
    session = MagicMock()
    session.execute.return_value.fetchone.side_effect = [None, row]
    svc = LeadMemoryService(session)

    mem = svc.upsert(
        creator_id=CREATOR_ID,
        lead_id=LEAD_ID,
        memory_type="objection",
        content="Es muy caro",
        last_writer="dm_extractor",
        why="dijo que no puede pagarlo",
        how_to_apply="ofrecer plan de pago",
    )

    assert mem.memory_type == "objection"
    assert mem.why == "dijo que no puede pagarlo"


def test_upsert_objection_missing_why_raises():
    svc, _ = _make_service()
    with pytest.raises(ValueError, match="requires 'why'"):
        svc.upsert(
            creator_id=CREATOR_ID,
            lead_id=LEAD_ID,
            memory_type="objection",
            content="Es muy caro",
            last_writer="dm_extractor",
            why=None,
            how_to_apply="ofrecer plan de pago",
        )


def test_upsert_invalid_memory_type_raises():
    svc, _ = _make_service()
    with pytest.raises(ValueError, match="Invalid memory_type"):
        svc.upsert(
            creator_id=CREATOR_ID,
            lead_id=LEAD_ID,
            memory_type="bad_type",
            content="x",
            last_writer="dm_extractor",
        )


def test_upsert_confidence_out_of_range_raises():
    svc, _ = _make_service()
    with pytest.raises(ValueError, match="confidence must be in"):
        svc.upsert(
            creator_id=CREATOR_ID,
            lead_id=LEAD_ID,
            memory_type="identity",
            content="x",
            last_writer="dm_extractor",
            confidence=1.5,
        )


# ─────────────────────────────────────────────────────────────────────────────
# get_all / get_by_type
# ─────────────────────────────────────────────────────────────────────────────

def test_get_by_lead_returns_all_types():
    rows = [
        _make_row(memory_type="identity"),
        _make_row(memory_type="interest"),
        _make_row(memory_type="objection", why="w", how_to_apply="h"),
    ]
    svc, _ = _make_service(fetchall=rows)

    result = svc.get_all(CREATOR_ID, LEAD_ID)

    assert len(result) == 3
    types = {m.memory_type for m in result}
    assert types == {"identity", "interest", "objection"}


def test_get_by_lead_filtered_by_type():
    rows = [_make_row(memory_type="interest")]
    svc, _ = _make_service(fetchall=rows)

    result = svc.get_by_type(CREATOR_ID, LEAD_ID, ["interest"])

    assert len(result) == 1
    assert result[0].memory_type == "interest"


def test_get_by_type_invalid_type_raises():
    svc, _ = _make_service()
    with pytest.raises(ValueError, match="Invalid memory_type"):
        svc.get_by_type(CREATOR_ID, LEAD_ID, ["bad_type"])


# ─────────────────────────────────────────────────────────────────────────────
# count_by_type
# ─────────────────────────────────────────────────────────────────────────────

def test_count_by_type_returns_dict_with_all_types():
    row = MagicMock()
    row.memory_type = "identity"
    row.cnt = 3
    svc, _ = _make_service(fetchall=[row])

    result = svc.count_by_type(CREATOR_ID, LEAD_ID)

    assert isinstance(result, dict)
    assert set(result.keys()) == set(MEMORY_TYPES)
    assert result["identity"] == 3
    assert result["interest"] == 0


def test_count_by_type_empty_lead_returns_zeros():
    svc, _ = _make_service(fetchall=[])

    result = svc.count_by_type(CREATOR_ID, LEAD_ID)

    assert all(v == 0 for v in result.values())


# ─────────────────────────────────────────────────────────────────────────────
# delete_by_lead
# ─────────────────────────────────────────────────────────────────────────────

def test_delete_by_lead_returns_count():
    svc, session = _make_service(rowcount=5)
    session.execute.return_value.rowcount = 5

    count = svc.delete_by_lead(CREATOR_ID, LEAD_ID)

    assert count == 5
    session.commit.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# recall_semantic
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skip(reason="requires real DB with pgvector + embeddings")
def test_search_semantic_returns_top_k_by_distance():
    pass


# ─────────────────────────────────────────────────────────────────────────────
# get_current_state
# ─────────────────────────────────────────────────────────────────────────────

def test_get_current_state_snapshot_structure():
    rows = [
        _make_row(memory_type="identity", content="nombre: Manel"),
        _make_row(memory_type="objection", content="caro", why="w", how_to_apply="h"),
        _make_row(memory_type="relationship_state", content="warm", why="w", how_to_apply="h"),
    ]
    svc, _ = _make_service(fetchall=rows)

    snapshot = svc.get_current_state(CREATOR_ID, LEAD_ID)

    assert len(snapshot["identity"]) == 1
    assert len(snapshot["objections"]) == 1
    assert snapshot["relationship_state"] is not None
    assert snapshot["relationship_state"].content == "warm"
