from datetime import datetime, timezone

import pytest
from metrics.dashboard import DashboardMetrics, MetricsDashboard


class TestDashboard:
    @pytest.fixture
    def dashboard(self):
        return MetricsDashboard(creator_id="test")

    def test_health_score_perfect(self, dashboard):
        metrics = DashboardMetrics(
            task_completion_rate=1.0,
            csat_average=1.0,
            abandonment_rate=0.0,
            avg_latency_seconds=0.0,
            knowledge_retention=1.0,
            total_conversations=100,
            period_days=30,
            generated_at=datetime.now(timezone.utc),
        )

        score = dashboard.calculate_health_score(metrics)
        assert score == 100.0

    def test_health_score_worst(self, dashboard):
        metrics = DashboardMetrics(
            task_completion_rate=0.0,
            csat_average=0.0,
            abandonment_rate=1.0,
            avg_latency_seconds=10.0,
            knowledge_retention=0.0,
            total_conversations=100,
            period_days=30,
            generated_at=datetime.now(timezone.utc),
        )

        score = dashboard.calculate_health_score(metrics)
        assert score == 0.0

    def test_health_score_moderate(self, dashboard):
        metrics = DashboardMetrics(
            task_completion_rate=0.5,
            csat_average=0.6,
            abandonment_rate=0.3,
            avg_latency_seconds=3.0,
            knowledge_retention=0.7,
            total_conversations=50,
            period_days=30,
            generated_at=datetime.now(timezone.utc),
        )

        score = dashboard.calculate_health_score(metrics)
        assert 30 < score < 80

    def test_to_dict_structure(self, dashboard):
        metrics = DashboardMetrics(
            task_completion_rate=0.7,
            csat_average=0.8,
            abandonment_rate=0.2,
            avg_latency_seconds=2.5,
            knowledge_retention=0.75,
            total_conversations=50,
            period_days=30,
            generated_at=datetime.now(timezone.utc),
        )

        result = dashboard.to_dict(metrics)
        assert "metrics" in result
        assert "summary" in result
        assert "health_score" in result
        assert "task_completion_rate" in result["metrics"]
        assert "csat" in result["metrics"]
        assert "abandonment_rate" in result["metrics"]
        assert "latency" in result["metrics"]
        assert "knowledge_retention" in result["metrics"]

    def test_metric_has_target(self, dashboard):
        metrics = DashboardMetrics(
            task_completion_rate=0.7,
            csat_average=0.8,
            abandonment_rate=0.2,
            avg_latency_seconds=2.5,
            knowledge_retention=0.75,
            total_conversations=50,
            period_days=30,
            generated_at=datetime.now(timezone.utc),
        )

        result = dashboard.to_dict(metrics)
        for metric_data in result["metrics"].values():
            assert "target" in metric_data
            assert "label" in metric_data
            assert "value" in metric_data
