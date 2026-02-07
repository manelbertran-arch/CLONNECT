"""Test edge_case_handler integration in dm_agent_v2 (Step 16)."""

from unittest.mock import MagicMock, patch


class TestEdgeCaseIntegration:
    def test_flag_exists(self):
        from core.dm_agent_v2 import ENABLE_EDGE_CASE_DETECTION

        assert isinstance(ENABLE_EDGE_CASE_DETECTION, bool)

    def test_handler_initialized(self):
        """Edge case handler should be initialized on agent."""
        with patch("core.dm_agent_v2.get_edge_case_handler") as mock_get:
            mock_get.return_value = MagicMock()
            from core.dm_agent_v2 import DMResponderAgentV2

            agent = DMResponderAgentV2.__new__(DMResponderAgentV2)
            agent.config = MagicMock()
            agent.personality = {"name": "test"}
            agent.products = []
            agent.style_prompt = ""
            agent.creator_id = "test"
            agent._init_services()
            assert hasattr(agent, "edge_case_handler")

    def test_detect_returns_result(self):
        from services.edge_case_handler import get_edge_case_handler

        handler = get_edge_case_handler()
        result = handler.detect("hola como estas")
        assert hasattr(result, "edge_type")
        assert hasattr(result, "should_escalate")
        assert hasattr(result, "confidence")

    def test_non_escalation_passes_through(self):
        from services.edge_case_handler import get_edge_case_handler

        handler = get_edge_case_handler()
        result = handler.detect("me interesa tu curso")
        assert not result.should_escalate
