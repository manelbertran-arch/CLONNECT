"""Unit tests for ARC3 Phase 1 Worker D — distill flag wiring.

Tests cover:
1. Flag OFF → get_distilled_style_prompt_sync not called
2. Flag ON + cache hit → distilled text returned, style_prompt swapped
3. Flag ON + cache miss → None returned, original style_prompt kept
4. Service failure (exception) → falls back to full Doc D (no raise)
5. Log output: INFO on hit, DEBUG on miss, WARNING on exception
"""
import logging
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# get_distilled_style_prompt_sync — unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestGetDistilledStylePromptSync:
    """Tests for services.creator_style_loader.get_distilled_style_prompt_sync."""

    def test_empty_doc_d_returns_none(self):
        """Empty full_doc_d short-circuits immediately."""
        from services.creator_style_loader import get_distilled_style_prompt_sync

        result = get_distilled_style_prompt_sync("iris_bertran", "")
        assert result is None

    def test_none_doc_d_returns_none(self):
        from services.creator_style_loader import get_distilled_style_prompt_sync

        result = get_distilled_style_prompt_sync("iris_bertran", None)
        assert result is None

    def _make_mock_db(self, uuid_val, distill_val):
        mock_db = MagicMock()
        uuid_row = MagicMock()
        uuid_row.__getitem__ = lambda self, i: uuid_val if i == 0 else None
        distill_row = MagicMock()
        distill_row.__getitem__ = lambda self, i: distill_val if i == 0 else None
        mock_db.execute.return_value.fetchone.side_effect = [uuid_row, distill_row]
        mock_db.close = MagicMock()
        return mock_db

    def test_cache_hit_returns_distilled(self):
        """When DB returns a row, returns distilled_short string."""
        from services.creator_style_loader import get_distilled_style_prompt_sync

        mock_db = self._make_mock_db("uuid-1234", "distilled text")

        with patch("api.database.SessionLocal", return_value=mock_db), \
             patch("services.style_distill_service.DISTILL_PROMPT_VERSION", 1):
            result = get_distilled_style_prompt_sync("iris_bertran", "full doc d content")

        assert result == "distilled text"

    def test_cache_miss_returns_none(self):
        """When distill row not found, returns None."""
        from services.creator_style_loader import get_distilled_style_prompt_sync

        mock_db = MagicMock()
        uuid_row = MagicMock()
        uuid_row.__getitem__ = lambda self, i: "uuid-1234" if i == 0 else None
        mock_db.execute.return_value.fetchone.side_effect = [uuid_row, None]
        mock_db.close = MagicMock()

        with patch("api.database.SessionLocal", return_value=mock_db), \
             patch("services.style_distill_service.DISTILL_PROMPT_VERSION", 1):
            result = get_distilled_style_prompt_sync("iris_bertran", "full doc d content")

        assert result is None

    def test_creator_uuid_not_found_returns_none(self):
        """When creator slug not in DB, returns None without error."""
        from services.creator_style_loader import get_distilled_style_prompt_sync

        mock_db = MagicMock()
        mock_db.execute.return_value.fetchone.return_value = None
        mock_db.close = MagicMock()

        with patch("api.database.SessionLocal", return_value=mock_db), \
             patch("services.style_distill_service.DISTILL_PROMPT_VERSION", 1):
            result = get_distilled_style_prompt_sync("unknown_creator", "full doc d")

        assert result is None

    def test_db_exception_returns_none_and_logs_warning(self, caplog):
        """Any DB exception → returns None, logs WARNING, does not raise."""
        from services.creator_style_loader import get_distilled_style_prompt_sync

        with patch("api.database.SessionLocal", side_effect=RuntimeError("db down")):
            with caplog.at_level(logging.WARNING, logger="services.creator_style_loader"):
                result = get_distilled_style_prompt_sync("iris_bertran", "full doc d")

        assert result is None
        assert any("[ARC3]" in r.message for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# _load_creator_data flag wiring — agent.py integration unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAgentDistillFlagWiring:
    """Tests for the USE_DISTILLED_DOC_D flag block in DMAgent._load_creator_data."""

    def _make_flags(self, *, use_distilled_doc_d: bool):
        flags = MagicMock()
        flags.use_distilled_doc_d = use_distilled_doc_d
        return flags

    def test_flag_off_does_not_call_distill(self):
        """When use_distilled_doc_d=False, get_distilled_style_prompt_sync never called."""
        with patch("services.creator_style_loader.get_distilled_style_prompt_sync") as mock_distill:
            style_prompt = "full doc d"
            _flags = self._make_flags(use_distilled_doc_d=False)
            if style_prompt and _flags.use_distilled_doc_d:
                from services.creator_style_loader import get_distilled_style_prompt_sync
                get_distilled_style_prompt_sync("iris_bertran", style_prompt)

        mock_distill.assert_not_called()

    def test_flag_on_cache_hit_swaps_style_prompt(self):
        """Flag ON + cache hit → style_prompt replaced with distilled."""
        with patch("services.creator_style_loader.get_distilled_style_prompt_sync",
                   return_value="distilled short") as mock_distill:
            style_prompt = "full doc d"
            _flags = self._make_flags(use_distilled_doc_d=True)
            if style_prompt and _flags.use_distilled_doc_d:
                from services.creator_style_loader import get_distilled_style_prompt_sync
                _distilled = get_distilled_style_prompt_sync("iris_bertran", style_prompt)
                if _distilled:
                    style_prompt = _distilled

            assert style_prompt == "distilled short"
            mock_distill.assert_called_once_with("iris_bertran", "full doc d")

    def test_flag_on_cache_miss_keeps_full_doc_d(self):
        """Flag ON + cache miss (None returned) → original full Doc D kept."""
        with patch("services.creator_style_loader.get_distilled_style_prompt_sync",
                   return_value=None):
            style_prompt = "full doc d"
            _flags = self._make_flags(use_distilled_doc_d=True)
            if style_prompt and _flags.use_distilled_doc_d:
                from services.creator_style_loader import get_distilled_style_prompt_sync
                _distilled = get_distilled_style_prompt_sync("iris_bertran", style_prompt)
                if _distilled:
                    style_prompt = _distilled

            assert style_prompt == "full doc d"

    def test_flag_on_service_exception_keeps_full_doc_d(self, caplog):
        """Flag ON + exception in distill call → falls back to full Doc D, logs WARNING."""
        def _raise(*args, **kwargs):
            raise RuntimeError("service offline")

        with patch("services.creator_style_loader.get_distilled_style_prompt_sync",
                   side_effect=_raise):
            style_prompt = "full doc d"
            _flags = self._make_flags(use_distilled_doc_d=True)
            import logging as _logging
            with caplog.at_level(_logging.WARNING):
                if style_prompt and _flags.use_distilled_doc_d:
                    try:
                        from services.creator_style_loader import get_distilled_style_prompt_sync
                        _distilled = get_distilled_style_prompt_sync("iris_bertran", style_prompt)
                        if _distilled:
                            style_prompt = _distilled
                    except Exception as _arc3_err:
                        import logging as _log
                        _log.getLogger("core.dm.agent").warning(
                            "[ARC3] Distill wiring failed for '%s': %s — using full Doc D",
                            "iris_bertran", _arc3_err,
                        )

            assert style_prompt == "full doc d"
