"""
Metrics Dashboard - Unified view of all metrics
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict

from metrics.collectors.abandonment import AbandonmentCollector
from metrics.collectors.csat import CSATCollector
from metrics.collectors.knowledge_retention import KnowledgeRetentionCollector
from metrics.collectors.latency import LatencyCollector
from metrics.collectors.task_completion import TaskCompletionCollector

logger = logging.getLogger(__name__)


@dataclass
class DashboardMetrics:
    """All metrics for dashboard display."""

    task_completion_rate: float
    csat_average: float
    abandonment_rate: float
    avg_latency_seconds: float
    knowledge_retention: float
    total_conversations: int
    period_days: int
    generated_at: datetime


class MetricsDashboard:
    """Unified metrics dashboard."""

    def __init__(self, creator_id: str):
        self.creator_id = creator_id
        self.collectors = {
            "task_completion": TaskCompletionCollector(creator_id),
            "csat": CSATCollector(creator_id),
            "abandonment": AbandonmentCollector(creator_id),
            "latency": LatencyCollector(creator_id),
            "retention": KnowledgeRetentionCollector(creator_id),
        }

    def get_dashboard(self, days: int = 30) -> DashboardMetrics:
        """Get all metrics for dashboard."""
        task_rate = self.collectors["task_completion"].get_aggregate_rate(days)
        csat = self.collectors["csat"].get_average_csat(days)
        abandonment = self.collectors["abandonment"].get_abandonment_rate(days)
        latency = self.collectors["latency"].get_latency_stats(days)

        retention_results = self.collectors["retention"].get_results()
        retention_avg = (
            sum(r.value for r in retention_results) / len(retention_results)
            if retention_results
            else 0.5
        )

        return DashboardMetrics(
            task_completion_rate=task_rate,
            csat_average=csat.get("normalized", 0),
            abandonment_rate=abandonment.get("rate", 0),
            avg_latency_seconds=latency.get("avg", 0),
            knowledge_retention=retention_avg,
            total_conversations=abandonment.get("total", 0),
            period_days=days,
            generated_at=datetime.now(timezone.utc),
        )

    def to_dict(self, metrics: DashboardMetrics) -> Dict[str, Any]:
        """Convert to dict for API response."""
        return {
            "metrics": {
                "task_completion_rate": {
                    "value": metrics.task_completion_rate,
                    "label": "Task Completion",
                    "format": "percent",
                    "target": 0.7,
                },
                "csat": {
                    "value": metrics.csat_average,
                    "label": "Customer Satisfaction",
                    "format": "percent",
                    "target": 0.8,
                },
                "abandonment_rate": {
                    "value": metrics.abandonment_rate,
                    "label": "Abandonment Rate",
                    "format": "percent",
                    "target": 0.2,
                    "inverse": True,
                },
                "latency": {
                    "value": metrics.avg_latency_seconds,
                    "label": "Avg Response Time",
                    "format": "seconds",
                    "target": 3.0,
                    "inverse": True,
                },
                "knowledge_retention": {
                    "value": metrics.knowledge_retention,
                    "label": "Knowledge Retention",
                    "format": "percent",
                    "target": 0.8,
                },
            },
            "summary": {
                "total_conversations": metrics.total_conversations,
                "period_days": metrics.period_days,
                "generated_at": metrics.generated_at.isoformat(),
            },
            "health_score": self.calculate_health_score(metrics),
        }

    def calculate_health_score(self, m: DashboardMetrics) -> float:
        """Calculate overall health score 0-100."""
        weights = {
            "task_completion": 0.25,
            "csat": 0.25,
            "abandonment": 0.20,
            "latency": 0.15,
            "retention": 0.15,
        }

        latency_score = max(0, 1 - (m.avg_latency_seconds / 5))
        abandonment_score = 1 - m.abandonment_rate

        score = (
            m.task_completion_rate * weights["task_completion"]
            + m.csat_average * weights["csat"]
            + abandonment_score * weights["abandonment"]
            + latency_score * weights["latency"]
            + m.knowledge_retention * weights["retention"]
        )

        return round(score * 100, 1)
