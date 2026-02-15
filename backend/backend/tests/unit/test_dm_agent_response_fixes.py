"""Tests for response fixes integration in dm_agent_v2.

Step 3 of cognitive module integration.
Module: core/response_fixes.py
Location: PHASE 5 (after output_validator, before guardrails)
"""


class TestResponseFixesModule:
    """Verify response_fixes module exists and is importable."""

    def test_apply_all_response_fixes_exists(self):
        """apply_all_response_fixes function should exist."""
        from core.response_fixes import apply_all_response_fixes
        assert callable(apply_all_response_fixes)

    def test_apply_all_response_fixes_returns_string(self):
        """apply_all_response_fixes should return a string."""
        from core.response_fixes import apply_all_response_fixes
        result = apply_all_response_fixes("Hola! Como estas? Te cuento sobre el curso.")
        assert isinstance(result, str)


class TestResponseFixesIntegration:
    """Verify integration points in dm_agent_v2."""

    def test_feature_flag_exists(self):
        """ENABLE_RESPONSE_FIXES flag should exist in dm_agent_v2."""
        from core import dm_agent_v2
        assert hasattr(dm_agent_v2, 'ENABLE_RESPONSE_FIXES')

    def test_feature_flag_default_true(self):
        """ENABLE_RESPONSE_FIXES should default to True."""
        from core import dm_agent_v2
        assert dm_agent_v2.ENABLE_RESPONSE_FIXES is True
