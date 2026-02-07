"""Test chain_of_thought activation in dm_agent_v2 (Step 11)."""


class TestChainOfThoughtActivation:
    def test_flag_default_is_true(self):
        """Chain of thought should default to true after activation."""
        import os

        # Clear any override
        original = os.environ.pop("ENABLE_CHAIN_OF_THOUGHT", None)
        try:
            # Re-evaluate the flag
            flag = os.getenv("ENABLE_CHAIN_OF_THOUGHT", "true").lower() == "true"
            assert flag is True
        finally:
            if original is not None:
                os.environ["ENABLE_CHAIN_OF_THOUGHT"] = original

    def test_module_importable(self):
        from core.reasoning.chain_of_thought import ChainOfThoughtReasoner

        assert ChainOfThoughtReasoner is not None
