"""
Tests for services/dual_write.py — ARC2 A2.4.

Coverage targets:
  1.  flag OFF → no-op (zero DB calls)
  2.  flag ON, extraction hook → writes to arc2
  3.  flag ON, follower_memory hook → identity/interest/objection/state
  4.  flag ON, conversation_memory hook → interest/objection/intent/identity
  5.  fail-silent: DB error does NOT propagate
  6.  failure counter increments on error
  7.  classification mapping (_MEMORY_EXTRACTION_MAP)
  8.  dedup: same content upserted, not inserted twice
  9.  compressed_memo fact type → skipped
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.dual_write import (
    DualWriteEntry,
    _CONV_FACT_MAP,
    _MEMORY_EXTRACTION_MAP,
    dual_write_from_conversation_memory,
    dual_write_from_extraction,
    dual_write_from_follower_memory,
    get_failure_count,
    maybe_dual_write,
    reset_failure_counters,
)

CREATOR_UUID = str(uuid.uuid4())
LEAD_UUID = str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_flags(dual_write_on: bool):
    flags = MagicMock()
    flags.dual_write_lead_memories = dual_write_on
    return flags


def _patch_flags(dual_write_on: bool):
    return patch("core.feature_flags.flags", _make_flags(dual_write_on))


def _patch_resolve(creator_uuid=CREATOR_UUID, lead_uuid=LEAD_UUID):
    return [
        patch(
            "services.dual_write._resolve_creator_uuid",
            new=AsyncMock(return_value=creator_uuid),
        ),
        patch(
            "services.dual_write._resolve_lead_uuid",
            new=AsyncMock(return_value=lead_uuid),
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Flag OFF → no-op
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_flag_off_no_db_call():
    with _patch_flags(False):
        with patch("services.dual_write._resolve_creator_uuid") as mock_res:
            await maybe_dual_write(
                CREATOR_UUID,
                LEAD_UUID,
                [DualWriteEntry(memory_type="identity", content="Alice")],
                "test_source",
            )
            mock_res.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Extraction hook writes entries
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extraction_hook_writes():
    facts = [
        {"type": "personal_info", "text": "Name is Bob", "confidence": 0.9},
        {"type": "preference", "text": "Likes fitness", "confidence": 0.8},
    ]
    upsert_calls = []

    def fake_write_sync(fn, creator_uuid, lead_uuid, entries, source):
        upsert_calls.extend(entries)
        return len(entries)

    with _patch_flags(True):
        patches = _patch_resolve()
        with patches[0], patches[1]:
            with patch("asyncio.to_thread", new=AsyncMock(side_effect=fake_write_sync)):
                await dual_write_from_extraction(CREATOR_UUID, LEAD_UUID, facts)

    assert len(upsert_calls) == 2
    types = {e.memory_type for e in upsert_calls}
    assert "identity" in types
    assert "interest" in types


# ─────────────────────────────────────────────────────────────────────────────
# 3. Follower memory hook: name + interest + objection + status
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_follower_memory_hook():
    memory = MagicMock()
    memory.name = "Maria"
    memory.interests = ["yoga", "nutrition"]
    memory.objections_raised = ["too expensive"]
    memory.is_customer = False
    memory.status = "hot"
    memory.creator_id = CREATOR_UUID
    memory.follower_id = LEAD_UUID

    upsert_calls = []

    def fake_write_sync(fn, creator_uuid, lead_uuid, entries, source):
        upsert_calls.extend(entries)
        return len(entries)

    with _patch_flags(True):
        patches = _patch_resolve()
        with patches[0], patches[1]:
            with patch("asyncio.to_thread", new=AsyncMock(side_effect=fake_write_sync)):
                await dual_write_from_follower_memory(memory)

    types = [e.memory_type for e in upsert_calls]
    assert "identity" in types
    assert "interest" in types
    assert "objection" in types
    assert "relationship_state" in types
    assert types.count("interest") == 2


# ─────────────────────────────────────────────────────────────────────────────
# 4. Conversation memory hook: interest/objection/intent/identity
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_conversation_memory_hook():
    fact_interest = MagicMock()
    fact_interest.fact_type = MagicMock(value="interest")
    fact_interest.content = "Loves CrossFit"
    fact_interest.confidence = 0.85

    fact_objection = MagicMock()
    fact_objection.fact_type = MagicMock(value="objection")
    fact_objection.content = "Price is too high"
    fact_objection.confidence = 0.9

    fact_name = MagicMock()
    fact_name.fact_type = MagicMock(value="name_used")
    fact_name.content = "Carlos"
    fact_name.confidence = 0.95

    fact_bot = MagicMock()
    fact_bot.fact_type = MagicMock(value="price_given")
    fact_bot.content = "150€"
    fact_bot.confidence = 1.0

    memory = MagicMock()
    memory.facts = [fact_interest, fact_objection, fact_name, fact_bot]
    memory.creator_id = CREATOR_UUID
    memory.lead_id = LEAD_UUID

    upsert_calls = []

    def fake_write_sync(fn, creator_uuid, lead_uuid, entries, source):
        upsert_calls.extend(entries)
        return len(entries)

    with _patch_flags(True):
        patches = _patch_resolve()
        with patches[0], patches[1]:
            with patch("asyncio.to_thread", new=AsyncMock(side_effect=fake_write_sync)):
                await dual_write_from_conversation_memory(memory)

    types = [e.memory_type for e in upsert_calls]
    assert "interest" in types
    assert "objection" in types
    assert "identity" in types
    # price_given is bot-side → skipped
    assert types.count("interest") + types.count("objection") + types.count("identity") == 3


# ─────────────────────────────────────────────────────────────────────────────
# 5. Fail-silent: DB error does NOT propagate
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fail_silent_on_db_error():
    reset_failure_counters()
    entries = [DualWriteEntry(memory_type="identity", content="Test")]

    with _patch_flags(True):
        patches = _patch_resolve()
        with patches[0], patches[1]:
            with patch(
                "asyncio.to_thread",
                new=AsyncMock(side_effect=RuntimeError("DB exploded")),
            ):
                # Should NOT raise
                await maybe_dual_write(CREATOR_UUID, LEAD_UUID, entries, "test_src")

    # No uncaught exception means pass


# ─────────────────────────────────────────────────────────────────────────────
# 6. Failure counter increments on error
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_failure_counter_increments():
    reset_failure_counters()
    entries = [DualWriteEntry(memory_type="interest", content="yoga")]

    with _patch_flags(True):
        patches = _patch_resolve()
        with patches[0], patches[1]:
            with patch(
                "asyncio.to_thread",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ):
                await maybe_dual_write(CREATOR_UUID, LEAD_UUID, entries, "counter_src")

    assert get_failure_count("counter_src") == 1


# ─────────────────────────────────────────────────────────────────────────────
# 7. Classification mapping
# ─────────────────────────────────────────────────────────────────────────────

def test_memory_extraction_map_coverage():
    assert _MEMORY_EXTRACTION_MAP["personal_info"] == "identity"
    assert _MEMORY_EXTRACTION_MAP["preference"] == "interest"
    assert _MEMORY_EXTRACTION_MAP["objection"] == "objection"
    assert _MEMORY_EXTRACTION_MAP["purchase_history"] == "intent_signal"
    assert _MEMORY_EXTRACTION_MAP["commitment"] == "relationship_state"
    assert _MEMORY_EXTRACTION_MAP["topic"] == "interest"
    assert _MEMORY_EXTRACTION_MAP["compressed_memo"] is None


def test_conv_fact_map_skips_bot_side():
    assert _CONV_FACT_MAP["price_given"] is None
    assert _CONV_FACT_MAP["link_shared"] is None
    assert _CONV_FACT_MAP["product_explained"] is None
    assert _CONV_FACT_MAP["question_asked"] is None
    assert _CONV_FACT_MAP["question_answered"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 8. Dedup: ON CONFLICT upsert (second call for same content returns without dup)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dedup_upsert_called_once_per_entry():
    entries = [DualWriteEntry(memory_type="identity", content="Alice")]
    call_count = []

    def fake_write_sync(fn, creator_uuid, lead_uuid, entries_inner, source):
        call_count.append(len(entries_inner))
        return len(entries_inner)

    with _patch_flags(True):
        patches = _patch_resolve()
        with patches[0], patches[1]:
            with patch("asyncio.to_thread", new=AsyncMock(side_effect=fake_write_sync)):
                await maybe_dual_write(CREATOR_UUID, LEAD_UUID, entries, "dedup_test")
                await maybe_dual_write(CREATOR_UUID, LEAD_UUID, entries, "dedup_test")

    assert len(call_count) == 2  # called twice but DB handles dedup via ON CONFLICT


# ─────────────────────────────────────────────────────────────────────────────
# 9. compressed_memo skipped
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compressed_memo_skipped():
    facts = [
        {"type": "compressed_memo", "text": "Summary of conversation", "confidence": 1.0},
    ]
    upsert_calls = []

    def fake_write_sync(fn, creator_uuid, lead_uuid, entries, source):
        upsert_calls.extend(entries)
        return len(entries)

    with _patch_flags(True):
        patches = _patch_resolve()
        with patches[0], patches[1]:
            with patch("asyncio.to_thread", new=AsyncMock(side_effect=fake_write_sync)):
                await dual_write_from_extraction(CREATOR_UUID, LEAD_UUID, facts)

    assert len(upsert_calls) == 0
