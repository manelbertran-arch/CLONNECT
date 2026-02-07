"""Audit tests for core/cache.py - QueryCache"""

import time

from core.cache import QueryCache


class TestAuditCache:
    def test_import(self):
        from core.cache import QueryCache  # noqa: F811

        assert QueryCache is not None

    def test_init(self):
        cache = QueryCache(max_size=10, ttl_seconds=60)
        assert cache is not None

    def test_happy_path(self):
        cache = QueryCache(max_size=10, ttl_seconds=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_edge_case_expired(self):
        cache = QueryCache(max_size=10, ttl_seconds=1)
        cache.set("key1", "value1")
        time.sleep(1.1)
        assert cache.get("key1") is None

    def test_error_handling_missing_key(self):
        cache = QueryCache(max_size=10, ttl_seconds=60)
        assert cache.get("nonexistent") is None
