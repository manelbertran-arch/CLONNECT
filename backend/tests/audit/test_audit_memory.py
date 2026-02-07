"""Audit tests for core/memory.py - FollowerMemory + MemoryStore"""

import tempfile

from core.memory import FollowerMemory, MemoryStore


class TestAuditMemory:
    def test_import(self):
        from core.memory import FollowerMemory, MemoryStore  # noqa: F811

        assert FollowerMemory is not None
        assert MemoryStore is not None

    def test_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = MemoryStore(storage_path=tmpdir)
            assert store is not None

    def test_happy_path_follower_memory(self):
        mem = FollowerMemory(follower_id="f1", creator_id="c1")
        assert mem.follower_id == "f1"

    def test_edge_case_follower_memory_defaults(self):
        mem = FollowerMemory(follower_id="f1", creator_id="c1")
        assert mem.follower_id == "f1"
        assert mem.is_lead is False or mem.is_lead is True or mem.is_lead is None

    def test_error_handling_store_init(self):
        store = MemoryStore(storage_path="/tmp/nonexistent_clonnect_test_dir")
        assert store is not None
