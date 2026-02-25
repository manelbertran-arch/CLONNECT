"""
Metrics API Router
Provides endpoints for the academic metrics dashboard
"""

import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/dashboard/{creator_id}")
def get_metrics_dashboard(creator_id: str, days: int = 30):
    """Get metrics dashboard for creator."""
    try:
        from metrics.dashboard import MetricsDashboard
        dashboard = MetricsDashboard(creator_id)
        metrics = dashboard.get_dashboard(days)
        return dashboard.to_dict(metrics)
    except Exception as e:
        logger.error(f"Metrics dashboard error for {creator_id}: {e}")
        # Return safe defaults instead of 500
        return {
            "metrics": {
                "task_completion_rate": {"value": 0, "label": "Task Completion", "format": "percent", "target": 0.7},
                "csat": {"value": 0, "label": "Customer Satisfaction", "format": "percent", "target": 0.8},
                "abandonment_rate": {"value": 0, "label": "Abandonment Rate", "format": "percent", "target": 0.2, "inverse": True},
                "latency": {"value": 0, "label": "Avg Response Time", "format": "seconds", "target": 3.0, "inverse": True},
                "knowledge_retention": {"value": 0, "label": "Knowledge Retention", "format": "percent", "target": 0.8},
            },
            "summary": {
                "total_conversations": 0,
                "period_days": days,
                "generated_at": None,
                "error": str(e),
            },
            "health_score": 0,
        }


@router.get("/health/{creator_id}")
def get_health_score(creator_id: str):
    """Get quick health score."""
    try:
        from metrics.dashboard import MetricsDashboard
        dashboard = MetricsDashboard(creator_id)
        metrics = dashboard.get_dashboard(7)
        health = dashboard.calculate_health_score(metrics)
        return {
            "health_score": health,
            "status": "healthy" if health > 70 else "needs_attention",
        }
    except Exception as e:
        logger.error(f"Health score error for {creator_id}: {e}")
        return {
            "health_score": 0,
            "status": "needs_attention",
            "error": str(e),
        }
