"""
Budget metrics emission — Prometheus counters + structured logger fallback.
Consumed by ARC5 observability. Design: ARC1 §2.7 (emit_budget_metrics call).
"""

from __future__ import annotations

import logging
from typing import Any

from core.dm.budget.section import AssembledContext

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter, Gauge, Histogram

    _budget_utilization = Histogram(
        "dm_budget_utilization",
        "Fraction of token budget used (0-1)",
        ["creator_id"],
        buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1],
    )
    _sections_selected = Gauge(
        "dm_budget_sections_selected",
        "Number of sections included in assembled context",
        ["creator_id"],
    )
    _sections_dropped = Counter(
        "dm_budget_sections_dropped_total",
        "Cumulative sections dropped due to budget",
        ["creator_id", "section_name"],
    )
    _sections_compressed = Counter(
        "dm_budget_sections_compressed_total",
        "Cumulative sections compressed due to cap",
        ["creator_id", "section_name"],
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False


def emit_budget_metrics(
    assembled: AssembledContext,
    context: Any,  # DmContext or any object with .creator_id
) -> None:
    """Emit token-budget telemetry. Fails silently to never block the DM pipeline."""
    try:
        creator_id: str = getattr(context, "creator_id", "unknown")

        logger.debug(
            "[BUDGET] creator=%s utilization=%.2f total=%d budget=%d "
            "selected=%d dropped=%d compressed=%d",
            creator_id,
            assembled.utilization,
            assembled.total_tokens,
            assembled.budget_tokens,
            len(assembled.sections_selected),
            len(assembled.sections_dropped),
            len(assembled.sections_compressed),
        )

        if not _PROMETHEUS_AVAILABLE:
            return

        _budget_utilization.labels(creator_id=creator_id).observe(assembled.utilization)
        _sections_selected.labels(creator_id=creator_id).set(
            len(assembled.sections_selected)
        )
        for section in assembled.sections_dropped:
            _sections_dropped.labels(
                creator_id=creator_id, section_name=section.name
            ).inc()
        for section, _ in assembled.sections_compressed:
            _sections_compressed.labels(
                creator_id=creator_id, section_name=section.name
            ).inc()

    except Exception as e:  # never propagate
        logger.debug("[BUDGET] metrics emission failed: %s", e)
