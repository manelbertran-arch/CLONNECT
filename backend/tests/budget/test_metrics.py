"""
Tests for core/dm/budget/metrics.py
Covers: emit_budget_metrics logger path, silent failure on exception,
        prometheus path (mocked), empty assembled context.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.dm.budget.metrics import emit_budget_metrics
from core.dm.budget.section import AssembledContext, Priority, Section


def _assembled(
    utilization: float = 0.5,
    selected: int = 2,
    dropped: int = 1,
    compressed: int = 0,
) -> AssembledContext:
    def _s(name: str) -> Section:
        return Section(
            name=name, content="x", priority=Priority.HIGH,
            cap_tokens=100, value_score=0.5,
        )

    return AssembledContext(
        combined="x",
        sections_selected=[_s(f"sel_{i}") for i in range(selected)],
        sections_dropped=[_s(f"drop_{i}") for i in range(dropped)],
        sections_compressed=[(_s(f"comp_{i}"), 10) for i in range(compressed)],
        total_tokens=50,
        budget_tokens=100,
        utilization=utilization,
    )


class TestEmitBudgetMetrics:
    def test_no_exception_with_minimal_context(self):
        ctx = MagicMock()
        ctx.creator_id = "iris_bertran"
        assembled = _assembled()
        emit_budget_metrics(assembled, ctx)  # must not raise

    def test_unknown_creator_id_fallback(self):
        ctx = object()  # no creator_id attr
        assembled = _assembled()
        emit_budget_metrics(assembled, ctx)  # must not raise

    def test_silent_on_exception(self):
        assembled = MagicMock()
        assembled.utilization = "bad"  # will cause issues downstream
        assembled.sections_selected = None
        ctx = MagicMock()
        ctx.creator_id = "test"
        emit_budget_metrics(assembled, ctx)  # must not raise

    def test_logs_debug_message(self):
        ctx = MagicMock()
        ctx.creator_id = "iris_bertran"
        assembled = _assembled(utilization=0.75, selected=3, dropped=2)
        with patch("core.dm.budget.metrics.logger") as mock_log:
            emit_budget_metrics(assembled, ctx)
            mock_log.debug.assert_called()
            call_args = mock_log.debug.call_args[0]
            assert "BUDGET" in call_args[0]

    def test_prometheus_labels_called_when_available(self):
        ctx = MagicMock()
        ctx.creator_id = "iris_bertran"
        assembled = _assembled(utilization=0.5, selected=2, dropped=1, compressed=1)

        # ARC5 Phase 3: budget/metrics.py now calls emit_metric — patch at that level
        with patch("core.dm.budget.metrics.emit_metric") as mock_emit:
            emit_budget_metrics(assembled, ctx)
            # utilization and sections_selected must be emitted
            calls = [c[0][0] for c in mock_emit.call_args_list]
            assert "dm_budget_utilization" in calls
            assert "dm_budget_sections_selected" in calls
            assert "dm_budget_sections_dropped_total" in calls

    def test_empty_context(self):
        ctx = MagicMock()
        ctx.creator_id = "stefano"
        assembled = _assembled(utilization=0.0, selected=0, dropped=0)
        emit_budget_metrics(assembled, ctx)  # must not raise

    def test_no_prometheus_skips_metrics(self):
        ctx = MagicMock()
        ctx.creator_id = "iris_bertran"
        assembled = _assembled()
        # ARC5 Phase 3: emit_metric is always called (fail-silent if prometheus unavailable)
        with patch("core.dm.budget.metrics.emit_metric") as mock_emit:
            with patch("core.dm.budget.metrics.logger") as mock_log:
                emit_budget_metrics(assembled, ctx)
                mock_log.debug.assert_called()
                mock_emit.assert_called()  # emit_metric called regardless
