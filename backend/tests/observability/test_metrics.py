"""
Tests for core/observability/metrics.py and core/observability/middleware.py
ARC5 Phase 3 — emit_metric registry + context middleware.
"""

import asyncio
import logging
from unittest.mock import MagicMock, patch

import pytest

from core.observability.metrics import (
    _REGISTRY,
    _REGISTRY_META,
    _get_declared_labels,
    emit_metric,
    get_declared_metric_names,
    get_registry_snapshot,
)
from core.observability.middleware import (
    CreatorContextMiddleware,
    clear_context,
    get_context,
    set_context,
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Registry declarations
# ─────────────────────────────────────────────────────────────────────────────

def test_registry_has_all_declared_metrics():
    declared = get_declared_metric_names()
    assert len(declared) >= 20, f"Expected ≥20 metrics, got {len(declared)}"
    # Key metrics from design doc §2.3
    for name in [
        "generation_duration_ms",
        "scoring_duration_ms",
        "detection_duration_ms",
        "compaction_applied_total",
        "rule_violation_total",
        "dual_write_success_total",
        "dual_write_failure_total",
        "llm_api_call_total",
        "llm_api_duration_ms",
        "cache_hit_total",
        "cache_miss_total",
        "webhook_received_total",
        "webhook_processed_total",
        "memory_extraction_total",
        "lead_memories_read_total",
        "budget_section_truncation_total",
        "budget_orchestrator_duration_ms",
        # Budget metrics (migrated from core/dm/budget/metrics.py)
        "dm_budget_utilization",
        "dm_budget_sections_selected",
        "dm_budget_sections_dropped_total",
        "dm_budget_sections_compressed_total",
    ]:
        assert name in declared, f"Missing from declared names: {name}"


def test_registry_snapshot_returns_type_strings():
    snap = get_registry_snapshot()
    # If prometheus is available, snapshot should have entries
    if snap:
        for name, mtype in snap.items():
            assert mtype in ("Counter", "Histogram", "Gauge"), f"{name}: unexpected type {mtype}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. emit_metric — Counter
# ─────────────────────────────────────────────────────────────────────────────

def test_emit_metric_counter_increments():
    mock_counter = MagicMock()
    mock_labels = MagicMock()
    mock_counter.labels.return_value = mock_labels
    mock_counter._labelnames = ["source"]

    with patch.dict("core.observability.metrics._REGISTRY", {"dual_write_success_total": mock_counter}):
        with patch.dict("core.observability.metrics._REGISTRY_META", {"dual_write_success_total": "Counter"}):
            emit_metric("dual_write_success_total", source="dual_write_memory_extraction")

    mock_counter.labels.assert_called_once_with(source="dual_write_memory_extraction")
    mock_labels.inc.assert_called_once_with(1)


def test_emit_metric_counter_custom_value():
    mock_counter = MagicMock()
    mock_labels = MagicMock()
    mock_counter.labels.return_value = mock_labels
    mock_counter._labelnames = ["creator_id", "rule_name"]

    with patch.dict("core.observability.metrics._REGISTRY", {"rule_violation_total": mock_counter}):
        with patch.dict("core.observability.metrics._REGISTRY_META", {"rule_violation_total": "Counter"}):
            emit_metric("rule_violation_total", 3, creator_id="iris", rule_name="no_price")

    mock_labels.inc.assert_called_once_with(3)


# ─────────────────────────────────────────────────────────────────────────────
# 3. emit_metric — Histogram
# ─────────────────────────────────────────────────────────────────────────────

def test_emit_metric_histogram_observes():
    mock_hist = MagicMock()
    mock_labels = MagicMock()
    mock_hist.labels.return_value = mock_labels
    mock_hist._labelnames = ["creator_id", "model", "status"]

    with patch.dict("core.observability.metrics._REGISTRY", {"generation_duration_ms": mock_hist}):
        with patch.dict("core.observability.metrics._REGISTRY_META", {"generation_duration_ms": "Histogram"}):
            emit_metric("generation_duration_ms", 450, creator_id="iris", model="gemma", status="ok")

    mock_labels.observe.assert_called_once_with(450)


# ─────────────────────────────────────────────────────────────────────────────
# 4. emit_metric — Gauge
# ─────────────────────────────────────────────────────────────────────────────

def test_emit_metric_gauge_sets():
    mock_gauge = MagicMock()
    mock_labels = MagicMock()
    mock_gauge.labels.return_value = mock_labels
    mock_gauge._labelnames = ["creator_id"]

    with patch.dict("core.observability.metrics._REGISTRY", {"active_conversations_gauge": mock_gauge}):
        with patch.dict("core.observability.metrics._REGISTRY_META", {"active_conversations_gauge": "Gauge"}):
            emit_metric("active_conversations_gauge", 12, creator_id="iris")

    mock_labels.set.assert_called_once_with(12)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Unknown metric name → warning, no crash
# ─────────────────────────────────────────────────────────────────────────────

def test_emit_metric_unknown_name_logs_warning_no_crash(caplog):
    with caplog.at_level(logging.WARNING, logger="core.observability.metrics"):
        emit_metric("nonexistent_metric_xyz", 1, creator_id="iris")
    assert "nonexistent_metric_xyz" in caplog.text


def test_emit_metric_unknown_name_does_not_raise():
    # Must not raise under any circumstance
    emit_metric("totally_unknown_metric", 999, foo="bar", baz="qux")


# ─────────────────────────────────────────────────────────────────────────────
# 6. Label filtering — undeclared labels are silently dropped
# ─────────────────────────────────────────────────────────────────────────────

def test_emit_metric_filters_undeclared_labels():
    mock_counter = MagicMock()
    mock_labels = MagicMock()
    mock_counter.labels.return_value = mock_labels
    mock_counter._labelnames = ["source"]  # only "source" declared

    with patch.dict("core.observability.metrics._REGISTRY", {"dual_write_success_total": mock_counter}):
        with patch.dict("core.observability.metrics._REGISTRY_META", {"dual_write_success_total": "Counter"}):
            # Pass extra labels that are NOT declared
            emit_metric("dual_write_success_total", source="x", undeclared_label="y", another="z")

    # Only declared label should be passed
    mock_counter.labels.assert_called_once_with(source="x")


# ─────────────────────────────────────────────────────────────────────────────
# 7. Prometheus internal error → no crash
# ─────────────────────────────────────────────────────────────────────────────

def test_emit_metric_with_prometheus_error_does_not_crash():
    mock_counter = MagicMock()
    mock_counter._labelnames = ["creator_id"]
    mock_counter.labels.side_effect = RuntimeError("prometheus registry exploded")

    with patch.dict("core.observability.metrics._REGISTRY", {"rule_violation_total": mock_counter}):
        with patch.dict("core.observability.metrics._REGISTRY_META", {"rule_violation_total": "Counter"}):
            # Must not raise
            emit_metric("rule_violation_total", creator_id="iris", rule_name="test")


# ─────────────────────────────────────────────────────────────────────────────
# 8. Context injection — creator_id from ContextVar
# ─────────────────────────────────────────────────────────────────────────────

def test_auto_inject_creator_id_from_context():
    mock_counter = MagicMock()
    mock_labels = MagicMock()
    mock_counter.labels.return_value = mock_labels
    mock_counter._labelnames = ["creator_id", "rule_name"]

    set_context(creator_id="iris_bertran")
    try:
        with patch.dict("core.observability.metrics._REGISTRY", {"rule_violation_total": mock_counter}):
            with patch.dict("core.observability.metrics._REGISTRY_META", {"rule_violation_total": "Counter"}):
                emit_metric("rule_violation_total", rule_name="test_rule")
                # creator_id NOT passed explicitly — should be auto-injected from context
        mock_counter.labels.assert_called_once_with(creator_id="iris_bertran", rule_name="test_rule")
    finally:
        clear_context()


def test_auto_inject_lead_id_from_context():
    mock_counter = MagicMock()
    mock_labels = MagicMock()
    mock_counter.labels.return_value = mock_labels
    mock_counter._labelnames = ["creator_id", "lead_id"]

    set_context(creator_id="iris", lead_id="lead_123")
    try:
        with patch.dict("core.observability.metrics._REGISTRY", {"test_lead_metric": mock_counter}):
            with patch.dict("core.observability.metrics._REGISTRY_META", {"test_lead_metric": "Counter"}):
                emit_metric("test_lead_metric")
        mock_counter.labels.assert_called_once_with(creator_id="iris", lead_id="lead_123")
    finally:
        clear_context()


def test_context_not_injected_when_label_not_declared():
    mock_counter = MagicMock()
    mock_labels = MagicMock()
    mock_counter.labels.return_value = mock_labels
    mock_counter._labelnames = ["cache_name"]  # does NOT include creator_id

    set_context(creator_id="iris")
    try:
        with patch.dict("core.observability.metrics._REGISTRY", {"cache_hit_total": mock_counter}):
            with patch.dict("core.observability.metrics._REGISTRY_META", {"cache_hit_total": "Counter"}):
                emit_metric("cache_hit_total", cache_name="rag")
        # creator_id from context should NOT be injected (not in _labelnames)
        mock_counter.labels.assert_called_once_with(cache_name="rag")
    finally:
        clear_context()


# ─────────────────────────────────────────────────────────────────────────────
# 9. ContextVars — set/get/clear
# ─────────────────────────────────────────────────────────────────────────────

def test_set_and_get_context():
    set_context(creator_id="alice", lead_id="lead_42", request_id="req_99")
    ctx = get_context()
    assert ctx["creator_id"] == "alice"
    assert ctx["lead_id"] == "lead_42"
    assert ctx["request_id"] == "req_99"
    clear_context()


def test_clear_context_resets_to_none():
    set_context(creator_id="alice", lead_id="lead_1")
    clear_context()
    ctx = get_context()
    assert ctx["creator_id"] is None
    assert ctx["lead_id"] is None


def test_get_context_defaults_none_when_unset():
    clear_context()
    ctx = get_context()
    assert ctx["creator_id"] is None
    assert ctx["lead_id"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 10. Middleware — sets and clears context
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_middleware_sets_and_clears_context():
    captured = {}

    async def fake_app(scope, receive, send):
        captured.update(get_context())

    mw = CreatorContextMiddleware(fake_app)
    scope = {
        "type": "http",
        "path": "/api/dm/iris_bertran/chat",
        "headers": [
            (b"x-lead-id", b"lead_999"),
        ],
    }
    await mw(scope, None, None)

    # During request: context was set
    assert captured.get("lead_id") == "lead_999"
    assert captured.get("creator_id") == "iris_bertran"
    # After request: context cleared
    assert get_context()["creator_id"] is None
    assert get_context()["lead_id"] is None


@pytest.mark.asyncio
async def test_middleware_extracts_creator_id_from_header():
    captured = {}

    async def fake_app(scope, receive, send):
        captured.update(get_context())

    mw = CreatorContextMiddleware(fake_app)
    scope = {
        "type": "http",
        "path": "/some/path",
        "headers": [
            (b"x-creator-id", b"iris_bertran"),
        ],
    }
    await mw(scope, None, None)
    assert captured.get("creator_id") == "iris_bertran"


@pytest.mark.asyncio
async def test_middleware_non_http_passthrough():
    """WebSocket / lifespan scopes should be passed through without context injection."""
    called = []

    async def fake_app(scope, receive, send):
        called.append(scope["type"])

    mw = CreatorContextMiddleware(fake_app)
    scope = {"type": "websocket", "path": "/ws", "headers": []}
    await mw(scope, None, None)
    assert called == ["websocket"]
    # Context untouched (never set)
    assert get_context()["creator_id"] is None
