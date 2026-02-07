"""
Response Latency Collector
Measures: Time between user message and bot response
"""

import logging
import statistics
from typing import Any, Dict, List

from metrics.base import MetricCategory, MetricResult, MetricsCollector
from sqlalchemy import text

logger = logging.getLogger(__name__)


class LatencyCollector(MetricsCollector):
    """Tracks response latency."""

    def __init__(self, creator_id: str):
        super().__init__(creator_id)
        self.latency_threshold_seconds = 5.0

    def collect(self, lead_id: str) -> List[MetricResult]:
        """Calculate latencies for conversation."""
        from api.database import get_db_session

        with get_db_session() as db:
            result = db.execute(
                text(
                    """
                    SELECT role, created_at
                    FROM messages
                    WHERE lead_id = :lead_id
                    ORDER BY created_at ASC
                    """
                ),
                {"lead_id": lead_id},
            )
            messages = [{"role": row.role, "created_at": row.created_at} for row in result]

        if len(messages) < 2:
            return []

        latencies = []
        for i in range(1, len(messages)):
            prev = messages[i - 1]
            curr = messages[i]

            # Only measure: user message -> bot response
            if prev["role"] == "lead" and curr["role"] != "lead":
                latency = (curr["created_at"] - prev["created_at"]).total_seconds()
                if latency > 0:
                    latencies.append(latency)

        if not latencies:
            return []

        avg_latency = statistics.mean(latencies)
        p95_idx = int(len(latencies) * 0.95)
        p95_latency = sorted(latencies)[p95_idx] if len(latencies) > 1 else latencies[0]

        metric = MetricResult(
            name="response_latency",
            value=avg_latency,
            category=MetricCategory.UX,
            metadata={
                "lead_id": lead_id,
                "avg_seconds": round(avg_latency, 2),
                "p95_seconds": round(p95_latency, 2),
                "min_seconds": round(min(latencies), 2),
                "max_seconds": round(max(latencies), 2),
                "measurements": len(latencies),
                "within_threshold": avg_latency < self.latency_threshold_seconds,
            },
        )

        self.add_result(metric)
        return [metric]

    def get_latency_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get latency statistics from collected results."""
        results = self.get_results()

        if not results:
            return {"avg": 0, "p95": 0, "within_threshold_pct": 0}

        latencies = [r.value for r in results]
        within = [r for r in results if r.metadata.get("within_threshold", False)]

        p95_idx = int(len(latencies) * 0.95)
        return {
            "avg": round(statistics.mean(latencies), 2),
            "p95": (
                round(sorted(latencies)[p95_idx], 2)
                if len(latencies) > 1
                else round(latencies[0], 2)
            ),
            "within_threshold_pct": round(len(within) / len(results) * 100, 1),
        }
