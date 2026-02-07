"""
Metrics API Router
Provides endpoints for the academic metrics dashboard
"""

from fastapi import APIRouter
from metrics.dashboard import MetricsDashboard

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/dashboard/{creator_id}")
def get_metrics_dashboard(creator_id: str, days: int = 30):
    """Get metrics dashboard for creator."""
    dashboard = MetricsDashboard(creator_id)
    metrics = dashboard.get_dashboard(days)
    return dashboard.to_dict(metrics)


@router.get("/health/{creator_id}")
def get_health_score(creator_id: str):
    """Get quick health score."""
    dashboard = MetricsDashboard(creator_id)
    metrics = dashboard.get_dashboard(7)
    health = dashboard.calculate_health_score(metrics)
    return {
        "health_score": health,
        "status": "healthy" if health > 70 else "needs_attention",
    }
