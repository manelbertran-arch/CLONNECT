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


class TestInstagramHandlerImportSafety(unittest.TestCase):
    """Test that instagram_handler decomposed modules import correctly.

    Note: These tests may be skipped if aiohttp is not installed
    (required by core.instagram which is imported by many modules).
    """

    def _try_import(self, module_name):
        """Import module, skip test if optional dependency missing."""
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError as e:
            if "aiohttp" in str(e) or "cloudinary" in str(e):
                self.skipTest(f"Optional dependency not installed: {e}")
            raise

    def test_import_instagram_handler(self):
        mod = self._try_import("core.instagram_handler")
        self.assertTrue(hasattr(mod, "InstagramHandler"))
        self.assertTrue(hasattr(mod, "InstagramHandlerStatus"))
        self.assertTrue(hasattr(mod, "get_instagram_handler"))

    def test_import_instagram_modules_webhook(self):
        mod = self._try_import("core.instagram_modules.webhook")
        self.assertTrue(hasattr(mod, "handle_webhook_impl"))

    def test_import_instagram_modules_dispatch(self):
        mod = self._try_import("core.instagram_modules.dispatch")
        self.assertTrue(hasattr(mod, "dispatch_response"))

    def test_import_instagram_modules_echo(self):
        mod = self._try_import("core.instagram_modules.echo")
        self.assertTrue(hasattr(mod, "record_creator_manual_response"))
        self.assertTrue(hasattr(mod, "process_reaction_events"))
        self.assertTrue(hasattr(mod, "has_creator_responded_recently"))

    def test_import_instagram_modules_media(self):
        mod = self._try_import("core.instagram_modules.media")
        self.assertTrue(hasattr(mod, "extract_media_info"))
        self.assertTrue(hasattr(mod, "process_message_impl"))

    def test_import_instagram_modules_package(self):
        """Test that core.instagram_modules re-exports all original symbols."""
        mod = self._try_import("core.instagram_modules")
        for name in ["CommentHandler", "LeadManager", "MessageSender", "MessageStore"]:
            self.assertTrue(hasattr(mod, name), f"core.instagram_modules missing: {name}")


class TestCopilotServiceImportSafety(unittest.TestCase):
    """Test that copilot_service decomposed modules import correctly."""

    def test_import_copilot_models(self):
        mod = importlib.import_module("core.copilot.models")
        self.assertTrue(hasattr(mod, "PendingResponse"))
        self.assertTrue(hasattr(mod, "DEBOUNCE_SECONDS"))
        self.assertTrue(hasattr(mod, "is_non_text_message"))

    def test_import_copilot_service(self):
        mod = importlib.import_module("core.copilot.service")
        self.assertTrue(hasattr(mod, "CopilotService"))
        self.assertTrue(hasattr(mod, "get_copilot_service"))

    def test_import_copilot_lifecycle(self):
        mod = importlib.import_module("core.copilot.lifecycle")
        self.assertTrue(hasattr(mod, "create_pending_response_impl"))
        self.assertTrue(hasattr(mod, "get_pending_responses_impl"))

    def test_import_copilot_actions(self):
        mod = importlib.import_module("core.copilot.actions")
        self.assertTrue(hasattr(mod, "approve_response_impl"))
        self.assertTrue(hasattr(mod, "discard_response_impl"))
        self.assertTrue(hasattr(mod, "auto_discard_pending_for_lead_impl"))

    def test_import_copilot_messaging(self):
        mod = importlib.import_module("core.copilot.messaging")
        self.assertTrue(hasattr(mod, "send_message_impl"))
        self.assertTrue(hasattr(mod, "schedule_debounced_regen_impl"))

    def test_import_copilot_package(self):
        """Test that core.copilot.__init__ re-exports all symbols."""
        mod = importlib.import_module("core.copilot")
        for name in [
            "CopilotService", "get_copilot_service",
            "PendingResponse", "DEBOUNCE_SECONDS", "is_non_text_message",
        ]:
            self.assertTrue(hasattr(mod, name), f"core.copilot missing: {name}")

    def test_backward_compat_copilot_service(self):
        """Test that the original core.copilot_service re-exports work."""
        mod = importlib.import_module("core.copilot_service")
        for name in [
            "CopilotService", "get_copilot_service",
            "PendingResponse", "DEBOUNCE_SECONDS", "is_non_text_message",
        ]:
            self.assertTrue(hasattr(mod, name), f"core.copilot_service missing: {name}")


if __name__ == "__main__":
    unittest.main()
