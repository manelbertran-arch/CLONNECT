"""
Migration tests - Verify dm_agent_v2 works as drop-in replacement.
Written BEFORE migration (TDD).
"""
import pytest


class TestMigrationImports:
    """Test that V2 can be imported with V1 alias."""

    def test_v2_importable_as_v1_alias(self):
        """V2 should be importable with DMResponderAgent alias."""
        from core.dm_agent_v2 import DMResponderAgentV2 as DMResponderAgent
        assert DMResponderAgent is not None

    def test_v2_instantiable_with_v1_interface(self):
        """V2 should instantiate with same interface as V1."""
        from core.dm_agent_v2 import DMResponderAgentV2 as DMResponderAgent
        agent = DMResponderAgent(creator_id="test_creator")
        assert agent is not None
        assert agent.creator_id == "test_creator"

    def test_v2_has_required_methods(self):
        """V2 should have all required public methods."""
        from core.dm_agent_v2 import DMResponderAgentV2 as DMResponderAgent
        agent = DMResponderAgent(creator_id="test")

        # Required methods
        assert hasattr(agent, 'process_dm')
        assert hasattr(agent, 'add_knowledge')
        assert hasattr(agent, 'get_stats')

    def test_v2_has_all_services(self):
        """V2 should have all required services initialized."""
        from core.dm_agent_v2 import DMResponderAgentV2 as DMResponderAgent
        agent = DMResponderAgent(creator_id="test")

        # Required services
        assert hasattr(agent, 'intent_classifier')
        assert hasattr(agent, 'prompt_builder')
        assert hasattr(agent, 'memory_store')
        assert hasattr(agent, 'semantic_rag')
        assert hasattr(agent, 'llm_service')
        assert hasattr(agent, 'lead_service')
        assert hasattr(agent, 'instagram_service')


class TestMigrationCompatibility:
    """Test V2 compatibility with expected V1 behavior."""

    def test_add_knowledge_returns_id(self):
        """add_knowledge should return document ID."""
        from core.dm_agent_v2 import DMResponderAgentV2 as DMResponderAgent
        agent = DMResponderAgent(creator_id="test")

        doc_id = agent.add_knowledge("Test content")
        assert doc_id is not None
        assert isinstance(doc_id, str)

    def test_get_stats_returns_dict(self):
        """get_stats should return dictionary with expected keys."""
        from core.dm_agent_v2 import DMResponderAgentV2 as DMResponderAgent
        agent = DMResponderAgent(creator_id="test")

        stats = agent.get_stats()
        assert isinstance(stats, dict)
        assert 'llm' in stats
        assert 'rag' in stats
        assert 'memory' in stats

    def test_health_check_all_healthy(self):
        """health_check should return all services healthy."""
        from core.dm_agent_v2 import DMResponderAgentV2 as DMResponderAgent
        agent = DMResponderAgent(creator_id="test")

        health = agent.health_check()
        assert isinstance(health, dict)
        assert all(v is True for v in health.values())
