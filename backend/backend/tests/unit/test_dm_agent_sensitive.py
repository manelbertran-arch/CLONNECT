"""Tests for sensitive content detection integration in dm_agent_v2.

Step 1 of cognitive module integration.
Module: core/sensitive_detector.py
Location: PRE-PIPELINE (before Phase 1)
"""


class TestSensitiveDetectorModule:
    """Verify sensitive_detector module exists and is importable."""

    def test_detect_function_exists(self):
        """detect_sensitive_content function should exist."""
        from core.sensitive_detector import detect_sensitive_content
        assert callable(detect_sensitive_content)

    def test_crisis_resources_function_exists(self):
        """get_crisis_resources function should exist."""
        from core.sensitive_detector import get_crisis_resources
        assert callable(get_crisis_resources)

    def test_detect_returns_result_or_none(self):
        """detect_sensitive_content should return result with attributes or None."""
        from core.sensitive_detector import detect_sensitive_content
        result = detect_sensitive_content("hola que tal")
        # Normal message should return None or low confidence
        if result is not None:
            assert hasattr(result, 'confidence')

    def test_crisis_resources_returns_spanish_text(self):
        """get_crisis_resources should return Spanish crisis resources."""
        from core.sensitive_detector import get_crisis_resources
        result = get_crisis_resources(language="es")
        assert isinstance(result, str)
        assert len(result) > 50  # Should have substantial content


class TestSensitiveDetectorIntegration:
    """Verify integration points in dm_agent_v2."""

    def test_feature_flag_exists(self):
        """ENABLE_SENSITIVE_DETECTION flag should exist in dm_agent_v2."""
        from core import dm_agent_v2
        assert hasattr(dm_agent_v2, 'ENABLE_SENSITIVE_DETECTION')

    def test_feature_flag_default_true(self):
        """ENABLE_SENSITIVE_DETECTION should default to True."""
        from core import dm_agent_v2
        assert dm_agent_v2.ENABLE_SENSITIVE_DETECTION is True
