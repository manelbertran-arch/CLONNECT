"""Tests for core/autolearning_evaluator.py."""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from services.persona_compiler import (
    _detect_daily_patterns,
    _generate_weekly_recommendations,
    run_daily_evaluation,
    run_weekly_recalibration,
)

# Reusable timestamp fixtures for tests
_SINCE = datetime(2026, 2, 18, 0, 0, tzinfo=timezone.utc)
_UNTIL = datetime(2026, 2, 19, 0, 0, tzinfo=timezone.utc)


class TestDailyPatternDetection:
    """Test pattern detection from edit diffs."""

    def test_empty_diffs_no_patterns(self):
        """No diffs produce no patterns."""
        mock_session = MagicMock()
        mock_session.query.return_value.join.return_value.filter.return_value.all.return_value = []
        patterns = _detect_daily_patterns(mock_session, "creator_db_id", _SINCE, _UNTIL)
        assert patterns == []

    def test_consistent_shortening_detected(self):
        """High frequency of 'shortened' category triggers pattern."""
        mock_session = MagicMock()
        diffs = [
            ({"length_delta": -30, "categories": ["shortened"]},),
            ({"length_delta": -25, "categories": ["shortened"]},),
            ({"length_delta": -40, "categories": ["shortened"]},),
            ({"length_delta": 5, "categories": []},),
        ]
        mock_session.query.return_value.join.return_value.filter.return_value.all.return_value = diffs
        patterns = _detect_daily_patterns(mock_session, "c1", _SINCE, _UNTIL)
        pattern_types = [p["type"] for p in patterns]
        assert "consistent_shortening" in pattern_types

    def test_question_removal_detected(self):
        """High frequency of 'removed_question' triggers pattern."""
        mock_session = MagicMock()
        diffs = [
            ({"length_delta": -5, "categories": ["removed_question"]},),
            ({"length_delta": -3, "categories": ["removed_question"]},),
            ({"length_delta": 0, "categories": []},),
        ]
        mock_session.query.return_value.join.return_value.filter.return_value.all.return_value = diffs
        patterns = _detect_daily_patterns(mock_session, "c1", _SINCE, _UNTIL)
        pattern_types = [p["type"] for p in patterns]
        assert "question_removal" in pattern_types

    def test_complete_rewrite_detected(self):
        """High rewrite rate triggers pattern."""
        mock_session = MagicMock()
        diffs = [
            ({"length_delta": 10, "categories": ["complete_rewrite"]},),
            ({"length_delta": -5, "categories": ["complete_rewrite"]},),
            ({"length_delta": 0, "categories": []},),
            ({"length_delta": 3, "categories": []},),
        ]
        mock_session.query.return_value.join.return_value.filter.return_value.all.return_value = diffs
        patterns = _detect_daily_patterns(mock_session, "c1", _SINCE, _UNTIL)
        pattern_types = [p["type"] for p in patterns]
        assert "high_rewrite_rate" in pattern_types

    def test_low_frequency_no_pattern(self):
        """Low frequency edits don't trigger patterns."""
        mock_session = MagicMock()
        diffs = [
            ({"length_delta": -30, "categories": ["shortened"]},),
            ({"length_delta": 0, "categories": []},),
            ({"length_delta": 5, "categories": []},),
            ({"length_delta": 2, "categories": []},),
            ({"length_delta": 1, "categories": []},),
        ]
        mock_session.query.return_value.join.return_value.filter.return_value.all.return_value = diffs
        patterns = _detect_daily_patterns(mock_session, "c1", _SINCE, _UNTIL)
        # Only 1/5 shortened — below 50% threshold
        pattern_types = [p["type"] for p in patterns]
        assert "consistent_shortening" not in pattern_types


class TestWeeklyRecommendations:
    """Test weekly recommendation generation."""

    def _make_eval(self, approval_rate=0.7, edit_rate=0.2, discard_rate=0.1, total=10):
        """Helper to make a mock daily evaluation."""
        ev = MagicMock()
        ev.metrics = {
            "approval_rate": approval_rate,
            "edit_rate": edit_rate,
            "discard_rate": discard_rate,
            "total_actions": total,
        }
        ev.patterns = []
        return ev

    def test_high_discard_rate_recommendation(self):
        """High discard rate generates review recommendation."""
        metrics = {"avg_approval_rate": 0.3, "avg_edit_rate": 0.2, "avg_discard_rate": 0.5, "total_actions": 50}
        evals = [self._make_eval(discard_rate=0.5) for _ in range(5)]
        recs = _generate_weekly_recommendations(evals, metrics)
        rec_types = [r["type"] for r in recs]
        assert "high_discard_rate" in rec_types

    def test_high_edit_rate_recommendation(self):
        """High edit rate generates tone adjustment recommendation."""
        metrics = {"avg_approval_rate": 0.3, "avg_edit_rate": 0.6, "avg_discard_rate": 0.1, "total_actions": 50}
        evals = [self._make_eval(edit_rate=0.6) for _ in range(5)]
        recs = _generate_weekly_recommendations(evals, metrics)
        rec_types = [r["type"] for r in recs]
        assert "high_edit_rate" in rec_types

    def test_high_performance_suggestion(self):
        """Very high approval rate suggests auto mode."""
        metrics = {"avg_approval_rate": 0.9, "avg_edit_rate": 0.05, "avg_discard_rate": 0.05, "total_actions": 30}
        evals = [self._make_eval(approval_rate=0.9) for _ in range(5)]
        recs = _generate_weekly_recommendations(evals, metrics)
        rec_types = [r["type"] for r in recs]
        assert "high_performance" in rec_types

    def test_improving_trend_detected(self):
        """Improving approval rate over the week is noted."""
        metrics = {"avg_approval_rate": 0.7, "avg_edit_rate": 0.2, "avg_discard_rate": 0.1, "total_actions": 50}
        evals = [
            self._make_eval(approval_rate=0.5),
            self._make_eval(approval_rate=0.5),
            self._make_eval(approval_rate=0.55),
            self._make_eval(approval_rate=0.8),
            self._make_eval(approval_rate=0.85),
            self._make_eval(approval_rate=0.9),
        ]
        recs = _generate_weekly_recommendations(evals, metrics)
        rec_types = [r["type"] for r in recs]
        assert "improving_trend" in rec_types

    def test_no_recommendations_for_normal_metrics(self):
        """Normal metrics don't generate unnecessary recommendations."""
        metrics = {"avg_approval_rate": 0.7, "avg_edit_rate": 0.2, "avg_discard_rate": 0.1, "total_actions": 15}
        evals = [self._make_eval(approval_rate=0.7) for _ in range(5)]
        recs = _generate_weekly_recommendations(evals, metrics)
        # Should not have high_discard, high_edit, or high_performance
        rec_types = [r["type"] for r in recs]
        assert "high_discard_rate" not in rec_types
        assert "high_edit_rate" not in rec_types


class TestDailyEvaluation:
    """Test daily evaluation function."""

    @pytest.mark.asyncio
    async def test_skips_if_already_exists(self):
        """Skips if evaluation already exists for the date."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = MagicMock(id="existing")

        with patch("api.database.SessionLocal", return_value=mock_session):
            result = await run_daily_evaluation("creator1", "db_id_1")
        assert result.get("skipped") is True

    @pytest.mark.asyncio
    async def test_skips_if_no_actions(self):
        """Skips if no copilot actions for the day."""
        mock_session = MagicMock()
        call_count = [0]

        def query_side(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # Existing check → not found
                result.filter_by.return_value.first.return_value = None
            elif call_count[0] == 2:
                # Actions query → empty
                result.join.return_value.filter.return_value.group_by.return_value.all.return_value = []
            return result

        mock_session.query.side_effect = query_side

        with patch("api.database.SessionLocal", return_value=mock_session):
            result = await run_daily_evaluation("creator1", "db_id_1")
        assert result.get("skipped") is True


class TestWeeklyRecalibration:
    """Test weekly recalibration function."""

    @pytest.mark.asyncio
    async def test_skips_if_already_exists(self):
        """Skips if weekly evaluation already exists."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = MagicMock(id="existing")

        with patch("api.database.SessionLocal", return_value=mock_session):
            result = await run_weekly_recalibration("creator1", "db_id_1")
        assert result.get("skipped") is True

    @pytest.mark.asyncio
    async def test_skips_insufficient_data(self):
        """Skips if fewer than 3 daily evaluations."""
        mock_session = MagicMock()
        call_count = [0]

        def query_side(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                # Existing check → not found
                result.filter_by.return_value.first.return_value = None
            elif call_count[0] == 2:
                # Daily evals → only 2
                result.filter.return_value.order_by.return_value.all.return_value = [
                    MagicMock(), MagicMock()
                ]
            return result

        mock_session.query.side_effect = query_side

        with patch("api.database.SessionLocal", return_value=mock_session):
            result = await run_weekly_recalibration("creator1", "db_id_1")
        assert result.get("skipped") is True
        assert result.get("reason") == "insufficient_data"
