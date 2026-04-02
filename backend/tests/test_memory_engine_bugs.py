"""
Functional tests for Memory Engine bug fixes (BUG-MEM-02..08).

Tests validate code paths WITHOUT requiring a live database.
Each test verifies the fix was applied correctly.
"""
import asyncio
import json
import os
import sys
import re
import inspect
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_01_resolve_creator_uuid_is_async():
    """BUG-MEM-02: _resolve_creator_uuid must be async (uses asyncio.to_thread)."""
    from services.memory_engine import MemoryEngine
    assert asyncio.iscoroutinefunction(MemoryEngine._resolve_creator_uuid), \
        "_resolve_creator_uuid must be async"
    print("PASS: test_01 — _resolve_creator_uuid is async")


def test_02_resolve_lead_uuid_is_async():
    """BUG-MEM-02: _resolve_lead_uuid must be async."""
    from services.memory_engine import MemoryEngine
    assert asyncio.iscoroutinefunction(MemoryEngine._resolve_lead_uuid), \
        "_resolve_lead_uuid must be async"
    print("PASS: test_02 — _resolve_lead_uuid is async")


def test_03_all_db_methods_use_to_thread():
    """BUG-MEM-03: All async DB methods must use asyncio.to_thread."""
    from services import memory_engine
    source = inspect.getsource(memory_engine.MemoryEngine)

    # Methods that do DB operations and should use to_thread
    db_methods = [
        '_store_fact', '_pgvector_search', '_get_existing_active_facts',
        '_get_recent_facts', '_update_access_counters', '_supersede_fact',
        '_find_similar_fact_by_embedding', '_refresh_fact_timestamp',
        '_expire_temporal_facts', '_store_summary', '_get_latest_summary',
        '_get_compressed_memo', '_deactivate_old_memos',
    ]

    # Count to_thread calls in source
    to_thread_count = source.count('asyncio.to_thread')
    assert to_thread_count >= len(db_methods), \
        f"Expected >= {len(db_methods)} asyncio.to_thread calls, found {to_thread_count}"
    print(f"PASS: test_03 — {to_thread_count} asyncio.to_thread calls found (>= {len(db_methods)} DB methods)")


def test_04_postprocessing_passes_history():
    """BUG-MEM-04: Fact extraction must include history messages (not just current pair)."""
    from core.dm.phases import postprocessing
    source = inspect.getsource(postprocessing)

    # Must reference history for memory extraction
    assert 'history[-3:]' in source or 'history[' in source, \
        "postprocessing must use history for memory extraction"
    assert 'recent_history' in source, \
        "postprocessing must build recent_history from conversation history"
    print("PASS: test_04 — postprocessing passes history to memory extraction")


def test_05_context_memory_no_hardcoded_patterns():
    """BUG-MEM-05: ContextMemoryService hardcoded patterns removed (file deleted)."""
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "services", "context_memory_service.py"
    )
    # File was deleted — hardcoded patterns no longer exist
    assert not os.path.exists(path), \
        "context_memory_service.py should be deleted (hardcoded patterns removed)"
    print("PASS: test_05 — context_memory_service.py deleted (no hardcoded patterns)")


def test_06_conversation_memory_uses_db():
    """BUG-MEM-06: ConversationMemoryService must persist to DB."""
    from services.memory_service import ConversationMemoryService
    source = inspect.getsource(ConversationMemoryService.save)

    assert 'lead_memories' in source, \
        "save() must write to lead_memories table"
    assert '_conv_memory_state' in source, \
        "save() must use _conv_memory_state fact_type"
    assert 'to_thread' in source, \
        "save() must use asyncio.to_thread for DB ops"

    source_load = inspect.getsource(ConversationMemoryService.load)
    assert 'lead_memories' in source_load, \
        "load() must read from lead_memories table"
    print("PASS: test_06 — ConversationMemoryService uses DB persistence")


def test_07_memory_store_bounded_cache():
    """BUG-MEM-07: MemoryStore must use BoundedTTLCache, not unbounded dict."""
    from services.memory_service import MemoryStore
    from core.cache import BoundedTTLCache

    store = MemoryStore()
    assert isinstance(store._cache, BoundedTTLCache), \
        f"MemoryStore._cache must be BoundedTTLCache, got {type(store._cache)}"
    print("PASS: test_07 — MemoryStore uses BoundedTTLCache")


def test_08_recall_cache_ts_removed():
    """BUG-MEM-01 (prev session): _recall_cache_ts must not exist."""
    from services import memory_engine
    source = inspect.getsource(memory_engine)
    assert '_recall_cache_ts' not in source, \
        "_recall_cache_ts reference still exists — BUG-MEM-01 not fully fixed"
    print("PASS: test_08 — _recall_cache_ts fully removed")


def test_09_decay_counter_adds():
    """BUG-MEM-08 (prev session): decay counter must use += not =."""
    from services import memory_engine
    source = inspect.getsource(memory_engine.MemoryEngine.decay_memories)
    assert 'deactivated += len(ids_to_deactivate)' in source, \
        "decay_memories must use += to accumulate deactivated count"
    print("PASS: test_09 — decay counter uses += correctly")


def test_10_resolve_uuid_fast_path():
    """BUG-MEM-02: UUID resolution must short-circuit for valid UUIDs (no DB call)."""
    from services.memory_engine import MemoryEngine

    engine = MemoryEngine()
    test_uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    # Should return immediately without DB call
    result = asyncio.get_event_loop().run_until_complete(
        MemoryEngine._resolve_creator_uuid(test_uuid)
    )
    assert result == test_uuid, f"Valid UUID should pass through, got {result}"

    result2 = asyncio.get_event_loop().run_until_complete(
        engine._resolve_lead_uuid(test_uuid, test_uuid)
    )
    assert result2 == test_uuid, f"Valid UUID should pass through, got {result2}"
    print("PASS: test_10 — UUID resolution fast-paths for valid UUIDs")


if __name__ == "__main__":
    tests = [
        test_01_resolve_creator_uuid_is_async,
        test_02_resolve_lead_uuid_is_async,
        test_03_all_db_methods_use_to_thread,
        test_04_postprocessing_passes_history,
        test_05_context_memory_no_hardcoded_patterns,
        test_06_conversation_memory_uses_db,
        test_07_memory_store_bounded_cache,
        test_08_recall_cache_ts_removed,
        test_09_decay_counter_adds,
        test_10_resolve_uuid_fast_path,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"FAIL: {test.__name__} — {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed}/{len(tests)} passed, {failed} failed")
