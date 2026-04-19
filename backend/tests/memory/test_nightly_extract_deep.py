"""Tests for scripts/nightly_extract_deep.py — ARC2 bonus: nightly extract_deep scheduler.

Unit tests — no DB, no real LLM.
Coverage target: 85%+

Test matrix:
  dry_run:
    - does not call LLM
    - reports candidate leads count

  run_nightly (active):
    - extract_deep called for each active lead
    - results upserted to arc2_lead_memories
    - last_writer is always 'extract_deep_nightly'
    - only processes leads from last 48h (via mock)
    - respects max_leads limit
    - LLM error is fail-silent (continues to next lead)
    - filters by creator_id when provided
    - returns stats dict with correct shape

Patching strategy: run_nightly imports deps inside the function body, so we
patch at the source modules (api.database.SessionLocal, services.*.Class) and
at the script module for module-level helpers (_build_llm_caller, _fetch_*).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Fixtures ─────────────────────────────────────────────────────────────────

_CREATOR_ID = str(uuid.uuid4())
_LEAD_ID_1 = str(uuid.uuid4())
_LEAD_ID_2 = str(uuid.uuid4())

_MEMORY_OBJECTION = SimpleNamespace(
    type="objection",
    fact="Lead finds price too high",
    why="Said 'está muy caro'",
    how_to_apply="Lead with value not price",
    confidence=0.85,
)
_MEMORY_INTEREST = SimpleNamespace(
    type="interest",
    fact="Lead interested in coaching program",
    why="Asked about program details",
    how_to_apply="Highlight coaching features",
    confidence=0.80,
)

_DUMMY_CONV = [{"role": "user", "content": "Hola, ¿cuánto cuesta el programa?"}]
_EXISTING_MEMORIES: list = []


def _mock_session_factory(lead_pairs=None):
    """Return a callable that returns a MagicMock session each time (like SessionLocal())."""
    pairs = lead_pairs or [(_CREATOR_ID, _LEAD_ID_1)]

    lead_result = MagicMock()
    lead_result.fetchall.return_value = [(c, l) for c, l in pairs]

    conv_result = MagicMock()
    conv_result.fetchall.return_value = [
        ("user", "Hola, quiero más información"),
    ]
    existing_result = MagicMock()
    existing_result.fetchall.return_value = []

    # First call (fetch_lead_pairs), then alternating conv + existing per lead
    per_lead_calls = [conv_result, existing_result] * len(pairs)

    sessions = []

    # Session 0: lead pairs query
    s0 = MagicMock()
    s0.execute.return_value = lead_result
    sessions.append(s0)

    # Sessions 1..N: one per lead (conv + existing)
    for _ in pairs:
        s = MagicMock()
        s.execute.side_effect = [conv_result, existing_result]
        sessions.append(s)

    session_iter = iter(sessions)
    return lambda: next(session_iter)


# ── Tests: dry_run ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dry_run_does_not_call_llm():
    """Dry-run must not invoke _build_llm_caller (no LLM calls)."""
    from scripts.nightly_extract_deep import run_nightly

    factory = _mock_session_factory(lead_pairs=[(_CREATOR_ID, _LEAD_ID_1)])

    with patch("api.database.SessionLocal", factory), \
         patch("scripts.nightly_extract_deep._build_llm_caller") as mock_build:

        result = await run_nightly(dry_run=True, max_leads=10)

    mock_build.assert_not_called()
    assert result["dry_run"] is True


@pytest.mark.asyncio
async def test_dry_run_reports_candidate_leads():
    """Dry-run returns exact candidate count from DB query."""
    from scripts.nightly_extract_deep import run_nightly

    pairs = [(_CREATOR_ID, _LEAD_ID_1), (_CREATOR_ID, _LEAD_ID_2)]
    factory = _mock_session_factory(lead_pairs=pairs)

    with patch("api.database.SessionLocal", factory):
        result = await run_nightly(dry_run=True, max_leads=100)

    assert result["candidates"] == 2


# ── Tests: active run ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_deep_called_per_active_lead():
    """extract_deep is invoked once for each lead in the candidate list."""
    from scripts.nightly_extract_deep import run_nightly

    pairs = [(_CREATOR_ID, _LEAD_ID_1), (_CREATOR_ID, _LEAD_ID_2)]
    factory = _mock_session_factory(lead_pairs=pairs)
    mock_extract_deep = AsyncMock(return_value=[])

    with patch("api.database.SessionLocal", factory), \
         patch("scripts.nightly_extract_deep._build_llm_caller", AsyncMock(return_value=AsyncMock())), \
         patch("services.memory_extractor.MemoryExtractor") as MockExtractor:
        MockExtractor.return_value.extract_deep = mock_extract_deep

        await run_nightly(dry_run=False, max_leads=100)

    assert mock_extract_deep.call_count == 2


@pytest.mark.asyncio
async def test_extract_deep_results_upserted_to_lead_memories():
    """Memories returned by extract_deep are each upserted via LeadMemoryService."""
    from scripts.nightly_extract_deep import run_nightly

    factory = _mock_session_factory(lead_pairs=[(_CREATOR_ID, _LEAD_ID_1)])
    mock_upsert = MagicMock()

    with patch("api.database.SessionLocal", factory), \
         patch("scripts.nightly_extract_deep._build_llm_caller", AsyncMock(return_value=AsyncMock())), \
         patch("services.memory_extractor.MemoryExtractor") as MockExtractor, \
         patch("services.lead_memory_service.LeadMemoryService") as MockSvc:
        MockExtractor.return_value.extract_deep = AsyncMock(return_value=[_MEMORY_OBJECTION])
        MockSvc.return_value.upsert = mock_upsert

        await run_nightly(dry_run=False, max_leads=100)

    assert mock_upsert.call_count == 1
    kwargs = mock_upsert.call_args.kwargs
    assert kwargs["memory_type"] == "objection"
    assert kwargs["content"] == _MEMORY_OBJECTION.fact


@pytest.mark.asyncio
async def test_last_writer_is_extract_deep_nightly():
    """Every upsert call must carry last_writer='extract_deep_nightly'."""
    from scripts.nightly_extract_deep import run_nightly, LAST_WRITER

    factory = _mock_session_factory(lead_pairs=[(_CREATOR_ID, _LEAD_ID_1)])
    mock_upsert = MagicMock()

    with patch("api.database.SessionLocal", factory), \
         patch("scripts.nightly_extract_deep._build_llm_caller", AsyncMock(return_value=AsyncMock())), \
         patch("services.memory_extractor.MemoryExtractor") as MockExtractor, \
         patch("services.lead_memory_service.LeadMemoryService") as MockSvc:
        MockExtractor.return_value.extract_deep = AsyncMock(
            return_value=[_MEMORY_OBJECTION, _MEMORY_INTEREST]
        )
        MockSvc.return_value.upsert = mock_upsert

        await run_nightly(dry_run=False, max_leads=100)

    assert LAST_WRITER == "extract_deep_nightly"
    for c in mock_upsert.call_args_list:
        assert c.kwargs["last_writer"] == "extract_deep_nightly"


@pytest.mark.asyncio
async def test_only_processes_active_leads_last_48h():
    """run_nightly processes exactly the leads returned by _fetch_active_lead_pairs (48h window)."""
    from scripts.nightly_extract_deep import run_nightly, ACTIVE_WINDOW_HOURS

    assert ACTIVE_WINDOW_HOURS == 48

    active_pairs = [(_CREATOR_ID, _LEAD_ID_1)]
    mock_fetch = MagicMock(return_value=active_pairs)

    s = MagicMock()
    conv_result = MagicMock()
    conv_result.fetchall.return_value = [("user", "Hola")]
    existing_result = MagicMock()
    existing_result.fetchall.return_value = []
    s.execute.side_effect = [conv_result, existing_result]

    with patch("api.database.SessionLocal", lambda: s), \
         patch("scripts.nightly_extract_deep._fetch_active_lead_pairs", mock_fetch), \
         patch("scripts.nightly_extract_deep._build_llm_caller", AsyncMock(return_value=AsyncMock())), \
         patch("services.memory_extractor.MemoryExtractor") as MockExtractor:
        MockExtractor.return_value.extract_deep = AsyncMock(return_value=[])

        stats = await run_nightly(dry_run=False, max_leads=1000)

    assert stats["leads_processed"] == 1
    mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_respects_max_leads_limit():
    """max_leads value is forwarded to _fetch_active_lead_pairs."""
    from scripts.nightly_extract_deep import run_nightly

    mock_fetch = MagicMock(return_value=[])

    session = MagicMock()
    session.execute.return_value.fetchall.return_value = []

    with patch("api.database.SessionLocal", lambda: session), \
         patch("scripts.nightly_extract_deep._fetch_active_lead_pairs", mock_fetch):
        await run_nightly(dry_run=True, max_leads=42)

    call_args = mock_fetch.call_args
    assert call_args.args[2] == 42


@pytest.mark.asyncio
async def test_llm_error_continues_to_next_lead():
    """LLM error on one lead must not abort the job — fail-silent, continues to next."""
    from scripts.nightly_extract_deep import run_nightly

    pairs = [(_CREATOR_ID, _LEAD_ID_1), (_CREATOR_ID, _LEAD_ID_2)]
    factory = _mock_session_factory(lead_pairs=pairs)
    mock_upsert = MagicMock()

    call_count = 0

    async def _flaky_extract(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("DeepInfra timeout")
        return [_MEMORY_INTEREST]

    with patch("api.database.SessionLocal", factory), \
         patch("scripts.nightly_extract_deep._build_llm_caller", AsyncMock(return_value=AsyncMock())), \
         patch("services.memory_extractor.MemoryExtractor") as MockExtractor, \
         patch("services.lead_memory_service.LeadMemoryService") as MockSvc:
        MockExtractor.return_value.extract_deep = _flaky_extract
        MockSvc.return_value.upsert = mock_upsert

        stats = await run_nightly(dry_run=False, max_leads=100)

    assert stats["leads_errored"] == 1
    assert stats["leads_processed"] == 1
    assert mock_upsert.call_count == 1


@pytest.mark.asyncio
async def test_filters_by_creator_id_when_provided():
    """creator_id_filter is forwarded as second positional arg to _fetch_active_lead_pairs."""
    from scripts.nightly_extract_deep import run_nightly

    mock_fetch = MagicMock(return_value=[])
    creator_uuid = str(uuid.uuid4())

    session = MagicMock()
    session.execute.return_value.fetchall.return_value = []

    with patch("api.database.SessionLocal", lambda: session), \
         patch("scripts.nightly_extract_deep._fetch_active_lead_pairs", mock_fetch):
        await run_nightly(dry_run=True, creator_id_filter=creator_uuid, max_leads=100)

    assert mock_fetch.call_args.args[1] == creator_uuid


@pytest.mark.asyncio
async def test_reports_stats_at_end():
    """Stats dict has the required keys and correct memory type counts."""
    from scripts.nightly_extract_deep import run_nightly

    factory = _mock_session_factory(lead_pairs=[(_CREATOR_ID, _LEAD_ID_1)])
    mock_upsert = MagicMock()

    with patch("api.database.SessionLocal", factory), \
         patch("scripts.nightly_extract_deep._build_llm_caller", AsyncMock(return_value=AsyncMock())), \
         patch("services.memory_extractor.MemoryExtractor") as MockExtractor, \
         patch("services.lead_memory_service.LeadMemoryService") as MockSvc:
        MockExtractor.return_value.extract_deep = AsyncMock(return_value=[_MEMORY_OBJECTION])
        MockSvc.return_value.upsert = mock_upsert

        stats = await run_nightly(dry_run=False, max_leads=100)

    assert "leads_processed" in stats
    assert "leads_skipped" in stats
    assert "leads_errored" in stats
    assert "memories_created" in stats
    assert "elapsed_seconds" in stats
    assert isinstance(stats["memories_created"], dict)
    assert stats["memories_created"].get("objection", 0) == 1


# ── Unit tests: helpers ───────────────────────────────────────────────────────

def test_detect_language_catalan():
    from scripts.nightly_extract_deep import _detect_language
    conv = [{"role": "user", "content": "Hola, tinc 30 anys i visc a Barcelona"}]
    assert _detect_language(conv) == "ca"


def test_detect_language_english():
    from scripts.nightly_extract_deep import _detect_language
    conv = [{"role": "user", "content": "Hi, I want to sign up for your coaching program"}]
    assert _detect_language(conv) == "en"


def test_detect_language_defaults_to_spanish():
    from scripts.nightly_extract_deep import _detect_language
    conv = [{"role": "user", "content": "Hola, ¿cómo estás?"}]
    assert _detect_language(conv) == "es"


def test_last_writer_constant_value():
    from scripts.nightly_extract_deep import LAST_WRITER
    assert LAST_WRITER == "extract_deep_nightly"


def test_active_window_hours_constant():
    from scripts.nightly_extract_deep import ACTIVE_WINDOW_HOURS
    assert ACTIVE_WINDOW_HOURS == 48
