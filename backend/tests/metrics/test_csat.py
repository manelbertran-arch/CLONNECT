import pytest
from metrics.collectors.csat import CSATCollector, CSATRating, generate_csat_prompt


class TestCSAT:
    @pytest.fixture
    def collector(self):
        return CSATCollector(creator_id="test")

    def test_rating_enum_values(self):
        assert CSATRating.VERY_DISSATISFIED.value == 1
        assert CSATRating.VERY_SATISFIED.value == 5

    def test_explicit_rating_normalized(self, collector):
        result = collector.collect_explicit("lead-1", rating=4, feedback="Great!")

        assert result.name == "csat_explicit"
        assert result.value == 0.8  # 4/5
        assert result.metadata["raw_rating"] == 4
        assert result.metadata["feedback"] == "Great!"

    def test_explicit_rating_clamped(self, collector):
        result = collector.collect_explicit("lead-1", rating=10)
        assert result.metadata["raw_rating"] == 5

        result2 = collector.collect_explicit("lead-2", rating=-1)
        assert result2.metadata["raw_rating"] == 1

    def test_positive_patterns_detected(self, collector):
        # Manually test pattern matching
        import re

        text = "genial perfecto increible gracias"
        matches = sum(1 for p in collector.positive_patterns if re.search(p, text, re.IGNORECASE))
        assert matches >= 2

    def test_negative_patterns_detected(self, collector):
        import re

        text = "horrible terrible no sirve"
        matches = sum(1 for p in collector.negative_patterns if re.search(p, text, re.IGNORECASE))
        assert matches >= 2

    def test_generate_csat_prompt(self):
        prompt = generate_csat_prompt()
        assert "1" in prompt
        assert "5" in prompt
