import pytest
from metrics.collectors.knowledge_retention import KnowledgeRetentionCollector


class TestKnowledgeRetention:
    @pytest.fixture
    def collector(self):
        return KnowledgeRetentionCollector(creator_id="test")

    def test_extract_name(self, collector):
        messages = [
            {"content": "Me llamo Carlos", "role": "lead"},
        ]
        facts = collector._extract_facts(messages)
        assert "name" in facts
        assert facts["name"] == "Carlos"

    def test_extract_location(self, collector):
        messages = [
            {"content": "Soy de Madrid", "role": "lead"},
        ]
        facts = collector._extract_facts(messages)
        assert "location" in facts

    def test_extract_interest(self, collector):
        messages = [
            {"content": "Me interesa el coaching", "role": "lead"},
        ]
        facts = collector._extract_facts(messages)
        assert "interest" in facts

    def test_no_facts_from_bot_messages(self, collector):
        messages = [
            {"content": "Me llamo Stefan", "role": "assistant"},
        ]
        facts = collector._extract_facts(messages)
        assert len(facts) == 0

    def test_retention_calculation_full(self, collector):
        messages = [
            {"content": "Me llamo Carlos", "role": "lead"},
            {"content": "Genial!", "role": "assistant"},
            {"content": "Que ofreces?", "role": "lead"},
            {"content": "Carlos, te cuento...", "role": "assistant"},
        ]
        facts = {"name": "Carlos"}
        score = collector._calculate_retention(messages, facts)
        assert score == 1.0  # Bot mentioned Carlos

    def test_retention_calculation_zero(self, collector):
        messages = [
            {"content": "Me llamo Carlos", "role": "lead"},
            {"content": "Genial!", "role": "assistant"},
            {"content": "Que ofreces?", "role": "lead"},
            {"content": "Te cuento sobre el programa", "role": "assistant"},
        ]
        facts = {"name": "Carlos"}
        score = collector._calculate_retention(messages, facts)
        assert score == 0.0  # Bot never mentioned Carlos

    def test_empty_facts(self, collector):
        messages = []
        score = collector._calculate_retention(messages, {})
        assert score == 1.0  # No facts to retain = perfect
