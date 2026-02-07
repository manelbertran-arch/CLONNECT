"""Test self_consistency integration in dm_agent_v2 (Step 21)."""


class TestSelfConsistencyIntegration:
    def test_flag_exists(self):
        from core.dm_agent_v2 import ENABLE_SELF_CONSISTENCY

        assert isinstance(ENABLE_SELF_CONSISTENCY, bool)
        # Default should be False (expensive)
        assert ENABLE_SELF_CONSISTENCY is False

    def test_import_works(self):
        from core.reasoning.self_consistency import get_self_consistency_validator

        assert callable(get_self_consistency_validator)
