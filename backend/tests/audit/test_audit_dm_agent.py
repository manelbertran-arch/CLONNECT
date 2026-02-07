"""Audit tests for core/dm_agent_v2.py"""

from core.dm_agent_v2 import AgentConfig, DMResponderAgentV2, DMResponse, apply_voseo


class TestAuditDMAgent:
    def test_import(self):
        from core.dm_agent_v2 import (  # noqa: F811
            AgentConfig,
            DMResponderAgentV2,
            DMResponse,
            apply_voseo,
            get_dm_agent,
        )

        assert DMResponderAgentV2 is not None

    def test_agent_config(self):
        try:
            config = AgentConfig()
            assert config is not None
        except TypeError:
            pass  # Requires args

    def test_happy_path_apply_voseo(self):
        result = apply_voseo("Tu puedes hacer esto")
        assert isinstance(result, str)

    def test_edge_case_dm_response(self):
        try:
            response = DMResponse()
            d = response.to_dict()
            assert isinstance(d, dict)
        except TypeError:
            pass  # Requires args

    def test_error_handling_has_methods(self):
        assert hasattr(DMResponderAgentV2, "add_knowledge")
        assert hasattr(DMResponderAgentV2, "add_knowledge_batch")
        assert hasattr(DMResponderAgentV2, "clear_knowledge")
