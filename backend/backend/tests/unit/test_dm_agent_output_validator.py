"""Tests for output validation integration in dm_agent_v2.

Step 2 of cognitive module integration.
Module: core/output_validator.py
Location: PHASE 5 (post-LLM, before guardrails)
"""


class TestOutputValidatorModule:
    """Verify output_validator module exists and is importable."""

    def test_validate_prices_function_exists(self):
        """validate_prices function should exist."""
        from core.output_validator import validate_prices
        assert callable(validate_prices)

    def test_validate_links_function_exists(self):
        """validate_links function should exist."""
        from core.output_validator import validate_links
        assert callable(validate_links)

    def test_validate_prices_returns_list(self):
        """validate_prices should return list of issues."""
        from core.output_validator import validate_prices
        result = validate_prices("El precio es 100€", {"producto": 100.0})
        assert isinstance(result, list)

    def test_validate_links_returns_tuple(self):
        """validate_links should return tuple of (issues, corrected)."""
        from core.output_validator import validate_links
        result = validate_links("Visita https://stripe.com/pay", [])
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestOutputValidatorIntegration:
    """Verify integration points in dm_agent_v2."""

    def test_feature_flag_exists(self):
        """ENABLE_OUTPUT_VALIDATION flag should exist in dm_agent_v2."""
        from core import dm_agent_v2
        assert hasattr(dm_agent_v2, 'ENABLE_OUTPUT_VALIDATION')

    def test_feature_flag_default_true(self):
        """ENABLE_OUTPUT_VALIDATION should default to True."""
        from core import dm_agent_v2
        assert dm_agent_v2.ENABLE_OUTPUT_VALIDATION is True
