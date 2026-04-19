"""
ARC5 Phase 3 — Unified Prometheus metric registry + emit_metric helper.

Single source of truth for all metrics. Use emit_metric() instead of
creating prometheus_client objects directly scattered across the codebase.

Design: docs/sprint5_planning/ARC5_observability.md §2.3
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Gauge, Histogram
    _PROMETHEUS_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PROMETHEUS_AVAILABLE = False
    logger.warning("[observability] prometheus_client not installed — emit_metric is a no-op")


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _create(cls: Any, name: str, desc: str, labels: List[str], **kw: Any) -> Optional[Any]:
    """Create a prometheus metric, silently ignoring duplicate registration."""
    if not _PROMETHEUS_AVAILABLE:
        return None
    try:
        return cls(name, desc, labelnames=labels, **kw)
    except ValueError:
        # Module reimport or test re-use — metric already registered in global registry
        return None


def _get_declared_labels(name: str) -> List[str]:
    m = _REGISTRY.get(name)
    if m is None:
        return []
    return list(getattr(m, "_labelnames", []))


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRY — all metrics declared here, nowhere else (for new metrics)
# ─────────────────────────────────────────────────────────────────────────────

_REGISTRY: Dict[str, Any] = {}

_METRIC_SPECS = [
    # ── DM Generation ──────────────────────────────────────────────────────
    ("generation_duration_ms", Histogram if _PROMETHEUS_AVAILABLE else None,
     "Generation duration in milliseconds",
     ["creator_id", "model", "status"],
     {"buckets": [50, 100, 200, 500, 1000, 2000, 5000, 10000]}),

    ("scoring_duration_ms", Histogram if _PROMETHEUS_AVAILABLE else None,
     "Scoring duration in milliseconds",
     ["creator_id", "phase"],
     {"buckets": [10, 50, 100, 500, 1000, 5000]}),

    ("detection_duration_ms", Histogram if _PROMETHEUS_AVAILABLE else None,
     "Detection phase duration in milliseconds",
     ["creator_id", "intent"],
     {"buckets": [5, 10, 50, 100, 200, 500]}),

    # ── Memory / ARC2 ───────────────────────────────────────────────────────
    ("compaction_applied_total", Counter if _PROMETHEUS_AVAILABLE else None,
     "Memory compaction applied events",
     ["creator_id", "reason"], {}),

    ("memory_extraction_total", Counter if _PROMETHEUS_AVAILABLE else None,
     "Memory facts extracted by type",
     ["creator_id", "memory_type"], {}),

    ("lead_memories_read_total", Counter if _PROMETHEUS_AVAILABLE else None,
     "Lead memory reads by source system",
     ["creator_id", "source"], {}),

    ("lead_memories_read_duration_ms", Histogram if _PROMETHEUS_AVAILABLE else None,
     "Lead memory read latency in milliseconds",
     ["creator_id"],
     {"buckets": [1, 5, 10, 50, 100, 500]}),

    ("dual_write_success_total", Counter if _PROMETHEUS_AVAILABLE else None,
     "Dual-write successes to arc2_lead_memories",
     ["source"], {}),

    ("dual_write_failure_total", Counter if _PROMETHEUS_AVAILABLE else None,
     "Dual-write failures to arc2_lead_memories",
     ["source", "error_type"], {}),

    # ── LLM API ─────────────────────────────────────────────────────────────
    ("llm_api_call_total", Counter if _PROMETHEUS_AVAILABLE else None,
     "LLM API calls by provider/model/status",
     ["provider", "model", "status"], {}),

    ("llm_api_duration_ms", Histogram if _PROMETHEUS_AVAILABLE else None,
     "LLM API call duration in milliseconds",
     ["provider", "model"],
     {"buckets": [100, 500, 1000, 3000, 10000, 30000]}),

    # ── Cache ────────────────────────────────────────────────────────────────
    ("cache_hit_total", Counter if _PROMETHEUS_AVAILABLE else None,
     "Cache hits by cache name",
     ["cache_name"], {}),

    ("cache_miss_total", Counter if _PROMETHEUS_AVAILABLE else None,
     "Cache misses by cache name",
     ["cache_name"], {}),

    # ── Webhooks ─────────────────────────────────────────────────────────────
    ("webhook_received_total", Counter if _PROMETHEUS_AVAILABLE else None,
     "Webhooks received by platform",
     ["platform"], {}),

    ("webhook_processed_total", Counter if _PROMETHEUS_AVAILABLE else None,
     "Webhooks processed by platform and status",
     ["platform", "status"], {}),

    # ── ARC1 Budget Orchestrator ─────────────────────────────────────────────
    ("budget_orchestrator_duration_ms", Histogram if _PROMETHEUS_AVAILABLE else None,
     "BudgetOrchestrator assembly duration in milliseconds",
     ["creator_id"],
     {"buckets": [1, 5, 10, 50, 100]}),

    ("budget_section_truncation_total", Counter if _PROMETHEUS_AVAILABLE else None,
     "Sections truncated by budget orchestrator",
     ["section_name"], {}),

    # Budget utilization metrics (migrated from core/dm/budget/metrics.py)
    ("dm_budget_utilization", Histogram if _PROMETHEUS_AVAILABLE else None,
     "Fraction of token budget used (0-1)",
     ["creator_id"],
     {"buckets": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1]}),

    ("dm_budget_sections_selected", Gauge if _PROMETHEUS_AVAILABLE else None,
     "Number of sections included in assembled context",
     ["creator_id"], {}),

    ("dm_budget_sections_dropped_total", Counter if _PROMETHEUS_AVAILABLE else None,
     "Cumulative sections dropped due to budget",
     ["creator_id", "section_name"], {}),

    ("dm_budget_sections_compressed_total", Counter if _PROMETHEUS_AVAILABLE else None,
     "Cumulative sections compressed due to cap",
     ["creator_id", "section_name"], {}),

    # ── ARC4 / Security ──────────────────────────────────────────────────────
    ("rule_violation_total", Counter if _PROMETHEUS_AVAILABLE else None,
     "Rule violation events",
     ["creator_id", "rule_name"], {}),

    # ── Active conversations ─────────────────────────────────────────────────
    ("active_conversations_gauge", Gauge if _PROMETHEUS_AVAILABLE else None,
     "Active conversations per creator",
     ["creator_id"], {}),
]

# _REGISTRY_META maps metric name → type string for dispatch (avoids isinstance on mocks in tests)
_REGISTRY_META: Dict[str, str] = {}

if _PROMETHEUS_AVAILABLE:
    _TYPE_NAMES = {}
    if _PROMETHEUS_AVAILABLE:
        from prometheus_client import Counter as _Counter, Gauge as _Gauge, Histogram as _Histogram
        _TYPE_NAMES = {_Counter: "Counter", _Histogram: "Histogram", _Gauge: "Gauge"}

    for _name, _cls, _desc, _labels, _kw in _METRIC_SPECS:
        if _cls is None:
            continue
        _m = _create(_cls, _name, _desc, _labels, **_kw)
        if _m is not None:
            _REGISTRY[_name] = _m
            _REGISTRY_META[_name] = _TYPE_NAMES.get(_cls, "Unknown")


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

def emit_metric(name: str, value: Any = 1, **labels: Any) -> None:
    """Emit a metric through the central registry.

    Auto-injects creator_id / lead_id from request context if declared by the
    metric and not already provided by the caller.

    Fail-open: any error (unknown name, bad label, prometheus failure) is logged
    and silently ignored — never raises.

    Usage:
        emit_metric("generation_duration_ms", 450, creator_id="iris", model="gemma-4-31b", status="ok")
        emit_metric("rule_violation_total", rule_name="no_price")
        emit_metric("cache_hit_total", cache_name="rag")
    """
    try:
        # Auto-inject context labels
        from core.observability.middleware import get_context
        ctx = get_context()
        declared = _get_declared_labels(name)
        for k, v in ctx.items():
            if k not in labels and v is not None and k in declared:
                labels[k] = v

        metric = _REGISTRY.get(name)
        if metric is None:
            logger.warning("[emit_metric] Unknown metric: %r", name)
            return

        # Filter to only declared labels (avoid prometheus label mismatch)
        filtered = {k: v for k, v in labels.items() if k in declared}

        metric_type = _REGISTRY_META.get(name, "Counter")
        labeled = metric.labels(**filtered)
        if metric_type == "Histogram":
            labeled.observe(value)
        elif metric_type == "Gauge":
            labeled.set(value)
        else:  # Counter (default)
            labeled.inc(value)
    except Exception as exc:
        logger.error("[emit_metric] Failed for %r: %s", name, exc)


def get_registry_snapshot() -> Dict[str, str]:
    """Return metric name → type string. Used for debugging and contract tests."""
    return dict(_REGISTRY_META)


def get_declared_metric_names() -> List[str]:
    """Return all metric names declared in the registry."""
    return [spec[0] for spec in _METRIC_SPECS]
