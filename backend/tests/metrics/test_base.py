import pytest
from metrics.base import MetricCategory, MetricResult, MetricsCollector


class TestMetricResult:
    def test_to_dict(self):
        result = MetricResult(
            name="test_metric",
            value=0.85,
            category=MetricCategory.UX,
        )
        d = result.to_dict()
        assert d["name"] == "test_metric"
        assert d["value"] == 0.85
        assert d["category"] == "user_experience"
        assert "timestamp" in d

    def test_all_categories(self):
        assert MetricCategory.COGNITIVE.value == "cognitive"
        assert MetricCategory.QUALITY.value == "quality"
        assert MetricCategory.UX.value == "user_experience"
        assert MetricCategory.ROBUSTNESS.value == "robustness"
        assert MetricCategory.DIALOGUE.value == "dialogue"
        assert MetricCategory.REASONING.value == "reasoning"


class TestMetricsCollector:
    def test_add_and_get_results(self):
        collector = MetricsCollector(creator_id="test")
        result = MetricResult(
            name="test",
            value=0.5,
            category=MetricCategory.UX,
        )
        collector.add_result(result)
        assert len(collector.get_results()) == 1

    def test_get_summary(self):
        collector = MetricsCollector(creator_id="test")
        collector.add_result(MetricResult(name="a", value=1.0, category=MetricCategory.UX))
        collector.add_result(MetricResult(name="a", value=0.5, category=MetricCategory.UX))
        collector.add_result(MetricResult(name="b", value=0.8, category=MetricCategory.QUALITY))

        summary = collector.get_summary()
        assert summary["a"] == 0.75
        assert summary["b"] == 0.8

    def test_collect_raises_not_implemented(self):
        collector = MetricsCollector(creator_id="test")
        with pytest.raises(NotImplementedError):
            collector.collect("some-lead")
