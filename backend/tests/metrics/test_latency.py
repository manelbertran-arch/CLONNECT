import pytest
from metrics.base import MetricCategory
from metrics.collectors.latency import LatencyCollector


class TestLatency:
    @pytest.fixture
    def collector(self):
        return LatencyCollector(creator_id="test")

    def test_default_threshold(self, collector):
        assert collector.latency_threshold_seconds == 5.0

    def test_latency_stats_empty(self, collector):
        stats = collector.get_latency_stats()
        assert stats["avg"] == 0
        assert stats["p95"] == 0
        assert stats["within_threshold_pct"] == 0

    def test_latency_stats_with_results(self, collector):
        from metrics.base import MetricResult

        # Simulate some results
        for latency_val in [1.0, 2.0, 3.0, 4.0, 5.0]:
            collector.add_result(
                MetricResult(
                    name="response_latency",
                    value=latency_val,
                    category=MetricCategory.UX,
                    metadata={"within_threshold": latency_val < 5.0},
                )
            )

        stats = collector.get_latency_stats()
        assert stats["avg"] == 3.0
        assert stats["within_threshold_pct"] == 80.0
