"""
Import safety test — verifies that decomposed modules
can be imported without errors and that backward-compatible
re-exports from the original files still work.
"""

import importlib
import sys
import unittest


class TestDMAgentImportSafety(unittest.TestCase):
    """Test that core.dm.* modules import correctly."""

    def test_import_dm_models(self):
        mod = importlib.import_module("core.dm.models")
        self.assertTrue(hasattr(mod, "AgentConfig"))
        self.assertTrue(hasattr(mod, "DMResponse"))
        self.assertTrue(hasattr(mod, "DetectionResult"))
        self.assertTrue(hasattr(mod, "ContextBundle"))
        self.assertTrue(hasattr(mod, "ENABLE_GUARDRAILS"))

    def test_import_dm_helpers(self):
        mod = importlib.import_module("core.dm.helpers")
        self.assertTrue(hasattr(mod, "apply_voseo"))
        self.assertTrue(hasattr(mod, "NON_CACHEABLE_INTENTS"))
        self.assertTrue(hasattr(mod, "_determine_response_strategy"))
        self.assertTrue(hasattr(mod, "_message_mentions_product"))
        self.assertTrue(hasattr(mod, "_smart_truncate_context"))

    def test_import_dm_detection(self):
        mod = importlib.import_module("core.dm.detection")
        self.assertTrue(hasattr(mod, "phase_detection"))

    def test_import_dm_context(self):
        mod = importlib.import_module("core.dm.context")
        self.assertTrue(hasattr(mod, "phase_memory_and_context"))

    def test_import_dm_generation(self):
        mod = importlib.import_module("core.dm.generation")
        self.assertTrue(hasattr(mod, "phase_llm_generation"))

    def test_import_dm_postprocessing(self):
        mod = importlib.import_module("core.dm.postprocessing")
        self.assertTrue(hasattr(mod, "phase_postprocessing"))

    def test_import_dm_public_api(self):
        mod = importlib.import_module("core.dm.public_api")
        self.assertTrue(hasattr(mod, "get_follower_detail"))
        self.assertTrue(hasattr(mod, "save_manual_message"))

    def test_import_dm_agent(self):
        mod = importlib.import_module("core.dm.agent")
        self.assertTrue(hasattr(mod, "DMResponderAgentV2"))
        self.assertTrue(hasattr(mod, "DMResponderAgent"))
        self.assertTrue(hasattr(mod, "get_dm_agent"))
        self.assertTrue(hasattr(mod, "invalidate_dm_agent_cache"))

    def test_import_dm_package(self):
        """Test that core.dm.__init__ re-exports all symbols."""
        mod = importlib.import_module("core.dm")
        for name in [
            "AgentConfig", "DMResponse", "DMResponderAgent", "DMResponderAgentV2",
            "DetectionResult", "ContextBundle", "Intent",
            "NON_CACHEABLE_INTENTS", "apply_voseo",
            "get_dm_agent", "invalidate_dm_agent_cache",
            "_determine_response_strategy",
        ]:
            self.assertTrue(hasattr(mod, name), f"core.dm missing: {name}")

    def test_backward_compat_dm_agent_v2(self):
        """Test that the original core.dm_agent_v2 re-exports work."""
        mod = importlib.import_module("core.dm_agent_v2")
        for name in [
            "AgentConfig", "DMResponse", "DMResponderAgent", "DMResponderAgentV2",
            "Intent", "NON_CACHEABLE_INTENTS", "apply_voseo",
            "get_dm_agent", "invalidate_dm_agent_cache",
            "ENABLE_GUARDRAILS", "ENABLE_SENSITIVE_DETECTION",
            "ENABLE_VOCABULARY_EXTRACTION", "ENABLE_SELF_CONSISTENCY",
            "ENABLE_RELATIONSHIP_DETECTION", "ENABLE_REFLEXION",
            "ENABLE_QUERY_EXPANSION", "ENABLE_QUESTION_REMOVAL",
            "ENABLE_MESSAGE_SPLITTING", "ENABLE_LEAD_CATEGORIZER",
            "ENABLE_FACT_TRACKING", "ENABLE_EDGE_CASE_DETECTION",
            "ENABLE_DNA_TRIGGERS", "ENABLE_CITATIONS",
            "ENABLE_CONVERSATION_STATE", "ENABLE_QUESTION_CONTEXT",
            "ENABLE_ADVANCED_PROMPTS", "ENABLE_EMAIL_CAPTURE",
            "_determine_response_strategy",
        ]:
            self.assertTrue(hasattr(mod, name), f"core.dm_agent_v2 missing: {name}")


if __name__ == "__main__":
    unittest.main()
