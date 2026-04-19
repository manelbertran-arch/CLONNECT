"""
Budget metrics emission via unified emit_metric channel.

ARC5 Phase 3: migrated from direct prometheus_client calls to emit_metric.
Metric declarations (dm_budget_*) moved to core/observability/metrics.py _REGISTRY.

Consumed by ARC5 observability. Design: ARC1 §2.7 (emit_budget_metrics call).
"""

from __future__ import annotations

import logging
from typing import Any

from core.dm.budget.section import AssembledContext
from core.observability.metrics import emit_metric

logger = logging.getLogger(__name__)


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

        emit_metric("dm_budget_utilization", assembled.utilization, creator_id=creator_id)
        emit_metric("dm_budget_sections_selected", len(assembled.sections_selected), creator_id=creator_id)

        for section in assembled.sections_dropped:
            emit_metric(
                "dm_budget_sections_dropped_total",
                creator_id=creator_id,
                section_name=section.name,
            )
        for section, _ in assembled.sections_compressed:
            emit_metric(
                "dm_budget_sections_compressed_total",
                creator_id=creator_id,
                section_name=section.name,
            )

    except Exception as e:  # never propagate
        logger.debug("[BUDGET] metrics emission failed: %s", e)
