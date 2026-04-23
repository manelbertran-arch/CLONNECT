"""Tests for core/data/tone_profile_repo.py (Domain A — tone profiles)."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Cache contract (rewritten from stale dict-based tests per B-02)
# ---------------------------------------------------------------------------
class TestToneCacheContract:
    """BoundedTTLCache contract — replaces dict-era assertions."""

    def test_cache_is_bounded_ttl_cache(self):
        from core.cache import BoundedTTLCache
        from core.data.tone_profile_repo import _tone_cache

        assert isinstance(_tone_cache, BoundedTTLCache)
        assert _tone_cache.max_size >= 1
        assert _tone_cache.ttl_seconds > 0

    def test_clear_cache_specific_key(self):
        from core.data.tone_profile_repo import _tone_cache, clear_cache

        _tone_cache.set("tpr_test_creator", {"some": "data"})
        assert "tpr_test_creator" in _tone_cache

        clear_cache("tpr_test_creator")
        assert "tpr_test_creator" not in _tone_cache

    def test_clear_cache_all(self):
        from core.data.tone_profile_repo import _tone_cache, clear_cache

        _tone_cache.set("tpr_a", 1)
        _tone_cache.set("tpr_b", 2)
        clear_cache()
        assert len(_tone_cache) == 0


# ---------------------------------------------------------------------------
# B-01 regression — cache-hit read must not raise TypeError
# ---------------------------------------------------------------------------
class TestCacheHitReadPath:
    """Regression for the BoundedTTLCache subscript bug (B-01)."""

    @pytest.mark.asyncio
    async def test_async_cache_hit_does_not_raise(self):
        """Before B-01 fix: `_tone_cache[creator_id]` raised TypeError."""
        from core.data.tone_profile_repo import _tone_cache, get_tone_profile_db

        _tone_cache.set("tpr_b01_async", {"hit": True})
        result = await get_tone_profile_db("tpr_b01_async")
        assert result == {"hit": True}
        _tone_cache.pop("tpr_b01_async", None)

    def test_sync_cache_hit_does_not_raise(self):
        from core.data.tone_profile_repo import _tone_cache, get_tone_profile_db_sync

        _tone_cache.set("tpr_b01_sync", {"hit": True, "sync": True})
        result = get_tone_profile_db_sync("tpr_b01_sync")
        assert result == {"hit": True, "sync": True}
        _tone_cache.pop("tpr_b01_sync", None)


# ---------------------------------------------------------------------------
# Save — happy path + error path
# ---------------------------------------------------------------------------
class TestSaveToneProfile:
    @pytest.mark.asyncio
    async def test_save_new_profile_populates_cache(self):
        from core.data.tone_profile_repo import _tone_cache, save_tone_profile_db

        _tone_cache.pop("tpr_save", None)

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None

        @contextmanager
        def fake_session():
            yield mock_session

        mock_db = MagicMock()
        mock_db.get_db_session = fake_session
        mock_models = MagicMock()
        mock_models.ToneProfile = MagicMock()

        with patch.dict("sys.modules", {"api.database": mock_db, "api.models": mock_models}):
            result = await save_tone_profile_db(
                "tpr_save",
                {"confidence_score": 0.9, "analyzed_posts_count": 20},
            )

        assert result is True
        assert _tone_cache.get("tpr_save") == {
            "confidence_score": 0.9,
            "analyzed_posts_count": 20,
        }
        _tone_cache.pop("tpr_save", None)

    @pytest.mark.asyncio
    async def test_save_returns_false_on_exception(self):
        """No mocks → DB import path hits real code → exception → False (golden master A2)."""
        from core.data.tone_profile_repo import save_tone_profile_db

        result = await save_tone_profile_db("tpr_bad_creator", {"data": 1})
        assert result is False


# ---------------------------------------------------------------------------
# Load / delete / list — error path contracts (golden master)
# ---------------------------------------------------------------------------
class TestErrorPathContracts:
    """Functions MUST return safe defaults on any exception (golden master A3–A7)."""

    @pytest.mark.asyncio
    async def test_get_returns_none_on_error(self):
        from core.data.tone_profile_repo import _tone_cache, get_tone_profile_db

        _tone_cache.pop("tpr_err_async", None)
        assert await get_tone_profile_db("tpr_err_async") is None

    def test_sync_get_returns_none_on_error(self):
        from core.data.tone_profile_repo import _tone_cache, get_tone_profile_db_sync

        _tone_cache.pop("tpr_err_sync", None)
        assert get_tone_profile_db_sync("tpr_err_sync") is None

    @pytest.mark.asyncio
    async def test_delete_returns_false_on_error(self):
        from core.data.tone_profile_repo import delete_tone_profile_db

        assert await delete_tone_profile_db("tpr_nonexistent") is False

    def test_list_profiles_returns_empty_on_error(self):
        from core.data.tone_profile_repo import list_profiles_db

        assert list_profiles_db() == []


# ---------------------------------------------------------------------------
# B-07 regression — env-driven cache sizing
# ---------------------------------------------------------------------------
class TestEnvCacheSizing:
    """Regression for hardcoded cache params (B-07)."""

    def test_cache_env_vars_respected(self, monkeypatch):
        import importlib

        monkeypatch.setenv("TONE_CACHE_MAX_SIZE", "77")
        monkeypatch.setenv("TONE_CACHE_TTL_SECONDS", "123")

        import core.data.tone_profile_repo as mod
        importlib.reload(mod)
        try:
            assert mod.TONE_CACHE_MAX_SIZE == 77
            assert mod.TONE_CACHE_TTL_SECONDS == 123
            assert mod._tone_cache.max_size == 77
            assert mod._tone_cache.ttl_seconds == 123
        finally:
            monkeypatch.delenv("TONE_CACHE_MAX_SIZE", raising=False)
            monkeypatch.delenv("TONE_CACHE_TTL_SECONDS", raising=False)
            importlib.reload(mod)  # restore defaults for other tests


# ---------------------------------------------------------------------------
# B-06 — public accessor (encapsulation)
# ---------------------------------------------------------------------------
class TestPublicCacheStatsAccessor:
    def test_get_tone_cache_stats_returns_dict(self):
        from core.data.tone_profile_repo import get_tone_cache_stats

        stats = get_tone_cache_stats()
        assert isinstance(stats, dict)
        assert "size" in stats
        assert "max_size" in stats
        assert "ttl_seconds" in stats
